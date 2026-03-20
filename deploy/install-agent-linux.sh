#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  iperf-manager  ·  Agent Deployment Script for Debian / Ubuntu / Proxmox
#  Idempotent – safe to re-run.  Use --uninstall to remove everything.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
API_TOKEN=""
API_PORT=9001
IPERF_PORTS="5211,5212"
INSTALL_DIR="/opt/iperf-manager"
CONFIG_DIR="/etc/iperf-manager"
LOG_DIR="/var/log/iperf-manager"
SERVICE_NAME="iperf-agent"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
REPO_URL="https://github.com/IT-BAER/iperf-manager.git"
UNINSTALL=false
TOKEN_GENERATED=false
SKIP_REPO_SYNC=${IPERF_MANAGER_SKIP_REPO_SYNC:-}
SKIP_REPO_SYNC_FLAG=false

case "${SKIP_REPO_SYNC,,}" in
    1|true|yes|on)
        SKIP_REPO_SYNC_FLAG=true
        ;;
esac

# ── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR ]${NC}  $*" >&2; }
die()   { err "$@"; exit 1; }

# ── Argument Parsing ─────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --token <api_key>          API key for agent authentication
  --port <port>              REST API port (default: 9001)
  --iperf-ports <p1,p2,...>  iperf3 autostart ports (default: 5211,5212)
  --uninstall                Remove agent, service, config and firewall rules
  -h, --help                 Show this help

Examples:
  sudo bash install-agent-linux.sh
  sudo bash install-agent-linux.sh --token mySecretKey --port 9001
  sudo bash install-agent-linux.sh --uninstall
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)       API_TOKEN="$2";   shift 2 ;;
        --port)        API_PORT="$2";    shift 2 ;;
        --iperf-ports) IPERF_PORTS="$2"; shift 2 ;;
        --uninstall)   UNINSTALL=true;   shift   ;;
        -h|--help)     usage ;;
        *) die "Unknown option: $1  (use --help)" ;;
    esac
done

# ── Root Check ───────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "This script must be run as root (use sudo)."

# ══════════════════════════════════════════════════════════════════════
#  UNINSTALL
# ══════════════════════════════════════════════════════════════════════
if $UNINSTALL; then
    echo ""
    info "Uninstalling iperf-manager agent …"

    # Stop & disable service
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl stop "$SERVICE_NAME" && ok "Service stopped"
    fi
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl disable "$SERVICE_NAME" && ok "Service disabled"
    fi

    # Remove unit file
    if [[ -f "$SERVICE_FILE" ]]; then
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        ok "Systemd unit removed"
    fi

    # Remove firewall rules (ufw)
    if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
        ufw delete allow "$API_PORT/tcp"   2>/dev/null && ok "Removed ufw rule ${API_PORT}/tcp"   || true
        ufw delete allow 9999/udp          2>/dev/null && ok "Removed ufw rule 9999/udp"          || true
        IFS=',' read -ra PORTS <<< "$IPERF_PORTS"
        for p in "${PORTS[@]}"; do
            p=$(echo "$p" | xargs)
            ufw delete allow "${p}/tcp" 2>/dev/null || true
            ufw delete allow "${p}/udp" 2>/dev/null || true
        done
        ok "Removed ufw iperf3 port rules"
    fi

    # Remove directories (prompt for confirmation)
    for dir in "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR"; do
        if [[ -d "$dir" ]]; then
            rm -rf "$dir"
            ok "Removed $dir"
        fi
    done

    echo ""
    ok "iperf-manager agent uninstalled successfully."
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════
#  INSTALL / UPDATE
# ══════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   iperf-manager Agent Installer (Linux)             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Install iperf3 ────────────────────────────────────────────────
info "Checking iperf3 …"
if command -v iperf3 &>/dev/null; then
    ok "iperf3 already installed: $(iperf3 --version 2>&1 | head -1)"
else
    info "Installing iperf3 via apt …"
    apt-get update -qq
    apt-get install -y -qq iperf3
    ok "iperf3 installed: $(iperf3 --version 2>&1 | head -1)"
fi

