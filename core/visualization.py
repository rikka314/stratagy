"""
可视化模块
==========
多股票对比、相关性热图、相对强弱、风险收益散点、周期收益热图、因子评分对比。
"""

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.indicators import add_indicators
from core.signals import compute_signals
from ui.theme import apply_plotly_theme, get_plotly_theme_tokens


def _prepare_timeseries_frame(df: pd.DataFrame, required_columns: list[str]) -> pd.DataFrame:
    """统一清洗日期和数值列，避免多股票图表静默失效。"""
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()

    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["date"])
    prepared = prepared.sort_values("date")
    prepared = prepared.drop_duplicates(subset=["date"], keep="last")

    for column in required_columns:
        if column not in prepared.columns:
            return pd.DataFrame()
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    prepared = prepared.dropna(subset=required_columns)
    return prepared.reset_index(drop=True)


def _format_period_label(period_value: pd.Period, period: str) -> str:
    """统一格式化周期标签。"""
    if period == "Q":
        return f"{period_value.year}-Q{period_value.quarter}"
    return str(period_value)


def _prepare_return_series(series: pd.Series) -> pd.Series:
    """清洗收益率序列：索引转日期、值转数值，并按日期升序去重。"""
    prepared = pd.Series(series).copy()
    prepared.index = pd.to_datetime(prepared.index, errors="coerce")
    prepared = prepared[~prepared.index.isna()]
    prepared = prepared.sort_index()
    prepared = prepared[~prepared.index.duplicated(keep="last")]
    prepared = pd.to_numeric(prepared, errors="coerce")
    return prepared.dropna()


def _period_returns_from_price_frame(df: pd.DataFrame, period: str) -> pd.Series:
    """从价格序列计算周期收益率。"""
    prepared = _prepare_timeseries_frame(df, ["close"])
    if len(prepared) < 2:
        return pd.Series(dtype=float)

    period_alias = {"M": "M", "Q": "Q", "YE": "Y"}.get(period, "M")
    series = prepared.set_index("date")["close"].sort_index()
    grouped = series.groupby(series.index.to_period(period_alias))

    return grouped.apply(
        lambda values: (values.iloc[-1] / values.iloc[0] - 1) * 100 if len(values) > 1 else np.nan
    ).dropna()


def _period_returns_from_return_series(series: pd.Series, period: str) -> pd.Series:
    """从日收益率序列按复利汇总周期收益率。"""
    prepared = _prepare_return_series(series)
    if prepared.empty:
        return pd.Series(dtype=float)

    period_alias = {"M": "M", "Q": "Q", "YE": "Y"}.get(period, "M")
    grouped = prepared.groupby(prepared.index.to_period(period_alias))
    return grouped.apply(lambda values: ((1.0 + values).prod() - 1.0) * 100).dropna()


_FIXED_ANALYSIS_VIEWPORT_POINTS = 32
_PRICE_LOG_RATIO_THRESHOLD = 2.4
_INDICATOR_COMPRESSION_THRESHOLD = 5.0


def _analysis_font() -> str:
    return str(get_plotly_theme_tokens()["font_family"])


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """将十六进制颜色转换成 Plotly 可用的 rgba 字符串。"""
    color = str(hex_color or "").lstrip("#")
    if len(color) != 6:
        return f"rgba(47, 93, 98, {alpha})"
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _analysis_rangebreaks(period_key: str) -> list[dict[str, Any]]:
    """日 K 默认折叠周末空白，避免柱子被自然日间隔压细。"""
    if str(period_key).upper() == "D":
        return [dict(bounds=["sat", "mon"])]
    return []


def _nice_number(value: float) -> float:
    """把数值提升到人类更容易读的刻度。"""
    if not np.isfinite(value) or value <= 0:
        return 1.0
    exponent = np.floor(np.log10(value))
    fraction = value / (10 ** exponent)
    if fraction <= 1:
        nice_fraction = 1
    elif fraction <= 2:
        nice_fraction = 2
    elif fraction <= 5:
        nice_fraction = 5
    else:
        nice_fraction = 10
    return float(nice_fraction * (10 ** exponent))


def _format_axis_tick(value: float) -> str:
    """为压缩轴生成较紧凑的刻度文案。"""
    if not np.isfinite(value):
        return "N/A"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    if absolute >= 100:
        return f"{value:,.0f}"
    if absolute >= 10:
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    if absolute >= 1:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _identity_transform(values: pd.Series | np.ndarray | list[float]) -> np.ndarray:
    return np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype=float)


def _build_axis_transform(
    raw_series_list: list[pd.Series | np.ndarray | list[float]],
    *,
    positive_only: bool,
    threshold: float = _INDICATOR_COMPRESSION_THRESHOLD,
) -> tuple[callable, dict[str, Any], bool]:
    """为跨度过大的指标轴构建压缩显示变换。"""
    combined_chunks: list[np.ndarray] = []
    for series in raw_series_list:
        numeric = _identity_transform(series)
        numeric = numeric[np.isfinite(numeric)]
        if positive_only:
            numeric = numeric[numeric > 0]
        if numeric.size:
            combined_chunks.append(numeric)

    if not combined_chunks:
        return _identity_transform, {}, False

    combined = np.concatenate(combined_chunks)
    if positive_only:
        reference = float(np.nanpercentile(combined, 35))
        max_value = float(np.nanmax(combined))
        ratio = max_value / max(reference, 1e-9)
    else:
        magnitudes = np.abs(combined)
        reference = float(np.nanpercentile(magnitudes[magnitudes > 0], 35)) if np.any(magnitudes > 0) else 0.0
        max_value = float(np.nanmax(magnitudes))
        ratio = max_value / max(reference, 1e-9)

    if not np.isfinite(ratio) or ratio < threshold:
        return _identity_transform, {}, False

    scale = max(
        float(np.nanpercentile(combined, 60)) if positive_only else float(np.nanpercentile(np.abs(combined), 60)),
        1e-9,
    )

    def transform(values: pd.Series | np.ndarray | list[float]) -> np.ndarray:
        numeric = _identity_transform(values)
        return np.arcsinh(numeric / scale)

    if positive_only:
        axis_top = _nice_number(max_value)
        tick_raw = np.array(sorted({0.0, axis_top / 4, axis_top / 2, axis_top * 3 / 4, axis_top}))
    else:
        axis_top = _nice_number(max_value)
        tick_raw = np.array(sorted({-axis_top, -axis_top / 2, 0.0, axis_top / 2, axis_top}))

    tick_vals = transform(tick_raw)
    axis_config = dict(
        tickmode="array",
        tickvals=tick_vals.tolist(),
        ticktext=[_format_axis_tick(float(value)) for value in tick_raw],
    )
    return transform, axis_config, True


