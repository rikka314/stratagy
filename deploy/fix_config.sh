#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${STRATAGY_APP_DIR:-/opt/stratagy}"
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
systemctl restart stratagy
"${APP_DIR}/deploy/check_runtime.sh" "${APP_DIR}"
