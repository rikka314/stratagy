from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_test.config import load_research_config
from model_test.dynamic_ensemble import DynamicEnsembleError
from model_test.dynamic_ensemble_bandit import (
    _LinearContextualBandit,
    _simulate_policy,
    load_dynamic_ensemble_bandit_config,
    materialize_dynamic_ensemble_bandit,
    validate_dynamic_ensemble_bandit_config,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _bandit_config() -> dict:
    return {
        "schema_version": "1.0",
        "name": "moe_phase_f_fixture",
        "phase": "F",
        "market": "US",
        "panel_output_dir": "model-test/outputs/panel_fixture",
        "phase_e_output_dir": "model-test/outputs/phase_e_fixture",
        "output_subdir": "moe_bandit_fixture",
        "random_seed": 42,
        "training_scope": "market_specific",
        "cross_market_policy": "ablation_only",
        "primary_horizon_days": 20,
        "return_field": "strategy_return",
        "cost_treatment": "source_net_no_recharge",
        "feedback_mode": "selected_action_only",
        "research_only": True,
        "context": {"feature_columns": ["ret_5", "state_id", "target_position"]},
        "source_action_variants": ["soft_moe", "hedge_fixed", "eg_fixed"],
        "bandit": {
            "algorithms": ["linucb", "contextual_thompson"],
            "linucb_alphas": [0.6],
            "thompson_scales": [0.6],
            "ridge_lambda": 1.0,
            "observation_variance": 0.0004,
            "reward_clip": 0.05,
            "incremental_action_switch_cost_bps": 10.0,
        },
    }


def _build_phase_e_fixture(root: Path) -> Path:
    panel_dir = root / "model-test" / "outputs" / "panel_fixture"
    phase_e_dir = root / "model-test" / "outputs" / "phase_e_fixture"
    panel_dir.mkdir(parents=True)
    phase_e_dir.mkdir(parents=True)
    dates = pd.date_range("2025-01-01", periods=180, freq="B")
    split = {
        "split_id": "wf_01",
        "train_start": dates[0].date().isoformat(), "train_end": dates[79].date().isoformat(),
        "validation_start": dates[100].date().isoformat(), "validation_end": dates[119].date().isoformat(),
        "test_start": dates[140].date().isoformat(), "test_end": dates[179].date().isoformat(),
        "purge_days": 20, "embargo_days": 20, "status": "ready", "reason": None,
    }
    ranges = {"train": (0, 79), "validation": (100, 119), "test": (140, 179)}
    rows: list[dict] = []
    for day_index, date in enumerate(dates):
        for expert_id, target_position in {"sm": 0.8, "adaptive_router": 0.6, "cash": 0.0}.items():
            label_end_index = day_index + 20
            memberships: list[dict[str, str]] = []
            if label_end_index < len(dates):
                for role, (start, end) in ranges.items():
                    if start <= day_index <= end and label_end_index <= end:
                        memberships.append({"split_id": "wf_01", "role": role})
            rows.append(
                {
                    "date": date, "symbol": "AAA", "market": "US", "expert_id": expert_id,
                    "expert_status": "available", "unavailable_reason": None,
                    "source_model_id": "rsm_adaptive_v1" if expert_id == "adaptive_router" else expert_id,
                    "target_position": target_position, "strategy_return": 0.01 if expert_id == "sm" else 0.0,
                    "future_utility": 0.01 if label_end_index < len(dates) else None,
                    "label_end_date": dates[label_end_index] if label_end_index < len(dates) else None,
                    "split_memberships_json": json.dumps(memberships),
                    "feature_columns_json": json.dumps(["ret_5", "state_id", "target_position"]),
                    "ret_5": (day_index % 7) / 100.0, "state_id": int((day_index // 5) % 2),
                }
            )
    panel = pd.DataFrame(rows)
    panel_path = panel_dir / "expert_day_panel.parquet"
    splits_path = panel_dir / "expert_panel_walk_forward_splits.csv"
    panel.to_parquet(panel_path, index=False)
    pd.DataFrame([split]).to_csv(splits_path, index=False)
    _write_json(panel_dir / "data_manifest.json", {"phase": "A", "status": "ready", "market": "US"})
    _write_json(
        panel_dir / "expert_panel_manifest.json",
        {
            "phase": "B", "status": "ready", "market": "US", "primary_horizon_days": 20,
            "cost_treatment": "source_net_no_recharge", "feature_columns": ["ret_5", "state_id", "target_position"],
            "expert_pool": [
                {"expert_id": "sm", "include_in_equal_weight": True},
                {"expert_id": "adaptive_router", "include_in_equal_weight": True},
                {"expert_id": "cash", "include_in_equal_weight": False},
            ],
            "artifacts": {
                "expert_day_panel": {"path": panel_path.name, "sha256": _sha256(panel_path)},
                "walk_forward_splits": {"path": splits_path.name, "sha256": _sha256(splits_path)},
            },
        },
    )
    pd.DataFrame([{"control_id": "adaptive_router_v1", "status": "ready", "selected_model_ids": "[]"}]).to_csv(
        panel_dir / "baseline_results.csv", index=False
    )

    source_rows: list[dict] = []
    allocations = {"sm": 0.4, "adaptive_router": 0.4, "cash": 0.2}
    for index, date in enumerate(dates[140:160]):
        post_break = index >= 10
        returns = {
            "soft_moe": 0.004,
            "hedge_fixed": -0.006 if post_break else 0.014,
            "eg_fixed": 0.015 if post_break else -0.004,
        }
        for variant, portfolio_return in returns.items():
            for expert_id, weight in allocations.items():
                source_rows.append(
                    {
                        "split_id": "wf_01", "variant": variant,
                        "algorithm": "soft_moe" if variant == "soft_moe" else variant.split("_")[0],
                        "learning_rate_mode": "fixed", "forgetting_factor": 1.0,
                        "date": date, "symbol": "AAA", "expert_id": expert_id, "expert_status": "available",
                        "expert_weight": weight, "portfolio_return": portfolio_return,
                        "portfolio_turnover": 0.0 if index == 0 else 0.05, "evaluation_status": "ready",
                    }
                )
    weights_path = phase_e_dir / "moe_online_weights.parquet"
    summary_path = phase_e_dir / "moe_online_summary.csv"
    pd.DataFrame(source_rows).to_parquet(weights_path, index=False)
    pd.DataFrame(
        [
            {"market": "US", "split_id": "wf_01", "variant": "soft_moe", "algorithm": "soft_moe", "status": "ready", "decision_count": 20, "total_return": 0.08},
            {"market": "US", "split_id": "wf_01", "variant": "hedge_fixed", "algorithm": "hedge", "status": "ready", "decision_count": 20, "total_return": 0.05},
        ]
    ).to_csv(summary_path, index=False)
    _write_json(
        phase_e_dir / "moe_online_manifest.json",
        {
            "schema_version": "1.0", "phase": "E", "status": "ready", "market": "US",
            "primary_horizon_days": 20, "return_field": "strategy_return", "cost_treatment": "source_net_no_recharge",
            "phase_b_panel_dir": "model-test/outputs/panel_fixture",
            "phase_a_manifest_sha256": _sha256(panel_dir / "data_manifest.json"),
            "phase_b_manifest_sha256": _sha256(panel_dir / "expert_panel_manifest.json"),
            "initial_source_phase": "D", "initial_source_manifest_sha256": "fixture",
            "gating": {"max_risk_expert_weight": 0.4},
            "artifacts": {
                "online_weights": {"path": weights_path.name, "sha256": _sha256(weights_path)},
                "summary": {"path": summary_path.name, "sha256": _sha256(summary_path)},
            },
        },
    )
    config_path = root / "model-test" / "configs" / "moe_phase_f_fixture.json"
    _write_json(config_path, _bandit_config())
    return config_path


def test_phase_f_materializes_selected_action_only_artifacts(tmp_path: Path) -> None:
    config_path = _build_phase_e_fixture(tmp_path)
    outputs = materialize_dynamic_ensemble_bandit(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_f_output")

    assert set(outputs) == {"decisions", "summary", "convergence", "drift_response", "comparison", "final_state", "report", "manifest"}
    assert all(path.is_file() for path in outputs.values())
    decisions = pd.read_parquet(outputs["decisions"])
    summary = pd.read_csv(outputs["summary"])
    convergence = pd.read_csv(outputs["convergence"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    state = json.loads(outputs["final_state"].read_text(encoding="utf-8"))

    assert set(decisions["policy_variant"]) == {"linucb_alpha_0.600", "contextual_thompson_scale_0.600"}
    assert decisions["feedback_mode"].eq("selected_action_only").all()
    assert decisions["available_action_count"].eq(4).all()  # three Phase-E policies plus Cash
    assert np.allclose(
        decisions["net_policy_return"], decisions["source_portfolio_return"] - decisions["incremental_exploration_cost"]
    )
    assert np.allclose(
        decisions["incremental_exploration_cost"], decisions["action_switched"].astype(float) * 0.001
    )
    assert summary["status"].eq("ready").all()
    assert not convergence.empty
    assert manifest["phase"] == "F"
    assert manifest["feedback_mode"] == "selected_action_only"
    assert manifest["candidate_action_variants"] == ["eg_fixed", "hedge_fixed", "soft_moe"]
    for policy_state in state.values():
        assert sum(policy_state["observation_count"].values()) == 20

    second = materialize_dynamic_ensemble_bandit(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_f_output_repeat")
    repeated = pd.read_parquet(second["decisions"])
    assert decisions[["policy_variant", "date", "symbol", "selected_action"]].equals(
        repeated[["policy_variant", "date", "symbol", "selected_action"]]
    )


def test_phase_f_updates_only_the_selected_action() -> None:
    bandit = _LinearContextualBandit(
        ["a", "b", "cash"], dimension=2, ridge_lambda=1.0, observation_variance=0.1, rng=np.random.default_rng(42)
    )
    context = np.asarray([1.0, 0.5])
    before = bandit.snapshot()
    bandit.update("a", context, 0.02, reward_clip=0.05)
    after = bandit.snapshot()
    assert after["observation_count"] == {"a": 1, "b": 0, "cash": 0}
    assert after["posterior"]["b"] == before["posterior"]["b"]
    assert after["posterior"]["cash"] == before["posterior"]["cash"]


def test_phase_f_does_not_leak_one_symbols_same_date_reward_into_another_choice() -> None:
    config = _bandit_config()
    rows: list[dict] = []
    for date in ("2025-01-02", "2025-01-03"):
        for symbol in ("AAA", "BBB"):
            for action_id, reward in (("a", 0.01), ("b", -0.01)):
                rows.append(
                    {
                        "split_id": "wf_01", "date": date, "symbol": symbol, "action_id": action_id,
                        "source_portfolio_return": reward, "source_portfolio_turnover": 0.0,
                        "context": np.asarray([1.0, 0.2]),
                    }
                )
    baseline, _state = _simulate_policy(
        pd.DataFrame(rows), split_id="wf_01", action_ids=["a", "b"], algorithm="linucb",
        exploration_parameter=0.6, policy_variant="fixture", config=config, seed_offset=0,
    )
    changed_rows = [dict(row) for row in rows]
    for row in changed_rows:
        if row["date"] == "2025-01-02" and row["symbol"] == "AAA":
            row["source_portfolio_return"] = -0.99
    changed, _state = _simulate_policy(
        pd.DataFrame(changed_rows), split_id="wf_01", action_ids=["a", "b"], algorithm="linucb",
        exploration_parameter=0.6, policy_variant="fixture", config=config, seed_offset=0,
    )
    baseline_bbb = next(row for row in baseline if row["date"] == "2025-01-02" and row["symbol"] == "BBB")
    changed_bbb = next(row for row in changed if row["date"] == "2025-01-02" and row["symbol"] == "BBB")
    assert baseline_bbb["selected_action"] == changed_bbb["selected_action"]
    assert baseline_bbb["posterior_mean"] == changed_bbb["posterior_mean"]


def test_phase_f_rejects_phase_e_artifact_hash_drift(tmp_path: Path) -> None:
    config_path = _build_phase_e_fixture(tmp_path)
    source = tmp_path / "model-test" / "outputs" / "phase_e_fixture" / "moe_online_weights.parquet"
    weights = pd.read_parquet(source)
    weights.loc[0, "portfolio_return"] = 0.99
    weights.to_parquet(source, index=False)
    with pytest.raises(DynamicEnsembleError, match="hash differs"):
        materialize_dynamic_ensemble_bandit(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_f_output")


def test_phase_f_configs_are_isolated_and_reject_future_context() -> None:
    us = load_dynamic_ensemble_bandit_config(REPO_ROOT / "model-test" / "configs" / "moe_bandit_us.json")
    cn = load_dynamic_ensemble_bandit_config(REPO_ROOT / "model-test" / "configs" / "moe_bandit_cn_a.json")
    assert (us["market"], cn["market"]) == ("US", "CN_A")
    assert cn["context"]["feature_columns"] == [
        "market_return_5",
        "state_market_regime_id_20",
        "target_position",
    ]
    with pytest.raises(ValueError, match="run_dynamic_ensemble_bandit.py"):
        load_research_config(REPO_ROOT / "model-test" / "configs" / "moe_bandit_us.json")

    invalid = copy.deepcopy(us)
    invalid["context"]["feature_columns"] = ["future_utility"]
    with pytest.raises(DynamicEnsembleError, match="future or reward"):
        validate_dynamic_ensemble_bandit_config(invalid)
