# 03 · CN_A Composite-Only

## Why this line started

The factor research moved from US assumptions toward market-native CN_A context. The question was whether a Composite built from technical and CN_A market factors could be a reproducible research object and outperform the original SM/FSM baselines under one unified comparison.

## Frozen scope

- Market: CN_A only; conclusions cannot be generalized to US or other markets.
- Universe: `full_cn_a_admission_60` / the frozen CN_A comparison universe.
- Factors: 10 technical factors plus 13 market-native factors with explicit lineage.
- Horizon: 20 trading days.
- Execution: 3 bps commission + 5 bps slippage; source-net returns, no recharge.
- Comparison: `composite_only`, `sm`, and `fsm` on the same market, folds, horizon, and execution semantics.
- Admission: Sharpe better than baseline, fold consistency at least 75%, at least one risk improvement, unified config, and traceable manifest.

## Research flow

1. Define explicit market-factor context and prohibit implicit SPY/VIX reads in CN_A.
2. Build and validate the CN_A factor panel, schema, quality report, lineage, and hashes.
3. Train Composite weights only against real 20-day forward returns.
4. Run long-only position mapping and fold-level execution comparison.
5. Compare Composite against SM/FSM with the same folds, cost, universe, and return field.
6. Apply the predeclared admission gate and preserve the failed mock-target attempt as a warning.

## Key decisions and ideas

- Market factors must be market-native and point-in-time; US artifacts cannot silently substitute for CN_A context.
- The initial random-noise target was invalid research input. It was corrected to real forward returns before accepting performance conclusions.
- Composite has its own learned direction and is evaluated as `composite_only` before any advisory overlay.
- A passed research gate is not a production review.

## Result

The corrected run produced Composite Sharpe `0.5972`, ahead of SM `0.5277` (+13.2%) and FSM `0.4984` (+19.8%). Mean maximum drawdown was `-54.81%` versus `-74.07%` for SM and `-64.50%` for FSM. Fold consistency was `76.7%`, meeting the `>=75%` threshold. Factor weights showed a stable mean-reversion pattern: positive RSI and negative MACD/BB-position contributions across folds.

## Gate and current status

Status: `passed_research_gate`. The result is CN_A-only, research-only, and not a production or cross-market claim.

## Problems and future work

- Only one frozen CN_A universe and four-fold comparison are covered.
- Advisory was not part of this gate.
- A future production review needs independent data-integrity review, UI fallback review, latency/rollback analysis, and shadow mode.

## Source files

- Phase records: [`phase 1`](../../document/acceptance/cn_a_factor_composite_phase1.md), [`phase 2`](../../document/acceptance/cn_a_factor_composite_phase2.md), [`phase 3`](../../document/acceptance/cn_a_factor_composite_phase3.md), [`phase 4 fixed`](../../document/acceptance/cn_a_factor_composite_phase4_fixed.md), [`phase 6`](../../document/acceptance/cn_a_factor_composite_phase6.md)
- Comparison report: [`cn_a_factor_composite_phase6.md`](../../document/acceptance/cn_a_factor_composite_phase6.md)
- Config: `model-test/configs/composite_cn_a.json`
- Runners: `model-test/build_cn_a_factor_panel.py`, `run_cn_a_baseline.py`, `run_cn_a_composite.py`, `compare_cn_a_composite_v2.py`
- Research modules retained at import paths: `core/cn_a_market_factors.py`, `core/market_factor_context.py`, `core/composite_cn_a.py`
- Evidence root: `model-test/outputs/composite_cn_a/` and `model-test/outputs/cn_a_factor_composite_comparison/`

## Reproduction boundary

Re-running the scripts creates a new run. It must preserve the real-forward-return target and the frozen CN_A cost/universe/fold contract; the old random-target diagnostic cannot be used as evidence.
