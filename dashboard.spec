# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for iperf3 Live Dashboard.

Entry point: main_dashboard.py
Bundles: PySide6, pyqtgraph, numpy, matplotlib (Agg only), QSS themes.
Excludes: tkinter, QtQml, QtWebEngine, QtMultimedia (size reduction).
"""

import sys
from pathlib import Path

block_cipher = None

HERE = Path(SPECPATH)

# QSS theme files + arrow SVGs
theme_datas = [
    (str(HERE / 'ui' / 'theme' / 'dark.qss'), 'ui/theme'),
    (str(HERE / 'ui' / 'theme' / 'light.qss'), 'ui/theme'),
    (str(HERE / 'ui' / 'theme' / 'arrows'), 'ui/theme/arrows'),
]

a = Analysis(
    [str(HERE / 'main_dashboard.py')],
    pathex=[str(HERE)],
    binaries=[],
    datas=theme_datas,
    hiddenimports=[
        # PySide6 essentials
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # pyqtgraph
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'pyqtgraph.graphicsItems.PlotDataItem',
        'pyqtgraph.graphicsItems.PlotItem',
        'pyqtgraph.graphicsItems.AxisItem',
        'pyqtgraph.graphicsItems.LegendItem',
        'pyqtgraph.graphicsItems.InfiniteLine',
        'pyqtgraph.graphicsItems.GraphicsLayout',
        # numpy
        'numpy',
        'numpy.core._methods',
        'numpy.lib.format',
        # matplotlib (Agg backend only)
        'matplotlib',
        'matplotlib.backends.backend_agg',
        'matplotlib.figure',
        'matplotlib.pyplot',
        # Project modules
        'core',
        'core.constants',
        'core.helpers',
        'core.agent_service',
        'core.config_model',
        'core.csv_recorder',
        'core.net_utils',
        'core.report',
        'core.test_runner',
        'ui',
        'ui.theme',
        'ui.theme.colors',
        'ui.models',
        'ui.models.client_table_model',
        'ui.widgets',
        'ui.widgets.live_chart',
        'ui.widgets.log_viewer',
        'ui.widgets.table_view',
        'ui.widgets.status_indicator',
        'ui.delegates',
        'ui.delegates.checkbox_delegate',
        'ui.delegates.combo_delegate',
        'ui.delegates.ipv4_delegate',
        'ui.delegates.spinbox_delegate',
        'ui.dialogs',
        'ui.dialogs.discover_dialog',
        'ui.dialogs.edit_client_dialog',
        'ui.pages',
        'ui.pages.agents_page',
        'ui.pages.test_page',
        'ui.pages.view_page',
        'ui.workers',
        'ui.workers.poller_worker',
        'ui.workers.test_runner_worker',
        'ui.workers.discovery_worker',
        'ui.dashboard_window',
        # Backward-compat wrappers (root-level re-exports)
        'net_utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # tkinter not needed (PySide6 replaces it)
        'tkinter', '_tkinter', 'Tkinter',
        # Heavy Qt modules not used
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
        'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtTest',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.QtDataVisualization', 'PySide6.QtCharts',
        # matplotlib backends we don't use
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.backend_gtk3agg',
        'matplotlib.backends.backend_wxagg',
        # pyqtgraph 3D (requires PyOpenGL, not used)
        'pyqtgraph.opengl', 'OpenGL',
        # Other heavy unused packages
        'scipy', 'pandas', 'PIL', 'IPython', 'notebook', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='iperf3-dashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='iperf3-dashboard',
)
