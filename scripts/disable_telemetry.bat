@echo off
echo Creating Streamlit config to disable telemetry...

REM Create .streamlit directory in user home
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"

REM Create config.toml
(
echo [browser]
echo gatherUsageStats = false
echo.
echo [server]
echo headless = true
) > "%USERPROFILE%\.streamlit\config.toml"

echo.
echo Config created successfully!
echo Location: %USERPROFILE%\.streamlit\config.toml
echo.
echo This will:
echo - Disable usage statistics collection
echo - Remove startup warnings
echo.
pause