def _resolve_price_axis(
    chart_df: pd.DataFrame,
) -> tuple[str, str]:
    """长周期大涨幅股票默认使用对数价轴，减轻前段价格被压扁的问题。"""
    price_source = chart_df["low"] if "low" in chart_df.columns else chart_df["close"]
    low_series = _identity_transform(price_source)
    low_series = low_series[np.isfinite(low_series)]
    low_series = low_series[low_series > 0]
    high_series = _identity_transform(chart_df["high"] if "high" in chart_df.columns else chart_df["close"])
    high_series = high_series[np.isfinite(high_series)]
    if low_series.size == 0 or high_series.size == 0:
        return "价格", "linear"

    min_price = float(np.nanmin(low_series))
    max_price = float(np.nanmax(high_series))
    if min_price <= 0:
        return "价格", "linear"

    ratio = max_price / min_price
    if np.isfinite(ratio) and ratio >= _PRICE_LOG_RATIO_THRESHOLD:
        return "价格（对数）", "log"
    return "价格", "linear"


def create_empty_state_chart(message: str, *, height: int = 220) -> go.Figure:
    """统一的空状态图表。"""
    tokens = get_plotly_theme_tokens()
    fig = go.Figure()
    fig.update_layout(
        template="none",
        height=height,
        paper_bgcolor=tokens["paper_bg"],
        plot_bgcolor=tokens["plot_bg"],
        margin=dict(l=18, r=18, t=18, b=18),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(
                text=message,
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=14, color=tokens["muted_text"], family=_analysis_font()),
            )
        ],
    )
    return apply_plotly_theme(fig, height=height)


def style_analysis_figure(
    fig: go.Figure,
    *,
    height: int,
    margin: dict[str, int] | None = None,
) -> go.Figure:
    """统一分析页图表的暖白主题。"""
    fig = apply_plotly_theme(
        fig,
        height=height,
        margin=margin or dict(l=18, r=18, t=22, b=18),
        hovermode="x unified",
    )
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0.01,
        ),
        font=dict(size=12),
    )
    fig.update_xaxes(
        showgrid=True,
        zeroline=False,
        showline=False,
    )
    fig.update_yaxes(
        showgrid=True,
        zeroline=False,
    )
    return fig


