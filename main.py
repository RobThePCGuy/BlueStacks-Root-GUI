"""Qt5-based GUI application for toggling BlueStacks root access."""
from __future__ import annotations

import sys
import os
import logging
import tempfile

from PyQt5.QtWidgets import QApplication, QMessageBox

import admin
import constants
import platform_support
from views import theme
from views.main_window import MainWindow

if platform_support.IS_WINDOWS:
    import pywintypes
    import win32api
    import win32event
    import winerror
else:
    import fcntl

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

# Single-instance guard: two copies patching the same BlueStacks binary, or
# attaching the same Root.vhd/Data.vhdx, at once can corrupt either. `Global\`
# (not `Local\`, which is scoped to one Terminal Services session) so the
# check also holds across two different Windows users on the same machine
# (RDP / Fast User Switching), since BlueStacks itself is a single
# machine-wide install under Program Files that any of them could be racing
# on -- elevation alone doesn't move a process to a different session, so
# same-user elevated vs. non-elevated copies were already covered under
# `Local\`. Not version-qualified: two different versions of this app race on
# the exact same on-disk files just as badly as two copies of the same
# version.
SINGLE_INSTANCE_MUTEX_NAME = r"Global\RobThePCGuy.BlueStacksRootGUI.SingleInstance"

# macOS equivalent: an flock() on a file in the shared temp dir. Same intent as
# the `Global\` mutex -- one copy per *machine*, not per user -- so two accounts
# via Fast User Switching can't both be rewriting BlueStacks Air's single
# shared system image (which lives in /Applications and is common to all users)
# at the same time. The lock releases automatically when the process exits,
# including on a crash, so no stale-lock cleanup is needed.
SINGLE_INSTANCE_LOCK_PATH = os.path.join(
    tempfile.gettempdir(), "RobThePCGuy.BlueStacksRootGUI.lock")

# Held for the process lifetime; must stay referenced or the lock is released.
_instance_guard = None


def _acquire_single_instance() -> bool:
    """Claim the single-instance lock. False means another copy has it."""
    global _instance_guard

    if not platform_support.IS_WINDOWS:
        try:
            handle = open(SINGLE_INSTANCE_LOCK_PATH, "w")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.warning("Another copy holds %s", SINGLE_INSTANCE_LOCK_PATH)
            return False
        _instance_guard = handle
        return True

    try:
        _instance_guard = win32event.CreateMutex(None, False, SINGLE_INSTANCE_MUTEX_NAME)
        return win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS
    except pywintypes.error as exc:
        # The mutex's default DACL (CreateMutex(None, ...)) grants access
        # to its creator, BUILTIN\Administrators, and SYSTEM only -- a
        # second, non-admin Windows user hitting a `Global\` mutex an
        # admin already created gets ACCESS_DENIED here, not the
        # already-exists success case above. To that user it's the same
        # situation ("someone else already has this open"), so it gets
        # the same friendly message instead of the generic startup-crash
        # handler. Any other CreateMutex failure is genuinely unexpected
        # and still surfaces as a real crash.
        if exc.winerror != winerror.ERROR_ACCESS_DENIED:
            raise
        return False


if __name__ == "__main__":
    # Patching Program Files binaries and killing BlueStacks processes need
    # admin rights. If not elevated, request elevation via UAC and relaunch;
    # this process then exits and the elevated copy takes over.
    admin.ensure_admin()

    try:
        logger.info("Starting %s (admin=%s, log=%s)",
                    constants.APP_NAME, admin.is_admin(), LOG_PATH)

        # Declare our own taskbar identity before any window exists. Without
        # this Windows groups the window under whatever host process it sees
        # (python.exe when run from source), so the taskbar shows the wrong
        # icon and a pinned shortcut opens a second, separate button. Must
        # happen before the first window is created to take effect.
        if platform_support.IS_WINDOWS:
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    constants.APP_ID)
            except Exception:  # noqa: BLE001 - cosmetic only, never block startup
                logger.debug("could not set AppUserModelID", exc_info=True)

        app = QApplication(sys.argv)

        if not _acquire_single_instance():
            logger.warning("%s is already running; exiting.", constants.APP_NAME)
            QMessageBox.warning(
                None, constants.APP_NAME,
                "%s is already running. Close the other window before opening "
                "a new one -- running two copies at once can corrupt a "
                "BlueStacks engine patch or instance disk if both act on it "
                "at the same time." % constants.APP_NAME)
            sys.exit(0)

        theme.apply_theme(app, theme.load_saved_theme())
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - capture any startup crash to the log
        logger.exception("Fatal error during startup")
        raise
