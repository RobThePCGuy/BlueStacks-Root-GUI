"""Offline staging of Magisk's DATABIN (``/data/adb/magisk``) into a shut-down
instance's ``Data.vhdx`` -- Phase 1 of the full Magisk-to-system install.

Why this exists
---------------
Magisk's daemon aborts at ``post-fs-data`` with *"environment incomplete"*
unless ``/data/adb/magisk`` holds an executable ``busybox`` (the daemon does
``access(DATABIN "/busybox", X_OK)``; see topjohnwu/Magisk ``magisk_env()``).
The normal installer can't populate this root-owned dir from within the guest
without an already-running root, a chicken-and-egg on BlueStacks.  We sidestep
it entirely: write the files **offline**, host-side, straight into the ext4
inside ``Data.vhdx`` with root ownership set in the filesystem metadata -- no
running guest, no ADB, no live root.

How it works
------------
``Data.vhdx`` holds the guest ``/data`` ext4 (the fs root ``/`` maps to
``/data``, so ``/data/adb`` is ext4 path ``/adb``).  We reuse ``ext4_symlink``'s
proven recipe: ``diskpart``-attach the vhdx so Windows materialises a real disk,
run bundled ``debugfs`` against the ext4 partition to (re)create
``/adb/magisk`` and ``write`` the tools with ``root:root`` + ``0755``,
``e2fsck``-verify, and detach.  ``/data/adb`` already exists on a booted-once
instance, so we only add ``magisk/`` under it.

Safety
------
- Every tool is stat-verified after writing, not just busybox -- a partial stage
  never reports success.
- On any failure the partial DATABIN is rolled back (removed), so a failed
  install is not a one-way door.
- The cleanup enumerates the dir's *actual* contents, so a prior/foreign Magisk
  install is fully replaced rather than leaving orphans.
- A host-side manifest (``.magisk_system.json`` next to Data.vhdx) records what
  was staged (payload hash + tools) as a provenance/reversal stamp.

Requirements: Windows, Administrator (raw-disk access + diskpart), instance shut
down (``Data.vhdx`` not locked).  SELinux is Disabled on BlueStacks guests, so no
policy work is needed; we still set the ``adb_data_file`` context for correctness.
"""
from __future__ import annotations

import datetime
import gzip
import json
import logging
import os
import re
import sys
import tempfile

import ext4_symlink as _es  # reuse attach/debugfs/e2fsck machinery
import magisk_payload as _mp

logger = logging.getLogger(__name__)

# ext4 path of DATABIN inside Data.vhdx (fs root == guest /data).
_DATABIN = "/adb/magisk"
_SELINUX_CTX = "u:object_r:adb_data_file:s0"
_MANIFEST_NAME = ".magisk_system.json"  # host sidecar next to Data.vhdx

# Tools that must be executable in DATABIN. busybox is the daemon's hard gate.
_EXEC_TOOLS = ("busybox", "magisk32", "magisk64", "magiskinit", "magiskpolicy", "magiskboot")

# debugfs output substrings that mean a command in the script failed.
_ERR_MARKERS = ("File not found", "no such", "Invalid", "Bad ", "No space",
                "not enough", "Could not", "error while")

# --- System-mode install (into Root.vhd's /android/system) ------------------
# Captured, version-pinned assets that Magisk's own "Install to System" produces
# but which aren't in the APK: the boot-sequence rc, the original backup, and
# the tiny config. Kept in lockstep with the pinned APK version.
_ASSET_SUBDIR = "kitsune-27.001"
# Guest system tree lives at /android/system inside Root.vhd (Data.vhdx is /data).
_SYSTEM_ROOTS = ("/android/system", "/system")
# Magisk binaries the system install pulls from the payload (not busybox/boot).
_SYS_MAGISK_BINS = ("magisk32", "magisk64", "magiskinit", "magiskpolicy")


def _data_vhdx(instance_dir: str) -> str:
    return os.path.join(instance_dir, "Data.vhdx")


def _manifest_path(instance_dir: str) -> str:
    return os.path.join(instance_dir, _MANIFEST_NAME)


