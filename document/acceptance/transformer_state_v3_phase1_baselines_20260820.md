# Transformer State v3 Phase 1 Baseline Acceptance

Date: 2026-08-20  
Market: US  
Decision: **Formal consistency gate passed; Phase 2 diagnostic admitted; Phase 3 training not yet admitted**

## Scope and outcome

Phase 1 ran the preregistered non-deep-learning baselines against the frozen
US Transformer-state v2 sequence panel:

- B01: Train-only scaler and PCA on the decision day's 28 features.
- B02: Train-only scaler and PCA on seven 20-day summary operators.
- B03: deterministic random Top-15 neighbors.

The run consumed Validation roles only. It did not inspect or execute the new
v3 Test window. All outputs were written under the Git-ignored v3 directory:

```text
model-test/outputs/transformer_state_v3_us/baseline_artifacts/
```

## Source lock and integration corrections

The original Phase 1 CLI unit tests did not cover the repository artifact
contract. Before the run, the integration path was corrected to:

- read `state_sequence_panel.parquet`, `state_feature_schema.json`, and
  `transformer_state_walk_forward_splits.csv` from the immutable
  `transformer_state_us/` output, rather than the Phase-B expert panel;
- verify the frozen `state_panel_manifest.json` and all referenced artifact
  SHA-256 hashes;
- select Train and Validation rows from `split_memberships_json`, not
  nonexistent positional split columns;
- consume the real `sequence_values` and eight-expert
  `expert_utilities_json` schema;
- apply Train-only mean imputation for missing features before scaling/PCA;
- persist query-level utility, regret, coverage-quality, statistical-test, and
  evidence artifacts.

Frozen v2 panel manifest SHA-256:
`bc791ff9a0fec54d049d6514ad6e890ac9f1bd72d146c05830af3e72632802b0`.

## Run command

```powershell
.\.venv\Scripts\python.exe .\model-test\run_baseline_phase1.py `
  --config .\model-test\configs\transformer_state_v3_us.json
```

The run completed all `3 methods × 4 folds = 12` method-fold jobs. Each job
contains 960 Validation queries, 14,400 Top-15 neighbor rows, a ten-point
coverage-quality curve, embeddings, metadata, and query metrics. The evidence
manifest sealed 76 artifacts; independent rehashing found zero mismatches.

## Main results

Four fold IDs exist, but `wf_02`, `wf_03`, and `wf_04` share the same
Train/Validation definition. Statistical inference therefore de-duplicated
identical split signatures and used 32 unique validation-date clusters with
1,920 paired queries.

| Method | PCA components | Utility consistency | Query-selected utility | Regret |
|---|---:|---:|---:|---:|
| B01 single day | 16 | -0.065086 | -0.005851 | 0.023804 |
| B02 20-day summary | 49 | -0.066369 | -0.006135 | 0.024087 |
| B03 random | n/a | -0.082239 | -0.002756 | 0.020709 |

Higher utility consistency is better; lower regret is better.

Paired date-cluster bootstrap, 1,000 iterations:

| Comparison vs B03 | Metric | Difference | 95% CI | One-sided p |
|---|---|---:|---:|---:|
| B01 | Utility consistency | +0.017500 | [0.015764, 0.019229] | 0.000999 |
| B02 | Utility consistency | +0.020940 | [0.016201, 0.024814] | 0.000999 |
| B01 | Query-selected utility | -0.003283 | [-0.005827, -0.000461] | 0.984016 |
| B02 | Query-selected utility | -0.005354 | [-0.009854, -0.000783] | 0.993007 |

## Research decision

The preregistered Phase 1 stopping rule is based on neighbor utility
consistency. Both PCA baselines beat random under that rule, so the study does
not stop at Phase 1.

However, the retrieved neighborhoods did not produce better Validation expert
choices: B01 was significantly worse than random on realized query utility,
and B02 showed no positive utility evidence. Match score was also not a stable
quality proxy across the two unique validation designs.

Therefore the allowed next step is Phase 2 label/stride reconstruction as a
diagnostic. This result does not admit Phase 3 Transformer training, does not
establish state-retrieval value, and does not change any production strategy or
Streamlit behavior. Before Phase 3, the rebuilt label/stride experiment must
show positive Validation query utility or lower regret relative to B03 under a
predeclared gate.

## Verification

```text
Phase 1 targeted tests:       13 passed
Transformer-adjacent tests:   78 passed, 2 PyTorch warnings
Full repository tests:       323 passed, 2 PyTorch warnings
Artifact rehash:              76/76 matched
Method-fold shape audit:      12/12 passed
```

The two warnings are the existing PyTorch nested-tensor notices caused by
`norm_first=True`; Phase 1 itself does not use PyTorch.
