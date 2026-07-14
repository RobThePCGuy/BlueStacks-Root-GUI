from views.engine_rules import blocked_for_root_toggle, update_was_reverted


def test_blocked_for_root_toggle_blocks_unpatched_patch_mode_instances():
    selected = {
        "Pie64 (Normal)": {"patch_mode": True},
        "MSI_Pie (MSI)": {"patch_mode": False},
    }
    assert blocked_for_root_toggle(selected, "unpatched") == ["Pie64 (Normal)"]


def test_blocked_for_root_toggle_allows_everything_when_patched():
    selected = {
        "Pie64 (Normal)": {"patch_mode": True},
        "MSI_Pie (MSI)": {"patch_mode": False},
    }
    assert blocked_for_root_toggle(selected, "patched") == []


def test_blocked_for_root_toggle_ignores_classic_instances():
    selected = {"MSI_Pie (MSI)": {"patch_mode": False}}
    assert blocked_for_root_toggle(selected, "unpatched") == []


def test_blocked_for_root_toggle_blocks_turning_root_on():
    selected = {"Pie64 (Normal)": {"patch_mode": True, "root_enabled": False}}
    assert blocked_for_root_toggle(selected, "unpatched") == ["Pie64 (Normal)"]


def test_blocked_for_root_toggle_allows_turning_root_off():
    # A currently-rooted patch-mode instance being toggled OFF is not blocked:
    # disabling root needs no engine patch, so a stale root after an
    # auto-update revert must still be clearable.
    selected = {"Pie64 (Normal)": {"patch_mode": True, "root_enabled": True}}
    assert blocked_for_root_toggle(selected, "unpatched") == []


def test_blocked_for_root_toggle_blocks_on_partial():
    selected = {"Pie64 (Normal)": {"patch_mode": True, "root_enabled": False}}
    assert blocked_for_root_toggle(selected, "partial") == ["Pie64 (Normal)"]


def test_blocked_for_root_toggle_allows_when_engine_state_unknown():
    # Unrecognized build: we can't read patch state, so don't trap the user.
    selected = {"Pie64 (Normal)": {"patch_mode": True, "root_enabled": False}}
    assert blocked_for_root_toggle(selected, "unknown") == []


def test_update_was_reverted_true_when_patch_lost_with_root_active():
    assert update_was_reverted("patched", "unpatched", any_rooted=True) is True


def test_update_was_reverted_false_when_nothing_was_rooted():
    assert update_was_reverted("patched", "unpatched", any_rooted=False) is False


def test_update_was_reverted_false_when_still_patched():
    assert update_was_reverted("patched", "patched", any_rooted=True) is False


def test_update_was_reverted_false_when_never_was_patched():
    assert update_was_reverted("unpatched", "unpatched", any_rooted=True) is False


def test_update_was_reverted_false_on_first_ever_check():
    assert update_was_reverted(None, "unpatched", any_rooted=True) is False
