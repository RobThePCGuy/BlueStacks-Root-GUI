"""Qt5-based GUI application for toggling BlueStacks root access."""
from __future__ import annotations

import sys
import os
import logging
import tempfile
from typing import Any

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QCheckBox,
    QMessageBox,
    QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QIcon


import constants
import registry_handler
import config_handler
import instance_handler
import root_persistence
import integrity_patch
import su_patch_offline
import ext4_symlink
import adb_handler
import admin

# Log to console AND a file in the local temp dir. The file is important when
# the app is relaunched elevated: that process has its own (often invisible)
# console, so a startup crash would otherwise vanish. The temp dir is always on
# a local drive and writable even when elevated.
LOG_PATH = os.path.join(tempfile.gettempdir(), "BlueStacksRootGUI.log")
_handlers = [logging.StreamHandler()]
try:
    _handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
except Exception:  # noqa: BLE001 - never let logging setup stop the app
    pass
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=_handlers)
logger = logging.getLogger(__name__)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class _OpWorker(QObject):
    """Runs a blocking job(progress) on a worker thread, relaying progress text."""
    progress = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, job):
        super().__init__()
        self._job = job

    @pyqtSlot()
    def run(self):
        try:
            summary = self._job(self.progress.emit)
            self.done.emit(True, summary)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Background operation failed")
            self.done.emit(False, str(exc))


