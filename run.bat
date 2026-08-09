@echo off
chcp 65001 >nul 2>&1
echo ============================================
echo   Quantitative Trading Strategy Analyzer
echo   One-Click Setup and Launch
echo ============================================
echo.

cd /d "%~dp0"

REM ---- Check Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

REM ---- Create venv if missing ----
if not exist .venv\Scripts\python.exe (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
    echo.
)

REM ---- Install/update dependencies only when requirements change ----
set "REQUIREMENTS_HASH_FILE=.venv\.requirements.sha256"
set "REQUIREMENTS_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath 'requirements.txt').Hash.ToLowerInvariant()"`) do set "REQUIREMENTS_HASH=%%H"

if not defined REQUIREMENTS_HASH (
    echo [ERROR] Failed to calculate requirements.txt hash.
    pause
    exit /b 1
)

set "INSTALLED_REQUIREMENTS_HASH="
if exist "%REQUIREMENTS_HASH_FILE%" set /p INSTALLED_REQUIREMENTS_HASH=<"%REQUIREMENTS_HASH_FILE%"

if /I "%REQUIREMENTS_HASH%"=="%INSTALLED_REQUIREMENTS_HASH%" (
    echo [OK] requirements.txt unchanged; skipping pip install.
) else (
    echo [SETUP] Installing dependencies because requirements.txt changed...
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        echo Try running: .venv\Scripts\python.exe -m pip install -r requirements.txt
        pause
        exit /b 1
    )
    >"%REQUIREMENTS_HASH_FILE%" echo %REQUIREMENTS_HASH%
    echo [OK] Dependencies installed and fingerprint recorded.
)

echo [RUNTIME] Python:
.venv\Scripts\python.exe --version
echo [RUNTIME] Streamlit:
.venv\Scripts\python.exe -c "import streamlit; print(streamlit.__version__)"
echo.

if /I "%~1"=="--setup-only" (
    echo [OK] Setup-only check complete.
    exit /b 0
)

REM ---- Launch app ----
set "STRATAGY_RESEARCH_CONTROL=1"
echo ============================================
echo   Starting application...
echo   URL: http://localhost:8501/strategy
echo   Experiment monitor: http://localhost:8501/strategy/experiment-monitor
echo   Press Ctrl+C to stop
echo ============================================
echo.

.venv\Scripts\python.exe -m streamlit run app.py

pause
