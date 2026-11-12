# 02 · Adaptive Systems and Dynamic Experts

## Why this line started

The baseline showed state-dependent behavior and motivated two related ideas: a hard adaptive regime router and a market-local dynamic mixture of experts. The goal was to improve selection while preserving cost, point-in-time, fallback, and risk constraints.

## Frozen scope

- US and CN_A are trained and evaluated independently.
- Primary horizon: 20 trading days; 5/60-day horizons are ablations.
- Source returns are already net of transaction costs (`source_net_no_recharge`); downstream stages never charge them again.
- Phase B uses purged walk-forward splits and at least one-horizon embargo.
- Cash is mandatory; missing experts remain explicit unavailable rows or move to Cash through audited fallback.
- Phase C-F cover soft gating, uncertainty/risk constraints, online updates, and selected-action bandit learning.

## Research flow

1. Lock the market-local full-run source, expert pool, manifests, seed, cost, and snapshot.
2. Materialize Phase A controls: best single expert, equal-weight experts, and adaptive-router control.
3. Build the point-in-time expert-day panel and future utility labels (Phase B).
4. Train and replay no-state/regime-aware soft gating (Phase C), then add uncertainty/OOD/risk limits (Phase D).
5. Replay Hedge/EG online updates (Phase E), then selected-action-only LinUCB/Thompson policies (Phase F).
6. Run W11 admission against market-matched adaptive controls using four test splits, drawdown, turnover, and non-inferiority breadth.
7. Stop product/shadow integration when the frozen 3/4 window gate fails.

## Key decisions and ideas

- A dynamic model may only consume evidence available at its decision time.
- Cash and explicit fallback reasons are part of the model contract, not hidden error handling.
- Unselected action returns are evaluation-only in the bandit study and cannot leak into learning.
- Lower risk or lower turnover alone does not satisfy the admission gate if return non-inferiority lacks breadth.

## Result

Phases A-F completed as research artifacts for the relevant market runs. W11 reached only 1/4 non-inferior windows for US and 2/4 for CN_A; both markets passed per-split drawdown and turnover checks but failed the required 3/4 breadth. W12 was blocked: no shadow mode, Streamlit integration, default change, or product admission was started. The existing `adaptive_router_v1` behavior remains the runtime default/fallback boundary.

## Gate and current status

Status: `not_admitted`. The line is not a failed engineering run; it is an explicit negative product-admission decision.

## Problems and future remedies

- Improvements were not broad enough across the four frozen test windows.
- Any future attempt must preserve the same costs, split policy, target-position turnover reconstruction, source lock, and market isolation. Choosing a favorable window or post-hoc parameter cell is not an allowed remedy.

## Source files

- Contract: [`dynamic-ensemble-research.md`](../../document/interfaces/dynamic-ensemble-research.md)
- Execution plan: [`post_gate2_model_upgrade_v1_execution.md`](../../plan/post_gate2_model_upgrade_v1_execution.md)
- Admission record: [`post_gate2_model_upgrade_w11_w12_20260817.md`](../../document/acceptance/post_gate2_model_upgrade_w11_w12_20260817.md)
- Runner guide: [`model-test README`](../../model-test/docs/README.md)
- Configs: `model-test/configs/moe_baseline_{us,cn_a}.json`, `moe_v1_*`, `moe_v2_*`, `moe_online_*`, `moe_bandit_*`
- Runners: `model-test/prepare_moe_baseline.py`, `prepare_expert_panel.py`, `run_dynamic_ensemble*.py`, `run_online_ensemble.py`, `run_contextual_bandit.py`, `run_w11_admission.py`
- Evidence roots: `model-test/outputs/moe_*`, `moe_*_admission_*`, and `w11_admission_*`

## Reproduction boundary

These commands materialize new research outputs only when the source lock is present and verified. They must not be described as reversing the frozen W11/W12 decision.
