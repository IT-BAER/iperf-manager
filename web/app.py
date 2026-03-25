# -*- coding: utf-8 -*-
"""web/app.py – Flask + Socket.IO backend for the iperf-manager web dashboard.

Reuses *only* the existing core/ modules (zero modifications).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import ipaddress
import json
import os
import socket
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from croniter import croniter, CroniterBadCronError
from flask import Flask, jsonify, render_template, request, send_from_directory, abort, session
from werkzeug.security import check_password_hash

try:
    from flask_socketio import SocketIO, emit
except ImportError:
    raise SystemExit("flask-socketio is required. Install with: pip install -r requirements.txt")

# ── Core imports (read-only, no modifications) ──────────────────────────
from core.net_utils import http_get_json, http_post_json, poll_metrics
from core.test_runner import run_test
from core.constants import (
    DISCOVER_PORT, DEFAULT_API_PORT, DEFAULT_BASE_PORT,
    TEST_MODES, PROTOCOLS, DASHBOARD_VERSION,
)

# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROFILES_DIR = DATA_DIR / "profiles"
LEGACY_PRIVATE_STATE_DIR = DATA_DIR / ".dashboard"

_private_state_dir_raw = os.environ.get("IPERF_MANAGER_STATE_DIR", "").strip()
if _private_state_dir_raw:
    PRIVATE_STATE_DIR = Path(_private_state_dir_raw).expanduser()
    if not PRIVATE_STATE_DIR.is_absolute():
        PRIVATE_STATE_DIR = BASE_DIR / PRIVATE_STATE_DIR
else:
    PRIVATE_STATE_DIR = LEGACY_PRIVATE_STATE_DIR

PRIVATE_STATE_DIR = PRIVATE_STATE_DIR.resolve()
AGENTS_STATE_FILE = PRIVATE_STATE_DIR / "agents.json"
SCHEDULES_STATE_FILE = PRIVATE_STATE_DIR / "schedules.json"


def _init_runtime_dirs() -> None:
    """Ensure runtime directories exist and migrate legacy private state when needed."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_STATE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        PRIVATE_STATE_DIR.chmod(0o700)
    except OSError:
        pass

    if PRIVATE_STATE_DIR != LEGACY_PRIVATE_STATE_DIR:
        for file_name in ("agents.json", "schedules.json"):
            src = LEGACY_PRIVATE_STATE_DIR / file_name
            dst = PRIVATE_STATE_DIR / file_name
            if src.is_file() and not dst.exists():
                try:
                    dst.write_bytes(src.read_bytes())
                except Exception:
                    continue
            if dst.is_file():
                try:
                    dst.chmod(0o600)
                except OSError:
                    pass


_init_runtime_dirs()

# ── Flask / Socket.IO setup ─────────────────────────────────────────────


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}

app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static"),
)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET") or secrets.token_hex(32)
app.config["SESSION_COOKIE_NAME"] = "iperf_manager_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in {
    "1", "true", "yes", "on",
}
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    hours=max(1, _env_int("DASHBOARD_AUTH_SESSION_HOURS", 12))
)

_cors_origins = os.environ.get("CORS_ORIGINS", "").strip()
_socketio_kwargs: dict[str, object] = {"async_mode": "threading"}
if _cors_origins:
    _socketio_kwargs["cors_allowed_origins"] = [
        origin.strip() for origin in _cors_origins.split(",") if origin.strip()
    ]
socketio = SocketIO(app, **_socketio_kwargs)

_AUTH_DISABLED = _env_flag("DASHBOARD_AUTH_DISABLE")
_AUTH_USERNAME = os.environ.get("DASHBOARD_AUTH_USERNAME", "").strip() or "admin"
_AUTH_PASSWORD = os.environ.get("DASHBOARD_AUTH_PASSWORD", "")
_AUTH_PASSWORD_HASH = os.environ.get("DASHBOARD_AUTH_PASSWORD_HASH", "")
_AUTH_GENERATED_PASSWORD = ""
if not _AUTH_DISABLED and not (_AUTH_PASSWORD_HASH or _AUTH_PASSWORD):
    _AUTH_GENERATED_PASSWORD = secrets.token_urlsafe(18)
    _AUTH_PASSWORD = _AUTH_GENERATED_PASSWORD
_LOGIN_WINDOW_SEC = max(60, _env_int("DASHBOARD_AUTH_RATE_WINDOW_SEC", 900))
_LOGIN_MAX_ATTEMPTS = max(1, _env_int("DASHBOARD_AUTH_MAX_ATTEMPTS", 5))
_LOGIN_FAILURES: dict[str, list[float]] = {}

# ── In-memory state ─────────────────────────────────────────────────────
_agents: dict[str, dict] = {}          # {agent_id: {url, name, status, last_seen}}
_agents_lock = threading.Lock()

_test_state: dict = {"status": "idle"}  # idle | running | stopping
_test_lock = threading.Lock()
_stop_event = threading.Event()
_test_thread: threading.Thread | None = None
_poller_thread: threading.Thread | None = None
_current_csv: str | None = None

_schedules: dict[str, dict] = {}
_schedule_lock = threading.Lock()
_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                            ║
# ╚══════════════════════════════════════════════════════════════════════╝

def _agent_id(url: str) -> str:
    """Deterministic short ID from agent URL."""
    return hashlib.md5(url.encode()).hexdigest()[:10]


def _dashboard_auth_enabled() -> bool:
    """Return True when dashboard login is enabled."""
    return not _AUTH_DISABLED


def auth_bootstrap_summary() -> str:
    """Describe the effective dashboard authentication mode for startup logs."""
    if not _dashboard_auth_enabled():
        return "[iperf-manager] Dashboard auth disabled via DASHBOARD_AUTH_DISABLE"
    if _AUTH_GENERATED_PASSWORD:
        return (
            "[iperf-manager] Dashboard auth enabled with generated credentials: "
            f"username={_AUTH_USERNAME} password={_AUTH_GENERATED_PASSWORD}"
        )
    return f"[iperf-manager] Dashboard auth enabled for username={_AUTH_USERNAME}"


def _dashboard_request_authenticated() -> bool:
    """Return True for authenticated dashboard sessions or when auth is disabled."""
    if not _dashboard_auth_enabled():
        return True
    if not session.get("auth_ok"):
        return False
    return hmac.compare_digest(str(session.get("auth_user", "") or ""), _AUTH_USERNAME)


