"""Light/dark QSS themes and persistence."""
from __future__ import annotations

from PyQt5.QtCore import QSettings

_ORG = "RobThePCGuy"
_APP = "BlueStacksRootGUI"
_SETTINGS_KEY = "theme"

LIGHT = "light"
DARK = "dark"

_LIGHT_QSS = """
QWidget { background-color: #f3f3f3; color: #1a1a1a; }
QPushButton { background-color: #ffffff; border: 1px solid rgba(0,0,0,0.13); border-radius: 7px; padding: 6px 14px; }
QPushButton:hover { background-color: #f6f6f6; }
QPushButton:checked { background-color: #005fb8; color: #ffffff; }
QProgressBar { border: 1px solid rgba(0,0,0,0.13); border-radius: 3px; background: #eaeef2; }
QProgressBar::chunk { background-color: #005fb8; border-radius: 3px; }
QLabel#InstanceHeader { color: rgba(0,0,0,0.55); font-weight: 600; padding: 2px 0; }
QLabel#RootOn { color: #0f7b0f; font-weight: 600; padding: 2px 0; }
QLabel#RootOff, QLabel#RwState { color: rgba(0,0,0,0.55); padding: 2px 0; }
"""

_DARK_QSS = """
QWidget { background-color: #202020; color: #ffffff; }
QPushButton { background-color: #2b2b2b; border: 1px solid rgba(255,255,255,0.11); border-radius: 7px; padding: 6px 14px; color: #ffffff; }
QPushButton:hover { background-color: #303030; }
QPushButton:checked { background-color: #60cdff; color: #0a0a0a; }
QProgressBar { border: 1px solid rgba(255,255,255,0.11); border-radius: 3px; background: #262626; }
QProgressBar::chunk { background-color: #60cdff; border-radius: 3px; }
QLabel#InstanceHeader { color: rgba(255,255,255,0.55); font-weight: 600; padding: 2px 0; }
QLabel#RootOn { color: #6ccb5f; font-weight: 600; padding: 2px 0; }
QLabel#RootOff, QLabel#RwState { color: rgba(255,255,255,0.55); padding: 2px 0; }
"""

_THEMES = {LIGHT: _LIGHT_QSS, DARK: _DARK_QSS}


def stylesheet_for(theme: str) -> str:
    """QSS text for ``theme`` ("light" or "dark"). Raises ValueError otherwise."""
    try:
        return _THEMES[theme]
    except KeyError:
        raise ValueError("Unknown theme: %r" % theme) from None


def apply_theme(app, theme: str) -> None:
    """Apply ``theme`` to ``app`` (a QApplication) and persist the choice."""
    app.setStyleSheet(stylesheet_for(theme))
    QSettings(_ORG, _APP).setValue(_SETTINGS_KEY, theme)


def load_saved_theme() -> str:
    """The last-persisted theme, defaulting to light if none was saved."""
    value = QSettings(_ORG, _APP).value(_SETTINGS_KEY, LIGHT)
    return value if value in _THEMES else LIGHT
