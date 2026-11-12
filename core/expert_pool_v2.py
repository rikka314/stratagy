"""异构专家池：按互斥风险职责计算可审计信号。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


PHASE25_WEIGHTS: Mapping[str, float] = {
    "mom_short_z": 1.1927024077349668,
    "rsi_z": 0.6774335748746589,
    "macd_z": -1.848279896441191,
    "vix_level": 0.4923060643659716,
    "volume_ratio_rank": 0.7149782039599426,
}
INTERACTION_WEIGHT = -0.5


@dataclass(frozen=True)
class ExpertDefinition:
    """一个专家的互斥风险职责和执行 contract。"""

    expert_id: str
    factors: tuple[str, ...]
    role: str
    logic: str
    position_semantics: str
    rebalance_days: int
    risk_budget: float


EXPERT_DEFINITIONS: tuple[ExpertDefinition, ...] = (
    ExpertDefinition(
        "momentum_optimized",
        ("mom_short_z", "mom_long_z", "macd_z"),
        "trend",
        "long trend exposure from short/long momentum; no reversal or macro inputs",
        "long_only",
        5,
        0.80,
    ),
    ExpertDefinition(
        "mean_reversion",
        ("rsi_z", "bb_position_rank", "price_position_rank"),
        "reversion",
        "signed contrarian exposure; oversold is long and overbought is short",
        "market_neutral_signed",
        2,
        0.45,
    ),
    ExpertDefinition(
        "macro_defensive",
        ("vix_level", "vol_z", "drawdown_rank"),
        "volatility",
        "volatility-targeted exposure reduction; no directional alpha claim",
        "long_only_risk_scaled",
        1,
        0.60,
    ),
    ExpertDefinition(
        "volume_confirmed",
        ("rel_strength_spy", "mom_short_z"),
        "relative_strength",
        "cross-sectional signed relative-strength exposure, held on a slower cadence",
        "market_neutral_signed",
        5,
        0.50,
    ),
    ExpertDefinition(
        "composite_optimized",
        tuple(PHASE25_WEIGHTS),
        "reference_composite",
        "Phase 2.5 long-only reference retained for comparison, not an orthogonal role",
        "long_only_reference",
        1,
        1.00,
    ),
    ExpertDefinition(
        "cash",
        (),
        "baseline",
        "zero exposure",
        "cash",
        1,
        0.00,
    ),
)


class ExpertPoolV2:
    """Compute role-specific target positions without mutating input.

    ``score_transform`` is deliberately injected by research callers.  When it
    is absent, the historical mapping is retained for backwards compatibility;
    Phase 0/1 replay must provide a train-window-fitted transform.
    """

    def __init__(
        self,
        *,
        temperature: float = 1.0,
        score_transform: object | None = None,
    ) -> None:
        if not np.isfinite(temperature) or temperature <= 0:
            raise ValueError("temperature must be finite and positive")
        self.temperature = float(temperature)
        self.score_transform = score_transform

    @staticmethod
    def definitions() -> tuple[ExpertDefinition, ...]:
        return EXPERT_DEFINITIONS

    @staticmethod
    def required_columns() -> tuple[str, ...]:
        columns = {
            "mom_short_z",
            "mom_long_z",
            "macd_z",
            "rsi_z",
            "bb_position_rank",
            "price_position_rank",
            "vol_z",
            "drawdown_rank",
            "vix_level",
            "rel_strength_spy",
            "volume_ratio_rank",
        }
        return tuple(sorted(columns))

    def _validated_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        missing = [column for column in self.required_columns() if column not in frame.columns]
        if missing:
            raise ValueError(f"missing factor columns: {', '.join(missing)}")
        result = frame.loc[:, list(self.required_columns())].apply(pd.to_numeric, errors="coerce")
        if not np.isfinite(result.to_numpy(dtype=float)).all():
            raise ValueError("factor columns must contain finite numeric values")
        return result

    def _bounded_signed(self, score: pd.Series, budget: float) -> pd.Series:
        values = budget * np.tanh(score.to_numpy(dtype=float) / self.temperature)
        return pd.Series(values, index=score.index, name=score.name)

    def _bounded_long(self, score: pd.Series, budget: float) -> pd.Series:
        transformed = score
        if self.score_transform is not None:
            transform = getattr(self.score_transform, "transform", None)
            if not callable(transform):
                raise ValueError("score_transform must expose transform(score)")
            transformed = transform(score)
        values = budget * np.clip(
            np.tanh(np.asarray(transformed, dtype=float) / self.temperature), 0.0, 1.0
        )
        return pd.Series(values, index=score.index, name=score.name)

    @staticmethod
    def _macro_exposure(factors: pd.DataFrame, budget: float) -> pd.Series:
        vix_risk = (factors["vix_level"] / 40.0).clip(0.0, 1.0)
        volatility_risk = np.clip(np.tanh(factors["vol_z"]), 0.0, 1.0)
        drawdown_risk = (1.0 - factors["drawdown_rank"]).clip(0.0, 1.0)
        risk = (vix_risk + volatility_risk + drawdown_risk) / 3.0
        exposure = budget * (1.0 - risk)
        return exposure.rename("macro_defensive")

    def compute_scores(
        self, frame: pd.DataFrame, *, relative_rank: pd.Series | None = None
    ) -> dict[str, pd.Series]:
        """Return role-specific raw scores, preserving the input index."""
        factors = self._validated_frame(frame)
        if relative_rank is None:
            relative_rank = factors["rel_strength_spy"].rank(pct=True)
        relative_rank = pd.to_numeric(relative_rank, errors="coerce").reindex(factors.index)
        if relative_rank.isna().any() or not np.isfinite(relative_rank.to_numpy()).all():
            raise ValueError("relative_rank must be finite and aligned")
        momentum = factors["mom_short_z"]
        scores = {
            "momentum_optimized": (
                0.50 * factors["mom_short_z"]
                + 0.30 * factors["mom_long_z"]
                - 0.20 * factors["macd_z"]
            ),
            "mean_reversion": -(
                0.55 * factors["rsi_z"]
                + 0.25 * (factors["bb_position_rank"] - 0.5)
                + 0.20 * (factors["price_position_rank"] - 0.5)
            ),
            "macro_defensive": -factors["vix_level"] - factors["vol_z"],
            "volume_confirmed": (
                (relative_rank - 0.5) * 4.0
                + 0.5 * factors["mom_short_z"]
            ),
            "composite_optimized": sum(
                weight * factors[name] for name, weight in PHASE25_WEIGHTS.items()
            )
            + INTERACTION_WEIGHT * factors["volume_ratio_rank"] * momentum,
            "cash": pd.Series(0.0, index=factors.index),
        }
        return {name: series.rename(name) for name, series in scores.items()}

    def get_all_expert_signals(
        self, frame: pd.DataFrame, *, relative_rank: pd.Series | None = None
    ) -> dict[str, pd.Series]:
        """Return role-specific positions, including signed market-neutral roles."""
        factors = self._validated_frame(frame)
        scores = self.compute_scores(frame, relative_rank=relative_rank)
        budgets = {item.expert_id: item.risk_budget for item in self.definitions()}
        signals = {
            "momentum_optimized": self._bounded_long(
                scores["momentum_optimized"], budgets["momentum_optimized"]
            ),
            "mean_reversion": self._bounded_signed(
                scores["mean_reversion"], budgets["mean_reversion"]
            ),
            "macro_defensive": self._macro_exposure(
                factors, budgets["macro_defensive"]
            ),
            "volume_confirmed": self._bounded_signed(
                scores["volume_confirmed"], budgets["volume_confirmed"]
            ),
            "composite_optimized": self._bounded_long(
                scores["composite_optimized"], budgets["composite_optimized"]
            ),
            "cash": pd.Series(0.0, index=factors.index, name="cash"),
        }
        return signals

    def metadata(self) -> list[dict[str, object]]:
        return [
            {
                "expert_id": item.expert_id,
                "factors": list(item.factors),
                "role": item.role,
                "logic": item.logic,
                "position_semantics": item.position_semantics,
                "rebalance_days": item.rebalance_days,
                "risk_budget": item.risk_budget,
            }
            for item in EXPERT_DEFINITIONS
        ]


__all__ = [
    "ExpertPoolV2",
    "ExpertDefinition",
    "EXPERT_DEFINITIONS",
    "PHASE25_WEIGHTS",
    "INTERACTION_WEIGHT",
]
