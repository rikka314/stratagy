"""Composite-centric, direction-preserving advisory overlay.

This module is intentionally independent from the production strategy path. The
composite signal owns direction; registered advisory roles can only reduce its
long-only exposure or leave it unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from core.expert_pool_v2 import ExpertPoolV2


POLICY_VERSION = "composite_advisory_phase1_v1"
POLICIES = (
    "composite_only",
    "composite_plus_trend",
    "composite_plus_reversion",
    "composite_plus_macro_cap",
    "composite_plus_relative_strength",
    "composite_plus_all_advisories",
    "cash",
)


@dataclass(frozen=True)
class AdvisoryConfig:
    """Frozen Phase 0 bounds and trigger thresholds."""

    trend_trigger: float = 0.50
    trend_conflict_multiplier: float = 0.80
    reversion_trigger: float = 0.60
    reversion_multiplier: float = 0.75
    relative_trigger: float = 0.25
    relative_conflict_multiplier: float = 0.80
    macro_cap_floor: float = 0.25
    max_single_decision_change: float = 0.25
    max_position: float = 1.0


@dataclass(frozen=True)
class AdvisoryDecision:
    """Immutable, reconstructable decision result for one date and symbol."""

    composite_score: float
    composite_base_position: float
    trend_confirmation: float
    reversion_warning: float
    relative_strength_confirmation: float
    macro_risk_level: float
    macro_risk_cap: float
    advisory_multiplier: float
    final_position: float
    fallback_reason: str | None
    policy_version: str = POLICY_VERSION
    fallback_used: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return float(np.clip(value, lower, upper))


class CompositeAdvisory:
    """Apply frozen, role-specific advisory rules to one factor row."""

    def __init__(
        self,
        *,
        pool: ExpertPoolV2 | None = None,
        config: AdvisoryConfig | None = None,
    ) -> None:
        self.pool = pool or ExpertPoolV2()
        self.config = config or AdvisoryConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        values = self.config.__dict__.values()
        if not all(np.isfinite(float(value)) for value in values):
            raise ValueError("advisory config must contain finite numeric values")
        if not 0 < self.config.trend_trigger <= 1:
            raise ValueError("trend_trigger must be in (0, 1]")
        if not 0 <= self.config.trend_conflict_multiplier <= 1:
            raise ValueError("trend_conflict_multiplier must be in [0, 1]")
        if not 0 < self.config.reversion_trigger <= 1:
            raise ValueError("reversion_trigger must be in (0, 1]")
        if not 0 <= self.config.reversion_multiplier <= 1:
            raise ValueError("reversion_multiplier must be in [0, 1]")
        if not 0 < self.config.relative_trigger <= 1:
            raise ValueError("relative_trigger must be in (0, 1]")
        if not 0 <= self.config.relative_conflict_multiplier <= 1:
            raise ValueError("relative_conflict_multiplier must be in [0, 1]")
        if not 0 <= self.config.macro_cap_floor <= 1:
            raise ValueError("macro_cap_floor must be in [0, 1]")
        if not 0 <= self.config.max_single_decision_change <= 1:
            raise ValueError("max_single_decision_change must be in [0, 1]")
        if not 0 <= self.config.max_position <= 1:
            raise ValueError("max_position must be in [0, 1]")

    @staticmethod
    def _fallback(reason: str) -> AdvisoryDecision:
        return AdvisoryDecision(
            composite_score=0.0,
            composite_base_position=0.0,
            trend_confirmation=0.0,
            reversion_warning=0.0,
            relative_strength_confirmation=0.0,
            macro_risk_level=1.0,
            macro_risk_cap=0.0,
            advisory_multiplier=0.0,
            final_position=0.0,
            fallback_reason=reason,
            fallback_used=True,
        )

    def decide(
        self,
        frame: pd.DataFrame,
        *,
        policy: str = "composite_plus_all_advisories",
        previous_position: float | None = None,
    ) -> AdvisoryDecision:
        """Return one decision; invalid input fails closed to cash."""
        if policy not in POLICIES:
            raise ValueError(f"unknown advisory policy: {policy}")
        if len(frame) != 1:
            raise ValueError("decide expects exactly one factor row")
        try:
            scores = self.pool.compute_scores(frame)
            signals = self.pool.get_all_expert_signals(frame)
            composite_score = float(scores["composite_optimized"].iloc[0])
            base = float(signals["composite_optimized"].iloc[0])
            trend = _clip(float(signals["momentum_optimized"].iloc[0]) / 0.80)
            reversion = _clip(-float(signals["mean_reversion"].iloc[0]) / 0.45)
            relative = _clip(
                float(signals["volume_confirmed"].iloc[0]) / 0.50,
                -1.0,
                1.0,
            )
            macro_cap = _clip(float(signals["macro_defensive"].iloc[0]) / 0.60)
            macro_risk = 1.0 - macro_cap
        except (KeyError, TypeError, ValueError, FloatingPointError) as exc:
            return self._fallback(f"invalid_input:{type(exc).__name__}")

        multiplier = 1.0
        if policy in ("composite_plus_trend", "composite_plus_all_advisories"):
            if trend < self.config.trend_trigger:
                multiplier = min(multiplier, self.config.trend_conflict_multiplier)
        if policy in ("composite_plus_reversion", "composite_plus_all_advisories"):
            if reversion >= self.config.reversion_trigger:
                multiplier = min(multiplier, self.config.reversion_multiplier)
        if policy in ("composite_plus_relative_strength", "composite_plus_all_advisories"):
            if relative <= -self.config.relative_trigger:
                multiplier = min(multiplier, self.config.relative_conflict_multiplier)
        if policy in ("composite_plus_macro_cap", "composite_plus_all_advisories"):
            multiplier = min(multiplier, max(self.config.macro_cap_floor, macro_cap))
        if policy == "cash":
            multiplier = 0.0

        final = min(base, base * multiplier, self.config.max_position)
        if policy != "cash" and base - final > self.config.max_single_decision_change:
            final = base - self.config.max_single_decision_change
        if previous_position is not None:
            if not np.isfinite(previous_position) or not 0.0 <= previous_position <= 1.0:
                return self._fallback("invalid_previous_position")
            if policy != "cash":
                final = float(
                    np.clip(
                        final,
                        previous_position - self.config.max_single_decision_change,
                        previous_position + self.config.max_single_decision_change,
                    )
                )
        final = _clip(final, 0.0, min(base, self.config.max_position))
        return AdvisoryDecision(
            composite_score=composite_score,
            composite_base_position=base,
            trend_confirmation=trend,
            reversion_warning=reversion,
            relative_strength_confirmation=relative,
            macro_risk_level=macro_risk,
            macro_risk_cap=macro_cap,
            advisory_multiplier=float(multiplier),
            final_position=final,
            fallback_reason=None,
        )


def decide_frame(
    frame: pd.DataFrame,
    *,
    policy: str = "composite_plus_all_advisories",
    advisory: CompositeAdvisory | None = None,
) -> pd.DataFrame:
    """Evaluate a time-ordered factor frame without mutating it."""
    engine = advisory or CompositeAdvisory()
    if policy not in POLICIES:
        raise ValueError(f"unknown advisory policy: {policy}")
    if frame.empty:
        return pd.DataFrame(index=frame.index)
    try:
        scores = engine.pool.compute_scores(frame)
        signals = engine.pool.get_all_expert_signals(frame)
        result = pd.DataFrame(
            {
                "composite_score": scores["composite_optimized"],
                "composite_base_position": signals["composite_optimized"],
                "trend_confirmation": (signals["momentum_optimized"] / 0.80).clip(0.0, 1.0),
                "reversion_warning": (-signals["mean_reversion"] / 0.45).clip(0.0, 1.0),
                "relative_strength_confirmation": (signals["volume_confirmed"] / 0.50).clip(-1.0, 1.0),
                "macro_risk_cap": (signals["macro_defensive"] / 0.60).clip(0.0, 1.0),
            },
            index=frame.index,
        )
        result["macro_risk_level"] = 1.0 - result["macro_risk_cap"]
    except (KeyError, TypeError, ValueError, FloatingPointError) as exc:
        fallback = CompositeAdvisory._fallback(f"invalid_input:{type(exc).__name__}").as_dict()
        return pd.DataFrame([fallback] * len(frame), index=frame.index)

    config = engine.config
    multiplier = pd.Series(1.0, index=frame.index)
    if policy in ("composite_plus_trend", "composite_plus_all_advisories"):
        multiplier = multiplier.where(
            result["trend_confirmation"] >= config.trend_trigger,
            config.trend_conflict_multiplier,
        )
    if policy in ("composite_plus_reversion", "composite_plus_all_advisories"):
        multiplier = multiplier.where(
            result["reversion_warning"] < config.reversion_trigger,
            np.minimum(multiplier, config.reversion_multiplier),
        )
    if policy in ("composite_plus_relative_strength", "composite_plus_all_advisories"):
        multiplier = multiplier.where(
            result["relative_strength_confirmation"] > -config.relative_trigger,
            np.minimum(multiplier, config.relative_conflict_multiplier),
        )
    if policy in ("composite_plus_macro_cap", "composite_plus_all_advisories"):
        multiplier = np.minimum(
            multiplier,
            np.maximum(config.macro_cap_floor, result["macro_risk_cap"]),
        )
    if policy == "cash":
        multiplier = pd.Series(0.0, index=frame.index)

    base = result["composite_base_position"].clip(0.0, config.max_position)
    final = np.minimum(base, base * multiplier)
    if policy != "cash":
        final = np.maximum(final, base - config.max_single_decision_change)
    bounded: list[float] = []
    previous: float | None = None
    base_values = base.to_numpy(dtype=float)
    for index, value in enumerate(final.to_numpy(dtype=float)):
        current = float(value)
        if previous is not None:
            current = float(
                np.clip(
                    current,
                    previous - config.max_single_decision_change,
                    previous + config.max_single_decision_change,
                )
            )
        bounded.append(float(np.clip(current, 0.0, base_values[index])))
        previous = bounded[-1]
    result["advisory_multiplier"] = multiplier
    result["final_position"] = bounded
    result["fallback_reason"] = None
    result["policy_version"] = POLICY_VERSION
    result["fallback_used"] = False
    return result


__all__ = [
    "AdvisoryConfig",
    "AdvisoryDecision",
    "CompositeAdvisory",
    "POLICIES",
    "POLICY_VERSION",
    "decide_frame",
]
