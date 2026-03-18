# iperf-manager

A distributed **iperf3** network performance testing platform with a **web dashboard** and **headless agents**. Deploy lightweight agents on test hosts and orchestrate multi-client throughput tests from any browser.

## Features

- **Distributed Architecture** — Deploy agents on multiple hosts; control everything from one web UI
- **Real-Time Monitoring** — Live throughput charts (total, per-agent, UDP jitter/loss) via Socket.IO
- **Multi-Client Testing** — Run simultaneous iperf3 sessions across multiple client/server pairs
- **Test Modes** — Bidirectional, upload-only, download-only, dual, two-phase
- **TCP & UDP** — Full support for both protocols with per-client configuration
- **Auto-Discovery** — Find agents on the local network via UDP broadcast
- **Profile Management** — Save, load, and delete test configurations
- **HTML Reports** — Generate reports with embedded throughput/jitter/loss charts
- **CSV Export** — Wide-format metrics export for further analysis
- **Headless Agents** — Zero-dependency agents for Linux/Windows server deployment

## Architecture

```
Web Dashboard (Flask + React)
    |  REST API (HTTP)
    +---> Agent A (server-side)          Agent B (client-side)
              | spawns                       | spawns
          iperf3 -s  <--- traffic --->   iperf3 -c
              |                              |
              +------ /metrics polling ------+
```

| Component | Description | Entry Point |
|-----------|-------------|-------------|
| **Agent** | Headless REST API service managing iperf3 processes | `main_agent.py` |
| **Web Dashboard** | Flask + React SPA for test orchestration and live visualization | `main_web.py` |

## Quick Start

### Prerequisites

- Python 3.10+
- [iperf3](https://iperf.fr/iperf-download.php) binary on each agent host

### 1. Start Agents

Install and run on each test host (server and client machines):

```bash
python main_agent.py
```

The agent starts a REST API on port **9001** (configurable) and listens for UDP discovery on port **9999**. Agents have zero pip dependencies — stdlib only.

### 2. Start Web Dashboard

Install dependencies and start:

```bash
pip install -r requirements.txt
python main_web.py
```

Open `http://localhost:5000` in your browser.

The React frontend is served from `web/frontend/dist/`. To rebuild it:

```bash
cd web/frontend
npm install
npm run build
```

### 3. Configure and Run Tests

1. Add agents (server + clients) in the dashboard sidebar
2. Configure test mode, duration, protocol, and per-client settings
3. Click **Start** — watch live throughput charts update in real time
4. Generate HTML reports or export CSV when done

## Agent Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `--host` | `0.0.0.0` | Interface to listen on |
| `--port` | `9001` | REST API port |
| Advertise MGMT IP | auto-detect | IP shown in discovery responses |
| iperf3 Path | auto-detect | Path to iperf3 binary |
| Autostart Ports | `5211,5212` | iperf3 server ports to start automatically |
| API Token | *(empty)* | Optional `X-API-Key` header for authentication |

Agent config is persisted to `%LOCALAPPDATA%\iperf3-agent\config.json` (Windows) or `~/.config/iperf3-agent/config.json` (Linux).

## Agent REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/server/start` | POST | Start iperf3 servers (`ports`, `bind`, `bind_map`) |
| `/server/stop` | POST | Stop iperf3 servers |
| `/client/start` | POST | Start iperf3 clients (`target`, `port`, `duration`, `proto`, `parallel`, `bitrate`, `bidir`, `reverse`) |
| `/client/stop` | POST | Stop iperf3 clients |
| `/metrics` | GET | Poll real-time throughput metrics |
| `/status` | GET | Agent status, log directory, advertise IP |

All endpoints require `X-API-Key` header when an API token is configured.

## Test Configuration

Test profiles are saved as JSON. Example:

```json
{
  "server": {
    "agent": "http://192.168.1.10:9001",
    "bind": "192.168.1.10"
  },
  "clients": [
    {
      "name": "client-1",
      "agent": "http://192.168.1.20:9001",
      "target": "192.168.1.10",
      "proto": "tcp",
      "parallel": 4,
      "bitrate": "0",
      "bidir": true,
      "reverse": false
    }
  ],
  "mode": "bidir",
  "duration_sec": 60,
  "base_port": 5211,
  "keep_servers_open": true
}
```

### Test Modes

| Mode | Description |
|------|-------------|
| `bidir` | Bidirectional (iperf3 `--bidir`) |
| `up_only` | Client-to-server only |
| `down_only` | Server-to-client only (iperf3 `--reverse`) |
| `dual` | Both directions simultaneously |
| `two_phase` | Upload phase then download phase sequentially |

### Constraints

- UDP tests cannot use `--bidir` or parallel > 1 (iperf3 limitation)

## Build

Build a standalone Windows agent executable with PyInstaller:

```bash
python build.py
```

Options:

```bash
python build.py --onefile    # single .exe only
python build.py --onedir     # directory bundle only
python build.py --no-zip     # skip zip compression
```

Output goes to `release/`:

```
release/
  iperf3-agent_v6.0.2/        # onedir bundle
  iperf3-agent_v6.0.2.zip     # zipped onedir
  iperf3-agent_v6.0.2.exe     # single exe
```

Build requires: `pip install pyinstaller`

### iperf3 Binary Setup (Windows)

Place iperf3 and Cygwin DLLs in the project root before building:

```
iperf3.exe
cygwin1.dll
cygz.dll
cygcrypto-3.dll
```

Download from: [iperf.fr](https://iperf.fr/iperf-download.php)

On Linux, install iperf3 from your package manager (`apt install iperf3`).

## Deployment

See [deploy/README-deploy.md](deploy/README-deploy.md) for Linux systemd and Windows service installation scripts.

## Project Structure

```
iperf-manager/
  main_agent.py            # Headless agent entry point
  main_web.py              # Web dashboard entry point
  build.py                 # PyInstaller build script (agent)
  requirements.txt         # Python dependencies (web dashboard)
  core/
    agent_service.py       # REST API + iperf3 process management
    test_runner.py         # Test orchestration (server/client lifecycle)
    net_utils.py           # HTTP helpers, connection pool, metrics parsing
    config_model.py        # Configuration validation
    csv_recorder.py        # CSV metrics recording with rollover
    report.py              # HTML report generation with matplotlib charts
    constants.py           # Versions, defaults, column definitions
    helpers.py             # iperf3 path resolution, utilities
  web/
    app.py                 # Flask + Socket.IO backend
    frontend/              # React + TypeScript + Tailwind SPA
      src/
        App.tsx            # Main application component
        components/        # Header, Sidebar, LiveResults, TestConfig, etc.
        hooks/             # useSocket hook for real-time updates
  data/
    profiles/              # Saved test profiles (JSON)
  deploy/
    install-agent-linux.sh # Linux systemd service installer
    Install-Agent.ps1      # Windows service installer
```

## License

[MIT](LICENSE)

---

> *This project originated as a fork of [iperf_manager](https://github.com/chaeynz/iperf_manager) and has since been extensively rewritten.*
