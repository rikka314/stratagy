"""Tests for CN_A market-native factors."""

import numpy as np
import pandas as pd
import pytest

from core.cn_a_market_factors import (
    build_cn_a_market_context,
    compute_benchmark_returns,
    compute_cn_a_market_factors,
    compute_cn_a_tradability_status,
    compute_market_beta,
    compute_market_breadth,
    compute_market_volatility_level,
    compute_relative_strength,
)
from core.market_factor_context import MarketFactorContext


@pytest.fixture
def sample_benchmark():
    """Create sample benchmark data."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    closes = 3000 + np.cumsum(np.random.randn(100) * 10)
    return pd.DataFrame({"date": dates, "close": closes})


@pytest.fixture
def sample_stock():
    """Create sample stock data."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    closes = 50 + np.cumsum(np.random.randn(100) * 2)
    opens = closes + np.random.randn(100) * 0.5
    highs = closes + np.abs(np.random.randn(100) * 1.5)
    lows = closes - np.abs(np.random.randn(100) * 1.5)
    volumes = 1000000 + np.random.randint(-100000, 100000, 100)
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


@pytest.fixture
def sample_universe():
    """Create sample universe data for 5 stocks."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    symbols = ["000001", "000002", "000003", "000004", "000005"]
    data = []
    for symbol in symbols:
        closes = 50 + np.cumsum(np.random.randn(100) * 0.5)  # Smaller volatility to keep positive
        closes = np.maximum(closes, 10.0)  # Ensure all prices stay above 10
        for date, close in zip(dates, closes):
            data.append({"date": date, "symbol": symbol, "close": close})
    return pd.DataFrame(data)


def test_compute_benchmark_returns(sample_benchmark):
    """Test benchmark returns computation."""
    result = compute_benchmark_returns(sample_benchmark)

    assert "date" in result.columns
    assert "close" in result.columns
    assert "return_1" in result.columns
    assert "return_5" in result.columns
    assert "return_20" in result.columns
    assert "volatility_20" in result.columns
    assert "drawdown_60" in result.columns
    assert "trend_20" in result.columns

    # Check that returns are computed correctly
    assert result["return_1"].isna().sum() == 1  # First row should be NaN
    assert result["return_5"].isna().sum() == 5  # First 5 rows should be NaN
    assert result["return_20"].isna().sum() >= 20  # First 20+ rows should be NaN


def test_compute_market_volatility_level(sample_benchmark):
    """Test market volatility level and regime computation."""
    result = compute_market_volatility_level(sample_benchmark)

    assert "date" in result.columns
    assert "market_vol_level" in result.columns
    assert "market_vol_regime" in result.columns

    # Check regime values
    regimes = result["market_vol_regime"].dropna().unique()
    assert all(r in ["low", "medium", "high"] for r in regimes)


def test_compute_relative_strength(sample_stock, sample_benchmark):
    """Test relative strength computation."""
    result = compute_relative_strength(sample_stock, sample_benchmark, lookback=20)

    assert "date" in result.columns
    assert "rel_strength_market_20" in result.columns

    # Check that first 20 rows are NaN
    assert result["rel_strength_market_20"].isna().sum() >= 20


def test_compute_market_beta(sample_stock, sample_benchmark):
    """Test market beta computation."""
    result = compute_market_beta(sample_stock, sample_benchmark, lookback=20)

    assert "date" in result.columns
    assert "market_beta_20d" in result.columns

    # Check that first 19-20 rows are NaN (lookback-1 due to pct_change)
    assert result["market_beta_20d"].isna().sum() >= 19


def test_compute_market_breadth():
    """Test market breadth computation."""
    # Test with valid breadth frame
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    breadth_frame = pd.DataFrame({
        "date": dates,
        "breadth_up_ratio_1": np.random.rand(50),
        "market_constituent_count": np.full(50, 60.0),
    })

    result = compute_market_breadth(breadth_frame)

    assert result is not None
    assert "date" in result.columns
    assert "breadth_up_ratio_1" in result.columns
    assert "breadth_up_ratio_20" in result.columns
    assert "market_breadth" in result.columns
    assert "market_constituent_count" in result.columns

    # Test with None
    result = compute_market_breadth(None)
    assert result is None


def test_compute_cn_a_tradability_status(sample_stock):
    """Test CN_A tradability status computation."""
    result = compute_cn_a_tradability_status(sample_stock)

    assert "date" in result.columns
    assert "is_suspended" in result.columns
    assert "is_limit_up" in result.columns
    assert "is_limit_down" in result.columns
    assert "has_valid_close" in result.columns
    assert "tradability_status" in result.columns

    # Check status values
    statuses = result["tradability_status"].unique()
    assert all(s in ["normal", "suspended", "limit_up", "limit_down"] for s in statuses)


def test_compute_cn_a_tradability_suspended():
    """Test suspended stock detection."""
    dates = pd.date_range("2023-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "open": [10] * 5 + [0] * 5,  # Suspended in last 5 days
        "high": [11] * 5 + [0] * 5,
        "low": [9] * 5 + [0] * 5,
        "close": [10] * 5 + [0] * 5,
        "volume": [1000000] * 5 + [0] * 5,
    })

    result = compute_cn_a_tradability_status(df)

    # Last 5 days should be marked as suspended
    assert result.iloc[-1]["is_suspended"]
    assert result.iloc[-1]["tradability_status"] == "suspended"


def test_compute_cn_a_tradability_limit_up():
    """Test limit up detection."""
    dates = pd.date_range("2023-01-01", periods=10, freq="D")
    closes = [100] * 10
    closes[5] = 110  # +10% limit up

    df = pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": [1000000] * 10,
    })

    result = compute_cn_a_tradability_status(df)

    # Day 6 should be marked as limit up
    assert result.iloc[5]["is_limit_up"]


def test_build_cn_a_market_context_with_benchmark(sample_benchmark):
    """Test building CN_A context with explicit benchmark."""
    context = build_cn_a_market_context(benchmark_frame=sample_benchmark)

    assert context.market == "CN_A"
    assert context.benchmark_symbol == "provided"
    assert len(context.benchmark_frame) == len(sample_benchmark)
    assert context.factor_availability["benchmark"] == "provided"


def test_build_cn_a_market_context_with_universe(sample_universe):
    """Test building CN_A context with universe (equal-weight benchmark)."""
    context = build_cn_a_market_context(universe_frame=sample_universe)

    assert context.market == "CN_A"
    assert context.benchmark_symbol == "frozen_universe_equal_weight"
    assert context.factor_availability["benchmark"] == "frozen_universe_equal_weight_close_return"
    assert context.factor_availability["breadth"] == "frozen_universe"
    assert context.breadth_frame is not None


def test_build_cn_a_market_context_no_input():
    """Test that CN_A context fails without benchmark or universe."""
    with pytest.raises(ValueError, match="CN_A requires"):
        build_cn_a_market_context()


def test_compute_cn_a_market_factors(sample_stock, sample_benchmark):
    """Test full CN_A market factors computation."""
    context = build_cn_a_market_context(benchmark_frame=sample_benchmark)
    result = compute_cn_a_market_factors(sample_stock, context)

    # Check required columns
    assert "date" in result.columns
    assert "market_return_1" in result.columns
    assert "market_return_5" in result.columns
    assert "market_return_20" in result.columns
    assert "market_vol_level" in result.columns
    assert "market_vol_regime" in result.columns
    assert "rel_strength_market" in result.columns
    assert "market_beta_20d" in result.columns
    assert "market_drawdown_60" in result.columns
    assert "sector_momentum" in result.columns
    assert "tradability_status" in result.columns

    # Breadth should be NaN since we didn't provide universe
    assert result["market_breadth"].isna().all()

    # Sector should be NaN (unavailable)
    assert result["sector_momentum"].isna().all()


def test_compute_cn_a_market_factors_with_universe(sample_stock, sample_universe):
    """Test CN_A market factors with universe breadth."""
    context = build_cn_a_market_context(universe_frame=sample_universe)
    result = compute_cn_a_market_factors(sample_stock, context)

    # Breadth should be available
    assert "market_breadth" in result.columns
    assert "market_constituent_count" in result.columns
    assert "breadth_up_ratio_1" in result.columns
    assert "breadth_up_ratio_20" in result.columns

    # Should have non-NaN values for most dates
    assert result["market_breadth"].notna().sum() > 0


def test_compute_cn_a_market_factors_wrong_market(sample_stock, sample_benchmark):
    """Test that compute_cn_a_market_factors fails with non-CN_A context."""
    # Create a US context
    context = MarketFactorContext(
        market="US",
        benchmark_symbol="SPY",
        benchmark_frame=sample_benchmark,
    )

    with pytest.raises(ValueError, match="Expected CN_A context"):
        compute_cn_a_market_factors(sample_stock, context)


def test_cn_a_no_spy_vix_leakage(sample_benchmark, tmp_path):
    """Test that CN_A context never loads SPY or VIX artifacts."""
    # Create fake SPY/VIX files
    macro_dir = tmp_path / "macro"
    macro_dir.mkdir()
    sample_benchmark.to_parquet(macro_dir / "spy_daily.parquet")
    sample_benchmark.to_parquet(macro_dir / "vix_daily.parquet")

    # Build CN_A context with universe - should NOT load SPY/VIX
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    universe = pd.DataFrame({
        "date": dates.repeat(5),
        "symbol": ["000001", "000002", "000003", "000004", "000005"] * 50,
        "close": 50 + np.random.randn(250) * 2,
    })

    context = build_cn_a_market_context(
        universe_frame=universe,
        data_dir=macro_dir,
    )

    # Should use equal-weight benchmark, not SPY
    assert context.benchmark_symbol == "frozen_universe_equal_weight"
    assert context.factor_availability["benchmark"] != "observed"
    assert context.factor_availability["volatility"] == "benchmark_realized_volatility"


def test_cn_a_factor_names_no_us_aliases(sample_stock, sample_benchmark):
    """Test that CN_A factors use market_* names, not vix_* or rel_strength_spy."""
    context = build_cn_a_market_context(benchmark_frame=sample_benchmark)
    result = compute_cn_a_market_factors(sample_stock, context)

    # Should NOT have US-specific aliases
    assert "vix_level" not in result.columns
    assert "vix_regime" not in result.columns
    assert "rel_strength_spy" not in result.columns

    # Should have CN_A-appropriate names
    assert "market_vol_level" in result.columns
    assert "market_vol_regime" in result.columns
    assert "rel_strength_market" in result.columns


def test_benchmark_returns_no_forward_looking(sample_benchmark):
    """Test that benchmark returns don't use future data."""
    result = compute_benchmark_returns(sample_benchmark)

    # Check that return_20 at row i only uses data up to row i
    for i in range(20, len(result)):
        expected = (result.iloc[i]["close"] / result.iloc[i - 20]["close"]) - 1
        actual = result.iloc[i]["return_20"]
        if pd.notna(actual):
            assert abs(actual - expected) < 1e-6


