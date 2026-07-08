"""Open up the BlueStacks 5.22.150.1014+ guest `su` (remove the root lockdown).

What changed in 5.22.150.1014
------------------------
BlueStacks did NOT remove root. It rewrote the guest `su` (`/system/xbin/su`
and `/system/xbin/bstk/su`) from a self-contained binary into a gatekeeper that
grants root only to a **cryptographically-signed whitelist** of its own packages
(`/system/etc/.swl.cfg` + `.swl.cfg.sig`). A normal app gets:

    Permission denied - command not in whitelist  /  uid %d not allowed to su

The one escape hatch in the binary is `isDeveloperMode()` — at the final deny
gate the su does:

    if (!isDeveloperMode()) { report_su_denied; return 1; }   // DENY
    // else  -> setuid(0) + exec   (GRANT)

`isDeveloperMode()` asks the host over `/dev/bstvmsg`. So either enabling
BlueStacks Developer Mode, or forcing this function to return true, opens su to
all apps. This patcher does the latter: it rewrites `isDeveloperMode()` to
`mov al,1 ; ret`, so every su request is granted.

It locates the function by the literal string "isDeveloperMode: Function
started." (referenced by a RIP-relative `lea` at/near the function entry), so it
is independent of build offsets and works across the per-Android-version su
variants. Reversible via the `.orig` backup.

Usage:
    python su_patch.py <su-file-or-dir> [more ...]
Then push the patched su back to the guest with /system R/W:
    HD-Adb.exe push su /system/xbin/su
    HD-Adb.exe push su /system/xbin/bstk/su
    HD-Adb.exe shell chmod 06755 /system/xbin/su /system/xbin/bstk/su
"""
from __future__ import annotations

import logging
import os
import shutil
import struct
import sys

logger = logging.getLogger(__name__)

DEVMODE_STRING = b"isDeveloperMode: Function started.\x00"
# mov al, 1 ; ret  -> isDeveloperMode() always returns true (developer mode)
PATCH = bytes([0xB0, 0x01, 0xC3])
PROLOGUE = bytes([0x53, 0x48, 0x8D])  # push rbx ; lea rdi, ... (observed prologue)


def _elf_segments(data: bytes) -> tuple[bool, list[tuple[int, int, int]]]:
    """Return (is64, [(p_vaddr, p_offset, p_filesz)]) for PT_LOAD segments."""
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF")
    is64 = data[4] == 2
    if not is64:
        # 32-bit ELF (e.g. A7 32-bit su)
        e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
        e_phentsize = struct.unpack_from("<H", data, 0x2A)[0]
        e_phnum = struct.unpack_from("<H", data, 0x2C)[0]
        segs = []
        for i in range(e_phnum):
            o = e_phoff + i * e_phentsize
            p_type = struct.unpack_from("<I", data, o)[0]
            if p_type == 1:  # PT_LOAD
                p_offset = struct.unpack_from("<I", data, o + 4)[0]
                p_vaddr = struct.unpack_from("<I", data, o + 8)[0]
                p_filesz = struct.unpack_from("<I", data, o + 16)[0]
                segs.append((p_vaddr, p_offset, p_filesz))
        return is64, segs
    e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x36)[0]
    e_phnum = struct.unpack_from("<H", data, 0x38)[0]
    segs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, o)[0]
        if p_type == 1:  # PT_LOAD
            p_offset = struct.unpack_from("<Q", data, o + 8)[0]
            p_vaddr = struct.unpack_from("<Q", data, o + 16)[0]
            p_filesz = struct.unpack_from("<Q", data, o + 32)[0]
            segs.append((p_vaddr, p_offset, p_filesz))
    return is64, segs


def _off_to_vaddr(segs, off: int) -> int | None:
    for vaddr, foff, fsz in segs:
        if foff <= off < foff + fsz:
            return vaddr + (off - foff)
    return None

