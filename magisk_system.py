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
import json
import logging
import os
import re

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


def _list_databin(device: str, env: dict) -> list[str]:
    """Names currently inside ``/adb/magisk`` (empty if the dir is absent)."""
    out = _es._run([_es._debugfs(), "-R", "ls -l %s" % _DATABIN, device],
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


def _clean_commands(device: str, env: dict) -> list[str]:
    """debugfs commands to remove whatever is *actually* in ``/adb/magisk`` and
    then the dir -- covers a prior/foreign install, not just our own names."""
    cmds = ["rm %s/%s" % (_DATABIN, n) for n in _list_databin(device, env)]
    cmds.append("rmdir %s" % _DATABIN)
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
        out = _es._run_script(dev, _clean_commands(dev, env) + _write_commands(tools), env)
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
                _es._run_script(dev, _clean_commands(dev, env), env)
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
        _es._run_script(dev, _clean_commands(dev, env), env)  # enumerate-based removal
        if "Inode:" in _es._stat_path(dev, _DATABIN, env):
            raise RuntimeError("failed to remove %s" % _DATABIN)
        if not _es._fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after removing DATABIN")
    _clear_manifest(instance_dir)
    return ["Removed /data/adb/magisk"]
