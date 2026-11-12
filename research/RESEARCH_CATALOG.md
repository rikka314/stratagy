# Research Catalog

Freeze date: **2026-08-23**  
Source commit: `d2168bf8a0073360f5a19a0f4e85e91fc65410a7`  
Source branch: `transformer-state-v3`

This is a conclusion-first map of the chronological research lines. The machine-readable source is [`RESEARCH_CATALOG.json`](RESEARCH_CATALOG.json).

## Timeline

| ID | Scope | Status | Main conclusion |
|---|---|---|---|
| `baseline_sm_fsm_full_market` | US/CN_A full-market SM/FSM-era baseline | `baseline_frozen` | Reproducible comparison established; ranking is not stable full-market outperformance. |
| `transformer_state_feasibility` | US state retrieval and Transformer feasibility | `stopped` | Engineering chain passed, but query utility failed; Transformer training stopped. |
| `adaptive_dynamic_experts` | US/CN_A adaptive and dynamic expert systems | `not_admitted` | W11 reached US 1/4 and CN_A 2/4 non-inferior windows; product admission blocked. |
| `cn_a_composite_only` | CN_A market-native Composite | `passed_research_gate` | Sharpe 0.5972 and fold consistency 76.7% beat SM/FSM under the frozen CN_A comparison. |
| `cn_a_composite_advisory` | CN_A Composite advisory overlay | `framework_complete_pending_real_data_gate` | Contract and tests complete; no empirical advisory pass is recorded. |
| `ml_enhancement` | ML search and filtering | `completed` | ML remains an optional research branch, not a universal upgrade. |
| `news_fusion` | Leakage-safe news fusion | `completed` | Fallback and ablation contracts are validated; no zero-coverage diagnostic is performance evidence. |
| `frontend_evolution` | W6-W8 frontend evolution | `completed` | The shared research-product visual and performance baseline was frozen. |
| `deployment_optimization` | Deployment and cross-device contracts | `completed` | Subpath, workspace, cache and runtime contracts were documented and tested. |
| `us_composite` | US Composite Phase 0-4 | `passed_research_gate` | US-only Composite research gate passed under its declared contract. |

The browser distinguishes a historical `passed_research_gate` label from current verifiability. For example, a record with no canonical machine artifact is shown as historical-only and its available supplemental charts are explicitly marked diagnostic.

## How to read each line

- [`00_baseline_sm_fsm`](00_baseline_sm_fsm/README.md) explains the initial full-market experiment, controls, ranking limits, and source runs.
- [`01_transformer_feasibility`](01_transformer_feasibility/README.md) separates engineering acceptance from the negative utility conclusion.
- [`02_adaptive_systems`](02_adaptive_systems/README.md) reconstructs Phase A-F and the W11/W12 admission decision.
- [`03_composite_only_cn_a`](03_composite_only_cn_a/README.md) records the factor-panel, real-forward-return correction, and CN_A-only Composite gate.
- [`04_composite_advisory_cn_a`](04_composite_advisory_cn_a/README.md) records the advisory contract and makes the missing real-data gate visible.
- [`05_ml_enhancement`](05_ml_enhancement/README.md) records optimization and filtering as optional branches.
- [`06_news_fusion`](06_news_fusion/README.md) records leakage-safe news normalization, fallback and ablation semantics.
- [`07_frontend_evolution`](07_frontend_evolution/README.md) records the frozen product-facing research surface.
- [`08_deployment_optimization`](08_deployment_optimization/README.md) records deployment, workspace and cache contracts.
- [`09_us_composite`](09_us_composite/README.md) records the US Composite Phase 0-4 research line.

## Evidence policy

The catalog points to existing reports, configs, scripts, manifests, CSVs, and ignored output directories. It does not copy large output datasets. A missing `model-test/outputs/` artifact is a visible evidence gap, never a zero-filled or invented result. A future research page should expose both the result and this provenance state.

## Freeze counts

- Research documentation files scanned: 132
- Research scripts/config files scanned: 141
- Research tests scanned: 55
- Research-specific core candidates scanned: 13
- Tracked files at initial inventory: `model-test` 96, `document` 90, `tests` 38, `core` 27, `data` 12
- The counts are inventory counts, not claims that every file belongs to one experiment. The catalog is the authoritative classification for the ten lines above.

## Important boundary

`research/` is the navigation and interpretation layer. Existing `model-test/` commands and output paths remain in place for compatibility. The Streamlit application and website route behavior are intentionally unchanged by this reorganization.
