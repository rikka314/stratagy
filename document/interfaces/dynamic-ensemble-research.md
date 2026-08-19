# Dynamic Ensemble Research Contract

> Phase A frozen: 2026-08-12
> Scope: research-only Regime-aware Mixture of Experts preparation under `model-test`; no online workflow integration.

## 1. Frozen scope

Phase A does not train a gating model. It freezes the source evidence, candidate experts and comparison rules that Phases B–F must reuse.

| Market | Config | Authoritative Phase-A source | Historical smoke trace (not a source lock) | Costs |
|---|---|---|---|---:|
| `US` | `model-test/configs/moe_baseline_us.json` | `full_us_deans_60` | `deans_window3b_us` | 1 bps commission + 2 bps slippage |
| `CN_A` | `model-test/configs/moe_baseline_cn_a.json` | `full_cn_a_deans_60` | `deans_window3b_cn_a` | 3 bps commission + 5 bps slippage |

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
| `adaptive_router` | `rsm_adaptive_v1` | Hard-router control | Yes when backed by a market-matched artifact |
| `cash` | synthetic | Zero-return fallback | No |

`adaptive_router_v1` must always use an artifact whose declared market equals the
research market. The historical W10 CN_A outputs retain their explicit
unavailable row because they predate a native artifact. The admission-specific
`full_cn_a_admission_60` replay now provides a CN_A-native artifact (60/60 main
records successful), so its Phase-A–F chain may emit an available CN_A control.
Neither path may silently substitute a US/SPY artifact or another strategy.

Cash is frozen now so later MoE phases cannot omit the safe expert, but it is not included in the Phase-A equal-weight comparison.

## 5. Frozen comparison controls

Exactly three controls are emitted in this order:

1. `best_single_expert`: one required source model selected by the training-only rule in §2.
2. `equal_weight_experts`: equal weight across every required expert marked `include_in_equal_weight=true`, first within each symbol and then across symbols.
3. `adaptive_router_v1`: the existing hard-routing output from `rsm_adaptive_v1`, available only when its persisted artifact is hash-verified and market-matched; otherwise emitted explicitly unavailable.

All required source experts must cover the same main-window symbol set. Missing expert rows, missing return artifacts or unequal symbol coverage make the control unavailable. Phase A does not silently re-normalize around missing models.

## 6. Source-lock and manifest requirements

`source_runs` contains exactly one authoritative `full_run`. The generator
requires it to contain:

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

The snapshot verifier recomputes every listed CSV's SHA-256 and size from
`data_snapshot/`, rejects missing or unmanifested CSVs, and recomputes the
aggregate SHA-256 before a source can be `ready`.

`historical_runs` may record a prior diagnostic/smoke run only with
`classification=non_authoritative_smoke`. It is retained for audit context,
but is not validated as a source, included in the source fingerprint, or used
to produce controls. A missing snapshot on such a run must never be repaired
by inserting a claimed hash.

The generated `model-test/outputs/moe_baseline_<market>/data_manifest.json` stores:

- Phase-A config path and SHA-256;
- generator code version (the Git commit that materialized the baseline);
- tracked source config path and SHA-256;
- each authoritative source manifest SHA-256;
- SHA-256 and size of the six required source files;
- source run ID, code version, random seed and data snapshot SHA-256;
- an aggregate authoritative-source fingerprint and any non-authoritative historical context;
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

When a legacy frozen full-run has no daily `state_*` / `regime_*` /
`adaptive_*` export, Phase B derives the explicit US fields
`state_market_trend_up_20`, `state_market_high_volatility_20`, and
`state_market_regime_id_20` from the persisted same-date/trailing benchmark
context.  The volatility regime compares `market_volatility_20` with the
*prior* 60-trading-day trailing median, so it never uses future dates.  The
manifest records source versus derived state columns and this rule; if the
required market context is absent, Phase C still fails closed rather than
inventing a state feature.

The source runner now exports a narrow `daily.csv` beside `returns.csv` when a
simulation artifact is available.  This preserves target position, executed
position, turnover, transaction cost and gross/net return audit fields for
Phase B without changing the existing consumer-facing return artifacts.  For a
legacy artifact that predates `daily.csv`, Phase B may reconstruct a binary
position from its own `trades.csv` and records `position_source` explicitly;
absence of both remains unavailable rather than being zero-filled.

## 10. Phase-C LightGBM soft-gating

Phase C remains research-only. It is invoked once per market with:

```bash
python model-test/run_dynamic_ensemble.py \
  --config model-test/configs/moe_v1_us.json
python model-test/run_dynamic_ensemble.py \
  --config model-test/configs/moe_v1_cn_a.json
```

