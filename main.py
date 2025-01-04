import sys
import os
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QLabel,
                             QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox, QLineEdit)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
import registry_handler
import config_handler
import instance_handler

# --- Constants ---
BLUESTACKS_CONF_FILENAME = "bluestacks.conf"
INSTANCE_PREFIX = "bst.instance."
ENABLE_ROOT_KEY = ".enable_root_access"
FEATURE_ROOTING_KEY = "bst.feature.rooting"
FASTBOOT_VDI = "fastboot.vdi"
ROOT_VHD = "Root.vhd"
REFRESH_INTERVAL_MS = 5000  # 5 seconds


class BluestacksRootToggle(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BlueStacks Root GUI")
        self.setWindowIcon(QIcon("main.ico"))
        self.bluestacks_path = None
        self.config_path = None
        self.instance_data = {}  # Store instance data
        self.init_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_instance_statuses)
        self.timer.start(REFRESH_INTERVAL_MS)

    def init_ui(self):
        # --- Main Layout ---
        main_layout = QVBoxLayout()

        # --- BlueStacks Path ---
        self.path_label = QLabel("BlueStacks Path: Loading...")
        main_layout.addWidget(self.path_label)

        # --- Instance Selection ---
        instance_group = QGroupBox("Instances")
        instance_layout = QVBoxLayout()
        instance_layout.setObjectName("instance_layout")
        self.instance_checkboxes = {}
        instance_group.setLayout(instance_layout)
        main_layout.addWidget(instance_group)

        # --- Toggle Buttons ---
        buttons_layout = QHBoxLayout()

        root_toggle_button = QPushButton("Toggle Root")
        root_toggle_button.clicked.connect(self.toggle_root)
        buttons_layout.addWidget(root_toggle_button)

        rw_toggle_button = QPushButton("Toggle R/W")
        rw_toggle_button.clicked.connect(self.toggle_rw)
        buttons_layout.addWidget(rw_toggle_button)

        main_layout.addLayout(buttons_layout)

        # --- Status Label ---
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

        # --- Initial Path and Status ---
        self.initialize_paths_and_instances()

    def initialize_paths_and_instances(self):
        """Initializes paths and detects instances."""
        user_defined_dir = registry_handler.get_bluestacks_path("UserDefinedDir")
        if user_defined_dir:
            self.config_path = os.path.join(user_defined_dir, BLUESTACKS_CONF_FILENAME)
        else:
            self.path_label.setText("BlueStacks Path: Not Found")
            self.status_label.setText("Error: Could not find BlueStacks installation.")
            return

        self.bluestacks_path = registry_handler.get_bluestacks_path("DataDir")
        if self.bluestacks_path:
            self.path_label.setText(f"BlueStacks Path: {self.bluestacks_path}")
            self.update_instance_data()
            self.update_instance_checkboxes()
            self.update_instance_statuses()
        else:
            self.path_label.setText("BlueStacks Path: Not Found")
            self.status_label.setText("Error: Could not find BlueStacks installation.")

    def update_instance_data(self):
        """Reads instance data from the config file."""
        if not self.config_path:
            return

        try:
            new_instance_data = {}
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith(INSTANCE_PREFIX) and ENABLE_ROOT_KEY in line:
                        instance_name = line.split(".")[2]
                        instance_path = os.path.join(self.bluestacks_path, instance_name)
                        new_instance_data[instance_name] = {
                            "root_enabled": config_handler.is_root_enabled(self.config_path, instance_name),
                            "rw_mode": "Normal" if not instance_handler.is_instance_readonly(instance_path) else "Readonly"
                        }
            self.instance_data = new_instance_data
        except Exception as e:
            self.status_label.setText(f"Error reading config file: {e}")

    def detect_instances(self, layout):
        """Adds/updates checkboxes based on self.instance_data."""
        if not self.instance_data:
            return

        for instance_name, data in self.instance_data.items():
            if instance_name not in self.instance_checkboxes:
                # Create UI elements for new instances
                hbox = QHBoxLayout()
                checkbox = QCheckBox(instance_name)
                root_status = QLineEdit(f"Root: {'On' if data['root_enabled'] else 'Off'}")
                root_status.setReadOnly(True)
                rw_status = QLineEdit(f"R/W: {'On' if data['rw_mode'] == 'Normal' else 'Off'}")
                rw_status.setReadOnly(True)
                hbox.addWidget(checkbox)
                hbox.addWidget(root_status)
                hbox.addWidget(rw_status)
                layout.addLayout(hbox)
                self.instance_checkboxes[instance_name] = {
                    "checkbox": checkbox,
                    "root_status": root_status,
                    "rw_status": rw_status,
                }
            else:
                # Update status of existing instances
                self.instance_checkboxes[instance_name]["root_status"].setText(
                    f"Root: {'On' if data['root_enabled'] else 'Off'}")
                self.instance_checkboxes[instance_name]["rw_status"].setText(
                    f"R/W: {'On' if data['rw_mode'] == 'Normal' else 'Off'}")

        # Remove checkboxes for instances that no longer exist
        instances_to_remove = set(self.instance_checkboxes.keys()) - set(self.instance_data.keys())
        for instance_name in instances_to_remove:
            widgets = self.instance_checkboxes.pop(instance_name)
            layout.removeWidget(widgets["checkbox"].parentWidget())  # Remove the hbox
            widgets["checkbox"].deleteLater()
            widgets["root_status"].deleteLater()
            widgets["rw_status"].deleteLater()
    
    def update_instance_checkboxes(self):
        """Updates the instance checkboxes based on the config file."""
        instance_layout = self.findChild(QVBoxLayout, "instance_layout")
        if instance_layout is None:
            # If not found, create one.
            instance_group = QGroupBox("Instances")
            instance_layout = QVBoxLayout()
            instance_layout.setObjectName("instance_layout")
            instance_group.setLayout(instance_layout)
            # Find the index for the "Instances" group box
            main_layout = self.layout()
            for i in range(main_layout.count()):
                item = main_layout.itemAt(i)
                if isinstance(item.widget(), QGroupBox) and item.widget().title() == "Instances":
                    # Insert the new instance_group right after the "Instances" group box
                    main_layout.insertWidget(i + 1, instance_group)
                    break

        # Detect instances and add new checkboxes
        self.detect_instances(instance_layout)

    def toggle_root(self):
        """Toggles root access for selected instances."""
        if not self.config_path:
            self.status_label.setText("Error: bluestacks.conf path not found.")
            return

        for instance_name, widgets in self.instance_checkboxes.items():
            checkbox = widgets["checkbox"]

            if checkbox.isChecked():
                try:
                    current_state = self.instance_data[instance_name]["root_enabled"]
                    new_state = "0" if current_state else "1"

                    config_handler.modify_config_file(self.config_path,
                                                    f"{INSTANCE_PREFIX}{instance_name}{ENABLE_ROOT_KEY}",
                                                    new_state)
                    config_handler.modify_config_file(self.config_path, FEATURE_ROOTING_KEY, new_state)

                    # Update the instance data and UI
                    self.instance_data[instance_name]["root_enabled"] = not current_state
                    widgets["root_status"].setText(
                        f"Root: {'On' if self.instance_data[instance_name]['root_enabled'] else 'Off'}")
                    self.status_label.setText(f"Root toggled for {instance_name}")

                except Exception as e:
                    self.status_label.setText(f"Error toggling root for {instance_name}: {e}")

    def toggle_rw(self):
        """Toggles R/W mode for selected instances, modifying both .bstk.in and .bstk files."""
        if not self.bluestacks_path:
            self.status_label.setText("Error: BlueStacks path not found.")
            return

        for instance_name, widgets in self.instance_checkboxes.items():
            checkbox = widgets["checkbox"]

            if checkbox.isChecked():
                try:
                    instance_path = os.path.join(self.bluestacks_path, instance_name)
                    current_state = self.instance_data[instance_name]["rw_mode"]
                    new_state = "Normal" if current_state == "Readonly" else "Readonly"

                    # Use the modify_instance_files from instance_handler
                    instance_handler.modify_instance_files(instance_path, [FASTBOOT_VDI, ROOT_VHD], new_state)

                    # Update the instance data and UI
                    self.instance_data[instance_name]["rw_mode"] = new_state
                    widgets["rw_status"].setText(f"R/W: {'On' if new_state == 'Normal' else 'Off'}")
                    self.status_label.setText(f"R/W toggled for {instance_name}")

                except Exception as e:
                    self.status_label.setText(f"Error toggling R/W for {instance_name}: {e}")
                    
    def update_instance_statuses(self):
        """Updates the status indicators for all instances."""
        self.update_instance_data()  # Refresh data before updating UI
        for instance_name, widgets in self.instance_checkboxes.items():
            try:
                widgets["root_status"].setText(
                    f"Root: {'On' if self.instance_data[instance_name]['root_enabled'] else 'Off'}")
                widgets["rw_status"].setText(
                    f"R/W: {'On' if self.instance_data[instance_name]['rw_mode'] == 'Normal' else 'Off'}")
            except Exception as e:
                self.status_label.setText(f"Error updating status for {instance_name}: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BluestacksRootToggle()
    window.show()
    sys.exit(app.exec_())