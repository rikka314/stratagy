from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from model_test.moe_baseline import (
    MoEBaselineError,
    build_phase_a_manifest,
    load_moe_baseline_config,
    materialize_phase_a_baseline,
)
from model_test.config import load_research_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def _phase_a_config() -> dict:
    return {
        "schema_version": "1.0",
        "name": "moe_fixture",
        "phase": "A",
        "market": "US",
        "output_subdir": "moe_fixture",
        "random_seed": 42,
        "training_scope": "market_specific",
        "cross_market_policy": "ablation_only",
        "source_runs": {
            "full_run": {
                "output_dir": "model-test/outputs/full_fixture",
                "config_path": "model-test/configs/full_fixture.json",
            },
        },
        "horizons": {"primary_days": 20, "ablation_days": [5, 60]},
        "returns": {
            "net_return_field": "strategy_return",
            "gross_return_field": "gross_strategy_return",
            "transaction_cost_field": "transaction_cost",
            "cost_treatment": "source_net_no_recharge",
        },
        "execution": {"commission_bps": 1, "slippage_bps": 2},
        "train_selection": {
            "scope": "market_train_only",
            "forbid_test_columns": True,
            "score_formula": "fixture",
            "score_weights": {
                "train_sharpe": 1.0,
                "train_annret": 2.0,
                "train_maxdd_penalty": 0.5,
            },
            "tie_break": ["coverage_rate_desc", "median_train_annret_desc", "model_id_asc"],
        },
        "experts": [
            {
                "expert_id": model_id,
                "source_model_id": model_id,
                "availability": "required",
                "include_in_equal_weight": True,
            }
            for model_id in ("naive", "drift", "sm", "fsm", "rsm_adaptive_v1")
        ]
        + [
            {
                "expert_id": "cash",
                "source_model_id": None,
                "availability": "required",
                "include_in_equal_weight": False,
            }
        ],
        "baseline_controls": [
            {"control_id": "best_single_expert"},
            {"control_id": "equal_weight_experts"},
            {
                "control_id": "adaptive_router_v1",
                "source_model_id": "rsm_adaptive_v1",
                "availability": "required",
            },
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_source(root: Path, config: dict, source_name: str, *, with_runs: bool) -> None:
    source = config["source_runs"][source_name]
    source_dir = root / source["output_dir"]
    source_dir.mkdir(parents=True, exist_ok=True)
    _write_json(root / source["config_path"], {"name": source_name})
    snapshot_file = source_dir / "data_snapshot" / "AAA_daily.csv"
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_bytes(b"date,close\n2026-01-05,100\n")
    snapshot_digest = hashlib.sha256(snapshot_file.read_bytes()).hexdigest()
    snapshot_entry = {
        "symbol": "AAA",
        "path": str(snapshot_file.resolve()),
        "sha256": snapshot_digest,
        "size_bytes": snapshot_file.stat().st_size,
    }
    snapshot_aggregate = hashlib.sha256(
        json.dumps(
            [{key: snapshot_entry[key] for key in ("symbol", "sha256", "size_bytes")}],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    _write_json(
        source_dir / "data_manifest.json",
        {
            "schema_version": "1.0",
            "market": "US",
            "run_id": f"{source_name}-run",
            "code_version": "abc123",
            "random_seed": 42,
            "data": {"snapshot_sha256": snapshot_aggregate},
            "universe": {"files": [snapshot_entry]},
            "execution": {"market": "US", "commission_bps": 1, "slippage_bps": 2},
        },
    )
    _write_json(
        source_dir / "config_snapshot.json",
        {"name": source_name, "market": "US", "commission_bps": 1, "slippage_bps": 2},
    )
    _write_json(source_dir / "report.json", {"source": source_name})
    pd.DataFrame([{"model_id": "fsm", "rank": 1}]).to_csv(source_dir / "model_summary.csv", index=False)
    pd.DataFrame([{"symbol": "AAA"}, {"symbol": "BBB"}]).to_csv(source_dir / "stocks.csv", index=False)

    if not with_runs:
        pd.DataFrame([{"symbol": "AAA", "model_id": "naive"}]).to_csv(source_dir / "runs.csv", index=False)
        return

    rows = []
    train_stats = {
        "naive": (0.1, 0.03, -0.10),
        "drift": (0.2, 0.04, -0.09),
        "sm": (0.3, 0.05, -0.08),
        "fsm": (0.8, 0.12, -0.06),
        "rsm_adaptive_v1": (0.4, 0.06, -0.07),
    }
    net_returns = {
        "naive": 0.001,
        "drift": 0.002,
        "sm": 0.003,
        "fsm": 0.004,
        "rsm_adaptive_v1": 0.005,
    }
    for symbol in ("AAA", "BBB"):
        for model_id, (train_sharpe, train_annret, train_maxdd) in train_stats.items():
            artifact = source_dir / "artifacts" / symbol / "main" / model_id / "returns.csv"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "date": ["2026-01-05", "2026-01-06", "2026-01-07"],
                    "strategy_return": [net_returns[model_id]] * 3,
                }
            ).to_csv(artifact, index=False)
            rows.append(
                {
                    "symbol": symbol,
                    "model_id": model_id,
                    "window_kind": "main",
                    "status": "success",
                    "train_sharpe": train_sharpe,
                    "train_annret": train_annret,
                    "train_maxdd": train_maxdd,
                    "returns_path": str(Path("artifacts") / symbol / "main" / model_id / "returns.csv"),
                    "total_turnover": 1.0,
                    "total_transaction_cost": 0.75,
                    "test_sharpe": 999.0 if model_id == "naive" else -999.0,
                }
            )
    pd.DataFrame(rows).to_csv(source_dir / "runs.csv", index=False)


def test_repository_phase_a_configs_freeze_market_specific_contracts() -> None:
    us = load_moe_baseline_config(REPO_ROOT / "model-test" / "configs" / "moe_baseline_us.json")
    cn = load_moe_baseline_config(REPO_ROOT / "model-test" / "configs" / "moe_baseline_cn_a.json")

    assert us["market"] == "US"
    assert cn["market"] == "CN_A"
    assert us["cross_market_policy"] == cn["cross_market_policy"] == "ablation_only"
    assert us["horizons"] == cn["horizons"] == {"primary_days": 20, "ablation_days": [5, 60]}
    assert us["execution"] == {"commission_bps": 1, "slippage_bps": 2}
    assert cn["execution"] == {"commission_bps": 3, "slippage_bps": 5}
    assert us["returns"]["cost_treatment"] == cn["returns"]["cost_treatment"] == "source_net_no_recharge"
    assert set(us["source_runs"]) == set(cn["source_runs"]) == {"full_run"}
    assert us["historical_runs"][0]["classification"] == "non_authoritative_smoke"
    assert [row["control_id"] for row in us["baseline_controls"]] == [
        "best_single_expert",
        "equal_weight_experts",
        "adaptive_router_v1",
    ]
    cn_router = next(row for row in cn["baseline_controls"] if row["control_id"] == "adaptive_router_v1")
    assert cn_router["availability"] == "known_unavailable"
    with pytest.raises(ValueError, match="prepare_moe_baseline.py"):
        load_research_config(REPO_ROOT / "model-test" / "configs" / "moe_baseline_us.json")


def test_materializer_uses_train_only_selection_and_reuses_net_returns(tmp_path: Path) -> None:
    config = _phase_a_config()
    config_path = tmp_path / "model-test" / "configs" / "moe_fixture.json"
    _write_json(config_path, config)
    _write_source(tmp_path, config, "full_run", with_runs=True)

    output_dir = tmp_path / "phase_a_output"
    outputs = materialize_phase_a_baseline(
        config_path,
        repo_root=tmp_path,
        output_dir=output_dir,
    )

    manifest = json.loads(outputs["data_manifest"].read_text(encoding="utf-8"))
    results = pd.read_csv(outputs["baseline_results"])
    selection = pd.read_csv(outputs["train_selection_summary"])

    assert manifest["status"] == "ready"
    assert all(source["data_snapshot_sha256"] for source in manifest["sources"])
    assert set(results["status"]) == {"ready"}
    best = results.loc[results["control_id"] == "best_single_expert"].iloc[0]
    assert json.loads(best["selected_model_ids"]) == ["fsm"]
    assert selection.iloc[0]["model_id"] == "fsm"
    assert best["total_return"] == pytest.approx((1.004**3) - 1.0)
    assert best["source_total_transaction_cost_mean"] == pytest.approx(0.75)
    equal_weight = results.loc[results["control_id"] == "equal_weight_experts"].iloc[0]
    assert equal_weight["total_return"] == pytest.approx((1.003**3) - 1.0)


def test_missing_sources_fail_strict_mode_and_remain_explicit_when_allowed(tmp_path: Path) -> None:
    config = _phase_a_config()
    config_path = tmp_path / "model-test" / "configs" / "moe_fixture.json"
    _write_json(config_path, config)

    manifest = build_phase_a_manifest(config_path, repo_root=tmp_path)
    assert manifest["status"] == "pending"
    assert any(source["issues"] for source in manifest["sources"])

    with pytest.raises(MoEBaselineError, match="source validation failed"):
        materialize_phase_a_baseline(
            config_path,
            repo_root=tmp_path,
            output_dir=tmp_path / "strict-output",
        )
    assert not (tmp_path / "strict-output").exists()

    outputs = materialize_phase_a_baseline(
        config_path,
        repo_root=tmp_path,
        output_dir=tmp_path / "pending-output",
        allow_pending=True,
    )
    results = pd.read_csv(outputs["baseline_results"])
    assert set(results["status"]) == {"unavailable"}
    assert set(results["control_id"]) == {
        "best_single_expert",
        "equal_weight_experts",
        "adaptive_router_v1",
    }


def test_source_snapshot_must_match_manifest_and_historical_smoke_does_not_gate(tmp_path: Path) -> None:
    config = _phase_a_config()
    config["historical_runs"] = [
        {
            "run_id": "historical-smoke",
            "output_dir": "model-test/outputs/historical-smoke",
            "config_path": "model-test/configs/historical-smoke.json",
            "classification": "non_authoritative_smoke",
            "reason": "diagnostic-only",
        }
    ]
    config_path = tmp_path / "model-test" / "configs" / "moe_fixture.json"
    _write_json(config_path, config)
    _write_source(tmp_path, config, "full_run", with_runs=True)

    manifest = build_phase_a_manifest(config_path, repo_root=tmp_path)
    assert manifest["status"] == "ready"
    assert manifest["sources"][0]["snapshot_file_count"] == 1
    assert manifest["historical_runs"] == config["historical_runs"]

    snapshot_file = tmp_path / config["source_runs"]["full_run"]["output_dir"] / "data_snapshot" / "AAA_daily.csv"
    snapshot_file.write_bytes(b"tampered")
    tampered = build_phase_a_manifest(config_path, repo_root=tmp_path)
    assert tampered["status"] == "pending"
    assert any("source snapshot hash mismatch" in issue for issue in tampered["sources"][0]["issues"])


def test_known_unavailable_router_is_not_silently_substituted(tmp_path: Path) -> None:
    config = _phase_a_config()
    router_expert = next(row for row in config["experts"] if row["expert_id"] == "rsm_adaptive_v1")
    router_expert["availability"] = "known_unavailable"
    router_expert["include_in_equal_weight"] = False
    router_control = next(
        row for row in config["baseline_controls"] if row["control_id"] == "adaptive_router_v1"
    )
    router_control["availability"] = "known_unavailable"
    router_control["unavailable_reason"] = "market-native artifact unavailable"
    config_path = tmp_path / "model-test" / "configs" / "moe_fixture.json"
    _write_json(config_path, config)
    _write_source(tmp_path, config, "full_run", with_runs=True)

    outputs = materialize_phase_a_baseline(
        config_path,
        repo_root=tmp_path,
        output_dir=tmp_path / "phase_a_output",
    )
    results = pd.read_csv(outputs["baseline_results"])
    router = results.loc[results["control_id"] == "adaptive_router_v1"].iloc[0]

    assert router["status"] == "unavailable"
    assert router["reason"] == "market-native artifact unavailable"
    assert json.loads(router["selected_model_ids"]) == []
