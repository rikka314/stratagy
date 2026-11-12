# Post-Gate-2 Model Upgrade — Phase C Acceptance (2026-08-16)

## Result

Phase-C implementation is complete as a research-only LightGBM soft-gating
workflow under `model-test`:

- `model_test.dynamic_ensemble` consumes only manifest-verified ready Phase-A
  and Phase-B artifacts; a pending source lock, hash drift, market/horizon
  mismatch, missing cash expert, missing state feature, or empty test
  membership fails closed;
- `run_dynamic_ensemble.py` trains separate no-state and regime-aware long
  table models using `expert_id` as a categorical feature and Phase-B purged
  walk-forward memberships;
- predictions use stable softmax; cash is mandatory; each risk expert is
  capped at 40% in the shipped configs; missing experts receive zero weight and
  remaining weights re-normalize; per-symbol exponential smoothing, cap and
  fallback reasons are retained;
- output artifacts are `moe_model.pkl`, `moe_feature_schema.json`,
  `moe_daily_weights.parquet`, `moe_summary.csv`, `moe_report.md`, and
  `moe_manifest.json`;
- the summary compares `moe_no_state` and `moe_regime_aware` with frozen
  `best_single_expert`, `equal_weight_experts`, and `adaptive_router_v1`.

The module uses the already-net source `strategy_return` for comparisons and
does not deduct source transaction costs a second time. It is not imported by
Streamlit and makes no online-default or UI change.

## Phase-B compatibility correction

The pre-existing default Phase-B validation/test role length equaled the
20-trading-day label horizon, which left no complete decision/label pair inside
the role. The default is now 40 trading days while the 20-day purge and 20-day
embargo stay unchanged. Explicit caller-supplied role lengths are unchanged.

## Automated verification

| Check | Result |
|---|---|
| Phase-A/B/C contracts, leakage, hash lock, numerical softmax, cash/cap and fallback tests | passed |
| model-test runner and full-run preflight regression | passed |
| Focused matrix (`test_moe_phase_a/b/c`, `test_model_test_runner`, `test_full_research_preflight`) | `42 passed` |
| Phase-C CLI help | passed |
| Synthetic ready-panel end-to-end materialization | passed; all six Phase-C artifacts written and read back |
| Full repository regression | `211 passed` |

## Evidence readiness boundary

No real-market Phase-C score was produced, deliberately:

- US strict Phase-A materialization refuses the legacy
  `deans_window3b_us` manifest because `data.snapshot_sha256` is absent and
  the output has no frozen `data_snapshot/` from which it could be recovered;
- the CN_A full-scale experiment is incomplete, so its strict Phase-A source
  cannot yet be materialized;
- the implementation does not accept `--allow-pending` and therefore cannot
  turn either condition into a model, weights, or performance claim.

The next evidence step is to create/re-freeze source runs with their data
snapshot hashes and complete the CN_A full-scale experiment, then materialize A → B → C with
the commands documented in `model-test/docs/README.md`.
