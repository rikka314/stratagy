"""Tests for Phase 2 robust Composite weight research."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_test.robust_weight_research import (
    WeightResearchConfig,
    bootstrap_weight_intervals,
    centred_interaction,
    fit_train_transform,
    stability_summary,
)


def _config() -> WeightResearchConfig:
    return WeightResearchConfig(
        factors=("mom", "risk"),
        directions={"mom": 1, "risk": -1},
        family_by_factor={"mom": "trend", "risk": "risk"},
        family_budgets={"trend": 2.0, "risk": 1.0},
        bootstrap_samples=30,
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=8),
            "mom": np.arange(8, dtype=float),
            "risk": np.arange(8, dtype=float)[::-1],
        }
    )


def test_train_transform_is_fitted_on_train_and_preserves_input() -> None:
    frame = _frame()
    original = frame.copy(deep=True)
    transform = fit_train_transform(frame, ("mom", "risk"))

    transformed = transform.transform(frame, ("mom", "risk"))

    assert frame.equals(original)
    assert transformed.shape == (8, 2)
    assert transform.fit_start == "2020-01-01"
    assert transform.fit_end == "2020-01-08"
    assert np.isfinite(transformed.to_numpy()).all()


def test_train_transform_rejects_missing_or_empty_factors() -> None:
    with pytest.raises(ValueError, match="missing factors"):
        fit_train_transform(pd.DataFrame({"mom": [1.0]}), ("mom", "risk"))
    with pytest.raises(ValueError, match="no finite"):
        fit_train_transform(pd.DataFrame({"mom": [np.nan]}), ("mom",))


def test_centred_interaction_uses_frozen_main_effect_transform() -> None:
    frame = _frame()
    transform = fit_train_transform(frame, ("mom", "risk"))

    interaction = centred_interaction(frame, "mom", "risk", transform)

    assert interaction.name == "mom_x_risk"
    assert len(interaction) == len(frame)
    assert np.isfinite(interaction.to_numpy()).all()


def test_bootstrap_intervals_and_stability_are_reproducible() -> None:
    paths = pd.DataFrame(
        {
            "fold_id": ["f1", "f2", "f3"],
            "seed": [1, 2, 3],
            "mom": [1.0, 0.8, 1.2],
            "risk": [-0.5, -0.4, -0.6],
        }
    )
    config = _config()

    intervals_a = bootstrap_weight_intervals(paths, samples=30, block_length=2, seed=7)
    intervals_b = bootstrap_weight_intervals(paths, samples=30, block_length=2, seed=7)
    summary = stability_summary(paths, config)

    assert intervals_a.equals(intervals_b)
    assert set(intervals_a["factor"]) == {"mom", "risk"}
    assert summary.set_index("factor").loc["mom", "sign_stability"] == 1.0
    assert summary.set_index("factor").loc["risk", "registered_direction"] == -1


def test_invalid_research_config_rejects_incomplete_direction_registry() -> None:
    with pytest.raises(ValueError, match="cover factors exactly"):
        WeightResearchConfig(
            factors=("mom",),
            directions={},
            family_by_factor={"mom": "trend"},
            family_budgets={"trend": 1.0},
        )
