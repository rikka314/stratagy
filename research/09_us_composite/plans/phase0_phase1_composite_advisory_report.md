# Composite Stability Phase 0/1 Completion

## Status

`Phase 0` and `Phase 1` are complete as research-only work. No Streamlit route, production default, or dynamic ensemble path was changed. The replay remains an offline evidence artifact; no advisory policy was admitted for production use.

## Phase 0: semantic and baseline lock

- Added train-window-fitted robust score transformation and bounded position mapping in `model-test/model_test/composite_mapping.py`.
- `ExpertPoolV2` accepts an injected transform, eliminating the optimizer/serve mismatch while preserving the legacy path when no transform is supplied.
- Added explicit OHLCV quality checks, abnormal-return diagnostics, factor direction views, and Pearson/Spearman redundancy output in `model-test/model_test/composite_quality.py`.
- The replay emits decision and execution timestamps, feature cutoff, return interval, raw score, transformed score, target position, executed position, turnover, gross/net return, and cost ledger columns.
- Policy cadence is now applied in the research runner: trend and relative-strength policies use 5 sessions, reversion uses 2 sessions, and daily policies use 1 session. Actual execution changes remain capped at `max_single_decision_change=0.25`.
- OHLCV cost treatment remains `ohlcv_gross_charge_once` with 1 bps commission and 2 bps slippage.

The historical raw-score saturation was removed from the replay baseline: the train-only transformed `composite_only` position has a near-max rate of approximately 1.4%, rather than the previous approximately 99% saturation diagnosis.

## Phase 1: factor direction and redundancy audit

The US frozen source lock was replayed across 60 symbols. Outputs are in `model-test/outputs/composite_advisory_phase1/`:

- `decision_audit.parquet`
- `factor_direction_report.csv`
- `factor_redundancy_matrix.parquet`
- `factor_registry.json`
- `quality_report.json`
- `ablation_metrics.csv`
- `admission_summary.json`
- `admission_report.md`
- `phase1_summary.json`

Run summary:

- `status=passed`
- `research_only=true`
- `symbols=60` in the locked source; 59 symbols provide a complete effective cross-section during the configured folds
- `audit_rows=1,007,377`
- `primary_horizon_days=20`
- `fold_01` and `fold_02` each have 291 complete dates; `fold_03` has 289 complete dates and excludes 2 dates with incomplete coverage
- source/config/macro/snapshot hashes are recorded in the summary and every audit row
- admission result: `composite_plus_reversion` passed the current frozen cross-fold gates; this is a research admission only, not a production recommendation
- no policy admission authorizes production or Streamlit integration

The registry explicitly classifies `vix_level` as a `risk_cap` variable rather than directional alpha pending fold-level direction voting. Factor direction output includes raw, inverse, and one-day lagged views; the redundancy output records per-symbol pairwise Pearson and Spearman relationships.

## Verification

- `42 passed` across Composite, expert pool, factor pipeline, market context, and related regression tests.
- `py_compile` passed for all new/modified research modules.
- The full 60-symbol Phase 0/1 runner completed with exit code `0`.
- All 1,007,377 audit rows have non-null decision/execution lineage and source-lock hashes; `return_end` has no `NaT` values.
- Metrics use only complete cross-sectional dates and explicitly report incomplete-date counts and minimum observed symbol count. The locked 60-symbol universe has an effective 59-symbol set during the folds because `RUBI` lacks the required history; fold 03 has two additional incomplete dates that are excluded.
- Price quality hard failures were zero across all 60 symbols. There are 73 symbol-level warnings covering historical OHLC high/low inconsistencies and large adjusted-close returns; these warnings remain visible in `quality_report.json` and are not silently treated as clean data.
- Direction diagnostics are pooled across each symbol's available history; they are descriptive evidence only and are not a fold-level direction vote or a frozen alpha decision. Fold-specific direction validation remains a follow-up item.

The artifacts are evidence for further research only. The remaining data warnings, fold coverage limitation, and unresolved relative-strength/fold-direction lineage limitations must be resolved or explicitly accepted in a later research phase before any production consideration.

## Remaining limitations
- The score transform is fit once on the pre-`fold_01` training window and reused for the later folds. This is a fixed initial transform for this replay, not a fold-specific expanding refit; the transform parameters are not yet emitted as a separate artifact.
- The runner's default `relative_rank` path is per-symbol historical ranking. A true cross-sectional relative-strength contract requires constructing and passing same-date universe ranks in a follow-up revision.
- The `code_sha256` audit field currently hashes the runner file only; a complete module bundle hash is still pending.
- The replay is therefore suitable for research comparison and audit, but not for production integration or final factor-direction freezing.

