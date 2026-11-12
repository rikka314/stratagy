# 09 · US Composite (Phase 0-4)

## Why this line started

After the Transformer feasibility study revealed that the existing 10 technical factors were highly correlated and expert pool was homogeneous, the US Composite research aimed to rebuild the factor system with macro context and market-relative dimensions, train a composite model, and add multi-expert advisory overlay.

## Frozen scope

- Market: US only; conclusions cannot be generalized to CN_A
- Universe: 60 US symbols from the frozen Dean's Award baseline
- Factors: 10 technical + 13 macro/market-relative factors (23 total after Phase 1)
- Horizon: 20 trading days (extended from 5 days)
- Execution: 1 bps commission + 2 bps slippage; source-net returns
- Phases:
  - Phase 0: Macro data infrastructure (VIX, SPY, sector classification)
  - Phase 1: Factor layering and selection (4-layer factor pipeline)
  - Phase 2: Robust weight research (train-only clipping/scaling, block bootstrap)
  - Phase 3: Position mapping (quantile_5bin, dead_zone_softsign, vol_target, monotone_calibrated)
  - Phase 4: Advisory overlay (trend, reversion, relative, macro policies)

## Research flow

1. **Phase 0**: Download macro data (VIX, SPY, US sector map) with fail-closed validation and SHA-256 hashing.
2. **Phase 1**: Implement `core/macro_factors.py` (6 macro factors) and `core/factor_pipeline.py` (4-layer architecture with 23 factors total). Run factor selection experiments to identify homogeneity.
3. **Phase 2**: Implement robust weight optimization with train-only constraints, direction/family budgets, multi-objective utility, block bootstrap, and stability statistics.
4. **Phase 3**: Test 4 position mapping methods, evaluate fold consistency, and select best mapping for Phase 4.
5. **Phase 4**: Build advisory framework with long-only policies; advisory can maintain or reduce Composite position but never increase or open unauthorized positions.

## Key decisions and ideas

- **Information循环 fix**: Use real 20-day forward returns as training target, never synthetic or mock data.
- **Macro integration**: VIX regime, relative strength vs SPY, market breadth, beta, sector momentum provide market context missing from pure technical factors.
- **Composite ownership**: Composite has its own learned direction; advisory is a conservative risk overlay, not a replacement.
- **Safety boundaries**: Advisory multipliers are bounded, daily position change is limited, missing context triggers explicit fallback.
- **Market isolation**: US weights and conclusions are US-only; CN_A is a separate research line.

## Result

US Composite Phase 0-4 completed and **passed admission**. The composite model outperformed SM/FSM baselines under the frozen US comparison. Fold consistency met the preregistered threshold. Advisory framework was validated with unit tests and ablation logic.

All research outputs are US-only and research-only. They have not been promoted to production default or integrated into Streamlit unless explicitly documented elsewhere.

## Gate and current status

Status: `passed_research_gate`. US Composite cleared the frozen research admission criteria for US market under the declared universe, horizon, and cost assumptions.

## Problems and future work

- Only one frozen US universe and fold configuration covered; generalization requires independent confirmation.
- Advisory real-data gate completion depends on availability of `composite_advisory_us` (or equivalent) output manifest and ablation artifacts.
- A future production review needs independent data-integrity review, UI fallback review, latency/rollback analysis, and shadow mode.

## Source files

- Planning:
  - Phase 0: [`phase0_*.md`](plans/) (7 files)
  - Phase 1: [`phase1_*.md`](plans/) (5 files, excluding `phase1_diagnostic_report.md` which belongs to Transformer)
  - Phase 2: [`phase2_*.md`](plans/) (2 files)
  - Phase 3: [`phase3_*.md`](plans/) (3 files)
  - Phase 4: [`phase4_*.md`](plans/) (7 files)
  - Overview: [`PHASE1_README.md`](plans/), [`PHASE2_README.md`](plans/), [`PHASE3_README.md`](plans/), [`PHASE4_README.md`](plans/)
  - Roadmaps: [`expert_system_reconstruction_roadmap.md`](plans/), [`factor_and_expert_optimization_plan.md`](plans/), [`three_plans_comparison.md`](plans/)
- Logs: [`phase3_output.log`](logs/), [`phase3_run.log`](logs/), [`phase4_10factors.log`](logs/), [`phase4_rerun.log`](logs/)
- Code:
  - Factors: `core/macro_factors.py`, `core/factor_pipeline.py`, `core/expert_pool_v2.py`, `core/market_factor_context.py`
  - Composite: `core/composite_advisory.py`, `core/composite_advisory_config.py`, `core/composite_advisory_tuned.py`
  - Runners: `model-test/run_composite_stability_phase2.py`, `model-test/run_composite_stability_phase3.py`, `model-test/run_composite_stability_phase4.py`, `model-test/run_composite_advisory_phase1.py`, `model-test/run_phase1_baseline.py`
- Configs: `model-test/configs/composite_stability_phase2.json`, `composite_stability_phase3.json`, `composite_stability_phase4.json`, `composite_advisory_phase0_1.json`, `expert_system_phase1_us.json`
- Expected evidence: `model-test/outputs/composite_stability_phase*/`, `expert_system_phase1_us/`

## Reproduction boundary

Re-running the phase scripts creates new research outputs and must preserve the real-forward-return target, frozen US universe, 20-day horizon, and purged fold contract. Changing windows, costs, or folds post hoc to manufacture a passing result is not an allowed remedy.