# ── 2. Check Python 3.9+ ────────────────────────────────────────────
info "Checking Python …"
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        PY_VER=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [[ "$PY_MAJOR" -ge 3 ]] && [[ "$PY_MINOR" -ge 9 ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    die "Python 3.9+ is required but not found. Install with: apt install python3"
fi
ok "Python found: $PYTHON_BIN ($PY_VER)"

if [[ -z "$API_TOKEN" ]]; then
    API_TOKEN=$($PYTHON_BIN -c 'import secrets; print(secrets.token_hex(32))')
    TOKEN_GENERATED=true
    ok "Generated API token automatically"
fi

# ── 3. Clone or update repository ───────────────────────────────────
info "Setting up repository in ${INSTALL_DIR} …"
if $SKIP_REPO_SYNC_FLAG; then
    [[ -f "${INSTALL_DIR}/main_agent.py" ]] || die "IPERF_MANAGER_SKIP_REPO_SYNC=1 requires an existing repo checkout in ${INSTALL_DIR}"
    ok "Using existing repository tree in ${INSTALL_DIR} without git sync"
elif [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Repository exists – pulling latest changes …"
    git -C "$INSTALL_DIR" fetch --quiet origin
    git -C "$INSTALL_DIR" reset --hard origin/main --quiet 2>/dev/null \
        || git -C "$INSTALL_DIR" reset --hard origin/master --quiet
    ok "Repository updated"
else
    # Install git if missing
    if ! command -v git &>/dev/null; then
        info "Installing git …"
        apt-get install -y -qq git
    fi
    rm -rf "$INSTALL_DIR"
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    ok "Repository cloned to ${INSTALL_DIR}"
fi

# ── 4. Create config directory & file ────────────────────────────────
info "Writing configuration …"
mkdir -p "${CONFIG_DIR}/iperf3-agent"
mkdir -p "${LOG_DIR}"
mkdir -p "${INSTALL_DIR}/data"

# The agent reads config from $LOCALAPPDATA/iperf3-agent/config.json
# We set LOCALAPPDATA=/etc/iperf-manager in the service unit so the
# config resolves to /etc/iperf-manager/iperf3-agent/config.json
CONFIG_FILE="${CONFIG_DIR}/iperf3-agent/config.json"

cat > "$CONFIG_FILE" <<CFGEOF
{
  "autostart": "${IPERF_PORTS}",
  "bind_host": "0.0.0.0",
  "port": ${API_PORT},
  "iperf3_path": "iperf3",
  "advertise_ip": "",
  "api_token": "${API_TOKEN}"
}
CFGEOF

chmod 600 "$CONFIG_FILE"
ok "Config written to ${CONFIG_FILE}"

# ── 5. Create systemd service ───────────────────────────────────────
info "Creating systemd service …"

# Stop existing service if running (for idempotent re-runs)
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
fi

cat > "$SERVICE_FILE" <<SVCEOF
[Unit]
Description=iperf-manager Agent (headless)
Documentation=https://github.com/IT-BAER/iperf-manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PYTHON_BIN} main_agent.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Config & log directory overrides
Environment="LOCALAPPDATA=${CONFIG_DIR}"
Environment="AGENT_LOGDIR=${LOG_DIR}"
SVCEOF

# Inject API key as env var if provided
if [[ -n "$API_TOKEN" ]]; then
    cat >> "$SERVICE_FILE" <<TOKEOF
Environment="AGENT_API_KEY=${API_TOKEN}"
TOKEOF
fi

cat >> "$SERVICE_FILE" <<TAILEOF

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${CONFIG_DIR} ${LOG_DIR} ${INSTALL_DIR}/data /tmp
ProtectHome=true

[Install]
WantedBy=multi-user.target
TAILEOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" --quiet
systemctl start "$SERVICE_NAME"
ok "Service ${SERVICE_NAME} enabled and started"

# ── 6. Firewall (ufw) ───────────────────────────────────────────────
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    info "Configuring ufw firewall rules …"
    ufw allow "${API_PORT}/tcp"  comment "iperf-manager API" >/dev/null 2>&1 || true
    ufw allow 9999/udp           comment "iperf-manager discovery" >/dev/null 2>&1 || true
    IFS=',' read -ra PORTS <<< "$IPERF_PORTS"
    for p in "${PORTS[@]}"; do
        p=$(echo "$p" | xargs)
        ufw allow "${p}/tcp" comment "iperf3 server" >/dev/null 2>&1 || true
        ufw allow "${p}/udp" comment "iperf3 server" >/dev/null 2>&1 || true
    done
    ok "Firewall rules added"
else
    info "ufw not active – skipping firewall configuration"
fi

# ── 7. Summary ───────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Installation Complete                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Install directory : ${CYAN}${INSTALL_DIR}${NC}"
echo -e "  Config file       : ${CYAN}${CONFIG_FILE}${NC}"
echo -e "  Log directory     : ${CYAN}${LOG_DIR}${NC}"
echo -e "  Service name      : ${CYAN}${SERVICE_NAME}${NC}"
echo -e "  API port          : ${CYAN}${API_PORT}/tcp${NC}"
echo -e "  Discovery port    : ${CYAN}9999/udp${NC}"
echo -e "  iperf3 ports      : ${CYAN}${IPERF_PORTS}${NC}"
if $TOKEN_GENERATED; then
    echo -e "  API token         : ${YELLOW}${API_TOKEN}${NC}"
    echo -e "  Token source      : ${YELLOW}generated automatically${NC}"
else
    echo -e "  API token         : ${CYAN}(provided)${NC}"
fi
echo ""

if $TOKEN_GENERATED; then
    warn "Save this token now. Use it when manually adding the agent in the dashboard so the server can refresh and control the agent securely."
fi

# Show service status
info "Service status:"
systemctl --no-pager status "$SERVICE_NAME" || true
echo ""
info "Verify with: curl -s http://localhost:${API_PORT}/status"
echo ""
