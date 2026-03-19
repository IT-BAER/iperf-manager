# iperf-manager Deployment Guide

This repository ships three deployment helpers:

- `deploy/install-agent-linux.sh` for Linux agents (`iperf-agent` systemd service)
- `deploy/Install-Agent.ps1` for Windows agents (`iperf-agent` scheduled task)
- `deploy/setup-web-service.sh` for the Linux web dashboard (`iperf-web` systemd service)

## Agent Quick Start

### Linux agent (Debian, Ubuntu, Proxmox)

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh | sudo bash
```

With parameters:

```bash
curl -fsSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh \
  | sudo bash -s -- --token "mySecretKey" --port 9001 --iperf-ports "5211,5212"
```

### Windows agent (PowerShell as Administrator)

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr -useb https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/Install-Agent.ps1 -OutFile $env:TEMP\Install-Agent.ps1
& $env:TEMP\Install-Agent.ps1
```

With parameters:

```powershell
& $env:TEMP\Install-Agent.ps1 -Token "mySecretKey" -Port 9001 -IperfPorts "5211,5212"
```

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

The generated service runs:

```bash
/opt/iperf-manager/venv/bin/python main_web.py --host 0.0.0.0 --port 5000
```

Verify it with:

```bash
sudo systemctl status iperf-web
curl -I http://127.0.0.1:5000
```

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

Windows agent:

```powershell
& C:\iperf-manager\deploy\Install-Agent.ps1 -Uninstall
```

## Troubleshooting

| Issue | Check |
|-------|-------|
| Agent not discovered | Confirm UDP 9999 is open and agents are on the same network segment |
| Agent API unreachable | Check `iperf-agent` status and firewall rules for TCP 9001 |
| Tests fail to start | Confirm `iperf3` is installed and the iperf3 ports are open between agents |
| Web dashboard unavailable | Check `iperf-web` status and verify the frontend was built into `web/frontend/dist/` |
| Config changes not applied | Restart the affected service after editing its config |