def compute_chart_view_range(
    chart_df: pd.DataFrame,
    period_key: str,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """固定默认可视柱宽，超出部分交给底部 rangeslider 浏览。"""
    if chart_df.empty or "date" not in chart_df.columns:
        return None

    _ = period_key
    date_index = pd.Series(pd.to_datetime(chart_df["date"], errors="coerce")).dropna().reset_index(drop=True)
    if len(date_index) <= _FIXED_ANALYSIS_VIEWPORT_POINTS:
        return None

    start = date_index.iloc[-_FIXED_ANALYSIS_VIEWPORT_POINTS]
    end = date_index.iloc[-1]
    return (start, end)


def compute_drawdown_series(equity_series: pd.Series) -> pd.Series:
    """将净值曲线转换为逐日回撤序列。"""
    equity = pd.Series(equity_series).copy()
    equity.index = pd.to_datetime(equity.index, errors="coerce")
    equity = equity[~equity.index.isna()]
    equity = equity.sort_index()
    equity = equity[~equity.index.duplicated(keep="last")]
    equity = pd.to_numeric(equity, errors="coerce").dropna()
    if equity.empty:
        return equity
    return equity / equity.cummax() - 1.0


def create_candlestick_chart(
    *,
    chart_df: pd.DataFrame,
    symbol: str,
    period_key: str,
    split_date: pd.Timestamp | None,
    height: int = 520,
) -> go.Figure:
    """共享的 K 线主图组件。"""
    if chart_df.empty:
        return create_empty_state_chart("暂无可展示的 K 线数据。", height=height)

    tokens = get_plotly_theme_tokens()
    price_axis_title, price_axis_type = _resolve_price_axis(chart_df)
    candle = go.Figure()
    candle.add_trace(
        go.Candlestick(
            x=chart_df["date"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name=symbol,
            showlegend=False,
            increasing_line_color=tokens["market_up"],
            increasing_fillcolor=tokens["market_up"],
            decreasing_line_color=tokens["market_down"],
            decreasing_fillcolor=tokens["market_down"],
            whiskerwidth=0.35,
        )
    )
    if "ema_fast" in chart_df.columns and not chart_df["ema_fast"].isna().all():
        candle.add_trace(
            go.Scatter(
                x=chart_df["date"],
                y=chart_df["ema_fast"],
                name="EMA 快线",
                line=dict(color=tokens["accent_warm"], width=1.55),
            )
        )
    if "ema_slow" in chart_df.columns and not chart_df["ema_slow"].isna().all():
        candle.add_trace(
            go.Scatter(
                x=chart_df["date"],
                y=chart_df["ema_slow"],
                name="EMA 慢线",
                line=dict(color=tokens["accent_primary"], width=1.4),
            )
        )

    candle.update_xaxes(
        title="日期",
        rangeslider=dict(
            visible=True,
            thickness=0.08,
            bgcolor=tokens["legend_bg"],
            yaxis=dict(rangemode="auto"),
        ),
        rangebreaks=_analysis_rangebreaks(period_key),
    )
    candle.update_yaxes(title=price_axis_title, type=price_axis_type)
    style_analysis_figure(candle, height=height)
    visible_range = compute_chart_view_range(chart_df, period_key)
    if visible_range is not None:
        candle.update_xaxes(range=list(visible_range))

    if split_date is not None:
        split_ts = pd.to_datetime(split_date, errors="coerce")
        if not pd.isna(split_ts):
            min_date = pd.to_datetime(chart_df["date"].min(), errors="coerce")
            max_date = pd.to_datetime(chart_df["date"].max(), errors="coerce")
            if pd.notna(min_date) and pd.notna(max_date) and min_date < split_ts < max_date:
                candle.add_shape(
                    type="line",
                    x0=split_ts,
                    x1=split_ts,
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    line=dict(
                        dash="dot",
                        color=tokens["accent_warm"],
                        width=1.2,
                    ),
                )
                candle.add_annotation(
                    x=split_ts,
                    y=1.02,
                    xref="x",
                    yref="paper",
                    text=f"{ {'D': '日', 'W': '周', 'M': '月'}.get(period_key, '日') }K 训练截止",
                    showarrow=False,
                    xanchor="left",
                    yanchor="bottom",
                    font=dict(size=11, color=tokens["font_color"], family=_analysis_font()),
                    bgcolor=tokens["annotation_bg"],
                    bordercolor=tokens["annotation_border"],
                    borderpad=4,
                )

    return candle


def create_candlestick_indicator_chart(
    *,
    chart_df: pd.DataFrame,
    symbol: str,
    period_key: str,
    split_date: pd.Timestamp | None,
    indicator_view: str,
    rsi_upper: float,
    rsi_lower: float,
    height: int = 780,
) -> go.Figure:
    """共享的 K 线主图 + 指标小图联动图组件。"""
    if chart_df.empty:
        return create_empty_state_chart("暂无可展示的行情与指标数据。", height=height)

    tokens = get_plotly_theme_tokens()
    price_axis_title, price_axis_type = _resolve_price_axis(chart_df)
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_df["date"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name=symbol,
            showlegend=False,
            increasing_line_color=tokens["market_up"],
            increasing_fillcolor=tokens["market_up"],
            decreasing_line_color=tokens["market_down"],
            decreasing_fillcolor=tokens["market_down"],
            whiskerwidth=0.35,
        )
    )
    if "ema_fast" in chart_df.columns and not chart_df["ema_fast"].isna().all():
        fig.add_trace(
            go.Scatter(
                x=chart_df["date"],
                y=chart_df["ema_fast"],
                name="EMA 快线",
                line=dict(color=tokens["accent_warm"], width=1.55),
            )
        )
    if "ema_slow" in chart_df.columns and not chart_df["ema_slow"].isna().all():
        fig.add_trace(
            go.Scatter(
                x=chart_df["date"],
                y=chart_df["ema_slow"],
                name="EMA 慢线",
                line=dict(color=tokens["accent_primary"], width=1.4),
            )
        )

    indicator_axis_title = {"MACD": "MACD", "RSI": "RSI", "VOL": "成交量"}.get(indicator_view, "指标")
    indicator_axis_config: dict[str, Any] = {}
    indicator_note = ""
    if indicator_view == "RSI":
        if "rsi" not in chart_df.columns or chart_df["rsi"].isna().all():
            indicator_note = "当前周期下没有可用的 RSI 指标。"
        else:
            fig.add_trace(
                go.Scatter(
                    x=chart_df["date"],
                    y=chart_df["rsi"],
                    name="RSI",
                    yaxis="y2",
                    line=dict(color=tokens["muted_text"], width=1.8),
                )
            )
            fig.add_shape(
                type="line",
                x0=0,
                x1=1,
                xref="paper",
                y0=rsi_upper,
                y1=rsi_upper,
                yref="y2",
                line=dict(dash="dash", color=tokens["market_up"], width=1.1),
            )
            fig.add_shape(
                type="line",
                x0=0,
                x1=1,
                xref="paper",
                y0=rsi_lower,
                y1=rsi_lower,
                yref="y2",
                line=dict(dash="dash", color=tokens["market_down"], width=1.1),
            )
    elif indicator_view == "VOL":
        if "volume" not in chart_df.columns or chart_df["volume"].isna().all():
            indicator_note = "当前周期下没有可用的成交量数据。"
        else:
            transform, indicator_axis_config, is_compressed = _build_axis_transform(
                [chart_df["volume"]],
                positive_only=True,
            )
            if is_compressed:
                indicator_axis_title = "成交量（压缩）"
            volume_colors = np.where(
                chart_df["close"] >= chart_df["open"],
                _hex_to_rgba(str(tokens["market_up"]), 0.72),
                _hex_to_rgba(str(tokens["market_down"]), 0.72),
            )
            volume_values = _identity_transform(chart_df["volume"])
            fig.add_trace(
                go.Bar(
                    x=chart_df["date"],
                    y=transform(volume_values),
                    name="成交量",
                    yaxis="y2",
                    marker_color=volume_colors,
                    customdata=volume_values,
                    hovertemplate="<b>成交量</b><br>日期: %{x|%Y-%m-%d}<br>数值: %{customdata:,.0f}<extra></extra>",
                )
            )
    else:
        required = {"macd", "signal", "histogram"}
        if not required.issubset(chart_df.columns) or chart_df[list(required)].isna().all().all():
            indicator_note = "当前周期下没有可用的 MACD 指标。"
        else:
            transform, indicator_axis_config, is_compressed = _build_axis_transform(
                [chart_df["macd"], chart_df["signal"], chart_df["histogram"]],
                positive_only=False,
            )
            if is_compressed:
                indicator_axis_title = "MACD（压缩）"
            histogram_colors = np.where(
                chart_df["histogram"] >= 0,
                _hex_to_rgba(str(tokens["market_down"]), 0.62),
                _hex_to_rgba(str(tokens["market_up"]), 0.58),
            )
            histogram_values = _identity_transform(chart_df["histogram"])
            macd_values = _identity_transform(chart_df["macd"])
            signal_values = _identity_transform(chart_df["signal"])
            fig.add_trace(
                go.Bar(
                    x=chart_df["date"],
                    y=transform(histogram_values),
                    name="Histogram",
                    yaxis="y2",
                    marker_color=histogram_colors,
                    customdata=histogram_values,
                    hovertemplate="<b>Histogram</b><br>日期: %{x|%Y-%m-%d}<br>数值: %{customdata:.3f}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=chart_df["date"],
                    y=transform(macd_values),
                    name="MACD",
                    yaxis="y2",
                    line=dict(color=tokens["accent_warm"], width=1.7),
                    customdata=macd_values,
                    hovertemplate="<b>MACD</b><br>日期: %{x|%Y-%m-%d}<br>数值: %{customdata:.3f}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=chart_df["date"],
                    y=transform(signal_values),
                    name="Signal",
                    yaxis="y2",
                    line=dict(color=tokens["accent_primary"], width=1.45),
                    customdata=signal_values,
                    hovertemplate="<b>Signal</b><br>日期: %{x|%Y-%m-%d}<br>数值: %{customdata:.3f}<extra></extra>",
                )
            )

    indicator_yaxis = dict(title=indicator_axis_title, domain=[0.0, 0.22], anchor="x")
    indicator_yaxis.update(indicator_axis_config)
    fig.update_layout(
        yaxis=dict(title=price_axis_title, type=price_axis_type, domain=[0.34, 1.0]),
        yaxis2=indicator_yaxis,
        xaxis=dict(
            title="日期",
            rangeslider=dict(
                visible=True,
                thickness=0.08,
                bgcolor=tokens["legend_bg"],
                yaxis=dict(rangemode="auto"),
            ),
            rangebreaks=_analysis_rangebreaks(period_key),
        ),
    )
    style_analysis_figure(fig, height=height, margin=dict(l=60, r=30, t=40, b=55))

    visible_range = compute_chart_view_range(chart_df, period_key)
    if visible_range is not None:
        fig.update_xaxes(range=list(visible_range))

    if split_date is not None:
        split_ts = pd.to_datetime(split_date, errors="coerce")
        if not pd.isna(split_ts):
            min_date = pd.to_datetime(chart_df["date"].min(), errors="coerce")
            max_date = pd.to_datetime(chart_df["date"].max(), errors="coerce")
            if pd.notna(min_date) and pd.notna(max_date) and min_date < split_ts < max_date:
                fig.add_shape(
                    type="line",
                    x0=split_ts,
                    x1=split_ts,
                    y0=0.34,
                    y1=1.0,
                    xref="x",
                    yref="paper",
                    line=dict(
                        dash="dot",
                        color=tokens["accent_warm"],
                        width=1.2,
                    ),
                )
                fig.add_annotation(
                    x=split_ts,
                    y=1.02,
                    xref="x",
                    yref="paper",
                    text=f"{ {'D': '日', 'W': '周', 'M': '月'}.get(period_key, '日') }K 训练截止",
                    showarrow=False,
                    xanchor="left",
                    yanchor="bottom",
                    font=dict(size=11, color=tokens["font_color"], family=_analysis_font()),
                    bgcolor=tokens["annotation_bg"],
                    bordercolor=tokens["annotation_border"],
                    borderpad=4,
                )

    if indicator_note:
        fig.add_annotation(
            x=0.5,
            y=0.1,
            xref="paper",
            yref="paper",
            text=indicator_note,
            showarrow=False,
            font=dict(size=13, color=tokens["muted_text"], family=_analysis_font()),
            bgcolor=tokens["annotation_bg"],
            bordercolor=tokens["annotation_border"],
            borderpad=6,
        )
        fig.update_layout(
            yaxis=dict(title=price_axis_title, type=price_axis_type, domain=[0.34, 1.0]),
            yaxis2=dict(title="", domain=[0.0, 0.22], anchor="x", showgrid=False, visible=False),
        )

    return fig


def create_equity_drawdown_chart(
    series_specs: list[dict[str, Any]],
    *,
    height: int = 620,
    subplot_titles: tuple[str, str] = ("净值曲线", "回撤曲线"),
    equity_axis_title: str = "净值（起始=1.0）",
    drawdown_axis_title: str = "回撤",
) -> go.Figure:
    """共享的净值 / 回撤双子图组件。"""
    prepared_specs: list[dict[str, Any]] = []
    for spec in series_specs:
        series = pd.Series(spec.get("series")).copy()
        series.index = pd.to_datetime(series.index, errors="coerce")
        series = series[~series.index.isna()]
        series = series.sort_index()
        series = series[~series.index.duplicated(keep="last")]
        series = pd.to_numeric(series, errors="coerce").dropna()
        if series.empty:
            continue

        prepared_specs.append(
            {
                "name": str(spec.get("name") or "策略"),
                "hover_name": str(spec.get("hover_name") or spec.get("name") or "策略"),
                "series": series,
                "color": str(spec.get("color") or "#ba7349"),
                "dash": str(spec.get("dash") or "solid"),
                "width": spec.get("width"),
                "fill_alpha": float(spec.get("fill_alpha", 0.18)),
                "drawdown_fill": bool(spec.get("drawdown_fill", True)),
                "showlegend": bool(spec.get("showlegend", True)),
            }
        )

    if not prepared_specs:
        return create_empty_state_chart("暂无可展示的净值与回撤数据。", height=height)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.68, 0.32],
        subplot_titles=subplot_titles,
    )

    for spec in prepared_specs:
        series = spec["series"]
        drawdown = compute_drawdown_series(series)
        dash = spec["dash"]
        line_width = (
            float(spec["width"])
            if spec["width"] is not None
            else (2.6 if dash == "solid" else 2.0)
        )
        fill_mode = "tozeroy" if spec["drawdown_fill"] else None
        fill_color = _hex_to_rgba(spec["color"], spec["fill_alpha"]) if spec["drawdown_fill"] else "rgba(0, 0, 0, 0)"

        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series.values,
                mode="lines",
                name=spec["name"],
                legendgroup=spec["name"],
                showlegend=spec["showlegend"],
                line=dict(color=spec["color"], width=line_width, dash=dash),
                hovertemplate=(
                    f"<b>{spec['hover_name']}</b><br>"
                    "日期: %{x|%Y-%m-%d}<br>"
                    "净值: %{y:.3f}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=drawdown.index,
                y=drawdown.values,
                mode="lines",
                name=f"{spec['name']} 回撤",
                legendgroup=spec["name"],
                showlegend=False,
                line=dict(color=spec["color"], width=max(1.3, line_width - 0.9), dash=dash),
                fill=fill_mode,
                fillcolor=fill_color,
                hovertemplate=(
                    f"<b>{spec['hover_name']}</b><br>"
                    "日期: %{x|%Y-%m-%d}<br>"
                    "回撤: %{y:.2%}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    style_analysis_figure(fig, height=height, margin=dict(l=60, r=30, t=70, b=50))
    fig.update_yaxes(title_text=equity_axis_title, row=1, col=1)
    fig.update_yaxes(title_text=drawdown_axis_title, tickformat=".0%", zeroline=True, row=2, col=1)
    fig.update_xaxes(title_text="日期", row=2, col=1)
    return fig


# ──────────────────────────────────────────────────────────────
# 1) 多股票归一化价格对比
# ──────────────────────────────────────────────────────────────
def create_multi_stock_comparison_chart(stock_data_dict: dict, title: str = "多股票价格对比（归一化）") -> go.Figure:
    """
    创建多股票归一化价格对比的交互式图表
    
    Parameters:
    -----------
    stock_data_dict : dict
        {股票代码: DataFrame} 字典
    title : str
        图表标题
    
    Returns:
    --------
    go.Figure
        Plotly 图表对象
    """
    fig = go.Figure()
    
    # 颜色方案 - 使用专业的配色
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    for idx, (symbol, df) in enumerate(stock_data_dict.items()):
        if df is None or df.empty:
            continue
        
        # 归一化价格（起点=100）
        normalized_price = (df['close'] / df['close'].iloc[0]) * 100
        
        # 计算收益率用于hover显示
        total_return = ((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100
        
        # 添加轨迹
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=normalized_price,
            mode='lines',
            name=f'{symbol} ({total_return:+.1f}%)',
            line=dict(color=colors[idx % len(colors)], width=2.5),
            hovertemplate=(
                f'<b>{symbol}</b><br>' +
                '日期: %{x|%Y-%m-%d}<br>' +
                '归一化价格: %{y:.2f}<br>' +
                f'期间收益: {total_return:+.2f}%<br>' +
                '<extra></extra>'
            ),
            legendgroup=symbol,
            showlegend=True,
        ))
    
    # 添加基准线（起点）
    if stock_data_dict:
        first_date = list(stock_data_dict.values())[0]['date'].iloc[0]
        last_date = list(stock_data_dict.values())[0]['date'].iloc[-1]
        
        fig.add_hline(
            y=100,
            line_dash="dash",
            line_color="gray",
            opacity=0.5,
            annotation_text="起点基准 (100)",
            annotation_position="right"
        )
    
    # 更新布局 - 专业金融风格
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=22, color='#2c3e50', family='Arial Black'),
            x=0.5,
            xanchor='center',
            y=0.98,
            yanchor='top'
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True,
            gridcolor='#ecf0f1',
            gridwidth=0.5,
            rangeslider=dict(
                visible=True,
                thickness=0.05,
                bgcolor='#f8f9fa',
                bordercolor='#bdc3c7',
                borderwidth=1
            ),
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1周", step="day", stepmode="backward"),
                    dict(count=1, label="1月", step="month", stepmode="backward"),
                    dict(count=3, label="3月", step="month", stepmode="backward"),
                    dict(count=6, label="6月", step="month", stepmode="backward"),
                    dict(count=1, label="1年", step="year", stepmode="backward"),
                    dict(step="all", label="全部"),
                ]),
                bgcolor='#ecf0f1',
                activecolor='#3498db',
                font=dict(size=10),
                x=0,
                y=1.05,
                xanchor='left',
                yanchor='top'
            ),
        ),
        yaxis=dict(
            title='归一化价格（起点=100）',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True,
            gridcolor='#ecf0f1',
            gridwidth=0.5,
            zeroline=True,
            zerolinecolor='#95a5a6',
            zerolinewidth=1.5,
            tickformat='.1f',
        ),
        hovermode='x unified',
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=650,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(255,255,255,0.95)',
            bordercolor='#bdc3c7',
            borderwidth=1.5,
            font=dict(size=11),
            title=dict(text='股票（期间收益）', font=dict(size=12, color='#2c3e50'))
        ),
        margin=dict(l=70, r=40, t=100, b=60),
        font=dict(family='Arial, sans-serif'),
    )
    
    return apply_plotly_theme(fig, height=650, margin=dict(l=70, r=40, t=100, b=60))


