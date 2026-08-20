# Phase 0 Diagnostic Report

**Generated**: 2026-08-20 23:39:52

---

## P0.1: Adaptive Router Baseline

**Model**: rsm_adaptive_v1

| Metric | Value | Target | Pass |
|--------|-------|--------|------|
| Sharpe Ratio | 0.271 | > 0.5 | FAIL |
| Max Drawdown | -28.4% | > -15% | FAIL |
| Success Rate | 100.0% | > 55% | PASS |

**Gates Passed**: 1/3

**P0.1 Decision**: `PHASE_1_2`

---

## P0.2: Expert Homogeneity Audit

**Number of Experts Analyzed**: 9

**Average Similarity**: -0.045
**Maximum Similarity**: 0.998
**High Similarity Pairs (>0.8)**: 7

**Homogeneity Issue**: Yes WARN

*Note*: Using aggregate metrics as proxy; daily return correlation would be more reliable

**Experts Analyzed**:
- sm_bayesian
- sm_genetic
- fsm_genetic
- rsm_no_router
- fsm_bayesian
- fsm_random
- rsm_adaptive_v1
- sm_random
- rsm_no_market

---

## Final Decision

### **PROCEED to Phase 1-2** - Full reconstruction

**Rationale**:
- Baseline performance: 1/3 gates passed
- Expert diversity: Issue detected

**Next Steps**:
- Phase 1: Add macro features + extend horizon
- Phase 2: Build diversified expert pool
- Address homogeneity problem

---

## Artifacts

- `adaptive_router_baseline.json` - Performance metrics
- `expert_similarity.json` - Correlation analysis
- `expert_similarity.png` - Similarity heatmap
- `expert_similarity.csv` - Similarity matrix