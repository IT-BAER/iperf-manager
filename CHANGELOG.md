# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog,
and this project adheres to Semantic Versioning.

## [Unreleased]

### Changed
- Default test base port is now `5211` in the dashboard, the backend fallback and the README, matching the agents' iperf3 autostart ports (`5211,5212`) and `/api/meta`. Saved profiles keep their stored port.

### Fixed
- The dashboard live chart no longer freezes mid-test: the metrics poller kept running only until the first zero-throughput poll (a 0 Mbit/s interval or an agent that missed two polls) and then stopped for the rest of the test.
- Profile dropdown: shows "No saved profiles" instead of an empty strip, widens for long names and truncates them with a tooltip, keeps a fixed width in the header, shows the placeholder muted, and offers "No profile" to clear the selection.
- Switching to Reports and back no longer resets the test setup, live chart and log.
- The agent list appears at once on page load; agent refresh probes all agents in parallel (68 s to 4 s with 17 unreachable agents).
- Profiles saved with backend mode names (`bidir`, `up_only`, `down_only`) now select the matching mode button.
- Duration is capped at 86400 s, the iperf3 maximum.
- Consistent look: one chevron style on all collapsible panels, themed dropdowns in Scheduled Tests, one throughput format everywhere (`0 Mbps` instead of `0 Kbps`/`0`), Upload green and Download blue in the KPI bar, and a neutral status dot when idle.
- Removing an agent and deleting reports now ask for confirmation, like profiles and schedules.
- A schedule can be added while a test is running.
- `data/profiles/*.json` is gitignored.
- Agents now record the real iperf3 client exit code; before, a client whose output closed before the process was reaped kept `exit_code: null` in `/status`, `/metrics` and the client log.

## [1.1.0] - 2026-03-25

### Added
- Added recurring cron-based scheduled tests with dashboard APIs and persistence, supporting both profile-based runs and manual configuration snapshots.
- Added a new Scheduled Tests panel in the React dashboard to create, enable/disable, trigger, and delete recurring schedules.

### Changed
- Profile selection in the React dashboard now loads the selected profile immediately, removing the extra manual load click.
- Added stale-request protection for profile loading so rapid selection changes do not apply older responses over newer choices.
- Documented explicit main-branch install one-liners (`--ref main`) for deployments that should track `main` instead of the latest release tag.
- Hardened dashboard state persistence for deployments by moving private runtime state (agent API keys and schedules) to a configurable external directory (`IPERF_MANAGER_STATE_DIR`), with Linux service installs defaulting to `/var/lib/iperf-manager/dashboard` and automatic migration from the legacy path.
- Normalized test/schedule agent references by both agent ID and URL so legacy profile/schedule payloads still resolve stored API keys correctly and avoid 403 errors on `server/start` and `client/start`.
- Modernized all dashboard dropdown controls with a consistent themed select style and updated icon treatment to match the Web UI visual language.
- Replaced native select popups with a custom themed dropdown menu that renders above layout clipping and uses viewport-aware positioning to prevent cutoff near header and screen edges.
- Restricted the `Quality And Release` GitHub Actions workflow to trigger only on version tag pushes (`v*`).
- Corrected README test base-port defaults and examples to match the current dashboard default (`5201`).

## [1.0.0] - 2026-03-24

### Added
- Added React dashboard profile controls to select, load, save, and delete predefined test profiles.
- Added app-level profile state and API wiring so profile loading restores full test configuration, including server, clients, and test settings.
- Added GitHub Actions workflow `.github/workflows/quality-release.yml` to run quality checks and create releases on version tags.

### Changed
- Improved profile hydration in test configuration by normalizing loaded profile payloads and applying safe defaults for missing fields.
- Updated config-change synchronization to reliably persist the latest edited setup before saving a profile.
- Enforced Keep a Changelog usage in CI and release publishing by extracting the tagged changelog section into GitHub release notes.
