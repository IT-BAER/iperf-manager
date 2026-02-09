# -*- coding: utf-8 -*-
"""
test_runner.py - iperf3 테스트 실행 엔진

controller_v5_18.py의 main() 로직을 라이브러리 함수로 추출.
Dashboard(직접 호출)과 Controller CLI(래퍼) 모두에서 사용.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time
from typing import Callable

from core.net_utils import http_post_json, poll_metrics


def run_test(cfg: dict,
             csv_path: str | None = None,
             on_log: Callable[[str], None] | None = None,
             stop_event: threading.Event | None = None):
    """Execute full test cycle: servers -> clients -> poll -> stop.

    Args:
        cfg: Test configuration dict (server, clients, duration_sec, etc.)
        csv_path: Optional CSV output path. If None, no CSV is written.
        on_log: Optional log callback. Called with log strings.
        stop_event: Optional threading.Event for early stop.
    """
    def log(msg: str):
        if on_log is not None:
            on_log(msg)

    server_cfg = cfg.get('server', {})
    server = server_cfg.get('agent', '')
    clients = cfg.get('clients', [])
    duration = int(cfg.get('duration_sec', 30))
    poll_interval_sec = max(0.2, float(cfg.get('poll_interval_sec', 1.0)))
    base_port = int(cfg.get('base_port', 5211))
    global_api_key = str(cfg.get('api_key') or os.environ.get('AGENT_API_KEY', '')).strip()
    server_api_key = str(server_cfg.get('api_key') or global_api_key).strip()

    # Global/common parameters
    common = {}
    for k in ('proto', 'parallel', 'omit', 'bitrate', 'length', 'tcp_window',
              'window', 'bind', 'interval', 'local_port', 'tos', 'reverse', 'bidir'):
        if k in cfg and cfg[k] not in (None, ''):
            common[k if k != 'tcp_window' else 'window'] = cfg[k]

    ports = [base_port + i for i, _ in enumerate(clients)]

    # Start servers (with optional bind / bind_map)
    try:
        if server:
            payload = {'ports': ports}
            if server_cfg.get('bind'):
                payload['bind'] = server_cfg['bind']
            if server_cfg.get('bind_map'):
                payload['bind_map'] = server_cfg['bind_map']
            http_post_json(server, '/server/start', payload, api_key=server_api_key)
            log('[server/start] OK')
    except Exception as e:
        log(f'[controller] server/start error: {e}')

    # Start clients
    for i, c in enumerate(clients):
        try:
            target = c.get('target', '')
            if not target:
                log(f'[controller] skip empty target: {c.get("name")}')
                continue
            payload = {'target': target, 'port': ports[i], 'duration': duration}
            for k, v in common.items():
                payload[k] = v
            mode = (c.get('mode') or cfg.get('mode') or '').lower()
            if mode == 'bidir':
                payload['bidir'] = True
                payload.pop('reverse', None)
            elif mode == 'down_only':
                payload['reverse'] = True
                payload.pop('bidir', None)
            else:  # up_only or unspecified -> forward only
                payload.pop('reverse', None)
                payload.pop('bidir', None)
            # per-client overrides (pass-through)
            for k, v in c.items():
                if k in ('name', 'agent', 'target'):
                    continue
                payload[k if k != 'tcp_window' else 'window'] = v
            client_api_key = str(c.get('api_key') or global_api_key).strip()
            http_post_json(c['agent'], '/client/start', payload, api_key=client_api_key)
        except Exception as e:
            log(f'[controller] client/start error: {c.get("agent")} {e}')
        time.sleep(0.05)

    # Prepare CSV columns
    agent_names = [c.get('name', f'agent{i}') for i, c in enumerate(clients)]
    csv_cols = ['ts', 'wall']
    for n in agent_names:
        csv_cols += [f'{n}_up', f'{n}_dn']
    csv_cols += ['total_up', 'total_dn']

    mode = (cfg.get('mode') or '').lower()
    mode_hint = 'down_only' if mode == 'down_only' else ('up_only' if mode == 'up_only' else None)

    # Poll metrics during the test
    csv_rows = []
    t0 = time.time()
    while time.time() - t0 <= duration + 1:
        if stop_event is not None and stop_event.is_set():
            log('[controller] stop requested')
            break
        ts = time.time()
        wall = time.strftime('%Y-%m-%d %H:%M:%S')
        row = {'ts': f'{ts:.0f}', 'wall': wall}
        total_up, total_dn = 0.0, 0.0
        for i, c in enumerate(clients):
            try:
                client_api_key = str(c.get('api_key') or global_api_key).strip()
                u, d, _ub, _db, _jit, _los = poll_metrics(
                    c['agent'], mode_hint=mode_hint, api_key=client_api_key
                )
            except Exception:
                u, d = 0.0, 0.0
            n = agent_names[i]
            row[f'{n}_up'] = f'{u:.3f}'
            row[f'{n}_dn'] = f'{d:.3f}'
            total_up += u
            total_dn += d
        row['total_up'] = f'{total_up:.3f}'
        row['total_dn'] = f'{total_dn:.3f}'
        csv_rows.append(row)
        time.sleep(poll_interval_sec)

    # Stop clients
    for c in clients:
        try:
            client_api_key = str(c.get('api_key') or global_api_key).strip()
            http_post_json(c['agent'], '/client/stop', {}, api_key=client_api_key)
        except Exception as e:
            log(f'[controller] client/stop error: {e}')

    # Optionally stop servers
    keep = cfg.get('keep_servers_open', True)
    try:
        if server and not keep:
            http_post_json(server, '/server/stop', {}, api_key=server_api_key)
    except Exception as e:
        log(f'[controller] server/stop error: {e}')

    # Write CSV (only if csv_path is given)
    if csv_path is not None:
        try:
            with open(csv_path, 'w', encoding='utf-8', newline='') as fp:
                w = csv.DictWriter(fp, fieldnames=csv_cols)
                w.writeheader()
                for row in csv_rows:
                    w.writerow(row)
        except Exception as e:
            log(f'[controller] CSV write error: {e}')

    log('[controller] finished')
