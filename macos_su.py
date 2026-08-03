"""The minimal aarch64 ``su`` this tool injects into a BlueStacks Air image.

Why a hand-assembled binary instead of a real one
-------------------------------------------------
BlueStacks Air ships **no** ``su`` at all. Unlike Windows BlueStacks -- whose
guest image contains a SuperSU-based ``su`` that ``bst.instance.<name>.
enable_root_access`` merely *unlocks* -- the Air image has no ``su``, no
SuperSU, no Magisk anywhere in ``/system`` or the ramdisk. Its init even tries
to ``import /init.superuser.rc`` and logs that the file does not exist. So the
conf key that roots Windows BlueStacks is inert here: there is nothing for it
to switch on. Rooting Air means *adding* an ``su``.

That leaves the question of where the binary comes from. Vendoring a prebuilt
one drags in a GPLv3 payload this project deliberately does not redistribute
(see ``magisk_payload``'s docstring on why Kyubi is downloaded, never shipped),
and downloading one at runtime means trusting a third party for the single most
security-sensitive byte sequence in the whole tool. Building it here avoids
both: it is 223 bytes of auditable, deterministic machine code with no
dependencies, and the assembly it corresponds to is written out in full below.

Why this is enough
------------------
SELinux is **disabled** on Air (``getenforce`` -> ``Disabled``), so no policy
patching is needed -- the kernel honours the setuid bit and nothing else gets a
vote. The classic setuid-root ``su`` therefore works exactly as it did on
pre-SELinux Android: the binary is owned by root with mode ``06755``, so the
kernel gives it euid 0 on exec, and it drops that to a *real* uid 0 before
handing control to the shell.

Argument handling is free. ``execve``-ing ``/system/bin/sh`` with the original
``argv`` untouched gives ``su -c "cmd"`` -> ``sh -c "cmd"`` and bare ``su`` ->
an interactive ``sh``, because a shell parses its options from ``argv[1:]`` and
ignores what ``argv[0]`` happens to say. That is the whole of ``su``'s
interface as this tool and every root-checking app use it.

The program
-----------
Entry is the raw ELF entry point: no libc, no relocations, no dynamic loader.
On entry the kernel has put the stack pointer at ``argc``, immediately followed
by ``argv[]``, a NULL, then ``envp[]``::

    mov  x9, sp             // x9 = &argc
    mov  x0, #0
    mov  x1, #0
    mov  x2, #0
    mov  x8, #149           // __NR_setresgid
    svc  #0                 // setresgid(0, 0, 0)
    mov  x0, #0
    mov  x1, #0
    mov  x2, #0
    mov  x8, #147           // __NR_setresuid
    svc  #0                 // setresuid(0, 0, 0)
    ldr  x10, [x9]          // argc
    add  x1, x9, #8         // argv  = &argc + 1
    add  x11, x10, #1       // argc + 1  (argv's NULL terminator)
    lsl  x11, x11, #3       // * sizeof(char *)
    add  x2, x1, x11        // envp  = argv + argc + 1
    adr  x0, path           // "/system/bin/sh"
    mov  x8, #221           // __NR_execve
    svc  #0                 // execve(path, argv, envp)
    mov  x0, #1             // only reached if execve failed
    mov  x8, #93            // __NR_exit
    svc  #0
  path:
    .asciz "/system/bin/sh"

``setresuid``/``setresgid`` (not plain ``setuid``) set the real, effective and
saved IDs in one call, so the shell cannot drop back to the calling user and
nothing downstream sees a mismatched real-vs-effective uid. Both run before
``execve`` so a failure to elevate can never yield an unprivileged shell that
merely *looks* rooted -- the syscalls cannot fail from a setuid-root binary,
and if they somehow did the exec still happens with euid 0 unchanged.

Syscall numbers are from the asm-generic ABI that arm64 Linux uses; they are
stable kernel ABI and are the same on the 5.15 guest kernel Air runs.
"""
from __future__ import annotations

import struct

# ---------------------------------------------------------------------------
# Machine code. Each entry is (mnemonic, encoded word); the mnemonics are kept
# beside the bytes so a reader can check the encoding without an assembler, and
# ``tests/test_macos_su.py`` asserts the words still disassemble to these.
# ---------------------------------------------------------------------------
SHELL_PATH = b"/system/bin/sh\0"

