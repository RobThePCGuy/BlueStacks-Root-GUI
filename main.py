import sys
import os
import logging

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QGroupBox, QCheckBox, QLineEdit, QComboBox, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon

import registry_handler
import config_handler
import instance_handler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
BLUESTACKS_CONF_FILENAME = "bluestacks.conf"
INSTANCE_PREFIX = "bst.instance."
ENABLE_ROOT_KEY = ".enable_root_access"
FEATURE_ROOTING_KEY = "bst.feature.rooting"
FASTBOOT_VDI = "fastboot.vdi"
ROOT_VHD = "Root.vhd"
REFRESH_INTERVAL_MS = 5000  # 5 seconds


class TranslationManager:
    """Manages translations for the application."""
    def __init__(self):
        self.languages = {"en": "English", "ja": "日本語"}
        self.current_language = "en"
        self.translations = {
            "en": {
                "BlueStacks Root GUI": "BlueStacks Root GUI",
                "BlueStacks Path: Loading...": "BlueStacks Path: Loading...",
                "BlueStacks Path: Not Found": "BlueStacks Path: Not Found",
                "BlueStacks Path: {}": "BlueStacks Path: {}",
                "Instances": "Instances",
                "Toggle Root": "Toggle Root",
                "Toggle R/W": "Toggle R/W",  # Removed (Requires Restart) text
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
                "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.": (
                    "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync."
                ),
                "Error updating status for {}: {}": "Error updating status for {}: {}",
                "Config file not found: {}": "Config file not found: {}",
                "Error reading config file: {}": "Error reading config file: {}",
                "BlueStacks is running. Terminating process...": "BlueStacks is running. Terminating process...",
                "BlueStacks terminated.": "BlueStacks terminated.",
                "Error terminating BlueStacks: {}": "Error terminating BlueStacks: {}",
                "Toggling Root...": "Toggling Root...",
                "Toggling R/W...": "Toggling R/W...",
                "Please restart BlueStacks for R/W changes to take effect.": "Please restart BlueStacks for R/W changes to take effect.",
                "Confirmation": "Confirmation",
                # New key for the Magisk install reminder popup when turning root on
                "Magisk install reminder": "After Magisk has installed to the System partition successfully, make sure you come back and turn Root Off.",
            },
            "ja": {
                "BlueStacks Root GUI": "BlueStacks Root GUI (日本語)",
                "BlueStacks Path: Loading...": "BlueStacks パス: 読み込み中...",
                "BlueStacks Path: Not Found": "BlueStacks パス: 見つかりません",
                "BlueStacks Path: {}": "BlueStacks パス: {}",
                "Instances": "インスタンス",
                "Toggle Root": "ルート切り替え",
                "Toggle R/W": "R/W切り替え",  # Removed (再起動が必要) text
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
                "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.": (
                    "インスタンス '{}' がチェックボックスにありますが、インスタンスデータに見つかりません。UI が同期していない可能性があります。"
                ),
                "Error updating status for {}: {}": "{} のステータス更新エラー：{}",
                "Config file not found: {}": "設定ファイルが見つかりません: {}",
                "Error reading config file: {}": "設定ファイルの読み込みエラー: {}",
                "BlueStacks is running. Terminating process...": "BlueStacks が実行中です。プロセスを終了しています...",
                "BlueStacks terminated.": "BlueStacks が終了しました。",
                "Error terminating BlueStacks: {}": "BlueStacks の終了エラー：{}",
                "Toggling Root...": "ルート切り替え中...",
                "Toggling R/W...": "R/W切り替え中...",
                "Please restart BlueStacks for R/W changes to take effect.": "R/W変更を有効にするにはBlueStacksを再起動してください。",
                "Confirmation": "確認",
                # New key for the Magisk install reminder popup when turning root on
                "Magisk install reminder": "Magiskがシステムパーティションに正常にインストールされた後、必ず戻ってきてルートをオフにしてください。",
            }
        }

    def get_translation(self, source_text):
        lang_dict = self.translations.get(self.current_language, {})
        return lang_dict.get(source_text, source_text)


