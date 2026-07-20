from PyQt5.QtCore import Qt

from views.magisk_page import MagiskPage

_INSTALLED = {"magisk": True, "version": "27.001-kitsune",
              "components": ["databin", "manager", "system"]}


def test_empty_label_shown_when_no_instances(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({})
    assert page.no_instances_label.isVisible() is True


def test_empty_label_hidden_when_instances_present(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Tiramisu64 (Normal)": None})
    assert page.no_instances_label.isVisible() is False


def test_no_action_buttons_shown_until_an_instance_is_selected(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Tiramisu64 (Normal)": None})
    assert page.install_button.isVisibleTo(page) is False
    assert page.uninstall_button.isVisibleTo(page) is False
    assert page.manager_button.isVisibleTo(page) is False


def test_not_installed_shows_only_install(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Tiramisu64 (Normal)": None})
    page._radios["Tiramisu64 (Normal)"].setChecked(True)
    # only Install is present, and it's clickable
    assert page.install_button.isVisibleTo(page) is True
    assert page.install_button.isEnabled() is True
    assert page.uninstall_button.isVisibleTo(page) is False
    assert page.manager_button.isVisibleTo(page) is False
    assert "not installed" in page.status_label.text().lower()


def test_installed_hides_install_shows_uninstall_and_manager(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Tiramisu64 (Normal)": _INSTALLED})
    page._radios["Tiramisu64 (Normal)"].setChecked(True)
    # no Install button when it's already installed (Rob's ask)
    assert page.install_button.isVisibleTo(page) is False
    assert page.uninstall_button.isVisibleTo(page) is True
    assert page.uninstall_button.isEnabled() is True
    assert page.manager_button.isVisibleTo(page) is True
    assert page.manager_button.isEnabled() is True
    txt = page.status_label.text()
    assert "27.001-kitsune" in txt and "system" in txt


def test_busy_forces_all_action_buttons_disabled(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Tiramisu64 (Normal)": _INSTALLED})
    page._radios["Tiramisu64 (Normal)"].setChecked(True)
    assert page.uninstall_button.isEnabled() is True

    page.set_busy(True)
    assert page.install_button.isEnabled() is False
    assert page.uninstall_button.isEnabled() is False
    assert page.manager_button.isEnabled() is False

    # A selection change mid-op must not re-enable anything while busy.
    page._radios["Tiramisu64 (Normal)"].setChecked(False)
    assert page.uninstall_button.isEnabled() is False

    page.set_busy(False)
    page._radios["Tiramisu64 (Normal)"].setChecked(True)
    assert page.uninstall_button.isEnabled() is True


def test_selection_preserved_across_status_refresh(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"A (Normal)": None, "B (Normal)": None})
    page._radios["B (Normal)"].setChecked(True)
    # A refresh (e.g. after an install) rebuilds the list; B stays selected.
    page.set_instances({"A (Normal)": None, "B (Normal)": _INSTALLED})
    assert page.selected_instance_id() == "B (Normal)"
    assert page.uninstall_button.isEnabled() is True  # B now installed


def test_selected_status_returns_the_instance_manifest(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"A (Normal)": _INSTALLED})
    page._radios["A (Normal)"].setChecked(True)
    assert page.selected_status() == _INSTALLED


def test_install_button_emits_signal(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"A (Normal)": None})
    page._radios["A (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.install_requested, timeout=1000):
        qtbot.mouseClick(page.install_button, Qt.LeftButton)


def test_manager_button_emits_signal_when_installed(qtbot):
    page = MagiskPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"A (Normal)": _INSTALLED})
    page._radios["A (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.install_manager_requested, timeout=1000):
        qtbot.mouseClick(page.manager_button, Qt.LeftButton)
