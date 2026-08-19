# Post-Gate-2 Model Upgrade — W11 Admission Comparison and W12 Gate (2026-08-18)

## Decision

- **W11: complete, not admitted.** Both markets were rerun with four purged
  test splits and a market-matched `adaptive_router_v1` control. US reached only
  1/4 non-inferior windows; CN_A reached 2/4.
- **W12: blocked.** No market passed the frozen 3/4 gate, so no shadow-mode or
  Streamlit integration was started. The existing `adaptive_router_v1`
  workflow remains unchanged.

This is a negative product-admission decision, not a failed research run. The
new A–F outputs are source-locked, hash-verified, and remain research-only.

## Source and execution audit

The admission-specific runs use new output directories and do not overwrite the
older full-run or W10 evidence. All manifests report the same market-local
`random_seed=42`, 20-trading-day primary horizon, `strategy_return`, and
`source_net_no_recharge` cost treatment. The W11 tool revalidated the supplied
Phase-B and Phase-D artifact hashes before building the comparison.

| Market | Full replay | Phase B manifest | Phase C manifest | Phase D manifest | Phase E manifest | Phase F manifest |
|---|---|---|---|---|---|---|
| US | `moe_admission_us/data_manifest.json` (`abdeb2a1d30b37a336bbdfc88ff9dac534b13100d67452090497029d261506af`) | `654e570252a0316cd83101256ddb3c492463810061c8cc28c5b603b5717e4b44` | `d501523a859ee210f1f4b3a98b1814ce035878880cf52bcdacdc00f231bab4c4` | `81e62e6544e7642be13a8d5479b341dc8c201655934bba7a1b2a90fc5ed77c09` | `0872028acba71875d31c150c725c5a2d4c56478ab4a9fb4dad3e958451f31c2e` | `11932611c33e6bd22f224d6e9d9f971b97a9d926b97f0596b06bd922164f5955` |
| CN_A | `full_cn_a_admission_60/data_manifest.json` (`d3825b9f8c6fdccd12c85b865c93d3b8226b2965416175530180227fdf61447e`); native adaptive main rows: 60/60 success | `b07f6c7bb3806c8ac37cd185043a78ffb8b0374cc935a4097e0e3603429ed309` | `c201cf7444534541fb9726a1f47e1719f77ebc6f277fc8a5d6ac1f71cf0a4971` | `4511bdd126981d9ab5f1e911bb569ec55e01d7cf191ec1fce687d8a98cb849d2` | `fee42c74ade4862ec024913d0b1c7fb32211feef0e753665d64dc57a3a694ee7` | `50e4cef43642995c2d1312b07570a4ee4c4d07852535da5ad8acb658f98ed3b3` |

The CN_A replay used the frozen `full_cn_a_deans_60` snapshot (aggregate
snapshot hash `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`)
and produced a market-native adaptive artifact; no US/SPY artifact was used.

## Frozen W11 gate and results

The admission tool compares the Phase-D `moe_v2_regime_aware` candidate with
the available adaptive-router rows using reconstructed target-position
execution turnover. It requires exactly four test splits, at least three
non-inferior windows, no worse maximum drawdown in any split, and turnover no
greater than `1.25x` the adaptive control.

| Market | Non-inferior windows | Candidate return vs adaptive by split | Turnover ratios | Decision |
|---|---:|---|---|---|
| US | 1/4 | `wf_01` 0.2650% vs 3.5294%; `wf_02` 0.0967% vs -1.6577%; `wf_03` 0.8237% vs 4.2850%; `wf_04` -0.0131% vs 0.6029% | 0.2804x / 0.2254x / 0.2241x / 0.2606x | **not_admitted** |
| CN_A | 2/4 | `wf_01` 0.4738% vs 7.8310%; `wf_02` -0.2209% vs -6.4089%; `wf_03` 0.9764% vs 2.1165%; `wf_04` -1.6917% vs -8.8596% | 0.2310x / 0.2866x / 0.2274x / 0.4119x | **not_admitted** |

Both markets passed the per-split drawdown and turnover checks. The hard gate
failed only on the required breadth of non-inferior windows:

- US decision: `model-test/outputs/w11_admission_us/w11_decision.json`,
  decision SHA-256 `86b7effefa0279f3e306a3bf9587c198f202dc8e736aabafa8645512d209cc5`.
- CN_A decision: `model-test/outputs/w11_admission_cn_a/w11_decision.json`,
  decision SHA-256 `050eb17a8b49175a08e0aeb0f2dfeaecd2e204637c01d10c3f5f1ad4796104fe`.

The symbol-level checks remain descriptive, not a selection rule: US median
return difference is `0.0`, improvement ratio `51.25%`; CN_A median difference
is `0.017507`, improvement ratio `56.25%`. These do not override the 3/4
window gate.

## W12 gate and rollback boundary

Because neither market passed W11, W12 remains deliberately blocked:

- no non-default single-stock workflow option;
- no Streamlit reader for Phase-C–F artifacts;
- no model-evaluation or HTML-export shadow fields;
- no change to the default or degraded fallback behavior of
  `adaptive_router_v1`.

The next eligible research window must preserve the frozen cost, split,
selection, and turnover rules. It may not reverse this decision by changing
windows, costs, or choosing a favorable parameter cell after seeing results.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_moe_admission.py tests\test_moe_phase_b.py tests\test_moe_phase_c.py tests\test_moe_phase_d.py tests\test_moe_phase_e.py tests\test_moe_phase_f.py -q
.\.venv\Scripts\python.exe model-test\run_w11_admission.py --panel-dir model-test\outputs\moe_admission_us --phase-d-dir model-test\outputs\moe_v2_admission_us --output-dir model-test\outputs\w11_admission_us
.\.venv\Scripts\python.exe model-test\run_w11_admission.py --panel-dir model-test\outputs\moe_admission_cn_a --phase-d-dir model-test\outputs\moe_v2_admission_cn_a --output-dir model-test\outputs\w11_admission_cn_a
```

The two admission commands intentionally return exit code `3` for a valid
`not_admitted` result; their JSON/CSV outputs are the evidence of that
decision, not a failed source run.
