from views.main_window import MainWindow


def _setup_window(qtbot, window):
    """Helper to set up MainWindow for testing dashboard alerts."""
    qtbot.addWidget(window)
    window.pages.setCurrentIndex(0)  # Show dashboard page
    window.show()


def test_no_alert_before_any_poll(qtbot):
    window = MainWindow()
    _setup_window(qtbot, window)
    assert window.dashboard_page.alert_label.isVisible() is False


def test_alert_shows_when_engine_state_drops_while_rooted(qtbot, monkeypatch):
    window = MainWindow()
    _setup_window(qtbot, window)
    window.instance_data = {"Pie64 (Normal)": {"root_enabled": True, "patch_mode": True}}
    states = iter(["patched", "unpatched"])
    monkeypatch.setattr(window, "_engine_state", lambda: next(states))

    window._check_for_reverted_patch()  # seeds _last_engine_state = "patched"
    assert window.dashboard_page.alert_label.isVisible() is False

    window._check_for_reverted_patch()  # drops to "unpatched" with root active
    assert window.dashboard_page.alert_label.isVisible() is True


def test_no_alert_when_nothing_was_rooted(qtbot, monkeypatch):
    window = MainWindow()
    _setup_window(qtbot, window)
    window.instance_data = {"Pie64 (Normal)": {"root_enabled": False}}
    states = iter(["patched", "unpatched"])
    monkeypatch.setattr(window, "_engine_state", lambda: next(states))

    window._check_for_reverted_patch()
    window._check_for_reverted_patch()
    assert window.dashboard_page.alert_label.isVisible() is False


def test_no_alert_when_only_classic_instance_rooted(qtbot, monkeypatch):
    # A rooted classic (conf/MSI) instance does not depend on the engine patch,
    # so a patch-mode engine flipping patched -> unpatched must NOT raise the
    # "your engine patch was reverted" alert on its account.
    window = MainWindow()
    _setup_window(qtbot, window)
    window.instance_data = {"MSI_Pie (MSI)": {"root_enabled": True, "patch_mode": False}}
    states = iter(["patched", "unpatched"])
    monkeypatch.setattr(window, "_engine_state", lambda: next(states))

    window._check_for_reverted_patch()
    window._check_for_reverted_patch()
    assert window.dashboard_page.alert_label.isVisible() is False


def test_repatch_via_on_async_done_clears_alert_immediately(qtbot, monkeypatch):
    # With the alert already showing, finishing a successful (re)patch should
    # clear it right away rather than waiting for the next timer tick.
    window = MainWindow()
    _setup_window(qtbot, window)
    window.instance_data = {"Pie64 (Normal)": {"root_enabled": True, "patch_mode": True}}
    window.dashboard_page.set_update_reverted(True)
    assert window.dashboard_page.alert_label.isVisible() is True
    monkeypatch.setattr(window, "_engine_state", lambda: "patched")

    window._on_async_done(True, "Engine patched.")
    assert window.dashboard_page.alert_label.isVisible() is False


def test_alert_clears_once_repatched(qtbot, monkeypatch):
    window = MainWindow()
    _setup_window(qtbot, window)
    window.instance_data = {"Pie64 (Normal)": {"root_enabled": True, "patch_mode": True}}
    states = iter(["patched", "unpatched", "patched"])
    monkeypatch.setattr(window, "_engine_state", lambda: next(states))

    window._check_for_reverted_patch()
    window._check_for_reverted_patch()
    assert window.dashboard_page.alert_label.isVisible() is True
    window._check_for_reverted_patch()
    assert window.dashboard_page.alert_label.isVisible() is False


def test_on_async_done_resyncs_state_so_manual_undo_does_not_false_alert(qtbot, monkeypatch):
    """Regression test: 'Undo Root Patch' (handle_restore_patches) legitimately
    reverts the engine patch but leaves per-instance root_enabled=True. Before
    the fix, _last_engine_state stayed "patched" after the operation finished,
    so the next status-timer tick saw patched -> unpatched with a rooted
    instance and misreported it as an auto-update revert. _on_async_done must
    resync _last_engine_state immediately so that doesn't happen."""
    window = MainWindow()
    _setup_window(qtbot, window)
    window.instance_data = {"Pie64 (Normal)": {"root_enabled": True, "patch_mode": True}}
    window._last_engine_state = "patched"
    monkeypatch.setattr(window, "_engine_state", lambda: "unpatched")

    window._on_async_done(True, "Restored 1 installation(s).")
    assert window._last_engine_state == "unpatched"
    assert window.dashboard_page.alert_label.isVisible() is False

    # Next timer tick should see no change from the now-resynced state.
    window._check_for_reverted_patch()
    assert window.dashboard_page.alert_label.isVisible() is False
