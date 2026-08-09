# Window 3B Campaign Monitor Acceptance — 2026-08-09

## Result

- Local route: `/strategy/experiment-monitor`
- Registration gate: `STRATAGY_RESEARCH_CONTROL=1`
- Formal sequence: `full_us_deans_60 -> full_cn_a_deans_60 -> full_cross_market_deans_60`
- Pause contract: cooperative task-boundary pause, exit code `75`, checkpoint resume
- Live ranking: separate Stage A, Stage B, rolling robustness, and final tables

## Verification

| Check | Result |
|---|---|
| Python compile | Passed for app, UI, core, and model-test entry points |
| Full pytest | `176 passed` |
| `run.bat --setup-only` | Passed; Python 3.13.7, Streamlit 1.60.0 |
| Real runner pause/resume smoke | Pause returned `75`; resume completed one-record run without duplication |
| Browser route | Page rendered on isolated local port with campaign empty state and enabled Start button |
| Dirty-worktree gate | Browser Start action surfaced the expected clean-worktree refusal |
| Local-only behavior | Route registration and buttons require the explicit local environment switch |

## Reproducibility safeguards

- Campaign JSON files use atomic replace with Windows retry handling.
- Config SHA-256 and clean Git commit are frozen at creation and revalidated on resume.
- A stale background PID becomes a failed-but-resumable state while preserving checkpoints.
- Fetched research history is written to ignored `model-test/cache/history/`, not tracked `data/`.
- `model-test/mlruns/`, campaign state, research outputs, browser artifacts, and local preview files are ignored.

