"""Root BlueStacks Air by injecting ``su`` into its Android system image.

Why this exists instead of the conf toggle
------------------------------------------
Windows BlueStacks ships a guest ``su`` that ``bst.instance.<name>.
enable_root_access`` unlocks, which is why ``config_handler`` can root it by
editing one line. BlueStacks Air ships no ``su`` anywhere -- verified against
the live guest *and* offline against the image's ext4 (``/system/bin``,
``/system/xbin``, ``/system/app``, ``/system/priv-app`` and the ramdisk are all
clean). The conf keys still exist in Air's ``bluestacks.conf``, and the player
still resets ``bst.feature.rooting`` to ``"0"`` on every launch, but nothing
consumes them: there is no ``su`` for them to gate. Rooting Air means putting
one there. See ``macos_su`` for the binary and why it is built rather than
downloaded.

What gets modified
------------------
``BlueStacks.app/Contents/img/Root.qcow2`` -- one qcow2 holding a single ext4
partition (MBR, type 0x83, starting at 1 MiB) whose ``/android/system`` tree the
guest bind-mounts as ``/system``. So ``/android/system/xbin/su`` in the image is
``/system/xbin/su`` in Android, which is already on the default ``PATH``.

Two consequences follow from this file living in the app bundle, and both are
deliberate behaviour rather than limitations worth hiding:

* **Rooting is install-wide, not per-instance.** Every Air instance boots this
  same image; there is no per-instance ``Root.qcow2`` (one placed in the
  instance directory is ignored -- tested). The UI reflects that.
* **Writing it needs the App Management privilege, not root.** The file's mode
  is ``rw-rw-rw-``, so the user can already write it; what refuses the write is
  macOS App Management, and that is granted to an *application*, so elevating
  does not inherit it -- a root ``cp`` through ``osascript`` is denied where a
  direct write succeeds. Hence the direct write first and elevation only as a
  fallback (``_install_image``). New files cannot be created in
  ``Contents/img`` at all (root-owned directory), so the image is overwritten
  in place and the backup lives outside the bundle.
* **Any edit invalidates the bundle's code signature**, because ``Root.qcow2``
  is a sealed resource. BlueStacks still launches, but ``codesign --verify``
  fails until the change is undone -- which is why undo restores the backup
  byte-for-byte rather than editing the modification back out.

The pipeline
------------
``qemu-img`` (BlueStacks' own copy) converts qcow2 to raw and back; ``debugfs``
edits the ext4 in place through e2fsprogs' ``?offset=`` syntax, so the partition
never has to be sliced out and spliced back. ``e2fsck`` runs before the image is
handed back to BlueStacks: a corrupt system image would fail to boot, and it is
cheap insurance next to a 1.7 GB rewrite.
"""
from __future__ import annotations

import contextlib
import errno
import json
import logging
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

import macos_locator
import macos_su
import platform_support

logger = logging.getLogger(__name__)

# Path *inside the image*; the guest bind-mounts /android/system as /system.
SU_IMAGE_PATH = "/android/system/xbin/su"
SU_GUEST_PATH = "/system/xbin/su"
SU_MODE = 0o106755          # regular file | setuid | rwxr-xr-x

# Kept beside bluestacks.conf, not in the bundle: Contents/img is root-owned, so
# a sibling backup cannot be created there even with the image world-writable.
BACKUP_NAME = "Root.qcow2.prepatch.bak"

# ONE state file for every edit this tool makes to the system image, not one
# per feature. Both root and the hosts block live in the same qcow2 and are
# validated by fingerprinting that qcow2, so per-feature state files would
# invalidate each other: applying the hosts block rewrites the image, which
# would make root's separately-stored fingerprint stop matching and silently
# report the instance as un-rooted. A single record with a single fingerprint
# cannot drift from itself.
STATE_NAME = "Root.qcow2.modstate.json"

# debugfs/e2fsck are not part of macOS. Homebrew keeps e2fsprogs keg-only, so
# its binaries are never on PATH even when installed -- look there explicitly
# before falling back to whatever PATH offers.
_E2FS_SEARCH_DIRS = (
    "/opt/homebrew/opt/e2fsprogs/sbin",     # Apple Silicon Homebrew
    "/opt/homebrew/sbin",
    "/usr/local/opt/e2fsprogs/sbin",        # Intel Homebrew
    "/usr/local/sbin",
    "/opt/local/sbin",                      # MacPorts
)