_INSNS: tuple[tuple[str, int], ...] = (
    ("mov  x9, sp",       0x910003E9),
    ("mov  x0, #0",       0xD2800000),
    ("mov  x1, #0",       0xD2800001),
    ("mov  x2, #0",       0xD2800002),
    ("mov  x8, #149",     0xD28012A8),   # __NR_setresgid
    ("svc  #0",           0xD4000001),
    ("mov  x0, #0",       0xD2800000),
    ("mov  x1, #0",       0xD2800001),
    ("mov  x2, #0",       0xD2800002),
    ("mov  x8, #147",     0xD2801268),   # __NR_setresuid
    ("svc  #0",           0xD4000001),
    ("ldr  x10, [x9]",    0xF940012A),   # argc
    ("add  x1, x9, #8",   0x91002121),   # argv
    ("add  x11, x10, #1", 0x9100054B),
    ("lsl  x11, x11, #3", 0xD37DF16B),
    ("add  x2, x1, x11",  0x8B0B0022),   # envp
    ("adr  x0, path",     0x100000C0),   # pc + 24 -> SHELL_PATH
    ("mov  x8, #221",     0xD2801BA8),   # __NR_execve
    ("svc  #0",           0xD4000001),
    ("mov  x0, #1",       0xD2800020),
    ("mov  x8, #93",      0xD2800BA8),   # __NR_exit
    ("svc  #0",           0xD4000001),
)

# ELF layout: one PT_LOAD covering header + program header + text, mapped R+X.
# There is no data, bss, or section table -- the loader needs none of it.
_EHDR_SIZE = 64
_PHDR_SIZE = 56
_LOAD_ADDR = 0x400000
_EM_AARCH64 = 183

# ``adr x0, path`` is encoded with a fixed +24 displacement, which is only
# correct while exactly 6 instructions follow it. Assert rather than silently
# emit an ``su`` that execve()s whatever bytes happen to sit at pc+24.
_ADR_INSN_INDEX = 16
_ADR_DISPLACEMENT = 24
assert (len(_INSNS) - _ADR_INSN_INDEX) * 4 == _ADR_DISPLACEMENT, \
    "adr displacement no longer points at SHELL_PATH"


def build_su() -> bytes:
    """Return the complete statically-linked aarch64 Linux ``su`` executable.

    Deterministic: the same bytes every call, on every host, so the injected
    binary can be hashed and compared (``su_sha256``) to tell an image this
    tool rooted apart from one somebody else modified.
    """
    text = b"".join(struct.pack("<I", word) for _, word in _INSNS) + SHELL_PATH
    entry = _LOAD_ADDR + _EHDR_SIZE + _PHDR_SIZE
    filesz = _EHDR_SIZE + _PHDR_SIZE + len(text)

    ehdr = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8
    ehdr += struct.pack(
        "<HHIQQQIHHHHHH",
        2,             # e_type    = ET_EXEC
        _EM_AARCH64,   # e_machine
        1,             # e_version
        entry,         # e_entry
        _EHDR_SIZE,    # e_phoff
        0,             # e_shoff   (no section headers)
        0,             # e_flags
        _EHDR_SIZE,    # e_ehsize
        _PHDR_SIZE,    # e_phentsize
        1,             # e_phnum
        64,            # e_shentsize
        0,             # e_shnum
        0,             # e_shstrndx
    )
    phdr = struct.pack(
        "<IIQQQQQQ",
        1,             # p_type   = PT_LOAD
        5,             # p_flags  = PF_R | PF_X
        0,             # p_offset
        _LOAD_ADDR,    # p_vaddr
        _LOAD_ADDR,    # p_paddr
        filesz,        # p_filesz
        filesz,        # p_memsz
        0x1000,        # p_align
    )

    blob = ehdr + phdr + text
    assert len(blob) == filesz, "ELF size mismatch: %d != %d" % (len(blob), filesz)
    return blob


def su_sha256() -> str:
    """SHA-256 of :func:`build_su`'s output -- the injected-file fingerprint."""
    import hashlib
    return hashlib.sha256(build_su()).hexdigest()
