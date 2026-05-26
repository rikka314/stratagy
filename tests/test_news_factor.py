from __future__ import annotations

import numpy as np
import pandas as pd

from core.news_factor import apply_news_fusion


def _signal_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-05-01", periods=8, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "close": np.linspace(100, 108, len(dates)),
            "factor_score": np.linspace(-0.4, 0.6, len(dates)),
            "factor_percentile": np.linspace(0.1, 0.9, len(dates)),
            "target_position": np.linspace(0.0, 1.0, len(dates)),
            "buy_signal": [False, True, False, False, False, False, False, False],
            "sell_signal": [False, False, False, False, False, False, False, True],
            "mom_short_z": np.linspace(-0.3, 0.4, len(dates)),
            "mom_long_z": np.linspace(-0.2, 0.5, len(dates)),
            "macd_z": np.linspace(-0.1, 0.6, len(dates)),
            "rsi_z": np.linspace(-0.4, 0.3, len(dates)),
        }
    )


def _write_news_csv(path) -> None:
    pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL", "AAPL", "AAPL"],
            "date": ["2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06"],
            "news_count": [2, 1, 3, 1],
            "positive_count": [2, 1, 1, 0],
            "neutral_count": [0, 0, 1, 0],
            "negative_count": [0, 0, 1, 1],
            "sentiment_mean": [0.8, 0.5, 0.0, -0.8],
            "sentiment_sum": [1.6, 0.5, 0.0, -0.8],
            "sentiment_ewm_3": [0.8, 0.65, 0.325, -0.2375],
            "sentiment_ewm_5": [0.8, 0.7, 0.4667, 0.0445],
            "negative_tail_ratio": [0.0, 0.0, 0.3333, 1.0],
            "confidence_mean": [0.85, 0.8, 0.7, 0.85],
        }
    ).to_csv(path, index=False)


def test_news_fusion_preserves_original_factor_score_and_adds_fused_columns(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    _write_news_csv(news_path)

    original = _signal_frame()
    fused, metadata = apply_news_fusion(
        original,
        news_factor_path=news_path,
        symbol="AAPL",
        news_weight=0.4,
        news_lookback=2,
        split_idx=4,
    )

    assert metadata["news_rows_loaded"] == 4
    assert metadata["news_rows_matched"] == 4
    assert "fused_factor_score" in fused.columns
    assert "news_delta" in fused.columns
    assert fused["factor_score"].equals(original["factor_score"])
    assert fused.loc[fused["news_delta"].abs() > 0, "fused_factor_score"].notna().any()


def test_news_weight_zero_keeps_upstream_target_position(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    _write_news_csv(news_path)

    original = _signal_frame()
    fused, metadata = apply_news_fusion(
        original,
        news_factor_path=news_path,
        symbol="AAPL",
        news_weight=0.0,
        news_lookback=2,
        split_idx=4,
    )

    assert metadata["news_weight"] == 0.0
    assert np.allclose(fused["news_delta"], 0.0)
    assert np.allclose(fused["fused_factor_score"], original["factor_score"])
    assert np.allclose(fused["target_position"], original["target_position"])
