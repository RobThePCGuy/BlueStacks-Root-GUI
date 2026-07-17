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
