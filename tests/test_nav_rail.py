from PyQt5.QtCore import Qt

from views.nav_rail import NavRail, DASHBOARD, INSTANCES, MODULES, PRIVACY


def test_nav_rail_starts_on_dashboard(qtbot):
    rail = NavRail()
    qtbot.addWidget(rail)
    assert rail.current() == DASHBOARD
    assert rail._buttons[DASHBOARD].isChecked() is True


def test_nav_rail_has_exactly_the_four_destinations(qtbot):
    """Magisk merged into Instances. A leftover Magisk button with no page
    behind it is what crashed the app on click, so pin the set."""
    rail = NavRail()
    qtbot.addWidget(rail)
    assert set(rail._buttons) == {DASHBOARD, INSTANCES, MODULES, PRIVACY}
    assert "magisk" not in rail._buttons


def test_nav_rail_has_privacy_destination(qtbot):
    rail = NavRail()
    qtbot.addWidget(rail)
    assert PRIVACY in rail._buttons
    with qtbot.waitSignal(rail.navigate, timeout=1000) as blocker:
        qtbot.mouseClick(rail._buttons[PRIVACY], Qt.LeftButton)
    assert blocker.args == [PRIVACY]
    assert rail.current() == PRIVACY


def test_clicking_instances_emits_navigate_and_updates_active_state(qtbot):
    rail = NavRail()
    qtbot.addWidget(rail)
    with qtbot.waitSignal(rail.navigate, timeout=1000) as blocker:
        qtbot.mouseClick(rail._buttons[INSTANCES], Qt.LeftButton)
    assert blocker.args == [INSTANCES]
    assert rail.current() == INSTANCES
    assert rail._buttons[DASHBOARD].isChecked() is False


def test_clicking_modules_then_dashboard_only_one_active(qtbot):
    rail = NavRail()
    qtbot.addWidget(rail)
    qtbot.mouseClick(rail._buttons[MODULES], Qt.LeftButton)
    qtbot.mouseClick(rail._buttons[DASHBOARD], Qt.LeftButton)
    assert rail.current() == DASHBOARD
    checked = [k for k, b in rail._buttons.items() if b.isChecked()]
    assert checked == [DASHBOARD]


def test_select_updates_state_without_a_click(qtbot):
    rail = NavRail()
    qtbot.addWidget(rail)
    rail.select(MODULES)
    assert rail.current() == MODULES
