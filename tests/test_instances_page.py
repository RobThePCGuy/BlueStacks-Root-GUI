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
    with qtbot.waitSignal(page.toggle_root_requested, timeout=1000):
        qtbot.mouseClick(page.root_toggle_button, Qt.LeftButton)


def test_clicking_fix_it_emits_go_to_dashboard(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    with qtbot.waitSignal(page.go_to_dashboard_requested, timeout=1000):
        qtbot.mouseClick(page.banner_fix_button, Qt.LeftButton)


def test_set_instances_shows_display_name_and_falls_back_to_unique_id(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {
        "Nougat64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE,
                               "display_name": "Main Farm Bot"},
        "Pie64 (Normal)": {"root_enabled": False, "rw_mode": constants.MODE_READWRITE},
    }
    page.set_instances(data)

    labels = [page.instance_layout.itemAt(i).widget() for i in range(page.instance_layout.count())]
    texts = {w.text() for w in labels if isinstance(w, QLabel)}
    assert "Main Farm Bot" in texts
    assert "Pie64 (Normal)" in texts  # no display_name key -> falls back to unique_id


def test_set_instances_highlights_rooted_instances_green(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {
        "Rooted (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE},
        "NotRooted (Normal)": {"root_enabled": False, "rw_mode": constants.MODE_READWRITE},
    }
    page.set_instances(data)

    root_labels = {
        w.text(): w for i in range(page.instance_layout.count())
        if isinstance((w := page.instance_layout.itemAt(i).widget()), QLabel)
        and w.text().startswith("Root:")
    }
    assert "green" in root_labels["Root: On"].styleSheet()
    assert "green" not in root_labels["Root: Off"].styleSheet()


def test_set_instances_refresh_does_not_leak_widgets(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    data = {"Pie64 (Normal)": {"root_enabled": True, "rw_mode": constants.MODE_READWRITE}}
    page.set_instances(data)
    count_after_first = page.instance_layout.count()

    page.set_instances(data)
    assert page.instance_layout.count() == count_after_first


def test_launch_and_restart_buttons_emit_signals(qtbot):
    page = InstancesPage()
    qtbot.addWidget(page)
    page.show()
    with qtbot.waitSignal(page.launch_requested, timeout=1000):
        qtbot.mouseClick(page.launch_button, Qt.LeftButton)
    with qtbot.waitSignal(page.restart_requested, timeout=1000):
        qtbot.mouseClick(page.restart_button, Qt.LeftButton)
