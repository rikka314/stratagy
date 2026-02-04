@echo off
chcp 65001 >nul
REM 量化交易策略分析器 - 启动脚本 (Windows)
REM 双击此文件即可启动应用

echo ==========================================
echo   量化交易策略分析器
echo   启动中...
echo ==========================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到 Python
    echo 请先安装 Python 3.8 或更高版本
    echo 下载地址：https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo ✓ Python 版本：
python --version
echo.

REM 检查依赖是否安装
echo 检查依赖...
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  首次运行，需要安装依赖包...
    echo 这可能需要几分钟时间...
    pip install -r requirements.txt
    
    if errorlevel 1 (
        echo ❌ 依赖安装失败
        pause
        exit /b 1
    )
    echo ✓ 依赖安装完成
)

REM 启动应用
echo.
echo ==========================================
echo ✓ 启动成功！
echo ==========================================
echo.
echo 应用地址：
echo   本地访问：http://localhost:8501
echo.
echo ⚠️  关闭此窗口将停止应用
echo ==========================================
echo.

REM 启动 Streamlit
streamlit run app.py

REM 如果出错，暂停以便查看错误信息
if errorlevel 1 (
    echo.
    echo ❌ 应用启动失败
    pause
)
