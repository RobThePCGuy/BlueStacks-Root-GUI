from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMessageBox

from views.main_window import MainWindow
from views.nav_rail import MAGISK as NAV_MAGISK

# See test_main_window_gating for why constructing MainWindow in a test is safe
# (initialize_paths_and_instances only fires under a running event loop).


def _one_instance(patch_mode=True, root_enabled=False):
    return {
        "Tiramisu64 (Normal)": {
            "patch_mode": patch_mode, "root_enabled": root_enabled,
            "config_path": "c", "original_name": "Tiramisu64",
            "data_path": r"C:\inst\Tiramisu64", "install_path": r"C:\bs",
        },
    }


def _select(window, uid="Tiramisu64 (Normal)", status=None):
    window.magisk_page.set_instances({uid: status})
    window.magisk_page._radios[uid].setChecked(True)


def test_navigate_to_magisk_populates_statuses(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    monkeypatch.setattr("magisk_system.magisk_status",
                        lambda path: {"magisk": True, "version": "27.001-kitsune",
                                      "components": ["system"]})
    window.nav_rail.select(NAV_MAGISK)
    assert window.magisk_page.selected_instance_id() is None
    assert "Tiramisu64 (Normal)" in window.magisk_page._radios
    window.magisk_page._radios["Tiramisu64 (Normal)"].setChecked(True)
    assert window.magisk_page.uninstall_button.isEnabled() is True


def test_install_blocked_when_patch_mode_engine_unpatched(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance(patch_mode=True)
    _select(window, status=None)
    monkeypatch.setattr(window, "_engine_state", lambda: "unpatched")
    warned = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warned)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_magisk()

    warned.assert_called_once()
    ran.assert_not_called()


def test_install_proceeds_when_engine_patched(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance(patch_mode=True)
    _select(window, status=None)
    monkeypatch.setattr(window, "_engine_state", lambda: "patched")
    monkeypatch.setattr(window, "_confirm", lambda *a, **k: True)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_magisk()

    ran.assert_called_once()


def test_install_aborts_when_user_declines_confirm(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance(patch_mode=True)
    _select(window, status=None)
    monkeypatch.setattr(window, "_engine_state", lambda: "patched")
    monkeypatch.setattr(window, "_confirm", lambda *a, **k: False)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_magisk()

    ran.assert_not_called()


def test_uninstall_proceeds_on_confirm(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status={"magisk": True, "version": "27.001-kitsune",
                            "components": ["system"]})
    monkeypatch.setattr(window, "_confirm", lambda *a, **k: True)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_uninstall_magisk()

    ran.assert_called_once()


def test_install_manager_warns_when_adb_missing(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status={"magisk": True, "version": "27.001-kitsune",
                            "components": ["system"]})
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: None)
    warned = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warned)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_manager()

    warned.assert_called_once()
    ran.assert_not_called()


def test_install_manager_runs_when_adb_present(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status={"magisk": True, "version": "27.001-kitsune",
                            "components": ["system"]})
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: r"C:\bs\HD-Adb.exe")
    monkeypatch.setattr("adb_handler.instance_adb_port", lambda c, n: 5555)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_manager()

    ran.assert_called_once()


_MGR = {"magisk": True, "version": "27.001-kitsune",
        "components": ["databin", "manager", "system"]}


def test_uninstall_manager_runs_when_adb_present(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status=_MGR)
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: r"C:\bs\HD-Adb.exe")
    monkeypatch.setattr("adb_handler.instance_adb_port", lambda c, n: 5555)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_uninstall_manager()

    ran.assert_called_once()


def test_install_rezygisk_runs_when_adb_present(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status=_MGR)
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: r"C:\bs\HD-Adb.exe")
    monkeypatch.setattr("adb_handler.instance_adb_port", lambda c, n: 5555)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_rezygisk()

    ran.assert_called_once()


def test_install_rezygisk_warns_when_adb_missing(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status=_MGR)
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: None)
    warned = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warned)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_rezygisk()

    warned.assert_called_once()
    ran.assert_not_called()


def test_install_pif_runs_when_adb_present(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status=_MGR)
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: r"C:\bs\HD-Adb.exe")
    monkeypatch.setattr("adb_handler.instance_adb_port", lambda c, n: 5555)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window._handle_install_pif()

    ran.assert_called_once()
