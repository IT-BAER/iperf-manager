# -*- coding: utf-8 -*-
"""
core.constants - Shared constants for iperf_manager.

All version strings, network defaults, UI column definitions,
color palettes, and preset values live here. No UI imports.
"""
from __future__ import annotations

# ------------------------------------------------------------------ #
# Version strings
# ------------------------------------------------------------------ #
AGENT_VERSION = '6.0.2'
DASHBOARD_VERSION = '7.0.0'

# ------------------------------------------------------------------ #
# Network defaults
# ------------------------------------------------------------------ #
DISCOVER_PORT = 9999
DEFAULT_API_PORT = 9001
DEFAULT_BASE_PORT = 5211
MAX_SERVERS = 50
MAX_CLIENTS = 50

# ------------------------------------------------------------------ #
# Test modes and protocols
# ------------------------------------------------------------------ #
TEST_MODES = ['bidir', 'up_only', 'down_only', 'dual', 'two_phase']
PROTOCOLS = ['tcp', 'udp']

# ------------------------------------------------------------------ #
# Time-window presets  (label -> seconds, -1 means "All")
# ------------------------------------------------------------------ #
WINDOW_PRESETS: dict[str, int] = {
    '60s': 60,
    '5m': 300,
    '30m': 1800,
    '2h': 7200,
    '1d': 86400,
    '3d': 259200,
    'All': -1,
}

# ------------------------------------------------------------------ #
# Default colors (10-color palette for charts)
# ------------------------------------------------------------------ #
DEFAULT_COLORS = [
    '#1f77b4',  # muted blue
    '#ff7f0e',  # safety orange
    '#2ca02c',  # cooked asparagus green
    '#d62728',  # brick red
    '#9467bd',  # muted purple
    '#8c564b',  # chestnut brown
    '#e377c2',  # raspberry yogurt pink
    '#7f7f7f',  # middle gray
    '#bcbd22',  # curry yellow-green
    '#17becf',  # blue-teal
]

# ------------------------------------------------------------------ #
# Default markers (pyqtgraph-compatible symbol names)
# ------------------------------------------------------------------ #
DEFAULT_MARKERS = ['o', 'x', 't', 'star', 's', 'd', 'p', 'h', 't1', 't2', 't3']

# Matplotlib marker equivalents (for report generation)
DEFAULT_MARKERS_MPL = ['o', 'x', '^', '*', 's', 'D', 'P', 'X', 'v', '>', '<']
DEFAULT_LINESTYLES = ['-', '--', '-.', ':']

# ------------------------------------------------------------------ #
# Table column definitions (matching the 20-column Tkinter Treeview)
# ------------------------------------------------------------------ #
TABLE_COLUMNS = (
    'name', 'source', 'agent', 'bind', 'target',
    'proto', 'parallel', 'reverse', 'bidir', 'bitrate',
    'up_mbps', 'dn_mbps', 'up_max', 'up_min', 'dn_max', 'dn_min',
    'sent_mb', 'recv_mb', 'jitter_ms', 'loss_pct',
)

TABLE_HEADERS: dict[str, str] = {
    'name': 'Name', 'source': 'IP', 'agent': 'B URL', 'bind': 'Bind(IP)', 'target': 'Target',
    'proto': 'Proto', 'parallel': 'P', 'reverse': 'R', 'bidir': 'bidir', 'bitrate': '-b',
    'up_mbps': 'Up (Mbps)', 'dn_mbps': 'Down (Mbps)',
    'up_max': 'Up Max', 'up_min': 'Up Min', 'dn_max': 'Down Max', 'dn_min': 'Down Min',
    'sent_mb': 'Sent (MB)', 'recv_mb': 'Recv (MB)', 'jitter_ms': 'Jitter (ms)', 'loss_pct': 'Loss (%)',
}

TABLE_WIDTHS: dict[str, int] = {
    'name': 160, 'source': 140, 'agent': 0, 'bind': 140, 'target': 190,
    'proto': 70, 'parallel': 60, 'reverse': 60, 'bidir': 70, 'bitrate': 90,
    'up_mbps': 100, 'dn_mbps': 100, 'up_max': 90, 'up_min': 90, 'dn_max': 90, 'dn_min': 90,
    'sent_mb': 110, 'recv_mb': 110, 'jitter_ms': 100, 'loss_pct': 90,
}

# Columns that are editable by user in the table
EDITABLE_COLUMNS = {'name', 'bind', 'target', 'proto', 'parallel', 'reverse', 'bidir', 'bitrate'}

# Columns that show live metrics (right-aligned numeric display)
METRIC_COLUMNS = {
    'up_mbps', 'dn_mbps', 'up_max', 'up_min', 'dn_max', 'dn_min',
    'sent_mb', 'recv_mb', 'jitter_ms', 'loss_pct',
}

# Left-aligned columns (text fields)
TEXT_COLUMNS = {'name', 'source', 'agent', 'bind', 'target'}
