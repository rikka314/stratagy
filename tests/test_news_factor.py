from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.news_factor import (
    NEWS_ABLATION_COLUMNS,
    apply_news_fusion,
    load_news_factor_csv,
    normalize_news_symbol,
    run_news_ablation,
    validate_news_factor_frame,
)


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


def test_news_alignment_uses_next_trading_day_and_records_information_dates(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    _write_news_csv(news_path)

    fused, metadata = apply_news_fusion(
        _signal_frame(),
        news_factor_path=news_path,
        symbol="AAPL",
        news_weight=0.4,
        news_lookback=2,
        split_idx=4,
    )

    same_day = fused.loc[fused["date"] == pd.Timestamp("2026-05-03")].iloc[0]
    next_day = fused.loc[fused["date"] == pd.Timestamp("2026-05-04")].iloc[0]
    assert pd.isna(same_day["news_information_date"])
    assert next_day["news_information_date"] == pd.Timestamp("2026-05-03")
    assert next_day["news_effective_date"] == pd.Timestamp("2026-05-04")
    assert metadata["news_available_lag_trading_days"] == 1
    assert metadata["future_leakage_violation_count"] == 0


def test_non_trading_news_rows_sharing_an_effective_date_do_not_duplicate_signal_rows(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "date": ["2026-05-02", "2026-05-03"],
            "news_count": [1, 1],
            "sentiment_ewm_3": [0.2, 0.7],
            "confidence_mean": [0.8, 0.8],
        }
    ).to_csv(news_path, index=False)
    signal = _signal_frame()
    signal["date"] = pd.bdate_range("2026-05-01", periods=len(signal))

    fused, metadata = apply_news_fusion(
        signal, news_factor_path=news_path, symbol="AAPL", news_lookback=2, split_idx=4
    )

    assert len(fused) == len(signal)
    assert metadata["effective_date_collision_count"] == 1
    assert metadata["duplicate_news_row_count"] == 1
    row = fused.loc[fused["date"] == pd.Timestamp("2026-05-05")].iloc[0]
    assert row["news_information_date"] == pd.Timestamp("2026-05-03")


