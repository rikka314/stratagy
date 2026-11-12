# 00 · SM/FSM Full-Market Baseline

## Why this line started

The first research question was whether the original SM/FSM-style strategy families and their search/ML variants remained useful when tested over a substantially larger, frozen market universe instead of a few hand-picked symbols.

## Frozen scope

- Markets: US and CN_A are separate evidence sets; no cross-market extrapolation.
- Standard universe: 60 symbols per market for the full run.
- Main window: 1,260 trading days.
- Robustness: four rolling windows of 756 days with a 126-day step.
- Search fairness: Random/Bayesian 240 evaluations; Genetic 240 objective evaluations; seed 42.
- Execution: US commission 1 bps + slippage 2 bps; CN_A commission 3 bps + slippage 5 bps.
- Controls: `Naive` buy-and-hold remains visible in every comparison.
- Data: selected CSVs are frozen under each full-run `data_snapshot/` and described by `data_manifest.json`.

## Research flow

1. Freeze the market-specific config, costs, seed, universe, freshness date, and search budget.
2. Run the preflight checks and reject stale data or a dirty official-run worktree.
3. Execute SM, FSM, RSM, baseline, search, ML, and adaptive-router candidates.
4. Record per-symbol/per-window artifacts, model summaries, rolling robustness, segments, and failures.
5. Aggregate multi-objective scores while retaining absolute return, excess return, Sharpe, drawdown, coverage, and `Naive` comparisons.
6. Write the market-local report and manifest; do not convert ranking into a return promise.

## Key decisions and ideas

- A candidate ranking is a research comparison, not a recommendation or expected-return estimate.
- Robustness and beat-`Naive` evidence are shown beside total score.
- ML remains an ablation/conditional branch; it is not automatically better than its parent.
- Adaptive routing is a state-aware candidate/control, not an independently proven production alpha.

## Result

The US baseline froze `full_us_deans_60` with 5,460 run records: 1,140 main-window successes and 4,318 successful rolling records plus two explicit degradations. `SM+Bayesian` ranked first by composite score (72.67), but its main-window median excess return was -7.95%, median Sharpe 0.03, and it beat `Naive` on only 40% of symbols. The honest conclusion is that the baseline established a reproducible comparison and a default research candidate, not stable full-market outperformance.

The CN_A full run is a separate market-local source. Its conclusions must be read from its own manifest/report and never substituted for the US result.

## Gate and current status

Status: `baseline_frozen`. This line is a reference baseline for later studies, not a production admission gate.

## Problems and future work

- Median excess return and broad beat-`Naive` evidence remain insufficient for a general performance claim.
- Segment winners have small samples and are research leads only.
- Any future claim requires a fresh, market-matched confirmation tier or an independently approved shadow study.

## Source files

- Contract: [`deans-award-research-contract.md`](../../document/interfaces/deans-award-research-contract.md)
- Runner guide: [`model-test README`](../../model-test/docs/README.md)
- Baseline report: [`strategy_research_baseline_us_20260811.md`](../../document/strategy_research_baseline_us_20260811.md)
- Gate records: [`gate_0`](../../document/acceptance/gate_0_20260803.md), [`gate_1`](../../document/acceptance/gate_1_20260803.md)
- Configs: `model-test/configs/full_us_deans_60.json`, `full_cn_a_deans_60.json`, `benchmark_us_deans_240.json`, `benchmark_cn_a_deans_240.json`
- Evidence roots: `model-test/outputs/full_us_deans_60/`, `full_cn_a_deans_60/`, `full_cross_market_deans_60/`

## Reproduction boundary

The original commands and output names remain under `model-test/`. Re-running them is a new experiment and must not overwrite or relabel this frozen record.
