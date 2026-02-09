# -*- coding: utf-8 -*-
"""Qt Model/View table model for iperf3 client rows.

20 columns matching the original dashboard Treeview layout.
Editable columns: name, bind, target, proto, parallel, reverse, bidir, bitrate.
Metric columns are read-only and updated by the poller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, Qt, Signal,
)

from core.constants import (
    TABLE_COLUMNS, TABLE_HEADERS, TABLE_WIDTHS,
    EDITABLE_COLUMNS, METRIC_COLUMNS, TEXT_COLUMNS,
)

# ── Column definitions (re-exported from core.constants) ──────────────
COLUMNS = list(TABLE_COLUMNS)
COLUMN_HEADERS = TABLE_HEADERS
COLUMN_WIDTHS = TABLE_WIDTHS

BOOL_COLUMNS = {"reverse", "bidir"}

# Center-aligned columns (everything except text columns)
CENTER_COLUMNS = set(COLUMNS) - TEXT_COLUMNS


@dataclass
class ClientRow:
    """Data backing a single row in the client table."""
    name: str = "B-host"
    source: str = ""
    agent: str = "http://B:9001"
    bind: str = ""
    target: str = "A.ip"
    proto: str = ""
    parallel: str = ""
    reverse: str = ""
    bidir: str = ""
    bitrate: str = ""
    # Metrics (updated by poller)
    up_mbps: str = "0.000"
    dn_mbps: str = "0.000"
    up_max: str = "0.000"
    up_min: str = "0.000"
    dn_max: str = "0.000"
    dn_min: str = "0.000"
    sent_mb: str = "0.000"
    recv_mb: str = "0.000"
    jitter_ms: str = "0.000"
    loss_pct: str = "0.000"

    # Hidden per-client overrides (not displayed, stored in model)
    overrides: Dict[str, Any] = field(default_factory=dict)

    def get(self, col: str) -> str:
        return getattr(self, col, "")

    def set(self, col: str, value: str):
        if hasattr(self, col):
            setattr(self, col, value)


class ClientTableModel(QAbstractTableModel):
    """Table model for the iperf3 client list.

    Supports editing of config columns, read-only metrics updates,
    and per-client override storage.
    """

    dataModified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[ClientRow] = []

    # ── Qt Model Interface ────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        col_name = COLUMNS[col]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._rows[row].get(col_name)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col_name in CENTER_COLUMNS:
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.CheckStateRole:
            if col_name in BOOL_COLUMNS:
                val = self._rows[row].get(col_name).strip().lower()
                return Qt.CheckState.Checked if val in ("1", "true", "yes", "on") else Qt.CheckState.Unchecked

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False
        row = index.row()
        col_name = COLUMNS[index.column()]

        if role == Qt.ItemDataRole.CheckStateRole and col_name in BOOL_COLUMNS:
            self._rows[row].set(col_name, "1" if value == Qt.CheckState.Checked.value else "")
            self.dataChanged.emit(index, index, [role])
            self.dataModified.emit()
            return True

        if role == Qt.ItemDataRole.EditRole and col_name in EDITABLE_COLUMNS:
            self._rows[row].set(col_name, str(value))
            self.dataChanged.emit(index, index, [role])
            self.dataModified.emit()
            return True

        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            return base
        col_name = COLUMNS[index.column()]
        if col_name in BOOL_COLUMNS:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        if col_name in EDITABLE_COLUMNS:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal and 0 <= section < len(COLUMNS):
                return COLUMN_HEADERS.get(COLUMNS[section], COLUMNS[section])
            if orientation == Qt.Orientation.Vertical:
                return str(section + 1)
        return None

    # ── Public API ────────────────────────────────────────────────────

    def add_client(self, name: str = "B-host", agent: str = "http://B:9001",
                   target: str = "A.ip", **kwargs) -> int:
        """Add a new client row. Returns the new row index."""
        row_data = ClientRow(name=name, agent=agent, target=target)
        for k, v in kwargs.items():
            if hasattr(row_data, k):
                setattr(row_data, k, str(v))
        idx = len(self._rows)
        self.beginInsertRows(QModelIndex(), idx, idx)
        self._rows.append(row_data)
        self.endInsertRows()
        self.dataModified.emit()
        return idx

    def remove_rows(self, rows: List[int]):
        """Remove rows by index (sorted descending to preserve indices)."""
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._rows):
                self.beginRemoveRows(QModelIndex(), row, row)
                self._rows.pop(row)
                self.endRemoveRows()
        self.dataModified.emit()

    def clear_all(self):
        """Remove all rows."""
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()
        self.dataModified.emit()

    def update_metrics(self, name: str, **metrics):
        """Update metric columns for a named client.

        Example: model.update_metrics("client1", up_mbps="123.456", dn_mbps="78.9")
        """
        for i, r in enumerate(self._rows):
            if r.name == name:
                for key, val in metrics.items():
                    if key in METRIC_COLUMNS:
                        r.set(key, str(val))
                # Emit change for the metrics columns
                left = self.index(i, COLUMNS.index("up_mbps"))
                right = self.index(i, len(COLUMNS) - 1)
                self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole])
                return

    def get_row(self, row: int) -> Optional[ClientRow]:
        """Get a ClientRow by index."""
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def get_row_by_name(self, name: str) -> Optional[ClientRow]:
        """Find a ClientRow by name."""
        for r in self._rows:
            if r.name == name:
                return r
        return None

    def get_client_configs(self) -> List[dict]:
        """Return list of client config dicts (for test execution / profile save)."""
        configs = []
        for r in self._rows:
            cfg = {
                "name": r.name,
                "agent": r.agent,
                "target": r.target,
            }
            if r.bind:
                cfg["bind"] = r.bind
            if r.proto:
                cfg["proto"] = r.proto.lower()
            if r.parallel and r.parallel.strip():
                try:
                    cfg["parallel"] = int(r.parallel)
                except ValueError:
                    cfg["parallel"] = r.parallel
            if r.reverse.strip().lower() in ("1", "true", "yes", "on"):
                cfg["reverse"] = True
            if r.bidir.strip().lower() in ("1", "true", "yes", "on"):
                cfg["bidir"] = True
            if r.bitrate:
                cfg["bitrate"] = r.bitrate
            # Merge overrides
            cfg.update(r.overrides)
            configs.append(cfg)
        return configs

    def load_from_config(self, clients: List[dict]):
        """Load rows from a saved config (e.g., last_profile.json)."""
        self.beginResetModel()
        self._rows.clear()

        for c in clients:
            from core.helpers import extract_ip_port
            name = c.get("name", "")
            agent = c.get("agent", "")
            target = c.get("target", "")
            bind = c.get("bind", "")
            proto = c.get("proto", "")
            parallel = str(c.get("parallel", ""))
            reverse = "1" if c.get("reverse") else ""
            bidir = "1" if c.get("bidir") else ""
            bitrate = str(c.get("bitrate", ""))

            ip, _ = extract_ip_port(agent) if agent else ("", 9001)

            row = ClientRow(
                name=name, source=ip, agent=agent, bind=bind, target=target,
                proto=proto, parallel=parallel, reverse=reverse,
                bidir=bidir, bitrate=bitrate,
            )

            # Store advanced overrides
            overrides = {}
            for k in ("interval", "omit", "length", "window", "extra_args"):
                if k in c:
                    overrides[k] = c[k]
            row.overrides = overrides

            self._rows.append(row)

        self.endResetModel()
        self.dataModified.emit()

    def set_override(self, name: str, key: str, value: Any):
        """Set a per-client override (interval, omit, length, window, extra_args)."""
        for r in self._rows:
            if r.name == name:
                r.overrides[key] = value
                self.dataModified.emit()
                return

    def get_override(self, name: str, key: str, default=None) -> Any:
        """Get a per-client override value."""
        for r in self._rows:
            if r.name == name:
                return r.overrides.get(key, default)
        return default

    def all_names(self) -> List[str]:
        """Return ordered list of client names."""
        return [r.name for r in self._rows]

    def column_index(self, col_name: str) -> int:
        """Return the column index for a given column name."""
        return COLUMNS.index(col_name)
