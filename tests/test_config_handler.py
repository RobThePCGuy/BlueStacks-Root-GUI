import config_handler


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
