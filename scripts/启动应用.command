#!/bin/bash

# 量化交易策略分析器 - 启动脚本 (macOS/Linux)
# 双击此文件即可启动应用

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  量化交易策略分析器"
echo "  启动中..."
echo "=========================================="
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null
then
    echo "❌ 错误：未找到 Python3"
    echo "请先安装 Python 3.8 或更高版本"
    echo "下载地址：https://www.python.org/downloads/"
    read -p "按任意键退出..."
    exit 1
fi

echo "✓ Python 版本："
python3 --version
echo ""

# 检查依赖是否安装
echo "检查依赖..."
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "⚠️  首次运行，需要安装依赖包..."
    echo "这可能需要几分钟时间..."
    pip3 install -r requirements.txt
    
    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败"
        read -p "按任意键退出..."
        exit 1
    fi
    echo "✓ 依赖安装完成"
fi

# 启动应用
echo ""
echo "=========================================="
echo "✓ 启动成功！"
echo "=========================================="
echo ""
echo "应用地址："
echo "  本地访问：http://localhost:8501"
echo "  网络访问：http://$(hostname -I 2>/dev/null | awk '{print $1}'):8501"
echo ""
echo "⚠️  关闭此窗口将停止应用"
echo "=========================================="
echo ""

# 启动 Streamlit
streamlit run app.py

# 如果出错，暂停以便查看错误信息
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 应用启动失败"
    read -p "按任意键退出..."
fi
