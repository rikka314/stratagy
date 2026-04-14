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

REM ---- Activate venv ----
call .venv\Scripts\activate.bat

REM ---- Install/update dependencies ----
echo [SETUP] Installing dependencies (this may take a few minutes on first run)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo Try running: pip install -r requirements.txt
    pause
    exit /b 1
)
echo [OK] Dependencies ready.
echo.

REM ---- Launch app ----
echo ============================================
echo   Starting application...
echo   URL: http://localhost:8501/strategy
echo   Press Ctrl+C to stop
echo ============================================
echo.

streamlit run app.py

pause
