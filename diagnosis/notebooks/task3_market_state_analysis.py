"""
Task 3.4 - Market state performance analysis.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from utils import add_all_indicators, calculate_all_metrics, load_data, save_results_to_csv
from task3_backtest_framework import backtest_with_cost
from task3_simple_strategies import build_baseline_strategies


def load_market_states(path: str) -> pd.DataFrame:
    market_states = pd.read_csv(path)
    if "year" not in market_states.columns or "market_state" not in market_states.columns:
        raise ValueError("task1_market_states.csv must include 'year' and 'market_state' columns.")
    return market_states[["year", "market_state"]]


def compute_state_metrics(
    df: pd.DataFrame,
    state: str,
) -> Dict[str, float]:
    state_df = df[df["market_state"] == state]
    if state_df.empty:
        return {
            "total_return": np.nan,
            "annual_return": np.nan,
            "annual_volatility": np.nan,
            "sharpe_ratio": np.nan,
            "sortino_ratio": np.nan,
            "max_drawdown": np.nan,
            "calmar_ratio": np.nan,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "num_trades": 0.0,
            "num_days": 0.0,
            "num_years": 0.0,
        }

    returns = state_df["strategy_return"].dropna()
    equity = (1 + returns).cumprod()
    metrics = calculate_all_metrics(returns, equity)
    metrics.update(
        {
            "num_days": float(len(state_df)),
            "num_years": float(state_df["year"].nunique()),
        }
    )
    return metrics


def run_market_state_analysis(
    symbol: str = "aapl",
    data_dir: str = "data",
    cost: float = 0.001,
    market_state_path: str = None,
    output_suffix: str = "",
) -> pd.DataFrame:
    if market_state_path is None:
        market_state_path = os.path.join(ROOT_DIR, "diagnosis", "results", "task1_market_states.csv")

    df = load_data(symbol, data_dir=data_dir)
    df = add_all_indicators(df)
    df["year"] = df["date"].dt.year

    market_states = load_market_states(market_state_path)
    df = df.merge(market_states, on="year", how="left")

    strategies = build_baseline_strategies()
    states = ["牛市", "熊市", "震荡市"]

    results: List[Dict[str, float]] = []

    for strategy in strategies:
        positions = strategy.generate_positions(df)
        bt_df = backtest_with_cost(df, positions, cost=cost)

        bt_df["year"] = df["year"]
        bt_df["market_state"] = df["market_state"]

        for state in states:
            metrics = compute_state_metrics(bt_df, state)
            results.append(
                {
                    "strategy": strategy.name,
                    "market_state": state,
                    **metrics,
                }
            )

    result_df = pd.DataFrame(results)
    results_dir = os.path.join(ROOT_DIR, "diagnosis", "results")
    save_results_to_csv(
        result_df,
        f"task3_market_state_performance{output_suffix}.csv",
        output_dir=results_dir,
    )
    return result_df


if __name__ == "__main__":
    run_market_state_analysis()
