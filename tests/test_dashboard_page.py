from PyQt5.QtCore import Qt

from views.dashboard_page import DashboardPage


def test_alert_hidden_by_default(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    assert page.alert_label.isVisible() is False
    assert page.repatch_button.isVisible() is False


def test_set_update_reverted_shows_alert(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    page.set_update_reverted(True)
    assert page.alert_label.isVisible() is True
    assert page.repatch_button.isVisible() is True


def test_clicking_repatch_emits_signal(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    page.set_update_reverted(True)
    with qtbot.waitSignal(page.repatch_requested, timeout=1000):
        qtbot.mouseClick(page.repatch_button, Qt.LeftButton)


def test_set_engine_state_updates_button(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    page.set_engine_state(True, "Patch BlueStacks Engine", "tip", "#c62828", True)
    assert page.engine_button.isVisible() is True
    assert page.engine_button.text() == "Patch BlueStacks Engine"
    assert page.engine_button.isEnabled() is True


def test_clicking_engine_button_emits_signal(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    page.set_engine_state(True, "Patch", "tip", "#c62828", True)
    with qtbot.waitSignal(page.patch_engine_requested, timeout=1000):
        qtbot.mouseClick(page.engine_button, Qt.LeftButton)


def test_set_rooted_count_updates_label(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    page.set_rooted_count(2, 5)
    assert page.stat_label.text() == "2 / 5 instances rooted"


def test_set_paths_text_updates_label(qtbot):
    page = DashboardPage()
    qtbot.addWidget(page)
    page.show()
    page.set_paths_text("Installations Found:\n  - NXT v5.22.232.1002: C:/x")
    assert page.path_label.text() == "Installations Found:\n  - NXT v5.22.232.1002: C:/x"
