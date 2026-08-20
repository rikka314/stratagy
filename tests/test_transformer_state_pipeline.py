from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from model_test.transformer_state_execution import ExecutionConfig
from model_test.transformer_state_pipeline import (
    TransformerStatePipelineError,
    _assert_daily_numeric_integrity,
    _assert_execution_evidence_complete,
    _load_execution_market_data,
    _memory_rows,
    _resolve_w15_fold_manifest,
    _resolve_w15_fold_output_dir,
    _target_dir,
    _verify_fixed_manifest_artifact,
    _verify_manifest_artifact,
    _verify_w15_fold_manifest,
    invalidate_downstream_manifests,
)


def test_memory_rows_join_only_realized_best_expert_components() -> None:
    sequences = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "symbol": ["AAA", "AAA"],
            "market": ["US", "US"],
            "best_expert_5d": ["sm", "cash"],
            "label_margin": [0.2, 0.3],
            "label_status": ["ready", "ready"],
        }
    )
    labels = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-02", "2025-01-03"]),
            "symbol": ["AAA", "AAA", "AAA"],
            "expert_id": ["sm", "cash", "cash"],
            "future_utility": [0.4, 0.1, 0.2],
            "future_net_return": [0.05, 0.0, 0.0],
            "future_downside": [0.01, 0.0, 0.0],
        }
    )

    rows = _memory_rows(
        sequences,
        labels,
        pd.Series([True, True]).to_numpy(),
        split_id="wf_01",
        source_sha256="a" * 64,
        encoder_sha256="b" * 64,
        feature_schema_sha256="c" * 64,
    )

    assert rows["future_5d_utility"].tolist() == [0.4, 0.2]
    assert rows["future_5d_drawdown"].tolist() == [-0.01, -0.0]
    assert rows["role"].eq("train").all()
    assert rows["label_status"].eq("available").all()


def test_frozen_market_configs_supply_w17_selected_values() -> None:
    root = Path(__file__).resolve().parents[1]
    for name, expected in (("transformer_state_us.json", "best_search"), ("transformer_state_cn_a.json", "sm")):
        config = json.loads((root / "model-test" / "configs" / name).read_text(encoding="utf-8"))
        resolved = ExecutionConfig.from_mapping(config)

        assert resolved.holding_days == 5
        assert resolved.matching_frequency_days == 5
        assert resolved.fallback_expert_ids["full_run_best_guard"] == expected


def test_execution_market_data_derives_point_in_time_atr(tmp_path) -> None:
    snapshot = tmp_path / "source" / "data_snapshot"
    snapshot.mkdir(parents=True)
    dates = pd.date_range("2025-01-01", periods=8, freq="D")
    pd.DataFrame(
        {
            "date": dates,
            "high": [11.0] * 8,
            "low": [9.0] * 8,
            "close": [10.0] * 8,
            "symbol": ["AAA"] * 8,
            "market": ["US"] * 8,
        }
    ).to_csv(snapshot / "AAA_daily.csv", index=False)

    result = _load_execution_market_data(
        tmp_path,
        {"sources": {"full_run_output_dir": "source"}},
    )

    assert result.loc[4:, "atr_pct"].eq(0.2).all()


def test_transformer_output_cannot_collide_with_source_directories(tmp_path) -> None:
    config = {
        "output_subdir": "transformer",
        "sources": {
            "phase_a_output_dir": "outputs/source",
            "phase_b_output_dir": "outputs/source",
            "full_run_output_dir": "outputs/full",
        },
    }

    with pytest.raises(TransformerStatePipelineError, match="collides"):
        _target_dir(tmp_path, config, tmp_path / "outputs" / "source" / "nested")


def test_w18_requires_executed_and_skipped_rows_to_cover_every_w16_decision() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    decisions = pd.DataFrame(
        {
            "split_id": ["wf_01", "wf_01"],
            "date": dates,
            "symbol": ["AAA", "AAA"],
            "market": ["US", "US"],
            "threshold_variant": ["balanced", "balanced"],
        }
    )
    daily = pd.DataFrame(
        {
            "split_id": ["wf_01"],
            "date": [dates[1]],
            "symbol": ["AAA"],
            "market": ["US"],
            "threshold": ["balanced"],
            "variant": ["primary"],
            "decision_date": [dates[0]],
            "holding_day": [1],
            "decision_marker": [True],
        }
    )
    skipped = pd.DataFrame(
        {
            "split_id": ["wf_01"],
            "date": [dates[1]],
            "symbol": ["AAA"],
            "market": ["US"],
            "threshold": ["balanced"],
            "variant": ["primary"],
        }
    )

    _assert_execution_evidence_complete(
        decisions,
        daily,
        skipped,
        expected_variants={"primary"},
        holding_days=1,
    )
    with pytest.raises(TransformerStatePipelineError, match="does not exactly cover"):
        _assert_execution_evidence_complete(
            decisions,
            daily,
            skipped.iloc[0:0],
            expected_variants={"primary"},
            holding_days=1,
        )


