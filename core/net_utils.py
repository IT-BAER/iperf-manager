# -*- coding: utf-8 -*-
"""
net_utils.py - 공통 네트워크 유틸리티
Agent/Dashboard/Controller 에서 공유하는 HTTP 통신 및 메트릭 폴링 함수.
Keep-Alive 연결 재사용을 통한 폴링 효율 개선 포함.
"""
import json
import os
import urllib.request
from http.client import HTTPConnection
from urllib.parse import urlparse
import threading


def _to_float(x, default=None):
    """안전한 float 변환."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# --- HTTP 연결 풀 (Keep-Alive) ---

class _ConnPool:
    """호스트별 HTTP 연결 캐시 (Keep-Alive). 스레드 안전."""
    def __init__(self):
        self._conns = {}
        self._lock = threading.Lock()

    def _key(self, host, port):
        return f'{host}:{port}'

    def get(self, host, port, timeout=6):
        key = self._key(host, port)
        with self._lock:
            conn = self._conns.get(key)
        if conn is not None:
            try:
                # 연결이 살아있는지 확인
                conn.timeout = timeout
                return conn
            except Exception:
                pass
        conn = HTTPConnection(host, port, timeout=timeout)
        with self._lock:
            self._conns[key] = conn
        return conn

    def remove(self, host, port):
        key = self._key(host, port)
        with self._lock:
            conn = self._conns.pop(key, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    def close_all(self):
        with self._lock:
            for conn in self._conns.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._conns.clear()


_pool = _ConnPool()


def _resolve_api_key(api_key=None):
    """우선순위: 명시 인자 > 환경변수."""
    if api_key is not None:
        return str(api_key).strip()
    return os.environ.get('AGENT_API_KEY', '').strip()


def close_pool():
    """연결 풀의 모든 Keep-Alive 연결을 정리."""
    _pool.close_all()


def http_post_json(base, path, payload, timeout=6, api_key=None):
    """HTTP POST JSON 요청. Keep-Alive 연결 재사용 시도, 실패 시 urllib fallback."""
    parsed = urlparse(base.rstrip('/'))
    host = parsed.hostname or 'localhost'
    port = parsed.port or 80
    url_path = (parsed.path or '') + path
    data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json', 'Connection': 'keep-alive'}
    token = _resolve_api_key(api_key)
    if token:
        headers['X-API-Key'] = token

    # Keep-Alive 연결 시도
    try:
        conn = _pool.get(host, port, timeout)
        conn.request('POST', url_path, body=data, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        if 200 <= resp.status < 300:
            return json.loads(body.decode('utf-8', 'replace'))
        raise RuntimeError(f'HTTP {resp.status}: {body.decode("utf-8","replace")[:200]}')
    except (ConnectionError, OSError, RuntimeError):
        # 연결 끊김 → 풀에서 제거 후 새 연결로 재시도
        _pool.remove(host, port)
        try:
            conn = _pool.get(host, port, timeout)
            conn.request('POST', url_path, body=data, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            if 200 <= resp.status < 300:
                return json.loads(body.decode('utf-8', 'replace'))
            raise RuntimeError(f'HTTP {resp.status}: {body.decode("utf-8","replace")[:200]}')
        except Exception:
            _pool.remove(host, port)
            # 최종 fallback: urllib
            url = base.rstrip('/') + path
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8', 'replace'))


def http_get_json(base, path, timeout=1.5, api_key=None):
    """HTTP GET JSON 요청. Keep-Alive 연결 재사용."""
    parsed = urlparse(base.rstrip('/'))
    host = parsed.hostname or 'localhost'
    port = parsed.port or 80
    url_path = (parsed.path or '') + path
    headers = {'Connection': 'keep-alive'}
    token = _resolve_api_key(api_key)
    if token:
        headers['X-API-Key'] = token

    try:
        conn = _pool.get(host, port, timeout)
        conn.request('GET', url_path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        if 200 <= resp.status < 300:
            return json.loads(body.decode('utf-8', 'replace'))
        return None
    except (ConnectionError, OSError):
        _pool.remove(host, port)
        try:
            conn = _pool.get(host, port, timeout)
            conn.request('GET', url_path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            if 200 <= resp.status < 300:
                return json.loads(body.decode('utf-8', 'replace'))
        except Exception:
            _pool.remove(host, port)
        return None
    except Exception:
        return None


# --- 메트릭 폴링 ---

def _deep_find_numbers(obj, key_like):
    """중첩 dict/list에서 key_like에 매칭되는 숫자값 수집."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(s in str(k).lower() for s in key_like):
                f = _to_float(v)
                if f is not None:
                    out.append(f)
            out += _deep_find_numbers(v, key_like)
    elif isinstance(obj, list):
        for x in obj:
            out += _deep_find_numbers(x, key_like)
    return out


def poll_metrics(base, mode_hint=None, api_key=None):
    """에이전트에서 메트릭 폴링. Keep-Alive 연결 사용.
    Returns: (up_mbps, dn_mbps, up_bytes, dn_bytes, jitter, loss)
    """
    obj = http_get_json(base, '/metrics', timeout=1.5, api_key=api_key)
    if obj is None:
        return 0.0, 0.0, None, None, None, None

    up = 0.0
    dn = 0.0
    ub = None
    db = None
    jit = None
    los = None

    def pick(obj, keys, default=0.0):
        for k in keys:
            if k in obj:
                return _to_float(obj.get(k, default), default)
        return default

    for e in obj.get('metrics', []):
        j = e.get('json') or {}
        u = pick(j, ['interval_up_mbps', 'up_mbps', 'tx_mbps'], 0.0)
        d = pick(j, ['interval_dn_mbps', 'down_mbps', 'rx_mbps'], 0.0)
        s = pick(j, ['interval_mbps', 'sum_mbps', 'bidir_mbps'], 0.0)
        if s and (u > 0.0) and (d == 0.0):
            d = max(0.0, s - u)
        elif s and (d > 0.0) and (u == 0.0):
            u = max(0.0, s - d)
        elif (not u) and (not d) and s:
            if mode_hint == 'down_only':
                d = s
            elif mode_hint == 'up_only':
                u = s
            else:
                d = s
        up += u
        dn += d
        up_bytes = pick(j, ['interval_up_bytes', 'up_bytes', 'tx_bytes'], None)
        dn_bytes = pick(j, ['interval_dn_bytes', 'dn_bytes', 'rx_bytes'], None)
        if up_bytes is not None:
            ub = max(ub or 0.0, up_bytes)
        if dn_bytes is not None:
            db = max(db or 0.0, dn_bytes)
        for v in _deep_find_numbers(j, ['jitter']):
            jit = max(jit or 0.0, v)
        for v in _deep_find_numbers(j, ['loss', 'lost']):
            los = max(los or 0.0, v)
    # top-level obj scan (once, outside per-metric loop)
    for v in _deep_find_numbers(obj, ['jitter']):
        jit = max(jit or 0.0, v)
    for v in _deep_find_numbers(obj, ['loss', 'lost']):
        los = max(los or 0.0, v)
    return up, dn, ub, db, jit, los
