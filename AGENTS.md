# Repository Guidelines

## Project Structure & Module Organization
- Entry points:
  - `main_dashboard.py`: PySide6 dashboard launcher
  - `main_agent.py`: PySide6 agent launcher (`--headless` supported)
  - `controller_v5_18.py`: CLI runner for config-driven tests
- Core logic lives in `core/`:
  - `core/agent_service.py` (REST + iperf3 process management)
  - `core/test_runner.py` (server/client orchestration + polling loop)
  - `core/net_utils.py` (HTTP helpers, keep-alive pool, metrics parsing)
  - `core/config_model.py`, `core/csv_recorder.py`, `core/report.py`
- UI layer lives in `ui/` (`pages/`, `models/`, `workers/`, `widgets/`, `theme/`).
- Runtime outputs and profiles are under `data/`.

## Build, Test, and Development Commands
- `python main_agent.py`
  - Start Agent GUI.
- `python main_agent.py --headless`
  - Run agent service without UI (factory/daemon use).
- `python main_dashboard.py`
  - Start dashboard UI.
- `python controller_v5_18.py --config test_config.json --out result.csv`
  - Run non-UI test flow from JSON.
- `python test_all.py`
  - Run integration/regression test suite.
- `python build.py` / `python build.py agent` / `python build.py dashboard`
  - Build Windows executables with PyInstaller (onedir+onefile, zip).

## Coding Style & Naming Conventions
- Python, UTF-8, 4-space indentation.
- `snake_case` for functions/variables, `CapWords` for classes.
- Keep business logic in `core/`; UI files should avoid protocol/process logic duplication.
- Prefer explicit exceptions over broad `except Exception` on critical paths.

## Testing Guidelines
- Primary gate: `python test_all.py` (must pass before merge).
- Add tests when changing:
  - network/auth flow (`X-API-Key`, status/metrics polling)
  - CSV persistence/rollover
  - config serialization/validation
- Keep tests deterministic (mock HTTP servers, temp directories).

## Commit & Pull Request Guidelines
- Commit message format: `type: short summary` (e.g., `fix: preserve csv on rollover`).
- PR should include:
  - behavior change summary
  - verification steps/commands
  - config impact (`api_key`, polling interval, ports)
  - screenshots for dashboard UI changes

## Security & Configuration Tips
- Closed network is assumed, but use `api_key` to prevent accidental control calls.
- Do not commit site-specific IPs, tokens, or generated `data/*.csv` artifacts.
- For long-running sessions, ensure graceful shutdown paths run (`close_pool`, service stop).
