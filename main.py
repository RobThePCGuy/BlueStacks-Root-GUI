"""Qt5-based GUI application for toggling BlueStacks root access."""
import sys
import os
import logging
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
    QComboBox,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSpacerItem,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QIcon


import constants
import registry_handler
import config_handler
import instance_handler

# NOTE: For brevity, logging setup and helper classes are omitted but are unchanged.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
            path_details.append(f"  - {inst['source']}: {inst['user_path']}")
        self.path_label.setText("\n".join(path_details))

        self.update_instance_statuses(preserve_selection=False)
        self.status_refresh_timer.start(constants.REFRESH_INTERVAL_MS)

    def update_instance_data(self) -> None:
        if not self.installations: return
        
        all_found_instances: Dict[str, Dict[str, Any]] = {}
        for inst in self.installations:
            source_id, config_path, data_path = inst["source"], inst["config_path"], inst["data_path"]
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

                # Get the individual (local) root status for this instance
                individual_root_on = instance_root_statuses.get(name, False)
                # The effective (displayed) root status depends on both global and local keys
                effective_root_status = global_root_on and individual_root_on
                
                all_found_instances[unique_id] = {
                    "original_name": name,
                    "config_path": config_path,
                    "data_path": instance_dir_path,
                    "rw_mode": rw_mode,
                    "root_enabled": effective_root_status,  # This is the combined status for the UI
                    "individual_root_status": individual_root_on,  # FIX: Store the local status for logic
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
        instance = self.instance_data[unique_id]
        config_path, original_name = instance["config_path"], instance["original_name"]
        is_currently_on = instance["root_enabled"]
        setting_key = f"{constants.INSTANCE_PREFIX}{original_name}{constants.ENABLE_ROOT_KEY}"

        if is_currently_on:
            # --- INTELLIGENTLY TURNING OFF ---
            # 1. Always turn off the local key for this specific instance.
            config_handler.modify_config_file(config_path, setting_key, "0")

            # 2. Check if any *other* instances in the same installation are still rooted.
            # We must re-check the live instance data, not just our current state.
            any_other_instance_rooted = False
            for uid, data in self.instance_data.items():
                if uid == unique_id: continue # Skip the instance we are turning off right now
                if data['config_path'] == config_path:
                    # Check the instance's individual status, not the one we just changed.
                    if data.get('individual_root_status', False):
                        any_other_instance_rooted = True
                        break
            
            # 3. Only turn off the global key if no other instances need it.
            if not any_other_instance_rooted:
                logger.info(f"Last rooted instance for {config_path} disabled. Turning off global rooting feature.")
                config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, "0")
            else:
                logger.info(f"Other instances are still rooted for {config_path}. Global rooting feature remains enabled.")

        else:
            # --- TURNING ON ---
            # Simply enable both the local and global keys.
            config_handler.modify_config_file(config_path, setting_key, "1")
            config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, "1")

        logger.info(f"Root toggle request processed for instance: {unique_id}")

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
    def update_instance_statuses(self, preserve_selection: bool = True): self.update_instance_data(); self.update_instance_checkboxes(preserve_selection)
    def closeEvent(self, event): self.status_refresh_timer.stop(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BluestacksRootToggle()
    window.show()
    sys.exit(app.exec_())