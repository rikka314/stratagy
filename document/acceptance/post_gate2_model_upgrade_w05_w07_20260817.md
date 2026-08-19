# Post-Gate-2 Model Upgrade — W05–W07 US Execution Acceptance (2026-08-17)

## Result

US W05–W07 are complete as a source-locked, research-only Phase-D → E → F
execution.  They do not grant product admission, change a Streamlit default,
or support a cross-market conclusion.

| Window | Output | Manifest SHA-256 | Verified artifacts | Status |
|---|---|---|---:|---|
| W05 / Phase D | `model-test/outputs/moe_v2_us/` | `8f1b7a8de08b4fdf499141ec55e78c21f3ae07a5cd6a37c240edf818434dffb9` | 8 | ready |
| W06 / Phase E | `model-test/outputs/moe_online_us/` | `20034b1eb3e70b535ad5b427369ffc363d8b85c67b725f6fdcb4800243c7771d` | 5 | ready |
| W07 / Phase F | `model-test/outputs/moe_bandit_us/` | `cebd726303e24b6cde44e6b1714652c59ef6c3f1b2f242aa1374eba306cb6edb` | 7 | ready |

The Phase-E manifest locks the listed Phase-D manifest.  The Phase-F manifest
locks the listed Phase-E manifest and the same ready Phase-A/B source lock.
All three runs use the US market, 20-trading-day horizon, and the already-net
`strategy_return`, and `source_net_no_recharge`.

## W07 configuration correction

The shipped US bandit configuration requested `ret_5` and `state_id`, neither
of which exists in the frozen Phase-B US panel.  The strict runner therefore
failed closed before producing an artifact.  The configuration now uses the
available point-in-time fields:

```text
market_return_5
state_market_regime_id_20
target_position
```

The revised configuration remains market-specific and excludes every future,
reward, label and split-membership field. It produced the ready Phase-F
output above.

## Safety and research boundary

- Phase D retains a 40% per-risk-expert cap, quantile uncertainty / OOD
  tracking, auditable fallback and risk controls.
- Phase E retains Cash, the 40% risk-expert cap and a 15% normal daily
  component weight-move bound; drift response is evaluation-only.
- Phase F retains Cash as an action and uses `selected_action_only` feedback.
  Same-date decisions are batched before rewards update a posterior; unselected
  rewards are only read for evaluation-only drift measurements.
- `incremental_action_switch_cost_bps=0` remains separately disclosed because
  no measured deployment cost model is available.  Expert execution costs are
  not charged a second time.

## Outcome boundary

The Phase-F summaries do not provide a stable improvement over Phase-E Hedge /
EG across the three US walk-forward splits.  For example, the strongest
LinUCB result is positive only in `wf_01` and negative in both `wf_02` and
`wf_03`; observed action-switch rates are high.  Phase F therefore remains an
ablation, not a promotion candidate.  W11 remains pending, and CN_A remains
explicitly incomplete.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_moe_phase_d.py tests\test_moe_phase_e.py tests\test_moe_phase_f.py -q
# 14 passed
```

An independent manifest check recomputed every declared Phase-D/E/F artifact
SHA-256, verified `status=ready`, verified the Phase-D → E and Phase-E → F
manifest links, and confirmed the frozen market, horizon, return and cost
contract.
