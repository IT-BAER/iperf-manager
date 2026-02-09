# -*- coding: utf-8 -*-
"""Pre-configured QTableView for the iperf3 client table.

Sets up delegates per column, alternating row colors, and column widths
matching the original Tkinter dashboard layout.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from ui.delegates.checkbox_delegate import CheckBoxDelegate
from ui.delegates.combo_delegate import ComboDelegate
from ui.delegates.ipv4_delegate import IPv4Delegate
from ui.delegates.spinbox_delegate import SpinBoxDelegate
from ui.models.client_table_model import (
    COLUMNS, COLUMN_WIDTHS, BOOL_COLUMNS, ClientTableModel,
)
from core.constants import PROTOCOLS


class ClientTableView(QTableView):
    """Table view for the iperf3 client list with per-column delegates."""

    def __init__(self, model: ClientTableModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModel(model)

        # Visual settings
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setDefaultSectionSize(26)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)

        # Column widths
        header = self.horizontalHeader()
        for i, col_name in enumerate(COLUMNS):
            width = COLUMN_WIDTHS.get(col_name, 80)
            if width == 0:
                self.setColumnHidden(i, True)
            else:
                self.setColumnWidth(i, width)
        header.setStretchLastSection(False)
        # Stretch the 'name' column
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # Per-column delegates
        self._setup_delegates()

        # F2 shortcut to edit current cell
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self)
        shortcut.activated.connect(self._on_f2)

    def _setup_delegates(self):
        """Assign specialized delegates to editable columns."""
        # IPv4 delegate for bind and target
        ipv4_delegate = IPv4Delegate(self)
        self.setItemDelegateForColumn(COLUMNS.index("bind"), ipv4_delegate)
        self.setItemDelegateForColumn(COLUMNS.index("target"), ipv4_delegate)

        # Combo delegate for proto
        combo_delegate = ComboDelegate([""] + PROTOCOLS, self)
        self.setItemDelegateForColumn(COLUMNS.index("proto"), combo_delegate)

        # Checkbox delegate for reverse and bidir
        checkbox_delegate = CheckBoxDelegate(self)
        self.setItemDelegateForColumn(COLUMNS.index("reverse"), checkbox_delegate)
        self.setItemDelegateForColumn(COLUMNS.index("bidir"), checkbox_delegate)

        # SpinBox delegate for parallel
        spinbox_delegate = SpinBoxDelegate(minimum=1, maximum=128, parent=self)
        self.setItemDelegateForColumn(COLUMNS.index("parallel"), spinbox_delegate)

    def _on_f2(self):
        """Open editor on the current cell if editable."""
        idx = self.currentIndex()
        if idx.isValid():
            col_name = COLUMNS[idx.column()]
            if col_name not in BOOL_COLUMNS:
                self.edit(idx)
