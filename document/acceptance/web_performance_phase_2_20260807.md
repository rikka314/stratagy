# Web Performance Phase 2 Acceptance - 2026-08-07

## Scope

Phase 2 changes the home page from serial data loading to shell-first rendering with bounded data fragments. It preserves public routes, the home stock state keys, real-data-first behavior, empty states, and the single-stock recommendation source contract.

## Implementation

- `ui.home.render_home_page()` now renders the route nav and a stable home shell before starting external data fetches.
- The home page has three independent Streamlit fragments using `st.fragment(parallel=True)`: daily headlines, stock recommendation cloud with dependent K-line fetch, and market lens.
- NewsAPI, Tencent market snapshot, and Tencent K-line requests now use explicit connect/read timeouts, while existing TTLs remain 24h for news and 15m for market/recommendation/K-line data.
- Home recommendation data is centralized through `get_home_recommendation_pool()` and uses bounded `st.cache_data(max_entries=...)` caching.
- `core.market_context._load_us_famous_recommendations()` uses one total deadline for all US category futures instead of one timeout per future.
- `core.market_context.build_market_context()` uses one total wait for indices and recommendations rather than sequential waits.
- `requirements.txt` now requires `streamlit>=1.60.0,<1.62.0` because Phase 2 depends on `st.fragment(..., parallel=True)`.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_home_news_api.py tests/test_market_context_recommendations.py tests/test_model_evaluation_page.py tests/test_web_performance_contracts.py
.\.venv\Scripts\python.exe -m compileall -q ui/home.py core/market_context.py ui/theme.py tests/test_home_news_api.py tests/test_market_context_recommendations.py
.\.venv\Scripts\python.exe scripts\measure_app_performance.py --samples 1 --skip-apptest
```

## Results

- Focused Phase 2 pytest suite: `40 passed`.
- Changed-file compile check: passed.
- `git diff --check` on Phase 2 files: no whitespace errors; Git reported only existing LF-to-CRLF working-copy warnings for `requirements.txt` and `ui/home.py`.
- Local Streamlit fragment signature verified: `1.60.0 (func=None, *, run_every=None, parallel=False)`.
- Cold `import app`, one fresh interpreter sample: `747.560 ms`; Phase 1 budget `<= 1000 ms`: passed.

## Compatibility

- Home stock state keys remain `home_stock_focus_market` and `home_stock_focus_index`.
- News fallback still fills to four headlines and never exposes `NEWS_API_KEY` in browser markup.
- Recommendation failure returns explicit unavailable state with `items=[]`; no default stock pool is reintroduced.
- K-line failure still renders `K 线暂不可用` / `Candles unavailable`.
- Browser timing was not measured in this phase; use the Phase 0 Playwright procedure for shell-visible and all-upstream-timeout timing.

## Residual Work

- Full `pytest -q` was not rerun in this phase because the focused Phase 2 suite covered the changed contracts. Run full suite before final release.
- Browser cold/hot shell timing and all-upstream-timeout timing remain part of the final Phase 7 matrix.
- Report pagination and rerun isolation remain Phase 3 and Phase 4 scope.
