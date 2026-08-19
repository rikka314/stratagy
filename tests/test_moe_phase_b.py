from __future__ import annotations

import json

import pandas as pd
import pytest

from model_test.expert_panel import (
    ExpertPanelError,
    _derive_market_state_features,
    build_purged_walk_forward_splits,
    compute_future_utility,
    resolve_phase_b_split_policy,
    validate_panel_no_leakage,
    validate_purged_walk_forward_splits,
)


def test_future_utility_uses_next_horizon_and_does_not_recharge_costs() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=5),
            "strategy_return": [0.10, 0.20, -0.10, 0.05, 0.10],
            "turnover": [0.0, 0.1, 0.2, 0.0, 0.0],
            "transaction_cost": [99.0] * 5,
        }
    )
    result = compute_future_utility(frame, horizon_days=2, lambda_downside=1.0, lambda_turnover=0.5)

    # t=0 sees only t+1 and t+2.  No transaction_cost column is consulted.
    assert result.loc[0, "future_net_return"] == pytest.approx((1.20 * 0.90) - 1.0)
    assert result.loc[0, "future_downside"] == pytest.approx(0.10)
    assert result.loc[0, "future_turnover_penalty"] == pytest.approx(0.30)
    assert result.loc[0, "future_utility"] == pytest.approx(-0.17)
    assert result["future_utility"].iloc[-2:].isna().all()


def test_purged_walk_forward_has_horizon_purge_and_embargo() -> None:
    dates = pd.date_range("2020-01-01", periods=240, freq="D")
    splits = build_purged_walk_forward_splits(
        dates,
        primary_horizon_days=20,
        n_splits=3,
        min_train_days=40,
        validation_days=20,
        test_days=20,
    )
    assert len(splits) == 3
    validate_purged_walk_forward_splits(splits, primary_horizon_days=20)
    for row in splits.to_dict("records"):
        train_end = pd.Timestamp(row["train_end"])
        validation_start = pd.Timestamp(row["validation_start"])
        validation_end = pd.Timestamp(row["validation_end"])
        test_start = pd.Timestamp(row["test_start"])
        assert (validation_start - train_end).days >= 40
        assert (test_start - validation_end).days >= 40


def test_default_evaluation_windows_leave_room_for_complete_future_labels() -> None:
    splits = build_purged_walk_forward_splits(pd.date_range("2020-01-01", periods=420, freq="B"))

    assert len(splits) == 3
    first = splits.iloc[0]
    validation_days = pd.date_range(first["validation_start"], first["validation_end"], freq="B")
    test_days = pd.date_range(first["test_start"], first["test_end"], freq="B")
    assert len(validation_days) == 40
    assert len(test_days) == 40


def test_admission_split_policy_requires_four_splits_from_the_frozen_config() -> None:
    policy = resolve_phase_b_split_policy({"phase_b": {"n_splits": 4}})

    assert policy["n_splits"] == 4
    assert policy["source"] == "config.phase_b.n_splits"


def test_panel_leakage_validator_rejects_duplicate_keys_and_future_features() -> None:
    panel = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "symbol": ["AAA", "AAA"],
            "market": ["US", "US"],
            "expert_id": ["sm", "sm"],
            "feature_columns_json": [json.dumps(["future_utility"])] * 2,
        }
    )
    with pytest.raises(ExpertPanelError, match="duplicate"):
        validate_panel_no_leakage(panel)

    panel = panel.iloc[[0]].copy()
    panel["expert_id"] = "fsm"
    with pytest.raises(ExpertPanelError, match="future label"):
        validate_panel_no_leakage(panel)


def test_split_builder_returns_empty_for_insufficient_history() -> None:
    splits = build_purged_walk_forward_splits(
        pd.date_range("2026-01-01", periods=10),
        primary_horizon_days=20,
        n_splits=3,
    )
    assert splits.empty


def test_legacy_market_state_features_are_trailing_and_auditable() -> None:
    dates = pd.date_range("2025-01-01", periods=90, freq="B")
    panel = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["AAA"] * len(dates) + ["BBB"] * len(dates),
            "market_trend_20": [0.01] * 45 + [-0.01] * 45 + [0.02] * len(dates),
            "market_volatility_20": list(range(len(dates))) + list(range(len(dates))),
        }
    )

    derived, columns = _derive_market_state_features(panel)

    assert columns == [
        "state_market_trend_up_20",
        "state_market_high_volatility_20",
        "state_market_regime_id_20",
    ]
    aaa = derived.loc[derived["symbol"].eq("AAA")].sort_values("date").reset_index(drop=True)
    assert aaa.loc[70, "state_market_trend_up_20"] == 0.0
    assert aaa.loc[70, "state_market_high_volatility_20"] == 1.0
    assert aaa.loc[70, "state_market_regime_id_20"] == 1.0

    changed = panel.copy()
    changed.loc[changed.index[-1], ["market_trend_20", "market_volatility_20"]] = [999.0, 999.0]
    changed_derived, _ = _derive_market_state_features(changed)
    stable_columns = ["state_market_trend_up_20", "state_market_high_volatility_20", "state_market_regime_id_20"]
    pd.testing.assert_frame_equal(
        derived.loc[derived["date"] < dates[-1], stable_columns].reset_index(drop=True),
        changed_derived.loc[changed_derived["date"] < dates[-1], stable_columns].reset_index(drop=True),
    )
