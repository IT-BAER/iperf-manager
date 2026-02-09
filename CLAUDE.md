# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**iperf_manager** is a Python-based distributed iperf3 network performance testing system with three components:

1. **Agent** (`agent_gui_v6_0_2.py`) - REST API service that manages iperf3 processes on remote hosts
2. **Dashboard** (`live_dashboard_v6_0_2_fixA_clean3(good_report수정필요.)my.pyw`) - Tkinter GUI for real-time test orchestration and visualization
3. **Controller** (`controller_v5_18.py`) - CLI tool for headless/automated test execution

## Architecture

```
Dashboard/Controller (orchestrator)
    ↓ REST API (HTTP POST/GET)
Agent A (server-side)              Agent B (client-side)
    ↓ spawns                           ↓ spawns
iperf3 -s (servers)    ←traffic→   iperf3 -c (clients)
    ↑                                  ↑
    └────── /metrics polling ──────────┘
```

### Communication Flow
- Dashboard/Controller → Agent: `/server/start`, `/client/start`, `/server/stop`, `/client/stop`
- Dashboard ← Agent: `/metrics` (polled for real-time throughput), `/status`
- Agent Discovery: UDP broadcast to 255.255.255.255:9999

### Key REST Endpoints (Agent)
- `POST /server/start` - `{"ports": [...], "bind": "ip", "bind_map": {}}`
- `POST /client/start` - `{"target": "ip", "port": N, "duration": N, "proto": "tcp|udp", "parallel": N, "bitrate": "100M", "bidir": bool, "reverse": bool, ...}`
- `POST /server/stop`, `POST /client/stop`
- `GET /metrics` - Returns `{"metrics": [{"key": "...", "task": {...}, "json": {"interval_up_mbps": N, "interval_dn_mbps": N, "jitter_ms": N, "loss_pct": N}}]}`
- `GET /status` - Returns server/client status, log directory, advertise IP

## Running the Application

### Agent (run on each test host)
```bash
python agent_gui_v6_0_2.py
```
- Starts REST API on port 9001 (configurable via UI)
- UDP discovery responder on port 9999
- Requires `iperf3` binary in PATH, same directory, or PyInstaller bundle
- Config persisted to `%LOCALAPPDATA%\iperf3-agent\config.json`
- Logs written to `%LOCALAPPDATA%\iperf3-agent\logs\` (or fallback locations)

### Dashboard (interactive GUI)
```bash
python live_dashboard_v6_0_2_fixA_clean3(good_report수정필요.)my.pyw
# or: pythonw <filename>.pyw (no console window)
```
- Auto-loads last profile from `data/last_profile.json`
- Outputs: CSV metrics, HTML reports, PNG graphs

### Controller (headless automation)
```bash
python controller_v5_18.py --config test_config.json --out results.csv
```

## Test Configuration JSON Schema

```json
{
  "server": {
    "agent": "http://server-host:9001",
    "bind": "optional_bind_ip",
    "bind_map": "optional"
  },
  "clients": [
    {
      "name": "client1",
      "agent": "http://client-host:9001",
      "target": "server_ip",
      "proto": "tcp",
      "parallel": 1,
      "bitrate": "100M",
      "reverse": false,
      "bidir": false
    }
  ],
  "duration_sec": 30,
  "base_port": 5211,
  "mode": "bidir|up_only|down_only",
  "keep_servers_open": true
}
```

## Dependencies

Required Python packages (no requirements.txt exists):
- `matplotlib` (graphing, TkAgg backend)
- `tkinter` (included with Python on Windows)
- `pandas` (optional, for long-format CSV export)

External:
- `iperf3` binary must be available on agent hosts

## Key Implementation Details

### Agent Architecture
- `AgentService` class: Manages iperf3 server/client subprocesses with thread-safe state
- HTTP server: Built on `http.server.HTTPServer` (no Flask/FastAPI)
- Output parsing: Regex-based extraction of throughput from iperf3 stdout (`INTERVAL_RE`, `UDP_INTERVAL_RE`, `TCP_BR_RE`)
- Discovery: UDP socket listener responds to `IPERF3_DISCOVER` broadcasts with JSON metadata

### UDP Test Constraints
Both Agent and Dashboard enforce: UDP tests cannot use `--bidir` or `-P > 1` (parallel > 1).

### Metrics Polling
The `Poller` thread polls `/metrics` endpoints at configurable intervals (default 1s). Metrics extracted:
- `interval_up_mbps`, `interval_dn_mbps` (TCP throughput)
- `jitter`, `loss`/`lost` (UDP-specific)

### Report Generation
`generate_report()` creates HTML with embedded PNGs:
- `*_total.png` - Total up/down throughput
- `*_agents.png` - Per-agent throughput
- `*_udp_jitter.png`, `*_udp_loss.png` - UDP metrics (when applicable)

### Data Files
- `data/last_profile.json` - Auto-saved test configuration
- `data/<timestamp>_ui.csv` - Wide-format metrics
- `data/<timestamp>_live.log` - Session log
- `%LOCALAPPDATA%\iperf3-agent\config.json` - Agent persistent config

## Code Conventions

- Korean comments appear throughout (bilingual codebase)
- matplotlib font fallback: Malgun Gothic → NanumGothic → Arial
- Threading: Queue-based communication between poller and UI; daemon threads for subprocess output readers
- HTTP Client: `urllib.request` (no requests library)
- HTTP Server: `http.server.HTTPServer` with custom `BaseHTTPRequestHandler`
- Path handling: `pathlib.Path`
- Windows compatibility: `CREATE_NO_WINDOW` flag, hidden `STARTUPINFO` for subprocess spawning
- Parameter normalization: Agent accepts multiple key aliases (e.g., `duration`/`time`/`seconds`, `parallel`/`P`/`pairs`)
