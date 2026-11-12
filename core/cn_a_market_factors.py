"""CN_A market-native factors: benchmark, volatility, breadth, relative strength.

This module computes CN_A market context factors using only CN_A-appropriate
sources. It never reads SPY or VIX artifacts, and produces market_* named
outputs that are semantically correct for A-shares.

All computation is point-in-time: only data available at or before the
decision date is used.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from core.market_factor_context import MarketFactorContext


def compute_benchmark_returns(benchmark_frame: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling returns and volatility from benchmark close prices.

    Args:
        benchmark_frame: DataFrame with date and close columns

    Returns:
        DataFrame with date, close, return_1, return_5, return_20,
        volatility_20, drawdown_60, trend_20
    """
    result = benchmark_frame.loc[:, ["date", "close"]].copy()
    result = result.sort_values("date").reset_index(drop=True)

    # Returns
    result["return_1"] = result["close"].pct_change(fill_method=None)
    result["return_5"] = result["close"].pct_change(5, fill_method=None)
    result["return_20"] = result["close"].pct_change(20, fill_method=None)

    # Realized volatility (20-day rolling std of daily returns)
    result["volatility_20"] = result["return_1"].rolling(20, min_periods=20).std()

    # Drawdown from 60-day high
    rolling_max = result["close"].rolling(60, min_periods=1).max()
    result["drawdown_60"] = (result["close"] - rolling_max) / rolling_max

    # Trend: 20-day simple moving average slope
    result["trend_20"] = result["close"].rolling(20, min_periods=20).mean()

    return result


def compute_market_volatility_level(benchmark_frame: pd.DataFrame) -> pd.DataFrame:
    """Compute realized volatility level and regime classification.

    CN_A does not use VIX. Instead, we use benchmark realized volatility
    and classify it into regimes using rolling percentiles.

    Args:
        benchmark_frame: DataFrame with date and close columns

    Returns:
        DataFrame with date, market_vol_level, market_vol_regime
    """
    bench = compute_benchmark_returns(benchmark_frame)
    result = bench.loc[:, ["date"]].copy()

    # Market volatility level = 20-day realized volatility
    result["market_vol_level"] = bench["volatility_20"]

    # Regime classification using 252-day rolling percentile
    # Low: <33rd percentile, Medium: 33-66, High: >66
    rolling_pct = bench["volatility_20"].rolling(252, min_periods=60).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else np.nan,
        raw=False
    )

    result["market_vol_regime"] = "medium"
    result.loc[rolling_pct < 0.33, "market_vol_regime"] = "low"
    result.loc[rolling_pct > 0.66, "market_vol_regime"] = "high"
    result.loc[result["market_vol_level"].isna(), "market_vol_regime"] = np.nan

    return result


