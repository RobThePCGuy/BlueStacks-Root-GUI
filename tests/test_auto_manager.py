"""The manager app installs itself after Manager Root goes in.

Booting the instance and pressing a second button for something the app can do
itself was the most confusing part of the flow, so the install now finishes the
job. The rule that matters here: the offline root install has already succeeded
by this point and is valuable on its own, so nothing in the follow-up may turn a
successful install into a reported failure.
"""
from unittest.mock import MagicMock

import pytest

import adb_handler
from views.main_window import MainWindow


class _CP:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


# --- adb_handler.wait_until_ready -------------------------------------------

def test_wait_until_ready_returns_the_serial_once_boot_completes():
    """Connectable is not enough: an app install into a half-booted guest fails."""
    calls = {"n": 0}

    def runner(cmd, **kw):
        if cmd[-1] == "connect" or "connect" in cmd:
            return _CP("connected to 127.0.0.1:5555")
        if cmd[-1] == "devices":
            return _CP("List of devices attached\n127.0.0.1:5555\tdevice\n")
        if "sys.boot_completed" in cmd:
            calls["n"] += 1
            return _CP("1" if calls["n"] >= 3 else "")   # boots on the third poll
        return _CP()

    slept = []
    serial = adb_handler.wait_until_ready("adb", 5555, timeout=60,
                                          runner=runner, sleep=slept.append)
    assert serial == "127.0.0.1:5555"
    assert slept, "should have waited rather than busy-looping"


def test_wait_until_ready_gives_up_instead_of_hanging_forever():
    def runner(cmd, **kw):
        if cmd[-1] == "devices":
            return _CP("List of devices attached\n")
        return _CP()

    slept = []
    assert adb_handler.wait_until_ready("adb", 5555, timeout=20,
                                        runner=runner, sleep=slept.append) is None
    assert sum(1 for _ in slept) <= 5      # bounded by the timeout


def test_wait_until_ready_reports_progress_while_waiting():
    seen = []

    def runner(cmd, **kw):
        return _CP("List of devices attached\n") if cmd[-1] == "devices" else _CP()

    adb_handler.wait_until_ready("adb", 5555, timeout=15, progress=seen.append,
                                 runner=runner, sleep=lambda _s: None)
    assert seen and "booting" in seen[0].lower()


# --- the controller's follow-up step ----------------------------------------

@pytest.fixture
def controller(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    return window.magisk_controller


def test_manager_step_is_skipped_cleanly_without_adb(controller):
    msg = controller._finish_with_manager(
        {"data_path": "data"}, "install", "Tiramisu64", "conf", adb_exe=None, port=None,
        report=lambda _m: None)
    assert "installed" in msg.lower()
    assert "manager app" in msg.lower()      # tells the user the retry


def test_a_failed_manager_step_does_not_report_a_failed_install(controller, monkeypatch):
    """The root is already in; this must read as a follow-up, not an error."""
    monkeypatch.setattr("config_handler.modify_config_file", lambda *a, **k: True)
    monkeypatch.setattr("instance_handler.launch_instance",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no player")))
    msg = controller._finish_with_manager(
        {"data_path": "data"}, "install", "Tiramisu64", "conf", adb_exe="adb", port=5555,
        report=lambda _m: None)
    assert "Manager Root installed" in msg
    assert "retry" in msg.lower()


def test_a_boot_timeout_is_reported_as_a_follow_up(controller, monkeypatch):
    monkeypatch.setattr("config_handler.modify_config_file", lambda *a, **k: True)
    monkeypatch.setattr("instance_handler.launch_instance", lambda *a, **k: None)
    monkeypatch.setattr("adb_handler.wait_until_ready", lambda *a, **k: None)
    msg = controller._finish_with_manager(
        {"data_path": "data"}, "install", "Tiramisu64", "conf", adb_exe="adb", port=5555,
        report=lambda _m: None)
    assert "did not finish booting" in msg


def test_the_happy_path_installs_the_app_and_records_it(controller, monkeypatch):
    monkeypatch.setattr("config_handler.modify_config_file", lambda *a, **k: True)
    monkeypatch.setattr("instance_handler.launch_instance", lambda *a, **k: None)
    monkeypatch.setattr("adb_handler.wait_until_ready", lambda *a, **k: "127.0.0.1:5555")
    monkeypatch.setattr("magisk_payload.fetch_apk", lambda *a, **k: "apk")
    installed = MagicMock(return_value="Installed")
    monkeypatch.setattr("adb_handler.install_manager", installed)
    recorded = MagicMock()
    monkeypatch.setattr("magisk_system.add_component", recorded)

    msg = controller._finish_with_manager(
        {"data_path": "data"}, "install", "Tiramisu64", "conf", adb_exe="adb", port=5555,
        report=lambda _m: None)

    installed.assert_called_once()
    recorded.assert_called_once_with("data", "manager")   # status stays honest
    assert "app are installed" in msg


def test_adb_is_enabled_before_launching(controller, monkeypatch):
    """ADB is off by default on a fresh instance, which is what made this step
    unreliable when done by hand."""
    import constants
    wrote = []
    monkeypatch.setattr("config_handler.modify_config_file",
                        lambda path, key, val: wrote.append((key, val)))
    monkeypatch.setattr("instance_handler.launch_instance", lambda *a, **k: None)
    monkeypatch.setattr("adb_handler.wait_until_ready", lambda *a, **k: None)
    controller._finish_with_manager({"data_path": "data"}, "install", "Tiramisu64", "conf",
                                    adb_exe="adb", port=5555, report=lambda _m: None)
    assert (constants.ENABLE_ADB_KEY, "1") in wrote
