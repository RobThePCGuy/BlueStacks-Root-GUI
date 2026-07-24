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
import re
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


def _run_script(device: str, lines: list[str], env: dict) -> str:
    """Run a ``-w`` debugfs command script against ``device``; return the
    combined stdout+stderr so callers can scan it for error markers.

    Shared by both offline-edit features (classic su symlink, Magisk staging).
    """
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\nquit\n")
        r = _run([_debugfs(), "-w", "-f", path, device], env=env)
        return (r.stdout or "") + (r.stderr or "")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _stat_path(device: str, ext4_path: str, env: dict) -> str:
    """``debugfs stat`` stdout for ``ext4_path`` (empty string if not found)."""
    return _run([_debugfs(), "-R", "stat %s" % ext4_path, device], env=env).stdout or ""


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


def _detach(vhd_path: str) -> bool:
    """Detach the VHD/VHDX; return True once Windows reports it gone.

    A silent detach failure leaves the image mounted as a raw disk, which can
    block the next instance boot or race BlueStacks reopening the same file, so
    we retry and verify rather than fire-and-forget (a transient 'device busy'
    right after debugfs closes is common).
    """
    for _ in range(4):
        _diskpart('select vdisk file="%s"\ndetach vdisk\n' % vhd_path)
        time.sleep(0.8)
        if _disk_number(vhd_path) is None:
            return True
    return False


def _ps_single_quote(s: str) -> str:
    """Escape ``s`` for embedding inside a single-quoted PowerShell string
    literal (PowerShell's escape for a literal ``'`` is doubling it: ``''``).
    A Windows profile path with an apostrophe (e.g. ``C:\\Users\\O'Brien\\...``)
    would otherwise break out of the ``'%s'`` it's substituted into below."""
    return s.replace("'", "''")


def _disk_number(vhd_path: str) -> int | None:
    """OS disk number of the attached VHD (== PhysicalDriveN index)."""
    r = _run(["powershell", "-NoProfile", "-Command",
              "(Get-Disk | Where-Object { $_.Location -eq '%s' }).Number" % _ps_single_quote(vhd_path)])
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
    return _stat_path(device, "%s/%s" % (xbin, _LINK_NAME), env)


def _fsck_ok(device: str, env: dict) -> bool:
    # -fn: full check, never modify.  Exit 0 == clean.
    return _run([_e2fsck(), "-fn", device], env=env).returncode == 0


_UUID_RE = re.compile(r"^Filesystem UUID:\s*(\S+)", re.MULTILINE)


def _fs_uuid(device: str, env: dict) -> str | None:
    """The ext4 superblock UUID, or None if this isn't a readable ext4 device.

    Read with ``debugfs`` rather than a check pass: it is a superblock read, so
    it costs milliseconds where ``e2fsck -f`` walks the whole (multi-GB) image,
    and a UUID is an actual identity where matching sizes are not.
    """
    r = _run([_debugfs(), "-R", "show_super_stats -h", device], env=env)
    m = _UUID_RE.search(r.stdout or "")
    return m.group(1) if m else None


def _partition_device(device: str, env: dict) -> str | None:
    """Find the ``/dev/sdX<n>`` node backing an ``/dev/sdX?offset=`` device.

    Repairs have to run on this rather than the offset form (see
    :func:`_fsck_repair`).  That means briefly relying on Cygwin's partition
    nodes, which :func:`_cyg_device` deliberately avoids for the *working*
    device, so this is best-effort by design: when no node matches, the caller
    skips the repair instead of failing.  Candidates are matched on superblock
    UUID, so a repair can never be pointed at a different filesystem.
    """
    base = device.split("?")[0]
    if base == device:          # already a plain device
        return device
    want = _fs_uuid(device, env)
    if not want:
        return None
    for n in range(1, 5):
        cand = "%s%d" % (base, n)
        if _fs_uuid(cand, env) == want:
            return cand
    return None


def _fsck_repair(device: str, env: dict) -> str | None:
    """Replay a dirty journal so the image is consistent before we write to it.

    BlueStacks instances are rarely shut down cleanly: the player is terminated
    rather than asked to close (its own clean exit needs a human to click through
    a confirmation dialog), so the guest never unmounts and ``/data`` routinely
    comes to rest with an unreplayed journal.  Booting replays it, which is why
    this is invisible in normal use.

    Offline it matters twice over.  ``e2fsck -fn`` cannot replay a journal, so it
    reports such an image as damaged and every caller here turned that into
    "e2fsck reported errors" -- an operation refused because of the previous
    shutdown, not because anything was wrong.  Worse, writing with ``debugfs``
    into a filesystem whose journal still holds pending metadata risks having
    that replay overwrite the very changes just made.

    Note what ``-fn`` actually reports on such an image::

        Warning: skipping journal recovery because doing a read-only filesystem check
        Inode 3410023 was part of the orphaned inode list.  IGNORED.
        Block bitmap differences: ...

    Those "errors" are phantoms: they are the journal's pending metadata, and
    they evaporate once it is replayed.  Refusing to work on that image was
    refusing over nothing.

    The repair has to run on the **partition device**, not on the
    ``?offset=`` one everything else here uses.  After replaying a journal
    e2fsck reopens the filesystem to restart its check, and the reopen drops the
    ``?offset=`` qualifier, so it lands on the raw disk and dies with ``Bad magic
    number in super-block`` (exit 12) *before committing anything*.  The replay
    then never persists: run it twice and it announces "recovering journal" both
    times, with the image byte-for-byte unchanged.  Pointed at ``/dev/sdX1``
    there is no qualifier to lose, and the same preen completes normally (exit 1,
    "recovering journal" plus the orphaned inodes cleared) and sticks.

    **Best-effort, and never raises.**  It would be wrong to turn "could not
    replay" into a hard failure: an unreplayed journal is the *normal* resting
    state of a BlueStacks image, so raising would blanket-block every offline
    write on any host where the partition node cannot be found, and it would
    also block the uninstall and restore paths, which deliberately tolerate a
    dirty filesystem (``remove_su_symlink`` runs ``_fsck_ok`` and discards the
    result precisely so a removal always completes).  Refusing to let someone
    undo a change because their last shutdown was untidy is a worse bug than the
    one this fixes.  When the replay cannot happen we are simply no worse off
    than before, and the callers' own post-write checks still apply.

    Returns a note when a repair happened, otherwise ``None``.
    """
    if _fsck_ok(device, env):
        return None

    part = _partition_device(device, env)
    if part is None:
        logger.warning(
            "%s: journal looks unreplayed but no matching partition node was "
            "found, so it is left as-is", device)
        return None

    # -fp (preen): the automatic, safe-repairs-only mode a Linux boot uses. Its
    # exit code is informative only (12 even on success here, see above), so the
    # verdict comes from re-checking; log it either way or a failed repair would
    # look like filesystem damage.
    result = _run([_e2fsck(), "-fp", part], env=env)
    logger.info("e2fsck -fp %s -> exit %s: %s", part, result.returncode,
                ((result.stdout or "") + (result.stderr or "")).strip()[:500])

    if _fsck_ok(device, env):
        return ("Replayed the filesystem journal left by the last shutdown "
                "before writing.")
    logger.warning(
        "%s: still reports errors after replaying its journal; continuing, but "
        "the caller's own verification may fail", device)
    return None


