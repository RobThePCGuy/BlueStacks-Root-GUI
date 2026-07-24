"""Instances page: instance grid + Toggle Root/R-W + patch-gating banner."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox, QCheckBox, QLabel,
    QPushButton, QHBoxLayout, QScrollArea,
)

import constants


class InstancesPage(QWidget):
    toggle_root_requested = pyqtSignal()
    toggle_rw_requested = pyqtSignal()
    launch_requested = pyqtSignal()
    restart_requested = pyqtSignal()
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
        self.banner_fix_button.setToolTip(
            "Opens the Dashboard, where the engine patch is applied.")
        self.banner_fix_button.clicked.connect(self.go_to_dashboard_requested.emit)
        banner_row = QHBoxLayout()
        banner_row.addWidget(self.banner_label, 1)
        banner_row.addWidget(self.banner_fix_button)
        layout.addLayout(banner_row)
        self.set_engine_locked_banner(False)

        # Instances group box: a scroll area wraps the grid so large instance
        # counts (20+) don't force the window taller than the screen.
        self.instance_group = QGroupBox("Instances")
        instance_group_layout = QVBoxLayout(self.instance_group)

        self.instance_scroll_area = QScrollArea()
        self.instance_scroll_area.setWidgetResizable(True)
        self.instance_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.instance_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.instance_container = QWidget()
        self.instance_layout = QGridLayout(self.instance_container)
        # One wide name column plus two narrow state columns. The name used to be
        # printed twice (checkbox text and a separate label), which ate the width
        # that made everything else feel cramped; the id now lives in a tooltip.
        self.instance_layout.setColumnStretch(0, 1)
        self.instance_layout.setColumnStretch(1, 0)
        self.instance_layout.setColumnStretch(2, 0)
        self.instance_layout.setHorizontalSpacing(18)
        self.instance_layout.setVerticalSpacing(4)
        # Rows start at the top of the scroll area; without this the grid floats
        # in the vertical middle once there are only a few instances.
        self.instance_layout.setAlignment(Qt.AlignTop)

        self.instance_scroll_area.setWidget(self.instance_container)
        instance_group_layout.addWidget(self.instance_scroll_area)
        layout.addWidget(self.instance_group)

        button_row = QHBoxLayout()
        self.root_toggle_button = QPushButton("Toggle Root")
        self.root_toggle_button.setToolTip(
            "Turns root on or off for the ticked instances. Closes BlueStacks "
            "first; start them again afterwards.")
        self.root_toggle_button.clicked.connect(self.toggle_root_requested.emit)
        self.rw_toggle_button = QPushButton("Toggle R/W")
        self.rw_toggle_button.setToolTip(
            "Switches the ticked instances' disks between read-only and "
            "writable, so the system partition can be modified.")
        self.rw_toggle_button.clicked.connect(self.toggle_rw_requested.emit)
        self.launch_button = QPushButton("Launch")
        self.launch_button.setToolTip("Start the selected instance (HD-Player).")
        self.launch_button.clicked.connect(self.launch_requested.emit)
        self.restart_button = QPushButton("Restart")
        self.restart_button.setToolTip(
            "Close all BlueStacks processes and relaunch the selected instance. "
            "The reliable reboot (adb reboot doesn't restart BlueStacks cleanly).")
        self.restart_button.clicked.connect(self.restart_requested.emit)
        for _b in (self.root_toggle_button, self.rw_toggle_button,
                   self.launch_button, self.restart_button):
            button_row.addWidget(_b)
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

        # Column headers, so "Root:" and "R/W:" aren't repeated on every row.
        for col, title in ((0, "Instance"), (1, "Root"), (2, "R/W")):
            header = QLabel(title)
            header.setObjectName("InstanceHeader")
            self.instance_layout.addWidget(header, 0, col)

        for index, unique_id in enumerate(sorted(instance_data.keys())):
            row = index + 1                      # row 0 is the header
            data = instance_data[unique_id]
            display_name = data.get("display_name", unique_id)
            root_on = bool(data.get("root_enabled"))
            rw_on = data.get("rw_mode") == constants.MODE_READWRITE

            # The checkbox carries the readable name; the unique id (which repeats
            # most of it) moves to the tooltip rather than a second column.
            checkbox = QCheckBox(display_name)
            checkbox.setChecked(unique_id in previous_selection)
            checkbox.setToolTip(unique_id)

            root_label = QLabel("On" if root_on else "Off")
            # Styled by object name in the theme's QSS instead of a hard-coded
            # colour, so it follows the light/dark palette like everything else.
            root_label.setObjectName("RootOn" if root_on else "RootOff")
            rw_label = QLabel("On" if rw_on else "Off")
            rw_label.setObjectName("RwState")

            self.instance_layout.addWidget(checkbox, row, 0)
            self.instance_layout.addWidget(root_label, row, 1)
            self.instance_layout.addWidget(rw_label, row, 2)
            self.checkboxes[unique_id] = checkbox

    def selected_ids(self) -> list[str]:
        return [uid for uid, cb in self.checkboxes.items() if cb.isChecked()]
