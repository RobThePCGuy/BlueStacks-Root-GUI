import sys
import os
import time
import logging

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QGroupBox, QCheckBox, QLineEdit, QComboBox  # Import QComboBox for language selection
)
from PyQt5.QtCore import Qt, QTimer, QLocale
from PyQt5.QtGui import QIcon, QFont

import registry_handler
import config_handler
import instance_handler

# Initialize logging (as before)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

        # --- Translation Setup (Dictionary-based) ---
        self.languages = {"en": "English", "ja": "日本語"}  # Language codes and names
        self.current_language = "en"  # Default language

        self.translations = {
            "en": {  # English translations (source strings are keys)
                "BlueStacks Root GUI": "BlueStacks Root GUI",
                "BlueStacks Path: Loading...": "BlueStacks Path: Loading...",
                "BlueStacks Path: Not Found": "BlueStacks Path: Not Found",
                "BlueStacks Path: {}": "BlueStacks Path: {}", # Placeholders still work
                "Instances": "Instances",
                "Toggle Root": "Toggle Root",
                "Toggle R/W": "Toggle R/W",
                "Ready": "Ready",
                "Error: Config path not initialized.": "Error: Config path not initialized.",
                "Error reading config: File not found.": "Error reading config: File not found.",
                "Error reading config: {}": "Error reading config: {}",
                "Root: {}": "Root: {}",
                "R/W: {}": "R/W: {}",
                "On": "On",
                "Off": "Off",
                "BlueStacks UserDefinedDir registry key not found.": "BlueStacks UserDefinedDir registry key not found.",
                "BlueStacks DataDir registry key not found.": "BlueStacks DataDir registry key not found.",
                "Error: bluestacks.conf not found.": "Error: bluestacks.conf not found.",
                "No instances selected to toggle root.": "No instances selected to toggle root.",
                "Root toggled for {}": "Root toggled for {}",
                "Root toggled for instance: {} to {}": "Root toggled for instance: {} to {}",
                "Error toggling root for {}: {}": "Error toggling root for {}: {}",
                "Error: BlueStacks path not found.": "Error: BlueStacks path not found.",
                "No instances selected to toggle R/W.": "No instances selected to toggle R/W.",
                "R/W toggled for {}": "R/W toggled for {}",
                "R/W toggled for instance: {} to {}": "R/W toggled for instance: {} to {}",
                "Error toggling R/W for {}: {}": "Error toggling R/W for {}: {}",
                "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.": "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.",
                "Error updating status for {}: {}": "Error updating status for {}: {}",
                "Config file not found: {}": "Config file not found: {}",
                "Error reading config file: {}": "Error reading config file: {}",
            },
            "ja": {  # Japanese translations
                "BlueStacks Root GUI": "BlueStacks Root GUI (日本語)",  # Example - Translated title
                "BlueStacks Path: Loading...": "BlueStacks パス: 読み込み中...",
                "BlueStacks Path: Not Found": "BlueStacks パス: 見つかりません",
                "BlueStacks Path: {}": "BlueStacks パス: {}",
                "Instances": "インスタンス",
                "Toggle Root": "ルート切り替え",
                "Toggle R/W": "R/W切り替え",
                "Ready": "準備完了",
                "Error: Config path not initialized.": "エラー：設定パスが初期化されていません。",
                "Error reading config: File not found.": "エラー：設定ファイルの読み込みエラー：ファイルが見つかりません。",
                "Error reading config: {}": "エラー：設定ファイルの読み込みエラー：{}",
                "Root: {}": "ルート: {}",
                "R/W: {}": "R/W: {}",
                "On": "オン",
                "Off": "オフ",
                "BlueStacks UserDefinedDir registry key not found.": "BlueStacks UserDefinedDir レジストリキーが見つかりません。",
                "BlueStacks DataDir registry key not found.": "BlueStacks DataDir レジストリキーが見つかりません。",
                "Error: bluestacks.conf not found.": "エラー：bluestacks.conf が見つかりません。",
                "No instances selected to toggle root.": "ルートを切り替えるインスタンスが選択されていません。",
                "Root toggled for {}": "{} のルートを切り替えました",
                "Root toggled for instance: {} to {}": "インスタンス {} のルートを {} に切り替えました",
                "Error toggling root for {}: {}": "{} のルート切り替えエラー：{}",
                "Error: BlueStacks path not found.": "エラー：BlueStacks パスが見つかりません。",
                "No instances selected to toggle R/W.": "R/W を切り替えるインスタンスが選択されていません。",
                "R/W toggled for {}": "{} の R/W を切り替えました",
                "R/W toggled for instance: {} to {}": "インスタンス {} の R/W を {} に切り替えました",
                "Error toggling R/W for {}: {}": "{} の R/W 切り替えエラー：{}",
                "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.": "インスタンス '{}' がチェックボックスにありますが、インスタンスデータに見つかりません。UI が同期していない可能性があります。",
                "Error updating status for {}: {}": "{} のステータス更新エラー：{}",
                "Config file not found: {}": "設定ファイルが見つかりません: {}",
                "Error reading config file: {}": "設定ファイルの読み込みエラー: {}",

            }
            # Add more languages here if needed (e.g., "es" for Spanish, "fr" for French)
        }
        # -----------------------------------------

        self.setWindowTitle(self.get_translation("BlueStacks Root GUI")) # Use translation function
        self.setWindowIcon(QIcon("main.ico"))
        self.bluestacks_path = None
        self.config_path = None
        self.instance_data = {}
        self.instance_checkboxes = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_instance_statuses)
        self.timer.start(REFRESH_INTERVAL_MS)
        self.init_ui()

    def get_translation(self, source_text):
        """Gets the translation for the given source text in the current language."""
        lang_dict = self.translations.get(self.current_language)
        if lang_dict and source_text in lang_dict:
            return lang_dict[source_text]
        return source_text  # Return source if no translation found

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Language selection combobox
        self.language_combo = QComboBox()
        for lang_code, lang_name in self.languages.items():
            self.language_combo.addItem(lang_name, lang_code) # Display name, store code as data
        self.language_combo.currentIndexChanged.connect(self.change_language) # Connect signal
        main_layout.addWidget(self.language_combo)


        self.path_label = QLabel(self.get_translation("BlueStacks Path: Loading...")) # Use translation function
        main_layout.addWidget(self.path_label)

        instance_group = QGroupBox(self.get_translation("Instances")) # Use translation function
        instance_layout = QVBoxLayout()
        instance_layout.setObjectName("instance_layout")
        instance_group.setLayout(instance_layout)
        main_layout.addWidget(instance_group)

        buttons_layout = QHBoxLayout()
        root_toggle_button = QPushButton(self.get_translation("Toggle Root")) # Use translation function
        root_toggle_button.clicked.connect(self.toggle_root)
        buttons_layout.addWidget(root_toggle_button)

        rw_toggle_button = QPushButton(self.get_translation("Toggle R/W")) # Use translation function
        rw_toggle_button.clicked.connect(self.toggle_rw)
        buttons_layout.addWidget(rw_toggle_button)

        main_layout.addLayout(buttons_layout)

        self.status_label = QLabel(self.get_translation("Ready")) # Use translation function
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)
        QTimer.singleShot(0, self.initialize_paths_and_instances)

    def change_language(self, index):
        """Changes the application language when the combobox is changed."""
        lang_code = self.language_combo.itemData(index) # Get language code from combobox data
        if lang_code:
            self.current_language = lang_code
            self.setWindowTitle(self.get_translation("BlueStacks Root GUI"))
            self.path_label.setText(self.get_translation("BlueStacks Path: Loading...")) # Update UI text
            instance_group = self.findChild(QGroupBox, "Instances") # Find the group box by title is less reliable
            if instance_group:
                instance_group.setTitle(self.get_translation("Instances"))
            root_toggle_button = self.findChild(QPushButton, "Toggle Root") # Find buttons by text is less reliable
            if root_toggle_button:
                root_toggle_button.setText(self.get_translation("Toggle Root"))
            rw_toggle_button = self.findChild(QPushButton, "Toggle R/W")
            if rw_toggle_button:
                rw_toggle_button.setText(self.get_translation("Toggle R/W"))
            self.status_label.setText(self.get_translation("Ready"))
            self.update_instance_checkboxes_text() # Update text in instance checkboxes
            self.initialize_paths_and_instances() # Re-initialize messages that might depend on language

    def update_instance_checkboxes_text(self):
        """Updates the text (Root: On/Off, R/W: On/Off) in instance checkboxes after language change."""
        for name, widgets in self.instance_checkboxes.items():
            data = self.instance_data.get(name, {}) # Safely get data, handle cases where instance might be removed
            if data: # Only update if instance data exists
                widgets["root_status"].setText(
                    self.get_translation("Root: {}").format(self.get_translation("On") if data['root_enabled'] else self.get_translation("Off"))
                )
                widgets["rw_status"].setText(
                    self.get_translation("R/W: {}").format(self.get_translation("On") if data['rw_mode'] == 'Normal' else self.get_translation("Off"))
                )


    def initialize_paths_and_instances(self):
        """Initializes Bluestacks paths and instance data."""
        user_defined_dir = registry_handler.get_bluestacks_path("UserDefinedDir")
        if user_defined_dir:
            self.config_path = os.path.join(user_defined_dir, BLUESTACKS_CONF_FILENAME)
        else:
            error_message = self.get_translation("BlueStacks UserDefinedDir registry key not found.")
            self.path_label.setText(self.get_translation("BlueStacks Path: Not Found"))
            self.status_label.setText(error_message)
            logging.error(error_message)
            return

        self.bluestacks_path = registry_handler.get_bluestacks_path("DataDir")
        if self.bluestacks_path:
            self.path_label.setText(self.get_translation("BlueStacks Path: {}").format(self.bluestacks_path))
            self.update_instance_data()
            self.update_instance_checkboxes()
            self.update_instance_statuses()
        else:
            error_message = self.get_translation("BlueStacks DataDir registry key not found.")
            self.path_label.setText(self.get_translation("BlueStacks Path: Not Found"))
            self.status_label.setText(error_message)
            logging.error(error_message)

    def update_instance_data(self):
        """Updates instance data from bluestacks.conf."""
        if not self.config_path:
            self.status_label.setText(self.get_translation("Error: Config path not initialized."))
            logging.error("Config path not initialized when trying to update instance data.")
            return
        try:
            new_data = {}
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith(INSTANCE_PREFIX) and ENABLE_ROOT_KEY in line:
                        parts = line.strip().split("=")
                        if len(parts) > 0:
                            key_part = parts[0]
                            instance = key_part.split(".")[2]
                            if not instance:
                                logging.warning(f"Could not parse instance name from line: {line.strip()}")
                                continue
                            path = os.path.join(self.bluestacks_path, instance)
                            new_data[instance] = {
                                "root_enabled": config_handler.is_root_enabled(self.config_path, instance),
                                "rw_mode": "Normal" if not instance_handler.is_instance_readonly(path) else "Readonly"
                            }
            self.instance_data = new_data
        except FileNotFoundError:
            error_message = self.get_translation("Config file not found: {}").format(self.config_path)
            self.status_label.setText(self.get_translation("Error reading config: File not found."))
            logging.error(error_message)
        except Exception as e:
            error_message = self.get_translation("Error reading config file: {}").format(e)
            self.status_label.setText(self.get_translation("Error reading config: {}").format(e))
            logging.exception(error_message)


    def detect_instances(self, layout):
        """Detects and updates instance checkboxes based on instance data."""
        if not self.instance_data:
            return

        current_instances = set(self.instance_checkboxes.keys())
        new_instances = set(self.instance_data.keys())

        # Add new instances
        for name in new_instances - current_instances:
            data = self.instance_data[name]
            hbox = QHBoxLayout()
            checkbox = QCheckBox(name)
            root_status = QLineEdit(self.get_translation("Root: {}").format(self.get_translation("On") if data['root_enabled'] else self.get_translation("Off")))
            root_status.setReadOnly(True)
            rw_status = QLineEdit(self.get_translation("R/W: {}").format(self.get_translation("On") if data['rw_mode'] == 'Normal' else self.get_translation("Off")))
            rw_status.setReadOnly(True)
            hbox.addWidget(checkbox)
            hbox.addWidget(root_status)
            hbox.addWidget(rw_status)
            layout.addLayout(hbox)
            self.instance_checkboxes[name] = {
                "checkbox": checkbox,
                "root_status": root_status,
                "rw_status": rw_status,
                "layout": hbox
            }

        # Update existing instances
        for name in new_instances & current_instances:
            data = self.instance_data[name]
            self.instance_checkboxes[name]["root_status"].setText(
                self.get_translation("Root: {}").format(self.get_translation("On") if data['root_enabled'] else self.get_translation("Off"))
            )
            self.instance_checkboxes[name]["rw_status"].setText(
                self.get_translation("R/W: {}").format(self.get_translation("On") if data['rw_mode'] == 'Normal' else self.get_translation("Off"))
            )

        # Remove old instances
        for name in current_instances - new_instances:
            widgets = self.instance_checkboxes.pop(name)
            layout.removeItem(widgets["layout"])
            widgets["layout"].deleteLater()
            widgets["checkbox"].deleteLater()
            widgets["root_status"].deleteLater()
            widgets["rw_status"].deleteLater()


    def update_instance_checkboxes(self):
        """Updates the instance checkboxes in the UI."""
        layout = self.findChild(QVBoxLayout, "instance_layout")
        if layout is None:
            logging.error("Instance layout not found during update_instance_checkboxes.")
            return

        self.detect_instances(layout)

    def toggle_root(self):
        """Toggles root access for selected instances."""
        if not self.config_path:
            self.status_label.setText(self.get_translation("Error: bluestacks.conf not found."))
            logging.error("bluestacks.conf path not found when toggling root.")
            return
        selected_instances = [name for name, widgets in self.instance_checkboxes.items() if widgets["checkbox"].isChecked()]
        if not selected_instances:
            self.status_label.setText(self.get_translation("No instances selected to toggle root."))
            return

        for name in selected_instances:
            try:
                curr = self.instance_data[name]["root_enabled"]
                new_state = "0" if curr else "1"
                config_handler.modify_config_file(
                    self.config_path, f"{INSTANCE_PREFIX}{name}{ENABLE_ROOT_KEY}", new_state
                )
                config_handler.modify_config_file(self.config_path, FEATURE_ROOTING_KEY, new_state)
                self.instance_data[name]["root_enabled"] = not curr
                self.instance_checkboxes[name]["root_status"].setText(
                    self.get_translation("Root: {}").format(self.get_translation("On") if not curr else self.get_translation("Off"))
                )
                self.status_label.setText(self.get_translation("Root toggled for {}").format(name))
                logging.info(self.get_translation("Root toggled for instance: {} to {}").format(name, self.get_translation("On") if not curr else self.get_translation("Off")))
            except Exception as e:
                error_message = self.get_translation("Error toggling root for {}: {}").format(name, e)
                self.status_label.setText(error_message)
                logging.exception(error_message)

    def toggle_rw(self):
        """Toggles read/write mode for selected instances."""
        if not self.bluestacks_path:
            self.status_label.setText(self.get_translation("Error: BlueStacks path not found."))
            logging.error("BlueStacks path not found when toggling R/W.")
            return

        selected_instances = [name for name, widgets in self.instance_checkboxes.items() if widgets["checkbox"].isChecked()]
        if not selected_instances:
            self.status_label.setText(self.get_translation("No instances selected to toggle R/W."))
            return

        for name in selected_instances:
            try:
                path = os.path.join(self.bluestacks_path, name)
                curr = self.instance_data[name]["rw_mode"]
                new_mode = "Normal" if curr == "Readonly" else "Readonly"
                instance_handler.modify_instance_files(path, [FASTBOOT_VDI, ROOT_VHD], new_mode)
                self.instance_data[name]["rw_mode"] = new_mode
                self.instance_checkboxes[name]["rw_status"].setText(
                    self.get_translation("R/W: {}").format(self.get_translation("On") if new_mode == 'Normal' else self.get_translation("Off"))
                )
                self.status_label.setText(self.get_translation("R/W toggled for {}").format(name))
                logging.info(self.get_translation("R/W toggled for instance: {} to {}").format(name, new_mode))
            except Exception as e:
                error_message = self.get_translation("Error toggling R/W for {}: {}").format(name, e)
                self.status_label.setText(error_message)
                logging.exception(error_message)

    def update_instance_statuses(self):
        """Updates the status of instances in the UI."""
        self.update_instance_data()
        for name, widgets in self.instance_checkboxes.items():
            try:
                if name in self.instance_data:
                    widgets["root_status"].setText(
                        self.get_translation("Root: {}").format(self.get_translation("On") if self.instance_data[name]['root_enabled'] else self.get_translation("Off"))
                    )
                    widgets["rw_status"].setText(
                        self.get_translation("R/W: {}").format(self.get_translation("On") if self.instance_data[name]['rw_mode'] == 'Normal' else self.get_translation("Off"))
                    )
                else:
                    logging.warning(self.get_translation("Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.").format(name))
            except Exception as e:
                error_message = self.get_translation("Error updating status for {}: {}").format(name, e)
                self.status_label.setText(error_message)
                logging.exception(error_message)


    def closeEvent(self, event):
        """Handles the close event of the main window."""
        self.timer.stop()
        logging.info("BlueStacks Root GUI closed.")
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BluestacksRootToggle()
    window.show()
    logging.info("BlueStacks Root GUI started.")
    sys.exit(app.exec_())