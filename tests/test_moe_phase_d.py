from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from model_test.dynamic_ensemble import DynamicEnsembleError, materialize_dynamic_ensemble
from model_test.dynamic_ensemble_v2 import (
    _quantile_weights_for_group,
    _strictly_reduces_risk,
    load_dynamic_ensemble_v2_config,
    materialize_dynamic_ensemble_v2,
)
from model_test.config import load_research_config


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


def _phase_c_config() -> dict:
    return {
        "schema_version": "1.0",
        "name": "moe_phase_d_fixture_source",
        "phase": "C",
        "market": "US",
        "panel_output_dir": "model-test/outputs/panel_fixture",
        "output_subdir": "phase_c_fixture",
        "random_seed": 42,
        "training_scope": "market_specific",
        "cross_market_policy": "ablation_only",
        "primary_horizon_days": 20,
        "return_field": "strategy_return",
        "cost_treatment": "source_net_no_recharge",
        "model": {
            "n_estimators": 24,
            "learning_rate": 0.08,
            "num_leaves": 7,
            "min_child_samples": 8,
            "n_jobs": 1,
            "minimum_train_rows": 80,
            "device_type": "cpu",
        },
        "gating": {
            "temperature": 0.05,
            "max_risk_expert_weight": 0.4,
            "smoothing_alpha": 0.5,
            "cash_expert_id": "cash",
        },
    }


def _phase_d_config() -> dict:
    return {
        "schema_version": "1.1",
        "name": "moe_phase_d_fixture",
        "phase": "D",
        "market": "US",
        "panel_output_dir": "model-test/outputs/panel_fixture",
        "phase_c_output_dir": "model-test/outputs/phase_c_fixture",
        "output_subdir": "phase_d_fixture",
        "random_seed": 42,
        "training_scope": "market_specific",
        "cross_market_policy": "ablation_only",
        "primary_horizon_days": 20,
        "return_field": "strategy_return",
        "cost_treatment": "source_net_no_recharge",
        "model": {
            "n_estimators": 24,
            "learning_rate": 0.08,
            "num_leaves": 7,
            "min_child_samples": 8,
            "n_jobs": 1,
            "minimum_train_rows": 80,
            "device_type": "cpu",
        },
        "quantiles": {"lower": 0.2, "median": 0.5},
        "gating": {
            "temperature": 0.05,
            "max_risk_expert_weight": 0.4,
            "smoothing_alpha": 0.5,
            "cash_expert_id": "cash",
        },
        "uncertainty": {
            "gamma": 0.5,
            "confidence_width_threshold": 10.0,
            "disagreement_std_threshold": 10.0,
            "ood_max_abs_zscore": 100.0,
        },
        "fallback": {
            "low_confidence_policy": "cash",
            "high_disagreement_policy": "equal_weight",
            "out_of_distribution_policy": "adaptive_router",
        },
        "risk": {
            "max_weight_change": 0.15,
            "max_portfolio_turnover": 0.12,
            "minimum_holding_days": 3,
            "position_active_threshold": 0.05,
            "drawdown_trigger": 0.9,
            "drawdown_risk_scale": 0.5,
        },
        "ablation": {
            "temperatures": [0.025, 0.05],
            "max_risk_expert_weights": [0.3, 0.4],
            "smoothing_alphas": [0.35, 0.5],
        },
    }


