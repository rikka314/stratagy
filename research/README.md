# Research Archive

This directory is the canonical index for the project's frozen research. It is an archive and provenance layer, not a second production runtime.

## Start Here

1. Read [`RESEARCH_CATALOG.md`](RESEARCH_CATALOG.md) for the timeline and conclusion-first summary.
2. Read [`RESEARCH_CATALOG.json`](RESEARCH_CATALOG.json) when consuming the archive from tools or a future evidence page.
3. Read [`conventions.md`](conventions.md) before adding or changing an experiment record.
4. Open the experiment README that matches the question being investigated.
5. Follow each README's evidence links back to the original acceptance records and local `model-test/outputs/` artifacts.

## Chronological research lines

| Directory | Question | Current status |
|---|---|---|
| [`00_baseline_sm_fsm`](00_baseline_sm_fsm/README.md) | Do SM/FSM-era strategies hold up across a full market universe? | `baseline_frozen` |
| [`01_transformer_feasibility`](01_transformer_feasibility/README.md) | Does state similarity/retrieval improve expert utility enough to justify Transformer work? | `stopped` |
| [`02_adaptive_systems`](02_adaptive_systems/README.md) | Can adaptive routing or a dynamic expert ensemble earn admission beyond frozen controls? | `not_admitted` |
| [`03_composite_only_cn_a`](03_composite_only_cn_a/README.md) | Does a market-native CN_A Composite beat SM/FSM under one frozen comparison? | `passed_research_gate` |
| [`04_composite_advisory_cn_a`](04_composite_advisory_cn_a/README.md) | Can multi-expert advisory safely improve or de-risk Composite? | `framework_complete_pending_real_data_gate` |
| [`05_ml_enhancement`](05_ml_enhancement/README.md) | Can ML search and filtering improve parameter selection? | `completed` |
| [`06_news_fusion`](06_news_fusion/README.md) | Can leakage-safe news sentiment be added without breaking fallback behavior? | `completed` |
| [`07_frontend_evolution`](07_frontend_evolution/README.md) | Can the research surface become a readable product tool? | `completed` |
| [`08_deployment_optimization`](08_deployment_optimization/README.md) | Can deployment and cache contracts remain stable across devices? | `completed` |
| [`09_us_composite`](09_us_composite/README.md) | Can US Composite with macro factors beat SM/FSM? | `passed_research_gate` |

## What stays where

Existing `model-test/` entry points, package modules, configs, `document/` reports, and `model-test/outputs/` directories remain in their original locations for compatibility. This archive links and classifies them; it does not duplicate large generated outputs or silently replace old commands.

The Streamlit application continues to discover `model-test/outputs/` directly. The `/strategy/model-evaluation` research browser consumes this catalog and the referenced artifacts while preserving the read-only and no-fabrication rules.

## Freeze command

From the repository root:

```bash
python research/validate_research_catalog.py
```

The validator checks catalog schema, source paths, evidence paths, and available manifest files. Missing ignored outputs are reported as `pending` or `unavailable`; no output is generated to fill the gap.
