"""Tuned advisory configuration for Phase 4 re-evaluation.

This configuration adjusts trigger thresholds to reduce over-conservative behavior
while maintaining risk management effectiveness.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdvisoryConfigTuned:
    """Tuned Phase 4 advisory parameters - targeting 30-50% trigger rate."""

    # Trend confirmation: reduce from 0.50 to 0.30
    # Only trigger when trend is clearly weak (< 30% confidence)
    trend_trigger: float = 0.30
    trend_conflict_multiplier: float = 0.80

    # Mean reversion: increase from 0.60 to 0.75
    # Only trigger on strong overbought signals (> 75% confidence)
    reversion_trigger: float = 0.75
    reversion_multiplier: float = 0.75

    # Relative strength: increase from 0.25 to 0.40
    # Only trigger on significantly weak relative performance
    relative_trigger: float = 0.40
    relative_conflict_multiplier: float = 0.80

    # Macro cap: keep floor but raise implicit threshold via cap computation
    # No change needed - cap is computed dynamically
    macro_cap_floor: float = 0.25

    # Execution constraints
    max_single_decision_change: float = 0.25
    max_position: float = 1.0


# Comparison with Phase 0 config
PHASE0_CONFIG = {
    'trend_trigger': 0.50,
    'reversion_trigger': 0.60,
    'relative_trigger': 0.25,
}

TUNED_CONFIG = {
    'trend_trigger': 0.30,        # -40% (stricter)
    'reversion_trigger': 0.75,    # +25% (more lenient)
    'relative_trigger': 0.40,     # +60% (stricter)
}

RATIONALE = """
Tuning Rationale:

1. trend_trigger: 0.50 → 0.30
   - Current: triggers when trend < 50% (too easy)
   - Tuned: triggers when trend < 30% (weak trend only)
   - Expected: reduce trigger rate from 100% to ~30-40%

2. reversion_trigger: 0.60 → 0.75
   - Current: triggers when overbought > 60% (moderate)
   - Tuned: triggers when overbought > 75% (extreme only)
   - Expected: reduce trigger rate from 82-97% to ~40-50%

3. relative_trigger: 0.25 → 0.40
   - Current: triggers when relative strength <= -25% (easy)
   - Tuned: triggers when relative strength <= -40% (clearly weak)
   - Expected: reduce trigger rate from 100% to ~30-40%

4. macro_cap_floor: 0.25 (unchanged)
   - Macro cap is computed dynamically from risk level
   - Floor ensures minimum 25% exposure even in extreme risk
   - trigger_rate=100% is expected (always applies cap)

Target Outcome:
- trend, relative_strength: 30-40% trigger rate
- reversion: 40-50% trigger rate
- macro_cap: 100% trigger rate (by design)
- all_advisories: 40-60% trigger rate (combination effect)
"""
