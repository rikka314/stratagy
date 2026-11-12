"""Tests for the composite-centric advisory contract."""

import numpy as np
import pandas as pd
import pytest

from core.composite_advisory import (
    POLICIES,
    AdvisoryConfig,
    CompositeAdvisory,
    decide_frame,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "mom_short_z": [1.0, -1.0],
            "mom_long_z": [0.8, -0.8],
            "macd_z": [1.0, -1.0],
            "rsi_z": [0.5, -0.5],
            "bb_position_rank": [0.8, 0.2],
            "price_position_rank": [0.7, 0.3],
            "vol_z": [0.2, 1.0],
            "drawdown_rank": [-0.1, -0.8],
            "vix_level": [20.0, 30.0],
            "rel_strength_spy": [0.8, -0.2],
            "volume_ratio_rank": [0.8, 0.2],
        },
        index=pd.Index(["a", "b"], name="row"),
    )


def test_all_registered_policies_are_available() -> None:
    assert POLICIES == (
        "composite_only",
        "composite_plus_trend",
        "composite_plus_reversion",
        "composite_plus_macro_cap",
        "composite_plus_relative_strength",
        "composite_plus_all_advisories",
        "cash",
    )


def test_overlay_never_exceeds_composite_directional_base() -> None:
    advisory = CompositeAdvisory()
    decisions = [advisory.decide(_frame().iloc[[index]]) for index in range(2)]

    assert all(0.0 <= item.final_position <= item.composite_base_position for item in decisions)
    assert all(item.advisory_multiplier <= 1.0 for item in decisions)


def test_zero_composite_does_not_create_position() -> None:
    frame = _frame().iloc[[0]].copy()
    frame.loc[:, "mom_short_z"] = -100.0
    frame.loc[:, "mom_long_z"] = -100.0
    frame.loc[:, "macd_z"] = 100.0
    frame.loc[:, "rsi_z"] = 0.0
    frame.loc[:, "bb_position_rank"] = 0.5
    frame.loc[:, "price_position_rank"] = 0.5
    frame.loc[:, "vix_level"] = 20.0
    frame.loc[:, "vol_z"] = 0.0
    frame.loc[:, "volume_ratio_rank"] = 0.5

    decision = CompositeAdvisory().decide(frame)
    assert decision.composite_base_position == 0.0
    assert decision.final_position == 0.0


def test_invalid_factor_fails_closed_with_explicit_reason() -> None:
    frame = _frame().iloc[[0]].copy()
    frame.loc[:, "vix_level"] = np.nan

    decision = CompositeAdvisory().decide(frame)

    assert decision.fallback_used is True
    assert decision.final_position == 0.0
    assert decision.fallback_reason == "invalid_input:ValueError"


def test_decide_frame_preserves_input_and_index() -> None:
    frame = _frame()
    original = frame.copy(deep=True)

    output = decide_frame(frame, policy="composite_only")

    assert frame.equals(original)
    assert output.index.equals(frame.index)
    assert set(output.columns) >= {
        "composite_score",
        "composite_base_position",
        "final_position",
        "fallback_used",
        "fallback_reason",
        "policy_version",
    }


def test_max_single_decision_change_is_enforced() -> None:
    advisory = CompositeAdvisory(
        config=AdvisoryConfig(
            macro_cap_floor=0.0,
            max_single_decision_change=0.10,
        )
    )
    frame = _frame().iloc[[0]].copy()
    frame.loc[:, "vix_level"] = 100.0
    frame.loc[:, "vol_z"] = 10.0
    decision = advisory.decide(frame, policy="composite_plus_macro_cap")

    assert decision.composite_base_position - decision.final_position <= 0.10 + 1e-12


def test_unknown_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown advisory policy"):
        CompositeAdvisory().decide(_frame().iloc[[0]], policy="winner_selection")


def test_previous_position_bound_is_enforced() -> None:
    advisory = CompositeAdvisory(
        config=AdvisoryConfig(max_single_decision_change=0.10)
    )
    decision = advisory.decide(
        _frame().iloc[[0]],
        policy="composite_only",
        previous_position=0.20,
    )

    assert decision.final_position <= 0.30 + 1e-12
    assert decision.final_position >= 0.10 - 1e-12


def test_cash_policy_exits_immediately_even_with_previous_position() -> None:
    decision = CompositeAdvisory().decide(
        _frame().iloc[[0]],
        policy="cash",
        previous_position=1.0,
    )

    assert decision.final_position == 0.0


@pytest.mark.parametrize(
    "field",
    [
        "trend_conflict_multiplier",
        "reversion_multiplier",
        "relative_conflict_multiplier",
        "macro_cap_floor",
        "max_position",
    ],
)
def test_directional_bounds_reject_invalid_config(field: str) -> None:
    values = {field: -0.01}

    with pytest.raises(ValueError, match=field):
        CompositeAdvisory(config=AdvisoryConfig(**values))
