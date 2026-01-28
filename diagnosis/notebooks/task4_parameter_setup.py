"""
Task 4.1 - Key parameter identification and scan ranges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ParameterGroup:
    name: str
    params: List[str]


# Tiered parameter importance
TIER_1 = ParameterGroup(
    name="tier_1_high_impact",
    params=[
        "entry_threshold",
        "exit_threshold",
        "adx_threshold",
        "stop_loss_mult",
        "take_profit_mult",
    ],
)

TIER_2 = ParameterGroup(
    name="tier_2_mid_impact",
    params=[
        "ema_fast",
        "ema_slow",
        "rsi_lower",
        "rsi_upper",
    ],
)

TIER_3 = ParameterGroup(
    name="tier_3_low_impact",
    params=[
        "rsi_period",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "adx_period",
        "atr_period",
        "momentum_short",
        "momentum_long",
        "score_lookback",
    ],
)


# Default parameters aligned with app.py sidebar defaults
BASE_PARAMS: Dict[str, float] = {
    "ema_fast": 20,
    "ema_slow": 60,
    "adx_threshold": 20,
    "adx_period": 14,
    "rsi_period": 14,
    "rsi_lower": 30,
    "rsi_upper": 70,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "atr_period": 14,
    "momentum_short": 5,
    "momentum_long": 20,
    "score_lookback": 30,
    "score_mid_pct": 0.6,
    "score_high_pct": 0.8,
    "weight_mom_short": 1.0,
    "weight_mom_long": 1.0,
    "weight_macd": 1.0,
    "weight_rsi": 0.5,
    "weight_vol": 0.5,
    "entry_threshold": 0.5,
    "exit_threshold": -0.5,
    "stop_loss_mult": 2.0,
    "take_profit_mult": 4.0,
}


def frange(start: float, stop: float, step: float) -> List[float]:
    values = []
    x = start
    while x <= stop + 1e-9:
        values.append(x)
        x += step
    return values


# Scan ranges for tier-1 parameters (Task 4.2 core)
SCAN_RANGES: Dict[str, List[float]] = {
    "entry_threshold": [round(x, 1) for x in frange(-2.0, 2.0, 0.2)],
    "exit_threshold": [round(x, 1) for x in frange(-2.0, 1.0, 0.2)],
    "adx_threshold": list(range(10, 41, 5)),
    "stop_loss_mult": [round(x, 1) for x in frange(0.0, 5.0, 0.5)],
    "take_profit_mult": list(range(0, 9, 1)),
}


def all_tiers() -> List[ParameterGroup]:
    return [TIER_1, TIER_2, TIER_3]


__all__ = [
    "ParameterGroup",
    "TIER_1",
    "TIER_2",
    "TIER_3",
    "BASE_PARAMS",
    "SCAN_RANGES",
    "all_tiers",
]
