# -*- coding: utf-8 -*-
"""Delegate for boolean checkbox columns (reverse, bidir).

Renders a centered checkbox and toggles on click/space.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QRect, Qt
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionButton,
    QStyleOptionViewItem, QWidget,
)


class CheckBoxDelegate(QStyledItemDelegate):
    """Centered checkbox delegate for boolean table columns."""

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex):
        # Draw background
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem,
                            option, painter, option.widget)

        # Draw centered checkbox
        check_opt = QStyleOptionButton()
        check_opt.rect = self._checkbox_rect(option)
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state == Qt.CheckState.Checked:
            check_opt.state = QStyle.StateFlag.State_On | QStyle.StateFlag.State_Enabled
        else:
            check_opt.state = QStyle.StateFlag.State_Off | QStyle.StateFlag.State_Enabled
        style.drawControl(QStyle.ControlElement.CE_CheckBox, check_opt,
                          painter, option.widget)

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem,
                    index: QModelIndex) -> bool:
        if event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            # Check if click is within the checkbox rect
            cb_rect = self._checkbox_rect(option)
            if not cb_rect.contains(event.position().toPoint()):
                return False
            # Toggle
            current = index.data(Qt.ItemDataRole.CheckStateRole)
            new_state = (Qt.CheckState.Unchecked
                         if current == Qt.CheckState.Checked
                         else Qt.CheckState.Checked)
            model.setData(index, new_state.value, Qt.ItemDataRole.CheckStateRole)
            return True

        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space:
                current = index.data(Qt.ItemDataRole.CheckStateRole)
                new_state = (Qt.CheckState.Unchecked
                             if current == Qt.CheckState.Checked
                             else Qt.CheckState.Checked)
                model.setData(index, new_state.value, Qt.ItemDataRole.CheckStateRole)
                return True

        return False

    def createEditor(self, parent, option, index):
        # No editor needed; editorEvent handles toggling
        return None

    def _checkbox_rect(self, option: QStyleOptionViewItem) -> QRect:
        """Calculate centered checkbox rect within the cell."""
        style = option.widget.style() if option.widget else QApplication.style()
        cb_opt = QStyleOptionButton()
        cb_rect = style.subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, cb_opt, option.widget)
        # Center the checkbox in the cell
        x = option.rect.x() + (option.rect.width() - cb_rect.width()) // 2
        y = option.rect.y() + (option.rect.height() - cb_rect.height()) // 2
        return QRect(x, y, cb_rect.width(), cb_rect.height())
