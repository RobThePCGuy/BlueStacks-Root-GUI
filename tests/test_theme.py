import pytest

from views import theme


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    # Route persistence at a throwaway org/app name per test so tests never
    # touch the real registry entry the actual app would use.
    monkeypatch.setattr(theme, "_ORG", "BlueStacksRootGUI-Test")
    monkeypatch.setattr(theme, "_APP", "theme-test-%s" % tmp_path.name)
    yield


def test_stylesheet_for_light_contains_light_background():
    assert "#f3f3f3" in theme.stylesheet_for(theme.LIGHT)


def test_stylesheet_for_dark_contains_dark_background():
    assert "#202020" in theme.stylesheet_for(theme.DARK)


def test_stylesheet_for_unknown_theme_raises():
    with pytest.raises(ValueError):
        theme.stylesheet_for("solarized")


def test_apply_theme_sets_app_stylesheet(qapp):
    theme.apply_theme(qapp, theme.DARK)
    assert qapp.styleSheet() == theme.stylesheet_for(theme.DARK)


def test_load_saved_theme_defaults_to_light():
    assert theme.load_saved_theme() == theme.LIGHT


def test_apply_theme_persists_choice(qapp):
    theme.apply_theme(qapp, theme.DARK)
    assert theme.load_saved_theme() == theme.DARK


# --- macOS native-style corrections --------------------------------------
# QMacStyle paints a QGroupBox's frame as a filled lightGray panel, and draws
# an empty checkbox at #f4f4f4 against the light theme's #f3f3f3 page. Both
# read as bugs on macOS and neither happens on Windows, so the corrections are
# appended only there -- Windows keeps the base themes byte-for-byte.

@pytest.mark.parametrize("name", [theme.LIGHT, theme.DARK])
def test_macos_appends_groupbox_and_checkbox_rules(monkeypatch, name):
    monkeypatch.setattr(theme, "IS_MACOS", True)
    qss = theme.stylesheet_for(name)
    assert "QGroupBox {" in qss
    assert "background-color: transparent" in qss
    assert "QGroupBox::title" in qss
    assert "QCheckBox::indicator:unchecked" in qss


@pytest.mark.parametrize("name", [theme.LIGHT, theme.DARK])
def test_windows_stylesheet_is_untouched(monkeypatch, name):
    """The base themes are this project's Windows appearance; leave them be."""
    monkeypatch.setattr(theme, "IS_MACOS", False)
    assert theme.stylesheet_for(name) == theme._THEMES[name]


def test_checkbox_rule_targets_unchecked_only(monkeypatch):
    """Styling every state hands the box to the QSS painter and loses the tick.

    Verified by rendering: an all-states rule draws the checked box as a flat
    white rectangle with no checkmark, so the rule must stay :unchecked-scoped.
    """
    monkeypatch.setattr(theme, "IS_MACOS", True)
    qss = theme.stylesheet_for(theme.LIGHT)
    assert "QCheckBox::indicator {" not in qss
    assert "QCheckBox::indicator:checked" not in qss


def test_macos_groupbox_leaves_room_for_its_title(monkeypatch):
    """Without a top margin the frame is drawn over the title text."""
    monkeypatch.setattr(theme, "IS_MACOS", True)
    qss = theme.stylesheet_for(theme.LIGHT)
    assert "margin-top" in qss
    assert "subcontrol-origin: margin" in qss
