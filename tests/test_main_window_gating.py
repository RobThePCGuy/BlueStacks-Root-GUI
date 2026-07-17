from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMessageBox

from views.main_window import MainWindow

# Note: MainWindow() is safe to construct in tests without touching the
# registry -- initialize_paths_and_instances only runs via
# QTimer.singleShot(0, ...), which needs an active event loop (app.exec_())
# to fire. Nothing in these tests calls that, so it never fires.


def test_toggle_root_blocked_when_patch_mode_unpatched(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = {
        "Pie64 (Normal)": {"patch_mode": True, "root_enabled": False,
                           "config_path": "c", "original_name": "Pie64"},
    }
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.checkboxes["Pie64 (Normal)"].setChecked(True)
    monkeypatch.setattr(window, "_engine_state", lambda: "unpatched")

    warned = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warned)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window.handle_toggle_root()

    warned.assert_called_once()
    ran.assert_not_called()


def test_toggle_root_proceeds_when_engine_patched(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = {
        "Pie64 (Normal)": {"patch_mode": True, "root_enabled": False,
                           "config_path": "c", "original_name": "Pie64"},
    }
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.checkboxes["Pie64 (Normal)"].setChecked(True)
    monkeypatch.setattr(window, "_engine_state", lambda: "patched")

    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window.handle_toggle_root()

    ran.assert_called_once()


def test_toggle_root_off_allowed_when_engine_unpatched(qtbot, monkeypatch):
    # A patch-mode instance that is currently rooted must be togglable OFF even
    # when the engine is unpatched (e.g. an auto-update reverted the patch) --
    # disabling root doesn't need the engine patch, so it must not be blocked.
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = {
        "Pie64 (Normal)": {"patch_mode": True, "root_enabled": True,
                           "config_path": "c", "original_name": "Pie64"},
    }
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.checkboxes["Pie64 (Normal)"].setChecked(True)
    monkeypatch.setattr(window, "_engine_state", lambda: "unpatched")

    warned = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warned)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window.handle_toggle_root()

    warned.assert_not_called()
    ran.assert_called_once()


def test_toggle_root_unaffected_for_classic_instance(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = {
        "MSI_Pie (MSI)": {"patch_mode": False, "root_enabled": False,
                          "config_path": "c", "original_name": "MSI_Pie"},
    }
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.checkboxes["MSI_Pie (MSI)"].setChecked(True)
    monkeypatch.setattr(window, "_engine_state", lambda: "unpatched")

    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window.handle_toggle_root()

    ran.assert_called_once()
