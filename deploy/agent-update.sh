#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  iperf-manager  ·  Agent updater (Linux)
#  Run by iperf-agent-update.service when the dashboard asks an agent to update.
#  Installs the latest GitHub release with that release's own installer.
#  Manual use as root: agent-update.sh --ref <tag>  (installs that ref even if not newer)
# ──────────────────────────────────────────────────────────────────────
set -Eeuo pipefail
umask 077

INSTALL_DIR="/opt/iperf-manager"
STATE_FILE="/etc/iperf-manager/iperf3-agent/update-state.json"
LOG_FILE="/var/log/iperf-manager/agent-update.log"
RELEASE_API="https://api.github.com/repos/IT-BAER/iperf-manager/releases/latest"
SERVICE_NAME="iperf-agent"
FORCED_REF=""
if [[ "${1:-}" == "--ref" ]]; then
    FORCED_REF="${2:-}"
    [[ "$FORCED_REF" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "invalid ref: ${FORCED_REF}" >&2; exit 2; }
fi

mkdir -p "$(dirname "$LOG_FILE")"
exec >>"$LOG_FILE" 2>&1
echo "=== $(date -Is) agent update start"

INSTALLED="$(python3 -c 'import re, sys; print(re.search(r"AGENT_VERSION = .([0-9.]+).", open(sys.argv[1]).read()).group(1))' \
    "${INSTALL_DIR}/core/constants.py")"
TARGET=""
STARTED="$(date +%s)"

write_state() {  # write_state <state> [error]
    python3 - "$STATE_FILE" "$1" "$INSTALLED" "$TARGET" "$STARTED" "${2:-}" <<'PY'
import json, os, sys, time
path, state, frm, to, started, error = sys.argv[1:7]
data = {'state': state, 'from': frm, 'to': to, 'started': float(started)}
if state not in ('requested', 'running'):
    data['finished'] = time.time()
if error:
    data['error'] = error
with open(path + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(data, f)
os.replace(path + '.tmp', path)
PY
}

on_error() {
    local line="$1"
    trap - ERR
    echo "update failed at line ${line}"
    if [[ -n "${PREVIOUS:-}" ]]; then
        git -C "$INSTALL_DIR" checkout -f -q "$PREVIOUS" || true
        systemctl restart "$SERVICE_NAME" || true
    fi
    write_state failed "update failed at line ${line}, see ${LOG_FILE}"
    exit 1
}
trap 'on_error $LINENO' ERR

if [[ -n "$FORCED_REF" ]]; then
    TARGET="$FORCED_REF"
else
    TARGET="$(curl -fsSL --max-time 30 "$RELEASE_API" \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
    [[ "$TARGET" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "unexpected release tag: '${TARGET}'"; false; }
    NEWEST="$(printf '%s\n%s\n' "$INSTALLED" "${TARGET#v}" | sort -V | tail -n 1)"
    if [[ "$NEWEST" == "$INSTALLED" ]]; then
        echo "installed ${INSTALLED} is current (latest ${TARGET})"
        write_state current
        exit 0
    fi
fi

echo "updating ${INSTALLED} -> ${TARGET}"
write_state running
PREVIOUS="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
git -C "$INSTALL_DIR" fetch --quiet --tags origin
git -C "$INSTALL_DIR" checkout -f -q "tags/${TARGET}" 2>/dev/null \
    || git -C "$INSTALL_DIR" checkout -f -q "origin/${TARGET}"
# The release's own installer runs; the repo is already at the target ref.
IPERF_MANAGER_SKIP_REPO_SYNC=1 bash "${INSTALL_DIR}/deploy/install-agent-linux.sh" --ref "$TARGET"
write_state ok
echo "=== $(date -Is) agent update done (${TARGET})"
