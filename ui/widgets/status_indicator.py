# -*- coding: utf-8 -*-
"""Small LED-style status indicator widget.

Draws a colored circle indicating running/stopped/idle state.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme.colors import (
    STATUS_IDLE, STATUS_RUNNING, STATUS_ERROR, STATUS_WARNING, STATUS_DISABLED,
)

# State -> color mapping
_STATE_COLORS = {
    "idle":     STATUS_IDLE,
    "running":  STATUS_RUNNING,
    "stopped":  STATUS_ERROR,
    "error":    STATUS_ERROR,
    "warning":  STATUS_WARNING,
    "disabled": STATUS_DISABLED,
}


class StatusIndicator(QWidget):
    """12x12 LED dot that changes color based on state."""

    def __init__(self, state: str = "idle", parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state
        self._color = QColor(_STATE_COLORS.get(state, STATUS_IDLE))
        self.setFixedSize(QSize(12, 12))

    def set_state(self, state: str):
        """Set the indicator state: 'idle', 'running', 'stopped', 'error', 'warning', 'disabled'."""
        self._state = state
        self._color = QColor(_STATE_COLORS.get(state, STATUS_IDLE))
        self.update()

    def state(self) -> str:
        return self._state

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer ring (slightly darker)
        ring_color = self._color.darker(130)
        painter.setPen(QPen(QColor(ring_color), 1))
        painter.setBrush(QBrush(self._color))

        # Draw circle centered in widget, with 1px margin
        margin = 1
        diameter = min(self.width(), self.height()) - 2 * margin
        x = (self.width() - diameter) // 2
        y = (self.height() - diameter) // 2
        painter.drawEllipse(x, y, diameter, diameter)

        painter.end()
