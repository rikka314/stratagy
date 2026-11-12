@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "SETUP_ONLY=0"
set "LEGACY_STREAMLIT=0"
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--setup-only" set "SETUP_ONLY=1"
if /I "%~1"=="--legacy-streamlit" set "LEGACY_STREAMLIT=1"
if /I not "%~1"=="--setup-only" if /I not "%~1"=="--legacy-streamlit" (
    echo [ERROR] Unknown option: %~1
    echo Usage: run.bat [--setup-only] [--legacy-streamlit]
    exit /b 2
)
shift
goto parse_args

:args_done
python --version >nul 2>&1 || (
    echo [ERROR] Python 3.10+ was not found in PATH.
    exit /b 1
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" || (
    echo [ERROR] Python 3.10+ is required.
    exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo [SETUP] Creating Python virtual environment...
    python -m venv .venv || exit /b 1
)

set "REQUIREMENTS_HASH_FILE=.venv\.requirements.sha256"
set "REQUIREMENTS_HASH="
for /f "usebackq delims=" %%H in (`.venv\Scripts\python.exe -c "from hashlib import sha256; from pathlib import Path; print(sha256(Path('requirements.txt').read_bytes()).hexdigest())"`) do set "REQUIREMENTS_HASH=%%H"
if not defined REQUIREMENTS_HASH (
    echo [ERROR] Failed to calculate requirements.txt hash.
    exit /b 1
)
set "INSTALLED_REQUIREMENTS_HASH="
if exist "%REQUIREMENTS_HASH_FILE%" set /p INSTALLED_REQUIREMENTS_HASH=<"%REQUIREMENTS_HASH_FILE%"
if /I "%REQUIREMENTS_HASH%"=="%INSTALLED_REQUIREMENTS_HASH%" (
    echo [OK] requirements.txt unchanged; skipping pip install.
) else (
    echo [SETUP] Installing Python dependencies...
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet || exit /b 1
    >"%REQUIREMENTS_HASH_FILE%" echo %REQUIREMENTS_HASH%
    echo [OK] Dependencies installed and fingerprint recorded.
)

echo [RUNTIME] Python:
.venv\Scripts\python.exe --version
if "%LEGACY_STREAMLIT%"=="1" goto legacy_ready

where node >nul 2>&1 || (
    echo [ERROR] Node.js 20.19+ or 22.12+ is required to build the JavaScript frontend.
    exit /b 1
)
where npm >nul 2>&1 || (
    echo [ERROR] npm was not found in PATH.
    exit /b 1
)
node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit((major===20 && minor>=19) || (major===22 && minor>=12) || major>22 ? 0 : 1)" || (
    echo [ERROR] Node.js 20.19+ or 22.12+ is required by Vite.
    exit /b 1
)
echo [RUNTIME] Node:
node --version
set "FRONTEND_HASH_FILE=.venv\.frontend-requirements.sha256"
set "FRONTEND_HASH="
for /f "usebackq delims=" %%H in (`.venv\Scripts\python.exe -c "from hashlib import sha256; from pathlib import Path; files=[Path('frontend/package.json'),Path('frontend/package-lock.json')]; print(sha256(b''.join(p.read_bytes() for p in files if p.is_file())).hexdigest())"`) do set "FRONTEND_HASH=%%H"
set "INSTALLED_FRONTEND_HASH="
if exist "%FRONTEND_HASH_FILE%" set /p INSTALLED_FRONTEND_HASH=<"%FRONTEND_HASH_FILE%"
set "INSTALL_FRONTEND_DEPS=1"
if /I "%FRONTEND_HASH%"=="%INSTALLED_FRONTEND_HASH%" if exist frontend\node_modules set "INSTALL_FRONTEND_DEPS=0"
if "%INSTALL_FRONTEND_DEPS%"=="0" (
    echo [OK] Frontend dependencies unchanged; skipping npm install.
) else (
    call npm --prefix frontend install || exit /b 1
    >"%FRONTEND_HASH_FILE%" echo %FRONTEND_HASH%
)
call npm --prefix frontend run build || exit /b 1
echo [RUNTIME] FastAPI / Uvicorn:
.venv\Scripts\python.exe -c "import fastapi, uvicorn; print(f'FastAPI {fastapi.__version__}, Uvicorn {uvicorn.__version__}')"
if "%SETUP_ONLY%"=="1" (
    echo [OK] Setup and frontend build complete.
    exit /b 0
)
echo [START] http://localhost:8501/strategy
.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8501
exit /b %errorlevel%

:legacy_ready
echo [RUNTIME] Streamlit legacy mode:
.venv\Scripts\python.exe -c "import streamlit; print(f'Streamlit {streamlit.__version__}')"
if "%SETUP_ONLY%"=="1" (
    echo [OK] Legacy Streamlit setup complete.
    exit /b 0
)
set "STRATAGY_RESEARCH_CONTROL=1"
echo [START] Legacy Streamlit: http://localhost:8501/strategy
.venv\Scripts\python.exe -m streamlit run app.py
exit /b %errorlevel%
