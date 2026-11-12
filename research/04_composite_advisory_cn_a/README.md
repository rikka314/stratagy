# 04 · CN_A Composite Advisory

## Why this line started

After Composite-only became a strong CN_A research candidate, the next question was narrower: can additional expert/context advisories reduce risk without taking control away from Composite or opening positions that Composite did not authorize?

## Frozen scope

- Market: CN_A only; no shared weights across markets.
- Base model: Phase 4/6 `composite_only` output.
- Policies: `composite_only`, trend, reversion, relative strength, macro cap, combined advisory, and cash controls.
- Semantics: long-only; advisory may maintain or reduce the Composite base position, never increase it; Composite zero cannot open a position.
- Safety: final position is bounded, daily change is limited, missing context has an explicit fallback, and reason codes are auditable.
- Real-data gate: Sharpe decline no more than 10%, at least one risk improvement, turnover at most 30%, and acceptable fallback quality.

## Research flow

1. Freeze the Composite baseline, factor panel, advisory rules, thresholds, and gate.
2. Validate the immutable decision contract and safety bounds with unit tests.
3. Merge the baseline and market-native factors without future leakage.
4. Run each policy as a separate ablation and calculate net performance, turnover, and risk.
5. Audit reason codes, fallback rate, advisory multiplier, and average reduction.
6. Mark the real-data gate only when `ablation_metrics.csv`, `decision_audit.csv`, `quality_report.json`, and `advisory_manifest.json` agree.

## Key decisions and ideas

- Composite owns direction; advisory is a conservative risk overlay.
- Multiple advisories combine by the minimum multiplier, preserving the safest active constraint.
- A missing context field is visible fallback behavior, not a silent neutral value.
- Framework tests prove contract safety, not out-of-sample benefit.

## Result and current status

The framework and unit tests are complete: the immutable contract, four advisory families, fallback rules, and safety boundaries are covered. The current record is **not** a claim that a real-data advisory policy passed. Unless the local advisory output manifest and ablation artifacts are present and validated, the line remains `framework_complete_pending_real_data_gate`.

## Gate and stop conditions

Status: `framework_complete_pending_real_data_gate`. If no policy meets all real-data criteria, retain `composite_only` as the recommendation and record the advisory result as a negative ablation. Do not fold advisory into Phase 6 Composite-only evidence retroactively.

## Problems and future remedies

- The framework still needs a valid real-data run and independent review of its fallback and turnover audit.
- A future extension may refine thresholds or add experts only under a new preregistered ablation; it must not tune against a favorable test result and relabel it as the frozen gate.

## Source files

- Contract: [`composite-advisory-research.md`](../../document/interfaces/composite-advisory-research.md)
- Acceptance/framework record: [`cn_a_factor_composite_phase5.md`](../../document/acceptance/cn_a_factor_composite_phase5.md)
- Config: `model-test/configs/composite_advisory_cn_a.json`, `composite_advisory_phase0_1.json`
- Runner: `model-test/run_cn_a_composite_advisory.py`, `run_composite_advisory_phase1.py`
- Research modules: `core/composite_advisory_cn_a.py`, `core/composite_advisory.py`, `core/composite_advisory_config.py`
- Tests: `tests/test_composite_advisory_cn_a.py`, `tests/test_composite_advisory.py`, `tests/test_composite_advisory_config.py`
- Expected evidence root: `model-test/outputs/composite_advisory_cn_a/`

## Reproduction boundary

A new run must emit and validate the manifest plus all ablation/audit artifacts. Missing output is `pending`, never a passed advisory result.
