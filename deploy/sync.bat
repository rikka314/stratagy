@echo off
chcp 65001 >nul
:: ================================================
:: 一键同步本地代码到服务器并重启
:: 用法: 双击运行，或命令行: sync.bat
:: ================================================

set SERVER=stratagy
set REMOTE_DIR=/opt/stratagy

echo [同步] 正在上传代码到服务器...

:: 获取项目根目录
for %%I in ("%~dp0\..") do set PROJECT_DIR=%%~fI

:: 上传核心文件
scp "%PROJECT_DIR%\app.py" %SERVER%:%REMOTE_DIR%/
scp "%PROJECT_DIR%\requirements.txt" %SERVER%:%REMOTE_DIR%/

:: 上传模块化代码
echo [同步] 上传 core/ 模块...
ssh %SERVER% "mkdir -p %REMOTE_DIR%/core %REMOTE_DIR%/ui"
scp "%PROJECT_DIR%\core\*.py" %SERVER%:%REMOTE_DIR%/core/
echo [同步] 上传 ui/ 模块...
scp "%PROJECT_DIR%\ui\*.py" %SERVER%:%REMOTE_DIR%/ui/

:: 上传数据文件（如有更新）
scp "%PROJECT_DIR%\data\*.csv" %SERVER%:%REMOTE_DIR%/data/

:: 重启服务
echo [重启] 正在重启 Streamlit 服务...
ssh %SERVER% "systemctl restart stratagy && sleep 2 && systemctl is-active stratagy"

echo.
echo ✅ 同步完成！访问: http://115.191.68.122:8501
pause
