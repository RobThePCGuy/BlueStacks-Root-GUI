"""Privacy page: two independent controls, deliberately kept apart because they
have very different reach.

**BlueStacks ads & telemetry** (top, global) flips BlueStacks' own switches in
``bluestacks.conf``.  This is the one that actually stops the ads: they are
served by ``HD-Player.exe`` on Windows, and a live capture measured the player's
ad/tracker endpoints going 40 -> 0 with these switches off.  It applies to every
instance, because that config file is global.

**In-guest tracker block** (bottom, per instance) null-routes tracker domains in
one Android version's guest hosts file.  It reaches apps running *inside* the
emulator -- it cannot touch BlueStacks' own ads, which never go through the
guest at all.  It also modifies the system image, so it needs the engine patch.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QPushButton, QGroupBox, QCheckBox,
)


class PrivacyPage(QWidget):
    # global BlueStacks ad/telemetry switches
    ads_off_requested = pyqtSignal()
    ads_restore_requested = pyqtSignal()
    ads_lock_toggled = pyqtSignal(bool)
    # per-instance guest hosts block
    block_requested = pyqtSignal()
    unblock_requested = pyqtSignal()

    _EMPTY_TEXT = ("No instances detected yet. They appear here once BlueStacks "
                   "and its instances are found.")
    _PROMPT_TEXT = "Select an instance to see its tracker-block status."

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # --- global: BlueStacks' own ad/telemetry switches -------------------
        ads_box = QGroupBox("BlueStacks ads && telemetry (all instances)")
        ads_layout = QVBoxLayout(ads_box)

        self.ads_status_label = QLabel("Checking BlueStacks ad settings...")
        self.ads_status_label.setWordWrap(True)
        self.ads_status_label.setObjectName("PrivacyAdsStatus")
        ads_layout.addWidget(self.ads_status_label)

        ads_row = QHBoxLayout()
        self.ads_off_button = QPushButton("Turn off ads && telemetry")
        self.ads_off_button.setToolTip(
            "Turns off every ad, promo and stats-upload switch found in "
            "bluestacks.conf. Closes BlueStacks first; fully reversible.")
        self.ads_off_button.clicked.connect(self.ads_off_requested.emit)
        self.ads_restore_button = QPushButton("Restore BlueStacks defaults")
        self.ads_restore_button.setToolTip(
            "Puts every switch back to the value it had before this tool "
            "changed it.")
        self.ads_restore_button.clicked.connect(self.ads_restore_requested.emit)
        ads_row.addWidget(self.ads_off_button)
        ads_row.addWidget(self.ads_restore_button)
        ads_layout.addLayout(ads_row)

        self.ads_lock_check = QCheckBox(
            "Lock the config file so BlueStacks can't turn them back on")
        self.ads_lock_check.setToolTip(
            "Sets bluestacks.conf read-only so the switches can't be reverted. "
            "It also blocks BlueStacks' own settings, so unlock before changing "
            "them.")
        self.ads_lock_check.toggled.connect(self._on_lock_toggled)
        ads_layout.addWidget(self.ads_lock_check)

        layout.addWidget(ads_box)

        # --- per instance: guest hosts block ---------------------------------
        guest_box = QGroupBox("In-guest tracker block (one Android version)")
        guest_layout = QVBoxLayout(guest_box)

        guest_layout.addWidget(QLabel("1. Choose an instance"))
        self.instance_group = QButtonGroup(self)
        self.instance_group.setExclusive(True)
        self._instance_layout = QVBoxLayout()
        guest_layout.addLayout(self._instance_layout)
        self.no_instances_label = QLabel(self._EMPTY_TEXT)
        self.no_instances_label.setWordWrap(True)
        self.no_instances_label.hide()
        guest_layout.addWidget(self.no_instances_label)

        self.status_label = QLabel(self._PROMPT_TEXT)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("PrivacyStatus")
        guest_layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.block_button = QPushButton("Block in-guest trackers")
        self.block_button.setToolTip(
            "Writes the block into the guest hosts file offline. Closes "
            "BlueStacks first; reversible. Needs the engine patch.")
        self.block_button.clicked.connect(self.block_requested.emit)
        self.unblock_button = QPushButton("Remove block")
        self.unblock_button.setToolTip("Restores the guest hosts file offline.")
        self.unblock_button.clicked.connect(self.unblock_requested.emit)
        button_row.addWidget(self.block_button)
        button_row.addWidget(self.unblock_button)
        guest_layout.addLayout(button_row)

        layout.addWidget(guest_box)
        layout.addStretch(1)

        self._radios: dict[str, QRadioButton] = {}
        self._statuses: dict[str, dict | None] = {}
        self._ads_status: dict | None = None
        self._ads_total = 0
        self._busy = False
        self._emit_lock = True
        self._update()

    # --- global ad settings --------------------------------------------------

    def _on_lock_toggled(self, checked: bool) -> None:
        # set_ad_status() drives the checkbox to match reality; only a real user
        # click should reach the controller.
        if self._emit_lock:
            self.ads_lock_toggled.emit(checked)

    def set_ad_status(self, status: dict | None, total_switches: int = 0) -> None:
        """``status`` is ad_settings.status() (None when not applied);
        ``total_switches`` is how many switches the current config exposes."""
        self._ads_status = status
        self._ads_total = total_switches
        self._emit_lock = False
        self.ads_lock_check.setChecked(bool(status and status.get("locked")))
        self._emit_lock = True
        self._update()

    def _ads_status_text(self) -> str:
        """The visible line: state only. The why lives in :meth:`_ads_status_tip`."""
        st = self._ads_status
        if not st:
            if not self._ads_total:
                return "Ads and telemetry: no switches in this build"
            return "Ads and telemetry: on (%d switches)" % self._ads_total
        off = len(st.get("off") or [])
        total = st.get("keys", 0)
        reverted = st.get("reverted") or []
        if reverted:
            return "Ads and telemetry: off, %d of %d reverted by BlueStacks" % (
                len(reverted), total)
        if st.get("unmanaged"):
            return "Ads and telemetry: off, new switches available"
        return "Ads and telemetry: off (%d of %d)" % (off, total)

    def _ads_status_tip(self) -> str:
        st = self._ads_status
        if not st:
            if not self._ads_total:
                return ("This BlueStacks build exposes no ad or telemetry switches, "
                        "so there is nothing to turn off.")
            return ("BlueStacks' own advertising and stats uploads are enabled. "
                    "Turning them off applies to every instance.")
        parts = ["Every ad, promo and stats-upload switch found in bluestacks.conf "
                 "is off. Originals are recorded, so restoring is exact."]
        reverted = st.get("reverted") or []
        if reverted:
            parts.append(
                "BlueStacks has turned %d back on since, mostly stats beacons: %s. "
                "Turn them off again, or lock the config file to hold them."
                % (len(reverted), ", ".join(reverted[:6])))
        unmanaged = st.get("unmanaged") or []
        if unmanaged:
            parts.append("This build added %d switch(es) not covered yet; turning "
                         "off again adopts them." % len(unmanaged))
        return "\n\n".join(parts)

    # --- per-instance guest block -------------------------------------------

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
            return "%s: no tracker block applied" % uid
        return "%s: blocking %s tracker hostnames" % (uid, st.get("domains", "?"))

    def _update(self, *_args) -> None:
        busy = self._busy

        applied = bool(self._ads_status)
        has_switches = bool(self._ads_total)
        # Offer "turn off" whenever anything is still on (including after
        # BlueStacks reverts a key), and "restore" once we've recorded originals.
        reverted = bool(applied and self._ads_status.get("reverted"))
        unmanaged = bool(applied and self._ads_status.get("unmanaged"))
        show_off = has_switches and (not applied or reverted or unmanaged)
        self.ads_status_label.setText(self._ads_status_text())
        self.ads_status_label.setToolTip(self._ads_status_tip())
        self.ads_off_button.setVisible(show_off)
        self.ads_off_button.setEnabled(show_off and not busy)
        self.ads_restore_button.setVisible(applied)
        self.ads_restore_button.setEnabled(applied and not busy)
        self.ads_lock_check.setEnabled(has_switches and not busy)

        uid = self.selected_instance_id()
        blocked = bool(uid and self._statuses.get(uid))
        self.status_label.setText(self._status_text(uid))
        show_block = bool(uid) and not blocked
        self.block_button.setVisible(show_block)
        self.unblock_button.setVisible(blocked)
        self.block_button.setEnabled(show_block and not busy)
        self.unblock_button.setEnabled(blocked and not busy)
