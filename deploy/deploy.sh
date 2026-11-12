#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${STRATAGY_APP_DIR:-/opt/stratagy}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "${SCRIPT_DIR}")"

echo "[deploy] installing system packages"
apt-get update -y
apt-get install -y python3 python3-pip python3-venv curl ufw

mkdir -p "${APP_DIR}" "${APP_DIR}/data" "${APP_DIR}/model-test/outputs" "${APP_DIR}/reports"

source_real="$(readlink -f "${SOURCE_DIR}")"
app_real="$(readlink -f "${APP_DIR}")"
if [ "${source_real}" != "${app_real}" ]; then
    echo "[deploy] copying uploaded application into ${APP_DIR}"
    cp -f "${SOURCE_DIR}/requirements.txt" "${APP_DIR}/"
    mkdir -p "${APP_DIR}/api" "${APP_DIR}/core" "${APP_DIR}/ui" "${APP_DIR}/frontend" "${APP_DIR}/deploy"
    cp -rf "${SOURCE_DIR}/api/"*.py "${APP_DIR}/api/"
    cp -rf "${SOURCE_DIR}/core/"*.py "${APP_DIR}/core/"
    cp -rf "${SOURCE_DIR}/ui/"*.py "${APP_DIR}/ui/" 2>/dev/null || true
    rm -rf "${APP_DIR}/frontend/dist"
    cp -rf "${SOURCE_DIR}/frontend/dist" "${APP_DIR}/frontend/"
    cp -rf "${SOURCE_DIR}/core/catalogs" "${APP_DIR}/core/" 2>/dev/null || true
    cp -rf "${SOURCE_DIR}/data/"* "${APP_DIR}/data/" 2>/dev/null || true
    cp -rf "${SOURCE_DIR}/model-test/outputs" "${APP_DIR}/model-test/" 2>/dev/null || true
    cp -rf "${SOURCE_DIR}/reports/"*.html "${APP_DIR}/reports/" 2>/dev/null || true
    cp -f "${SOURCE_DIR}/deploy/"*.sh "${SOURCE_DIR}/deploy/nginx_strategy.conf" "${APP_DIR}/deploy/"
fi

if [ ! -f "${APP_DIR}/api/main.py" ] || [ ! -f "${APP_DIR}/frontend/dist/index.html" ]; then
    echo "[deploy] api/main.py and frontend/dist/index.html are required" >&2
    exit 1
fi

if [ ! -x "${APP_DIR}/venv/bin/python" ]; then
    python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"
sha256sum "${APP_DIR}/requirements.txt" | awk '{print $1}' > "${APP_DIR}/venv/.requirements.sha256"

cat > /etc/systemd/system/stratagy.service <<EOF
[Unit]
Description=Stratagy JavaScript frontend and Python API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=${APP_DIR}/venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable stratagy.service
systemctl restart stratagy.service
chmod +x "${APP_DIR}/deploy/check_runtime.sh"
"${APP_DIR}/deploy/check_runtime.sh" "${APP_DIR}"

ufw allow 22/tcp
ufw --force enable

echo "[deploy] complete: merge ${APP_DIR}/deploy/nginx_strategy.conf into the site vhost"
echo "[deploy] public URL: https://www.gfm156.com/strategy/"
