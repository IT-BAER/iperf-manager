#!/usr/bin/env bash
# iperf-manager Web UI bootstrap installer for Debian / Ubuntu / Proxmox
set -euo pipefail

INSTALL_DIR='/opt/iperf-manager'
REPO_URL='https://github.com/IT-BAER/iperf-manager.git'
BRANCH='main'
SERVICE_NAME='iperf-web'
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_PORT=${IPERF_MANAGER_WEB_PORT:-}
SKIP_REPO_SYNC=${IPERF_MANAGER_SKIP_REPO_SYNC:-}
SKIP_FRONTEND_BUILD=${IPERF_MANAGER_SKIP_FRONTEND_BUILD:-}
ACTION='install'
PURGE_ON_UNINSTALL=false
SKIP_REPO_SYNC_FLAG=false
SKIP_FRONTEND_BUILD_FLAG=false

case "${SKIP_REPO_SYNC,,}" in
	1|true|yes|on)
		SKIP_REPO_SYNC_FLAG=true
		;;
esac

case "${SKIP_FRONTEND_BUILD,,}" in
	1|true|yes|on)
		SKIP_FRONTEND_BUILD_FLAG=true
		;;
esac

usage() {
	cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Actions:
  --install                 Install or converge to desired state (default)
  --update                  Alias for --install
  --uninstall               Remove service and firewall rule

Options:
  --purge                   With --uninstall, also remove install directory
  --repo-url <url>          Repository URL (default: ${REPO_URL})
  --branch <name>           Repository branch (default: ${BRANCH})
  --install-dir <path>      Install directory (default: ${INSTALL_DIR})
  --port <port>             Web service port (default: 5000)
  --skip-repo-sync          Use existing local tree without git fetch/reset
  --skip-frontend-build     Skip npm install + npm run build
  -h, --help                Show this help

Examples:
  sudo bash install-web-linux.sh
  sudo bash install-web-linux.sh --update --port 5001
  sudo bash install-web-linux.sh --uninstall
  sudo bash install-web-linux.sh --uninstall --purge
EOF
	exit 0
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--install)
			ACTION='install'
			shift
			;;
		--update)
			ACTION='install'
			shift
			;;
		--uninstall)
			ACTION='uninstall'
			shift
			;;
		--purge)
			PURGE_ON_UNINSTALL=true
			shift
			;;
		--repo-url)
			REPO_URL="$2"
			shift 2
			;;
		--branch)
			BRANCH="$2"
			shift 2
			;;
		--install-dir)
			INSTALL_DIR="$2"
			shift 2
			;;
		--port)
			SERVICE_PORT="$2"
			shift 2
			;;
		--skip-repo-sync)
			SKIP_REPO_SYNC_FLAG=true
			shift
			;;
		--skip-frontend-build)
			SKIP_FRONTEND_BUILD_FLAG=true
			shift
			;;
		-h|--help)
			usage
			;;
		*)
			die "Unknown option: $1 (use --help)"
			;;
	esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR ]${NC}  $*" >&2; }
die()   { err "$@"; exit 1; }

detect_service_port() {
	[[ -f "$SERVICE_FILE" ]] || return 0
	sed -n 's/^ExecStart=.* --port \([0-9][0-9]*\)$/\1/p' "$SERVICE_FILE" | tail -n 1
}

[[ $EUID -eq 0 ]] || die 'This script must be run as root (use sudo).'

if [[ "$ACTION" == 'uninstall' ]]; then
	info 'Uninstalling Web UI service ...'

	if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
		systemctl stop "$SERVICE_NAME"
		ok "Service ${SERVICE_NAME} stopped"
	fi

	if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
		systemctl disable "$SERVICE_NAME"
		ok "Service ${SERVICE_NAME} disabled"
	fi

	if [[ -f "$SERVICE_FILE" ]]; then
		rm -f "$SERVICE_FILE"
		systemctl daemon-reload
		ok 'Systemd unit removed'
	fi

	UNINSTALL_PORT=${SERVICE_PORT:-$(detect_service_port)}
	UNINSTALL_PORT=${UNINSTALL_PORT:-5000}
	if command -v ufw >/dev/null 2>&1 && ufw status | grep -q 'active'; then
		ufw delete allow "${UNINSTALL_PORT}/tcp" >/dev/null 2>&1 || true
		ok "Firewall rule removed for ${UNINSTALL_PORT}/tcp"
	fi

	if $PURGE_ON_UNINSTALL && [[ -d "$INSTALL_DIR" ]]; then
		rm -rf "$INSTALL_DIR"
		ok "Removed ${INSTALL_DIR}"
	fi

	ok 'Web UI uninstall complete'
	exit 0
