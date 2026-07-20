"""Magisk page: full offline system-root install/uninstall per instance, plus
the post-boot manager install.

Unlike the app-root toggle (which flips a guest ``su``), this installs a real
Magisk-managed root into the instance's system + data images while it's shut
down -- no R/W toggle, no temp-root. The flow is inherently two-phase: install
Magisk offline (instance closed), then boot the instance and install the manager
app over ADB.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QPushButton,
)


class MagiskPage(QWidget):
    install_requested = pyqtSignal()
    uninstall_requested = pyqtSignal()
    install_manager_requested = pyqtSignal()

    _EMPTY_TEXT = ("No instances detected yet. They appear here once BlueStacks "
                   "and its instances are found.")
    _PROMPT_TEXT = "Select an instance to see its Magisk status."
    _INTEGRITY_NOTE = (
        "How this works: Magisk installs into the instance's system + data "
        "images while it's shut down (no R/W toggle, no temp-root, no taps). "
        "After it finishes — start the instance, then click “Install "
        "manager app”.\n\n"
        "Play Integrity: with the right modules, Basic and Device are within "
        "reach. STRONG relies on a hardware-backed keystore that emulators "
        "don't have, so aim for Basic/Device here."
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
        self.status_label.setObjectName("MagiskStatus")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.install_button = QPushButton("Install Magisk (system root)")
        self.install_button.clicked.connect(self.install_requested.emit)
        self.uninstall_button = QPushButton("Uninstall Magisk")
        self.uninstall_button.clicked.connect(self.uninstall_requested.emit)
        self.manager_button = QPushButton("Install manager app")
        self.manager_button.setToolTip(
            "Installs the Magisk manager over ADB. Start the instance and enable "
            "ADB (Settings → Advanced) first.")
        self.manager_button.clicked.connect(self.install_manager_requested.emit)
        button_row.addWidget(self.install_button)
        button_row.addWidget(self.uninstall_button)
        button_row.addWidget(self.manager_button)
        layout.addLayout(button_row)

        note = QLabel(self._INTEGRITY_NOTE)
        note.setWordWrap(True)
        note.setObjectName("MagiskIntegrityNote")
        layout.addWidget(note)
        layout.addStretch(1)

        self._radios: dict[str, QRadioButton] = {}
        self._statuses: dict[str, dict | None] = {}
        self._busy = False
        self._update()

    def set_busy(self, busy: bool) -> None:
        """Force the action buttons disabled while a background op runs, so a
        selection change mid-operation can't re-enable them."""
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
        """Rebuild the instance list. ``statuses`` maps unique_id -> the
        instance's ``magisk_status()`` dict (or None if Magisk isn't installed).
        The current selection is preserved if that instance is still present."""
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

    def selected_status(self) -> dict | None:
        return self._statuses.get(self.selected_instance_id())

    def _status_text(self, uid) -> str:
        if uid is None:
            return self._PROMPT_TEXT
        st = self._statuses.get(uid)
        if not st:
            return "%s: Magisk not installed." % uid
        comps = ", ".join(st.get("components", [])) or "?"
        return "%s: Magisk %s installed (%s)." % (uid, st.get("version", "?"), comps)

    def _update(self, *_args) -> None:
        uid = self.selected_instance_id()
        installed = bool(uid and self._statuses.get(uid))
        self.status_label.setText(self._status_text(uid))
        # Show only the actions that apply: Install when Magisk isn't there yet,
        # Uninstall + manager once it is. A present-but-disabled button reads as
        # "you could do this" when you can't, so hide it rather than grey it.
        show_install = bool(uid) and not installed
        self.install_button.setVisible(show_install)
        self.uninstall_button.setVisible(installed)
        self.manager_button.setVisible(installed)
        # A visible button is clickable unless a background op is running.
        self.install_button.setEnabled(show_install and not self._busy)
        self.uninstall_button.setEnabled(installed and not self._busy)
        self.manager_button.setEnabled(installed and not self._busy)
