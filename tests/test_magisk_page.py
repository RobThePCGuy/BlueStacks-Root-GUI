from PyQt5.QtCore import Qt

from views.magisk_page import MagiskPage

# Offline install done, manager not yet installed over ADB.
_INSTALLED_NO_MGR = {"magisk": True, "version": "27.001-kitsune",
                     "components": ["databin", "system"]}
# Manager installed too (adb step done) -> Remove manager + ReZygisk unlock.
_INSTALLED_MGR = {"magisk": True, "version": "27.001-kitsune",
                  "components": ["databin", "manager", "system"]}


def _page(qtbot, statuses=None):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    if statuses is not None:
        page.set_instances(statuses)
    return page


def _select(page, uid="Tiramisu64 (Normal)"):
    page._radios[uid].setChecked(True)


def test_empty_label_shown_when_no_instances(qtbot):
    page = _page(qtbot, {})
    assert page.no_instances_label.isVisible() is True


def test_empty_label_hidden_when_instances_present(qtbot):
    page = _page(qtbot, {"Tiramisu64 (Normal)": None})
    assert page.no_instances_label.isVisible() is False


def test_no_action_buttons_shown_until_an_instance_is_selected(qtbot):
    page = _page(qtbot, {"Tiramisu64 (Normal)": None})
    for b in (page.install_button, page.uninstall_button, page.manager_button,
              page.remove_manager_button, page.rezygisk_button, page.lsposed_button):
        assert b.isVisibleTo(page) is False


def test_not_installed_shows_only_install(qtbot):
    page = _page(qtbot, {"Tiramisu64 (Normal)": None})
    _select(page)
    assert page.install_button.isVisibleTo(page) is True
    assert page.install_button.isEnabled() is True
    for b in (page.uninstall_button, page.manager_button,
              page.remove_manager_button, page.rezygisk_button, page.lsposed_button):
        assert b.isVisibleTo(page) is False
    assert "not installed" in page.status_label.text().lower()


def test_installed_without_manager_shows_uninstall_and_install_manager(qtbot):
    page = _page(qtbot, {"Tiramisu64 (Normal)": _INSTALLED_NO_MGR})
    _select(page)
    assert page.install_button.isVisibleTo(page) is False       # already installed
    assert page.uninstall_button.isVisibleTo(page) is True
    assert page.manager_button.isVisibleTo(page) is True         # manager not in yet
    assert page.remove_manager_button.isVisibleTo(page) is False
    assert page.rezygisk_button.isVisibleTo(page) is False       # needs the manager first


def test_installed_with_manager_unlocks_remove_manager_and_rezygisk(qtbot):
    page = _page(qtbot, {"Tiramisu64 (Normal)": _INSTALLED_MGR})
    _select(page)
    assert page.install_button.isVisibleTo(page) is False
    assert page.uninstall_button.isVisibleTo(page) is True
    assert page.manager_button.isVisibleTo(page) is False        # already installed
    assert page.remove_manager_button.isVisibleTo(page) is True
    assert page.rezygisk_button.isVisibleTo(page) is True
    assert page.lsposed_button.isVisibleTo(page) is True
    assert "manager" in page.status_label.text()


def test_busy_forces_visible_action_buttons_disabled(qtbot):
    page = _page(qtbot, {"Tiramisu64 (Normal)": _INSTALLED_MGR})
    _select(page)
    assert page.rezygisk_button.isEnabled() is True

    page.set_busy(True)
    for b in (page.uninstall_button, page.remove_manager_button,
              page.rezygisk_button, page.lsposed_button):
        assert b.isEnabled() is False
    # a selection change mid-op must not re-enable anything
    page._radios["Tiramisu64 (Normal)"].setChecked(False)
    assert page.rezygisk_button.isEnabled() is False

    page.set_busy(False)
    page._radios["Tiramisu64 (Normal)"].setChecked(True)
    assert page.rezygisk_button.isEnabled() is True


def test_selection_preserved_across_status_refresh(qtbot):
    page = _page(qtbot, {"A (Normal)": None, "B (Normal)": None})
    page._radios["B (Normal)"].setChecked(True)
    # a refresh (e.g. after the manager install) rebuilds the list; B stays chosen
    page.set_instances({"A (Normal)": None, "B (Normal)": _INSTALLED_MGR})
    assert page.selected_instance_id() == "B (Normal)"
    assert page.rezygisk_button.isVisibleTo(page) is True


def test_selected_status_returns_the_instance_manifest(qtbot):
    page = _page(qtbot, {"A (Normal)": _INSTALLED_MGR})
    _select(page, "A (Normal)")
    assert page.selected_status() == _INSTALLED_MGR


def test_install_button_emits_signal(qtbot):
    page = _page(qtbot, {"A (Normal)": None})
    _select(page, "A (Normal)")
    with qtbot.waitSignal(page.install_requested, timeout=1000):
        qtbot.mouseClick(page.install_button, Qt.LeftButton)


def test_manager_button_emits_signal_when_not_yet_installed(qtbot):
    page = _page(qtbot, {"A (Normal)": _INSTALLED_NO_MGR})
    _select(page, "A (Normal)")
    with qtbot.waitSignal(page.install_manager_requested, timeout=1000):
        qtbot.mouseClick(page.manager_button, Qt.LeftButton)


def test_remove_manager_rezygisk_lsposed_buttons_emit_signals(qtbot):
    page = _page(qtbot, {"A (Normal)": _INSTALLED_MGR})
    _select(page, "A (Normal)")
    with qtbot.waitSignal(page.uninstall_manager_requested, timeout=1000):
        qtbot.mouseClick(page.remove_manager_button, Qt.LeftButton)
    with qtbot.waitSignal(page.install_rezygisk_requested, timeout=1000):
        qtbot.mouseClick(page.rezygisk_button, Qt.LeftButton)
    with qtbot.waitSignal(page.install_lsposed_requested, timeout=1000):
        qtbot.mouseClick(page.lsposed_button, Qt.LeftButton)