fi

SERVICE_PORT=${SERVICE_PORT:-5000}

info 'Installing system dependencies (git, python, node/npm if needed) ...'
apt-get update -qq
apt-get install -y -qq git curl ca-certificates python3 python3-venv python3-pip

if ! command -v npm >/dev/null 2>&1; then
	info 'npm not found, installing nodejs and npm ...'
	apt-get install -y -qq nodejs npm
fi

info "Setting up repository in ${INSTALL_DIR} ..."
if $SKIP_REPO_SYNC_FLAG; then
	[[ -f "${INSTALL_DIR}/main_web.py" ]] || die "IPERF_MANAGER_SKIP_REPO_SYNC=1 requires an existing repo checkout in ${INSTALL_DIR}"
	ok "Using existing repository tree in ${INSTALL_DIR} without git sync"
elif [[ -d "${INSTALL_DIR}/.git" ]]; then
	info 'Repository exists - pulling latest changes ...'
	git -C "$INSTALL_DIR" fetch --quiet origin
	git -C "$INSTALL_DIR" reset --hard "origin/${BRANCH}" --quiet 2>/dev/null \
		|| git -C "$INSTALL_DIR" reset --hard origin/master --quiet
	ok 'Repository updated'
else
	rm -rf "$INSTALL_DIR"
	git clone --quiet "$REPO_URL" "$INSTALL_DIR"
	ok "Repository cloned to ${INSTALL_DIR}"
fi

VENV_PY=''
if [[ -x "${INSTALL_DIR}/venv/bin/python" ]]; then
	VENV_PY="${INSTALL_DIR}/venv/bin/python"
else
	info 'Creating Python virtual environment ...'
	python3 -m venv "${INSTALL_DIR}/venv"
	VENV_PY="${INSTALL_DIR}/venv/bin/python"
fi

info 'Installing Python dependencies ...'
"${VENV_PY}" -m pip install --upgrade pip wheel >/dev/null
"${VENV_PY}" -m pip install -r "${INSTALL_DIR}/requirements.txt"
ok 'Python dependencies installed'

if ! $SKIP_FRONTEND_BUILD_FLAG; then
	if [[ -f "${INSTALL_DIR}/web/frontend/package.json" ]]; then
		info 'Building frontend assets ...'
		pushd "${INSTALL_DIR}/web/frontend" >/dev/null
		npm install
		npm run build
		popd >/dev/null
		ok 'Frontend build complete'
	else
		warn 'web/frontend/package.json not found, skipping frontend build'
	fi
else
	warn 'Skipping frontend build because IPERF_MANAGER_SKIP_FRONTEND_BUILD is enabled'
fi

info 'Creating/updating systemd service ...'
WEB_PORT="$SERVICE_PORT" "${INSTALL_DIR}/deploy/setup-web-service.sh"

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q 'active'; then
	ufw allow "${SERVICE_PORT}/tcp" comment 'iperf-manager web dashboard' >/dev/null 2>&1 || true
	ok "Firewall rule ensured for ${SERVICE_PORT}/tcp"
fi

echo ''
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Web UI Installation Complete                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ''
echo -e "  Install directory : ${CYAN}${INSTALL_DIR}${NC}"
echo -e "  Service name      : ${CYAN}${SERVICE_NAME}${NC}"
echo -e "  URL               : ${CYAN}http://<server-ip>:${SERVICE_PORT}${NC}"
echo ''
info 'Verify with: systemctl status iperf-web'
