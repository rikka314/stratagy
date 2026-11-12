# Web Performance Phase 4 Acceptance

> Date: 2026-08-08
> Scope: sidebar batching and analysis-page display rerun isolation.

## Implemented

- `ui/sidebar.py` places sidebar strategy sliders in the `sidebar_strategy_parameters` form and retains the `render_sidebar()` output key set.
- `ui/single_stock.py` caches pure market-display figures in `single_stock_display_cache`. The cache key includes workflow context, artifact identity, split/date and display inputs, strategy indicator inputs, language, and theme. Workflow context resets only clear this display cache.
- `ui/multi_stock.py` batches portfolio weights in `multi_stock_portfolio_weights` and applies inline advanced adjustments through an immutable helper. Existing strategy signature, portfolio workspace, and figure/heatmap caches remain unchanged.
- Frontend contracts and project context record the new state and caching boundaries.

## Verification

```text
.venv\Scripts\python.exe -m compileall -q ui/sidebar.py ui/single_stock.py ui/multi_stock.py
.venv\Scripts\python.exe -m pytest tests/test_web_performance_contracts.py tests/test_entry_page_states.py tests/test_w8_exports_and_routes.py -q

26 passed in 9.29s
```

The focused suite covers form presence, single-display cache-key invalidation, immutable multi-parameter overlays, route-state behavior, and export/path regressions.
