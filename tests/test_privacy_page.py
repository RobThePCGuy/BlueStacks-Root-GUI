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
    assert "no tracker block" in page.status_label.text().lower()


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


# --- global BlueStacks ad/telemetry switches --------------------------------

_ADS_OFF = {"ads_disabled": True, "keys": 23, "off": ["a"], "reverted": [],
            "unmanaged": [], "locked": False}


def test_ads_on_offers_turn_off_only(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(None, 23)
    assert page.ads_off_button.isVisibleTo(page) is True
    assert page.ads_restore_button.isVisibleTo(page) is False
    assert "on" in page.ads_status_label.text().lower()
    assert "23" in page.ads_status_label.text()


def test_ads_off_offers_restore_only(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(_ADS_OFF, 23)
    assert page.ads_off_button.isVisibleTo(page) is False
    assert page.ads_restore_button.isVisibleTo(page) is True
    assert "off" in page.ads_status_label.text().lower()


def test_reverted_switches_offer_turn_off_again(qtbot):
    """BlueStacks puts some keys back on every start; the user needs a re-apply."""
    page = _page(qtbot, {})
    page.set_ad_status(dict(_ADS_OFF, reverted=["bst.feature.nowbux"]), 23)
    assert page.ads_off_button.isVisibleTo(page) is True
    assert page.ads_restore_button.isVisibleTo(page) is True
    assert "reverted" in page.ads_status_label.text().lower()


def test_switches_added_by_a_bluestacks_update_offer_reapply(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(dict(_ADS_OFF, unmanaged=["bst.feature.send_new_stats"]), 24)
    assert page.ads_off_button.isVisibleTo(page) is True
    assert "new switches" in page.ads_status_label.text().lower()


def test_no_switches_in_this_build_hides_the_control(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(None, 0)
    assert page.ads_off_button.isVisibleTo(page) is False
    assert "no switches" in page.ads_status_label.text().lower()


# The explanation moved off the page and into the tooltip, so that is where the
# detail has to be asserted now: the label stays a short state line.
def test_the_visible_line_stays_short_and_the_detail_is_a_tooltip(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(dict(_ADS_OFF, reverted=["bst.feature.nowbux",
                                                "bst.feature.send_offer_stats"]), 23)
    label = page.ads_status_label.text()
    tip = page.ads_status_label.toolTip()
    assert len(label) <= 80, label
    assert "bst.feature.nowbux" in tip          # the specifics live here
    assert "lock the config" in tip.lower()     # and so does the remedy
    assert "bst.feature.nowbux" not in label    # never on the page itself


def test_every_control_on_the_page_has_a_tooltip(qtbot):
    """The page carries no explanatory prose any more, so a control without a
    tooltip would leave the user with nothing to go on."""
    page = _page(qtbot, {"A (Normal)": None})
    page.set_ad_status(None, 23)
    for name in ("ads_off_button", "ads_restore_button", "ads_lock_check",
                 "block_button", "unblock_button"):
        widget = getattr(page, name)
        assert widget.toolTip().strip(), name
        assert len(widget.toolTip()) <= 150, (name, len(widget.toolTip()))


def test_ads_buttons_emit_signals(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(None, 23)
    with qtbot.waitSignal(page.ads_off_requested, timeout=1000):
        qtbot.mouseClick(page.ads_off_button, Qt.LeftButton)
    page.set_ad_status(_ADS_OFF, 23)
    with qtbot.waitSignal(page.ads_restore_requested, timeout=1000):
        qtbot.mouseClick(page.ads_restore_button, Qt.LeftButton)


def test_lock_checkbox_reflects_state_without_emitting(qtbot):
    """set_ad_status() syncs the box to reality; only a user click should fire."""
    page = _page(qtbot, {})
    fired = []
    page.ads_lock_toggled.connect(fired.append)
    page.set_ad_status(dict(_ADS_OFF, locked=True), 23)
    assert page.ads_lock_check.isChecked() is True
    assert fired == []
    page.ads_lock_check.setChecked(False)
    assert fired == [False]


def test_busy_disables_ads_buttons(qtbot):
    page = _page(qtbot, {})
    page.set_ad_status(None, 23)
    assert page.ads_off_button.isEnabled() is True
    page.set_busy(True)
    assert page.ads_off_button.isEnabled() is False
    page.set_busy(False)
    assert page.ads_off_button.isEnabled() is True


def test_buttons_emit_signals(qtbot):
    page = _page(qtbot, {"A (Normal)": None})
    page._radios["A (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.block_requested, timeout=1000):
        qtbot.mouseClick(page.block_button, Qt.LeftButton)

    page.set_instances({"A (Normal)": _BLOCKED})
    page._radios["A (Normal)"].setChecked(True)
    with qtbot.waitSignal(page.unblock_requested, timeout=1000):
        qtbot.mouseClick(page.unblock_button, Qt.LeftButton)
