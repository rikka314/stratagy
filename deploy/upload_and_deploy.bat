@echo off
setlocal EnableExtensions

set "SERVER_USER=root"
set "SERVER_HOST=115.191.68.122"
set "SERVER=%SERVER_USER%@%SERVER_HOST%"
set "REMOTE_DIR=/opt/stratagy"
set "SCRIPT_DIR=%~dp0"

if /I "%~1"=="--dry-run" (
    set "DRY_RUN=1"
) else (
    set "DRY_RUN=0"
)

for %%I in ("%SCRIPT_DIR%\..") do set "PROJECT_DIR=%%~fI"

call :require_tool ssh || exit /b 1
call :require_tool scp || exit /b 1

call :require_file "%PROJECT_DIR%\app.py" || exit /b 1
call :require_file "%PROJECT_DIR%\requirements.txt" || exit /b 1
call :require_file "%PROJECT_DIR%\.streamlit\config.toml" || exit /b 1
call :require_file "%PROJECT_DIR%\deploy\deploy.sh" || exit /b 1
call :require_file "%PROJECT_DIR%\deploy\fix_config.sh" || exit /b 1
call :require_file "%PROJECT_DIR%\deploy\install_requirements_if_needed.sh" || exit /b 1
call :require_file "%PROJECT_DIR%\deploy\check_runtime.sh" || exit /b 1
call :require_file "%PROJECT_DIR%\deploy\nginx_strategy.conf" || exit /b 1

echo ============================================
echo   Stratagy full upload and deploy
echo ============================================
echo [info] project: %PROJECT_DIR%
echo [info] server:  %SERVER%
echo [info] remote:  %REMOTE_DIR%
if "%DRY_RUN%"=="1" echo [info] dry-run enabled
echo.

call :run ssh %SERVER% "mkdir -p %REMOTE_DIR% %REMOTE_DIR%/core %REMOTE_DIR%/core/catalogs %REMOTE_DIR%/ui %REMOTE_DIR%/.streamlit %REMOTE_DIR%/deploy %REMOTE_DIR%/data %REMOTE_DIR%/model-test %REMOTE_DIR%/model-test/outputs" || exit /b 1

call :run scp "%PROJECT_DIR%\app.py" "%PROJECT_DIR%\requirements.txt" %SERVER%:%REMOTE_DIR%/ || exit /b 1
call :run scp "%PROJECT_DIR%\core\*.py" %SERVER%:%REMOTE_DIR%/core/ || exit /b 1
call :run scp "%PROJECT_DIR%\ui\*.py" %SERVER%:%REMOTE_DIR%/ui/ || exit /b 1
call :run scp "%PROJECT_DIR%\.streamlit\config.toml" %SERVER%:%REMOTE_DIR%/.streamlit/ || exit /b 1
call :run scp "%PROJECT_DIR%\deploy\deploy.sh" "%PROJECT_DIR%\deploy\fix_config.sh" "%PROJECT_DIR%\deploy\install_requirements_if_needed.sh" "%PROJECT_DIR%\deploy\check_runtime.sh" "%PROJECT_DIR%\deploy\nginx_strategy.conf" %SERVER%:%REMOTE_DIR%/deploy/ || exit /b 1

if exist "%PROJECT_DIR%\core\catalogs\*.csv" (
    call :run scp "%PROJECT_DIR%\core\catalogs\*.csv" %SERVER%:%REMOTE_DIR%/core/catalogs/ || exit /b 1
)

if exist "%PROJECT_DIR%\data\*.csv" (
    call :run scp "%PROJECT_DIR%\data\*.csv" %SERVER%:%REMOTE_DIR%/data/ || exit /b 1
)

if exist "%PROJECT_DIR%\model-test\outputs" (
    call :sync_model_outputs || exit /b 1
)

call :run ssh %SERVER% "chmod +x %REMOTE_DIR%/deploy/deploy.sh %REMOTE_DIR%/deploy/fix_config.sh %REMOTE_DIR%/deploy/install_requirements_if_needed.sh %REMOTE_DIR%/deploy/check_runtime.sh && bash %REMOTE_DIR%/deploy/deploy.sh" || exit /b 1

echo.
echo ============================================
echo   Deploy complete
echo   App url: https://www.gfm156.com/strategy
echo   Nginx template: %REMOTE_DIR%/deploy/nginx_strategy.conf
echo ============================================
exit /b 0

:sync_model_outputs
for /D %%D in ("%PROJECT_DIR%\model-test\outputs\*") do (
    if exist "%%~fD\report.json" (
        call :run scp -r "%%~fD" %SERVER%:%REMOTE_DIR%/model-test/outputs/ || exit /b 1
    )
)
exit /b 0

:require_tool
where %~1 >nul 2>nul
if errorlevel 1 (
    echo [error] missing tool: %~1
    exit /b 1
)
exit /b 0

:require_file
if not exist "%~1" (
    echo [error] missing file: %~1
    exit /b 1
)
exit /b 0

:run
echo [run] %*
if "%DRY_RUN%"=="1" exit /b 0
%*
if errorlevel 1 (
    echo [error] command failed
    exit /b 1
)
exit /b 0