def test_market_beta_valid_range(sample_stock, sample_benchmark):
    """Test that market beta is in a reasonable range."""
    result = compute_market_beta(sample_stock, sample_benchmark, lookback=20)

    valid_betas = result["market_beta_20d"].dropna()
    # Beta should typically be between -3 and 3 for most stocks
    assert (valid_betas.abs() < 10).all(), "Beta values are unreasonably large"


def test_relative_strength_symmetry(sample_benchmark):
    """Test that relative strength is zero when stock equals benchmark."""
    # Use benchmark as stock
    result = compute_relative_strength(sample_benchmark, sample_benchmark, lookback=20)

    # Relative strength should be approximately zero
    valid_rs = result["rel_strength_market_20"].dropna()
    assert (valid_rs.abs() < 1e-10).all()


def test_breadth_ratio_range():
    """Test that breadth ratios are in valid [0, 1] range."""
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    breadth_frame = pd.DataFrame({
        "date": dates,
        "breadth_up_ratio_1": np.random.rand(50),
        "market_constituent_count": np.full(50, 60.0),
    })

    result = compute_market_breadth(breadth_frame)

    assert (result["breadth_up_ratio_1"] >= 0).all()
    assert (result["breadth_up_ratio_1"] <= 1).all()


def test_tradability_mutually_exclusive(sample_stock):
    """Test that tradability states are mutually exclusive."""
    result = compute_cn_a_tradability_status(sample_stock)

    # A row should not be both limit_up and limit_down
    both = result["is_limit_up"] & result["is_limit_down"]
    assert not both.any()


def test_volatility_regime_distribution(sample_benchmark):
    """Test that volatility regime classification is balanced over time."""
    # Create a longer benchmark for better distribution
    dates = pd.date_range("2023-01-01", periods=300, freq="D")
    closes = 3000 + np.cumsum(np.random.randn(300) * 10)
    long_benchmark = pd.DataFrame({"date": dates, "close": closes})

    result = compute_market_volatility_level(long_benchmark)

    regimes = result["market_vol_regime"].dropna()
    if len(regimes) > 100:  # Only check if we have enough data
        # Each regime should appear at least once
        assert "low" in regimes.values
        assert "medium" in regimes.values
        assert "high" in regimes.values
