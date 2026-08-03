"""Structural checks on the injected ``su``.

This is the one artefact the tool puts inside the guest, and it runs as root by
construction, so the things worth pinning down are the ones that would make it
silently wrong rather than obviously broken: an ELF header the guest kernel
rejects, a ``adr`` that points somewhere other than the shell path, or a
privilege drop that happens after the ``execve`` instead of before it.

These run on every platform -- the bytes are generated, not compiled, so there
is nothing host-specific to skip.
"""
from __future__ import annotations

import struct

import macos_su


def _text() -> bytes:
    """The code+data portion, i.e. everything after the two headers."""
    return macos_su.build_su()[64 + 56:]


def _words() -> list[int]:
    text = _text()[:4 * len(macos_su._INSNS)]
    return [struct.unpack_from("<I", text, i)[0] for i in range(0, len(text), 4)]


def test_is_a_valid_aarch64_static_elf():
    blob = macos_su.build_su()
    assert blob[:4] == b"\x7fELF"
    assert blob[4] == 2      # ELFCLASS64
    assert blob[5] == 1      # ELFDATA2LSB
    e_type, e_machine = struct.unpack_from("<HH", blob, 16)
    assert e_type == 2               # ET_EXEC
    assert e_machine == 183          # EM_AARCH64 -- an x86 su would not run


def test_entry_point_lands_on_the_first_instruction():
    blob = macos_su.build_su()
    entry = struct.unpack_from("<Q", blob, 24)[0]
    p_vaddr = struct.unpack_from("<Q", blob, 64 + 16)[0]
    assert entry - p_vaddr == 64 + 56, "entry must skip the headers"
    # ...and that first instruction is `mov x9, sp`, which the rest depends on.
    assert _words()[0] == 0x910003E9


def test_single_load_segment_covers_the_whole_file():
    blob = macos_su.build_su()
    p_type, p_flags = struct.unpack_from("<II", blob, 64)
    p_filesz, p_memsz = struct.unpack_from("<QQ", blob, 64 + 32)
    assert p_type == 1               # PT_LOAD
    assert p_flags == 5              # R+X, and notably not W
    assert p_filesz == p_memsz == len(blob)


def test_adr_displacement_resolves_to_the_shell_path():
    """The one encoding that silently breaks if instructions are added."""
    blob = macos_su.build_su()
    adr_index = macos_su._ADR_INSN_INDEX
    word = _words()[adr_index]

    # ADR: immlo in bits 30:29, immhi in bits 23:5, both scaled to a byte offset.
    immlo = (word >> 29) & 0b11
    immhi = (word >> 5) & 0x7FFFF
    disp = (immhi << 2) | immlo
    assert disp == macos_su._ADR_DISPLACEMENT

    # Follow it and confirm the bytes really are the path.
    target = (64 + 56) + adr_index * 4 + disp
    assert blob[target:target + len(macos_su.SHELL_PATH)] == macos_su.SHELL_PATH
    assert macos_su.SHELL_PATH.endswith(b"\0"), "execve needs a NUL-terminated path"


def test_privileges_are_dropped_before_exec_not_after():
    """setresgid/setresuid must both precede execve.

    Reversed, the exec would happen first and the shell would keep the caller's
    uid -- a root-looking su that is not root.
    """
    words = _words()
    svc = 0xD4000001
    # Syscall number is the immediate of the `mov x8, #N` before each svc.
    calls = [(words[i - 1] >> 5) & 0xFFFF
             for i, w in enumerate(words) if w == svc]
    assert calls[:3] == [149, 147, 221], calls   # setresgid, setresuid, execve


def test_output_is_deterministic_and_fingerprinted():
    first, second = macos_su.build_su(), macos_su.build_su()
    assert first == second
    import hashlib
    assert macos_su.su_sha256() == hashlib.sha256(first).hexdigest()


def test_binary_is_small_enough_to_audit():
    # Not a golden hash (that would churn on any deliberate change) but a guard
    # that this never quietly becomes a vendored multi-megabyte payload.
    assert len(macos_su.build_su()) < 1024
