import sys
import os
import logging
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QGroupBox, QCheckBox, QLineEdit, QComboBox, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QIcon

import registry_handler
import config_handler
import instance_handler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
BLUESTACKS_CONF_FILENAME = "bluestacks.conf"
INSTANCE_PREFIX = "bst.instance."
ENABLE_ROOT_KEY = ".enable_root_access"
FEATURE_ROOTING_KEY = "bst.feature.rooting"
FASTBOOT_VDI = "fastboot.vdi"
ROOT_VHD = "Root.vhd"
REFRESH_INTERVAL_MS = 5000  # milliseconds

# Worker class to run blocking tasks in the background
class Worker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        
    def run(self):
        try:
            self.func(*self.args, **self.kwargs)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class TranslationManager:
    """
    Manages UI translations.
    """
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
                "Magisk install reminder": "After Magisk has installed to the System partition successfully, make sure you come back and turn Root Off.",
            },
            "ja": {
                "BlueStacks Root GUI": "BlueStacks Root GUI (日本語)",
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
                "Magisk install reminder": "Magiskがシステムパーティションに正常にインストールされた後、必ず戻ってきてルートをオフにしてください。",
            }
        }

    def get_translation(self, text: str) -> str:
        return self.translations.get(self.current_language, {}).get(text, text)

