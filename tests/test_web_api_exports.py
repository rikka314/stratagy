from __future__ import annotations

import pandas as pd

from api.exporting import build_portfolio_export, build_single_export
from api.service import prepare_dataframe, run_portfolio_calculation, run_single_calculation


def _dataset(symbol: str, frame: pd.DataFrame) -> dict:
    return {"dataset_id": symbol.lower() * 20, "symbol": symbol, "market": "US", "adjust": "qfq", "source": "upload", "dataframe": frame.copy()}


def test_single_export_contains_charts_trades_and_language() -> None:
    frame = prepare_dataframe(pd.read_csv("data/aapl_clean_daily.csv").tail(700))
    result = run_single_calculation(_dataset("AAPL", frame), {"family": "search", "search_base": "sm"}, {}, 0.7)
    job = {"symbol": "AAPL", "market": "US", "result": result}

    zh = build_single_export(job, "zh")
    en = build_single_export(job, "en")

    assert "AAPL 策略分析报告" in zh
    assert "AAPL Strategy Analysis Report" in en
    assert "Plotly.newPlot" in zh
    assert "single-candle-chart" in zh
    assert "single-equity-chart" in zh
    assert "交易明细" in zh
    assert result["artifact"]["trades"]
    assert str(result["artifact"]["trades"][0]["entry_date"])[:10] in zh
    assert "<pre>{" not in zh


def test_single_export_escapes_hostile_symbol() -> None:
    frame = prepare_dataframe(pd.read_csv("data/aapl_clean_daily.csv").tail(300))
    result = run_single_calculation(_dataset("AAPL", frame), {"family": "baseline", "baseline_kind": "naive"}, {}, 0.7)
    hostile = '</title><script id="attack">alert(1)</script>'
    report = build_single_export({"symbol": hostile, "market": "US", "result": result}, "en")

    assert '<script id="attack">' not in report
    assert "&lt;/title&gt;" in report


def test_portfolio_export_contains_symbols_weights_and_real_charts() -> None:
    first = prepare_dataframe(pd.read_csv("data/aapl_clean_daily.csv").tail(500))
    second = first.copy()
    for column in ("open", "high", "low", "close"):
        second[column] *= 1.02
    datasets = [_dataset("AAPL", first), _dataset("SECOND", second)]
    result = run_portfolio_calculation(datasets, {}, {datasets[0]["dataset_id"]: 0.6, datasets[1]["dataset_id"]: 0.4})

    report = build_portfolio_export(datasets, result, {}, "en")

    assert "Multi-stock Portfolio Strategy Report" in report
    assert "AAPL" in report and "SECOND" in report
    assert "60.0%" in report and "40.0%" in report
    assert "multi-comparison-chart" in report
    assert "multi-portfolio-chart" in report
    assert "Plotly.newPlot" in report
