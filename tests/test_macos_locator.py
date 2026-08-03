"""Detection of a BlueStacks Air install, against a faked bundle on disk.

Everything here is filesystem shape, so it runs on any host: the tests build a
miniature BlueStacks.app + shared data directory in tmp_path and point the
module's two hard-coded locations at it.
"""
from __future__ import annotations

import plistlib
import struct

import pytest

import constants
import macos_locator

CPU_ARM64 = 0x0100000C
CPU_X86_64 = 0x01000007


def _write_macho(path, cputype):
    """A minimal thin 64-bit Mach-O header with the given cputype."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xcf\xfa\xed\xfe" + struct.pack("<I", cputype) + b"\0" * 24)


def _write_fat(path, cputypes):
    """A universal binary header advertising several architectures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = b"\xca\xfe\xba\xbe" + struct.pack(">I", len(cputypes))
    for cpu in cputypes:
        blob += struct.pack(">I", cpu) + b"\0" * 16
    path.write_bytes(blob)


@pytest.fixture
def air(tmp_path, monkeypatch):
    """A minimal but complete-looking Air installation."""
    app = tmp_path / "BlueStacks.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    # Detection refuses anything that isn't the Apple Silicon build, so the
    # fixture has to carry a real (if stub) arm64 player binary.
    _write_macho(app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME, CPU_ARM64)
    (app / "Contents" / "img").mkdir(parents=True)
    (app / "Contents" / "img" / "Root.qcow2").write_bytes(b"qcow")
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleShortVersionString": "5.21.782"}, fh)

    data = tmp_path / "data"
    (data / "Engine" / "Tiramisu64").mkdir(parents=True)
    (data / "Engine" / "UserData").mkdir(parents=True)
    (data / "bluestacks.conf").write_text(
        'bst.instance.Tiramisu64.enable_root_access="0"\n', encoding="utf-8")

    monkeypatch.setattr(macos_locator, "DEFAULT_APP_PATH", str(app))
    monkeypatch.setattr(macos_locator, "DATA_DIR", str(data))
    monkeypatch.setattr(macos_locator, "SETTING_PLIST", str(data / "setting.plist"))
    return app, data


def test_finds_install_and_reports_registry_handler_shape(air):
    app, data = air
    (inst,) = macos_locator.get_all_bluestacks_installations()

    assert inst["source"] == constants.APP_SOURCE_AIR
    assert inst["version"] == (5, 21, 782)
    assert inst["config_path"] == str(data / "bluestacks.conf")
    assert inst["app_path"] == str(app)
    # Instances live under Engine/, not the data dir itself.
    assert inst["data_path"] == str(data / "Engine")
    # Air has no 5.22 integrity check and no .exe to patch, so the Dashboard's
    # engine-patch button must stay hidden.
    assert inst["patch_mode"] is False
    assert inst["air_mode"] is True


def test_reports_nothing_when_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(macos_locator, "DEFAULT_APP_PATH", str(tmp_path / "nope.app"))
    monkeypatch.setattr(macos_locator, "SETTING_PLIST", str(tmp_path / "nope.plist"))
    assert macos_locator.get_all_bluestacks_installations() == []


def test_bundle_without_a_conf_is_not_reported(air):
    """Installed but never launched: no conf, no instances, nothing to show."""
    _, data = air
    (data / "bluestacks.conf").unlink()
    assert macos_locator.get_all_bluestacks_installations() == []


def test_userdata_is_not_listed_as_an_instance(air):
    _, data = air
    assert macos_locator.list_instance_dirs(str(data)) == ["Tiramisu64"]


def test_setting_plist_overrides_the_default_location(air, tmp_path, monkeypatch):
    """A relocated bundle is found through setting.plist."""
    app, data = air
    moved = tmp_path / "Elsewhere" / "BlueStacks.app"
    moved.parent.mkdir()
    app.rename(moved)
    with open(data / "setting.plist", "wb") as fh:
        plistlib.dump({macos_locator.SETTING_PATH_KEY:
                       str(moved / "Contents" / "MacOS")}, fh)

    (inst,) = macos_locator.get_all_bluestacks_installations()
    assert inst["app_path"] == str(moved)


def test_bundled_tool_requires_executability(air):
    app, _ = air
    adb = app / "Contents" / "MacOS" / "hd-adb"
    adb.write_bytes(b"#!/bin/sh\n")
    # Present but not executable is a broken install, not a usable adb.
    assert macos_locator.bundled_tool(str(app), "hd-adb") is None
    adb.chmod(0o755)
    assert macos_locator.bundled_tool(str(app), "hd-adb") == str(adb)


def test_root_image_path_points_into_the_bundle(air):
    app, _ = air
    assert macos_locator.root_image_path(str(app)) == \
        str(app / "Contents" / "img" / "Root.qcow2")


# --- Apple Silicon only --------------------------------------------------
# The Intel macOS BlueStacks is a different product inside (VirtualBox, VHDX
# disks, x86 guest). Detecting it as Air would not merely fail -- macos_root
# would write an *aarch64* su into an x86 guest, leaving a modified system
# image and an su that cannot exec. So detection fails closed.

def test_reports_arm64_player(air):
    app, _ = air
    _write_macho(app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME, CPU_ARM64)
    assert macos_locator.player_architectures(str(app)) == {"arm64"}


def test_reports_x86_player(air):
    app, _ = air
    _write_macho(app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME, CPU_X86_64)
    assert macos_locator.player_architectures(str(app)) == {"x86_64"}


def test_reads_universal_binary(air):
    app, _ = air
    _write_fat(app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME, [CPU_X86_64, CPU_ARM64])
    assert macos_locator.player_architectures(str(app)) == {"x86_64", "arm64"}


def test_intel_install_is_not_reported_as_air(air):
    app, _ = air
    _write_macho(app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME, CPU_X86_64)
    assert macos_locator.get_all_bluestacks_installations() == []


def test_universal_build_with_arm64_is_supported(air):
    """A future universal build still runs the arm64 guest; accept it."""
    app, _ = air
    _write_fat(app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME, [CPU_X86_64, CPU_ARM64])
    assert len(macos_locator.get_all_bluestacks_installations()) == 1


def test_unreadable_player_fails_closed(air):
    """Never edit a system image belonging to a build we could not identify."""
    app, _ = air
    (app / "Contents" / "MacOS" / macos_locator.PLAYER_NAME).unlink()
    assert macos_locator.player_architectures(str(app)) == set()
    assert macos_locator.get_all_bluestacks_installations() == []
