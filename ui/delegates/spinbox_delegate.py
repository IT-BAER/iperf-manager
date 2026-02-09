# -*- coding: utf-8 -*-
"""Delegate for integer spin-box editing in the client table.

Used for the 'parallel' column (range 1-128).
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QSpinBox, QStyledItemDelegate, QWidget


class SpinBoxDelegate(QStyledItemDelegate):
    """Integer spin-box editor delegate.

    Args:
        minimum: Minimum value (default 1).
        maximum: Maximum value (default 128).
        parent: Parent widget.
    """

    def __init__(self, minimum: int = 1, maximum: int = 128,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum

    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        editor = QSpinBox(parent)
        editor.setMinimum(self._min)
        editor.setMaximum(self._max)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor: QSpinBox, index: QModelIndex):
        value = str(index.data(Qt.ItemDataRole.EditRole) or "").strip()
        try:
            editor.setValue(int(value))
        except (ValueError, TypeError):
            editor.setValue(self._min)

    def setModelData(self, editor: QSpinBox, model, index: QModelIndex):
        model.setData(index, str(editor.value()), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QSpinBox, option, index: QModelIndex):
        editor.setGeometry(option.rect)
