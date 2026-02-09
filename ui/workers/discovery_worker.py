# -*- coding: utf-8 -*-
"""
DiscoveryWorker - UDP broadcast agent discovery worker.

Sends IPERF3_DISCOVER broadcast and collects agent responses.
Runs on a QThread to avoid blocking the UI.
"""
from __future__ import annotations

import json
import socket

from PySide6.QtCore import QObject, Signal

from core.helpers import extract_ip_port


class AgentInfo:
    """Discovered agent data."""

    __slots__ = ('ip', 'port', 'name', 'servers', 'mgmt', 'ips', 'non_mgmt_ips', 'base')

    def __init__(self, data: dict, addr: tuple | None = None):
        base = data.get('base', '')
        ip, port = extract_ip_port(base) if base else ('', 9001)
        self.base = base
        self.ip = ip
        self.port = port
        self.name = data.get('name', ip)
        self.servers = data.get('servers', [])
        self.mgmt = data.get('mgmt', ip)
        self.ips = data.get('ips', [ip])
        self.non_mgmt_ips = data.get('non_mgmt_ips', [])

    def to_dict(self) -> dict:
        return {
            'ip': self.ip,
            'port': self.port,
            'name': self.name,
            'servers': self.servers,
            'mgmt': self.mgmt,
            'ips': self.ips,
            'non_mgmt_ips': self.non_mgmt_ips,
            'base': self.base,
        }


class DiscoveryWorker(QObject):
    """Performs UDP broadcast discovery of iperf3 agents.

    Signals:
        agent_found(dict): Emitted for each unique agent discovered.
        discovery_finished(int): Emitted when discovery completes with count of agents found.
        error_occurred(str): Error description.
    """

    agent_found = Signal(dict)
    discovery_finished = Signal(int)
    error_occurred = Signal(str)

    DISCOVER_PORT = 9999
    DISCOVER_MSG = b'IPERF3_DISCOVER'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timeout: float = 0.8
        self._retries: int = 2

    def set_timeout(self, seconds: float):
        self._timeout = max(0.3, seconds)

    def set_retries(self, count: int):
        self._retries = max(1, count)

    def run_discovery(self):
        """Execute discovery. Call from the worker thread."""
        seen: dict[str, AgentInfo] = {}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(self._timeout)

            # Send broadcast packets
            for _ in range(self._retries):
                try:
                    sock.sendto(self.DISCOVER_MSG, ('255.255.255.255', self.DISCOVER_PORT))
                except Exception:
                    pass

            # Collect responses
            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    break
                except Exception:
                    break
                try:
                    obj = json.loads(data.decode('utf-8', 'ignore'))
                except Exception:
                    continue

                info = AgentInfo(obj, addr)
                key = f'{info.ip}:{info.port}'
                if key not in seen:
                    seen[key] = info
                    self.agent_found.emit(info.to_dict())

            sock.close()
        except Exception as e:
            self.error_occurred.emit(str(e))

        self.discovery_finished.emit(len(seen))
