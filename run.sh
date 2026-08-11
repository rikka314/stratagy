#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

printf '%s\n' "============================================"
printf '%s\n' "  Quantitative Trading Strategy Analyzer"
printf '%s\n' "  One-Click Setup and Launch"
printf '%s\n\n' "============================================"

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
    printf '%s\n' "On macOS, install it with: brew install python@3.12" >&2
    exit 1
fi

if ! "$python_command" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    printf '%s\n' "[ERROR] Python 3.10+ is required." >&2
    printf '%s\n' "Set PYTHON_BIN to a compatible interpreter and try again." >&2
    exit 1
fi

printf '%s\n' "[OK] Python found:"
"$python_command" --version
printf '\n'

venv_python=.venv/bin/python
if [ ! -x "$venv_python" ]; then
    printf '%s\n' "[SETUP] Creating virtual environment..."
    "$python_command" -m venv .venv
    printf '%s\n\n' "[OK] Virtual environment created."
fi

if ! "$venv_python" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    printf '%s\n' "[ERROR] The existing .venv uses Python older than 3.10." >&2
    printf '%s\n' "Remove .venv, set PYTHON_BIN if needed, and run this script again." >&2
    exit 1
fi

requirements_hash_file=.venv/.requirements.sha256
requirements_hash=$(
    "$venv_python" -c "from hashlib import sha256; from pathlib import Path; print(sha256(Path('requirements.txt').read_bytes()).hexdigest())"
)
installed_requirements_hash=
if [ -f "$requirements_hash_file" ]; then
    IFS= read -r installed_requirements_hash < "$requirements_hash_file" || true
fi

if [ "$requirements_hash" = "$installed_requirements_hash" ]; then
    printf '%s\n' "[OK] requirements.txt unchanged; skipping pip install."
else
    printf '%s\n' "[SETUP] Installing dependencies because requirements.txt changed..."
    "$venv_python" -m pip install -r requirements.txt --quiet
    printf '%s\n' "$requirements_hash" > "$requirements_hash_file"
    printf '%s\n' "[OK] Dependencies installed and fingerprint recorded."
fi

printf '%s\n' "[RUNTIME] Python:"
"$venv_python" --version
printf '%s\n' "[RUNTIME] Streamlit:"
"$venv_python" -c "import streamlit; print(streamlit.__version__)"
printf '\n'

if [ "${1:-}" = "--setup-only" ]; then
    printf '%s\n' "[OK] Setup-only check complete."
    exit 0
fi

export STRATAGY_RESEARCH_CONTROL=1
printf '%s\n' "============================================"
printf '%s\n' "  Starting application..."
printf '%s\n' "  URL: http://localhost:8501/strategy"
printf '%s\n' "  Experiment monitor: http://localhost:8501/strategy/experiment-monitor"
printf '%s\n' "  Press Ctrl+C to stop"
printf '%s\n\n' "============================================"

exec "$venv_python" -m streamlit run app.py
