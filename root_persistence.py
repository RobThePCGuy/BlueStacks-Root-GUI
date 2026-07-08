"""Root-persistence bypass for BlueStacks 5.22.x.

Why root "turns off" every time you start an instance
-----------------------------------------------------
There are two distinct mechanisms, and you need both handled:

1. The disk-integrity check (handled by ``integrity_patch.py``). On 5.22.150.1014+,
   ``HD-Player.exe`` rejects a modified ``Root.vhd`` / ``fastboot.vdi`` on boot
   ("...illegally tampered...") and shuts the instance down, so the rooted
   ``/system`` never survives a launch. Patching that check is the primary fix.

2. The ``bluestacks.conf`` keys. ``HD-Player.exe`` only *reads*
   ``bst.feature.rooting`` / ``bst.instance.<name>.enable_root_access`` (default
   ``0``); it is the BlueStacks **service / frontend** (``BstkSVC.exe``) that
   rewrites ``bluestacks.conf`` and can clear those keys back to ``0`` when an
   instance starts or settings are touched. The reliable, reversible bypass is
   to set ``bluestacks.conf`` **read-only** after the root keys are written, so
   nothing can revert them. This module manages that lock.

The lock is just the standard Windows FILE_ATTRIBUTE_READONLY bit, so it is
trivially reversible (unlock, or untick the box) and leaves no residue.
"""
from __future__ import annotations

import contextlib
import ctypes
import logging
import os
import struct
from ctypes import wintypes
from typing import Iterator

import integrity_patch

logger = logging.getLogger(__name__)

# Win32 file-attribute constants.
FILE_ATTRIBUTE_READONLY = 0x01
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetFileAttributesW.restype = wintypes.DWORD
_kernel32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
_kernel32.SetFileAttributesW.restype = wintypes.BOOL


def _get_attributes(path: str) -> int:
    attrs = _kernel32.GetFileAttributesW(path)
    if attrs == INVALID_FILE_ATTRIBUTES:
        raise ctypes.WinError(ctypes.get_last_error())
    return attrs


def _set_attributes(path: str, attrs: int) -> None:
    if not _kernel32.SetFileAttributesW(path, attrs):
        raise ctypes.WinError(ctypes.get_last_error())


def is_locked(config_path: str) -> bool:
    """Return True if ``config_path`` currently has the read-only attribute."""
    if not os.path.isfile(config_path):
        return False
    return bool(_get_attributes(config_path) & FILE_ATTRIBUTE_READONLY)


def lock(config_path: str) -> bool:
    """Set ``bluestacks.conf`` read-only so the root keys cannot be reverted.

    Returns True if the attribute was changed, False if it was already locked.
    """
    if not os.path.isfile(config_path):
        raise FileNotFoundError(config_path)
    attrs = _get_attributes(config_path)
    if attrs & FILE_ATTRIBUTE_READONLY:
        logger.debug("Config already locked: %s", config_path)
        return False
    _set_attributes(config_path, attrs | FILE_ATTRIBUTE_READONLY)
    logger.info("Locked (read-only) to persist root keys: %s", config_path)
    return True


def unlock(config_path: str) -> bool:
    """Clear the read-only attribute so the config can be edited again.

    Returns True if the attribute was changed, False if it was already writable.
    """
    if not os.path.isfile(config_path):
        raise FileNotFoundError(config_path)
    attrs = _get_attributes(config_path)
    if not (attrs & FILE_ATTRIBUTE_READONLY):
        return False
    _set_attributes(config_path, attrs & ~FILE_ATTRIBUTE_READONLY)
    logger.info("Unlocked (writable): %s", config_path)
    return True


# ---------------------------------------------------------------------------
# Binary alternative to the read-only lock
# ---------------------------------------------------------------------------
# HD-MultiInstanceManager.exe rewrites bluestacks.conf whenever you create /
# edit / clone (and on some launch paths). Its serializer (MimBackend.cpp)
# *hard-codes* enable_root_access="0" for every instance it writes -- the value
# is a literal 0, not the instance's real setting -- which is what silently
# turns root back off. The decompiled write is:
#
#     lea  r8, ".enable_root_access"     ; build "bst.instance.<name>.enable_root_access"
#     ...
#     xor  edx, edx                      ; value = 0  (hard-coded)
#     mov  rcx, rax
#     call writeIntSetting               ; <-- writes enable_root_access = 0
#
# NOP-ing that one call makes the serializer skip the key, so the value already
# present in bluestacks.conf (whatever the GUI wrote) is preserved on save. This
# is the read-only-free way to keep root: the conf stays fully writable, so you
# can still create and edit instances.
#
# Locating it across builds: the discriminator is the lea's target -- the
# ".enable_root_access" string -- not a fixed displacement. enable_vsync and the
# other bool settings share the identical instruction shape, differing only in
# which string the lea loads, and the lea's rel32 moves every build. So we:
#   1. find the ".enable_root_access" string and compute its VA (PE section map),
#   2. scan for the bool-setting shape `lea r8,[rip]; mov rdx,rax;
#      lea rcx,[rbp+disp]; call; nop; xor edx,edx; mov rcx,rax`,
#   3. keep only the candidate whose lea actually resolves to that string.
# This is version-independent (verified on 5.22.150.1014 and 5.22.166.1003) and
# fails closed if the compiler ever changes this codegen.
ROOT_PATCH_BINARY = "HD-MultiInstanceManager.exe"