def test_upstream_refresh_immediately_invalidates_every_downstream_manifest(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    phase_files = {
        "W13": "transformer_state_source_manifest.json",
        "W14": "state_panel_manifest.json",
        "W15": "transformer_state_model_manifest.json",
        "W16": "state_retrieval_manifest.json",
        "W17": "state_execution_manifest.json",
        "W18": "transformer_state_evidence_manifest.json",
    }
    for phase, name in phase_files.items():
        (tmp_path / name).write_text(
            json.dumps({"phase": phase, "status": "ready"}),
            encoding="utf-8",
        )

    written = invalidate_downstream_manifests(
        root / "model-test" / "configs" / "transformer_state_us.json",
        repo_root=root,
        after_phase="W15",
        output_dir=tmp_path,
    )

    assert set(written) == {"W16", "W17", "W18"}
    for phase in ("W13", "W14", "W15"):
        payload = json.loads((tmp_path / phase_files[phase]).read_text(encoding="utf-8"))
        assert payload["status"] == "ready"
    for phase in ("W16", "W17", "W18"):
        payload = json.loads((tmp_path / phase_files[phase]).read_text(encoding="utf-8"))
        assert payload["status"] == "blocked"
        assert payload["invalidated_by_phase"] == "W15"


def test_manifest_artifact_and_w15_fold_paths_cannot_escape_output_directory(tmp_path: Path) -> None:
    target = tmp_path / "output"
    target.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    manifest = {
        "artifacts": {
            "escape": {
                "path": "../outside.json",
                "sha256": "0" * 64,
            }
        }
    }

    with pytest.raises(TransformerStatePipelineError, match="escapes output directory"):
        _verify_manifest_artifact(target, manifest, "escape")
    alternate = target / "alternate.json"
    alternate.write_text("{}", encoding="utf-8")
    fixed_manifest = {
        "artifacts": {
            "fixed": {
                "path": "alternate.json",
                "sha256": hashlib.sha256(alternate.read_bytes()).hexdigest(),
            }
        }
    }
    with pytest.raises(TransformerStatePipelineError, match="must resolve to the fixed path"):
        _verify_fixed_manifest_artifact(target, fixed_manifest, "fixed", "required.json")
    with pytest.raises(TransformerStatePipelineError, match="fold manifest path is invalid"):
        _resolve_w15_fold_manifest(
            target,
            {"split_id": "wf_01", "manifest_path": "../outside.json"},
        )
    with pytest.raises(TransformerStatePipelineError, match="not a safe path component"):
        _resolve_w15_fold_output_dir(target, "../escape")


def test_w15_fold_verifier_rejects_inner_artifact_escape_and_lineage_drift(tmp_path: Path) -> None:
    target = tmp_path / "output"
    fold_dir = target / "folds" / "wf_01"
    fold_dir.mkdir(parents=True)
    expected_lock = {
        "config_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "panel_manifest_sha256": "c" * 64,
        "sequence_panel_sha256": "d" * 64,
        "feature_schema_sha256": "e" * 64,
        "code_lock_aggregate_sha256": "f" * 64,
    }
    artifacts = {
        name: {"path": f"{name}.json", "sha256": "0" * 64}
        for name in (
            "transformer_encoder",
            "state_embedding_schema",
            "train_metrics",
            "validation_metrics",
            "training_log",
        )
    }
    artifacts["transformer_encoder"] = {
        "path": "../../../outside.pt",
        "sha256": "0" * 64,
    }
    manifest = {
        "status": "ready",
        "market": "US",
        "split_id": "wf_01",
        "source_lock": expected_lock,
        "artifacts": artifacts,
    }
    manifest_path = fold_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    entry = {
        "split_id": "wf_01",
        "status": "ready",
        "manifest_path": "folds/wf_01/manifest.json",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }

    with pytest.raises(TransformerStatePipelineError, match="escapes fold directory"):
        _verify_w15_fold_manifest(
            target,
            entry,
            market="US",
            expected_source_lock=expected_lock,
        )

    manifest["source_lock"] = {**expected_lock, "feature_schema_sha256": "9" * 64}
    manifest["artifacts"]["transformer_encoder"]["path"] = "transformer_encoder.pt"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    entry["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(TransformerStatePipelineError, match="fold source lock drifted"):
        _verify_w15_fold_manifest(
            target,
            entry,
            market="US",
            expected_source_lock=expected_lock,
        )


def test_w18_rejects_nonfinite_daily_values_and_persisted_turnover_drift() -> None:
    daily = pd.DataFrame(
        {
            "split_id": ["wf_01", "wf_01"],
            "threshold": ["balanced", "balanced"],
            "variant": ["primary", "primary"],
            "symbol": ["AAA", "AAA"],
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "strategy_return": [0.0, 0.01],
            "target_position": [0.0, 0.5],
            "decision_target_position": [0.0, 0.5],
            "source_expert_strategy_return": [0.0, 0.01],
            "source_expert_target_position": [0.0, 0.5],
            "counterfactual_no_guard_return": [0.0, 0.01],
            "adaptive_return": [0.0, 0.01],
            "execution_turnover": [0.0, 0.5],
            "equity_before": [1.0, 1.0],
            "geometric_return_contribution": [0.0, 0.01],
            "full_run_best_only_return": [0.0, 0.01],
        }
    )
    _assert_daily_numeric_integrity(daily)

    drifted = daily.copy()
    drifted.loc[1, "execution_turnover"] = 0.0
    with pytest.raises(TransformerStatePipelineError, match="does not reconstruct"):
        _assert_daily_numeric_integrity(drifted)

    nonfinite = daily.copy()
    nonfinite.loc[1, "target_position"] = float("inf")
    with pytest.raises(TransformerStatePipelineError, match="non-finite"):
        _assert_daily_numeric_integrity(nonfinite)
