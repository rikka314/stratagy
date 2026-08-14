# Post-Gate-2 Model Upgrade — Phase A Acceptance (2026-08-12)

## Result

Phase-A implementation is complete for the research repository:

- dynamic-ensemble contract frozen;
- US and CN_A market-specific configs added;
- three comparison controls frozen;
- 20-day primary and 5/60-day ablation horizons frozen;
- net-return/no-double-cost semantics validated;
- source run, config, code version, seed and data SHA-256 validation implemented;
- deterministic baseline and manifest materializer added;
- missing sources and unsupported CN_A adaptive routing remain explicit instead of being fabricated or silently replaced.

## Verification boundary

The checkout does not contain `model-test/outputs/` because research outputs are intentionally ignored. The generator therefore distinguishes implementation acceptance from evidence readiness:

- strict mode fails until the referenced Window 3B and full-run output directories are restored;
- `--allow-pending` may create coordination artifacts, but these have `status=pending` and are not passing research evidence;
- the existing frozen US conclusion remains documented in `document/strategy_research_baseline_us_20260811.md`;
- CN_A full-run evidence remains pending, consistent with the current project decision to pause CN_A and cross-market research.

## Automated verification

| Check | Result |
|---|---|
| Phase-A config, selection, net-return, missing-source and unavailable-router tests | `4 passed` |
| Phase-A plus existing model-test runner regression | `27 passed` |
| Repository regression excluding dependency-gated `opencc` / LightGBM suites | `164 passed` |
| Strict CLI against the current checkout | Expected refusal: frozen source outputs are absent |
| Pending CLI for US and CN_A | Wrote explicit pending manifests and three unavailable control rows |

The system Python environment used for this acceptance does not contain
`lightgbm` or `opencc`. The full suite therefore cannot collect two UI modules,
and the CPU-device preflight correctly reports LightGBM unavailable. No
Phase-A module imports either optional dependency.

## Commands

```bash
python -m pytest tests/test_moe_phase_a.py

python model-test/prepare_moe_baseline.py \
  --config model-test/configs/moe_baseline_us.json

python model-test/prepare_moe_baseline.py \
  --config model-test/configs/moe_baseline_cn_a.json
```

The last two commands are expected to fail clearly when the ignored frozen source outputs are not locally present. This is the required safety behavior.
