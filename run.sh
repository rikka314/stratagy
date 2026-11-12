#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
setup_only=0
legacy_streamlit=0
for argument in "$@"; do
    case "$argument" in
        --setup-only) setup_only=1 ;;
        --legacy-streamlit) legacy_streamlit=1 ;;
        *)
            printf '%s\n' "[ERROR] Unknown option: $argument" >&2
            printf '%s\n' "Usage: ./run.sh [--setup-only] [--legacy-streamlit]" >&2
            exit 2
            ;;
    esac
done

if [ -n "${PYTHON_BIN:-}" ]; then
    python_command=$PYTHON_BIN
elif command -v python3.12 >/dev/null 2>&1; then
    python_command=python3.12
elif command -v python3 >/dev/null 2>&1; then
    python_command=python3
elif command -v python >/dev/null 2>&1; then
    python_command=python
else
    printf '%s\n' "[ERROR] Python 3.10+ was not found in PATH." >&2
    exit 1
fi
if ! "$python_command" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    printf '%s\n' "[ERROR] Python 3.10+ is required." >&2
    exit 1
fi

venv_python=.venv/bin/python
if [ ! -x "$venv_python" ]; then
    printf '%s\n' "[SETUP] Creating Python virtual environment..."
    "$python_command" -m venv .venv
fi
requirements_hash_file=.venv/.requirements.sha256
requirements_hash=$("$venv_python" -c "from hashlib import sha256; from pathlib import Path; print(sha256(Path('requirements.txt').read_bytes()).hexdigest())")
installed_requirements_hash=
if [ -f "$requirements_hash_file" ]; then
    IFS= read -r installed_requirements_hash < "$requirements_hash_file" || true
fi
if [ "$requirements_hash" = "$installed_requirements_hash" ]; then
    printf '%s\n' "[OK] requirements.txt unchanged; skipping pip install."
else
    printf '%s\n' "[SETUP] Installing Python dependencies..."
    "$venv_python" -m pip install -r requirements.txt --quiet
    printf '%s\n' "$requirements_hash" > "$requirements_hash_file"
    printf '%s\n' "[OK] Dependencies installed and fingerprint recorded."
fi

printf '%s\n' "[RUNTIME] Python:"
"$venv_python" --version
if [ "$legacy_streamlit" -eq 1 ]; then
    printf '%s\n' "[RUNTIME] Streamlit legacy mode:"
    "$venv_python" -c "import streamlit; print(f'Streamlit {streamlit.__version__}')"
    if [ "$setup_only" -eq 1 ]; then
        printf '%s\n' "[OK] Legacy Streamlit setup complete."
        exit 0
    fi
    export STRATAGY_RESEARCH_CONTROL=1
    printf '%s\n' "[START] Legacy Streamlit: http://localhost:8501/strategy"
    exec "$venv_python" -m streamlit run app.py
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    printf '%s\n' "[ERROR] Node.js 20.19+ or 22.12+ and npm are required to build the JavaScript frontend." >&2
    exit 1
fi
if ! node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit((major===20 && minor>=19) || (major===22 && minor>=12) || major>22 ? 0 : 1)"; then
    printf '%s\n' "[ERROR] Node.js 20.19+ or 22.12+ is required by Vite." >&2
    exit 1
fi
printf '%s\n' "[RUNTIME] Node:"
node --version
frontend_hash_file=.venv/.frontend-requirements.sha256
frontend_hash=$("$venv_python" -c "from hashlib import sha256; from pathlib import Path; files=[Path('frontend/package.json'),Path('frontend/package-lock.json')]; print(sha256(b''.join(p.read_bytes() for p in files if p.is_file())).hexdigest())")
installed_frontend_hash=
if [ -f "$frontend_hash_file" ]; then
    IFS= read -r installed_frontend_hash < "$frontend_hash_file" || true
fi
if [ "$frontend_hash" = "$installed_frontend_hash" ] && [ -d frontend/node_modules ]; then
    printf '%s\n' "[OK] Frontend dependencies unchanged; skipping npm install."
else
    npm --prefix frontend install
    printf '%s\n' "$frontend_hash" > "$frontend_hash_file"
fi
npm --prefix frontend run build
printf '%s\n' "[RUNTIME] FastAPI / Uvicorn:"
"$venv_python" -c "import fastapi, uvicorn; print(f'FastAPI {fastapi.__version__}, Uvicorn {uvicorn.__version__}')"
if [ "$setup_only" -eq 1 ]; then
    printf '%s\n' "[OK] Setup and frontend build complete."
    exit 0
fi
printf '%s\n' "[START] http://localhost:8501/strategy"
exec "$venv_python" -m uvicorn api.main:app --host 0.0.0.0 --port 8501
