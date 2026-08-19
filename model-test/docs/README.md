# Model-Test Workspace

This workspace adds an offline research runner that reuses the existing
single-stock strategy pipeline without changing the Streamlit UI.

## Entry Point

```bash
python model-test/run_research.py --config model-test/configs/us_v1.json
python model-test/run_research.py --config model-test/configs/us_v2.json
python model-test/run_research.py --config model-test/configs/us_v2_locked_240.json
python model-test/run_research.py --config model-test/configs/us_v2_fast.json
```

## Window 3B Local Campaign Monitor

Local `run.bat` enables the control-only route at
`/strategy/experiment-monitor`. Production deployments do not register this
route unless `STRATAGY_RESEARCH_CONTROL=1` is explicitly set.

The page starts the official sequence in a detached background manager:

1. `full_us_deans_60.json`
2. `full_cn_a_deans_60.json`
3. `full_cross_market_deans_60.json`

The equivalent management CLI is:

```bash
python model-test/manage_campaign.py start
python model-test/manage_campaign.py status --campaign-id <campaign-id>
python model-test/manage_campaign.py pause --campaign-id <campaign-id>
python model-test/manage_campaign.py resume --campaign-id <campaign-id>
```

Campaign control data lives under
`model-test/outputs/_campaigns/<campaign-id>/`. `campaign.json` is the durable
campaign state, `progress.json` is the active runner snapshot,
`pause.request.json` is a cooperative pause request, and `campaign.log` is the
combined manager/runner log. JSON state files are replaced atomically.

Pause is task-boundary safe: the executor stops submitting new stock-window
batches, allows at most the current worker-count of in-flight batches to finish,
checkpoints their records, and exits with code `75`. Resume requires the same
clean Git commit and unchanged config SHA-256 values, then skips completed
`(symbol, window_id, model_id)` records.

For faster local validation runs:

```bash
python model-test/run_research.py --config model-test/configs/smoke_us_v1.json
python model-test/run_research.py --config model-test/configs/smoke_us_v2.json
python model-test/run_research.py --config model-test/configs/smoke_us_v2_locked_240.json
python model-test/run_research.py --config model-test/configs/smoke_us_v2_locked_240_mlflow_qs.json
python model-test/run_research.py --config model-test/configs/us_v2_fast_mlflow_qs.json
python model-test/run_research.py --config model-test/configs/smoke_us_deans_gate1.json
python model-test/run_research.py --config model-test/configs/smoke_cn_a_deans_gate1.json
```

## Dean's Award Full-Run Preparation

The final research is split into two market-specific runs plus a separate shared-candidate comparison:

```bash
python model-test/preflight_research.py \
  --config model-test/configs/full_us_deans_60.json \
  --config model-test/configs/full_cn_a_deans_60.json

python model-test/run_research.py --config model-test/configs/benchmark_us_deans_240.json
python model-test/run_research.py --config model-test/configs/benchmark_cn_a_deans_240.json
python model-test/run_research.py --config model-test/configs/full_us_deans_60.json
python model-test/run_research.py --config model-test/configs/full_cn_a_deans_60.json
python model-test/run_research.py --config model-test/configs/full_cross_market_deans_60.json
```

- `60` symbols per market is the standard full run; it is not the earlier 12–24-symbol pilot.
- `confirm_us_deans_120.json` and `confirm_cn_a_deans_120.json` are the second confirmation tier. Run them only after the 60-symbol methods and parameters are frozen.
- The full configs use 1,260-day main windows, four 756-day rolling windows, uniform 240-evaluation search budgets, Stage B ML, frozen execution costs, and exact CSV snapshots under each output directory.
- `minimum_data_end_date: 2026-07-31` is a hard freshness gate. Older sample/cache files are skipped and refetched; a fetch failure stops the run instead of silently accepting stale history.
- Full configs refuse to start from a dirty worktree. `--allow-dirty` is only for checking config/dependency readiness; it does not bypass the runner's clean-worktree gate.
- Market recommendations use every strategy validated for that market. The cross-market shared benchmark is a separate view restricted to common candidates.

### LightGBM GPU

`lightgbm_device_type` accepts `cpu`, `gpu`, or `cuda`. The runner performs a tiny fit before a non-CPU run and fails immediately when the installed LightGBM build lacks the requested backend. It never silently falls back to CPU for an official GPU run.

Probe the current environment with:

