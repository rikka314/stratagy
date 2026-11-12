# Research Archive Conventions

## Status vocabulary

- `baseline_frozen`: the baseline is recorded and remains a control; it is not an alpha guarantee.
- `passed_research_gate`: the declared research gate passed within the stated market, universe, costs, and horizon.
- `framework_complete_pending_real_data_gate`: code and unit-test contract are complete, but real-data acceptance has not been proven.
- `not_admitted`: execution/evidence may be complete, but the product admission gate failed.
- `stopped`: a preregistered diagnostic or feasibility gate stopped the line.
- `pending`: required local evidence is absent or not yet materialized.
- `unavailable`: a required source is explicitly unavailable; never replace it with zeros or invented metrics.

## Evidence rules

1. Every conclusion must name its market, universe, time horizon, execution costs, split/purge policy, and source artifact.
2. A report or acceptance document is narrative evidence; a CSV/JSON/Parquet/manifest is machine-readable evidence. Passing requires both when the line declares a data gate.
3. `model-test/outputs/` is Git-ignored. A missing output is an evidence gap, not a license to rerun or fabricate a result.
4. A result marked `research-only` must not be described as production-ready or generalized across markets.
5. Cross-market comparisons must use explicitly shared controls and must not overwrite market-local conclusions.
6. Preserve negative results, failed gates, fallback reasons, and known data-quality blocks.
7. Use relative repository paths in catalog records so the archive remains portable.

## Record shape

Every experiment record contains:

- `id`, `title`, `status`, `date_range`, `markets`, `question`, `hypothesis`;
- `scope` and `method` (universe, horizon, costs, split/leakage policy);
- `workflow` (ordered phases and commands);
- `decision`, `gate`, `results`, `limitations`, `next_steps`;
- `sources`, `evidence`, and `runtime_boundary`.

## Canonical versus compatibility files

The `research/` directory is canonical for navigation and interpretation. Existing `model-test/`, `document/`, `plan/`, `core/`, and `tests/` paths remain compatibility/source paths unless a future migration explicitly proves that moving them is safe. Do not add a second output root.
