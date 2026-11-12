import numpy as np
import pandas as pd
import pytest

from core.market_factor_context import (
    MarketFactorContext,
    build_market_factor_context,
    normalize_market,
)
from core.factor_pipeline import FactorPipeline
from core.macro_factors import MacroFactors


def _prices(days: int = 45) -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=days, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "open": np.linspace(10, 12, days),
            "high": np.linspace(10.2, 12.2, days),
            "low": np.linspace(9.8, 11.8, days),
            "close": np.linspace(10, 12, days),
            "volume": np.full(days, 1000),
        }
    )


def test_market_normalization_and_unknown_market() -> None:
    assert normalize_market("cn-a") == "CN_A"
    with pytest.raises(ValueError, match="Unsupported market"):
        normalize_market("EU")


def test_legacy_compute_batch_panel_accepts_single_stock_frame() -> None:
    macro = MacroFactors()
    result = macro.compute_batch_panel(_prices(), dates=_prices()["date"].iloc[-2:])
    assert result.index.name == "date"
    assert {"vix_level", "beta_20d", "rel_strength_vs_spy"}.issubset(result.columns)


    frame = pd.concat(
        [
            _prices().assign(symbol="000001"),
            _prices().assign(symbol="000002", close=lambda value: value["close"] * 1.01),
        ],
        ignore_index=True,
    )
    context = build_market_factor_context("CN_A", universe_frame=frame)
    assert context.market == "CN_A"
    assert context.benchmark_symbol == "frozen_universe_equal_weight"
    assert context.factor_availability["benchmark"] == "frozen_universe_equal_weight_close_return"
    assert context.volatility_frame is None
    assert {"breadth_up_ratio_1", "market_constituent_count"}.issubset(
        context.breadth_frame.columns
    )


def test_cn_a_explicit_benchmark_keeps_universe_breadth() -> None:
    universe = pd.concat(
        [
            _prices().assign(symbol="000001"),
            _prices().assign(symbol="000002", close=lambda value: value["close"] * 1.01),
        ],
        ignore_index=True,
    )
    context = build_market_factor_context(
        "CN_A", benchmark_frame=_prices()[["date", "close"]], universe_frame=universe
    )
    assert context.breadth_frame is not None
    assert context.factor_availability["breadth"] == "frozen_universe"
    assert context.breadth_frame["market_constituent_count"].iloc[-1] == 2.0


def test_cn_a_never_reads_us_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("CN_A attempted to read an artifact")

    monkeypatch.setattr(pd, "read_parquet", fail_if_read)
    context = build_market_factor_context("CN_A", benchmark_frame=_prices()[["date", "close"]])
    result = FactorPipeline().compute_all_factors(
        _prices(), "000001", market="CN_A", market_context=context
    )
    assert "market_vol_level" in result.columns


def test_universe_rejects_duplicate_keys_and_non_finite_close() -> None:
    prices = _prices().assign(symbol="000001")
    with pytest.raises(ValueError, match="duplicate date-symbol"):
        build_market_factor_context("CN_A", universe_frame=pd.concat([prices, prices.iloc[[0]]]))
    invalid = prices.copy()
    invalid.loc[0, "close"] = np.inf
    with pytest.raises(ValueError, match="finite and positive"):
        build_market_factor_context("CN_A", universe_frame=invalid)


def test_cn_a_breadth_is_nan_when_unavailable() -> None:
    benchmark = _prices()[["date", "close"]]
    context = MarketFactorContext("CN_A", "000300", benchmark)
    result = FactorPipeline().compute_all_factors(
        _prices(), "000001", market="CN_A", market_context=context
    )
    assert result["market_breadth"].isna().all()
    assert result["breadth_up_ratio_1"].isna().all()
    assert result["market_constituent_count"].isna().all()


def test_cn_a_requires_context_and_never_uses_us_compatibility() -> None:
    with pytest.raises(ValueError, match="explicit MarketFactorContext"):
        FactorPipeline().compute_all_factors(_prices(), "000001", market="CN_A")


def test_cn_a_output_does_not_expose_us_intermediate_names() -> None:
    prices = _prices()
    context = build_market_factor_context("CN_A", universe_frame=prices.assign(symbol="000001"))
    result = FactorPipeline().compute_all_factors(
        prices, "000001", market="CN_A", market_context=context
    )
    assert "beta_20d" not in result.columns
    assert "sector_momentum" not in result.columns


def test_context_market_mismatch_fails() -> None:
    benchmark = _prices()[["date", "close"]]
    context = MarketFactorContext("US", "SPY", benchmark)
    with pytest.raises(ValueError, match="market/context mismatch"):
        FactorPipeline().compute_all_factors(
            _prices(), "000001", market="CN_A", market_context=context
        )


def test_context_rejects_duplicate_or_unsorted_benchmark_dates() -> None:
    benchmark = _prices()[["date", "close"]].iloc[[1, 0]]
    with pytest.raises(ValueError, match="unique and sorted"):
        MarketFactorContext("CN_A", "000300", benchmark)


def test_cn_a_factor_output_has_market_native_names_and_preserves_input() -> None:
    prices = _prices()
    context = build_market_factor_context("CN_A", universe_frame=prices.assign(symbol="000001"))
    original = prices.copy(deep=True)
    result = FactorPipeline().compute_all_factors(
        prices, "000001", market="CN_A", market_context=context
    )
    assert "market_vol_level" in result
    assert "rel_strength_market" in result
    assert "vix_level" not in result
    pd.testing.assert_frame_equal(prices, original)