```bash
python model-test/preflight_research.py \
  --config model-test/configs/full_us_deans_60.json \
  --allow-dirty --probe-device gpu --probe-device cuda
```

GPU acceleration applies only to LightGBM-based ML filters and the adaptive state classifier. Data loading, pandas indicators, backtests, Logistic Regression, and most parameter-search evaluations remain CPU-bound.

## Output Files

Each run writes to `model-test/outputs/<output_subdir>/` and produces:

- `runs.csv`
- `stocks.csv`
- `model_summary.csv`
- `segment_summary.csv`
- `robustness_summary.csv`
- `report.json`
- `report.md`
- `config_snapshot.json` with the effective market, cost, and search settings
- `data_manifest.json` with code version, seed, data/split ranges, universe, execution costs, compute device, and aggregate data-snapshot SHA-256
- `artifacts/<symbol>/<window_id>/<model_id>/...` per-run analysis bundles for successful and degraded runs
- `regime_artifacts/` when adaptive regime artifacts are trained in the run
- `quantstats/<rank>_<model_id>/...` when `enable_quantstats=true`
- `mlflow_run.json` when `enable_mlflow=true`

## Dynamic-Ensemble Phase A

The Post-Gate-2 baseline contract is frozen in
`document/interfaces/dynamic-ensemble-research.md`. After the ignored Window 3B
and full-run source outputs are available locally, materialize the three frozen
controls and their source-lock manifest with:

```bash
python model-test/prepare_moe_baseline.py --config model-test/configs/moe_baseline_us.json
python model-test/prepare_moe_baseline.py --config model-test/configs/moe_baseline_cn_a.json
```

Strict mode refuses missing files, market/cost/seed mismatches, missing data
snapshot hashes, unequal expert coverage, and missing return artifacts. For
coordination only, `--allow-pending` writes a manifest with `status=pending` and
explicit unavailable result rows; it is not valid research evidence.

The generated Phase-A directory contains `data_manifest.json`,
`baseline_results.csv`, `baseline_daily_returns.csv`, and
`train_selection_summary.csv`. Every baseline consumes the already-net
`strategy_return` field and never charges the source transaction cost twice.

## Dynamic-Ensemble Phase B

Once the Phase-A source locks are ready, materialize the market-specific
expert-day panel with:

```bash
python model-test/prepare_expert_panel.py --config model-test/configs/moe_baseline_us.json
python model-test/prepare_expert_panel.py --config model-test/configs/moe_baseline_cn_a.json
```

The command writes `expert_day_panel.parquet`,
`expert_panel_walk_forward_splits.csv`, `expert_panel_manifest.json`, and a
JSON/Markdown quality report under the same output directory. The panel is
keyed by `date / symbol / market / expert_id`, uses point-in-time trailing
features, and labels the next 20 trading days with the already-net
`strategy_return`. Missing or unsupported experts remain explicit unavailable
rows. Optional news factors are joined only from the prior completed trading
day; no Phase-B output is imported by Streamlit or the online workflow.

## Dynamic-Ensemble Phase C

Only after the same output directory contains a **ready** Phase-A source lock,
the ready Phase-B panel, and `baseline_results.csv`, run the market-specific
LightGBM soft-gating experiment:

```bash
python model-test/run_dynamic_ensemble.py --config model-test/configs/moe_v1_us.json
python model-test/run_dynamic_ensemble.py --config model-test/configs/moe_v1_cn_a.json
```

Phase C verifies both input manifest hashes before fitting. It trains a long
table `expert_id` categorical regressor separately for every purged
walk-forward train fold, then compares `moe_no_state` and
`moe_regime_aware` with the three frozen controls. The output directory holds
`moe_model.pkl`, `moe_feature_schema.json`, `moe_daily_weights.parquet`,
`moe_summary.csv`, `moe_report.md`, and a source-lock `moe_manifest.json`.

Every decision retains its prediction, raw/final weight, weight-change and
fallback reason. Cash is mandatory, each non-cash expert is capped at 40% by
default, missing experts are re-normalized away, and exponential smoothing is
applied before the final target position is calculated. This remains a
research-only workflow; it does not import Streamlit or alter any online
default.

## Dynamic-Ensemble Phase D

Phase D is a source-locked uncertainty and risk layer on top of ready Phase A,
B, and C outputs. It is market-specific and must use the corresponding
Phase-C output directory:

