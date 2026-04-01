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

For faster local validation runs:

```bash
python model-test/run_research.py --config model-test/configs/smoke_us_v1.json
python model-test/run_research.py --config model-test/configs/smoke_us_v2.json
python model-test/run_research.py --config model-test/configs/smoke_us_v2_locked_240.json
python model-test/run_research.py --config model-test/configs/smoke_us_v2_locked_240_mlflow_qs.json
python model-test/run_research.py --config model-test/configs/us_v2_fast_mlflow_qs.json
```

## Output Files

Each run writes to `model-test/outputs/<output_subdir>/` and produces:

- `runs.csv`
- `stocks.csv`
- `model_summary.csv`
- `segment_summary.csv`
- `robustness_summary.csv`
- `report.json`
- `report.md`
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
- Worker processes are persistent during a run instead of respawning per model.
- The runner clears `streamlit.session_state` at task start before calling the
  existing `run_strategy_pipeline()` entrypoint.
- Config `parallelism: 0` means auto mode. The runner resolves it to a
  hardware-aware worker count and also constrains nested optimizer / LightGBM
  threads to avoid oversubscription.
- Config `cache_dir` defaults to `model-test/cache`, and the default
  `universe_parallelism` is `min(16, max(4, parallelism))`.
- `model-test/cache/` is a research acceleration layer only. It stores:
  - per-symbol profile caches for `build_main_research_profiles()`
  - pool-candidate manifests for the filtered research universe
- Profile cache invalidation is lossless: a cached symbol is recomputed only
  when its source CSV is missing, its file `mtime` changes, or the profile
  signature (`market + adjust + profile_lookback_days`) changes.
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
