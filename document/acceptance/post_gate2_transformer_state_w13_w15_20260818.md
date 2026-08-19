# Post-Gate-2 Transformer-state v2 W13-W15 acceptance

Date: 2026-08-18

Scope: research-only `model-test` implementation. Existing v1 W11 remains US
`1/4`, CN_A `2/4`; W12 remains blocked. No Streamlit/default-strategy change.

## Decision

| Window | Result | Evidence |
|---|---|---|
| W13 | implementation complete; CN_A ready, US blocked | CN_A source lock revalidates every configured hash, market, snapshot, Cash, adaptive control, rank-1 fallback and exact daily position source. US fails closed because 58 non-Cash Phase-B experts have interval-trade reconstruction rather than exact daily `target_position`/turnover. |
| W14 | implementation complete; CN_A ready, US blocked | CN_A emitted the five-day label panel, max-20-day sequence panel and four protected splits. US emits blocked manifests and no new valid W14 evidence. |
| W15 | implementation complete; runtime/upstream blocked | The encoder, fold-local fit, metrics/schema/artifact runner and fail-closed tests are implemented. CN_A has four `unavailable: pytorch_not_installed` folds; US cannot enter W15 while W13/W14 are blocked. No checkpoint was fabricated, so W16 remains blocked. |

The plan requires both markets to be ready before W13/W14 can be accepted as a
whole. Therefore this record does not mark those windows globally complete.

## W13 source evidence

- CN_A fallback remains `sm -> sm`, rank `1`, score
  `66.06666666666666`, valid `60`; all 60 artifacts contain native daily
  `target_position` evidence.
- US fallback remains frozen as `sm_bayesian -> best_search`, but its 58
  non-Cash artifacts expose interval entries/exits rather than an exact daily
  position/turnover path. Reconstructing binary holding intervals loses
  within-trade size changes: for example, AAPL `best_search` reconstructed
  turnover totals `31.0`, while source `trades.csv` reports `39.38`.
- Because W14 utility includes `0.1 * future_turnover`, that mismatch can alter
  `best_expert_5d`. US source, panel and model manifests are therefore
  `blocked`; the earlier reconstructed US panel is explicitly invalidated.
- The source manifest recomputes every snapshot CSV hash/size and aggregate,
  and requires exact unique daily dates aligned with source returns.
- It also records SHA-256 for the full config, config snapshot and all five
  executed W13-W15 modules, including `expert_panel.py` and `moe_baseline.py`.
  A dirty Git suffix alone is not treated as a reproducible code lock. The
  final aggregate code lock is
  `9afd6f2acb57db11667e5a35d301a9c3bb52e393dd15c74496fbbb6a93363e1b`.

## W14 panel evidence

Only CN_A has admissible W14 output:

| Market | State rows | Expert-label rows | Complete sequences | Features | Splits | Status |
|---|---:|---:|---:|---:|---:|---|
| US | — | — | — | — | — | blocked: exact daily execution source missing |
| CN_A | 23,238 | 181,440 | 22,098 | 28 | 4 | ready |

CN_A split role sample counts:

- `wf_01`: train 5,033 / validation 960 / test 940
- `wf_02`: train 7,424 / validation 960 / test 960
- `wf_03`: train 7,424 / validation 960 / test 960
- `wf_04`: train 7,424 / validation 960 / test 954

The union of all 160 legacy W11 test dates is forbidden in every v2 train and
validation membership. To retain that isolation, train/validation sources are
frozen as `wf_01 -> wf_01`, `wf_02 -> wf_02`, `wf_03 -> wf_02`, and
`wf_04 -> wf_02`; the four original test windows remain unchanged. Every
train-to-validation and validation-to-test boundary has at least 20 intervening
trading days (actual gaps: `40/40`, `40/40`, `40/80`, `40/120`).

Every membership additionally requires the 20-day sequence start, decision
date and full five-day label end to remain in the same role. Labels use the
next five complete source-net `strategy_return`/turnover rows only; source
returns are not charged again. Same-day and future dates are excluded from the
historical-memory eligibility helper.

Final manifest SHA-256 values:

- CN_A W13: `26d023d79dbab86a4f7b2d9f5a2554f3ea2a67cc03c3f57af2077e4d45f0ba28`
- CN_A W14: `4ddb7d149f5eb9e934f87d190d931cb09095447a5f184b11039645d47a471667`
- CN_A W15 unavailable: `411e92031bbb6979ede03c8622488640cc5c28cdd7961d6a571d220af20f1a81`
- US W13 blocked: `9023cf4a2d947bb6dc8f30feaeadb70cabfad57619a88a7ec57eac8a3c8bc420`
- US W14 blocked: `aabfd4437c47fe0c548ac2909e68dad486d49b196a17484e3cb8bf1c32208910`
- US W15 blocked: `65c56fc627838e216a259d55fe01d817daedc8927c4a86b3707ac4606e2e5a5b`

## W15 runtime evidence

The implementation provides:

- fold-local train scaler with an appended missingness mask;
- linear projection, sinusoidal positional encoding, small encoder-only
  Transformer, pooled embedding, classifier and utility-margin head;
- preregistered 10/20-day and 1/2-layer candidates selected only on validation;
- no test argument in `fit_transformer_fold`;
- schema fail-closed checks for `model_input`, future/outcome fields and missing
  metadata;
- bounded cosine-collapse sampling, majority/Cash-baseline checks and true
  top-expert utility regret;
- fold-local regime coverage and top-1 accuracy by observed regime;
- per-fold schema, train/validation metrics, training log and manifest.

The CN_A model command returns the intentional unavailable-runtime code `3`.
All four folds have reason `pytorch_not_installed`; there is no
`transformer_encoder.pt`. The US source command stops earlier with code `2`
and writes blocked W13/W14/W15 manifests.

## Tests

Targeted W13-W15 contract suite:

```text
30 passed, 1 skipped
```

Full repository regression suite:

```text
263 passed, 1 skipped
```

The skipped case is the optional real-PyTorch tiny fit. Non-PyTorch tests cover
feature leakage rejection, exact-daily-source enforcement, label completeness,
legacy-test isolation, protection gaps, sequence chronology, role boundaries,
historical-memory filtering, fold-local scaling, no-test fit API,
serialization, collapse/baseline rejection and missing-runtime behavior.

## Stop condition

W16 must not start until both blockers are resolved and independently rerun:

1. regenerate the US Phase-B source from exact daily target positions and
   turnover, then obtain ready W13/W14 manifests;
2. explicitly authorize/install a compatible PyTorch runtime, then produce four
   ready W15 checkpoints per market whose hashes match their fold manifests.

No alternative model, interval-trade approximation or cross-market artifact
may replace either blocked dependency.
