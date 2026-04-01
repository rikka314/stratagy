"""
课程基线模型（Naive / Mean / Drift）
====================================
将课件中的简单预测规则转为仓位序列，经 `simulate_strategy()` 回测，输出统一 `ModelResult`。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.backtest import simulate_strategy
from core.indicators import compute_atr

ModelResult = dict[str, Any]


def _ensure_atr(df: pd.DataFrame, atr_period: int = 14) -> pd.DataFrame:
    out = df.copy()
    if "atr" not in out.columns:
        out["atr"] = compute_atr(out, period=atr_period)
    return out


def _sim_to_model_result(label: str, sim_df: pd.DataFrame, trades_df: pd.DataFrame | None) -> ModelResult:
    if "date" in sim_df.columns:
        idx = pd.to_datetime(sim_df["date"], errors="coerce")
    else:
        idx = pd.RangeIndex(len(sim_df))
    equity_series = pd.Series(sim_df["strategy_equity"].to_numpy(), index=idx, name="equity")
    returns = pd.Series(sim_df["strategy_return"].to_numpy(), index=idx, name="returns")
    return {
        "label": label,
        "equity_series": equity_series,
        "returns": returns,
        "trades_df": trades_df,
        "metrics": None,
    }


def mean_target_position(df: pd.DataFrame, window: int = 60) -> pd.Series:
    """
    课程 Mean 基线对应的目标仓位序列。

    说明：
    - 用全历史滚动均值，便于测试段继续复用训练段之前的价格历史
    - 与 `mean_baseline()` 共用该定义，避免 UI / core 逻辑漂移
    """
    close = pd.to_numeric(df["close"], errors="coerce")
    rolling_mean = close.rolling(window=window, min_periods=window).mean()
    target = np.where(close > rolling_mean, 1.0, 0.0).astype(float)
    return pd.Series(target, index=df.index, name="target_position")


def drift_target_position(df: pd.DataFrame, split_idx: int) -> pd.Series:
    """
    课程 Drift 基线对应的目标仓位序列。

    训练段仓位恒为 0；测试段根据价格相对漂移线的位置逐日决定是否持仓。
    """
    n = len(df)
    target = np.zeros(n, dtype=float)
    close = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float, copy=False)
    idx = np.arange(n, dtype=float)

    if split_idx >= 2:
        y_first = float(close[0])
        y_last_train = float(close[split_idx - 1])
        beta = (y_last_train - y_first) / (split_idx - 1)
        pred_line = y_first + beta * idx
        if split_idx < n:
            target[split_idx:] = np.where(close[split_idx:] >= pred_line[split_idx:], 1.0, 0.0)
    elif split_idx <= 0:
        if n >= 2:
            y_first = float(close[0])
            y_last = float(close[-1])
            beta = (y_last - y_first) / (n - 1)
            pred_line = y_first + beta * idx
            target[:] = np.where(close >= pred_line, 1.0, 0.0)
    else:
        y0 = float(close[0])
        if split_idx < n:
            target[split_idx:] = np.where(close[split_idx:] >= y0, 1.0, 0.0)

    return pd.Series(target, index=df.index, name="target_position")


def naive_baseline(df: pd.DataFrame) -> ModelResult:
    """
    永远满仓；净值与买入持有一致。
    通过 `target_position=1` + `initial_position=1` 走 `simulate_strategy()`。
    """
    d = _ensure_atr(df).drop(columns=["target_position"], errors="ignore")
    d["target_position"] = 1.0
    sim_df, trades_df = simulate_strategy(
        d,
        initial_position=1,
        stop_loss_mult=0.0,
        take_profit_mult=0.0,
        return_trades=True,
    )
    return _sim_to_model_result("Naive（买入持有）", sim_df, trades_df)


def mean_baseline(df: pd.DataFrame, window: int = 60) -> ModelResult:
    """
    收盘价 > 过去 window 日滚动均值时满仓，否则空仓。
    """
    d = _ensure_atr(df).drop(columns=["target_position"], errors="ignore")
    d["target_position"] = mean_target_position(d, window=window)
    sim_df, trades_df = simulate_strategy(
        d,
        initial_position=0,
        stop_loss_mult=0.0,
        take_profit_mult=0.0,
        return_trades=True,
    )
    return _sim_to_model_result("Mean（均值基线）", sim_df, trades_df)


def drift_baseline(df: pd.DataFrame, split_idx: int) -> ModelResult:
    """
    在训练段 `df[:split_idx]` 上估计线性漂移（与课件 Drift 一致）：
    以训练期首、末收盘为端点，β = (y_T - y_1) / (T - 1)，并沿**行索引 i** 外推漂移线
    pred[i] = y_1 + β * i。

    测试段（i ≥ split_idx）：若 close[i] ≥ pred[i]，视为价格不低于外推漂移水平，满仓；否则空仓。
    这样仓位随收盘价相对漂移线的位置逐日变化，而不会退化成「β<0 则整段测试永远空仓」。

    训练段仓位为 0，避免在估计期内建仓（与样本外评估口径一致）。
    """
    d = _ensure_atr(df).drop(columns=["target_position"], errors="ignore")
    d["target_position"] = drift_target_position(d, split_idx=split_idx)
    sim_df, trades_df = simulate_strategy(
        d,
        initial_position=0,
        stop_loss_mult=0.0,
        take_profit_mult=0.0,
        return_trades=True,
    )
    return _sim_to_model_result("Drift（漂移基线）", sim_df, trades_df)


def run_all_baselines(df: pd.DataFrame, split_idx: int) -> list[ModelResult]:
    """依次返回 Naive、Mean、Drift 三个基线的 `ModelResult` 列表。"""
    return [
        naive_baseline(df),
        mean_baseline(df),
        drift_baseline(df, split_idx),
    ]
