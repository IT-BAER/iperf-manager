---
applyTo: "**"
description: "Core project conventions for iperf-manager: Python style, layer architecture, TypeScript/React frontend rules, REST API patterns, and build/deploy practices."
---
# iperf-manager Project Conventions

## Architecture — Two Components Only

The project has two deployable components:

| Component | Path | Entry Point | Description |
|-----------|------|-------------|-------------|
| **Agent** | `core/`, `main_agent.py` | `python main_agent.py` | Headless REST API managing iperf3 processes |
| **Web Dashboard** | `web/`, `main_web.py` | `python main_web.py` | Flask + React SPA for test orchestration |

**There is no desktop/PySide6 GUI.** Do not add PySide6, tkinter, or any desktop GUI dependencies.

### Layer Separation (strict)

| Layer | Path | May import from | Must NOT import from |
|-------|------|-----------------|----------------------|
| **core** | `core/` | stdlib only | `web/`, Flask, any GUI framework |
| **web** | `web/` | `core/`, Flask, SocketIO | any GUI framework |

- `core/` is the shared, UI-independent service layer. Keep it free of framework imports.
- Entry points (`main_agent.py`, `main_web.py`) wire layers together — business logic belongs in `core/`.

### Key Modules

| Module | Purpose |
|--------|---------|
| `core/agent_service.py` | AgentService class — iperf3 server/client subprocess management, REST API, UDP discovery |
| `core/test_runner.py` | Test orchestration: server start → client start → poll metrics → stop |
| `core/net_utils.py` | HTTP helpers (keep-alive connection pool), metric polling |
| `core/csv_recorder.py` | Wide-format CSV recording with rollover and zip compression |
| `core/config_model.py` | `TestConfig` / `ClientConfig` dataclasses |
| `core/report.py` | HTML report generation with matplotlib charts |
| `core/helpers.py` | Pure utility functions (path resolution, IP listing, process helpers) |
| `core/constants.py` | Version strings (`AGENT_VERSION`, `DASHBOARD_VERSION`), network defaults, palettes |
| `web/app.py` | Flask + Socket.IO backend — routes, test lifecycle, real-time events |

## Python Style

- **File header**: `# -*- coding: utf-8 -*-` on every `.py` file.
- **Future annotations**: `from __future__ import annotations` at the top of every module.
- **Quotes**: `core/` and entry points use single quotes (`'`). `web/app.py` uses double quotes (`"`). Stay consistent within each file — match the existing convention of the file you edit.
- **Type hints**: Use PEP 604 union syntax (`X | Y`, `str | None`) — never `Optional[X]` or `Union[X, Y]`.
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for module-level constants. Private members prefixed with `_`.
- **Paths**: Prefer `pathlib.Path` over `os.path` for file system operations.
- **Docstrings**: Module-level docstring describing purpose. Class/function docstrings for public APIs. Use triple-double-quote style.
- **Imports**: Group and order as: stdlib → third-party → local (`core`). Blank line between groups.
- **Language**: Write all new comments, docstrings, and log messages in English. Some legacy files contain Korean text — do not add more.

## TypeScript / React (`web/frontend/`)

- Functional components with hooks — no class components.
- TypeScript `interface` for data shapes (not `type` aliases for objects). Simple string unions (`type Tab = 'test' | 'results'`) are fine.
- All shared types live in `types.ts`.
- API calls go through `api.ts` helper. Socket.IO via `useSocket` hook.
- Tailwind CSS for styling. No inline `style` props unless dynamically computed.
- No semicolons at end of statements.
- Icons: Font Awesome 7 (`@fortawesome/fontawesome-free`). Use `<i className="fa-solid fa-…" />`.
- Charts: chart.js + react-chartjs-2 for live results and report viewing.

### Design System (dark theme)

The frontend uses a custom Tailwind dark theme defined in `tailwind.config.js`:

