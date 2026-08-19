# Post-Gate-2 Model Upgrade — Phase D Acceptance (2026-08-16)

## Result

Phase D is complete as a research-only uncertainty- and risk-aware extension
of the source-locked dynamic-ensemble line:

- `model_test.dynamic_ensemble_v2` accepts only a ready Phase-A/B panel and a
  market-matched, hash-verified ready Phase-C output; all market, horizon,
  return, cost, source-manifest and artifact checks fail closed;
- lower-quantile and median LightGBM models are fit only on each purged
  walk-forward train fold for both no-state and regime-aware v2 variants;
- each decision records lower / median predictions, absolute quantile width,
  conservative score, fold-train OOD score, weights, prior weight change,
  turnover, holding state, drawdown state, fallback trigger and reason;
- Cash is fixed at zero utility and mandatory. Low confidence, high score
  disagreement and OOD inputs use an explicit configured Cash, equal-weight,
  or adaptive-router fallback. An unavailable adaptive router falls back to
  Cash rather than substituting another model;
- normal rebalances enforce risk-expert cap, component weight-change and
  aggregate equal-symbol turnover limits, minimum expert-mix holding time,
  and pre-decision drawdown de-risking. Safety fallback, missing-expert exit,
  and drawdown de-risking may exceed action limits only to reduce risk, with a
  reason retained in the daily artifact;
- generated artifacts are the v2 quantile models/schema/daily weights/summary,
  uncertainty calibration, risk ablation matrix, v1-v2 comparison, report,
  and a complete manifest. Source `strategy_return` remains already net and is
  never charged a second time.

The implementation is not imported by Streamlit and changes no online default.

## Automated verification

| Check | Result |
|---|---|
| Synthetic ready Phase-A/B/C source-lock materialization | passed |
| Quantile artifact, calibration, ablation, v1/v2 comparison, cap and normal-turnover assertions | passed |
| Cash and adaptive-router degradation-path assertions | passed |
| Phase-A–D focused regression | `15 passed` |
| model-test runner and full-run preflight regression | `30 passed` |
| Phase-D CLI help and strict source-lock rejection | passed |
| Full repository regression | `214 passed` |

## Evidence readiness boundary

No real-market Phase-D performance claim is produced by this change. The
current checkout has no ready Phase-A/B source lock, so the strict Phase-D CLI
rejects it before fitting. Once source outputs are restored, the recorded
Phase-C boundary still applies: the legacy US Window 3B source needs a
verifiable `data.snapshot_sha256` and frozen snapshot; the CN_A full-scale
experiment is incomplete. Re-freeze the US inputs and complete CN_A, then materialize A →
B → C → D with the documented market-specific commands before judging
calibration, turnover, drawdown, tail-loss or promotion eligibility.