class BluestacksRootToggle(QWidget):
    """Main application window for toggling BlueStacks root and R/W settings."""

    # Emitted from the worker thread to surface a modal notice on the UI thread.
    show_notice = pyqtSignal(str, str)  # (title, message)

    def __init__(self):
        super().__init__()
        self.installations: list[registry_handler.Installation] = []
        self.instance_data: dict[str, dict[str, Any]] = {}
        self.instance_checkboxes: dict[str, dict[str, Any]] = {}

        # Queued (cross-thread) so background jobs can pop a dialog safely.
        self.show_notice.connect(self._show_notice)
        self.setWindowTitle(f"{constants.APP_NAME} v{constants.APP_VERSION}")
        self._set_icon()
        self.status_refresh_timer = QTimer(self)
        self.status_refresh_timer.timeout.connect(
            lambda: self.update_instance_statuses(preserve_selection=True)
        )
        self.init_ui()
        QTimer.singleShot(0, self.initialize_paths_and_instances)

    def _set_icon(self):
        try:
            icon_path = resource_path(constants.ICON_FILENAME)
            app_icon = QIcon(icon_path)
            if not app_icon.isNull(): self.setWindowIcon(app_icon)
        except Exception as e:
            logger.error(f"Error setting window icon: {e}")

    def init_ui(self) -> None:
        main_layout = QVBoxLayout()
        self.path_label = QLabel("BlueStacks Path: Loading...")
        self.path_label.setWordWrap(True)
        main_layout.addWidget(self.path_label)

        self.instance_group = QGroupBox("Instances")
        self.instance_layout = QGridLayout()
        self.instance_layout.setColumnStretch(0, 3)
        self.instance_layout.setColumnStretch(1, 4)
        self.instance_layout.setColumnStretch(2, 1)
        self.instance_layout.setColumnStretch(3, 1)
        self.instance_layout.setHorizontalSpacing(10)
        self.instance_group.setLayout(self.instance_layout)
        main_layout.addWidget(self.instance_group)

        button_layout = QHBoxLayout()
        self.root_toggle_button = QPushButton("Toggle Root")
        self.root_toggle_button.clicked.connect(self.handle_toggle_root)
        self.rw_toggle_button = QPushButton("Toggle R/W")
        self.rw_toggle_button.clicked.connect(self.handle_toggle_rw)
        button_layout.addWidget(self.root_toggle_button)
        button_layout.addWidget(self.rw_toggle_button)
        main_layout.addLayout(button_layout)

        # --- Engine patch (5.22.150.1014+ only) ----------------------------
        # One button that both SHOWS the engine state and acts on it: when the
        # engine isn't patched it offers "Patch"; once patched it turns green and
        # offers "Undo". The engine patch flips _isDiskVerificationRequired() in
        # HD-Player.exe to 0 (disables the "illegally tampered" shutdown so a
        # rooted /system can boot). It's per-install, shared by every instance.
        # Hidden entirely on older builds (classic conf rooting).
        self.engine_button = QPushButton("")
        self.engine_button.clicked.connect(self.handle_engine_button)
        main_layout.addWidget(self.engine_button)
        self.engine_button.setVisible(False)  # shown once installations are read

        # --- Install a Magisk/Kitsune module directly ---------------------
        # Pushes a module .zip into a RUNNING instance and flashes it over an ADB
        # root shell (magisk --install-module) -- sidesteps BlueStacks' file
        # picker handing Magisk an "Invalid Uri" it can't open. Falls back to
        # dropping the zip in Download if the root shell isn't reachable.
        self.sideload_button = QPushButton("Install Magisk Module (.zip) into a running instance")
        self.sideload_button.setToolTip(
            "Select one running instance above, choose a module .zip, and it's "
            "pushed in and flashed via Magisk automatically. Close and reopen the "
            "instance afterwards to activate it. The instance must be running."
        )
        self.sideload_button.clicked.connect(self.handle_sideload_module)
        main_layout.addWidget(self.sideload_button)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)
        self.setMinimumWidth(550)

    def initialize_paths_and_instances(self) -> None:
        logger.info("Initializing BlueStacks paths and instances...")
        self._clear_instance_widgets()
        self.installations = registry_handler.get_all_bluestacks_installations()
        if not self.installations:
            self.path_label.setText("No BlueStacks installations found.")
            return

        path_details = ["Installations Found:"]
        for inst in self.installations:
            ver = ".".join(map(str, inst["version"])) if inst.get("version") else "?"
            path_details.append(f"  - {inst['source']} v{ver}: {inst['user_path']}")
        self.path_label.setText("\n".join(path_details))

        self._refresh_patch_ui()
        self.update_instance_statuses(preserve_selection=False)
        self.status_refresh_timer.start(constants.REFRESH_INTERVAL_MS)

    def _refresh_patch_ui(self) -> None:
        """Drive the single engine button from the current patch state.

        Shown only when a 5.22.150.1014+ install exists. The button's label,
        colour, and action all reflect state: unpatched -> "Patch", patched ->
        green "Undo", partial -> "re-patch", unknown -> disabled.
        """
        has_patch_build = any(i.get("patch_mode") for i in self.installations)
        self.engine_button.setVisible(has_patch_build)
        if not has_patch_build:
            return
        state = self._engine_state()
        text, color, tip, enabled = {
            "patched": ("✓ Engine patched — click to Undo (restore originals)",
                        "#2e7d32", "Restores HD-Player.exe + HD-MultiInstanceManager.exe "
                        "from the .prepatch.bak backups.", True),
            "unpatched": ("Patch BlueStacks Engine (required for root)",
                          "#c62828", "Patches HD-Player.exe (+ HD-MultiInstanceManager.exe) "
                          "to disable the integrity shutdown so rooted instances boot. Do "
                          "this once, then Toggle Root per instance.", True),
            "partial": ("⚠ Engine partially patched — click to finish patching",
                        "#e65100", "Some engine binaries aren't patched yet — re-run the "
                        "patch to bring them all up to date.", True),
            "unknown": ("Engine status unknown (unrecognized build)",
                        "#616161", "Couldn't read the engine patch state for this build.",
                        False),
        }[state]
        self.engine_button.setText(text)
        self.engine_button.setToolTip(tip)
        self.engine_button.setStyleSheet(f"color: {color}; font-weight: bold;")
        # Remember the action for the click handler; disabled only on unknown
        # builds (busy-state disabling is handled by _set_busy during ops).
        self._engine_action = "restore" if state == "patched" else "patch"
        self.engine_button.setEnabled(enabled)

    def _engine_state(self) -> str:
        """One of 'patched' | 'unpatched' | 'partial' | 'unknown' across installs."""
        states = [integrity_patch.installation_patched(i["install_path"])
                  for i in self.installations
                  if i.get("patch_mode") and i.get("install_path")
                  and os.path.isdir(i["install_path"])]
        if states and all(s is True for s in states):
            return "patched"
        if states and all(s is False for s in states):
            return "unpatched"
        if any(s is True for s in states):
            return "partial"
        return "unknown"

    def handle_engine_button(self) -> None:
        """Patch or restore the engine, per the current (freshly-read) state."""
        # Re-read state at click time so a stale label can't send us the wrong way.
        self._refresh_patch_ui()
        if getattr(self, "_engine_action", "patch") == "restore":
            self.handle_restore_patches()
        else:
            self.handle_apply_patches()

    def update_instance_data(self) -> None:
        if not self.installations: return

        all_found_instances: dict[str, dict[str, Any]] = {}
        for inst in self.installations:
            source_id, config_path, data_path = inst["source"], inst["config_path"], inst["data_path"]
            install_path = inst.get("install_path")     # for locating HD-Adb.exe (sideload)
            patch_mode = inst.get("patch_mode", False)  # 5.22.150.1014+ uses the patches
            root_info = config_handler.get_complete_root_statuses(config_path)
            instance_root_statuses = root_info['instance_statuses']
            display_names = root_info.get('display_names', {})

            disk_instances = {entry for entry in (os.listdir(data_path) if os.path.isdir(data_path) else []) if os.path.isdir(os.path.join(data_path, entry))}
            all_instance_names = set(instance_root_statuses.keys()) | disk_instances

            for name in sorted(all_instance_names):
                unique_id = f"{name} ({source_id})"
                instance_dir_path = os.path.join(data_path, name)

                rw_mode = constants.MODE_UNKNOWN
                if os.path.isdir(instance_dir_path):
                    is_readonly = instance_handler.is_instance_readonly(instance_dir_path)
                    if is_readonly is True: rw_mode = constants.MODE_READONLY
                    elif is_readonly is False: rw_mode = constants.MODE_READWRITE

                individual_root_on = instance_root_statuses.get(name, False)
                display_name = display_names.get(name, name)

                if patch_mode:
                    # 5.22.150.1014+: app root = the guest su binary actually patched
                    # (tracked by the Data.vhdx sidecar). enable_root_access only makes
                    # /system/xbin/su appear; apps still need the su patched because
                    # they cannot reach /dev/bstvmsg for the dev-mode escape, so the
                    # sidecar -- not the conf flag -- is the real indicator.
                    effective_root_status = su_patch_offline.instance_root_state(instance_dir_path)
                else:
                    # Classic builds: the per-instance enable_root_access flag is the
                    # persistent root control (it exposes the guest `su`). Do NOT gate
                    # status on bst.feature.rooting -- BlueStacks resets that global flag
                    # to 0 on launch while root stays live, which would wrongly show a
                    # rooted instance as "Off". The toggle re-sets feature.rooting when
                    # enabling.
                    effective_root_status = individual_root_on

                all_found_instances[unique_id] = {
                    "original_name": name,
                    "config_path": config_path,
                    "data_path": instance_dir_path,
                    "install_path": install_path,
                    "rw_mode": rw_mode,
                    "root_enabled": effective_root_status,
                    "individual_root_status": individual_root_on,
                    "display_name": display_name,
                    "patch_mode": patch_mode,
                }

        self.instance_data = {
            uid: data for uid, data in all_found_instances.items()
            if data["rw_mode"] != constants.MODE_UNKNOWN
        }

        logger.debug(f"Instance data updated. Displaying {len(self.instance_data)} instances.")

    def _clear_instance_widgets(self):
        while self.instance_layout.count():
            item = self.instance_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def update_instance_checkboxes(self, preserve_selection: bool = True):
        previous_selection = {uid for uid, w in self.instance_checkboxes.items() if w["checkbox"].isChecked()} if preserve_selection else set()

        self._clear_instance_widgets()
        self.instance_checkboxes = {}

        for row, unique_id in enumerate(sorted(self.instance_data.keys())):
            data = self.instance_data[unique_id]
            checkbox = QCheckBox(unique_id)
            checkbox.setChecked(unique_id in previous_selection)

            root_text = "On" if data["root_enabled"] else "Off"
            Qlabel_root = QLabel(f"Root: {root_text}")
            if root_text == "On":
                Qlabel_root.setStyleSheet("""QLabel { background-color: green; color: white; padding: 2px;}""")
            else:
                Qlabel_root.setStyleSheet("""QLabel { padding: 2px;}""")
            rw_text = "On" if data["rw_mode"] == constants.MODE_READWRITE else "Off"

            self.instance_layout.addWidget(checkbox, row, 0)
            self.instance_layout.addWidget(QLabel(data["display_name"]), row, 1)
            self.instance_layout.addWidget(Qlabel_root, row, 2)
            self.instance_layout.addWidget(QLabel(f"R/W: {rw_text}"), row, 3)
            self.instance_checkboxes[unique_id] = {"checkbox": checkbox}

    def _toggle_single_instance_root(self, unique_id, progress=None):
        """Dispatch root toggle by build: 5.22.150.1014+ needs the su-binary patch
        AND enable_root_access; older builds just toggle the conf flag."""
        if self.instance_data[unique_id].get("patch_mode"):
            self._toggle_root_patchmode(unique_id, progress)
        else:
            self._toggle_root_conf(unique_id, progress)

    def _toggle_root_patchmode(self, unique_id, progress=None):
        """5.22.150.1014+ app root needs BOTH halves:
          1. enable_root_access=1, so BlueStacks exposes /system/xbin/su, and
          2. the guest su binary patched (isDeveloperMode->true) inside Data.vhdx.
        An app cannot reach /dev/bstvmsg, so the host-side dev-mode escape (the
        engine patch) only grants a root *shell* -- apps stay denied until the su
        binary itself is patched. The engine patch is still required (integrity
        bypass + keeping enable_root_access from being reset).

        su only exists in Data.vhdx after the instance has booted once with root
        enabled; if it isn't there yet, su_patch_offline reports that and you
        re-toggle after a single boot.
        """
        instance = self.instance_data[unique_id]
        turn_on = not instance["root_enabled"]
        config_path = instance["config_path"]
        key = f"{constants.INSTANCE_PREFIX}{instance['original_name']}{constants.ENABLE_ROOT_KEY}"
        if turn_on:
            if progress:
                progress("Part 1/2: enabling root access in bluestacks.conf...")
            config_handler.modify_config_file(config_path, key, "1")
            config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, "1")
            if progress:
                progress("Part 2/2: patching guest su in Data.vhdx...")
            results = su_patch_offline.set_instance_root(instance["data_path"], True, progress)
            # If no guest su was patched (sidecar not written), Android hasn't
            # generated su yet -- the instance must be booted once first. This is
            # easy to miss in the status bar, so tell the user with a dialog.
            if not su_patch_offline.instance_root_state(instance["data_path"]):
                self.show_notice.emit(
                    "Boot this instance once first",
                    "%s hasn't generated its root files yet, so there was nothing "
                    "to patch.\n\nStart this instance in BlueStacks, let it fully "
                    "reach the home screen, then close it completely and click "
                    "\"Toggle Root\" again." % unique_id,
                )
        else:
            if progress:
                progress("Part 1/2: restoring guest su in Data.vhdx...")
            results = su_patch_offline.set_instance_root(instance["data_path"], False, progress)
            if progress:
                progress("Part 2/2: disabling root access in bluestacks.conf...")
            config_handler.modify_config_file(config_path, key, "0")
        logger.info("Root %s (patch-mode) for %s: %s", "ON" if turn_on else "OFF",
                    unique_id, " | ".join(results))

    def _toggle_root_conf(self, unique_id, progress=None):
        """Root toggle via bluestacks.conf (enable_root_access + feature.rooting).

        Classic builds expose only /system/xbin/bstk/su (a root *shell*); apps
        cannot see it because it is not on PATH. So we also add a
        /system/xbin/su -> bstk/su symlink offline in Root.vhd for app-visible
        root. That step is best-effort: if it fails (tools missing, no Root.vhd,
        unexpected layout) the conf-based shell root still applies.
        """
        if progress:
            progress("updating bluestacks.conf...")
        instance = self.instance_data[unique_id]
        config_path, original_name = instance["config_path"], instance["original_name"]
        is_currently_on = instance["root_enabled"]
        setting_key = f"{constants.INSTANCE_PREFIX}{original_name}{constants.ENABLE_ROOT_KEY}"
        if is_currently_on:
            config_handler.modify_config_file(config_path, setting_key, "0")
            any_other_rooted = any(
                d.get("individual_root_status", False)
                for uid, d in self.instance_data.items()
                if uid != unique_id and d["config_path"] == config_path)
            if not any_other_rooted:
                config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, "0")
            self._set_classic_app_su(instance, False, progress)
        else:
            config_handler.modify_config_file(config_path, setting_key, "1")
            config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, "1")
            self._set_classic_app_su(instance, True, progress)
        logger.info(f"Root toggle (conf) processed for {unique_id}")

    def _set_classic_app_su(self, instance, turn_on, progress=None):
        """Best-effort /system/xbin/su symlink in Root.vhd for app-visible root.

        Only meaningful on classic builds whose Root.vhd ships bstk/su. Any
        failure is logged and surfaced via progress but never fails the toggle.
        """
        if not ext4_symlink.tools_available():
            logger.info("app-su: bundled e2fsprogs not present; skipping symlink")
            return
        try:
            if turn_on:
                results = ext4_symlink.add_su_symlink(instance["data_path"], progress)
            else:
                results = ext4_symlink.remove_su_symlink(instance["data_path"], progress)
            logger.info("app-su %s: %s", "ON" if turn_on else "OFF", " | ".join(results))
        except Exception as exc:  # noqa: BLE001 - never break the conf toggle
            logger.warning("app-su symlink step failed: %s", exc)
            if progress:
                progress("app-root symlink skipped: %s" % exc)

    def _toggle_single_instance_rw(self, unique_id, progress=None):
        instance = self.instance_data[unique_id]
        new_mode = constants.MODE_READONLY if instance["rw_mode"] == constants.MODE_READWRITE else constants.MODE_READWRITE
        if progress:
            progress("setting disk to %s..." % new_mode)
        instance_handler.modify_instance_files(instance["data_path"], new_mode)
        logger.info(f"R/W toggled for instance: {unique_id} to {new_mode}")

    def _perform_operation(self, operation_func, operation_name):
        selected_ids = [uid for uid, w in self.instance_checkboxes.items() if w["checkbox"].isChecked()]
        if not selected_ids:
            QMessageBox.information(self, "No Selection", f"No instances selected to toggle {operation_name}.")
            return
        total = len(selected_ids)

        def job(progress):
            progress("Closing BlueStacks...")
            logger.info("Terminating BlueStacks before %s of %d instance(s)", operation_name, total)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            for idx, uid in enumerate(selected_ids, 1):
                prefix = "Part %d/%d (%s)" % (idx, total, uid)
                logger.info("---- %s: %s ----", prefix, operation_name)
                progress("%s: %s..." % (prefix, operation_name))
                operation_func(uid, lambda m, _p=prefix: progress("%s: %s" % (_p, m)))
            return "%s complete for %d instance(s). Restart the instance(s)." % (operation_name, total)

        self._run_async(job, f"Toggling {operation_name}...")

    def handle_toggle_root(self): self._perform_operation(self._toggle_single_instance_root, "Root")
    def handle_toggle_rw(self): self._perform_operation(self._toggle_single_instance_rw, "R/W")

    def handle_sideload_module(self) -> None:
        """Push a chosen module .zip into one running instance and flash it.

        Unlike every other action here, this needs the instance RUNNING (its ADB
        port must be open). We target exactly one selected instance so the module
        installs into the right guest.
        """
        selected = [uid for uid, w in self.instance_checkboxes.items() if w["checkbox"].isChecked()]
        if len(selected) != 1:
            QMessageBox.information(
                self, "Select one instance",
                "Tick exactly one (running) instance to receive the module, then "
                "click Sideload again.")
            return
        uid = selected[0]
        instance = self.instance_data[uid]

        install_dirs = [i.get("install_path") for i in self.installations]
        adb_exe = adb_handler.find_adb(install_dirs)
        if not adb_exe:
            QMessageBox.warning(
                self, "ADB not found",
                "Couldn't find HD-Adb.exe in the BlueStacks install folder, so the "
                "module can't be pushed.")
            return

        zip_path, _ = QFileDialog.getOpenFileName(
            self, "Select Magisk/Kitsune module", "", "Module archives (*.zip)")
        if not zip_path:
            return

        port = adb_handler.instance_adb_port(instance["config_path"], instance["original_name"])

        def job(progress):
            msg = adb_handler.install_module(adb_exe, port, zip_path, progress=progress)
            self.show_notice.emit("Module installed", msg)
            return "Module installed. Close and reopen the instance to activate it."

        self._run_async(job, "Installing %s..." % os.path.basename(zip_path))

    # ---- Background-thread plumbing (keeps the UI responsive) -------------
    def _action_buttons(self):
        return [self.root_toggle_button, self.rw_toggle_button,
                self.engine_button, self.sideload_button]

    def _set_busy(self, busy):
        for b in self._action_buttons():
            b.setEnabled(not busy)
        if busy:
            self.status_refresh_timer.stop()

    def _run_async(self, job, start_text):
        """Run job(progress) on a worker thread; relay progress to the status bar."""
        if getattr(self, "_op_thread", None) is not None:
            QMessageBox.information(self, "Busy", "An operation is already running.")
            return
        self._set_busy(True)
        self.status_label.setText(start_text)
        logger.info("==== %s ====", start_text)
        self._op_thread = QThread(self)
        self._op_worker = _OpWorker(job)
        self._op_worker.moveToThread(self._op_thread)
        self._op_thread.started.connect(self._op_worker.run)
        self._op_worker.progress.connect(self._on_async_progress)
        self._op_worker.done.connect(self._on_async_done)
        self._op_worker.done.connect(self._op_thread.quit)
        self._op_thread.finished.connect(self._cleanup_async)
        self._op_thread.start()

    def _on_async_progress(self, msg):
        self.status_label.setText(msg)

    @pyqtSlot(str, str)
    def _show_notice(self, title, message):
        """Show a modal info dialog. Runs on the UI thread via a queued signal."""
        QMessageBox.information(self, title, message)

    def _on_async_done(self, ok, summary):
        self._set_busy(False)
        self.status_label.setText(summary if ok else f"Error: {summary}")
        logger.info("Operation finished (ok=%s): %s", ok, summary)
        self.update_instance_statuses(preserve_selection=True)
        self._refresh_patch_ui()  # reflect the new engine-patch state after a patch/restore
        self.status_refresh_timer.start(constants.REFRESH_INTERVAL_MS)

    def _cleanup_async(self):
        if getattr(self, "_op_worker", None) is not None:
            self._op_worker.deleteLater()
        if getattr(self, "_op_thread", None) is not None:
            self._op_thread.deleteLater()
        self._op_worker = None
        self._op_thread = None

    # ---- Engine patch (5.22.150.1014+) ------------------------------------
    def _install_dirs_or_warn(self) -> list[str] | None:
        """Return BlueStacks install dirs, after ensuring admin rights.

        Returns None (and shows the appropriate dialog) if not elevated or no
        install directory was found.
        """
        # Writing into Program Files needs admin. Offer to relaunch elevated.
        if not admin.is_admin():
            choice = QMessageBox.question(
                self, "Administrator required",
                "Patching the BlueStacks binaries requires administrator rights.\n\n"
                "Relaunch this app as administrator now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if choice == QMessageBox.Yes and admin.relaunch_as_admin():
                QApplication.quit()
            return None

        # Only patch 5.22.150.1014+ installs (older builds don't need it).
        install_dirs = sorted({inst.get("install_path") for inst in self.installations
                               if inst.get("patch_mode") and inst.get("install_path")
                               and os.path.isdir(inst["install_path"])})
        if not install_dirs:
            QMessageBox.warning(self, "Not applicable",
                                "No BlueStacks 5.22.150.1014+ install found that needs the "
                                "engine patch (older builds use classic conf rooting).")
            return None
        return install_dirs

    def handle_apply_patches(self) -> None:
        """One click: patch BlueStacks so apps get root and root stays on.

        * HD-Player.exe -> _isDiskVerificationRequired() returns 0, which both
          disables the "illegally tampered" shutdown AND turns on Developer Mode
          (so the guest `su` grants root to every app -- no /system edits needed).
        * HD-MultiInstanceManager.exe -> stop resetting enable_root_access to 0.
        """
        install_dirs = self._install_dirs_or_warn()
        if install_dirs is None:
            return

        confirm = QMessageBox.question(
            self, "Enable Root",
            "This patches your BlueStacks install to enable root:\n\n"
            "  - Unlocks root for apps (Developer Mode) and removes the\n"
            "    \"illegally tampered\" shutdown  [HD-Player.exe]\n"
            "  - Keeps root enabled across launches  [HD-MultiInstanceManager.exe]\n\n"
            "No guest /system changes are needed. A .prepatch.bak backup is made "
            "next to each binary (use \"Undo Root Patch\" to revert). All BlueStacks "
            "processes will be closed first.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        total = len(install_dirs)

        def job(progress):
            progress("Closing BlueStacks...")
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            all_results = []
            for i, install_dir in enumerate(install_dirs, 1):
                progress("Patching engine %d/%d: HD-Player.exe..." % (i, total))
                all_results.extend(integrity_patch.patch_installation(install_dir))
                progress("Patching engine %d/%d: HD-MultiInstanceManager.exe..." % (i, total))
                all_results.extend(root_persistence.patch_root_persistence(install_dir))
            for line in all_results:
                logger.info("  %s", line)
            logger.info("Engine patched. Next: Toggle Root per instance, then restart. "
                        "Disable BstHdUpdaterSvc so an update doesn't re-lock it.")
            return "Engine patched. Now Toggle Root per instance, then restart."

        self._run_async(job, "Patching BlueStacks engine...")

    def handle_restore_patches(self) -> None:
        """Restore HD-Player.exe + HD-MultiInstanceManager.exe from backups."""
        install_dirs = self._install_dirs_or_warn()
        if install_dirs is None:
            return
        if QMessageBox.question(
                self, "Undo Root Patch",
                "Restore the original BlueStacks binaries from their .prepatch.bak "
                "backups? All BlueStacks processes will be closed first.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return

        total = len(install_dirs)

        def job(progress):
            progress("Closing BlueStacks...")
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            all_results = []
            for i, install_dir in enumerate(install_dirs, 1):
                progress("Restoring engine %d/%d..." % (i, total))
                all_results.extend(integrity_patch.patch_installation(install_dir, restore=True))
                all_results.extend(root_persistence.patch_root_persistence(install_dir, restore=True))
            for line in all_results:
                logger.info("  %s", line)
            return "Engine binaries restored from backup."

        self._run_async(job, "Restoring BlueStacks engine...")
    def update_instance_statuses(self, preserve_selection: bool = True): self.update_instance_data(); self.update_instance_checkboxes(preserve_selection)
    def closeEvent(self, event): self.status_refresh_timer.stop(); event.accept()

if __name__ == "__main__":
    # Patching Program Files binaries and killing BlueStacks processes need
    # admin rights. If not elevated, request elevation via UAC and relaunch;
    # this process then exits and the elevated copy takes over.
    admin.ensure_admin()

    try:
        logger.info("Starting %s (admin=%s, log=%s)",
                    constants.APP_NAME, admin.is_admin(), LOG_PATH)
        app = QApplication(sys.argv)
        window = BluestacksRootToggle()
        window.show()
        sys.exit(app.exec_())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - capture any startup crash to the log
        logger.exception("Fatal error during startup")
        raise
