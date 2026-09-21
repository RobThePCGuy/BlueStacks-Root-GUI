"""Light/dark QSS themes and persistence."""
from __future__ import annotations

import sys

from PyQt5.QtCore import QSettings

_ORG = "RobThePCGuy"
_APP = "BlueStacksRootGUI"
_SETTINGS_KEY = "theme"

LIGHT = "light"
DARK = "dark"

# --- macOS group boxes ----------------------------------------------------
# QMacStyle paints a QGroupBox's *frame* as a filled panel in Qt's lightGray
# (#d3d3d3). The generic `QWidget { background-color }` rule below does not
# override it, because it is the frame being drawn and not the background --
# setting `background-color: transparent` changes nothing, only removing the
# border does. The result is that the Instances and Privacy tabs show grey
# slabs behind their groups on macOS that are invisible on Windows.
#
# So restate the frame explicitly, in the same flat rounded style the buttons
# already use. The title needs its own rule: once QSS takes over the box model,
# the frame is drawn at the widget's top edge and the title is clipped by it
# unless margin-top leaves room and the title is positioned into that margin.
#
# Scrollbars get the same treatment for a related reason: the blanket QWidget
# background breaks QMacStyle's scrollbar, which is then drawn *over* the
# content of a scroll area (the help window's text ran under it and was cut).
#
# Scoped to macOS deliberately. Windows already renders these correctly, it is
# this project's primary platform, and it cannot be verified from here -- so it
# keeps the native rendering untouched rather than trading a visible bug on one
# platform for an unverifiable change on the other.
_GROUPBOX_QSS = """
QGroupBox {
    background-color: transparent;
    border: 1px solid %(border)s;
    border-radius: 7px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QCheckBox::indicator:unchecked {
    background: %(box)s;
    border: 1px solid %(box_border)s;
    border-radius: 4px;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: %(box_border)s; border-radius: 3px; }
QScrollBar::handle:vertical { min-height: 24px; }
QScrollBar::handle:horizontal { min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""

# The indicator rule is deliberately :unchecked only. An *empty* macOS checkbox
# is drawn as near-white (#f4f4f4) against this theme's #f3f3f3 page, so it is
# invisible -- you cannot see which instances are tickable until one turns
# blue. Giving it a border fixes that. Styling the indicator in *all* states
# would instead hand the whole box to the QSS box model, which paints a flat
# rectangle and loses the checkmark glyph entirely (verified: the checked box
# renders white and empty). Restricting the rule to :unchecked leaves the
# checked state on the native painter, so the tick survives.

IS_MACOS = sys.platform == "darwin"

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

# Colours for the macOS-only rules, matching each theme's existing buttons.
_MACOS_COLOURS = {
    LIGHT: {"border": "rgba(0,0,0,0.13)", "box": "#ffffff",
            "box_border": "rgba(0,0,0,0.30)"},
    DARK: {"border": "rgba(255,255,255,0.11)", "box": "#2b2b2b",
           "box_border": "rgba(255,255,255,0.35)"},
}


def stylesheet_for(theme: str) -> str:
    """QSS text for ``theme`` ("light" or "dark"). Raises ValueError otherwise.

    On macOS this appends rules that correct two native-style artefacts; see
    ``_GROUPBOX_QSS``. Windows gets the base themes unchanged.
    """
    try:
        qss = _THEMES[theme]
    except KeyError:
        raise ValueError("Unknown theme: %r" % theme) from None
    if IS_MACOS:
        qss += _GROUPBOX_QSS % _MACOS_COLOURS[theme]
    return qss


def apply_theme(app, theme: str) -> None:
    """Apply ``theme`` to ``app`` (a QApplication) and persist the choice."""
    app.setStyleSheet(stylesheet_for(theme))
    QSettings(_ORG, _APP).setValue(_SETTINGS_KEY, theme)


def load_saved_theme() -> str:
    """The last-persisted theme, defaulting to light if none was saved."""
    value = QSettings(_ORG, _APP).value(_SETTINGS_KEY, LIGHT)
    return value if value in _THEMES else LIGHT
