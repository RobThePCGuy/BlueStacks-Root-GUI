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
    uninstall_manager_requested = pyqtSignal()
    install_rezygisk_requested = pyqtSignal()
    install_lsposed_requested = pyqtSignal()

    _EMPTY_TEXT = ("No instances detected yet. They appear here once BlueStacks "
                   "and its instances are found.")
    _PROMPT_TEXT = "Select an instance to see its Magisk status."

    # One short line that tracks the current step (set in _update). The buttons
    # already show only what applies now; the hint says what to do with them.
    _HINT_INSTALL = ("Install Magisk to root this instance. It runs offline, "
                     "then restarts the instance.")
    _HINT_MANAGER = "Next: start the instance, then install the manager."
    _HINT_MODULES = ("Next: install ReZygisk, then LSPosed, then Restart the "
                     "instance once from the Instances tab to activate them.")


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
        self.install_button = QPushButton("Install Magisk")
        self.install_button.setToolTip(
            "Offline Magisk system-root install, with the instance shut down.")
        self.install_button.clicked.connect(self.install_requested.emit)
        self.uninstall_button = QPushButton("Uninstall Magisk")
        self.uninstall_button.setToolTip(
            "Removes Magisk and restores the stock system image.")
        self.uninstall_button.clicked.connect(self.uninstall_requested.emit)
        self.manager_button = QPushButton("Install manager")
        self.manager_button.setToolTip(
            "Installs the Magisk app over ADB. Start the instance and enable ADB "
            "in its Settings, Advanced, first.")
        self.manager_button.clicked.connect(self.install_manager_requested.emit)
        self.remove_manager_button = QPushButton("Remove manager")
        self.remove_manager_button.setToolTip(
            "Uninstalls the Magisk app. Leaves the system root in place.")
        self.remove_manager_button.clicked.connect(self.uninstall_manager_requested.emit)
        self.rezygisk_button = QPushButton("Install ReZygisk")
        self.rezygisk_button.setToolTip(
            "Adds Zygisk, which Zygisk modules need. Install this before LSPosed.")
        self.rezygisk_button.clicked.connect(self.install_rezygisk_requested.emit)
        self.lsposed_button = QPushButton("Install LSPosed")
        self.lsposed_button.setToolTip(
            "The Xposed framework; needs ReZygisk first. Manage its modules from "
            "the LSPosed app once the instance restarts.")
        self.lsposed_button.clicked.connect(self.install_lsposed_requested.emit)
        for _b in (self.install_button, self.uninstall_button, self.manager_button,
                   self.remove_manager_button, self.rezygisk_button, self.lsposed_button):
            button_row.addWidget(_b)
        layout.addLayout(button_row)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setObjectName("MagiskHint")
        layout.addWidget(self.hint_label)

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
            return "%s · not rooted" % uid
        return "%s · rooted ✓" % uid

    def _status_tip(self, uid) -> str:
        # The version + component list lives in the tooltip: there when wanted,
        # off the main view otherwise.
        st = self._statuses.get(uid) if uid else None
        if not st:
            return ""
        comps = ", ".join(st.get("components", [])) or "?"
        return "Magisk %s installed (%s)." % (st.get("version", "?"), comps)

    def _hint_text(self, uid, installed, manager) -> str:
        if uid is None:
            return ""
        if not installed:
            return self._HINT_INSTALL
        if not manager:
            return self._HINT_MANAGER
        return self._HINT_MODULES

    def _update(self, *_args) -> None:
        uid = self.selected_instance_id()
        st = self._statuses.get(uid) if uid else None
        installed = bool(st)
        manager = installed and "manager" in (st.get("components") or [])
        self.status_label.setText(self._status_text(uid))
        self.status_label.setToolTip(self._status_tip(uid))
        self.hint_label.setText(self._hint_text(uid, installed, manager))
        # Show only the actions that apply, in flow order: Install Magisk when
        # it's not there; once installed, Uninstall + Install manager; once the
        # manager is in, Remove manager + Install ReZygisk (which needs the
        # manager to grant su for the flash). A present-but-disabled button reads
        # as "you could do this" when you can't, so hide rather than grey.
        show_install = bool(uid) and not installed
        self.install_button.setVisible(show_install)
        self.uninstall_button.setVisible(installed)
        self.manager_button.setVisible(installed and not manager)
        self.remove_manager_button.setVisible(manager)
        self.rezygisk_button.setVisible(manager)
        self.lsposed_button.setVisible(manager)
        # A visible button is clickable unless a background op is running.
        busy = self._busy
        self.install_button.setEnabled(show_install and not busy)
        self.uninstall_button.setEnabled(installed and not busy)
        self.manager_button.setEnabled(installed and not manager and not busy)
        self.remove_manager_button.setEnabled(manager and not busy)
        self.rezygisk_button.setEnabled(manager and not busy)
        self.lsposed_button.setEnabled(manager and not busy)
