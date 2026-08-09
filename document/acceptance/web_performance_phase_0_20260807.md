# Web Performance Phase 0 Baseline — 2026-08-07

## Scope

Phase 0 adds opt-in JSON Lines telemetry plus repeatable Python and Streamlit probes. It intentionally does not alter route imports, network deadlines, report loading, or rerun behavior; those remain later phases.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_web_performance_contracts.py
.\.venv\Scripts\python.exe scripts\measure_app_performance.py --samples 3 --skip-apptest
.\.venv\Scripts\python.exe scripts\measure_app_performance.py --samples 1
```

## Results

- Focused contract tests: `5 passed`.
- `import app`, three fresh interpreter samples: `2609.759 ms`, `2562.289 ms`, `2555.727 ms`; p50 `2562.289 ms`, p75 `2586.024 ms`.
- Advisory cold-import budget: `1000 ms`; current result is `warn`, not a test failure. Reducing import time is Phase 1 scope.
- One AppTest sample: cold `4228.795 ms`; same-process warm `14.569 ms`.
- Browser timing is explicitly `not_measured`; perform the Phase 0 Playwright procedure separately so client timing is not mixed with Python/Streamlit timing.

## Telemetry Contract

Set `STRATAGY_PERF_TRACE=1` to emit privacy-safe JSON events to stderr. Events contain the route, phase, elapsed time, status, and an allowlisted set of simple metadata fields only. Production is silent by default.

Trace coverage: `app.route_imports`, home data stages, report parse/render, single-stock indicator/figure/walk-forward work, and multi-stock data/figure cache paths.
