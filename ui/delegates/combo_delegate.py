# -*- coding: utf-8 -*-
"""Delegate for combo-box (dropdown) editing in the client table.

Used for the 'proto' column (tcp / udp).
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate, QWidget


class ComboDelegate(QStyledItemDelegate):
    """Drop-down editor delegate.

    Args:
        items: List of selectable values (e.g. ["tcp", "udp"]).
        parent: Parent widget.
    """

    def __init__(self, items: List[str], parent: QWidget | None = None):
        super().__init__(parent)
        self._items = items

    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        editor = QComboBox(parent)
        editor.addItems(self._items)
        editor.setEditable(False)
        return editor

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        value = str(index.data(Qt.ItemDataRole.EditRole) or "").strip().lower()
        idx = editor.findText(value, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            editor.setCurrentIndex(idx)
        else:
            editor.setCurrentIndex(0)

    def setModelData(self, editor: QComboBox, model, index: QModelIndex):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QComboBox, option, index: QModelIndex):
        editor.setGeometry(option.rect)