def test_no_news_rows_restore_upstream_position_when_weight_is_nonzero(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    _write_news_csv(news_path)
    original = _signal_frame()

    fused, _ = apply_news_fusion(
        original, news_factor_path=news_path, symbol="AAPL", news_weight=0.4, news_lookback=2, split_idx=4
    )

    no_news = fused["sentiment_ewm_3"].isna()
    assert no_news.any()
    assert np.allclose(fused.loc[no_news, "target_position"], original.loc[no_news, "target_position"])


def test_validation_normalizes_a_share_symbols_and_reports_duplicates_and_outliers() -> None:
    raw = pd.DataFrame(
        {
            "symbol": ["SZ000001", "000001.SZ"],
            "date": ["2026-05-01", "2026-05-01"],
            "news_count": [-1, 2],
            "sentiment_ewm_3": [99.0, 0.2],
            "confidence_mean": [1.5, 0.8],
        }
    )

    validated, diagnostics = validate_news_factor_frame(raw, market="CN_A")

    assert normalize_news_symbol("SZ000001", market="CN_A") == "000001"
    assert len(validated) == 1
    assert validated.loc[0, "symbol"] == "000001"
    assert diagnostics["duplicate_news_row_count"] == 1
    assert diagnostics["sentiment_outlier_count"] == 1
    assert diagnostics["confidence_outlier_count"] == 1
    assert diagnostics["negative_news_count_count"] == 1


def test_validation_drops_missing_symbols_and_fusion_degrades_without_proxy_columns(tmp_path) -> None:
    raw = pd.DataFrame(
        {
            "symbol": [None, "AAPL"],
            "date": ["2026-05-01", "2026-05-03"],
            "news_count": [1, 1],
            "sentiment_ewm_3": [0.1, 0.8],
            "confidence_mean": [0.8, 0.8],
        }
    )
    validated, diagnostics = validate_news_factor_frame(raw, market="US")
    assert len(validated) == 1
    assert diagnostics["empty_symbol_count"] == 1

    news_path = tmp_path / "news_sentiment_daily.csv"
    raw.iloc[1:].to_csv(news_path, index=False)
    sparse_signal = _signal_frame().drop(columns=["mom_short_z", "mom_long_z", "macd_z", "rsi_z"])
    fused, metadata = apply_news_fusion(
        sparse_signal, news_factor_path=news_path, symbol="AAPL", news_lookback=2, split_idx=4
    )
    assert metadata["news_beta"] == {"mom_short_z": 0.0, "mom_long_z": 0.0, "macd_z": 0.0, "rsi_z": 0.0}
    assert len(fused) == len(sparse_signal)


def test_missing_news_file_is_visible_to_callers(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="news factor CSV not found"):
        load_news_factor_csv(tmp_path / "missing.csv")


def test_news_ablation_writes_frozen_summary_schema(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    output_path = tmp_path / "news_ablation_summary.csv"
    _write_news_csv(news_path)

    result = run_news_ablation(
        _signal_frame(),
        news_factor_path=news_path,
        output_path=output_path,
        base_strategy_id="sm",
        symbol="AAPL",
        weights=(0.0, 0.30),
        lookbacks=(3, 5),
        split_idx=4,
    )

    assert tuple(result.columns) == NEWS_ABLATION_COLUMNS
    assert len(result) == 4
    assert (result["future_leakage_violation_count"] == 0).all()
    assert (result["fallback_position_match_rate"] == 1.0).all()
    assert output_path.exists()


def test_load_mixed_market_csv_preserves_cn_leading_zero_and_filters_market(tmp_path) -> None:
    news_path = tmp_path / "mixed_news.csv"
    pd.DataFrame(
        {
            "market": ["CN", "US"],
            "symbol": ["000001", "AAPL"],
            "date": ["2026-05-01", "2026-05-01"],
            "news_count": [1, 2],
            "sentiment_ewm_3": [0.1, 0.2],
            "confidence_mean": [0.8, 0.9],
        }
    ).to_csv(news_path, index=False)

    cn_news, diagnostics = load_news_factor_csv(
        news_path, market="CN_A", return_diagnostics=True
    )

    assert cn_news["symbol"].tolist() == ["000001"]
    assert cn_news["market"].tolist() == ["CN_A"]
    assert diagnostics["markets"] == ["CN_A", "US"]
    assert diagnostics["news_rows_after_market_filter"] == 1


def test_validation_reports_future_missing_and_unknown_market_values() -> None:
    raw = pd.DataFrame(
        {
            "market": ["US", "A"],
            "symbol": ["AAPL", "SZ000001"],
            "date": ["2099-01-01", "2026-05-01"],
            "news_count": [None, 1],
            "sentiment_ewm_3": [None, 0.2],
            "confidence_mean": [None, 0.8],
        }
    )

    validated, diagnostics = validate_news_factor_frame(raw, as_of_date="2026-08-09")

    assert validated["market"].tolist() == ["US", "CN_A"]
    assert validated["symbol"].tolist() == ["AAPL", "000001"]
    assert diagnostics["future_information_date_count"] == 1
    assert diagnostics["missing_news_count_count"] == 1
    assert diagnostics["missing_sentiment_count"] == 1
    assert diagnostics["missing_confidence_count"] == 1
    with pytest.raises(ValueError, match="unsupported news market values"):
        validate_news_factor_frame(raw.assign(market=["EU", "A"]))


def test_custom_lag_delays_effective_date_and_zero_lag_is_rejected(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    _write_news_csv(news_path)

    fused, metadata = apply_news_fusion(
        _signal_frame(),
        news_factor_path=news_path,
        symbol="AAPL",
        news_lookback=2,
        news_available_lag_trading_days=2,
    )

    first_match = fused.loc[fused["news_information_date"].notna()].iloc[0]
    assert first_match["news_information_date"] == pd.Timestamp("2026-05-03")
    assert first_match["news_effective_date"] == pd.Timestamp("2026-05-05")
    assert metadata["news_available_lag_trading_days"] == 2
    with pytest.raises(ValueError, match="at least 1"):
        apply_news_fusion(
            _signal_frame(),
            news_factor_path=news_path,
            symbol="AAPL",
            news_available_lag_trading_days=0,
        )


def test_extreme_sentiment_is_reported_and_fusion_stays_finite(tmp_path) -> None:
    news_path = tmp_path / "extreme_news.csv"
    pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "date": ["2026-05-01", "2026-05-02"],
            "news_count": [1, 2],
            "sentiment_ewm_3": [1e12, -1e12],
            "confidence_mean": [0.8, 0.9],
        }
    ).to_csv(news_path, index=False)

    fused, metadata = apply_news_fusion(
        _signal_frame(),
        news_factor_path=news_path,
        symbol="AAPL",
        news_weight=0.4,
        news_lookback=2,
    )

    assert metadata["sentiment_outlier_count"] == 2
    assert np.isfinite(fused["news_delta"]).all()
    assert np.isfinite(fused["target_position"]).all()


def test_multi_symbol_fusion_keeps_rolling_state_isolated(tmp_path) -> None:
    news_path = tmp_path / "news_sentiment_daily.csv"
    news = pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL", "MSFT", "MSFT"],
            "date": ["2026-05-01", "2026-05-02", "2026-05-01", "2026-05-02"],
            "news_count": [1, 2, 2, 1],
            "sentiment_ewm_3": [0.2, 0.6, -0.3, -0.7],
            "confidence_mean": [0.8, 0.8, 0.9, 0.9],
        }
    )
    news.to_csv(news_path, index=False)
    aapl = _signal_frame().iloc[:5].assign(symbol="AAPL")
    msft = _signal_frame().iloc[:5].assign(symbol="MSFT")
    msft["date"] = pd.to_datetime(
        ["2026-05-01", "2026-05-03", "2026-05-04", "2026-05-06", "2026-05-07"]
    )
    combined = pd.concat([aapl, msft], ignore_index=True)

    fused_combined, _ = apply_news_fusion(
        combined, news_factor_path=news_path, market="US", news_lookback=2
    )
    fused_aapl, _ = apply_news_fusion(
        aapl, news_factor_path=news_path, symbol="AAPL", market="US", news_lookback=2
    )
    fused_msft, _ = apply_news_fusion(
        msft, news_factor_path=news_path, symbol="MSFT", market="US", news_lookback=2
    )

    assert np.allclose(
        fused_combined.loc[fused_combined["symbol"] == "AAPL", "news_delta"],
        fused_aapl["news_delta"],
    )
    assert np.allclose(
        fused_combined.loc[fused_combined["symbol"] == "MSFT", "news_delta"],
        fused_msft["news_delta"],
    )