# ──────────────────────────────────────────────────────────────
# 2) 相关性热图
# ──────────────────────────────────────────────────────────────
def create_correlation_heatmap(stock_data_dict: dict) -> go.Figure:
    """创建股票收益率相关性热图，按股票配对独立计算共同样本。"""

    returns_series = {}
    for symbol, df in stock_data_dict.items():
        prepared = _prepare_timeseries_frame(df, ["close"])
        if len(prepared) <= 1:
            continue
        returns = prepared.set_index("date")["close"].pct_change().dropna()
        if not returns.empty:
            returns_series[symbol] = returns

    if len(returns_series) < 2:
        return None

    returns_df = pd.concat(returns_series, axis=1)
    common_counts = returns_df.notna().astype(int).T.dot(returns_df.notna().astype(int))
    min_pair_days = 5
    corr_matrix = returns_df.corr(min_periods=min_pair_days)

    if corr_matrix.empty:
        return None

    off_diagonal_mask = ~np.eye(len(corr_matrix), dtype=bool)
    valid_pair_mask = off_diagonal_mask & corr_matrix.notna().values
    if not valid_pair_mask.any():
        return None

    annotations_text = []
    for i in range(len(corr_matrix)):
        row_text = []
        for j in range(len(corr_matrix.columns)):
            corr_val = corr_matrix.iloc[i, j]
            if pd.isna(corr_val):
                row_text.append("")
            elif i == j:
                row_text.append(f"{corr_val:.2f}")
            else:
                row_text.append(f"{corr_val:.3f}")
        annotations_text.append(row_text)

    pair_counts = common_counts.reindex(index=corr_matrix.index, columns=corr_matrix.columns)

    x_labels = [str(label) for label in corr_matrix.columns.tolist()]
    y_labels = [str(label) for label in corr_matrix.index.tolist()]

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=x_labels,
        y=y_labels,
        colorscale=[
            [0.0, '#d73027'],      # 深红色 (-1)
            [0.25, '#fc8d59'],     # 橙红色 (-0.5)
            [0.5, '#f7f7f7'],      # 白色 (0)
            [0.75, '#91bfdb'],     # 浅蓝色 (0.5)
            [1.0, '#4575b4']       # 深蓝色 (1)
        ],
        zmid=0,
        zmin=-1,
        zmax=1,
        text=annotations_text,
        texttemplate="%{text}",
        textfont={"size": 14, "color": "#1f2933", "family": "Arial Black"},
        customdata=pair_counts.values,
        colorbar=dict(
            title=dict(
                text="相关系数",
                font=dict(size=13, color='#2c3e50'),
                side="right"
            ),
            tickmode="linear",
            tick0=-1,
            dtick=0.25,
            tickfont=dict(size=11),
            len=0.8,
            thickness=15,
        ),
        hovertemplate=(
            "<b>%{y} vs %{x}</b><br>"
            "相关系数: %{z:.4f}<br>"
            "共同交易日: %{customdata:.0f}<br>"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        title=dict(
            text="股票收益率相关性矩阵（按股票配对计算）",
            font=dict(size=18, color="#2c3e50", family="Arial Black"),
            x=0.5,
            xanchor="center",
            y=0.95,
            yanchor="top",
        ),
        xaxis=dict(
            title="",
            side="bottom",
            tickfont=dict(size=12, color="#2c3e50"),
            showgrid=False,
            type="category",
            categoryorder="array",
            categoryarray=x_labels,
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=12, color="#2c3e50"),
            showgrid=False,
            type="category",
            categoryorder="array",
            categoryarray=y_labels,
        ),
        height=550,
        width=None,  # 自适应宽度
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        margin=dict(l=100, r=100, t=100, b=80),
    )
    
    # 添加说明文本
    fig.add_annotation(
        text="💡 提示：接近1表示正相关，接近-1表示负相关，接近0表示无相关性",
        xref="paper", yref="paper",
        x=0.5, y=-0.12,
        xanchor="center", yanchor="top",
        showarrow=False,
        font=dict(size=11, color="#7f8c8d", family="Arial"),
    )

    return apply_plotly_theme(fig, height=550, margin=dict(l=100, r=100, t=100, b=80))