class BluestacksRootToggle(QWidget):
    def __init__(self):
        super().__init__()
        self.translation_manager = TranslationManager()
        self.bluestacks_path = None
        self.config_path = None
        self.instance_data = {}
        self.instance_checkboxes = {}
        self.is_toggling = False

        self.setWindowTitle(self.translation_manager.get_translation("BlueStacks Root GUI"))
        self.setWindowIcon(QIcon("main.ico"))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_instance_statuses)
        self.timer.start(REFRESH_INTERVAL_MS)

        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout()

        # Language selection
        self.language_combo = QComboBox()
        for code, name in self.translation_manager.languages.items():
            self.language_combo.addItem(name, code)
        self.language_combo.currentIndexChanged.connect(self.change_language)
        main_layout.addWidget(self.language_combo)

        # BlueStacks path label
        self.path_label = QLabel(self.translation_manager.get_translation("BlueStacks Path: Loading..."))
        main_layout.addWidget(self.path_label)

        # Instances group box
        self.instance_group = QGroupBox(self.translation_manager.get_translation("Instances"))
        self.instance_layout = QVBoxLayout()
        self.instance_group.setLayout(self.instance_layout)
        main_layout.addWidget(self.instance_group)

        # Control buttons
        button_layout = QHBoxLayout()
        self.root_toggle_button = QPushButton(self.translation_manager.get_translation("Toggle Root"))
        self.root_toggle_button.clicked.connect(self.handle_toggle_root)
        button_layout.addWidget(self.root_toggle_button)

        self.rw_toggle_button = QPushButton(self.translation_manager.get_translation("Toggle R/W"))
        self.rw_toggle_button.clicked.connect(self.handle_toggle_rw)
        button_layout.addWidget(self.rw_toggle_button)
        main_layout.addLayout(button_layout)

        # Status label and progress bar
        self.status_label = QLabel(self.translation_manager.get_translation("Ready"))
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self.setLayout(main_layout)
        QTimer.singleShot(0, self.initialize_paths_and_instances)

    def change_language(self, index: int) -> None:
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

    def update_instance_checkboxes_text(self) -> None:
        for name, widgets in self.instance_checkboxes.items():
            data = self.instance_data.get(name, {})
            if data:
                root_status = self.translation_manager.get_translation("On") if data.get("root_enabled") else self.translation_manager.get_translation("Off")
                rw_status = self.translation_manager.get_translation("On") if data.get("rw_mode") == "Normal" else self.translation_manager.get_translation("Off")
                widgets["root_status"].setText(self.translation_manager.get_translation("Root: {}").format(root_status))
                widgets["rw_status"].setText(self.translation_manager.get_translation("R/W: {}").format(rw_status))

    def check_and_kill_bluestacks(self) -> None:
        self.status_label.setText(self.translation_manager.get_translation("BlueStacks is running. Terminating process..."))
        self.progress_bar.show()
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

    def initialize_paths_and_instances(self) -> None:
        self.status_label.setText(self.translation_manager.get_translation("BlueStacks Path: Loading..."))
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

    def update_instance_data(self) -> None:
        if not self.config_path:
            self.status_label.setText(self.translation_manager.get_translation("Error: Config path not initialized."))
            logging.error("Config path not initialized.")
            return
        try:
            new_data = {}
            with open(self.config_path, "r") as f:
                for line in f:
                    if line.startswith(INSTANCE_PREFIX) and ENABLE_ROOT_KEY in line:
                        parts = line.strip().split("=")
                        if parts:
                            key_parts = parts[0].split(".")
                            if len(key_parts) >= 3:
                                instance = key_parts[2]
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

    def detect_instances(self) -> None:
        if not self.instance_data:
            return

        current_instances = set(self.instance_checkboxes.keys())
        new_instances = set(self.instance_data.keys())

        # Add new instances
        for name in new_instances - current_instances:
            data = self.instance_data[name]
            hbox = QHBoxLayout()
            checkbox = QCheckBox(name)
            root_status = QLineEdit(self.translation_manager.get_translation("Root: {}").format(
                self.translation_manager.get_translation("On") if data.get("root_enabled") else self.translation_manager.get_translation("Off")))
            root_status.setReadOnly(True)
            rw_status = QLineEdit(self.translation_manager.get_translation("R/W: {}").format(
                self.translation_manager.get_translation("On") if data.get("rw_mode") == "Normal" else self.translation_manager.get_translation("Off")))
            rw_status.setReadOnly(True)
            hbox.addWidget(checkbox)
            hbox.addWidget(root_status)
            hbox.addWidget(rw_status)
            self.instance_layout.addLayout(hbox)
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
                self.translation_manager.get_translation("On") if data.get("root_enabled") else self.translation_manager.get_translation("Off")
            )
            self.instance_checkboxes[name]["rw_status"].setText(
                self.translation_manager.get_translation("On") if data.get("rw_mode") == "Normal" else self.translation_manager.get_translation("Off")
            )

        # Remove instances no longer present
        for name in current_instances - new_instances:
            widgets = self.instance_checkboxes.pop(name)
            self.instance_layout.removeItem(widgets["layout"])
            widgets["layout"].deleteLater()
            widgets["checkbox"].deleteLater()
            widgets["root_status"].deleteLater()
            widgets["rw_status"].deleteLater()

    def update_instance_checkboxes(self) -> None:
        self.detect_instances()

    # ---- Toggle Operations using Background Worker ----
    def handle_toggle_root(self) -> None:
        if self.is_toggling:
            return
        self.is_toggling = True
        self.status_label.setText(self.translation_manager.get_translation("Toggling Root..."))
        self.progress_bar.show()
        self.root_toggle_button.setEnabled(False)

        self.thread = QThread()
        self.worker = Worker(self.toggle_root_operation)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_toggle_finished)
        self.worker.error.connect(self.on_worker_error)
        self.thread.start()

    def toggle_root_operation(self) -> None:
        self.check_and_kill_bluestacks()

        if not self.config_path:
            raise Exception(self.translation_manager.get_translation("Error: bluestacks.conf not found."))

        selected = [name for name, widgets in self.instance_checkboxes.items() if widgets["checkbox"].isChecked()]
        if not selected:
            raise Exception(self.translation_manager.get_translation("No instances selected to toggle root."))

        # Show reminder if enabling root
        if any(not self.instance_data[name]["root_enabled"] for name in selected):
            popup = QMessageBox()
            popup.setWindowTitle(self.translation_manager.get_translation("Confirmation"))
            popup.setIcon(QMessageBox.Information)
            popup.setText(self.translation_manager.get_translation("Magisk install reminder"))
            popup.exec_()

        for name in selected:
            current_state = self.instance_data[name]["root_enabled"]
            new_state = "0" if current_state else "1"
            config_handler.modify_config_file(self.config_path, f"{INSTANCE_PREFIX}{name}{ENABLE_ROOT_KEY}", new_state)
            config_handler.modify_config_file(self.config_path, FEATURE_ROOTING_KEY, new_state)
            self.instance_data[name]["root_enabled"] = not current_state
            status_text = self.translation_manager.get_translation("On") if not current_state else self.translation_manager.get_translation("Off")
            self.instance_checkboxes[name]["root_status"].setText(self.translation_manager.get_translation("Root: {}").format(status_text))
            logging.info(self.translation_manager.get_translation("Root toggled for instance: {} to {}").format(name, status_text))

    def handle_toggle_rw(self) -> None:
        if self.is_toggling:
            return
        self.is_toggling = True
        self.status_label.setText(self.translation_manager.get_translation("Toggling R/W..."))
        self.progress_bar.show()
        self.rw_toggle_button.setEnabled(False)

        self.thread = QThread()
        self.worker = Worker(self.toggle_rw_operation)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_toggle_finished)
        self.worker.error.connect(self.on_worker_error)
        self.thread.start()

    def toggle_rw_operation(self) -> None:
        self.check_and_kill_bluestacks()

        if not self.bluestacks_path:
            raise Exception(self.translation_manager.get_translation("Error: BlueStacks path not found."))

        selected = [name for name, widgets in self.instance_checkboxes.items() if widgets["checkbox"].isChecked()]
        if not selected:
            raise Exception(self.translation_manager.get_translation("No instances selected to toggle R/W."))

        for name in selected:
            engine_path = os.path.join(self.bluestacks_path, name)
            instance_path = os.path.join(self.bluestacks_path, name)
            current_mode = self.instance_data[name]["rw_mode"]
            new_mode = "Normal" if current_mode == "Readonly" else "Readonly"

            bstk_file_path = os.path.join(engine_path, "Android.bstk.in")
            if not os.path.exists(bstk_file_path):
                logging.error(f"BSTK file not found at {bstk_file_path}")
                continue

            instance_handler.modify_instance_files(engine_path, instance_path, [FASTBOOT_VDI, ROOT_VHD], new_mode)
            self.instance_data[name]["rw_mode"] = new_mode
            status_text = self.translation_manager.get_translation("On") if new_mode == "Normal" else self.translation_manager.get_translation("Off")
            self.instance_checkboxes[name]["rw_status"].setText(self.translation_manager.get_translation("R/W: {}").format(status_text))
            logging.info(self.translation_manager.get_translation("R/W toggled for instance: {} to {}").format(name, new_mode))

    def on_toggle_finished(self) -> None:
        self.is_toggling = False
        self.progress_bar.hide()
        self.root_toggle_button.setEnabled(True)
        self.rw_toggle_button.setEnabled(True)
        self.thread.quit()
        self.thread.wait()
        self.status_label.setText(self.translation_manager.get_translation("Ready"))

    def on_worker_error(self, error_message: str) -> None:
        self.status_label.setText(error_message)
        logging.error(error_message)
        self.is_toggling = False
        self.progress_bar.hide()
        self.root_toggle_button.setEnabled(True)
        self.rw_toggle_button.setEnabled(True)
        self.thread.quit()
        self.thread.wait()

    def update_instance_statuses(self) -> None:
        if self.is_toggling:
            return
        self.update_instance_data()
        for name, widgets in self.instance_checkboxes.items():
            if name in self.instance_data:
                try:
                    root_text = self.translation_manager.get_translation("On") if self.instance_data[name]["root_enabled"] else self.translation_manager.get_translation("Off")
                    rw_text = self.translation_manager.get_translation("On") if self.instance_data[name]["rw_mode"] == "Normal" else self.translation_manager.get_translation("Off")
                    widgets["root_status"].setText(self.translation_manager.get_translation("Root: {}").format(root_text))
                    widgets["rw_status"].setText(self.translation_manager.get_translation("R/W: {}").format(rw_text))
                except Exception as e:
                    error_message = self.translation_manager.get_translation("Error updating status for {}: {}").format(name, e)
                    self.status_label.setText(error_message)
                    logging.exception(error_message)
            else:
                logging.warning(self.translation_manager.get_translation("Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.").format(name))

    def closeEvent(self, event) -> None:
        self.timer.stop()
        logging.info("BlueStacks Root GUI closed.")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BluestacksRootToggle()
    window.show()
    logging.info("BlueStacks Root GUI started.")
    sys.exit(app.exec_())
