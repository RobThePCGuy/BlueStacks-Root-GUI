"""Disk-integrity ("illegally tampered") bypass for BlueStacks 5.22.x.

Background
----------
Starting with BlueStacks 5.22.150.1014, ``HD-Player.exe`` runs a disk-integrity
check on every instance boot (``plrCheckDiskIntegrity`` in ``PlrSecurity.cpp``,
called from ``plrDiskCheckThreadEntry`` in ``PlrMain.cpp``). When an instance's
``Root.vhd`` / ``fastboot.vdi`` have been modified -- which is exactly what
happens once you enable R/W and install Magisk/Kitsune to ``/system`` -- the
check fails and the player shows:

    "The Android system will be shut down because it has been illegally
     tampered with and does not meet security requirements!"

...and force-stops the instance. That is why a freshly rooted instance "loses"
root on the next launch: the modified disk is rejected before Android finishes
booting.

The decompiled call site is::

    xor   bl, bl
    mov   [rsp+40h], bl
    call  plrCheckDiskIntegrity        ; returns AL = 1 (ok) / 0 (tampered)
    test  al, al
    jz    <tamper -> show dialog + shutdown>

This module locates that call site by a unique byte signature and overwrites
the 5-byte ``call`` with ``mov al, 1`` + 3x ``nop`` so the result is always
"verified". This is semantically identical to a state BlueStacks already ships:
``plrCheckDiskIntegrity`` itself returns 1 early when signature checking is off.

The patch is located by signature (not a hard-coded offset) so it keeps working
across minor 5.22.x rebuilds, and it is fully reversible via the ``.bak`` backup.

Usage (standalone)::

    python integrity_patch.py "C:\\Program Files\\BlueStacks_nxt"
    python integrity_patch.py --restore "C:\\Program Files\\BlueStacks_nxt"
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import struct
import sys
from dataclasses import dataclass
from typing import Callable

import constants

logger = logging.getLogger(__name__)

# Backup suffix appended next to the original executable before patching.
BACKUP_SUFFIX = ".prepatch.bak"

# Binaries that embed the integrity check / its shared resources. We scan all of
# them; only the ones that actually contain the runtime check (HD-Player.exe in
# 5.22.150.1014) carry the signature, the rest are skipped automatically.
CANDIDATE_BINARIES = [
    "HD-Player.exe",
    "HD-MultiInstanceManager.exe",
    "HD-DiskCompaction.exe",
    "HD-DiskFormatCheck.exe",
]


@dataclass(frozen=True)
class PatchSpec:
    """A located patch.

    The match site is found either by ``signature`` (a byte pattern where
    ``None`` entries are wildcards, e.g. a rel32 that differs per build) or, for
    cases a plain signature can't disambiguate across builds, by a ``locator``
    callable ``(data) -> list[int]`` returning match-start offsets.

    ``patch_offset`` is added to the match start; ``patch_bytes`` is written
    there. ``expect_bytes`` (a prefix of the original) is what must currently be
    present so we never patch the wrong thing or double-patch.
    """

    name: str
    patch_offset: int
    expect_bytes: bytes
    patch_bytes: bytes
    signature: list[int | None] | None = None
    locator: Callable[[bytes], list[int]] | None = None


# --- Minimal PE helpers (for locators that must resolve RIP-relative refs) ---
def pe_image_base_and_sections(data: bytes) -> tuple[int, list[tuple[int, int, int, int]]]:
    """Parse just enough PE to map file offsets <-> RVAs.

    Returns ``(image_base, sections)`` where each section is
    ``(virtual_address, virtual_size, pointer_to_raw, size_of_raw)``.
    """
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("not a PE file")
    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_opt = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    image_base = (struct.unpack_from("<Q", data, opt + 24)[0] if magic == 0x20B
                  else struct.unpack_from("<I", data, opt + 28)[0])
    sec_table = opt + size_opt
    sections = []
    for i in range(num_sections):
        o = sec_table + i * 40
        vsize = struct.unpack_from("<I", data, o + 8)[0]
        va = struct.unpack_from("<I", data, o + 12)[0]
        sraw = struct.unpack_from("<I", data, o + 16)[0]
        praw = struct.unpack_from("<I", data, o + 20)[0]
        sections.append((va, vsize, praw, sraw))
    return image_base, sections


def file_offset_to_rva(sections, foff: int) -> int | None:
    """Map a raw file offset to its RVA, or None if outside any raw section."""
    for va, _vsize, praw, sraw in sections:
        if praw <= foff < praw + sraw:
            return va + (foff - praw)
    return None


# xor bl,bl ; mov [rsp+40h],bl ; call rel32 ; test al,al ; jz
#   32 DB    88 5C 24 40        E8 ?? ?? ?? ?? 84 C0       74
# The 5 wildcarded bytes are the E8 opcode + rel32 of the call to
# plrCheckDiskIntegrity. We overwrite those 5 bytes (offset 6..11) with
#   B0 01            mov al, 1
#   90 90 90         nop ; nop ; nop
DISK_INTEGRITY_CALL = PatchSpec(
    name="plrCheckDiskIntegrity call (force 'verified')",
    signature=[0x32, 0xDB, 0x88, 0x5C, 0x24, 0x40,
               None, None, None, None, None,  # E8 rel32 (call)
               0x84, 0xC0, 0x74],
    patch_offset=6,
    expect_bytes=bytes([0xE8]),                 # original starts with the call opcode
    patch_bytes=bytes([0xB0, 0x01, 0x90, 0x90, 0x90]),
)


def _find_signature(data: bytes, sig: list[int | None]) -> list[int]:
    """Return every start offset in ``data`` matching ``sig`` (None = wildcard)."""
    hits: list[int] = []
    first = sig[0]
    assert first is not None, "signature must start with a concrete byte"
    n = len(sig)
    start = 0
    while True:
        idx = data.find(bytes([first]), start)
        if idx == -1 or idx + n > len(data):
            break
        if all(sig[k] is None or data[idx + k] == sig[k] for k in range(n)):
            hits.append(idx)
        start = idx + 1
    return hits


# Standard MSVC prologue of _isDiskVerificationRequired:
#   mov [rsp+8],rbx ; mov [rsp+10],rsi ; mov [rsp+18],rdi
_ISDVR_PROLOGUE = bytes([0x48, 0x89, 0x5C, 0x24, 0x08,
                         0x48, 0x89, 0x74, 0x24, 0x10,
                         0x48, 0x89, 0x7C, 0x24, 0x18])


def _locate_isdiskverify(data: bytes) -> list[int]:
    """Locate _isDiskVerificationRequired() via its 'unlock_player.bin' reference.

    That function reads the signed unlock file and returns 0 only when a valid
    `unlock_player.bin` is present. It is the single switch behind BOTH the disk
    integrity check (`if(!_isDiskVerificationRequired()) return 1;`) and the
    guest root grant (`developer_mode = (_isDiskVerificationRequired()==0)`).
    Forcing it to return 0 unlocks the player: integrity skipped + developer mode
    on (so the guest `su` grants every app).

    We find the "unlock_player.bin" string, resolve the `lea` inside the function
    that references it, then walk back to the function's prologue.
    """
    try:
        image_base, sections = pe_image_base_and_sections(data)
    except ValueError:
        return []
    s = data.find(b"unlock_player.bin\x00")
    if s < 0:
        return []
    str_rva = file_offset_to_rva(sections, s)
    if str_rva is None:
        return []
    str_va = image_base + str_rva

    i = 0
    while True:
        i = data.find(b"\x8D", i)
        if i < 0 or i + 5 > len(data):
            break
        if i >= 1 and data[i - 1] in (0x48, 0x4C) and data[i + 1] in constants.RIP_LEA_MODRM:
            lea_off = i - 1
            lea_rva = file_offset_to_rva(sections, lea_off)
            if lea_rva is not None:
                rel = struct.unpack_from("<i", data, i + 2)[0]
                if image_base + lea_rva + 7 + rel == str_va:
                    # Walk back to the function entry. Anchor on the prologue's
                    # tail (bytes 3..15) which the 3-byte patch leaves intact, so
                    # an already-patched binary is still located (entry = tail-3).
                    tail = data.rfind(_ISDVR_PROLOGUE[3:], max(0, lea_off - 0x800), lea_off)
                    if tail != -1:
                        return [tail - 3]
        i += 1
    return []


# Force _isDiskVerificationRequired() -> return 0 (xor eax,eax ; ret).
# Single host-side switch: disables the "illegally tampered" shutdown AND turns
# on Developer Mode, which the rewritten guest su honors as "grant root to all".
UNLOCK_PLAYER = PatchSpec(
    name="_isDiskVerificationRequired -> 0 (unlock: integrity off + root grant)",
    locator=_locate_isdiskverify,
    patch_offset=0,
    expect_bytes=bytes([0x48, 0x89, 0x5C]),       # start of the prologue
    patch_bytes=bytes([0x31, 0xC0, 0xC3]),        # xor eax,eax ; ret
)


def _apply_to_buffer(data: bytearray, spec: PatchSpec) -> str:
    """Apply ``spec`` to ``data`` in place. Returns a human-readable status."""
    if spec.locator is not None:
        hits = spec.locator(bytes(data))
    else:
        hits = _find_signature(data, spec.signature)
    if not hits:
        return "match not found (binary does not contain this check)"
    if len(hits) > 1:
        raise RuntimeError(
            f"{spec.name}: signature matched {len(hits)} times "
            f"({', '.join(hex(h) for h in hits)}); refusing to patch ambiguously."
        )

    at = hits[0] + spec.patch_offset
    current = bytes(data[at:at + len(spec.patch_bytes)])
    if current == spec.patch_bytes:
        return f"already patched at 0x{at:X}"
    if current[: len(spec.expect_bytes)] != spec.expect_bytes:
        raise RuntimeError(
            f"{spec.name}: unexpected bytes at 0x{at:X}: {current.hex(' ')}"
        )
    data[at:at + len(spec.patch_bytes)] = spec.patch_bytes
    return f"patched at 0x{at:X}: {current.hex(' ')} -> {spec.patch_bytes.hex(' ')}"


def patch_file(path: str, specs: list[PatchSpec] = (DISK_INTEGRITY_CALL,),
               make_backup: bool = True) -> bool:
    """Patch a single executable. Returns True if any change was written."""
    with open(path, "rb") as fh:
        data = bytearray(fh.read())

    changed = False
    for spec in specs:
        try:
            status = _apply_to_buffer(data, spec)
        except RuntimeError as exc:
            logger.error("%s: %s", os.path.basename(path), exc)
            raise
        logger.info("%s [%s]: %s", os.path.basename(path), spec.name, status)
        if status.startswith("patched"):
            changed = True

    if not changed:
        return False

    if make_backup:
        backup = path + BACKUP_SUFFIX
        # At this point `path` on disk is still the ORIGINAL, unpatched binary
        # (we only patched the in-memory `data`); so it is safe to back up now.
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
            logger.info("Backed up original to %s", backup)
        elif _sha256(path) != _sha256(backup):
            # A backup exists but the current unpatched binary differs from it:
            # BlueStacks replaced the binary with a newer build since we last
            # patched. The old backup is stale (a different version), and keeping
            # it would let a later "Undo" restore the WRONG build over this one.
            # Archive the stale backup and take a fresh one of the current build.
            stale = backup + ".old"
            try:
                shutil.copy2(backup, stale)
                logger.info("BlueStacks updated %s since last patch; archived "
                            "stale backup to %s", os.path.basename(path),
                            os.path.basename(stale))
            except OSError:
                logger.debug("Could not archive stale backup %s", backup, exc_info=True)
            shutil.copy2(path, backup)
            logger.info("Refreshed backup for updated %s", os.path.basename(path))
    with open(path, "wb") as fh:
        fh.write(data)
    # Record the hash of the file *as we just patched it*. restore_file() uses
    # this to detect the case where BlueStacks auto-updated the binary to a new
    # version after we patched: restoring the stale backup over a newer binary
    # would mismatch the rest of the install and could break the player.
    if make_backup:
        try:
            with open(backup + ".sha256", "w", encoding="utf-8") as fh:
                fh.write(_sha256(path))
        except OSError:
            logger.debug("Could not record patched-file hash for %s", path, exc_info=True)
    return True


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def restore_file(path: str) -> bool:
    """Restore a binary from its ``.prepatch.bak`` backup. Returns True if done.

    Refuses to restore when the current on-disk binary is not the one we patched
    (its hash no longer matches what patch_file() recorded) -- that means
    BlueStacks replaced it with a newer build, and overwriting it with our stale
    backup could leave the install inconsistent. In that case the fresh binary is
    already unpatched, so there is nothing to restore anyway.
    """
    backup = path + BACKUP_SUFFIX
    if not os.path.exists(backup):
        logger.warning("No backup found for %s", path)
        return False
    meta = backup + ".sha256"
    if os.path.exists(meta) and os.path.exists(path):
        try:
            recorded = open(meta, encoding="utf-8").read().strip()
        except OSError:
            recorded = ""
        if recorded:
            current = _sha256(path)
            if current != recorded:
                logger.warning(
                    "%s changed since it was patched (current %s != patched %s) -- "
                    "BlueStacks likely updated it. Refusing to overwrite the newer "
                    "binary with the stale backup.",
                    os.path.basename(path), current[:12], recorded[:12])
                return False
    shutil.copy2(backup, path)
    for stale in (meta,):  # patched-hash record is meaningless once restored
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except OSError:
            pass
    logger.info("Restored %s from backup", path)
    return True


def is_file_patched(path: str, spec: PatchSpec) -> bool | None:
    """Return True/False if ``spec`` is/ isn't applied to the binary at ``path``.

    Returns None when the state is indeterminate (file missing/unreadable, or the
    signature isn't found -- e.g. a build this patch doesn't apply to).
    """
    try:
        with open(path, "rb") as fh:
            data = bytearray(fh.read())
    except OSError:
        return None
    hits = spec.locator(bytes(data)) if spec.locator is not None else _find_signature(data, spec.signature)
    if len(hits) != 1:
        return None
    at = hits[0] + spec.patch_offset
    return bytes(data[at:at + len(spec.patch_bytes)]) == spec.patch_bytes


def installation_patched(install_dir: str) -> bool | None:
    """Whether this install's engine is currently patched.

    True if ``HD-Player.exe`` carries the unlock patch, False if it doesn't, None
    if it can't be determined (binary missing, or an unrecognized build). Cheap
    enough to call on a UI refresh -- it just reads and scans one binary.
    """
    path = os.path.join(install_dir, "HD-Player.exe")
    if not os.path.isfile(path):
        return None
    return is_file_patched(path, UNLOCK_PLAYER)


def patch_installation(install_dir: str, restore: bool = False) -> list[str]:
    """Patch (or restore) every candidate binary found in ``install_dir``.

    Returns a list of status lines for display in a UI/log.
    """
    results: list[str] = []
    for name in CANDIDATE_BINARIES:
        path = os.path.join(install_dir, name)
        if not os.path.isfile(path):
            continue
        # HD-Player.exe gets the unlock patch (disables integrity AND turns on
        # developer mode so the guest su grants root). It supersedes the
        # call-site integrity patch, which is kept as a harmless fallback.
        if name.lower() == "hd-player.exe":
            specs = [UNLOCK_PLAYER, DISK_INTEGRITY_CALL]
        else:
            specs = [DISK_INTEGRITY_CALL]
        try:
            if restore:
                ok = restore_file(path)
                results.append(f"{name}: {'restored' if ok else 'no backup'}")
            else:
                ok = patch_file(path, specs=specs)
                results.append(f"{name}: {'patched' if ok else 'unchanged'}")
        except Exception as exc:  # noqa: BLE001 - surface to caller/UI
            results.append(f"{name}: ERROR - {exc}")
    return results


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("install_dir",
                        help='BlueStacks install dir, e.g. "C:\\Program Files\\BlueStacks_nxt"')
    parser.add_argument("--restore", action="store_true",
                        help="restore originals from .prepatch.bak backups")
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

    results = patch_installation(args.install_dir, restore=args.restore)
    if not results:
        logger.error("No BlueStacks binaries found in %s", args.install_dir)
        return 1
    print("\n".join(results))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
