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

The runner also maintains resumable internal checkpoint files in the same
output directory:

- `_checkpoint_runs.csv`
- `_checkpoint_meta.json`

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
