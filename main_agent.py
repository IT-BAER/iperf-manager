# -*- coding: utf-8 -*-
"""
main_agent.py - Entry point for the iperf3 Agent (PySide6).

Supports:
    --headless  Run without GUI (service only, console output)
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

def main():
    parser = argparse.ArgumentParser(description='iperf3 Agent')
    parser.add_argument('--headless', action='store_true', help='Run without GUI')
    args = parser.parse_args()

    if args.headless:
        _run_headless()
    else:
        _run_gui()


def _run_headless():
    """Run AgentService without a GUI window."""
    from core.agent_service import AgentService, load_agent_cfg

    cfg = load_agent_cfg()
    try:
        ports = [int(p) for p in cfg.get('autostart', '5211,5212').split(',') if p.strip()]
    except Exception:
        ports = [5211, 5212]

    service = AgentService(
        host=cfg.get('bind_host', '0.0.0.0'),
        port=int(cfg.get('port', 9001)),
        iperf3_bin=cfg.get('iperf3_path', '') or 'iperf3',
        autostart_ports=ports,
        advertise_ip=cfg.get('advertise_ip', ''),
        api_token=cfg.get('api_token', ''),
    )
    service.start()
    print(f'[Agent] Running at {service.base_url()} (headless)')
    print('[Agent] Press Ctrl+C to stop.')

    def _on_signal(signum, frame):
        print(f'\n[Agent] Signal {signum}, stopping...')
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    # Block forever
    try:
        import threading
        threading.Event().wait()
    except KeyboardInterrupt:
        service.stop()


def _run_gui():
    """Run AgentWindow with PySide6 GUI."""
    # HiDPI support
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName('iperf3-agent')

    # Apply dark theme
    try:
        from ui.theme import load_theme
        app.setStyleSheet(load_theme('dark'))
    except Exception as e:
        print(f'[WARN] Theme load failed: {e}')

    from ui.agent_window import AgentWindow
    window = AgentWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