def _build_source_locked_fixture(root: Path) -> tuple[Path, Path]:
    panel_dir = root / "model-test" / "outputs" / "panel_fixture"
    panel_dir.mkdir(parents=True)
    dates = pd.date_range("2025-01-01", periods=280, freq="B")
    split = {
        "split_id": "wf_01",
        "train_start": dates[0].date().isoformat(),
        "train_end": dates[109].date().isoformat(),
        "validation_start": dates[150].date().isoformat(),
        "validation_end": dates[199].date().isoformat(),
        "test_start": dates[240].date().isoformat(),
        "test_end": dates[279].date().isoformat(),
        "purge_days": 20,
        "embargo_days": 20,
        "status": "ready",
        "reason": None,
    }
    ranges = {"train": (0, 109), "validation": (150, 199), "test": (240, 279)}
    rows: list[dict] = []
    expert_spec = {
        "sm": ("sm", 0.8),
        "fsm": ("fsm", 0.6),
        "adaptive_router": ("rsm_adaptive_v1", 0.9),
        "cash": (None, 0.0),
    }
    for day_index, date in enumerate(dates):
        state_id = int((day_index // 8) % 2)
        for expert_id, (source_model_id, target_position) in expert_spec.items():
            unavailable = expert_id == "fsm" and day_index == 246
            utility = {"sm": 0.020 if state_id == 0 else 0.006, "fsm": 0.012, "adaptive_router": 0.034 if state_id == 1 else -0.008, "cash": 0.0}[expert_id]
            net_return = {"sm": 0.0015 if state_id == 0 else 0.0005, "fsm": 0.0010, "adaptive_router": 0.0025 if state_id == 1 else -0.0005, "cash": 0.0}[expert_id]
            label_end_index = day_index + 20
            membership: list[dict[str, str]] = []
            if not unavailable and label_end_index < len(dates):
                for role, (start, end) in ranges.items():
                    if start <= day_index <= end and label_end_index <= end:
                        membership.append({"split_id": "wf_01", "role": role})
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
                    "strategy_return": None if unavailable else net_return,
                    "future_utility": None if unavailable or label_end_index >= len(dates) else utility,
                    "future_net_return": None if unavailable or label_end_index >= len(dates) else utility + 0.01,
                    "future_downside": None if unavailable or label_end_index >= len(dates) else 0.01,
                    "future_turnover_penalty": None if unavailable or label_end_index >= len(dates) else 0.02,
                    "ret_5": (day_index % 11) / 100.0,
                    "state_id": state_id,
                    "label_end_date": dates[label_end_index] if label_end_index < len(dates) else None,
                    "split_memberships_json": json.dumps(membership),
                    "feature_columns_json": json.dumps(["ret_5", "state_id", "target_position"]),
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
            {"control_id": "best_single_expert", "status": "ready", "selected_model_ids": json.dumps(["fsm"]), "source_model_id": "fsm"},
            {"control_id": "equal_weight_experts", "status": "ready", "selected_model_ids": json.dumps([]), "source_model_id": None},
            {"control_id": "adaptive_router_v1", "status": "ready", "selected_model_ids": json.dumps(["rsm_adaptive_v1"]), "source_model_id": "rsm_adaptive_v1"},
        ]
    ).to_csv(panel_dir / "baseline_results.csv", index=False)
    phase_c_config = root / "model-test" / "configs" / "moe_phase_d_source.json"
    _write_json(phase_c_config, _phase_c_config())
    phase_c_dir = root / "model-test" / "outputs" / "phase_c_fixture"
    materialize_dynamic_ensemble(phase_c_config, repo_root=root, output_dir=phase_c_dir)
    phase_d_config = root / "model-test" / "configs" / "moe_phase_d_fixture.json"
    _write_json(phase_d_config, _phase_d_config())
    return phase_d_config, phase_c_dir


