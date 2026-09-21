"""Left navigation rail: Dashboard / Instances / Modules / Privacy.

Magisk used to be its own destination. It is part of Instances now: root
is one decision per instance, and splitting it across two tabs hid that
app root and Magisk are alternatives that conflict.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QPushButton, QVBoxLayout

DASHBOARD = "dashboard"
INSTANCES = "instances"
MODULES = "modules"
PRIVACY = "privacy"

_DESTINATIONS = [
    (DASHBOARD, "Dashboard"),
    (INSTANCES, "Instances"),
    (MODULES, "Modules"),
    (PRIVACY, "Privacy"),
]

_TIPS = {
    DASHBOARD: "Where BlueStacks was found, and whether it is ready to root.",
    INSTANCES: "Your instances: root them, launch them, restart them.",
    MODULES: "Install a Magisk module .zip into a running instance.",
    PRIVACY: "Turn off BlueStacks' ads and telemetry, and block trackers inside Android.",
}


class NavRail(QFrame):
    """Emits ``navigate(str)`` with a destination key (see _DESTINATIONS)."""

    navigate = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavRail")
        self._buttons: dict[str, QPushButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 12)
        for key, label in _DESTINATIONS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(_TIPS[key])
            btn.clicked.connect(lambda _checked, k=key: self.select(k))
            layout.addWidget(btn)
            self._buttons[key] = btn
        layout.addStretch(1)
        self.select(DASHBOARD)

    def set_destination_visible(self, key: str, visible: bool) -> None:
        """Show or hide one destination.

        Used to drop Modules on BlueStacks Air, whose module install path is
        Magisk-over-ADB and does not exist there. If the hidden destination is
        the current one, fall back to Dashboard so the rail cannot end up with
        nothing selected and a page the user can no longer navigate away from.
        """
        btn = self._buttons.get(key)
        if btn is None:
            return
        btn.setVisible(visible)
        if not visible and self.current() == key:
            self.select(DASHBOARD)

    def select(self, key: str) -> None:
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        self.navigate.emit(key)

    def current(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return DASHBOARD
