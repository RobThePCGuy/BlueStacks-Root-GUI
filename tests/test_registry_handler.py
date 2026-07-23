"""Coverage for ``registry_handler.get_all_bluestacks_installations`` -- reads
three Windows Registry paths (Normal/CN/MSI editions) and had zero tests.

``winreg`` itself is real here (the whole suite already requires Windows, see
conftest.py), so rather than faking module *existence* we monkeypatch
``winreg.OpenKey``/``winreg.QueryValueEx`` to serve fixture data instead of the
real registry, and keep the real ``HKEY_LOCAL_MACHINE``/``KEY_READ``/``REG_SZ``
constants the code compares/passes through. Each test pins down one specific,
previously-unverified branch: a whole source missing vs. permission-denied vs.
one individual value missing, the "need both UserDefinedDir and DataDir"
gating rule, the REG_SZ type guard, and that sources aren't cross-contaminated.
"""
from __future__ import annotations

import winreg

import constants
import registry_handler

# conftest.py's repo-root autouse fixture stubs
# registry_handler.get_all_bluestacks_installations to `lambda: []` for every
# test (so unrelated GUI tests never hit the real registry). These tests exist
# specifically to exercise the real function, so capture the genuine function
# object at collection time -- before that fixture ever runs for any test --
# and call it directly instead of through the (per-test-patched) module
# attribute. The captured function still reads module globals (winreg, etc.)
# via its own __globals__, so our winreg patches below still apply to it.
_get_all = registry_handler.get_all_bluestacks_installations


class _FakeKey:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_registry(monkeypatch, data: dict, deny: set = frozenset()):
    """``data`` maps reg_path -> {value_name: (value, type)}. ``deny`` is the
    set of reg_paths that should raise PermissionError on OpenKey. A reg_path
    present in neither raises FileNotFoundError on OpenKey (path doesn't exist)."""

    def fake_open_key(hkey, path, reserved, access):
        assert hkey == winreg.HKEY_LOCAL_MACHINE
        assert access == winreg.KEY_READ
        if path in deny:
            raise PermissionError()
        if path not in data:
            raise FileNotFoundError()
        return _FakeKey(data[path])

    def fake_query_value_ex(key, name):
        if name not in key.values:
            raise FileNotFoundError()
        return key.values[name]

    monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(winreg, "QueryValueEx", fake_query_value_ex)


def _full_values(user_dir, data_dir, install_dir, version):
    return {
        constants.REGISTRY_USER_DIR_KEY: (user_dir, winreg.REG_SZ),
        constants.REGISTRY_DATA_DIR_KEY: (data_dir, winreg.REG_SZ),
        constants.REGISTRY_INSTALL_DIR_KEY: (install_dir, winreg.REG_SZ),
        constants.REGISTRY_VERSION_KEY: (version, winreg.REG_SZ),
    }


def test_finds_single_installation_with_all_fields_and_patch_mode(monkeypatch):
    _patch_registry(monkeypatch, {
        constants.REGISTRY_BASE_PATH: _full_values(
            r"C:\Users\me\AppData\Local\BlueStacks_nxt",
            r"C:\ProgramData\BlueStacks_nxt",
            r"C:\Program Files\BlueStacks_nxt",
            "5.22.232.1002",  # >= PATCH_MIN_VERSION
        ),
    })

    result = _get_all()

    assert len(result) == 1
    entry = result[0]
    assert entry["source"] == constants.APP_SOURCE_NXT
    assert entry["user_path"] == r"C:\Users\me\AppData\Local\BlueStacks_nxt"
    assert entry["data_path"] == r"C:\ProgramData\BlueStacks_nxt"
    assert entry["install_path"] == r"C:\Program Files\BlueStacks_nxt"
    assert entry["version"] == (5, 22, 232, 1002)
    assert entry["patch_mode"] is True
    assert entry["config_path"] == r"C:\Users\me\AppData\Local\BlueStacks_nxt\bluestacks.conf"


