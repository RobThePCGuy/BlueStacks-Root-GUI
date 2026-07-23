"""Tests for ad_settings: which config keys get turned off, and the toggle.

The fixture below is the real key set observed in bluestacks.conf on
5.22.250.1015 (BlueStacks 5, Android 13 instance), including the near-misses
that must NOT be touched -- bst.enable_adb_access (contains "ad"),
android_google_ad_id (an id, not a switch), the *_preference keys (they control
whether BlueStacks' own ad toggle is visible), and skipNowggLogin (inverted).
"""
import ad_settings as ads

# Verbatim shape of the real config, trimmed to the relevant keys.
REAL_CONF = '''\
bst.campaign_hash="5eb05192d5318a59eed61137da00d3e7"
bst.campaign_name=""
bst.enable_adb_access="1"
bst.enable_adb_remote_access="0"
bst.enable_android_ads_test_app="0"
bst.enable_auto_upload_recording="1"
bst.enable_boot_banner="1"
bst.enable_gamepad_detection="1"
bst.enable_programmatic_ads="1"
bst.feature.android_ads_stats="0"
bst.feature.auto_upload_nowgg_moments="1"
bst.feature.auto_upload_nowgg_recording="1"
bst.feature.bluestacksX="1"
bst.feature.nowbux="1"
bst.feature.nowgg_cloud_upload_enabled="1"
bst.feature.nowgg_login_popup="1"
bst.feature.programmatic_ads="1"
bst.feature.rooting="1"
bst.feature.send_internal_notification_stats="1"
bst.feature.send_notification_stats="0"
bst.feature.send_nowbux_login_boot_stats="1"
bst.feature.send_offer_stats="0"
bst.feature.send_programmatic_ads_boot_stats="1"
bst.feature.send_programmatic_ads_click_stats="1"
bst.feature.send_programmatic_ads_fill_stats="0"
bst.feature.show_boot_banner_preference="1"
bst.feature.show_gp_ads="1"
bst.feature.show_programmatic_ads_preference="1"
bst.feature.skipNowggLogin="1"
bst.instance.Tiramisu64.ads_app_package="com.uncube.gamevantage"
bst.instance.Tiramisu64.android_google_ad_id="b11c1080-79be-42f6-99b4-0ae2bdf109ee"
bst.instance.Tiramisu64.enable_root_access="1"
bst.instance.Tiramisu64.split_ad_enabled="0"
bst.nowgg_username=""
'''


def _conf(tmp_path, text=REAL_CONF):
    p = tmp_path / "bluestacks.conf"
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- the three safety gates -------------------------------------------------

def test_adb_keys_are_never_managed():
    """"adb" contains "ad" -- the classic false positive."""
    assert ads.is_managed("bst.enable_adb_access", "1") is False
    assert ads.is_managed("bst.enable_adb_remote_access", "0") is False


def test_rooting_keys_are_never_managed():
    assert ads.is_managed("bst.feature.rooting", "1") is False
    assert ads.is_managed("bst.instance.Foo.enable_root_access", "1") is False


def test_preference_keys_are_never_managed():
    """These control whether the user's own ad toggle is visible in Settings."""
    assert ads.is_managed("bst.feature.show_programmatic_ads_preference", "1") is False
    assert ads.is_managed("bst.feature.show_boot_banner_preference", "1") is False


def test_inverted_semantics_keys_are_never_managed():
    """We only ever write "0", so a disable_/skip_ key would be flipped backwards."""
    assert ads.is_managed("bst.feature.skipNowggLogin", "1") is False
    assert ads.is_managed("bst.feature.disable_ads", "1") is False


def test_non_boolean_values_are_never_managed():
    """The value gate keeps ids and strings out no matter how they're named."""
    assert ads.is_managed("bst.instance.X.android_google_ad_id", "b11c1080-79be") is False
    assert ads.is_managed("bst.instance.X.ads_app_package", "com.uncube.gamevantage") is False
    assert ads.is_managed("bst.instance.X.ads_display_time", "") is False


def test_real_ad_switches_are_managed():
    for key in ("bst.enable_programmatic_ads",
                "bst.feature.programmatic_ads",
                "bst.feature.show_gp_ads",
                "bst.enable_boot_banner",
                "bst.feature.nowbux",
                "bst.feature.bluestacksX",
                "bst.feature.send_programmatic_ads_boot_stats",
                "bst.feature.send_internal_notification_stats",
                "bst.feature.auto_upload_nowgg_moments",
                "bst.enable_auto_upload_recording"):
        assert ads.is_managed(key, "1") is True, key


def test_a_future_renamed_stats_key_is_still_caught():
    """The point of pattern discovery: no code change for a new build's keys."""
    assert ads.is_managed("bst.feature.send_brand_new_ad_stats", "1") is True
    assert ads.is_managed("bst.feature.programmatic_ads_v2", "1") is True


