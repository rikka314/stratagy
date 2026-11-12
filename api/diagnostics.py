"""Presentation diagnostics for the API, using the existing Python backtest."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.backtest import walk_forward_backtest


def build_walk_forward(
    full_signal_df: pd.DataFrame,
    params_snapshot: dict[str, Any],
    train_window: int,
    test_window: int,
) -> dict[str, Any]:
    """Replay existing signals with the same rolling-window semantics as the UI.

    This deliberately does not claim that upstream models are refit per window.
    JSON conversion belongs to the API's common serializer.
    """
    if train_window < 1 or test_window < 1:
        raise ValueError("Train and test windows must be positive.")
    if train_window + test_window > len(full_signal_df):
        raise ValueError("Train and test windows exceed the available data.")
    windows, equity = walk_forward_backtest(
        full_signal_df,
        train_window=train_window,
        test_window=test_window,
        stop_loss_mult=float(params_snapshot.get("stop_loss_mult", 0.0)),
        take_profit_mult=float(params_snapshot.get("take_profit_mult", 0.0)),
    )
    return {
        "windows": windows,
        "equity": equity,
        "train_window": train_window,
        "test_window": test_window,
        "method": "existing_signal_rolling_replay",
    }


def _split_diagnostics(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    drawdown = pd.DataFrame(columns=["date", "drawdown"])
    monthly = pd.DataFrame(columns=["month", "strategy_return", "buy_hold_return"])
    if frame.empty or "date" not in frame:
        return {"drawdown": drawdown, "monthly_returns": monthly}
    dates = pd.to_datetime(frame["date"], errors="coerce")
    if "strategy_equity" in frame:
        equity = pd.to_numeric(frame["strategy_equity"], errors="coerce")
        peaks = equity.cummax().replace(0, np.nan)
        drawdown = pd.DataFrame({"date": dates, "drawdown": equity / peaks - 1})
    columns = [name for name in ("strategy_return", "buy_hold_return") if name in frame]
    if columns:
        returns = frame[columns].apply(pd.to_numeric, errors="coerce")
        returns.index = pd.DatetimeIndex(dates)
        returns = returns.loc[returns.index.notna()]
        monthly = returns.groupby(returns.index.to_period("M")).agg(
            lambda values: (1 + values).prod(min_count=1) - 1
        )
        monthly.index = monthly.index.astype(str)
        monthly = monthly.rename_axis("month").reset_index()
    return {"drawdown": drawdown, "monthly_returns": monthly}


def build_artifact_diagnostics(artifact: Any) -> dict[str, Any]:
    """Keep train/test diagnostics separate and preserve missing ML results."""
    return {
        "train": _split_diagnostics(artifact.train_sim_df),
        "test": _split_diagnostics(artifact.test_sim_df),
        "ml_quality": artifact.ml_quality,
    }
