# Transformer State v3 Research Protocol

> Version: 3.0.0
> Created: 2026-08-20
> Market: US (primary), CN_A (follow-on)
> Status: Active

---

## Protocol Principles

### 1. One-Shot Test Revelation

**Rule**: The Test window (2026-06-01 to 2026-07-31) will be evaluated **exactly once** after all hyperparameters, thresholds, and model choices are frozen based on Train/Validation.

**Forbidden**:
- Adjusting thresholds after seeing Test coverage
- Re-running Test with different configurations
- Cherry-picking random seeds based on Test results
- Using Test performance to select between model variants

**Enforcement**: All Test decisions will be logged with timestamps. Any Test query made before the final frozen run will invalidate the admission.

---

### 2. v2 Immutability

**Rule**: All v2/W18 outputs (manifests, artifacts, reports, acceptance records) are **frozen and immutable**.

**Frozen artifacts**:
- `transformer_state_us/` outputs (W13-W18)
- All manifest SHA-256 hashes
- `post_gate2_transformer_state_w16_w18_20260820.md` acceptance
- Git tag: `transformer-state-v2-final`

**Forbidden**:
- Modifying v2 manifests or artifacts
- Re-interpreting v2 results with new thresholds
- Replacing v2 coverage with v3 results in the same Test window
- Claiming v2 was "fixed" by v3 changes

---

### 3. Baseline First

**Rule**: Before training any Transformer model, establish non-deep-learning baselines and verify that "state similarity retrieval" adds value.

**Required baselines**:
1. **B01 - PCA Single Day**: Last-day features → Train-only PCA → cosine retrieval
2. **B02 - PCA Summary**: 20-day statistical summary → Train-only PCA → cosine retrieval
3. **B03 - Random Neighbor**: Random selection from Train memory (null hypothesis)

**Stop condition**: If B01/B02 do not show neighbor utility consistency superior to B03 (p < 0.05, bootstrap 1000 iterations), **stop the entire research** and re-evaluate the product hypothesis.

**Continue condition**: If B01 or B02 shows value but Transformer does not improve upon them by >10% Validation regret, **downgrade to PCA baseline** as the primary method.

---

### 4. Geometry Gate

**Rule**: Every fold's Train embedding must pass geometry quality checks before entering the retrieval phase.

**Required checks**:
- Effective rank ≥ 4.0 / 16
- PC1 variance share ≤ 70%
- Minimum dimension std ≥ 0.01
- Train→Validation centroid L2 shift < 0.5

**Failure handling**: If a fold fails geometry gate, mark it as `geometry_collapsed` and exclude from retrieval. If >50% of folds fail, **stop the experiment** and either:
- Adjust loss weights (pre-registered grid only)
- Apply Train-only whitening as a fallback
- Downgrade to PCA baseline

---

### 5. Admission Fail-Closed

**Rule**: All admission gates must pass for v3 to enter W20. Any single failure results in `not_ready`.

**Admission gates** (all required):
- ✅ Baseline comparison: Transformer > PCA (if PCA is valid)
- ✅ Geometry gate: ≥3/4 folds pass
- ✅ Coverage: ≥30% per fold (all 4 folds must pass)
- ✅ Matched utility: > adaptive baseline + 0.5% annualized
- ✅ Drawdown: < adaptive × 1.2
- ✅ Turnover: < adaptive × 1.5
- ✅ Symbol breadth: ≥40/60 symbols in Test
- ✅ Hash consistency: All source/code/artifact hashes match

**No exceptions**: Cannot override a failed gate with manual interpretation.

---

## v3 Configuration Summary

### Label Schema Changes

| Aspect | v2 | v3 |
|---|---|---|
| Expert labels | Winner class only | Full 8-expert utility vector |
| Ambiguous states | Deleted (17,000/22,604) | Preserved with soft labels |
| Margin weighting | No | Yes (temperature = 0.5) |
| Availability mask | Implicit | Explicit per expert per date |
| Cash utility | Inferred | Always present and available |

**Schema**: `state_label_panel_v3.parquet`

Columns: `date`, `symbol`, `market`, `sequence_id`, `utility_naive`, `utility_drift`, `utility_sm`, `utility_fsm`, `utility_best_search`, `utility_ml_filter`, `utility_adaptive_router`, `utility_cash`, `availability_*` (8 bools), `best_expert_5d` (legacy), `utility_margin`, `utility_dispersion`, `is_ambiguous`, `label_quality`