def test_phase_d_materializer_writes_quantile_risk_and_comparison_artifacts(tmp_path: Path) -> None:
    config_path, _ = _build_source_locked_fixture(tmp_path)
    outputs = materialize_dynamic_ensemble_v2(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_d_output")

    expected = {
        "moe_v2_model",
        "feature_schema",
        "daily_weights",
        "summary",
        "uncertainty_calibration",
        "risk_ablation",
        "v1_v2_comparison",
        "report",
        "manifest",
    }
    assert set(outputs) == expected
    assert all(path.is_file() for path in outputs.values())
    weights = pd.read_parquet(outputs["daily_weights"])
    summary = pd.read_csv(outputs["summary"])
    calibration = pd.read_csv(outputs["uncertainty_calibration"])
    ablation = pd.read_csv(outputs["risk_ablation"])
    comparison = pd.read_csv(outputs["v1_v2_comparison"])

    assert {"moe_v2_no_state", "moe_v2_regime_aware"}.issubset(set(summary["variant"]))
    assert {"moe_v1_no_state", "moe_v1_regime_aware", "moe_v2_no_state", "moe_v2_regime_aware"}.issubset(
        set(comparison["variant"])
    )
    assert calibration["status"].eq("ready").all()
    assert len(ablation) == 16
    dynamic = weights.loc[weights["variant"] == "moe_v2_regime_aware"]
    sums = dynamic.groupby(["split_id", "date", "symbol"])["expert_weight"].sum()
    assert (sums - 1.0).abs().max() < 1e-9
    assert dynamic.loc[dynamic["expert_id"] != "cash", "expert_weight"].max() <= 0.4000000001
    ordinary = dynamic.loc[~dynamic["weight_change_reason"].fillna("").str.contains("safety")]
    assert ordinary["portfolio_turnover"].max() <= 0.1200000001
    assert dynamic["weight_change_reason"].fillna("").str.contains("missing_expert_safety_exit").any()
    assert {"predicted_lower_utility", "predicted_median_utility", "uncertainty_width", "conservative_score"}.issubset(
        dynamic.columns
    )


def test_phase_d_explicit_degradation_policies_are_auditable() -> None:
    group = pd.DataFrame(
        [
            {"expert_id": "cash", "eligible_for_weight": True, "predicted_lower_utility": 0.0, "predicted_median_utility": 0.0, "input_out_of_distribution": False},
            {"expert_id": "sm", "eligible_for_weight": True, "predicted_lower_utility": 0.02, "predicted_median_utility": 0.12, "input_out_of_distribution": False},
            {"expert_id": "adaptive_router", "eligible_for_weight": True, "predicted_lower_utility": -0.08, "predicted_median_utility": 0.02, "input_out_of_distribution": False},
        ]
    )
    definition = {"adaptive_expert_id": "adaptive_router", "equal_weight_expert_ids": {"sm", "adaptive_router"}}
    gating = {"temperature": 0.05, "max_risk_expert_weight": 0.4, "smoothing_alpha": 0.5}
    fallback = {"low_confidence_policy": "cash", "high_disagreement_policy": "equal_weight", "out_of_distribution_policy": "adaptive_router"}

    _, weights, status, reason, diagnostics, safety = _quantile_weights_for_group(
        group,
        previous=None,
        definition=definition,
        gating=gating,
        uncertainty={"gamma": 0.5, "confidence_width_threshold": 0.04, "disagreement_std_threshold": 1.0, "ood_max_abs_zscore": 5.0},
        fallback=fallback,
    )
    assert (status, safety, diagnostics["fallback_trigger"]) == ("fallback", True, "low_confidence")
    assert weights == {"cash": 1.0}
    assert reason == "low_confidence:cash"

    group.loc[group["expert_id"] == "sm", "input_out_of_distribution"] = True
    _, weights, status, reason, diagnostics, _ = _quantile_weights_for_group(
        group,
        previous=None,
        definition=definition,
        gating=gating,
        uncertainty={"gamma": 0.5, "confidence_width_threshold": 1.0, "disagreement_std_threshold": 1.0, "ood_max_abs_zscore": 5.0},
        fallback=fallback,
    )
    assert status == "fallback"
    assert diagnostics["fallback_trigger"] == "out_of_distribution"
    assert reason == "out_of_distribution:adaptive_router"
    assert weights["adaptive_router"] == pytest.approx(0.4)
    assert weights["cash"] == pytest.approx(0.6)


def test_phase_d_fallback_may_bypass_constraints_only_when_it_de_risks() -> None:
    assert _strictly_reduces_risk({"cash": 1.0}, {"cash": 0.6, "sm": 0.4})
    assert not _strictly_reduces_risk({"cash": 0.6, "adaptive_router": 0.4}, {"cash": 1.0})
    assert not _strictly_reduces_risk({"cash": 0.0, "sm": 0.4, "fsm": 0.6}, {"cash": 0.0, "sm": 0.4, "fsm": 0.6})


def test_phase_d_config_is_not_an_accidental_research_campaign() -> None:
    us = load_dynamic_ensemble_v2_config(REPO_ROOT / "model-test" / "configs" / "moe_v2_us.json")
    cn = load_dynamic_ensemble_v2_config(REPO_ROOT / "model-test" / "configs" / "moe_v2_cn_a.json")
    assert (us["market"], cn["market"]) == ("US", "CN_A")
    with pytest.raises(ValueError, match="run_dynamic_ensemble_v2.py"):
        load_research_config(REPO_ROOT / "model-test" / "configs" / "moe_v2_us.json")
