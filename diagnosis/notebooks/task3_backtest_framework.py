"""
Task 3.2 - Unified backtest framework for strategy comparison.
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

from utils import (
    add_all_indicators,
    calculate_all_metrics,
    load_data,
    plot_equity_curves,
    save_results_to_csv,
    split_train_test,
)

from task3_simple_strategies import build_baseline_strategies


def backtest_with_cost(df: pd.DataFrame, position: pd.Series, cost: float = 0.001) -> pd.DataFrame:
    """Backtest using position series with transaction costs (0.1% per side by default)."""
    df = df.copy()
    df["position"] = position.fillna(0.0).astype(float)
    returns = df["close"].pct_change().fillna(0.0)
    turnover = df["position"].diff().abs().fillna(0.0)
    df["strategy_return"] = df["position"].shift(1).fillna(0.0) * returns - turnover * cost
    df["equity"] = (1 + df["strategy_return"]).cumprod()
    return df


def extract_trade_log(df: pd.DataFrame) -> pd.DataFrame:
    """Simple trade log based on 0 -> >0 entries and >0 -> 0 exits."""
    trades = []
    in_position = False
    entry_idx = None
    entry_price = None
    entry_pos = None

    for i in range(len(df)):
        pos = df["position"].iloc[i]
        if not in_position and pos > 0:
            in_position = True
            entry_idx = i
            entry_price = df["close"].iloc[i]
            entry_pos = pos
        elif in_position and pos <= 0:
            exit_idx = i
            exit_price = df["close"].iloc[i]
            holding_days = exit_idx - entry_idx
            gross_return = exit_price / entry_price - 1 if entry_price else 0.0
            trades.append(
                {
                    "entry_date": df["date"].iloc[entry_idx],
                    "exit_date": df["date"].iloc[exit_idx],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "position_size": entry_pos,
                    "holding_days": holding_days,
                    "gross_return": gross_return,
                }
            )
            in_position = False
            entry_idx = None
            entry_price = None
            entry_pos = None

    if in_position and entry_idx is not None:
        exit_idx = len(df) - 1
        exit_price = df["close"].iloc[exit_idx]
        holding_days = exit_idx - entry_idx
        gross_return = exit_price / entry_price - 1 if entry_price else 0.0
        trades.append(
            {
                "entry_date": df["date"].iloc[entry_idx],
                "exit_date": df["date"].iloc[exit_idx],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "position_size": entry_pos,
                "holding_days": holding_days,
                "gross_return": gross_return,
                "forced_exit": True,
            }
        )

    return pd.DataFrame(trades)


def evaluate_strategy(
    df: pd.DataFrame,
    position: pd.Series,
    train_ratio: float,
    cost: float,
) -> Tuple[pd.DataFrame, Dict[str, float], Dict[str, float], Dict[str, float]]:
    """Run backtest and compute metrics for full/train/test."""
    bt_df = backtest_with_cost(df, position, cost=cost)
    split_idx = int(len(bt_df) * train_ratio)

    full_metrics = calculate_all_metrics(bt_df["strategy_return"].dropna(), bt_df["equity"])
    train_metrics = calculate_all_metrics(
        bt_df.iloc[:split_idx]["strategy_return"].dropna(),
        bt_df.iloc[:split_idx]["equity"],
    )
    test_metrics = calculate_all_metrics(
        bt_df.iloc[split_idx:]["strategy_return"].dropna(),
        bt_df.iloc[split_idx:]["equity"],
    )

    return bt_df, full_metrics, train_metrics, test_metrics


def run_backtests(
    symbol: str = "aapl",
    data_dir: str = "data",
    cost: float = 0.001,
    train_ratio: float = 0.7,
    output_suffix: str = "",
) -> None:
    df = load_data(symbol, data_dir=data_dir)
    df = add_all_indicators(df)

    strategies = build_baseline_strategies()

    metrics_rows = []
    equity_curves: Dict[str, pd.Series] = {}

    results_dir = os.path.join(ROOT_DIR, "diagnosis", "results")
    figures_dir = os.path.join(ROOT_DIR, "diagnosis", "figures")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    for strategy in strategies:
        positions = strategy.generate_positions(df)
        bt_df, full_metrics, train_metrics, test_metrics = evaluate_strategy(
            df, positions, train_ratio=train_ratio, cost=cost
        )

        metrics_rows.append(
            {
                "strategy": strategy.name,
                **{f"full_{k}": v for k, v in full_metrics.items()},
                **{f"train_{k}": v for k, v in train_metrics.items()},
                **{f"test_{k}": v for k, v in test_metrics.items()},
            }
        )

        equity_curves[strategy.name] = bt_df["equity"]

        trade_log = extract_trade_log(bt_df)
        trade_log.to_csv(
            os.path.join(results_dir, f"task3_trade_log_{strategy.name}.csv"), index=False
        )

    metrics_df = pd.DataFrame(metrics_rows)
    save_results_to_csv(
        metrics_df,
        f"task3_backtest_results_split{output_suffix}.csv",
        output_dir=results_dir,
    )

    plot_equity_curves(
        equity_curves,
        title="Task 3 - 基准策略权益曲线对比",
        save_path=os.path.join(figures_dir, f"task3_equity_curves{output_suffix}.png"),
    )


if __name__ == "__main__":
    run_backtests()
