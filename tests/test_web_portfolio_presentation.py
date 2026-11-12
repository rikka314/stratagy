from __future__ import annotations

import pandas as pd

from api.portfolio_presentation import build_portfolio_presentation


def test_portfolio_presentation_contains_drawdown_and_all_legacy_periods() -> None:
    index = pd.date_range("2024-01-01", periods=260, freq="B")
    returns = pd.Series([0.001] * 130 + [-0.002] * 130, index=index)
    equity = (1 + returns).cumprod()
    result = {
        "portfolio_equity": equity,
        "portfolio_strat_ret": returns,
        "individual_results": {"AAA": {"strategy_return": returns}},
    }

    payload = build_portfolio_presentation(result)

    assert len(payload["drawdown"]) == len(equity)
    assert payload["drawdown"][0]["drawdown"] == 0.0
    assert payload["drawdown"][-1]["drawdown"] < 0.0
    assert set(payload["periodic_returns"]) == {"M", "Q", "YE"}
    for period in ("M", "Q", "YE"):
        heatmap = payload["periodic_returns"][period]
        assert heatmap is not None
        assert heatmap["y"] == ["portfolio", "AAA"]
        assert len(heatmap["x"]) == len(heatmap["z"][0])


def test_portfolio_presentation_handles_missing_series() -> None:
    assert build_portfolio_presentation({"individual_results": {}}) == {
        "drawdown": [],
        "periodic_returns": {"M": None, "Q": None, "YE": None},
    }
