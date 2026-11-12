"""Tests for Phase 3 position mapping and execution constraints."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_test.position_map_research import (
    PositionMapConfig,
    PositionMapResult,
    ExecutionConstraints,
    fit_position_map,
    compute_diagnostics,
)


@pytest.fixture
def sample_train_data():
    """Generate sample train data."""
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "score": np.random.randn(n),
            "returns": np.random.randn(n) * 0.01,
            "future_return": np.random.randn(n) * 0.02,
        }
    )


@pytest.fixture
def sample_test_data():
    """Generate sample test data."""
    np.random.seed(43)
    n = 50
    dates = pd.date_range("2024-04-11", periods=n, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "score": np.random.randn(n),
            "returns": np.random.randn(n) * 0.01,
            "future_return": np.random.randn(n) * 0.02,
        }
    )


def test_quantile_map_fit_transform(sample_train_data, sample_test_data):
    """Test quantile position map fitting and transformation."""
    config = PositionMapConfig(
        variant="quantile_5bin",
        p_max=1.0,
        positions=(0.0, 0.25, 0.50, 0.75, 1.0),
    )

    # Fit on train
    fitted = fit_position_map(
        config,
        train_score=sample_train_data["score"],
        train_returns=None,
        train_future_return=None,
    )

    assert fitted.fitted_quantiles is not None
    assert len(fitted.fitted_quantiles) == 5
    assert fitted.fitted_quantiles[0] <= fitted.fitted_quantiles[-1]

    # Transform test
    test_positions = fitted.transform(sample_test_data["score"])
    assert len(test_positions) == len(sample_test_data)
    assert test_positions.min() >= 0.0
    assert test_positions.max() <= 1.0


def test_dead_zone_softsign_map(sample_train_data, sample_test_data):
    """Test dead-zone softsign position map."""
    config = PositionMapConfig(
        variant="dead_zone_softsign",
        p_max=1.0,
        threshold=0.25,
        scale=1.0,
    )

    # Fit (no-op for this variant)
    fitted = fit_position_map(
        config,
        train_score=sample_train_data["score"],
        train_returns=None,
        train_future_return=None,
    )

    # Transform
    test_positions = fitted.transform(sample_test_data["score"])
    assert len(test_positions) == len(sample_test_data)
    assert test_positions.min() >= 0.0
    assert test_positions.max() <= 1.0

    # Check dead zone: negative scores should give 0 position
    negative_score = pd.Series([-1.0, -0.5, 0.0])
    negative_pos = fitted.transform(negative_score)
    assert (negative_pos <= 0.01).all()


def test_vol_target_map(sample_train_data, sample_test_data):
    """Test volatility-targeted position map."""
    config = PositionMapConfig(
        variant="vol_target",
        p_max=1.0,
        target_vol=0.15,
        vol_window=20,
    )

    # Fit
    fitted = fit_position_map(
        config,
        train_score=sample_train_data["score"],
        train_returns=sample_train_data["returns"],
        train_future_return=None,
    )

    assert fitted.train_vol_median is not None
    assert fitted.train_vol_median > 0.0

    # Transform
    test_positions = fitted.transform(
        sample_test_data["score"], sample_test_data["returns"]
    )
    assert len(test_positions) == len(sample_test_data)
    assert test_positions.min() >= 0.0
    # Vol target can exceed p_max before clipping, but result should be clipped
    assert test_positions.max() <= 1.0


def test_monotone_calibrated_map(sample_train_data, sample_test_data):
    """Test monotone calibrated position map."""
    config = PositionMapConfig(
        variant="monotone_calibrated",
        p_max=1.0,
        increasing=True,
        calibration_clip=(-0.5, 0.5),
    )

    # Fit
    fitted = fit_position_map(
        config,
        train_score=sample_train_data["score"],
        train_returns=None,
        train_future_return=sample_train_data["future_return"],
    )

    assert fitted.x_knots is not None
    assert fitted.y_knots is not None
    assert len(fitted.x_knots) == len(fitted.y_knots)

    # Transform
    test_positions = fitted.transform(sample_test_data["score"])
    assert len(test_positions) == len(sample_test_data)
    assert test_positions.min() >= 0.0
    assert test_positions.max() <= 1.0


def test_execution_constraints_no_trade_band():
    """Test no-trade band constraint."""
    constraints = ExecutionConstraints(
        no_trade_band=0.05,
        max_daily_delta_increase=0.20,
        max_daily_delta_decrease=0.20,
        rebalance_cadence_days=1,
    )

    target = pd.Series([0.50, 0.53, 0.48, 0.60])
    prev = pd.Series([0.50, 0.50, 0.50, 0.50])
    days_since = pd.Series([1, 1, 1, 1])

    result = constraints.apply(target, prev, days_since)

    # First: no change (same as prev)
    assert result.iloc[0] == 0.50
    # Second: delta=0.03 < 0.05, no trade
    assert result.iloc[1] == 0.50
    # Third: delta=-0.02 < 0.05, no trade
    assert result.iloc[2] == 0.50
    # Fourth: delta=0.10 > 0.05, should trade
    assert result.iloc[3] > 0.50


def test_execution_constraints_delta_limits():
    """Test delta limit constraints."""
    constraints = ExecutionConstraints(
        no_trade_band=0.02,
        max_daily_delta_increase=0.10,
        max_daily_delta_decrease=0.10,
        rebalance_cadence_days=1,
    )

    # Large positive delta should be capped
    target = pd.Series([0.80])
    prev = pd.Series([0.50])
    days_since = pd.Series([1])

    result = constraints.apply(target, prev, days_since)
    # Delta would be 0.30, but capped at 0.10
    assert result.iloc[0] <= 0.60


def test_execution_constraints_rebalance_cadence():
    """Test rebalance cadence constraint."""
    constraints = ExecutionConstraints(
        no_trade_band=0.02,
        max_daily_delta_increase=0.20,
        max_daily_delta_decrease=0.20,
        rebalance_cadence_days=3,
    )

    target = pd.Series([0.80, 0.80, 0.80])
    prev = pd.Series([0.50, 0.50, 0.50])
    days_since = pd.Series([1, 2, 3])

    result = constraints.apply(target, prev, days_since)

    # First two: days < cadence, no rebalance
    assert result.iloc[0] == 0.50
    assert result.iloc[1] == 0.50
    # Third: days >= cadence, should rebalance
    assert result.iloc[2] > 0.50


def test_compute_diagnostics_basic():
    """Test basic diagnostics computation."""
    n = 100
    score = pd.Series(np.random.randn(n))
    target_pos = pd.Series(np.random.uniform(0, 1, n))
    exec_pos = target_pos.copy()
    returns = pd.Series(np.random.randn(n) * 0.01)

    diag = compute_diagnostics(
        variant="test_variant",
        execution_label="test_exec",
        cost_multiplier=1.0,
        score=score,
        target_position=target_pos,
        exec_position=exec_pos,
        returns=returns,
    )

    assert diag.variant == "test_variant"
    assert diag.execution_label == "test_exec"
    assert diag.cost_multiplier == 1.0
    assert diag.score_min <= diag.score_median <= diag.score_max
    assert 0.0 <= diag.near_zero_rate <= 1.0
    assert 0.0 <= diag.near_max_rate <= 1.0
    assert diag.mean_exposure >= 0.0
    assert diag.total_turnover >= 0.0


def test_compute_diagnostics_zero_turnover():
    """Test diagnostics with zero turnover (constant position)."""
    n = 100
    score = pd.Series(np.random.randn(n))
    exec_pos = pd.Series([0.5] * n)
    returns = pd.Series(np.random.randn(n) * 0.01)

    diag = compute_diagnostics(
        variant="constant",
        execution_label="no_change",
        cost_multiplier=1.0,
        score=score,
        target_position=exec_pos,
        exec_position=exec_pos,
        returns=returns,
    )

    # Zero turnover should mean zero transaction cost
    assert diag.total_turnover < 1e-6
    assert diag.transaction_cost < 1e-6
    assert diag.cost_to_gross_ratio < 1e-6


def test_position_map_config_validation():
    """Test position map config validation."""
    # Invalid p_max
    with pytest.raises(ValueError, match="p_max"):
        PositionMapConfig(variant="quantile_5bin", p_max=1.5)

    # Invalid threshold
    with pytest.raises(ValueError, match="threshold"):
        PositionMapConfig(variant="dead_zone_softsign", threshold=-0.1)

    # Mismatched quantile lengths
    with pytest.raises(ValueError, match="matching breakpoints"):
        PositionMapConfig(
            variant="quantile_5bin", quantiles=(0.0, 0.5, 1.0), positions=(0.0, 1.0)
        )


def test_map_monotonicity(sample_train_data):
    """Test that position maps are monotonic in score."""
    config = PositionMapConfig(variant="dead_zone_softsign", p_max=1.0)
    fitted = fit_position_map(config, sample_train_data["score"])

    # Generate sorted scores
    sorted_scores = pd.Series(np.linspace(-3, 3, 50))
    positions = fitted.transform(sorted_scores)

    # Check monotonicity: positions should be non-decreasing
    diffs = positions.diff().dropna()
    assert (diffs >= -1e-6).all(), "Position map is not monotonic"


def test_saturation_detection():
    """Test detection of saturated positions."""
    # Create a score that leads to saturation
    saturated_score = pd.Series([10.0] * 50 + [-10.0] * 50)
    config = PositionMapConfig(variant="dead_zone_softsign", p_max=1.0, scale=0.1)
    fitted = fit_position_map(config, saturated_score)

    positions = fitted.transform(saturated_score)

    near_max_rate = (positions >= 0.99).mean()
    near_zero_rate = (positions <= 0.01).mean()

    # With extreme scores and small scale, should saturate
    assert near_max_rate > 0.4 or near_zero_rate > 0.4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
