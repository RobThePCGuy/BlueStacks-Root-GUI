import os

import pytest

import config_handler
import win_retry


def _write_conf(tmp_path, text):
    conf = tmp_path / "bluestacks.conf"
    conf.write_text(text, encoding="utf-8")
    return str(conf)


def test_get_complete_root_statuses_parses_display_names(tmp_path):
    conf = _write_conf(tmp_path, '\n'.join([
        'bst.instance.Nougat64.enable_root_access="1"',
        'bst.instance.Nougat64.display_name="Main Farm Bot"',
        'bst.instance.Pie64.enable_root_access="0"',
        'bst.instance.Pie64.display_name="Alt Account"',
        'bst.instance.NoName.enable_root_access="1"',
        'bst.feature.rooting="1"',
    ]))

    result = config_handler.get_complete_root_statuses(conf)

    assert result["global_status"] is True
    assert result["instance_statuses"] == {"Nougat64": True, "Pie64": False, "NoName": True}
    assert result["display_names"] == {"Nougat64": "Main Farm Bot", "Pie64": "Alt Account"}


def test_get_complete_root_statuses_missing_file_includes_display_names_key(tmp_path):
    result = config_handler.get_complete_root_statuses(str(tmp_path / "does_not_exist.conf"))
    assert result == {"global_status": False, "instance_statuses": {}, "display_names": {}}


def test_get_complete_root_statuses_unreadable_file_includes_display_names_key(tmp_path, monkeypatch):
    conf = _write_conf(tmp_path, 'bst.instance.Pie64.enable_root_access="1"')
    monkeypatch.setattr(config_handler, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")), raising=False)

    result = config_handler.get_complete_root_statuses(conf)
    assert result == {"global_status": False, "instance_statuses": {}, "display_names": {}}


def test_modify_config_file_updates_existing_setting(tmp_path):
    conf = _write_conf(tmp_path, 'bst.instance.Pie64.enable_root_access="0"\n')

    changed = config_handler.modify_config_file(
        conf, "bst.instance.Pie64.enable_root_access", "1")

    assert changed is True
    assert open(conf, encoding="utf-8").read() == 'bst.instance.Pie64.enable_root_access="1"\n'


def test_modify_config_file_appends_missing_setting(tmp_path):
    conf = _write_conf(tmp_path, 'bst.feature.rooting="0"\n')

    changed = config_handler.modify_config_file(
        conf, "bst.instance.New64.enable_root_access", "1")

    assert changed is True
    content = open(conf, encoding="utf-8").read()
    assert 'bst.feature.rooting="0"' in content
    assert 'bst.instance.New64.enable_root_access="1"' in content


def test_modify_config_file_no_temp_file_left_behind_on_success(tmp_path):
    conf = _write_conf(tmp_path, 'bst.feature.rooting="0"\n')

    config_handler.modify_config_file(conf, "bst.feature.rooting", "1")

    assert not os.path.isfile(conf + ".tmp")


def test_modify_config_file_retries_past_a_transient_sharing_violation(tmp_path, monkeypatch):
    """A real Windows sharing violation on os.replace() (AV/indexer/BlueStacks
    briefly holding the destination open) must self-heal via win_retry rather
    than fail the whole write on the first collision."""
    conf = _write_conf(tmp_path, 'bst.feature.rooting="0"\n')
    monkeypatch.setattr(win_retry.time, "sleep", lambda s: None)

    real_replace = os.replace
    calls = []

    def flaky_replace(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("sharing violation")
        return real_replace(src, dst)
    monkeypatch.setattr(config_handler.os, "replace", flaky_replace)

    changed = config_handler.modify_config_file(conf, "bst.feature.rooting", "1")

    assert changed is True
    assert len(calls) == 3  # two failures + the successful attempt
    assert open(conf, encoding="utf-8").read() == 'bst.feature.rooting="1"\n'
    assert not os.path.isfile(conf + ".tmp")


def test_modify_config_file_cleans_up_temp_and_preserves_original_on_persistent_failure(
        tmp_path, monkeypatch):
    """If the sharing violation never clears, the original file must be left
    completely intact (never truncated) and no .tmp sibling left behind."""
    conf = _write_conf(tmp_path, 'bst.feature.rooting="0"\n')
    monkeypatch.setattr(win_retry.time, "sleep", lambda s: None)

    def always_locked(src, dst):
        raise PermissionError("still locked")
    monkeypatch.setattr(config_handler.os, "replace", always_locked)

    with pytest.raises(OSError):
        config_handler.modify_config_file(conf, "bst.feature.rooting", "1")

    assert open(conf, encoding="utf-8").read() == 'bst.feature.rooting="0"\n'
    assert not os.path.isfile(conf + ".tmp")


def test_modify_config_file_unchanged_setting_skips_write_entirely(tmp_path, monkeypatch):
    conf = _write_conf(tmp_path, 'bst.feature.rooting="1"\n')

    def _boom(*a, **k):
        raise AssertionError("wrote despite the value already matching")
    monkeypatch.setattr(config_handler.win_retry, "retry_on_sharing_violation", _boom)

    changed = config_handler.modify_config_file(conf, "bst.feature.rooting", "1")

    assert changed is False
