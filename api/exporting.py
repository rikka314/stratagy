"""Rebuild rich offline HTML reports from API-safe serialized results."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from ui.export_reports import build_multi_stock_export_html, build_single_stock_export_html


def _language(value: str) -> str:
    return "en" if str(value).lower() == "en" else "zh"


def _safe_plot_label(value: object) -> str:
    return str(value or "").replace("<", "").replace(">", "").replace("&", "and")[:80]


def _frame(rows: object) -> pd.DataFrame:
    frame = pd.DataFrame(rows if isinstance(rows, list) else [])
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def _series(points: object, value_key: str) -> pd.Series:
    frame = _frame(points)
    if frame.empty or "date" not in frame or value_key not in frame:
        return pd.Series(dtype=float)
    values = pd.to_numeric(frame[value_key], errors="coerce")
    result = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(frame["date"])).dropna()
    return result[~result.index.duplicated(keep="last")].sort_index()


def _basic_figure(*traces: go.BaseTraceType, height: int = 440) -> go.Figure:
    figure = go.Figure(data=list(traces))
    figure.update_layout(
        height=height,
        margin=dict(l=54, r=24, t=26, b=44),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(120,120,120,.14)")
    return figure


def _candles(signals: pd.DataFrame) -> go.Figure:
    if signals.empty or not {"date", "open", "high", "low", "close"}.issubset(signals):
        return go.Figure()
    return _basic_figure(
        go.Candlestick(
            x=signals["date"], open=signals["open"], high=signals["high"],
            low=signals["low"], close=signals["close"], name="OHLC",
            increasing_line_color="#2b7a55", decreasing_line_color="#b64d45",
        ),
        height=560,
    )


def _indicator(signals: pd.DataFrame) -> go.Figure:
    traces: list[go.BaseTraceType] = []
    for column, label, color in (("rsi", "RSI", "#3568a8"), ("macd", "MACD", "#b56b34"), ("macd_signal", "MACD signal", "#62656a")):
        if column in signals and pd.to_numeric(signals[column], errors="coerce").notna().any():
            traces.append(go.Scatter(x=signals["date"], y=signals[column], mode="lines", name=label, line=dict(color=color)))
    return _basic_figure(*traces) if traces else go.Figure()


def _score(signals: pd.DataFrame) -> go.Figure:
    column = "factor_score" if "factor_score" in signals else "regime_score" if "regime_score" in signals else None
    if column is None:
        return go.Figure()
    return _basic_figure(go.Scatter(x=signals["date"], y=signals[column], mode="lines", name="Factor score", line=dict(color="#3568a8")))


def _equity(artifact: dict[str, Any]) -> go.Figure:
    strategy = _series(artifact.get("equity"), "equity")
    test = _frame(artifact.get("test"))
    traces: list[go.BaseTraceType] = []
    if not strategy.empty:
        traces.append(go.Scatter(x=strategy.index, y=strategy, mode="lines", name="Strategy", line=dict(color="#3568a8", width=2.4)))
    if not test.empty and {"date", "buy_hold_equity"}.issubset(test):
        traces.append(go.Scatter(x=test["date"], y=test["buy_hold_equity"], mode="lines", name="Buy & hold", line=dict(color="#62656a", dash="dash")))
    return _basic_figure(*traces, height=540) if traces else go.Figure()


def _signals(signals: pd.DataFrame) -> go.Figure:
    if signals.empty or not {"date", "close"}.issubset(signals):
        return go.Figure()
    traces: list[go.BaseTraceType] = [go.Scatter(x=signals["date"], y=signals["close"], mode="lines", name="Close", line=dict(color="#202124"))]
    for column, label, color, symbol in (("buy_signal", "Buy", "#2b7a55", "triangle-up"), ("sell_signal", "Sell", "#b64d45", "triangle-down")):
        if column in signals:
            mask = signals[column].fillna(False).astype(bool)
            traces.append(go.Scatter(x=signals.loc[mask, "date"], y=signals.loc[mask, "close"], mode="markers", name=label, marker=dict(color=color, symbol=symbol, size=9)))
    return _basic_figure(*traces, height=500)


def _table_section(title: str, rows: list[dict[str, Any]], language: str, *, limit: int = 500) -> str:
    if not rows:
        empty = "暂无数据" if language == "zh" else "N/A"
        return f'<section class="section-stack"><article class="paper-block"><h2 class="section-title">{html.escape(title)}</h2><p>{empty}</p></article></section>'
    columns = list(rows[0])
    head = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
        for row in rows[-limit:]
    )
    return f'<section class="section-stack"><article class="paper-block"><h2 class="section-title">{html.escape(title)}</h2><div class="table-shell"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></article></section>'


def _metadata_section(result: dict[str, Any], artifact: dict[str, Any], language: str) -> str:
    labels = ("运行信息", "参数与元数据", "告警") if language == "zh" else ("Run information", "Parameters and metadata", "Warnings")
    warnings = result.get("warnings") or []
    warning_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in warnings) or f"<li>{'无' if language == 'zh' else 'None'}</li>"
    params = [{"parameter": key, "value": value} for key, value in (artifact.get("params") or {}).items()]
    stage_metadata = (artifact.get("lineage") or [{}])[-1].get("metadata") or {}
    metadata = [{"parameter": f"metadata.{key}", "value": value} for key, value in stage_metadata.items()]
    return (
        f'<section class="section-stack"><article class="paper-block"><h2 class="section-title">{labels[0]}</h2>'
        f'<p><strong>Status:</strong> {html.escape(str(result.get("status", "")))}</p><h3>{labels[2]}</h3><ul>{warning_html}</ul></article></section>'
        + _table_section(labels[1], params + metadata, language)
    )


def build_single_export(job: dict[str, Any], language: str = "zh") -> str:
    language = _language(language)
    result = dict(job.get("result") or {})
    artifact = dict(result.get("artifact") or {})
    signals = _frame(artifact.get("signals"))
    test = _frame(artifact.get("test"))
    trades = list(artifact.get("trades") or [])
    symbol = str(job.get("symbol") or "")
    if not symbol and not signals.empty and "symbol" in signals:
        symbol = str(signals["symbol"].dropna().iloc[0]) if signals["symbol"].notna().any() else ""
    symbol = symbol or "Strategy"
    safe_plot_symbol = _safe_plot_label(symbol)
    model_payload = {
        artifact.get("display_label") or "Strategy": {
            "label": artifact.get("display_label") or "Strategy",
            "short_label": artifact.get("display_label") or "Strategy",
            "eval": artifact.get("metrics") or {},
            "equity_series": _series(artifact.get("equity"), "equity"),
            "returns_series": _series(artifact.get("returns"), "return"),
            "sim_df": test,
            "trades_df": _frame(trades),
            "ml_quality": artifact.get("ml_quality"),
            "color": "#3568a8",
        }
    }
    latest_position = pd.to_numeric(signals.get("target_position"), errors="coerce").dropna() if "target_position" in signals else pd.Series(dtype=float)
    suggestion = ("持有 / 关注" if language == "zh" else "Hold / watch") if not latest_position.empty and latest_position.iloc[-1] > 0 else ("观望" if language == "zh" else "Wait")
    report = build_single_stock_export_html(
        title=(f"{symbol} 策略分析报告" if language == "zh" else f"{symbol} Strategy Analysis Report"),
        symbol=symbol,
        stock_name="",
        market=str(job.get("market") or ""),
        currency="CNY" if job.get("market") == "CN_A" else "USD",
        df=signals,
        test_df=test,
        model_payload=model_payload,
        active_models=list(model_payload),
        candle=_candles(signals),
        ind_fig=_indicator(signals),
        score_fig=_score(signals),
        equity_fig=_equity(artifact),
        signal_fig=_signals(signals),
        suggestion=suggestion,
        indicator_title="技术指标" if language == "zh" else "Technical indicators",
        include_date=True,
        language=language,
        generated_at=datetime.now(),
        ticker_info={"symbol": safe_plot_symbol},
    )
    additions = _metadata_section(result, artifact, language) + _table_section("交易明细" if language == "zh" else "Trade details", trades, language)
    return report.replace('<footer class="footer">', additions + '<footer class="footer">', 1)


def _comparison_stats(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for item in datasets:
        frame = item["dataframe"]
        close = pd.to_numeric(frame["close"], errors="coerce").dropna()
        if close.empty:
            continue
        start, end = float(close.iloc[0]), float(close.iloc[-1])
        total = end / start - 1 if start else None
        periods = max(len(close) - 1, 1)
        annualized = (end / start) ** (252 / periods) - 1 if start > 0 and end > 0 else None
        values.append({
            "symbol": item["symbol"], "display_name": item["symbol"], "start_price": start,
            "latest_price": end, "total_return": total, "annualized_return": annualized,
            "high_price": float(frame["high"].max()), "low_price": float(frame["low"].min()),
            "data_days": len(frame), "date_min": frame["date"].min(), "date_max": frame["date"].max(),
        })
    return sorted(values, key=lambda row: -(row["total_return"] or 0))


def _portfolio_payload(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    equity = _series(result.get("equity"), "equity")
    benchmark = _series(result.get("benchmark"), "equity")
    individual = {}
    for symbol, item in (result.get("individual") or {}).items():
        individual[symbol] = {
            "total_return": item.get("total_return"), "sharpe": item.get("sharpe"),
            "max_dd": item.get("max_drawdown"), "strategy_return": _series(item.get("returns"), "return"),
        }
    figure = _basic_figure(
        go.Scatter(x=equity.index, y=equity, mode="lines", name="Portfolio", line=dict(color="#3568a8", width=2.5)),
        go.Scatter(x=benchmark.index, y=benchmark, mode="lines", name="Buy & hold", line=dict(color="#62656a", dash="dash")),
        height=560,
    )
    return {
        "fig": figure, "portfolio_equity": equity, "bh_equity": benchmark,
        "port_total_return": metrics.get("total_return"), "port_sharpe": metrics.get("sharpe"),
        "port_max_dd": metrics.get("max_drawdown"), "bh_total_return": metrics.get("benchmark_total_return"),
        "bh_sharpe": metrics.get("benchmark_sharpe"), "bh_max_dd": metrics.get("benchmark_max_drawdown"),
        "individual_results": individual, "weights": result.get("weights") or {},
    }


def _normalized_prices(datasets: list[dict[str, Any]]) -> go.Figure:
    traces = []
    for item in datasets:
        frame = item["dataframe"]
        close = pd.to_numeric(frame["close"], errors="coerce")
        if close.notna().any() and close.dropna().iloc[0] != 0:
            traces.append(go.Scatter(x=frame["date"], y=close / close.dropna().iloc[0] * 100, mode="lines", name=_safe_plot_label(item["symbol"])))
    return _basic_figure(*traces, height=500)


def _correlation(datasets: list[dict[str, Any]]) -> go.Figure:
    prices = pd.DataFrame({item["symbol"]: item["dataframe"].set_index("date")["close"] for item in datasets})
    correlation = prices.pct_change().corr()
    labels = [_safe_plot_label(value) for value in correlation.columns]
    return _basic_figure(go.Heatmap(z=correlation.to_numpy(), x=labels, y=labels, zmin=-1, zmax=1, colorscale="RdBu", reversescale=True), height=480)


def _monthly_heatmap(result: dict[str, Any]) -> go.Figure:
    equity = _series(result.get("equity"), "equity")
    if equity.empty:
        return go.Figure()
    monthly = equity.resample("ME").last().pct_change().dropna()
    if monthly.empty:
        return go.Figure()
    table = pd.DataFrame({"year": monthly.index.year, "month": monthly.index.month, "return": monthly.values}).pivot(index="year", columns="month", values="return")
    return _basic_figure(go.Heatmap(z=table.to_numpy(), x=[str(value) for value in table.columns], y=[str(value) for value in table.index], colorscale="RdYlGn", zmid=0), height=420)


def build_portfolio_export(datasets: list[dict[str, Any]], result: dict[str, Any], params: dict[str, Any], language: str = "zh") -> str:
    language = _language(language)
    stocks = [str(item["symbol"]) for item in datasets]
    report = build_multi_stock_export_html(
        title="多股组合策略报告" if language == "zh" else "Multi-stock Portfolio Strategy Report",
        compare_stocks=stocks,
        stock_data_dict={str(item["symbol"]): item["dataframe"] for item in datasets},
        comparison_stats=_comparison_stats(datasets),
        comparison_fig=_normalized_prices(datasets),
        rs_fig=None,
        risk_return_fig=None,
        factor_score_fig=None,
        corr_fig=_correlation(datasets),
        periodic_heatmap_fig=_monthly_heatmap(result),
        portfolio_result=_portfolio_payload(result),
        include_date=True,
        market=str(datasets[0].get("market") or "") if datasets else "",
        language=language,
        generated_at=datetime.now(),
    )
    params_rows = [{"parameter": key, "value": value} for key, value in params.items()]
    additions = _table_section("策略参数" if language == "zh" else "Strategy parameters", params_rows, language)
    return report.replace('<footer class="footer">', additions + '<footer class="footer">', 1)
