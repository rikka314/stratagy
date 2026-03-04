@echo off
echo ==========================================
echo   Quantitative Trading Strategy Analyzer
echo   Starting...
echo ==========================================
echo.

cd /d "%~dp0\.."

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo Virtual environment activated
) else (
    echo ERROR: Virtual environment not found
    echo Please run setup.bat first
    pause
    exit /b 1
)

echo.
echo Starting Streamlit application...
echo Local URL: http://localhost:8501
echo.
echo Press Ctrl+C to stop the application
echo.

streamlit run app.py

pause