---

### Sample Strategy Changes

| Aspect | v2 | v3 |
|---|---|---|
| Sequence stride | 1 day (consecutive overlap) | 5 days (aligned with holding period) |
| Train Top-1 max similarity | ~0.999 (q75), ~0.9996 (q90) | Expected < 0.995 (reduced overlap) |
| Memory rows (fold wf_02) | 1,901 | ~380 (5× reduction, but higher independence) |

**Rationale**: Consecutive 20-day windows share 19/20 days, causing Train strictly-prior Top-1 to concentrate near 1.0. Stride=5 reduces this overlap while maintaining execution frequency alignment.

---

### Loss Function Changes

| Component | v2 | v3 |
|---|---|---|
| Primary | CrossEntropy(best_expert) | HuberLoss(U_pred, U_true, δ=0.5) |
| Auxiliary | Margin regression (top1-top2) | PairwiseRankingLoss(margin=0.1) |
| Regularization | None | VarianceFloor(min_var=0.01) + CovariancePenalty(off_diag=0.1) |

**Weights**: `λ_u=1.0`, `λ_r=1.0`, `λ_v=0.5`, `λ_cov=0.1` (validated on grid)

**Objective alignment**: v2 trained for classification, v3 trains for utility prediction + ranking + geometry preservation, directly supporting retrieval tasks.

---

### Retrieval Changes

| Aspect | v2 | v3 |
|---|---|---|
| Calibration | Train→prior Train Top-1 | Validation→Train Top-5 mean |
| Primary score | max(s₁, ..., s₁₅) | mean(s₁, ..., s₅) |
| Threshold source | Train self-query q75 | Validation query calibration |
| Coverage target | 30% (but q75 ≈ 25% acceptance) | Val: 35-40%, Test: ≥30% |
| Neighbor weight | max(cosine, 0) | softmax(cosine / T), T=0.05 |
| Utility aggregation | Winner group vote | Full vector weighted mean |
| ESS gate | No | Yes, ESS ≥ 5 |
| Uncertainty | No | Yes, γ=0.5 |

**Rationale**: v2's calibration mismatch (Train→prior Train vs Test→full Train) and Top-1 sensitivity to outliers caused structural 0% coverage. v3 aligns calibration forms and uses Top-5 mean for stability.

---

### Test Window

| Window | Train/Val | Test | Unseen |
|---|---|---|---|
| v2 | 2022-01-01 ~ 2025-10-31 | 2025-11-01 ~ 2026-02-28 | No (used for diagnosis) |
| v3 | 2022-01-01 ~ 2026-05-31 | 2026-06-01 ~ 2026-07-31 | Yes (never observed) |

**Data quality pre-check**: Before finalizing, audit that 2026-06-01~07-31 has:
- Complete OHLCV for all 60 symbols
- No missing dates beyond normal holidays
- Consistent regime distribution (not all extreme crash/rally)

---

## Execution Checkpoints

### Checkpoint 0: Governance (Day 1-2)

**Deliverables**:
- [x] v2/W18 frozen and tagged
- [x] v3 config created (`transformer_state_v3_us.json`)
- [x] v3 output directory created
- [x] Research protocol documented (this file)
- [x] Git branch: `transformer-state-v3`

**Verification**: `git log --oneline -1` shows v3 docs committed, `git tag` shows `transformer-state-v2-final`

---

### Checkpoint 1: Baseline (Day 3-7)

**Deliverables**:
- [ ] B01 PCA single-day baseline completed
- [ ] B02 PCA summary baseline completed
- [ ] B03 random neighbor baseline completed
- [ ] `baseline_comparison_report.md` generated
- [ ] Decision: Continue Transformer / Downgrade to PCA / Stop research

**Success criteria**:
- B01 or B02 neighbor utility consistency > B03 (p < 0.05)
- Bootstrap 95% CI does not include zero improvement

**Stop trigger**: If baselines fail, escalate to user for product hypothesis review.

---

### Checkpoint 2: Label (Day 8-11)

**Deliverables**:
- [ ] `state_label_panel_v3.parquet` generated
- [ ] All 8 experts have finite utility values
- [ ] Ambiguous ratio audited and recorded
- [ ] Stride=5 vs stride=1 comparison completed
- [ ] Selected stride strategy frozen in config

**Verification**:
- Load parquet and check schema
- Count non-null utility values per expert
- Compare Train Top-1 similarity distribution: v3 < v2

