# iperf-manager Deployment Guide

This repository ships three deployment helpers:

- `deploy/install-agent-linux.sh` for Linux agents (`iperf-agent` systemd service)
- `deploy/Install-Agent.ps1` for Windows agents (`iperf-agent` scheduled task)
- `deploy/install-web-linux.sh` for one-shot Linux web dashboard bootstrap + service setup
- `deploy/setup-web-service.sh` for the Linux web dashboard (`iperf-web` systemd service)

## One-Line Lifecycle Commands

### Linux web dashboard (Debian, Ubuntu, Proxmox)

Install:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-web-linux.sh | sudo bash
```

Install with parameters (port + dashboard credentials):

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-web-linux.sh \
  | sudo DASHBOARD_AUTH_USERNAME=admin DASHBOARD_AUTH_PASSWORD='change-me' \
    bash -s -- --port 5000
```

Update (idempotent):

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-web-linux.sh \
  | sudo bash -s -- --update
```

Uninstall service only:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-web-linux.sh \
  | sudo bash -s -- --uninstall
```

Uninstall and purge `/opt/iperf-manager`:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-web-linux.sh \
  | sudo bash -s -- --uninstall --purge
```

## Agent Quick Start

### Linux agent (Debian, Ubuntu, Proxmox)

Install:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh | sudo bash
```

Install or update with parameters:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh \
  | sudo bash -s -- --token "mySecretKey" --port 9001 --iperf-ports "5211,5212"
```

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh \
  | sudo bash -s -- --uninstall
```

Uninstall and purge `/opt/iperf-manager`:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh \
  | sudo bash -s -- --uninstall --purge
```

For staged local-tree rollouts, extract the repo to `/opt/iperf-manager` first and then run:

```bash
cd /opt/iperf-manager
sudo IPERF_MANAGER_SKIP_REPO_SYNC=1 bash deploy/install-agent-linux.sh
```

That mode keeps the staged local tree instead of resetting the host back to GitHub.

### Windows agent (PowerShell as Administrator)

Install:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr -useb https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/Install-Agent.ps1 | iex"
```

Install or update with parameters:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr -useb https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/Install-Agent.ps1 -OutFile $env:TEMP\Install-Agent.ps1; & $env:TEMP\Install-Agent.ps1 -Token 'mySecretKey' -Port 9001 -IperfPorts '5211,5212'"
```

Uninstall:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr -useb https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/Install-Agent.ps1 -OutFile $env:TEMP\Install-Agent.ps1; & $env:TEMP\Install-Agent.ps1 -Uninstall"
```

## Security Notes

- Agent install scripts now generate a random API token when you do not pass `--token` or `-Token` explicitly.
- Save the generated token and re-add the agent through the dashboard's manual Add Agent form with that API key so the dashboard server can refresh and control the protected agent.
- Set an agent token with `--token` or `-Token` explicitly if you need a deterministic value for automation.
- The web dashboard now enables built-in session authentication by default. Set `DASHBOARD_AUTH_USERNAME` plus either `DASHBOARD_AUTH_PASSWORD_HASH` or `DASHBOARD_AUTH_PASSWORD` to control the credentials, or set `DASHBOARD_AUTH_DISABLE=1` to opt out explicitly.
- Agent and dashboard control traffic is plain HTTP by default. Use TLS termination if the traffic can cross untrusted networks.

## Manual Agent Installation

### Linux

```bash
sudo apt update
sudo apt install -y iperf3 git python3
sudo git clone https://github.com/IT-BAER/iperf-manager.git /opt/iperf-manager

# optional smoke test before installing the service
sudo LOCALAPPDATA=/etc/iperf-manager python3 /opt/iperf-manager/main_agent.py --host 0.0.0.0 --port 9001

# create the service, config, and firewall rules
sudo bash /opt/iperf-manager/deploy/install-agent-linux.sh
```

### Windows

```powershell
git clone https://github.com/IT-BAER/iperf-manager.git C:\iperf-manager

# optional smoke test before registering the scheduled task
cd C:\iperf-manager
python main_agent.py --host 0.0.0.0 --port 9001

# create the scheduled task, config, and firewall rules
.\deploy\Install-Agent.ps1
```

## Agent Configuration Paths

Default runtime paths:

| Platform | Default config path |
|----------|---------------------|
| Linux | `~/.config/iperf3-agent/config.json` |
| Windows | `%LOCALAPPDATA%\iperf3-agent\config.json` |

