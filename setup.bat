@echo off
echo ==========================================
echo   Setup - Quantitative Trading Analyzer
echo ==========================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if venv exists and is valid
if exist .venv\Scripts\python.exe (
    echo Checking existing virtual environment...
    .venv\Scripts\python.exe --version >nul 2>&1
    if errorlevel 1 (
        echo WARNING: Virtual environment is broken
        echo Removing old virtual environment...
        rmdir /s /q .venv
    ) else (
        echo Found valid virtual environment, removing to ensure clean setup...
        rmdir /s /q .venv
    )
)

echo Creating fresh virtual environment...
python -m venv .venv

echo.
echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ==========================================
echo Setup complete!
echo ==========================================
echo.
echo You can now run start.bat to launch the application
echo.
pause
