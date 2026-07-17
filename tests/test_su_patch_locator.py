"""Regression coverage for issue #49: `_find_isdevmode_entry` missed valid
`lea rXX, [rip+rel32]` register variants (rdx/rbx/rbp), silently skipping su
binaries that used them. Repro courtesy of @guclumhg's issue report."""
import struct

import pytest

import su_patch

# reg -> modrm byte for `lea rXX, [rip+rel32]` (mod=00, rm=101)
_REGS = {
    "rax": 0x05, "rcx": 0x0D, "rdx": 0x15, "rbx": 0x1D,
    "rbp": 0x2D, "rsi": 0x35, "rdi": 0x3D,
}


def _build_elf64(modrm: int) -> bytes:
    """Minimal ELF64, one PT_LOAD segment containing `push rbx; lea rXX,[rip+rel]`
    immediately followed by DEVMODE_STRING, so the lea's rip-relative target
    resolves to the string's own vaddr."""
    devstr = su_patch.DEVMODE_STRING
    vbase, phoff, f, s = 0x400000, 0x40, 0x80, 0x100
    total = s + len(devstr)
    b = bytearray(total)
    b[0:4] = b"\x7fELF"
    b[4] = 2  # ELFCLASS64
    b[5] = 1  # little-endian
    b[6] = 1  # EI_VERSION
    struct.pack_into("<H", b, 0x10, 2)      # e_type = ET_EXEC
    struct.pack_into("<H", b, 0x12, 0x3E)   # e_machine = EM_X86_64
    struct.pack_into("<Q", b, 0x20, phoff)  # e_phoff
    struct.pack_into("<H", b, 0x36, 56)     # e_phentsize
    struct.pack_into("<H", b, 0x38, 1)      # e_phnum
    struct.pack_into("<I", b, phoff + 0, 1)        # PT_LOAD
    struct.pack_into("<Q", b, phoff + 8, 0)        # p_offset
    struct.pack_into("<Q", b, phoff + 16, vbase)   # p_vaddr
    struct.pack_into("<Q", b, phoff + 32, total)   # p_filesz
    b[f], b[f + 1], b[f + 2], b[f + 3] = 0x53, 0x48, 0x8D, modrm  # push rbx; lea reg,[rip+rel]
    rel = (vbase + s) - (vbase + (f + 1) + 7)
    struct.pack_into("<i", b, f + 4, rel)
    b[s:s + len(devstr)] = devstr
    return bytes(b)


@pytest.mark.parametrize("reg", sorted(_REGS))
def test_find_isdevmode_entry_accepts_every_gp_register(reg):
    modrm = _REGS[reg]
    entry = su_patch._find_isdevmode_entry(_build_elf64(modrm))
    assert entry is not None, f"lea targeting {reg} (modrm=0x{modrm:02X}) was not found"
