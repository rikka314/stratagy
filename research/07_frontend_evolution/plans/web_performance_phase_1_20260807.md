# Web Performance Phase 1 Acceptance - 2026-08-07

## Scope

Phase 1 removes cold-import work for routes that have not been visited. It preserves the public routes, route-state payloads, sidebar parameter keys, core public exports, and existing market fallback behavior. Network total deadlines, parallel home fragments, report pagination, and rerun scoping remain later phases.

## Implementation

- `core/__init__.py` now exposes the previous package API through a PEP 562 lazy compatibility map. Explicit symbol imports and supported core module imports resolve on first access.
- `app.py` registers lightweight route wrappers. Home, single-stock, multi-stock, model-evaluation, final-report, pandas, data loaders, and sidebar imports happen only inside the route that uses them.
- `core.market_context` imports AkShare only after a direct HTTP path needs an AkShare fallback.
- `ui.sidebar` imports `st_keyup` only when the live search input is rendered and still falls back to `st.text_input` when unavailable.
- Subprocess contract tests verify real `sys.modules` state in fresh interpreters.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\measure_app_performance.py --samples 3 --skip-apptest
.\.venv\Scripts\python.exe scripts\measure_app_performance.py --samples 1
```

## Results

- Full pytest suite: `120 passed`.
- Cold `import app`, three fresh interpreter samples: `758.787 ms`, `750.395 ms`, `740.696 ms`.
- Import p50: `750.395 ms`; p75: `754.591 ms`; Phase 1 budget `<= 1000 ms`: passed.
- Phase 0 comparison p50: `2562.289 ms`; Phase 1 p50 reduction: about `70.7%`.
- One AppTest sample: cold `2890.607 ms`; same-process warm `15.063 ms`.
- Fresh `import app` leaves `akshare`, `sklearn`, `lightgbm`, `optuna`, `st_keyup`, and unvisited route modules absent from `sys.modules`.
- Fresh `import core.config` leaves the same optional heavy dependencies absent.
- Fresh `import core.market_context` does not import AkShare.

## Compatibility

Verified examples include:

```python
from core import DATA_DIR, DEFAULT_SYMBOL, add_indicators
from core import ml_filter
```

Unknown package exports continue to raise `AttributeError`. `from core import *` continues to expose legacy public symbols without importing lazy module exports. The final-report route source contract was updated to recognize its lazy wrapper while preserving native `render_html()` rendering and the no-iframe requirement.

## Residual Work

- Browser timing was not measured in this phase; browser acceptance remains part of the later end-to-end matrix.
- AkShare executor total deadlines and parallel home data loading are explicitly Phase 2 scope.
- Report section loading and rerun isolation are Phase 3 and Phase 4 scope.