INSTALL_HINT = (
    "This needs the e2fsprogs tools (debugfs, e2fsck) to edit the Android "
    "system image.\n\nInstall them with:\n    brew install e2fsprogs"
)

# macOS App Management (TCC). Since Ventura, writing into another application's
# bundle is refused with EPERM unless the *responsible* app holds this
# privilege -- and, unlike a permissions problem, elevating does not help:
# running the copy as root through osascript is denied identically. The only
# fix is the user granting it, so say exactly that instead of surfacing a bare
# "Operation not permitted".
APP_MANAGEMENT_HINT = (
    "macOS blocked the write into BlueStacks.app.\n\n"
    "Modifying another app's bundle needs the \"App Management\" privilege, "
    "which administrator rights alone do not provide. Grant it here:\n\n"
    "    System Settings > Privacy & Security > App Management\n\n"
    "(opened for you just now). Enable BlueStacksRootGUI (or your terminal, "
    "if you are running from source). macOS will then ask to quit and reopen "
    "it; do that and try again."
)

_EPERM_MARKERS = ("Operation not permitted", "not permitted")


class RootError(RuntimeError):
    """Rooting could not be completed; the message is user-facing."""


# --------------------------------------------------------------------------
# Tool discovery
# --------------------------------------------------------------------------

def _bundled_e2fs_dir() -> str | None:
    """Where the packaged .app carries its own debugfs/e2fsck, when frozen.

    ``tools/build_macos_app.sh`` relocates Homebrew's copies (and their dylibs)
    into the bundle so a downloaded app needs no Homebrew at all.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "tools", "e2fsprogs-macos")  # type: ignore[attr-defined]
    return None


def _find_tool(name: str) -> str | None:
    bundled = _bundled_e2fs_dir()
    dirs = ((bundled,) if bundled else ()) + _E2FS_SEARCH_DIRS
    for directory in dirs:
        candidate = os.path.join(directory, name)
        if os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(name)


def find_e2fs_tools() -> tuple[str, str]:
    """Return ``(debugfs, e2fsck)`` paths, or raise with an install hint."""
    debugfs, e2fsck = _find_tool("debugfs"), _find_tool("e2fsck")
    if not debugfs or not e2fsck:
        raise RootError(INSTALL_HINT)
    return debugfs, e2fsck


def find_qemu_img(app_path: str) -> str:
    """BlueStacks' bundled ``qemu-img``; it is always present in the bundle."""
    tool = macos_locator.bundled_tool(app_path, macos_locator.QEMU_IMG_NAME)
    if not tool:
        raise RootError(
            "Could not find qemu-img inside %s. Is this a complete BlueStacks "
            "Air installation?" % app_path)
    return tool


def _run(argv: list[str], *, label: str) -> subprocess.CompletedProcess:
    logger.debug("running %s", argv)
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RootError("%s failed: %s" % (label, (proc.stderr or proc.stdout).strip()))
    return proc


# --------------------------------------------------------------------------
# Image geometry
# --------------------------------------------------------------------------

def partition_offset(raw_path: str) -> int:
    """Byte offset of the first MBR partition in ``raw_path``.

    Read rather than hard-coded at 1 MiB: a BlueStacks update is free to lay the
    image out differently, and silently editing the wrong offset would corrupt
    the system image instead of failing.
    """
    with open(raw_path, "rb") as fh:
        mbr = fh.read(512)
    if len(mbr) < 512 or mbr[510:512] != b"\x55\xaa":
        raise RootError("Android system image has no MBR signature; refusing to edit it.")
    for i in range(4):
        entry = mbr[446 + i * 16: 446 + (i + 1) * 16]
        part_type = entry[4]
        start_lba = struct.unpack("<I", entry[8:12])[0]
        if part_type == 0x83 and start_lba:      # 0x83 = Linux
            return start_lba * 512
    raise RootError("No Linux partition found in the Android system image.")


def _debugfs(debugfs: str, image: str, offset: int, commands: str, *,
             writable: bool) -> str:
    """Drive debugfs over the ext4 at ``offset`` inside ``image``."""
    argv = [debugfs]
    if writable:
        argv.append("-w")
    argv += ["-f", "/dev/stdin", "%s?offset=%d" % (image, offset)]
    proc = subprocess.run(argv, input=commands, capture_output=True, text=True)
    # debugfs reports per-command failures on stdout and still exits 0, so the
    # caller checks the text; a non-zero exit is a hard failure.
    if proc.returncode != 0:
        raise RootError("debugfs failed: %s" % (proc.stderr or proc.stdout).strip())
    return proc.stdout