def test_ablation_marks_missing_file_as_skipped_without_changing_grid_shape(tmp_path) -> None:
    result = run_news_ablation(
        _signal_frame(),
        news_factor_path=tmp_path / "missing.csv",
        output_path=tmp_path / "news_ablation_summary.csv",
        base_strategy_id="sm",
        symbol="AAPL",
        weights=(0.0, 0.3),
        lookbacks=(3,),
    )

    assert len(result) == 2
    assert (result["status"] == "skipped").all()
    assert result["skip_reason"].str.contains("news factor CSV not found").all()
    assert (result["coverage_rate"] == 0.0).all()


def test_ablation_marks_zero_coverage_as_skipped_but_preserves_fallback_metrics(tmp_path) -> None:
    news_path = tmp_path / "news.csv"
    pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "date": ["2099-01-01"],
            "news_count": [1],
            "sentiment_ewm_3": [0.2],
            "confidence_mean": [0.8],
        }
    ).to_csv(news_path, index=False)

    result = run_news_ablation(
        _signal_frame(),
        news_factor_path=news_path,
        output_path=tmp_path / "news_ablation_summary.csv",
        base_strategy_id="sm",
        symbol="AAPL",
        weights=(0.3,),
        lookbacks=(3,),
    )

    assert result.loc[0, "status"] == "skipped"
    assert result.loc[0, "skip_reason"] == "no matched news rows"
    assert result.loc[0, "fallback_position_match_rate"] == 1.0
    assert pd.notna(result.loc[0, "net_total_return"])
