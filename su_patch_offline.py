"""Offline guest-su patch: enable/disable app root by editing /system inside an
instance's Root.vhd directly -- no running instance, no adb, no WSL2, no admin.

Root.vhd is a *dynamic* VHD wrapping an ext4 /system. We parse the VHD ourselves
(footer -> dynamic header -> Block Allocation Table) and read/write the flat disk
directly in the .vhd file. We locate every gated guest `su` (by the unique string
"isDeveloperMode: Function started.") -- handling the 64-bit (PIE + static) and
32-bit variants -- and flip its isDeveloperMode() to always-true (3-byte patch),
which makes su grant root to every app, independent of enable_root_access.

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
from typing import Dict, List, Optional, Tuple

import su_patch  # DEVMODE_STRING, PATCH, _find_isdevmode_entry

logger = logging.getLogger(__name__)

VHD_FOOTER_COOKIE = b"conectix"
DYN_COOKIE = b"cxsparse"
BAT_UNUSED = 0xFFFFFFFF
ENGINE_DIR = r"C:\ProgramData\BlueStacks_nxt\Engine"
MAX_SCAN_BACK = 0x200000     # 2 MB: distance back from the string to the ELF header
MAX_ELF = 0x200000           # 2 MB: cap on how much of an ELF we read


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

    def _phys(self, flat: int) -> Optional[int]:
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
            raise IOError("flat 0x%X not allocated" % flat)
        if (flat % self.block_size) + len(data) > self.block_size:
            raise IOError("write crosses block boundary")
        self.f.seek(phys)
        self.f.write(data)

    def close(self):
        self.f.close()


def _elf_size(hdr: bytes) -> Optional[int]:
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
_FALLBACK_SIGS: List[List[Optional[int]]] = [
    # A9 (Android 9) static-64: push rbx; lea rdi,[rip+0xE66A8 -> isDevStr]; xor eax,eax; call
    [0x53, 0x48, 0x8D, 0x3D, 0xA8, 0x66, 0x0E, 0x00, 0x31, 0xC0, 0xE8],
]


def _match_sig(hay: bytes, sig: List[Optional[int]], start: int) -> int:
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


def _find_su_entries(vhd: DynamicVHD) -> List[int]:
    """Flat offsets of every gated su's isDeveloperMode entry (deduped).

    Primary path: locate the "isDeveloperMode" string, find the owning ELF, run
    the architecture-aware locator. Fallback path (same block sweep): match known
    entry signatures directly -- needed for large statically-linked su whose
    ext4 file is fragmented (string and function land far apart on disk).
    """
    marker = su_patch.DEVMODE_STRING
    entries: List[int] = []
    seen_elf = set()
    prev_tail = b""
    tail_len = max(len(marker), max((len(s) for s in _FALLBACK_SIGS), default=0)) + 8
    for blk in range(vhd.max_entries):
        if vhd.bat[blk] == BAT_UNUSED:
            prev_tail = b""
            continue
        flat = blk * vhd.block_size
        data = vhd.read(flat, vhd.block_size)
        hay = prev_tail + data
        base = flat - len(prev_tail)
        # fallback: direct entry-signature matches in this block
        for sig in _FALLBACK_SIGS:
            si = 0
            while True:
                si = _match_sig(hay, sig, si)
                if si < 0:
                    break
                entries.append(base + si)
                si += 1
        pos = 0
        while True:
            j = hay.find(marker, pos)
            if j < 0:
                break
            pos = j + 1
            str_flat = base + j
            # find the ELF that owns this string: scan back through every \x7fELF
            # header that could contain it, and keep going until the locator hits
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
                    ent = su_patch._find_isdevmode_entry(elf)
                except Exception:
                    ent = None
                if ent is not None:
                    seen_elf.add(cand)
                    entries.append(cand + ent)
                    break   # found the su that owns this string
        prev_tail = data[-tail_len:]
    return sorted(set(entries))


def _find_patched_entries(vhd: DynamicVHD) -> List[int]:
    """Flat offsets of ALREADY-patched 64-bit isDeveloperMode entries.

    After patching, the entry reads `b0 01 c3 3d <rel32>` -- the `mov al,1; ret`
    plus the orphaned `lea` modrm+disp that still points at the isDeveloperMode
    string. Verifying that target lets us re-detect patched su (the locator can't,
    since the patch consumed its anchor) -- so we can rebuild backups / report
    'already rooted'. (Small/contiguous 64-bit su only.)
    """
    marker = su_patch.DEVMODE_STRING
    out: List[int] = []
    prev = b""
    for blk in range(vhd.max_entries):
        if vhd.bat[blk] == BAT_UNUSED:
            prev = b""
            continue
        flat = blk * vhd.block_size
        data = vhd.read(flat, vhd.block_size)
        hay = prev + data
        base = flat - len(prev)
        i = 0
        while True:
            i = hay.find(b"\xB0\x01\xC3", i)
            if i < 0 or i + 8 > len(hay):
                break
            # next byte is the orphaned lea's rip-relative modrm (05/0D/3D/35 etc.)
            if (hay[i + 3] & 0xC7) == 0x05:
                rel = struct.unpack_from("<i", hay, i + 4)[0]
                entry = base + i
                if vhd.read(entry + 8 + rel, len(marker)) == marker:
                    out.append(entry)
            i += 1
        prev = data[-64:]
    return sorted(set(out))


def _sidecar(vhd_path: str) -> str:
    return vhd_path + ".suroot.json"


def enable(vhd_path: str) -> List[str]:
    """Patch every gated su to grant app root; back up originals to the sidecar."""
    results: List[str] = []
    merged: Dict[int, str] = {}
    sc = _sidecar(vhd_path)
    if os.path.isfile(sc):
        for p in json.load(open(sc)).get("patches", []):
            if p.get("orig"):
                merged[p["offset"]] = p["orig"]
    vhd = DynamicVHD(vhd_path, writable=True)
    try:
        for off in _find_su_entries(vhd):           # un-patched su -> patch now
            cur = vhd.read(off, 3)
            if cur == su_patch.PATCH:
                results.append("su@0x%X already patched" % off)
                continue
            merged.setdefault(off, cur.hex(" "))      # remember the original bytes
            vhd.write(off, su_patch.PATCH)
            ok = vhd.read(off, 3) == su_patch.PATCH
            results.append("su@0x%X %s (%s -> %s)" % (
                off, "rooted" if ok else "write-verify FAILED",
                cur.hex(" "), su_patch.PATCH.hex(" ")))
        for off in _find_patched_entries(vhd):       # already patched -> just back up
            merged.setdefault(off, "53 48 8d")
            results.append("su@0x%X already rooted" % off)
    finally:
        vhd.close()
    if merged:
        json.dump({"patches": [{"offset": o, "orig": h} for o, h in merged.items()]},
                  open(sc, "w"), indent=2)
    elif not results:
        results.append("no gated su found")
    return results


def disable(vhd_path: str) -> List[str]:
    """Restore original su bytes from the sidecar (un-root)."""
    sc = _sidecar(vhd_path)
    if not os.path.isfile(sc):
        return ["no backup sidecar -- nothing to restore"]
    patches = json.load(open(sc)).get("patches", [])
    results: List[str] = []
    vhd = DynamicVHD(vhd_path, writable=True)
    try:
        for p in patches:
            off = p["offset"]
            orig = bytes(int(x, 16) for x in p["orig"].split())
            cur = vhd.read(off, 3)
            if cur == orig:
                results.append("su@0x%X already original" % off)
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


def _system_vhd(instance_dir: str) -> Optional[str]:
    p = os.path.join(instance_dir, "Root.vhd")
    return p if os.path.isfile(p) else None


# --- instance-level helpers for the GUI -----------------------------------
def instance_root_state(instance_dir: str) -> bool:
    """True if this instance's su is patched (rooted), tracked by the backup sidecar."""
    vhd = _system_vhd(instance_dir)
    return bool(vhd and os.path.isfile(_sidecar(vhd)))