def _client_ip() -> str:
    """Resolve the client IP, honoring reverse proxy forwarding when present."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def _recent_login_failures(client_ip: str) -> list[float]:
    """Return recent failed login timestamps for the client."""
    now = time.time()
    attempts = [
        ts for ts in _LOGIN_FAILURES.get(client_ip, [])
        if now - ts < _LOGIN_WINDOW_SEC
    ]
    if attempts:
        _LOGIN_FAILURES[client_ip] = attempts
    else:
        _LOGIN_FAILURES.pop(client_ip, None)
    return attempts


def _record_login_failure(client_ip: str):
    """Track a failed login attempt for basic in-memory rate limiting."""
    attempts = _recent_login_failures(client_ip)
    attempts.append(time.time())
    _LOGIN_FAILURES[client_ip] = attempts


def _clear_login_failures(client_ip: str):
    """Clear recorded login failures after a successful authentication."""
    _LOGIN_FAILURES.pop(client_ip, None)


def _verify_dashboard_password(password: str) -> bool:
    """Verify the submitted dashboard password against the configured secret."""
    if _AUTH_PASSWORD_HASH:
        try:
            return check_password_hash(_AUTH_PASSWORD_HASH, password)
        except ValueError:
            return False
    return hmac.compare_digest(password, _AUTH_PASSWORD)


def _auth_state() -> dict:
    """Serialize the current dashboard authentication state for the SPA."""
    authenticated = _dashboard_request_authenticated()
    return {
        "enabled": _dashboard_auth_enabled(),
        "authenticated": authenticated,
        "username": _AUTH_USERNAME if authenticated else "",
    }


def _normalize_agent_url(url: str) -> str:
    """Validate and normalize a manually added agent base URL."""
    raw = url.strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("agent url must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("agent url must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("agent url must not include credentials")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("agent url must not include a path, query, or fragment")

    host = parsed.hostname
    if host and ":" in host:
        host = f"[{host}]"

    normalized = f"{parsed.scheme}://{host}"
    if parsed.port:
        normalized += f":{parsed.port}"
    return normalized


def _save_agents_state():
    """Persist dashboard-managed agent settings, including stored API keys."""
    with _agents_lock:
        snapshot = [
            {
                "url": info.get("url", ""),
                "name": info.get("name", ""),
                "api_key": info.get("api_key", ""),
            }
            for info in _agents.values()
            if info.get("url")
        ]

    tmp_path = AGENTS_STATE_FILE.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass
        tmp_path.replace(AGENTS_STATE_FILE)
        try:
            AGENTS_STATE_FILE.chmod(0o600)
        except OSError:
            pass
    except Exception:
        pass


def _load_agents_state():
    """Restore dashboard-managed agent settings from the private runtime state file."""
    try:
        raw = json.loads(AGENTS_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(raw, list):
        return

    restored: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            url = _normalize_agent_url(str(item.get("url", "")))
        except ValueError:
            continue
        aid = _agent_id(url)
        restored[aid] = {
            "id": aid,
            "url": url,
            "name": str(item.get("name", "")).strip() or url,
            "status": "unknown",
            "last_seen": None,
            "api_key": str(item.get("api_key", "") or "").strip(),
            "details": {},
        }

    with _agents_lock:
        _agents.update(restored)


def _public_agent(info: dict) -> dict:
    """Remove secret fields before returning agent data to the browser."""
    public = dict(info)
    public.pop("api_key", None)
    details = public.get("details")
    if isinstance(details, dict):
        public["details"] = {
            key: details[key]
            for key in ("version", "ips", "interfaces")
            if key in details
        }
    return public


def _public_test_config(config: dict | None) -> dict | None:
    """Redact agent API keys from test config data sent to the browser."""
    if not isinstance(config, dict):
        return None

    public = dict(config)
    public["api_key"] = ""
    public["clients"] = [
        {**client, "api_key": ""} if isinstance(client, dict) else client
        for client in config.get("clients", [])
    ]
    return public


def _public_test_state(state: dict) -> dict:
    """Return a browser-safe snapshot of current test state."""
    public = dict(state)
    if "config" in public:
        public["config"] = _public_test_config(public.get("config"))
    return public


def _redact_profile_config(config: dict | None) -> dict | None:
    """Strip secrets before writing profiles to disk."""
    if not isinstance(config, dict):
        return None
    return _public_test_config(config)


def _validate_test_start_config(config: dict | None) -> str | None:
    """Validate that a test-start payload has the required minimum shape."""
    if not isinstance(config, dict):
        return "config required"
    if not str(config.get("server_agent", "") or "").strip():
        return "server agent required"
    clients = config.get("clients")
    if not isinstance(clients, list) or not clients:
        return "at least one client agent is required"
    return None


def _start_test_with_config(config: dict, *, trigger: str, schedule_id: str | None = None) -> tuple[dict, int]:
    """Start a test run from the provided config payload."""
    global _test_thread

    err = _validate_test_start_config(config)
    if err:
        return {"error": err}, 400

    with _test_lock:
        if _test_state["status"] == "running":
            return {"error": "test already running"}, 409

        _stop_event.clear()
        _test_state["status"] = "running"
        _test_state["started_at"] = time.time()
        _test_state["config"] = _public_test_config(config)
        _test_state["trigger"] = trigger
        if schedule_id:
            _test_state["schedule_id"] = schedule_id
        else:
            _test_state.pop("schedule_id", None)

    _test_thread = threading.Thread(target=_run_test_thread, args=(config,), daemon=True)
    _test_thread.start()
    return {"ok": True, "status": "running"}, 200


def _normalize_cron_expression(expr: str) -> str:
    """Collapse whitespace in cron expressions."""
    return " ".join((expr or "").strip().split())


def _validate_cron_expression(expr: str) -> str | None:
    """Validate expected cron syntax (5 fields, standard minute-hour-day-month-weekday)."""
    normalized = _normalize_cron_expression(expr)
    if len(normalized.split()) != 5:
        return "cron must have 5 fields: minute hour day month weekday"
    try:
        croniter(normalized, datetime.now())
    except (CroniterBadCronError, ValueError):
        return "invalid cron expression"
    return None


def _next_cron_timestamp(expr: str, after_ts: float) -> float | None:
    """Compute next execution timestamp for a cron expression."""
    try:
        return float(croniter(_normalize_cron_expression(expr), datetime.fromtimestamp(after_ts)).get_next(float))
    except (CroniterBadCronError, ValueError, TypeError, OSError):
        return None


def _manual_schedule_summary(config: dict | None) -> dict:
    """Build a non-sensitive summary for manual schedule configs."""
    if not isinstance(config, dict):
        return {"server_agent": "", "client_count": 0, "duration_sec": 0, "protocol": "", "mode": ""}

    clients = config.get("clients")
    client_count = len(clients) if isinstance(clients, list) else 0
    duration = config.get("duration_sec", 0)
    try:
        duration_int = int(duration)
    except (TypeError, ValueError):
        duration_int = 0

    return {
        "server_agent": str(config.get("server_agent", "") or ""),
        "client_count": client_count,
        "duration_sec": max(0, duration_int),
        "protocol": str(config.get("protocol", "") or ""),
        "mode": str(config.get("mode", "") or ""),
    }


def _public_schedule(schedule: dict) -> dict:
    """Return a browser-safe schedule payload."""
    public = {
        "id": str(schedule.get("id", "") or ""),
        "name": str(schedule.get("name", "") or ""),
        "cron": str(schedule.get("cron", "") or ""),
        "enabled": bool(schedule.get("enabled", False)),
        "source": str(schedule.get("source", "profile") or "profile"),
        "profile_name": str(schedule.get("profile_name", "") or ""),
        "next_run_at": schedule.get("next_run_at"),
        "last_run_at": schedule.get("last_run_at"),
        "last_result": str(schedule.get("last_result", "") or ""),
        "created_at": schedule.get("created_at"),
        "updated_at": schedule.get("updated_at"),
    }
    if public["source"] == "manual":
        public["manual_summary"] = _manual_schedule_summary(schedule.get("config"))
    return public


def _save_schedules_state_locked() -> None:
    """Persist scheduler state to disk. Caller must hold _schedule_lock."""
    snapshot: list[dict] = []
    for schedule in _schedules.values():
        source = str(schedule.get("source", "profile") or "profile")
        item = {
            "id": str(schedule.get("id", "") or ""),
            "name": str(schedule.get("name", "") or ""),
            "cron": str(schedule.get("cron", "") or ""),
            "enabled": bool(schedule.get("enabled", False)),
            "source": source,
            "profile_name": str(schedule.get("profile_name", "") or ""),
            "next_run_at": schedule.get("next_run_at"),
            "last_run_at": schedule.get("last_run_at"),
            "last_result": str(schedule.get("last_result", "") or ""),
            "created_at": schedule.get("created_at"),
            "updated_at": schedule.get("updated_at"),
        }
        if source == "manual" and isinstance(schedule.get("config"), dict):
            item["config"] = schedule.get("config")
        snapshot.append(item)

    tmp_path = SCHEDULES_STATE_FILE.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass
        tmp_path.replace(SCHEDULES_STATE_FILE)
        try:
            SCHEDULES_STATE_FILE.chmod(0o600)
        except OSError:
            pass
    except Exception:
        pass


def _save_schedules_state() -> None:
    """Persist scheduler state with locking."""
    with _schedule_lock:
        _save_schedules_state_locked()


def _load_schedules_state() -> None:
    """Restore saved scheduler definitions from disk."""
    try:
        raw = json.loads(SCHEDULES_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    if not isinstance(raw, list):
        return

    now = time.time()
    restored: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue

        schedule_id = str(item.get("id", "") or "").strip() or secrets.token_hex(8)
        name = str(item.get("name", "") or "").strip() or f"schedule-{schedule_id[:6]}"
        cron_expr = _normalize_cron_expression(str(item.get("cron", "") or ""))
        source = str(item.get("source", "profile") or "profile")
        enabled = bool(item.get("enabled", False))

        if source not in {"profile", "manual"}:
            continue
        if _validate_cron_expression(cron_expr):
            continue

        created_at = item.get("created_at")
        updated_at = item.get("updated_at")
        try:
            created_ts = float(created_at) if created_at is not None else now
        except (TypeError, ValueError):
            created_ts = now
        try:
            updated_ts = float(updated_at) if updated_at is not None else created_ts
        except (TypeError, ValueError):
            updated_ts = created_ts

        schedule: dict = {
            "id": schedule_id,
            "name": name,
            "cron": cron_expr,
            "enabled": enabled,
            "source": source,
            "last_result": str(item.get("last_result", "") or ""),
            "created_at": created_ts,
            "updated_at": updated_ts,
            "last_run_at": item.get("last_run_at"),
            "next_run_at": item.get("next_run_at"),
        }

        if source == "profile":
            schedule["profile_name"] = Path(str(item.get("profile_name", "") or "")).name
            if not schedule["profile_name"]:
                continue
        else:
            config = item.get("config")
            if not isinstance(config, dict):
                continue
            schedule["config"] = config

        try:
            next_run = float(schedule.get("next_run_at"))
        except (TypeError, ValueError):
            next_run = None

        if enabled and (next_run is None or next_run <= now):
            next_run = _next_cron_timestamp(cron_expr, now)
        schedule["next_run_at"] = next_run

        restored[schedule_id] = schedule

    with _schedule_lock:
        _schedules.clear()
        _schedules.update(restored)


def _resolve_schedule_config(schedule: dict) -> tuple[dict | None, str | None]:
    """Resolve schedule source into a runnable config payload."""
    source = str(schedule.get("source", "profile") or "profile")
    if source == "profile":
        profile_name = Path(str(schedule.get("profile_name", "") or "")).name
        if not profile_name:
            return None, "profile name is required"

        path = PROFILES_DIR / f"{profile_name}.json"
        if path.resolve().parent != PROFILES_DIR.resolve():
            return None, "invalid profile name"
        if not path.is_file():
            return None, f"profile \"{profile_name}\" not found"

        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None, f"profile \"{profile_name}\" could not be read"

        if not isinstance(config, dict):
            return None, "profile config is invalid"
        return config, None

    config = schedule.get("config")
    if not isinstance(config, dict):
        return None, "manual config is missing"
    return dict(config), None


def _set_schedule_result(schedule_id: str, result: str, *, mark_run: bool) -> None:
    """Update schedule run status and persist the result."""
    with _schedule_lock:
        schedule = _schedules.get(schedule_id)
        if not schedule:
            return
        now = time.time()
        if mark_run:
            schedule["last_run_at"] = now
        schedule["last_result"] = result
        schedule["updated_at"] = now
        _save_schedules_state_locked()


def _execute_schedule(schedule_id: str) -> None:
    """Run a due schedule once."""
    with _schedule_lock:
        schedule = _schedules.get(schedule_id)
        if not schedule or not schedule.get("enabled", False):
            return
        schedule_copy = dict(schedule)

    config, err = _resolve_schedule_config(schedule_copy)
    if err:
        _set_schedule_result(schedule_id, f"error: {err}", mark_run=False)
        return

    response, status = _start_test_with_config(config, trigger="schedule", schedule_id=schedule_id)
    if status == 200:
        _set_schedule_result(schedule_id, "started", mark_run=True)
    else:
        reason = str(response.get("error", "not started") or "not started")
        _set_schedule_result(schedule_id, f"skipped: {reason}", mark_run=False)


def _scheduler_worker() -> None:
    """Background scheduler loop that checks for due cron jobs."""
    while not _scheduler_stop.is_set():
        now = time.time()
        due_ids: list[str] = []

        with _schedule_lock:
            changed = False
            for schedule_id, schedule in _schedules.items():
                if not schedule.get("enabled", False):
                    continue

                cron_expr = str(schedule.get("cron", "") or "")
                next_run = schedule.get("next_run_at")
                try:
                    next_ts = float(next_run)
                except (TypeError, ValueError):
                    next_ts = _next_cron_timestamp(cron_expr, now)
                    schedule["next_run_at"] = next_ts
                    schedule["updated_at"] = now
                    changed = True

                if next_ts is None:
                    schedule["enabled"] = False
                    schedule["last_result"] = "error: invalid cron expression"
                    schedule["updated_at"] = now
                    changed = True
                    continue

                if now + 0.2 < next_ts:
                    continue

                due_ids.append(schedule_id)
                schedule["next_run_at"] = _next_cron_timestamp(cron_expr, now + 1)
                schedule["updated_at"] = now
                changed = True

            if changed:
                _save_schedules_state_locked()

        for schedule_id in due_ids:
            _execute_schedule(schedule_id)

        _scheduler_stop.wait(1.0)


def _start_scheduler_worker() -> None:
    """Start the recurring schedule worker once."""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_worker, name="schedule-worker", daemon=True)
    _scheduler_thread.start()


_load_agents_state()
_load_schedules_state()


@app.before_request
def _require_dashboard_auth():
    """Enforce session auth for dashboard API routes when configured."""
    if not _dashboard_auth_enabled():
        return None

    path = request.path or "/"
    if path == "/" or path == "/favicon.ico" or path.startswith("/assets/"):
        return None
    if path == "/api/auth/session":
        return None
    if _dashboard_request_authenticated():
        return None
    if path.startswith("/api/"):
        return jsonify({"error": "authentication required"}), 401
    abort(401)


@app.after_request
def _apply_security_headers(response):
    """Apply conservative browser-facing security headers."""
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path == "/api/auth/session":
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


def _check_agent(url: str, api_key: str = "") -> dict | None:
    """GET /status on an agent, return parsed JSON or None."""
    try:
        return http_get_json(url, "/status", timeout=2.0, api_key=api_key or None)
    except Exception:
        return None


def _refresh_agent(aid: str, info: dict) -> dict:
    """Probe an agent and update its stored status."""
    st = _check_agent(info["url"], info.get("api_key", ""))
    with _agents_lock:
        if st:
            info["status"] = "online"
            info["last_seen"] = time.time()
            info["details"] = st
        else:
            info["status"] = "offline"
            info["details"] = {}
        _agents[aid] = info
    return info


def _discover_agents(timeout: float = 3.0) -> list[dict]:
    """Discover agents via unicast targets, with optional UDP broadcast."""
    found_by_url: dict[str, dict] = {}

    def _record_packet(data: bytes, addr: tuple[str, int]) -> None:
        try:
            info = json.loads(data.decode())
        except Exception:
            return

        url = info.get("base", f"http://{addr[0]}:{DEFAULT_API_PORT}")
        if not isinstance(url, str) or not url:
            return

        found_by_url[url] = {
            "url": url,
            "name": info.get("name", addr[0]),
            "version": info.get("version", ""),
            "ips": info.get("ips", [addr[0]]),
            "interfaces": info.get("interfaces", []),
            "servers": info.get("servers", []),
        }

    def _probe(targets: list[tuple[str, int]], recv_timeout: float) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            for host, port in targets:
                try:
                    sock.sendto(b"IPERF3_DISCOVER", (host, port))
                except OSError:
                    continue

            deadline = time.time() + max(0.1, recv_timeout)
            while time.time() < deadline:
                sock.settimeout(max(0.05, deadline - time.time()))
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    break
                _record_packet(data, addr)
        finally:
            sock.close()

    local_ip = ""
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe_sock.connect(("10.255.255.255", 1))
        local_ip = probe_sock.getsockname()[0]
    except OSError:
        pass
    finally:
        probe_sock.close()

    targets: list[str] = []
    seen: set[str] = set()

    def _add_target(host: str) -> None:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return
        if host == local_ip or host in seen:
            return
        seen.add(host)
        targets.append(host)

    cidr_list = os.environ.get("DASHBOARD_DISCOVERY_CIDRS", "").strip()
    if cidr_list:
        for token in cidr_list.split(","):
            candidate = token.strip()
            if not candidate:
                continue
            if "/" in candidate:
                try:
                    net = ipaddress.ip_network(candidate, strict=False)
                except ValueError:
                    continue
                if net.num_addresses > 1024:
                    continue
                for ip in net.hosts():
                    _add_target(str(ip))
            else:
                _add_target(candidate)

    broadcast_mode = os.environ.get("DASHBOARD_DISCOVERY_BROADCAST", "auto").strip().lower()
    if broadcast_mode in {"1", "true", "yes", "on"}:
        use_broadcast = True
    elif broadcast_mode in {"0", "false", "no", "off"}:
        use_broadcast = False
    else:
        # Auto mode: avoid noisy global broadcasts when explicit targets are configured.
        use_broadcast = not bool(targets)

    if use_broadcast:
        _probe([("<broadcast>", DISCOVER_PORT), ("255.255.255.255", DISCOVER_PORT)], timeout)

    if not found_by_url and not targets and local_ip:
        try:
            local_net = ipaddress.ip_network(f"{local_ip}/24", strict=False)
            for ip in local_net.hosts():
                _add_target(str(ip))
        except ValueError:
            pass

    if targets:
        _probe([(host, DISCOVER_PORT) for host in targets], min(timeout, 2.0))

    return list(found_by_url.values())


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Test execution helpers                                             ║
# ╚══════════════════════════════════════════════════════════════════════╝

# Frontend → backend mode name mapping
_MODE_MAP = {
    "bidirectional": "bidir",
    "upload": "up_only",
    "download": "down_only",
}


def _resolve_agent_url(agent_id: str) -> str:
    """Look up agent URL from ID. Returns ID unchanged if not found."""
    with _agents_lock:
        info = _agents.get(agent_id)
    return info["url"] if info else agent_id


def _normalize_config(raw: dict) -> dict:
    """Transform frontend config shape into the format run_test expects."""
    server_id = raw.get("server_agent", "")
    server_url = _resolve_agent_url(server_id) if server_id else ""
    with _agents_lock:
        agent_snapshot = {aid: dict(info) for aid, info in _agents.items()}

    # Derive server IP from its URL for default client target
    server_ip = ""
    if server_url:
        try:
            server_ip = urlparse(server_url).hostname or ""
        except Exception:
            pass

    # Resolve server display name from agents dict
    server_info = agent_snapshot.get(server_id, {})
    server_name = server_info.get("name", server_id)
    server_api_key = str(server_info.get("api_key", "") or "")

    mode = _MODE_MAP.get(raw.get("mode", ""), raw.get("mode", ""))

    server_bind = str(raw.get("server_bind", "") or "").strip()

    clients = []
    for c in raw.get("clients", []):
        agent_id = c.get("agent", "")
        agent_info = agent_snapshot.get(agent_id, {})
        agent_api_key = str(agent_info.get("api_key", "") or "")
        target = c.get("server_target") or c.get("target", "") or server_bind or server_ip
        client_entry: dict = {
            "agent": _resolve_agent_url(agent_id) if agent_id else "",
            "name": c.get("name") or agent_id,
            "target": target,
            "api_key": c.get("api_key", "") or agent_api_key,
        }
        if c.get("bind"):
            client_entry["bind"] = c["bind"]
        clients.append(client_entry)

    cfg: dict = {
        "server": {
            "agent": server_url,
            "name": server_name,
            "bind": server_bind,
            "api_key": raw.get("api_key", "") or server_api_key,
        },
        "clients": clients,
        "duration_sec": raw.get("duration_sec", 10),
        "base_port": raw.get("base_port", 5201),
        "poll_interval_sec": raw.get("poll_interval_sec", 1),
        "mode": mode,
        "api_key": raw.get("api_key", ""),
    }

    # Optional parameters
    if raw.get("protocol") == "udp":
        cfg["proto"] = "udp"
    if raw.get("parallel", 1) > 1:
        cfg["parallel"] = raw["parallel"]
    if raw.get("omit_sec", 0):
        cfg["omit"] = raw["omit_sec"]
    if raw.get("bitrate"):
        cfg["bitrate"] = raw["bitrate"]
    if raw.get("tcp_window"):
        cfg["tcp_window"] = raw["tcp_window"]

    return cfg


def _on_log(msg: str):
    """Forward test-runner log messages to Socket.IO clients."""
    socketio.emit("test_log", {"message": msg, "ts": time.time()})


def _metrics_poller(config: dict, stop_ev: threading.Event):
    """Parallel poller: fetches agent metrics and emits via Socket.IO."""
    clients = config.get("clients", [])
    global_api_key = str(config.get("api_key", "")).strip()
    poll_interval = max(0.5, float(config.get("poll_interval_sec", 1.0)))
    mode = (config.get("mode") or "").lower()
    mode_hint = "down_only" if mode == "down_only" else ("up_only" if mode == "up_only" else None)

    # Let iperf3 processes start producing output before polling
    stop_ev.wait(2)
    was_active = False

    while not stop_ev.is_set():
        metrics: dict = {}
        total_up = total_dn = 0.0
        for c in clients:
            name = c.get("name", c.get("agent", "?"))
            try:
                api_key = str(c.get("api_key") or global_api_key).strip()
                up, dn, _ub, _db, jitter, loss = poll_metrics(
                    c["agent"], mode_hint=mode_hint, api_key=api_key or None
                )
                metrics[name] = {
                    "up": round(up, 3) if up else 0,
                    "dn": round(dn, 3) if dn else 0,
                    "jitter": round(jitter, 3) if jitter is not None else None,
                    "loss": round(loss, 3) if loss is not None else None,
                }
                total_up += up or 0
                total_dn += dn or 0
            except Exception:
                metrics[name] = {"up": 0, "dn": 0, "jitter": None, "loss": None}

        # Only emit meaningful data; stop once data drops to zero after being active
        if total_up > 0 or total_dn > 0:
            was_active = True
            socketio.emit("metrics", {
                "timestamp": time.time(),
                "clients": metrics,
                "total_up": round(total_up, 3),
                "total_dn": round(total_dn, 3),
            })
        elif was_active:
            break

        stop_ev.wait(poll_interval)


def _run_test_thread(config: dict):
    """Background thread that runs a test and emits Socket.IO lifecycle events."""
    global _test_state, _current_csv, _poller_thread

    # Normalize frontend config into run_test format
    cfg = _normalize_config(config)

    csv_name = time.strftime("test_%Y%m%d_%H%M%S") + ".csv"
    csv_path = str(DATA_DIR / csv_name)
    _current_csv = csv_path

    socketio.emit("test_started", {
        "ts": time.time(),
        "config": _public_test_config(config),
        "csv": csv_name,
    })

    # Start parallel metrics poller
    poller_stop = threading.Event()
    _poller_thread = threading.Thread(
        target=_metrics_poller, args=(cfg, poller_stop), daemon=True
    )
    _poller_thread.start()

    error = None
    try:
        run_test(
            cfg=cfg,
            csv_path=csv_path,
            on_log=_on_log,
            stop_event=_stop_event,
        )
    except Exception as exc:
        error = str(exc)
        socketio.emit("test_error", {"message": error, "ts": time.time()})

    # Stop poller
    poller_stop.set()
    if _poller_thread and _poller_thread.is_alive():
        _poller_thread.join(timeout=5)

    with _test_lock:
        _test_state["status"] = "idle"
        _test_state["last_csv"] = csv_name
        _test_state["finished_at"] = time.time()
        _test_state.pop("trigger", None)
        _test_state.pop("schedule_id", None)

    socketio.emit("test_completed", {
        "ts": time.time(),
        "csv": csv_name,
        "error": error,
    })

    # Enforce report retention limit: keep newest 1000 CSV files
    _prune_reports(limit=1000)


def _prune_reports(limit: int = 1000):
    """Delete oldest CSV reports when count exceeds limit."""
    try:
        csvs = sorted(
            [f for f in DATA_DIR.iterdir() if f.is_file() and f.suffix == ".csv"],
            key=lambda f: f.stat().st_mtime,
        )
        for old in csvs[:-limit]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        pass


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Pages                                                     ║
# ╚══════════════════════════════════════════════════════════════════════╝

# Serve React frontend (built) if available, fall back to legacy template
_FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


@app.route("/")
def index():
    if (_FRONTEND_DIST / "index.html").is_file():
        return send_from_directory(str(_FRONTEND_DIST), "index.html")
    return render_template("dashboard.html", version=DASHBOARD_VERSION)


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve Vite-built frontend assets."""
    return send_from_directory(str(_FRONTEND_DIST / "assets"), filename)


