# -*- coding: utf-8 -*-
"""Delegate for IPv4 address editing in the client table.

Validates input as a valid IPv4 host address (rejects network/broadcast).
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QLineEdit, QMessageBox, QStyledItemDelegate, QWidget,
)

from core.helpers import is_ipv4, is_ipv4_host


class IPv4Delegate(QStyledItemDelegate):
    """Editor delegate for bind/target IP address columns."""

    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        editor = QLineEdit(parent)
        editor.setPlaceholderText("e.g. 192.168.1.100")
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex):
        value = index.data(Qt.ItemDataRole.EditRole) or ""
        editor.setText(str(value))

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex):
        text = editor.text().strip()
        if not text:
            # Allow clearing the field
            model.setData(index, "", Qt.ItemDataRole.EditRole)
            return
        if not is_ipv4(text):
            QMessageBox.warning(
                editor, "Invalid IP",
                f'"{text}" is not a valid IPv4 address.',
            )
            return
        if not is_ipv4_host(text):
            QMessageBox.warning(
                editor, "Invalid Host",
                f'"{text}" is a network or broadcast address.',
            )
            return
        model.setData(index, text, Qt.ItemDataRole.EditRole)
