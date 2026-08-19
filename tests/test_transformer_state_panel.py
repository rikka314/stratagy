from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_test.transformer_state_panel import (
    STATE_FEATURE_COLUMNS,
    TransformerStatePanelError,
    _attach_sequence_memberships,
    build_transformer_walk_forward_splits,
    _compute_five_day_labels,
    _position_proof,
    _snapshot_inventory,
    eligible_historical_memory,
    load_transformer_state_config,
    transformer_code_lock,
    validate_feature_columns,
    validate_sequence_panel,
)


def _minimal_label_config() -> dict[str, object]:
    return {
        "experts": ["cash", "sm"],
        "panel": {
            "lambda_downside": 1.0,
            "lambda_turnover": 0.1,
            "label_margin": 0.001,
        },
    }


def test_five_day_label_uses_only_next_complete_horizon_and_marks_ambiguity() -> None:
    dates = pd.date_range("2026-01-01", periods=7, freq="B")
    rows: list[dict[str, object]] = []
    for expert_id, returns in {
        "cash": [0.0] * 7,
        "sm": [0.9, 0.01, 0.0, 0.0, 0.0, 0.0, 99.0],
    }.items():
        for date, strategy_return in zip(dates, returns, strict=True):
            rows.append(
                {
                    "date": date,
                    "symbol": "AAA",
                    "market": "US",
                    "expert_id": expert_id,
                    "expert_status": "available",
                    "strategy_return": strategy_return,
                    "turnover": 0.0,
                }
            )

    result = _compute_five_day_labels(pd.DataFrame(rows), config=_minimal_label_config())
    first = result.loc[result["date"].eq(dates[0])]

    assert set(first["best_expert_5d"]) == {"sm"}
    assert set(first["label_status"]) == {"ready"}
    assert first.loc[first["expert_id"].eq("sm"), "future_net_return"].item() == pytest.approx(0.01)
    assert result.loc[result["date"].isin(dates[-5:]), "future_utility"].isna().all()
    # Current-day 0.9 and the out-of-horizon 99.0 are both excluded.
    assert first.loc[first["expert_id"].eq("sm"), "future_utility"].item() < 0.02


def test_feature_schema_rejects_future_and_outcome_columns() -> None:
    validate_feature_columns(STATE_FEATURE_COLUMNS)
    with pytest.raises(TransformerStatePanelError, match="future/outcome"):
        validate_feature_columns(["asset_return_1", "future_5d_utility"])
    with pytest.raises(TransformerStatePanelError, match="future/outcome"):
        validate_feature_columns(["best_expert_5d"])


def test_sequence_validator_enforces_same_ordered_history_and_shape() -> None:
    dates = pd.date_range("2026-01-01", periods=3, freq="B")
    panel = pd.DataFrame(
        [
            {
                "date": dates[-1],
                "symbol": "AAA",
                "market": "US",
                "sequence_start_date": dates[0],
                "sequence_end_date": dates[-1],
                "sequence_dates": [date.date().isoformat() for date in dates],
                "sequence_values": [[1.0], [np.nan], [3.0]],
                "sequence_missing_mask": [[False], [True], [False]],
                "label_end_date": dates[-1] + pd.Timedelta(days=7),
                "expert_utilities_json": json.dumps({"cash": 0.0, "sm": 0.1}),
                "split_memberships_json": "[]",
            }
        ]
    )
    validate_sequence_panel(panel, feature_columns=["asset_return_1"], expected_length=3)

    invalid = panel.copy()
    invalid.at[0, "sequence_dates"] = [dates[1].date().isoformat(), dates[0].date().isoformat(), dates[2].date().isoformat()]
    with pytest.raises(TransformerStatePanelError, match="non-chronological"):
        validate_sequence_panel(invalid, feature_columns=["asset_return_1"], expected_length=3)


