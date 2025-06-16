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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    except Exception:
        base_path = os.path.abspath(".")

    path = os.path.join(base_path, relative_path)
    return path


class Worker(QObject):
    """
    Runs a function in a separate thread and emits signals upon completion or error.
    """

    finished = pyqtSignal()
    error = pyqtSignal(str)
    instance_status_updated = pyqtSignal(str, str, str)
    operation_message = pyqtSignal(str, str)

    def __init__(self, func, *args, **kwargs):
        """
        Initializes the worker.

        Args:
            func: The function to execute in the background thread.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        """Executes the target function and handles exceptions."""
        try:
            self.func(*self.args, **self.kwargs)
            self.finished.emit()
        except Exception as e:
            logger.exception("Critical error during worker execution.")
            self.error.emit(f"Operation failed: {e}")


class TranslationManager:
    """Manages UI translations based on selected language."""

    def __init__(self):
        """Initializes with supported languages and default translations."""
        self.languages = {"en": "English", "ja": "日本語"}
        self.current_language = "en"
        self.translations = {
            "en": {
                constants.APP_NAME: constants.APP_NAME,
                "BlueStacks Path: Loading...": "BlueStacks Path: Loading...",
                "BlueStacks Path: Not Found": "BlueStacks Path: Not Found",
                "BlueStacks Path: {}": "BlueStacks Path: {}",
                "Installations Found:": "Installations Found:",
                "Instances": "Instances",
                "Toggle Root": "Toggle Root",
                "Toggle R/W": "Toggle R/W",
                "Ready": "Ready",
                "On": "On",
                "Off": "Off",
                "Unknown": "Unknown",
                "Language": "Language",
                "Error: Config path not initialized.": (
                    "Error: Config path not initialized."
                ),
                "Error reading config: File not found.": (
                    "Error reading config: File not found."
                ),
                "Error reading config: {}": "Error reading config: {}",
                "Root: {}": "Root: {}",
                "R/W: {}": "R/W: {}",
                "No BlueStacks installations found.": "No BlueStacks installations found.",
                "Error: bluestacks.conf not found. Cannot toggle root.": (
                    "Error: bluestacks.conf not found. Cannot toggle root."
                ),
                "No instances selected to toggle root.": (
                    "No instances selected to toggle root."
                ),
                "Root toggled for instance: {} to {}": (
                    "Root toggled for instance: {} to {}"
                ),
                "Error toggling root for {}: {}": "Error toggling root for {}: {}",
                "Error: BlueStacks data path not found for instance. Cannot toggle R/W.": (
                    "Error: BlueStacks data path not found for instance. Cannot toggle R/W."
                ),
                "Error: Instance path for '{}' not found. Cannot toggle R/W.": (
                    "Error: Instance path for '{}' not found. Cannot toggle R/W."
                ),
                "No instances selected to toggle R/W.": (
                    "No instances selected to toggle R/W."
                ),
                "R/W toggled for instance: {} to {}": (
                    "R/W toggled for instance: {} to {}"
                ),
                "Error toggling R/W for {}: {}": "Error toggling R/W for {}: {}",
                "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.": (
                    "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync."
                ),
                "Error updating status for {}: {}": "Error updating status for {}: {}",
                "Config file not found: {}": "Config file not found: {}",
                "Error reading config file: {}": "Error reading config file: {}",
                "Checking if BlueStacks is running...": (
                    "Checking if BlueStacks is running..."
                ),
                "BlueStacks is running. Attempting termination...": (
                    "BlueStacks is running. Attempting termination..."
                ),
                "BlueStacks termination attempted.": (
                    "BlueStacks termination attempted."
                ),
                "No running BlueStacks processes found.": (
                    "No running BlueStacks processes found."
                ),
                "Error during BlueStacks termination check/attempt: {}": (
                    "Error during BlueStacks termination check/attempt: {}"
                ),
                "Toggling Root...": "Toggling Root...",
                "Toggling R/W...": "Toggling R/W...",
                "Please restart BlueStacks for R/W changes to take effect.": (
                    "Please restart BlueStacks for R/W changes to take effect."
                ),
                "Confirmation": "Confirmation",
                "Magisk Install Reminder": "Kitsune Mask Install Reminder",
                "Magisk install reminder text": (
                    "After Kitsune Mask has installed to the System partition successfully, make sure you come back and turn Root Off (using Toggle Root). Leave R/W On."
                ),
                "Operation completed.": "Operation completed.",
                "Operation completed with errors. Check log.": (
                    "Operation completed with errors. Check log."
                ),
                "Toggling Root for {}...": "Toggling Root for {}...",
                "Toggling R/W for {}...": "Toggling R/W for {}...",
                "Error preparing root toggle: {}": "Error preparing root toggle: {}",
                "Error preparing R/W toggle: {}": "Error preparing R/W toggle: {}",
                "Operation failed: {}": "Operation failed: {}",
            },
            "ja": {
                constants.APP_NAME: f"{constants.APP_NAME} (日本語)",
                "BlueStacks Path: Loading...": "BlueStacks パス: 読み込み中...",
                "BlueStacks Path: Not Found": "BlueStacks パス: 見つかりません",
                "BlueStacks Path: {}": "BlueStacks パス: {}",
                "Installations Found:": "見つかったインストール:",
                "Instances": "インスタンス",
                "Toggle Root": "ルート切り替え",
                "Toggle R/W": "R/W切り替え",
                "Ready": "準備完了",
                "On": "オン",
                "Off": "オフ",
                "Unknown": "不明",
                "Language": "言語",
                "Error: Config path not initialized.": (
                    "エラー：設定パスが初期化されていません。"
                ),
                "Error reading config: File not found.": (
                    "エラー：設定ファイルの読み込みエラー：ファイルが見つかりません。"
                ),
                "Error reading config: {}": "エラー：設定ファイルの読み込みエラー：{}",
                "Root: {}": "ルート: {}",
                "R/W: {}": "R/W: {}",
                "No BlueStacks installations found.": "BlueStacksのインストールが見つかりません。",
                "Error: bluestacks.conf not found. Cannot toggle root.": (
                    "エラー：bluestacks.conf が見つかりません。ルートを切り替えられません。"
                ),
                "No instances selected to toggle root.": (
                    "ルートを切り替えるインスタンスが選択されていません。"
                ),
                "Root toggled for instance: {} to {}": (
                    "インスタンス {} のルートを {} に切り替えました"
                ),
                "Error toggling root for {}: {}": "{} のルート切り替えエラー：{}",
                "Error: BlueStacks data path not found for instance. Cannot toggle R/W.": (
                    "エラー：インスタンスのBlueStacksデータパスが見つかりません。R/Wを切り替えられません。"
                ),
                "Error: Instance path for '{}' not found. Cannot toggle R/W.": (
                    "エラー: インスタンス '{}' のパスが見つかりません。R/W を切り替えられません。"
                ),
                "No instances selected to toggle R/W.": (
                    "R/W を切り替えるインスタンスが選択されていません。"
                ),
                "R/W toggled for instance: {} to {}": (
                    "インスタンス {} の R/W を {} に切り替えました"
                ),
                "Error toggling R/W for {}: {}": "{} の R/W 切り替えエラー：{}",
                "Instance '{}' found in checkboxes but not in instance data. UI may be out of sync.": (
                    "インスタンス '{}' がチェックボックスにありますが、インスタンスデータに見つかりません。UI が同期していない可能性があります。"
                ),
                "Error updating status for {}: {}": "{} のステータス更新エラー：{}",
                "Config file not found: {}": "設定ファイルが見つかりません: {}",
                "Error reading config file: {}": "設定ファイルの読み込みエラー: {}",
                "Checking if BlueStacks is running...": (
                    "BlueStacksが実行中か確認しています..."
                ),
                "BlueStacks is running. Attempting termination...": (
                    "BlueStacks が実行中です。終了を試みています..."
                ),
                "BlueStacks termination attempted.": (
                    "BlueStacks の終了が試みられました。"
                ),
                "No running BlueStacks processes found.": (
                    "実行中の BlueStacks プロセスが見つかりませんでした。"
                ),
                "Error during BlueStacks termination check/attempt: {}": (
                    "BlueStacks の終了確認/試行中にエラーが発生しました：{}"
                ),
                "Toggling Root...": "ルート切り替え中...",
                "Toggling R/W...": "R/W切り替え中...",
                "Please restart BlueStacks for R/W changes to take effect.": (
                    "R/W変更を有効にするにはBlueStacksを再起動してください。"
                ),
                "Confirmation": "確認",
                "Magisk Install Reminder": "Kitsune Mask インストール リマインダー",
                "Magisk install reminder text": (
                    "Kitsune Maskがシステムパーティションに正常にインストールされた後、必ずここに戻り、「ルート切り替え」を使用してルートをオフにしてください。R/Wはオンのままにしてください。"
                ),
                "Operation completed.": "操作が完了しました。",
                "Operation completed with errors. Check log.": (
                    "操作はエラーで完了しました。ログを確認してください。"
                ),
                "Toggling Root for {}...": "{} のルートを切り替え中...",
                "Toggling R/W for {}...": "{} の R/W を切り替え中...",
                "Error preparing root toggle: {}": "ルート切り替え準備エラー: {}",
                "Error preparing R/W toggle: {}": "R/W 切り替え準備エラー: {}",
                "Operation failed: {}": "操作に失敗しました: {}",
            },
        }

    def get_translation(self, text_key: str) -> str:
        """
        Retrieves the translation for a given text key in the current language.

        Args:
            text_key: The English text key representing the string to translate.

        Returns:
            The translated string, or the original key if no translation is found.
        """
        return self.translations.get(
            self.current_language, self.translations["en"]
        ).get(text_key, text_key)


class BluestacksRootToggle(QWidget):
    """Main application window for toggling BlueStacks root and R/W settings."""

    def __init__(self):
        """Initializes the application window, UI components, and timer."""
        super().__init__()
        self.translation_manager = TranslationManager()
        self.installations: List[registry_handler.Installation] = []
        self.instance_data: Dict[str, Dict[str, Any]] = {}
        self.instance_checkboxes: Dict[str, Dict[str, Any]] = {}
        self.is_toggling: bool = False
        self.background_thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self.operation_had_errors: bool = False
        self._config_missing_logged: bool = False

        self.setWindowTitle(
            self.translation_manager.get_translation(constants.APP_NAME)
        )
        self._set_icon()

        self.status_refresh_timer = QTimer(self)
        self.status_refresh_timer.timeout.connect(
            lambda: self.update_instance_statuses(preserve_selection=True)
        )

        self.init_ui()
        QTimer.singleShot(0, self.initialize_paths_and_instances)

    def _set_icon(self):
        """Sets the window icon if the icon file exists."""
        try:
            icon_path = resource_path(constants.ICON_FILENAME)
            app_icon = QIcon(icon_path)
            if not app_icon.isNull():
                self.setWindowIcon(app_icon)
                logger.debug(f"Window icon set from {icon_path}")
            else:
                logger.warning(
                    f"Icon file loaded from {icon_path} but QIcon is null. Check icon validity/path."
                )
        except Exception as e:
            logger.error(f"Error setting window icon using resource_path: {e}")

    def init_ui(self) -> None:
        """Creates and arranges the UI widgets."""
        main_layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        lang_label = QLabel(self.translation_manager.get_translation("Language") + ":")
        self.language_combo = QComboBox()
        for code, name in self.translation_manager.languages.items():
            self.language_combo.addItem(name, code)
        current_lang_code = self.translation_manager.current_language
        index = self.language_combo.findData(current_lang_code)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.language_combo.currentIndexChanged.connect(self.change_language)
        top_layout.addWidget(lang_label)
        top_layout.addWidget(self.language_combo)
        top_layout.addSpacerItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        main_layout.addLayout(top_layout)

        self.path_label = QLabel(
            self.translation_manager.get_translation("BlueStacks Path: Loading...")
        )
        self.path_label.setWordWrap(True)
        main_layout.addWidget(self.path_label)

        self.instance_group = QGroupBox(
            self.translation_manager.get_translation("Instances")
        )

        self.instance_layout = QGridLayout()
        # FIX: Adjust column stretch to give more room for the instance name
        self.instance_layout.setColumnStretch(0, 4) # Checkbox name
        self.instance_layout.setColumnStretch(1, 1) # Root status
        self.instance_layout.setColumnStretch(2, 1) # R/W status
        self.instance_layout.setHorizontalSpacing(15)
        self.instance_layout.setVerticalSpacing(5)
        self.instance_group.setLayout(self.instance_layout)
        main_layout.addWidget(self.instance_group)

        button_layout = QHBoxLayout()
        self.root_toggle_button = QPushButton(
            self.translation_manager.get_translation("Toggle Root")
        )
        self.root_toggle_button.clicked.connect(self.handle_toggle_root)
        self.root_toggle_button.setToolTip(
            "Enable/Disable root access setting in bluestacks.conf"
        )
        button_layout.addWidget(self.root_toggle_button)

        self.rw_toggle_button = QPushButton(
            self.translation_manager.get_translation("Toggle R/W")
        )
        self.rw_toggle_button.clicked.connect(self.handle_toggle_rw)
        self.rw_toggle_button.setToolTip(
            "Switch instance disk files between Readonly and Read/Write (Normal)"
        )
        button_layout.addWidget(self.rw_toggle_button)
        main_layout.addLayout(button_layout)

        self.status_label = QLabel(self.translation_manager.get_translation("Ready"))
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        main_layout.addStretch(1)

        self.setLayout(main_layout)
        # FIX: Increase minimum width to prevent truncation
        self.setMinimumWidth(550)

    def change_language(self, index: int) -> None:
        """Handles language change from the ComboBox."""
        lang_code = self.language_combo.itemData(index)
        if lang_code and lang_code != self.translation_manager.current_language:
            self.translation_manager.current_language = lang_code
            logger.info(f"Language changed to: {lang_code}")
            self._update_ui_text()
            self.status_refresh_timer.stop()
            self.initialize_paths_and_instances()

    def _update_ui_text(self) -> None:
        """Updates all static translatable text elements in the UI."""
        logger.debug("Updating static UI text elements for new language.")
        self.setWindowTitle(
            self.translation_manager.get_translation(constants.APP_NAME)
        )
        self.path_label.setText(
            self.translation_manager.get_translation("BlueStacks Path: Loading...")
        )
        self.instance_group.setTitle(
            self.translation_manager.get_translation("Instances")
        )
        self.root_toggle_button.setText(
            self.translation_manager.get_translation("Toggle Root")
        )
        self.rw_toggle_button.setText(
            self.translation_manager.get_translation("Toggle R/W")
        )
        self.status_label.setText(self.translation_manager.get_translation("Ready"))
        try:
            lang_label_widget = self.language_combo.parent().layout().itemAt(0).widget()
            if isinstance(lang_label_widget, QLabel):
                lang_label_widget.setText(
                    self.translation_manager.get_translation("Language") + ":"
                )
        except AttributeError:
            logger.warning("Could not find language label to update text.")
        # FIX: No longer need to call update_instance_checkboxes_text as it's merged
        self.update_instance_checkboxes(preserve_selection=True)

    def initialize_paths_and_instances(self) -> None:
        """
        Fetches all BlueStacks installations from registry, updates instance data, and populates the UI.
        """
        logger.info("Initializing BlueStacks paths and instances...")
        self.status_label.setText(
            self.translation_manager.get_translation("BlueStacks Path: Loading...")
        )
        QApplication.processEvents()

        self._clear_instance_widgets()
        self.instance_data = {}
        self.instance_checkboxes = {}

        self.installations = registry_handler.get_all_bluestacks_installations()

        if not self.installations:
            error_message = self.translation_manager.get_translation(
                "No BlueStacks installations found."
            )
            self.path_label.setText(error_message)
            self.status_label.setText(error_message)
            logger.error(error_message)
            self.status_refresh_timer.stop()
            return

        path_details = [self.translation_manager.get_translation("Installations Found:")]
        for inst in self.installations:
            path_details.append(f"  - {inst['source']}: {inst['user_path']}")
        self.path_label.setText("\n".join(path_details))

        self.update_instance_data()
        self.update_instance_checkboxes(preserve_selection=False)

        self.status_label.setText(self.translation_manager.get_translation("Ready"))

        if not self.status_refresh_timer.isActive():
            self.status_refresh_timer.start(constants.REFRESH_INTERVAL_MS)

    def update_instance_data(self) -> None:
        """
        Reads all bluestacks.conf files and instance R/W status, then filters for valid instances.
        """
        if not self.installations:
            return

        logger.debug("Updating internal instance data cache...")
        all_found_instances: Dict[str, Dict[str, Any]] = {}
        for inst in self.installations:
            source_id, config_path, data_path = inst["source"], inst["config_path"], inst["data_path"]
            
            root_statuses = {}
            if os.path.isfile(config_path):
                try:
                    root_statuses = config_handler.get_all_instance_root_statuses(config_path)
                except Exception as e:
                    logger.error(f"Failed to read config {config_path}: {e}")
            else:
                 logger.warning(f"Config file not found for {source_id}: {config_path}")

            disk_instances = {entry for entry in (os.listdir(data_path) if os.path.isdir(data_path) else []) if os.path.isdir(os.path.join(data_path, entry))}
            all_instance_names = set(root_statuses.keys()) | disk_instances

            for name in sorted(all_instance_names):
                unique_id = f"{name} ({source_id})"
                instance_dir_path = os.path.join(data_path, name)
                
                rw_mode = constants.MODE_UNKNOWN
                if os.path.isdir(instance_dir_path):
                    try:
                        is_readonly = instance_handler.is_instance_readonly(instance_dir_path)
                        if is_readonly is True: rw_mode = constants.MODE_READONLY
                        elif is_readonly is False: rw_mode = constants.MODE_READWRITE
                    except Exception as e:
                         logger.exception(f"Error checking R/W status for {unique_id}: {e}")

                all_found_instances[unique_id] = {
                    "unique_id": unique_id,
                    "original_name": name,
                    "source_app": source_id,
                    "root_enabled": root_statuses.get(name),
                    "rw_mode": rw_mode,
                    "data_path": instance_dir_path,
                    "config_path": config_path,
                }
        
        # FIX: Filter out any instances with an unknown status before storing them
        self.instance_data = {
            uid: data for uid, data in all_found_instances.items()
            if data["root_enabled"] is not None and data["rw_mode"] != constants.MODE_UNKNOWN
        }
        
        omitted_count = len(all_found_instances) - len(self.instance_data)
        if omitted_count > 0:
            logger.info(f"Instance data updated. Displaying {len(self.instance_data)} instances, omitted {omitted_count} due to unknown/incomplete status.")
        else:
            logger.debug(f"Instance data cache updated: {len(self.instance_data)} unique instances")

    def _clear_instance_widgets(self):
        """Removes all widgets currently in the instance_layout grid."""
        while self.instance_layout.count():
            item = self.instance_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.instance_checkboxes = {}

    def update_instance_checkboxes(self, preserve_selection: bool = True) -> None:
        """
        Clears and rebuilds the instance grid UI based on current instance_data.
        Ensures column alignment using QGridLayout.
        """
        logger.debug("Rebuilding instance checkboxes UI grid...")
        previous_selection = {
            uid for uid, widgets in self.instance_checkboxes.items() if widgets["checkbox"].isChecked()
        } if preserve_selection else set()
        
        self._clear_instance_widgets()

        if not self.instance_data:
            logger.debug("No instance data found, grid will be empty.")
            return

        # Get translated text once before the loop
        on_text = self.translation_manager.get_translation("On")
        off_text = self.translation_manager.get_translation("Off")
        root_fmt = self.translation_manager.get_translation("Root: {}")
        rw_fmt = self.translation_manager.get_translation("R/W: {}")

        for row, unique_id in enumerate(sorted(self.instance_data.keys())):
            data = self.instance_data[unique_id]
            checkbox = QCheckBox(unique_id)
            checkbox.setChecked(unique_id in previous_selection)
            
            # FIX: Determine status text immediately and create the labels
            root_text = on_text if data["root_enabled"] else off_text
            rw_text = on_text if data["rw_mode"] == constants.MODE_READWRITE else off_text
            
            root_status_label = QLabel(root_fmt.format(root_text))
            rw_status_label = QLabel(rw_fmt.format(rw_text))

            self.instance_layout.addWidget(checkbox, row, 0)
            self.instance_layout.addWidget(root_status_label, row, 1)
            self.instance_layout.addWidget(rw_status_label, row, 2)

            # Store all widgets for potential real-time updates by the worker
            self.instance_checkboxes[unique_id] = {
                "checkbox": checkbox, "root_status": root_status_label, "rw_status": rw_status_label
            }

    def _start_worker(self, operation_func, status_message_key: str) -> bool:
        if self.is_toggling:
            logger.warning("Operation already in progress. Ignoring request.")
            QMessageBox.warning(
                self, "Busy", "An operation is already in progress. Please wait."
            )
            return False

        self.is_toggling = True
        self.operation_had_errors = False
        self.status_label.setText(
            self.translation_manager.get_translation(status_message_key)
        )
        self.progress_bar.setVisible(True)
        self.root_toggle_button.setEnabled(False)
        self.rw_toggle_button.setEnabled(False)
        self.language_combo.setEnabled(False)

        self.background_thread = QThread(self)
        self.worker = Worker(operation_func)
        self.worker.moveToThread(self.background_thread)

        self.worker.finished.connect(self.on_operation_finished)
        self.worker.error.connect(self.on_worker_critical_error)
        self.worker.instance_status_updated.connect(self._update_instance_ui_status)
        self.worker.operation_message.connect(self._show_operation_message)

        self.background_thread.started.connect(self.worker.run)
        self.background_thread.finished.connect(self.worker.deleteLater)
        self.background_thread.finished.connect(self.background_thread.deleteLater)
        self.worker.finished.connect(self._trigger_thread_quit)
        self.worker.error.connect(self._trigger_thread_quit)

        logger.info(f"Starting background worker for: {operation_func.__name__}")
        self.background_thread.start()
        return True

    @pyqtSlot()
    def _trigger_thread_quit(self):
        if self.background_thread and self.background_thread.isRunning():
            logger.debug("Requesting background thread quit.")
            self.background_thread.quit()

    def _cleanup_after_operation(self):
        logger.debug("Cleaning up UI after operation.")
        self.is_toggling = False
        self.progress_bar.setVisible(False)
        self.root_toggle_button.setEnabled(True)
        self.rw_toggle_button.setEnabled(True)
        self.language_combo.setEnabled(True)
        self.worker = None
        self.background_thread = None
        logger.debug("Toggle cleanup complete.")

    @pyqtSlot()
    def on_operation_finished(self) -> None:
        logger.info("Background worker finished successfully.")
        if self.operation_had_errors:
            final_message = self.translation_manager.get_translation(
                "Operation completed with errors. Check log."
            )
            logger.warning(final_message)
        else:
            final_message = self.translation_manager.get_translation(
                "Operation completed."
            )
            logger.info(final_message)
        self.status_label.setText(final_message)
        self.status_label.setStyleSheet("")
        self._cleanup_after_operation()
        QTimer.singleShot(
            500, lambda: self.update_instance_statuses(preserve_selection=True)
        )

    @pyqtSlot(str)
    def on_worker_critical_error(self, error_message: str) -> None:
        logger.error(f"Worker emitted critical error: {error_message}")
        self.status_label.setText(error_message)
        self.status_label.setStyleSheet("color: red;")
        QMessageBox.critical(self, "Critical Error", error_message)
        self._cleanup_after_operation()

    def handle_toggle_root(self) -> None:
        logger.info("Toggle Root button clicked.")
        selected_count = sum(
            1 for w in self.instance_checkboxes.values() if w["checkbox"].isChecked()
        )
        if selected_count == 0:
            QMessageBox.information(
                self,
                "No Selection",
                self.translation_manager.get_translation(
                    "No instances selected to toggle root."
                ),
            )
            return
        if not self._start_worker(
            self._perform_root_toggle_operation, "Toggling Root..."
        ):
            logger.warning("Failed to start root toggle worker (maybe busy?).")

    def handle_toggle_rw(self) -> None:
        logger.info("Toggle R/W button clicked.")
        selected_count = sum(
            1 for w in self.instance_checkboxes.values() if w["checkbox"].isChecked()
        )
        if selected_count == 0:
            QMessageBox.information(
                self,
                "No Selection",
                self.translation_manager.get_translation(
                    "No instances selected to toggle R/W."
                ),
            )
            return
        if not self._start_worker(self._perform_rw_toggle_operation, "Toggling R/W..."):
            logger.warning("Failed to start R/W toggle worker (maybe busy?).")

    def _check_and_kill_bluestacks_worker(self) -> None:
        if not self.worker:
            return
        self.worker.operation_message.emit(
            "info",
            self.translation_manager.get_translation(
                "Checking if BlueStacks is running..."
            ),
        )
        try:
            if not instance_handler.is_bluestacks_running():
                logger.info("No running BlueStacks processes found.")
                self.worker.operation_message.emit(
                    "info",
                    self.translation_manager.get_translation(
                        "No running BlueStacks processes found."
                    ),
                )
                return
            self.worker.operation_message.emit(
                "info",
                self.translation_manager.get_translation(
                    "BlueStacks is running. Attempting termination..."
                ),
            )
            attempted = instance_handler.terminate_bluestacks()
            if attempted:
                logger.info("BlueStacks termination attempt finished.")
                self.worker.operation_message.emit(
                    "info",
                    self.translation_manager.get_translation(
                        "BlueStacks termination attempted."
                    ),
                )
                QThread.msleep(constants.PROCESS_TERMINATION_WAIT_MS)
        except Exception as e:
            error_message = self.translation_manager.get_translation(
                "Error during BlueStacks termination check/attempt: {}"
            ).format(e)
            logger.exception(error_message)
            raise Exception(error_message) from e

    def _toggle_single_instance_rw(self, unique_id: str) -> None:
        """Toggles R/W for a single, uniquely identified instance."""
        if not self.worker:
            raise Exception("Worker is not available.")
        
        instance = self.instance_data.get(unique_id)
        if not instance:
             raise Exception(f"Instance data missing for {unique_id}.")
        
        instance_dir_path = instance.get("data_path")
        if not instance_dir_path or not os.path.isdir(instance_dir_path):
            raise FileNotFoundError(
                self.translation_manager.get_translation("Error: Instance path for '{}' not found. Cannot toggle R/W.").format(instance.get("original_name"))
            )
            
        current_mode = instance.get("rw_mode", constants.MODE_UNKNOWN)
        if current_mode == constants.MODE_UNKNOWN:
            raise Exception(
                f"Cannot toggle R/W for '{unique_id}': Current status is Unknown."
            )
        new_mode = (
            constants.MODE_READONLY
            if current_mode == constants.MODE_READWRITE
            else constants.MODE_READWRITE
        )
        on_off_text = (
            self.translation_manager.get_translation("On")
            if new_mode == constants.MODE_READWRITE
            else self.translation_manager.get_translation("Off")
        )
        try:
            instance_handler.modify_instance_files(instance_dir_path, new_mode)
            self.instance_data[unique_id]["rw_mode"] = new_mode
            self.worker.instance_status_updated.emit(unique_id, "rw", on_off_text)
            log_mode_display = f"{on_off_text} ({new_mode})"
            logger.info(
                self.translation_manager.get_translation(
                    "R/W toggled for instance: {} to {}"
                ).format(unique_id, log_mode_display)
            )
        except Exception as e:
            logger.exception(f"Failed to toggle R/W for instance {unique_id}")
            raise Exception(f"Failed to modify instance files for {unique_id}: {e}") from e

    def _perform_root_toggle_operation(self) -> None:
        """
        FIXED: This operation toggles root for selected instances and then sets the
        global root flag based on the final state of ALL instances per config file.
        This prevents toggling one instance from breaking others.
        """
        if not self.worker:
            return
        try:
            self._check_and_kill_bluestacks_worker()
        except Exception as e:
            self.worker.error.emit(str(e))
            return

        selected_ids = {uid for uid, w in self.instance_checkboxes.items() if w["checkbox"].isChecked()}
        if not selected_ids:
            return

        # Show reminder if the user is turning root ON for any instance
        show_reminder = any(
            not self.instance_data.get(uid, {}).get("root_enabled", False)
            for uid in selected_ids
        )
        if show_reminder:
            self.worker.operation_message.emit("reminder", "show_magisk_reminder")

        # Group all instances by their config file path to process them in batches
        configs_map: Dict[str, List[Dict[str, Any]]] = {}
        for instance in self.instance_data.values():
            path = instance["config_path"]
            if path not in configs_map:
                configs_map[path] = []
            configs_map[path].append(instance)

        # --- Main Logic ---
        for config_path, instances_in_config in configs_map.items():
            # Check if this config file is affected by the user's selection
            if not any(inst["unique_id"] in selected_ids for inst in instances_in_config):
                continue  # Skip this config file if no instances in it were selected

            try:
                # 1. Toggle the individual root flags for selected instances
                for instance in instances_in_config:
                    unique_id = instance["unique_id"]
                    if unique_id not in selected_ids:
                        continue  # Only toggle selected instances

                    self.worker.operation_message.emit(
                        "info",
                        self.translation_manager.get_translation("Toggling Root for {}...").format(unique_id)
                    )
                    
                    original_name = instance["original_name"]
                    current_state = instance.get("root_enabled", False)
                    new_state_bool = not current_state
                    new_state_val = "1" if new_state_bool else "0"
                    
                    setting_key = f"{constants.INSTANCE_PREFIX}{original_name}{constants.ENABLE_ROOT_KEY}"
                    config_handler.modify_config_file(config_path, setting_key, new_state_val)

                    # Update internal state so the next step is accurate
                    instance["root_enabled"] = new_state_bool
                    
                    # Emit UI update signal
                    on_off_text = self.translation_manager.get_translation("On") if new_state_bool else self.translation_manager.get_translation("Off")
                    self.worker.instance_status_updated.emit(unique_id, "root", on_off_text)

                # 2. Determine the new state for the global root flag
                is_any_root_on = any(inst.get("root_enabled", False) for inst in instances_in_config)
                new_global_value = "1" if is_any_root_on else "0"

                logger.info(f"Setting global '{constants.FEATURE_ROOTING_KEY}' to '{new_global_value}' in {config_path}")
                config_handler.modify_config_file(config_path, constants.FEATURE_ROOTING_KEY, new_global_value)

            except Exception as e:
                # Report a general error for this config file
                error_msg = f"Error processing {os.path.basename(config_path)}: {e}"
                self.worker.operation_message.emit("error", error_msg)
                self.operation_had_errors = True
                
    def _perform_rw_toggle_operation(self) -> None:
        if not self.worker:
            return
        try:
            self._check_and_kill_bluestacks_worker()
        except Exception as e:
            self.worker.error.emit(str(e))
            return
            
        if not self.installations:
            err_msg = self.translation_manager.get_translation(
                "No BlueStacks installations found."
            )
            logger.error(err_msg)
            self.worker.error.emit(err_msg)
            return
            
        selected_ids = [
            uid for uid, w in self.instance_checkboxes.items() if w["checkbox"].isChecked()
        ]
        show_restart_reminder = False
        for unique_id in selected_ids:
            self.worker.operation_message.emit(
                "info",
                self.translation_manager.get_translation(
                    "Toggling R/W for {}..."
                ).format(unique_id),
            )
            try:
                self._toggle_single_instance_rw(unique_id)
                show_restart_reminder = True
            except Exception as e:
                error_msg = self.translation_manager.get_translation(
                    "Error toggling R/W for {}: {}"
                ).format(unique_id, e)
                self.worker.operation_message.emit("error", error_msg)
                self.operation_had_errors = True
        if show_restart_reminder:
            self.worker.operation_message.emit(
                "info",
                self.translation_manager.get_translation(
                    "Please restart BlueStacks for R/W changes to take effect."
                ),
            )

    @pyqtSlot(str, str, str)
    def _update_instance_ui_status(
        self, unique_id: str, status_type: str, new_value_text: str
    ):
        logger.debug(
            f"GUI Update Signal: Instance='{unique_id}', Type='{status_type}', Value='{new_value_text}'"
        )
        if unique_id in self.instance_checkboxes:
            widgets = self.instance_checkboxes[unique_id]
            label_widget: Optional[QLabel] = None
            format_key = ""
            if status_type == "root":
                label_widget = widgets.get("root_status")
                format_key = "Root: {}"
            elif status_type == "rw":
                label_widget = widgets.get("rw_status")
                format_key = "R/W: {}"
            else:
                logger.warning(
                    f"Unknown status type received for UI update: {status_type}"
                )
                return
            if label_widget and format_key:
                label_text = self.translation_manager.get_translation(
                    format_key
                ).format(new_value_text)
                label_widget.setText(label_text)
            else:
                logger.warning(
                    f"Could not find label widget for '{status_type}' for instance '{unique_id}' during UI update."
                )
        else:
            logger.warning(
                f"Received UI update for unknown or removed instance: '{unique_id}'"
            )

    @pyqtSlot(str, str)
    def _show_operation_message(self, message_type: str, message_text: str):
        logger.debug(
            f"GUI Operation Message: Type='{message_type}', Text='{message_text[:100]}...'"
        )
        if message_type == "reminder" and message_text == "show_magisk_reminder":
            QMessageBox.information(
                self,
                self.translation_manager.get_translation("Magisk Install Reminder"),
                self.translation_manager.get_translation(
                    "Magisk install reminder text"
                ),
            )
        elif message_type == "error":
            self.status_label.setText(f"Error: {message_text}")
            self.status_label.setStyleSheet("color: red;")
        elif message_type == "warning":
            self.status_label.setText(f"Warning: {message_text}")
            self.status_label.setStyleSheet("color: orange;")
        elif message_type == "info":
            self.status_label.setText(message_text)
            self.status_label.setStyleSheet("")
        else:
            self.status_label.setText(message_text)
            self.status_label.setStyleSheet("")

    def update_instance_statuses(self, preserve_selection: bool = True) -> None:
        if self.is_toggling:
            logger.debug(
                "Skipping periodic status update while an operation is in progress."
            )
            return
        logger.debug("Performing periodic status update...")
        self.update_instance_data()
        self.update_instance_checkboxes(preserve_selection=preserve_selection)

        logger.debug("Periodic status update complete.")

    def closeEvent(self, event) -> None:
        logger.info("Close event triggered. Cleaning up...")
        self.status_refresh_timer.stop()
        logger.debug("Status refresh timer stopped.")
        if self.background_thread and self.background_thread.isRunning():
            logger.info(
                "Waiting for background worker thread to finish before closing..."
            )
            self.background_thread.quit()
            if not self.background_thread.wait(2000):
                logger.warning(
                    "Worker thread did not finish gracefully after 2s. Terminating."
                )
                self.background_thread.terminate()
                self.background_thread.wait(500)
            logger.info("Background thread finished or terminated.")
        else:
            logger.debug("Background thread was not running.")
        logger.info(f"{constants.APP_NAME} closed.")
        event.accept()


if __name__ == "__main__":
    if os.name == "nt":
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                constants.APP_ID
            )
            logger.debug(f"AppUserModelID set to: {constants.APP_ID}")
        except AttributeError:
            logger.warning(
                "Could not set AppUserModelID (ctypes or shell32 not found?)."
            )
        except Exception as e:
            logger.error(f"Error setting AppUserModelID: {e}")

    app = QApplication(sys.argv)

    try:
        icon_path = resource_path(constants.ICON_FILENAME)
        app_icon = QIcon(icon_path)
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)
            logger.debug(f"Application icon set from {icon_path}")
        else:
            logger.warning(f"App icon file loaded from {icon_path} but QIcon is null.")
    except Exception as e:
        logger.error(f"Error setting application icon using resource_path: {e}")

    window = BluestacksRootToggle()
    window.show()
    logger.info(f"{constants.APP_NAME} started.")
    sys.exit(app.exec_())