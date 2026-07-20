"""Privacy page: block ad/telemetry domains in an instance's guest hosts file.

Offline + reversible, per Android version (Root.vhd is shared across instances
of a version). Emulator-only -- never touches the user's Windows hosts.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QPushButton,
)


class PrivacyPage(QWidget):
    block_requested = pyqtSignal()
    unblock_requested = pyqtSignal()

    _EMPTY_TEXT = ("No instances detected yet. They appear here once BlueStacks "
                   "and its instances are found.")
    _PROMPT_TEXT = "Select an instance to see its telemetry-block status."
    _NOTE = (
        "This null-routes ad, tracker, and analytics domains in the instance's "
        "guest hosts file — the same trick as a phone ad-blocker, but applied "
        "offline while the instance is shut down. It affects only the emulator "
        "(never your Windows machine) and is fully reversible.\n\n"
        "The block covers a version's shared system image, so it applies to "
        "every instance of that Android version. It does not touch Google Play, "
        "GMS, or an app's own servers."
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("1. Choose an instance"))
        self.instance_group = QButtonGroup(self)
        self.instance_group.setExclusive(True)
        self._instance_layout = QVBoxLayout()
        layout.addLayout(self._instance_layout)
        self.no_instances_label = QLabel(self._EMPTY_TEXT)
        self.no_instances_label.setWordWrap(True)
        self.no_instances_label.hide()
        layout.addWidget(self.no_instances_label)

        self.status_label = QLabel(self._PROMPT_TEXT)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("PrivacyStatus")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.block_button = QPushButton("Block ads & telemetry")
        self.block_button.setToolTip(
            "Writes the block into the guest hosts file offline. Closes BlueStacks "
            "first; reversible.")
        self.block_button.clicked.connect(self.block_requested.emit)
        self.unblock_button = QPushButton("Remove block")
        self.unblock_button.setToolTip("Restores the guest hosts file offline.")
        self.unblock_button.clicked.connect(self.unblock_requested.emit)
        button_row.addWidget(self.block_button)
        button_row.addWidget(self.unblock_button)
        layout.addLayout(button_row)

        note = QLabel(self._NOTE)
        note.setWordWrap(True)
        note.setObjectName("PrivacyNote")
        layout.addWidget(note)
        layout.addStretch(1)

        self._radios: dict[str, QRadioButton] = {}
        self._statuses: dict[str, dict | None] = {}
        self._busy = False
        self._update()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update()

    def _clear_radios(self) -> None:
        for radio in self._radios.values():
            self.instance_group.removeButton(radio)
            radio.deleteLater()
        self._radios = {}
        while self._instance_layout.count():
            item = self._instance_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def set_instances(self, statuses: dict) -> None:
        """``statuses`` maps unique_id -> telemetry_block.status() dict (or None
        if not blocked). Preserves selection if still present."""
        previous = self.selected_instance_id()
        self._clear_radios()
        self._statuses = dict(statuses)
        for uid in sorted(statuses):
            radio = QRadioButton(uid)
            radio.toggled.connect(self._update)
            self.instance_group.addButton(radio)
            self._instance_layout.addWidget(radio)
            self._radios[uid] = radio
        if previous in self._radios:
            self._radios[previous].setChecked(True)
        self.no_instances_label.setVisible(not statuses)
        self._update()

    def selected_instance_id(self):
        for uid, radio in self._radios.items():
            if radio.isChecked():
                return uid
        return None

    def _status_text(self, uid) -> str:
        if uid is None:
            return self._PROMPT_TEXT
        st = self._statuses.get(uid)
        if not st:
            return "%s: no telemetry block applied." % uid
        return "%s: blocking %s ad/telemetry domains." % (uid, st.get("domains", "?"))

    def _update(self, *_args) -> None:
        uid = self.selected_instance_id()
        blocked = bool(uid and self._statuses.get(uid))
        self.status_label.setText(self._status_text(uid))
        # Block when an instance is chosen and it's not blocked; Remove once it is.
        show_block = bool(uid) and not blocked
        self.block_button.setVisible(show_block)
        self.unblock_button.setVisible(blocked)
        busy = self._busy
        self.block_button.setEnabled(show_block and not busy)
        self.unblock_button.setEnabled(blocked and not busy)
