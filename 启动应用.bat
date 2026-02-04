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

REM 检查虚拟环境
if exist ".venv\Scripts\activate.bat" (
    echo ✓ 检测到虚拟环境
    echo 正在激活虚拟环境...
    call .venv\Scripts\activate.bat
    if errorlevel 1 (
        echo ❌ 虚拟环境激活失败
        echo 请先运行"一键安装.bat"
        pause
        exit /b 1
    )
    echo ✓ 虚拟环境已激活
) else (
    echo ⚠️  未找到虚拟环境
    echo 请先双击运行"一键安装.bat"进行初始化
    echo.
    pause
    exit /b 1
)
echo.

REM 检查依赖是否安装
echo 检查依赖...
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo ❌ 依赖未正确安装
    echo 请运行"一键安装.bat"重新安装
    pause
    exit /b 1
)
echo ✓ 依赖检查通过

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
    echo 请检查上方错误信息
    echo.
    pause
    exit /b 1
)

REM 正常退出时也暂停（避免闪退）
echo.
echo 应用已关闭
pause