The config is market-specific, freezes seed `42`, the 20-trading-day primary
horizon, `strategy_return` as the already-net return field, and
`source_net_no_recharge` cost treatment. The command accepts only a ready
Phase-A `data_manifest.json`, ready Phase-B `expert_panel_manifest.json`,
their manifest-verified panel/split artifacts, and `baseline_results.csv` in
the configured panel output directory. Pending manifests, altered hashes,
market/horizon mismatches, absent state features, missing cash, or empty test
memberships fail closed.

For every purged walk-forward split, the gate fits only Phase-B `train`
memberships. `expert_id` is categorical; all other gate features come from the
persisted point-in-time numeric feature schema. `moe_no_state` removes
`state_*`, `regime_*`, and `adaptive_*` fields, while `moe_regime_aware` keeps
them. Test memberships are never used in the fold fit. A final all-ready-label
refit is saved only as a future research artifact after evaluation; it is not
used to report walk-forward test performance.

At one `date / symbol`, predicted utilities are converted by numerically stable
softmax. Cash is mandatory. All missing/untradeable risk experts receive zero
weight and the remaining available experts re-normalize. Exponential smoothing
is applied per symbol, then each non-cash expert is capped (40% in the shipped
configs); excess goes to cash. The daily artifact records prediction, raw and
final weights, target-position contribution, weight change, smoothing/cap
reason and fallback reason. It never zero-fills an unavailable expert as an
apparently successful one.

The experiment writes under its Phase-C `output_subdir`:

| File | Contract |
|---|---|
| `moe_model.pkl` | Final full-ready-label LightGBM models for the no-state and regime-aware variants. |
| `moe_feature_schema.json` | Point-in-time feature schema, state-feature partition and feature importance. |
| `moe_daily_weights.parquet` | Per-split/date/symbol/expert raw and constrained weights, target positions, next already-net expert return and reasons. |
| `moe_summary.csv` | Per-split comparison of both MoE variants and frozen `best_single_expert`, `equal_weight_experts`, `adaptive_router_v1` controls. |
| `moe_report.md` | Compact human-readable walk-forward and safety report. |
| `moe_manifest.json` | Config, source-manifest hashes, LightGBM preflight, model policy and artifact hashes. |

The reported daily comparison is an equal-symbol aggregate of the selected
experts' next already-net `strategy_return` values. It deliberately does not
charge the same expert execution cost twice; later portfolio-level rebalancing
cost and uncertainty controls belong to Phase D.

## 11. Phase-D uncertainty- and risk-aware MoE v2

Phase D remains research-only and is invoked only after the matching market has
a ready, manifest-verified Phase-C output:

```bash
python model-test/run_dynamic_ensemble_v2.py \
  --config model-test/configs/moe_v2_us.json
python model-test/run_dynamic_ensemble_v2.py \
  --config model-test/configs/moe_v2_cn_a.json
```

The Phase-D config retains the frozen market, seed `42`, 20-day horizon,
`strategy_return`, and `source_net_no_recharge` policy. It names both the
ready Phase-B panel directory and a market-matched Phase-C output directory.
The runner revalidates Phase-A/B manifests and hashes, then verifies Phase-C's
manifest, decision, summary, feature-schema artifact hashes, and its recorded
Phase-A/B source-lock hashes. Pending or drifted inputs fail closed.

For each purged walk-forward fold and for both `moe_v2_no_state` and
`moe_v2_regime_aware`, two LightGBM quantile regressors fit **only** the
Phase-B train memberships: the configured lower quantile and median. Cash is
fixed at zero predicted utility. Every risk-expert decision records:

```text
uncertainty_width = abs(predicted_median_utility - predicted_lower_utility)
conservative_score = predicted_median_utility - gamma * uncertainty_width
```

The absolute width makes the score conservative even if finite-sample quantile
crossing occurs. The artifact records the two predictions, width, conservative
score, train-fold numeric OOD z-score, fallback trigger/policy, raw/final
weight, and the prior-decision risk state.

Three configured, auditable degradation triggers are evaluated from information
available at the decision date:

| Trigger | Default US policy | Resolution contract |
|---|---|---|
| All available risk experts exceed the uncertainty-width threshold | Cash | Cash receives 100%. |
| Risk-expert median-score standard deviation exceeds the disagreement threshold | Equal weight | Equal-weight eligible frozen experts are cap-constrained; unavailable members are not silently imputed. |
| Any available risk-expert numeric feature is beyond the train-fold OOD z-score threshold | Adaptive router | Uses the market's frozen adaptive expert if available; otherwise falls back to Cash. |

