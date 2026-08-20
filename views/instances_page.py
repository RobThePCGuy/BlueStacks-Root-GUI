"""Instances page: one place for everything you do to an instance.

Root used to be split across two tabs, which hid the most important fact about
it: there are **two ways to root an instance and they conflict**. App root flips
BlueStacks' own switch and patches the guest ``su``; Magisk installs a real
managed root into the system image and brings modules with it. Both provide
``su``, so running both at once is the "Abnormal State" failure. Presented as
separate tabs they read as unrelated features rather than a choice, so they now
sit in one "Root" group where only the applicable actions are shown.

Selection follows what was already here: ticking several instances is how bulk
Toggle Root / Toggle R/W works, while the actions that only make sense for one
instance (Launch, Restart, and everything Magisk) require exactly one tick.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox, QCheckBox, QLabel,
    QPushButton, QHBoxLayout, QScrollArea,
)

import constants


class InstancesPage(QWidget):
    # instance-level
    toggle_root_requested = pyqtSignal()
    toggle_rw_requested = pyqtSignal()
    launch_requested = pyqtSignal()
    restart_requested = pyqtSignal()
    go_to_dashboard_requested = pyqtSignal()
    # magisk
    install_requested = pyqtSignal()
    update_requested = pyqtSignal()
    uninstall_requested = pyqtSignal()
    install_manager_requested = pyqtSignal()
    uninstall_manager_requested = pyqtSignal()
    install_rezygisk_requested = pyqtSignal()
    install_lsposed_requested = pyqtSignal()

    _PICK_ONE = "Tick one instance to see what you can do with it."
    _HINT_NATIVE = "Native Root is on. Choose Manager Root instead if you want modules."
    _HINT_CHOOSE = "Native Root for a quick su, or Manager Root to add modules."
    _HINT_MODULES = "Add ReZygisk, then LSPosed, then Restart once to activate them."
    _HINT_CONFLICT = ("Both roots are on and will fight over su. Switch off "
                      "Native Root.")

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
        # One wide name column plus three narrow state columns. The name used to
        # be printed twice (checkbox text and a separate label), which ate the
        # width that made everything else feel cramped; the id is a tooltip now.
        self.instance_layout.setColumnStretch(0, 1)
        for _c in (1, 2, 3):
            self.instance_layout.setColumnStretch(_c, 0)
        self.instance_layout.setHorizontalSpacing(18)
        self.instance_layout.setVerticalSpacing(4)
        # Rows start at the top of the scroll area; without this the grid floats
        # in the vertical middle once there are only a few instances.
        self.instance_layout.setAlignment(Qt.AlignTop)

        self.instance_scroll_area.setWidget(self.instance_container)
        instance_group_layout.addWidget(self.instance_scroll_area)
        layout.addWidget(self.instance_group)

        # --- what you do to the instance itself -----------------------------
        instance_actions = QHBoxLayout()
        self.launch_button = QPushButton("Launch")
        self.launch_button.setToolTip("Start the ticked instance.")
        self.launch_button.clicked.connect(self.launch_requested.emit)
        self.restart_button = QPushButton("Restart")
        self.restart_button.setToolTip(
            "Closes BlueStacks and starts the ticked instance again. The "
            "reliable reboot; an adb reboot does not restart BlueStacks.")
        self.restart_button.clicked.connect(self.restart_requested.emit)
        self.rw_toggle_button = QPushButton("Toggle R/W")
        self.rw_toggle_button.setToolTip(
            "Switches the ticked instances' disks between read-only and "
            "writable, so the system partition can be modified.")
        self.rw_toggle_button.clicked.connect(self.toggle_rw_requested.emit)
        for _b in (self.launch_button, self.restart_button, self.rw_toggle_button):
            instance_actions.addWidget(_b)
        instance_actions.addStretch(1)
        layout.addLayout(instance_actions)

        # --- root: the two methods, together so the choice is visible --------
        self.root_group = QGroupBox("Root")
        root_layout = QVBoxLayout(self.root_group)

        # Row 1: the choice itself. Two labels, kept short so they cannot
        # truncate at the window's minimum width; the explanation is in the
        # tooltips rather than on the buttons.
        choice_row = QHBoxLayout()
        self.root_toggle_button = QPushButton("Native Root")
        self.root_toggle_button.setToolTip(
            "BlueStacks' own su. Quick and reversible, works for root apps and "
            "root checkers, but gives you no modules.")
        self.root_toggle_button.clicked.connect(self.toggle_root_requested.emit)
        self.install_button = QPushButton("Manager Root")
        self.install_button.setToolTip(
            "Magisk-managed root: adds modules, Zygisk and LSPosed. Installed "
            "into the system image offline; switches off Native Root for you.")
        self.install_button.clicked.connect(self.install_requested.emit)
        self.uninstall_button = QPushButton("Remove Manager Root")
        self.uninstall_button.setToolTip(
            "Removes Magisk and restores the stock system image.")
        self.uninstall_button.clicked.connect(self.uninstall_requested.emit)
        for _b in (self.root_toggle_button, self.install_button, self.uninstall_button):
            choice_row.addWidget(_b)
        choice_row.addStretch(1)
        root_layout.addLayout(choice_row)

        # Row 2: what you can add once Manager Root is in. Separate row so the
        # group never overflows the window and truncates its labels.
        extras_row = QHBoxLayout()
        self.update_button = QPushButton("Update")
        self.update_button.setToolTip(
            "Checks for a newer Magisk and refreshes it if found. Your manager "
            "app and modules stay. Does nothing if already up to date.")
        self.update_button.clicked.connect(self.update_requested.emit)
        self.manager_button = QPushButton("Manager app")
        self.manager_button.setToolTip(
            "Installs the Magisk app over ADB. Normally handled for you when "
            "Manager Root is installed; this is the retry if that did not run.")
        self.manager_button.clicked.connect(self.install_manager_requested.emit)
        self.remove_manager_button = QPushButton("Remove app")
        self.remove_manager_button.setToolTip(
            "Uninstalls the Magisk app. Leaves the root itself in place.")
        self.remove_manager_button.clicked.connect(self.uninstall_manager_requested.emit)
        self.rezygisk_button = QPushButton("ReZygisk")
        self.rezygisk_button.setToolTip(
            "Adds Zygisk, which Zygisk modules need. Install this before LSPosed.")
        self.rezygisk_button.clicked.connect(self.install_rezygisk_requested.emit)
        self.lsposed_button = QPushButton("LSPosed")
        self.lsposed_button.setToolTip(
            "The Xposed framework; needs ReZygisk first. Manage its modules from "
            "the LSPosed app once the instance restarts.")
        self.lsposed_button.clicked.connect(self.install_lsposed_requested.emit)
        for _b in (self.update_button, self.manager_button, self.remove_manager_button,
                   self.rezygisk_button, self.lsposed_button):
            extras_row.addWidget(_b)
        extras_row.addStretch(1)
        root_layout.addLayout(extras_row)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setObjectName("MagiskHint")
        root_layout.addWidget(self.hint_label)
        layout.addWidget(self.root_group)

        self.checkboxes: dict[str, QCheckBox] = {}
        self._instance_data: dict[str, dict] = {}
        self._magisk: dict[str, dict | None] = {}
        self._busy = False
        # Set from the detected installation; see set_air_mode().
        self._air_mode = False
        self._update()

    # --- state in --------------------------------------------------------

    def set_engine_locked_banner(self, locked: bool) -> None:
        self.banner_label.setVisible(locked)
        self.banner_fix_button.setVisible(locked)

    def set_busy(self, busy: bool) -> None:
        """Force the action buttons disabled while a background op runs, so a
        selection change mid-operation can't re-enable them."""
        self._busy = busy
        self._update()

    def set_magisk_statuses(self, statuses: dict) -> None:
        """``statuses`` maps unique_id -> ``magisk_status()`` dict (or None)."""
        self._magisk = dict(statuses)
        self._refresh_rows()
        self._update()

    def _clear_grid(self) -> None:
        while self.instance_layout.count():
            item = self.instance_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def set_instances(self, instance_data: dict, preserve_selection: bool = True) -> None:
        """Rebuild the grid from ``instance_data`` (unique_id -> dict with
        at least ``root_enabled`` and ``rw_mode``)."""
        previous_selection = (
            {uid for uid, cb in self.checkboxes.items() if cb.isChecked()}
            if preserve_selection else set()
        )
        self._instance_data = dict(instance_data)
        self._build_rows(previous_selection)
        self._update()

    def _refresh_rows(self) -> None:
        self._build_rows({uid for uid, cb in self.checkboxes.items() if cb.isChecked()})

    def _build_rows(self, selected: set) -> None:
        self._clear_grid()
        self.checkboxes = {}

        # Column headers, so "Root:" and "R/W:" aren't repeated on every row.
        # R/W and Manager app are Windows-only concepts; on Air the columns are
        # dropped entirely rather than filled with "Off"/"-", which would read
        # as "a thing you have switched off" instead of "not a thing here".
        air = getattr(self, "_air_mode", False)
        columns = ((0, "Instance"), (1, "Root")) if air else (
            (0, "Instance"), (1, "Root"), (2, "R/W"), (3, "Manager app"))
        for col, title in columns:
            header = QLabel(title)
            header.setObjectName("InstanceHeader")
            self.instance_layout.addWidget(header, 0, col)

        for index, unique_id in enumerate(sorted(self._instance_data.keys())):
            row = index + 1                      # row 0 is the header
            data = self._instance_data[unique_id]
            app_root = bool(data.get("root_enabled"))
            rw_on = data.get("rw_mode") == constants.MODE_READWRITE
            magisk = self._magisk.get(unique_id)

            # Lead with the engine name, which is unique and stable. A display
            # name only earns a place when the user renamed it from BlueStacks'
            # generic default; otherwise every instance would read the same.
            checkbox = QCheckBox(self._row_label(unique_id, data))
            checkbox.setChecked(unique_id in selected)
            checkbox.setToolTip(unique_id)
            checkbox.toggled.connect(self._update)

            root_label = QLabel(self._root_text(app_root, magisk))
            # Styled by object name in the theme's QSS instead of a hard-coded
            # colour, so it follows the light/dark palette like everything else.
            root_label.setObjectName("RootOn" if (app_root or magisk) else "RootOff")
            if app_root and magisk:
                root_label.setToolTip(self._HINT_CONFLICT)
            rw_label = QLabel("On" if rw_on else "Off")
            rw_label.setObjectName("RwState")
            magisk_label = QLabel(self._magisk_text(magisk))
            magisk_label.setObjectName("RwState")
            if magisk:
                magisk_label.setToolTip(
                    "Magisk %s (%s)" % (magisk.get("version", "?"),
                                        ", ".join(magisk.get("components") or []) or "?"))

            self.instance_layout.addWidget(checkbox, row, 0)
            self.instance_layout.addWidget(root_label, row, 1)
            if not air:
                self.instance_layout.addWidget(rw_label, row, 2)
                self.instance_layout.addWidget(magisk_label, row, 3)
            self.checkboxes[unique_id] = checkbox

    @staticmethod
    def _row_label(unique_id: str, data: dict) -> str:
        name = data.get("original_name") or unique_id
        display = (data.get("display_name") or "").strip()
        if display and display != name and display not in constants.GENERIC_DISPLAY_NAMES:
            return "%s  ·  %s" % (name, display)   # "Tiramisu64 · My Bot"
        return name

    @staticmethod
    def _root_text(app_root: bool, magisk: dict | None) -> str:
        if app_root and magisk:
            return "Native + Manager"      # the conflicting state, named plainly
        if magisk:
            return "Manager"
        return "Native" if app_root else "Off"

    @staticmethod
    def _magisk_text(magisk: dict | None) -> str:
        if not magisk:
            return "-"
        return "yes" if "manager" in (magisk.get("components") or []) else "missing"

    # --- selection -------------------------------------------------------

    def selected_ids(self) -> list[str]:
        return [uid for uid, cb in self.checkboxes.items() if cb.isChecked()]

    def selected_instance_id(self):
        """The single ticked instance, or None when it isn't exactly one.

        Magisk acts on one instance at a time, the same rule Launch and Restart
        already used.
        """
        ids = self.selected_ids()
        return ids[0] if len(ids) == 1 else None

    def selected_status(self) -> dict | None:
        uid = self.selected_instance_id()
        return self._magisk.get(uid) if uid else None

    # --- derived UI ------------------------------------------------------

    # Air has one root method, not a choice between two, so the hints that
    # weigh Native Root against Manager Root would be advertising a button
    # that is not on screen.
    _HINT_AIR_OFF = ("Adds su to the Android system image all instances share. "
                     "Close BlueStacks first; undo from the same button.")
    _HINT_AIR_ON = ("Rooted: su is at /system/xbin/su in every instance. A "
                    "BlueStacks update replaces the image and removes it.")

    def _hint_text(self, uid, app_root, installed, manager) -> str:
        if uid is None:
            return self._PICK_ONE
        if getattr(self, "_air_mode", False):
            return self._HINT_AIR_ON if app_root else self._HINT_AIR_OFF
        if app_root and installed:
            return self._HINT_CONFLICT
        if app_root:
            return self._HINT_NATIVE
        if not installed:
            return self._HINT_CHOOSE
        return self._HINT_MODULES

    def set_air_mode(self, air: bool) -> None:
        """Reduce the page to the actions BlueStacks Air actually supports.

        Air has no R/W state to toggle (no .bstk files, one shared read-only
        system image) and no Magisk path (its offline installer drives Windows
        VHDs through bundled e2fsprogs ``.exe``s). Those buttons are hidden
        rather than disabled: a greyed-out button reads as "not right now",
        which would be a lie -- they will never apply here.
        """
        self._air_mode = air
        # The grid's columns depend on this flag, so rows built before it
        # arrived have to be rebuilt. Detection normally sets it before the
        # first load, so this is only for a later rescan that finds a
        # different install; skip the no-op rebuild when there is nothing
        # on screen yet.
        if self._instance_data:
            self._refresh_rows()
        self._update()

    def _update(self, *_args) -> None:
        busy = self._busy
        any_ticked = bool(self.selected_ids())
        uid = self.selected_instance_id()
        data = self._instance_data.get(uid) if uid else None
        st = self._magisk.get(uid) if uid else None
        app_root = bool(data and data.get("root_enabled"))
        installed = bool(st)
        manager = installed and "manager" in (st.get("components") or [])
        air = getattr(self, "_air_mode", False)

        self.hint_label.setText(self._hint_text(uid, app_root, installed, manager))

        # Bulk actions work on every tick; single-instance actions need one.
        self.root_toggle_button.setEnabled(any_ticked and not busy)
        self.rw_toggle_button.setEnabled(any_ticked and not busy)
        self.launch_button.setEnabled(uid is not None and not busy)
        self.restart_button.setEnabled(uid is not None and not busy)

        # The Native Root button is a toggle, so its label says what the click
        # will do rather than leaving the user to infer it from the grid.
        if air:
            # "Native Root" would understate it: on Air this installs su into
            # the shared system image, so it roots every instance at once.
            self.root_toggle_button.setText(
                "Remove Root (all instances)" if app_root else "Root (all instances)")
            self.root_toggle_button.setToolTip(
                "Installs su into the Android system image BlueStacks Air "
                "shares between all instances. Air ships no su of its own, so "
                "this is what root means here.\n\n"
                "While it is applied, BlueStacks.app's code signature no longer "
                "validates (the image is a sealed resource) -- the app still "
                "runs. Undoing from this same button restores the original "
                "image byte for byte and repairs that.")
        else:
            self.root_toggle_button.setText(
                "Disable Native Root" if app_root else "Native Root")

        self.rw_toggle_button.setVisible(not air)

        # Show only the actions that apply, in flow order. A present but disabled
        # button reads as "you could do this" when you can't.
        one = uid is not None and not air
        show_install = one and not installed
        self.install_button.setVisible(show_install)
        self.uninstall_button.setVisible(one and installed)
        self.update_button.setVisible(one and installed)
        # The manager app installs itself as part of Manager Root; this is the
        # retry for when that step could not run (instance never came up, ADB
        # unreachable), so it only appears when the app is actually absent.
        self.manager_button.setVisible(one and installed and not manager)
        self.remove_manager_button.setVisible(one and manager)
        self.rezygisk_button.setVisible(one and manager)
        self.lsposed_button.setVisible(one and manager)
        self.install_button.setEnabled(show_install and not busy)
        self.uninstall_button.setEnabled(one and installed and not busy)
        self.update_button.setEnabled(one and installed and not busy)
        self.manager_button.setEnabled(one and installed and not manager and not busy)
        self.remove_manager_button.setEnabled(one and manager and not busy)
        self.rezygisk_button.setEnabled(one and manager and not busy)
        self.lsposed_button.setEnabled(one and manager and not busy)
