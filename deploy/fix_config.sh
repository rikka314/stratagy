#!/bin/bash
# 写入正确的 Streamlit 配置
mkdir -p /opt/stratagy/.streamlit
cat > /opt/stratagy/.streamlit/config.toml << 'EOF'
[server]
headless = true
port = 8501
address = "0.0.0.0"
maxUploadSize = 50

[browser]
gatherUsageStats = false
EOF

echo "Config written:"
cat /opt/stratagy/.streamlit/config.toml

# 重启服务
systemctl restart stratagy
sleep 3

# 检查状态
echo ""
echo "=== Service Status ==="
systemctl is-active stratagy

echo ""
echo "=== Port Check ==="
ss -tlnp | grep 8501

echo ""
echo "FIXCONFIG_DONE"
