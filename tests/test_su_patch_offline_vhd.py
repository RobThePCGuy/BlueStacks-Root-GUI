"""Coverage for ``su_patch_offline``'s hand-rolled VHD/VHDX readers
(``DynamicVHD`` / ``DynamicVHDX``) and the ``open_disk`` format dispatch.

These classes are the foundation every guest-su patch operation is built on
(``enable``/``disable`` read and write through them with no other safety net),
and previously had zero test coverage. Rather than requiring a real
BlueStacks-generated disk image, each test builds a minimal synthetic VHD or
VHDX byte structure that satisfies exactly what ``__init__`` parses -- footer/
dynamic-header/BAT for VHD, region-table/metadata-table/BAT for VHDX -- so the
parsing, block-presence, read (incl. zero-fill of holes), and write (incl. the
boundary/allocation guards) logic is exercised without any Windows-only disk
attach.
"""
from __future__ import annotations

import struct

import pytest

import su_patch_offline as spo


# --------------------------------------------------------------------------
# VHD (legacy dynamic VHD, e.g. Root.vhd) synthetic fixture
# --------------------------------------------------------------------------

def _build_vhd(tmp_path, present_blocks: dict[int, bytes], max_entries=4,
               block_size=512, disk_type=3):
    """A minimal dynamic VHD: [dynamic header][BAT][block regions...][footer].

    ``present_blocks`` maps block index -> exact ``block_size``-byte payload;
    any index in range(max_entries) not present is left BAT_UNUSED (a hole).
    """
    spb = block_size // 512
    bitmap_size = (((spb + 7) // 8 + 511) // 512) * 512
    region_size = bitmap_size + block_size

    dyn_off = 0
    bat_off = 1024
    data_start = bat_off + max_entries * 4
    if data_start % 512:
        data_start += 512 - (data_start % 512)

    bat = [spo.BAT_UNUSED] * max_entries
    placements: dict[int, int] = {}  # block -> byte offset of its region
    cursor = data_start
    for blk in sorted(present_blocks):
        placements[blk] = cursor
        bat[blk] = cursor // 512
        cursor += region_size

    dh = bytearray(1024)
    dh[0:8] = spo.DYN_COOKIE
    struct.pack_into(">Q", dh, 16, bat_off)
    struct.pack_into(">I", dh, 28, max_entries)
    struct.pack_into(">I", dh, 32, block_size)

    footer = bytearray(512)
    footer[0:8] = spo.VHD_FOOTER_COOKIE
    struct.pack_into(">Q", footer, 16, dyn_off)
    struct.pack_into(">I", footer, 60, disk_type)

    path = tmp_path / "Root.vhd"
    with open(path, "wb") as f:
        f.write(bytes(dh))
        f.seek(bat_off)
        f.write(struct.pack(">%dI" % max_entries, *bat))
        for blk, payload in present_blocks.items():
            assert len(payload) == block_size
            off = placements[blk]
            f.seek(off + bitmap_size)
            f.write(payload)
        f.seek(cursor)
        f.write(bytes(footer))
    return str(path)


def test_dynamicvhd_is_present_matches_bat_holes(tmp_path):
    path = _build_vhd(tmp_path, {0: b"A" * 512, 2: b"C" * 512})
    vhd = spo.DynamicVHD(path)
    try:
        assert [vhd.is_present(i) for i in range(4)] == [True, False, True, False]
        assert vhd.is_present(4) is False  # out of range
    finally:
        vhd.close()


def test_dynamicvhd_read_zero_fills_holes(tmp_path):
    path = _build_vhd(tmp_path, {0: b"A" * 512, 2: b"C" * 512})
    vhd = spo.DynamicVHD(path)
    try:
        assert vhd.read(0, 512) == b"A" * 512
        assert vhd.read(512, 512) == b"\x00" * 512  # block 1: unallocated hole
        assert vhd.read(1024, 512) == b"C" * 512
    finally:
        vhd.close()


def test_dynamicvhd_write_round_trips_and_leaves_neighbors_untouched(tmp_path):
    path = _build_vhd(tmp_path, {0: b"A" * 512, 2: b"C" * 512})
    vhd = spo.DynamicVHD(path, writable=True)
    try:
        vhd.write(0, b"Z" * 512)
        vhd.write(10, b"XXXX")  # partial in-block write
        expected = bytearray(b"Z" * 512)
        expected[10:14] = b"XXXX"
        assert vhd.read(0, 512) == bytes(expected)
        assert vhd.read(1024, 512) == b"C" * 512  # untouched sibling block
    finally:
        vhd.close()


def test_dynamicvhd_write_to_unallocated_block_raises(tmp_path):
    path = _build_vhd(tmp_path, {0: b"A" * 512})
    vhd = spo.DynamicVHD(path, writable=True)
    try:
        with pytest.raises(OSError):
            vhd.write(512, b"x")  # block 1 has no BAT entry
    finally:
        vhd.close()


def test_dynamicvhd_write_crossing_block_boundary_raises(tmp_path):
    path = _build_vhd(tmp_path, {0: b"A" * 512, 1: b"B" * 512})
    vhd = spo.DynamicVHD(path, writable=True)
    try:
        with pytest.raises(OSError):
            vhd.write(500, b"Y" * 20)  # 500 + 20 > block_size (512)
    finally:
        vhd.close()


def test_dynamicvhd_rejects_non_vhd_file(tmp_path):
    path = tmp_path / "not_a.vhd"
    path.write_bytes(b"\x00" * 4096)
    with pytest.raises(ValueError, match="not a VHD"):
        spo.DynamicVHD(str(path))


def test_dynamicvhd_rejects_non_dynamic_disk_type(tmp_path):
    # disk_type=2 is "fixed", not "dynamic" (3) -- the only type this reader supports.
    path = _build_vhd(tmp_path, {0: b"A" * 512}, disk_type=2)
    with pytest.raises(ValueError, match="not a dynamic VHD"):
        spo.DynamicVHD(path)


# --------------------------------------------------------------------------
# VHDX (Data.vhdx) synthetic fixture
# --------------------------------------------------------------------------

_REGION_TABLE_OFF = 0x30000
_META_OFF = 0x40000
_BAT_OFF = 0x50000
_FILEPARAMS_REL_OFF = 128
_VDISKSIZE_REL_OFF = 256


def _build_vhdx(tmp_path, present_blocks: dict[int, bytes], max_entries=3,
                block_size=4096, dirty=False, missing_regions=False):
    """A minimal VHDX: signature, optional dirty-log header, region table
    (BAT + Metadata), metadata table (FileParameters + VirtualDiskSize), BAT,
    and 1 MiB-aligned block payloads (real VHDX BAT entries encode the
    physical offset in bits 20-63, so payload placement must be 1 MiB-aligned;
    the file is sparse, so this doesn't cost real disk space)."""
    virtual_size = max_entries * block_size
    path = tmp_path / "Data.vhdx"
    with open(path, "wb") as f:
        f.write(spo.VHDX_SIGNATURE)

        if dirty:
            hdr = bytearray(64)
            hdr[0:4] = b"head"
            struct.pack_into("<Q", hdr, 8, 1)
            hdr[48:64] = bytes(range(1, 17))  # non-zero LogGuid
            f.seek(0x10000)
            f.write(bytes(hdr))

        rhdr = bytearray(16)
        rhdr[0:4] = b"regi"
        struct.pack_into("<I", rhdr, 8, 0 if missing_regions else 2)
        f.seek(_REGION_TABLE_OFF)
        f.write(bytes(rhdr))
        if not missing_regions:
            bat_entry = bytearray(32)
            bat_entry[0:16] = spo._VHDX_REG_BAT
            struct.pack_into("<Q", bat_entry, 16, _BAT_OFF)
            f.write(bytes(bat_entry))
            meta_entry = bytearray(32)
            meta_entry[0:16] = spo._VHDX_REG_META
            struct.pack_into("<Q", meta_entry, 16, _META_OFF)
            f.write(bytes(meta_entry))

            mhdr = bytearray(32)
            mhdr[0:8] = b"metadata"
            struct.pack_into("<H", mhdr, 10, 2)
            f.seek(_META_OFF)
            f.write(bytes(mhdr))
            me1 = bytearray(32)
            me1[0:16] = spo._VHDX_MD_FILEPARAMS
            struct.pack_into("<I", me1, 16, _FILEPARAMS_REL_OFF)
            f.write(bytes(me1))
            me2 = bytearray(32)
            me2[0:16] = spo._VHDX_MD_VDISKSIZE
            struct.pack_into("<I", me2, 16, _VDISKSIZE_REL_OFF)
            f.write(bytes(me2))
            f.seek(_META_OFF + _FILEPARAMS_REL_OFF)
            f.write(struct.pack("<I", block_size))
            f.seek(_META_OFF + _VDISKSIZE_REL_OFF)
            f.write(struct.pack("<Q", virtual_size))

            for blk in range(max_entries):
                phys = 0x100000 * (blk + 1)
                entry = (phys | spo._VHDX_BAT_FULLY_PRESENT) if blk in present_blocks else 0
                f.seek(_BAT_OFF + blk * 8)
                f.write(struct.pack("<Q", entry))

            for blk, payload in present_blocks.items():
                assert len(payload) == block_size
                f.seek(0x100000 * (blk + 1))
                f.write(payload)
    return str(path)


def test_dynamicvhdx_is_present_matches_bat_holes(tmp_path):
    path = _build_vhdx(tmp_path, {0: b"A" * 4096, 2: b"C" * 4096})
    vhdx = spo.DynamicVHDX(path)
    try:
        assert [vhdx.is_present(i) for i in range(3)] == [True, False, True]
        assert vhdx.dirty is False
    finally:
        vhdx.close()


def test_dynamicvhdx_read_zero_fills_holes(tmp_path):
    path = _build_vhdx(tmp_path, {0: b"A" * 4096, 2: b"C" * 4096})
    vhdx = spo.DynamicVHDX(path)
    try:
        assert vhdx.read(0, 4096) == b"A" * 4096
        assert vhdx.read(4096, 4096) == b"\x00" * 4096  # block 1: unallocated hole
        assert vhdx.read(2 * 4096, 4096) == b"C" * 4096
    finally:
        vhdx.close()


def test_dynamicvhdx_write_round_trips_and_leaves_neighbors_untouched(tmp_path):
    path = _build_vhdx(tmp_path, {0: b"A" * 4096, 2: b"C" * 4096})
    vhdx = spo.DynamicVHDX(path, writable=True)
    try:
        vhdx.write(0, b"Z" * 4096)
        vhdx.write(10, b"XXXX")
        expected = bytearray(b"Z" * 4096)
        expected[10:14] = b"XXXX"
        assert vhdx.read(0, 4096) == bytes(expected)
        assert vhdx.read(2 * 4096, 4096) == b"C" * 4096
    finally:
        vhdx.close()


def test_dynamicvhdx_write_to_unallocated_block_raises(tmp_path):
    path = _build_vhdx(tmp_path, {0: b"A" * 4096})
    vhdx = spo.DynamicVHDX(path, writable=True)
    try:
        with pytest.raises(OSError):
            vhdx.write(4096, b"x")  # block 1 has no BAT entry
    finally:
        vhdx.close()


def test_dynamicvhdx_write_crossing_block_boundary_raises(tmp_path):
    path = _build_vhdx(tmp_path, {0: b"A" * 4096, 1: b"B" * 4096})
    vhdx = spo.DynamicVHDX(path, writable=True)
    try:
        with pytest.raises(OSError):
            vhdx.write(4090, b"Y" * 20)  # 4090 + 20 > block_size (4096)
    finally:
        vhdx.close()


def test_dynamicvhdx_dirty_flag_true_when_log_guid_nonzero(tmp_path):
    path = _build_vhdx(tmp_path, {0: b"A" * 4096}, dirty=True)
    vhdx = spo.DynamicVHDX(path)
    try:
        assert vhdx.dirty is True
    finally:
        vhdx.close()


def test_dynamicvhdx_rejects_bad_signature(tmp_path):
    path = tmp_path / "not_a.vhdx"
    path.write_bytes(b"\x00" * 4096)
    with pytest.raises(ValueError, match="not a VHDX"):
        spo.DynamicVHDX(str(path))


def test_dynamicvhdx_rejects_missing_bat_or_metadata_region(tmp_path):
    path = _build_vhdx(tmp_path, {}, missing_regions=True)
    with pytest.raises(ValueError, match="missing BAT or Metadata region"):
        spo.DynamicVHDX(path)


# --------------------------------------------------------------------------
# open_disk(): format dispatch by signature (the "transparently" promise in
# the module's own docstring -- previously unverified).
# --------------------------------------------------------------------------

def test_open_disk_dispatches_vhd_and_vhdx_by_signature(tmp_path):
    vhd_path = _build_vhd(tmp_path, {0: b"A" * 512})
    vhdx_path = _build_vhdx(tmp_path, {0: b"A" * 4096})

    vhd = spo.open_disk(vhd_path)
    try:
        assert isinstance(vhd, spo.DynamicVHD)
    finally:
        vhd.close()

    vhdx = spo.open_disk(vhdx_path)
    try:
        assert isinstance(vhdx, spo.DynamicVHDX)
    finally:
        vhdx.close()