def test_split_membership_requires_sequence_and_label_to_stay_inside_role() -> None:
    split = pd.DataFrame(
        [
            {
                "split_id": "wf_01",
                "train_start": "2026-01-01",
                "train_end": "2026-01-31",
                "validation_start": "2026-02-21",
                "validation_end": "2026-03-31",
                "test_start": "2026-04-21",
                "test_end": "2026-05-31",
            }
        ]
    )
    sequences = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-03-10"),
                "sequence_start_date": pd.Timestamp("2026-02-21"),
                "label_end_date": pd.Timestamp("2026-03-17"),
                "label_status": "ready",
            },
            {
                "date": pd.Timestamp("2026-03-10"),
                "sequence_start_date": pd.Timestamp("2026-02-20"),
                "label_end_date": pd.Timestamp("2026-03-17"),
                "label_status": "ready",
            },
            {
                "date": pd.Timestamp("2026-03-30"),
                "sequence_start_date": pd.Timestamp("2026-03-01"),
                "label_end_date": pd.Timestamp("2026-04-06"),
                "label_status": "ready",
            },
        ]
    )

    attached, counts = _attach_sequence_memberships(sequences, split)

    assert json.loads(attached.loc[0, "split_memberships_json"]) == [
        {"role": "validation", "split_id": "wf_01"}
    ]
    assert json.loads(attached.loc[1, "split_memberships_json"]) == []
    assert json.loads(attached.loc[2, "split_memberships_json"]) == []
    assert counts == {"wf_01": {"validation": 1}}


def test_memory_date_filter_excludes_self_same_day_and_future() -> None:
    mask = eligible_historical_memory(
        "2026-01-03", ["2026-01-01", "2026-01-03", "2026-01-04"]
    )
    assert mask.tolist() == [True, False, False]