Normal rebalances apply all four Phase-D risk constraints: per-expert maximum
daily weight change (bounded-simplex projection), equal-symbol aggregate daily
turnover cap, minimum expert-mix holding period when attempting to close an
active position, and pre-decision drawdown risk scaling into Cash. A missing
expert, an explicit fallback, or drawdown de-risking may bypass the move/
turnover limits **only to reduce risk**; the daily artifact marks the
`safety_override_weight_change` / `missing_expert_safety_exit` reason rather
than hiding the exception. In particular, a fallback that does not strictly
lower aggregate non-Cash exposure remains subject to the normal bounded-simplex
and turnover constraints. The first decision for a symbol is not a rebalance:
it records `is_initial_allocation=true`, a null `previous_expert_weight`, and
`initial_allocation` rather than claiming a daily weight-change exception. No
portfolio-level transaction cost is inferred or deducted in Phase D; the
reported source return remains already net.

The runner writes under `output_subdir`:

| File | Contract |
|---|---|
| `moe_v2_model.pkl` | Final all-ready-label lower/median quantile models for both v2 variants; not used for walk-forward reporting. |
| `moe_v2_feature_schema.json` | Point-in-time schema plus lower/median feature importance. |
| `moe_v2_daily_weights.parquet` | Per-fold/date/symbol/expert quantile predictions, uncertainty, constrained weights, risk state, fallback and reason fields. |
| `moe_v2_summary.csv` | Walk-forward v2 return, drawdown, tail-loss, turnover, weight-change, and fallback summaries. |
| `moe_uncertainty_calibration.csv` | Per-fold lower-tail coverage, median MAE, and mean uncertainty width. |
| `moe_risk_ablation.csv` | Split-level grid over temperature, risk-expert cap, and smoothing alpha. |
| `moe_v1_v2_comparison.csv` | Same-source Phase-C v1 and Phase-D v2 summary rows. |
| `moe_v2_report.md` / `moe_v2_manifest.json` | Readable result/safety report and complete source/artifact lock. |

Phase-D result files are evidence, not a promotion decision. They must satisfy
the roadmap's cross-window, turnover, tail-risk, and honest market-specific
admission conditions before Phase E or any workflow integration is considered.

## 12. Phase-E online full-information expert weighting

Phase E remains research-only and replays a market-matched ready Phase-D
decision artifact (or an explicitly configured ready Phase-C compatibility
source) after Phase-A/B source-lock verification:

```bash
python model-test/run_dynamic_ensemble_online.py --config model-test/configs/moe_online_us.json
python model-test/run_dynamic_ensemble_online.py --config model-test/configs/moe_online_cn_a.json
```

The runner verifies the Phase-D/C manifest and its daily-weight and summary
artifact hashes, then rechecks that its Phase-A/B manifest hashes and panel
directory still equal the configured ready Phase-B source. Market, primary
20-trading-day horizon, `strategy_return`, and
`source_net_no_recharge` mismatches fail closed. The shipped configs initialize
from `moe_v2_regime_aware`; a fallback source variant is selected only when the
requested frozen variant is absent.

For every source test date and symbol, the first decision uses the frozen
offline MoE allocation. The feedback for that decision is the next observed
Phase-B `strategy_return`, obtained only after sorting each `symbol / expert`
timeline and shifting one step forward. The source return is already net of
execution cost and is never charged again. After the decision is recorded,
Hedge and Exponentiated Gradient receive the complete return vector of every
available expert. The run compares fixed and rolling-volatility-adaptive
learning rates across configured forgetting factors; structural-break winners
are evaluation fields only and never feed the update.

Cash is mandatory. Missing or unavailable risk experts receive zero weight and
their allocation moves to Cash. Every ordinary update is projected onto the
simplex with the frozen risk-expert cap (40% in shipped configs) and maximum
daily component weight change (15% by default). A missing-expert safety exit
may bypass the movement limit only to reduce risk and is retained as
`missing_expert_safety_exit` in the daily artifact.

The Phase-E output directory contains:

| File | Contract |
|---|---|
| `moe_online_weights.parquet` | Per-split/date/symbol expert weights, initial/prior weights, next net returns, portfolio return/turnover, learning rate, evaluation state and safety reason. |
| `moe_online_summary.csv` | Soft-MoE, Hedge and EG return, drawdown, turnover and maximum-weight-change comparison for every parameter cell. |
| `moe_online_drift_response.csv` | Fixed-midpoint pre/post winner and recovery-delay measurement; it is evaluation-only. |
| `moe_online_comparison.csv` / `moe_online_report.md` | Compact comparison surface and readable method/safety report. |
| `moe_online_manifest.json` | Config, Phase-A/B and initial-source hashes, policy, expert-pool/baseline lineage, and hashes for every Phase-E artifact. |

Phase-E artifacts are evidence, not a promotion decision. A real-market
comparison must demonstrate repeatable adaptation across the frozen
walk-forward windows before online weights can replace the offline MoE or enter
any Streamlit workflow.

## 13. Phase-F contextual-bandit comparison

