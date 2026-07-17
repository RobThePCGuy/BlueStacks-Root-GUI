# views/main_window.py
"""Main application window: nav rail + Dashboard/Instances/Modules pages."""
from __future__ import annotations

import os
import sys
import logging
from typing import Any

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QPushButton,
    QMessageBox, QFileDialog, QApplication,
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

from views.nav_rail import (
    NavRail, DASHBOARD as NAV_DASHBOARD, INSTANCES as NAV_INSTANCES,
    MODULES as NAV_MODULES,
)
from views.dashboard_page import DashboardPage
from views.instances_page import InstancesPage
from views.modules_page import ModulesPage
from views.progress import OperationProgressBar, step_percent
from views import theme
from views import engine_rules

logger = logging.getLogger(__name__)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class _OpWorker(QObject):
    """Runs a blocking job(progress) on a worker thread, relaying progress
    text and an optional percent complete (-1 for unknown)."""
    progress = pyqtSignal(str, int)
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


class _RunningScanWorker(QObject):
    """Probes which instances are reachable over ADB, on a worker thread.

    The probe shells out to adb once per instance (adb server start + a per-port
    ``connect`` that blocks until it succeeds or times out), which can take
    several seconds and must never run on the UI thread.
    """
    finished = pyqtSignal(list)  # sorted list of running unique_ids

    def __init__(self, adb_exe, instances):
        super().__init__()
        self._adb_exe = adb_exe
        self._instances = instances

    @pyqtSlot()
    def run(self):
        try:
            running = adb_handler.list_running_instances(self._adb_exe, self._instances)
            self.finished.emit(sorted(running.keys()))
        except Exception:  # noqa: BLE001 - a probe failure just means "none found"
            logger.exception("Running-instance ADB probe failed")
            self.finished.emit([])


