"""Tests for Phase 4 cross-fold admission module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_test.cross_fold_admission import (
    FoldMetrics,
    AdmissionGate,
    StrategyCandidate,
    compute_returns_and_equity,
    compute_drawdown_stats,
    compute_sharpe_sortino,
    compute_beta,
    compute_rank_ic,
    check_fold_quality,
    evaluate_fold,
    check_admission,
    aggregate_candidate_metrics,
)


@pytest.fixture
def sample_returns():
    """Sample returns for testing."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=252, freq="D")
    returns = pd.Series(
        np.random.normal(0.001, 0.02, 252),
        index=dates,
        name="return",
    )
    return returns


@pytest.fixture
def sample_positions():
    """Sample positions for testing."""
    dates = pd.date_range("2020-01-01", periods=252, freq="D")
    # Varying position: 0.5 -> 0.8 -> 0.5
    pos = np.concatenate([
        np.linspace(0.5, 0.8, 126),
        np.linspace(0.8, 0.5, 126),
    ])
    return pd.Series(pos, index=dates, name="position")


def test_compute_returns_and_equity_zero_position(sample_returns):
    """Test that zero position yields zero returns and costs."""
    positions = pd.Series(0.0, index=sample_returns.index)

    gross_rets, costs, net_rets, total_cost = compute_returns_and_equity(
        positions, sample_returns, commission=0.001, slippage=0.0005
    )

    assert gross_rets.sum() == 0.0
    assert total_cost == 0.0
    assert net_rets.sum() == 0.0


def test_compute_returns_and_equity_constant_position(sample_returns):
    """Test that constant position has zero turnover after initial."""
    positions = pd.Series(1.0, index=sample_returns.index)

    gross_rets, costs, net_rets, total_cost = compute_returns_and_equity(
        positions, sample_returns, commission=0.001, slippage=0.0005
    )

    # Gross returns should equal benchmark (shifted by 1)
    expected_gross = sample_returns.values
    expected_gross[0] = 0.0  # First day is 0
    assert np.allclose(gross_rets, expected_gross)

    # Total cost should only be initial position entry
    assert total_cost == pytest.approx(0.0015, abs=0.0001)  # 1.0 * (0.001 + 0.0005)


def test_compute_returns_and_equity_varying_position(sample_positions, sample_returns):
    """Test returns and costs with varying positions."""
    gross_rets, costs, net_rets, total_cost = compute_returns_and_equity(
        sample_positions, sample_returns, commission=0.001, slippage=0.0005
    )

    # Gross returns should be position-weighted
    assert len(gross_rets) == len(sample_returns)

    # Costs should be positive (turnover exists)
    assert total_cost > 0

    # Net returns = gross - costs
    assert np.allclose(net_rets, gross_rets - costs)


def test_compute_drawdown_stats_no_drawdown():
    """Test drawdown stats with monotonically increasing equity."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    equity = pd.Series(np.linspace(1.0, 2.0, 100), index=dates)

    max_dd, max_dd_duration, recovery_time = compute_drawdown_stats(equity)

    assert max_dd == 0.0
    assert max_dd_duration == 0
    # Recovery time is None or 0 when no real drawdown


def test_compute_drawdown_stats_simple_drawdown():
    """Test drawdown stats with one drawdown and recovery."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    # Peak at 50, trough at 75, recover at 90
    equity_values = np.concatenate([
        np.linspace(1.0, 2.0, 50),   # Rise to peak
        np.linspace(2.0, 1.5, 25),   # Drawdown 25%
        np.linspace(1.5, 2.0, 25),   # Recovery
    ])
    equity = pd.Series(equity_values, index=dates)

    max_dd, max_dd_duration, recovery_time = compute_drawdown_stats(equity)

    assert max_dd == pytest.approx(0.25, abs=0.01)
    assert max_dd_duration >= 0  # Duration from peak to trough
    assert recovery_time is not None  # Should recover


