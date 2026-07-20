from PyQt5.QtCore import Qt

from views.privacy_page import PrivacyPage

_BLOCKED = {"telemetry_block": True, "domains": 19}


def _page(qtbot, statuses=None):
    page = PrivacyPage()
    qtbot.addWidget(page)
    page.show()
    if statuses is not None:
        page.set_instances(statuses)
    return page


def test_empty_label_shown_when_no_instances(qtbot):
    page = _page(qtbot, {})
    assert page.no_instances_label.isVisible() is True


def test_no_buttons_until_instance_selected(qtbot):
    page = _page(qtbot, {"A (Normal)": None})
    assert page.block_button.isVisibleTo(page) is False
    assert page.unblock_button.isVisibleTo(page) is False


def test_not_blocked_shows_block_only(qtbot):
    page = _page(qtbot, {"A (Normal)": None})
    page._radios["A (Normal)"].setChecked(True)
    assert page.block_button.isVisibleTo(page) is True
    assert page.block_button.isEnabled() is True
    assert page.unblock_button.isVisibleTo(page) is False
    assert "no telemetry block" in page.status_label.text().lower()


def test_blocked_shows_remove_only(qtbot):
    page = _page(qtbot, {"A (Normal)": _BLOCKED})
    page._radios["A (Normal)"].setChecked(True)
    assert page.block_button.isVisibleTo(page) is False
    assert page.unblock_button.isVisibleTo(page) is True
    assert "19" in page.status_label.text()


def test_busy_disables_visible_button(qtbot):
    page = _page(qtbot, {"A (Normal)": _BLOCKED})
    page._radios["A (Normal)"].setChecked(True)
    assert page.unblock_button.isEnabled() is True
    page.set_busy(True)
    assert page.unblock_button.isEnabled() is False
    page.set_busy(False)
    assert page.unblock_button.isEnabled() is True


def test_buttons_emit_signals(qtbot):
    page = _page(qtbot, {"A (Normal)": None})
    page._radios["A (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.block_requested, timeout=1000):
        qtbot.mouseClick(page.block_button, Qt.LeftButton)

    page.set_instances({"A (Normal)": _BLOCKED})
    page._radios["A (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.unblock_requested, timeout=1000):
        qtbot.mouseClick(page.unblock_button, Qt.LeftButton)
