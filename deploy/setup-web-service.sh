#!/usr/bin/env bash
set -euo pipefail

# Generate a random Flask secret key
FLASK_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32), end='')")

cat > /etc/systemd/system/iperf-web.service << SVCEOF
[Unit]
Description=iperf-manager Web Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/iperf-manager
ExecStart=/opt/iperf-manager/venv/bin/python main_web.py --host 0.0.0.0 --port 5000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=iperf-web
Environment=FLASK_SECRET=${FLASK_KEY}
NoNewPrivileges=true
ProtectHome=true

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable iperf-web
systemctl restart iperf-web
echo "iperf-web service created and started"
systemctl --no-pager status iperf-web || true
