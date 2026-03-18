# iperf-manager Agent — Deployment Guide

## Quick Start

### Linux (Debian / Ubuntu / Proxmox)

One-liner (as root):

```bash
curl -sSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh | sudo bash
```

With an API token:

```bash
curl -sSL https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/install-agent-linux.sh \
  | sudo bash -s -- --token "mySecretKey" --port 9001 --iperf-ports "5211,5212"
```

### Windows (PowerShell — Run as Administrator)

One-liner:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr -useb https://raw.githubusercontent.com/IT-BAER/iperf-manager/main/deploy/Install-Agent.ps1 -OutFile $env:TEMP\Install-Agent.ps1; & $env:TEMP\Install-Agent.ps1
```

With parameters:

```powershell
& $env:TEMP\Install-Agent.ps1 -Token "mySecretKey" -Port 9001 -IperfPorts "5211,5212"
```

---

## Manual Installation

### Linux

```bash
# 1. Install prerequisites
sudo apt update && sudo apt install -y iperf3 git python3

# 2. Clone repository
sudo git clone https://github.com/IT-BAER/iperf-manager.git /opt/iperf-manager

# 3. Create config
sudo mkdir -p /etc/iperf-manager/iperf3-agent
sudo cat > /etc/iperf-manager/iperf3-agent/config.json <<EOF
{
  "autostart": "5211,5212",
  "bind_host": "0.0.0.0",
  "port": 9001,
  "iperf3_path": "iperf3",
  "advertise_ip": "",
  "api_token": ""
}
EOF

# 4. Test headless mode
sudo LOCALAPPDATA=/etc/iperf-manager python3 /opt/iperf-manager/main_agent.py --headless

# 5. Run the installer to create the systemd service automatically
sudo bash /opt/iperf-manager/deploy/install-agent-linux.sh
```

### Windows

```powershell
# 1. Install Python 3.9+ from https://python.org (add to PATH)
# 2. Install Git from https://git-scm.com/download/win

# 3. Clone repository
git clone https://github.com/IT-BAER/iperf-manager.git C:\iperf-manager

# 4. Download iperf3 from https://github.com/ar51an/iperf3-win-builds/releases
#    Extract iperf3.exe + DLLs to C:\iperf-manager\iperf3\

# 5. Test headless mode
cd C:\iperf-manager
python main_agent.py --headless

# 6. Run the installer to register the scheduled task
.\deploy\Install-Agent.ps1
```

---

## Configuration

The agent reads its config from a JSON file. The deployment scripts place it at:

| Platform | Config Path |
|----------|-------------|
| Linux    | `/etc/iperf-manager/iperf3-agent/config.json` |
| Windows  | `C:\iperf-manager\config\iperf3-agent\config.json` |

### Config Keys

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

| Key | Default | Description |
|-----|---------|-------------|
| `autostart` | `"5211,5212"` | Comma-separated iperf3 server ports to start automatically |
| `bind_host` | `"0.0.0.0"` | Network interface to listen on (all interfaces) |
| `port` | `9001` | REST API listen port |
| `iperf3_path` | `"iperf3"` | Path to iperf3 binary (auto-detected if on PATH) |
| `advertise_ip` | `""` | IP advertised to dashboard (empty = auto-detect) |
| `api_token` | `""` | Optional API key for `X-API-Key` header authentication |

### Environment Variables

| Variable | Effect |
|----------|--------|
| `AGENT_API_KEY` | Overrides `api_token` in config |
| `AGENT_MGMT_IP` | Overrides `advertise_ip` for discovery |
| `AGENT_LOGDIR` | Custom log directory (Linux: `/var/log/iperf-manager`) |

### Connecting to the Dashboard

In the iperf-manager Dashboard, add agents by their IP and port:

```
http://<agent-ip>:9001
```

If you configured an API token, enter it in the dashboard's agent settings.

---

## Verifying the Agent

### Check service status

**Linux:**
```bash
sudo systemctl status iperf-agent
journalctl -u iperf-agent -f    # live logs
```

**Windows:**
```powershell
Get-ScheduledTask -TaskName "iperf-agent" | Select-Object State
Get-Content C:\iperf-manager\logs\*.log -Tail 50    # recent logs
```

### Test the REST API

```bash
# Health check
curl -s http://localhost:9001/status

# With API token
curl -s -H "X-API-Key: mySecretKey" http://localhost:9001/status
```

Expected response:
```json
{
  "agent_version": "6.0.2",
  "hostname": "server-01",
  "servers": {"5211": "running", "5212": "running"},
  "uptime": 3600
}
```

---

## Network Ports

| Port | Protocol | Purpose | Direction |
|------|----------|---------|-----------|
| 9001 | TCP | Agent REST API | Dashboard → Agent |
| 9999 | UDP | Agent auto-discovery | Dashboard ↔ Agents (broadcast) |
| 5211 | TCP+UDP | iperf3 server (slot 1) | Agent ↔ Agent |
| 5212 | TCP+UDP | iperf3 server (slot 2) | Agent ↔ Agent |

> **Note:** iperf3 ports are configurable. The values above are defaults.

---

## Architecture

```
 ┌─────────────────────────────────────┐
 │         Web Dashboard                │
 │           (main_web.py)             │
 └──────────┬──────────────────┬───────┘
            │ :9001/tcp REST   │ :9999/udp
            │ API calls        │ discovery
            ▼                  ▼
 ┌──────────────────┐   ┌──────────────────┐
 │   Agent Node A   │   │   Agent Node B   │
 │  (iperf-agent)   │   │  (iperf-agent)   │
 │                  │   │                  │
 │  :9001  REST API │   │  :9001  REST API │
 │  :5211  iperf3   │◄─►│  :5211  iperf3   │
 │  :5212  iperf3   │   │  :5212  iperf3   │
 └──────────────────┘   └──────────────────┘
        ▲                       ▲
        │  :5211-5212 tcp/udp   │
        └───── iperf3 traffic ──┘

 Flow:
 1. Dashboard discovers agents via UDP broadcast (:9999)
 2. Dashboard sends test commands via REST API (:9001)
 3. Agents start iperf3 server/client on configured ports
 4. Test results stream back to dashboard via REST polling
```

---

## Uninstall

### Linux

```bash
sudo bash /opt/iperf-manager/deploy/install-agent-linux.sh --uninstall
```

This removes: systemd service, `/opt/iperf-manager`, `/etc/iperf-manager`, `/var/log/iperf-manager`, and ufw rules.

### Windows (Run as Administrator)

```powershell
& C:\iperf-manager\deploy\Install-Agent.ps1 -Uninstall
```

This removes: scheduled task, `C:\iperf-manager`, and firewall rules.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `curl: Connection refused` on :9001 | Check service is running, verify firewall allows port |
| Agent not discovered by dashboard | Ensure UDP 9999 is open, agents are on same subnet |
| iperf3 tests fail | Verify iperf3 ports (5211-5212) are open on both agents |
| Python not found (Windows) | Reinstall Python with "Add to PATH" checked |
| Permission denied (Linux) | Run installer with `sudo` |
| Config changes not applied | Restart service: `systemctl restart iperf-agent` |
