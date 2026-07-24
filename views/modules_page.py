"""Modules page: pick a running instance, pick a module zip, push & flash."""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QRadioButton, QButtonGroup, QPushButton,
)


class ModulesPage(QWidget):
    browse_zip_requested = pyqtSignal()
    push_requested = pyqtSignal()

    _EMPTY_TEXT = ("No instance is running. Start one from the Instances tab, then "
                   "it will appear here.")
    _SCANNING_TEXT = "Checking which instances are running..."

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("1. Choose a running instance"))
        self.running_group = QButtonGroup(self)
        self.running_group.setExclusive(True)
        self._running_layout = QVBoxLayout()
        layout.addLayout(self._running_layout)
        self.no_running_label = QLabel(self._EMPTY_TEXT)
        self.no_running_label.setWordWrap(True)
        self.no_running_label.hide()
        layout.addWidget(self.no_running_label)

        layout.addWidget(QLabel("2. Choose module archive"))
        self.zip_label = QLabel("No file chosen")
        self.zip_label.setWordWrap(True)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setToolTip(
            "Pick a Magisk module .zip from your PC.")
        self.browse_button.clicked.connect(self.browse_zip_requested.emit)
        layout.addWidget(self.zip_label)
        layout.addWidget(self.browse_button)

        self.push_button = QPushButton("Push and flash module")
        self.push_button.setToolTip(
            "Copies the module into the running instance and flashes it with "
            "Magisk. Close and reopen the instance to activate it.")
        self.push_button.clicked.connect(self.push_requested.emit)
        self.push_button.setEnabled(False)
        layout.addWidget(self.push_button)
        layout.addStretch(1)

        self._radios: dict[str, QRadioButton] = {}
        self._busy = False

    def set_busy(self, busy: bool) -> None:
        """Force the push button disabled while a background op runs, so a
        radio/zip change mid-operation can't re-enable it out from under the
        app's busy state."""
        self._busy = busy
        self._update_push_enabled()

    def _clear_radios(self) -> None:
        for radio in self._radios.values():
            self.running_group.removeButton(radio)
            radio.deleteLater()
        self._radios = {}
        while self._running_layout.count():
            item = self._running_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def set_scanning(self) -> None:
        """Show a transient 'checking...' hint while the ADB probe runs on a
        background thread, so switching to this tab stays instant."""
        self._clear_radios()
        self.no_running_label.setText(self._SCANNING_TEXT)
        self.no_running_label.show()
        self._update_push_enabled()

    def set_running_instances(self, unique_ids: list) -> None:
        """Rebuild the radio list. Selection is cleared on every rebuild."""
        self._clear_radios()

        for uid in unique_ids:
            radio = QRadioButton(uid)
            radio.toggled.connect(self._update_push_enabled)
            self.running_group.addButton(radio)
            self._running_layout.addWidget(radio)
            self._radios[uid] = radio

        if unique_ids:
            self.no_running_label.hide()
        else:
            self.no_running_label.setText(self._EMPTY_TEXT)
            self.no_running_label.show()
        self._update_push_enabled()

    def set_zip_path(self, path: str) -> None:
        self.zip_label.setText(path or "No file chosen")
        self._update_push_enabled()

    def selected_instance_id(self):
        for uid, radio in self._radios.items():
            if radio.isChecked():
                return uid
        return None

    def zip_path(self) -> str:
        text = self.zip_label.text()
        return "" if text == "No file chosen" else text

    def _update_push_enabled(self) -> None:
        self.push_button.setEnabled(
            not self._busy
            and bool(self.selected_instance_id())
            and bool(self.zip_path())
        )
