"""Robust Composite weight and interaction research primitives.

This module is research-only. Every fitted statistic is derived from a train
window and returned as an immutable-style result without modifying inputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResearchFold:
    fold_id: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    purge_days: int = 20
    embargo_days: int = 20

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        return {key: value.isoformat() if isinstance(value, pd.Timestamp) else value for key, value in result.items()}


@dataclass(frozen=True)
class WeightResearchConfig:
    factors: tuple[str, ...]
    directions: Mapping[str, int]
    family_by_factor: Mapping[str, str]
    family_budgets: Mapping[str, float]
    factor_budget: float = 2.0
    interaction_budget: float = 0.75
    lambda_drawdown: float = 0.25
    lambda_turnover: float = 0.05
    lambda_cost: float = 0.05
    lambda_complexity: float = 0.02
    commission_bps: float = 1.0
    slippage_bps: float = 2.0
    horizon_days: int = 20
    block_length: int = 20
    bootstrap_samples: int = 1000

    def __post_init__(self) -> None:
        if not self.factors or any(not factor for factor in self.factors):
            raise ValueError("factors must be non-empty")
        if set(self.factors) != set(self.directions) or set(self.factors) != set(self.family_by_factor):
            raise ValueError("directions and family_by_factor must cover factors exactly")
        if any(direction not in (-1, 1) for direction in self.directions.values()):
            raise ValueError("factor directions must be -1 or 1")
        if any(value <= 0 for value in self.family_budgets.values()):
            raise ValueError("family budgets must be positive")
        if self.factor_budget <= 0 or self.interaction_budget < 0:
            raise ValueError("budgets must be positive/non-negative")
        if self.horizon_days <= 0 or self.block_length <= 0 or self.bootstrap_samples <= 0:
            raise ValueError("horizon, block length and bootstrap samples must be positive")


@dataclass(frozen=True)
class TrainTransform:
    center: Mapping[str, float]
    scale: Mapping[str, float]
    lower: Mapping[str, float]
    upper: Mapping[str, float]
    covariance: tuple[tuple[float, ...], ...]
    fit_start: str
    fit_end: str

    def transform(self, frame: pd.DataFrame, factors: Iterable[str]) -> pd.DataFrame:
        names = tuple(factors)
        values = frame.loc[:, names].apply(pd.to_numeric, errors="coerce")
        result = pd.DataFrame(index=frame.index)
        for factor in names:
            clipped = values[factor].clip(self.lower[factor], self.upper[factor])
            result[factor] = (clipped - self.center[factor]) / self.scale[factor]
        return result

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def fit_train_transform(frame: pd.DataFrame, factors: Iterable[str]) -> TrainTransform:
    """Fit robust clipping/scaling and covariance using only ``frame``."""
    names = tuple(factors)
    missing = sorted(set(names) - set(frame.columns))
    if missing:
        raise ValueError(f"missing factors: {missing}")
    values = frame.loc[:, names].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    if values.dropna().empty:
        raise ValueError("train factors contain no finite observations")
    center: dict[str, float] = {}
    scale: dict[str, float] = {}
    lower_bounds: dict[str, float] = {}
    upper_bounds: dict[str, float] = {}
    transformed = pd.DataFrame(index=values.index)
    for factor in names:
        series = values[factor].dropna()
        median = float(series.median())
        lower, upper = series.quantile([0.01, 0.99]).to_numpy(dtype=float)
        clipped = series.clip(lower, upper)
        mad = float(np.median(np.abs(clipped.to_numpy() - median)))
        spread = max(1.4826 * mad, float(clipped.std(ddof=1)), 1e-8)
        center[factor] = median
        scale[factor] = spread
        lower_bounds[factor] = float(lower)
        upper_bounds[factor] = float(upper)
        transformed[factor] = ((values[factor].clip(lower, upper) - median) / spread).fillna(0.0)
    covariance = transformed.loc[:, names].cov().fillna(0.0).to_numpy(dtype=float)
    covariance = covariance + np.eye(len(names), dtype=float) * 1e-8
    return TrainTransform(
        center=center,
        scale=scale,
        lower=lower_bounds,
        upper=upper_bounds,
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
        fit_start=str(pd.to_datetime(frame["date"]).min().date()) if "date" in frame else "",
        fit_end=str(pd.to_datetime(frame["date"]).max().date()) if "date" in frame else "",
    )


def _normalised_score(values: np.ndarray, weights: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    if covariance.shape != (len(weights), len(weights)):
        covariance = np.eye(len(weights), dtype=float)
    raw = values @ weights
    variance = float(weights @ covariance @ weights)
    return raw / max(np.sqrt(max(variance, 0.0)), 1e-8)


def _positions(score: np.ndarray) -> np.ndarray:
    """A bounded long-only map used consistently by all candidates."""
    return np.clip(np.maximum(score - 0.25, 0.0) / (1.0 + np.maximum(score - 0.25, 0.0)), 0.0, 1.0)


def _objective(
    score: np.ndarray,
    returns: np.ndarray,
    *,
    commission_bps: float,
    slippage_bps: float,
    lambda_drawdown: float,
    lambda_turnover: float,
    lambda_cost: float,
    lambda_complexity: float,
    weights: np.ndarray,
) -> tuple[float, dict[str, float]]:
    positions = _positions(score)
    turnover = np.abs(np.diff(np.r_[0.0, positions]))
    costs = turnover * (commission_bps + slippage_bps) / 10000.0
    strategy = positions * returns - costs
    equity = np.cumprod(1.0 + np.nan_to_num(strategy, nan=0.0))
    running_max = np.maximum.accumulate(equity)
    drawdown = equity / np.maximum(running_max, 1e-12) - 1.0
    finite = strategy[np.isfinite(strategy)]
    volatility = float(np.std(finite, ddof=1)) if len(finite) > 1 else 0.0
    sharpe = float(np.mean(finite) / volatility * np.sqrt(252.0)) if volatility > 1e-12 else 0.0
    metrics = {
        "sharpe": sharpe,
        "max_drawdown": float(np.min(drawdown)) if len(drawdown) else 0.0,
        "turnover": float(turnover.sum()),
        "transaction_cost": float(costs.sum()),
        "cost_to_gross": float(costs.sum() / max(np.abs((positions * returns)).sum(), 1e-12)),
        "mean_position": float(np.mean(positions)) if len(positions) else 0.0,
    }
    utility = (
        sharpe
        + lambda_drawdown * metrics["max_drawdown"]
        - lambda_turnover * metrics["turnover"] / max(len(positions), 1)
        - lambda_cost * metrics["cost_to_gross"]
        - lambda_complexity * float(np.abs(weights).sum())
    )
    return float(utility), metrics


def _project_weights(weights: np.ndarray, config: WeightResearchConfig) -> np.ndarray:
    values = np.asarray(weights, dtype=float).copy()
    for index, factor in enumerate(config.factors):
        direction = config.directions[factor]
        values[index] = direction * min(abs(values[index]), config.factor_budget)
    for family, budget in config.family_budgets.items():
        indexes = [i for i, factor in enumerate(config.factors) if config.family_by_factor[factor] == family]
        total = float(np.abs(values[indexes]).sum())
        if total > budget:
            values[indexes] *= budget / total
    return values


def fit_candidate(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    config: WeightResearchConfig,
    *,
    transform: TrainTransform,
    seed: int,
    method: str,
    candidate_count: int = 256,
) -> dict[str, object]:
    """Select weights on train and score them once on validation."""
    rng = np.random.default_rng(seed)
    names = config.factors
    covariance = np.asarray(transform.covariance, dtype=float)
    train_values = transform.transform(train, names).fillna(0.0).to_numpy(dtype=float)
    validation_values = transform.transform(validation, names).fillna(0.0).to_numpy(dtype=float)
    train_returns = pd.to_numeric(train["future_return"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    validation_returns = pd.to_numeric(validation["future_return"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    methods = {"random", "coordinate"}
    if method not in methods:
        raise ValueError(f"unknown optimisation method: {method}")
    candidates: list[np.ndarray] = []
    if method == "coordinate":
        for index in range(len(names)):
            for value in (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0):
                candidate = np.zeros(len(names), dtype=float)
                candidate[index] = value
                candidates.append(_project_weights(candidate, config))
    candidates.extend(
        _project_weights(rng.normal(0.0, 1.0, len(names)), config)
        for _ in range(max(candidate_count - len(candidates), 1))
    )
    best: tuple[float, np.ndarray, dict[str, float]] | None = None
    for candidate in candidates:
        score = _normalised_score(train_values, candidate, covariance)
        utility, metrics = _objective(
            score,
            train_returns,
            commission_bps=config.commission_bps,
            slippage_bps=config.slippage_bps,
            lambda_drawdown=config.lambda_drawdown,
            lambda_turnover=config.lambda_turnover,
            lambda_cost=config.lambda_cost,
            lambda_complexity=config.lambda_complexity,
            weights=candidate,
        )
        if best is None or utility > best[0]:
            best = (utility, candidate, metrics)
    assert best is not None
    utility, weights, train_metrics = best
    validation_score = _normalised_score(validation_values, weights, covariance)
    validation_utility, validation_metrics = _objective(
        validation_score,
        validation_returns,
        commission_bps=config.commission_bps,
        slippage_bps=config.slippage_bps,
        lambda_drawdown=config.lambda_drawdown,
        lambda_turnover=config.lambda_turnover,
        lambda_cost=config.lambda_cost,
        lambda_complexity=config.lambda_complexity,
        weights=weights,
    )
    return {
        "method": method,
        "seed": int(seed),
        "weights": {factor: float(value) for factor, value in zip(names, weights)},
        "train_utility": float(utility),
        "validation_utility": float(validation_utility),
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "transform": transform.as_dict(),
    }


def evaluate_fixed_candidate(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    config: WeightResearchConfig,
    *,
    transform: TrainTransform,
    weights: Mapping[str, float],
) -> dict[str, object]:
    """Evaluate frozen main/interaction weights without refitting statistics."""
    names = tuple(config.factors)
    base_covariance = np.asarray(transform.covariance, dtype=float)
    base_names = tuple(factor for factor in names if "_x_" not in factor)
    ordered_names = tuple(weights)
    missing_weights = set(names) - set(ordered_names)
    if missing_weights:
        raise ValueError(f"weights missing configured factors: {sorted(missing_weights)}")
    ordered_weights = np.asarray([weights[name] for name in ordered_names], dtype=float)
    def design(frame: pd.DataFrame) -> np.ndarray:
        base = transform.transform(frame, base_names).fillna(0.0)
        columns = [base[factor].to_numpy(dtype=float) for factor in base_names]
        for factor in ordered_names:
            if "_x_" not in factor:
                continue
            left, right = factor.split("_x_", 1)
            if left not in base or right not in base:
                raise ValueError(f"interaction references unknown factor: {factor}")
            if factor in frame.columns:
                interaction = pd.to_numeric(frame[factor], errors="coerce").fillna(0.0)
            else:
                interaction = base[left] * base[right]
            columns.append(interaction.to_numpy(dtype=float))
        return np.column_stack(columns)

    train_design = design(train)
    validation_design = design(validation)
    if len(ordered_names) != len(base_names):
        covariance = pd.DataFrame(train_design).cov().fillna(0.0).to_numpy(dtype=float)
        covariance = covariance + np.eye(len(ordered_names), dtype=float) * 1e-8
    else:
        covariance = base_covariance
    train_score = _normalised_score(train_design, ordered_weights, covariance)
    validation_score = _normalised_score(validation_design, ordered_weights, covariance)
    train_returns = pd.to_numeric(train["future_return"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    validation_returns = pd.to_numeric(validation["future_return"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    train_utility, train_metrics = _objective(
        train_score, train_returns,
        commission_bps=config.commission_bps, slippage_bps=config.slippage_bps,
        lambda_drawdown=config.lambda_drawdown, lambda_turnover=config.lambda_turnover,
        lambda_cost=config.lambda_cost, lambda_complexity=config.lambda_complexity,
        weights=ordered_weights,
    )
    validation_utility, validation_metrics = _objective(
        validation_score, validation_returns,
        commission_bps=config.commission_bps, slippage_bps=config.slippage_bps,
        lambda_drawdown=config.lambda_drawdown, lambda_turnover=config.lambda_turnover,
        lambda_cost=config.lambda_cost, lambda_complexity=config.lambda_complexity,
        weights=ordered_weights,
    )
    return {
        "weights": {key: float(value) for key, value in weights.items()},
        "train_utility": train_utility,
        "validation_utility": validation_utility,
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "transform": transform.as_dict(),
    }


def centred_interaction(
    frame: pd.DataFrame,
    left: str,
    right: str,
    transform: TrainTransform,
) -> pd.Series:
    """Build an interaction from train-fitted centered/scaled main effects."""
    values = transform.transform(frame, (left, right)).fillna(0.0)
    return (values[left] * values[right]).rename(f"{left}_x_{right}")


def bootstrap_weight_intervals(
    weight_paths: pd.DataFrame,
    *,
    samples: int,
    block_length: int,
    seed: int,
) -> pd.DataFrame:
    """Date-cluster/block bootstrap confidence intervals for each weight."""
    if weight_paths.empty:
        return pd.DataFrame(columns=["factor", "mean", "lower_025", "upper_975", "observations"])
    factors = [column for column in weight_paths.columns if column not in {"fold_id", "method", "seed"}]
    rng = np.random.default_rng(seed)
    values = weight_paths.loc[:, factors].to_numpy(dtype=float)
    paths = np.empty((samples, len(factors)), dtype=float)
    block = max(1, min(block_length, len(values)))
    for sample in range(samples):
        indexes: list[int] = []
        while len(indexes) < len(values):
            start = int(rng.integers(0, len(values)))
            indexes.extend((start + offset) % len(values) for offset in range(block))
        paths[sample] = values[np.asarray(indexes[: len(values)])].mean(axis=0)
    return pd.DataFrame(
        {
            "factor": factors,
            "mean": values.mean(axis=0),
            "lower_025": np.quantile(paths, 0.025, axis=0),
            "upper_975": np.quantile(paths, 0.975, axis=0),
            "observations": len(values),
        }
    )


def stability_summary(weight_paths: pd.DataFrame, config: WeightResearchConfig) -> pd.DataFrame:
    """Summarise sign/selection/rank stability across folds and seeds."""
    if weight_paths.empty:
        return pd.DataFrame()
    factors = list(config.factors)
    rows: list[dict[str, object]] = []
    for factor in factors:
        values = pd.to_numeric(weight_paths[factor], errors="coerce").dropna()
        nonzero = values[values.abs() > 1e-8]
        rows.append(
            {
                "factor": factor,
                "observations": int(len(values)),
                "sign_stability": float(max((nonzero > 0).mean(), (nonzero < 0).mean())) if len(nonzero) else 0.0,
                "coefficient_mean": float(values.mean()) if len(values) else 0.0,
                "coefficient_std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                "coefficient_cv": float(values.std(ddof=1) / max(abs(values.mean()), 1e-8)) if len(values) > 1 else 0.0,
                "selection_frequency": float((values.abs() > 1e-8).mean()) if len(values) else 0.0,
                "registered_direction": int(config.directions[factor]),
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "ResearchFold",
    "TrainTransform",
    "WeightResearchConfig",
    "bootstrap_weight_intervals",
    "centred_interaction",
    "evaluate_fixed_candidate",
    "fit_candidate",
    "fit_train_transform",
    "stability_summary",
]
