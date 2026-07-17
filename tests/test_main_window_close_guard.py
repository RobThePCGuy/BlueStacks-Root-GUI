from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMessageBox

from views.main_window import MainWindow


def test_close_blocked_while_operation_running(qtbot, monkeypatch):
    # Closing mid-operation would kill a thread writing real binaries/disk
    # images. closeEvent must warn and refuse instead of tearing down.
    window = MainWindow()
    qtbot.addWidget(window)
    window._op_thread = object()  # stand-in for an in-flight operation
    warned = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warned)
    event = MagicMock()

    window.closeEvent(event)

    warned.assert_called_once()
    event.ignore.assert_called_once()
    event.accept.assert_not_called()


def test_close_allowed_when_idle(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._op_thread = None
    event = MagicMock()

    window.closeEvent(event)

    event.accept.assert_called_once()
    event.ignore.assert_not_called()
