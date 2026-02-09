# -*- coding: utf-8 -*-
"""Read-only log viewer widget.

Displays timestamped log messages with a monospace font.
Auto-scrolls to bottom and caps line count at MAX_LINES.
"""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

MAX_LINES = 5000


class LogViewer(QPlainTextEdit):
    """Read-only log display widget with auto-scroll and line capping."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(MAX_LINES)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Cascadia Code", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["Cascadia Code", "Consolas", "D2Coding", "Courier New"])
        self.setFont(font)

    def append_log(self, msg: str):
        """Append a timestamped log line and scroll to bottom."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.appendPlainText(f"[{ts}] {msg}")
        # Auto-scroll
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()

    def append_raw(self, text: str):
        """Append text without timestamp (for subprocess output etc.)."""
        self.appendPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()
