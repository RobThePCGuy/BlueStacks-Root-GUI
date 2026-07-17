"""Instances page: instance grid + Toggle Root/R-W + patch-gating banner."""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox, QCheckBox, QLabel,
    QPushButton, QHBoxLayout,
)

import constants


class InstancesPage(QWidget):
    toggle_root_requested = pyqtSignal()
    toggle_rw_requested = pyqtSignal()
    go_to_dashboard_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.banner_label = QLabel(
            "Patch-mode root is locked. Patch the engine to root the "
            "5.22.150+ instances. (The MSI classic instance roots without it.)"
        )
        self.banner_label.setWordWrap(True)
        self.banner_fix_button = QPushButton("Fix it")
        self.banner_fix_button.clicked.connect(self.go_to_dashboard_requested.emit)
        banner_row = QHBoxLayout()
        banner_row.addWidget(self.banner_label, 1)
        banner_row.addWidget(self.banner_fix_button)
        layout.addLayout(banner_row)
        self.set_engine_locked_banner(False)

        self.instance_group = QGroupBox("Instances")
        self.instance_layout = QGridLayout()
        self.instance_layout.setColumnStretch(0, 4)
        self.instance_layout.setColumnStretch(1, 1)
        self.instance_layout.setColumnStretch(2, 1)
        self.instance_layout.setHorizontalSpacing(15)
        self.instance_group.setLayout(self.instance_layout)
        layout.addWidget(self.instance_group)

        button_row = QHBoxLayout()
        self.root_toggle_button = QPushButton("Toggle Root")
        self.root_toggle_button.clicked.connect(self.toggle_root_requested.emit)
        self.rw_toggle_button = QPushButton("Toggle R/W")
        self.rw_toggle_button.clicked.connect(self.toggle_rw_requested.emit)
        button_row.addWidget(self.root_toggle_button)
        button_row.addWidget(self.rw_toggle_button)
        layout.addLayout(button_row)

        self.checkboxes: dict[str, QCheckBox] = {}

    def set_engine_locked_banner(self, locked: bool) -> None:
        self.banner_label.setVisible(locked)
        self.banner_fix_button.setVisible(locked)

    def set_instances(self, instance_data: dict, preserve_selection: bool = True) -> None:
        """Rebuild the grid from ``instance_data`` (unique_id -> dict with
        at least ``root_enabled`` and ``rw_mode``)."""
        previous_selection = (
            {uid for uid, cb in self.checkboxes.items() if cb.isChecked()}
            if preserve_selection else set()
        )
        while self.instance_layout.count():
            item = self.instance_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.checkboxes = {}

        for row, unique_id in enumerate(sorted(instance_data.keys())):
            data = instance_data[unique_id]
            checkbox = QCheckBox(unique_id)
            checkbox.setChecked(unique_id in previous_selection)
            root_text = "On" if data.get("root_enabled") else "Off"
            rw_text = "On" if data.get("rw_mode") == constants.MODE_READWRITE else "Off"
            self.instance_layout.addWidget(checkbox, row, 0)
            self.instance_layout.addWidget(QLabel("Root: %s" % root_text), row, 1)
            self.instance_layout.addWidget(QLabel("R/W: %s" % rw_text), row, 2)
            self.checkboxes[unique_id] = checkbox

    def selected_ids(self) -> list[str]:
        return [uid for uid, cb in self.checkboxes.items() if cb.isChecked()]