def _cygpath(win_path: str) -> str:
    """Windows path -> Cygwin path, so the Cygwin ``debugfs`` can open a host
    file as a ``write`` source (``C:\\x\\y`` -> ``/cygdrive/c/x/y``)."""
    p = os.path.abspath(win_path)
    drive, rest = os.path.splitdrive(p)
    rest = rest.replace("\\", "/")
    if drive:
        return "/cygdrive/%s%s" % (drive[0].lower(), rest)
    return rest


def _dq(path: str) -> str:
    """Double-quote a path for a debugfs script argument, so a host path with a
    space (a Windows profile like ``C:\\Users\\John Doe\\...``) survives debugfs's
    whitespace tokenizer.  Our paths never contain a double-quote."""
    return '"%s"' % path


def _errtail(out: str) -> str:
    """Pull the debugfs error lines out of script output for a useful message."""
    lines = [ln.strip() for ln in out.splitlines()
             if any(m.lower() in ln.lower() for m in _ERR_MARKERS)]
    return " | ".join(lines[-6:]) if lines else (out.strip()[-200:] or "(no output)")


def _list_dir(device: str, ext4_dir: str, env: dict) -> list[str]:
    """Names currently inside ``ext4_dir`` (empty if it's absent)."""
    out = _es._run([_es._debugfs(), "-R", "ls -l %s" % ext4_dir, device],
                   env=env).stdout or ""
    names: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        # symlink lines read "... name -> target"; take the name, not the target
        name = parts[parts.index("->") - 1] if "->" in parts else parts[-1]
        if name in (".", ".."):
            continue
        names.append(name)
    return names


def _clean_dir_commands(device: str, ext4_dir: str, env: dict) -> list[str]:
    """debugfs commands to remove whatever is *actually* in ``ext4_dir`` and then
    the dir itself -- covers a prior/foreign install, not just our own names."""
    cmds = ["rm %s/%s" % (ext4_dir, n) for n in _list_dir(device, ext4_dir, env)]
    cmds.append("rmdir %s" % ext4_dir)
    return cmds


def _write_commands(tools: dict[str, str]) -> list[str]:
    """Pure command list that (re)creates ``/adb/magisk`` and writes ``tools``
    root-owned.  Pure (no disk) so the debugfs quirks stay unit-testable:
    ``write`` links its dest as a *bare filename in the CWD*, so we ``cd`` in
    first and write bare names; the source path is quoted for spaces."""
    cmds = ["mkdir %s" % _DATABIN, "sif %s mode 040700" % _DATABIN,
            "sif %s uid 0" % _DATABIN, "sif %s gid 0" % _DATABIN,
            "cd %s" % _DATABIN]
    for name, hostpath in sorted(tools.items()):
        dst = "%s/%s" % (_DATABIN, name)
        mode = "0100755" if name in _EXEC_TOOLS else "0100644"
        cmds += ["write %s %s" % (_dq(_cygpath(hostpath)), name),  # quoted src, bare dest
                 "sif %s mode %s" % (dst, mode),                   # full path OK for sif
                 "sif %s uid 0" % dst, "sif %s gid 0" % dst]
    cmds.append("ea_set %s security.selinux %s" % (_DATABIN, _SELINUX_CTX))
    return cmds


def _verify_staged(device: str, tools: dict[str, str], env: dict) -> list[str]:
    """Return the names of tools that are NOT correctly staged (regular file,
    root-owned, expected mode).  Empty list == every tool verified."""
    bad: list[str] = []
    for name in tools:
        st = _es._stat_path(device, "%s/%s" % (_DATABIN, name), env)
        want = "0755" if name in _EXEC_TOOLS else "0644"
        ok = ("Inode:" in st and "Type: regular" in st
              and re.search(r"Mode:\s+%s\b" % want, st)
              and re.search(r"User:\s+0\b", st) and re.search(r"Group:\s+0\b", st))
        if not ok:
            bad.append(name)
    return bad