---

### Checkpoint 3: Model (Day 12-18)

**Deliverables**:
- [ ] Loss ablation (R01-A/B/C/D) completed
- [ ] 4 folds trained with selected loss
- [ ] Geometry gate results for all folds
- [ ] `geometry_report_v3.csv` generated
- [ ] At least 3/4 folds pass geometry gate

**Stop trigger**: If >50% folds fail geometry gate, **stop** and downgrade to PCA.

**Verification**: Read `geometry_report_v3.csv` and confirm effective_rank ≥ 4.0, PC1 ≤ 70%.

---

### Checkpoint 4: Calibration (Day 19-22)

**Deliverables**:
- [ ] Validation→Train memory calibration completed
- [ ] Primary score selected (Top-5 mean recommended)
- [ ] Softmax temperature selected (T ∈ [0.01, 0.05, 0.1])
- [ ] Threshold quantile frozen (achieves Val coverage 35-40%)
- [ ] Validation matched utility > fallback baseline

**Stop trigger**: If Validation matched utility < fallback, **stop** and record failure.

**Verification**: Read `state_retrieval_calibration_v3.csv` and confirm coverage in [0.35, 0.40], matched utility > adaptive.

---

### Checkpoint 5: Test (Day 23-25)

**Deliverables**:
- [ ] Test decisions generated (once, final)
- [ ] Execution daily audit completed
- [ ] Summary regenerated and hash-verified
- [ ] All admission gates evaluated
- [ ] `transformer_state_v3_evidence_manifest.json` generated

**Admission result**:
- `ready` if all gates pass
- `not_ready` if any gate fails

**No retry**: Test result is final, no parameter adjustment allowed.

---

## CN_A W19 Handling

### Decision: W19-C (Wait for US v3)

**Rationale**: Preserve CN's independent validation value by using the same frozen v3 protocol after US passes.

**Workflow**:
1. US v3 completes Checkpoint 5 with `ready` status
2. Freeze all v3 parameters (same config, same loss weights, same thresholds)
3. CN runs with identical protocol, only changing `market: "CN_A"` and data sources
4. CN Test is revealed **once**
5. CN results are **never** used to adjust US v3

**Fallback**: If US v3 fails, run W19-B (diagnostic only) to verify if root causes are cross-market.

---

## Pre-Registered Failure Responses

### Failure 1: Baseline > Transformer

**If**: B01 or B02 Validation regret < Transformer Validation regret by >10%

**Response**: 
- Approve PCA baseline for admission (if it passes coverage/utility gates)
- Archive Transformer v3 as "complexity not justified"
- Update production recommendation: Use PCA method

**Reason**: Simplicity wins when equivalent or better.

---

### Failure 2: Geometry Collapse

**If**: >50% folds fail geometry gate after loss weight grid exhausted

**Response**:
- Try Train-only whitening as last resort
- If still fails, downgrade to PCA
- Record "Transformer fails to learn multi-dimensional representations at current data scale"

**Reason**:塌缩表示无法支持可靠检索。

---

### Failure 3: Validation Coverage/Utility Mismatch

**If**: No threshold achieves both coverage ≥35% AND matched utility > fallback

**Response**:
- Stop admission attempt
- Investigate memory label quality and same-symbol memory alternative
- If no solution, conclude "state matching does not improve expert selection"

**Reason**: Coverage without utility improvement is meaningless.

---

### Failure 4: Test Admission Rejection

**If**: Any admission gate fails on Test

**Response**:
- Record failure evidence in manifest
- Do **not** retry with adjusted parameters
- Preserve `adaptive_router_v1` as production default
- Conclude: "Transformer state matching unproven at current data/expert structure"

**Reason**: 研究诚信要求接受阴性结果。

---

## Contact & Escalation

**Project lead**: [User]
**Research executor**: Claude Code (this session)
**Checkpoint reviewer**: [User]

**Escalation triggers**:
- Any baseline failure (Checkpoint 1)
- >50% geometry gate failure (Checkpoint 3)
- Validation coverage/utility mismatch (Checkpoint 4)
- Test admission failure (Checkpoint 5)

**Decision authority**: User must approve any deviation from this protocol.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 3.0.0 | 2026-08-20 | Initial v3 protocol established |

---

**Protocol Status**: Active
**Next Checkpoint**: Checkpoint 1 (Baseline)
**Expected Completion**: 2026-10-01 (6 weeks from start)