def compute_relative_strength(
    stock_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    """Compute relative strength vs market benchmark.

    Args:
        stock_frame: DataFrame with date and close columns for a single stock
        benchmark_frame: DataFrame with date and close columns for benchmark
        lookback: Number of days for relative strength calculation

    Returns:
        DataFrame with date and rel_strength_market_{lookback} columns
    """
    stock = stock_frame.loc[:, ["date", "close"]].copy()
    stock = stock.sort_values("date").reset_index(drop=True)
    stock["stock_return"] = stock["close"].pct_change(lookback, fill_method=None)

    bench = benchmark_frame.loc[:, ["date", "close"]].copy()
    bench = bench.sort_values("date").reset_index(drop=True)
    bench["bench_return"] = bench["close"].pct_change(lookback, fill_method=None)

    # Align on date (use only prior or same-date benchmark data)
    merged = pd.merge(stock, bench, on="date", how="left", suffixes=("", "_bench"))
    merged[f"rel_strength_market_{lookback}"] = merged["stock_return"] - merged["bench_return"]

    result = merged.loc[:, ["date", f"rel_strength_market_{lookback}"]].copy()
    return result


def compute_market_breadth(breadth_frame: pd.DataFrame | None) -> pd.DataFrame | None:
    """Extract market breadth indicators from breadth frame.

    Args:
        breadth_frame: Optional DataFrame from MarketFactorContext with
                      breadth_up_ratio_1, breadth_up_ratio_20, market_constituent_count

    Returns:
        DataFrame with date, breadth_up_ratio_1, breadth_up_ratio_20,
        market_breadth, market_constituent_count, or None if unavailable
    """
    if breadth_frame is None:
        return None

    required = {"date", "breadth_up_ratio_1", "market_constituent_count"}
    if not required.issubset(breadth_frame.columns):
        return None

    result = breadth_frame.loc[:, list(required)].copy()

    # Add 20-day rolling average if not present
    if "breadth_up_ratio_20" not in breadth_frame.columns:
        result["breadth_up_ratio_20"] = result["breadth_up_ratio_1"].rolling(20, min_periods=20).mean()
    else:
        result["breadth_up_ratio_20"] = breadth_frame["breadth_up_ratio_20"]

    # market_breadth is the primary breadth signal (1-day)
    result["market_breadth"] = result["breadth_up_ratio_1"]

    return result


def compute_market_beta(
    stock_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    """Compute rolling beta vs benchmark.

    Args:
        stock_frame: DataFrame with date and close columns for a single stock
        benchmark_frame: DataFrame with date and close columns for benchmark
        lookback: Number of days for beta calculation

    Returns:
        DataFrame with date and market_beta_{lookback}d columns
    """
    stock = stock_frame.loc[:, ["date", "close"]].copy()
    stock = stock.sort_values("date").reset_index(drop=True)
    stock["stock_return"] = stock["close"].pct_change(fill_method=None)

    bench = benchmark_frame.loc[:, ["date", "close"]].copy()
    bench = bench.sort_values("date").reset_index(drop=True)
    bench["bench_return"] = bench["close"].pct_change(fill_method=None)

    # Align on date
    merged = pd.merge(stock, bench, on="date", how="left", suffixes=("", "_bench"))

    # Compute rolling beta using window-based calculation
    betas = []
    for i in range(len(merged)):
        if i < lookback - 1:
            betas.append(np.nan)
            continue

        window = merged.iloc[i - lookback + 1 : i + 1]
        stock_ret = window["stock_return"].to_numpy()
        bench_ret = window["bench_return"].to_numpy()

        mask = np.isfinite(stock_ret) & np.isfinite(bench_ret)
        if mask.sum() < lookback // 2:
            betas.append(np.nan)
            continue

        stock_ret_clean = stock_ret[mask]
        bench_ret_clean = bench_ret[mask]

        cov = np.cov(stock_ret_clean, bench_ret_clean)[0, 1]
        var = np.var(bench_ret_clean, ddof=1)
        beta = cov / var if var > 1e-12 else np.nan
        betas.append(beta)

    merged[f"market_beta_{lookback}d"] = betas

    result = merged.loc[:, ["date", f"market_beta_{lookback}d"]].copy()
    return result


def compute_cn_a_tradability_status(stock_frame: pd.DataFrame) -> pd.DataFrame:
    """Compute A-share tradability flags.

    Args:
        stock_frame: DataFrame with date, open, high, low, close, volume columns

    Returns:
        DataFrame with date, is_suspended, is_limit_up, is_limit_down,
        has_valid_close, tradability_status columns
    """
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(stock_frame.columns)
    if missing:
        raise ValueError(f"stock_frame missing columns for tradability: {missing}")

    df = stock_frame.loc[:, list(required)].copy()
    df = df.sort_values("date").reset_index(drop=True)

    # Convert to numeric
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Has valid close
    df["has_valid_close"] = df["close"].notna() & (df["close"] > 0)

    # Suspended: all OHLC are zero or missing, or volume is zero
    df["is_suspended"] = (
        (~df["has_valid_close"]) |
        (df["open"].isna() | (df["open"] <= 0)) |
        (df["volume"].isna() | (df["volume"] <= 0))
    )

    # Limit up/down detection: approximately 10% (simplified)
    # In reality, different boards have different limits (10%, 20%, 30%)
    # This is a conservative approximation
    df["prev_close"] = df["close"].shift(1)
    df["daily_return"] = df["close"].pct_change(fill_method=None)

    df["is_limit_up"] = False
    df["is_limit_down"] = False

    # If price movement is close to +10%, likely limit up
    df.loc[df["daily_return"] >= 0.095, "is_limit_up"] = True
    # If price movement is close to -10%, likely limit down
    df.loc[df["daily_return"] <= -0.095, "is_limit_down"] = True

    # Tradability status
    df["tradability_status"] = "normal"
    df.loc[df["is_suspended"], "tradability_status"] = "suspended"
    df.loc[df["is_limit_up"], "tradability_status"] = "limit_up"
    df.loc[df["is_limit_down"], "tradability_status"] = "limit_down"

    result = df.loc[:, [
        "date", "is_suspended", "is_limit_up", "is_limit_down",
        "has_valid_close", "tradability_status"
    ]].copy()

    return result


def build_cn_a_market_context(
    universe_frame: pd.DataFrame | None = None,
    benchmark_frame: pd.DataFrame | None = None,
    data_dir: str | Path = "data/macro",
) -> MarketFactorContext:
    """Build CN_A MarketFactorContext with all available CN_A factors.

    Priority for benchmark:
    1. Explicit benchmark_frame (e.g., 000300 沪深300)
    2. Frozen universe equal-weight benchmark from universe_frame
    3. Fail if neither is provided

    Args:
        universe_frame: Optional DataFrame with date, symbol, close for CN_A universe
        benchmark_frame: Optional DataFrame with date, close for CN_A benchmark
        data_dir: Directory containing macro data artifacts

    Returns:
        MarketFactorContext for CN_A market

    Raises:
        ValueError: If neither benchmark_frame nor universe_frame is provided
    """
    from core.market_factor_context import build_market_factor_context

    # Delegate to the unified builder
    context = build_market_factor_context(
        market="CN_A",
        data_dir=data_dir,
        universe_frame=universe_frame,
        benchmark_frame=benchmark_frame,
    )

    return context


def compute_cn_a_market_factors(
    stock_frame: pd.DataFrame,
    context: MarketFactorContext,
) -> pd.DataFrame:
    """Compute all CN_A market-native factors for a single stock.

    Args:
        stock_frame: DataFrame with date and OHLCV columns for a single stock
        context: MarketFactorContext for CN_A market

    Returns:
        DataFrame with date and all market factor columns, aligned to stock dates
    """
    if context.market != "CN_A":
        raise ValueError(f"Expected CN_A context, got {context.market}")

    stock = stock_frame.loc[:, ["date"]].copy()
    stock = stock.sort_values("date").reset_index(drop=True)
    stock["date"] = pd.to_datetime(stock["date"])

    # 1. Benchmark returns and volatility
    bench_stats = compute_benchmark_returns(context.benchmark_frame)
    stock = pd.merge(stock, bench_stats, on="date", how="left", suffixes=("", "_bench"))
    stock.rename(columns={
        "return_1": "market_return_1",
        "return_5": "market_return_5",
        "return_20": "market_return_20",
        "volatility_20": "market_vol_level",
        "drawdown_60": "market_drawdown_60",
    }, inplace=True)

    # 2. Volatility regime
    vol_regime = compute_market_volatility_level(context.benchmark_frame)
    stock = pd.merge(stock, vol_regime[["date", "market_vol_regime"]], on="date", how="left")

    # 3. Relative strength
    rel_strength = compute_relative_strength(stock_frame, context.benchmark_frame, lookback=20)
    stock = pd.merge(stock, rel_strength, on="date", how="left")
    stock.rename(columns={"rel_strength_market_20": "rel_strength_market"}, inplace=True)

    # 4. Beta
    beta = compute_market_beta(stock_frame, context.benchmark_frame, lookback=20)
    stock = pd.merge(stock, beta, on="date", how="left")
    stock.rename(columns={"market_beta_20d": "market_beta_20d"}, inplace=True)

    # 5. Breadth (if available)
    if context.breadth_frame is not None:
        breadth = compute_market_breadth(context.breadth_frame)
        if breadth is not None:
            stock = pd.merge(stock, breadth, on="date", how="left")

    # If breadth is unavailable, fill with NaN and mark status
    if "market_breadth" not in stock.columns:
        stock["breadth_up_ratio_1"] = np.nan
        stock["breadth_up_ratio_20"] = np.nan
        stock["market_breadth"] = np.nan
        stock["market_constituent_count"] = np.nan

    # 6. Sector momentum (currently unavailable for CN_A)
    stock["sector_momentum"] = np.nan

    # 7. Tradability status
    if all(c in stock_frame.columns for c in ["open", "high", "low", "close", "volume"]):
        tradability = compute_cn_a_tradability_status(stock_frame)
        stock = pd.merge(stock, tradability, on="date", how="left")
    else:
        stock["is_suspended"] = False
        stock["is_limit_up"] = False
        stock["is_limit_down"] = False
        stock["has_valid_close"] = True
        stock["tradability_status"] = "normal"

    # Drop intermediate benchmark columns
    stock.drop(columns=["close", "trend_20"], errors="ignore", inplace=True)

    return stock


def export_cn_a_market_context_quality_report(
    context: MarketFactorContext,
    output_path: Path | str,
) -> dict:
    """Generate quality report for CN_A market context.

    Args:
        context: MarketFactorContext for CN_A
        output_path: Path to save the quality report JSON

    Returns:
        Dictionary with quality metrics
    """
    import json

    report = {
        "market": context.market,
        "benchmark_symbol": context.benchmark_symbol,
        "factor_availability": dict(context.factor_availability),
        "source_manifest_sha256": context.source_manifest_sha256,
        "benchmark_stats": {
            "date_count": len(context.benchmark_frame),
            "date_range": [
                context.benchmark_frame["date"].min().isoformat(),
                context.benchmark_frame["date"].max().isoformat(),
            ],
            "has_duplicates": context.benchmark_frame["date"].duplicated().any(),
            "has_missing_close": context.benchmark_frame["close"].isna().any(),
        },
    }

    if context.breadth_frame is not None:
        report["breadth_stats"] = {
            "date_count": len(context.breadth_frame),
            "date_range": [
                context.breadth_frame["date"].min().isoformat(),
                context.breadth_frame["date"].max().isoformat(),
            ],
            "avg_constituent_count": float(context.breadth_frame["market_constituent_count"].mean()),
        }
    else:
        report["breadth_stats"] = {"status": "unavailable"}

    if context.volatility_frame is not None:
        report["volatility_stats"] = {
            "status": "observed",
            "date_count": len(context.volatility_frame),
        }
    else:
        report["volatility_stats"] = {
            "status": "benchmark_realized_volatility",
        }

    report["sector_stats"] = {"status": context.factor_availability.get("sector", "unavailable")}

    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report
