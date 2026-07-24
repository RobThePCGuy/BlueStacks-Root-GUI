"""Dashboard page: install paths, engine-patch state, rooted-count stat,
update-revert alert."""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton


class DashboardPage(QWidget):
    patch_engine_requested = pyqtSignal()
    repatch_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.path_label = QLabel("BlueStacks Path: Loading...")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.alert_label = QLabel(
            "An auto-update reverted your engine patch. Rooted instances will "
            "fail the integrity check on next boot until you re-patch."
        )
        self.alert_label.setWordWrap(True)
        self.alert_label.setObjectName("UpdateRevertedAlert")
        self.repatch_button = QPushButton("Re-patch now")
        self.repatch_button.setToolTip(
            "Re-applies the engine patch that the BlueStacks update removed, "
            "so rooted instances boot again.")
        self.repatch_button.clicked.connect(self.repatch_requested.emit)
        layout.addWidget(self.alert_label)
        layout.addWidget(self.repatch_button)
        self.set_update_reverted(False)

        self.engine_button = QPushButton("")
        self.engine_button.clicked.connect(self.patch_engine_requested.emit)
        self.engine_button.setVisible(False)
        layout.addWidget(self.engine_button)

        self.stat_label = QLabel("0 / 0 instances rooted")
        layout.addWidget(self.stat_label)
        layout.addStretch(1)

    def set_paths_text(self, text: str) -> None:
        self.path_label.setText(text)

    def set_update_reverted(self, reverted: bool) -> None:
        self.alert_label.setVisible(reverted)
        self.repatch_button.setVisible(reverted)

    def set_engine_state(self, visible: bool, text: str, tooltip: str,
                         color: str, enabled: bool) -> None:
        self.engine_button.setVisible(visible)
        self.engine_button.setText(text)
        self.engine_button.setToolTip(tooltip)
        self.engine_button.setStyleSheet("color: %s; font-weight: bold;" % color)
        self.engine_button.setEnabled(enabled)

    def set_rooted_count(self, rooted: int, total: int) -> None:
        self.stat_label.setText("%d / %d instances rooted" % (rooted, total))
