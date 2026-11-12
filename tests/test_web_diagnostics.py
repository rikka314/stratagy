from types import SimpleNamespace

import pandas as pd
import pytest

from api.diagnostics import build_artifact_diagnostics, build_walk_forward
from core.backtest import walk_forward_backtest


def test_walk_forward_matches_existing_engine():
    frame = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=40),
        "close": [100 + i for i in range(40)],
        "target_position": [0.5] * 40,
    })
    frame["open"] = frame["close"]
    frame["high"] = frame["close"] + 1
    frame["low"] = frame["close"] - 1
    frame["atr"] = 2.0
    expected_windows, expected_equity = walk_forward_backtest(frame, 20, 10, 0, 0)
    actual = build_walk_forward(frame, {}, 20, 10)
    pd.testing.assert_frame_equal(actual["windows"], expected_windows)
    pd.testing.assert_frame_equal(actual["equity"], expected_equity)


@pytest.mark.parametrize("train,test", [(0, 5), (5, 0), (-2, 5), (30, 20)])
def test_walk_forward_rejects_invalid_windows(train, test):
    with pytest.raises(ValueError):
        build_walk_forward(pd.DataFrame({"close": range(40)}), {}, train, test)


def test_diagnostics_use_daily_returns_and_keep_splits_separate():
    test = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-30", "2025-01-31", "2025-02-01"]),
        "strategy_equity": [1.1, 0.99, 1.089],
        "strategy_return": [0.1, -0.1, 0.1],
        "buy_hold_return": [0.0, 0.01, 0.02],
    })
    artifact = SimpleNamespace(test_sim_df=test, train_sim_df=test.iloc[:1],
                               ml_quality=None, full_signal_df=pd.DataFrame())
    result = build_artifact_diagnostics(artifact)
    assert result["test"]["drawdown"]["drawdown"].tolist() == pytest.approx([0, -0.1, -0.01])
    assert result["test"]["monthly_returns"]["strategy_return"].tolist() == pytest.approx([-0.01, 0.1])
    assert len(result["train"]["drawdown"]) == 1
    assert result["ml_quality"] is None


def test_missing_returns_are_unavailable_not_zero():
    artifact = SimpleNamespace(test_sim_df=pd.DataFrame(), train_sim_df=pd.DataFrame(),
                               ml_quality=None, full_signal_df=pd.DataFrame())
    result = build_artifact_diagnostics(artifact)
    assert result["test"]["monthly_returns"].empty
    assert result["test"]["drawdown"].empty
