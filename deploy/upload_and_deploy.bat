@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   量化策略应用 - Windows 一键上传部署脚本
echo ============================================
echo.

:: ===== 配置区域 =====
set SERVER_IP=115.191.68.122
set SERVER_USER=root
set REMOTE_DIR=/opt/stratagy
set DEPLOY_SCRIPT=/opt/stratagy/deploy/deploy.sh

:: 获取项目根目录（脚本所在目录的上一级）
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%\..") do set PROJECT_DIR=%%~fI

echo [信息] 项目目录: %PROJECT_DIR%
echo [信息] 服务器: %SERVER_USER%@%SERVER_IP%
echo [信息] 远程目录: %REMOTE_DIR%
echo.

:: ===== 检查 SSH =====
where ssh >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 ssh 命令。请安装 OpenSSH 客户端。
    echo   Windows 10+: 设置 - 应用 - 可选功能 - 添加 OpenSSH 客户端
    pause
    exit /b 1
)

:: ===== 提示密码 =====
echo ============================================
echo   即将开始上传文件到服务器
echo   过程中可能需要多次输入服务器密码
echo   建议配置 SSH 密钥免密登录
echo ============================================
echo.
pause

:: ===== Step 1: 在服务器上创建目录 =====
echo.
echo [1/5] 创建远程目录...
ssh %SERVER_USER%@%SERVER_IP% "mkdir -p %REMOTE_DIR%/data %REMOTE_DIR%/deploy %REMOTE_DIR%/core %REMOTE_DIR%/ui"

:: ===== Step 2: 上传核心文件 =====
echo.
echo [2/5] 上传核心文件...
scp "%PROJECT_DIR%\app.py" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/
scp "%PROJECT_DIR%\requirements.txt" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/

:: ===== Step 3: 上传模块化代码 =====
echo.
echo [3/5] 上传 core/ 和 ui/ 模块...
scp "%PROJECT_DIR%\core\*.py" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/core/
scp "%PROJECT_DIR%\ui\*.py" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/ui/

:: ===== Step 4: 上传数据文件 =====
echo.
echo [4/5] 上传数据文件...
scp "%PROJECT_DIR%\data\*.csv" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/data/

:: ===== Step 5: 上传部署脚本并执行 =====
echo.
echo [5/5] 上传并执行部署脚本...
scp "%PROJECT_DIR%\deploy\deploy.sh" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/deploy/
ssh %SERVER_USER%@%SERVER_IP% "chmod +x %REMOTE_DIR%/deploy/deploy.sh && bash %REMOTE_DIR%/deploy/deploy.sh"

echo.
echo ============================================
echo   部署完成！
echo   访问地址: http://%SERVER_IP%:8501
echo ============================================
echo.
echo   ⚠️  记得在火山引擎安全组中开放 8501 端口！
echo.
pause