# ──────────────────────────────────────────────────────────────
# 3) 相对强弱对比
# ──────────────────────────────────────────────────────────────
def create_relative_strength_chart(stock_data_dict: dict, benchmark: str = "equal_weight") -> go.Figure:
    """
    创建相对强弱对比图（Relative Strength Comparison）

    【原理说明】
    相对强弱指标（RS）= 个股归一化价格 / 基准归一化价格。
    - RS 曲线上升 → 该股票跑赢基准（即使股价本身在跌，只要跌得比基准少也算跑赢）
    - RS 曲线下降 → 该股票跑输基准
    - RS = 1.0 水平线表示与基准持平

    【对决策的影响】
    动量交易者倾向于买入相对强势的股票、回避相对弱势的股票。
    通过 RS 曲线可以清晰地看到资金应该往哪个方向分配。

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        benchmark: 基准模式，"equal_weight"=所有股票等权平均，或指定某只股票代码

    返回：
        Plotly 图表对象，失败返回 None
    """
    if len(stock_data_dict) < 2:
        return None

    # 步骤1：构建各股票的归一化收盘价序列（起点=1.0），按日期对齐
    norm_series = {}
    for sym, df in stock_data_dict.items():
        if df is None or len(df) < 2 or 'close' not in df.columns:
            continue
        s = df.set_index('date')['close'].sort_index()
        s = s / s.iloc[0]  # 归一化到起点=1.0
        norm_series[sym] = s

    if len(norm_series) < 2:
        return None

    # 合并成 DataFrame，日期对齐（取交集）
    norm_df = pd.DataFrame(norm_series)
    norm_df = norm_df.dropna()

    if len(norm_df) < 2:
        return None

    # 步骤2：计算基准
    if benchmark == "equal_weight" or benchmark not in norm_df.columns:
        benchmark_series = norm_df.mean(axis=1)  # 等权平均
        benchmark_label = "等权平均基准"
    else:
        benchmark_series = norm_df[benchmark]
        benchmark_label = f"{benchmark} 基准"

    # 步骤3：计算相对强弱 RS = 个股 / 基准
    rs_df = norm_df.div(benchmark_series, axis=0)

    # 步骤4：绘图
    # 使用与项目一致的配色
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#636efa', '#ef553b', '#00cc96', '#ab63fa', '#ffa15a',
    ]

    fig = go.Figure()

    for i, sym in enumerate(rs_df.columns):
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=rs_df.index,
            y=rs_df[sym],
            name=sym,
            mode='lines',
            line=dict(color=color, width=2),
            hovertemplate=(
                f'<b>{sym}</b><br>'
                '日期: %{x|%Y-%m-%d}<br>'
                '相对强弱: %{y:.4f}<br>'
                '<extra></extra>'
            ),
        ))

    # 添加基准线 RS=1.0
    fig.add_hline(
        y=1.0,
        line_dash='dash',
        line_color='rgba(128,128,128,0.6)',
        line_width=1.5,
        annotation_text='基准线 (RS=1.0)',
        annotation_position='top right',
        annotation_font=dict(size=11, color='#7f8c8d'),
    )

    fig.update_layout(
        title=dict(
            text=f'相对强弱对比（基准: {benchmark_label}）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#f0f0f0',
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            title='相对强弱 (RS)',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            hoverformat='.4f',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=500,
        margin=dict(l=60, r=60, t=80, b=80),
        legend=dict(
            orientation='h',
            yanchor='bottom', y=-0.25,
            xanchor='center', x=0.5,
            font=dict(size=12),
        ),
        hovermode='x unified',
    )

    # 底部注释
    fig.add_annotation(
        text=f'RS > 1.0 表示跑赢{benchmark_label}，RS < 1.0 表示跑输{benchmark_label}',
        xref='paper', yref='paper',
        x=0.5, y=-0.32,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=11, color='#7f8c8d', family='Arial'),
    )

    return apply_plotly_theme(fig, height=500, margin=dict(l=60, r=60, t=80, b=80))