# --- discovery --------------------------------------------------------------

def test_discover_finds_switches_and_excludes_the_near_misses(tmp_path):
    found = ads.discover(_conf(tmp_path))
    assert "bst.enable_programmatic_ads" in found
    assert "bst.feature.send_programmatic_ads_boot_stats" in found
    # near misses stay out
    for key in ("bst.enable_adb_access",
                "bst.feature.rooting",
                "bst.instance.Tiramisu64.enable_root_access",
                "bst.feature.skipNowggLogin",
                "bst.feature.show_programmatic_ads_preference",
                "bst.instance.Tiramisu64.android_google_ad_id",
                "bst.instance.Tiramisu64.ads_app_package",
                "bst.campaign_hash"):
        assert key not in found, key


def test_discover_reports_current_values(tmp_path):
    found = ads.discover(_conf(tmp_path))
    assert found["bst.enable_programmatic_ads"] == "1"
    assert found["bst.feature.send_offer_stats"] == "0"  # already off, still managed


# --- apply / remove ---------------------------------------------------------

def test_apply_turns_everything_off_and_status_reports_it(tmp_path):
    conf = _conf(tmp_path)
    assert ads.status(conf) is None
    ads.apply(conf)
    after = ads.discover(conf)
    assert after and all(v == "0" for v in after.values())
    st = ads.status(conf)
    assert st["ads_disabled"] is True
    assert st["reverted"] == []
    assert set(st["off"]) == set(after)


def test_apply_leaves_unrelated_keys_untouched(tmp_path):
    conf = _conf(tmp_path)
    ads.apply(conf)
    text = open(conf, encoding="utf-8").read()
    assert 'bst.enable_adb_access="1"' in text
    assert 'bst.feature.rooting="1"' in text
    assert 'bst.instance.Tiramisu64.enable_root_access="1"' in text
    assert 'bst.feature.skipNowggLogin="1"' in text
    assert 'bst.instance.Tiramisu64.android_google_ad_id="b11c1080-79be-42f6-99b4-0ae2bdf109ee"' in text


def test_remove_restores_original_values_exactly(tmp_path):
    conf = _conf(tmp_path)
    before = open(conf, encoding="utf-8").read()
    ads.apply(conf)
    ads.remove(conf)
    assert open(conf, encoding="utf-8").read() == before
    assert ads.status(conf) is None


def test_apply_is_idempotent(tmp_path):
    conf = _conf(tmp_path)
    ads.apply(conf)
    once = open(conf, encoding="utf-8").read()
    ads.apply(conf)
    assert open(conf, encoding="utf-8").read() == once


def test_reapply_after_bluestacks_reverts_a_key_keeps_true_originals(tmp_path):
    """BlueStacks puts some keys back to "1" on start; re-applying must not
    record "1" as the original and must not lose the real pre-change value."""
    conf = _conf(tmp_path)
    ads.apply(conf)
    # BlueStacks reverts one of the keys it's known to revert
    import config_handler
    config_handler.modify_config_file(conf, "bst.feature.programmatic_ads", "1")
    st = ads.status(conf)
    assert st["reverted"] == ["bst.feature.programmatic_ads"]

    ads.apply(conf)
    assert ads.status(conf)["reverted"] == []
    # and a full removal still restores the genuine original, not the reverted value
    ads.remove(conf)
    text = open(conf, encoding="utf-8").read()
    assert 'bst.feature.send_offer_stats="0"' in text   # was already 0 originally
    assert 'bst.feature.programmatic_ads="1"' in text   # was 1 originally


def test_status_flags_switches_a_bluestacks_update_added(tmp_path):
    conf = _conf(tmp_path)
    ads.apply(conf)
    import config_handler
    config_handler.modify_config_file(conf, "bst.feature.send_shiny_new_stats", "1")
    st = ads.status(conf)
    assert st["unmanaged"] == ["bst.feature.send_shiny_new_stats"]
    # re-applying adopts it
    ads.apply(conf)
    st = ads.status(conf)
    assert st["unmanaged"] == []
    assert "bst.feature.send_shiny_new_stats" in st["off"]


def test_apply_on_a_config_with_no_switches_is_not_an_error(tmp_path):
    conf = _conf(tmp_path, 'bst.enable_adb_access="1"\nbst.feature.rooting="1"\n')
    msg = ads.apply(conf)[0]
    assert "No ad/telemetry switches found" in msg
    assert ads.status(conf) is None


def test_remove_without_apply_is_a_no_op(tmp_path):
    conf = _conf(tmp_path)
    before = open(conf, encoding="utf-8").read()
    ads.remove(conf)
    assert open(conf, encoding="utf-8").read() == before
