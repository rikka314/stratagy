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
from model_test.dynamic_ensemble_online import (
    _return_panel,
    apply_online_constraints,
    exponentiated_gradient_update,
    hedge_update,
    load_online_ensemble_config,
    materialize_online_ensemble,
    validate_online_ensemble_config,
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


def _online_config() -> dict:
    return {
        "schema_version": "1.0",
        "name": "moe_phase_e_fixture",
        "phase": "E",
        "market": "US",
        "panel_output_dir": "model-test/outputs/panel_fixture",
        "phase_d_output_dir": "model-test/outputs/phase_d_fixture",
        "output_subdir": "moe_online_fixture",
        "random_seed": 42,
        "training_scope": "market_specific",
        "cross_market_policy": "ablation_only",
        "primary_horizon_days": 20,
        "return_field": "strategy_return",
        "cost_treatment": "source_net_no_recharge",
        "gating": {"max_risk_expert_weight": 0.4, "cash_expert_id": "cash"},
        "online": {
            "initial_variant": "moe_v2_regime_aware",
            "algorithms": ["hedge", "eg"],
            "learning_rate_modes": ["fixed", "volatility_adaptive"],
            "base_learning_rate": 0.75,
            "min_learning_rate": 0.05,
            "max_learning_rate": 2.0,
            "volatility_floor": 0.005,
            "volatility_lookback": 20,
            "reward_clip": 0.05,
            "forgetting_factors": [1.0, 0.98],
            "max_weight_change": 0.15,
            "cash_expert_id": "cash",
        },
    }


def _build_source_locked_fixture(root: Path) -> Path:
    panel_dir = root / "model-test" / "outputs" / "panel_fixture"
    phase_d_dir = root / "model-test" / "outputs" / "phase_d_fixture"
    panel_dir.mkdir(parents=True)
    phase_d_dir.mkdir(parents=True)
    dates = pd.date_range("2025-01-01", periods=180, freq="B")
    split = {
        "split_id": "wf_01",
        "train_start": dates[0].date().isoformat(),
        "train_end": dates[79].date().isoformat(),
        "validation_start": dates[100].date().isoformat(),
        "validation_end": dates[119].date().isoformat(),
        "test_start": dates[140].date().isoformat(),
        "test_end": dates[179].date().isoformat(),
        "purge_days": 20,
        "embargo_days": 20,
        "status": "ready",
        "reason": None,
    }
    ranges = {"train": (0, 79), "validation": (100, 119), "test": (140, 179)}
    experts = {
        "sm": ("sm", 0.8),
        "fsm": ("fsm", 0.6),
        "adaptive_router": ("rsm_adaptive_v1", 0.9),
        "cash": (None, 0.0),
    }
    rows: list[dict] = []
    for day_index, date in enumerate(dates):
        for expert_id, (source_model_id, target_position) in experts.items():
            unavailable = expert_id == "fsm" and day_index == 146
            # The winner changes at the predetermined test-window midpoint.
            before_break = day_index < 150
            strategy_return = {
                "sm": 0.03 if before_break else -0.01,
                "fsm": 0.002,
                "adaptive_router": -0.01 if before_break else 0.03,
                "cash": 0.0,
            }[expert_id]
            label_end_index = day_index + 20
            memberships: list[dict[str, str]] = []
            if not unavailable and label_end_index < len(dates):
                for role, (start, end) in ranges.items():
                    if start <= day_index <= end and label_end_index <= end:
                        memberships.append({"split_id": "wf_01", "role": role})
            rows.append(
                {
                    "date": date,
                    "symbol": "AAA",
                    "market": "US",
                    "expert_id": expert_id,
                    "expert_status": "unavailable" if unavailable else "available",
                    "unavailable_reason": "fixture gap" if unavailable else None,
                    "source_model_id": source_model_id,
                    "target_position": None if unavailable else target_position,
                    "strategy_return": None if unavailable else strategy_return,
                    "future_utility": None if unavailable or label_end_index >= len(dates) else strategy_return,
                    "label_end_date": dates[label_end_index] if label_end_index < len(dates) else None,
                    "split_memberships_json": json.dumps(memberships),
                    "feature_columns_json": json.dumps(["ret_5", "state_id", "target_position"]),
                    "ret_5": (day_index % 11) / 100.0,
                    "state_id": int((day_index // 8) % 2),
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
            "phase": "B",
            "status": "ready",
            "market": "US",
            "primary_horizon_days": 20,
            "cost_treatment": "source_net_no_recharge",
            "feature_columns": ["ret_5", "state_id", "target_position"],
            "expert_pool": [
                {"expert_id": "sm", "include_in_equal_weight": True},
                {"expert_id": "fsm", "include_in_equal_weight": True},
                {"expert_id": "adaptive_router", "include_in_equal_weight": True},
                {"expert_id": "cash", "include_in_equal_weight": False},
            ],
            "artifacts": {
                "expert_day_panel": {"path": panel_path.name, "sha256": _sha256(panel_path)},
                "walk_forward_splits": {"path": splits_path.name, "sha256": _sha256(splits_path)},
            },
        },
    )
    pd.DataFrame(
        [
            {"control_id": "best_single_expert", "status": "ready", "selected_model_ids": json.dumps(["sm"]), "source_model_id": "sm"},
            {"control_id": "equal_weight_experts", "status": "ready", "selected_model_ids": json.dumps([]), "source_model_id": None},
            {"control_id": "adaptive_router_v1", "status": "ready", "selected_model_ids": json.dumps(["rsm_adaptive_v1"]), "source_model_id": "rsm_adaptive_v1"},
        ]
    ).to_csv(panel_dir / "baseline_results.csv", index=False)

    source_dates = dates[140:160]
    source_rows = []
    initial = {"sm": 0.2, "fsm": 0.2, "adaptive_router": 0.4, "cash": 0.2}
    for date in source_dates:
        for expert_id, weight in initial.items():
            source_rows.append(
                {
                    "split_id": "wf_01",
                    "variant": "moe_v2_regime_aware",
                    "date": date,
                    "symbol": "AAA",
                    "expert_id": expert_id,
                    "expert_weight": weight,
                }
            )
    weights_path = phase_d_dir / "moe_v2_daily_weights.parquet"
    summary_path = phase_d_dir / "moe_v2_summary.csv"
    pd.DataFrame(source_rows).to_parquet(weights_path, index=False)
    pd.DataFrame([{"variant": "moe_v2_regime_aware", "status": "ready"}]).to_csv(summary_path, index=False)
    _write_json(
        phase_d_dir / "moe_v2_manifest.json",
        {
            "phase": "D",
            "status": "ready",
            "market": "US",
            "primary_horizon_days": 20,
            "return_field": "strategy_return",
            "cost_treatment": "source_net_no_recharge",
            "phase_b_panel_dir": "model-test/outputs/panel_fixture",
            "phase_a_manifest_sha256": _sha256(panel_dir / "data_manifest.json"),
            "phase_b_manifest_sha256": _sha256(panel_dir / "expert_panel_manifest.json"),
            "artifacts": {
                "daily_weights": {"path": weights_path.name, "sha256": _sha256(weights_path)},
                "summary": {"path": summary_path.name, "sha256": _sha256(summary_path)},
            },
        },
    )
    config_path = root / "model-test" / "configs" / "moe_phase_e_fixture.json"
    _write_json(config_path, _online_config())
    return config_path


def test_phase_e_materializer_writes_source_locked_online_artifacts(tmp_path: Path) -> None:
    config_path = _build_source_locked_fixture(tmp_path)
    outputs = materialize_online_ensemble(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_e_output")

    assert set(outputs) == {"online_weights", "summary", "drift_response", "comparison", "report", "manifest"}
    assert all(path.is_file() for path in outputs.values())
    weights = pd.read_parquet(outputs["online_weights"])
    summary = pd.read_csv(outputs["summary"])
    drift = pd.read_csv(outputs["drift_response"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert {"soft_moe", "hedge_fixed_ff1.000", "eg_volatility_adaptive_ff0.980"}.issubset(set(weights["variant"]))
    assert len(summary) == 9
    assert len(drift) == 9
    assert summary["status"].eq("ready").all()
    assert drift["status"].eq("ready").all()
    assert drift["winner_switched"].any()
    sums = weights.groupby(["variant", "date", "symbol"])["expert_weight"].sum()
    assert np.allclose(sums.to_numpy(), 1.0)
    assert weights.loc[weights["expert_id"] != "cash", "expert_weight"].max() <= 0.4000000001
    ordinary_moves = weights.loc[
        weights["algorithm"].ne("soft_moe")
        & ~weights["weight_change_reason"].fillna("").str.contains("safety")
        & weights["portfolio_turnover"].gt(0.0),
        "weight_change",
    ]
    assert ordinary_moves.abs().max() <= 0.1500000001
    fsm_gap = weights.loc[(weights["expert_id"] == "fsm") & (weights["expert_status"] == "unavailable")]
    assert not fsm_gap.empty
    assert fsm_gap["expert_weight"].eq(0.0).all()
    assert fsm_gap["weight_change_reason"].str.contains("missing_expert_safety_exit").any()
    assert manifest["phase"] == "E"
    assert manifest["initial_source_phase"] == "D"
    assert set(manifest["artifacts"]) == {"online_weights", "summary", "drift_response", "comparison", "report"}

    hedge_sm = weights.loc[(weights["variant"] == "hedge_fixed_ff1.000") & (weights["expert_id"] == "sm")].sort_values("date")
    assert hedge_sm.iloc[0]["expert_weight"] == pytest.approx(0.2)
    assert hedge_sm.iloc[1]["expert_weight"] > hedge_sm.iloc[0]["expert_weight"]


def test_phase_e_online_updates_and_constraints_preserve_safety() -> None:
    previous = {"sm": 0.25, "fsm": 0.25, "adaptive_router": 0.25, "cash": 0.25}
    returns = {"sm": 0.03, "fsm": -0.02, "adaptive_router": 0.0, "cash": 0.0}
    hedge = hedge_update(previous, returns, learning_rate=0.75)
    eg = exponentiated_gradient_update(previous, returns, learning_rate=0.75)
    for updated in (hedge, eg):
        assert updated["sm"] > previous["sm"]
        assert min(updated.values()) >= 0.0
        assert sum(updated.values()) == pytest.approx(1.0)

    bounded, _ = apply_online_constraints(
        {"sm": 0.9, "fsm": 0.05, "adaptive_router": 0.0, "cash": 0.05},
        previous,
        ids=list(previous),
        max_weight_change=0.15,
        max_risk_expert_weight=0.4,
    )
    assert sum(bounded.values()) == pytest.approx(1.0)
    assert max(bounded[key] for key in bounded if key != "cash") <= 0.4000000001
    assert max(abs(bounded[key] - previous[key]) for key in bounded) <= 0.1500000001

    missing, _ = apply_online_constraints(
        previous,
        previous,
        ids=list(previous),
        max_weight_change=0.15,
        max_risk_expert_weight=0.4,
        unavailable_ids={"sm"},
    )
    assert missing["sm"] == 0.0
    assert missing["cash"] > previous["cash"]
    assert sum(missing.values()) == pytest.approx(1.0)


def test_phase_e_return_panel_is_causal_for_unsorted_source_rows() -> None:
    panel = pd.DataFrame(
        [
            {"date": "2025-01-03", "symbol": "AAA", "expert_id": "sm", "strategy_return": 0.03},
            {"date": "2025-01-01", "symbol": "AAA", "expert_id": "sm", "strategy_return": 0.01},
            {"date": "2025-01-02", "symbol": "AAA", "expert_id": "sm", "strategy_return": 0.02},
        ]
    )
    returns = _return_panel(panel).sort_values("date")
    assert returns["realized_next_net_return"].iloc[:2].tolist() == pytest.approx([0.02, 0.03])
    assert pd.isna(returns["realized_next_net_return"].iloc[2])


def test_phase_e_rejects_source_artifact_hash_drift(tmp_path: Path) -> None:
    config_path = _build_source_locked_fixture(tmp_path)
    weights_path = tmp_path / "model-test" / "outputs" / "phase_d_fixture" / "moe_v2_daily_weights.parquet"
    weights = pd.read_parquet(weights_path)
    weights.loc[0, "expert_weight"] = 0.39
    weights.to_parquet(weights_path, index=False)

    with pytest.raises(DynamicEnsembleError, match="hash differs"):
        materialize_online_ensemble(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_e_output")


def test_phase_e_configs_are_market_specific_and_not_research_campaigns() -> None:
    us = load_online_ensemble_config(REPO_ROOT / "model-test" / "configs" / "moe_online_us.json")
    cn = load_online_ensemble_config(REPO_ROOT / "model-test" / "configs" / "moe_online_cn_a.json")
    assert (us["market"], cn["market"]) == ("US", "CN_A")
    with pytest.raises(ValueError, match="run_dynamic_ensemble_online.py"):
        load_research_config(REPO_ROOT / "model-test" / "configs" / "moe_online_us.json")

    invalid = copy.deepcopy(us)
    invalid["market"] = "CROSS_MARKET"
    with pytest.raises(DynamicEnsembleError, match="Unsupported market"):
        validate_online_ensemble_config(invalid)
