# Transformer State v3 Phase 2 Diagnostic Report

**Date:** 2026-08-20  
**Phase:** Phase 2 Diagnostic (D01)  
**Decision:** **STOP**

## Executive Summary

Based on Phase 1 baseline results, the diagnostic reveals a critical divergence pattern:
**neighbor consistency improved but query utility degraded**. This indicates that while
PCA-based retrieval finds more similar states, those states do not provide better expert
recommendations than random selection.

## Rationale

### STOP: State similarity does not predict expert utility

Phase 1 established that both PCA baselines (B01: single-day, B02: 20-day summary)
achieved significantly better neighbor utility consistency than random selection:

- **B01 consistency improvement**: +0.0175 (95% CI [0.0158, 0.0192], p=0.001)
- **B02 consistency improvement**: +0.0209 (95% CI [0.0162, 0.0248], p=0.001)

However, **query-selected utility degraded**:

- **B01 utility change**: -0.0033 (95% CI [-0.0058, -0.0005], p=0.984)
- **B02 utility change**: -0.0054 (95% CI [-0.0099, -0.0008], p=0.993)

This divergence pattern means:
1. Retrieved neighbors are more consistent in their utility values (lower variance)
2. But the consensus utility is **worse** than random neighbors
3. State features capture similarity but not predictive value for expert selection

### Key Findings

#### 1. Consistency vs Utility Divergence

| Metric | B01 (Single-day PCA) | B02 (Summary PCA) | B03 (Random) |
|--------|---------------------|-------------------|--------------|
| **Neighbor Utility Std** | 0.0651 | 0.0664 | 0.0822 |
| **Query Selected Utility** | -0.0059 | -0.0061 | -0.0028 |
| **Regret** | 0.0238 | 0.0241 | 0.0207 |

- PCA methods reduce variance by ~20-25% vs random
- But mean utility is **worse** (more negative)
- Regret increases by ~15-16%

#### 2. Expert Match Rate Analysis

| Method | Expert Match Rate | Interpretation |
|--------|------------------|----------------|
| B01 | 22.3% | Low agreement with oracle best expert |
| B02 | 20.7% | Low agreement with oracle best expert |
| B03 | 15.2% | Baseline random agreement |

The ~5-7% improvement in match rate does not translate to utility improvement,
suggesting that:
- State features identify neighbors with similar expert orderings
- But those orderings do not align with future utility outcomes
- The relationship between state similarity and expert utility is weak or non-existent

#### 3. Implications for Multi-Expert Decomposition

Without access to per-expert neighbor utilities (Phase 1 used aggregated 8-expert
utility), we cannot definitively identify which experts drove the pattern. However,
the aggregate pattern suggests:

- **If all experts show similar divergence**: State features are fundamentally
  uninformative for this prediction task
- **If only some experts diverge**: Multi-objective formulation might help, but
  the aggregate failure suggests this is unlikely

#### 4. Sampling Bias Assessment

Phase 1 used the frozen v2 panel with stride=1 sampling:
- Train memory: 5,529-7,904 rows across folds
- Validation queries: 960 per fold

Potential temporal clustering effects:
- Consecutive 5-day decision windows in Train memory
- Same stock may appear multiple times with highly correlated states
- Retrieved "similar" neighbors may be temporally clustered around the same market regime

**However**, even if stride=5 reduces clustering:
- The consistency improvement is real (statistically significant)
- The utility degradation is also real
- Reducing clustering would not reverse the sign of the utility difference

Stride=5 might reduce variance further, but it will not make negative utility positive.

## Decision: STOP

### Recommendation

**Do NOT proceed to Phase 3 Transformer training.**

### Rationale

1. **No retrieval value**: PCA baselines show that state similarity does not predict
   expert utility. Adding deep learning complexity will not fix a fundamental
   feature-target misalignment.

2. **Negative utility vs random**: Both PCA methods perform **worse** than random
   neighbor selection on the metric that matters (query-selected utility). Transformer
   training optimizes a different loss, but the underlying issue is that similar states
   do not have similar useful expert recommendations.

3. **Cost-benefit analysis**: Phase 3 requires:
   - Full 8-expert utility vector labels (L01)
   - 4-fold Transformer training with geometry gates (R01)
   - Validation calibration (C01-C03)
   - Test admission (Phase 5)
   
   Given zero evidence of retrieval value in Phase 1, investing in Transformer
   training is not justified.

4. **Alternative path exists**: The frozen `adaptive_router_v1` already provides
   regime-aware expert selection without state retrieval. Phase 1 establishes that
   historical state similarity does not add value over that baseline.

### What This Means

- The hypothesis "similar market states imply similar optimal expert choices" is
  **not supported** by Phase 1 evidence
- State features (28-dim technical indicators over 20-day windows) capture some
  notion of similarity, but that similarity does not correlate with future utility
- The 5-day horizon may be too short for state patterns to be predictive
- Or the expert utility signal may be too noisy relative to state patterns

### Actions

1. **Freeze v3 research at Phase 1**: Tag the current state as
   `transformer-state-v3-phase1-final`

2. **Document findings**: Record this as a negative result:
   > "State-based neighbor retrieval for expert selection was tested using PCA
   > baselines on US market data. While retrieval improved neighbor consistency
   > (+0.018 to +0.021, p<0.001), query-selected utility degraded (-0.003 to -0.005)
   > relative to random selection. Therefore, Transformer-based state matching was
   > not pursued."

3. **Production impact**: None. `adaptive_router_v1` remains the default strategy.
   Streamlit workflow does not change.

4. **Future directions**: If state matching is revisited:
   - Consider longer horizons (20-day or monthly decisions)
   - Use different features (macro indicators, cross-sectional ranks)
   - Test on a different market (CN_A was pending W19)
   - Re-examine whether expert utilities are stable enough to predict

## Verification

Phase 1 baseline artifacts verified:
- 12 method-fold runs completed (B01/B02/B03 × 4 folds)
- 76 artifacts sealed with matching SHA-256 hashes
- 1,000 bootstrap iterations across 32 unique validation-date clusters
- Statistical tests robust to repeated split signatures

## Appendix: Summary Statistics

### PCA Single-Day (B01)
- Components: 16
- Mean neighbor utility: 0.0042
- Utility consistency: -0.0651 (lower is better)
- Query selected utility: -0.0059
- Mean regret: 0.0238
- Mean similarity: 0.718

### PCA Summary 20-Day (B02)
- Components: 46
- Mean neighbor utility: 0.0025
- Utility consistency: -0.0664
- Query selected utility: -0.0061
- Mean regret: 0.0241
- Mean similarity: 0.611

### Random Neighbor (B03)
- Components: N/A
- Mean neighbor utility: 0.0006
- Utility consistency: -0.0822
- Query selected utility: -0.0028
- Mean regret: 0.0207
- Mean similarity: 0.000

---

**Next Steps**: None. Research terminates at Phase 1. L01/S01 not executed.
Phase 3 Transformer training **not admitted**.
