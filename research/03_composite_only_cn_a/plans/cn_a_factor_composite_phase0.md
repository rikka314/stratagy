# CN_A Factor Composite Phase 0 Acceptance Record — 2026-08-22

## Scope

Phase 0 locks the CN_A Composite research boundary, frozen input sources,
benchmark policy, and execution-cost semantics. This phase is research-only and
does not train Composite, tune advisory rules, modify the production strategy,
or connect Streamlit to the new pipeline.

## Source lock

| Role | Source | Status | Symbols | Snapshot aggregate SHA-256 |
|---|---|---:|---:|---|
| Admission development | `full_cn_a_admission_60` | `ready` | 60 | `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058` |
| Formal confirmation | `full_cn_a_deans_60` | `ready` | 60 | `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058` |

The two sources have identical symbol ordering and identical snapshot aggregate
hashes. Their manifest and config hashes remain separately recorded in
`source_lock.json`:

- `full_cn_a_admission_60` manifest: `d3825b9f8c6fdccd12c85b865c93d3b8226b2965416175530180227fdf61447e`
- `full_cn_a_admission_60` config: `05d156abae46f5741cb85d26df00d59d6aa07dd430bc91d175a97b84bea43013`
- `full_cn_a_deans_60` manifest: `f46e4d677bbd051e91b27fd07625fa87f3b98ea9af45b28d67d4ef066e1d1aa`
- `full_cn_a_deans_60` config: `f045a85ee18ea7d0397862b7bcdab29c858fe353b0745357537f87d373c72896`

Both snapshots contain the required `date/open/high/low/close/volume` fields.
No duplicate dates, invalid numeric rows, or non-positive OHLC prices were
found. The raw snapshot rows span `1993-03-16` through `2026-08-17`; the
registered research manifest window is `2021-05-12` through `2026-08-17`, with
`2026-07-31` as the minimum required end date. The raw per-symbol business-day
gap counts are retained in `source_quality.json`; these counts represent
calendar gaps, not evidence that a symbol was incorrectly backfilled.

## Benchmark decision

The preferred CN_A market-native artifact `data/macro/cn_a_000300_daily.parquet`
is not present. It was not replaced with US `SPY`, another market's artifact, or
synthetic values.

The registered policy is therefore:

1. Prefer the frozen market-native `000300` artifact when it is available and
   passes its own hash, field, date, and coverage checks.
2. Until then, use only the explicit
   `frozen_universe_equal_weight_close_return` fallback.
3. Do not switch between the two sources implicitly.

The registered fallback is a policy registration only at this stage; no
benchmark artifact has been built or hash-verified yet. Its status is
`registered_policy_only`, so Phase 1 must build and validate the fallback before
consuming it. This is a benchmark availability gate for later factor work, not
a failure of the two frozen stock snapshots. The machine-readable lock records
`preferred_status=unavailable`, `fallback_status=registered_policy_only`, and
`fallback_is_implicit=false`.

## Execution contract

```text
commission_bps = 3
slippage_bps = 5
source_net_cost_treatment = source_net_no_recharge
ohlcv_cost_treatment = ohlcv_gross_charge_once
```

Existing `strategy_return` values are already net of source costs and must not
be charged again. Experiments reconstructed from OHLCV must calculate gross
returns and charge the 3 + 5 bps cost once.

## Acceptance checks

| Check | Result |
|---|---|
| Both source manifests and config snapshots present | PASS |
| Every manifest snapshot file present and hash/size matched | PASS |
| Snapshot aggregate hash recomputed | PASS |
| 60 unique symbols per source | PASS |
| Cross-source symbols match | PASS |
| Cross-source snapshot hashes match | PASS |
| Required fields and basic OHLCV quality | PASS |
| Preferred `000300` artifact | UNAVAILABLE |
| Registered fallback policy | PASS, policy-only registration |
| CN_A execution contract | PASS |
| Production impact | None |
| Streamlit impact | None |

## Decision

**Phase 0 source lock: accepted with a benchmark availability condition.**
The frozen source inputs are ready for later research, while the overall lock
status remains `pending` until a verified benchmark artifact exists. Phase 1/2
may only build and validate the explicitly registered equal-weight fallback, or
use a separately verified CN_A `000300` artifact. No model admission or
production authorization is implied by the `ready` source status.

Machine-readable outputs:

- `model-test/outputs/cn_a_factor_composite_source_lock/source_lock.json`
- `model-test/outputs/cn_a_factor_composite_source_lock/source_quality.json`
- `model-test/outputs/cn_a_factor_composite_source_lock/source_quality.md`