def test_compute_sharpe_sortino(sample_returns):
    """Test Sharpe and Sortino calculation."""
    sharpe, sortino, volatility = compute_sharpe_sortino(sample_returns, annualize_factor=252.0)

    # Basic sanity checks
    assert isinstance(sharpe, float)
    assert isinstance(sortino, float)
    assert isinstance(volatility, float)
    assert volatility > 0

    # Sortino should be >= Sharpe (uses downside deviation only)
    # In general, this may not always hold, but for symmetric returns it often does


def test_compute_sharpe_sortino_all_positive_returns():
    """Test Sharpe/Sortino with all positive returns."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    returns = pd.Series(np.abs(np.random.normal(0.01, 0.01, 100)), index=dates)

    sharpe, sortino, volatility = compute_sharpe_sortino(returns)

    assert sharpe > 0
    assert sortino > 0
    assert volatility > 0


def test_compute_beta_perfect_correlation(sample_returns):
    """Test beta when strategy = benchmark."""
    beta, upside_beta, downside_beta = compute_beta(sample_returns, sample_returns)

    assert beta == pytest.approx(1.0, abs=0.01)


def test_compute_beta_zero_correlation():
    """Test beta with uncorrelated returns."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=252, freq="D")
    strategy_returns = pd.Series(np.random.normal(0.001, 0.02, 252), index=dates)

    np.random.seed(100)
    benchmark_returns = pd.Series(np.random.normal(0.001, 0.02, 252), index=dates)

    beta, upside_beta, downside_beta = compute_beta(strategy_returns, benchmark_returns)

    # Beta should be close to 0 for uncorrelated returns
    assert beta is not None
    assert abs(beta) < 0.5  # Loose check due to randomness


def test_compute_rank_ic():
    """Test rank IC computation."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    scores = pd.Series(np.random.randn(100), index=dates)
    future_returns = scores * 0.01 + np.random.randn(100) * 0.005  # Correlated

    rank_ic, _ = compute_rank_ic(scores, future_returns)

    assert isinstance(rank_ic, float)
    assert -1.0 <= rank_ic <= 1.0
    # Should have positive IC due to construction
    assert rank_ic > 0


def test_check_fold_quality_clean_data():
    """Test quality check with clean data."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "return": np.random.normal(0.001, 0.02, 100),
    }, index=dates)

    has_dq, has_pit, has_audit, notes = check_fold_quality(df)

    assert not has_dq
    assert not has_pit
    assert not has_audit
    assert notes == ""