class MainWindow(QWidget):
    """Main application window for toggling BlueStacks root and R/W settings."""

    show_notice = pyqtSignal(str, str)  # (title, message)

    def __init__(self):
        super().__init__()
        self.installations: list = []
        self.instance_data: dict[str, dict[str, Any]] = {}

        self.show_notice.connect(self._show_notice)
        self.setWindowTitle(f"{constants.APP_NAME} v{constants.APP_VERSION}")
        self._set_icon()
        self._last_engine_state = None
        # Background ADB probe for the Modules tab (see _refresh_running_instances).
        self._scan_thread = None
        self._scan_worker = None
        self._scan_pending = False
        self.status_refresh_timer = QTimer(self)
        self.status_refresh_timer.timeout.connect(self._on_status_timer)
        self.init_ui()
        QTimer.singleShot(0, self.initialize_paths_and_instances)

    def _set_icon(self):
        try:
            icon_path = resource_path(constants.ICON_FILENAME)
            app_icon = QIcon(icon_path)
            if not app_icon.isNull():
                self.setWindowIcon(app_icon)
        except Exception as e:
            logger.error(f"Error setting window icon: {e}")

    def init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.addStretch(1)
        self.theme_button = QPushButton("Toggle theme")
        self.theme_button.clicked.connect(self._handle_toggle_theme)
        toolbar.addWidget(self.theme_button)
        root_layout.addLayout(toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.nav_rail = NavRail()
        self.nav_rail.navigate.connect(self._handle_navigate)
        body.addWidget(self.nav_rail)

        self.pages = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.instances_page = InstancesPage()
        self.modules_page = ModulesPage()
        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.instances_page)
        self.pages.addWidget(self.modules_page)
        self._pages_by_key = {
            NAV_DASHBOARD: self.dashboard_page,
            NAV_INSTANCES: self.instances_page,
            NAV_MODULES: self.modules_page,
        }
        body.addWidget(self.pages, 1)

        root_layout.addLayout(body, 1)

        self.progress_bar = OperationProgressBar()
        root_layout.addWidget(self.progress_bar)

        self.dashboard_page.patch_engine_requested.connect(self.handle_engine_button)
        self.dashboard_page.repatch_requested.connect(self.handle_apply_patches)
        self.instances_page.toggle_root_requested.connect(self.handle_toggle_root)
        self.instances_page.toggle_rw_requested.connect(self.handle_toggle_rw)
        self.instances_page.go_to_dashboard_requested.connect(
            lambda: self.nav_rail.select(NAV_DASHBOARD))
        self.modules_page.browse_zip_requested.connect(self._handle_browse_zip)
        self.modules_page.push_requested.connect(self._handle_push_module)

        self.setMinimumWidth(700)
        self.setMinimumHeight(480)

    def _handle_navigate(self, key: str) -> None:
        self.pages.setCurrentWidget(self._pages_by_key[key])
        if key == NAV_MODULES:
            self._refresh_running_instances()

    def _handle_toggle_theme(self) -> None:
        current = theme.load_saved_theme()
        next_theme = theme.DARK if current == theme.LIGHT else theme.LIGHT
        theme.apply_theme(QApplication.instance(), next_theme)

    def initialize_paths_and_instances(self) -> None:
        logger.info("Initializing BlueStacks paths and instances...")
        self.installations = registry_handler.get_all_bluestacks_installations()
        if not self.installations:
            self.dashboard_page.set_paths_text("No BlueStacks installations found.")
            return

        path_details = ["Installations Found:"]
        for inst in self.installations:
            ver = ".".join(map(str, inst["version"])) if inst.get("version") else "?"
            path_details.append(f"  - {inst['source']} v{ver}: {inst['user_path']}")
        self.dashboard_page.set_paths_text("\n".join(path_details))

        # Populate instance_data BEFORE refreshing the patch UI: the Dashboard
        # "N / M instances rooted" stat is derived from instance_data, so
        # refreshing first would render "0 / 0" until the next timer tick.
        self.update_instance_statuses(preserve_selection=False)
        self._refresh_patch_ui()
        self.status_refresh_timer.start(constants.REFRESH_INTERVAL_MS)

    def _refresh_patch_ui(self, state: str | None = None) -> None:
        has_patch_build = any(i.get("patch_mode") for i in self.installations)
        if not has_patch_build:
            self.dashboard_page.set_engine_state(False, "", "", "#000000", False)
            self.instances_page.set_engine_locked_banner(False)
        else:
            if state is None:
                state = self._engine_state()
            text, color, tip, enabled = {
                "patched": ("Engine patched (click to Undo)",
                            "#2e7d32", "Restores HD-Player.exe and HD-MultiInstanceManager.exe "
                            "from the .prepatch.bak backups.", True),
                "unpatched": ("Patch BlueStacks Engine (required for root)",
                              "#c62828", "Patches HD-Player.exe (and HD-MultiInstanceManager.exe) "
                              "to disable the integrity shutdown so rooted instances boot. Do "
                              "this once, then Toggle Root per instance.", True),
                "partial": ("Engine partially patched (click to finish)",
                            "#e65100", "Some engine binaries aren't patched yet. Re-run the "
                            "patch to bring them all up to date.", True),
                "unknown": ("Engine status unknown (unrecognized build)",
                            "#616161", "Couldn't read the engine patch state for this build.",
                            False),
            }[state]
            self._engine_action = "restore" if state == "patched" else "patch"
            self.dashboard_page.set_engine_state(True, text, tip, color, enabled)
            # Only surface the "locked" banner for states we can act on from
            # the Dashboard (unpatched/partial). "unknown" leaves the engine
            # button disabled, so a banner pointing there would be a dead end.
            self.instances_page.set_engine_locked_banner(state in ("unpatched", "partial"))

        rooted = sum(1 for d in self.instance_data.values() if d.get("root_enabled"))
        self.dashboard_page.set_rooted_count(rooted, len(self.instance_data))

    def _engine_state(self) -> str:
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

    def _on_status_timer(self) -> None:
        self.update_instance_statuses(preserve_selection=True)
        # _engine_state() reads and byte-scans HD-Player.exe from disk; compute
        # it once per tick and share it with both consumers.
        state = self._engine_state()
        self._refresh_patch_ui(state)
        self._check_for_reverted_patch(state)

    def _check_for_reverted_patch(self, current_state: str | None = None) -> None:
        if current_state is None:
            current_state = self._engine_state()
        # Only patch-mode instances depend on the engine patch; a rooted classic
        # (MSI/conf) instance is unaffected by a revert, so don't let it trigger
        # a false "your engine patch was reverted" alert.
        any_rooted = any(d.get("root_enabled") for d in self.instance_data.values()
                         if d.get("patch_mode"))
        if engine_rules.update_was_reverted(self._last_engine_state, current_state, any_rooted):
            self.dashboard_page.set_update_reverted(True)
            logger.warning("Engine patch appears to have been reverted (was %s, now %s) "
                           "while a rooted instance exists.", self._last_engine_state, current_state)
        elif current_state == "patched":
            self.dashboard_page.set_update_reverted(False)
        self._last_engine_state = current_state

    def handle_engine_button(self) -> None:
        self._refresh_patch_ui()
        if getattr(self, "_engine_action", "patch") == "restore":
            self.handle_restore_patches()
        else:
            self.handle_apply_patches()

    def update_instance_data(self) -> None:
        if not self.installations:
            return

        all_found_instances: dict[str, dict[str, Any]] = {}
        for inst in self.installations:
            source_id, config_path, data_path = inst["source"], inst["config_path"], inst["data_path"]
            install_path = inst.get("install_path")
            patch_mode = inst.get("patch_mode", False)
            root_info = config_handler.get_complete_root_statuses(config_path)
            instance_root_statuses = root_info['instance_statuses']

            disk_instances = set()
            if os.path.isdir(data_path):
                try:
                    disk_instances = {
                        entry for entry in os.listdir(data_path)
                        if os.path.isdir(os.path.join(data_path, entry))
                    }
                except OSError:
                    # Runs on the status-refresh timer; a PermissionError here
                    # must not take down the refresh loop.
                    logger.warning("Could not list %s", data_path, exc_info=True)
            all_instance_names = set(instance_root_statuses.keys()) | disk_instances

            for name in sorted(all_instance_names):
                unique_id = f"{name} ({source_id})"
                instance_dir_path = os.path.join(data_path, name)

                rw_mode = constants.MODE_UNKNOWN
                if os.path.isdir(instance_dir_path):
                    is_readonly = instance_handler.is_instance_readonly(instance_dir_path)
                    if is_readonly is True:
                        rw_mode = constants.MODE_READONLY
                    elif is_readonly is False:
                        rw_mode = constants.MODE_READWRITE

                individual_root_on = instance_root_statuses.get(name, False)
                if patch_mode:
                    effective_root_status = su_patch_offline.instance_root_state(instance_dir_path)
                else:
                    effective_root_status = individual_root_on

                all_found_instances[unique_id] = {
                    "original_name": name,
                    "config_path": config_path,
                    "data_path": instance_dir_path,
                    "install_path": install_path,
                    "rw_mode": rw_mode,
                    "root_enabled": effective_root_status,
                    "individual_root_status": individual_root_on,
                    "patch_mode": patch_mode,
                }

        self.instance_data = {
            uid: data for uid, data in all_found_instances.items()
            if data["rw_mode"] != constants.MODE_UNKNOWN
        }

        logger.debug(f"Instance data updated. Displaying {len(self.instance_data)} instances.")

    def update_instance_checkboxes(self, preserve_selection: bool = True) -> None:
        self.instances_page.set_instances(self.instance_data, preserve_selection)

    def _toggle_single_instance_root(self, unique_id, progress=None):
        if self.instance_data[unique_id].get("patch_mode"):
            self._toggle_root_patchmode(unique_id, progress)
        else:
            self._toggle_root_conf(unique_id, progress)

    def _toggle_root_patchmode(self, unique_id, progress=None):
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
        if not ext4_symlink.tools_available():
            logger.info("app-su: bundled e2fsprogs not present; skipping symlink")
            return
        try:
            if turn_on:
                results = ext4_symlink.add_su_symlink(instance["data_path"], progress)
            else:
                results = ext4_symlink.remove_su_symlink(instance["data_path"], progress)
            logger.info("app-su %s: %s", "ON" if turn_on else "OFF", " | ".join(results))
        except Exception as exc:  # noqa: BLE001
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
        selected_ids = self.instances_page.selected_ids()
        if not selected_ids:
            QMessageBox.information(self, "No Selection", f"No instances selected to toggle {operation_name}.")
            return

        if operation_name == "Root":
            blocked = engine_rules.blocked_for_root_toggle(
                {uid: self.instance_data[uid] for uid in selected_ids},
                self._engine_state(),
            )
            if blocked:
                QMessageBox.warning(
                    self, "Patch the engine first",
                    "%s need%s the engine patched before root will work.\n\n"
                    "Patch it from the Dashboard, then try again."
                    % (", ".join(blocked), "" if len(blocked) > 1 else "s"))
                return

        total = len(selected_ids)

        def job(progress):
            progress("Closing BlueStacks...", 0)
            logger.info("Terminating BlueStacks before %s of %d instance(s)", operation_name, total)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            for idx, uid in enumerate(selected_ids, 1):
                prefix = "Part %d/%d (%s)" % (idx, total, uid)
                logger.info("---- %s: %s ----", prefix, operation_name)
                pct = step_percent(idx - 1, total)
                progress("%s: %s..." % (prefix, operation_name), pct)
                operation_func(uid, lambda m, _p=prefix, _pct=pct: progress("%s: %s" % (_p, m), _pct))
            return ("%s complete for %d instance(s). They're now closed. Start "
                    "them from BlueStacks to use the change." % (operation_name, total))

        self._run_async(job, f"Toggling {operation_name}...")

    def handle_toggle_root(self):
        self._perform_operation(self._toggle_single_instance_root, "Root")

    def handle_toggle_rw(self):
        self._perform_operation(self._toggle_single_instance_rw, "R/W")

    def _refresh_running_instances(self) -> None:
        """Populate the Modules tab's running-instance list.

        The ADB probe is slow (seconds), so it runs on a worker thread and the
        list is filled in when it returns -- switching to the Modules tab stays
        instant. Only one probe runs at a time; a request that arrives while one
        is in flight is coalesced and re-run once it finishes.
        """
        install_dirs = [i.get("install_path") for i in self.installations]
        adb_exe = adb_handler.find_adb(install_dirs)
        if not adb_exe:
            self.modules_page.set_running_instances([])
            return
        if self._scan_thread is not None:
            self._scan_pending = True
            return
        instances = [
            (uid, data["config_path"], data["original_name"])
            for uid, data in self.instance_data.items()
        ]
        self._scan_pending = False
        self.modules_page.set_scanning()
        self._scan_thread = QThread(self)
        self._scan_worker = _RunningScanWorker(adb_exe, instances)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        # Delete the worker from inside its own still-running event loop; a
        # deleteLater() issued after the thread has stopped never gets processed.
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._cleanup_scan)
        self._scan_thread.start()

    def _on_scan_finished(self, running_ids: list) -> None:
        self.modules_page.set_running_instances(running_ids)

    def _cleanup_scan(self) -> None:
        # The worker deletes itself via its finished -> deleteLater connection.
        if self._scan_thread is not None:
            self._scan_thread.deleteLater()
        self._scan_worker = None
        self._scan_thread = None
        # A refresh was requested while the probe was running (e.g. instance data
        # changed after an operation). Re-run it now against the current data.
        if self._scan_pending:
            self._refresh_running_instances()

    def _handle_browse_zip(self) -> None:
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "Select Magisk/Kitsune module", "", "Module archives (*.zip)")
        if zip_path:
            self.modules_page.set_zip_path(zip_path)

    def _handle_push_module(self) -> None:
        uid = self.modules_page.selected_instance_id()
        zip_path = self.modules_page.zip_path()
        if not uid or not zip_path:
            return
        instance = self.instance_data[uid]
        install_dirs = [i.get("install_path") for i in self.installations]
        adb_exe = adb_handler.find_adb(install_dirs)
        if not adb_exe:
            QMessageBox.warning(
                self, "ADB not found",
                "Couldn't find HD-Adb.exe in the BlueStacks install folder, so the "
                "module can't be pushed.")
            return
        port = adb_handler.instance_adb_port(instance["config_path"], instance["original_name"])

        def job(progress):
            def adb_progress(msg):
                progress(msg, -1)
            msg = adb_handler.install_module(adb_exe, port, zip_path, progress=adb_progress)
            self.show_notice.emit("Module installed", msg)
            return "Module installed. Close and reopen the instance to activate it."

        self._run_async(job, "Installing %s..." % os.path.basename(zip_path))

    def _action_buttons(self):
        return [self.instances_page.root_toggle_button, self.instances_page.rw_toggle_button,
                self.dashboard_page.engine_button, self.modules_page.push_button]

    def _set_busy(self, busy):
        for b in self._action_buttons():
            b.setEnabled(not busy)
        # The Modules push button re-derives its own enabled state on every
        # radio/zip change, so it needs the busy flag explicitly or it would
        # re-enable itself mid-operation.
        self.modules_page.set_busy(busy)
        if busy:
            self.status_refresh_timer.stop()

    def _run_async(self, job, start_text):
        if getattr(self, "_op_thread", None) is not None:
            QMessageBox.information(self, "Busy", "An operation is already running.")
            return
        self._set_busy(True)
        self.progress_bar.start(start_text)
        logger.info("==== %s ====", start_text)
        self._op_thread = QThread(self)
        self._op_worker = _OpWorker(job)
        self._op_worker.moveToThread(self._op_thread)
        self._op_thread.started.connect(self._op_worker.run)
        self._op_worker.progress.connect(self._on_async_progress)
        self._op_worker.done.connect(self._on_async_done)
        self._op_worker.done.connect(self._op_thread.quit)
        # Delete the worker from inside its own still-running event loop (see
        # _refresh_running_instances for why a post-stop deleteLater leaks).
        self._op_worker.done.connect(self._op_worker.deleteLater)
        self._op_thread.finished.connect(self._cleanup_async)
        self._op_thread.start()

    def _on_async_progress(self, msg, pct):
        self.progress_bar.set_progress(msg, None if pct < 0 else pct)

    @pyqtSlot(str, str)
    def _show_notice(self, title, message):
        QMessageBox.information(self, title, message)

    def _confirm(self, title: str, text: str, informative_html: str) -> bool:
        """A Yes/No confirmation, defaulting to No.

        ``informative_html`` is rendered as rich text so bullet lists and
        emphasis lay out consistently -- plain-text messages with hand-drawn
        indentation render ragged in a proportional font.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setTextFormat(Qt.RichText)
        box.setInformativeText(informative_html)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec_() == QMessageBox.Yes

    def _on_async_done(self, ok, summary):
        self._set_busy(False)
        self.progress_bar.finish(summary if ok else f"Error: {summary}")
        logger.info("Operation finished (ok=%s): %s", ok, summary)
        self.update_instance_statuses(preserve_selection=True)
        state = self._engine_state()
        self._refresh_patch_ui(state)
        # A successful (re)patch clears any standing "reverted" alert right away
        # instead of waiting for the next timer tick. We only ever CLEAR here:
        # a user-initiated Undo (state now unpatched) must not re-raise the
        # alert, and resyncing _last_engine_state keeps the next tick from
        # misreading that deliberate change as an auto-revert.
        if state == "patched":
            self.dashboard_page.set_update_reverted(False)
        self._last_engine_state = state
        if self.nav_rail.current() == NAV_MODULES:
            self._refresh_running_instances()
        self.status_refresh_timer.start(constants.REFRESH_INTERVAL_MS)

    def _cleanup_async(self):
        # The worker deletes itself via its done -> deleteLater connection.
        if getattr(self, "_op_thread", None) is not None:
            self._op_thread.deleteLater()
        self._op_worker = None
        self._op_thread = None

    def _install_dirs_or_warn(self):
        if not admin.is_admin():
            choice = QMessageBox.question(
                self, "Administrator required",
                "Patching the BlueStacks binaries requires administrator rights.\n\n"
                "Relaunch this app as administrator now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if choice == QMessageBox.Yes and admin.relaunch_as_admin():
                QApplication.quit()
            return None

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
        install_dirs = self._install_dirs_or_warn()
        if install_dirs is None:
            return

        if not self._confirm(
                "Enable Root",
                "Patch the BlueStacks engine to enable root?",
                "<p>This modifies two BlueStacks program files:</p>"
                "<ul>"
                "<li>Unlocks root for apps and removes the \"illegally tampered\" "
                "shutdown (HD-Player.exe)</li>"
                "<li>Keeps root enabled across launches "
                "(HD-MultiInstanceManager.exe)</li>"
                "</ul>"
                "<p>A backup is saved automatically, so you can undo this at any "
                "time. All BlueStacks processes will be closed first.</p>"):
            return

        total = len(install_dirs)

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            all_results = []
            for i, install_dir in enumerate(install_dirs, 1):
                pct = step_percent(i - 1, total)
                progress("Patching engine %d/%d: HD-Player.exe..." % (i, total), pct)
                all_results.extend(integrity_patch.patch_installation(install_dir))
                progress("Patching engine %d/%d: HD-MultiInstanceManager.exe..." % (i, total), pct)
                all_results.extend(root_persistence.patch_root_persistence(install_dir))
            for line in all_results:
                logger.info("  %s", line)
            logger.info("Engine patched. Next: Toggle Root per instance, then start "
                        "BlueStacks. Disable BstHdUpdaterSvc so an update doesn't "
                        "re-lock it.")
            return "Engine patched. Now Toggle Root per instance, then start BlueStacks."

        self._run_async(job, "Patching BlueStacks engine...")

    def handle_restore_patches(self) -> None:
        install_dirs = self._install_dirs_or_warn()
        if install_dirs is None:
            return
        if not self._confirm(
                "Undo Root Patch",
                "Restore the original BlueStacks binaries?",
                "<p>This restores <b>HD-Player.exe</b> and "
                "<b>HD-MultiInstanceManager.exe</b> from their <b>.prepatch.bak</b> "
                "backups, undoing the root patch.</p>"
                "<p>All BlueStacks processes will be closed first.</p>"):
            return

        total = len(install_dirs)

        def job(progress):
            progress("Closing BlueStacks...", 0)
            instance_handler.terminate_bluestacks()
            QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
            all_results = []
            for i, install_dir in enumerate(install_dirs, 1):
                progress("Restoring engine %d/%d..." % (i, total), step_percent(i - 1, total))
                all_results.extend(integrity_patch.patch_installation(install_dir, restore=True))
                all_results.extend(root_persistence.patch_root_persistence(install_dir, restore=True))
            for line in all_results:
                logger.info("  %s", line)
            return "Engine binaries restored from backup."

        self._run_async(job, "Restoring BlueStacks engine...")

    def update_instance_statuses(self, preserve_selection: bool = True):
        self.update_instance_data()
        self.update_instance_checkboxes(preserve_selection)

    def closeEvent(self, event):
        # A background engine/root operation writes real binaries and disk
        # images; tearing the app down mid-write can crash on exit or corrupt
        # those files. Refuse to close until it finishes rather than killing it.
        if getattr(self, "_op_thread", None) is not None:
            QMessageBox.warning(
                self, "Operation in progress",
                "A background operation is still running. Please wait for it to "
                "finish before closing.")
            event.ignore()
            return
        self.status_refresh_timer.stop()
        # Don't let a running ADB probe outlive the window (QThread would warn
        # "destroyed while still running"). It's bounded by adb's own timeout.
        self._scan_pending = False
        if self._scan_thread is not None:
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
        event.accept()
