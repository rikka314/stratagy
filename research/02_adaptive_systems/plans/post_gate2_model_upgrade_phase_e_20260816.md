# Post-Gate-2 Model Upgrade — Phase E Acceptance (2026-08-16)

## Result

Phase E is complete as a research-only full-information online expert-weighting
extension of the source-locked dynamic-ensemble line:

- `model_test.dynamic_ensemble_online` and
  `run_dynamic_ensemble_online.py` accept only a ready, market-matched,
  hash-verified Phase-D source (with an explicit Phase-C compatibility source
  only for research); they recheck the matching ready Phase-A/B panel,
  manifests, horizon, return and cost contract before reading any weights;
- the first decision in each source test window replays the frozen offline MoE
  allocation. Hedge and Exponentiated Gradient update only after that
  decision's complete vector of next observed expert net returns is recorded;
- `strategy_return` remains the source net return. It is shifted causally by
  sorted `symbol / expert` timeline and is never charged a second time;
- fixed and volatility-adaptive learning rates, plus the configured forgetting
  factors, are materialized alongside a `soft_moe` control. Cash is required;
  unavailable expert allocation transfers to Cash; normal decisions preserve
  simplex, 40% risk-expert cap and 15% daily component move constraints. A
  missing-expert safety exit is explicitly marked and may only reduce risk;
- the generated evidence is `moe_online_weights.parquet`, online summary,
  fixed-midpoint drift response, comparison, report and a hash-locked manifest.
  The drift winner/recovery calculation is evaluation-only and does not enter
  the online update.

The implementation is not imported by Streamlit and changes no online default.

## Automated verification

| Check | Result |
|---|---|
| Synthetic ready Phase-A/B/D source-lock materialization | passed |
| Hedge/EG reward response, simplex, Cash transfer, cap and daily-move assertions | passed |
| Unsorted source chronology and decision-before-feedback assertions | passed |
| Fixed-midpoint structural-break response and all six Phase-E artifacts | passed |
| Phase-D source artifact hash-drift rejection | passed |
| US/CN_A config isolation and accidental `run_research.py` rejection | passed |
| Focused Phase-C/D/E regression | `11 passed` |
| Phase-B/C/D/E source-chain regression | `16 passed` |
| Primary and backward-compatible online CLI help | passed |

## Evidence readiness boundary

No real-market Phase-E performance claim is produced by this change. The
current checkout lacks a ready Phase-A/B source lock: the legacy US Window 3B
source has no verifiable `data.snapshot_sha256` or frozen data snapshot, and
the CN_A full-scale experiment is incomplete. Strict Phase-E commands must
continue to reject those inputs rather than create weights, drift results or
promotion claims. Re-freeze the US source data and complete the CN_A full-scale experiment,
then materialize A → B → C → D → E per market before judging whether online
adaptation adds value over the fixed offline MoE.
