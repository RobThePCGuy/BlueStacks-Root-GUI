from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

import constants
from views.instances_page import InstancesPage


def test_banner_hidden_by_default(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    assert page.banner_label.isVisible() is False


def test_set_engine_locked_banner_shows_banner(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_engine_locked_banner(True)
    assert page.banner_label.isVisible() is True
    assert page.banner_fix_button.isVisible() is True


def test_set_instances_creates_one_row_per_instance(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {
        "Pie64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE},
        "MSI_Pie (MSI)": {"root_enabled": False, "rw_mode": constants.MODE_READONLY},
    }
    page.set_instances(data)
    assert set(page.checkboxes.keys()) == {"Pie64 (Normal)", "MSI_Pie (MSI)"}


def test_selected_ids_reflects_checked_boxes(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {"Pie64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE}}
    page.set_instances(data)
    page.checkboxes["Pie64 (Normal)"].setChecked(True)
    assert page.selected_ids() == ["Pie64 (Normal)"]


def test_set_instances_preserves_selection_across_refresh(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {"Pie64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE}}
    page.set_instances(data)
    page.checkboxes["Pie64 (Normal)"].setChecked(True)

    page.set_instances(data, preserve_selection=True)
    assert page.checkboxes["Pie64 (Normal)"].isChecked() is True


def test_set_instances_can_clear_selection(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {"Pie64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE}}
    page.set_instances(data)
    page.checkboxes["Pie64 (Normal)"].setChecked(True)

    page.set_instances(data, preserve_selection=False)
    assert page.checkboxes["Pie64 (Normal)"].isChecked() is False


def test_clicking_toggle_root_emits_signal(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Pie64 (Normal)": {"root_enabled": False,
                                           "rw_mode": constants.MODE_READONLY}})
    page.checkboxes["Pie64 (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.toggle_root_requested, timeout=1000):
        qtbot.mouseClick(page.root_toggle_button, Qt.LeftButton)


def test_clicking_fix_it_emits_go_to_dashboard(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    with qtbot.waitSignal(page.go_to_dashboard_requested, timeout=1000):
        qtbot.mouseClick(page.banner_fix_button, Qt.LeftButton)


def test_row_leads_with_the_engine_name_not_the_display_name(qtbot):
    """The engine name identifies an instance; a display name is a bonus. The
    generic default "BlueStacks App Player" must never stand in for the name."""
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {
        # renamed by the user -> engine name plus the custom name
        "Nougat64 (Normal)": {"original_name": "Nougat64", "display_name": "Main Farm Bot",
                              "root_enabled": True, "rw_mode": constants.MODE_READWRITE},
        # BlueStacks' generic default -> engine name only
        "Tiramisu64 (Normal)": {"original_name": "Tiramisu64",
                                "display_name": "BlueStacks App Player",
                                "root_enabled": False, "rw_mode": constants.MODE_READWRITE},
        # no display name at all -> engine name only
        "Pie64 (Normal)": {"original_name": "Pie64",
                           "root_enabled": False, "rw_mode": constants.MODE_READWRITE},
    }
    page.set_instances(data)

    assert "Nougat64" in page.checkboxes["Nougat64 (Normal)"].text()
    assert "Main Farm Bot" in page.checkboxes["Nougat64 (Normal)"].text()
    assert page.checkboxes["Tiramisu64 (Normal)"].text() == "Tiramisu64"
    assert "BlueStacks App Player" not in page.checkboxes["Tiramisu64 (Normal)"].text()
    assert page.checkboxes["Pie64 (Normal)"].text() == "Pie64"
    # the technical id stays reachable on hover
    assert page.checkboxes["Pie64 (Normal)"].toolTip() == "Pie64 (Normal)"


def test_the_name_is_not_printed_twice(qtbot):
    """The duplicate name column was what made the grid feel cramped."""
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Tiramisu64 (Normal)": {
        "root_enabled": True, "rw_mode": constants.MODE_READWRITE,
        "display_name": "Tiramisu64"}})
    texts = [w.text() for i in range(page.instance_layout.count())
             if isinstance((w := page.instance_layout.itemAt(i).widget()), QLabel)]
    assert not any("Tiramisu64" in t for t in texts), texts


def test_root_state_is_themed_by_object_name_not_a_hardcoded_colour(qtbot):
    """A hard-coded green ignored the light/dark palette."""
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {
        "Rooted (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE},
        "NotRooted (Normal)": {"root_enabled": False, "rw_mode": constants.MODE_READWRITE},
    }
    page.set_instances(data)

    names = {
        w.objectName() for i in range(page.instance_layout.count())
        if isinstance((w := page.instance_layout.itemAt(i).widget()), QLabel)
    }
    assert {"RootOn", "RootOff", "InstanceHeader"} <= names
    styled = [w for i in range(page.instance_layout.count())
              if isinstance((w := page.instance_layout.itemAt(i).widget()), QLabel)
              and w.styleSheet()]
    assert styled == [], "state colours belong in the theme QSS, not inline"


def test_both_themes_style_the_root_state(qtbot):
    from views import theme
    for name in (theme.LIGHT, theme.DARK):
        qss = theme.stylesheet_for(name)
        for obj in ("InstanceHeader", "RootOn", "RootOff", "RwState"):
            assert obj in qss, (name, obj)


def test_set_instances_refresh_does_not_leak_widgets(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {"Pie64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE}}
    page.set_instances(data)
    count_after_first = page.instance_layout.count()

    page.set_instances(data)
    assert page.instance_layout.count() == count_after_first


def _one_ticked(page, uid="Pie64 (Normal)"):
    page.set_instances({uid: {"root_enabled": False,
                              "rw_mode": constants.MODE_READONLY}})
    page.checkboxes[uid].setChecked(True)


def test_launch_and_restart_buttons_emit_signals(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    _one_ticked(page)
    with qtbot.waitSignal(page.launch_requested, timeout=1000):
        qtbot.mouseClick(page.launch_button, Qt.LeftButton)
    with qtbot.waitSignal(page.restart_requested, timeout=1000):
        qtbot.mouseClick(page.restart_button, Qt.LeftButton)


def test_actions_are_disabled_until_something_is_ticked(qtbot):
    """They used to be clickable and then complain in a dialog; now the page
    says what to do and the buttons wait."""
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Pie64 (Normal)": {"root_enabled": False,
                                           "rw_mode": constants.MODE_READONLY}})
    assert page.root_toggle_button.isEnabled() is False
    assert page.launch_button.isEnabled() is False
    assert "tick one instance" in page.hint_label.text().lower()

    page.checkboxes["Pie64 (Normal)"].setChecked(True)
    assert page.root_toggle_button.isEnabled() is True
    assert page.launch_button.isEnabled() is True


def test_root_column_names_the_method_in_use(qtbot):
    """The whole reason the pages merged: app root and Magisk are alternatives,
    so a single column has to say which one an instance is using."""
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({
        "AppRooted (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READONLY},
        "MagiskRooted (Normal)": {"root_enabled": False, "rw_mode": constants.MODE_READONLY},
        "Both (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READONLY},
        "Neither (Normal)": {"root_enabled": False, "rw_mode": constants.MODE_READONLY},
    })
    page.set_magisk_statuses({
        "MagiskRooted (Normal)": {"magisk": True, "components": ["system"]},
        "Both (Normal)": {"magisk": True, "components": ["system"]},
    })
    texts = [w.text() for i in range(page.instance_layout.count())
             if isinstance((w := page.instance_layout.itemAt(i).widget()), QLabel)]
    assert "App" in texts
    assert "Magisk" in texts
    assert "App + Magisk" in texts      # the conflicting state is named
    assert "Off" in texts


def test_conflicting_root_methods_are_called_out(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    page.set_instances({"Both (Normal)": {"root_enabled": True,
                                          "rw_mode": constants.MODE_READONLY}})
    page.set_magisk_statuses({"Both (Normal)": {"magisk": True,
                                                "components": ["system"]}})
    page.checkboxes["Both (Normal)"].setChecked(True)
    hint = page.hint_label.text().lower()
    assert "both provide su" in hint and "turn app root off" in hint
