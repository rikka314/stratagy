# Quantitative Trading Strategy Analyzer

A modular Streamlit-based WebApp for financial data analysis, strategy backtesting, model comparison and offline HTML report export. Covers US and A-share markets.

## Final Submission Entry Points

| Item | Path |
|------|------|
| WebApp entry | `app.py` |
| Offline HTML report | `reports/Final_Report.html` |
| Dependency list | `requirements.txt` |
| Final packaging script | `scripts/prepare_final_zip.ps1` |

## Quick Start (Windows One-Click)

**Prerequisites:** Python 3.10+ installed and added to PATH.

Double-click **`run.bat`** in the project root. It will automatically:

1. Create a virtual environment (`.venv/`)
2. Install all dependencies from `requirements.txt`
3. Launch the Streamlit app

Then open your browser at: **http://localhost:8501/strategy**

## Manual Setup

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate (Windows)
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
streamlit run app.py
```

Open browser: `http://localhost:8501/strategy`

## Alternative Windows Scripts

| Script | Purpose |
|--------|---------|
| `run.bat` | One-click install + launch (recommended) |
| `scripts\setup.bat` | Create venv and install deps only |
| `scripts\start.bat` | Launch app (venv must exist) |

## Data

The `data/` folder contains sample US stock CSV files (AAPL, GOOGL, META, NVDA, TSLA, etc.). For other stocks, the app fetches data online via AkShare, which requires a network connection.

## Features

- Single-stock analysis with strategy signal generation and backtesting
- Multi-stock comparison, risk-return analysis and portfolio simulation
- Baseline (Naive, Mean, Drift) vs Proposed Model comparison
- Walk-forward validation, model evaluation and metric checking
- Adjustable parameters via UI sliders (entry/exit thresholds, stop-loss/take-profit, factor weights)
- Single-stock and multi-stock offline HTML export

## Project Structure

```text
stratagy/
├── run.bat                   # One-click install + launch (Windows)
├── app.py                    # Streamlit entry point & route shell
├── requirements.txt          # Python dependencies
├── pytest.ini                # Test configuration
├── core/                     # Data, indicators, signals, backtest, evaluation, optimization
├── ui/                       # Pages, sidebar, theme, HTML export
├── data/                     # Sample & cached stock CSV data
├── reports/                  # Final offline HTML report
├── scripts/                  # Setup, start, packaging and legacy utility scripts
├── deploy/                   # Server deployment scripts & Nginx config
├── model-test/               # Offline strategy research workspace
├── tests/                    # Pytest test suite
├── document/                 # Project documentation & archives
├── plan/                     # Semester & weekly plans
├── .streamlit/               # Streamlit framework config
└── AI_CONTEXT.md             # Project-level AI collaboration context
```

## Final ZIP Packaging

Generate the course-required `Final_gpXX.zip`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_final_zip.ps1 -GroupNumber 01
```

The script automatically copies source code, excludes build artifacts (`.git`, `__pycache__`, `.venv`, temp dirs), and creates `dist/Final_gp01.zip`.

**Smoke test:** After packaging, extract the ZIP on a clean machine and run `run.bat` to verify everything works.

## Cloud Deployment

| Item | Value |
|------|-------|
| Public path | `/strategy` |
| Server directory | `/opt/stratagy` |
| Incremental sync | `deploy/sync.bat` |
| Full deploy | `deploy/upload_and_deploy.bat` |

## Disclaimer

This application is for academic coursework and research only. It does not constitute investment advice.
