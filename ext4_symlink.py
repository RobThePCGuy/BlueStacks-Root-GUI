"""Offline ``/system/xbin/su`` symlink injection for classic (MSI / pre-5.22.150)
BlueStacks builds.

Why this exists
---------------
On classic builds root is exposed only as ``/system/xbin/bstk/su`` -- there is no
``su`` on the app ``PATH`` (``/system/xbin/su`` etc.), so root-checker *apps*
report "not rooted" even though a shell gets ``uid=0``.  ``/system`` lives in the
per-instance ``Root.vhd`` and is mounted read-only by the hypervisor, so it can
only be changed offline while the instance is shut down.

Patch-mode builds don't need this (``su_patch_offline`` handles their app root);
this module is the classic-build counterpart.

How it works
------------
``Root.vhd`` is a dynamic VHD holding an ext4 ``/system`` image.  We can't edit
ext4 (htree dirs + gdt_csum/metadata_csum checksums) reliably by hand, so we use
the battle-tested ``debugfs`` from e2fsprogs, bundled with the app (no Cygwin
install required -- ``tools/e2fsprogs/`` ships ``debugfs.exe``/``e2fsck.exe`` and
their DLLs).  Because a dynamic VHD isn't a linear image, we ``diskpart``-attach
it so Windows materialises a real disk, then run debugfs against that disk at the
ext4 partition offset, create ``su -> bstk/su``, ``e2fsck``-verify, and detach.

Requirements: Windows, Administrator (raw-disk access + diskpart), instance shut
down (``Root.vhd`` not locked).
"""
from __future__ import annotations

import logging
import os
import struct
import subprocess
import sys
import tempfile
import time

import su_patch_offline  # reuse its dynamic-VHD reader for the MBR probe

logger = logging.getLogger(__name__)

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

# Candidate parents of the guest /system/xbin inside the Root.vhd ext4 image.
# Classic MSI packs Android under /android/system; some builds expose /system at
# the fs root.  We pick whichever actually contains bstk/su.
_XBIN_CANDIDATES = ("/android/system/xbin", "/system/xbin")
_LINK_NAME = "su"
_LINK_TARGET = "bstk/su"  # relative -> resolves to <xbin>/bstk/su


def _tool_dir() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller onefile
        return os.path.join(sys._MEIPASS, "e2fsprogs")  # type: ignore[attr-defined]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "e2fsprogs")


def _debugfs() -> str:
    return os.path.join(_tool_dir(), "debugfs.exe")


def _e2fsck() -> str:
    return os.path.join(_tool_dir(), "e2fsck.exe")


def tools_available() -> bool:
    """True if the bundled e2fsprogs binaries are present."""
    return os.path.isfile(_debugfs()) and os.path.isfile(_e2fsck())


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          creationflags=_NO_WINDOW, env=env)


def _tool_env() -> dict:
    # debugfs/e2fsck resolve their cyg*.dll from their own directory; keep the
    # dir on PATH too for safety.
    env = dict(os.environ)
    env["PATH"] = _tool_dir() + os.pathsep + env.get("PATH", "")
    return env


def _root_vhd(instance_dir: str) -> str:
    return os.path.join(instance_dir, "Root.vhd")


def _partition_offset(vhd_path: str) -> int:
    """Byte offset of the first partition inside the VHD, from its MBR.

    Reads through su_patch_offline's dynamic-VHD reader so it works on the sparse
    Root.vhd without attaching.  Falls back to the standard 1 MiB (LBA 2048).
    """
    try:
        v = su_patch_offline.open_disk(vhd_path)
    except Exception:
        return 1024 * 1024
    try:
        mbr = v.read(0, 512)
        if mbr[510:512] == b"\x55\xaa":
            start_lba = struct.unpack_from("<I", mbr, 446 + 8)[0]
            if start_lba:
                return start_lba * 512
    finally:
        v.close()
    return 1024 * 1024


def _diskpart(script: str) -> subprocess.CompletedProcess:
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(script)
        return _run(["diskpart", "/s", path])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _attach(vhd_path: str) -> None:
    _diskpart('select vdisk file="%s"\nattach vdisk\n' % vhd_path)


def _detach(vhd_path: str) -> None:
    _diskpart('select vdisk file="%s"\ndetach vdisk\n' % vhd_path)


def _disk_number(vhd_path: str) -> int | None:
    """OS disk number of the attached VHD (== PhysicalDriveN index)."""
    r = _run(["powershell", "-NoProfile", "-Command",
              "(Get-Disk | Where-Object { $_.Location -eq '%s' }).Number" % vhd_path])
    out = (r.stdout or "").strip()
    return int(out) if out.isdigit() else None


