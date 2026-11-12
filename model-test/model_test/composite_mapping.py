"""Train-only score transforms and interpretable long-only position maps."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

import numpy as np
import pandas as pd


MapName = Literal["dead_zone_softsign", "quantile"]


@dataclass(frozen=True)
class ScoreTransform:
    """Robust score standardisation fitted on a training window only."""

    center: float
    scale: float
    lower: float
    upper: float
    version: str = "robust_clip_v1"

    @classmethod
    def fit(cls, score: pd.Series, *, lower_q: float = 0.01, upper_q: float = 0.99) -> "ScoreTransform":
        values = pd.to_numeric(score, errors="coerce").to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if values.size == 0:
            raise ValueError("cannot fit score transform on empty/non-finite scores")
        if not 0.0 <= lower_q < upper_q <= 1.0:
            raise ValueError("quantile bounds must satisfy 0 <= lower < upper <= 1")
        center = float(np.median(values))
        mad = float(np.median(np.abs(values - center)))
        scale = max(1.4826 * mad, float(np.std(values)), 1e-8)
        lower, upper = np.quantile(values, [lower_q, upper_q])
        return cls(center=center, scale=scale, lower=float(lower), upper=float(upper))

    def transform(self, score: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
        values = np.asarray(score, dtype=float)
        clipped = np.clip(values, self.lower, self.upper)
        result = (clipped - self.center) / self.scale
        if isinstance(score, pd.Series):
            return pd.Series(result, index=score.index, name=score.name)
        return result

    def as_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass(frozen=True)
class PositionMap:
    """A monotone, bounded map from transformed score to long-only target."""

    name: MapName = "dead_zone_softsign"
    p_max: float = 1.0
    threshold: float = 0.25
    scale: float = 1.0
    quantiles: tuple[float, ...] = (0.0, 0.35, 0.60, 0.80, 1.0)
    positions: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75, 1.0)

    def __post_init__(self) -> None:
        if self.name not in ("dead_zone_softsign", "quantile"):
            raise ValueError(f"unknown position map: {self.name}")
        if not 0.0 < self.p_max <= 1.0:
            raise ValueError("p_max must be in (0, 1]")
        if self.threshold < 0.0 or self.scale <= 0.0:
            raise ValueError("threshold must be non-negative and scale positive")
        if self.name == "quantile":
            if len(self.quantiles) != len(self.positions) or len(self.quantiles) < 2:
                raise ValueError("quantile map requires matching breakpoints")
            if any(a >= b for a, b in zip(self.quantiles, self.quantiles[1:])):
                raise ValueError("quantiles must be strictly increasing")

    def transform(self, score: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
        values = np.asarray(score, dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("position map input must be finite")
        if self.name == "quantile":
            result = np.interp(values, self.quantiles, self.positions)
        else:
            positive = np.maximum(values - self.threshold, 0.0)
            result = self.p_max * positive / (self.scale + positive)
        result = np.clip(result, 0.0, self.p_max)
        if isinstance(score, pd.Series):
            return pd.Series(result, index=score.index, name=score.name)
        return result

    def diagnostics(self, raw_score: pd.Series, position: pd.Series) -> dict[str, float]:
        values = pd.to_numeric(raw_score, errors="coerce")
        positions = pd.to_numeric(position, errors="coerce")
        return {
            "score_min": float(values.min()),
            "score_median": float(values.median()),
            "score_max": float(values.max()),
            "near_zero_position_rate": float((positions <= 0.01).mean()),
            "near_max_position_rate": float((positions >= self.p_max - 0.01).mean()),
            "mean_exposure": float(positions.mean()),
            "median_exposure": float(positions.median()),
            "position_unique_count": float(positions.nunique()),
        }


__all__ = ["MapName", "PositionMap", "ScoreTransform"]