```bash
python model-test/run_dynamic_ensemble_v2.py --config model-test/configs/moe_v2_us.json
python model-test/run_dynamic_ensemble_v2.py --config model-test/configs/moe_v2_cn_a.json
```

For every purged walk-forward fold it fits lower-quantile and median LightGBM
regressors for both no-state and regime-aware variants. The decision score is
`median - gamma * abs(median - lower)`; Cash remains a fixed zero-utility safe
expert. Low confidence, excessive expert-score disagreement, and a numeric
input outside the fold's train distribution take the config-selected Cash,
equal-weight, or adaptive-router route and record the trigger/reason.

Normal decisions enforce the configured maximum component weight change,
equal-symbol aggregate turnover, minimum expert-mix holding time, and
pre-decision drawdown scaling. A missing expert, safety fallback, or drawdown
de-risking is permitted to break the movement limit only to lower risk, and is
explicitly marked in the daily artifact. The output directory contains the
v2 quantile models, daily decisions, calibration report, risk ablation grid,
v1/v2 comparison, readable report, and full source-lock manifest. It does not
add a second execution-cost deduction to the source net return.

The runner also maintains resumable internal checkpoint files in the same
output directory:

- `_checkpoint_runs.csv`
- `_checkpoint_meta.json`

## Dynamic-Ensemble Phase E

Phase E replays the frozen, ready same-market Phase-D MoE weights and compares
full-information Hedge and Exponentiated Gradient expert updates. It verifies
the Phase-D daily-weight/summary hashes and rechecks the same Phase-A/B source
lock before running:

```bash
python model-test/run_dynamic_ensemble_online.py --config model-test/configs/moe_online_us.json
python model-test/run_dynamic_ensemble_online.py --config model-test/configs/moe_online_cn_a.json
```

The first decision in each test window is the offline MoE allocation. Later
decisions use only complete expert feedback observed after the previous
decision; the Phase-B `strategy_return` is already net and is not charged
again. The shipped configs compare Hedge/EG, fixed/volatility-adaptive learning
rates, and two forgetting factors. Cash is required, unavailable experts move
to Cash, every risk expert is capped at 40%, and ordinary daily component moves
are capped at 15%. A missing-expert safety exit may only relax the movement
bound to reduce risk and is recorded explicitly.

The output directory contains `moe_online_weights.parquet`,
`moe_online_summary.csv`, `moe_online_drift_response.csv`,
`moe_online_comparison.csv`, `moe_online_report.md`, and the hash-locked
`moe_online_manifest.json`. The fixed-midpoint drift response is an
evaluation-only measurement; it cannot influence an online update. This is
research-only and does not alter a Streamlit default.

## Dynamic-Ensemble Phase F

Phase F is a research-only comparison for deployments that can observe only
the reward of the allocation actually chosen. It verifies a market-matched,
ready Phase-E manifest and its artifact hashes, then rechecks the same
Phase-A/B source lock before replaying each Phase-E decision variant as an
allocation action:

```bash
python model-test/run_dynamic_ensemble_bandit.py --config model-test/configs/moe_bandit_us.json
python model-test/run_dynamic_ensemble_bandit.py --config model-test/configs/moe_bandit_cn_a.json
```

LinUCB and contextual Thompson Sampling use only configured numeric,
point-in-time Phase-B context columns. Every action for a date is selected from
the prior posterior, then only that action's next net return is batch-applied.
Cash is mandatory. Unselected returns never enter the decision trace or a
model update; the fixed-midpoint drift/recovery calculation is explicitly
evaluation-only.

Source `strategy_return` is already net of expert execution cost and is not
recharged. The optional `incremental_action_switch_cost_bps` is reported
separately for a measured deployment-level action transition; shipped configs
set it to zero. Outputs are `moe_bandit_decisions.parquet`, summary,
convergence, drift, comparison, final posterior state, report and a
hash-locked manifest. Phase F remains an ablation and never changes a
Streamlit default.

## Execution Notes

- Tasks are grouped by `symbol + window`, so one worker reuses the same data
  slice and Streamlit stage cache across all models for that stock/window.
- With a campaign control directory, the process pool keeps only one in-flight
  batch per worker instead of submitting the complete run up front. Calls
  without `--control-dir` remain backward compatible and do not create control
  files.
- Worker processes are persistent during a run instead of respawning per model.
- The runner clears `streamlit.session_state` at task start before calling the
  existing `run_strategy_pipeline()` entrypoint.
