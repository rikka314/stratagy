#!/bin/bash
# ============================================================
# 量化交易策略分析应用 - 服务器一键部署脚本
# 适用于 Ubuntu 24.04 LTS (火山引擎 ECS)
# ============================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  量化交易策略分析应用 - 服务器部署脚本${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ===== 1. 系统更新和基础依赖 =====
echo -e "${YELLOW}[1/6] 更新系统包并安装基础依赖...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git curl ufw

echo -e "${GREEN}✓ 系统依赖安装完成${NC}"

# ===== 2. 创建项目目录 =====
echo -e "${YELLOW}[2/6] 创建项目目录...${NC}"
APP_DIR="/opt/stratagy"
mkdir -p ${APP_DIR}
mkdir -p ${APP_DIR}/data
mkdir -p ${APP_DIR}/model-test

# 如果脚本在项目目录中运行，复制文件
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
APP_REAL_DIR="$(readlink -f "${APP_DIR}")"
PARENT_REAL_DIR="$(readlink -f "${PARENT_DIR}")"
SCRIPT_REAL_DIR="$(readlink -f "${SCRIPT_DIR}")"

if [ -f "${PARENT_DIR}/app.py" ] && [ "${PARENT_REAL_DIR}" != "${APP_REAL_DIR}" ]; then
    echo "从 ${PARENT_DIR} 复制项目文件..."
    cp -f "${PARENT_DIR}/app.py" ${APP_DIR}/
    cp -f "${PARENT_DIR}/requirements.txt" ${APP_DIR}/
    # 复制模块化代码
    mkdir -p ${APP_DIR}/core ${APP_DIR}/ui
    cp -rf "${PARENT_DIR}/core/"*.py ${APP_DIR}/core/ 2>/dev/null || true
    cp -rf "${PARENT_DIR}/ui/"*.py ${APP_DIR}/ui/ 2>/dev/null || true
    cp -rf "${PARENT_DIR}/data/"* ${APP_DIR}/data/ 2>/dev/null || true
    cp -rf "${PARENT_DIR}/model-test/outputs" ${APP_DIR}/model-test/ 2>/dev/null || true
elif [ -f "${SCRIPT_DIR}/app.py" ] && [ "${SCRIPT_REAL_DIR}" != "${APP_REAL_DIR}" ]; then
    echo "从 ${SCRIPT_DIR} 复制项目文件..."
    cp -f "${SCRIPT_DIR}/app.py" ${APP_DIR}/
    cp -f "${SCRIPT_DIR}/requirements.txt" ${APP_DIR}/
    mkdir -p ${APP_DIR}/core ${APP_DIR}/ui
    cp -rf "${SCRIPT_DIR}/core/"*.py ${APP_DIR}/core/ 2>/dev/null || true
    cp -rf "${SCRIPT_DIR}/ui/"*.py ${APP_DIR}/ui/ 2>/dev/null || true
    cp -rf "${SCRIPT_DIR}/data/"* ${APP_DIR}/data/ 2>/dev/null || true
    cp -rf "${SCRIPT_DIR}/model-test/outputs" ${APP_DIR}/model-test/ 2>/dev/null || true
else
    # 检查 /opt/stratagy 下是否已有文件
    if [ ! -f "${APP_DIR}/app.py" ]; then
        echo -e "${RED}✗ 未找到 app.py，请先上传项目文件到 ${APP_DIR}${NC}"
        echo "  使用 scp 上传: scp app.py requirements.txt core/ ui/ root@<IP>:${APP_DIR}/"
        echo "  使用 scp 上传数据: scp -r data/ root@<IP>:${APP_DIR}/"
        exit 1
    fi
fi

echo -e "${GREEN}✓ 项目目录准备完成: ${APP_DIR}${NC}"

# ===== 3. 创建 Python 虚拟环境并安装依赖 =====
echo -e "${YELLOW}[3/6] 创建 Python 虚拟环境并安装依赖...${NC}"
cd ${APP_DIR}

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt

