"""Qt5-based GUI application for toggling BlueStacks root access."""
from __future__ import annotations

import sys
import os
import logging
import tempfile

from PyQt5.QtWidgets import QApplication

import admin
import constants
from views import theme
from views.main_window import MainWindow

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

if __name__ == "__main__":
    # Patching Program Files binaries and killing BlueStacks processes need
    # admin rights. If not elevated, request elevation via UAC and relaunch;
    # this process then exits and the elevated copy takes over.
    admin.ensure_admin()

    try:
        logger.info("Starting %s (admin=%s, log=%s)",
                    constants.APP_NAME, admin.is_admin(), LOG_PATH)
        app = QApplication(sys.argv)
        theme.apply_theme(app, theme.load_saved_theme())
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - capture any startup crash to the log
        logger.exception("Fatal error during startup")
        raise
