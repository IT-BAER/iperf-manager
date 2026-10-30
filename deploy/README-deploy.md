# iperf-manager Deployment Guide

This guide covers every installer option, path, setting and common problem. For a short overview, see the [README](../README.md).

## Contents

- [What gets installed where](#what-gets-installed-where)
- [Before you start](#before-you-start)
- [Web dashboard (Linux)](#web-dashboard-linux)
- [Linux agent](#linux-agent)
- [Windows agent](#windows-agent)
- [Add agents to the dashboard](#add-agents-to-the-dashboard)
- [Remote update from the dashboard](#remote-update-from-the-dashboard)
- [Agent configuration](#agent-configuration)
- [Verify an agent](#verify-an-agent)
- [Network ports and firewall](#network-ports-and-firewall)
- [Security notes](#security-notes)
- [Manual agent installation](#manual-agent-installation)
- [Troubleshooting](#troubleshooting)

## What gets installed where

| Script | Purpose | Runs as |
|--------|---------|---------|
| `deploy/install-web-linux.sh` | Installs or updates the web dashboard: repository, Python venv, frontend build, `iperf-web` service | root |
| `deploy/setup-web-service.sh` | Writes and starts the `iperf-web` systemd service. `install-web-linux.sh` calls it; you can also run it alone | root |
| `deploy/install-agent-linux.sh` | Installs, updates or removes a Linux agent (`iperf-agent` systemd service) | root |
| `deploy/Install-Agent.ps1` | Installs, updates or removes a Windows agent (`iperf-agent` scheduled task) | Administrator |
| `deploy/agent-update.sh`, `deploy/Agent-Update.ps1` | Updaters for [remote update](#remote-update-from-the-dashboard). The agent installers copy them into place; you do not run them by hand | root / SYSTEM |

| Item | Linux | Windows |
|------|-------|---------|
| Program files | `/opt/iperf-manager` | `C:\iperf-manager` |
| Agent config, API key, TLS certificate | `/etc/iperf-manager/iperf3-agent/` | `C:\iperf-manager\config\iperf3-agent\` |
| Agent logs | `/var/log/iperf-manager/` | `C:\iperf-manager\logs\` |
| Agent service | systemd unit `iperf-agent` | scheduled task `iperf-agent` (runs as SYSTEM at startup) |
| Updater | `/usr/local/lib/iperf-manager/agent-update.sh`, unit `iperf-agent-update` | `C:\ProgramData\iperf-manager\Agent-Update.ps1`, task `iperf-agent-update` |
| Dashboard service | systemd unit `iperf-web` | not supported |
| Dashboard private state (stored agent keys, schedules) | `/var/lib/iperf-manager/dashboard/` | - |
| Dashboard extra settings | `/etc/iperf-manager/web.env` (optional, see [Dashboard settings](#dashboard-settings)) | - |
| Test reports | `/opt/iperf-manager/data/` | - |

## Before you start

- **Linux:** Debian, Ubuntu or Proxmox with `apt`, `systemd` and root access (`sudo`). The installers install missing packages (`git`, `python3`, `iperf3`, `openssl`, and for the dashboard `nodejs`/`npm`).
- **Windows:** PowerShell 5.1 or later, started with **Run as Administrator**. The installer installs Python 3.12 and Git for Windows when they are missing, and downloads `iperf3.exe`.
- **Internet access** from the target host to `github.com`, `api.github.com`, `raw.githubusercontent.com` and the package mirrors.
- **Line endings:** if you copy a `.sh` script from a Windows checkout, convert it first, or bash fails on line 3 with `set: pipefail: invalid option name`: `tr -d '\r' < install-agent-linux.sh | sudo bash`.

### Choose the version (ref)

Without a ref, all installers install the **latest GitHub release**. The one-liners below download the installer of the latest release. Set these variables once per shell:

```bash
REPO="IT-BAER/iperf-manager"
REF="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
REF="${REF:-main}"
```

To install a specific tag or branch:

| Installer | How to pin a ref |
|-----------|------------------|
| `install-web-linux.sh` | `--ref v1.3.0` (or `--branch v1.3.0`) |
| `install-agent-linux.sh` | `--ref v1.3.0`, or environment variable `IPERF_MANAGER_REF=v1.3.0` |
| `Install-Agent.ps1` | environment variable only: `$env:IPERF_MANAGER_REF = 'v1.3.0'` before you run the script |

To follow `main` instead of releases, download the script from `main` and pass `--ref main`:

```bash
curl -fsSL "https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-web-linux.sh" \
  | sudo bash -s -- --ref main
```

## Web dashboard (Linux)

### Install

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-web-linux.sh" | sudo bash
```

At the end, the installer prints the dashboard URL and, on a fresh install, a generated `admin` password. **Save this password.** The service stores only its hash, and the password is not shown again.

Install with your own port and credentials:

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-web-linux.sh" \
  | sudo DASHBOARD_AUTH_USERNAME=admin DASHBOARD_AUTH_PASSWORD='change-me' \
    bash -s -- --port 5000
```

### Options of `install-web-linux.sh`

| Option | Default | Effect |
|--------|---------|--------|
| `--install` | yes | Install or bring an existing install up to date |
| `--update` | - | Same as `--install` |
| `--uninstall` | - | Stop and remove the `iperf-web` service and its ufw rule |
| `--purge` | - | With `--uninstall`: also delete the install directory |
| `--ref <name>`, `--branch <name>` | latest release | Tag or branch to install |
| `--repo-url <url>` | GitHub repository | Install from a fork or mirror |
| `--install-dir <path>` | `/opt/iperf-manager` | Install directory |
| `--port <port>` | `5000` | Dashboard port. Also: environment variable `IPERF_MANAGER_WEB_PORT` |
| `--skip-repo-sync` | - | Use the tree in the install directory as it is (no git fetch/reset). Also: `IPERF_MANAGER_SKIP_REPO_SYNC=1` |
| `--skip-frontend-build` | - | Skip `npm install` and `npm run build`. Also: `IPERF_MANAGER_SKIP_FRONTEND_BUILD=1` |

The installer opens the dashboard port in ufw when ufw is active. Keep the default install directory: `setup-web-service.sh` always starts the service from `/opt/iperf-manager`.

### Update

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-web-linux.sh" \
  | sudo bash -s -- --update
```

Updates keep the login, the port, the stored agent keys and the schedules. They do not change the password.

### Uninstall

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-web-linux.sh" \
  | sudo bash -s -- --uninstall
```

Add `--purge` to also delete `/opt/iperf-manager`. The private state in `/var/lib/iperf-manager/dashboard` and `/etc/iperf-manager/web.env` stay in place; delete them by hand if you do not need them.

### Login and credentials

Login is on by default. The service gets its credentials in this order:

1. `DASHBOARD_AUTH_USERNAME` and `DASHBOARD_AUTH_PASSWORD_HASH` or `DASHBOARD_AUTH_PASSWORD`, passed when you run the installer.
2. The values already in `/etc/iperf-manager/web.env` or in the current `iperf-web` unit (reruns keep them).
3. On a fresh install: user `admin` with a generated password, printed once.

Change the password (the hash goes into the unit, the password does not):

```bash
AUTH_HASH=$(/opt/iperf-manager/venv/bin/python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('new-password'))")
sudo DASHBOARD_AUTH_USERNAME=admin DASHBOARD_AUTH_PASSWORD_HASH="$AUTH_HASH" \
  bash /opt/iperf-manager/deploy/setup-web-service.sh
```

Run the dashboard without login (trusted networks only):

```bash
sudo DASHBOARD_AUTH_DISABLE=1 bash /opt/iperf-manager/deploy/setup-web-service.sh
```

The dashboard serves plain HTTP. For access from untrusted networks, put a reverse proxy with HTTPS in front of it and set `SESSION_COOKIE_SECURE=1`, so the browser sends the session cookie only over HTTPS.

### Dashboard settings

`setup-web-service.sh` writes these settings into the `iperf-web` unit. Pass them as environment variables when you run the script (or `install-web-linux.sh`):

| Variable | Default | Effect |
|----------|---------|--------|
| `DASHBOARD_AUTH_USERNAME` | `admin` | Login user |
| `DASHBOARD_AUTH_PASSWORD_HASH` | generated | Werkzeug password hash (preferred) |
| `DASHBOARD_AUTH_PASSWORD` | - | Plain password; the script stores only its hash |
| `DASHBOARD_AUTH_DISABLE` | off | `1` turns the login off |
| `SESSION_COOKIE_SECURE` | off | `1` sends the session cookie only over HTTPS |
| `WEB_PORT` | `5000` | Dashboard port (`setup-web-service.sh` only; the web installer uses `--port`) |
| `WEB_STATE_DIR` or `IPERF_MANAGER_STATE_DIR` | `/var/lib/iperf-manager/dashboard` | Private state directory |

Other settings go into `/etc/iperf-manager/web.env`, one `NAME=value` per line. `setup-web-service.sh` copies them into the unit on every run, so run it again after you edit the file:

| Variable | Default | Effect |
|----------|---------|--------|
| `DASHBOARD_DISCOVERY_CIDRS` | - | Comma-separated IPs or networks (at most 1024 addresses per network) that discovery probes directly. Use this when agents are in other subnets, because broadcasts do not cross routers |
| `DASHBOARD_DISCOVERY_BROADCAST` | `auto` | `1` always sends broadcasts, `0` never. `auto` sends broadcasts only when `DASHBOARD_DISCOVERY_CIDRS` is empty |
| `DASHBOARD_AUTH_SESSION_HOURS` | `12` | Session lifetime in hours |
| `DASHBOARD_AUTH_MAX_ATTEMPTS` | `5` | Failed logins allowed per time window |
| `DASHBOARD_AUTH_RATE_WINDOW_SEC` | `900` | Time window for failed logins, in seconds |
| `CORS_ORIGINS` | same origin only | Comma-separated extra origins allowed for Socket.IO |

Example:

```bash
echo 'DASHBOARD_DISCOVERY_CIDRS=10.10.20.0/24,192.168.0.15' | sudo tee -a /etc/iperf-manager/web.env
sudo bash /opt/iperf-manager/deploy/setup-web-service.sh
```

`FLASK_SECRET` (session signing key) is generated once and kept on reruns. A new value logs out all users.

### Staged update from a local tree

Use this to deploy a local tree, for example local changes. The installer still needs the package mirrors (apt, pip, npm). It keeps the private dashboard state.

```bash
# on your workstation
tar -czf /tmp/iperf-manager-deploy.tar.gz \
  --exclude='node_modules' --exclude='venv' --exclude='__pycache__' --exclude='.git' \
  --exclude='web/frontend/dist' --exclude='*.pyc' --exclude='data/.dashboard' \
  -C /path/to/iperf-manager .

# on the target host
sudo tar -xzf /tmp/iperf-manager-deploy.tar.gz -C /opt/iperf-manager
cd /opt/iperf-manager && sudo bash deploy/install-web-linux.sh --skip-repo-sync
```

From a Windows checkout, create the archive with `git -c core.autocrlf=false archive --format=tar.gz -o iperf-manager-deploy.tar.gz HEAD`, so the scripts keep LF line endings.

## Linux agent

### Install

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-agent-linux.sh" | sudo bash
```

The installer installs `iperf3` and `openssl`, clones the repository to `/opt/iperf-manager`, writes the config, starts the `iperf-agent` service and opens the ports in ufw (when ufw is active). At the end it prints:

- **API token**: a generated key, shown only on this first run. Save it; the dashboard needs it to control the agent (see [Add agents to the dashboard](#add-agents-to-the-dashboard)).
- **TLS SHA-256**: the certificate fingerprint. Compare it with the fingerprint the dashboard shows.

Install with options:

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-agent-linux.sh" \
  | sudo bash -s -- --token "mySecretKey" --port 9001 --iperf-ports "5211,5212,5213,5214" --remote-update yes
```

| Option | Default | Effect |
|--------|---------|--------|
| `--token <key>` | generated on first install | Agent API key. Reruns keep the existing key unless you pass a new one |
| `--port <port>` | `9001` | Agent REST API port |
| `--iperf-ports <list>` | `5211,5212` | iperf3 server ports that the agent starts and the firewall opens. See [Network ports](#network-ports-and-firewall) |
| `--remote-update yes\|no` | `no` | Allow the dashboard to update this agent |
| `--ref <name>` | latest release | Tag or branch to install |
| `--uninstall` | - | Remove the agent (see below) |
| `--purge` | - | With `--uninstall`: also delete `/opt/iperf-manager` |

### Update

Run the install command again. A rerun keeps every value in `config.json` (API key, port, iperf3 ports, advertise IP, remote update) unless you pass the option again. With remote update turned on, you can also click **Update** in the dashboard.

### Uninstall

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-agent-linux.sh" \
  | sudo bash -s -- --uninstall
```

This removes the `iperf-agent` and `iperf-agent-update` units, the updater, the agent config folder `/etc/iperf-manager/iperf3-agent` (API key and certificate), `/var/log/iperf-manager`, and the ufw rules for the configured ports. It keeps `/opt/iperf-manager` and `/etc/iperf-manager/web.env`, because a dashboard on the same host still needs them. Add `--purge` to also delete `/opt/iperf-manager`; do not use `--purge` when the dashboard runs on the same host.

### Staged local tree

Copy the repository to `/opt/iperf-manager` first, then run:

```bash
cd /opt/iperf-manager
sudo IPERF_MANAGER_SKIP_REPO_SYNC=1 bash deploy/install-agent-linux.sh
```

The installer then uses the tree as it is and does not reset it to GitHub.

## Windows agent

Run all commands in PowerShell **as Administrator**.

### Install

Download the installer of the latest release:

```powershell
$ref = (Invoke-RestMethod -UseBasicParsing https://api.github.com/repos/IT-BAER/iperf-manager/releases/latest).tag_name
Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/IT-BAER/iperf-manager/$ref/deploy/Install-Agent.ps1" -OutFile "$env:TEMP\Install-Agent.ps1"
```

Run it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\Install-Agent.ps1"
```

The installer installs Python and Git when they are missing, downloads `iperf3.exe`, sets up `C:\iperf-manager`, registers the scheduled tasks, creates the firewall rules and starts the agent. Like the Linux installer, it prints the **API token** (first run only) and the **TLS SHA-256** fingerprint.

### Install with parameters

Add the parameters to the run command, for example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\Install-Agent.ps1" -Port 9001 -IperfPorts '5211,5212,5213,5214' -RemoteUpdate Yes
```

| Parameter | Default | Effect |
|-----------|---------|--------|
| `-Token <key>` | generated on first install | Agent API key. Reruns keep the existing key unless you pass a new one |
| `-Port <port>` | `9001` | Agent REST API port |
| `-IperfPorts <list>` | `5211,5212` | iperf3 server ports that the agent starts and the firewall opens |
| `-RemoteUpdate Yes\|No` | `No` | Allow the dashboard to update this agent |
| `-InstallDir <path>` | `C:\iperf-manager` | Install directory |
| `-Uninstall` | - | Remove the agent (see below) |

To pin a version, set `$env:IPERF_MANAGER_REF = 'v1.3.0'` in the same PowerShell window before you run the script.

### Update

Run the install command again. Like on Linux, a rerun keeps the values in `config.json` unless you pass the parameter again, and it keeps a remote-address restriction that you set on the "iperf-manager API" firewall rule.

### Uninstall

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\iperf-manager\deploy\Install-Agent.ps1 -Uninstall
```

This removes both scheduled tasks, all firewall rules named `iperf-manager*`, `C:\ProgramData\iperf-manager` and the **whole** `C:\iperf-manager` folder, including the config with the API key and the certificate. A later install creates a new key and certificate, so the dashboard shows "certificate fingerprint changed" and needs the new key.

### Staged local tree

Copy the repository files to `C:\iperf-manager` first, then run:

```powershell
$env:IPERF_MANAGER_SKIP_REPO_SYNC = "1"; powershell -NoProfile -ExecutionPolicy Bypass -File C:\iperf-manager\deploy\Install-Agent.ps1
```

### Folder permissions

The installer limits `C:\iperf-manager` and `C:\ProgramData\iperf-manager` to SYSTEM and Administrators, because code in both folders runs as SYSTEM. It makes Administrators the owner of any item that a non-admin created there, resets those items to the inherited permissions, and deletes links inside both folders. It stops when one of the folders itself is a link.

## Add agents to the dashboard

1. Open the dashboard and log in.
2. Agents in the same subnet appear automatically (UDP broadcast discovery on page load). For other subnets, click **Add Agent** and enter `https://<agent-ip>:9001`, or set `DASHBOARD_DISCOVERY_CIDRS` (see [Dashboard settings](#dashboard-settings)).
3. Set the API key: click the key button on the agent row and paste the token. In the **Add Agent** form you can enter the key directly. The dashboard stores the key on the server and never sends it back to the browser.
4. Hover over the agent URL to see the pinned certificate fingerprint. Compare it with the `TLS SHA-256` line of the installer output.

An agent without the right key shows as offline or answers `403 forbidden`.

**Read the API key later.** The installer shows a generated key only once. Afterwards, read it from the config (root or Administrator only):

```bash
sudo sed -n 's/.*"api_token": "\(.*\)".*/\1/p' /etc/iperf-manager/iperf3-agent/config.json
```

```powershell
(Get-Content -Raw 'C:\iperf-manager\config\iperf3-agent\config.json' | ConvertFrom-Json).api_token
```

## Remote update from the dashboard

With remote update turned on, the dashboard shows the agent version and an **Update** button when a newer GitHub release exists. Remote update is off by default. Turn it on per agent with the installer:

```bash
curl -fsSL "https://raw.githubusercontent.com/${REPO}/${REF}/deploy/install-agent-linux.sh" \
  | sudo bash -s -- --remote-update yes
```

On Windows, run the installer with `-RemoteUpdate Yes` (see [Install with parameters](#install-with-parameters)). When remote update is off, the dashboard shows an info icon instead of the button.

How it works:

- The agent needs an API key; without one, it refuses `/update`. The agent also refuses the update while a test runs.
- The dashboard sends no version, URL or command. The agent starts a separate updater (`iperf-agent-update.service` on Linux, scheduled task `iperf-agent-update` on Windows). The updater reads the latest release of `IT-BAER/iperf-manager` from GitHub and runs that release's own installer.
- The agent host needs HTTPS access to `api.github.com` and `github.com`. The dashboard host needs HTTPS access to `api.github.com` to know the latest version.
- The agent restarts during the update. Do not start tests on it until the update ends.
- A failed update restores the previous version: on Linux the git checkout and the `iperf-agent` unit file, on Windows the install folder and the `iperf-agent` task. The dashboard then shows "Update failed"; hover over it for the error.
- Log: `/var/log/iperf-manager/agent-update.log` (Linux), `C:\ProgramData\iperf-manager\agent-update.log` (Windows). State: `update-state.json` next to `config.json`.
- Manual run for one ref, as root or Administrator: `/usr/local/lib/iperf-manager/agent-update.sh --ref v1.3.0` or `C:\ProgramData\iperf-manager\Agent-Update.ps1 -Ref v1.3.0`.

**Downgrade warning:** installers before v1.3.0 store the agent API key in the systemd unit (Linux), or in a machine environment variable and in `start-agent.cmd` (Windows). Local users can read all of these. The old Windows installer also resets the "iperf-manager API" firewall rule to any remote address. After a downgrade, check both by hand, or install v1.3.0 or later again.

## Agent configuration

The agent reads `config.json` from the folder `iperf3-agent` under `LOCALAPPDATA_IPERF` or `LOCALAPPDATA`:

| How the agent runs | Config file |
|--------------------|-------------|
| Linux installer | `/etc/iperf-manager/iperf3-agent/config.json` |
| Windows installer | `C:\iperf-manager\config\iperf3-agent\config.json` |
| `python main_agent.py` on Linux | `~/iperf3-agent/config.json` (home directory, because Linux has no `LOCALAPPDATA`) |
| `python main_agent.py` on Windows | `%LOCALAPPDATA%\iperf3-agent\config.json` |

Example:

```json
{
  "autostart": "5211,5212",
  "bind_host": "0.0.0.0",
  "port": 9001,
  "iperf3_path": "iperf3",
  "advertise_ip": "",
  "api_token": "generated-secret",
  "allow_remote_update": false,
  "tls": true
}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `autostart` | `5211,5212` | iperf3 server ports started at agent start |
| `bind_host` | `0.0.0.0` | Address the REST API listens on |
| `port` | `9001` | REST API port |
| `iperf3_path` | `iperf3` | Path to the iperf3 binary |
| `advertise_ip` | auto-detect | Management IP the agent reports in discovery |
| `api_token` | empty (installers generate one) | Key the dashboard must send as `X-API-Key`. Empty means no authentication |
| `allow_remote_update` | `false` | Allow `POST /update` (see [Remote update](#remote-update-from-the-dashboard)) |
| `tls` | `true` | HTTPS on the API port with a self-signed certificate. `false` serves plain HTTP only |

Environment overrides:

| Variable | Effect |
|----------|--------|
| `AGENT_MGMT_IP` | Used when `advertise_ip` is empty |
| `AGENT_LOGDIR` | Log directory |
| `LOCALAPPDATA_IPERF` | Base folder for `iperf3-agent/config.json` (takes priority over `LOCALAPPDATA`) |

After you edit `config.json`, restart the agent:

```bash
sudo systemctl restart iperf-agent
```

```powershell
Stop-ScheduledTask -TaskName iperf-agent; Start-ScheduledTask -TaskName iperf-agent
```

## Verify an agent

Every agent API call needs the API key, also `/status`. Plain HTTP on the same port works for local checks.

Linux:

```bash
sudo systemctl status iperf-agent
TOKEN=$(sudo sed -n 's/.*"api_token": "\(.*\)".*/\1/p' /etc/iperf-manager/iperf3-agent/config.json)
curl -s -H "X-API-Key: $TOKEN" http://localhost:9001/status
openssl x509 -in /etc/iperf-manager/iperf3-agent/agent.crt -noout -fingerprint -sha256
journalctl -u iperf-agent -n 50
```

Windows:

```powershell
Get-ScheduledTask -TaskName iperf-agent | Select-Object State
$key = (Get-Content -Raw 'C:\iperf-manager\config\iperf3-agent\config.json' | ConvertFrom-Json).api_token
Invoke-RestMethod http://localhost:9001/status -Headers @{ 'X-API-Key' = $key }
Get-ChildItem C:\iperf-manager\logs | Sort-Object LastWriteTime | Select-Object -Last 5
```

Expected: `/status` returns JSON with `version`, `port` and `tls.enabled: true`. `{"error": "forbidden"}` means a missing or wrong key.

Agent API endpoints (all need `X-API-Key` when a key is set):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/status` | GET | Version, servers, clients, IPs, TLS fingerprint, update state |
| `/metrics` | GET | Live throughput of running clients |
| `/server/start`, `/server/stop` | POST | Start or stop iperf3 servers |
| `/client/start`, `/client/stop` | POST | Start or stop iperf3 clients |
| `/update` | POST | Start the updater (only with `allow_remote_update`) |

## Network ports and firewall

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 5000 | TCP | browser -> dashboard | Web dashboard |
| 9001 | TCP | dashboard -> agent | Agent REST API (HTTPS) |
| 9999 | UDP | dashboard -> agent | Agent discovery |
| 5211 and up | TCP and UDP | client agent -> server agent | iperf3 test traffic |
| 443 | TCP | agent and dashboard -> GitHub | Remote update and release check |

**iperf3 ports per test:** the test server uses one port per client: `base_port` (default `5211`) for the first client, `base_port + 1` for the second, and so on. The installers open only the ports in `--iperf-ports` / `-IperfPorts` (default `5211,5212`, so two clients). For more clients, list more ports on the **server** agent, for example `--iperf-ports "5211,5212,5213,5214"`, or open a range such as `5211-5299` in your firewall.

Example rules for a segmented network:

- UDP `9999` and TCP `9001` from the dashboard host to all agent networks
- TCP and UDP `5211-5299` between agent networks
- TCP `5000` from admin clients to the dashboard host

On Windows you can limit the API rule to the dashboard host; reruns of the installer keep that restriction:

```powershell
Set-NetFirewallRule -DisplayName "iperf-manager API (TCP 9001)" -RemoteAddress 10.10.20.20
```

## Security notes

- **Agent API key:** the installers generate a random key on the first install and keep it on reruns. The key is stored only in `config.json`, readable by root or Administrators only. The agent never reads the old copies in the systemd unit, `start-agent.cmd` or the machine variable `AGENT_API_KEY`; the v1.3.0 installers remove them.
- **TLS:** agents serve HTTPS on the API port with a self-signed certificate (`agent.crt` and `agent.key` next to `config.json`), created with the `openssl` CLI on first start. The Linux installer installs `openssl`; on Windows the agent uses `openssl.exe` from `PATH` or from Git for Windows. Without `openssl`, the agent logs a warning and serves plain HTTP only.
- **Certificate pinning:** the same port still answers plain HTTP, so older dashboards keep working. The dashboard switches an agent to `https://` as soon as the agent reports TLS, never switches back, and pins the certificate SHA-256 fingerprint on first contact (trust on first use).
- **Certificate change:** when an agent certificate changes (reinstall, deleted `agent.crt`), the dashboard marks the agent offline with "certificate fingerprint changed". Compare the new fingerprint with the installer output, then trust it in the dashboard.
- **Old keys:** API keys that were sent over plain HTTP before the switch to HTTPS may have been captured. Set new keys after all agents and the dashboard use HTTPS.
- **Test traffic:** iperf3 test traffic is not encrypted (iperf3 limit).
- **Remote update trust:** remote update runs the installer of the latest GitHub release as root (Linux) or SYSTEM (Windows). Turn it on only where you accept that trust in the GitHub repository. There is no signature check beyond HTTPS.
- **Dashboard:** login is on by default. Without HTTPS in front of it, do not expose the dashboard to untrusted networks.

## Manual agent installation

Use this only when you cannot run the one-liner directly.

Linux:

```bash
sudo apt update
sudo apt install -y iperf3 git python3 openssl
REF="$(curl -fsSL "https://api.github.com/repos/IT-BAER/iperf-manager/releases/latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
sudo git clone --branch "${REF:-main}" https://github.com/IT-BAER/iperf-manager.git /opt/iperf-manager
sudo bash /opt/iperf-manager/deploy/install-agent-linux.sh --ref "${REF:-main}"
```

Windows (as Administrator, Git installed):

```powershell
$ref = (Invoke-RestMethod -UseBasicParsing https://api.github.com/repos/IT-BAER/iperf-manager/releases/latest).tag_name
git clone --branch $ref https://github.com/IT-BAER/iperf-manager.git C:\iperf-manager
$env:IPERF_MANAGER_REF = $ref; powershell -NoProfile -ExecutionPolicy Bypass -File C:\iperf-manager\deploy\Install-Agent.ps1
```

## Troubleshooting

| Problem | Cause and fix |
|---------|---------------|
| Agent is not discovered | Broadcasts do not cross routers. Add the agent with **Add Agent**, or set `DASHBOARD_DISCOVERY_CIDRS`. Check UDP 9999 to the agent |
| Agent is offline, API unreachable | Check `systemctl status iperf-agent` or the scheduled task, and TCP 9001 in the firewall |
| `{"error": "forbidden"}` or agent offline after adding | Missing or wrong API key. Set the key with the key button on the agent row; read it as shown in [Add agents](#add-agents-to-the-dashboard) |
| "certificate fingerprint changed" | The agent has a new certificate (reinstall, deleted `agent.crt`). Compare the fingerprint with the installer output, then trust it |
| Installer warns "No TLS certificate" | `openssl` is missing. Linux: `apt install openssl`; Windows: install Git for Windows. Then restart the agent |
| No **Update** button, only an info icon | Remote update is off. Rerun the installer with `--remote-update yes` / `-RemoteUpdate Yes` |
| "Update failed" | Read `agent-update.log` (see [Remote update](#remote-update-from-the-dashboard)). The previous version is restored |
| Test fails to start or hangs at 0 | `iperf3` missing on an agent, or iperf3 ports blocked. With more clients than `--iperf-ports` entries, open more ports (see [Network ports](#network-ports-and-firewall)) |
| Scheduled test shows "skipped: test already running" | Only one test runs at a time. A schedule whose test is still running skips the next run. iperf3 accepts at most 86400 seconds per test |
| `iperf-agent` exits with `226/NAMESPACE` | `/opt/iperf-manager/data` is missing for the systemd `ReadWritePaths` rule. Rerun the Linux installer |
| `set: pipefail: invalid option name` | The script has Windows line endings. Use `tr -d '\r' < script.sh \| sudo bash` |
| Dashboard unreachable | Check `systemctl status iperf-web` and TCP 5000. Check that `/opt/iperf-manager/web/frontend/dist/` exists |
| Lost dashboard password | Set a new one as shown in [Login and credentials](#login-and-credentials) |
| Config change has no effect | Restart the agent or rerun `setup-web-service.sh` for the dashboard |