Phase F is a research-only partial-feedback ablation. It consumes a ready,
market-matched, hash-verified Phase-E source and rechecks the same ready
Phase-A/B panel, 20-day horizon, `strategy_return` and
`source_net_no_recharge` contract:

```bash
python model-test/run_dynamic_ensemble_bandit.py --config model-test/configs/moe_bandit_us.json
python model-test/run_dynamic_ensemble_bandit.py --config model-test/configs/moe_bandit_cn_a.json
```

Each hash-verified Phase-E decision variant is an allocation action; its
original simplex and risk-expert cap are verified before it enters the action
set. Cash is always an additional action. LinUCB and contextual Thompson
Sampling choose one action for each `date / symbol`; their context comes only
from configured numeric Phase-B point-in-time columns. Label, future-return,
split-membership and reward columns are rejected as context.

The only feedback that may update a policy is the selected allocation's next
net source return. All choices for a date are made with the preceding
posterior, then that date's selected rewards are batch-applied, so one symbol's
next-period reward cannot affect another same-date choice. Unselected action
outcomes are never written into the decision trace or used for learning. They
may be read after replay solely for the explicitly `evaluation_only` fixed-
midpoint drift/recovery measurement.

`strategy_return` already includes the source execution costs and is never
charged again. `incremental_action_switch_cost_bps` is an optional, separately
reported deployment-layer action-transition assumption; the shipped configs
set it to zero until a measured execution model exists.

The Phase-F output directory contains:

| File | Contract |
|---|---|
| `moe_bandit_decisions.parquet` | One selected action per decision with context snapshot, selected-only reward, source allocation turnover, switch indicator and separately disclosed incremental cost. It contains no unselected action reward. |
| `moe_bandit_summary.csv` / `moe_bandit_convergence.csv` | Net performance, drawdown, switch/cost surface and daily partial-feedback convergence trajectory. |
| `moe_bandit_drift_response.csv` | Evaluation-only fixed-midpoint post-break winner and selected-action recovery delay. |
| `moe_bandit_comparison.csv` / `moe_bandit_report.md` | Full-feedback Phase-E reference beside partial-feedback bandit results and explicit non-promotion boundary. |
| `moe_bandit_final_state.json` / `moe_bandit_manifest.json` | Final per-split posterior state, config, source-lock lineage and SHA-256 metadata for every Phase-F artifact. |

Phase F is not a product admission path by itself. If it cannot stably improve
net results over Hedge / EG after exploration costs, or it worsens turnover or
drawdown, retain it as an ablation and do not connect it to Streamlit.

## 14. Transformer-state v2 W13-W15 source and model boundary

Transformer-state v2 is independent of the Phase A-F promotion path and keeps
the v1 W11 result unchanged. The US and CN_A configs separately freeze Phase-
A/B artifact hashes, the authoritative full-run source manifest and summary,
the market snapshot, the rank-1 `source_model_id -> expert_id` fallback, four
walk-forward splits, q50/q75/q90 retrieval rules, and validation-only jump-
guard candidates.

`run_transformer_state.py --stage panel` produces the W13 source manifest and
W14 artifacts. The five-day label compounds only the following five complete
source-net `strategy_return` rows, subtracts downside and the non-cost turnover
regularizer, and keeps incomplete horizons `NaN`. Feature inputs come only
from same-day/trailing frozen OHLCV, a market-specific equal-weight frozen-
universe benchmark, trailing regime/relative features, and same-day/trailing
expert context. Every feature has source/lookback/shift/missing metadata. A
sequence never crosses symbols, and split membership additionally requires
its sequence start and label end to remain inside the same train, validation,
or test role.

Exact daily `target_position` and turnover are a W13 precondition. Entry/exit
intervals from `trades.csv` do not prove within-trade position sizing and cannot
be used to generate formal five-day utility labels. The union of every legacy
W11 test date is also forbidden from all W15 train/validation memberships;
train-validation and validation-test boundaries retain the configured
protection interval. As of 2026-08-18 CN_A satisfies these W13/W14 conditions,
while US is blocked on the exact-daily-execution precondition.

`run_transformer_state.py --stage model` verifies all W13/W14 hashes before
calling the W15 encoder. Each fold owns its train scaler, train encoder and
label vocabulary; validation alone chooses among the preregistered sequence-
length/layer candidates and the early-stopping checkpoint. The API accepts no
test data during fit. The stored model is a small encoder-only Transformer with
linear projection, sinusoidal position encoding, mean-pooled embedding,
`best_expert_5d` classifier and utility-margin head. Collapsed cosine geometry
or a classifier not above the majority/Cash baseline marks the fold
unavailable.

PyTorch remains an optional research runtime and is not added automatically.
When absent, fold-local normalization/schema and explicit unavailable
manifests are still emitted, no `transformer_encoder.pt` is fabricated, the
runner exits with code `3`, and W16 retrieval is blocked.