# ──────────────────────────────────────────────────────────────
# 4) 风险收益散点图
# ──────────────────────────────────────────────────────────────
def create_risk_return_scatter(stock_data_dict: dict) -> go.Figure:
    """
    创建风险收益散点图（Risk-Return Scatter Plot）
    
    【原理说明】
    风险收益散点图是现代投资组合理论（MPT）中最基础的可视化工具：
    - 横轴：年化波动率（衡量风险，波动越大风险越高）
    - 纵轴：年化收益率（衡量回报）
    - 理想标的位于左上角（高收益 + 低风险）
    - 劣质标的位于右下角（低收益 + 高风险）
    
    【计算方法】
    - 年化收益率 = (1 + 总收益率) ^ (252 / 交易天数) - 1
    - 年化波动率 = 日收益率标准差 × √252
    - 夏普比率 = 年化收益率 / 年化波动率（简化版，无风险利率设为0）
    
    【对决策的影响】
    帮助投资者在多只股票中快速识别风险收益特征最优的标的，
    支持资产配置决策。
    
    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
    
    返回：
        Plotly 散点图对象，失败返回 None
    """
    
    symbols = []
    ann_returns = []    # 年化收益率（百分比）
    ann_vols = []       # 年化波动率（百分比）
    sharpe_ratios = []  # 夏普比率
    
    for symbol, df in stock_data_dict.items():
        if df is None or len(df) < 2:
            continue
        
        try:
            # 计算日收益率
            daily_returns = df['close'].pct_change().dropna()
            if daily_returns.empty:
                continue
            
            # 计算年化收益率（假设一年 252 个交易日）
            total_return = df['close'].iloc[-1] / df['close'].iloc[0] - 1
            trading_days = len(df)
            
            # 安全检查：total_return 不能 <= -1（否则底数为负，幂运算出错）
            if total_return <= -1:
                annualized_return = -0.99  # 钳位到 -99%，避免数学错误
            else:
                annualized_return = (1 + total_return) ** (252 / trading_days) - 1
            
            # 计算年化波动率
            annualized_volatility = daily_returns.std() * np.sqrt(252)
            
            # 计算夏普比率（简化版，无风险利率 = 0）
            if annualized_volatility > 0:
                sr = annualized_return / annualized_volatility
            else:
                sr = 0.0
            
            symbols.append(symbol)
            ann_returns.append(annualized_return * 100)
            ann_vols.append(annualized_volatility * 100)
            sharpe_ratios.append(round(sr, 2))
            
        except Exception:
            # 跳过计算失败的股票，不影响其他股票
            continue
    
    if not symbols:
        return None
    
    fig = go.Figure()
    
    # 添加散点（hover 包含夏普比率）
    fig.add_trace(go.Scatter(
        x=ann_vols,
        y=ann_returns,
        mode='markers+text',
        text=symbols,
        textposition='top center',
        marker=dict(
            size=15,
            color=sharpe_ratios,      # 颜色映射到夏普比率
            colorscale='RdYlGn',      # 红（差）→ 黄 → 绿（好）
            showscale=True,
            colorbar=dict(title='夏普比率'),
            line=dict(width=1.5, color='DarkSlateGrey'),
        ),
        customdata=np.column_stack([sharpe_ratios]),
        hovertemplate=(
            '<b>%{text}</b><br>'
            '年化波动率 (风险): %{x:.2f}%<br>'
            '年化收益率 (回报): %{y:.2f}%<br>'
            '夏普比率: %{customdata[0]:.2f}<br>'
            '<extra></extra>'
        ),
    ))
    
    # 添加象限辅助线（以中位数为界）
    if len(ann_vols) > 1:
        median_vol = np.median(ann_vols)
        median_ret = np.median(ann_returns)
        
        fig.add_vline(x=median_vol, line_dash='dash', line_color='gray', opacity=0.5)
        fig.add_hline(y=median_ret, line_dash='dash', line_color='gray', opacity=0.5)
        
        # 象限标注
        min_vol, max_vol = min(ann_vols), max(ann_vols)
        min_ret, max_ret = min(ann_returns), max(ann_returns)
        
        fig.add_annotation(
            x=min_vol, y=max_ret, text='⭐ 高收益低风险',
            showarrow=False, font=dict(color='green', size=11),
            xanchor='left', yanchor='top', bgcolor='rgba(255,255,255,0.8)',
        )
        fig.add_annotation(
            x=max_vol, y=min_ret, text='⚠️ 低收益高风险',
            showarrow=False, font=dict(color='red', size=11),
            xanchor='right', yanchor='bottom', bgcolor='rgba(255,255,255,0.8)',
        )
    
    fig.update_layout(
        title=dict(
            text='风险-收益散点图（年化）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='年化波动率（风险）%',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1', zeroline=False,
        ),
        yaxis=dict(
            title='年化收益率（回报）%',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            zeroline=True, zerolinecolor='#95a5a6',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=550,
        margin=dict(l=80, r=80, t=80, b=80),
    )

    return apply_plotly_theme(fig, height=550, margin=dict(l=80, r=80, t=80, b=80))


# ──────────────────────────────────────────────────────────────
# 5) 周期收益率热图
# ──────────────────────────────────────────────────────────────
def create_periodic_returns_heatmap(
    stock_data_dict: dict | None = None,
    period: str = "M",
    returns_series: pd.Series | dict[str, pd.Series] | None = None,
) -> go.Figure:
    """
    创建周期收益率热图（Periodic Returns Heatmap）

    【原理说明】
    支持两种输入模式：
    - `stock_data_dict`：按月/季度/年展示每只股票基于收盘价的周期收益率
    - `returns_series`：按月/季度/年展示一个或多个收益率序列的复利周期收益率

    热图结构：
    - 行 = 股票代码 / 策略名称
    - 列 = 时间周期
    - 颜色红绿色阶：绿=盈利，红=亏损

    【对决策的影响】
    帮助发现股票或策略在不同月份/季度/年度中的表现差异。

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典（可选）
        period: 时间周期，"M"=月度，"Q"=季度，"YE"=年度
        returns_series: 单个收益率序列，或 {名称: 收益率序列} 字典（可选）

    返回：
        Plotly 热图对象，失败返回 None
    """
    if not stock_data_dict and returns_series is None:
        return None

    period_labels = {"M": "月度", "Q": "季度", "YE": "年度"}
    all_returns = {}
    y_axis_title = "股票"
    title_prefix = "股票"

    if returns_series is not None:
        series_dict = (
            returns_series
            if isinstance(returns_series, dict)
            else {"策略收益": returns_series}
        )
        y_axis_title = "策略/模型"
        title_prefix = "策略"

        for name, series in series_dict.items():
            if series is None:
                continue
            period_returns = _period_returns_from_return_series(series, period)
            if period_returns.empty:
                continue
            labels = [_format_period_label(period_value, period) for period_value in period_returns.index]
            all_returns[str(name)] = pd.Series(period_returns.values, index=labels)
    else:
        for sym, df in stock_data_dict.items():
            period_returns = _period_returns_from_price_frame(df, period)
            if period_returns.empty:
                continue
            labels = [_format_period_label(period_value, period) for period_value in period_returns.index]
            all_returns[sym] = pd.Series(period_returns.values, index=labels)

    if not all_returns:
        return None

    returns_df = pd.DataFrame(all_returns).T

    max_cols = 24
    if returns_df.shape[1] > max_cols:
        returns_df = returns_df.iloc[:, -max_cols:]

    numeric_values = returns_df.to_numpy(dtype=float)
    finite_values = numeric_values[np.isfinite(numeric_values)]
    if finite_values.size == 0:
        return None

    text_matrix = returns_df.map(lambda x: f"{x:.1f}%" if pd.notna(x) else "")
    z_limit = float(np.nanmax(np.abs(finite_values))) if finite_values.size else 1.0
    z_limit = max(z_limit, 1.0)

    x_labels = [str(label) for label in returns_df.columns.tolist()]
    y_labels = [str(label) for label in returns_df.index.tolist()]

    fig = go.Figure(data=go.Heatmap(
        z=returns_df.values,
        x=x_labels,
        y=y_labels,
        text=text_matrix.values,
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorscale=[
            [0.0, '#d32f2f'],    # 深红（大亏）
            [0.3, '#ef5350'],    # 红
            [0.45, '#ffcdd2'],   # 浅红
            [0.5, '#ffffff'],    # 白（零点）
            [0.55, '#c8e6c9'],   # 浅绿
            [0.7, '#66bb6a'],    # 绿
            [1.0, '#2e7d32'],    # 深绿（大涨）
        ],
        zmid=0,
        zmin=-z_limit,
        zmax=z_limit,
        colorbar=dict(
            title=dict(text="收益率(%)", side="right"),
            ticksuffix="%",
            len=0.8,
        ),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "周期: %{x}<br>"
            "收益率: %{z:.2f}%<br>"
            "<extra></extra>"
        ),
    ))

    period_name = period_labels.get(period, "月度")

    fig.update_layout(
        title=dict(
            text=f'{title_prefix}{period_name}收益率热图',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='时间周期',
            title_font=dict(size=14, color='#34495e'),
            tickangle=-45,
            tickfont=dict(size=10),
            side='bottom',
            type="category",
            categoryorder="array",
            categoryarray=x_labels,
        ),
        yaxis=dict(
            title=y_axis_title,
            title_font=dict(size=14, color='#34495e'),
            tickfont=dict(size=12, color='#2c3e50', family='Arial Black'),
            autorange='reversed',  # 第一只股票在顶部
            type="category",
            categoryorder="array",
            categoryarray=y_labels,
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=max(300, 80 * len(returns_df) + 150),  # 动态高度
        margin=dict(l=80, r=80, t=80, b=120),
    )

    return apply_plotly_theme(
        fig,
        height=max(300, 80 * len(returns_df) + 150),
        margin=dict(l=80, r=80, t=80, b=120),
    )


# ──────────────────────────────────────────────────────────────
# 6) 因子评分横向对比
# ──────────────────────────────────────────────────────────────
def create_factor_score_comparison(stock_data_dict: dict, **kwargs) -> go.Figure:
    """
    创建多股票最新因子评分横向对比图
    
    【原理说明】
    使用项目中已有的 10 因子评分体系（动量/MACD/RSI/波动率/布林带/OBV/
    成交量/价格位置/回撤），对每只股票独立计算最新一天的综合因子评分，
    然后以柱状图横向对比，帮助用户在多标的中快速筛选。
    
    【计算流程】
    1. 对每只股票分别调用 add_indicators → compute_signals
    2. 提取最新一行的 factor_score 和 target_position
    3. 按评分降序排列绘制柱状图
    
    【颜色含义】
    - 绿色：策略建议重仓（≥80%）
    - 橙色：策略建议半仓（≥40%）
    - 蓝色：策略建议轻仓（>0%）
    - 灰色：策略建议空仓（0%）
    
    【对决策的影响】
    直接回答"当前哪只股票最值得买"的问题。
    红色虚线标示入场阈值，超过该线的股票是策略推荐买入的标的。
    
    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        **kwargs: 侧边栏传入的所有策略参数
    
    返回：
        Plotly 柱状图对象，失败返回 None
    """
    
    symbols = []
    scores = []
    target_positions = []
    percentiles = []
    
    score_lookback = int(kwargs.get("score_lookback", 30))
    indicator_period = int(kwargs.get("indicator_period", 20))
    momentum_long = int(kwargs.get("momentum_long", 20))
    ema_slow = int(kwargs.get("ema_slow", 60))
    macd_slow = int(kwargs.get("macd_slow", 26))
    macd_signal = int(kwargs.get("macd_signal", 9))
    rsi_period = int(kwargs.get("rsi_period", 14))
    adx_period = int(kwargs.get("adx_period", 14))
    atr_period = int(kwargs.get("atr_period", 14))
    bb_period = int(kwargs.get("bb_period", 20))
    min_required_rows = max(
        35,
        score_lookback + max(momentum_long, indicator_period),
        ema_slow,
        macd_slow + macd_signal,
        rsi_period,
        adx_period * 2,
        atr_period * 2,
        bb_period,
    )

    for symbol, df in stock_data_dict.items():
        prepared = _prepare_timeseries_frame(df, ["open", "high", "low", "close", "volume"])
        if len(prepared) < min_required_rows:
            continue

        try:
            df_indicators = add_indicators(
                prepared,
                rsi_period=rsi_period,
                macd_fast=kwargs.get("macd_fast", 12),
                macd_slow=macd_slow,
                macd_signal=macd_signal,
                ema_fast=kwargs.get("ema_fast", 20),
                ema_slow=ema_slow,
                adx_period=adx_period,
                atr_period=atr_period,
                bb_period=bb_period,
                bb_std=kwargs.get("bb_std", 2.0),
                indicator_period=indicator_period,
            )

            df_signals = compute_signals(
                df_indicators,
                rsi_lower=kwargs.get("rsi_lower", 30),
                rsi_upper=kwargs.get("rsi_upper", 70),
                adx_threshold=kwargs.get("adx_threshold", 20),
                momentum_short=kwargs.get("momentum_short", 5),
                momentum_long=momentum_long,
                score_lookback=score_lookback,
                score_mid_pct=kwargs.get("score_mid_pct", 0.6),
                score_high_pct=kwargs.get("score_high_pct", 0.8),
                weight_mom_short=kwargs.get("weight_mom_short", 1.0),
                weight_mom_long=kwargs.get("weight_mom_long", 1.0),
                weight_macd=kwargs.get("weight_macd", 1.0),
                weight_rsi=kwargs.get("weight_rsi", 0.5),
                weight_vol=kwargs.get("weight_vol", 0.5),
                entry_threshold=kwargs.get("entry_threshold", 0.5),
                exit_threshold=kwargs.get("exit_threshold", -0.5),
                use_trend_filter=kwargs.get("use_trend_filter", True),
                use_strength_filter=kwargs.get("use_strength_filter", True),
                use_rsi_filter=kwargs.get("use_rsi_filter", True),
                use_macd_filter=kwargs.get("use_macd_filter", True),
                use_voting_entry=kwargs.get("use_voting_entry", True),
                entry_vote_threshold=kwargs.get("entry_vote_threshold", 2.5),
                exit_min_signals=kwargs.get("exit_min_signals", 2),
                entry_min_signals=kwargs.get("entry_min_signals", 3),
                weight_bb=kwargs.get("weight_bb", 0.8),
                weight_obv=kwargs.get("weight_obv", 1.0),
                weight_volume=kwargs.get("weight_volume", 0.6),
                weight_price=kwargs.get("weight_price", 0.7),
                weight_drawdown=kwargs.get("weight_drawdown", 0.5),
            )

            latest = df_signals.iloc[-1]
            score_val = float(latest.get("factor_score", 0.0))
            pos_val = float(latest.get("target_position", 0.0))
            pct_val = float(latest.get("factor_percentile", 0.0))
            
            symbols.append(symbol)
            scores.append(score_val)
            target_positions.append(pos_val)
            percentiles.append(pct_val)
            
        except Exception:
            # 某只股票计算失败时跳过，不影响其他股票
            continue
    
    if not symbols:
        return None
    
    # 按评分降序排序
    sorted_indices = np.argsort(scores)[::-1]
    symbols = [symbols[i] for i in sorted_indices]
    scores = [scores[i] for i in sorted_indices]
    target_positions = [target_positions[i] for i in sorted_indices]
    percentiles = [percentiles[i] for i in sorted_indices]
    
    # 确定柱子颜色：根据目标仓位分档
    colors = []
    for pos in target_positions:
        if pos >= 0.8:
            colors.append('#2ca02c')   # 绿色（重仓）
        elif pos >= 0.4:
            colors.append('#ff7f0e')   # 橙色（半仓）
        elif pos > 0:
            colors.append('#1f77b4')   # 蓝色（轻仓）
        else:
            colors.append('#7f7f7f')   # 灰色（空仓）
    
    symbol_labels = [str(symbol) for symbol in symbols]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=symbol_labels,
        y=scores,
        marker_color=colors,
        text=[f'{s:.2f}' for s in scores],
        textposition='auto',
        customdata=np.column_stack([target_positions, [p * 100 for p in percentiles]]),
        hovertemplate=(
            '<b>%{x}</b><br>'
            '因子评分: %{y:.2f}<br>'
            '建议仓位: %{customdata[0]:.0%}<br>'
            '评分分位数: %{customdata[1]:.1f}%<br>'
            '<extra></extra>'
        ),
    ))
    
    # 添加入场阈值辅助线
    entry_thr = kwargs.get('entry_threshold', 0.5)
    fig.add_hline(
        y=entry_thr,
        line_dash='dash',
        line_color='red',
        annotation_text=f'入场阈值 ({entry_thr})',
        annotation_position='top right',
    )
    
    fig.update_layout(
        title=dict(
            text='最新因子评分横向对比',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='股票代码',
            title_font=dict(size=14, color='#34495e'),
            tickfont=dict(size=12, color='#2c3e50', family='Arial Black'),
            type="category",
            categoryorder="array",
            categoryarray=symbol_labels,
        ),
        yaxis=dict(
            title='综合因子评分',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=450,
        margin=dict(l=60, r=60, t=80, b=80),
        showlegend=False,
    )
    
    # 底部图例说明
    fig.add_annotation(
        text='颜色说明: 🟩 重仓 (≥80%) | 🟧 半仓 (≥40%) | 🟦 轻仓 (>0%) | ⬜ 空仓 (0%)',
        xref='paper', yref='paper',
        x=0.5, y=-0.18,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=12, color='#7f8c8d'),
    )

    return apply_plotly_theme(fig, height=450, margin=dict(l=60, r=60, t=80, b=80))
