# CN_A Factor Composite Phase 1 Acceptance Record — 2026-08-22

## Scope

Phase 1 introduces the market-aware factor context boundary. It is research-only
and does not train Composite, tune advisory rules, modify production strategy,
or connect Streamlit.

## Implementation

- `core/market_factor_context.py` defines canonical market normalization,
  validated benchmark frames, optional volatility/breadth/sector sources, and
  `build_market_factor_context()`.
- `core/macro_factors.py` accepts `MarketFactorContext` and computes market-native
  CN_A names without creating misleading SPY/VIX aliases.
- `core/factor_pipeline.py` accepts `market` and `market_context` while retaining the
  legacy two-argument US path.
- `MacroFactors.compute(date, stock_data, stock_symbol=None)` remains available for
  historical research callers; the DataFrame-first form is the market-aware pipeline
  interface.
- CN_A context construction requires an explicit benchmark or frozen-universe
  frame. It never probes `spy_daily.parquet` or `vix_daily.parquet`.
- All factor calculations copy input frames before adding columns.

## Contract checks

| Check | Result |
|---|---|
| US legacy `compute_all_factors(df, symbol)` | PASS |
| Canonical market aliases (`USA`, `CN-A`, `CNA`) | PASS |
| Unknown market fails clearly | PASS |
| CN_A without explicit context fails closed | PASS |
| Context market mismatch fails clearly | PASS |
| Duplicate or unsorted benchmark rejected | PASS |
| CN_A equal-weight fallback is explicit and labeled | PASS |
| CN_A explicit benchmark retains frozen-universe breadth | PASS |
| CN_A does not read US macro artifacts | PASS |
| Universe duplicate/non-finite rows rejected | PASS |
| CN_A output excludes `vix_level` / `rel_strength_spy` aliases | PASS |
| CN_A output excludes US-only `beta_20d` / `sector_momentum` | PASS |
| Breadth-unavailable path emits explicit missing values | PASS |
| Input DataFrame remains unchanged | PASS |
| CN_A reads US macro artifacts implicitly | PASS: prohibited by construction |

## Validation

```text
pytest -q tests/test_market_factor_context.py tests/test_macro_factors.py tests/test_factor_pipeline.py
32 passed
python -m py_compile core/market_factor_context.py core/macro_factors.py core/factor_pipeline.py
PASS
```

## Status and decision

```text
Status: ready
Decision: continue
Market: CN_A
Source: Phase 0 locked CN_A snapshots; benchmark remains explicit native-or-registered-fallback policy
Primary result: MarketFactorContext boundary, market-native CN_A factors, and US-compatible factor interfaces are implemented and tested.
Gate result: Phase 1 interface gate passed; Phase 2 CN_A market-factor implementation may proceed.
Known limitations: sector context is unavailable in this phase; the Phase 0 equal-weight fallback is a registered policy and still requires its own artifact validation in Phase 2.
Production impact: none
Streamlit impact: none
```
