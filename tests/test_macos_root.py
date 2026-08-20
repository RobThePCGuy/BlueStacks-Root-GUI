"""Coverage for the Air rooting engine's decisions, without touching a real image.

The 1.7 GB convert/edit/repack round-trip is validated live against a real
BlueStacks Air install; what is worth locking in here is the logic that decides
*what* to do and *when to refuse*: where the ext4 actually starts, whether the
recorded root state is still trustworthy, and that the two failure modes a user
will actually hit (e2fsprogs missing, macOS App Management blocking the write)
produce an actionable message rather than a raw errno.
"""
from __future__ import annotations

import json
import os
import struct

import pytest

import macos_root
import platform_support


# --- partition geometry --------------------------------------------------

def _mbr_image(tmp_path, *, part_type=0x83, start_lba=2048, signature=True):
    mbr = bytearray(512)
    if signature:
        mbr[510:512] = b"\x55\xaa"
    entry = bytearray(16)
    entry[4] = part_type
    entry[8:12] = struct.pack("<I", start_lba)
    entry[12:16] = struct.pack("<I", 1000)
    mbr[446:462] = entry
    path = tmp_path / "Root.raw"
    path.write_bytes(bytes(mbr))
    return str(path)


def test_partition_offset_is_read_not_assumed(tmp_path):
    # 1 MiB is the value on today's build, but a future one is free to differ.
    assert macos_root.partition_offset(_mbr_image(tmp_path)) == 2048 * 512
    assert macos_root.partition_offset(
        _mbr_image(tmp_path, start_lba=4096)) == 4096 * 512


def test_refuses_an_image_with_no_mbr_signature(tmp_path):
    with pytest.raises(macos_root.RootError, match="MBR signature"):
        macos_root.partition_offset(_mbr_image(tmp_path, signature=False))


def test_refuses_an_image_with_no_linux_partition(tmp_path):
    # Editing the wrong partition would corrupt the system image rather than
    # fail, so an unrecognised layout has to stop the operation.
    with pytest.raises(macos_root.RootError, match="No Linux partition"):
        macos_root.partition_offset(_mbr_image(tmp_path, part_type=0x07))


# --- recorded state ------------------------------------------------------

@pytest.fixture
def rooted(tmp_path, monkeypatch):
    """An app bundle whose image is recorded as rooted."""
    app = tmp_path / "BlueStacks.app"
    (app / "Contents" / "img").mkdir(parents=True)
    image = app / "Contents" / "img" / "Root.qcow2"
    image.write_bytes(b"pretend-qcow2")
    data = tmp_path / "data"
    data.mkdir()
    macos_root.write_modstate(str(app), str(data), {"root": True})
    return str(app), str(data), image


def test_reports_rooted_when_state_matches_the_image(rooted):
    app, data, _ = rooted
    assert macos_root.image_root_state(app, data) is True


def test_reports_not_rooted_without_a_state_file(rooted):
    app, data, _ = rooted
    os.unlink(os.path.join(data, macos_root.STATE_NAME))
    assert macos_root.image_root_state(app, data) is False


def test_a_replaced_image_reads_as_not_rooted(rooted):
    """A BlueStacks update overwrites the image and silently drops root.

    The fingerprint stops matching, and reporting "still rooted" would leave the
    user believing they have root they no longer have.
    """
    app, data, image = rooted
    image.write_bytes(b"a-completely-different-image")
    assert macos_root.image_root_state(app, data) is False


def test_state_records_what_was_injected(rooted):
    _, data, _ = rooted
    state = json.load(open(os.path.join(data, macos_root.STATE_NAME), encoding="utf-8"))
    import macos_su
    assert state["su_sha256"] == macos_su.su_sha256()
    assert state["su_path"] == macos_root.SU_GUEST_PATH


def test_missing_image_reads_as_not_rooted(rooted):
    app, data, image = rooted
    image.unlink()
    assert macos_root.image_root_state(app, data) is False


# --- failure modes the user will actually hit ----------------------------

def test_missing_e2fsprogs_explains_how_to_install_it(monkeypatch):
    monkeypatch.setattr(macos_root, "_find_tool", lambda name: None)
    with pytest.raises(macos_root.RootError, match="brew install e2fsprogs"):
        macos_root.find_e2fs_tools()


def test_app_management_denial_is_translated(monkeypatch, tmp_path):
    """macOS refuses bundle writes with EPERM even as root.

    Elevating does not help, so the message must send the user to the App
    Management setting instead of implying they need admin rights.
    """
    def deny(script, *, label, timeout=1800):
        raise platform_support.ElevationError(
            "%s failed: cp: /Applications/BlueStacks.app/Contents/img/"
            "Root.qcow2: Operation not permitted" % label)

    monkeypatch.setattr(platform_support, "run_elevated", deny)
    src, dst = tmp_path / "new.qcow2", tmp_path / "old.qcow2"
    src.write_bytes(b"x")
    with pytest.raises(macos_root.RootError, match="App Management"):
        macos_root._install_image(str(src), str(dst), label="update the image")


