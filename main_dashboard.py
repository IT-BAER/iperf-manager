# -*- coding: utf-8 -*-
"""
main_dashboard.py - Entry point for the iperf3 Live Dashboard (PySide6).

IMPORTANT: matplotlib backend must be set to 'Agg' BEFORE any matplotlib
import so that report.py does not accidentally pull in TkAgg.
"""
from __future__ import annotations

import os
import sys

# Set matplotlib backend to Agg BEFORE any other import that might
# transitively import matplotlib (e.g. report.py).
import matplotlib
matplotlib.use('Agg')


def main():
    # HiDPI support
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName('iperf3-dashboard')

    # Apply dark theme
    try:
        from ui.theme import load_theme
        app.setStyleSheet(load_theme('dark'))
    except Exception as e:
        print(f'[WARN] Theme load failed: {e}')

    from ui.dashboard_window import DashboardWindow
    window = DashboardWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
