"""Presentation-only data derived from the canonical Python portfolio result."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.visualization import create_periodic_returns_heatmap


def build_portfolio_presentation(result: dict[str, Any]) -> dict[str, Any]:
    """Build drawdown and M/Q/YE heatmaps with the legacy visualization path."""
    equity = result.get("portfolio_equity")
    drawdown: list[dict[str, Any]] = []
    if isinstance(equity, pd.Series) and not equity.empty:
        values = pd.to_numeric(equity, errors="coerce")
        series = values.div(values.cummax()).sub(1.0)
        drawdown = [
            {"date": _date_text(index), "drawdown": _finite(value)}
            for index, value in series.items()
        ]

    returns: dict[str, pd.Series] = {}
    portfolio_returns = result.get("portfolio_strat_ret")
    if isinstance(portfolio_returns, pd.Series) and not portfolio_returns.empty:
        returns["portfolio"] = portfolio_returns
    for symbol, item in (result.get("individual_results") or {}).items():
        strategy_return = item.get("strategy_return")
        if isinstance(strategy_return, pd.Series) and not strategy_return.empty:
            returns[str(symbol)] = strategy_return

    periodic = {period: _heatmap_payload(returns, period) for period in ("M", "Q", "YE")}
    return {"drawdown": drawdown, "periodic_returns": periodic}


def _heatmap_payload(returns: dict[str, pd.Series], period: str) -> dict[str, Any] | None:
    figure = create_periodic_returns_heatmap(returns_series=returns, period=period)
    if figure is None or not figure.data:
        return None
    trace = figure.data[0]
    return {
        "x": [str(value) for value in trace.x],
        "y": [str(value) for value in trace.y],
        "z": [[_finite(value) for value in row] for row in np.asarray(trace.z, dtype=object).tolist()],
        "text": [[str(value or "") for value in row] for row in np.asarray(trace.text, dtype=object).tolist()],
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _date_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)
