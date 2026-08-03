"""Detection of a BlueStacks Air install, against a faked bundle on disk.

Everything here is filesystem shape, so it runs on any host: the tests build a
miniature BlueStacks.app + shared data directory in tmp_path and point the
module's two hard-coded locations at it.
"""
from __future__ import annotations

import plistlib

import pytest

import constants
import macos_locator


@pytest.fixture
def air(tmp_path, monkeypatch):
    """A minimal but complete-looking Air installation."""
    app = tmp_path / "BlueStacks.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
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
