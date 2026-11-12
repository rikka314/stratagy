"""Leak-aware expert utility metrics for a configurable future horizon."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


class ExpertUtilityV4:
    """Compute complete-horizon expert metrics, defaulting to 20 days."""

    def __init__(self, horizon: int = 20) -> None:
        self.horizon = int(horizon)
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")

    def compute_expert_utility(
        self,
        expert_positions: np.ndarray,
        future_returns: np.ndarray,
    ) -> dict[str, float]:
        positions = np.asarray(expert_positions, dtype=float)
        returns = np.asarray(future_returns, dtype=float)
        if positions.shape != (self.horizon,) or returns.shape != (self.horizon,):
            raise ValueError(f"inputs must each contain exactly {self.horizon} observations")
        if not np.isfinite(positions).all() or not np.isfinite(returns).all():
            raise ValueError("positions and returns must be finite")
        if np.any((positions < 0.0) | (positions > 1.0)):
            raise ValueError("expert positions must be within [0, 1]")

        strategy_returns = positions * returns
        mean_return = float(strategy_returns.mean())
        volatility = float(strategy_returns.std(ddof=0))
        sharpe_ratio = mean_return / volatility * np.sqrt(252.0) if volatility > 1e-12 else 0.0
        equity = np.concatenate(([1.0], np.cumprod(1.0 + strategy_returns)))
        drawdown = equity / np.maximum.accumulate(equity) - 1.0
        return {
            "mean_return": mean_return,
            "sharpe_ratio": float(sharpe_ratio),
            "win_rate": float(np.mean(strategy_returns > 0.0)),
            "max_drawdown": float(drawdown.min()),
            "total_return": float(equity[-1] - 1.0),
        }

    def compute_all_experts_utility(
        self,
        expert_positions_dict: Mapping[str, np.ndarray],
        future_returns: np.ndarray,
    ) -> pd.DataFrame:
        rows = []
        for expert_name, positions in expert_positions_dict.items():
            row = self.compute_expert_utility(positions, future_returns)
            row["expert_name"] = str(expert_name)
            rows.append(row)
        if not rows:
            raise ValueError("at least one expert is required")
        return pd.DataFrame(rows).set_index("expert_name")

    def generate_labels_for_backtest(
        self,
        stock_data: pd.DataFrame,
        expert_decisions: Mapping[str, pd.Series],
        start_idx: int = 0,
        end_idx: int | None = None,
    ) -> pd.DataFrame:
        """Generate labels at decision date ``t`` from ``t+1 ... t+h``.

        Partial future windows are never emitted. Return ``t+1`` is earned by
        the position decided at ``t``; consequently the horizon uses decision
        positions ``t ... t+h-1`` against returns ``t+1 ... t+h``.
        """

        close_column = "close" if "close" in stock_data.columns else "Close"
        if close_column not in stock_data.columns:
            raise ValueError("stock_data must contain a close column")
        if not stock_data.index.is_unique:
            raise ValueError("stock_data index must be unique")
        closes = pd.to_numeric(stock_data[close_column], errors="coerce")
        returns = closes.pct_change(fill_method=None)
        stop = len(stock_data) - self.horizon if end_idx is None else int(end_idx)
        stop = min(stop, len(stock_data) - self.horizon)
        rows: list[dict[str, float | pd.Timestamp]] = []
        for index in range(max(0, int(start_idx)), max(0, stop)):
            decision_index = stock_data.index[index : index + self.horizon]
            future_returns = returns.iloc[index + 1 : index + 1 + self.horizon].to_numpy(dtype=float)
            if len(future_returns) != self.horizon or not np.isfinite(future_returns).all():
                continue
            positions_by_expert: dict[str, np.ndarray] = {}
            for expert_name, raw_positions in expert_decisions.items():
                positions = pd.to_numeric(
                    raw_positions.reindex(decision_index), errors="coerce"
                ).to_numpy(dtype=float)
                if len(positions) == self.horizon and np.isfinite(positions).all():
                    positions_by_expert[str(expert_name)] = positions
            if not positions_by_expert:
                continue
            metrics = self.compute_all_experts_utility(positions_by_expert, future_returns)
            row: dict[str, float | pd.Timestamp] = {"date": stock_data.index[index]}
            for expert_name, values in metrics.iterrows():
                for metric, value in values.items():
                    row[f"{expert_name}_{metric}"] = float(value)
            rows.append(row)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("date")


def compute_expert_utility_20d(
    stock_data: pd.DataFrame,
    expert_decisions: Mapping[str, pd.Series],
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    labels = ExpertUtilityV4(horizon=20).generate_labels_for_backtest(
        stock_data,
        expert_decisions,
    )
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".parquet":
            labels.to_parquet(path)
        elif path.suffix.lower() == ".csv":
            labels.to_csv(path)
        else:
            raise ValueError(f"unsupported output format: {path.suffix}")
    return labels


__all__ = ["ExpertUtilityV4", "compute_expert_utility_20d"]
