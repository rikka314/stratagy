"""
Task 3.1 - Implement 5 baseline strategies for comparison.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils import add_all_indicators


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    z = (series - mean) / std
    return z.replace([np.inf, -np.inf], np.nan)


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def last_percentile(values: pd.Series) -> float:
        ranked = values.rank(pct=True)
        return float(ranked.iloc[-1])

    return series.rolling(window=window, min_periods=window).apply(last_percentile, raw=False)


class Strategy:
    def __init__(self, name: str):
        self.name = name

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        """Return a position series (0/1 or 0/0.5/1)."""
        raise NotImplementedError


class BuyHoldStrategy(Strategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)


class MACDStrategy(Strategy):
    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        buy = (df["macd"] > df["signal"]) & (df["macd"].shift(1) <= df["signal"].shift(1))
        sell = (df["macd"] < df["signal"]) & (df["macd"].shift(1) >= df["signal"].shift(1))
        signals = pd.Series(np.nan, index=df.index)
        signals[buy] = 1.0
        signals[sell] = 0.0
        return signals.ffill().fillna(0.0)


class RSIStrategy(Strategy):
    def __init__(self, name: str, lower: float = 30.0, upper: float = 70.0):
        super().__init__(name)
        self.lower = lower
        self.upper = upper

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        buy = df["rsi"] < self.lower
        sell = df["rsi"] > self.upper
        signals = pd.Series(np.nan, index=df.index)
        signals[buy] = 1.0
        signals[sell] = 0.0
        return signals.ffill().fillna(0.0)


class TrendStrategy(Strategy):
    def __init__(self, name: str, ema_period: int = 50):
        super().__init__(name)
        self.ema_period = ema_period

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        ema_col = f"ema_{self.ema_period}"
        if ema_col not in df.columns:
            raise KeyError(f"Missing indicator column: {ema_col}")
        return (df["close"] > df[ema_col]).astype(float)


class OriginalStrategy(Strategy):
    def __init__(
        self,
        name: str,
        ema_fast: int = 20,
        ema_slow: int = 60,
        adx_threshold: float = 20.0,
        rsi_lower: float = 30.0,
        rsi_upper: float = 70.0,
        momentum_short: int = 5,
        momentum_long: int = 20,
        score_lookback: int = 30,
        score_mid_pct: float = 0.6,
        score_high_pct: float = 0.8,
        weight_mom_short: float = 1.0,
        weight_mom_long: float = 1.0,
        weight_macd: float = 1.0,
        weight_rsi: float = 0.5,
        weight_vol: float = 0.5,
        entry_threshold: float = 0.5,
        exit_threshold: float = -0.5,
    ):
        super().__init__(name)
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.adx_threshold = adx_threshold
        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.momentum_short = momentum_short
        self.momentum_long = momentum_long
        self.score_lookback = score_lookback
        self.score_mid_pct = score_mid_pct
        self.score_high_pct = score_high_pct
        self.weight_mom_short = weight_mom_short
        self.weight_mom_long = weight_mom_long
        self.weight_macd = weight_macd
        self.weight_rsi = weight_rsi
        self.weight_vol = weight_vol
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def _ensure_emas(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        return df

    def generate_positions(self, df: pd.DataFrame) -> pd.Series:
        df = df.copy()
        df = self._ensure_emas(df)

        df["trend_ok"] = df["ema_fast"] > df["ema_slow"]
        df["strength_ok"] = df["adx"] >= self.adx_threshold
        df["rsi_ok"] = (df["rsi"] > self.rsi_lower) & (df["rsi"] < self.rsi_upper)
        df["ret_short"] = df["close"].pct_change(self.momentum_short)
        df["ret_long"] = df["close"].pct_change(self.momentum_long)
        df["volatility"] = df["atr"] / df["close"]
        df["mom_short_z"] = rolling_zscore(df["ret_short"], self.score_lookback)
        df["mom_long_z"] = rolling_zscore(df["ret_long"], self.score_lookback)
        df["macd_z"] = rolling_zscore(df["histogram"], self.score_lookback)
        df["rsi_z"] = rolling_zscore(df["rsi"], self.score_lookback)
        df["vol_z"] = rolling_zscore(df["volatility"], self.score_lookback)

        df["factor_score"] = (
            self.weight_mom_short * df["mom_short_z"]
            + self.weight_mom_long * df["mom_long_z"]
            + self.weight_macd * df["macd_z"]
            + self.weight_rsi * df["rsi_z"]
            - self.weight_vol * df["vol_z"]
        ).fillna(0.0)

        df["factor_percentile"] = rolling_percentile(df["factor_score"], self.score_lookback).fillna(0.0)
        score_position = np.select(
            [df["factor_percentile"] >= self.score_high_pct, df["factor_percentile"] >= self.score_mid_pct],
            [1.0, 0.5],
            default=0.0,
        )

        macd_above = df["macd"] > df["signal"]
        filter_ok = (
            df["trend_ok"]
            & df["strength_ok"]
            & df["rsi_ok"]
            & macd_above
            & (df["factor_score"] >= self.entry_threshold)
        )
        target_position = np.where(filter_ok, score_position, 0.0)
        exit_block = (
            (df["factor_score"] <= self.exit_threshold)
            | (df["ema_fast"] < df["ema_slow"])
            | (df["rsi"] > self.rsi_upper)
            | (df["rsi"] < self.rsi_lower)
            | (df["macd"] < df["signal"])
        )
        target_position = np.where(exit_block, 0.0, target_position)
        return pd.Series(target_position, index=df.index)


def build_baseline_strategies() -> list[Strategy]:
    return [
        BuyHoldStrategy("S1_BuyHold"),
        MACDStrategy("S2_MACD_Only"),
        RSIStrategy("S3_RSI_Only"),
        TrendStrategy("S4_Trend_Only"),
        OriginalStrategy("S5_Original"),
    ]


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Add required indicators for all strategies."""
    return add_all_indicators(df)


__all__ = [
    "Strategy",
    "BuyHoldStrategy",
    "MACDStrategy",
    "RSIStrategy",
    "TrendStrategy",
    "OriginalStrategy",
    "build_baseline_strategies",
    "prepare_data",
]
