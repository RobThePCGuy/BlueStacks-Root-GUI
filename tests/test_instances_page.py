from PyQt5.QtCore import Qt

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
