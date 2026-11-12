"""CN_A Composite Advisory: long-only, direction-preserving risk overlay.

This module implements CN_A-specific advisory rules that:
- Only reduce Composite exposure, never increase or reverse
- Use CN_A market-native factors (not US SPY/VIX)
- Follow long-only/cash semantics (no short positions)
- Provide full audit trail with fallback reasons
- Support single-item ablation testing

Design principles:
- Composite owns direction and base position
- Advisory can only maintain or reduce exposure
- All decisions are immutable and reconstructable
- Missing context triggers explicit fallback to cash
- No cross-market weight sharing
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd


POLICY_VERSION = "cn_a_advisory_phase5_v1"

POLICIES = (
    "composite_only",
    "composite_plus_trend",
    "composite_plus_reversion",
    "composite_plus_relative_strength",
    "composite_plus_macro_cap",
    "composite_plus_all_advisories",
    "cash",
)


@dataclass(frozen=True)
class CNAdvisoryConfig:
    """CN_A advisory configuration (immutable)."""

    # Trend confirmation thresholds
    trend_trigger: float = 0.50  # Require trend > 0.5 to maintain full position
    trend_conflict_multiplier: float = 0.75  # Reduce to 75% if trend weak

    # Mean reversion warning thresholds
    reversion_trigger: float = 0.65  # RSI/BB overbought threshold
    reversion_multiplier: float = 0.70  # Reduce to 70% if overbought

    # Relative strength confirmation thresholds
    relative_trigger: float = 0.30  # Minimum relative strength vs benchmark
    relative_conflict_multiplier: float = 0.75  # Reduce if underperforming

    # Macro defensive cap thresholds
    macro_cap_floor: float = 0.25  # Minimum exposure in high-risk regime
    macro_cap_ceiling: float = 1.0  # Maximum exposure cap

    # Position change limits
    max_single_decision_change: float = 0.25  # Max position change per decision
    max_position: float = 1.0  # Absolute position cap

    def validate(self) -> None:
        """Validate all config values are finite and in valid ranges."""
        if not all(np.isfinite(float(v)) for v in self.__dict__.values()):
            raise ValueError("All config values must be finite")
        if not 0 < self.trend_trigger <= 1:
            raise ValueError("trend_trigger must be in (0, 1]")
        if not 0 <= self.trend_conflict_multiplier <= 1:
            raise ValueError("trend_conflict_multiplier must be in [0, 1]")
        if not 0 < self.reversion_trigger <= 1:
            raise ValueError("reversion_trigger must be in (0, 1]")
        if not 0 <= self.reversion_multiplier <= 1:
            raise ValueError("reversion_multiplier must be in [0, 1]")
        if not 0 < self.relative_trigger <= 1:
            raise ValueError("relative_trigger must be in (0, 1]")
        if not 0 <= self.relative_conflict_multiplier <= 1:
            raise ValueError("relative_conflict_multiplier must be in [0, 1]")
        if not 0 <= self.macro_cap_floor <= 1:
            raise ValueError("macro_cap_floor must be in [0, 1]")
        if not 0 <= self.macro_cap_ceiling <= 1:
            raise ValueError("macro_cap_ceiling must be in [0, 1]")
        if not 0 < self.max_single_decision_change <= 1:
            raise ValueError("max_single_decision_change must be in (0, 1]")
        if not 0 <= self.max_position <= 1:
            raise ValueError("max_position must be in [0, 1]")


@dataclass(frozen=True)
class CNCompositeAdvisoryDecision:
    """CN_A Composite advisory decision (immutable, reconstructable)."""

    date: pd.Timestamp
    symbol: str
    market: Literal["CN_A"]
    composite_score: float
    composite_base_position: float
    trend_confirmation: float  # [0, 1]: higher = stronger trend
    reversion_warning: float  # [0, 1]: higher = more overbought
    relative_strength_confirmation: float  # [-1, 1]: vs market benchmark
    macro_risk_level: float  # [0, 1]: higher = more risky
    macro_risk_cap: float  # [0, 1]: cap applied to position
    advisory_multiplier: float  # [0, 1]: final multiplier applied
    final_position: float  # [0, risk_budget]: final position after advisory
    fallback_used: bool
    fallback_reason: str | None
    reason_codes: tuple[str, ...]  # List of triggered advisory rules
    policy_version: str = POLICY_VERSION

    def as_dict(self) -> dict[str, object]:
        """Convert to dictionary for serialization."""
        return asdict(self)


def _normalize_factor(
    value: float,
    *,
    scale: float = 1.0,
    lower: float = 0.0,
    upper: float = 1.0,
) -> float:
    """Normalize and clip factor value to target range."""
    if not np.isfinite(value):
        return 0.0
    normalized = value / scale if scale != 0 else 0.0
    return float(np.clip(normalized, lower, upper))


class CNCompositeAdvisory:
    """CN_A Composite advisory engine with long-only semantics."""

    def __init__(self, config: CNAdvisoryConfig | None = None) -> None:
        self.config = config or CNAdvisoryConfig()
        self.config.validate()

    @staticmethod
    def _fallback(reason: str) -> CNCompositeAdvisoryDecision:
        """Return cash fallback decision with explicit reason."""
        return CNCompositeAdvisoryDecision(
            date=pd.NaT,
            symbol="",
            market="CN_A",
            composite_score=0.0,
            composite_base_position=0.0,
            trend_confirmation=0.0,
            reversion_warning=0.0,
            relative_strength_confirmation=0.0,
            macro_risk_level=1.0,
            macro_risk_cap=0.0,
            advisory_multiplier=0.0,
            final_position=0.0,
            fallback_used=True,
            fallback_reason=reason,
            reason_codes=("fallback",),
        )

    def decide(
        self,
        row: pd.Series,
        *,
        policy: str = "composite_plus_all_advisories",
        previous_position: float | None = None,
    ) -> CNCompositeAdvisoryDecision:
        """Make one advisory decision for a single factor row.

        Args:
            row: Factor row with composite_score, composite_base_position, and advisory factors
            policy: Advisory policy to apply
            previous_position: Previous position for change limiting

        Returns:
            Immutable advisory decision
        """
        if policy not in POLICIES:
            raise ValueError(f"Unknown policy: {policy}")

        # Extract required fields with fallback
        try:
            # Check required fields exist
            if "composite_base_position" not in row:
                return self._fallback("missing_composite_base_position")

            date = row.get("date", pd.NaT)
            symbol = row.get("symbol", "")
            composite_score = float(row.get("composite_score", 0.0))
            base_position = float(row["composite_base_position"])

            # Extract advisory factors
            trend = _normalize_factor(
                float(row.get("mom_long_z", 0.0)),
                scale=2.0,
                lower=0.0,
                upper=1.0,
            )
            reversion = _normalize_factor(
                float(row.get("rsi_z", 0.0)),
                scale=2.0,
                lower=0.0,
                upper=1.0,
            )
            relative = _normalize_factor(
                float(row.get("rel_strength_market", 0.0)),
                scale=0.20,
                lower=-1.0,
                upper=1.0,
            )
            macro_vol = float(row.get("market_vol_level", 0.0))
            macro_risk_cap = _normalize_factor(
                1.0 - macro_vol / 0.30 if macro_vol > 0 else 1.0,
                scale=1.0,
                lower=0.0,
                upper=1.0,
            )
            macro_risk = 1.0 - macro_risk_cap

            if not np.isfinite(base_position) or base_position < 0:
                return self._fallback("invalid_base_position")

        except (KeyError, TypeError, ValueError) as exc:
            return self._fallback(f"invalid_input:{type(exc).__name__}")

        # Apply advisory rules based on policy
        multiplier = 1.0
        reason_codes: list[str] = []

        if policy == "cash":
            multiplier = 0.0
            reason_codes.append("cash_policy")
        elif base_position == 0.0:
            # Composite is 0: advisory cannot open position
            multiplier = 0.0
            reason_codes.append("composite_zero")
        else:
            # Apply individual advisory rules
            if policy in ("composite_plus_trend", "composite_plus_all_advisories"):
                if trend < self.config.trend_trigger:
                    multiplier = min(multiplier, self.config.trend_conflict_multiplier)
                    reason_codes.append("trend_weak")

            if policy in ("composite_plus_reversion", "composite_plus_all_advisories"):
                if reversion >= self.config.reversion_trigger:
                    multiplier = min(multiplier, self.config.reversion_multiplier)
                    reason_codes.append("reversion_overbought")

            if policy in (
                "composite_plus_relative_strength",
                "composite_plus_all_advisories",
            ):
                if relative <= -self.config.relative_trigger:
                    multiplier = min(multiplier, self.config.relative_conflict_multiplier)
                    reason_codes.append("relative_weak")

            if policy in ("composite_plus_macro_cap", "composite_plus_all_advisories"):
                macro_multiplier = max(self.config.macro_cap_floor, macro_risk_cap)
                multiplier = min(multiplier, macro_multiplier)
                if macro_risk_cap < 1.0:
                    reason_codes.append("macro_risk_cap")

        # Compute final position with constraints
        final = base_position * multiplier
        final = min(final, self.config.max_position)

        # Limit single-decision change from base
        if policy != "cash":
            if base_position - final > self.config.max_single_decision_change:
                final = base_position - self.config.max_single_decision_change
                reason_codes.append("decision_change_limit")

        # Limit change from previous position
        if previous_position is not None:
            if not np.isfinite(previous_position) or not 0.0 <= previous_position <= 1.0:
                return self._fallback("invalid_previous_position")
            if policy != "cash":
                prev_lower = previous_position - self.config.max_single_decision_change
                prev_upper = previous_position + self.config.max_single_decision_change
                if final < prev_lower or final > prev_upper:
                    final = float(np.clip(final, prev_lower, prev_upper))
                    reason_codes.append("position_change_limit")

        # Final bounds: must not exceed base and must be in [0, max_position]
        final = float(np.clip(final, 0.0, min(base_position, self.config.max_position)))

        if not reason_codes:
            reason_codes.append("no_reduction")

        return CNCompositeAdvisoryDecision(
            date=date,
            symbol=symbol,
            market="CN_A",
            composite_score=composite_score,
            composite_base_position=base_position,
            trend_confirmation=trend,
            reversion_warning=reversion,
            relative_strength_confirmation=relative,
            macro_risk_level=macro_risk,
            macro_risk_cap=macro_risk_cap,
            advisory_multiplier=multiplier,
            final_position=final,
            fallback_used=False,
            fallback_reason=None,
            reason_codes=tuple(reason_codes),
        )


def decide_frame(
    frame: pd.DataFrame,
    *,
    policy: str = "composite_plus_all_advisories",
    config: CNAdvisoryConfig | None = None,
) -> pd.DataFrame:
    """Apply advisory policy to entire factor frame without mutation.

    Args:
        frame: Factor DataFrame with required columns
        policy: Advisory policy to apply
        config: Advisory configuration

    Returns:
        DataFrame with advisory decisions (one row per input row)
    """
    if frame.empty:
        return pd.DataFrame(columns=CNCompositeAdvisoryDecision.__dataclass_fields__.keys())

    engine = CNCompositeAdvisory(config=config)
    decisions = []
    previous_position: float | None = None

    for _, row in frame.iterrows():
        decision = engine.decide(row, policy=policy, previous_position=previous_position)
        decisions.append(decision.as_dict())
        previous_position = decision.final_position

    return pd.DataFrame(decisions)


__all__ = [
    "CNAdvisoryConfig",
    "CNCompositeAdvisoryDecision",
    "CNCompositeAdvisory",
    "POLICIES",
    "POLICY_VERSION",
    "decide_frame",
]