# --------------------------------------------------------------------------
# Recorded state
# --------------------------------------------------------------------------
# Reading the real answer means converting 1.7 GB of qcow2, which cannot run on
# the 5-second status refresh. Instead the injected state is recorded next to
# the backup, fingerprinted with the image's size and mtime. If BlueStacks
# updates and replaces the image, the fingerprint stops matching and the state
# reads "not rooted" -- which is exactly what happened to the guest.

def _state_path(data_dir: str) -> str:
    return os.path.join(data_dir, STATE_NAME)


def backup_path(data_dir: str) -> str:
    return os.path.join(data_dir, BACKUP_NAME)


def _fingerprint(image: str) -> dict:
    st = os.stat(image)
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


def read_modstate(app_path: str, data_dir: str = macos_locator.DATA_DIR) -> dict:
    """Everything this tool has done to the current system image.

    ``{"root": bool, "hosts": {...}|None}``. Returns empty when the image no
    longer matches what was recorded -- a BlueStacks update replaces the image
    and takes every edit with it, so reporting the old contents would claim
    modifications the guest no longer has.
    """
    image = macos_locator.root_image_path(app_path)
    if not os.path.isfile(image):
        return {}
    try:
        with open(_state_path(data_dir), encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return {}
    if state.get("image") != _fingerprint(image):
        logger.info("Android system image changed since it was modified (a "
                    "BlueStacks update would do this); reporting it as stock.")
        return {}
    return state


def write_modstate(app_path: str, data_dir: str, state: dict) -> None:
    """Record ``state``, stamped with the image as it is right now.

    Must be called *after* the image has been written back, so the fingerprint
    describes the image the user actually has.
    """
    image = macos_locator.root_image_path(app_path)
    payload = {k: v for k, v in state.items() if v}
    if not payload:
        _clear_state(data_dir)
        return
    payload["image"] = _fingerprint(image)
    payload.pop("su_sha256", None)
    payload.pop("su_path", None)
    if payload.get("root"):
        # Fingerprint of the exact binary that was injected, so a future
        # version can tell its own su from one somebody else put there.
        payload["su_sha256"] = macos_su.su_sha256()
        payload["su_path"] = SU_GUEST_PATH
    with open(_state_path(data_dir), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _clear_state(data_dir: str) -> None:
    try:
        os.unlink(_state_path(data_dir))
    except FileNotFoundError:
        pass


def image_root_state(app_path: str, data_dir: str = macos_locator.DATA_DIR) -> bool:
    """True when this tool's ``su`` is believed to be in the current image."""
    return bool(read_modstate(app_path, data_dir).get("root"))


def verify_image_rooted(app_path: str) -> bool:
    """Authoritative -- and slow -- check that ``su`` really is in the image.

    Converts the whole image, so this is for explicit verification only; the UI
    uses :func:`image_root_state`.
    """
    debugfs, _ = find_e2fs_tools()
    qemu_img = find_qemu_img(app_path)
    image = macos_locator.root_image_path(app_path)
    workdir = tempfile.mkdtemp(prefix="bsroot-verify-")
    try:
        raw = os.path.join(workdir, "Root.raw")
        _run([qemu_img, "convert", "-O", "raw", image, raw], label="qemu-img convert")
        out = _debugfs(debugfs, raw, partition_offset(raw),
                       "stat %s\nquit\n" % SU_IMAGE_PATH, writable=False)
        return "Inode" in out and "File not found" not in out
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------
# The operation
# --------------------------------------------------------------------------

def _copy_in_place(source: str, dest: str) -> None:
    """Overwrite ``dest``'s contents, keeping its inode, owner and mode.

    Opened ``r+b`` and truncated rather than replaced: ``Contents/img`` is
    root-owned, so no new file can be created there to rename over, and the
    image itself is what must stay put.
    """
    with open(source, "rb") as src, open(dest, "r+b") as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
        dst.truncate()


# Opens System Settings straight at Privacy & Security > App Management.
APP_MANAGEMENT_URL = ("x-apple.systempreferences:com.apple.preference.security"
                      "?Privacy_AppBundles")


def _blocked_by_app_management(exc: OSError, image: str) -> bool:
    """EPERM on a file the user may write is App Management, not permissions.

    POSIX refusal is EACCES, and is what elevating fixes. EPERM on a file whose
    mode already lets us write it is TCC refusing, which elevating does not fix.
    The mode bits are read directly: ``os.access`` also answers "no" while TCC
    is blocking, which would hide the very case this detects.
    """
    if exc.errno != errno.EPERM:
        return False
    try:
        st = os.stat(image)
    except OSError:
        return False
    # No uid/gid on Windows, where the suite also runs this: st_mode's owner
    # bit there mirrors the read-only attribute, which is the right question.
    if not hasattr(os, "getuid") or st.st_uid == os.getuid():
        bit = stat.S_IWUSR
    elif st.st_gid in os.getgroups():
        bit = stat.S_IWGRP
    else:
        bit = stat.S_IWOTH
    return bool(st.st_mode & bit)


def open_app_management_settings() -> None:
    try:
        subprocess.Popen(["/usr/bin/open", APP_MANAGEMENT_URL])
    except OSError:
        logger.debug("could not open System Settings", exc_info=True)


def check_image_writable(image: str) -> None:
    """Fail before any work if macOS will refuse the final write.

    Opening for update is enough to trigger the App Management check and writes
    nothing, so the user hears about the missing permission up front instead of
    after the image has been unpacked, and without a password prompt.
    """
    try:
        with open(image, "r+b"):
            pass
    except OSError as exc:
        if _blocked_by_app_management(exc, image):
            open_app_management_settings()
            raise RootError(APP_MANAGEMENT_HINT) from exc
        # Anything else is left to _install_image's elevated fallback.


def _install_image(source: str, image: str, *, label: str) -> None:
    """Write ``source`` over the bundle's image, unelevated where possible.

    Order matters, and not for the obvious reason. ``Root.qcow2`` ships mode
    ``rw-rw-rw-``, so the logged-in user can already write it -- the only thing
    standing in the way is macOS App Management. And that privilege is granted
    to an *application*, not to a user: a root shell spawned through
    ``osascript`` does **not** inherit the grant its parent holds. Escalating
    therefore fails exactly where a plain write succeeds (observed: a direct
    write permitted while ``cp`` under ``with administrator privileges`` was
    refused on the same file, seconds apart).

    So try the direct write first -- which also means the common case needs no
    password prompt at all -- and keep elevation as the fallback for an install
    whose image is not user-writable.
    """
    try:
        _copy_in_place(source, image)
        return
    except OSError as direct_exc:
        if _blocked_by_app_management(direct_exc, image):
            # The elevated copy below cannot succeed here (root does not
            # inherit the grant), so asking for a password would be a prompt
            # that is guaranteed to fail. Send the user to the switch instead.
            open_app_management_settings()
            raise RootError(APP_MANAGEMENT_HINT) from direct_exc
        logger.info("Direct write to %s failed (%s); trying with administrator "
                    "rights.", image, direct_exc)
        direct_blocked = isinstance(direct_exc, PermissionError)

    try:
        platform_support.run_elevated(
            "/bin/cp %s %s\n" % (platform_support.shell_quote(source),
                                 platform_support.shell_quote(image)),
            label=label)
    except platform_support.ElevationError as exc:
        # EPERM from *both* paths is the App Management signature: a plain
        # permissions problem would have been fixed by running as root.
        if direct_blocked or any(marker in str(exc) for marker in _EPERM_MARKERS):
            raise RootError(APP_MANAGEMENT_HINT) from exc
        raise RootError(str(exc)) from exc


# The edits this tool can have applied to the system image. Root and the hosts
# block share one image, so neither can decide on its own whether undoing means
# "restore the pristine backup" or "edit the current image" -- that depends on
# whether the *other* one is still applied.
MODIFICATIONS = ("root", "hosts", "kyubi")


def applied_modifications(state: dict) -> set[str]:
    """Which of :data:`MODIFICATIONS` a modstate record says are in place."""
    return {key for key in MODIFICATIONS if state.get(key)}


def ensure_backup(image: str, data_dir: str, *, image_is_pristine: bool,
                  step=None) -> str | None:
    """Keep one pristine copy of the system image, shared by every edit.

    Refreshed only while the image is unmodified, which is what makes it
    *pristine*: overwriting it from an already-rooted image would turn "undo"
    into "restore the rooted image". Not refreshing at all would be worse in a
    different way -- a BlueStacks update replaces the image, and a stale backup
    would undo to the previous build's ``/system``.
    """
    # Before the 1.7 GB copy: a missing App Management grant should cost the
    # user nothing but the message.
    check_image_writable(image)
    backup = backup_path(data_dir)
    if os.path.isfile(backup) and not image_is_pristine:
        return backup
    if step:
        step("Backing up the original system image (this is how it is undone)...")
    _require_free_space(backup, os.path.getsize(image) + 2**30)
    shutil.copy2(image, backup)
    return backup


def restore_pristine(image: str, data_dir: str, step=None) -> list[str]:
    """Put the untouched image back and drop the backup.

    Byte-for-byte, which also repairs the app bundle's code-signature seal --
    any edit to ``Root.qcow2`` invalidates it, so restoring identical bytes is
    the only way to leave the install exactly as it was found.
    """
    backup = backup_path(data_dir)
    results = []
    check_image_writable(image)
    if step:
        step("Restoring the original Android system image...")
    _install_image(backup, image,
                   label="restore the original BlueStacks system image")
    results.append("restored %s from backup" % os.path.basename(image))
    try:
        os.unlink(backup)
        results.append("removed the backup copy")
    except OSError:
        logger.warning("Could not remove backup %s", backup, exc_info=True)
    return results


def _require_free_space(path: str, needed: int) -> None:
    free = shutil.disk_usage(os.path.dirname(path) or "/").free
    if free < needed:
        raise RootError(
            "Not enough free disk space: this needs about %.1f GB free and "
            "only %.1f GB is available." % (needed / 2**30, free / 2**30))


class ImageSession:
    """An unpacked system image, open for editing.

    Yielded by :func:`open_image`. ``run`` drives debugfs against the guest
    filesystem; ``read_file`` and ``write_file`` are the file-level helpers the
    hosts editor needs (``macos_hosts``).
    """

    def __init__(self, raw: str, offset: int, debugfs: str, workdir: str):
        self.raw = raw
        self.offset = offset
        self.workdir = workdir
        self._debugfs = debugfs

    def run(self, commands: str) -> str:
        out = _debugfs(self._debugfs, self.raw, self.offset, commands, writable=True)
        if "Bad magic" in out or "Filesystem not open" in out:
            raise RootError("Could not open the guest filesystem: %s" % out.strip())
        return out

    def read_file(self, path: str) -> str | None:
        """Contents of a file in the guest, or None when it does not exist."""
        dest = os.path.join(self.workdir, "dump.tmp")
        if os.path.exists(dest):
            os.unlink(dest)
        self.run("dump %s %s\nquit\n" % (path, dest))
        if not os.path.isfile(dest):
            return None
        with open(dest, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def write_file(self, path: str, content: str, *, mode: int = 0o100644) -> None:
        """Replace a file in the guest, root-owned with ``mode``."""
        src = os.path.join(self.workdir, "write.tmp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        parent, name = path.rsplit("/", 1)
        # debugfs `write` refuses to overwrite, and links the destination as a
        # bare name in the current directory -- hence the rm, the cd, and the
        # unqualified name.
        self.run(
            "rm {path}\ncd {parent}\nwrite {src} {name}\n"
            "sif {name} mode 0{mode:o}\nsif {name} uid 0\nsif {name} gid 0\nquit\n"
            .format(path=path, parent=parent, src=src, name=name, mode=mode))


@contextlib.contextmanager
def open_image(app_path: str, progress=None, *, results: list[str] | None = None):
    """Unpack the Air system image, yield an :class:`ImageSession`, repack it.

    The image is only written back if the body completes without raising, so a
    failed edit leaves BlueStacks exactly as it was rather than installing a
    half-modified system image.
    """
    def _step(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    if not platform_support.IS_MACOS:
        raise RootError("Editing the BlueStacks Air system image is macOS-only.")

    image = macos_locator.root_image_path(app_path)
    if not os.path.isfile(image):
        raise RootError("Android system image not found at %s" % image)

    check_image_writable(image)
    debugfs, e2fsck = find_e2fs_tools()
    qemu_img = find_qemu_img(app_path)
    # A 10 GiB sparse raw plus the rebuilt qcow2; the raw only ever holds the
    # ~1.7 GB that is actually allocated, but leave room for both.
    _require_free_space(tempfile.gettempdir(), 6 * 2**30)

    workdir = tempfile.mkdtemp(prefix="bsimg-")
    try:
        raw = os.path.join(workdir, "Root.raw")
        _step("Unpacking the Android system image...")
        _run([qemu_img, "convert", "-O", "raw", image, raw], label="qemu-img convert")

        offset = partition_offset(raw)
        logger.info("ext4 partition at offset %d", offset)

        yield ImageSession(raw, offset, debugfs, workdir)

        _step("Checking the guest filesystem...")
        # e2fsck exits 1 when it fixed something, which is a success here; only
        # 4+ (uncorrected errors) means the image is unusable.
        check = subprocess.run([e2fsck, "-fy", "%s?offset=%d" % (raw, offset)],
                               capture_output=True, text=True)
        if check.returncode >= 4:
            raise RootError("The guest filesystem failed its check and was not "
                            "written back:\n%s" % (check.stdout or check.stderr))
        if check.returncode == 1 and results is not None:
            results.append("e2fsck repaired the filesystem")

        _step("Repacking the system image...")
        new_image = os.path.join(workdir, "Root.qcow2")
        _run([qemu_img, "convert", "-O", "qcow2", raw, new_image],
             label="qemu-img convert")

        _step("Writing the image back into BlueStacks...")
        _install_image(new_image, image, label="update the BlueStacks system image")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def set_root(app_path: str, enabled: bool, progress=None,
             data_dir: str = macos_locator.DATA_DIR) -> list[str]:
    """Add (or remove) ``su`` in the Air system image. Returns log lines."""
    def _step(msg: str) -> None:
        logger.info(msg)
        if progress:
            progress(msg)

    if not platform_support.IS_MACOS:
        raise RootError("BlueStacks Air rooting is macOS-only.")

    image = macos_locator.root_image_path(app_path)
    if not os.path.isfile(image):
        raise RootError("Android system image not found at %s" % image)

    backup = backup_path(data_dir)
    state = read_modstate(app_path, data_dir)
    active = applied_modifications(state)
    results: list[str] = []

    # Undoing the *last* edit means putting the pristine image back, which is
    # faster than editing, and is the only thing that repairs the bundle's
    # code-signature seal. Deliberately ahead of the tool lookup below: this
    # path is a plain file copy, and someone who has since removed e2fsprogs
    # must never be trapped in a rooted state by a dependency undo does not use.
    if not enabled and not (active - {"root"}) and os.path.isfile(backup):
        results += restore_pristine(image, data_dir, _step)
        _clear_state(data_dir)   # nothing is applied any more, by definition
        _step("Root removed. Restart BlueStacks for the change to take effect.")
        return results

    if enabled and "kyubi" in active:
        # Both provide su and would fight over it.
        raise RootError("Kyubi is installed and already provides root. Remove "
                        "Kyubi first if you want the plain su instead.")

    if enabled:
        ensure_backup(image, data_dir, image_is_pristine=not active, step=_step)
        results.append("backed up to %s" % backup)

    with open_image(app_path, progress, results=results) as img:
        if enabled:
            _step("Installing su into the guest system...")
            su_path = os.path.join(img.workdir, "su")
            with open(su_path, "wb") as fh:
                fh.write(macos_su.build_su())
            parent, name = SU_IMAGE_PATH.rsplit("/", 1)
            # rm first so re-running is idempotent rather than failing on an
            # existing inode; a missing file makes rm a harmless no-op.
            img.run(
                "rm {img}\ncd {parent}\nwrite {src} {name}\n"
                "sif {name} mode 0{mode:o}\nsif {name} uid 0\nsif {name} gid 0\nquit\n"
                .format(img=SU_IMAGE_PATH, parent=parent, src=su_path,
                        name=name, mode=SU_MODE))
            results.append("installed %s (mode %04o, uid 0)"
                           % (SU_GUEST_PATH, SU_MODE & 0o7777))
        else:
            # No backup to fall back on -- remove the inode we added.
            _step("Removing su from the guest system...")
            img.run("rm %s\nquit\n" % SU_IMAGE_PATH)
            results.append("removed %s" % SU_GUEST_PATH)

    # Rewrite the whole record: the image just changed, so every edit still
    # applied has to be re-stamped against the new fingerprint, not just root's.
    state["root"] = enabled
    write_modstate(app_path, data_dir, state)

    _step("Done. Restart BlueStacks for the change to take effect.")
    return results
