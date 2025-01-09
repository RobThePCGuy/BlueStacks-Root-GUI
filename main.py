import sys
import os
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QGroupBox, QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
import registry_handler
import config_handler
import instance_handler

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
        self.instance_data = {}
        self.init_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_instance_statuses)
        self.timer.start(REFRESH_INTERVAL_MS)

    def init_ui(self):
        main_layout = QVBoxLayout()

        self.path_label = QLabel("BlueStacks Path: Loading...")
        main_layout.addWidget(self.path_label)

        instance_group = QGroupBox("Instances")
        instance_layout = QVBoxLayout()
        instance_layout.setObjectName("instance_layout")
        self.instance_checkboxes = {}
        instance_group.setLayout(instance_layout)
        main_layout.addWidget(instance_group)

        buttons_layout = QHBoxLayout()
        root_toggle_button = QPushButton("Toggle Root")
        root_toggle_button.clicked.connect(self.toggle_root)
        buttons_layout.addWidget(root_toggle_button)

        rw_toggle_button = QPushButton("Toggle R/W")
        rw_toggle_button.clicked.connect(self.toggle_rw)
        buttons_layout.addWidget(rw_toggle_button)

        main_layout.addLayout(buttons_layout)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)
        self.initialize_paths_and_instances()

    def initialize_paths_and_instances(self):
        user_defined_dir = registry_handler.get_bluestacks_path("UserDefinedDir")
        if user_defined_dir:
            self.config_path = os.path.join(user_defined_dir, BLUESTACKS_CONF_FILENAME)
        else:
            self.path_label.setText("BlueStacks Path: Not Found")
            self.status_label.setText("Could not find BlueStacks installation.")
            return

        self.bluestacks_path = registry_handler.get_bluestacks_path("DataDir")
        if self.bluestacks_path:
            self.path_label.setText(f"BlueStacks Path: {self.bluestacks_path}")
            self.update_instance_data()
            self.update_instance_checkboxes()
            self.update_instance_statuses()
        else:
            self.path_label.setText("BlueStacks Path: Not Found")
            self.status_label.setText("Could not find BlueStacks installation.")

    def update_instance_data(self):
        if not self.config_path:
            return
        try:
            new_data = {}
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith(INSTANCE_PREFIX) and ENABLE_ROOT_KEY in line:
                        instance = line.split(".")[2]
                        path = os.path.join(self.bluestacks_path, instance)
                        new_data[instance] = {
                            "root_enabled": config_handler.is_root_enabled(self.config_path, instance),
                            "rw_mode": "Normal" if not instance_handler.is_instance_readonly(path) else "Readonly"
                        }
            self.instance_data = new_data
        except Exception as e:
            self.status_label.setText(f"Error reading config: {e}")

    def detect_instances(self, layout):
        if not self.instance_data:
            return
        # Create or update
        for name, data in self.instance_data.items():
            if name not in self.instance_checkboxes:
                hbox = QHBoxLayout()
                checkbox = QCheckBox(name)
                root_status = QLineEdit(f"Root: {'On' if data['root_enabled'] else 'Off'}")
                root_status.setReadOnly(True)
                rw_status = QLineEdit(f"R/W: {'On' if data['rw_mode'] == 'Normal' else 'Off'}")
                rw_status.setReadOnly(True)
                hbox.addWidget(checkbox)
                hbox.addWidget(root_status)
                hbox.addWidget(rw_status)
                layout.addLayout(hbox)
                self.instance_checkboxes[name] = {
                    "checkbox": checkbox,
                    "root_status": root_status,
                    "rw_status": rw_status,
                }
            else:
                self.instance_checkboxes[name]["root_status"].setText(
                    f"Root: {'On' if data['root_enabled'] else 'Off'}"
                )
                self.instance_checkboxes[name]["rw_status"].setText(
                    f"R/W: {'On' if data['rw_mode'] == 'Normal' else 'Off'}"
                )

        # Remove missing
        to_remove = set(self.instance_checkboxes.keys()) - set(self.instance_data.keys())
        for name in to_remove:
            widgets = self.instance_checkboxes.pop(name)
            layout.removeWidget(widgets["checkbox"].parentWidget())
            widgets["checkbox"].deleteLater()
            widgets["root_status"].deleteLater()
            widgets["rw_status"].deleteLater()

    def update_instance_checkboxes(self):
        layout = self.findChild(QVBoxLayout, "instance_layout")
        if layout is None:
            group = QGroupBox("Instances")
            layout = QVBoxLayout()
            layout.setObjectName("instance_layout")
            group.setLayout(layout)
            main_layout = self.layout()
            for i in range(main_layout.count()):
                item = main_layout.itemAt(i)
                if isinstance(item.widget(), QGroupBox) and item.widget().title() == "Instances":
                    main_layout.insertWidget(i + 1, group)
                    break
        self.detect_instances(layout)

    def toggle_root(self):
        if not self.config_path:
            self.status_label.setText("Error: bluestacks.conf not found.")
            return
        for name, widgets in self.instance_checkboxes.items():
            if widgets["checkbox"].isChecked():
                try:
                    curr = self.instance_data[name]["root_enabled"]
                    new_state = "0" if curr else "1"
                    config_handler.modify_config_file(
                        self.config_path, f"{INSTANCE_PREFIX}{name}{ENABLE_ROOT_KEY}", new_state
                    )
                    config_handler.modify_config_file(self.config_path, FEATURE_ROOTING_KEY, new_state)
                    self.instance_data[name]["root_enabled"] = not curr
                    widgets["root_status"].setText(f"Root: {'On' if not curr else 'Off'}")
                    self.status_label.setText(f"Root toggled for {name}")
                except Exception as e:
                    self.status_label.setText(f"Error toggling root for {name}: {e}")

    def toggle_rw(self):
        if not self.bluestacks_path:
            self.status_label.setText("Error: BlueStacks path not found.")
            return
        for name, widgets in self.instance_checkboxes.items():
            if widgets["checkbox"].isChecked():
                try:
                    path = os.path.join(self.bluestacks_path, name)
                    curr = self.instance_data[name]["rw_mode"]
                    new_mode = "Normal" if curr == "Readonly" else "Readonly"
                    instance_handler.modify_instance_files(path, [FASTBOOT_VDI, ROOT_VHD], new_mode)
                    self.instance_data[name]["rw_mode"] = new_mode
                    widgets["rw_status"].setText(f"R/W: {'On' if new_mode == 'Normal' else 'Off'}")
                    self.status_label.setText(f"R/W toggled for {name}")
                except Exception as e:
                    self.status_label.setText(f"Error toggling R/W for {name}: {e}")

    def update_instance_statuses(self):
        self.update_instance_data()
        for name, widgets in self.instance_checkboxes.items():
            try:
                widgets["root_status"].setText(
                    f"Root: {'On' if self.instance_data[name]['root_enabled'] else 'Off'}"
                )
                widgets["rw_status"].setText(
                    f"R/W: {'On' if self.instance_data[name]['rw_mode'] == 'Normal' else 'Off'}"
                )
            except Exception as e:
                self.status_label.setText(f"Error updating status for {name}: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BluestacksRootToggle()
    window.show()
    sys.exit(app.exec_())