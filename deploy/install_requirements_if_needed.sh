#!/bin/bash

set -euo pipefail

APP_DIR="${1:-/opt/stratagy}"
VENV_DIR="${APP_DIR}/venv"
REQUIREMENTS_FILE="${APP_DIR}/requirements.txt"
HASH_FILE="${VENV_DIR}/.requirements.sha256"

if [ ! -f "${REQUIREMENTS_FILE}" ]; then
    echo "[requirements] missing file: ${REQUIREMENTS_FILE}" >&2
    exit 1
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
    echo "[requirements] missing virtual environment: ${VENV_DIR}" >&2
    echo "[requirements] run deploy/deploy.sh for a full bootstrap" >&2
    exit 1
fi

requirements_hash="$(sha256sum "${REQUIREMENTS_FILE}" | awk '{print $1}')"
installed_hash=""
if [ -f "${HASH_FILE}" ]; then
    installed_hash="$(tr -d '\r\n' < "${HASH_FILE}")"
fi

if [ "${requirements_hash}" = "${installed_hash}" ]; then
    echo "[requirements] unchanged; skipping pip install"
else
    echo "[requirements] changed; installing dependencies"
    "${VENV_DIR}/bin/python" -m pip install -r "${REQUIREMENTS_FILE}"
    temporary_hash_file="${HASH_FILE}.tmp.$$"
    printf '%s\n' "${requirements_hash}" > "${temporary_hash_file}"
    mv -f "${temporary_hash_file}" "${HASH_FILE}"
    echo "[requirements] dependency fingerprint updated"
fi

"${VENV_DIR}/bin/python" --version
"${VENV_DIR}/bin/python" -c 'import streamlit; print(f"Streamlit {streamlit.__version__}")'
