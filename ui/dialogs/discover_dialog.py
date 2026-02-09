# -*- coding: utf-8 -*-
"""Discover agents dialog.

Shows agents discovered via UDP broadcast.
User can select one as Server (A) or add selections as Clients (B).
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class DiscoverDialog(QDialog):
    """Modal dialog showing discovered iperf3 agents.

    Signals:
        server_selected(str ip, int port): User chose an agent as server (A).
        clients_selected(list[dict]): User chose agents as clients (B).
            Each dict: {ip, name, port, mgmt, ips: list[str], non_mgmt_ips: list[str]}
    """

    server_selected = Signal(str, int)
    clients_selected = Signal(list)

    _COLUMNS = ("ip", "name", "servers", "port", "mgmt", "ips")
    _HEADERS = ("IP", "Name", "Servers", "Port", "MGMT IP", "All IPs")
    _WIDTHS = (220, 180, 240, 80, 180, 300)

    def __init__(self, found: List[dict], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Discovered Agents")
        self.setMinimumSize(900, 350)
        self._found = found
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self._table = QTableWidget(len(self._found), len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)

        header = self._table.horizontalHeader()
        for i, w in enumerate(self._WIDTHS):
            if w > 0:
                self._table.setColumnWidth(i, w)
        header.setStretchLastSection(True)

        for row_idx, agent in enumerate(self._found):
            ip = agent.get("ip", "")
            name = agent.get("name", ip)
            servers = ",".join(str(s) for s in agent.get("servers", []))
            port = str(agent.get("port", 9001))
            mgmt = agent.get("mgmt", ip)
            ips = ",".join(agent.get("ips", [ip]))

            for col_idx, val in enumerate((ip, name, servers, port, mgmt, ips)):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row_idx, col_idx, item)

        layout.addWidget(self._table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_set_a = QPushButton("Set selected as A")
        btn_add_b = QPushButton("Add selected as B")
        btn_close = QPushButton("Close")

        btn_set_a.clicked.connect(self._on_set_as_a)
        btn_add_b.clicked.connect(self._on_add_as_b)
        btn_close.clicked.connect(self.close)

        btn_layout.addWidget(btn_set_a)
        btn_layout.addWidget(btn_add_b)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _selected_agents(self) -> List[dict]:
        """Return list of agent dicts for selected rows."""
        rows = set()
        for item in self._table.selectedItems():
            rows.add(item.row())
        return [self._found[r] for r in sorted(rows) if r < len(self._found)]

    def _on_set_as_a(self):
        agents = self._selected_agents()
        if not agents:
            return
        a = agents[0]
        self.server_selected.emit(a.get("ip", ""), int(a.get("port", 9001)))

    def _on_add_as_b(self):
        agents = self._selected_agents()
        if not agents:
            return
        self.clients_selected.emit(agents)
