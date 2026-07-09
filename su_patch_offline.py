"""Offline guest-su patch: enable/disable app root by editing /system inside an
instance's disk directly -- no running instance, no adb, no WSL2, no admin.

On 5.22.150.1014+ the live `/system/xbin/su` is NOT in Root.vhd (that copy is
read-only and shadowed): /system/xbin is bind-mounted rw from **Data.vhdx**, so
su is patched there. su only materialises in Data.vhdx after the instance's
FIRST BOOT. We support both container formats transparently: Root.vhd (a legacy
dynamic VHD: footer -> dynamic header -> BAT) and Data.vhdx (a Microsoft VHDX:
region table -> BAT + metadata). For either we read/write the flat ext4 disk,
locate every gated guest `su` (by the unique string "isDeveloperMode: Function
started.") -- handling the 64-bit (PIE + static) and 32-bit variants -- and flip
its isDeveloperMode() to always-true (3-byte patch), which makes su grant root
to every app, independent of enable_root_access.

Enable  = patch each su, recording the original bytes to a <vhd>.suroot.json
          backup sidecar.
Disable = restore the original bytes from the sidecar (un-root).

The instance MUST be shut down (the .vhd must not be open by BlueStacks).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import struct
import sys

import su_patch  # DEVMODE_STRING, PATCH, _find_isdevmode_entry

logger = logging.getLogger(__name__)

VHD_FOOTER_COOKIE = b"conectix"
DYN_COOKIE = b"cxsparse"
BAT_UNUSED = 0xFFFFFFFF
ENGINE_DIR = r"C:\ProgramData\BlueStacks_nxt\Engine"
MAX_SCAN_BACK = 0x200000     # 2 MB: distance back from the string to the ELF header
MAX_ELF = 0x200000           # 2 MB: cap on how much of an ELF we read

# VHDX (Data.vhdx) parsing constants. GUIDs are the on-disk little-endian byte
# order of the Microsoft VHDX spec GUIDs.
VHDX_SIGNATURE = b"vhdxfile"
_VHDX_REGION_TABLE_OFF = 0x30000
_VHDX_REG_BAT = bytes([0x66, 0x77, 0xC2, 0x2D, 0x23, 0xF6, 0x00, 0x42,
                       0x9D, 0x64, 0x11, 0x5E, 0x9B, 0xFD, 0x4A, 0x08])
_VHDX_REG_META = bytes([0x06, 0xA2, 0x7C, 0x8B, 0x90, 0x47, 0x9A, 0x4B,
                        0xB8, 0xFE, 0x57, 0x5F, 0x05, 0x0F, 0x88, 0x6E])
_VHDX_MD_FILEPARAMS = bytes([0x37, 0x67, 0xA1, 0xCA, 0x36, 0xFA, 0x43, 0x4D,
                             0xB3, 0xB6, 0x33, 0xF0, 0xAA, 0x44, 0xE7, 0x6B])
_VHDX_MD_VDISKSIZE = bytes([0x24, 0x42, 0xA5, 0x2F, 0x1B, 0xCD, 0x76, 0x48,
                            0xB2, 0x11, 0x5D, 0xBE, 0xD8, 0x3B, 0xF4, 0xB8])
# Logical sector size: spec GUID 8141BF1D-A96F-4709-BA47-F233A8FAAB5E. Some
# BlueStacks VHDX writers store a one-off variant ending ...5F, so we accept both
# and fall back to the Physical Sector Size item, else default 512.
_VHDX_MD_LOGSECSIZE = bytes([0x1D, 0xBF, 0x41, 0x81, 0x6F, 0xA9, 0x09, 0x47,
                             0xBA, 0x47, 0xF2, 0x33, 0xA8, 0xFA, 0xAB, 0x5E])
_VHDX_MD_LOGSECSIZE_ALT = bytes([0x1D, 0xBF, 0x41, 0x81, 0x6F, 0xA9, 0x09, 0x47,
                                 0xBA, 0x47, 0xF2, 0x33, 0xA8, 0xFA, 0xAB, 0x5F])
_VHDX_MD_PHYSSECSIZE = bytes([0xC7, 0x48, 0xA3, 0xCD, 0x5D, 0x44, 0x71, 0x44,
                              0x9C, 0xC9, 0xE9, 0x88, 0x52, 0x51, 0xC5, 0x56])
_VHDX_BAT_FULLY_PRESENT = 6


class DynamicVHD:
    def __init__(self, path: str, writable: bool = False):
        self.path = path
        self.f = open(path, "r+b" if writable else "rb")
        self.f.seek(0, 2)
        self.filesize = self.f.tell()
        self.f.seek(self.filesize - 512)
        footer = self.f.read(512)
        if footer[:8] != VHD_FOOTER_COOKIE:
            raise ValueError("not a VHD")
        if struct.unpack_from(">I", footer, 60)[0] != 3:
            raise ValueError("not a dynamic VHD")
        dyn_off = struct.unpack_from(">Q", footer, 16)[0]
        self.f.seek(dyn_off)
        dh = self.f.read(1024)
        if dh[:8] != DYN_COOKIE:
            raise ValueError("missing cxsparse header")
        self.bat_off = struct.unpack_from(">Q", dh, 16)[0]
        self.max_entries = struct.unpack_from(">I", dh, 28)[0]
        self.block_size = struct.unpack_from(">I", dh, 32)[0]
        self.f.seek(self.bat_off)
        self.bat = list(struct.unpack(">%dI" % self.max_entries,
                                      self.f.read(self.max_entries * 4)))
        spb = self.block_size // 512
        self.bitmap_size = (((spb + 7) // 8 + 511) // 512) * 512

    def is_present(self, blk: int) -> bool:
        return 0 <= blk < self.max_entries and self.bat[blk] != BAT_UNUSED

    def _phys(self, flat: int) -> int | None:
        blk = flat // self.block_size
        if blk >= self.max_entries or self.bat[blk] == BAT_UNUSED:
            return None
        return self.bat[blk] * 512 + self.bitmap_size + (flat % self.block_size)

    def read(self, flat: int, size: int) -> bytes:
        out = bytearray()
        while size > 0:
            within = flat % self.block_size
            chunk = min(size, self.block_size - within)
            phys = self._phys(flat)
            if phys is None:
                out += b"\x00" * chunk
            else:
                self.f.seek(phys)
                out += self.f.read(chunk)
            flat += chunk
            size -= chunk
        return bytes(out)

    def write(self, flat: int, data: bytes) -> None:
        phys = self._phys(flat)
        if phys is None:
            raise OSError("flat 0x%X not allocated" % flat)
        if (flat % self.block_size) + len(data) > self.block_size:
            raise OSError("write crosses block boundary")
        self.f.seek(phys)
        self.f.write(data)

    def close(self):
        self.f.close()


class DynamicVHDX:
    """Read/write a dynamic VHDX's flat disk (Data.vhdx).

    Exposes the same interface DynamicVHD does -- ``block_size``,
    ``max_entries``, ``is_present(blk)``, ``read()``, ``write()``, ``close()`` --
    so the su scanners work on either container unchanged.
    """

    def __init__(self, path: str, writable: bool = False):
        self.path = path
        self.f = open(path, "r+b" if writable else "rb")
        if self.f.read(8) != VHDX_SIGNATURE:
            raise ValueError("not a VHDX")
        # A non-zero LogGuid in the active header means the disk was left dirty
        # (an unflushed metadata log) by an abrupt shutdown. We read/write the
        # payload directly and do NOT replay that log, so patching a dirty disk
        # risks BlueStacks replaying pending entries over our writes on next
        # boot. Surface it (warn, don't block) so the caller can advise a clean
        # shutdown first.
        self.dirty = self._log_dirty()
        # Region table (at 1 MB): find the BAT and Metadata regions.
        self.f.seek(_VHDX_REGION_TABLE_OFF)
        rhdr = self.f.read(16)
        if rhdr[:4] != b"regi":
            raise ValueError("bad VHDX region table")
        entry_count = struct.unpack_from("<I", rhdr, 8)[0]
        regions: dict[bytes, int] = {}
        for _ in range(entry_count):
            e = self.f.read(32)
            regions[e[:16]] = struct.unpack_from("<Q", e, 16)[0]
        if _VHDX_REG_BAT not in regions or _VHDX_REG_META not in regions:
            raise ValueError("VHDX missing BAT or Metadata region")
        bat_off = regions[_VHDX_REG_BAT]
        meta_off = regions[_VHDX_REG_META]
        # Metadata table: BlockSize, LogicalSectorSize, VirtualDiskSize.
        self.f.seek(meta_off)
        mhdr = self.f.read(32)
        if mhdr[:8] != b"metadata":
            raise ValueError("bad VHDX metadata table")
        md_count = struct.unpack_from("<H", mhdr, 10)[0]
        items: dict[bytes, int] = {}
        for _ in range(md_count):
            me = self.f.read(32)
            items[me[:16]] = struct.unpack_from("<I", me, 16)[0]  # offset in region

        def _md(guid: bytes, fmt: str) -> int:
            self.f.seek(meta_off + items[guid])
            return struct.unpack(fmt, self.f.read(struct.calcsize(fmt)))[0]

        self.block_size = _md(_VHDX_MD_FILEPARAMS, "<I")
        virtual_size = _md(_VHDX_MD_VDISKSIZE, "<Q")
        self.sector = 512
        for _sg in (_VHDX_MD_LOGSECSIZE, _VHDX_MD_LOGSECSIZE_ALT, _VHDX_MD_PHYSSECSIZE):
            if _sg in items:
                self.sector = _md(_sg, "<I")
                break
        chunk_ratio = (2 ** 23 * self.sector) // self.block_size
        self.max_entries = (virtual_size + self.block_size - 1) // self.block_size
        # Payload BAT: every ``chunk_ratio`` payload entries are followed by one
        # sector-bitmap entry, so payload block N is BAT index N + N//chunk_ratio.
        self._phys_off: list[int | None] = []
        for blk in range(self.max_entries):
            idx = blk + blk // chunk_ratio
            self.f.seek(bat_off + idx * 8)
            entry = struct.unpack("<Q", self.f.read(8))[0]
            if (entry & 0x7) == _VHDX_BAT_FULLY_PRESENT:
                self._phys_off.append(entry & ~0xFFFFF)
            else:
                self._phys_off.append(None)

    def _log_dirty(self) -> bool:
        """True if the VHDX's active header carries a non-zero LogGuid (dirty log).

        The two header sections live at 64 KB and 128 KB; the one with the higher
        SequenceNumber is active. In each 4 KB header: signature "head" @0,
        SequenceNumber @8 (u64), LogGuid @48 (16 bytes). All-zero LogGuid = clean.
        """
        best_seq = -1
        dirty = False
        for hoff in (0x10000, 0x20000):
            self.f.seek(hoff)
            hdr = self.f.read(64)
            if len(hdr) < 64 or hdr[:4] != b"head":
                continue
            seq = struct.unpack_from("<Q", hdr, 8)[0]
            if seq > best_seq:
                best_seq = seq
                dirty = hdr[48:64] != b"\x00" * 16
        return dirty

    def is_present(self, blk: int) -> bool:
        return 0 <= blk < self.max_entries and self._phys_off[blk] is not None

    def _phys(self, flat: int) -> int | None:
        blk = flat // self.block_size
        if not self.is_present(blk):
            return None
        return self._phys_off[blk] + (flat % self.block_size)

    def read(self, flat: int, size: int) -> bytes:
        out = bytearray()
        while size > 0:
            within = flat % self.block_size
            chunk = min(size, self.block_size - within)
            phys = self._phys(flat)
            if phys is None:
                out += b"\x00" * chunk
            else:
                self.f.seek(phys)
                out += self.f.read(chunk)
            flat += chunk
            size -= chunk
        return bytes(out)

    def write(self, flat: int, data: bytes) -> None:
        phys = self._phys(flat)
        if phys is None:
            raise OSError("flat 0x%X not allocated" % flat)
        if (flat % self.block_size) + len(data) > self.block_size:
            raise OSError("write crosses block boundary")
        self.f.seek(phys)
        self.f.write(data)

    def close(self):
        self.f.close()


def open_disk(path: str, writable: bool = False):
    """Open a Data.vhdx (VHDX) or Root.vhd (legacy dynamic VHD) transparently."""
    with open(path, "rb") as fh:
        sig = fh.read(8)
    if sig == VHDX_SIGNATURE:
        return DynamicVHDX(path, writable=writable)
    return DynamicVHD(path, writable=writable)


def _elf_size(hdr: bytes) -> int | None:
    """Total file size of the ELF whose header starts at hdr[0], or None."""
    if hdr[:4] != b"\x7fELF":
        return None
    is64 = hdr[4] == 2
    if is64:
        e_shoff = struct.unpack_from("<Q", hdr, 0x28)[0]
        e_shentsize = struct.unpack_from("<H", hdr, 0x3A)[0]
        e_shnum = struct.unpack_from("<H", hdr, 0x3C)[0]
    else:
        e_shoff = struct.unpack_from("<I", hdr, 0x20)[0]
        e_shentsize = struct.unpack_from("<H", hdr, 0x2E)[0]
        e_shnum = struct.unpack_from("<H", hdr, 0x30)[0]
    if e_shoff and e_shnum:
        return e_shoff + e_shnum * e_shentsize
    return None


# Fallback isDeveloperMode entry signatures (5.22.166) for su whose /system file
# is fragmented (large static su), where the marker->ELF scan can't correlate the
# string with the function. Each pattern starts AT the entry (first 3 bytes get
# the b0 01 c3 patch). The build-specific rel32 keeps it unique. Derived from the
# installer su binaries; None = wildcard.
_FALLBACK_SIGS: list[list[int | None]] = [
    # A9 (Android 9) static-64: push rbx; lea rdi,[rip+0xE66A8 -> isDevStr]; xor eax,eax; call
    [0x53, 0x48, 0x8D, 0x3D, 0xA8, 0x66, 0x0E, 0x00, 0x31, 0xC0, 0xE8],
]


def _match_sig(hay: bytes, sig: list[int | None], start: int) -> int:
    n = len(sig)
    i = start
    first = sig[0]
    while True:
        i = hay.find(bytes([first]), i)
        if i < 0 or i + n > len(hay):
            return -1
        if all(sig[k] is None or hay[i + k] == sig[k] for k in range(n)):
            return i
        i += 1


def _classify_elf_su(elf: bytes, marker: bytes):
    """Classify an su ELF image. Returns (state, entry_off, is64) where state is
    "unpatched" or "patched", or None if this ELF is not a gated su.

    Unpatched: the prologue-anchored locator finds isDeveloperMode directly.
    Patched: the prologue was overwritten with `b0 01 c3` (mov al,1; ret), so the
    locator's anchor is gone -- we instead re-find the orphaned string reference
    (segment-correct, in the ELF's own vaddr space, so it works for page-aligned
    multi-segment su like A11/A13) and confirm the `b0 01 c3` at the entry.
    """
    try:
        is64, segs = su_patch._elf_segments(elf)
    except ValueError:
        return None
    ent = su_patch._find_isdevmode_entry(elf)
    if ent is not None:
        return ("unpatched", ent, is64)
    s = elf.find(marker)
    if s < 0:
        return None
    str_va = su_patch._off_to_vaddr(segs, s)
    if str_va is None:
        return None
    if is64:
        # patched 64-bit: `b0 01 c3 <modrm> <rel32>` -- orphaned lea rXX,[rip+rel]
        i = 0
        while True:
            i = elf.find(b"\xB0\x01\xC3", i)
            if i < 0 or i + 8 > len(elf):
                break
            if (elf[i + 3] & 0xC7) == 0x05:
                rel = struct.unpack_from("<i", elf, i + 4)[0]
                lea_next = su_patch._off_to_vaddr(segs, i + 1)  # lea spans off+1..off+8
                if lea_next is not None and lea_next + 7 + rel == str_va:
                    return ("patched", i, is64)
            i += 1
        return None
    # patched 32-bit: prologue 55 89 e5 -> b0 01 c3; the string is GOT-loaded via
    # get_pc_thunk later in the function. Resolve the thunk + GOT lea to the
    # string, then take the b0 01 c3 entry just before the thunk.
    thunk = b"\xE8\x00\x00\x00\x00\x5B\x81\xC3"
    i = 0
    while True:
        i = elf.find(thunk, i)
        if i < 0:
            break
        call_va = su_patch._off_to_vaddr(segs, i)
        if call_va is not None:
            ebx = (call_va + 5) + struct.unpack_from("<i", elf, i + 8)[0]
            w = elf[i + 12:i + 12 + 96]
            k = 0
            while True:
                k = w.find(b"\x8D\x83", k)
                if k < 0 or k + 6 > len(w):
                    break
                disp = struct.unpack_from("<i", w, k + 2)[0]
                if ebx + disp == str_va:
                    pe = elf.rfind(b"\xB0\x01\xC3", max(0, i - 0x20), i)
                    if pe != -1:
                        return ("patched", pe, is64)
                k += 2
        i += 1
    return None


def _scan_su_entries(vhd, pct=None) -> list[tuple[int, bool, bool]]:
    """Every gated su's isDeveloperMode entry as (flat_off, patched, is64).

    String-driven: locate each "isDeveloperMode" string, find the owning ELF, and
    classify it (patched or not) -- so enable() can patch the un-patched ones and
    record originals for the already-patched ones, and disable() can restore all.
    A signature fallback (same sweep) catches large statically-linked su whose
    ext4 file is fragmented (string and function land far apart on disk).
    """
    marker = su_patch.DEVMODE_STRING
    found: dict[int, tuple[bool, bool]] = {}      # flat_off -> (patched, is64)
    seen_elf = set()
    prev_tail = b""
    tail_len = max(len(marker), max((len(s) for s in _FALLBACK_SIGS), default=0)) + 8
    nblk = vhd.max_entries
    for blk in range(nblk):
        if pct is not None and (blk & 0x1F) == 0:
            pct(int(100 * blk / nblk))
        if not vhd.is_present(blk):
            prev_tail = b""
            continue
        flat = blk * vhd.block_size
        data = vhd.read(flat, vhd.block_size)
        hay = prev_tail + data
        base = flat - len(prev_tail)
        # fallback: direct un-patched entry-signature matches (fragmented static su)
        for sig in _FALLBACK_SIGS:
            si = 0
            while True:
                si = _match_sig(hay, sig, si)
                if si < 0:
                    break
                found.setdefault(base + si, (False, True))
                si += 1
        pos = 0
        while True:
            j = hay.find(marker, pos)
            if j < 0:
                break
            pos = j + 1
            str_flat = base + j
            # find the ELF that owns this string: scan back through every \x7fELF
            # header that could contain it, and keep going until one classifies
            # (a closer \x7fELF may falsely "contain" by size but not be the su).
            region_start = max(0, str_flat - MAX_SCAN_BACK)
            region = vhd.read(region_start, str_flat - region_start)
            search = len(region)
            while True:
                e = region.rfind(b"\x7fELF", 0, search)
                if e < 0:
                    break
                search = e
                cand = region_start + e
                if cand in seen_elf:
                    continue
                hdr = vhd.read(cand, 64)
                size = _elf_size(hdr)
                if not size or not (cand <= str_flat < cand + size):
                    continue
                elf = vhd.read(cand, min(size, MAX_ELF))
                try:
                    cls = _classify_elf_su(elf, marker)
                except Exception:
                    cls = None
                if cls is not None:
                    state, ent, is64 = cls
                    seen_elf.add(cand)
                    found[cand + ent] = (state == "patched", is64)
                    break   # found the su that owns this string
        prev_tail = data[-tail_len:]
    return sorted((off, p, a) for off, (p, a) in found.items())


def _find_su_entries(vhd, pct=None) -> list[int]:
    """Compat wrapper: flat offsets of UN-patched su entries (for dry-run)."""
    return [off for off, patched, _is64 in _scan_su_entries(vhd, pct) if not patched]


def _sidecar(vhd_path: str) -> str:
    return vhd_path + ".suroot.json"


def enable(vhd_path: str, progress=None) -> list[str]:
    """Patch every gated su to grant app root; back up originals to the sidecar.

    ``progress`` (optional) is called with a status string for each step.
    """
    def _p(msg):
        logger.info(msg)
        if progress:
            progress(msg)

    results: list[str] = []
    merged: dict[int, str] = {}
    sc = _sidecar(vhd_path)
    if os.path.isfile(sc):
        for p in json.load(open(sc)).get("patches", []):
            if p.get("orig"):
                merged[p["offset"]] = p["orig"]
    # Progress-only percentage reporter: updates the GUI status label, deduped so
    # it fires only when the integer %% changes, and NEVER goes to the logger --
    # the per-block scan ticks thousands of times and would flood the console.
    _last_pc = [-1]
    def _pct(pc):
        if progress and pc != _last_pc[0]:
            _last_pc[0] = pc
            progress("Scanning /system for su... %d%%" % pc)

    _p("Opening %s" % os.path.basename(vhd_path))
    vhd = open_disk(vhd_path, writable=True)
    if getattr(vhd, "dirty", False):
        _p("WARNING: this instance's disk was not shut down cleanly (dirty VHDX "
           "log). Boot it once and fully close it before patching, or the patch "
           "may be lost on next launch.")
    try:
        _p("Scanning /system for su binaries...")
        entries = _scan_su_entries(vhd, _pct)
        logger.info("Found %d gated su entr%s", len(entries), "y" if len(entries) == 1 else "ies")
        n = len(entries)
        for i, (off, patched, is64) in enumerate(entries, 1):
            orig_hex = "53 48 8d" if is64 else "55 89 e5"
            cur = vhd.read(off, 3)
            if patched or cur == su_patch.PATCH:
                merged.setdefault(off, orig_hex)         # track the already-rooted copy
                results.append("su@0x%X already rooted" % off)
                continue
            _p("Patching su %d/%d (offset 0x%X)..." % (i, n, off))
            merged.setdefault(off, cur.hex(" "))         # remember the original bytes
            vhd.write(off, su_patch.PATCH)
            ok = vhd.read(off, 3) == su_patch.PATCH
            line = "su@0x%X %s (%s -> %s)" % (off, "rooted" if ok else "write-verify FAILED",
                                              cur.hex(" "), su_patch.PATCH.hex(" "))
            logger.info(line)
            results.append(line)
    finally:
        vhd.close()
    if merged:
        _p("Writing backup sidecar...")
        json.dump({"patches": [{"offset": o, "orig": h} for o, h in merged.items()]},
                  open(sc, "w"), indent=2)
    elif not results:
        results.append("no gated su found -- boot the instance once so Android "
                       "populates /system/xbin/su in Data.vhdx, then shut it "
                       "down and retry")
    return results


def disable(vhd_path: str, progress=None) -> list[str]:
    """Restore original su bytes from the sidecar (un-root)."""
    def _p(msg):
        logger.info(msg)
        if progress:
            progress(msg)

    sc = _sidecar(vhd_path)
    if not os.path.isfile(sc):
        return ["no backup sidecar -- nothing to restore"]
    patches = json.load(open(sc)).get("patches", [])
    results: list[str] = []
    _p("Opening %s" % os.path.basename(vhd_path))
    vhd = open_disk(vhd_path, writable=True)
    if getattr(vhd, "dirty", False):
        _p("WARNING: this instance's disk was not shut down cleanly (dirty VHDX "
           "log). Boot it once and fully close it before un-rooting.")
    try:
        for i, p in enumerate(patches, 1):
            _p("Restoring su %d/%d..." % (i, len(patches)))
            off = p["offset"]
            orig = bytes(int(x, 16) for x in p["orig"].split())
            cur = vhd.read(off, 3)
            if cur == orig:
                results.append("su@0x%X already original" % off)
                continue
            # Only restore when this location still holds OUR patch (b0 01 c3).
            # If it holds neither the patch nor the original, the ext4 layout has
            # shifted under us (block reallocated) -- writing the original bytes
            # blindly could clobber unrelated data, so skip and flag it.
            if cur != su_patch.PATCH:
                results.append("su@0x%X unexpected bytes (%s); skipped to avoid "
                               "clobbering" % (off, cur.hex(" ")))
                continue
            vhd.write(off, orig)
            results.append("su@0x%X restored (%s -> %s)" % (off, cur.hex(" "), orig.hex(" ")))
    finally:
        vhd.close()
    try:
        os.remove(sc)
    except OSError:
        pass
    return results


def _su_disk(instance_dir: str) -> str | None:
    """Disk that holds the live /system/xbin/su on 5.22.150.1014+ -- the writable
    Data.vhdx (bind-mounted rw at /system/xbin). su only appears here after the
    instance's first boot. Falls back to the legacy Root.vhd if Data.vhdx is
    absent (pre-5.22.150 layout)."""
    vhdx = os.path.join(instance_dir, "Data.vhdx")
    if os.path.isfile(vhdx):
        return vhdx
    vhd = os.path.join(instance_dir, "Root.vhd")
    return vhd if os.path.isfile(vhd) else None


# --- instance-level helpers for the GUI -----------------------------------
def instance_root_state(instance_dir: str) -> bool:
    """True if this instance's su is patched (rooted), tracked by the backup sidecar."""
    vhd = _su_disk(instance_dir)
    return bool(vhd and os.path.isfile(_sidecar(vhd)))