# 记录已安装 requirements 指纹，供日常增量同步按需安装。
sha256sum requirements.txt | awk '{print $1}' > "${APP_DIR}/venv/.requirements.sha256"

echo "已安装运行时版本:"
"${APP_DIR}/venv/bin/python" --version
"${APP_DIR}/venv/bin/python" -c 'import streamlit; print(f"Streamlit {streamlit.__version__}")'

echo -e "${GREEN}✓ Python 依赖安装完成${NC}"

# ===== 4. 创建 Streamlit 配置文件 =====
echo -e "${YELLOW}[4/6] 创建 Streamlit 配置...${NC}"
mkdir -p ${APP_DIR}/.streamlit

cat > ${APP_DIR}/.streamlit/config.toml << 'EOF'
[server]
# 监听所有网络接口（允许外部访问）
address = "0.0.0.0"
port = 8501
headless = true
baseUrlPath = "strategy"
maxUploadSize = 50

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#1a56a0"
backgroundColor = "#f5f7fb"
secondaryBackgroundColor = "#edf1f8"
textColor = "#1e2a38"
EOF

echo -e "${GREEN}✓ Streamlit 配置完成${NC}"

# ===== 5. 创建 systemd 服务（开机自启 + 后台运行）=====
echo -e "${YELLOW}[5/6] 配置 systemd 服务...${NC}"

cat > /etc/systemd/system/stratagy.service << EOF
[Unit]
Description=量化交易策略分析应用 (Streamlit)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=${APP_DIR}/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd 配置
systemctl daemon-reload
# 启用开机自启
systemctl enable stratagy.service
# 启动服务
systemctl restart stratagy.service

# 服务必须在受支持的 base path 健康端点上通过检查，部署才算成功。
chmod +x "${APP_DIR}/deploy/check_runtime.sh"
"${APP_DIR}/deploy/check_runtime.sh" "${APP_DIR}"

echo -e "${GREEN}✓ systemd 服务配置完成${NC}"

# ===== 6. 配置防火墙 =====
echo -e "${YELLOW}[6/6] 配置防火墙...${NC}"

# 开放 8501 端口
ufw allow 22/tcp    # SSH
ufw allow 8501/tcp  # Streamlit
ufw --force enable

echo -e "${GREEN}✓ 防火墙配置完成（已开放 22, 8501 端口）${NC}"

# ===== 完成 =====
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}  ✅ 部署完成！${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# 获取公网 IP
PUBLIC_IP=$(curl -s --connect-timeout 5 http://ifconfig.me 2>/dev/null || echo "115.191.68.122")

echo -e "  📊 访问地址: ${GREEN}http://${PUBLIC_IP}:8501/strategy${NC}"
echo -e "  Nginx subpath template: ${YELLOW}${APP_DIR}/deploy/nginx_strategy.conf${NC}"
echo ""
echo -e "  常用命令:"
echo -e "    查看状态:  ${YELLOW}systemctl status stratagy${NC}"
echo -e "    查看日志:  ${YELLOW}journalctl -u stratagy -f${NC}"
echo -e "    重启服务:  ${YELLOW}systemctl restart stratagy${NC}"
echo -e "    停止服务:  ${YELLOW}systemctl stop stratagy${NC}"
echo ""
echo -e "${RED}  ⚠️ 重要提醒：${NC}"
echo -e "  请确保在火山引擎控制台的 ${YELLOW}安全组${NC} 中放通 ${YELLOW}8501${NC} 端口！"
echo -e "  路径: 云服务器 → 安全组 → 入方向规则 → 添加规则"
echo -e "  协议: TCP  端口: 8501  源地址: 0.0.0.0/0"
echo -e "  如需接入 www.gfm156.com/strategy，请把 deploy/nginx_strategy.conf 合并到站点 Nginx 配置后再 reload nginx"
echo ""