| Token | Use |
|-------|-----|
| `bg` | Page background (`#0c0c0f`) |
| `surface`, `surface-raised`, `surface-hover`, `surface-active` | Panel/card backgrounds |
| `line`, `line-bright` | Borders |
| `fg`, `fg-2`, `fg-3`, `fg-4` | Text hierarchy (brightest → dimmest) |
| `accent`, `accent-dim`, `accent-subtle` | Primary blue |
| `ok`, `warn`, `err` + `-subtle` | Semantic status colors |

Custom component classes in `index.css`: `.input-base`, `.btn`, `.btn-primary`, `.btn-danger`, `.btn-sm`, `.panel`, `.collapsible-grid`.

## REST API Conventions (`web/app.py`)

- All routes under `/api/` namespace. JSON request/response bodies.
- Route groups: `/api/agents`, `/api/profiles`, `/api/test`, `/api/reports`, `/api/meta`.
- Path traversal prevention: sanitize filenames with `Path(name).name` and verify `resolve().parent == expected_dir`.
- Agent IDs are deterministic MD5-hex[:10] of the agent URL.
- Test lifecycle: `POST /api/test/start` → background thread → `POST /api/test/stop`.

### Socket.IO Events

| Event | Direction | Payload |
|-------|-----------|---------|
| `status` | server → client | `{test: TestState}` on connect |
| `metrics` | server → client | `{timestamp, clients, total_up, total_dn}` during test |
| `test_started` | server → client | `{ts, config, csv}` |
| `test_completed` | server → client | `{ts, csv, error}` |
| `test_error` | server → client | `{message, ts}` |
| `test_log` | server → client | `{message, ts}` |
| `ping_agents` | client → server | triggers agent refresh |
| `agents_update` | server → client | `Agent[]` |

## Error Handling

- At system boundaries (REST endpoints, subprocess calls, file I/O): catch `Exception`, log with `[LEVEL][context] message` format, and return a safe default.
- Inside `core/` helpers: include fallback return values; never let exceptions propagate silently without logging.

## Data & Configuration

- Runtime data (CSV, logs, HTML reports) goes to `data/` — these are git-ignored.
- Test profiles are JSON files in `data/profiles/`.
- Agent config persists to the OS-specific app data directory (see `load_agent_cfg` / `save_agent_cfg`).
- CSV format: wide-format with a `# schema,wide_v1,...,proto,<tcp|udp>` comment row, then header row. Columns: `ts`, `wall`, per-agent `{name}_up`, `{name}_dn`, `{name}_jit_ms`, `{name}_loss_pct`, `{name}_sent_mb`, `{name}_recv_mb`, `total_up`, `total_dn`.
- Report retention: auto-pruned to 1000 newest CSV files after each test run.

## Dependencies

- **Agent**: Zero pip dependencies (stdlib only).
- **Web dashboard**: Flask, flask-socketio (threading async mode).
- **Report generation**: matplotlib (optional).
- All Python deps in a single `requirements.txt`.
- **Frontend**: React 19, chart.js, react-chartjs-2, socket.io-client, Font Awesome 7, Tailwind CSS 3.

## Build & Deployment

- Agent binary: `python build.py` (wraps PyInstaller, agent target only).
- Web frontend: `npm run build` in `web/frontend/`. Output lands in `web/frontend/dist/`.
- Flask serves the React SPA from `web/frontend/dist/` if it exists, falling back to the legacy Jinja template at `web/templates/dashboard.html`.

### Deployment Scripts (`deploy/`)

| Script | Target | Description |
|--------|--------|-------------|
| `install-agent-linux.sh` | Debian/Ubuntu/Proxmox | Installs iperf3, clones repo, creates systemd service, opens firewall |
| `Install-Agent.ps1` | Windows Server | Installs iperf3, clones repo, registers scheduled task, opens firewall |
| `setup-web-service.sh` | Linux | Creates `iperf-web` systemd unit for the web dashboard |

### Versioning

- `AGENT_VERSION` and `DASHBOARD_VERSION` are defined in `core/constants.py`.
- Bump these constants when releasing — build.py reads `AGENT_VERSION` for release artifact names.
