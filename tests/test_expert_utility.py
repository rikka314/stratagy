from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.expert_utility import ExpertUtilityV4


def test_expert_utility_compounds_returns_and_uses_equity_drawdown() -> None:
    calculator = ExpertUtilityV4(horizon=3)
    metrics = calculator.compute_expert_utility(
        np.ones(3),
        np.asarray([0.10, -0.20, 0.10]),
    )

    assert metrics["total_return"] == pytest.approx(1.10 * 0.80 * 1.10 - 1.0)
    assert metrics["max_drawdown"] == pytest.approx(-0.20)
    assert metrics["win_rate"] == pytest.approx(2.0 / 3.0)


def test_label_generation_uses_prior_decision_position_and_complete_horizon() -> None:
    dates = pd.bdate_range("2025-01-02", periods=5)
    stock = pd.DataFrame(
        {"close": [100.0, 110.0, 99.0, 108.9, 108.9]},
        index=dates,
    )
    positions = pd.Series([1.0, 0.0, 1.0, 1.0, 1.0], index=dates)

    labels = ExpertUtilityV4(horizon=3).generate_labels_for_backtest(
        stock,
        {"expert": positions},
    )

    assert list(labels.index) == [dates[0], dates[1]]
    first_expected = (1.0 + 1.0 * 0.10) * (1.0 + 0.0 * -0.10) * (1.0 + 1.0 * 0.10) - 1.0
    assert labels.loc[dates[0], "expert_total_return"] == pytest.approx(first_expected)


def test_expert_utility_rejects_invalid_horizon() -> None:
    with pytest.raises(ValueError, match="positive"):
        ExpertUtilityV4(horizon=0)