class BluestacksRootToggle(QWidget):
    """Main GUI class for toggling BlueStacks root and R/W modes."""
    def __init__(self):
        super().__init__()
        self.translation_manager = TranslationManager()
        self.setWindowTitle(self.translation_manager.get_translation("BlueStacks Root GUI"))
        self.setWindowIcon(QIcon("main.ico"))

        self.bluestacks_path = None
        self.config_path = None
        self.instance_data = {}
        self.instance_checkboxes = {}
        self.is_toggling = False  # Flag to prevent concurrent toggling

        # Timer to update instance statuses periodically
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_instance_statuses)
        self.timer.start(REFRESH_INTERVAL_MS)

        # Initialize the UI components
        self.init_ui()

    def init_ui(self):
        """Initializes and lays out all UI components."""
        main_layout = QVBoxLayout()

        # Language selection
        self.language_combo = QComboBox()
        for lang_code, lang_name in self.translation_manager.languages.items():
            self.language_combo.addItem(lang_name, lang_code)
        self.language_combo.currentIndexChanged.connect(self.change_language)
        main_layout.addWidget(self.language_combo)

        # BlueStacks path label
        self.path_label = QLabel(self.translation_manager.get_translation("BlueStacks Path: Loading..."))
        main_layout.addWidget(self.path_label)

        # Instances group box and layout
        self.instance_group = QGroupBox(self.translation_manager.get_translation("Instances"))
        self.instance_layout = QVBoxLayout()
        self.instance_layout.setObjectName("instance_layout")
        self.instance_group.setLayout(self.instance_layout)
        main_layout.addWidget(self.instance_group)

        # Control buttons layout
        buttons_layout = QHBoxLayout()
        self.root_toggle_button = QPushButton(self.translation_manager.get_translation("Toggle Root"))
        self.root_toggle_button.clicked.connect(self.toggle_root)
        buttons_layout.addWidget(self.root_toggle_button)

        # Directly connect the R/W button to toggle_rw without confirmation popup
        self.rw_toggle_button = QPushButton(self.translation_manager.get_translation("Toggle R/W"))
        self.rw_toggle_button.clicked.connect(self.toggle_rw)
        buttons_layout.addWidget(self.rw_toggle_button)

        main_layout.addLayout(buttons_layout)

        # Status label
        self.status_label = QLabel(self.translation_manager.get_translation("Ready"))
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Progress bar (indeterminate)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self.setLayout(main_layout)

        # Delay initialization of paths and instances until after UI is shown
        QTimer.singleShot(0, self.initialize_paths_and_instances)

    def change_language(self, index):
        """Handles language change and updates all UI text."""
        lang_code = self.language_combo.itemData(index)
        if lang_code:
            self.translation_manager.current_language = lang_code
            self.setWindowTitle(self.translation_manager.get_translation("BlueStacks Root GUI"))
            self.path_label.setText(self.translation_manager.get_translation("BlueStacks Path: Loading..."))
            self.instance_group.setTitle(self.translation_manager.get_translation("Instances"))
            self.root_toggle_button.setText(self.translation_manager.get_translation("Toggle Root"))
            self.rw_toggle_button.setText(self.translation_manager.get_translation("Toggle R/W"))
            self.status_label.setText(self.translation_manager.get_translation("Ready"))
            self.update_instance_checkboxes_text()
            self.initialize_paths_and_instances()

    def update_instance_checkboxes_text(self):
        """Updates the checkbox status texts according to the current language."""
        for name, widgets in self.instance_checkboxes.items():
            data = self.instance_data.get(name, {})
            if data:
                root_text = self.translation_manager.get_translation("On") if data['root_enabled'] else self.translation_manager.get_translation("Off")
                rw_text = self.translation_manager.get_translation("On") if data['rw_mode'] == 'Normal' else self.translation_manager.get_translation("Off")
                widgets["root_status"].setText(
                    self.translation_manager.get_translation("Root: {}").format(root_text)
                )
                widgets["rw_status"].setText(
                    self.translation_manager.get_translation("R/W: {}").format(rw_text)
                )

    def check_and_kill_bluestacks(self):
        """Terminates BlueStacks if it is running."""
        self.status_label.setText(self.translation_manager.get_translation("BlueStacks is running. Terminating process..."))
        self.progress_bar.show()
        QApplication.processEvents()  # Update UI immediately
        try:
            instance_handler.terminate_bluestacks()
            self.status_label.setText(self.translation_manager.get_translation("BlueStacks terminated."))
            logging.info(self.translation_manager.get_translation("BlueStacks terminated."))
        except Exception as e:
            error_message = self.translation_manager.get_translation("Error terminating BlueStacks: {}").format(e)
            self.status_label.setText(error_message)
            logging.exception(error_message)
        finally:
            self.progress_bar.hide()
            QApplication.processEvents()

    def initialize_paths_and_instances(self):
        """Initializes BlueStacks paths and loads instance data."""
        self.status_label.setText(self.translation_manager.get_translation("BlueStacks Path: Loading..."))
        QApplication.processEvents()
        user_defined_dir = registry_handler.get_bluestacks_path("UserDefinedDir")
        if user_defined_dir:
            self.config_path = os.path.join(user_defined_dir, BLUESTACKS_CONF_FILENAME)
        else:
            error_message = self.translation_manager.get_translation("BlueStacks UserDefinedDir registry key not found.")
            self.path_label.setText(self.translation_manager.get_translation("BlueStacks Path: Not Found"))
            self.status_label.setText(error_message)
            logging.error(error_message)
            return

        self.bluestacks_path = registry_handler.get_bluestacks_path("DataDir")
        if self.bluestacks_path:
            self.path_label.setText(self.translation_manager.get_translation("BlueStacks Path: {}").format(self.bluestacks_path))
            self.update_instance_data()
            self.update_instance_checkboxes()
            self.update_instance_statuses()
            self.status_label.setText(self.translation_manager.get_translation("Ready"))
        else:
            error_message = self.translation_manager.get_translation("BlueStacks DataDir registry key not found.")
            self.path_label.setText(self.translation_manager.get_translation("BlueStacks Path: Not Found"))
            self.status_label.setText(error_message)
            logging.error(error_message)

    def update_instance_data(self):
        """Reads the config file to update instance data."""
        if not self.config_path:
            self.status_label.setText(self.translation_manager.get_translation("Error: Config path not initialized."))
            logging.error("Config path not initialized when trying to update instance data.")
            return
        try:
            new_data = {}
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith(INSTANCE_PREFIX) and ENABLE_ROOT_KEY in line:
                        parts = line.strip().split("=")
                        if parts:
                            key_part = parts[0]
                            # Instance name is expected to be the third component
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
            error_message = self.translation_manager.get_translation("Config file not found: {}").format(self.config_path)
            self.status_label.setText(self.translation_manager.get_translation("Error reading config: File not found."))
            logging.error(error_message)
        except Exception as e:
            error_message = self.translation_manager.get_translation("Error reading config file: {}").format(e)
            self.status_label.setText(self.translation_manager.get_translation("Error reading config: {}").format(e))
            logging.exception(error_message)

    def detect_instances(self, layout):
        """Detects and updates instance checkboxes in the UI."""
        if not self.instance_data:
            return

        current_instances = set(self.instance_checkboxes.keys())
        new_instances = set(self.instance_data.keys())

        # Add new instances
        for name in new_instances - current_instances:
            data = self.instance_data[name]
            hbox = QHBoxLayout()
            checkbox = QCheckBox(name)
            root_text = self.translation_manager.get_translation("On") if data['root_enabled'] else self.translation_manager.get_translation("Off")
            rw_text = self.translation_manager.get_translation("On") if data['rw_mode'] == 'Normal' else self.translation_manager.get_translation("Off")
            root_status = QLineEdit(self.translation_manager.get_translation("Root: {}").format(root_text))
            root_status.setReadOnly(True)
            rw_status = QLineEdit(self.translation_manager.get_translation("R/W: {}").format(rw_text))
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
                self.translation_manager.get_translation("On") if data['root_enabled'] else self.translation_manager.get_translation("Off")
            )
            self.instance_checkboxes[name]["rw_status"].setText(
                self.translation_manager.get_translation("On") if data['rw_mode'] == 'Normal' else self.translation_manager.get_translation("Off")
            )

        # Remove instances no longer present
        for name in current_instances - new_instances:
            widgets = self.instance_checkboxes.pop(name)
            layout.removeItem(widgets["layout"])
            widgets["layout"].deleteLater()
            widgets["checkbox"].deleteLater()
            widgets["root_status"].deleteLater()
            widgets["rw_status"].deleteLater()

    def update_instance_checkboxes(self):
        """Updates the instance checkboxes area with current instance data."""
        self.detect_instances(self.instance_layout)

    def toggle_root(self):
        """Toggles the root access for selected instances."""
        if self.is_toggling:
            return  # Prevent concurrent toggling

        self.is_toggling = True
        self.status_label.setText(self.translation_manager.get_translation("Toggling Root..."))
        self.progress_bar.show()
        QApplication.processEvents()
        self.root_toggle_button.setEnabled(False)

        self.check_and_kill_bluestacks()

        if not self.config_path:
            self.status_label.setText(self.translation_manager.get_translation("Error: bluestacks.conf not found."))
            logging.error("bluestacks.conf path not found when toggling root.")
            self.reset_ui_after_toggle()
            return

        selected_instances = [
            name for name, widgets in self.instance_checkboxes.items()
            if widgets["checkbox"].isChecked()
        ]
        if not selected_instances:
            self.status_label.setText(self.translation_manager.get_translation("No instances selected to toggle root."))
            self.reset_ui_after_toggle()
            return

        # If any selected instance is being enabled (currently off), show the Magisk install reminder popup.
        if any(not self.instance_data[name]["root_enabled"] for name in selected_instances):
            popup = QMessageBox()
            popup.setWindowTitle(self.translation_manager.get_translation("Confirmation"))
            popup.setIcon(QMessageBox.Information)
            popup.setText(self.translation_manager.get_translation("Magisk install reminder"))
            popup.exec_()

        for name in selected_instances:
            try:
                curr = self.instance_data[name]["root_enabled"]
                new_state = "0" if curr else "1"
                config_handler.modify_config_file(
                    self.config_path, f"{INSTANCE_PREFIX}{name}{ENABLE_ROOT_KEY}", new_state
                )
                config_handler.modify_config_file(self.config_path, FEATURE_ROOTING_KEY, new_state)
                self.instance_data[name]["root_enabled"] = not curr
                new_status = self.translation_manager.get_translation("On") if not curr else self.translation_manager.get_translation("Off")
                self.instance_checkboxes[name]["root_status"].setText(
                    self.translation_manager.get_translation("Root: {}").format(new_status)
                )
                self.status_label.setText(self.translation_manager.get_translation("Root toggled for {}").format(name))
                logging.info(
                    self.translation_manager.get_translation("Root toggled for instance: {} to {}").format(
                        name, new_status
                    )
                )
            except Exception as e:
                error_message = self.translation_manager.get_translation("Error toggling root for {}: {}").format(name, e)
                self.status_label.setText(error_message)
                logging.exception(error_message)
                break  # Stop on first error

        self.reset_ui_after_toggle()

    def reset_ui_after_toggle(self):
        """Resets UI elements after toggling operations."""
        self.is_toggling = False
        self.progress_bar.hide()
        self.root_toggle_button.setEnabled(True)
        self.rw_toggle_button.setEnabled(True)
        QApplication.processEvents()

    def toggle_rw(self):
        """Toggles read/write mode for selected instances."""
        if self.is_toggling:
            return

        self.is_toggling = True
        self.status_label.setText(self.translation_manager.get_translation("Toggling R/W..."))
        self.progress_bar.show()
        QApplication.processEvents()
        self.rw_toggle_button.setEnabled(False)

        self.check_and_kill_bluestacks()

        if not self.bluestacks_path:
            self.status_label.setText(self.translation_manager.get_translation("Error: BlueStacks path not found."))
            logging.error("BlueStacks path not found when toggling R/W.")
            self.reset_ui_after_toggle()
            return

        selected_instances = [
            name for name, widgets in self.instance_checkboxes.items()
            if widgets["checkbox"].isChecked()
        ]
        if not selected_instances:
            self.status_label.setText(self.translation_manager.get_translation("No instances selected to toggle R/W."))
            self.reset_ui_after_toggle()
            return

        for name in selected_instances:
            try:
                engine_path = os.path.join(self.bluestacks_path, name)
                instance_path = os.path.join(self.bluestacks_path, name)
                curr = self.instance_data[name]["rw_mode"]
                new_mode = "Normal" if curr == "Readonly" else "Readonly"

                # Check for required BSTK file
                bstk_file_path = os.path.join(engine_path, "Android.bstk.in")
                if not os.path.exists(bstk_file_path):
                    error_message = f"BSTK file not found at {bstk_file_path}"
                    self.status_label.setText(error_message)
                    logging.error(error_message)
                    continue

                instance_handler.modify_instance_files(engine_path, instance_path, [FASTBOOT_VDI, ROOT_VHD], new_mode)
                self.instance_data[name]["rw_mode"] = new_mode
                new_status = self.translation_manager.get_translation("On") if new_mode == "Normal" else self.translation_manager.get_translation("Off")
                self.instance_checkboxes[name]["rw_status"].setText(
                    self.translation_manager.get_translation("R/W: {}").format(new_status)
                )
                self.status_label.setText(self.translation_manager.get_translation("R/W toggled for {}").format(name))
                logging.info(
                    self.translation_manager.get_translation("R/W toggled for instance: {} to {}").format(name, new_mode)
                )
            except Exception as e:
                error_message = self.translation_manager.get_translation("Error toggling R/W for {}: {}").format(name, e)
                self.status_label.setText(error_message)
                logging.exception(error_message)
                break

        self.reset_ui_after_toggle()




    def update_instance_statuses(self):
        """Periodically updates the status of each instance in the UI."""
        if self.is_toggling:
            return
        self.update_instance_data()
        for name, widgets in self.instance_checkboxes.items():
            try:
                if name in self.instance_data:
                    root_text = self.translation_manager.get_translation("On") if self.instance_data[name]['root_enabled'] else self.translation_manager.get_translation("Off")
                    rw_text = self.translation_manager.get_translation("On") if self.instance_data[name]['rw_mode'] == 'Normal' else self.translation_manager.get_translation("Off")
                    widgets["root_status"].setText(
                        self.translation_manager.get_translation("Root: {}").format(root_text)
                    )
                    widgets["rw_status"].setText(
                        self.translation_manager.get_translation("R/W: {}").format(rw_text)
                    )
                else:
                    logging.warning(
                        self.translation_manager.get_translation("Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.").format(name)
                    )
            except Exception as e:
                error_message = self.translation_manager.get_translation("Error updating status for {}: {}").format(name, e)
                self.status_label.setText(error_message)
                logging.exception(error_message)

    def closeEvent(self, event):
        """Handles cleanup on application close."""
        self.timer.stop()
        logging.info("BlueStacks Root GUI closed.")
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BluestacksRootToggle()
    window.show()
    logging.info("BlueStacks Root GUI started.")
    sys.exit(app.exec_())
