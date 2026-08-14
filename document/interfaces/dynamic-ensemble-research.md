# Dynamic Ensemble Research Contract

> Phase A frozen: 2026-08-12
> Scope: research-only Regime-aware Mixture of Experts preparation under `model-test`; no online workflow integration.

## 1. Frozen scope

Phase A does not train a gating model. It freezes the source evidence, candidate experts and comparison rules that Phases B–E must reuse.

| Market | Config | Window 3B source | Full-run source | Costs |
|---|---|---|---|---:|
| `US` | `model-test/configs/moe_baseline_us.json` | `deans_window3b_us` | `full_us_deans_60` | 1 bps commission + 2 bps slippage |
| `CN_A` | `model-test/configs/moe_baseline_cn_a.json` | `deans_window3b_cn_a` | `full_cn_a_deans_60` | 3 bps commission + 5 bps slippage |

The two markets are trained, selected and evaluated independently. A later cross-market model is an additional experiment and must not replace either market-specific baseline.

`model-test/outputs/` is intentionally ignored by Git. A baseline is ready only when its referenced source directories are present and pass the manifest checks below. Missing output is recorded as `pending` / `unavailable`; it is never replaced with invented hashes or optimistic metrics.

## 2. Frozen horizons and split use

- Primary prediction horizon: 20 trading days.
- Ablation horizons: 5 and 60 trading days.
- The best-single-expert control is selected once at market level from main-window training metrics only.
- The selector may read only `train_sharpe`, `train_annret`, `train_maxdd`, coverage fields and identity fields. It must not read any `test_*`, rolling result or final rank.
- Frozen selection score:

  ```text
  median(train_sharpe)
  + 2.0 * median(train_annret)
  - 0.5 * abs(median(train_maxdd))
  ```

- Tie break: higher valid training coverage, then higher median training annualized return, then ascending `model_id`.
- After selection, the chosen expert is applied to the test partition without reselection.

Phase B must add purged walk-forward splits and an embargo of at least one primary prediction horizon before a gating model is trained.

## 3. Net-return and execution-cost contract

The source runner already applies the market execution config inside `simulate_strategy()`:

```text
turnover_t = abs(position_t - position_(t-1))
transaction_cost_t = turnover_t * (commission_bps + slippage_bps) / 10_000
strategy_return_t = gross_strategy_return_t - transaction_cost_t
```

Therefore:

- `strategy_return` is the canonical net return used by every Phase-A baseline and later label.
- `gross_strategy_return` is retained only for audits and gross-return ablations.
- A downstream baseline, expert panel or MoE must not deduct `transaction_cost` again from `strategy_return`.
- `cost_treatment` is persisted as `source_net_no_recharge`.
- Any future gross-return experiment must use an explicitly gross-named field and deduct costs exactly once.

## 4. Frozen representative expert pools

The pool is intentionally limited to eight entries including Cash. Correlated search variants are not all admitted.

### US

| Expert ID | Source model | Role | Equal-weight control |
|---|---|---|---|
| `naive` | `naive` | Buy-and-hold anchor | Yes |
| `drift` | `drift` | Trend baseline | Yes |
| `sm` | `sm` | Fixed signal model | Yes |
| `fsm` | `fsm` | Factor signal model | Yes |
| `best_search` | `sm_bayesian` | Frozen search representative | Yes |
| `ml_filter` | `sm_bayesian_ml_lgbm` | ML-filter representative | Yes |
| `adaptive_router` | `rsm_adaptive_v1` | Existing hard regime router | Yes |
| `cash` | synthetic | Zero-return fallback | No |

### CN_A

| Expert ID | Source model | Role | Equal-weight control |
|---|---|---|---|
| `naive` | `naive` | Buy-and-hold anchor | Yes |
| `drift` | `drift` | Trend baseline | Yes |
| `sm` | `sm` | Fixed signal model | Yes |
| `fsm` | `fsm` | Factor signal model | Yes |
| `sm_bayesian` | `sm_bayesian` | Search representative | Yes |
| `fsm_genetic` | `fsm_genetic` | Search-diversity representative | Yes |
| `adaptive_router` | `rsm_adaptive_v1` | Hard-router control | Explicitly unavailable |
| `cash` | synthetic | Zero-return fallback | No |

The current `adaptive_router_v1` feature schema depends on the US `SPY` proxy and is not validated for `CN_A`. The CN_A result must retain an explicit unavailable control row until a market-native artifact exists. It must not silently substitute a US artifact or another strategy.

Cash is frozen now so later MoE phases cannot omit the safe expert, but it is not included in the Phase-A equal-weight comparison.

## 5. Frozen comparison controls

Exactly three controls are emitted in this order:

1. `best_single_expert`: one required source model selected by the training-only rule in §2.
2. `equal_weight_experts`: equal weight across every required expert marked `include_in_equal_weight=true`, first within each symbol and then across symbols.
3. `adaptive_router_v1`: the existing hard-routing output from `rsm_adaptive_v1`; `CN_A` remains explicitly unavailable under the current artifact schema.

All required source experts must cover the same main-window symbol set. Missing expert rows, missing return artifacts or unequal symbol coverage make the control unavailable. Phase A does not silently re-normalize around missing models.

