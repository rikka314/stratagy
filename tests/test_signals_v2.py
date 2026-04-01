from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import core.signals as signals


def _build_signal_input(
    *,
    ema_fast: list[float],
    ema_slow: list[float],
    adx: list[float],
    rsi: list[float],
    macd: list[float],
    signal_line: list[float],
) -> pd.DataFrame:
    rows = len(ema_fast)
    close = np.linspace(100.0, 100.0 + rows - 1, rows)
    return pd.DataFrame(
        {
            "close": close,
            "atr": np.full(rows, 1.0),
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "adx": adx,
            "rsi": rsi,
            "macd": macd,
            "signal": signal_line,
            "histogram": np.zeros(rows),
            "bb_position": np.full(rows, 0.5),
            "obv_trend": np.zeros(rows),
            "volume_ratio": np.full(rows, 1.0),
            "price_position": np.full(rows, 0.5),
            "drawdown": np.zeros(rows),
        }
    )


def _stub_signal_features(
    monkeypatch: pytest.MonkeyPatch,
    *,
    factor_scores: list[float],
    factor_percentiles: list[float],
    volatility_percentiles: list[float] | None = None,
) -> None:
    factor_series = pd.Series(factor_scores, dtype=float)
    factor_pct_series = pd.Series(factor_percentiles, dtype=float)
    vol_pct_series = pd.Series(
        volatility_percentiles if volatility_percentiles is not None else [0.5] * len(factor_scores),
        dtype=float,
    )

    monkeypatch.setattr(
        signals,
        "_compute_manual_factor_score",
        lambda df, **kwargs: pd.Series(factor_series.to_numpy(), index=df.index, dtype=float),
    )
    monkeypatch.setattr(
        signals,
        "rolling_zscore",
        lambda series, lookback: pd.Series(np.zeros(len(series)), index=series.index, dtype=float),
    )
    monkeypatch.setattr(
        signals,
        "rolling_rank",
        lambda series, lookback: pd.Series(np.full(len(series), 0.5), index=series.index, dtype=float),
    )

    def fake_percentile(series: pd.Series, lookback: int) -> pd.Series:
        source = factor_pct_series if series.name == "factor_score" else vol_pct_series
        return pd.Series(source.to_numpy(), index=series.index, dtype=float)

    monkeypatch.setattr(signals, "rolling_percentile", fake_percentile)


def _compute(df: pd.DataFrame, **overrides) -> pd.DataFrame:
    params = {
        "rsi_lower": 30.0,
        "rsi_upper": 70.0,
        "adx_threshold": 20.0,
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
        "exit_threshold": 0.0,
        "weight_bb": 0.0,
        "weight_obv": 0.0,
        "weight_volume": 0.0,
        "weight_price": 0.0,
        "weight_drawdown": 0.0,
    }
    params.update(overrides)
    return signals.compute_signals(df, **params)


def test_hold_until_exit_keeps_position_until_exit_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _build_signal_input(
        ema_fast=[1.0, 2.0, 2.0, 1.0],
        ema_slow=[2.0, 1.0, 1.0, 2.0],
        adx=[10.0, 25.0, 10.0, 25.0],
        rsi=[50.0, 50.0, 80.0, 80.0],
        macd=[0.0, 1.0, 1.0, -1.0],
        signal_line=[1.0, 0.0, 0.0, 0.0],
    )
    _stub_signal_features(
        monkeypatch,
        factor_scores=[0.0, 0.8, 0.2, -1.0],
        factor_percentiles=[0.0, 0.9, 0.05, 0.05],
    )

    v2 = _compute(
        df,
        entry_min_signals=3,
        exit_min_signals=2,
        hold_until_exit=True,
        hold_min_position=0.2,
    )
    legacy = _compute(
        df,
        entry_min_signals=3,
        exit_min_signals=2,
        hold_until_exit=False,
    )

    assert v2["target_position"].tolist() == [0.0, 1.0, 0.2, 0.0]
    assert legacy["target_position"].tolist() == [0.0, 1.0, 0.0, 0.0]
    assert v2["buy_signal"].tolist() == [False, True, False, False]
    assert v2["sell_signal"].tolist() == [False, False, False, True]


def test_entry_exit_thresholds_shrink_with_disabled_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _build_signal_input(
        ema_fast=[1.0, 2.0, 1.0],
        ema_slow=[2.0, 1.0, 2.0],
        adx=[10.0, 10.0, 10.0],
        rsi=[50.0, 50.0, 50.0],
        macd=[0.0, 1.0, -1.0],
        signal_line=[1.0, 0.0, 0.0],
    )
    _stub_signal_features(
        monkeypatch,
        factor_scores=[0.0, 0.8, -1.0],
        factor_percentiles=[0.0, 0.9, 0.9],
    )

    result = _compute(
        df,
        entry_min_signals=5,
        exit_min_signals=5,
        use_strength_filter=False,
        use_rsi_filter=False,
        hold_until_exit=False,
    )

    assert result["entry_count"].tolist() == [0, 3, 0]
    assert result["exit_count"].tolist() == [3, 0, 3]
    assert result["target_position"].tolist() == [0.0, 1.0, 0.0]


def test_score_mid_high_percentiles_map_directly_to_position_bands(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _build_signal_input(
        ema_fast=[2.0] * 5,
        ema_slow=[1.0] * 5,
        adx=[25.0] * 5,
        rsi=[50.0] * 5,
        macd=[1.0] * 5,
        signal_line=[0.0] * 5,
    )
    _stub_signal_features(
        monkeypatch,
        factor_scores=[1.0] * 5,
        factor_percentiles=[0.92, 0.82, 0.62, 0.52, 0.42],
    )

    result = _compute(
        df,
        entry_min_signals=1,
        exit_threshold=-2.0,
        score_mid_pct=0.6,
        score_high_pct=0.9,
    )

    assert result["target_position"].tolist() == [1.0, 0.8, 0.6, 0.4, 0.2]