@app.route("/favicon.ico")
def favicon():
    """Serve a favicon when present, or return no content without logging a 404."""
    icon_path = Path(__file__).resolve().parent / "static" / "favicon.ico"
    if icon_path.is_file():
        return send_from_directory(str(icon_path.parent), icon_path.name)
    return ("", 204)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Authentication                                            ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/auth/session", methods=["GET"])
def auth_session_status():
    return jsonify(_auth_state())


@app.route("/api/auth/session", methods=["POST"])
def create_auth_session():
    if not _dashboard_auth_enabled():
        return jsonify({"error": "dashboard auth is not enabled"}), 400

    client_ip = _client_ip()
    if len(_recent_login_failures(client_ip)) >= _LOGIN_MAX_ATTEMPTS:
        return jsonify({"error": "too many login attempts; try again later"}), 429

    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "") or "").strip()
    password = str(body.get("password", "") or "")

    if (
        not username or not password
        or not hmac.compare_digest(username, _AUTH_USERNAME)
        or not _verify_dashboard_password(password)
    ):
        _record_login_failure(client_ip)
        return jsonify({"error": "invalid credentials"}), 401

    _clear_login_failures(client_ip)
    session.clear()
    session.permanent = True
    session["auth_ok"] = True
    session["auth_user"] = _AUTH_USERNAME
    return jsonify(_auth_state())