def _write_manifest(instance_dir: str, tools: dict[str, str]) -> None:
    data = {
        "databin": "/data/adb/magisk",
        "payload": _mp.PAYLOAD_NAME,
        "payload_sha256": _mp.PAYLOAD_SHA256,
        "tools": sorted(tools),
        "staged_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with open(_manifest_path(instance_dir), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:  # a missing stamp must not fail a good install
        logger.warning("could not write Magisk manifest: %s", exc)


def _clear_manifest(instance_dir: str) -> None:
    try:
        os.unlink(_manifest_path(instance_dir))
    except OSError:
        pass


def stage_databin(instance_dir: str, tools: dict[str, str], progress=None) -> list[str]:
    """Write Magisk's DATABIN (``/data/adb/magisk``) into the instance's Data.vhdx.

    ``tools`` maps tool name -> host file path (from ``magisk_payload.extract_tools``).
    All-or-nothing: every tool is verified, and a failure rolls back the partial
    DATABIN.  Returns status lines; raises on hard failure.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    vhdx = _data_vhdx(instance_dir)
    if not _es.tools_available():
        raise RuntimeError("bundled e2fsprogs (debugfs) not found")
    if not os.path.isfile(vhdx):
        raise RuntimeError("Data.vhdx not found in %s" % instance_dir)
    if "busybox" not in tools:
        raise RuntimeError("payload missing busybox (the daemon's environment gate)")

    env = _es._tool_env()
    _p("Attaching Data.vhdx (staging Magisk binaries)...")
    with _es._Attached(vhdx) as att:
        dev = att.device
        _p("Writing %d tools into %s..." % (len(tools), _DATABIN))
        out = _es._run_script(dev, _clean_dir_commands(dev, _DATABIN, env) + _write_commands(tools), env)
        try:
            bad = _verify_staged(dev, tools, env)
            if bad:
                raise RuntimeError(
                    "staging incomplete -- not correctly written: %s (debugfs: %s)"
                    % (", ".join(sorted(bad)), _errtail(out)))
            _p("Verifying filesystem (e2fsck)...")
            if not _es._fsck_ok(dev, env):
                raise RuntimeError("e2fsck reported errors after staging")
        except Exception:
            _p("Staging failed -- rolling back /data/adb/magisk...")
            try:
                _es._run_script(dev, _clean_dir_commands(dev, _DATABIN, env), env)
            except Exception:
                logger.exception("rollback cleanup also failed")
            raise
    _write_manifest(instance_dir, tools)
    return ["Staged %d Magisk tools into /data/adb/magisk (all verified, busybox gate OK)"
            % len(tools)]


def unstage_databin(instance_dir: str, progress=None) -> list[str]:
    """Remove ``/data/adb/magisk`` (and its manifest) from a shut-down Data.vhdx."""
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    vhdx = _data_vhdx(instance_dir)
    if not _es.tools_available() or not os.path.isfile(vhdx):
        return ["e2fsprogs/Data.vhdx unavailable -- nothing to remove"]
    env = _es._tool_env()
    _p("Attaching Data.vhdx (removing Magisk binaries)...")
    with _es._Attached(vhdx) as att:
        dev = att.device
        _es._run_script(dev, _clean_dir_commands(dev, _DATABIN, env), env)  # enumerate-based removal
        if "Inode:" in _es._stat_path(dev, _DATABIN, env):
            raise RuntimeError("failed to remove %s" % _DATABIN)
        if not _es._fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after removing DATABIN")
    _clear_manifest(instance_dir)
    return ["Removed /data/adb/magisk"]


# --------------------------------------------------------------------------
# System-mode install: write Magisk's /system footprint into Root.vhd offline.
# --------------------------------------------------------------------------

def _asset_dir() -> str:
    """Directory holding the captured, version-pinned system-install assets
    (config, bootanim.rc, bootanim.rc.gz)."""
    if getattr(sys, "frozen", False):  # PyInstaller onefile
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "magisk_assets", _ASSET_SUBDIR)


def _find_system_root(device: str, env: dict) -> str:
    """ext4 path of the guest system tree (/android/system or /system) --
    whichever actually holds etc/init inside Root.vhd."""
    for root in _SYSTEM_ROOTS:
        if "Inode:" in _es._stat_path(device, "%s/etc/init" % root, env):
            return root
    raise RuntimeError("guest system tree (etc/init) not found in Root.vhd")


def _system_write_commands(sysroot: str, srcs: dict[str, str]) -> list[str]:
    """Pure debugfs command list writing Magisk's system-mode footprint under
    ``sysroot``.  ``srcs`` maps each footprint file to its host source path.

    Footprint (exactly what Magisk's own Install-to-System writes):
      <sysroot>/etc/init/magisk/{config,magisk32,magisk64,magiskinit,
                                 magiskpolicy,stub.apk}   0700 root:root
      <sysroot>/etc/init/bootanim.rc                      0664 system:system
      <sysroot>/etc/init/bootanim.rc.gz                   0600 root:root
    """
    initdir = "%s/etc/init" % sysroot
    magiskdir = "%s/magisk" % initdir
    cmds = ["mkdir %s" % magiskdir, "sif %s mode 040700" % magiskdir,
            "sif %s uid 0" % magiskdir, "sif %s gid 0" % magiskdir,
            "cd %s" % magiskdir]
    for name in ("config",) + _SYS_MAGISK_BINS + ("stub.apk",):
        dst = "%s/%s" % (magiskdir, name)
        cmds += ["write %s %s" % (_dq(_cygpath(srcs[name])), name),  # quoted src, bare dest
                 "sif %s mode 0100700" % dst, "sif %s uid 0" % dst, "sif %s gid 0" % dst]
    # bootanim.rc replaces the stock service file; bootanim.rc.gz backs up the
    # original so uninstall can restore it.
    bo = "%s/bootanim.rc" % initdir
    boz = "%s/bootanim.rc.gz" % initdir
    cmds += ["cd %s" % initdir, "rm bootanim.rc",
             "write %s bootanim.rc" % _dq(_cygpath(srcs["bootanim.rc"])),
             "sif %s mode 0100664" % bo, "sif %s uid 1000" % bo, "sif %s gid 1000" % bo,
             "write %s bootanim.rc.gz" % _dq(_cygpath(srcs["bootanim.rc.gz"])),
             "sif %s mode 0100600" % boz, "sif %s uid 0" % boz, "sif %s gid 0" % boz]
    return cmds


def _system_app_commands(sysroot: str, apk_src: str) -> list[str]:
    """debugfs commands to preinstall the full Magisk manager as a system app at
    ``<sysroot>/app/KitsuneMask/KitsuneMask.apk``.

    Magisk's Install-to-System only writes a *stub* manager that self-downloads
    the full UI from an (abandoned) URL -> it comes up greyed/non-functional
    offline.  Shipping the real, pinned APK as a preinstalled system app means
    PackageManager installs a working manager at boot, before magiskd's
    boot-complete stub check, so no stub is ever needed.
    """
    appdir = "%s/app/KitsuneMask" % sysroot
    dst = "%s/KitsuneMask.apk" % appdir
    return ["rm %s" % dst, "rmdir %s" % appdir,          # clean any prior copy
            "mkdir %s" % appdir, "sif %s mode 040755" % appdir,
            "sif %s uid 1000" % appdir, "sif %s gid 1000" % appdir,
            "cd %s" % appdir,
            "write %s KitsuneMask.apk" % _dq(_cygpath(apk_src)),  # quoted src, bare dest
            "sif %s mode 0100644" % dst, "sif %s uid 1000" % dst, "sif %s gid 1000" % dst]


def install_to_system(instance_dir: str, tools: dict[str, str], stub_path: str,
                      manager_apk: str | None = None, progress=None) -> list[str]:
    """Write Magisk's system-mode footprint into the instance's Root.vhd offline.

    ``tools`` provides the magisk binaries (magisk_payload.extract_tools);
    ``stub_path`` is stub.apk (magisk_payload.extract_stub_apk); config +
    bootanim.rc + bootanim.rc.gz come from the pinned captured assets.
    All-or-nothing: a partial magisk/ dir is rolled back on failure.
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    root_vhd = os.path.join(instance_dir, "Root.vhd")
    if not _es.tools_available():
        raise RuntimeError("bundled e2fsprogs (debugfs) not found")
    if not os.path.isfile(root_vhd):
        raise RuntimeError("Root.vhd not found in %s (system install needs the "
                           "classic Root.vhd system image)" % instance_dir)
    assets = _asset_dir()
    srcs = {"config": os.path.join(assets, "config"),
            "bootanim.rc": os.path.join(assets, "bootanim.rc"),
            "bootanim.rc.gz": os.path.join(assets, "bootanim.rc.gz"),
            "stub.apk": stub_path}
    for name in _SYS_MAGISK_BINS:
        if name not in tools:
            raise RuntimeError("payload missing %s" % name)
        srcs[name] = tools[name]
    for name, path in srcs.items():
        if not os.path.isfile(path):
            raise RuntimeError("missing source for %s: %s" % (name, path))
    if manager_apk and not os.path.isfile(manager_apk):
        raise RuntimeError("manager APK not found: %s" % manager_apk)

    env = _es._tool_env()
    _p("Attaching Root.vhd (installing Magisk to /system)...")
    with _es._Attached(root_vhd) as att:
        dev = att.device
        sysroot = _find_system_root(dev, env)
        magiskdir = "%s/etc/init/magisk" % sysroot
        appdir = "%s/app/KitsuneMask" % sysroot
        _p("Writing Magisk system files under %s/etc/init ..." % sysroot)
        script = _clean_dir_commands(dev, magiskdir, env) + _system_write_commands(sysroot, srcs)
        if manager_apk:
            _p("Preinstalling the full Kitsune manager as a system app...")
            script += _system_app_commands(sysroot, manager_apk)
        out = _es._run_script(dev, script, env)
        try:
            checks = ["%s/config" % magiskdir, "%s/magisk64" % magiskdir,
                      "%s/stub.apk" % magiskdir, "%s/etc/init/bootanim.rc" % sysroot]
            if manager_apk:
                checks.append("%s/KitsuneMask.apk" % appdir)
            for path in checks:
                if "Inode:" not in _es._stat_path(dev, path, env):
                    raise RuntimeError("system install incomplete: missing %s (debugfs: %s)"
                                       % (path, _errtail(out)))
            _p("Verifying filesystem (e2fsck)...")
            if not _es._fsck_ok(dev, env):
                raise RuntimeError("e2fsck reported errors after system install")
        except Exception:
            _p("System install failed -- rolling back...")
            try:
                rb = _clean_dir_commands(dev, magiskdir, env)
                if manager_apk:
                    rb += _clean_dir_commands(dev, appdir, env)
                _es._run_script(dev, rb, env)
            except Exception:
                logger.exception("rollback cleanup also failed")
            raise
    return ["Installed Magisk system files into %s/etc/init" % sysroot]


def uninstall_from_system(instance_dir: str, progress=None) -> list[str]:
    """Remove Magisk's system-mode footprint from Root.vhd and restore the stock
    bootanim.rc from the pinned original."""
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    root_vhd = os.path.join(instance_dir, "Root.vhd")
    if not _es.tools_available() or not os.path.isfile(root_vhd):
        return ["e2fsprogs/Root.vhd unavailable -- nothing to remove"]

    # Decompress the pinned original bootanim.rc so we can restore it (debugfs
    # can't gunzip). The captured .gz is BlueStacks' generic stock service file.
    original = None
    gzpath = os.path.join(_asset_dir(), "bootanim.rc.gz")
    if os.path.isfile(gzpath):
        fd, original = tempfile.mkstemp(suffix="-bootanim.rc")
        with os.fdopen(fd, "wb") as out, gzip.open(gzpath, "rb") as src:
            out.write(src.read())

    env = _es._tool_env()
    _p("Attaching Root.vhd (removing Magisk system files)...")
    try:
        with _es._Attached(root_vhd) as att:
            dev = att.device
            sysroot = _find_system_root(dev, env)
            initdir = "%s/etc/init" % sysroot
            magiskdir = "%s/magisk" % initdir
            appdir = "%s/app/KitsuneMask" % sysroot
            cmds = _clean_dir_commands(dev, magiskdir, env) + _clean_dir_commands(dev, appdir, env)
            cmds += ["rm %s/bootanim.rc.gz" % initdir]
            if original:  # restore the stock bootanim service
                bo = "%s/bootanim.rc" % initdir
                cmds += ["cd %s" % initdir, "rm bootanim.rc",
                         "write %s bootanim.rc" % _dq(_cygpath(original)),
                         "sif %s mode 0100664" % bo, "sif %s uid 1000" % bo,
                         "sif %s gid 1000" % bo]
            _es._run_script(dev, cmds, env)
            if "Inode:" in _es._stat_path(dev, magiskdir, env):
                raise RuntimeError("failed to remove %s" % magiskdir)
            if not _es._fsck_ok(dev, env):
                raise RuntimeError("e2fsck reported errors after removing system files")
    finally:
        if original:
            try:
                os.unlink(original)
            except OSError:
                pass
    return ["Removed Magisk system files"]
