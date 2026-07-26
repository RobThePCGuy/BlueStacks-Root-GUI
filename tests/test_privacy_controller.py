"""Locking the config file is confirmed before it happens.

The lock's side effect is silent: BlueStacks cannot write bluestacks.conf
either, so settings changed in BlueStacks' own UI look like they saved and are
gone at the next start, with no error shown anywhere. That is an easy evening to
lose, so ticking the box asks first; unticking does not, because unlocking
cannot surprise anyone.
"""
from unittest.mock import MagicMock

import pytest

from views.main_window import MainWindow


@pytest.fixture
def window(qtbot, monkeypatch):
    w = MainWindow()
    qtbot.addWidget(w)
    w.instance_data = {
        "Tiramisu64 (Normal)": {
            "config_path": r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf",
            "data_path": "d", "original_name": "Tiramisu64",
        },
    }
    # keep the status refresh off the real disk
    monkeypatch.setattr("telemetry_block.status", lambda _p: None)
    monkeypatch.setattr("ad_settings.discover", lambda _p: {})
    monkeypatch.setattr("ad_settings.status", lambda _p: None)
    return w


def test_locking_asks_first(window, monkeypatch):
    confirm = MagicMock(return_value=True)
    monkeypatch.setattr(window, "_confirm", confirm)
    locked = MagicMock()
    monkeypatch.setattr("ad_settings.lock", locked)

    window.privacy_controller.handle_ads_lock(True)

    confirm.assert_called_once()
    locked.assert_called_once()


def test_declining_does_not_lock(window, monkeypatch):
    monkeypatch.setattr(window, "_confirm", lambda *a, **k: False)
    locked = MagicMock()
    monkeypatch.setattr("ad_settings.lock", locked)

    window.privacy_controller.handle_ads_lock(True)

    locked.assert_not_called()


def test_the_warning_names_the_surprise(window, monkeypatch):
    """The whole point is that BlueStacks' own settings stop saving."""
    seen = {}

    def confirm(title, text, informative):
        seen["title"], seen["text"], seen["informative"] = title, text, informative
        return False

    monkeypatch.setattr(window, "_confirm", confirm)
    window.privacy_controller.handle_ads_lock(True)

    body = seen["informative"].lower()
    assert "cannot save its own settings" in body
    assert "untick" in body            # and how to get out of it


def test_unlocking_is_not_gated(window, monkeypatch):
    """Unlocking restores normal behaviour, so it needs no confirmation."""
    confirm = MagicMock(return_value=True)
    monkeypatch.setattr(window, "_confirm", confirm)
    unlocked = MagicMock()
    monkeypatch.setattr("ad_settings.unlock", unlocked)

    window.privacy_controller.handle_ads_lock(False)

    confirm.assert_not_called()
    unlocked.assert_called_once()


def test_a_declined_lock_leaves_the_checkbox_unticked(window, monkeypatch):
    """The box was ticked by the click; declining has to put it back."""
    monkeypatch.setattr(window, "_confirm", lambda *a, **k: False)
    monkeypatch.setattr("ad_settings.lock", MagicMock())
    window.privacy_page.ads_lock_check.setChecked(True)

    window.privacy_controller.handle_ads_lock(True)

    assert window.privacy_page.ads_lock_check.isChecked() is False