## 6. Source-lock and manifest requirements

For both `window3b` and `full_run`, the generator requires:

- `config_snapshot.json`
- `data_manifest.json`
- `report.json`
- `runs.csv`
- `model_summary.csv`
- `stocks.csv`

The source `data_manifest.json` must contain:

- canonical market;
- random seed `42`;
- non-empty code version;
- non-empty `data.snapshot_sha256`;
- the exact market commission and slippage values.

The generated `model-test/outputs/moe_baseline_<market>/data_manifest.json` stores:

- Phase-A config path and SHA-256;
- generator code version (the Git commit that materialized the baseline);
- tracked source config path and SHA-256;
- each source manifest SHA-256;
- SHA-256 and size of the six required source files;
- source run ID, code version, random seed and data snapshot SHA-256;
- an aggregate source fingerprint;
- frozen horizons, return semantics, costs, expert pool and baseline controls.

If any required field differs, the strict command fails. `--allow-pending` writes an auditable pending manifest and unavailable result rows for coordination only; it is not a passing research result.

## 7. Phase-A outputs

Run independently for each market:

```bash
python model-test/prepare_moe_baseline.py \
  --config model-test/configs/moe_baseline_us.json

python model-test/prepare_moe_baseline.py \
  --config model-test/configs/moe_baseline_cn_a.json
```

These JSON files are materialization contracts, not ordinary `run_research.py`
configs. `load_research_config()` rejects them explicitly so they cannot launch
an accidental default research campaign.

Each ready run writes:

| File | Contract |
|---|---|
| `data_manifest.json` | Source locks, hashes, code versions, seeds, data hashes and frozen Phase-A policy |
| `baseline_results.csv` | One row per frozen control with selected models, coverage, date range and net-return metrics |
| `baseline_daily_returns.csv` | `date / market / control_id / strategy_return`; no second cost deduction |
| `train_selection_summary.csv` | Training-only model aggregates, score and deterministic selection rank |

`baseline_results.csv` uses these stable fields:

```text
market,control_id,status,selected_model_ids,selection_scope,
return_field,cost_treatment,record_count,symbol_count,start,end,
total_return,annualized_return,sharpe,max_drawdown,
source_total_turnover_mean,source_total_transaction_cost_mean,reason
```

## 8. Boundary for later phases

- Phase B owns the leak-free `date × symbol × market × expert_id` panel and point-in-time features.
- Phase C owns LightGBM gating, softmax weights and weight constraints.
- No Phase-A module is imported by the Streamlit workflow.
- Existing configs, reports, `adaptive_router_v1` artifacts and online defaults remain unchanged.

## 9. Phase-B expert-day panel

Phase B is materialized independently for each market with:

```bash
python model-test/prepare_expert_panel.py \
  --config model-test/configs/moe_baseline_us.json
python model-test/prepare_expert_panel.py \
  --config model-test/configs/moe_baseline_cn_a.json
```

The command revalidates both frozen Phase-A source runs before reading the
full-run `runs.csv` and per-symbol main-window artifacts.  A ready output is
written under the Phase-A `output_subdir` and contains:

| File | Contract |
|---|---|
| `expert_day_panel.parquet` | One row per `date / symbol / market / expert_id`; source `strategy_return` is already net and is never charged again. |
| `expert_panel_walk_forward_splits.csv` | Expanding purged walk-forward intervals; one primary horizon is purged and a separate embargo of at least one primary horizon is enforced between partitions. |
| `expert_panel_manifest.json` | Phase-A config/source fingerprints, expert pool, label policy, feature/lineage schema, split policy and artifact hashes. |
| `expert_panel_quality.json` / `.md` | Missingness, expert availability, label distribution, market/state coverage and split counts. |

The stable key columns are `date`, `symbol`, `market` and `expert_id`.
`label_end_date` and `split_memberships_json` make the purge decision
machine-checkable: a row is assigned to a train/validation/test role only when
its complete label horizon ends inside that role's boundary.
`future_net_return` compounds the next 20 trading-day source
`strategy_return` values; `future_downside` is cumulative absolute negative
return and `future_turnover_penalty` is cumulative future turnover as a
non-cost risk regularizer.  Their combination is `future_utility` under the
manifest's two penalty weights; execution cost is never subtracted again.
Rows without a complete future horizon remain `NaN` labels.  Failed or missing
experts, including the currently unsupported CN_A adaptive router, remain
explicit `expert_status=unavailable` rows with a reason; they are never
replaced by zero or by another expert's result.  Optional news factors are
joined with a strict prior-trading-day lookup (`news_*_lag1`), while optional
market context and exported daily simulation columns are point-in-time only.

The source runner now exports a narrow `daily.csv` beside `returns.csv` when a
simulation artifact is available.  This preserves target position, executed
position, turnover, transaction cost and gross/net return audit fields for
Phase B without changing the existing consumer-facing return artifacts.  For a
legacy artifact that predates `daily.csv`, Phase B may reconstruct a binary
position from its own `trades.csv` and records `position_source` explicitly;
absence of both remains unavailable rather than being zero-filled.
