"""Position mapping and execution constraint research for Phase 3.

Compares:
- Position maps: quantile, dead-zone softsign, vol-target, monotone calibrated
- Execution constraints: no-trade band, rebalance cadence, delta limits
- Cost sensitivity: base, 2x, 4x multipliers

All maps fit parameters on train-only data; validation/test only transform.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator


MapVariant = Literal[
    "quantile_5bin",
    "dead_zone_softsign",
    "vol_target",
    "monotone_calibrated",
]


@dataclass(frozen=True)
class VolatilityForecast:
    """Train-only rolling volatility estimator for vol-targeting."""

    window: int = 20
    annualize_factor: float = 252.0 ** 0.5
    floor: float = 0.01

    def fit_transform(self, returns: pd.Series) -> pd.Series:
        """Compute rolling volatility; first window observations are NaN."""
        vol = returns.rolling(self.window, min_periods=self.window).std()
        vol = vol * self.annualize_factor
        vol = vol.clip(lower=self.floor)
        return vol


@dataclass(frozen=True)
class MonotoneCalibrator:
    """Isotonic regression to map score -> future return; train-only fit."""

    increasing: bool = True
    y_min: float = -0.5
    y_max: float = 0.5

    def fit(
        self, score: pd.Series, future_return: pd.Series
    ) -> tuple[np.ndarray, np.ndarray]:
        """Fit monotone spline on (score, future_return) pairs."""
        from sklearn.isotonic import IsotonicRegression

        valid = np.isfinite(score) & np.isfinite(future_return)
        if valid.sum() < 10:
            raise ValueError("monotone calibrator needs >=10 valid pairs")
        x = score[valid].to_numpy()
        y = future_return[valid].to_numpy()
        y = np.clip(y, self.y_min, self.y_max)
        iso = IsotonicRegression(increasing=self.increasing, out_of_bounds="clip")
        iso.fit(x, y)
        # Extract knots
        x_knots = iso.X_thresholds_
        y_knots = iso.y_thresholds_
        return x_knots, y_knots

    def transform(
        self, score: pd.Series, x_knots: np.ndarray, y_knots: np.ndarray
    ) -> pd.Series:
        """Apply fitted monotone map."""
        values = score.to_numpy()
        result = np.interp(values, x_knots, y_knots)
        return pd.Series(result, index=score.index, name="calibrated_return")


@dataclass(frozen=True)
class PositionMapConfig:
    """Configuration for a single position map variant."""

    variant: MapVariant
    p_max: float = 1.0
    # dead_zone_softsign params
    threshold: float = 0.25
    scale: float = 1.0
    # quantile params
    quantiles: tuple[float, ...] = (0.0, 0.35, 0.60, 0.80, 1.0)
    positions: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75, 1.0)
    # vol_target params
    target_vol: float = 0.15
    vol_window: int = 20
    # monotone_calibrated params
    increasing: bool = True
    calibration_clip: tuple[float, float] = (-0.5, 0.5)

    def __post_init__(self) -> None:
        if not 0.0 < self.p_max <= 1.0:
            raise ValueError("p_max must be in (0, 1]")
        if self.threshold < 0.0:
            raise ValueError("threshold must be non-negative")
        if self.scale <= 0.0:
            raise ValueError("scale must be positive")
        if self.variant == "quantile_5bin":
            if len(self.quantiles) != len(self.positions) or len(self.quantiles) < 2:
                raise ValueError("quantile map requires matching breakpoints")
            if any(a >= b for a, b in zip(self.quantiles, self.quantiles[1:])):
                raise ValueError("quantiles must be strictly increasing")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PositionMapResult:
    """Fitted position map with train-only parameters."""

    config: PositionMapConfig
    # For quantile map: fitted quantile breakpoints from train score
    fitted_quantiles: tuple[float, ...] | None = None
    # For monotone_calibrated: knots
    x_knots: np.ndarray | None = None
    y_knots: np.ndarray | None = None
    # For vol_target: train volatility stats
    train_vol_median: float | None = None

    def transform(
        self, score: pd.Series, returns: pd.Series | None = None
    ) -> pd.Series:
        """Apply fitted map to score; returns needed for vol_target."""
        cfg = self.config
        values = np.asarray(score, dtype=float)

        if cfg.variant == "quantile_5bin":
            q_vals = (
                self.fitted_quantiles if self.fitted_quantiles else cfg.quantiles
            )
            result = np.interp(values, q_vals, cfg.positions)

        elif cfg.variant == "dead_zone_softsign":
            positive = np.maximum(values - cfg.threshold, 0.0)
            result = cfg.p_max * positive / (cfg.scale + positive)

        elif cfg.variant == "vol_target":
            if returns is None:
                raise ValueError("vol_target map requires returns series")
            vol_forecast = VolatilityForecast(window=cfg.vol_window)
            vol = vol_forecast.fit_transform(returns)
            # alpha = score, p = alpha / vol
            alpha = values
            vol_values = vol.reindex(score.index).fillna(
                self.train_vol_median if self.train_vol_median else 0.15
            )
            result = alpha / vol_values

        elif cfg.variant == "monotone_calibrated":
            if self.x_knots is None or self.y_knots is None:
                raise ValueError("monotone_calibrated map not fitted")
            result = np.interp(values, self.x_knots, self.y_knots)
            # Map calibrated return to position (simple linear scaling)
            # Positive return -> long position
            result = np.clip(result * 5.0, 0.0, cfg.p_max)

        else:
            raise ValueError(f"unknown map variant: {cfg.variant}")

        result = np.clip(result, 0.0, cfg.p_max)
        return pd.Series(result, index=score.index, name="target_position")


@dataclass(frozen=True)
class ExecutionConstraints:
    """Execution layer constraints applied after position map."""

    no_trade_band: float = 0.02
    max_daily_delta_increase: float = 0.20
    max_daily_delta_decrease: float = 0.20
    rebalance_cadence_days: int = 1
    min_holding_days: int = 1

    def as_dict(self) -> dict:
        return asdict(self)

    def apply(
        self,
        target_position: pd.Series,
        previous_position: pd.Series,
        days_since_last_rebalance: pd.Series,
    ) -> pd.Series:
        """Apply execution constraints to target position."""
        exec_position = previous_position.copy()

        # Rebalance cadence gate
        should_rebalance = days_since_last_rebalance >= self.rebalance_cadence_days

        for idx in target_position.index:
            if not should_rebalance.loc[idx]:
                continue

            prev = previous_position.loc[idx]
            target = target_position.loc[idx]
            delta = target - prev

            # No-trade band
            if abs(delta) < self.no_trade_band:
                exec_position.loc[idx] = prev
                continue

            # Delta limits
            if delta > 0:
                delta = min(delta, self.max_daily_delta_increase)
            else:
                delta = max(delta, -self.max_daily_delta_decrease)

            exec_position.loc[idx] = prev + delta

        return exec_position


@dataclass
class PositionMapDiagnostics:
    """Diagnostics for a single map variant."""

    variant: str
    execution_label: str
    cost_multiplier: float
    # Score distribution
    score_min: float
    score_median: float
    score_max: float
    score_std: float
    # Position distribution
    near_zero_rate: float
    near_max_rate: float
    mean_exposure: float
    median_exposure: float
    position_unique_count: int
    # Execution
    total_turnover: float
    daily_avg_turnover: float
    trade_count: int
    rebalance_count: int
    # Performance
    gross_return: float
    net_return: float
    transaction_cost: float
    cost_to_gross_ratio: float
    sharpe_ratio: float
    max_drawdown: float
    volatility: float

    def as_dict(self) -> dict:
        return asdict(self)


def fit_position_map(
    config: PositionMapConfig,
    train_score: pd.Series,
    train_returns: pd.Series | None = None,
    train_future_return: pd.Series | None = None,
) -> PositionMapResult:
    """Fit position map parameters on train data only."""
    result = PositionMapResult(config=config)

    if config.variant == "quantile_5bin":
        # Fit quantile breakpoints from train score distribution
        values = train_score.to_numpy()
        values = values[np.isfinite(values)]
        if values.size < 10:
            raise ValueError("need >=10 finite train scores")
        # Use 5 bins: 0, 35%, 60%, 80%, 100%
        q_vals = np.quantile(values, [0.0, 0.35, 0.60, 0.80, 1.0])
        result.fitted_quantiles = tuple(float(v) for v in q_vals)

    elif config.variant == "vol_target":
        if train_returns is None:
            raise ValueError("vol_target requires train_returns")
        vol_forecast = VolatilityForecast(window=config.vol_window)
        vol = vol_forecast.fit_transform(train_returns)
        result.train_vol_median = float(vol.median())

    elif config.variant == "monotone_calibrated":
        if train_future_return is None:
            raise ValueError("monotone_calibrated requires train_future_return")
        calibrator = MonotoneCalibrator(
            increasing=config.increasing,
            y_min=config.calibration_clip[0],
            y_max=config.calibration_clip[1],
        )
        x_knots, y_knots = calibrator.fit(train_score, train_future_return)
        result.x_knots = x_knots
        result.y_knots = y_knots

    elif config.variant == "dead_zone_softsign":
        # No fitting needed, uses config params directly
        pass

    else:
        raise ValueError(f"unknown variant: {config.variant}")

    return result


def compute_diagnostics(
    variant: str,
    execution_label: str,
    cost_multiplier: float,
    score: pd.Series,
    target_position: pd.Series,
    exec_position: pd.Series,
    returns: pd.Series,
    base_commission: float = 0.001,
    base_slippage: float = 0.0005,
) -> PositionMapDiagnostics:
    """Compute full diagnostics for a map + execution + cost scenario."""
    # Score stats
    score_vals = score.to_numpy()
    score_vals = score_vals[np.isfinite(score_vals)]

    # Position stats
    near_zero = (exec_position <= 0.01).mean()
    near_max = (exec_position >= 0.99).mean()

    # Turnover
    position_changes = exec_position.diff().abs()
    total_turnover = position_changes.sum()
    daily_avg_turnover = position_changes.mean()
    trade_count = (position_changes > 1e-6).sum()
    rebalance_count = (position_changes > 0.02).sum()

    # Returns
    strategy_returns = exec_position.shift(1) * returns
    cost_rate = (base_commission + base_slippage) * cost_multiplier
    costs = position_changes * cost_rate
    net_returns = strategy_returns - costs

    gross_return = (1 + strategy_returns).prod() - 1
    net_return = (1 + net_returns).prod() - 1
    total_cost = costs.sum()
    cost_to_gross = total_cost / abs(gross_return) if abs(gross_return) > 1e-6 else 0.0

    # Risk metrics
    sharpe = (
        net_returns.mean() / net_returns.std() * (252**0.5)
        if net_returns.std() > 1e-6
        else 0.0
    )
    cum_net = (1 + net_returns).cumprod()
    running_max = cum_net.expanding().max()
    drawdown = (cum_net - running_max) / running_max
    max_dd = drawdown.min()
    vol = net_returns.std() * (252**0.5)

    return PositionMapDiagnostics(
        variant=variant,
        execution_label=execution_label,
        cost_multiplier=cost_multiplier,
        score_min=float(score_vals.min()) if score_vals.size > 0 else 0.0,
        score_median=float(np.median(score_vals)) if score_vals.size > 0 else 0.0,
        score_max=float(score_vals.max()) if score_vals.size > 0 else 0.0,
        score_std=float(np.std(score_vals)) if score_vals.size > 0 else 0.0,
        near_zero_rate=float(near_zero),
        near_max_rate=float(near_max),
        mean_exposure=float(exec_position.mean()),
        median_exposure=float(exec_position.median()),
        position_unique_count=int(exec_position.nunique()),
        total_turnover=float(total_turnover),
        daily_avg_turnover=float(daily_avg_turnover),
        trade_count=int(trade_count),
        rebalance_count=int(rebalance_count),
        gross_return=float(gross_return),
        net_return=float(net_return),
        transaction_cost=float(total_cost),
        cost_to_gross_ratio=float(cost_to_gross),
        sharpe_ratio=float(sharpe),
        max_drawdown=float(max_dd),
        volatility=float(vol),
    )


def run_position_map_ablation(
    train_score: pd.Series,
    train_returns: pd.Series,
    train_future_return: pd.Series,
    test_score: pd.Series,
    test_returns: pd.Series,
    map_configs: list[PositionMapConfig],
    execution_configs: list[ExecutionConstraints],
    cost_multipliers: list[float],
    output_dir: Path,
) -> pd.DataFrame:
    """Run full position map ablation grid.

    Returns:
        DataFrame with one row per (map, execution, cost) combination.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for map_cfg in map_configs:
        print(f"Fitting map: {map_cfg.variant}")
        fitted_map = fit_position_map(
            map_cfg, train_score, train_returns, train_future_return
        )

        # Transform test scores
        test_target = fitted_map.transform(test_score, test_returns)

        for exec_cfg in execution_configs:
            exec_label = (
                f"ntb{exec_cfg.no_trade_band:.3f}_"
                f"cad{exec_cfg.rebalance_cadence_days}_"
                f"delta{exec_cfg.max_daily_delta_increase:.2f}"
            )

            # Apply execution constraints
            prev_position = pd.Series(0.0, index=test_target.index)
            days_since = pd.Series(999, index=test_target.index)
            exec_position = exec_cfg.apply(test_target, prev_position, days_since)

            # Simulate realistic execution with state tracking
            exec_positions = []
            prev_pos = 0.0
            days_count = 0
            for idx in test_target.index:
                days_count += 1
                target = test_target.loc[idx]
                delta = target - prev_pos

                # Rebalance cadence
                if days_count < exec_cfg.rebalance_cadence_days:
                    exec_positions.append(prev_pos)
                    continue

                # No-trade band
                if abs(delta) < exec_cfg.no_trade_band:
                    exec_positions.append(prev_pos)
                    continue

                # Delta limits
                if delta > 0:
                    delta = min(delta, exec_cfg.max_daily_delta_increase)
                else:
                    delta = max(delta, -exec_cfg.max_daily_delta_decrease)

                new_pos = prev_pos + delta
                exec_positions.append(new_pos)
                prev_pos = new_pos
                days_count = 0

            exec_position = pd.Series(exec_positions, index=test_target.index)

            for cost_mult in cost_multipliers:
                diag = compute_diagnostics(
                    variant=map_cfg.variant,
                    execution_label=exec_label,
                    cost_multiplier=cost_mult,
                    score=test_score,
                    target_position=test_target,
                    exec_position=exec_position,
                    returns=test_returns,
                )
                results.append(diag.as_dict())

    df = pd.DataFrame(results)
    df.to_csv(output_dir / "position_map_ablation.csv", index=False)
    print(f"Saved {len(df)} ablation results to {output_dir / 'position_map_ablation.csv'}")
    return df


__all__ = [
    "MapVariant",
    "PositionMapConfig",
    "PositionMapResult",
    "ExecutionConstraints",
    "PositionMapDiagnostics",
    "fit_position_map",
    "compute_diagnostics",
    "run_position_map_ablation",
]