def test_check_fold_quality_duplicate_dates():
    """Test quality check detects duplicate dates."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    # Duplicate the first date
    dates = dates.insert(0, dates[0])
    df = pd.DataFrame({
        "return": np.random.normal(0.001, 0.02, 101),
    }, index=dates)

    has_dq, has_pit, has_audit, notes = check_fold_quality(df)

    assert has_dq
    assert "duplicate_dates" in notes


def test_check_fold_quality_extreme_returns():
    """Test quality check detects extreme returns."""
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    returns = np.random.normal(0.001, 0.02, 100)
    returns[50] = 0.80  # Extreme outlier
    df = pd.DataFrame({"return": returns}, index=dates)

    has_dq, has_pit, has_audit, notes = check_fold_quality(df)

    assert has_dq
    assert "extreme_returns" in notes


def test_evaluate_fold_basic(sample_positions, sample_returns):
    """Test basic fold evaluation."""
    df = pd.DataFrame({
        "return": sample_returns,
    })

    metrics = evaluate_fold(
        fold_id="test_fold",
        df=df,
        positions=sample_positions,
        returns=sample_returns,
        commission=0.001,
        slippage=0.0005,
    )

    assert metrics.fold_id == "test_fold"
    assert metrics.trading_days == len(df)
    assert isinstance(metrics.sharpe_ratio, float)
    assert isinstance(metrics.max_drawdown, float)
    assert metrics.total_turnover > 0  # Positions vary


def test_check_admission_pass():
    """Test admission check with passing candidate."""
    candidate = StrategyCandidate(
        variant="composite_only",
        description="Test strategy",
        fold_metrics=[
            FoldMetrics(
                fold_id="fold_01",
                start_date="2020-01-01",
                end_date="2020-12-31",
                trading_days=252,
                total_return=0.15,
                net_return=0.15,
                gross_return=0.16,
                sharpe_ratio=0.8,
                sortino_ratio=1.0,
                annualized_volatility=0.20,
                max_drawdown=0.15,
                max_drawdown_duration_days=20,
                recovery_time_days=30,
                daily_win_rate=0.55,
                monthly_win_rate=0.60,
                mean_exposure=0.60,
                median_exposure=0.65,
                max_exposure=0.90,
                near_zero_rate=0.05,
                near_max_rate=0.05,
                total_turnover=5.0,
                daily_avg_turnover=0.02,
                trade_count=100,
                rebalance_count=100,
                transaction_cost=0.005,
                cost_to_gross_ratio=0.03,
            ),
            FoldMetrics(
                fold_id="fold_02",
                start_date="2021-01-01",
                end_date="2021-12-31",
                trading_days=252,
                total_return=0.12,
                net_return=0.12,
                gross_return=0.13,
                sharpe_ratio=0.7,
                sortino_ratio=0.9,
                annualized_volatility=0.22,
                max_drawdown=0.18,
                max_drawdown_duration_days=25,
                recovery_time_days=35,
                daily_win_rate=0.53,
                monthly_win_rate=0.58,
                mean_exposure=0.58,
                median_exposure=0.62,
                max_exposure=0.88,
                near_zero_rate=0.06,
                near_max_rate=0.06,
                total_turnover=5.5,
                daily_avg_turnover=0.022,
                trade_count=110,
                rebalance_count=110,
                transaction_cost=0.0055,
                cost_to_gross_ratio=0.04,
            ),
            FoldMetrics(
                fold_id="fold_03",
                start_date="2022-01-01",
                end_date="2022-12-31",
                trading_days=252,
                total_return=0.10,
                net_return=0.10,
                gross_return=0.11,
                sharpe_ratio=0.6,
                sortino_ratio=0.8,
                annualized_volatility=0.24,
                max_drawdown=0.20,
                max_drawdown_duration_days=30,
                recovery_time_days=40,
                daily_win_rate=0.52,
                monthly_win_rate=0.56,
                mean_exposure=0.56,
                median_exposure=0.60,
                max_exposure=0.86,
                near_zero_rate=0.07,
                near_max_rate=0.07,
                total_turnover=6.0,
                daily_avg_turnover=0.024,
                trade_count=120,
                rebalance_count=120,
                transaction_cost=0.006,
                cost_to_gross_ratio=0.05,
            ),
            FoldMetrics(
                fold_id="fold_04",
                start_date="2023-01-01",
                end_date="2023-12-31",
                trading_days=252,
                total_return=0.08,
                net_return=0.08,
                gross_return=0.09,
                sharpe_ratio=0.5,
                sortino_ratio=0.7,
                annualized_volatility=0.26,
                max_drawdown=0.22,
                max_drawdown_duration_days=35,
                recovery_time_days=45,
                daily_win_rate=0.51,
                monthly_win_rate=0.54,
                mean_exposure=0.54,
                median_exposure=0.58,
                max_exposure=0.84,
                near_zero_rate=0.08,
                near_max_rate=0.08,
                total_turnover=6.5,
                daily_avg_turnover=0.026,
                trade_count=130,
                rebalance_count=130,
                transaction_cost=0.0065,
                cost_to_gross_ratio=0.07,
            ),
        ],
    )

    gate = AdmissionGate(
        min_fold_pass_rate=0.75,
        min_sharpe_ratio=0.3,
        min_sortino_ratio=0.4,
        max_drawdown_threshold=0.30,
    )

    status, reason = check_admission(candidate, gate)

    assert status == "pass"
    assert "0.75" in reason or "75" in reason  # Pass rate mentioned


def test_check_admission_fail_low_pass_rate():
    """Test admission fails with low fold pass rate."""
    candidate = StrategyCandidate(
        variant="composite_only",
        description="Test strategy",
        fold_metrics=[
            FoldMetrics(
                fold_id="fold_01",
                start_date="2020-01-01",
                end_date="2020-12-31",
                trading_days=252,
                total_return=0.05,
                net_return=0.05,
                gross_return=0.06,
                sharpe_ratio=0.2,  # Below threshold
                sortino_ratio=0.3,
                annualized_volatility=0.30,
                max_drawdown=0.25,
                max_drawdown_duration_days=40,
                recovery_time_days=50,
                daily_win_rate=0.50,
                monthly_win_rate=None,
                mean_exposure=0.50,
                median_exposure=0.52,
                max_exposure=0.80,
                near_zero_rate=0.10,
                near_max_rate=0.10,
                total_turnover=8.0,
                daily_avg_turnover=0.032,
                trade_count=150,
                rebalance_count=150,
                transaction_cost=0.008,
                cost_to_gross_ratio=0.13,
            ),
        ] * 4,  # 4 folds, all below threshold
    )

    gate = AdmissionGate(min_fold_pass_rate=0.75, min_sharpe_ratio=0.3)

    status, reason = check_admission(candidate, gate)

    assert status == "fail"


def test_check_admission_blocked_data_quality():
    """Test admission blocked by data quality issue."""
    candidate = StrategyCandidate(
        variant="composite_only",
        description="Test strategy",
        fold_metrics=[
            FoldMetrics(
                fold_id="fold_01",
                start_date="2020-01-01",
                end_date="2020-12-31",
                trading_days=252,
                total_return=0.15,
                net_return=0.15,
                gross_return=0.16,
                sharpe_ratio=0.8,
                sortino_ratio=1.0,
                annualized_volatility=0.20,
                max_drawdown=0.15,
                max_drawdown_duration_days=20,
                recovery_time_days=30,
                daily_win_rate=0.55,
                monthly_win_rate=None,
                mean_exposure=0.60,
                median_exposure=0.65,
                max_exposure=0.90,
                near_zero_rate=0.05,
                near_max_rate=0.05,
                total_turnover=5.0,
                daily_avg_turnover=0.02,
                trade_count=100,
                rebalance_count=100,
                transaction_cost=0.005,
                cost_to_gross_ratio=0.03,
                has_data_quality_issue=True,  # Quality issue
            ),
        ],
    )

    gate = AdmissionGate(allow_data_quality_issues=False)

    status, reason = check_admission(candidate, gate)

    assert status == "blocked"
    assert "data_quality_issue" in reason


def test_aggregate_candidate_metrics():
    """Test aggregation of fold metrics."""
    candidate = StrategyCandidate(
        variant="composite_only",
        description="Test strategy",
        fold_metrics=[
            FoldMetrics(
                fold_id=f"fold_{i:02d}",
                start_date="2020-01-01",
                end_date="2020-12-31",
                trading_days=252,
                total_return=0.10,
                net_return=0.10,
                gross_return=0.11,
                sharpe_ratio=0.5 + i * 0.1,
                sortino_ratio=0.7,
                annualized_volatility=0.25,
                max_drawdown=0.20,
                max_drawdown_duration_days=30,
                recovery_time_days=40,
                daily_win_rate=0.52,
                monthly_win_rate=None,
                mean_exposure=0.55,
                median_exposure=0.58,
                max_exposure=0.85,
                near_zero_rate=0.08,
                near_max_rate=0.08,
                total_turnover=6.0,
                daily_avg_turnover=0.024,
                trade_count=120,
                rebalance_count=120,
                transaction_cost=0.006,
                cost_to_gross_ratio=0.05,
            )
            for i in range(4)
        ],
    )

    aggregate_candidate_metrics(candidate)

    assert candidate.total_folds == 4
    assert candidate.mean_sharpe == pytest.approx(0.65, abs=0.01)  # (0.5+0.6+0.7+0.8)/4
    assert candidate.median_sharpe == pytest.approx(0.65, abs=0.01)
    assert candidate.worst_sharpe == pytest.approx(0.5, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