- Config `parallelism: 0` means auto mode. The runner resolves it to a
  hardware-aware worker count and also constrains nested optimizer / LightGBM
  threads to avoid oversubscription.
- Config `cache_dir` defaults to `model-test/cache`, and the default
  `universe_parallelism` is `min(16, max(4, parallelism))`.
- `model-test/cache/` is a research acceleration layer only. It stores:
  - fetched market history under `history/`, keeping formal runs from dirtying
    the tracked `data/` sample directory
  - per-symbol profile caches for `build_main_research_profiles()`
  - pool-candidate manifests for the filtered research universe
- Profile cache invalidation is lossless: a cached symbol is recomputed only
  when its source CSV is missing, its file `mtime` changes, or the profile
  signature (`market + adjust + profile_lookback_days + minimum_data_end_date`) changes.
- Pool-cache invalidation is also lossless: changes to the catalog file or pool
  selection config rebuild the candidate manifest; otherwise hot runs reuse the
  cached candidate list and only recompute symbols whose profile cache went
  stale.
- Search optimization now reuses a request-scoped evaluation cache and carries
  the best `full_signal_df` forward directly, so finding the best parameters no
  longer triggers an extra base-stage recomputation.
- ML filtering now builds one full-signal feature bundle and derives train /
  full / test views from it, while still preventing labels from crossing the
  training boundary.
- Config can optionally inject research-only request overrides:
  - `request_params_overrides`: merged into `build_request_params_snapshot()`
  - `stage_b_request_overrides`: merged into Stage B `StrategyRequest`
- Config can optionally run a targeted incremental pass without rebuilding the
  whole output:
  - `selected_model_ids`: only build tasks for the listed `model_id`s
  - `merge_into_existing_output=true`: seed from the current `runs.csv` when no
    checkpoint exists, append the new records into the same output directory,
    and then rewrite the combined summaries / reports
- `us_v2.json` enables `hold_until_exit=True` / `hold_min_position=0.2`, which
  activates the V2 search space and stateful holding behavior in the shared
  core.
- `us_v2.json` Stage B also fixes `ml_horizon_days=20` and
  `ml_min_excess_samples=40` for longer-horizon research labels.
- `commission_bps` and `slippage_bps` are optional config fields. If omitted,
  Gate-1 research defaults are US `1 + 2 bps` and CN_A `3 + 5 bps`; setting
  both to `0` explicitly enables the zero-cost regression mode.

## Stage A Models

Stage A now includes the US-only regime family plus the adaptive router:

- `rsm`: the main dual-state router candidate
- `rsm_no_market`: research-only ablation without SPY proxy
- `rsm_no_router`: research-only ablation without the execution router
- `rsm_adaptive_v1`: adaptive regime router trained from candidate state metrics

Adaptive-specific notes:

- Standard Stage A tasks run first.
- If `rsm_adaptive_v1` is selected, the runner then trains
  `regime_artifacts/` from the same run's main-window results.
- The runner exports the artifact directory through
  `STRATAGY_ADAPTIVE_REGIME_ARTIFACT_DIR` before launching adaptive Stage A
  tasks, so the adaptive model in that run consumes the freshly generated
  offline artifacts.
- `report.json` and `report.md` append adaptive state and routing summaries
  when the training step succeeds.

## Config Profiles

- `smoke_us_v1.json` uses the repository `data/` samples and only executes
  Stage A.
- `smoke_us_deans_gate1.json` and `smoke_cn_a_deans_gate1.json` are the
  smallest reproducible dual-market checks. Each runs the Naive baseline on one
  symbol, writes a readable report and manifest, and exercises the frozen
  market-cost defaults.
- `smoke_us_v2.json` uses the same sample universe but turns on the V2 request
  overrides and Stage B ML settings for a faster end-to-end validation run.
- `us_v2_locked_240.json` keeps the V2 research flow but locks the search budget
  to a fair `240` objective-eval benchmark:
  - random / bayesian: `240` trials
  - genetic: `24 x (9 + 1) = 240` evals
  - rolling robustness reuses the main-window frozen params instead of
    re-running search
- `smoke_us_v2_locked_240.json` mirrors the locked benchmark on the sample
  universe for end-to-end validation.
- `us_v2_fast.json` is the lighter day-to-day validation profile:
  `120 / 12 / 9`, `main_pool_size=24`, `run_robustness=false`.
