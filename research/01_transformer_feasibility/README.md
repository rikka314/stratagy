# 01 · Transformer Feasibility and State Retrieval

## Why this line started

After the expert baseline and adaptive work, the question was whether a learned state representation could retrieve historical situations whose expert utility would improve the next decision. The line intentionally tested feasibility before allowing a larger Transformer training effort.

## Frozen scope

- Primary completed evidence: US; CN_A W19 is a separate pending window.
- Retrieval uses strictly earlier memory rows and purged walk-forward splits.
- W16-W18 executes five-day holding windows with next-day effectiveness and source-net returns.
- v3 Phase 1 uses train-only scaling/PCA and deterministic random neighbors on Validation roles; duplicate split signatures are deduplicated for inference.
- The primary value gate is query-selected expert utility/regret, not visual similarity or neighbor consistency alone.

## Research flow

1. Freeze exact-daily expert artifacts, adaptive artifacts, data snapshot, code lock, and manifests.
2. Build the state panel and walk-forward splits with leakage checks.
3. Run v2 retrieval and exact five-day replay; independently rehash and rebuild summaries.
4. Run v3 non-deep-learning baselines: B01 single-day PCA, B02 20-day summary PCA, B03 random neighbors.
5. Compare utility consistency, query-selected utility, regret, coverage, and bootstrap evidence.
6. Apply the preregistered stop/admission decision before considering Transformer training.

## Key decisions and ideas

- Engineering completeness is separate from research value.
- A more internally consistent neighbor group is not useful if it consistently selects worse experts.
- Thresholds, windows, costs, and test periods cannot be changed after seeing the outcome to manufacture admission.
- All production and Streamlit behavior remains unchanged unless the value gate is passed.

## Result

W16-W18 were engineering-accepted: all 11,520 windows were audited, exact-daily artifacts and manifests matched, and the primary `state_match_balanced` matched coverage was 0% in all four folds against a frozen 30% minimum. W20 was therefore not admitted.

In v3 Phase 1, B01/B02 improved utility consistency over random by +0.017500/+0.020940 with one-sided p=0.000999, but query-selected utility was worse than random by -0.003283/-0.005354 and regret increased. Phase 2 concluded that state similarity did not predict expert utility and issued STOP before Transformer training.

## Gate and current status

Status: `stopped`. This is a complete negative feasibility study, not evidence that Transformer effectiveness was demonstrated.

## Problems and future remedies

- The representation captures similarity that is misaligned with decision utility.
- A future study would need a predeclared label/stride reconstruction or a different utility-aligned state target, followed by a new query utility/regret gate. It must be a new study, not a post-hoc rescue of this result.

## Source files

- v2 acceptance: [`post_gate2_transformer_state_w16_w18_20260820.md`](../../document/acceptance/post_gate2_transformer_state_w16_w18_20260820.md)
- v3 protocol: [`transformer_state_v3_research_protocol.md`](../../document/transformer_state_v3_research_protocol.md)
- v3 baseline acceptance: [`transformer_state_v3_phase1_baselines_20260820.md`](../../document/acceptance/transformer_state_v3_phase1_baselines_20260820.md)
- v3 diagnosis: [`phase1_diagnostic_report.md`](../../document/phase1_diagnostic_report.md)
- Stop decision: [`transformer_state_v3_phase2_completion.md`](../../document/transformer_state_v3_phase2_completion.md)
- Configs: `model-test/configs/transformer_state_us.json`, `transformer_state_cn_a.json`, `transformer_state_v3_us.json`
- Runners: `model-test/run_transformer_state.py`, `run_baseline_phase1.py`, `run_diagnostic_phase2.py`
- Evidence roots: `model-test/outputs/transformer_state_us/`, `transformer_state_cn_a/`, `transformer_state_v3_us/`

## Reproduction boundary

The frozen output directories are Git-ignored and must be supplied by the local evidence archive. Missing artifacts are `pending`, not a reason to invent a successful result.