def set_instance_root(instance_dir: str, on: bool, progress=None) -> list[str]:
    """Root (patch su + back up) or un-root (restore su) a single instance.

    The instance must be shut down. Returns human-readable status lines.
    """
    vhd = _su_disk(instance_dir)
    if not vhd:
        return ["Data.vhdx not found in %s -- boot the instance once, then shut "
                "it down and retry." % instance_dir]
    return enable(vhd, progress) if on else disable(vhd, progress)


def _collect(targets: list[str], all_instances: bool) -> list[str]:
    vhds: list[str] = []
    if all_instances or not targets:
        if os.path.isdir(ENGINE_DIR):
            for n in sorted(os.listdir(ENGINE_DIR)):
                v = _su_disk(os.path.join(ENGINE_DIR, n))
                if v:
                    vhds.append(v)
    for t in targets:
        tl = t.lower()
        if (tl.endswith(".vhdx") or tl.endswith(".vhd")) and os.path.isfile(t):
            vhds.append(t)
        elif os.path.isdir(t):
            v = _su_disk(t)
            if v:
                vhds.append(v)
            else:
                for n in sorted(os.listdir(t)):
                    v2 = _su_disk(os.path.join(t, n))
                    if v2:
                        vhds.append(v2)
    return list(dict.fromkeys(vhds))


def run(targets: list[str], action: str, all_instances: bool) -> list[tuple[str, list[str]]]:
    out = []
    for v in _collect(targets, all_instances):
        try:
            if action == "enable":
                out.append((v, enable(v)))
            elif action == "disable":
                out.append((v, disable(v)))
            else:  # dry-run: just locate
                vhd = open_disk(v)
                try:
                    ents = _find_su_entries(vhd)
                finally:
                    vhd.close()
                out.append((v, ["su@0x%X" % e for e in ents] or ["no gated su found"]))
        except Exception as exc:  # noqa: BLE001
            out.append((v, ["ERROR - %s" % exc]))
    return out


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="Data.vhdx / Root.vhd / instance dir / engine dir")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--enable", action="store_true", help="patch su (root), back up originals")
    g.add_argument("--disable", action="store_true", help="restore su from backup (un-root)")
    ap.add_argument("--all", action="store_true", help="all instances under the engine dir")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    action = "enable" if args.enable else "disable" if args.disable else "dryrun"
    res = run(args.targets, action, args.all)
    if not res:
        logger.error("No Data.vhdx found.")
        return 1
    for vhd, lines in res:
        print("[%s] %s" % (action.upper(), vhd))
        for ln in lines:
            print("    " + ln)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