def set_instance_root(instance_dir: str, on: bool) -> List[str]:
    """Root (patch su + back up) or un-root (restore su) a single instance.

    The instance must be shut down. Returns human-readable status lines.
    """
    vhd = _system_vhd(instance_dir)
    if not vhd:
        return ["Root.vhd not found in %s" % instance_dir]
    return enable(vhd) if on else disable(vhd)


def _collect(targets: List[str], all_instances: bool) -> List[str]:
    vhds: List[str] = []
    if all_instances or not targets:
        if os.path.isdir(ENGINE_DIR):
            for n in sorted(os.listdir(ENGINE_DIR)):
                v = _system_vhd(os.path.join(ENGINE_DIR, n))
                if v:
                    vhds.append(v)
    for t in targets:
        if t.lower().endswith(".vhd") and os.path.isfile(t):
            vhds.append(t)
        elif os.path.isdir(t):
            v = _system_vhd(t)
            if v:
                vhds.append(v)
            else:
                for n in sorted(os.listdir(t)):
                    v2 = _system_vhd(os.path.join(t, n))
                    if v2:
                        vhds.append(v2)
    return list(dict.fromkeys(vhds))


def run(targets: List[str], action: str, all_instances: bool) -> List[Tuple[str, List[str]]]:
    out = []
    for v in _collect(targets, all_instances):
        try:
            if action == "enable":
                out.append((v, enable(v)))
            elif action == "disable":
                out.append((v, disable(v)))
            else:  # dry-run: just locate
                vhd = DynamicVHD(v)
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
    ap.add_argument("targets", nargs="*", help="Root.vhd / instance dir / engine dir")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--enable", action="store_true", help="patch su (root), back up originals")
    g.add_argument("--disable", action="store_true", help="restore su from backup (un-root)")
    ap.add_argument("--all", action="store_true", help="all instances under the engine dir")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    action = "enable" if args.enable else "disable" if args.disable else "dryrun"
    res = run(args.targets, action, args.all)
    if not res:
        logger.error("No Root.vhd found.")
        return 1
    for vhd, lines in res:
        print("[%s] %s" % (action.upper(), vhd))
        for ln in lines:
            print("    " + ln)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
