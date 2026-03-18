# -*- coding: utf-8 -*-
"""
core.helpers - Pure Python utility functions (no UI dependencies).

Extracted from agent_gui_v6_0_2.py and live_dashboard.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

IS_WIN = os.name == 'nt'
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def win_hidden_startupinfo():
    """Return a STARTUPINFO that hides the console window on Windows."""
    if not IS_WIN:
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si


def _writable_dir(path: Path) -> bool:
    """Check if *path* can be created and written to."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / '.__wtest__'
        with open(test, 'w', encoding='utf-8') as f:
            f.write('ok')
        try:
            test.unlink(missing_ok=True)
        except TypeError:
            if test.exists():
                test.unlink()
        return True
    except Exception:
        return False


def resolve_log_dir(app_name: str = "iperf3-agent") -> str:
    """Determine a writable log directory, trying several candidates."""
    override = os.environ.get('AGENT_LOGDIR')
    if override:
        p = Path(override)
        if _writable_dir(p):
            return str(p)
    la = os.environ.get('LOCALAPPDATA')
    if la:
        p = Path(la) / app_name / 'logs'
        if _writable_dir(p):
            return str(p)
    pd = os.environ.get('PROGRAMDATA')
    if pd:
        p = Path(pd) / app_name / 'logs'
        if _writable_dir(p):
            return str(p)
    base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    p = base_dir / 'logs'
    if _writable_dir(p):
        return str(p)
    import tempfile
    p = Path(tempfile.gettempdir()) / app_name / 'logs'
    _writable_dir(p)
    return str(p)


def resolve_iperf3_path(preferred: str | None = None) -> str:
    """Locate the iperf3 binary, checking several candidate paths."""
    if preferred:
        p = Path(preferred)
        if p.exists():
            return str(p)
    base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    for cand in ['iperf3.exe', 'iperf3']:
        p = base_dir / cand
        if p.exists():
            return str(p)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        for cand in ['iperf3.exe', 'iperf3']:
            p = Path(sys._MEIPASS) / cand
            if p.exists():
                return str(p)
    found = shutil.which('iperf3')
    if found:
        return found
    raise FileNotFoundError(
        'iperf3 실행 파일을 찾지 못했습니다. 실행 폴더에 iperf3.exe를 두거나 UI에서 경로를 지정하세요.'
    )


def list_local_ipv4(exclude_loopback: bool = True) -> list[str]:
    """Return sorted list of local IPv4 addresses."""
    ips: set[str] = set()
    try:
        for fam, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None):
            if fam == socket.AF_INET:
                ip = sockaddr[0]
                if exclude_loopback and ip.startswith('127.'):
                    continue
                ips.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not (exclude_loopback and ip.startswith('127.')):
            ips.add(ip)
    except Exception:
        pass
    try:
        return sorted(ips, key=lambda x: tuple(int(p) for p in x.split('.')))
    except Exception:
        pass

    # Windows fallback: parse ipconfig
    try:
        import locale
        encs = [locale.getpreferredencoding(False), 'cp949', 'utf-8', 'latin1']
        out = None
        for enc in encs:
            try:
                out = subprocess.check_output(['ipconfig'], text=True, encoding=enc, errors='ignore')
                break
            except Exception:
                continue
        if out:
            for line in out.splitlines():
                s = line.strip()
                if ('IPv4 주소' in s) or ('IPv4 Address' in s):
                    ip = s.split(':')[-1].strip()
                    if exclude_loopback and ip.startswith('127.'):
                        continue
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                        ips.add(ip)
            return sorted(list(ips), key=lambda x: tuple(int(p) for p in x.split('.')))
    except Exception:
        pass
    return sorted(list(ips))


def list_local_interfaces(exclude_loopback: bool = True) -> list[dict]:
    """Return list of ``{"iface": "eth0", "ip": "10.0.0.1"}`` dicts.

    Tries ``ip -j addr`` (Linux), then ``ipconfig`` (Windows) for adapter names.
    Falls back to IP-only entries from :func:`list_local_ipv4`.
    """
    results: list[dict] = []

    # Linux: ``ip -j addr`` gives structured JSON
    if not IS_WIN:
        try:
            import json as _json
            raw = subprocess.check_output(
                ['ip', '-j', 'addr'],
                text=True, timeout=5,
            )
            data = _json.loads(raw)
            for entry in data:
                ifname = entry.get('ifname', '')
                if exclude_loopback and ifname == 'lo':
                    continue
                for ai in entry.get('addr_info', []):
                    if ai.get('family') != 'inet':
                        continue
                    ip = ai.get('local', '')
                    if ip:
                        results.append({'iface': ifname, 'ip': ip})
        except Exception:
            pass
        if results:
            return results

    # Windows: parse ipconfig
    if IS_WIN:
        try:
            import locale
            encs = [locale.getpreferredencoding(False), 'cp949', 'utf-8', 'latin1']
            out = None
            for enc in encs:
                try:
                    out = subprocess.check_output(
                        ['ipconfig', '/all'], text=True, encoding=enc, errors='ignore',
                    )
                    break
                except Exception:
                    continue
            if out:
                current_adapter = ''
                for line in out.splitlines():
                    stripped = line.strip()
                    # Adapter header lines are not indented
                    if line and not line[0].isspace() and ':' in line:
                        current_adapter = line.split(':')[0].strip()
                        # Remove "Ethernet adapter" / "Wireless LAN adapter" prefix
                        for pfx in ('Ethernet adapter', 'Wireless LAN adapter',
                                    'Ethernet-Adapter', 'Drahtlos-LAN-Adapter'):
                            if current_adapter.startswith(pfx):
                                current_adapter = current_adapter[len(pfx):].strip()
                    if ('IPv4 Address' in stripped or 'IPv4-Adresse' in stripped
                            or 'IPv4 주소' in stripped):
                        ip = stripped.split(':')[-1].strip().rstrip('(Preferred)').rstrip('(Bevorzugt)').strip()
                        if exclude_loopback and ip.startswith('127.'):
                            continue
                        if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                            results.append({'iface': current_adapter or ip, 'ip': ip})
        except Exception:
            pass
        if results:
            return results

    # Fallback: IP-only
    for ip in list_local_ipv4(exclude_loopback):
        results.append({'iface': ip, 'ip': ip})
    return results

def is_ipv4(s: str) -> bool:
    """Check if string is a valid IPv4 address."""
    parts = s.split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except Exception:
        return False


def is_ipv4_host(s: str) -> bool:
    """Check if string is a valid IPv4 host address (not network/broadcast)."""
    if not is_ipv4(s):
        return False
    try:
        octs = [int(p) for p in s.split('.')]
        if octs[3] in (0, 255):
            return False
    except Exception:
        pass
    return True


def extract_ip_port(base_url: str) -> tuple[str, int]:
    """Extract (hostname, port) from an agent URL."""
    try:
        p = urlparse(base_url)
        return (p.hostname or ''), (p.port or 9001)
    except Exception:
        return ('', 9001)


def to_float(x, default=None):
    """Safe float conversion."""
    try:
        return float(x)
    except Exception:
        return default
