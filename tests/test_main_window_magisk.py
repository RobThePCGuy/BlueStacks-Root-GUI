from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMessageBox

from views.main_window import MainWindow
from views.nav_rail import INSTANCES as NAV_INSTANCES

# See test_main_window_gating for why constructing MainWindow in a test is safe
# (initialize_paths_and_instances only fires under a running event loop).


def test_every_nav_destination_has_a_page(qtbot):
    """The merge left a Magisk nav button with no page, so clicking it raised
    KeyError and killed the app. Every rail key must map to a real page, and an
    unknown key must be inert rather than fatal."""
    window = MainWindow()
    qtbot.addWidget(window)
    for key in window.nav_rail._buttons:
        assert key in window._pages_by_key, key
        window._handle_navigate(key)          # must not raise
    assert "magisk" not in window._pages_by_key
    window._handle_navigate("does-not-exist")  # guarded, no crash


def _one_instance(patch_mode=True, root_enabled=False):
    return {
        "Tiramisu64 (Normal)": {
            "patch_mode": patch_mode, "root_enabled": root_enabled,
            "config_path": "c", "original_name": "Tiramisu64",
            "data_path": r"C:\inst\Tiramisu64", "install_path": r"C:\bs",
        },
    }


def _select(window, uid="Tiramisu64 (Normal)", status=None):
    """Tick exactly one instance: how a Magisk action is targeted now that
    Instances and Magisk are one page."""
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.set_magisk_statuses({uid: status})
    window.instances_page.checkboxes[uid].setChecked(True)


def test_navigate_to_instances_populates_magisk_statuses(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    window.instances_page.set_instances(window.instance_data)
    monkeypatch.setattr("magisk_system.magisk_status",
                        lambda path: {"magisk": True, "version": "27.001-kitsune",
                                      "components": ["system"]})
    window.nav_rail.select(NAV_INSTANCES)
    # Nothing ticked yet, so no single instance is targeted.
    assert window.instances_page.selected_instance_id() is None
    assert "Tiramisu64 (Normal)" in window.instances_page.checkboxes
    window.instances_page.checkboxes["Tiramisu64 (Normal)"].setChecked(True)
    assert window.instances_page.uninstall_button.isEnabled() is True


def test_magisk_actions_need_exactly_one_instance(qtbot):
    """Ticking several is how bulk root works; Magisk acts on one at a time."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    window.instance_data["Pie64 (Normal)"] = dict(
        window.instance_data["Tiramisu64 (Normal)"])
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.set_magisk_statuses(
        {"Tiramisu64 (Normal)": None, "Pie64 (Normal)": None})
    for cb in window.instances_page.checkboxes.values():
        cb.setChecked(True)
    assert window.instances_page.selected_instance_id() is None
    assert window.instances_page.install_button.isEnabled() is False
    # bulk actions stay available with several ticked
    assert window.instances_page.root_toggle_button.isEnabled() is True


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

    window.magisk_controller.handle_install()

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

    window.magisk_controller.handle_install()

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

    window.magisk_controller.handle_install()

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

    window.magisk_controller.handle_uninstall()

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

    window.magisk_controller.handle_install_manager()

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

    window.magisk_controller.handle_install_manager()

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

    window.magisk_controller.handle_uninstall_manager()

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

    window.magisk_controller.handle_install_rezygisk()

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

    window.magisk_controller.handle_install_rezygisk()

    warned.assert_called_once()
    ran.assert_not_called()


def test_install_lsposed_runs_when_adb_present(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _one_instance()
    _select(window, status=_MGR)
    monkeypatch.setattr("adb_handler.find_adb", lambda dirs: r"C:\bs\HD-Adb.exe")
    monkeypatch.setattr("adb_handler.instance_adb_port", lambda c, n: 5555)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)

    window.magisk_controller.handle_install_lsposed()

    ran.assert_called_once()


def _inst_with(uid, **extra):
    d = {"patch_mode": True, "root_enabled": False, "config_path": "c",
         "original_name": uid.split(" ")[0], "data_path": r"C:\i", "install_path": r"C:\bs"}
    d.update(extra)
    return {uid: d}


def test_launch_instance_needs_exactly_one_selected(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _inst_with("Tiramisu64 (Normal)")
    window.instances_page.set_instances(window.instance_data)
    # nothing selected -> informs, doesn't launch
    info = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", info)
    launched = MagicMock()
    monkeypatch.setattr("instance_handler.launch_instance", launched)
    window._handle_launch_instance()
    info.assert_called_once()
    launched.assert_not_called()


def test_launch_instance_runs_for_single_selection(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _inst_with("Tiramisu64 (Normal)")
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.checkboxes["Tiramisu64 (Normal)"].setChecked(True)
    launched = MagicMock()
    monkeypatch.setattr("instance_handler.launch_instance", launched)
    window._handle_launch_instance()
    launched.assert_called_once()


def test_restart_instance_runs_async(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.instance_data = _inst_with("Tiramisu64 (Normal)")
    window.instances_page.set_instances(window.instance_data)
    window.instances_page.checkboxes["Tiramisu64 (Normal)"].setChecked(True)
    ran = MagicMock()
    monkeypatch.setattr(window, "_run_async", ran)
    window._handle_restart_instance()
    ran.assert_called_once()