def _cyg_device(disk_number: int, offset: int) -> str:
    # Cygwin maps PhysicalDriveN -> /dev/sd<a+N>; ?offset= selects the ext4
    # partition without relying on Cygwin's own partition detection.
    return "/dev/sd%s?offset=%d" % (chr(ord("a") + disk_number), offset)


def _find_xbin(device: str, env: dict) -> str | None:
    """Return the xbin dir (from _XBIN_CANDIDATES) that holds bstk/su, or None."""
    for xbin in _XBIN_CANDIDATES:
        r = _run([_debugfs(), "-R", "stat %s/bstk/su" % xbin, device], env=env)
        if "Inode:" in (r.stdout or ""):
            return xbin
    return None


def _stat_su(device: str, xbin: str, env: dict) -> str:
    return _run([_debugfs(), "-R", "stat %s/%s" % (xbin, _LINK_NAME), device],
                env=env).stdout or ""


def _fsck_ok(device: str, env: dict) -> bool:
    # -fn: full check, never modify.  Exit 0 == clean.
    return _run([_e2fsck(), "-fn", device], env=env).returncode == 0


class _Attached:
    """Context manager: attach the VHD, resolve its Cygwin device, detach on exit."""

    def __init__(self, vhd_path: str):
        self.vhd = vhd_path
        self.offset = _partition_offset(vhd_path)
        self.device: str | None = None

    def __enter__(self) -> _Attached:
        _attach(self.vhd)
        time.sleep(1.5)  # let Windows enumerate the disk
        num = _disk_number(self.vhd)
        if num is None:
            _detach(self.vhd)
            raise RuntimeError("could not locate the attached Root.vhd disk")
        self.device = _cyg_device(num, self.offset)
        return self

    def __exit__(self, *exc) -> None:
        _detach(self.vhd)

def add_su_symlink(instance_dir: str, progress=None) -> list[str]:
    """Create ``/system/xbin/su -> bstk/su`` in a shut-down instance's Root.vhd.

    Idempotent; returns human-readable status lines.  Raises on hard failure
    (missing tools, unlocatable disk, verification failure).
    """
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    vhd = _root_vhd(instance_dir)
    if not tools_available():
        raise RuntimeError("bundled e2fsprogs (debugfs) not found in %s" % _tool_dir())
    if not os.path.isfile(vhd):
        raise RuntimeError("Root.vhd not found in %s" % instance_dir)

    env = _tool_env()
    results: list[str] = []
    _p("Attaching Root.vhd (app-root symlink)...")
    with _Attached(vhd) as att:
        dev = att.device
        xbin = _find_xbin(dev, env)
        if not xbin:
            raise RuntimeError("guest su (bstk/su) not found in Root.vhd -- "
                               "not a classic-root layout")
        if "Type: symlink" in _stat_su(dev, xbin, env):
            results.append("%s/su already present" % xbin)
            return results
        _p("Creating %s/su -> %s..." % (xbin, _LINK_TARGET))
        cmds = (f"symlink {xbin}/{_LINK_NAME} {_LINK_TARGET}\n"
                f"sif {xbin}/{_LINK_NAME} uid 0\n"
                f"sif {xbin}/{_LINK_NAME} gid 0\n"
                "quit\n")
        fd, cf = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(cmds)
            _run([_debugfs(), "-w", "-f", cf, dev], env=env)
        finally:
            try:
                os.unlink(cf)
            except OSError:
                pass
        if "Type: symlink" not in _stat_su(dev, xbin, env):
            raise RuntimeError("symlink creation did not take effect")
        _p("Verifying filesystem (e2fsck)...")
        if not _fsck_ok(dev, env):
            raise RuntimeError("e2fsck reported errors after injection")
        results.append("%s/su -> %s created (app-visible root)" % (xbin, _LINK_TARGET))
    return results


def remove_su_symlink(instance_dir: str, progress=None) -> list[str]:
    """Remove the injected ``/system/xbin/su`` symlink (if present)."""
    def _p(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    vhd = _root_vhd(instance_dir)
    if not tools_available() or not os.path.isfile(vhd):
        return ["e2fsprogs/Root.vhd unavailable -- nothing to remove"]
    env = _tool_env()
    results: list[str] = []
    _p("Attaching Root.vhd (remove app-root symlink)...")
    with _Attached(vhd) as att:
        dev = att.device
        xbin = _find_xbin(dev, env)
        if not xbin or "Type: symlink" not in _stat_su(dev, xbin, env):
            return ["%s/su not present" % (xbin or "/system/xbin")]
        _run([_debugfs(), "-w", "-R", "rm %s/%s" % (xbin, _LINK_NAME), dev], env=env)
        if "Type: symlink" in _stat_su(dev, xbin, env):
            raise RuntimeError("failed to remove %s/su" % xbin)
        _fsck_ok(dev, env)
        results.append("%s/su removed" % xbin)
    return results
