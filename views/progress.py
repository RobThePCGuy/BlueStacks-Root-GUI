"""Docked status/progress indicator for long-running operations."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar


def step_percent(index: int, total: int) -> int:
    """Percent complete for step ``index`` of ``total``.

    Clamped to [0, 100]; ``total <= 0`` returns 0 to avoid a
    divide-by-zero when a job has no steps yet.
    """
    if total <= 0:
        return 0
    pct = int((index / total) * 100)
    return max(0, min(100, pct))


class OperationProgressBar(QWidget):
    """A status label that's always visible, plus a QProgressBar that only
    shows itself while an operation is running (determinate or
    indeterminate/busy)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self._label = QLabel("Ready")
        # Status text can be a full sentence; wrap it so it never clips at the
        # window edge instead of running off to the right.
        self._label.setWordWrap(True)
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setVisible(False)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)

    def start(self, text: str) -> None:
        self.show()  # Ensure parent is visible
        self._bar.setVisible(True)
        self.set_progress(text, None)

    def set_progress(self, text: str, pct: Optional[int]) -> None:
        self._label.setText(text)
        if pct is None:
            self._bar.setRange(0, 0)  # indeterminate/busy animation
        else:
            self._bar.setRange(0, 100)
            self._bar.setValue(max(0, min(100, pct)))

    def finish(self, text: str) -> None:
        self._label.setText(text)
        self._bar.setVisible(False)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
