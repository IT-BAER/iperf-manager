# -*- coding: utf-8 -*-
"""
core.agent_service - UI-independent AgentService.

Manages iperf3 server/client subprocesses, REST API, and UDP discovery.
Extracted from agent_gui_v6_0_2.py with all tkinter dependencies removed.
"""
import threading
import time
import json
import subprocess
import socket
import os
import re
import io
import sys
import signal
import atexit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from pathlib import Path

from core.helpers import (
    IS_WIN,
    CREATE_NO_WINDOW,
    win_hidden_startupinfo,
    resolve_log_dir,
    resolve_iperf3_path,
    list_local_ipv4,
)

AGENT_VERSION = '6.0.2'

# --- config persistence ---
CFG_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'iperf3-agent'
CFG_DIR.mkdir(parents=True, exist_ok=True)
CFG_FILE = CFG_DIR / 'config.json'


def load_agent_cfg() -> dict:
    """Load agent config from persistent storage."""
    try:
        if CFG_FILE.exists():
            return json.loads(CFG_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'[WARN] config load failed: {e}')
    return {}


def save_agent_cfg(obj: dict):
    """Save agent config to persistent storage."""
    try:
        CFG_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f'[WARN] config save failed: {e}')


class AgentService:
    """Manages iperf3 server/client subprocesses with thread-safe state.

    Provides REST API endpoints and UDP discovery responder.
    No UI dependencies -- all tkinter/ttk references removed.
    """

    DISCOVER_PORT = 9999
    MAX_SERVERS = 50
    MAX_CLIENTS = 50

    def __init__(
        self,
        host='0.0.0.0',
        port=9001,
        iperf3_bin='iperf3',
        autostart_ports=None,
        advertise_ip: str | None = None,
        api_token: str = '',
    ):
        self.host = host
        self.port = int(port)
        self.iperf3_bin = iperf3_bin or 'iperf3'
        self.autostart_ports = autostart_ports or []
        self.advertise_ip = (advertise_ip or '').strip() or os.environ.get('AGENT_MGMT_IP', '').strip()
        self.api_token = (api_token or '').strip()

        self.SERVER_PROCS: dict[int, subprocess.Popen] = {}
        self.CLIENT_PROCS: dict[str, dict] = {}
        self.LOCK = threading.Lock()

        self.LOG_DIR = resolve_log_dir()
        os.makedirs(self.LOG_DIR, exist_ok=True)
        self._log_dir_ok = os.access(self.LOG_DIR, os.W_OK)

        self.httpd = None
        self.http_thread = None
        self.disc_thread = None
        self.stop_flag = False
        self.version_str = ''
        self._hooks_registered = False

        # --- regex patterns for parsing iperf3 output ---
        self.INTERVAL_RE = re.compile(
            r"(?i)(?P<mbps>\d+(?:[\.,]\d+)?)\s*(?P<unit>[KMG])?bits/sec\b.*?(?P<role>sender|receiver)?\b"
        )
        self.UNIT2M = {'K': 1e-3, 'M': 1.0, 'G': 1e3, None: 1.0}

        self.UDP_INTERVAL_RE = re.compile(
            r"^\s*\[\s*\d+\s*\]\s+"
            r"\d+(?:\.\d+)?-\d+(?:\.\d+)?\s+sec\s+"
            r"([\d\.,]+)\s*([KMG])?Bytes\s+"
            r"([\d\.,]+)\s*([KMG])?bits/sec\s+"
            r"([\d\.,]+)\s*ms\s+"
            r"(\d+)\s*/\s*(\d+)\s*\((?:[\d\.,]+)%\)\s*$",
            re.IGNORECASE,
        )
        self.UDP_INTERVAL_RE2 = re.compile(
            r"(?i)([\d\.,]+)\s*([KMG])?Bytes.*?([\d\.,]+)\s*([KMG])?bits/sec"
            r".*?([\d\.,]+)\s*ms.*?(([\d\.,]+)%)"
        )
        self.BUNIT2B = {'K': 1024.0, 'M': 1024.0 * 1024.0, 'G': 1024.0 * 1024.0 * 1024.0, None: 1.0}

        self.TCP_BR_RE = re.compile(
            r'^\s*\[\s*\d+\s*\]\[(TX-C|RX-C)\]\s+'
            r'\d+\.?\d*\-\d+\.?\d*\s+sec\s+'
            r'([\d\.,]+)\s*([KMG])?Bytes\s+'
            r'([\d\.,]+)\s*([KMG])?bits/sec',
            re.IGNORECASE,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _now_ts(self) -> str:
        return time.strftime('%Y%m%d_%H%M%S')

    def _log(self, level: str, ctx: str, msg: str):
        ts = time.strftime('%H:%M:%S')
        print(f'[{ts}][{level}][{ctx}] {msg}')

    def _register_runtime_hooks(self):
        if self._hooks_registered:
            return
        try:
            atexit.register(self._atexit_cleanup)
        except Exception as e:
            self._log('WARN', 'hook', f'atexit register failed: {e}')
        for sig_name in ('SIGINT', 'SIGTERM'):
            sig = getattr(signal, sig_name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, self._on_signal)
            except Exception as e:
                self._log('WARN', 'hook', f'{sig_name} register failed: {e}')
        self._hooks_registered = True

    def _on_signal(self, signum, _frame):
        self._log('WARN', 'signal', f'received signal={signum}, stopping service')
        try:
            self.stop()
        except Exception as e:
            self._log('ERR', 'signal', f'stop failed: {e}')

    def _popen(self, args, **kw):
        if IS_WIN:
            kw.setdefault('creationflags', 0)
            kw['creationflags'] = CREATE_NO_WINDOW
            kw.setdefault('startupinfo', win_hidden_startupinfo())
        return subprocess.Popen(args, **kw)

    def _safe_open_log(self, path_str: str):
        try:
            return open(path_str, 'w', encoding='utf-8', errors='ignore', buffering=1)
        except Exception as e:
            try:
                print(f"[WARN] cannot open log file: {path_str} -> {e}")
            except Exception:
                pass
            return io.StringIO()

    def _advertise_ip(self) -> str:
        if self.advertise_ip:
            return self.advertise_ip
        h = (self.host or '').strip()
        if h and h not in ('0.0.0.0', '127.0.0.1'):
            return h
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return '127.0.0.1'

    def _to_float(self, s):
        if s is None:
            return None
        try:
            return float(str(s).replace(',', '.'))
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Server process management
    # ------------------------------------------------------------------ #

    def _start_server_port(self, port: int, bind_ip: str = None):
        args = [self.iperf3_bin, '-s', '-p', str(port)]
        if bind_ip:
            args += ['-B', str(bind_ip)]
        log = os.path.join(self.LOG_DIR, f'server_{port}_{self._now_ts()}.log')
        lf = self._safe_open_log(log)
        proc = self._popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        def _srv_reader():
            try:
                for line in proc.stdout:
                    try:
                        lf.write(line)
                    except Exception:
                        pass
            finally:
                try:
                    lf.flush()
                    lf.close()
                except Exception:
                    pass

        threading.Thread(target=_srv_reader, daemon=True).start()
        time.sleep(0.15)
        if proc.poll() is not None:
            try:
                lf.write(f'[ERROR] server exited immediately (exit={proc.returncode})\n')
            except Exception:
                pass
            raise RuntimeError('iperf3 server exited immediately')
        return proc, log

    def _stop_proc(self, p):
        try:
            p.terminate()
            p.wait(timeout=2)
        except (subprocess.TimeoutExpired, OSError):
            try:
                p.kill()
            except OSError:
                pass

    # ------------------------------------------------------------------ #
    # Output parsing
    # ------------------------------------------------------------------ #

    def _parse_interval_line(self, line: str):
        m = self.INTERVAL_RE.search(line)
        if not m:
            return None
        try:
            raw = str(m.group('mbps')).replace(',', '.')
            val = float(raw)
            unit = (m.group('unit') or '').upper() or None
            role = (m.group('role') or '').lower()
            mbps = val * self.UNIT2M.get(unit, 1.0)
            return mbps, role
        except Exception:
            return None

    def _parse_json_interval(self, json_obj):
        """Extract metrics from iperf3 --json interval block.

        For future --json mode. Currently regex parsing is default for compatibility.
        Returns: dict with interval_up_mbps, interval_dn_mbps, jitter_ms, loss_pct or None
        """
        try:
            result = {}
            intervals = json_obj.get('intervals', [])
            if not intervals:
                return None
            last = intervals[-1]
            streams = last.get('streams', [])
            sums = last.get('sum', {})
            if sums:
                bps = sums.get('bits_per_second', 0)
                mbps = bps / 1_000_000.0
                sender = sums.get('sender', False)
                if sender:
                    result['interval_up_mbps'] = mbps
                else:
                    result['interval_dn_mbps'] = mbps
                if 'jitter_ms' in sums:
                    result['jitter_ms'] = sums['jitter_ms']
                if 'lost_percent' in sums:
                    result['loss_pct'] = sums['lost_percent']
            for s in streams:
                bps = s.get('bits_per_second', 0)
                mbps = bps / 1_000_000.0
                if s.get('sender', False):
                    result['interval_up_mbps'] = result.get('interval_up_mbps', 0) + mbps
                else:
                    result['interval_dn_mbps'] = result.get('interval_dn_mbps', 0) + mbps
                if 'jitter_ms' in s:
                    result['jitter_ms'] = max(result.get('jitter_ms', 0), s['jitter_ms'])
                if 'lost_percent' in s:
                    result['loss_pct'] = max(result.get('loss_pct', 0), s['lost_percent'])
            return result if result else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Task normalization
    # ------------------------------------------------------------------ #

    def _normalize_task(self, data: dict) -> dict:
        t = dict(data)
        if 'proto' not in t and 'protocol' in t:
            t['proto'] = t['protocol']
        if 'duration' not in t:
            for k in ('time', 'seconds'):
                if k in t:
                    t['duration'] = t[k]
                    break
        if 'parallel' not in t:
            for k in ('P', 'pairs', 'threads'):
                if k in t:
                    t['parallel'] = t[k]
                    break
        if 'bitrate' not in t:
            for k in ('bandwidth', 'bw'):
                if k in t:
                    t['bitrate'] = t[k]
                    break
        if 'length' not in t:
            for k in ('len', 'bytes'):
                if k in t:
                    t['length'] = t[k]
                    break
        if 'bind' not in t and 'bind_ip' in t:
            t['bind'] = t['bind_ip']
        if 'reverse' in t and isinstance(t['reverse'], str):
            t['reverse'] = t['reverse'].lower() in ('1', 'true', 'yes', 'on', 'y')
        if 'bidir' in t and isinstance(t['bidir'], str):
            t['bidir'] = t['bidir'].lower() in ('1', 'true', 'yes', 'on', 'y')
        if 'local_port' in t and isinstance(t['local_port'], str) and t['local_port'].isdigit():
            t['local_port'] = int(t['local_port'])
        if 'tos' in t and isinstance(t['tos'], str):
            t['tos'] = t['tos'].strip()
        if 'interval' in t and str(t['interval']).strip():
            t['interval'] = str(t['interval']).strip()
        if 'extra_args' in t and not isinstance(t['extra_args'], list):
            try:
                t['extra_args'] = [x for x in str(t['extra_args']).split(' ') if x]
            except Exception:
                t['extra_args'] = [str(t['extra_args'])]
        return t

    # ------------------------------------------------------------------ #
    # Client process management
    # ------------------------------------------------------------------ #

    def _start_client(self, task: dict):
        task = self._normalize_task(task)
        if 'target' not in task:
            raise ValueError("'target' required")
        if 'port' not in task:
            raise ValueError("'port' required")
        with self.LOCK:
            dead = [k for k, info in self.CLIENT_PROCS.items() if info['proc'].poll() is not None]
            for k in dead:
                self.CLIENT_PROCS.pop(k, None)
            if len(self.CLIENT_PROCS) >= self.MAX_CLIENTS:
                raise ValueError(f'max_clients({self.MAX_CLIENTS}) reached')
        if 'proto' not in task:
            task['proto'] = 'tcp'
        is_udp = str(task.get('proto', 'tcp')).lower() == 'udp'
        if is_udp:
            if task.get('bidir'):
                raise ValueError('UDP에서는 --bidir를 사용할 수 없습니다.')
            try:
                if int(task.get('parallel', 1)) > 1:
                    raise ValueError('UDP에서는 -P(>1) 옵션을 사용할 수 없습니다.')
            except ValueError:
                raise
            except Exception as e:
                self._log('WARN', 'client', f'parallel check failed: {e}')

        args = [self.iperf3_bin, '-c', task['target'], '-p', str(task['port'])]
        args += ['-i', str(task.get('interval', '1'))]
        args.append('--forceflush')
        if is_udp:
            args.append('-u')
        if task.get('bidir'):
            args.append('--bidir')
        elif task.get('reverse'):
            args.append('-R')
        if task.get('duration'):
            args += ['-t', str(int(task['duration']))]
        if task.get('bytes') is not None:
            args += ['-n', str(int(task['bytes']))]
        if task.get('blockcount') is not None:
            args += ['-k', str(int(task['blockcount']))]
        if task.get('omit'):
            args += ['-O', str(int(task['omit']))]
        if task.get('parallel') and int(task['parallel']) > 1:
            args += ['-P', str(int(task['parallel']))]
        if task.get('bitrate'):
            args += ['-b', str(task['bitrate'])]
        if task.get('length'):
            args += ['-l', str(task['length'])]
        if task.get('zerocopy'):
            args.append('-Z')
        if task.get('window'):
            args += ['-w', str(task['window'])]
        if task.get('bind'):
            args += ['-B', str(task['bind'])]
        if task.get('extra_args'):
            try:
                args += [str(x) for x in task['extra_args']]
            except Exception as e:
                self._log('WARN', 'client', f'extra_args parse error: {e}')

        log = os.path.join(self.LOG_DIR, f"client_{task['target']}_{task['port']}_{self._now_ts()}.log")
        lf = self._safe_open_log(log)
        proc = self._popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        key = f"{task['target']}:{task['port']}:{'B' if task.get('bidir') else ('R' if task.get('reverse') else 'F')}:{time.time()}"

        def reader():
            try:
                for line in proc.stdout:
                    try:
                        lf.write(line)
                    except Exception:
                        pass
                    # UDP interval parsing
                    u = self.UDP_INTERVAL_RE.search(line) or self.UDP_INTERVAL_RE2.search(line)
                    if u:
                        try:
                            if u.re is self.UDP_INTERVAL_RE:
                                bytes_val = (
                                    self._to_float(u.group(1))
                                    * self.BUNIT2B.get((u.group(2) or '').upper() or None, 1.0)
                                    if u.group(1)
                                    else None
                                )
                                mbps_val = (
                                    self._to_float(u.group(3))
                                    * self.UNIT2M.get((u.group(4) or '').upper() or None, 1.0)
                                    if u.group(3)
                                    else None
                                )
                                jitter_ms = self._to_float(u.group(5))
                                lost = float(u.group(6)) if u.group(6) is not None else None
                                total = float(u.group(7)) if u.group(7) is not None else None
                                loss_pct = (lost * 100.0 / total) if (lost is not None and total and total > 0) else None
                            else:
                                bytes_val = (
                                    self._to_float(u.group(1))
                                    * self.BUNIT2B.get((u.group(2) or '').upper() or None, 1.0)
                                    if u.group(1)
                                    else None
                                )
                                mbps_val = (
                                    self._to_float(u.group(3))
                                    * self.UNIT2M.get((u.group(4) or '').upper() or None, 1.0)
                                    if u.group(3)
                                    else None
                                )
                                jitter_ms = self._to_float(u.group(5))
                                loss_pct = self._to_float(u.group(7)) if len(u.groups()) >= 7 else None
                        except Exception:
                            bytes_val = mbps_val = jitter_ms = loss_pct = None
                        with self.LOCK:
                            info = self.CLIENT_PROCS.get(key)
                            if info:
                                lj = info.get('last_json') or {}
                                rev = bool(info.get('task', {}).get('reverse'))
                                if mbps_val is not None:
                                    if rev:
                                        lj['interval_dn_mbps'] = mbps_val
                                    else:
                                        lj['interval_up_mbps'] = mbps_val
                                if bytes_val is not None:
                                    if rev:
                                        lj['interval_dn_bytes'] = bytes_val
                                    else:
                                        lj['interval_up_bytes'] = bytes_val
                                if jitter_ms is not None:
                                    lj['jitter_ms'] = jitter_ms
                                if loss_pct is not None:
                                    lj['loss_pct'] = loss_pct
                                info['last_json'] = lj
                        continue

                    # TCP bidir interval parsing
                    m = self.TCP_BR_RE.search(line)
                    if m:
                        role_tok = (m.group(1) or '').upper()
                        bytes_val = (
                            self._to_float(m.group(2))
                            * self.BUNIT2B.get((m.group(3) or '').upper() or None, 1.0)
                            if m.group(2)
                            else None
                        )
                        mbps_val = (
                            self._to_float(m.group(4))
                            * self.UNIT2M.get((m.group(5) or '').upper() or None, 1.0)
                            if m.group(4)
                            else None
                        )
                        with self.LOCK:
                            info = self.CLIENT_PROCS.get(key)
                            if info:
                                lj = info.get('last_json') or {}
                                if role_tok == 'TX-C':
                                    if mbps_val is not None:
                                        lj['interval_up_mbps'] = mbps_val
                                    if bytes_val is not None:
                                        lj['interval_up_bytes'] = bytes_val
                                elif role_tok == 'RX-C':
                                    if mbps_val is not None:
                                        lj['interval_dn_mbps'] = mbps_val
                                    if bytes_val is not None:
                                        lj['interval_dn_bytes'] = bytes_val
                                else:
                                    if mbps_val is not None:
                                        lj['interval_mbps'] = mbps_val
                                info['last_json'] = lj
                        continue

                    # Generic TCP interval parsing
                    res = self._parse_interval_line(line)
                    if res is not None:
                        mbps, role = res
                        with self.LOCK:
                            info = self.CLIENT_PROCS.get(key)
                            if info:
                                lj = info.get('last_json') or {}
                                if role == 'sender':
                                    lj['interval_up_mbps'] = mbps
                                elif role == 'receiver':
                                    lj['interval_dn_mbps'] = mbps
                                else:
                                    lj['interval_mbps'] = mbps
                                info['last_json'] = lj
            finally:
                code = proc.poll()
                try:
                    lf.write(f"\n[exit_code] {code}\n")
                    lf.close()
                except Exception:
                    pass
                with self.LOCK:
                    info = self.CLIENT_PROCS.get(key)
                    if info is not None:
                        info['exit_code'] = code
                    self.CLIENT_PROCS.pop(key, None)

        with self.LOCK:
            self.CLIENT_PROCS[key] = {
                'proc': proc,
                'start_ts': time.time(),
                'last_json': None,
                'task': task,
                'exit_code': None,
                'log': log,
            }
        threading.Thread(target=reader, daemon=True).start()
        return key

    # ------------------------------------------------------------------ #
    # Discovery responder
    # ------------------------------------------------------------------ #

    def _discover_responder(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        sock.bind(('', self.DISCOVER_PORT))
        sock.settimeout(0.5)
        name = socket.gethostname()
        base_ip = self._advertise_ip()
        base = f"http://{base_ip}:{self.port}"
        try:
            ip_list = list_local_ipv4(exclude_loopback=True)
        except Exception:
            ip_list = [base_ip]
        while not self.stop_flag:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                break
            try:
                msg = data.decode('utf-8', 'ignore')
            except Exception:
                msg = ''
            if msg.startswith('IPERF3_DISCOVER'):
                with self.LOCK:
                    servers = sorted([p for p, pr in self.SERVER_PROCS.items() if pr.poll() is None])
                payload = {
                    'name': name,
                    'base': base,
                    'servers': servers,
                    'version': AGENT_VERSION,
                    'mgmt': base_ip,
                    'ips': ip_list,
                    'non_mgmt_ips': [ip for ip in ip_list if ip != base_ip],
                }
                try:
                    sock.sendto(json.dumps(payload).encode('utf-8'), addr)
                except Exception:
                    pass
        sock.close()

    # ------------------------------------------------------------------ #
    # HTTP handler
    # ------------------------------------------------------------------ #

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 10

            def setup(self):
                super().setup()
                try:
                    self.connection.settimeout(10)
                except Exception:
                    pass

            def log_message(self, fmt, *args):
                return

            def _json(self, code, obj):
                data = json.dumps(obj).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                p = urlparse(self.path)
                if p.path == '/status':
                    with outer.LOCK:
                        servers = []
                        for port, proc in list(outer.SERVER_PROCS.items()):
                            alive = proc.poll() is None
                            if not alive:
                                outer.SERVER_PROCS.pop(port, None)
                            else:
                                servers.append({'port': port, 'alive': True})
                        clients = []
                        for k, info in outer.CLIENT_PROCS.items():
                            clients.append({
                                'key': k,
                                'exit_code': info.get('exit_code'),
                                'last': info.get('last_json'),
                            })
                    self._json(200, {
                        'servers': servers,
                        'clients': clients,
                        'port': outer.port,
                        'log_dir': outer.LOG_DIR,
                        'log_dir_ok': outer._log_dir_ok,
                        'mgmt': outer._advertise_ip(),
                        'ips': list_local_ipv4(True),
                    })
                    return
                if p.path == '/metrics':
                    snap = []
                    with outer.LOCK:
                        for k, info in outer.CLIENT_PROCS.items():
                            snap.append({
                                'key': k,
                                'task': info['task'],
                                'json': info['last_json'],
                                'exit_code': info.get('exit_code'),
                            })
                    self._json(200, {'metrics': snap})
                    return
                self._json(404, {'error': 'not found'})

            def do_POST(self):
                try:
                    if outer.api_token:
                        req_token = (self.headers.get('X-API-Key') or '').strip()
                        if req_token != outer.api_token:
                            self._json(403, {'error': 'forbidden'})
                            return
                    p = urlparse(self.path)
                    ln = int(self.headers.get('Content-Length', '0'))
                    if ln > 64 * 1024:
                        self._json(413, {'error': 'payload too large'})
                        return
                    body = self.rfile.read(ln) if ln > 0 else b'{}'
                    try:
                        data = json.loads(body.decode('utf-8'))
                    except Exception:
                        data = {}

                    if p.path == '/server/start':
                        ports = data.get('ports', [5201])
                        bind_global = data.get('bind')
                        bind_map = data.get('bind_map', {})
                        started, already, errors = [], [], {}
                        with outer.LOCK:
                            dead = [pt for pt, pr in outer.SERVER_PROCS.items() if pr.poll() is not None]
                            for pt in dead:
                                outer.SERVER_PROCS.pop(pt, None)
                            for port in ports:
                                try:
                                    port = int(port)
                                except Exception:
                                    errors[str(port)] = 'invalid_port'
                                    continue
                                if port in outer.SERVER_PROCS:
                                    already.append(port)
                                    continue
                                if len(outer.SERVER_PROCS) >= outer.MAX_SERVERS:
                                    errors[str(port)] = f'max_servers({outer.MAX_SERVERS}) reached'
                                    continue
                                try:
                                    bind_ip = bind_map.get(str(port)) or bind_global
                                    proc, _ = outer._start_server_port(int(port), bind_ip=bind_ip)
                                    outer.SERVER_PROCS[int(port)] = proc
                                    started.append(port)
                                except Exception as e:
                                    errors[str(port)] = str(e)
                        self._json(200, {'started': started, 'already_running': already, 'errors': errors})
                        return

                    if p.path in ('server/stop', '/server/stop'):
                        req_ports = data.get('ports')
                        to_stop = None
                        if isinstance(req_ports, list) and req_ports:
                            try:
                                to_stop = set(int(x) for x in req_ports)
                            except Exception:
                                to_stop = None
                        stopped = []
                        with outer.LOCK:
                            for port, proc in list(outer.SERVER_PROCS.items()):
                                if (to_stop is None) or (int(port) in to_stop):
                                    outer._stop_proc(proc)
                                    outer.SERVER_PROCS.pop(port, None)
                                    stopped.append(int(port))
                        self._json(200, {'stopped': stopped})
                        return

                    if p.path == '/client/start':
                        try:
                            key = outer._start_client(data)
                        except FileNotFoundError as e:
                            self._json(500, {'error': str(e)})
                            return
                        except (ValueError, OSError, RuntimeError) as e:
                            self._json(500, {'error': str(e)})
                            return
                        self._json(200, {'client_key': key})
                        return

                    if p.path == '/client/stop':
                        count = 0
                        with outer.LOCK:
                            for k, info in list(outer.CLIENT_PROCS.items()):
                                outer._stop_proc(info['proc'])
                                outer.CLIENT_PROCS.pop(k, None)
                                count += 1
                        self._json(200, {'stopped_clients': count})
                        return

                    self._json(404, {'error': 'not found'})
                except Exception as e:
                    try:
                        self._json(500, {'error': str(e)})
                    except Exception as e2:
                        outer._log('ERR', 'http', f'double fault: {e} / {e2}')

        return Handler

    # ------------------------------------------------------------------ #
    # Service lifecycle
    # ------------------------------------------------------------------ #

    def start(self):
        if self.httpd:
            return
        self.stop_flag = False
        try:
            self.iperf3_bin = resolve_iperf3_path(self.iperf3_bin)
            ver_out = subprocess.check_output(
                [self.iperf3_bin, '-v'], text=True, stderr=subprocess.STDOUT, timeout=3
            )
            self.version_str = ver_out.strip().splitlines()[0]
        except Exception as e:
            self.version_str = f'? ({e})'

        class ReuseThreadingHTTPServer(ThreadingHTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.httpd = ReuseThreadingHTTPServer((self.host, self.port), self._make_handler())
        self.http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()
        self.disc_thread = threading.Thread(target=self._discover_responder, daemon=True)
        self.disc_thread.start()
        self._register_runtime_hooks()
        if self.autostart_ports:
            with self.LOCK:
                for p in self.autostart_ports:
                    try:
                        proc, _ = self._start_server_port(int(p))
                        self.SERVER_PROCS[int(p)] = proc
                    except Exception as e:
                        self._log('WARN', 'autostart', f'port {p} failed: {e}')

    def _atexit_cleanup(self):
        with self.LOCK:
            servers = list(self.SERVER_PROCS.values())
            clients = list(self.CLIENT_PROCS.values())
        for proc in servers:
            try:
                proc.kill()
            except Exception:
                pass
        for info in clients:
            try:
                info['proc'].kill()
            except Exception:
                pass

    def stop(self):
        if not self.httpd:
            return
        self.stop_flag = True
        with self.LOCK:
            for proc in list(self.SERVER_PROCS.values()):
                self._stop_proc(proc)
            for info in list(self.CLIENT_PROCS.values()):
                self._stop_proc(info['proc'])
            self.SERVER_PROCS.clear()
            self.CLIENT_PROCS.clear()
        try:
            self.httpd.shutdown()
        except Exception:
            pass
        self.httpd.server_close()
        self.httpd = None
        self.http_thread = None
        self.disc_thread = None

    def current_servers(self) -> list[int]:
        with self.LOCK:
            return sorted([port for port, proc in self.SERVER_PROCS.items() if proc.poll() is None])

    def base_url(self) -> str:
        return f"http://{self._advertise_ip()}:{self.port}"
