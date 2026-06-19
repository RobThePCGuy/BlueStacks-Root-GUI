"""Qt5-based GUI application for toggling BlueStacks root access."""
import sys
import os
import logging
import tempfile
from typing import Dict, Any, Optional, List

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
)
from PyQt5.QtCore import Qt, QTimer, QThread
from PyQt5.QtGui import QIcon


import constants
import registry_handler
import config_handler
import instance_handler
import root_persistence
import integrity_patch
import su_patch_offline
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


class BluestacksRootToggle(QWidget):
    """Main application window for toggling BlueStacks root and R/W settings."""

    def __init__(self):
        super().__init__()
        self.installations: List[registry_handler.Installation] = []
        self.instance_data: Dict[str, Dict[str, Any]] = {}
        self.instance_checkboxes: Dict[str, Dict[str, Any]] = {}
        self.is_toggling: bool = False
        
        self.setWindowTitle(constants.APP_NAME)
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
        self.instance_layout.setColumnStretch(0, 4)
        self.instance_layout.setColumnStretch(1, 1)
        self.instance_layout.setColumnStretch(2, 1)
        self.instance_layout.setHorizontalSpacing(15)
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
        # Patches HD-Player.exe so _isDiskVerificationRequired() returns 0 --
        # disabling the "illegally tampered" disk-integrity shutdown so a
        # su-modified /system can boot. Required once before per-instance root
        # works on these builds. Hidden on older builds (classic conf rooting).
        self.patch_button = QPushButton("Patch BlueStacks Engine (required for root)")
        self.patch_button.setToolTip(
            "Patches HD-Player.exe (+ HD-MultiInstanceManager.exe) to disable the "
            "integrity shutdown so rooted instances boot. Do this once, then use "
            "Toggle Root per instance. Only for BlueStacks 5.22.150.1014+."
        )
        self.patch_button.clicked.connect(self.handle_apply_patches)
        main_layout.addWidget(self.patch_button)

        self.restore_button = QPushButton("Undo Engine Patch (restore originals)")
        self.restore_button.setToolTip(
            "Restores HD-Player.exe + HD-MultiInstanceManager.exe from the "
            ".prepatch.bak backups."
        )
        self.restore_button.clicked.connect(self.handle_restore_patches)
        main_layout.addWidget(self.restore_button)
        # Visibility is decided once installations are read (see _refresh_patch_ui).
        self.patch_button.setVisible(False)
        self.restore_button.setVisible(False)

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
        """Show the engine-patch buttons only when a 5.22.150.1014+ install exists."""
        has_patch_build = any(i.get("patch_mode") for i in self.installations)
        self.patch_button.setVisible(has_patch_build)
        self.restore_button.setVisible(has_patch_build)

    def update_instance_data(self) -> None:
        if not self.installations: return
        
        all_found_instances: Dict[str, Dict[str, Any]] = {}
        for inst in self.installations:
            source_id, config_path, data_path = inst["source"], inst["config_path"], inst["data_path"]
            patch_mode = inst.get("patch_mode", False)  # 5.22.150.1014+ uses the patches
            root_info = config_handler.get_complete_root_statuses(config_path)
            global_root_on = root_info['global_status']
            instance_root_statuses = root_info['instance_statuses']
            
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
                if patch_mode:
                    # 5.22.150.1014+: root status = the real guest-su patch state
                    # (sidecar), immune to BlueStacks flipping enable_root_access.
                    effective_root_status = su_patch_offline.instance_root_state(instance_dir_path)
                else:
                    # Older builds: classic conf-based rooting.
                    effective_root_status = global_root_on and individual_root_on

                all_found_instances[unique_id] = {
                    "original_name": name,
                    "config_path": config_path,
                    "data_path": instance_dir_path,
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
            rw_text = "On" if data["rw_mode"] == constants.MODE_READWRITE else "Off"
            
            self.instance_layout.addWidget(checkbox, row, 0)
            self.instance_layout.addWidget(QLabel(f"Root: {root_text}"), row, 1)
            self.instance_layout.addWidget(QLabel(f"R/W: {rw_text}"), row, 2)
            self.instance_checkboxes[unique_id] = {"checkbox": checkbox}

    def _toggle_single_instance_root(self, unique_id: str):
        """Dispatch root toggle by build: su-patch (5.22.150.1014+) or conf (older)."""
        if self.instance_data[unique_id].get("patch_mode"):
            self._toggle_root_supatch(unique_id)
        else:
            self._toggle_root_conf(unique_id)

    def _toggle_root_supatch(self, unique_id: str):
        """5.22.150.1014+: root/un-root by patching the guest su offline.

        Root ON extracts the gated su from Root.vhd, backs up the original bytes
        to a sidecar, patches isDeveloperMode->true and writes it back. Root OFF
        restores the original su from the backup. Instance must be stopped first
        (the caller terminates BlueStacks). Independent of enable_root_access, so
        BlueStacks can't flip it off on launch.
        """
        instance = self.instance_data[unique_id]
        turn_on = not instance["root_enabled"]
        results = su_patch_offline.set_instance_root(instance["data_path"], turn_on)
        logger.info("Root %s (su-patch) for %s: %s", "ON" if turn_on else "OFF",
                    unique_id, " | ".join(results))

    def _toggle_root_conf(self, unique_id: str):
        """Older builds (< 5.22.150.1014): classic conf-based rooting."""
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
        else:
            config_handler.modify_config_file(config_path, setting_key, "1")
            config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, "1")
        logger.info(f"Root toggle (conf) processed for {unique_id}")

    def _toggle_single_instance_rw(self, unique_id: str):
        instance = self.instance_data[unique_id]
        new_mode = constants.MODE_READONLY if instance["rw_mode"] == constants.MODE_READWRITE else constants.MODE_READWRITE
        instance_handler.modify_instance_files(instance["data_path"], new_mode)
        logger.info(f"R/W toggled for instance: {unique_id} to {new_mode}")

    def _perform_operation(self, operation_func, operation_name):
        selected_ids = [uid for uid, w in self.instance_checkboxes.items() if w["checkbox"].isChecked()]
        if not selected_ids:
            QMessageBox.information(self, "No Selection", f"No instances selected to toggle {operation_name}.")
            return

        # Simplified operation handling for clarity
        self.status_label.setText(f"Toggling {operation_name}...")
        QApplication.processEvents()
        
        # We should kill bluestacks before making changes
        instance_handler.terminate_bluestacks()
        QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)

        for uid in selected_ids:
            try:
                operation_func(uid)
            except Exception as e:
                logger.error(f"Error toggling {operation_name} for {uid}: {e}")
                self.status_label.setText(f"Error for {uid}")
                break
        else:
             self.status_label.setText("Operation completed.")

        # Refresh the UI with the new state
        self.update_instance_statuses(preserve_selection=True)

    def handle_toggle_root(self): self._perform_operation(self._toggle_single_instance_root, "Root")
    def handle_toggle_rw(self): self._perform_operation(self._toggle_single_instance_rw, "R/W")

    # ---- Engine patch (5.22.150.1014+) ------------------------------------
    def _install_dirs_or_warn(self) -> Optional[List[str]]:
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

        instance_handler.terminate_bluestacks()
        QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)

        all_results: List[str] = []
        for install_dir in install_dirs:
            try:
                all_results.extend(integrity_patch.patch_installation(install_dir))
                all_results.extend(root_persistence.patch_root_persistence(install_dir))
            except Exception as e:
                logger.exception("Root patch failed")
                all_results.append(f"{install_dir}: ERROR - {e}")

        self.status_label.setText("Root patch applied - restart your instance.")
        QMessageBox.information(
            self, "Root Enabled",
            "\n".join(all_results) +
            "\n\nNext steps:\n"
            "  1. Make sure Root is ON (Toggle Root) for the instance — that's\n"
            "     what installs su in the guest.\n"
            "  2. Start/restart the instance — apps can now request root.\n\n"
            "Note: a BlueStacks auto-update will replace these files and re-lock "
            "root; disable the BlueStacks Updater Service to keep it.")

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

        instance_handler.terminate_bluestacks()
        QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)

        all_results: List[str] = []
        for install_dir in install_dirs:
            try:
                all_results.extend(integrity_patch.patch_installation(install_dir, restore=True))
                all_results.extend(root_persistence.patch_root_persistence(install_dir, restore=True))
            except Exception as e:
                logger.exception("Restore failed")
                all_results.append(f"{install_dir}: ERROR - {e}")

        self.status_label.setText("Originals restored.")
        QMessageBox.information(self, "Restored", "\n".join(all_results))
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