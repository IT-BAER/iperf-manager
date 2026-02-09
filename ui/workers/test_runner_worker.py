# -*- coding: utf-8 -*-
"""
TestRunnerWorker - Manages iperf3 test lifecycle via REST API.

Handles server/client start/stop, custom flow (up_only/down_only),
and controller flow (bidir/dual/two_phase) via core.test_runner.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from PySide6.QtCore import QObject, Signal

from core.net_utils import http_post_json


class TestRunnerWorker(QObject):
    """Runs iperf3 tests through agent REST API.

    Signals:
        test_started(): Test has begun
        test_finished(str): Test completed with reason string
        log_message(str): Log line to display
        error_occurred(str): Error description
    """

    test_started = Signal()
    test_finished = Signal(str)
    log_message = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _global_api_key(cfg: dict) -> str:
        return str(cfg.get('api_key', '')).strip()

    @classmethod
    def _server_api_key(cls, cfg: dict) -> str:
        server_cfg = cfg.get('server', {})
        return str(server_cfg.get('api_key') or cls._global_api_key(cfg)).strip()

    @classmethod
    def _client_api_key(cls, cfg: dict, client_cfg: dict) -> str:
        return str(client_cfg.get('api_key') or cls._global_api_key(cfg)).strip()

    def start_test(self, cfg: dict, ctrl_path: str | None = None):
        """Start a test. Runs in a background thread to avoid blocking.

        Args:
            cfg: Full test configuration dict (from _collect_cfg).
            ctrl_path: Unused (kept for API compatibility). Ignored.
        """
        self._stop_event.clear()
        mode = cfg.get('mode', 'bidir')
        if mode in ('up_only', 'down_only'):
            direction = 'down' if mode == 'down_only' else 'up'
            self._thread = threading.Thread(
                target=self._run_custom_flow,
                args=(cfg, direction),
                daemon=True,
            )
        else:
            self._thread = threading.Thread(
                target=self._run_controller_flow,
                args=(cfg,),
                daemon=True,
            )
        self._thread.start()
        self.test_started.emit()

    def stop_test(self, cfg: dict | None = None):
        """Stop a running test."""
        self._stop_event.set()
        # Stop clients and optionally servers
        if cfg is not None:
            threading.Thread(
                target=self._stop_agents, args=(cfg,), daemon=True
            ).start()

    # ── Custom flow (up_only / down_only) ──

    def _run_custom_flow(self, cfg: dict, direction: str):
        try:
            ports = []
            base_port = int(cfg.get('base_port', 5211))
            for i, _ in enumerate(cfg['clients']):
                ports.append(base_port + i)

            # Start servers
            try:
                srv_payload = {'ports': ports}
                srv_cfg = cfg.get('server', {})
                if srv_cfg.get('bind'):
                    srv_payload['bind'] = srv_cfg['bind']
                server_api_key = self._server_api_key(cfg) or None
                http_post_json(
                    srv_cfg['agent'],
                    '/server/start',
                    srv_payload,
                    api_key=server_api_key,
                )
                self.log_message.emit('[server/start] OK')
                # Wait for servers to be alive
                self._wait_servers_alive(
                    srv_cfg['agent'],
                    ports,
                    timeout=3.0,
                    api_key=server_api_key,
                )
            except Exception as e:
                self.log_message.emit(f'[server/start FAIL] {e}')

            common = {'proto': cfg.get('proto', 'tcp'),
                      'parallel': int(cfg.get('parallel', 1))}
            if cfg.get('bitrate'):
                common['bitrate'] = str(cfg['bitrate'])
            if cfg.get('length'):
                common['length'] = str(cfg['length'])
            if cfg.get('omit'):
                common['omit'] = int(cfg['omit'])
            if cfg.get('tcp_window'):
                common['window'] = str(cfg['tcp_window'])

            dur = int(cfg.get('duration_sec', 30))
            payloads = []
            for i, c in enumerate(cfg['clients']):
                payload = {
                    'target': c['target'],
                    'port': ports[i],
                    'duration': dur,
                    'bidir': False,
                    'reverse': direction == 'down',
                }
                payload.update(common)
                for k in ('proto', 'parallel', 'reverse', 'bidir', 'bitrate',
                          'length', 'omit', 'window', 'interval', 'extra_args', 'bind'):
                    if k in c:
                        payload[k] = c[k]
                payloads.append(payload)

            # Start clients in parallel
            workers = []
            for i, c in enumerate(cfg['clients']):
                t = threading.Thread(
                    target=self._start_one_client,
                    args=(cfg, c, payloads[i]),
                    daemon=True,
                )
                t.start()
                workers.append(t)
            for t in workers:
                t.join(timeout=0.2)

            # Wait for duration (or until stop requested)
            self._stop_event.wait(timeout=dur)

        except Exception as e:
            self.error_occurred.emit(f'[custom flow ERROR] {e}')
        finally:
            keep_open = cfg.get('keep_servers_open', True)
            if not keep_open:
                try:
                    http_post_json(
                        cfg['server']['agent'],
                        '/server/stop',
                        {},
                        api_key=self._server_api_key(cfg) or None,
                    )
                except Exception:
                    pass
            self.test_finished.emit('custom_done')

    def _start_one_client(self, cfg: dict, client_cfg: dict, payload: dict):
        try:
            client_api_key = self._client_api_key(cfg, client_cfg) or None
            http_post_json(
                client_cfg['agent'],
                '/client/start',
                payload,
                timeout=4,
                api_key=client_api_key,
            )
            self.log_message.emit(f"[client/start] {client_cfg.get('name', '?')} OK")
        except Exception as e:
            self.log_message.emit(
                f"[client/start FAIL] {client_cfg.get('name', '?')} -> {e}"
            )

    def _wait_servers_alive(
        self,
        agent_url: str,
        ports: list,
        timeout: float = 3.0,
        api_key: str | None = None,
    ):
        """Wait until all requested server ports are alive."""
        want = set(ports)
        t0 = time.time()
        headers = {}
        if api_key:
            headers['X-API-Key'] = api_key
        while time.time() - t0 <= timeout:
            try:
                req = urllib.request.Request(
                    agent_url.rstrip('/') + '/status',
                    headers=headers,
                )
                with urllib.request.urlopen(
                    req, timeout=2
                ) as r:
                    o = json.loads(r.read().decode('utf-8', 'ignore'))
                    alive = {
                        int(e.get('port'))
                        for e in (o.get('servers') or [])
                        if e.get('alive')
                    }
                    if want.issubset(alive):
                        return
            except Exception:
                pass
            time.sleep(0.1)

    # ── Controller flow (bidir / dual / two_phase) ──

    def _run_controller_flow(self, cfg: dict):
        try:
            from core.test_runner import run_test
            run_test(
                cfg,
                on_log=self.log_message.emit,
                stop_event=self._stop_event,
            )
        except Exception as e:
            self.error_occurred.emit(f'Controller flow failed: {e}')
        finally:
            self.test_finished.emit('controller_done')

    # ── Stop agents ──

    def _stop_agents(self, cfg: dict):
        for c in cfg.get('clients', []):
            try:
                client_api_key = self._client_api_key(cfg, c) or None
                http_post_json(
                    c['agent'],
                    '/client/stop',
                    {},
                    timeout=1.5,
                    api_key=client_api_key,
                )
            except Exception as e:
                self.log_message.emit(f'[STOP] client {c["agent"]} -> {e}')
        keep_open = cfg.get('keep_servers_open', True)
        if not keep_open:
            try:
                http_post_json(
                    cfg['server']['agent'],
                    '/server/stop',
                    {},
                    timeout=1.5,
                    api_key=self._server_api_key(cfg) or None,
                )
            except Exception as e:
                self.log_message.emit(f'[STOP] server -> {e}')
