"""Left navigation rail: Dashboard / Instances / Magisk / Modules / Privacy."""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QPushButton, QVBoxLayout

DASHBOARD = "dashboard"
INSTANCES = "instances"
MAGISK = "magisk"
MODULES = "modules"
PRIVACY = "privacy"

_DESTINATIONS = [
    (DASHBOARD, "Dashboard"),
    (INSTANCES, "Instances"),
    (MAGISK, "Magisk"),
    (MODULES, "Modules"),
    (PRIVACY, "Privacy"),
]


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
            btn.clicked.connect(lambda _checked, k=key: self.select(k))
            layout.addWidget(btn)
            self._buttons[key] = btn
        layout.addStretch(1)
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
