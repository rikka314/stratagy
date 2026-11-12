"""Tests for the Phase 3 heterogeneous expert pool."""

import numpy as np
import pandas as pd
import pytest

from core.expert_pool_v2 import ExpertPoolV2


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "mom_short_z": [1.0, -1.0],
            "mom_long_z": [0.8, -0.8],
            "macd_z": [1.0, -1.0],
            "rsi_z": [0.5, -0.5],
            "bb_position_rank": [0.8, 0.2],
            "price_position_rank": [0.7, 0.3],
            "vix_level": [20.0, 30.0],
            "vol_z": [0.2, 1.0],
            "drawdown_rank": [-0.1, -0.8],
            "rel_strength_spy": [0.8, -0.2],
            "volume_ratio_rank": [0.8, 0.2],
        },
        index=pd.Index(["a", "b"], name="row"),
    )


def test_experts_use_expected_orthogonal_factor_sets() -> None:
    pool = ExpertPoolV2()
    definitions = {item.expert_id: set(item.factors) for item in pool.definitions()}

    assert definitions["momentum_optimized"] == {"mom_short_z", "mom_long_z", "macd_z"}
    assert definitions["mean_reversion"] == {"rsi_z", "bb_position_rank", "price_position_rank"}
    assert definitions["macro_defensive"] == {"vix_level", "vol_z", "drawdown_rank"}
    assert definitions["volume_confirmed"] == {"rel_strength_spy", "mom_short_z"}
    assert definitions["cash"] == set()


def test_scores_include_phase25_weights_and_interaction() -> None:
    pool = ExpertPoolV2()
    frame = _frame()
    scores = pool.compute_scores(frame)

    assert scores["volume_confirmed"].iloc[0] > scores["volume_confirmed"].iloc[1]
    assert scores["composite_optimized"].index.equals(frame.index)
    assert scores["cash"].eq(0.0).all()


def test_signals_preserve_index_and_do_not_mutate_input() -> None:
    pool = ExpertPoolV2()
    frame = _frame()
    original = frame.copy(deep=True)

    signals = pool.get_all_expert_signals(
        frame,
        relative_rank=pd.Series([0.75, 0.25], index=frame.index),
    )

    assert frame.equals(original)
    assert all(signal.index.equals(frame.index) for signal in signals.values())
    assert all(np.isfinite(signal.to_numpy()).all() for signal in signals.values())
    assert all(((signal >= -1.0) & (signal <= 1.0)).all() for signal in signals.values())
    assert (signals["mean_reversion"] < 0).any()
    assert (signals["volume_confirmed"] < 0).any()


def test_missing_or_nonfinite_factors_fail_closed() -> None:
    pool = ExpertPoolV2()
    with pytest.raises(ValueError, match="missing factor columns"):
        pool.compute_scores(_frame().drop(columns=["rsi_z"]))

    invalid = _frame()
    invalid.loc["a", "vix_level"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        pool.compute_scores(invalid)
