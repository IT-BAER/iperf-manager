# -*- coding: utf-8 -*-
"""
main_agent.py - Entry point for the headless iperf3 Agent.

Starts the AgentService REST API and UDP discovery responder.
"""
from __future__ import annotations

import argparse
import signal
import sys
import threading


def main():
    parser = argparse.ArgumentParser(description='iperf3 Agent (headless)')
    parser.add_argument('--host', default=None, help='Bind address (overrides config)')
    parser.add_argument('--port', type=int, default=None, help='REST API port (overrides config)')
    args = parser.parse_args()

    from core.agent_service import AgentService, load_agent_cfg

    cfg = load_agent_cfg()
    try:
        ports = [int(p) for p in cfg.get('autostart', '5211,5212').split(',') if p.strip()]
    except Exception:
        ports = [5211, 5212]

    service = AgentService(
        host=args.host or cfg.get('bind_host', '0.0.0.0'),
        port=args.port or int(cfg.get('port', 9001)),
        iperf3_bin=cfg.get('iperf3_path', '') or 'iperf3',
        autostart_ports=ports,
        advertise_ip=cfg.get('advertise_ip', ''),
        api_token=cfg.get('api_token', ''),
    )
    service.start()
    print(f'[Agent] Running at {service.base_url()}')
    print('[Agent] Press Ctrl+C to stop.')

    def _on_signal(signum, frame):
        print(f'\n[Agent] Signal {signum}, stopping...')
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        service.stop()


if __name__ == '__main__':
    main()