class _Attached:
    """Context manager: attach the VHD, resolve its Cygwin device, detach on exit."""

    def __init__(self, vhd_path: str, repair: bool = True, progress=None):
        self.vhd = vhd_path
        self.offset = _partition_offset(vhd_path)
        self.device: str | None = None
        # Every offline writer funnels through here, so this is the one place a
        # dirty journal can be dealt with once for all of them.
        self.repair = repair
        # A replay runs before the caller's first progress message and can take a
        # while on a large image, so callers pass their reporter in to say so
        # rather than looking frozen on "Attaching...".
        self.progress = progress
        self.repaired: str | None = None

    def _resolve_device(self) -> str:
        num = _disk_number(self.vhd)
        if num is None:
            raise RuntimeError("could not locate the attached Root.vhd disk")
        return _cyg_device(num, self.offset)

    def __enter__(self) -> _Attached:
        _attach(self.vhd)
        time.sleep(1.5)  # let Windows enumerate the disk
        try:
            self.device = self._resolve_device()
            if self.repair:
                self.repaired = _fsck_repair(self.device, _tool_env())
                if self.repaired:
                    logger.info("%s: %s", self.vhd, self.repaired)
                    if self.progress:
                        self.progress(self.repaired)
                    # The preen wrote through the *partition* node, while every
                    # other write here goes through the *disk* node. On Windows
                    # those are separate device objects with separate caches, so
                    # a late write-back of stale partition-cached sectors could
                    # land on top of what debugfs writes next. Reattaching drops
                    # both caches and removes the aliasing entirely.
                    if _detach(self.vhd):
                        _attach(self.vhd)
                        time.sleep(1.5)
                        self.device = self._resolve_device()
                    else:
                        # Re-attaching something still attached would only make
                        # this worse, so keep the working device and say why the
                        # cache was not dropped.
                        logger.warning(
                            "%s: could not detach to refresh the device cache "
                            "after the journal replay; continuing on the "
                            "existing attachment", self.vhd)
        except Exception:
            # Leaving the VHD attached keeps the image locked and the instance
            # unbootable, so detach before the error propagates -- and say so if
            # that detach fails, or the user gets an unrelated error while a raw
            # disk is still mounted.
            if not _detach(self.vhd):
                logger.error(
                    "failed to detach %s -- it may still be mounted as a raw "
                    "disk; detach it via Disk Management before relaunching the "
                    "instance", self.vhd)
            raise
        return self

    def __exit__(self, *exc) -> None:
        if not _detach(self.vhd):
            msg = ("failed to detach %s -- it may still be mounted as a raw disk; "
                   "detach it via Disk Management before relaunching the instance"
                   % self.vhd)
            # A slow/failed detach must not turn an already-successful patch
            # into a reported error: the caller's work (write + verify + fsck)
            # is done by this point, so a sluggish `diskpart detach` here is a
            # cleanup nuisance, not a failure of the operation.
            if exc[0] is None:
                logger.warning(msg)
            else:
                # The body is already unwinding from a real error. Raising a
                # new exception here would REPLACE it as what propagates to
                # the caller (Python's implicit exception chaining makes the
                # original merely `__context__`, invisible to a plain
                # `except Exception as e: str(e)`), hiding the actual failure
                # behind this unrelated detach message. Log only.
                logger.error(msg)

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
    with _Attached(vhd, progress=_p) as att:
        dev = att.device
        xbin = _find_xbin(dev, env)
        if not xbin:
            raise RuntimeError("guest su (bstk/su) not found in Root.vhd -- "
                               "not a classic-root layout")
        if "Type: symlink" in _stat_su(dev, xbin, env):
            results.append("%s/su already present" % xbin)
            return results
        _p("Creating %s/su -> %s..." % (xbin, _LINK_TARGET))
        _run_script(dev, [f"symlink {xbin}/{_LINK_NAME} {_LINK_TARGET}",
                          f"sif {xbin}/{_LINK_NAME} uid 0",
                          f"sif {xbin}/{_LINK_NAME} gid 0"], env)
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
    with _Attached(vhd, progress=_p) as att:
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
