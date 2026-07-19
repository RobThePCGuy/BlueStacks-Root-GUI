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
``/data``, so ``/data/adb`` is ext4 path ``/adb``).  We reuse
``ext4_symlink``'s proven recipe: ``diskpart``-attach the vhdx so Windows
materialises a real disk, run bundled ``debugfs`` against the ext4 partition to
``mkdir /adb/magisk`` and ``write`` the tools with ``root:root`` + ``0755``,
``e2fsck``-verify, and detach.  ``/data/adb`` already exists (``0700 root:root``,
context ``adb_data_file``) on a booted-once instance, so we only add ``magisk/``
under it.

Requirements: Windows, Administrator (raw-disk access + diskpart), instance shut
down (``Data.vhdx`` not locked).  SELinux is Disabled on BlueStacks guests, so
no policy work is needed; we still set the ``adb_data_file`` context to match the
parent for correctness on any enforcing setup.
"""
from __future__ import annotations

import logging
import os
import tempfile

import ext4_symlink as _es  # reuse attach/debugfs/e2fsck machinery

logger = logging.getLogger(__name__)

# ext4 path of DATABIN inside Data.vhdx (fs root == guest /data).
_ADB_DIR = "/adb"
_DATABIN = "/adb/magisk"
_SELINUX_CTX = "u:object_r:adb_data_file:s0"

# Tools that must be executable in DATABIN. busybox is the daemon's hard gate.
_EXEC_TOOLS = ("busybox", "magisk32", "magisk64", "magiskinit", "magiskpolicy", "magiskboot")


def _data_vhdx(instance_dir: str) -> str:
    return os.path.join(instance_dir, "Data.vhdx")


def _cygpath(win_path: str) -> str:
    """Windows path -> Cygwin path, so the Cygwin ``debugfs`` can open a host
    file as a ``write`` source (``C:\\x\\y`` -> ``/cygdrive/c/x/y``)."""
    p = os.path.abspath(win_path)
    drive, rest = os.path.splitdrive(p)
    rest = rest.replace("\\", "/")
    if drive:
        return "/cygdrive/%s%s" % (drive[0].lower(), rest)
    return rest


def _run_debugfs_script(device: str, lines: list[str], env: dict) -> str:
    """Run a -w debugfs command script against ``device``; return combined output."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\nquit\n")
        r = _es._run([_es._debugfs(), "-w", "-f", path, device], env=env)
        return (r.stdout or "") + (r.stderr or "")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _stat(device: str, ext4_path: str, env: dict) -> str:
    return _es._run([_es._debugfs(), "-R", "stat %s" % ext4_path, device],
                    env=env).stdout or ""


def _stage_commands(tools: dict[str, str]) -> list[str]:
    """Build the debugfs command list that (re)creates ``/data/adb/magisk`` and
    writes ``tools`` into it root-owned.

    Kept pure (no disk) so the debugfs quirks are unit-testable: ``write`` links
    its dest as a *bare filename in the CWD*, so we ``cd`` into the dir first and
    write bare names; ``sif`` resolves full paths fine.
    """
    cmds = ["rm %s/%s" % (_DATABIN, n) for n in sorted(tools)]  # best-effort clean
    cmds += ["rmdir %s" % _DATABIN, "mkdir %s" % _DATABIN,
             "sif %s mode 040700" % _DATABIN,
             "sif %s uid 0" % _DATABIN, "sif %s gid 0" % _DATABIN,
             "cd %s" % _DATABIN]
    for name, hostpath in sorted(tools.items()):
        dst = "%s/%s" % (_DATABIN, name)
        mode = "0100755" if name in _EXEC_TOOLS else "0100644"
        cmds += ["write %s %s" % (_cygpath(hostpath), name),  # bare name -> CWD
                 "sif %s mode %s" % (dst, mode),              # full path OK for sif
                 "sif %s uid 0" % dst, "sif %s gid 0" % dst]
    # Best-effort SELinux context (harmless: guest SELinux is Disabled).
    cmds += ["ea_set %s security.selinux %s" % (_DATABIN, _SELINUX_CTX)]
    return cmds


def stage_databin(instance_dir: str, tools: dict[str, str], progress=None) -> list[str]:
    """Write Magisk's DATABIN (``/data/adb/magisk``) into the instance's Data.vhdx.

    ``tools`` maps tool name -> host file path (from ``magisk_payload.extract_tools``).
    Idempotent: an existing ``/adb/magisk`` is replaced.  Returns status lines;
    raises on hard failure (missing tools/disk, verification failure).
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
    results: list[str] = []
    _p("Attaching Data.vhdx (staging Magisk binaries)...")
    with _es._Attached(vhdx) as att:
        dev = att.device

        _p("Writing %d tools into %s..." % (len(tools), _DATABIN))
        _run_debugfs_script(dev, _stage_commands(tools), env)

        # Verify the gate: busybox present, regular file, executable, root-owned.
        st = _stat(dev, "%s/busybox" % _DATABIN, env)
        if "Inode:" not in st or "Type: regular" not in st or "0755" not in st:
            raise RuntimeError("busybox not staged executable in %s (stat: %s)"
                               % (_DATABIN, st[:200]))
        _p("Verifying filesystem (e2fsck)...")
        if not _es._fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after staging")
        results.append("Staged %d Magisk tools into /data/adb/magisk (busybox gate OK)"
                       % len(tools))
    return results


def unstage_databin(instance_dir: str, progress=None) -> list[str]:
    """Remove ``/data/adb/magisk`` from a shut-down instance's Data.vhdx."""
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
        # debugfs has no recursive rm: unlink known files, then rmdir the dir.
        cmds = ["rm %s/%s" % (_DATABIN, n) for n in
                ("busybox", "magisk32", "magisk64", "magiskinit",
                 "magiskpolicy", "magiskboot")]
        cmds += ["rmdir %s" % _DATABIN]
        _run_debugfs_script(dev, cmds, env)
        if "Inode:" in _stat(dev, _DATABIN, env):
            raise RuntimeError("failed to remove %s" % _DATABIN)
        _es._fsck_ok(dev, env)
    return ["Removed /data/adb/magisk"]