@app.route("/api/auth/session", methods=["DELETE"])
def delete_auth_session():
    session.clear()
    return jsonify(_auth_state())


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Agents                                                    ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/agents", methods=["GET"])
def list_agents():
    with _agents_lock:
        agents = dict(_agents)
    # Optionally refresh on request
    if request.args.get("refresh") == "1":
        for aid, info in agents.items():
            _refresh_agent(aid, info)
        with _agents_lock:
            agents = dict(_agents)
    return jsonify([_public_agent(info) for info in agents.values()])


@app.route("/api/agents", methods=["POST"])
def add_agent():
    data = request.get_json(force=True)
    try:
        url = _normalize_agent_url(data.get("url", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    aid = _agent_id(url)
    with _agents_lock:
        existing = dict(_agents.get(aid, {}))
    name = data.get("name", "").strip() or existing.get("name") or url
    api_key = str(data.get("api_key", "") or existing.get("api_key", "")).strip()
    info = {"id": aid, "url": url, "name": name, "status": "unknown",
            "last_seen": existing.get("last_seen"), "api_key": api_key, "details": existing.get("details", {})}
    _refresh_agent(aid, info)
    _save_agents_state()
    return jsonify(_public_agent(info)), 201


@app.route("/api/agents/<agent_id>", methods=["PATCH"])
def update_agent(agent_id):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400

    with _agents_lock:
        existing = dict(_agents.get(agent_id, {}))
    if not existing:
        return jsonify({"error": "not found"}), 404

    existing_name = str(existing.get("name", "") or "").strip()
    existing_key = str(existing.get("api_key", "") or "").strip()
    name = str(data.get("name", existing_name) or "").strip() or existing_name or existing.get("url", "")
    api_key = existing_key
    if "api_key" in data:
        api_key = str(data.get("api_key", "") or "").strip()

    info = {
        "id": existing.get("id", agent_id),
        "url": existing.get("url", ""),
        "name": name,
        "status": existing.get("status", "unknown"),
        "last_seen": existing.get("last_seen"),
        "api_key": api_key,
        "details": existing.get("details", {}),
    }
    _refresh_agent(agent_id, info)
    _save_agents_state()
    return jsonify(_public_agent(info))


@app.route("/api/agents/<agent_id>", methods=["DELETE"])
def remove_agent(agent_id):
    with _agents_lock:
        removed = _agents.pop(agent_id, None)
    if removed:
        _save_agents_state()
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


@app.route("/api/agents/discover", methods=["POST"])
def discover_agents():
    body = request.get_json(silent=True) or {}
    timeout = float(body.get("timeout", 3)) if isinstance(body, dict) else 3
    found = _discover_agents(timeout=timeout)
    added = []
    for f in found:
        try:
            url = _normalize_agent_url(f["url"])
        except ValueError:
            continue
        aid = _agent_id(url)
        with _agents_lock:
            existing = dict(_agents.get(aid, {}))
        info = {"id": aid, "url": url, "name": existing.get("name") or f.get("name", url),
                "status": "online", "last_seen": time.time(),
                "api_key": str(existing.get("api_key", "") or ""),
                "details": {"version": f.get("version"), "ips": f.get("ips"), "interfaces": f.get("interfaces")}}
        with _agents_lock:
            _agents[aid] = info
        added.append(_public_agent(info))
    if added:
        _save_agents_state()
    return jsonify({"discovered": len(added), "agents": added})


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Profiles                                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    profiles = []
    for p in sorted(PROFILES_DIR.glob("*.json")):
        profiles.append({"name": p.stem, "file": p.name})
    return jsonify(profiles)


@app.route("/api/profiles", methods=["POST"])
def save_profile():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    config = data.get("config")
    if not name or config is None:
        return jsonify({"error": "name and config are required"}), 400
    if not isinstance(config, dict):
        return jsonify({"error": "config must be an object"}), 400
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    if not safe_name:
        return jsonify({"error": "invalid profile name"}), 400
    path = PROFILES_DIR / f"{safe_name}.json"
    safe_config = _redact_profile_config(config)
    path.write_text(json.dumps(safe_config, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "name": safe_name})


@app.route("/api/profiles/<name>", methods=["GET"])
def load_profile(name):
    safe = Path(name).name
    path = PROFILES_DIR / f"{safe}.json"
    if not path.resolve().parent == PROFILES_DIR.resolve():
        return jsonify({"error": "invalid name"}), 400
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    config = json.loads(path.read_text(encoding="utf-8"))
    return jsonify({"name": safe, "config": config})


@app.route("/api/profiles/<name>", methods=["DELETE"])
def delete_profile(name):
    safe = Path(name).name
    path = PROFILES_DIR / f"{safe}.json"
    if not path.resolve().parent == PROFILES_DIR.resolve():
        return jsonify({"error": "invalid name"}), 400
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    path.unlink()
    return jsonify({"ok": True})


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Schedules                                                 ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/schedules", methods=["GET"])
def list_schedules():
    with _schedule_lock:
        schedules = [_public_schedule(dict(schedule)) for schedule in _schedules.values()]
    schedules.sort(key=lambda schedule: str(schedule.get("name", "")).lower())
    return jsonify(schedules)


@app.route("/api/schedules", methods=["POST"])
def create_schedule():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be an object"}), 400

    name = str(data.get("name", "") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    cron_expr = _normalize_cron_expression(str(data.get("cron", "") or ""))
    cron_err = _validate_cron_expression(cron_expr)
    if cron_err:
        return jsonify({"error": cron_err}), 400

    source = str(data.get("source", "profile") or "profile").strip().lower()
    if source not in {"profile", "manual"}:
        return jsonify({"error": "source must be profile or manual"}), 400

    now = time.time()
    enabled = bool(data.get("enabled", True))
    schedule: dict = {
        "id": "",
        "name": name,
        "cron": cron_expr,
        "enabled": enabled,
        "source": source,
        "next_run_at": _next_cron_timestamp(cron_expr, now) if enabled else None,
        "last_run_at": None,
        "last_result": "",
        "created_at": now,
        "updated_at": now,
    }

    if source == "profile":
        profile_name = Path(str(data.get("profile_name", "") or "")).name
        if not profile_name:
            return jsonify({"error": "profile_name is required for profile schedules"}), 400
        path = PROFILES_DIR / f"{profile_name}.json"
        if path.resolve().parent != PROFILES_DIR.resolve():
            return jsonify({"error": "invalid profile_name"}), 400
        if not path.is_file():
            return jsonify({"error": "profile not found"}), 404
        schedule["profile_name"] = profile_name
    else:
        config = data.get("config")
        err = _validate_test_start_config(config)
        if err:
            return jsonify({"error": f"manual schedule config invalid: {err}"}), 400
        schedule["config"] = config

    with _schedule_lock:
        schedule_id = secrets.token_hex(8)
        while schedule_id in _schedules:
            schedule_id = secrets.token_hex(8)
        schedule["id"] = schedule_id
        _schedules[schedule_id] = schedule
        _save_schedules_state_locked()

    return jsonify(_public_schedule(dict(schedule))), 201


@app.route("/api/schedules/<schedule_id>", methods=["PATCH"])
def update_schedule(schedule_id):
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be an object"}), 400

    with _schedule_lock:
        existing = _schedules.get(schedule_id)
        if not existing:
            return jsonify({"error": "not found"}), 404
        updated = dict(existing)

    if "name" in data:
        name = str(data.get("name", "") or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        updated["name"] = name

    if "cron" in data:
        cron_expr = _normalize_cron_expression(str(data.get("cron", "") or ""))
        cron_err = _validate_cron_expression(cron_expr)
        if cron_err:
            return jsonify({"error": cron_err}), 400
        updated["cron"] = cron_expr

    if "enabled" in data:
        updated["enabled"] = bool(data.get("enabled"))

    if "source" in data:
        source = str(data.get("source", "") or "").strip().lower()
        if source not in {"profile", "manual"}:
            return jsonify({"error": "source must be profile or manual"}), 400
        updated["source"] = source

    source = str(updated.get("source", "profile") or "profile")
    if source == "profile":
        profile_name = data.get("profile_name") if "profile_name" in data else updated.get("profile_name", "")
        safe_name = Path(str(profile_name or "")).name
        if not safe_name:
            return jsonify({"error": "profile_name is required for profile schedules"}), 400
        path = PROFILES_DIR / f"{safe_name}.json"
        if path.resolve().parent != PROFILES_DIR.resolve():
            return jsonify({"error": "invalid profile_name"}), 400
        if not path.is_file():
            return jsonify({"error": "profile not found"}), 404
        updated["profile_name"] = safe_name
        updated.pop("config", None)
    else:
        config = data.get("config") if "config" in data else updated.get("config")
        err = _validate_test_start_config(config)
        if err:
            return jsonify({"error": f"manual schedule config invalid: {err}"}), 400
        updated["config"] = config
        updated.pop("profile_name", None)

    now = time.time()
    if "cron" in data or "enabled" in data or "source" in data:
        updated["next_run_at"] = _next_cron_timestamp(updated["cron"], now) if updated.get("enabled") else None
    updated["updated_at"] = now

    with _schedule_lock:
        _schedules[schedule_id] = updated
        _save_schedules_state_locked()

    return jsonify(_public_schedule(dict(updated)))


@app.route("/api/schedules/<schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id):
    with _schedule_lock:
        schedule = _schedules.pop(schedule_id, None)
        if not schedule:
            return jsonify({"error": "not found"}), 404
        _save_schedules_state_locked()
    return jsonify({"ok": True, "id": schedule_id})


@app.route("/api/schedules/<schedule_id>/run", methods=["POST"])
def run_schedule_now(schedule_id):
    with _schedule_lock:
        schedule = _schedules.get(schedule_id)
        if not schedule:
            return jsonify({"error": "not found"}), 404
        schedule_copy = dict(schedule)

    config, err = _resolve_schedule_config(schedule_copy)
    if err:
        _set_schedule_result(schedule_id, f"error: {err}", mark_run=False)
        return jsonify({"error": err}), 400

    response, status = _start_test_with_config(config, trigger="schedule", schedule_id=schedule_id)
    if status == 200:
        _set_schedule_result(schedule_id, "started", mark_run=True)
    else:
        reason = str(response.get("error", "not started") or "not started")
        _set_schedule_result(schedule_id, f"skipped: {reason}", mark_run=False)
    return jsonify(response), status


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Test Control                                              ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/test/start", methods=["POST"])
def start_test():
    config = request.get_json(force=True)
    response, status = _start_test_with_config(config, trigger="manual")
    return jsonify(response), status


@app.route("/api/test/stop", methods=["POST"])
def stop_test():
    with _test_lock:
        if _test_state["status"] != "running":
            return jsonify({"error": "no test running"}), 409
        _test_state["status"] = "stopping"
    _stop_event.set()
    return jsonify({"ok": True, "status": "stopping"})


@app.route("/api/test/status", methods=["GET"])
def test_status():
    with _test_lock:
        return jsonify(_public_test_state(dict(_test_state)))


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Reports / Files                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝

def _parse_csv_meta(path: Path) -> dict:
    """Extract summary metadata from a CSV report file."""
    meta: dict = {"protocol": None, "clients": [], "server": None,
                  "duration_s": None, "rows": 0, "peak_up": None, "peak_dn": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().rstrip("\n")
            # Check for schema comment row: # schema,wide_v1,...,proto,tcp,server,name
            if first_line.startswith("# schema") or first_line.startswith("#"):
                parts = first_line.split(",")
                # Parse key-value pairs from schema comment
                for i, p in enumerate(parts):
                    tok = p.strip().lower()
                    if tok == "proto" and i + 1 < len(parts):
                        meta["protocol"] = parts[i + 1].strip().upper()
                    elif tok == "server" and i + 1 < len(parts):
                        meta["server"] = parts[i + 1].strip() or None
                header_line = f.readline().rstrip("\n")
            else:
                header_line = first_line

            # Parse columns to extract client IDs
            cols = [c.strip() for c in header_line.split(",")]
            # Columns like "agentname_up", "agentname_dn" → extract agent names
            clients: list[str] = []
            seen: set = set()
            skip_pfx = {"ts", "wall", "total", "on", "sum"}
            for col in cols:
                for sfx in ("_up", "_dn", "_jit_ms", "_loss_pct", "_sent_mb", "_recv_mb"):
                    if col.endswith(sfx):
                        name = col[: -len(sfx)]
                        if name and name not in skip_pfx and name not in seen:
                            clients.append(name)
                            seen.add(name)
                        break
            meta["clients"] = clients

            # Fallback protocol detection from column names when schema row is absent
            if not meta["protocol"]:
                has_udp_cols = any(c.endswith("_jit_ms") or c.endswith("_loss_pct") for c in cols)
                meta["protocol"] = "UDP" if has_udp_cols else "TCP"

            # Read data rows
            data_rows: list = []
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                row_vals = line.split(",")
                data_rows.append(dict(zip(cols, row_vals)))

            meta["rows"] = len(data_rows)

            if data_rows:
                # Duration from first to last wall/ts
                first_ts = data_rows[0].get("ts", "")
                last_ts = data_rows[-1].get("ts", "")
                try:
                    meta["duration_s"] = int(last_ts) - int(first_ts) + 1
                except (ValueError, TypeError):
                    pass

                # Peak up/dn from total columns
                up_col = "total_up" if "total_up" in cols else None
                dn_col = "total_dn" if "total_dn" in cols else None
                if up_col:
                    vals = [float(r[up_col]) for r in data_rows if r.get(up_col, "") not in ("", None)]
                    meta["peak_up"] = round(max(vals), 2) if vals else None
                if dn_col:
                    vals = [float(r[dn_col]) for r in data_rows if r.get(dn_col, "") not in ("", None)]
                    meta["peak_dn"] = round(max(vals), 2) if vals else None
    except Exception:
        pass
    return meta


@app.route("/api/reports", methods=["GET"])
def list_reports():
    files = []
    for f in sorted(DATA_DIR.iterdir(), reverse=True):  # newest first
        if f.is_file() and f.suffix in (".csv", ".html", ".zip"):
            stat = f.stat()
            entry: dict = {
                "name": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
            if f.suffix == ".csv":
                entry.update(_parse_csv_meta(f))
                # Resolve agent-ID hashes to friendly display names
                with _agents_lock:
                    entry["clients"] = [
                        _agents[cid]["name"] if cid in _agents else cid
                        for cid in entry.get("clients", [])
                    ]
            files.append(entry)
    return jsonify(files)


@app.route("/api/reports", methods=["DELETE"])
def delete_reports_bulk():
    """Delete multiple report files. Body: {"files": ["name1.csv", ...]}"""
    body = request.get_json(silent=True) or {}
    filenames = body.get("files", [])
    if not isinstance(filenames, list):
        abort(400)
    deleted, errors = [], []
    for name in filenames:
        safe = Path(name).name
        target = DATA_DIR / safe
        try:
            target.unlink(missing_ok=True)
            deleted.append(safe)
        except Exception as e:
            errors.append({"name": safe, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})


@app.route("/api/reports/<path:filename>/data", methods=["GET"])
def report_data(filename):
    """Return CSV file contents as parsed JSON for inline viewing."""
    safe = Path(filename).name
    target = DATA_DIR / safe
    if not target.is_file():
        abort(404)
    rows = []
    columns = []
    with open(target, "r", encoding="utf-8") as f:
        first_line = f.readline()
        # Skip schema comment row if present
        if first_line.startswith("#"):
            header_line = f.readline()
        else:
            header_line = first_line
        reader = csv.DictReader(f, fieldnames=[c.strip() for c in header_line.rstrip("\n").split(",")])
        columns = reader.fieldnames or []
        for row in reader:
            rows.append(dict(row))
    return jsonify({"filename": safe, "columns": columns, "rows": rows})


@app.route("/api/reports/<path:filename>", methods=["DELETE"])
def delete_report(filename):
    """Delete a single report file."""
    safe = Path(filename).name
    target = DATA_DIR / safe
    if not target.is_file():
        abort(404)
    target.unlink()
    return jsonify({"deleted": safe})


@app.route("/api/reports/<path:filename>", methods=["GET"])
def download_report(filename):
    # Prevent path traversal
    safe = Path(filename).name
    target = DATA_DIR / safe
    if not target.is_file():
        abort(404)
    return send_from_directory(str(DATA_DIR), safe, as_attachment=True)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Metadata                                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/meta", methods=["GET"])
def meta():
    return jsonify({
        "version": DASHBOARD_VERSION,
        "test_modes": TEST_MODES,
        "protocols": PROTOCOLS,
        "default_base_port": DEFAULT_BASE_PORT,
    })


_start_scheduler_worker()


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Socket.IO events                                                   ║
# ╚══════════════════════════════════════════════════════════════════════╝

@socketio.on("connect")
def handle_connect():
    if not _dashboard_request_authenticated():
        return False
    with _test_lock:
        emit("status", {"test": _public_test_state(dict(_test_state))})


@socketio.on("ping_agents")
def handle_ping_agents():
    """Client requests a live refresh of all agents."""
    with _agents_lock:
        agents = dict(_agents)
    for aid, info in agents.items():
        _refresh_agent(aid, info)
    with _agents_lock:
        emit("agents_update", [_public_agent(info) for info in _agents.values()])