def _find_isdevmode_entry(data: bytes) -> int | None:
    """File offset of the isDeveloperMode() entry, or None."""
    s = data.find(DEVMODE_STRING)
    if s < 0:
        return None
    is64, segs = _elf_segments(data)
    str_vaddr = _off_to_vaddr(segs, s)
    if str_vaddr is None:
        return None

    if is64:
        # x86-64 (PIE *and* statically-linked): the function loads the string with
        # `lea rXX, [rip+rel32]` (48/4C 8D 05/0D/3D/35 rel32). Find the one whose
        # target == str_vaddr; the entry is the `push rbx` (53) right before it.
        i = 0
        while True:
            i = data.find(b"\x8d", i)
            if i < 0 or i + 5 > len(data):
                break
            if i >= 1 and data[i - 1] in (0x48, 0x4C) and data[i + 1] in (0x05, 0x0D, 0x3D, 0x35):
                rel = struct.unpack_from("<i", data, i + 2)[0]
                lea_off = i - 1
                lea_vaddr = _off_to_vaddr(segs, lea_off)
                if lea_vaddr is not None and lea_vaddr + 7 + rel == str_vaddr:
                    entry = lea_off - 1
                    if data[entry:entry + 3] == PROLOGUE:
                        return entry
                    return lea_off if data[lea_off:lea_off + 2] in (b"\x48\x8d", b"\x4c\x8d") else None
            i += 1
        return None

    # 32-bit PIE (A7 32-bit): the string is loaded GOT-relative via get_pc_thunk:
    #   E8 00 00 00 00   call $+5
    #   5B               pop ebx                ; ebx = vaddr of next insn
    #   81 C3 <imm32>    add ebx, imm32         ; ebx = GOT base
    #   ... 8D 83 <disp32>  lea eax, [ebx+disp32]  ; eax = string address
    # Resolve ebx, find the lea that targets the string, then walk back to the
    # `55 89 E5` (push ebp; mov ebp,esp) entry.
    i = 0
    thunk = b"\xE8\x00\x00\x00\x00\x5B\x81\xC3"
    while True:
        i = data.find(thunk, i)
        if i < 0:
            break
        call_vaddr = _off_to_vaddr(segs, i)
        if call_vaddr is None:
            i += 1
            continue
        ebx = (call_vaddr + 5) + struct.unpack_from("<i", data, i + 8)[0]
        window = data[i + 12:i + 12 + 96]
        k = 0
        while True:
            k = window.find(b"\x8D\x83", k)
            if k < 0 or k + 6 > len(window):
                break
            disp = struct.unpack_from("<i", window, k + 2)[0]
            if ebx + disp == str_vaddr:
                pe = data.rfind(b"\x55\x89\xE5", max(0, i - 0x20), i)
                if pe != -1:
                    return pe
            k += 2
        i += 1
    return None


def patch_su(path: str, make_backup: bool = True) -> str:
    data = bytearray(open(path, "rb").read())
    if data[:4] != b"\x7fELF":
        return "skip (not an ELF su)"
    entry = _find_isdevmode_entry(data)
    if entry is None:
        return "skip (no isDeveloperMode gate — likely an older/open su)"
    cur = bytes(data[entry:entry + 3])
    if cur == PATCH:
        return f"already patched (isDeveloperMode@0x{entry:X})"
    data[entry:entry + 3] = PATCH
    if make_backup and not os.path.exists(path + ".orig"):
        shutil.copy2(path, path + ".orig")
    open(path, "wb").write(data)
    return f"patched isDeveloperMode@0x{entry:X}: {cur.hex(' ')} -> {PATCH.hex(' ')}"


def _iter_su_files(target: str):
    if os.path.isfile(target):
        yield target
    elif os.path.isdir(target):
        for root, _dirs, files in os.walk(target):
            for fn in files:
                if fn == "su" or fn.startswith("su"):
                    yield os.path.join(root, fn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for tgt in sys.argv[1:]:
        for su in _iter_su_files(tgt):
            try:
                print(f"{su}: {patch_su(su)}")
            except Exception as e:  # noqa: BLE001
                print(f"{su}: ERROR - {e}")
