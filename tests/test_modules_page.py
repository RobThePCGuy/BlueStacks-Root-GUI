from PyQt5.QtCore import Qt

from views.modules_page import ModulesPage


def test_no_running_label_visible_when_list_empty(qtbot):
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances([])
    assert page.no_running_label.isVisible() is True


def test_no_running_label_hidden_when_instances_present(qtbot):
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances(["Pie64 (Normal)"])
    assert page.no_running_label.isVisible() is False


def test_push_button_stays_disabled_while_busy(qtbot):
    # Even with a running instance selected and a zip chosen, the push button
    # must stay disabled while the app is busy with a background operation.
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances(["Pie64 (Normal)"])
    page._radios["Pie64 (Normal)"].setChecked(True)
    page.set_zip_path("C:/mod.zip")
    assert page.push_button.isEnabled() is True

    page.set_busy(True)
    assert page.push_button.isEnabled() is False

    # A zip/radio change mid-operation re-runs _update_push_enabled; it must
    # still stay disabled while busy.
    page.set_zip_path("C:/other.zip")
    assert page.push_button.isEnabled() is False

    page.set_busy(False)
    assert page.push_button.isEnabled() is True


def test_set_scanning_shows_hint_and_clears_radios(qtbot):
    # While the background ADB probe runs, the tab shows a "checking..." hint
    # instead of a stale list, and no instance can be selected.
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances(["Pie64 (Normal)"])
    assert len(page._radios) == 1

    page.set_scanning()
    assert page._radios == {}
    assert page.no_running_label.isVisible() is True
    assert page.no_running_label.text() == ModulesPage._SCANNING_TEXT
    assert page.push_button.isEnabled() is False


def test_empty_result_after_scanning_restores_empty_text(qtbot):
    # A scan that finds nothing must reset the label back to the "no instance
    # running" copy, not leave the transient "checking..." text stuck.
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_scanning()
    assert page.no_running_label.text() == ModulesPage._SCANNING_TEXT

    page.set_running_instances([])
    assert page.no_running_label.isVisible() is True
    assert page.no_running_label.text() == ModulesPage._EMPTY_TEXT


def test_push_disabled_until_instance_and_zip_chosen(qtbot):
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances(["Pie64 (Normal)"])
    assert page.push_button.isEnabled() is False

    page._radios["Pie64 (Normal)"].setChecked(True)
    assert page.push_button.isEnabled() is False  # zip still missing

    page.set_zip_path("C:/mods/module.zip")
    assert page.push_button.isEnabled() is True


def test_selected_instance_id_reflects_radio_choice(qtbot):
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances(["A (Normal)", "B (Normal)"])
    page._radios["B (Normal)"].setChecked(True)
    assert page.selected_instance_id() == "B (Normal)"


def test_clicking_browse_emits_signal(qtbot):
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    with qtbot.waitSignal(page.browse_zip_requested, timeout=1000):
        qtbot.mouseClick(page.browse_button, Qt.LeftButton)


def test_clicking_push_emits_signal_when_enabled(qtbot):
    page = ModulesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_running_instances(["Pie64 (Normal)"])
    page._radios["Pie64 (Normal)"].setChecked(True)
    page.set_zip_path("C:/mods/module.zip")
    with qtbot.waitSignal(page.push_requested, timeout=1000):
        qtbot.mouseClick(page.push_button, Qt.LeftButton)