# Instruction shape from the lea to the write call. Wildcards: the lea rel32
# (3..6), the lea-rcx disp32 (13..16) and the build_key call rel32 (18..21).
_ROOT_WRITE_SHAPE = [0x4C, 0x8D, 0x05, None, None, None, None,  # lea r8, <string>
                     0x48, 0x8B, 0xD0,                          # mov rdx, rax
                     0x48, 0x8D, 0x8D, None, None, None, None,   # lea rcx, [rbp+disp32]
                     0xE8, None, None, None, None,               # call build_key
                     0x90,                                       # nop
                     0x33, 0xD2,                                 # xor edx, edx (value 0)
                     0x48, 0x8B, 0xC8]                           # mov rcx, rax
_ROOT_WRITE_CALL_OFFSET = 28                                     # the E8 to NOP


def _locate_enable_root_write(data: bytes) -> list[int]:
    """Find the lea that loads ".enable_root_access" and feeds the write call."""
    try:
        image_base, sections = integrity_patch.pe_image_base_and_sections(data)
    except ValueError:
        return []
    s = data.find(b".enable_root_access\x00")
    if s < 0:
        return []
    str_rva = integrity_patch.file_offset_to_rva(sections, s)
    if str_rva is None:
        return []
    str_va = image_base + str_rva

    hits: list[int] = []
    for cand in integrity_patch._find_signature(bytearray(data), _ROOT_WRITE_SHAPE):
        lea_rva = integrity_patch.file_offset_to_rva(sections, cand)
        if lea_rva is None:
            continue
        rel = struct.unpack_from("<i", data, cand + 3)[0]
        # lea r8, [rip + rel32]: target = VA of next instruction (lea is 7 bytes) + rel
        if image_base + lea_rva + 7 + rel == str_va:
            hits.append(cand)
    return hits


ROOT_RESET_NOP = integrity_patch.PatchSpec(
    name="MimBackend enable_root_access reset (preserve existing value)",
    locator=_locate_enable_root_write,
    patch_offset=_ROOT_WRITE_CALL_OFFSET,
    expect_bytes=bytes([0xE8]),                            # original: the write call
    patch_bytes=bytes([0x90, 0x90, 0x90, 0x90, 0x90]),     # 5x nop
)


def patch_root_persistence(install_dir: str, restore: bool = False) -> list[str]:
    """Binary alternative to the read-only lock.

    Patches ``HD-MultiInstanceManager.exe`` so it no longer resets
    ``enable_root_access`` to 0 when it rewrites ``bluestacks.conf``. Leaves the
    conf fully writable, so instances can still be created/edited.

    Returns a list of human-readable status lines.
    """
    path = os.path.join(install_dir, ROOT_PATCH_BINARY)
    if not os.path.isfile(path):
        return [f"{ROOT_PATCH_BINARY}: not found in {install_dir}"]
    try:
        if restore:
            ok = integrity_patch.restore_file(path)
            return [f"{ROOT_PATCH_BINARY}: {'restored' if ok else 'no backup'}"]
        ok = integrity_patch.patch_file(path, specs=[ROOT_RESET_NOP])
        return [f"{ROOT_PATCH_BINARY}: {'patched' if ok else 'unchanged'}"]
    except Exception as exc:  # noqa: BLE001 - surface to caller/UI
        return [f"{ROOT_PATCH_BINARY}: ERROR - {exc}"]


@contextlib.contextmanager
def unlocked(config_path: str) -> Iterator[None]:
    """Context manager: temporarily clear read-only for a write, then restore.

    Use this to wrap any write to ``bluestacks.conf`` so the persistence lock
    never causes a PermissionError, and so the lock is faithfully restored
    afterwards::

        with root_persistence.unlocked(config_path):
            ...write the file...
    """
    was_locked = is_locked(config_path) if os.path.isfile(config_path) else False
    if was_locked:
        unlock(config_path)
    try:
        yield
    finally:
        if was_locked and os.path.isfile(config_path):
            try:
                lock(config_path)
            except OSError:
                logger.exception("Failed to re-lock config: %s", config_path)


def _main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Binary root-persistence patch (no read-only conf): stop "
                    "HD-MultiInstanceManager.exe resetting enable_root_access to 0.")
    parser.add_argument("install_dir",
                        help='BlueStacks install dir, e.g. "C:\\Program Files\\BlueStacks_nxt"')
    parser.add_argument("--restore", action="store_true",
                        help="restore HD-MultiInstanceManager.exe from its .prepatch.bak backup")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        import admin
        if not args.restore and not admin.is_admin():
            logger.warning("Not elevated: writing into Program Files will be denied. "
                           "Re-run this from an Administrator terminal.")
    except Exception:  # noqa: BLE001 - admin helper is optional
        pass

    if not os.path.isdir(args.install_dir):
        logger.error("Not a directory: %s", args.install_dir)
        return 2
    print("\n".join(patch_root_persistence(args.install_dir, restore=args.restore)))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