def test_snapshot_inventory_recomputes_each_file_and_aggregate(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "data_snapshot"
    snapshot_dir.mkdir()
    snapshot_path = snapshot_dir / "AAA_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.0],
            "volume": [100.0],
            "market": ["US"],
        }
    ).to_csv(snapshot_path, index=False)
    digest = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    portable = [{"symbol": "AAA", "sha256": digest, "size_bytes": snapshot_path.stat().st_size}]
    aggregate = hashlib.sha256(
        json.dumps(portable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    config = {
        "market": "US",
        "sources": {"data_snapshot_sha256": aggregate},
        "benchmark": {"minimum_constituents": 1, "method": "test_equal_weight"},
    }
    manifest = {
        "data": {"snapshot_sha256": aggregate},
        "universe": {"files": portable},
    }

    inventory = _snapshot_inventory(config, full_dir=tmp_path, full_manifest=manifest)
    assert inventory["aggregate_sha256"] == aggregate

    snapshot_path.write_text(snapshot_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(TransformerStatePanelError, match="file drifted"):
        _snapshot_inventory(config, full_dir=tmp_path, full_manifest=manifest)


def test_transformer_code_lock_covers_executed_panel_dependencies(tmp_path: Path) -> None:
    relative_paths = [
        "model-test/model_test/expert_panel.py",
        "model-test/model_test/moe_baseline.py",
        "model-test/model_test/transformer_state_panel.py",
        "model-test/model_test/transformer_state_model.py",
        "model-test/run_transformer_state.py",
    ]
    for relative in relative_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")

    before = transformer_code_lock(tmp_path)
    dependency = tmp_path / "model-test/model_test/expert_panel.py"
    dependency.write_text("# changed dependency\n", encoding="utf-8")
    after = transformer_code_lock(tmp_path)

    assert before["aggregate_sha256"] != after["aggregate_sha256"]
    assert {entry["path"] for entry in after["artifacts"]} == set(relative_paths)


def test_transformer_splits_never_reuse_legacy_test_dates_for_fit_or_selection() -> None:
    dates = pd.date_range("2025-01-01", periods=360, freq="B")
    legacy = pd.DataFrame(
        [
            {
                "split_id": "wf_01",
                "train_start": dates[0],
                "train_end": dates[99],
                "validation_start": dates[120],
                "validation_end": dates[159],
                "test_start": dates[180],
                "test_end": dates[219],
            },
            {
                "split_id": "wf_02",
                "train_start": dates[0],
                "train_end": dates[119],
                "validation_start": dates[160],
                "validation_end": dates[179],
                "test_start": dates[220],
                "test_end": dates[259],
            },
            {
                "split_id": "wf_03",
                "train_start": dates[0],
                "train_end": dates[159],
                "validation_start": dates[180],
                "validation_end": dates[219],
                "test_start": dates[260],
                "test_end": dates[299],
            },
            {
                "split_id": "wf_04",
                "train_start": dates[0],
                "train_end": dates[179],
                "validation_start": dates[220],
                "validation_end": dates[259],
                "test_start": dates[300],
                "test_end": dates[339],
            },
        ]
    )

    splits, isolation = build_transformer_walk_forward_splits(
        legacy, dates, protection_days=20
    )
    legacy_test_dates = set()
    for row in legacy.to_dict("records"):
        legacy_test_dates.update(dates[(dates >= row["test_start"]) & (dates <= row["test_end"])])
    for row in splits.to_dict("records"):
        train = set(dates[(dates >= row["train_start"]) & (dates <= row["train_end"])])
        validation = set(
            dates[(dates >= row["validation_start"]) & (dates <= row["validation_end"])]
        )
        assert train.isdisjoint(legacy_test_dates)
        assert validation.isdisjoint(legacy_test_dates)
        assert int(((dates > row["train_end"]) & (dates < row["validation_start"])).sum()) >= 20
        assert int(((dates > row["validation_end"]) & (dates < row["test_start"])).sum()) >= 20
    assert splits.loc[splits["split_id"].eq("wf_01"), "source_train_validation_split_id"].item() == "wf_01"
    assert splits.loc[splits["split_id"].eq("wf_03"), "source_train_validation_split_id"].item() == "wf_02"
    assert isolation["legacy_test_date_count"] == 160


def test_zero_position_proof_is_strict_and_auditable(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    dates = pd.date_range("2026-01-01", periods=3, freq="B")
    pd.DataFrame({"date": dates, "strategy_return": [0.0, 0.0, 0.0]}).to_csv(
        artifact / "returns.csv", index=False
    )
    pd.DataFrame({"date": dates, "strategy_equity": [1.0, 1.0, 1.0]}).to_csv(
        artifact / "equity.csv", index=False
    )
    (artifact / "metadata.json").write_text(
        json.dumps({"status": "success", "eval": {"turnover": 0.0}}), encoding="utf-8"
    )

    proof = _position_proof(artifact)
    assert proof["method"] == "provable_zero_position"

    returns = pd.read_csv(artifact / "returns.csv")
    returns.loc[1, "strategy_return"] = 0.01
    returns.to_csv(artifact / "returns.csv", index=False)
    with pytest.raises(TransformerStatePanelError, match="cannot be proven zero"):
        _position_proof(artifact)

    pd.DataFrame(
        {"entry_date": [dates[0]], "exit_date": [dates[-1]], "trade_turnover": [2.4]}
    ).to_csv(artifact / "trades.csv", index=False)
    with pytest.raises(TransformerStatePanelError, match="cannot reconstruct exact daily"):
        _position_proof(artifact)


def test_daily_position_proof_requires_exact_unique_return_dates(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    dates = pd.date_range("2026-01-01", periods=3, freq="B")
    pd.DataFrame({"date": dates, "strategy_return": [0.0, 0.01, -0.01]}).to_csv(
        artifact / "returns.csv", index=False
    )
    pd.DataFrame({"date": dates, "target_position": [0.0, 0.5, 0.25]}).to_csv(
        artifact / "daily.csv", index=False
    )
    (artifact / "metadata.json").write_text("{}", encoding="utf-8")

    proof = _position_proof(artifact)
    assert proof["method"] == "source_target_position"

    pd.DataFrame(
        {"date": [dates[0], dates[2], dates[1]], "target_position": [0.0, 0.5, 0.25]}
    ).to_csv(artifact / "daily.csv", index=False)
    with pytest.raises(TransformerStatePanelError, match="incomplete"):
        _position_proof(artifact)

@pytest.mark.parametrize("name", ["transformer_state_us.json", "transformer_state_cn_a.json"])
def test_checked_in_transformer_configs_freeze_w13_to_w15_contract(name: str) -> None:
    config = load_transformer_state_config(Path("model-test/configs") / name)

    assert config["panel"]["label_horizon_days"] == 5
    assert config["panel"]["n_splits"] == 4
    assert config["retrieval"]["primary_variant"] == "state_match_balanced"
    assert config["full_run_best_guard"]["rank"] == 1
    assert config["transformer"]["runtime"] == "pytorch"