- `smoke_us_v2_locked_240_mlflow_qs.json` enables local MLflow tracking and
  QuantStats tear sheets on top of the locked smoke benchmark, writing to
  `model-test/outputs/smoke_us_v2_locked_240_mlflow_qs/`.
- `us_v2_fast_mlflow_qs.json` enables the same observability stack on the
  faster day-to-day profile, writing to
  `model-test/outputs/us_v2_fast_mlflow_qs/`.
- `us_v1.json` builds a US research pool from `core/catalogs/us_stock_catalog.csv`,
  runs Stage A, expands Stage B for the winning SM / FSM search paths, and then
  performs rolling-window robustness checks on the top-ranked models.
- `us_v2.json` keeps the same research pool flow, but raises search intensity to
  `120 / 40 / 30` (`search_trials / ga_population_size / ga_generations`) and
  records outputs under `model-test/outputs/us_v2/`.

## Scoring, Robustness, and Reporting

- When rolling robustness is enabled, the runner writes checkpoint records after
  each completed task and can resume by skipping finished
  `(symbol, window_id, model_id)` records.
- `model_summary.csv` records both `main_total_score` and
  `robustness_total_score`, and the final `total_score` blends them using
  `robustness_weight` (default `0.3`) whenever robustness is present.
- `rsm_adaptive_v1` is excluded from rolling robustness selection and does not
  contribute rows to `robustness_summary.csv`.
- Successful and degraded task records now persist `returns.csv`,
  `benchmark_returns.csv`, `equity.csv`, optional `trades.csv`, and
  `metadata.json` under the per-run `artifacts/` tree; `runs.csv` stores the
  resolved paths for those bundles.
- QuantStats tear sheets are generated from the final top-N models by pooling
  all main-window run-level returns with an equal-weight daily mean. The
  resulting HTML path is written back to `model_summary.csv`, `report.json`, and
  `report.md`.
- MLflow logging is optional and run-level only: once local files are written,
  the runner logs config scalars, headline metrics, and output artifacts to the
  configured experiment, defaulting to the local file store
  `model-test/mlruns/`.

## Transformer-state W13-W15 research extension

The v2 Transformer-state line is a separate research-only hypothesis after the
v1 W11 admission rejection. It does not alter Phase A-F outputs, Streamlit, or
the existing admission decision. Market-specific entrypoints are:

```bash
python model-test/run_transformer_state.py \
  --config model-test/configs/transformer_state_us.json --stage panel
python model-test/run_transformer_state.py \
  --config model-test/configs/transformer_state_cn_a.json --stage panel
python model-test/run_transformer_state.py \
  --config model-test/configs/transformer_state_us.json --stage model
```

W13 revalidates the frozen Phase-A/B manifests and artifact hashes, the
authoritative full-run snapshot and rank-1 fallback mapping, Cash, the adaptive
control, and exact daily fallback positions/turnover. Interval-trade entry/exit
reconstruction is not exact daily evidence and fails closed. US no-trade rank-1 artifacts may be
classified as `provable_zero_position` only when the successful source has
zero turnover, all-zero net returns, and constant equity; all other missing
position cases fail closed.

W14 writes `state_label_panel.parquet`, `state_sequence_panel.parquet`, a
four-fold protected split CSV, point-in-time feature schema, quality report and
hash-locked manifest. The label uses only complete `t+1..t+5` source-net
`strategy_return`, downside and turnover. The max 20-day sequence remains
within one symbol and a role membership is emitted only when both the sequence
start and label end stay inside that role. The union of all legacy W11 test
dates is globally excluded from every v2 train/validation membership, and each
train/validation/test boundary retains the configured trading-day protection.

W15 uses a fold-local train scaler plus missingness mask and a small
encoder-only PyTorch Transformer with classifier and utility-margin heads.
Only train data fits model/scaler state; validation selects a preregistered
capacity/sequence candidate and early-stopping checkpoint; the fit API has no
test input. PyTorch is optional at import time. If it is absent, each fold and
the overall model manifest are written as `unavailable`, the runner exits `3`,
and W16 is not allowed to proceed. No large runtime dependency is installed by
this workflow.

Current evidence (2026-08-18): CN_A W13/W14 is ready with 22,098 complete
sequences; its four W15 folds are unavailable because PyTorch is not installed.
US is blocked at W13 because its Phase-B non-Cash artifacts do not contain exact
daily execution paths. Earlier interval-reconstructed US panel output is not
valid W14 evidence.
