# -*- coding: utf-8 -*-
"""web/app.py – Flask + Socket.IO backend for the iperf-manager web dashboard.

Reuses *only* the existing core/ modules (zero modifications).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import socket
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, abort

try:
    from flask_socketio import SocketIO, emit
except ImportError:
    raise SystemExit("flask-socketio is required. Install with: pip install -r requirements-web.txt")

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
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# ── Flask / Socket.IO setup ─────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static"),
)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "iperf-manager-dev-key")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── In-memory state ─────────────────────────────────────────────────────
_agents: dict[str, dict] = {}          # {agent_id: {url, name, status, last_seen}}
_agents_lock = threading.Lock()

_test_state: dict = {"status": "idle"}  # idle | running | stopping
_test_lock = threading.Lock()
_stop_event = threading.Event()
_test_thread: threading.Thread | None = None
_poller_thread: threading.Thread | None = None
_current_csv: str | None = None


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                            ║
# ╚══════════════════════════════════════════════════════════════════════╝

def _agent_id(url: str) -> str:
    """Deterministic short ID from agent URL."""
    return hashlib.md5(url.encode()).hexdigest()[:10]


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
    """Send UDP broadcast and collect agent responses."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    found: list[dict] = []
    try:
        sock.sendto(b"IPERF3_DISCOVER", ("<broadcast>", DISCOVER_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                info = json.loads(data.decode())
                url = info.get("base", f"http://{addr[0]}:{DEFAULT_API_PORT}")
                found.append({
                    "url": url,
                    "name": info.get("name", addr[0]),
                    "version": info.get("version", ""),
                    "ips": info.get("ips", [addr[0]]),
                    "servers": info.get("servers", []),
                })
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        sock.close()
    return found


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Test execution helpers                                             ║
# ╚══════════════════════════════════════════════════════════════════════╝

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

        socketio.emit("metrics", {
            "timestamp": time.time(),
            "clients": metrics,
            "total_up": round(total_up, 3),
            "total_dn": round(total_dn, 3),
        })
        stop_ev.wait(poll_interval)


def _run_test_thread(config: dict):
    """Background thread that runs a test and emits Socket.IO lifecycle events."""
    global _test_state, _current_csv, _poller_thread

    csv_name = time.strftime("test_%Y%m%d_%H%M%S") + ".csv"
    csv_path = str(DATA_DIR / csv_name)
    _current_csv = csv_path

    socketio.emit("test_started", {
        "ts": time.time(),
        "config": config,
        "csv": csv_name,
    })

    # Start parallel metrics poller
    poller_stop = threading.Event()
    _poller_thread = threading.Thread(
        target=_metrics_poller, args=(config, poller_stop), daemon=True
    )
    _poller_thread.start()

    error = None
    try:
        run_test(
            cfg=config,
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

    socketio.emit("test_completed", {
        "ts": time.time(),
        "csv": csv_name,
        "error": error,
    })


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
    return jsonify(list(agents.values()))


@app.route("/api/agents", methods=["POST"])
def add_agent():
    data = request.get_json(force=True)
    url = data.get("url", "").strip().rstrip("/")
    if not url:
        return jsonify({"error": "url is required"}), 400
    name = data.get("name", "").strip() or url
    api_key = data.get("api_key", "")
    aid = _agent_id(url)
    info = {"id": aid, "url": url, "name": name, "status": "unknown",
            "last_seen": None, "api_key": api_key, "details": {}}
    _refresh_agent(aid, info)
    return jsonify(info), 201


@app.route("/api/agents/<agent_id>", methods=["DELETE"])
def remove_agent(agent_id):
    with _agents_lock:
        removed = _agents.pop(agent_id, None)
    if removed:
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


@app.route("/api/agents/discover", methods=["POST"])
def discover_agents():
    timeout = float(request.get_json(silent=True) or {}).get("timeout", 3) if request.is_json else 3
    found = _discover_agents(timeout=timeout)
    added = []
    for f in found:
        aid = _agent_id(f["url"])
        info = {"id": aid, "url": f["url"], "name": f.get("name", f["url"]),
                "status": "online", "last_seen": time.time(),
                "api_key": "", "details": {"version": f.get("version"), "ips": f.get("ips")}}
        with _agents_lock:
            _agents[aid] = info
        added.append(info)
    return jsonify({"discovered": len(found), "agents": added})


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
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    if not safe_name:
        return jsonify({"error": "invalid profile name"}), 400
    path = PROFILES_DIR / f"{safe_name}.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "name": safe_name})


@app.route("/api/profiles/<name>", methods=["GET"])
def load_profile(name):
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    config = json.loads(path.read_text(encoding="utf-8"))
    return jsonify({"name": name, "config": config})


@app.route("/api/profiles/<name>", methods=["DELETE"])
def delete_profile(name):
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    path.unlink()
    return jsonify({"ok": True})


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Test Control                                              ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/test/start", methods=["POST"])
def start_test():
    global _test_thread
    with _test_lock:
        if _test_state["status"] == "running":
            return jsonify({"error": "test already running"}), 409

    config = request.get_json(force=True)
    if not config:
        return jsonify({"error": "config required"}), 400

    _stop_event.clear()
    with _test_lock:
        _test_state["status"] = "running"
        _test_state["started_at"] = time.time()
        _test_state["config"] = config

    _test_thread = threading.Thread(target=_run_test_thread, args=(config,), daemon=True)
    _test_thread.start()
    return jsonify({"ok": True, "status": "running"})


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
        return jsonify(dict(_test_state))


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Routes – Reports / Files                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝

@app.route("/api/reports", methods=["GET"])
def list_reports():
    files = []
    for f in sorted(DATA_DIR.iterdir()):
        if f.is_file() and f.suffix in (".csv", ".html", ".zip"):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
    return jsonify(files)


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
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            rows.append(dict(row))
    return jsonify({"filename": safe, "columns": columns, "rows": rows})


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


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Socket.IO events                                                   ║
# ╚══════════════════════════════════════════════════════════════════════╝

@socketio.on("connect")
def handle_connect():
    with _test_lock:
        emit("status", {"test": dict(_test_state)})


@socketio.on("ping_agents")
def handle_ping_agents():
    """Client requests a live refresh of all agents."""
    with _agents_lock:
        agents = dict(_agents)
    for aid, info in agents.items():
        _refresh_agent(aid, info)
    with _agents_lock:
        emit("agents_update", list(_agents.values()))