Paths used by the deployment scripts:

| Platform | Managed config path |
|----------|---------------------|
| Linux | `/etc/iperf-manager/iperf3-agent/config.json` |
| Windows | `C:\iperf-manager\config\iperf3-agent\config.json` |

Config shape:

```json
{
  "autostart": "5211,5212",
  "bind_host": "0.0.0.0",
  "port": 9001,
  "iperf3_path": "iperf3",
  "advertise_ip": "",
  "api_token": "optional-secret-key"
}
```

Environment overrides:

| Variable | Effect |
|----------|--------|
| `AGENT_API_KEY` | Overrides `api_token` |
| `AGENT_MGMT_IP` | Overrides `advertise_ip` |
| `AGENT_LOGDIR` | Overrides the log directory |

## Verifying an Agent

Linux:

```bash
sudo systemctl status iperf-agent
journalctl -u iperf-agent -f
curl -s http://127.0.0.1:9001/status
```

Windows:

```powershell
Get-ScheduledTask -TaskName "iperf-agent" | Select-Object State
Get-Content C:\iperf-manager\logs\*.log -Tail 50
curl http://127.0.0.1:9001/status
```

If you configured an API token, send it as `X-API-Key`.

## Web Dashboard Service (Linux)

`deploy/setup-web-service.sh` creates the `iperf-web` systemd service for the Flask dashboard.

Typical flow:

```bash
cd /opt/iperf-manager
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cd /opt/iperf-manager/web/frontend
npm install
npm run build

sudo bash /opt/iperf-manager/deploy/setup-web-service.sh
```

If you do not provide dashboard auth settings, the setup script generates a random admin password on a fresh install, stores only its hash in the service, and prints the one-time password in the terminal. On later reruns, if auth settings already exist and you do not pass new ones, the script preserves the existing username and stored hash instead of rotating the password.

To enable built-in dashboard authentication with a password hash:

```bash
AUTH_HASH=$(python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('change-me'))")
sudo DASHBOARD_AUTH_USERNAME=admin DASHBOARD_AUTH_PASSWORD_HASH="$AUTH_HASH" SESSION_COOKIE_SECURE=1 \
  bash /opt/iperf-manager/deploy/setup-web-service.sh
```

Set `SESSION_COOKIE_SECURE=1` when the dashboard is served over HTTPS so browsers only send the session cookie on encrypted requests.

To opt out and run the dashboard without login protection:

```bash
sudo DASHBOARD_AUTH_DISABLE=1 bash /opt/iperf-manager/deploy/setup-web-service.sh
```

The generated service runs:

```bash
/opt/iperf-manager/venv/bin/python main_web.py --host 0.0.0.0 --port 5000
```

The default dashboard port is `5000`. To use another port, rerun either installer with `--port` (for `install-web-linux.sh`) or set `WEB_PORT` when calling `setup-web-service.sh` directly.

Verify it with:

```bash
sudo systemctl status iperf-web
curl -I http://127.0.0.1:5000
```

Do not expose the dashboard directly to untrusted networks without authentication and TLS in front of it. Built-in auth protects the app session, but HTTPS is still required for untrusted networks.

## Network Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 9001 | TCP | Agent REST API |
| 9999 | UDP | Agent discovery |
| 5211 | TCP and UDP | Default iperf3 server port |
| 5212 | TCP and UDP | Default secondary iperf3 server port |
| 5000 | TCP | Web dashboard |

The iperf3 port range is configurable.

## Uninstall

Linux agent:

```bash
sudo bash /opt/iperf-manager/deploy/install-agent-linux.sh --uninstall
```

Add `--purge` if you also want to remove `/opt/iperf-manager`.

Windows agent:

```powershell
& C:\iperf-manager\deploy\Install-Agent.ps1 -Uninstall
```

## Troubleshooting

| Issue | Check |
|-------|-------|
| Agent not discovered | Confirm UDP 9999 is open and agents are on the same network segment |
| Agent API unreachable | Check `iperf-agent` status and firewall rules for TCP 9001 |
| `iperf-agent` exits with `226/NAMESPACE` | Rerun the updated Linux installer, or verify `/opt/iperf-manager/data` exists for the systemd `ReadWritePaths` policy |
| Tests fail to start | Confirm `iperf3` is installed and the iperf3 ports are open between agents |
| Web dashboard unavailable | Check `iperf-web` status and verify the frontend was built into `web/frontend/dist/` |
| Config changes not applied | Restart the affected service after editing its config |
