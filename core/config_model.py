# -*- coding: utf-8 -*-
"""
core.config_model - Dataclass models for test configuration.

Backward-compatible with the existing last_profile.json format
produced by _collect_cfg() in the Tkinter dashboard.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class ClientConfig:
    """Per-client iperf3 test configuration."""
    name: str = ''
    agent: str = ''
    target: str = ''
    bind: str = ''
    proto: str = ''
    parallel: int | str = ''
    reverse: bool = False
    bidir: bool = False
    bitrate: str = ''
    # Advanced overrides (edit dialog)
    interval: str = ''
    omit: int | str = ''
    length: str = ''
    window: str = ''
    extra_args: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict matching last_profile.json client entry format."""
        d: dict[str, Any] = {'name': self.name, 'agent': self.agent, 'target': self.target}
        if self.bind:
            d['bind'] = self.bind
        if self.proto:
            d['proto'] = self.proto.lower()
        if self.parallel and str(self.parallel).strip():
            val = str(self.parallel).strip()
            d['parallel'] = int(val) if val.isdigit() else val
        if self.reverse:
            d['reverse'] = True
        if self.bidir:
            d['bidir'] = True
        if self.bitrate:
            d['bitrate'] = self.bitrate
        # Advanced overrides
        if self.interval:
            d['interval'] = self.interval
        if self.omit and str(self.omit).strip():
            val = str(self.omit).strip()
            d['omit'] = int(val) if val.isdigit() else val
        if self.length:
            d['length'] = self.length
        if self.window:
            d['window'] = self.window
        if self.extra_args:
            d['extra_args'] = self.extra_args
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientConfig:
        """Deserialize from last_profile.json client entry."""
        return cls(
            name=str(d.get('name', '')),
            agent=str(d.get('agent', '')),
            target=str(d.get('target', '')),
            bind=str(d.get('bind', '')),
            proto=str(d.get('proto', '')),
            parallel=d.get('parallel', ''),
            reverse=bool(d.get('reverse', False)),
            bidir=bool(d.get('bidir', False)),
            bitrate=str(d.get('bitrate', '')),
            interval=str(d.get('interval', '')),
            omit=d.get('omit', ''),
            length=str(d.get('length', '')),
            window=str(d.get('window', '')),
            extra_args=d.get('extra_args', []),
        )


