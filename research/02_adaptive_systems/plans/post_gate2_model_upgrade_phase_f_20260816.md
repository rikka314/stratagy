# Post-Gate-2 Model Upgrade — Phase F Acceptance (2026-08-16)

## Result

Phase F is complete as a research-only contextual-bandit comparison on the
source-locked dynamic-ensemble line:

- `model_test.dynamic_ensemble_bandit` and
  `run_dynamic_ensemble_bandit.py` accept only a ready, same-market,
  hash-verified Phase-E source; they recheck the ready Phase-A/B manifests,
  panel directory, 20-day horizon, return field and cost contract before
  reading action rows;
- every eligible Phase-E allocation variant becomes an action only after its
  simplex and risk-expert cap are checked; Cash is always a separate action;
- LinUCB and contextual Thompson Sampling use configured numeric Phase-B
  point-in-time context. Future labels, realized return fields and split
  membership fields are rejected as context;
- only the selected action's next net return is used in an update. All choices
  on a date use the preceding posterior and selected rewards are batch-applied
  afterwards, preventing same-date cross-symbol leakage. Unselected action
  returns are absent from the decision trace and learner state;
- `strategy_return` is already net of expert execution costs and is not
  recharged. An optional action-switch cost is separately named and set to
  zero in the shipped configs until a measured deployment cost model exists;
- evidence consists of selected-action decisions, partial-feedback summary and
  convergence, evaluation-only drift recovery, Phase-E comparison, final
  posterior state, report and a hash-locked manifest.

The implementation is not imported by Streamlit and changes no online default.

## Automated verification

| Check | Result |
|---|---|
| Synthetic ready Phase-A/B/E source-lock materialization | passed |
| Selected-action-only posterior update and deterministic replay | passed |
| Cash availability, explicit switch cost and source-allocation cap checks | passed |
| Phase-E source artifact hash-drift rejection | passed |
| US/CN_A config isolation, future-context rejection and `run_research.py` rejection | passed |
| Same-date cross-symbol feedback isolation | passed |
| Focused Phase-F test suite | `5 passed` |
| Focused Phase-C–F source-chain regression | `16 passed` |
| Primary and compatibility CLI help | passed |

## Evidence readiness boundary

No real-market Phase-F performance claim is produced by this change. The
current checkout still lacks the ready Phase-A/B source lock required upstream:
the legacy US Window 3B source has no verifiable `data.snapshot_sha256` or
frozen data snapshot; the CN_A full-scale experiment is incomplete.
Strict Phase-F commands must continue to reject those inputs rather than create
bandit results or promotion claims. Re-freeze the source data and materialize
A → B → C → D → E → F separately per market before deciding whether partial
feedback adds value over full-feedback Hedge / EG.
