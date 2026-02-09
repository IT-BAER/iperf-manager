# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for iperf3 Agent.

Entry point: main_agent.py
Lighter build: no matplotlib, no pyqtgraph.
Bundles: PySide6 (core widgets only), QSS themes.
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

# iperf3 binary + Cygwin DLLs (Agent executes iperf3 directly)
iperf3_binaries = [
    (str(HERE / 'iperf3.exe'), '.'),
    (str(HERE / 'cygwin1.dll'), '.'),
    (str(HERE / 'cygz.dll'), '.'),
    (str(HERE / 'cygcrypto-3.dll'), '.'),
]

a = Analysis(
    [str(HERE / 'main_agent.py')],
    pathex=[str(HERE)],
    binaries=iperf3_binaries,
    datas=theme_datas,
    hiddenimports=[
        # PySide6 essentials
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # Project modules
        'core',
        'core.constants',
        'core.helpers',
        'core.agent_service',
        'ui',
        'ui.theme',
        'ui.theme.colors',
        'ui.agent_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # tkinter not needed
        'tkinter', '_tkinter', 'Tkinter',
        # Heavy packages not needed for agent
        'matplotlib', 'pyqtgraph', 'numpy', 'scipy', 'pandas',
        'PIL', 'IPython', 'notebook', 'pytest',
        # Heavy Qt modules
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
        'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtTest',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.QtDataVisualization', 'PySide6.QtCharts',
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
    name='iperf3-agent',
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
    name='iperf3-agent',
)