def test_cancelled_prompt_is_not_reported_as_app_management(monkeypatch, tmp_path):
    def cancel(script, *, label, timeout=1800):
        raise platform_support.ElevationError(
            "Administrator access is required to %s, and the prompt was dismissed."
            % label)

    monkeypatch.setattr(platform_support, "run_elevated", cancel)
    with pytest.raises(macos_root.RootError, match="prompt was dismissed"):
        macos_root._install_image("a", "b", label="update the image")


def test_writes_directly_without_prompting_when_permitted(tmp_path, monkeypatch):
    """No authorization prompt when the image is writable.

    ``Root.qcow2`` ships mode rw-rw-rw-, and App Management is granted to an
    *app* rather than to root -- an elevated helper does not inherit it, so
    escalating can fail exactly where a direct write succeeds. The direct write
    has to be tried first, and the common case must be prompt-free.
    """
    src, dst = tmp_path / "new.qcow2", tmp_path / "Root.qcow2"
    src.write_bytes(b"new-contents-that-are-longer")
    dst.write_bytes(b"old")
    prompted = []
    monkeypatch.setattr(platform_support, "run_elevated",
                        lambda *a, **k: prompted.append(1))

    macos_root._install_image(str(src), str(dst), label="update the image")

    assert dst.read_bytes() == b"new-contents-that-are-longer"
    assert prompted == [], "must not prompt when a plain write works"


def test_direct_write_keeps_the_destination_inode(tmp_path):
    """Contents/img is root-owned, so the image cannot be replaced -- only
    overwritten in place."""
    src, dst = tmp_path / "new.qcow2", tmp_path / "Root.qcow2"
    src.write_bytes(b"shorter")
    dst.write_bytes(b"much-longer-original-contents")
    before = os.stat(dst).st_ino

    macos_root._copy_in_place(str(src), str(dst))

    assert dst.read_bytes() == b"shorter", "stale tail must be truncated"
    assert os.stat(dst).st_ino == before


def test_turning_root_off_restores_the_backup_without_touching_e2fsprogs(
        tmp_path, monkeypatch):
    """The undo path is a file copy; it must not require the optional tools."""
    app = tmp_path / "BlueStacks.app"
    (app / "Contents" / "img").mkdir(parents=True)
    image = app / "Contents" / "img" / "Root.qcow2"
    image.write_bytes(b"rooted-image")
    data = tmp_path / "data"
    data.mkdir()
    backup = data / macos_root.BACKUP_NAME
    backup.write_bytes(b"pristine-image")
    macos_root.write_modstate(str(app), str(data), {"root": True})

    # Neither tool may be consulted on the undo path: a user who never
    # installed e2fsprogs must still be able to get back to stock.
    def boom():
        raise AssertionError("undo must not need e2fsprogs")

    monkeypatch.setattr(macos_root, "find_e2fs_tools", boom)
    monkeypatch.setattr(macos_root, "find_qemu_img", lambda app_path: "qemu-img")
    monkeypatch.setattr(platform_support, "IS_MACOS", True)

    results = macos_root.set_root(str(app), False, data_dir=str(data))

    assert image.read_bytes() == b"pristine-image"
    assert any("restored" in r for r in results)
    # ...and the recorded state is cleared, so the UI stops claiming root.
    assert not os.path.exists(os.path.join(str(data), macos_root.STATE_NAME))


def test_backup_is_deleted_after_a_successful_restore(tmp_path, monkeypatch):
    """A kept backup goes stale the moment BlueStacks updates.

    Re-rooting after an update would otherwise reuse the previous build's
    image as the "original", so undoing would downgrade /system rather than
    restore it.
    """
    app = tmp_path / "BlueStacks.app"
    (app / "Contents" / "img").mkdir(parents=True)
    image = app / "Contents" / "img" / "Root.qcow2"
    image.write_bytes(b"rooted-image")
    data = tmp_path / "data"
    data.mkdir()
    backup = data / macos_root.BACKUP_NAME
    backup.write_bytes(b"pristine-image")
    macos_root.write_modstate(str(app), str(data), {"root": True})
    monkeypatch.setattr(macos_root, "find_qemu_img", lambda app_path: "qemu-img")
    monkeypatch.setattr(platform_support, "IS_MACOS", True)

    macos_root.set_root(str(app), False, data_dir=str(data))

    assert not backup.exists()


def test_elevation_is_the_fallback_when_the_direct_write_fails(tmp_path, monkeypatch):
    """An image that is not user-writable still gets through, via a prompt."""
    src, dst = tmp_path / "new.qcow2", tmp_path / "Root.qcow2"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")

    def refuse(source, dest):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(macos_root, "_copy_in_place", refuse)
    prompted = []

    def fake_elevated(script, *, label, timeout=1800):
        prompted.append(label)
        dst.write_bytes(src.read_bytes())
        return ""

    monkeypatch.setattr(platform_support, "run_elevated", fake_elevated)

    macos_root._install_image(str(src), str(dst), label="update the image")

    assert prompted, "must fall back to an authorization prompt"
    assert dst.read_bytes() == b"new"
