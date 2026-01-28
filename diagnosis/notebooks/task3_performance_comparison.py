"""
Task 3.3 - Compute comprehensive performance comparison table.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Tuple

import numpy as np
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from utils import add_all_indicators, calculate_all_metrics, load_data, save_results_to_csv
from task3_simple_strategies import build_baseline_strategies
from task3_backtest_framework import backtest_with_cost


def compute_trade_stats(df: pd.DataFrame) -> Dict[str, float]:
    """Compute trade-level stats based on position changes."""
    trade_returns = []
    holding_days = []
    in_position = False
    entry_price = None
    entry_idx = None

    for i in range(len(df)):
        pos = df["position"].iloc[i]
        if not in_position and pos > 0:
            in_position = True
            entry_price = df["close"].iloc[i]
            entry_idx = i
        elif in_position and pos <= 0:
            exit_price = df["close"].iloc[i]
            trade_returns.append(exit_price / entry_price - 1 if entry_price else 0.0)
            holding_days.append(i - entry_idx)
            in_position = False

    if in_position and entry_price is not None:
        exit_price = df["close"].iloc[-1]
        trade_returns.append(exit_price / entry_price - 1 if entry_price else 0.0)
        holding_days.append(len(df) - 1 - entry_idx)

    if len(trade_returns) == 0:
        return {"num_trades": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "avg_holding_days": 0.0}

    trade_returns = pd.Series(trade_returns)
    win_rate = (trade_returns > 0).mean()
    profit_factor = (
        trade_returns[trade_returns > 0].sum() / abs(trade_returns[trade_returns < 0].sum())
        if (trade_returns < 0).any()
        else np.inf
    )
    avg_holding_days = float(np.mean(holding_days)) if holding_days else 0.0
    return {
        "num_trades": float(len(trade_returns)),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "avg_holding_days": avg_holding_days,
    }


def run_performance_comparison(
    symbol: str = "aapl",
    data_dir: str = "data",
    cost: float = 0.001,
    output_suffix: str = "",
) -> pd.DataFrame:
    df = load_data(symbol, data_dir=data_dir)
    df = add_all_indicators(df)

    results = []
    strategies = build_baseline_strategies()

    for strategy in strategies:
        positions = strategy.generate_positions(df)
        bt_df = backtest_with_cost(df, positions, cost=cost)
        metrics = calculate_all_metrics(bt_df["strategy_return"].dropna(), bt_df["equity"])
        trade_stats = compute_trade_stats(bt_df)
        metrics["num_trades"] = trade_stats["num_trades"]
        metrics["win_rate"] = trade_stats["win_rate"]
        metrics["profit_factor"] = trade_stats["profit_factor"]
        results.append(
            {
                "strategy": strategy.name,
                **metrics,
                "avg_holding_days": trade_stats["avg_holding_days"],
            }
        )

    comparison_df = pd.DataFrame(results)
    results_dir = os.path.join(ROOT_DIR, "diagnosis", "results")
    save_results_to_csv(
        comparison_df,
        f"task3_backtest_results{output_suffix}.csv",
        output_dir=results_dir,
    )
    return comparison_df


if __name__ == "__main__":
    run_performance_comparison()
