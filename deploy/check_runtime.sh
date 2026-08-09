#!/bin/bash

set -euo pipefail

APP_DIR="${1:-/opt/stratagy}"
HEALTH_URL="${2:-http://127.0.0.1:8501/strategy/_stcore/health}"
ATTEMPTS="${STRATAGY_HEALTH_ATTEMPTS:-20}"

if [ ! -x "${APP_DIR}/venv/bin/python" ]; then
    echo "[runtime] missing Python runtime: ${APP_DIR}/venv/bin/python" >&2
    exit 1
fi

echo "[runtime] installed versions"
"${APP_DIR}/venv/bin/python" --version
"${APP_DIR}/venv/bin/python" -c 'import streamlit; print(f"Streamlit {streamlit.__version__}")'

attempt=1
while [ "${attempt}" -le "${ATTEMPTS}" ]; do
    if response="$(curl --fail --silent --show-error --max-time 2 "${HEALTH_URL}" 2>/dev/null)"; then
        echo "[runtime] health check passed: ${HEALTH_URL} (${response})"
        exit 0
    fi
    sleep 1
    attempt=$((attempt + 1))
done

echo "[runtime] health check failed after ${ATTEMPTS} attempts: ${HEALTH_URL}" >&2
systemctl status stratagy --no-pager >&2 || true
exit 1
