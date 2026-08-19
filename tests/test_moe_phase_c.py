from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from model_test.dynamic_ensemble import (
    DynamicEnsembleError,
    constrain_expert_weights,
    load_dynamic_ensemble_config,
    materialize_dynamic_ensemble,
    stable_softmax,
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


def _phase_c_config(panel_dir: str = "model-test/outputs/panel_fixture") -> dict:
    return {
        "schema_version": "1.0",
        "name": "moe_phase_c_fixture",
        "phase": "C",
        "market": "US",
        "panel_output_dir": panel_dir,
        "output_subdir": "moe_phase_c_fixture",
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


def _build_fixture_panel(root: Path) -> tuple[Path, Path]:
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
    ranges = {
        "train": (0, 109),
        "validation": (150, 199),
        "test": (240, 279),
    }
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
            utility = {
                "sm": 0.020 if state_id == 0 else 0.006,
                "fsm": 0.012,
                "adaptive_router": 0.034 if state_id == 1 else -0.008,
                "cash": 0.0,
            }[expert_id]
            net_return = {
                "sm": 0.0015 if state_id == 0 else 0.0005,
                "fsm": 0.0010,
                "adaptive_router": 0.0025 if state_id == 1 else -0.0005,
                "cash": 0.0,
            }[expert_id]
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
    config_path = root / "model-test" / "configs" / "moe_phase_c_fixture.json"
    _write_json(config_path, _phase_c_config())
    return config_path, panel_dir


def test_phase_c_materializer_writes_constrained_walk_forward_artifacts(tmp_path: Path) -> None:
    config_path, _ = _build_fixture_panel(tmp_path)
    outputs = materialize_dynamic_ensemble(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_c_output")

    assert {"model", "feature_schema", "daily_weights", "summary", "report", "manifest"} == set(outputs)
    assert all(path.is_file() for path in outputs.values())
    weights = pd.read_parquet(outputs["daily_weights"])
    schema = json.loads(outputs["feature_schema"].read_text(encoding="utf-8"))
    summary = pd.read_csv(outputs["summary"])

    assert schema["state_feature_columns"] == ["state_id"]
    assert "state_id" not in schema["no_state_feature_columns"]
    assert {"moe_no_state", "moe_regime_aware", "best_single_expert", "equal_weight_experts", "adaptive_router_v1"}.issubset(
        set(summary["variant"])
    )
    assert set(summary.loc[summary["status"] == "ready", "variant"]).issuperset({"moe_no_state", "moe_regime_aware"})

    dynamic = weights.loc[weights["variant"] == "moe_regime_aware"]
    sums = dynamic.groupby(["split_id", "date", "symbol"])["expert_weight"].sum()
    assert (sums - 1.0).abs().max() < 1e-9
    risk = dynamic.loc[dynamic["expert_id"] != "cash", "expert_weight"]
    assert risk.max() <= 0.4000000001
    unavailable = dynamic.loc[(dynamic["expert_id"] == "fsm") & (dynamic["expert_status"] == "unavailable")]
    assert not unavailable.empty
    assert unavailable["expert_weight"].eq(0.0).all()
    assert dynamic["final_target_position"].notna().all()


def test_phase_c_rejects_panel_hash_drift(tmp_path: Path) -> None:
    config_path, panel_dir = _build_fixture_panel(tmp_path)
    panel_path = panel_dir / "expert_day_panel.parquet"
    panel = pd.read_parquet(panel_path)
    panel.loc[0, "ret_5"] = 99.0
    panel.to_parquet(panel_path, index=False)

    with pytest.raises(DynamicEnsembleError, match="hash differs"):
        materialize_dynamic_ensemble(config_path, repo_root=tmp_path, output_dir=tmp_path / "phase_c_output")


def test_phase_c_config_and_weight_guards() -> None:
    us = load_dynamic_ensemble_config(REPO_ROOT / "model-test" / "configs" / "moe_v1_us.json")
    cn = load_dynamic_ensemble_config(REPO_ROOT / "model-test" / "configs" / "moe_v1_cn_a.json")
    assert us["market"] == "US"
    assert cn["market"] == "CN_A"
    with pytest.raises(ValueError, match="run_dynamic_ensemble.py"):
        load_research_config(REPO_ROOT / "model-test" / "configs" / "moe_v1_us.json")
    assert stable_softmax([1000.0, -1000.0], temperature=0.01).sum() == pytest.approx(1.0)
    weights, capped = constrain_expert_weights({"sm": 0.95, "cash": 0.05}, max_risk_expert_weight=0.4)
    assert capped is True
    assert weights["sm"] == pytest.approx(0.4)
    assert weights["cash"] == pytest.approx(0.6)
