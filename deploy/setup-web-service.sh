#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=iperf-web
SERVICE_FILE=/etc/systemd/system/${SERVICE_NAME}.service
HASH_PYTHON_BIN=python3
DEFAULT_WEB_PORT=5000

if [[ -x /opt/iperf-manager/venv/bin/python ]]; then
	HASH_PYTHON_BIN=/opt/iperf-manager/venv/bin/python
fi

read_service_env() {
	local name="$1"
	[[ -f "$SERVICE_FILE" ]] || return 0
	sed -n "s/^Environment=${name}=//p" "$SERVICE_FILE" | tail -n 1
}

read_service_port() {
	[[ -f "$SERVICE_FILE" ]] || return 0
	sed -n 's/^ExecStart=.* --port \([0-9][0-9]*\)$/\1/p' "$SERVICE_FILE" | tail -n 1
}

env_flag_is_enabled() {
	case "${1,,}" in
		1|true|yes|on)
			return 0
			;;
	esac
	return 1
}

hash_password() {
	local password="$1"
	AUTH_PASSWORD_VALUE="$password" "$HASH_PYTHON_BIN" -c "import os; from werkzeug.security import generate_password_hash; print(generate_password_hash(os.environ['AUTH_PASSWORD_VALUE']), end='')"
}

EXISTING_FLASK_KEY=$(read_service_env FLASK_SECRET)
EXISTING_AUTH_USER=$(read_service_env DASHBOARD_AUTH_USERNAME)
EXISTING_AUTH_PASSWORD=$(read_service_env DASHBOARD_AUTH_PASSWORD)
EXISTING_AUTH_PASSWORD_HASH=$(read_service_env DASHBOARD_AUTH_PASSWORD_HASH)
EXISTING_AUTH_DISABLED=$(read_service_env DASHBOARD_AUTH_DISABLE)
EXISTING_COOKIE_SECURE=$(read_service_env SESSION_COOKIE_SECURE)
EXISTING_WEB_PORT=$(read_service_port)

FLASK_KEY=${EXISTING_FLASK_KEY:-$(python3 -c "import secrets; print(secrets.token_hex(32), end='')")}
AUTH_USER=${DASHBOARD_AUTH_USERNAME:-$EXISTING_AUTH_USER}
AUTH_PASSWORD=${DASHBOARD_AUTH_PASSWORD:-$EXISTING_AUTH_PASSWORD}
AUTH_PASSWORD_HASH=${DASHBOARD_AUTH_PASSWORD_HASH:-$EXISTING_AUTH_PASSWORD_HASH}
AUTH_DISABLED=${DASHBOARD_AUTH_DISABLE:-}
COOKIE_SECURE=${SESSION_COOKIE_SECURE:-$EXISTING_COOKIE_SECURE}
WEB_PORT=${WEB_PORT:-$EXISTING_WEB_PORT}
WEB_PORT=${WEB_PORT:-$DEFAULT_WEB_PORT}
AUTH_DISABLED_FLAG=false
AUTH_GENERATED=false
AUTH_REUSED_EXISTING=false
AUTH_GENERATED_PASSWORD=

AUTH_USER_SET=${DASHBOARD_AUTH_USERNAME+x}
AUTH_PASSWORD_SET=${DASHBOARD_AUTH_PASSWORD+x}
AUTH_PASSWORD_HASH_SET=${DASHBOARD_AUTH_PASSWORD_HASH+x}
AUTH_DISABLED_SET=${DASHBOARD_AUTH_DISABLE+x}

if [[ -n "$AUTH_DISABLED_SET" ]]; then
	if env_flag_is_enabled "$AUTH_DISABLED"; then
		AUTH_DISABLED_FLAG=true
	fi
elif [[ -n "${AUTH_USER_SET}${AUTH_PASSWORD_SET}${AUTH_PASSWORD_HASH_SET}" ]]; then
	AUTH_DISABLED_FLAG=false
elif env_flag_is_enabled "$EXISTING_AUTH_DISABLED"; then
	AUTH_DISABLED_FLAG=true
fi

if ! $AUTH_DISABLED_FLAG; then
	AUTH_USER=${AUTH_USER:-admin}
	if [[ -n "$AUTH_PASSWORD" && -z "$AUTH_PASSWORD_HASH" ]]; then
		AUTH_PASSWORD_HASH=$(hash_password "$AUTH_PASSWORD")
		AUTH_PASSWORD=
	fi
	if [[ -z "$AUTH_PASSWORD_HASH" ]]; then
		AUTH_GENERATED=true
		AUTH_GENERATED_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(18), end='')")
		AUTH_PASSWORD_HASH=$(hash_password "$AUTH_GENERATED_PASSWORD")
	elif [[ -n "$EXISTING_AUTH_PASSWORD_HASH" || -n "$EXISTING_AUTH_PASSWORD" ]] \
		&& [[ -z "${AUTH_USER_SET}${AUTH_PASSWORD_SET}${AUTH_PASSWORD_HASH_SET}${AUTH_DISABLED_SET}" ]]; then
		AUTH_REUSED_EXISTING=true
	fi
fi

cat > "$SERVICE_FILE" <<SVCEOF
[Unit]
Description=iperf-manager Web Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/iperf-manager
ExecStart=/opt/iperf-manager/venv/bin/python main_web.py --host 0.0.0.0 --port ${WEB_PORT}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=iperf-web
Environment=FLASK_SECRET=${FLASK_KEY}
NoNewPrivileges=true
ProtectHome=true
SVCEOF

if $AUTH_DISABLED_FLAG; then
	cat >> "$SERVICE_FILE" <<SVCEOF
Environment=DASHBOARD_AUTH_DISABLE=1
SVCEOF
elif [[ -n "$AUTH_USER" ]]; then
	cat >> "$SERVICE_FILE" <<SVCEOF
Environment=DASHBOARD_AUTH_USERNAME=${AUTH_USER}
SVCEOF
fi

if [[ -n "$AUTH_PASSWORD_HASH" ]]; then
	cat >> "$SERVICE_FILE" <<SVCEOF
Environment=DASHBOARD_AUTH_PASSWORD_HASH=${AUTH_PASSWORD_HASH}
SVCEOF
fi

if [[ -n "$COOKIE_SECURE" ]]; then
	cat >> "$SERVICE_FILE" <<SVCEOF
Environment=SESSION_COOKIE_SECURE=${COOKIE_SECURE}
SVCEOF
fi

cat >> "$SERVICE_FILE" <<SVCEOF

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
echo "${SERVICE_NAME} service created and started"
if $AUTH_DISABLED_FLAG; then
	echo "Dashboard auth : disabled (DASHBOARD_AUTH_DISABLE=1)"
elif $AUTH_GENERATED; then
	echo "Dashboard auth : enabled with generated credentials"
	echo "  Username     : ${AUTH_USER}"
	echo "  Password     : ${AUTH_GENERATED_PASSWORD}"
elif $AUTH_REUSED_EXISTING; then
	echo "Dashboard auth : preserved existing credentials for username ${AUTH_USER}"
else
	echo "Dashboard auth : enabled for username ${AUTH_USER}"
fi
echo "Dashboard port : ${WEB_PORT}"
systemctl --no-pager status "$SERVICE_NAME" || true