def test_below_patch_min_version_is_not_patch_mode(monkeypatch):
    _patch_registry(monkeypatch, {
        constants.REGISTRY_BASE_PATH: _full_values(
            r"C:\u", r"C:\d", r"C:\i", "5.21.130.1001",
        ),
    })

    result = _get_all()

    assert result[0]["patch_mode"] is False


def test_all_registry_paths_missing_returns_empty_list(monkeypatch):
    _patch_registry(monkeypatch, {})

    assert _get_all() == []


def test_permission_denied_source_is_skipped_others_still_found(monkeypatch):
    _patch_registry(
        monkeypatch,
        data={
            constants.REGISTRY_MSI_BASE_PATH: _full_values(
                r"C:\u_msi", r"C:\d_msi", r"C:\i_msi", "5.22.75.6322",
            ),
        },
        deny={constants.REGISTRY_BASE_PATH},
    )

    result = _get_all()

    assert len(result) == 1
    assert result[0]["source"] == constants.APP_SOURCE_MSI


def test_missing_install_dir_and_version_values_still_yields_partial_entry(monkeypatch):
    # UserDefinedDir + DataDir present; InstallDir + Version absent (older/odd
    # build). Only user_dir/data_dir gate whether an entry is appended at all.
    _patch_registry(monkeypatch, {
        constants.REGISTRY_BASE_PATH: {
            constants.REGISTRY_USER_DIR_KEY: (r"C:\u", winreg.REG_SZ),
            constants.REGISTRY_DATA_DIR_KEY: (r"C:\d", winreg.REG_SZ),
        },
    })

    result = _get_all()

    assert len(result) == 1
    assert result[0]["install_path"] is None
    assert result[0]["version"] is None
    assert result[0]["patch_mode"] is False  # bool(None and ...) is False


def test_missing_data_dir_excludes_installation_even_with_user_dir_present(monkeypatch):
    _patch_registry(monkeypatch, {
        constants.REGISTRY_BASE_PATH: {
            constants.REGISTRY_USER_DIR_KEY: (r"C:\u", winreg.REG_SZ),
            # DataDir absent -> "if user_dir and data_dir" gate fails.
        },
    })

    assert _get_all() == []


def test_non_string_value_type_is_ignored(monkeypatch):
    # A REG_DWORD (or any non-REG_SZ type) for UserDefinedDir must be treated
    # as absent, not coerced -- the code explicitly gates on reg_type == REG_SZ.
    _patch_registry(monkeypatch, {
        constants.REGISTRY_BASE_PATH: {
            constants.REGISTRY_USER_DIR_KEY: (1, winreg.REG_DWORD),
            constants.REGISTRY_DATA_DIR_KEY: (r"C:\d", winreg.REG_SZ),
        },
    })

    # user_dir stayed None (wrong type), so the "user_dir and data_dir" gate fails.
    assert _get_all() == []


def test_three_sources_found_are_not_cross_contaminated(monkeypatch):
    _patch_registry(monkeypatch, {
        constants.REGISTRY_BASE_PATH: _full_values(
            r"C:\nxt_u", r"C:\nxt_d", r"C:\nxt_i", "5.22.232.1002",
        ),
        constants.REGISTRY_CN_BASE_PATH: _full_values(
            r"C:\cn_u", r"C:\cn_d", r"C:\cn_i", "5.22.170.6509",
        ),
        constants.REGISTRY_MSI_BASE_PATH: _full_values(
            r"C:\msi_u", r"C:\msi_d", r"C:\msi_i", "5.22.75.6322",
        ),
    })

    result = _get_all()

    by_source = {e["source"]: e for e in result}
    assert set(by_source) == {constants.APP_SOURCE_NXT, constants.APP_SOURCE_NXT_CN,
                              constants.APP_SOURCE_MSI}
    assert by_source[constants.APP_SOURCE_NXT]["user_path"] == r"C:\nxt_u"
    assert by_source[constants.APP_SOURCE_NXT_CN]["user_path"] == r"C:\cn_u"
    assert by_source[constants.APP_SOURCE_MSI]["user_path"] == r"C:\msi_u"
