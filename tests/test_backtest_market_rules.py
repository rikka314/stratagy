import numpy as np
import pandas as pd
import pytest

from core.backtest import extract_trades, simulate_strategy
from core.market_rules import MarketExecutionConfig, normalize_market, using_execution_config


def _frame(target_position: list[float]) -> pd.DataFrame:
    periods = len(target_position)
    close = np.linspace(100.0, 100.0 + periods - 1, periods)
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=periods, freq="B"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "atr": np.ones(periods),
            "target_position": target_position,
        }
    )


def test_default_execution_is_legacy_compatible() -> None:
    frame = _frame([0.0, 1.0, 1.0, 0.5, 0.0])

    legacy = simulate_strategy(frame)
    legacy_with_trades, legacy_trades = simulate_strategy(frame, return_trades=True)
    zero_cost = simulate_strategy(
        frame,
        execution_config=MarketExecutionConfig("US", commission_bps=0, slippage_bps=0),
    )

    np.testing.assert_allclose(zero_cost["strategy_return"], legacy["strategy_return"])
    np.testing.assert_allclose(zero_cost["strategy_equity"], legacy["strategy_equity"])
    assert {"turnover", "transaction_cost", "gross_strategy_return"}.isdisjoint(legacy.columns)
    assert {"turnover", "transaction_cost", "gross_strategy_return"}.issubset(zero_cost.columns)
    assert zero_cost["transaction_cost"].eq(0.0).all()
    pd.testing.assert_frame_equal(legacy, legacy_with_trades)
    assert list(legacy_trades.columns) == ["entry_date", "exit_date", "hold_days", "trade_return", "is_win"]


def test_contextual_execution_config_applies_only_inside_research_scope() -> None:
    frame = _frame([0.0, 1.0, 1.0])
    legacy = simulate_strategy(frame)

    with using_execution_config(MarketExecutionConfig("US", commission_bps=1, slippage_bps=2)):
        research = simulate_strategy(frame)

    restored = simulate_strategy(frame)
    assert research["transaction_cost"].sum() == pytest.approx(0.0003)
    assert research["strategy_equity"].iloc[-1] < legacy["strategy_equity"].iloc[-1]
    pd.testing.assert_frame_equal(restored, legacy)


def test_extract_trades_keeps_legacy_recalculation_without_execution_fields() -> None:
    result = simulate_strategy(_frame([0.0, 1.0, 1.0, 0.0]))
    expected = extract_trades(result)
    result["strategy_return"] = 0.0

    pd.testing.assert_frame_equal(extract_trades(result), expected)


def test_costs_charge_open_close_and_position_resizes_only() -> None:
    config = MarketExecutionConfig("CN_A", commission_bps=3, slippage_bps=5)
    result = simulate_strategy(_frame([0.0, 1.0, 1.0, 0.4, 0.0]), execution_config=config)

    np.testing.assert_allclose(result["turnover"], [0.0, 1.0, 0.0, 0.6, 0.4])
    np.testing.assert_allclose(result["transaction_cost"], [0.0, 0.0008, 0.0, 0.00048, 0.00032])
    np.testing.assert_allclose(
        result["strategy_return"],
        result["gross_strategy_return"] - result["transaction_cost"],
    )
    assert result["strategy_equity"].iloc[-1] < (1 + result["gross_strategy_return"]).prod()


def test_initial_position_is_charged_against_zero_pre_observation_position() -> None:
    result = simulate_strategy(
        _frame([1.0, 1.0]),
        initial_position=1,
        execution_config=MarketExecutionConfig("US", commission_bps=1, slippage_bps=2),
    )

    np.testing.assert_allclose(result["turnover"], [1.0, 0.0])
    np.testing.assert_allclose(result["transaction_cost"], [0.0003, 0.0])


def test_trade_details_include_cost_and_turnover_for_completed_trade() -> None:
    result, trades = simulate_strategy(
        _frame([0.0, 1.0, 1.0, 0.0]),
        execution_config=MarketExecutionConfig("US", commission_bps=10, slippage_bps=0),
        return_trades=True,
    )

    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["trade_turnover"] == pytest.approx(2.0)
    assert trade["trade_transaction_cost"] == pytest.approx(0.002)
    assert trade["trade_return"] < trade["gross_trade_return"]
    assert trade["trade_return"] == pytest.approx(
        (1 + result["strategy_return"].iloc[1:4]).prod() - 1
    )
    pd.testing.assert_frame_equal(trades, extract_trades(result))


@pytest.mark.parametrize(
    ("value", "expected"),
    [("us", "US"), (" CN ", "CN_A"), ("a", "CN_A")],
)
def test_market_aliases_are_normalized(value: str, expected: str) -> None:
    assert normalize_market(value) == expected


@pytest.mark.parametrize(
    "config",
    [
        {"market": "EU", "commission_bps": 1, "slippage_bps": 1},
        {"market": "US", "commission_bps": -1, "slippage_bps": 1},
        {"market": "US", "commission_bps": 1, "slippage_bps": -1},
        {"market": "US", "commission_bps": float("nan"), "slippage_bps": 1},
    ],
)
def test_invalid_execution_config_is_rejected(config: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MarketExecutionConfig(**config)