@dataclass
class TestConfig:
    """Full test configuration including server and all clients."""
    # Server
    server_agent: str = 'http://A-IP:9001'
    server_bind: str = ''
    api_key: str = ''
    keep_servers_open: bool = True
    # Test parameters
    mode: str = 'bidir'
    duration_sec: int = 30
    base_port: int = 5211
    proto: str = 'tcp'
    parallel: int = 1
    omit: int = 1
    bitrate: str = ''
    length: str = ''
    tcp_window: str = ''
    poll_interval_sec: float = 1.0
    # Clients
    clients: list[ClientConfig] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict matching the existing last_profile.json format."""
        cfg: dict[str, Any] = {
            'mode': self.mode,
            'duration_sec': self.duration_sec,
            'poll_interval_sec': self.poll_interval_sec,
            'base_port': self.base_port,
            'parallel': self.parallel,
            'proto': self.proto,
            'omit': self.omit,
            'keep_servers_open': self.keep_servers_open,
            'server': {'agent': self.server_agent},
            'clients': [c.to_dict() for c in self.clients],
        }
        if self.api_key:
            cfg['api_key'] = self.api_key
            cfg['server']['api_key'] = self.api_key
        if self.server_bind:
            cfg['server']['bind'] = self.server_bind
        if self.bitrate:
            cfg['bitrate'] = self.bitrate
        if self.length:
            cfg['length'] = self.length
        if self.tcp_window:
            cfg['tcp_window'] = self.tcp_window
        return cfg

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TestConfig:
        """Deserialize from last_profile.json format."""
        server = d.get('server', {})
        clients_raw = d.get('clients', [])
        return cls(
            server_agent=server.get('agent', ''),
            server_bind=str(server.get('bind', '')),
            api_key=str(d.get('api_key') or server.get('api_key', '')),
            keep_servers_open=bool(d.get('keep_servers_open', True)),
            mode=d.get('mode', 'bidir'),
            duration_sec=int(d.get('duration_sec', 30)),
            base_port=int(d.get('base_port', 5211)),
            proto=d.get('proto', 'tcp'),
            parallel=int(d.get('parallel', 1)),
            omit=int(d.get('omit', 0)),
            bitrate=str(d.get('bitrate', '')),
            length=str(d.get('length', '')),
            tcp_window=str(d.get('tcp_window', '')),
            poll_interval_sec=float(d.get('poll_interval_sec', 1.0)),
            clients=[ClientConfig.from_dict(c) for c in clients_raw],
        )

    def to_controller_dict(self) -> dict[str, Any]:
        """Produce a dict suitable for controller_v5_18.py --config."""
        d = self.to_dict()
        d['keep_servers_open'] = self.keep_servers_open
        return d

    def save_profile(self, path: str | Path):
        """Save to JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')

    @classmethod
    def load_profile(cls, path: str | Path) -> TestConfig:
        """Load from JSON file."""
        p = Path(path)
        raw = json.loads(p.read_text(encoding='utf-8'))
        return cls.from_dict(raw)

    # ── Validation ──

    _VALID_MODES = ('bidir', 'up_only', 'down_only', 'dual', 'two_phase')
    _BITRATE_RE = re.compile(r'^\d+(\.\d+)?[kKmMgG]?$')
    _LENGTH_RE = re.compile(r'^\d+[kKmMgG]?$')

    def validate(self) -> list[str]:
        """Return list of validation errors. Empty list means valid."""
        errors: list[str] = []

        # Server URL
        if not self.server_agent or self.server_agent == 'http://A-IP:9001':
            errors.append('Server (A) URL is not configured.')
        elif not self.server_agent.startswith('http://'):
            errors.append(f'Server URL must start with http:// — got "{self.server_agent}"')

        # Clients
        if not self.clients:
            errors.append('At least one client must be configured.')

        for i, c in enumerate(self.clients):
            label = c.name or f'#{i}'
            if not c.agent or c.agent == 'http://B:9001':
                errors.append(f'Client "{label}" has no agent URL.')
            if not c.target:
                errors.append(f'Client "{label}" has no target IP.')

            # Per-client UDP constraints
            proto = (c.proto or self.proto or 'tcp').lower()
            if proto == 'udp':
                if c.bidir:
                    errors.append(f'Client "{label}": UDP cannot use --bidir.')
                par = c.parallel
                if par and str(par).strip().isdigit() and int(par) > 1:
                    errors.append(f'Client "{label}": UDP cannot use -P > 1.')

        # Port range
        n = len(self.clients)
        if n > 0:
            if self.base_port < 1024:
                errors.append(f'Base port {self.base_port} is below 1024 (reserved).')
            if self.base_port + n - 1 > 65535:
                errors.append(f'Base port {self.base_port} + {n} clients exceeds 65535.')

        # Value ranges
        if self.duration_sec <= 0:
            errors.append(f'Duration must be > 0 (got {self.duration_sec}).')
        if self.poll_interval_sec <= 0:
            errors.append(f'poll_interval_sec must be > 0 (got {self.poll_interval_sec}).')
        if self.parallel <= 0:
            errors.append(f'Parallel must be > 0 (got {self.parallel}).')
        if self.omit < 0:
            errors.append(f'Omit must be >= 0 (got {self.omit}).')

        # Mode
        if self.mode not in self._VALID_MODES:
            errors.append(f'Invalid mode "{self.mode}". '
                          f'Must be one of {self._VALID_MODES}.')

        # Bitrate / length format
        if self.bitrate and not self._BITRATE_RE.match(self.bitrate):
            errors.append(f'Invalid bitrate format: "{self.bitrate}" '
                          '(expected e.g. "100M", "1G", "500k").')
        if self.length and not self._LENGTH_RE.match(self.length):
            errors.append(f'Invalid length format: "{self.length}" '
                          '(expected e.g. "128K", "1M").')

        return errors
