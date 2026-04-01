"""
单股票策略分析页面
==================
选中单只股票时展示的策略工作流页面，包含：
- 训练/测试集切分
- 策略工作台与显式“生成策略”
- K线图 + RSI/MACD + 因子评分
- 当前策略摘要 + 阶段比较
- Walk-Forward 回测
- 交易信号
- HTML 报告导出
"""

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.backtest import max_drawdown, sharpe_ratio, walk_forward_backtest
from core.adaptive_regime import ADAPTIVE_REGIME_KIND
from core.data import get_stock_label_map, search_stock_candidates
from core.evaluation import build_comparison_table
from core.indicators import add_indicators
from core.utils import format_pct
from core.visualization import (
    _build_axis_transform,
    _identity_transform,
    compute_chart_view_range,
    create_candlestick_chart,
    create_candlestick_indicator_chart,
    create_empty_state_chart,
    create_equity_drawdown_chart,
    create_periodic_returns_heatmap,
    style_analysis_figure,
)
from core.market_context import get_market_indices
from ui.single_stock_workflow import (
    StrategyArtifact,
    StrategyRequest,
    build_strategy_context_key,
    commit_current_artifact,
    ensure_strategy_workspace,
    freeze_params_snapshot,
    get_strategy_workspace,
    get_workspace_status,
    run_strategy_pipeline,
    save_current_artifact,
)
from ui.export_reports import build_single_stock_export_html
from ui.theme import (
    get_ui_language,
    get_ui_theme,
    get_plotly_theme_tokens,
    render_analysis_date_range_control,
    render_html,
    render_status_note,
)


SELECTED_ARTIFACT_IDS_KEY = "single_stock_selected_artifact_ids"
FOCUS_ARTIFACT_ID_KEY = "single_stock_focus_artifact_id"
SIGNAL_DATASET_SPLIT_KEY = "single_stock_signal_dataset_split"
ARTIFACT_SELECTOR_OPTIONS_KEY = "single_stock_artifact_selector_options"
ARTIFACT_SELECTOR_CURRENT_KEY = "single_stock_artifact_selector_current"
SINGLE_ROUTE_STATE_KEY = "route_single_state"
SWITCH_STOCK_QUERY_KEY = "single_stock_switch_query"
TRAIN_RATIO_KEY = "single_stock_train_ratio"
STRATEGY_RESULT_MODE_KEY = "single_stock_strategy_result_mode"
WORKSPACE_DETAIL_VIEW_KEY = "single_stock_workspace_detail_view"
COMPARE_DETAIL_VIEW_KEY = "single_stock_compare_detail_view"
ANALYSIS_SECTION_KEY = "single_stock_analysis_section"
WORKFLOW_REQUEST_STATE_KEYS = (
    "single_stock_workflow_family",
    "single_stock_workflow_baseline_kind",
    "single_stock_workflow_regime_kind",
    "single_stock_workflow_search_base",
    "single_stock_workflow_use_search",
    "single_stock_workflow_search_method",
    "single_stock_workflow_search_trials",
    "single_stock_workflow_ga_population",
    "single_stock_workflow_ga_generations",
    "single_stock_workflow_use_ml",
    "single_stock_workflow_ml_model_type",
)


@dataclass(frozen=True)
class ArtifactLibraryEntry:
    artifact_id: str
    artifact: StrategyArtifact
    selector_label: str
    compare_label: str
    slot_kind: Literal["current", "saved"]


def _normalize_market_key(market: str | None) -> str:
    return "A" if str(market or "US").strip().upper() in {"A", "CN", "CN_A"} else "US"


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, np.number)):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return None if pd.isna(numeric) else numeric

    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"--", "None", "nan", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_decimal(value: object, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:,.{digits}f}"


def _format_signed_pct(value: object, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:+.{digits}f}%"


def _format_signed_change(value: object, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:+,.{digits}f}"


def _format_compact_number(value: object) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"

    absolute = abs(numeric)
    if absolute >= 1_000_000_000:
        return f"{numeric / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{numeric / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{numeric / 1_000:.2f}K"
    return f"{numeric:,.0f}"


def _format_date_text(value: object) -> str:
    if value is None:
        return "N/A"
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "N/A"
    return timestamp.strftime("%Y-%m-%d")


def _ensure_segmented_value(key: str, options: list[str], default: str) -> str:
    current = st.session_state.get(key)
    if current not in options:
        st.session_state[key] = default
        return default
    return str(current)


def _delta_class_from_pct(value: object) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return ""
    if numeric > 0:
        return "up"
    if numeric < 0:
        return "down"
    return ""


def _render_single_stock_snapshot_panel(
    *,
    df_indicators: pd.DataFrame,
    latest_row: pd.Series,
    latest_close: float | None,
    latest_volume: float | None,
    rolling_volume: float | None,
    rsi_upper: float,
    rsi_lower: float,
) -> None:
    latest_rsi = _safe_float(latest_row.get("rsi"))
    latest_hist = _safe_float(latest_row.get("histogram"))
    ema_fast_value = _safe_float(latest_row.get("ema_fast"))
    ema_slow_value = _safe_float(latest_row.get("ema_slow"))
    range_high = _safe_float(pd.to_numeric(df_indicators.get("high"), errors="coerce").max())
    range_low = _safe_float(pd.to_numeric(df_indicators.get("low"), errors="coerce").min())

    if latest_rsi is None:
        rsi_text = "N/A"
    elif latest_rsi >= rsi_upper:
        rsi_text = f"{latest_rsi:.1f} · 偏热"
    elif latest_rsi <= rsi_lower:
        rsi_text = f"{latest_rsi:.1f} · 偏冷"
    else:
        rsi_text = f"{latest_rsi:.1f} · {'中性偏强' if latest_rsi >= 50 else '中性偏弱'}"

    if latest_hist is None:
        macd_text = "N/A"
    else:
        macd_text = f"{latest_hist:+.2f} · {'多头动能' if latest_hist > 0 else '空头动能' if latest_hist < 0 else '动能中性'}"

    if latest_volume is None or rolling_volume in {None, 0}:
        volume_text = "N/A"
    else:
        volume_ratio = latest_volume / rolling_volume
        volume_text = f"{volume_ratio:.2f}x · {'量能放大' if volume_ratio >= 1.15 else '量能回落' if volume_ratio <= 0.85 else '量能平稳'}"

    if latest_close is None or range_high in {None} or range_low in {None} or range_high <= range_low:
        range_text = "N/A"
    else:
        range_position = max(0.0, min(1.0, (latest_close - range_low) / (range_high - range_low)))
        range_text = f"{range_position:.0%} · {'靠近区间高位' if range_position >= 0.67 else '处于区间中段' if range_position >= 0.33 else '靠近区间低位'}"

    returns_window = pd.to_numeric(df_indicators.get("close"), errors="coerce").pct_change().dropna().tail(60)
    if returns_window.empty:
        volatility_text = "N/A"
    else:
        annualized_vol = float(returns_window.std() * np.sqrt(252) * 100.0)
        volatility_text = f"{annualized_vol:.1f}% · {'波动偏高' if annualized_vol >= 40 else '波动适中' if annualized_vol >= 20 else '波动偏稳'}"

    if latest_close in {None, 0} or ema_fast_value is None or ema_slow_value is None:
        ema_text = "N/A"
    else:
        ema_spread_pct = ((ema_fast_value - ema_slow_value) / latest_close) * 100.0
        ema_text = f"{ema_spread_pct:+.2f}% · {'快线在上' if ema_spread_pct > 0 else '快线在下' if ema_spread_pct < 0 else '双线贴合'}"

    snapshot_markup = "".join(
        f"<div class='board-micro-item'><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"
        for label, value in [
            ("RSI 状态", rsi_text),
            ("MACD 柱体", macd_text),
            ("量能相对值", volume_text),
            ("区间位置", range_text),
            ("近 60 日波动", volatility_text),
            ("EMA 价差", ema_text),
        ]
    )
    render_html(
        f"""
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">当前技术快照</h4>
  <p class="analysis-callout-copy">补足左下摘要区的空白，用当前指标、量能和区间位置快速回答“这只股票现在处在哪一段”。</p>
  <div class="board-micro-list">{snapshot_markup}</div>
</div>
        """
    )


def _resolve_symbol_identity(symbol: str, market: str) -> dict[str, str]:
    route_state = st.session_state.get(SINGLE_ROUTE_STATE_KEY, {})
    market_key = _normalize_market_key(market)
    market_label = "A 股" if market_key == "A" else "美股"
    route_source = str(route_state.get("source") or "").strip().lower()

    if route_source == "upload" and route_state.get("uploaded_name"):
        uploaded_name = str(route_state.get("uploaded_name")).strip()
        display_name = uploaded_name.rsplit(".", 1)[0] if "." in uploaded_name else uploaded_name
        subtitle = f"{symbol} · {market_label} · 上传数据"
        return {
            "symbol": symbol,
            "display_name": display_name or symbol,
            "display_label": subtitle,
            "market_label": market_label,
            "source_label": "上传数据",
        }

    label_map = get_stock_label_map([symbol], market=market_key)
    full_label = label_map.get(symbol, symbol)
    display_name = full_label
    if full_label.startswith(f"{symbol} "):
        display_name = full_label[len(symbol) + 1 :].strip() or symbol

    return {
        "symbol": symbol,
        "display_name": display_name,
        "display_label": full_label,
        "market_label": market_label,
        "source_label": "市场数据",
    }


def _render_single_stock_header(
    *,
    symbol: str,
    market: str,
    df_indicators: pd.DataFrame,
    split_idx: int,
    train_ratio: float,
    selected_range: object,
) -> None:
    identity = _resolve_symbol_identity(symbol, market)
    latest = df_indicators.iloc[-1]
    previous_close = _safe_float(df_indicators["close"].iloc[-2]) if len(df_indicators) > 1 else None
    latest_close = _safe_float(latest.get("close"))
    change_value = None if latest_close is None or previous_close in {None, 0} else latest_close - previous_close
    change_pct = None if change_value is None or previous_close in {None, 0} else (change_value / previous_close) * 100.0

    date_min = _format_date_text(df_indicators["date"].min())
    date_max = _format_date_text(df_indicators["date"].max())
    test_count = max(len(df_indicators) - split_idx, 0)
    split_date = _format_date_text(df_indicators["date"].iloc[split_idx - 1])

    quick_items = [
        {
            "label": "最新收盘",
            "value": _format_decimal(latest_close),
            "meta": f"{_format_signed_change(change_value)} / {_format_signed_pct(change_pct)}",
        },
        {
            "label": "训练 / 测试",
            "value": f"{split_idx} / {test_count}",
            "meta": f"训练比例 {train_ratio:.0%}",
        },
        {
            "label": "数据区间",
            "value": f"{len(df_indicators)} 天",
            "meta": f"{date_min} 到 {date_max}",
        },
    ]
    quick_markup = "".join(
        f"""
<div class="analysis-quick-item">
  <span class="analysis-quick-label">{html.escape(item['label'])}</span>
  <span class="analysis-quick-value">{html.escape(item['value'])}</span>
  <span class="analysis-quick-meta">{html.escape(item['meta'])}</span>
</div>
        """
        for item in quick_items
    )

    index_cards = []
    for item in get_market_indices(_normalize_market_key(market)):
        index_cards.append(
            f"""
<div class="analysis-market-card">
  <span class="analysis-market-label">{html.escape(str(item.get('label') or '市场指数'))}</span>
  <span class="analysis-market-value">{html.escape(_format_decimal(item.get('close')))}</span>
  <span class="analysis-market-delta {_delta_class_from_pct(item.get('pct_change'))}">{html.escape(_format_signed_pct(item.get('pct_change')))}</span>
</div>
            """
        )
    if not index_cards:
        index_cards.append(
            """
<div class="analysis-market-card">
  <span class="analysis-market-label">市场指数</span>
  <span class="analysis-market-value">N/A</span>
  <span class="analysis-market-delta">暂无数据</span>
</div>
            """
        )

    with st.container(key="single-stock-analysis-hero"):
        render_html(
            f"""
<div class="analysis-hero-topline">
  <span class="analysis-pill accent">Single Stock Analysis</span>
  <span class="analysis-pill">{html.escape(identity['market_label'])}</span>
  <span class="analysis-pill">{html.escape(identity['source_label'])}</span>
  <span class="analysis-pill {('positive' if (_safe_float(change_pct) or 0) > 0 else 'negative' if (_safe_float(change_pct) or 0) < 0 else '')}">{html.escape(_format_signed_pct(change_pct))}</span>
</div>
            """
        )
        summary_col, quick_col = st.columns([1.08, 0.92], gap="large")
        with summary_col:
            render_html(
                f"""
<h1 class="analysis-title">{html.escape(identity['display_name'])}</h1>
<div class="analysis-subtitle">{html.escape(identity['display_label'])}</div>
<div class="analysis-chart-meta">
  <span class="analysis-chart-chip">训练截止 {html.escape(split_date)}</span>
  <span class="analysis-chart-chip">当前标的 {html.escape(symbol)}</span>
</div>
                """
            )
            render_analysis_date_range_control(
                current_range=selected_range,
                key_prefix="single_stock",
                label="时间范围",
                in_hero=True,
            )
        with quick_col:
            render_html(f"<div class='analysis-quick-grid'>{quick_markup}</div>")
        render_html(f"<div class='analysis-market-strip'>{''.join(index_cards)}</div>")


def _render_single_stock_section_nav(*, symbol: str, market: str) -> str:
    nav_col, switch_col = st.columns([1.85, 1.0], gap="small")
    section_default = _ensure_segmented_value(ANALYSIS_SECTION_KEY, ["basics", "strategy"], "basics")
    with nav_col:
        st.caption("分析区切换")
        section_view = st.segmented_control(
            "分析区切换",
            options=["basics", "strategy"],
            format_func=lambda value: "基础信息" if value == "basics" else "策略",
            default=section_default,
            key=ANALYSIS_SECTION_KEY,
            width="stretch",
            label_visibility="collapsed",
        ) or section_default
    with switch_col:
        st.caption("切换股票")
        with st.container(key="single-stock-switch-popover"):
            with st.popover("切换股票", use_container_width=True):
                _render_switch_stock_popover(symbol=symbol, market=market)
    return section_view


def _render_switch_stock_popover(*, symbol: str, market: str) -> None:
    market_key = _normalize_market_key(market)
    st.caption(f"当前标的：{symbol}")
    query = st.text_input(
        "搜索股票名称或代码",
        value="",
        placeholder="例如：AAPL / Apple / 600519",
        key=SWITCH_STOCK_QUERY_KEY,
    ).strip()

    if not query:
        render_status_note("输入新股票后即可直接切换，当前页面的工作流会跟随新标的重新建立。", tone="info")
        return

    try:
        matched = search_stock_candidates(query, market=market_key, limit=8)
    except Exception as exc:
        matched = pd.DataFrame(columns=["symbol", "name", "label"])
        render_status_note(f"搜索候选项失败：{exc}", tone="warning")

    if matched.empty:
        fallback_symbol = query.zfill(6)[-6:] if market_key == "A" and query.isdigit() else query.upper()
        render_status_note("没有找到索引匹配，将按当前输入直接切换。", tone="warning")
        if st.button("按当前输入切换", key="single_stock_switch_direct", use_container_width=True):
            _switch_single_stock_symbol(fallback_symbol, market_key)
        return

    for row in matched.itertuples(index=False):
        info_col, action_col = st.columns([4.5, 1.0], gap="small")
        info_col.markdown(
            f"<div class='recommend-row'><div class='recommend-row-title'>{html.escape(str(row.symbol))}</div><div class='recommend-row-meta'>{html.escape(str(row.label))}</div></div>",
            unsafe_allow_html=True,
        )
        if action_col.button("切换", key=f"single_stock_switch_{row.symbol}"):
            _switch_single_stock_symbol(str(row.symbol), market_key)


def _switch_single_stock_symbol(symbol: str, market: str) -> None:
    st.session_state[SINGLE_ROUTE_STATE_KEY] = {
        "view": "analysis",
        "market": market,
        "symbol": symbol,
        "uploaded_name": None,
        "uploaded_bytes": None,
        "source": "switch",
    }
    st.rerun()


def _render_basic_info_section(
    *,
    symbol: str,
    market: str,
    df_indicators: pd.DataFrame,
    split_idx: int,
    indicator_kwargs: dict[str, Any],
    artifact: StrategyArtifact | None,
    rsi_upper: float,
    rsi_lower: float,
) -> tuple[go.Figure, go.Figure, go.Figure, str]:
    identity = _resolve_symbol_identity(symbol, market)
    latest = df_indicators.iloc[-1]
    previous_close = _safe_float(df_indicators["close"].iloc[-2]) if len(df_indicators) > 1 else None
    latest_close = _safe_float(latest.get("close"))
    latest_open = _safe_float(latest.get("open"))
    latest_high = _safe_float(latest.get("high"))
    latest_low = _safe_float(latest.get("low"))
    latest_volume = _safe_float(latest.get("volume"))
    change_pct = None if latest_close is None or previous_close in {None, 0} else ((latest_close / previous_close) - 1.0) * 100.0
    range_return = None
    first_close = _safe_float(df_indicators["close"].iloc[0]) if len(df_indicators) > 0 else None
    if latest_close is not None and first_close not in {None, 0}:
        range_return = (latest_close / first_close - 1.0) * 100.0

    split_date = df_indicators["date"].iloc[split_idx - 1]
    test_start = df_indicators["date"].iloc[split_idx] if split_idx < len(df_indicators) else None
    rolling_volume = pd.to_numeric(df_indicators.get("volume"), errors="coerce").tail(20).mean() if "volume" in df_indicators.columns else None

    metrics = [
        ("当前价格", _format_decimal(latest_close), f"最新交易日 {_format_date_text(latest.get('date'))}"),
        ("最新涨跌", _format_signed_pct(change_pct), f"较前一日 {_format_signed_change(None if latest_close is None or previous_close is None else latest_close - previous_close)}"),
        ("开盘 / 最高", f"{_format_decimal(latest_open)} / {_format_decimal(latest_high)}", "当日开高"),
        ("最低 / 成交量", f"{_format_decimal(latest_low)} / {_format_compact_number(latest_volume)}", "当日低点与成交量"),
        ("区间收益", _format_signed_pct(range_return), f"{_format_date_text(df_indicators['date'].min())} 到 {_format_date_text(df_indicators['date'].max())}"),
        ("20 日均量", _format_compact_number(rolling_volume), "不足 20 日时按现有窗口计算"),
        ("训练集截止", _format_date_text(split_date), f"测试起点 {_format_date_text(test_start)}"),
        ("数据行数", f"{len(df_indicators)}", f"{identity['market_label']} · {identity['source_label']}"),
    ]
    metrics_markup = "".join(
        f"""
<div class="analysis-kv-item">
  <span class="analysis-kv-label">{html.escape(label)}</span>
  <span class="analysis-kv-value">{html.escape(value)}</span>
  <span class="analysis-kv-meta">{html.escape(meta)}</span>
</div>
        """
        for label, value, meta in metrics
    )

    with st.container(key="single-stock-basic-section"):
        render_html(
            f"""
<div id="single-stock-basics"></div>
<div class="analysis-section-header">
  <div class="surface-kicker">Basic Information</div>
  <h2 class="analysis-section-title">单股基础信息区</h2>
  <p class="analysis-section-copy">左侧用文字快速交代当前标的状态，右侧保留高密度 K 线主图和指标小图，训练/测试边界在行情图里保持可见。</p>
</div>
            """
        )
        info_col, chart_col = st.columns([0.72, 1.48], gap="large")
        with info_col:
            render_html(
                f"""
<div class="analysis-kv-grid">{metrics_markup}</div>
<div class="analysis-chart-meta">
  <span class="analysis-chart-chip">标的 {html.escape(symbol)}</span>
  <span class="analysis-chart-chip">显示名 {html.escape(identity['display_name'])}</span>
</div>
                """
            )
            _render_single_stock_snapshot_panel(
                df_indicators=df_indicators,
                latest_row=latest,
                latest_close=latest_close,
                latest_volume=latest_volume,
                rolling_volume=rolling_volume,
                rsi_upper=rsi_upper,
                rsi_lower=rsi_lower,
            )
            render_status_note("缺失字段会回退为 N/A，不会阻断图表和后续策略工作流。", tone="info")

        with chart_col:
            candle, ind_fig, score_fig, indicator_title = _build_market_visualizations(
                df_raw=df_indicators[["date", "open", "high", "low", "close"] + (["volume"] if "volume" in df_indicators.columns else [])].copy(),
                indicator_kwargs=indicator_kwargs,
                artifact=artifact,
                split_date=split_date,
                symbol=symbol,
                rsi_upper=rsi_upper,
                rsi_lower=rsi_lower,
                render_controls=True,
            )

    return candle, ind_fig, score_fig, indicator_title


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 公共入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def render_single_stock_page(params: dict, df_raw: pd.DataFrame, symbol: str) -> None:
    """
    渲染单股票策略分析页面。

    Parameters
    ----------
    params : dict
        ``render_sidebar()`` 返回的完整参数字典。
    df_raw : pd.DataFrame
        原始 OHLCV 数据（已筛选日期范围）。
    symbol : str
        当前分析的股票代码。
    """
    p = params
    strategy_preset = p["strategy_preset"]

    indicator_kwargs = {
        "rsi_period": p["rsi_period"],
        "macd_fast": p["macd_fast"],
        "macd_slow": p["macd_slow"],
        "macd_signal": p["macd_signal"],
        "ema_fast": p["ema_fast"],
        "ema_slow": p["ema_slow"],
        "adx_period": p["adx_period"],
        "atr_period": p["atr_period"],
        "bb_period": p["bb_period"],
        "bb_std": p["bb_std"],
        "indicator_period": p["indicator_period"],
    }
    df_indicators = add_indicators(df_raw, **indicator_kwargs)

    page_top_slot = st.container()
    train_ratio = _safe_float(st.session_state.get(TRAIN_RATIO_KEY))
    if train_ratio is None or train_ratio < 0.6 or train_ratio > 0.9:
        train_ratio = 0.7
        st.session_state[TRAIN_RATIO_KEY] = train_ratio
    if len(df_indicators) <= 1:
        st.warning("数据量不足，无法进行策略工作流分析。")
        return

    split_idx = min(max(1, int(len(df_indicators) * train_ratio)), len(df_indicators) - 1)
    params_snapshot = freeze_params_snapshot(params)
    context_key = build_strategy_context_key(
        market=p.get("market", "US"),
        symbol=symbol,
        adjust=p.get("adjust", ""),
        df_raw=df_raw,
        train_ratio=train_ratio,
        uploaded_file=p.get("uploaded_file"),
    )
    workspace, was_reset = ensure_strategy_workspace(context_key)
    if was_reset:
        _reset_workflow_request_state()
        _reset_downstream_display_state()
    with page_top_slot:
        _render_single_stock_header(
            symbol=symbol,
            market=p.get("market", "US"),
            df_indicators=df_indicators,
            split_idx=split_idx,
            train_ratio=train_ratio,
            selected_range=p.get("selected_range"),
        )
        analysis_section = _render_single_stock_section_nav(symbol=symbol, market=p.get("market", "US"))

    current_artifact: StrategyArtifact | None = workspace.get("current_artifact")
    if analysis_section == "basics":
        candle, ind_fig, score_fig, indicator_title = _render_basic_info_section(
            symbol=symbol,
            market=p.get("market", "US"),
            df_indicators=df_indicators,
            split_idx=split_idx,
            indicator_kwargs=indicator_kwargs,
            artifact=current_artifact,
            rsi_upper=p["rsi_upper"],
            rsi_lower=p["rsi_lower"],
        )
    else:
        candle, ind_fig, score_fig, indicator_title = _build_market_visualizations(
            df_raw=df_indicators[["date", "open", "high", "low", "close"] + (["volume"] if "volume" in df_indicators.columns else [])].copy(),
            indicator_kwargs=indicator_kwargs,
            artifact=current_artifact,
            split_date=df_indicators["date"].iloc[split_idx - 1],
            symbol=symbol,
            rsi_upper=p["rsi_upper"],
            rsi_lower=p["rsi_lower"],
            render_controls=False,
        )

    page_state = "EMPTY"
    request = StrategyRequest()
    request_ready = False
    missing_items: list[str] = []
    saved_artifacts: list[StrategyArtifact] = []
    selected_entries: list[ArtifactLibraryEntry] = []
    focus_entry: ArtifactLibraryEntry | None = None
    signal_dataset_split = str(st.session_state.get(SIGNAL_DATASET_SPLIT_KEY, "test"))
    if signal_dataset_split not in {"train", "test"}:
        signal_dataset_split = "test"
        st.session_state[SIGNAL_DATASET_SPLIT_KEY] = signal_dataset_split
    artifact_payload: dict[str, dict] = {}
    active_artifacts: list[str] = []
    export_payload: dict[str, dict] = {}
    export_active_models: list[str] = []
    suggestion = "未生成策略"
    equity_fig = go.Figure()
    signal_fig = go.Figure()

    if analysis_section != "strategy":
        return

    with st.container(key="single-stock-strategy-section"):
        render_html(
            """
<div class="analysis-section-header">
  <div class="surface-kicker">Strategy Workspace</div>
  <h2 class="analysis-section-title">策略区</h2>
  <p class="analysis-section-copy">左侧固定为模型控制台，右侧固定为结果展示板。W5 已冻结的 request、lineage、artifact、回测和导出链路继续复用，本轮只重构交互壳层与结果组织方式。</p>
</div>
            """
        )
        control_col, result_col = st.columns([0.78, 1.22], gap="large")

        with control_col:
            with st.container(key="single-stock-strategy-control-panel"):
                render_html(
                    f"""
<div class="analysis-section-header">
  <div class="surface-kicker">Control Desk</div>
  <h3 class="analysis-section-title">模型控制台</h3>
  <p class="analysis-section-copy">训练区间、模型路径、生成按钮和策略库都收拢在同一控制面里；切换股票或训练比例时，workspace 会按上下文重新建立。</p>
</div>
<div class="analysis-chart-meta">
  <span class="analysis-chart-chip">训练 {split_idx} 行</span>
  <span class="analysis-chart-chip">测试 {max(len(df_indicators) - split_idx, 0)} 行</span>
  <span class="analysis-chart-chip">比例 {train_ratio:.0%}</span>
</div>
                    """
                )
                st.slider(
                    "训练集比例",
                    min_value=0.6,
                    max_value=0.9,
                    value=float(train_ratio),
                    step=0.05,
                    key=TRAIN_RATIO_KEY,
                    help="按时间顺序切分训练/测试集。",
                )
                render_status_note("修改训练比例后，训练/测试边界、workspace 上下文和右侧结果板会一起刷新。", tone="info")

                st.divider()
                entry_status_slot = st.empty()
                render_html(
                    """
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">工作台入口</h4>
  <p class="analysis-callout-copy">先确定是课程基线、Search 还是 Regime 路径，再继续补齐下方配置。页面不再默认预计算所有模型结果。</p>
</div>
                    """
                )
                selected_family = _render_workbench_entry(
                    total_rows=len(df_indicators),
                    split_idx=split_idx,
                    df_indicators=df_indicators,
                    market=p.get("market", "US"),
                )

                st.divider()
                render_html(
                    """
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">模型配置</h4>
  <p class="analysis-callout-copy">按 W5 冻结语义继续配置 Baseline / SM / FSM / Search / Regime，不在这里改底层参数合同。</p>
</div>
                    """
                )
                request = _render_model_configuration_section(selected_family)

                current_artifact = get_strategy_workspace().get("current_artifact")
                workspace_status = get_workspace_status(workspace, request, params_snapshot)
                page_state = _derive_workbench_page_state(workspace_status, current_artifact, request)
                missing_items = _get_request_missing_items(request)
                request_ready = not missing_items
                _render_workbench_status(
                    slot=entry_status_slot,
                    page_state=page_state,
                    was_reset=was_reset,
                    current_artifact=current_artifact,
                    request_ready=request_ready,
                )

                st.divider()
                render_html(
                    """
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">生成与策略库</h4>
  <p class="analysis-callout-copy">生成只会提交新的 <code>current_artifact</code>；保存后才会进入会话内策略库，供右侧结果板做多策略比对。</p>
</div>
                    """
                )
                request_path = _describe_request_pipeline(request)
                if request_path:
                    render_status_note("当前路径：" + request_path, tone="info")

                generate_disabled = bool(missing_items) or (request.use_search and split_idx < 50)
                if missing_items:
                    render_status_note("待完成项：" + "；".join(missing_items), tone="warning")
                elif request.use_search and split_idx < 50:
                    render_status_note("参数搜索至少需要 50 个训练样本；当前训练样本不足，已禁用“生成策略”。", tone="warning")
                elif page_state == "REQUEST_DRAFT" and current_artifact is not None:
                    render_status_note("当前结果仍是上次成功提交的 artifact；草稿修改后需要重新点击“生成策略”才会生效。", tone="warning")
                else:
                    render_status_note("点击下方按钮后，系统会按当前请求生成新的 current_artifact。", tone="positive")

                if st.button("生成策略", type="primary", disabled=generate_disabled, key="single_stock_generate_strategy"):
                    with st.spinner("正在生成策略工作流..."):
                        pipeline_result = run_strategy_pipeline(
                            context_key=context_key,
                            request=request,
                            request_params_snapshot=params_snapshot,
                            df_raw=df_raw,
                            split_idx=split_idx,
                        )
                    for info_message in pipeline_result.info_messages:
                        render_status_note(info_message, tone="info")
                    if pipeline_result.artifact is not None:
                        commit_current_artifact(pipeline_result.artifact)
                        _set_downstream_display_state(pipeline_result.artifact)
                        if pipeline_result.status == "success":
                            render_status_note(f"已生成策略：{pipeline_result.artifact.display_label}", tone="positive")
                        else:
                            for warning_message in pipeline_result.warnings:
                                render_status_note(warning_message, tone="warning")
                    else:
                        render_status_note(pipeline_result.error_message or "策略生成失败。", tone="error")

                workspace = get_strategy_workspace()
                current_artifact = workspace.get("current_artifact")
                workspace_status = get_workspace_status(workspace, request, params_snapshot)
                page_state = _derive_workbench_page_state(workspace_status, current_artifact, request)
                _render_workbench_status(
                    slot=entry_status_slot,
                    page_state=page_state,
                    was_reset=was_reset,
                    current_artifact=current_artifact,
                    request_ready=request_ready,
                )

                if current_artifact is not None:
                    saved_artifacts = list(workspace.get("saved_artifacts", []))
                    st.divider()
                    selected_entries, focus_entry, signal_dataset_split = _render_strategy_library(
                        current_artifact=current_artifact,
                        saved_artifacts=saved_artifacts,
                    )

        with result_col:
            with st.container(key="single-stock-strategy-result-board"):
                render_html(
                    """
<div class="analysis-section-header">
  <div class="surface-kicker">Result Board</div>
  <h3 class="analysis-section-title">策略结果区</h3>
  <p class="analysis-section-copy">右侧只保留一个稳定展示板。默认查看当前策略，切到“策略比对”后保持同一布局，只替换结果内容，不再把比较图表散落到页面底部。</p>
</div>
                    """
                )

                if current_artifact is None:
                    _render_strategy_result_empty(
                        page_state=page_state,
                        request_ready=request_ready,
                        request_path=request_path,
                    )
                else:
                    current_entry = _resolve_current_artifact_entry(current_artifact, selected_entries)
                    if not selected_entries:
                        selected_entries = [current_entry]
                    if focus_entry is None:
                        focus_entry = current_entry

                    saved_artifacts = list(get_strategy_workspace().get("saved_artifacts", []))
                    artifact_payload = _build_selected_artifact_payload(selected_entries)
                    active_artifacts = list(artifact_payload.keys())

                    result_mode_default = _ensure_segmented_value(
                        STRATEGY_RESULT_MODE_KEY,
                        ["workspace", "compare"],
                        "workspace",
                    )
                    result_mode = st.segmented_control(
                        "结果模式",
                        options=["workspace", "compare"],
                        format_func=lambda value: "当前策略" if value == "workspace" else "策略比对",
                        default=result_mode_default,
                        key=STRATEGY_RESULT_MODE_KEY,
                        width="stretch",
                    ) or result_mode_default

                    if result_mode == "workspace":
                        suggestion, equity_fig, signal_fig, export_payload, export_active_models = _render_strategy_workspace_result(
                            current_artifact=current_artifact,
                            current_entry=current_entry,
                            strategy_preset=strategy_preset,
                            is_stale_result=page_state == "REQUEST_DRAFT",
                            signal_dataset_split=signal_dataset_split,
                        )
                    else:
                        suggestion, equity_fig, signal_fig = _render_strategy_compare_result(
                            selected_entries=selected_entries,
                            focus_entry=focus_entry,
                            current_artifact=current_artifact,
                            saved_artifacts=saved_artifacts,
                            signal_dataset_split=signal_dataset_split,
                            artifact_payload=artifact_payload,
                            active_artifacts=active_artifacts,
                        )
                        export_payload = artifact_payload
                        export_active_models = active_artifacts

                    score_source_entry = current_entry if result_mode == "workspace" else (focus_entry or current_entry)
                    score_fig = _render_result_factor_score_panel(
                        artifact=score_source_entry.artifact if score_source_entry is not None else current_artifact,
                        artifact_label=score_source_entry.compare_label if score_source_entry is not None else current_artifact.display_label,
                        split_idx=split_idx,
                        signal_dataset_split=signal_dataset_split,
                    )

                    _render_single_stock_export(
                        symbol=symbol,
                        df=current_artifact.full_signal_df,
                        test_df=focus_entry.artifact.test_sim_df if focus_entry is not None else current_artifact.test_sim_df,
                        model_payload=export_payload,
                        active_models=export_active_models,
                        candle=candle,
                        ind_fig=ind_fig,
                        score_fig=score_fig,
                        equity_fig=equity_fig,
                        signal_fig=signal_fig,
                        suggestion=suggestion,
                        indicator_title=indicator_title,
                    )


def _reset_downstream_display_state() -> None:
    st.session_state[SELECTED_ARTIFACT_IDS_KEY] = []
    st.session_state[FOCUS_ARTIFACT_ID_KEY] = None
    st.session_state[SIGNAL_DATASET_SPLIT_KEY] = "test"
    st.session_state[ARTIFACT_SELECTOR_OPTIONS_KEY] = []
    st.session_state[ARTIFACT_SELECTOR_CURRENT_KEY] = None


def _reset_workflow_request_state() -> None:
    for key in WORKFLOW_REQUEST_STATE_KEYS:
        st.session_state.pop(key, None)


def _set_downstream_display_state(artifact: StrategyArtifact | None) -> None:
    if artifact is None:
        _reset_downstream_display_state()
        return
    st.session_state[SELECTED_ARTIFACT_IDS_KEY] = [artifact.id]
    st.session_state[FOCUS_ARTIFACT_ID_KEY] = artifact.id
    st.session_state[SIGNAL_DATASET_SPLIT_KEY] = "test"
    st.session_state[ARTIFACT_SELECTOR_CURRENT_KEY] = artifact.id


def _build_strategy_library_entries(
    current_artifact: StrategyArtifact | None,
    saved_artifacts: list[StrategyArtifact],
) -> list[ArtifactLibraryEntry]:
    entries: list[ArtifactLibraryEntry] = []
    if current_artifact is not None:
        current_label = f"当前 · {current_artifact.display_label}"
        entries.append(
            ArtifactLibraryEntry(
                artifact_id=current_artifact.id,
                artifact=current_artifact,
                selector_label=current_label,
                compare_label=current_label,
                slot_kind="current",
            )
        )

    saved_label_counts: dict[str, int] = {}
    saved_labels: dict[str, str] = {}
    for artifact in saved_artifacts:
        base_label = f"已保存 · {artifact.display_label}"
        saved_label_counts[artifact.display_label] = saved_label_counts.get(artifact.display_label, 0) + 1
        label_index = saved_label_counts[artifact.display_label]
        saved_labels[artifact.id] = base_label if label_index == 1 else f"{base_label} ({label_index})"

    for artifact in reversed(saved_artifacts):
        saved_label = saved_labels[artifact.id]
        entries.append(
            ArtifactLibraryEntry(
                artifact_id=artifact.id,
                artifact=artifact,
                selector_label=saved_label,
                compare_label=saved_label,
                slot_kind="saved",
            )
        )
    return entries


def _dedupe_artifact_entries(entries: list[ArtifactLibraryEntry]) -> list[ArtifactLibraryEntry]:
    deduped: list[ArtifactLibraryEntry] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if entry.artifact_id in seen_ids:
            continue
        deduped.append(entry)
        seen_ids.add(entry.artifact_id)
    return deduped


def _normalize_selected_artifact_ids(
    available_ids: list[str],
    current_artifact_id: str | None,
    selected_ids: list[str] | None,
) -> list[str]:
    normalized = [artifact_id for artifact_id in (selected_ids or []) if artifact_id in available_ids]
    if normalized:
        return normalized
    if current_artifact_id in available_ids:
        return [current_artifact_id]
    return available_ids[:1]


def _normalize_focus_artifact_id(selected_ids: list[str], focus_artifact_id: str | None) -> str | None:
    if focus_artifact_id in selected_ids:
        return focus_artifact_id
    return selected_ids[0] if selected_ids else None


def _sync_downstream_display_state(
    current_artifact: StrategyArtifact | None,
    unique_entries: list[ArtifactLibraryEntry],
) -> None:
    available_ids = [entry.artifact_id for entry in unique_entries]
    current_artifact_id = current_artifact.id if current_artifact is not None else None
    normalized_selected = _normalize_selected_artifact_ids(
        available_ids=available_ids,
        current_artifact_id=current_artifact_id,
        selected_ids=st.session_state.get(SELECTED_ARTIFACT_IDS_KEY),
    )
    normalized_focus = _normalize_focus_artifact_id(
        selected_ids=normalized_selected,
        focus_artifact_id=st.session_state.get(FOCUS_ARTIFACT_ID_KEY),
    )

    st.session_state[ARTIFACT_SELECTOR_OPTIONS_KEY] = available_ids
    st.session_state[ARTIFACT_SELECTOR_CURRENT_KEY] = current_artifact_id
    st.session_state[SELECTED_ARTIFACT_IDS_KEY] = normalized_selected
    st.session_state[FOCUS_ARTIFACT_ID_KEY] = normalized_focus
    if st.session_state.get(SIGNAL_DATASET_SPLIT_KEY) not in {"train", "test"}:
        st.session_state[SIGNAL_DATASET_SPLIT_KEY] = "test"


def _on_artifact_selection_change() -> None:
    available_ids = list(st.session_state.get(ARTIFACT_SELECTOR_OPTIONS_KEY, []))
    current_artifact_id = st.session_state.get(ARTIFACT_SELECTOR_CURRENT_KEY)
    normalized_selected = _normalize_selected_artifact_ids(
        available_ids=available_ids,
        current_artifact_id=current_artifact_id,
        selected_ids=st.session_state.get(SELECTED_ARTIFACT_IDS_KEY),
    )
    st.session_state[SELECTED_ARTIFACT_IDS_KEY] = normalized_selected
    st.session_state[FOCUS_ARTIFACT_ID_KEY] = _normalize_focus_artifact_id(
        selected_ids=normalized_selected,
        focus_artifact_id=st.session_state.get(FOCUS_ARTIFACT_ID_KEY),
    )


def _on_focus_artifact_change() -> None:
    selected_ids = list(st.session_state.get(SELECTED_ARTIFACT_IDS_KEY, []))
    st.session_state[FOCUS_ARTIFACT_ID_KEY] = _normalize_focus_artifact_id(
        selected_ids=selected_ids,
        focus_artifact_id=st.session_state.get(FOCUS_ARTIFACT_ID_KEY),
    )


def _render_strategy_library(
    *,
    current_artifact: StrategyArtifact,
    saved_artifacts: list[StrategyArtifact],
) -> tuple[list[ArtifactLibraryEntry], ArtifactLibraryEntry | None, str]:
    entries = _build_strategy_library_entries(current_artifact, saved_artifacts)
    unique_entries = _dedupe_artifact_entries(entries)
    _sync_downstream_display_state(current_artifact, unique_entries)

    st.markdown("##### 策略库 / 多策略选择器")
    action_col, info_col = st.columns([1.0, 2.0])
    with action_col:
        if st.button("保存当前策略", key="single_stock_save_current_artifact", width="stretch"):
            save_status, saved_artifact = save_current_artifact()
            if save_status == "saved" and saved_artifact is not None:
                st.success(f"已保存：{saved_artifact.display_label}")
            elif save_status == "exists":
                st.info("当前策略已在策略库中。")
            else:
                st.info("当前没有可保存的策略。")
            workspace = get_strategy_workspace()
            saved_artifacts = list(workspace.get("saved_artifacts", []))
            entries = _build_strategy_library_entries(current_artifact, saved_artifacts)
            unique_entries = _dedupe_artifact_entries(entries)
            _sync_downstream_display_state(current_artifact, unique_entries)
    with info_col:
        st.caption("当前策略固定置顶；已保存策略按最近保存倒序展示。比较器按底层 artifact 去重，不重复画线。")
        st.caption(f"策略库规模：当前 1 条，已保存 {len(saved_artifacts)} 条。")

    if not saved_artifacts:
        st.info("当前还没有已保存策略。保存当前策略后，这里会形成本次会话的策略库。")

    unique_labels = {entry.artifact_id: entry.selector_label for entry in unique_entries}
    selected_ids = st.multiselect(
        "参与下游比较的策略",
        options=[entry.artifact_id for entry in unique_entries],
        format_func=lambda artifact_id: unique_labels.get(artifact_id, artifact_id),
        key=SELECTED_ARTIFACT_IDS_KEY,
        on_change=_on_artifact_selection_change,
        help="当前策略默认参与；已保存策略按需勾选加入多策略比较。",
    )
    selected_entries = [entry for entry in unique_entries if entry.artifact_id in selected_ids]
    if not selected_entries:
        selected_ids = list(st.session_state.get(SELECTED_ARTIFACT_IDS_KEY, []))
        selected_entries = [entry for entry in unique_entries if entry.artifact_id in selected_ids]

    if len(selected_entries) < 2:
        st.caption("当前仅有 1 条可比较策略。保存更多快照或额外勾选策略后，可进行多策略比较。")

    selected_labels = {entry.artifact_id: entry.selector_label for entry in selected_entries}
    if selected_entries:
        if len(selected_entries) == 1:
            st.session_state[FOCUS_ARTIFACT_ID_KEY] = selected_entries[0].artifact_id
            st.caption("主策略：" + selected_entries[0].selector_label)
        else:
            st.selectbox(
                "主策略（供收益热图 / 买卖点细看）",
                options=[entry.artifact_id for entry in selected_entries],
                format_func=lambda artifact_id: selected_labels.get(artifact_id, artifact_id),
                key=FOCUS_ARTIFACT_ID_KEY,
                on_change=_on_focus_artifact_change,
            )

    split_col, library_col = st.columns([1.1, 1.9])
    with split_col:
        st.radio(
            "买卖点查看数据集",
            options=["test", "train"],
            format_func=lambda value: "测试集" if value == "test" else "训练集",
            horizontal=True,
            key=SIGNAL_DATASET_SPLIT_KEY,
        )
    with library_col:
        st.caption("策略库视图：")
        for entry in entries:
            st.write(entry.selector_label)

    focus_artifact_id = st.session_state.get(FOCUS_ARTIFACT_ID_KEY)
    focus_entry = next(
        (entry for entry in selected_entries if entry.artifact_id == focus_artifact_id),
        selected_entries[0] if selected_entries else None,
    )
    signal_dataset_split = str(st.session_state.get(SIGNAL_DATASET_SPLIT_KEY, "test"))
    return selected_entries, focus_entry, signal_dataset_split


def _artifact_style(entry: ArtifactLibraryEntry, order_index: int) -> tuple[str, str]:
    final_stage_key = entry.artifact.pipeline_lineage[-1].stage_key if entry.artifact.pipeline_lineage else "baseline"
    color_map = {
        "baseline": "#c8ae7d",
        "sm_base": "#2f5d62",
        "fsm_base": "#8f3b2e",
        "search": "#f39c12",
        "ml": "#7d5a9e",
        "regime": "#18636c",
    }
    saved_dash_cycle = ("dash", "dot", "dashdot", "longdash", "longdashdot")
    color = color_map.get(final_stage_key, "#2f5d62")
    dash = "solid" if entry.slot_kind == "current" else saved_dash_cycle[order_index % len(saved_dash_cycle)]
    return color, dash


def _resolve_score_columns(df: pd.DataFrame | None) -> tuple[str | None, str | None, str]:
    if df is None or df.empty:
        return None, None, "评分"
    if {"factor_score", "factor_percentile"}.issubset(df.columns):
        return "factor_score", "factor_percentile", "因子评分"
    if {"regime_score", "regime_score_percentile"}.issubset(df.columns):
        return "regime_score", "regime_score_percentile", "Regime 评分"
    return None, None, "评分"


def _build_score_chart_input(df: pd.DataFrame | None) -> tuple[pd.DataFrame | None, str]:
    score_col, percentile_col, score_label = _resolve_score_columns(df)
    if df is None or score_col is None or percentile_col is None:
        return None, score_label

    score_df = df.copy()
    score_df["factor_score"] = pd.to_numeric(score_df[score_col], errors="coerce")
    score_df["factor_percentile"] = pd.to_numeric(score_df[percentile_col], errors="coerce")
    return score_df, score_label


def _build_selected_artifact_payload(selected_entries: list[ArtifactLibraryEntry]) -> dict[str, dict]:
    payload: dict[str, dict] = {}
    for order_index, entry in enumerate(selected_entries):
        color, dash = _artifact_style(entry, order_index)
        artifact = entry.artifact
        payload[entry.compare_label] = {
            "label": entry.compare_label,
            "short_label": entry.compare_label,
            "eval": dict(artifact.eval),
            "equity_series": artifact.equity_series.copy(),
            "returns_series": artifact.returns_series.copy(),
            "color": color,
            "dash": dash,
            "ml_quality": dict(artifact.ml_quality) if artifact.ml_quality is not None else None,
        }
    return payload


def _resolve_current_artifact_entry(
    current_artifact: StrategyArtifact,
    selected_entries: list[ArtifactLibraryEntry],
) -> ArtifactLibraryEntry:
    for entry in selected_entries:
        if entry.artifact_id == current_artifact.id:
            return entry
    return ArtifactLibraryEntry(
        artifact_id=current_artifact.id,
        artifact=current_artifact,
        selector_label=f"当前 · {current_artifact.display_label}",
        compare_label=current_artifact.display_label,
        slot_kind="current",
    )


def _render_workbench_entry(
    *,
    total_rows: int,
    split_idx: int,
    df_indicators: pd.DataFrame,
    market: str,
) -> str | None:
    st.caption("先选模型路径，再显式点击“生成策略”；页面不再默认预计算全模型结果。")

    if pd.api.types.is_datetime64_any_dtype(df_indicators["date"]):
        date_range = f"{df_indicators['date'].min().date()} 到 {df_indicators['date'].max().date()}"
    else:
        date_range = "行索引"

    summary_col, family_col = st.columns([1.4, 1.0])
    with summary_col:
        st.write(
            f"行数：{total_rows:,} | 训练：{split_idx:,} | 测试：{max(total_rows - split_idx, 0):,} | "
            f"日期范围：{date_range}"
        )
    with family_col:
        st.caption("Step 1 选择 Family")
        family_options = ["", "baseline", "search"]
        if _normalize_market_key(market) == "US":
            family_options.append("regime")
        if st.session_state.get("single_stock_workflow_family") not in family_options:
            st.session_state["single_stock_workflow_family"] = ""
        family = st.selectbox(
            "模型家族",
            options=family_options,
            format_func=lambda value: {
                "": "请选择模型家族",
                "baseline": "Baseline",
                "search": "Search",
                "regime": "Regime (Experimental)",
            }[value],
            key="single_stock_workflow_family",
        )

    st.caption("Step 2 完成模型配置；Step 3 点击“生成策略”提交当前请求。")
    return family or None


def _render_model_configuration_section(family: str | None) -> StrategyRequest:
    if family is None:
        request = StrategyRequest()
        _render_model_configuration_guidance(request)
        return request

    request = _build_strategy_request(family)
    _render_model_configuration_guidance(request)
    return request


def _build_strategy_request(family: str) -> StrategyRequest:
    if family == "baseline":
        baseline_kind = st.selectbox(
            "Step 2 · Baseline 路径",
            options=["", "naive", "mean", "drift"],
            format_func=lambda value: {
                "": "请选择 Baseline 类型",
                "naive": "Naive（买入持有）",
                "mean": "Mean（均值基线）",
                "drift": "Drift（漂移基线）",
            }[value],
            key="single_stock_workflow_baseline_kind",
        )
        return StrategyRequest(family="baseline", baseline_kind=baseline_kind or None)

    if family == "regime":
        if st.session_state.get("single_stock_workflow_regime_kind") not in {
            ADAPTIVE_REGIME_KIND,
            "dual_state_router",
            "no_market",
            "no_router",
        }:
            st.session_state["single_stock_workflow_regime_kind"] = ADAPTIVE_REGIME_KIND
        regime_kind = st.selectbox(
            "Step 2 · Regime 路径",
            options=[ADAPTIVE_REGIME_KIND, "dual_state_router", "no_market", "no_router"],
            format_func=lambda value: {
                ADAPTIVE_REGIME_KIND: "Adaptive Router V1（推荐）",
                "dual_state_router": "Legacy Dual-State Router",
                "no_market": "Legacy No-Market Ablation",
                "no_router": "Legacy No-Router Ablation",
            }[value],
            key="single_stock_workflow_regime_kind",
        )
        st.caption("Adaptive Router V1 会优先读取最近一次离线 `regime_artifacts/`；缺失时自动降级到 legacy dual-state router。")
        return StrategyRequest(family="regime", regime_kind=regime_kind or None)

    search_base = st.selectbox(
        "Step 2 · Search 基础模型",
        options=["", "sm", "fsm"],
        format_func=lambda value: {
            "": "请选择 Search 基础模型",
            "sm": "SM（10因子）",
            "fsm": "FSM（FA增强）",
        }[value],
        key="single_stock_workflow_search_base",
    )

    search_trials = 60
    ga_population_size = 30
    ga_generations = 20
    use_search = False
    search_method = None
    use_ml = False
    ml_model_type = None

    if search_base:
        if search_base == "fsm":
            st.caption("FSM 路径会先在训练集拟合 FA，再进入 FSM 基础策略。")

        use_search = st.checkbox("启用参数搜索", value=False, key="single_stock_workflow_use_search")
        if use_search:
            search_method = st.selectbox(
                "参数搜索方法",
                options=["bayesian", "genetic", "random"],
                format_func=lambda value: {
                    "bayesian": "贝叶斯优化",
                    "genetic": "遗传算法",
                    "random": "随机搜索",
                }[value],
                key="single_stock_workflow_search_method",
            )
            if search_method == "genetic":
                ga_col1, ga_col2 = st.columns(2)
                with ga_col1:
                    ga_population_size = st.slider(
                        "种群大小",
                        min_value=10,
                        max_value=60,
                        value=30,
                        key="single_stock_workflow_ga_population",
                    )
                with ga_col2:
                    ga_generations = st.slider(
                        "进化代数",
                        min_value=5,
                        max_value=40,
                        value=20,
                        key="single_stock_workflow_ga_generations",
                    )
            else:
                search_trials = st.slider(
                    "搜索次数",
                    min_value=20,
                    max_value=150,
                    value=60 if search_method == "bayesian" else 40,
                    key="single_stock_workflow_search_trials",
                )

        use_ml = st.checkbox("启用 ML 过滤", value=False, key="single_stock_workflow_use_ml")
        if use_ml:
            ml_model_type = st.radio(
                "ML 模型",
                options=["logistic", "lgbm"],
                format_func=lambda value: "Logistic" if value == "logistic" else "LightGBM",
                horizontal=True,
                key="single_stock_workflow_ml_model_type",
            )

    return StrategyRequest(
        family="search",
        search_base=search_base or None,
        use_search=use_search,
        search_method=search_method,
        use_ml=use_ml,
        ml_model_type=ml_model_type,
        search_trials=search_trials,
        ga_population_size=ga_population_size,
        ga_generations=ga_generations,
    )


def _render_model_configuration_guidance(request: StrategyRequest) -> None:
    if request.family is None:
        st.info("请先在上方选择 Baseline、Search 或 Regime，再展开具体配置。")
        return

    if request.family == "baseline":
        st.caption("Baseline 路径只生成单步基线策略，不进入参数搜索或 ML 过滤。")
        if request.baseline_kind is None:
            st.info("请选择 Naive / Mean / Drift 之一。")
        return

    if request.family == "regime":
        if request.regime_kind == ADAPTIVE_REGIME_KIND:
            st.caption("Adaptive 路径会先预测离散 state，再按 state 在 baseline / SM / FSM 候选中动态切换。")
            st.write("当前版本只在美股展示，默认使用 SPY 作为市场代理；若 adaptive artifact 缺失或损坏，会降级到 legacy dual-state router。")
        else:
            st.caption("Legacy Regime 路径会固定执行双状态路由：股票状态 + 市场代理状态 -> trend / range / risk-off。")
            st.write("当前版本只在美股展示，默认使用 SPY 作为市场代理；若代理不可用，会降级为 stock-only 路由。")
        return

    if request.search_base is None:
        st.info("请先选择 SM 或 FSM，再决定是否追加参数搜索与 ML 过滤。")
        return

    st.caption("Search 路径的固定顺序是：基础策略 -> 可选参数搜索 -> 可选 ML 过滤。")
    if request.use_search:
        st.write("已启用参数搜索：搜索结果只进入 lineage / artifact，不会自动回写侧边栏参数。")
    if request.use_ml:
        st.write("已启用 ML 过滤：ML 始终消费最近一步成功的上游结果。")


def _derive_workbench_page_state(
    workspace_status: str,
    current_artifact: StrategyArtifact | None,
    request: StrategyRequest,
) -> str:
    if current_artifact is None:
        return "REQUEST_DRAFT" if request.family is not None else "EMPTY"
    return workspace_status


def _render_workbench_status(
    *,
    slot,
    page_state: str,
    was_reset: bool,
    current_artifact: StrategyArtifact | None,
    request_ready: bool,
) -> None:
    with slot.container():
        if was_reset:
            st.info("检测到股票/数据上下文变化，已清空上一个上下文中的策略结果。")

        if page_state == "EMPTY":
            st.info("请选择模型路径并生成第一条策略。")
        elif page_state == "REQUEST_DRAFT" and current_artifact is None:
            if request_ready:
                st.info("当前请求已完成配置，尚未生成结果。")
            else:
                st.info("当前正在配置策略请求；完成必要选择后即可生成。")
        elif page_state == "REQUEST_DRAFT":
            st.warning("当前展示的是上次成功生成的结果；重新生成后才会更新下游分析。")
        elif page_state == "CURRENT_AND_SAVED":
            st.success("当前上下文中存在最新策略和已保存快照。")
        else:
            st.success("当前上下文中已有最新生成策略，可继续查看下游分析或再次生成。")


def _get_request_missing_items(request: StrategyRequest) -> list[str]:
    if request.family is None:
        return ["请选择 Baseline、Search 或 Regime"]

    if request.family == "baseline":
        if request.baseline_kind is None:
            return ["请选择 Naive / Mean / Drift"]
        return []

    if request.family == "regime":
        if request.regime_kind is None:
            return ["Regime 配置缺失"]
        return []

    missing_items: list[str] = []
    if request.search_base is None:
        missing_items.append("请选择 SM 或 FSM")
    if request.use_search and request.search_method is None:
        missing_items.append("请选择参数搜索方法")
    if request.use_ml and request.ml_model_type is None:
        missing_items.append("请选择 ML 模型")
    return missing_items


def _describe_request_pipeline(request: StrategyRequest) -> str | None:
    if request.family is None:
        return None

    if request.family == "baseline":
        label_map = {
            "naive": "Naive",
            "mean": "Mean",
            "drift": "Drift",
        }
        if request.baseline_kind is None:
            return "Baseline -> 等待选择 Naive / Mean / Drift"
        return f"Baseline -> {label_map[request.baseline_kind]} -> 生成策略"

    if request.family == "regime":
        if request.regime_kind is None:
            return "Regime -> 等待选择 adaptive / legacy 路径"
        if request.regime_kind == ADAPTIVE_REGIME_KIND:
            return "Regime -> Adaptive Router V1 -> 动态候选切换 -> 生成策略"
        return "Regime -> Legacy 双状态路由 -> 生成策略"

    if request.search_base is None:
        return "Search -> 等待选择 SM / FSM"

    pipeline_parts = ["FA", "FSM基础"] if request.search_base == "fsm" else ["SM基础"]
    if request.use_search:
        pipeline_parts.append("参数搜索")
    if request.use_ml:
        pipeline_parts.append("ML过滤")
    return "Search -> " + " -> ".join(pipeline_parts) + " -> 生成策略"


def _render_current_workflow_lineage(
    artifact: StrategyArtifact,
    *,
    is_stale_result: bool,
) -> None:
    if is_stale_result:
        st.caption("当前展示的是上次成功生成的 lineage；新草稿尚未提交。")

    st.caption("阶段链路：" + " -> ".join(stage.display_label for stage in artifact.pipeline_lineage))
    stage_columns = st.columns(len(artifact.pipeline_lineage))
    for idx, stage in enumerate(artifact.pipeline_lineage):
        with stage_columns[idx]:
            st.markdown(f"**{stage.display_label}**")
            if idx == len(artifact.pipeline_lineage) - 1:
                st.caption("最终提交到 current_artifact")
            else:
                st.caption("中间阶段结果")

            st.write(f"累计收益：{format_pct(stage.eval.get('cumret', 0.0))}")
            st.write(f"最大回撤：{format_pct(stage.eval.get('maxdd', 0.0))}")
            st.write(f"夏普：{stage.eval.get('sharpe', 0.0):.2f}")

            if stage.metadata.get("search_method"):
                st.caption("参数搜索：" + str(stage.metadata["search_method"]))
            if stage.metadata.get("regime_summary"):
                regime_summary = stage.metadata["regime_summary"]
                st.caption("市场代理：" + str(regime_summary.get("market_proxy_symbol", "SPY")))
                st.caption("最新 Regime：" + _format_execution_regime_label(regime_summary.get("latest_execution_regime")))
            if stage.ml_quality is not None:
                precision = stage.ml_quality.get("precision")
                if precision is not None:
                    st.caption("ML Precision：" + format_pct(precision))


def _resolve_market_visualization_state(*, render_controls: bool) -> tuple[str, str, str]:
    period_default = _ensure_segmented_value("single_stock_chart_period", ["D", "W", "M"], "D")
    scope_default = _ensure_segmented_value("single_stock_market_scope", ["dataset", "train"], "dataset")
    indicator_default = _ensure_segmented_value("single_stock_indicator_view", ["MACD", "RSI", "VOL"], "MACD")
    if not render_controls:
        return period_default, scope_default, indicator_default

    period_col, scope_col, indicator_col = st.columns(3, gap="small")
    with period_col:
        st.caption("股票周期")
        period_key = st.segmented_control(
            "股票周期",
            options=["D", "W", "M"],
            format_func=lambda value: {"D": "日 K", "W": "周 K", "M": "月 K"}[value],
            default=period_default,
            key="single_stock_chart_period",
            width="stretch",
            label_visibility="collapsed",
        ) or period_default
    with scope_col:
        st.caption("数据集时间")
        chart_scope = st.segmented_control(
            "数据集时间",
            options=["dataset", "train"],
            format_func=lambda value: "完整数据" if value == "dataset" else "训练集",
            default=scope_default,
            key="single_stock_market_scope",
            width="stretch",
            label_visibility="collapsed",
        ) or scope_default
    with indicator_col:
        st.caption("指标小图")
        indicator_view = st.segmented_control(
            "指标小图",
            options=["MACD", "RSI", "VOL"],
            format_func=lambda value: {"MACD": "MACD", "RSI": "RSI", "VOL": "成交量"}[value],
            default=indicator_default,
            key="single_stock_indicator_view",
            width="stretch",
            label_visibility="collapsed",
        ) or indicator_default
    return period_key, chart_scope, indicator_view


def _build_market_visualizations(
    *,
    df_raw: pd.DataFrame,
    indicator_kwargs: dict[str, Any],
    artifact: StrategyArtifact | None,
    split_date: pd.Timestamp,
    symbol: str,
    rsi_upper: float,
    rsi_lower: float,
    render_controls: bool,
) -> tuple[go.Figure, go.Figure, go.Figure, str]:
    period_key, chart_scope, indicator_view = _resolve_market_visualization_state(render_controls=render_controls)
    chart_df = _prepare_chart_dataframe(df_raw, indicator_kwargs, period_key)
    scope_note = ""
    if chart_scope == "train":
        filtered = chart_df[chart_df["date"] <= split_date].copy()
        if filtered.empty:
            scope_note = "当前周期下训练窗口可用样本不足，已回退到完整数据区间。"
        else:
            chart_df = filtered

    visible_range = compute_chart_view_range(chart_df, period_key)
    latest_close = _format_decimal(chart_df["close"].iloc[-1]) if not chart_df.empty else "N/A"
    ema_fast_value = _format_decimal(chart_df["ema_fast"].iloc[-1]) if "ema_fast" in chart_df.columns and not chart_df["ema_fast"].isna().all() else "N/A"
    ema_slow_value = _format_decimal(chart_df["ema_slow"].iloc[-1]) if "ema_slow" in chart_df.columns and not chart_df["ema_slow"].isna().all() else "N/A"
    scope_label = "训练集" if chart_scope == "train" and not scope_note else "完整数据"
    indicator_title = {"MACD": "MACD 指标", "RSI": "RSI 指标", "VOL": "成交量"}[indicator_view]

    candle = _build_candlestick_chart(
        chart_df=chart_df,
        symbol=symbol,
        period_key=period_key,
        split_date=None if scope_label == "训练集" else split_date,
    )
    ind_fig = _build_indicator_mini_chart(
        chart_df=chart_df,
        indicator_view=indicator_view,
        period_key=period_key,
        rsi_upper=rsi_upper,
        rsi_lower=rsi_lower,
        visible_range=visible_range,
    )

    score_fig = go.Figure()
    score_df = None
    score_label = "因子评分"
    if artifact is not None:
        score_df = artifact.full_signal_df.copy()
        if chart_scope == "train":
            score_df = score_df[score_df["date"] <= split_date].copy()

    score_input_df, score_label = _build_score_chart_input(score_df)
    if score_input_df is not None:
        score_fig = _build_factor_score_chart(score_input_df, score_label=score_label)

    if render_controls:
        render_html(
            f"""
<div class="analysis-chart-meta">
  <span class="analysis-chart-chip">{html.escape(scope_label)}</span>
  <span class="analysis-chart-chip">{html.escape({'D': '日 K', 'W': '周 K', 'M': '月 K'}[period_key])}</span>
  <span class="analysis-chart-chip">最新收盘 {html.escape(latest_close)}</span>
  <span class="analysis-chart-chip">EMA 快线 {html.escape(ema_fast_value)}</span>
  <span class="analysis-chart-chip">EMA 慢线 {html.escape(ema_slow_value)}</span>
</div>
            """
        )
        if scope_note:
            render_status_note(scope_note, tone="warning")
        linked_chart = create_candlestick_indicator_chart(
            chart_df=chart_df,
            symbol=symbol,
            period_key=period_key,
            split_date=None if scope_label == "训练集" else split_date,
            indicator_view=indicator_view,
            rsi_upper=rsi_upper,
            rsi_lower=rsi_lower,
        )
        st.plotly_chart(linked_chart, width="stretch")

    return candle, ind_fig, score_fig, indicator_title


def _format_execution_regime_label(value: object) -> str:
    mapping = {
        "trend_follow": "Trend Follow",
        "range_selective": "Range Selective",
        "risk_off": "Risk Off",
    }
    text = str(value or "").strip()
    return mapping.get(text, text or "N/A")


def _get_regime_summary(artifact: StrategyArtifact | None) -> dict[str, Any] | None:
    if artifact is None or not artifact.pipeline_lineage:
        return None
    final_stage = artifact.pipeline_lineage[-1]
    summary = final_stage.metadata.get("regime_summary")
    return summary if isinstance(summary, dict) else None


def _build_regime_timeline_figure(artifact: StrategyArtifact) -> go.Figure:
    if artifact.full_signal_df.empty or "execution_regime" not in artifact.full_signal_df.columns:
        return go.Figure()

    timeline_df = artifact.full_signal_df[["date", "execution_regime"]].copy().tail(30)
    timeline_df["date"] = pd.to_datetime(timeline_df["date"], errors="coerce")
    timeline_df = timeline_df.dropna(subset=["date"])
    if timeline_df.empty:
        return go.Figure()

    color_map = {
        "trend_follow": "#1d6f6d",
        "range_selective": "#c27a2c",
        "risk_off": "#a84a3c",
    }
    fig = go.Figure(
        go.Bar(
            x=timeline_df["date"],
            y=[1.0] * len(timeline_df),
            marker_color=[color_map.get(str(item), "#7d5a9e") for item in timeline_df["execution_regime"]],
            customdata=timeline_df["execution_regime"],
            hovertemplate="日期: %{x|%Y-%m-%d}<br>Regime: %{customdata}<extra></extra>",
            showlegend=False,
        )
    )
    fig.update_yaxes(visible=False, range=[0, 1.2])
    fig.update_xaxes(title="最近 30 个交易日")
    fig.update_layout(height=220, bargap=0.12, margin=dict(t=24, r=16, b=32, l=16))
    _apply_analysis_chart_layout(fig, height=220)
    return fig


def _render_regime_diagnostics_panel(artifact: StrategyArtifact) -> None:
    regime_summary = _get_regime_summary(artifact)
    if regime_summary is None:
        return

    render_html(
        """
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">Regime Diagnostics</h4>
  <p class="analysis-callout-copy">展示执行分支占比、各分支收益贡献，以及最近 30 个交易日的 regime 时间线。</p>
</div>
        """
    )
    proxy_mode = str(regime_summary.get("market_proxy_mode") or "enabled")
    proxy_symbol = str(regime_summary.get("market_proxy_symbol") or "SPY")
    latest_regime = _format_execution_regime_label(regime_summary.get("latest_execution_regime"))
    proxy_note = "SPY 代理可用" if proxy_mode == "enabled" else "已切到 stock-only" if proxy_mode == "fallback_stock_only" else "研究禁用市场代理"

    overview_col1, overview_col2, overview_col3 = st.columns(3)
    overview_col1.metric("市场代理", proxy_symbol, proxy_note)
    overview_col2.metric("代理模式", proxy_mode, "enabled / disabled / fallback")
    overview_col3.metric("最新 Regime", latest_regime)

    regime_table = pd.DataFrame(regime_summary.get("regime_table") or [])
    if not regime_table.empty:
        regime_table = regime_table.copy()
        regime_table["regime"] = regime_table["regime"].map(_format_execution_regime_label)
        st.dataframe(
            regime_table,
            width="stretch",
            hide_index=True,
            column_config={
                "regime": st.column_config.TextColumn("Regime"),
                "day_count": st.column_config.NumberColumn("天数", format="%d"),
                "day_ratio": st.column_config.NumberColumn("时间占比", format="%.2f"),
                "return_contribution": st.column_config.NumberColumn("收益贡献", format="%.4f"),
                "exposure_ratio": st.column_config.NumberColumn("Exposure 占比", format="%.2f"),
            },
        )

    timeline_fig = _build_regime_timeline_figure(artifact)
    if timeline_fig.data:
        st.plotly_chart(timeline_fig, width="stretch")
    if regime_summary.get("market_proxy_warning"):
        render_status_note(str(regime_summary["market_proxy_warning"]), tone="warning")


def _render_generated_strategy_summary(
    artifact: StrategyArtifact | None,
    strategy_preset: str,
) -> str:
    if artifact is None:
        render_status_note("请先在左侧工作台生成一条策略。", tone="info")
        return "未生成策略"
    if artifact.full_signal_df.empty:
        render_status_note("当前策略缺少可展示的信号数据。", tone="warning")
        return artifact.display_label

    latest = artifact.full_signal_df.iloc[-1]
    score_col, percentile_col, score_label = _resolve_score_columns(artifact.full_signal_df)
    latest_factor = "课程基线策略"
    latest_percentile = "N/A"
    target_position = _safe_float(latest.get("target_position")) or 0.0
    score_metric_label = "评分 / 分位"
    if score_col is not None and percentile_col is not None:
        score_value = _safe_float(latest.get(score_col))
        latest_factor = f"{score_value:.2f}" if score_value is not None else "N/A"
        percentile_value = pd.to_numeric(latest.get(percentile_col), errors="coerce")
        if pd.notna(percentile_value):
            latest_percentile = f"{float(percentile_value) * 100:.1f}%"
        score_metric_label = f"{score_label} / 分位"
    eval_result = artifact.eval
    final_stage = artifact.pipeline_lineage[-1].display_label if artifact.pipeline_lineage else "未记录"
    action_text = _describe_strategy_action(artifact)
    metrics = [
        ("当前 artifact", artifact.display_label, "右侧所有结果默认读取 current_artifact"),
        ("预设来源", strategy_preset, f"最终阶段 {final_stage}"),
        ("最新建议", action_text, "按最近一个交易日信号与目标仓位生成"),
        (score_metric_label, latest_factor, latest_percentile),
        ("目标仓位", f"{target_position:.1f}", "来自最新一行 target_position"),
        ("累计收益", format_pct(eval_result.get("cumret")), "测试期"),
        ("最大回撤", format_pct(eval_result.get("maxdd")), "测试期"),
        ("夏普", _fmt_eval_metric(eval_result.get("sharpe"), "sharpe"), "风险调整后表现"),
    ]
    metrics_markup = "".join(
        f"""
<div class="analysis-kv-item">
  <span class="analysis-kv-label">{html.escape(label)}</span>
  <span class="analysis-kv-value">{html.escape(value)}</span>
  <span class="analysis-kv-meta">{html.escape(meta)}</span>
</div>
        """
        for label, value, meta in metrics
    )
    render_html(
        f"""
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">当前策略摘要</h4>
  <p class="analysis-callout-copy">当前已提交 artifact：{html.escape(artifact.display_label)}。{html.escape(action_text)}</p>
  <div class="analysis-kv-grid">{metrics_markup}</div>
</div>
        """
    )
    return artifact.display_label


def _render_strategy_library_overview(
    selected_entries: list[ArtifactLibraryEntry],
    current_artifact: StrategyArtifact | None,
    saved_artifacts: list[StrategyArtifact],
    focus_entry: ArtifactLibraryEntry | None,
    signal_dataset_split: str,
) -> None:
    if current_artifact is None:
        return

    selected_labels = "、".join(entry.compare_label for entry in selected_entries) if selected_entries else "无"
    focus_label = focus_entry.compare_label if focus_entry is not None else "无"
    split_label = "测试集" if signal_dataset_split == "test" else "训练集"
    st.caption(
        f"当前策略 1 条 + 已保存 {len(saved_artifacts)} 条；当前参与比较：{selected_labels}。"
    )
    st.caption(f"主策略：{focus_label} | 买卖点读取：{split_label}。")


def _describe_strategy_action(artifact: StrategyArtifact) -> str:
    if artifact.full_signal_df.empty:
        return "当前没有足够的信号数据。"

    latest = artifact.full_signal_df.iloc[-1]
    target_position = _safe_float(latest.get("target_position")) or 0.0
    execution_regime = _format_execution_regime_label(latest.get("execution_regime"))
    if bool(latest.get("buy_signal")):
        return f"最新信号偏多，目标仓位 {target_position:.1f}，执行分支 {execution_regime}。"
    if bool(latest.get("sell_signal")):
        return f"最新信号偏空，目标仓位 {target_position:.1f}，执行分支 {execution_regime}。"
    if target_position >= 0.8:
        return f"当前维持高仓位，目标仓位 {target_position:.1f}，执行分支 {execution_regime}。"
    if target_position >= 0.2:
        return f"当前处于观察仓位，目标仓位 {target_position:.1f}，执行分支 {execution_regime}。"
    return f"当前更接近观望状态，执行分支 {execution_regime}。"


def _render_strategy_result_empty(
    *,
    page_state: str,
    request_ready: bool,
    request_path: str | None,
) -> None:
    render_html(
        """
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">结果板暂未生成</h4>
  <p class="analysis-callout-copy">左侧完成模型路径后，这里会承接当前策略摘要、净值 / 回撤 / 月度收益、买卖点、Walk-Forward 和策略比对视图。</p>
</div>
        """
    )
    if request_path:
        render_status_note("当前草稿路径：" + request_path, tone="info")

    if page_state == "EMPTY":
        render_status_note("先在左侧选择 Baseline、Search 或 Regime 家族，结果板才会进入可配置状态。", tone="info")
    elif request_ready:
        render_status_note("当前草稿已经准备好，点击“生成策略”后右侧会提交新的 current_artifact。", tone="positive")
    else:
        render_status_note("当前草稿尚未补齐，先完成左侧待选项。", tone="warning")


def _render_strategy_workspace_result(
    *,
    current_artifact: StrategyArtifact,
    current_entry: ArtifactLibraryEntry,
    strategy_preset: str,
    is_stale_result: bool,
    signal_dataset_split: str,
) -> tuple[str, go.Figure, go.Figure, dict[str, dict], list[str]]:
    suggestion = _render_generated_strategy_summary(current_artifact, strategy_preset)

    st.divider()
    render_html(
        """
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">当前工作流链路</h4>
  <p class="analysis-callout-copy">继续沿用 W5 的分阶段产物语义，便于判断当前结果来自 baseline、search、regime 或 ML 过滤后的最终提交。</p>
</div>
        """
    )
    _render_current_workflow_lineage(current_artifact, is_stale_result=is_stale_result)
    if _get_regime_summary(current_artifact) is not None:
        st.divider()
        _render_regime_diagnostics_panel(current_artifact)

    st.divider()
    current_payload = _build_selected_artifact_payload([current_entry])
    current_models = list(current_payload.keys())
    equity_fig = _render_test_performance(
        current_payload,
        active_models=current_models,
        title="当前策略净值 / 回撤",
    )
    _render_periodic_returns_heatmap(current_entry)
    _render_artifact_comparison_table(current_payload, current_models)

    detail_view_default = _ensure_segmented_value(
        WORKSPACE_DETAIL_VIEW_KEY,
        ["signals", "walk_forward", "ml"],
        "signals",
    )
    detail_view = st.segmented_control(
        "结果细看",
        options=["signals", "walk_forward", "ml"],
        format_func=lambda value: {
            "signals": "买卖点",
            "walk_forward": "Walk-Forward",
            "ml": "ML 质量",
        }[value],
        default=detail_view_default,
        key=WORKSPACE_DETAIL_VIEW_KEY,
        width="stretch",
    ) or detail_view_default
    signal_fig = go.Figure()
    if detail_view == "signals":
        signal_fig = _render_trade_signals(current_entry, signal_dataset_split)
    elif detail_view == "walk_forward":
        _render_walk_forward(current_artifact)
    else:
        if current_artifact.ml_quality is None:
            render_status_note("当前策略路径没有可展示的 ML 过滤质量指标。", tone="info")
        else:
            _render_ml_quality(current_payload, current_models)

    return suggestion, equity_fig, signal_fig, current_payload, current_models


def _pick_best_artifact_entry(selected_entries: list[ArtifactLibraryEntry]) -> ArtifactLibraryEntry | None:
    if not selected_entries:
        return None

    def sort_key(entry: ArtifactLibraryEntry) -> tuple[float, float]:
        eval_result = entry.artifact.eval
        cumret = _safe_float(eval_result.get("cumret"))
        sharpe = _safe_float(eval_result.get("sharpe"))
        return (
            cumret if cumret is not None else float("-inf"),
            sharpe if sharpe is not None else float("-inf"),
        )

    return max(selected_entries, key=sort_key)


def _render_strategy_compare_summary(
    selected_entries: list[ArtifactLibraryEntry],
    focus_entry: ArtifactLibraryEntry | None,
    signal_dataset_split: str,
) -> ArtifactLibraryEntry | None:
    best_entry = _pick_best_artifact_entry(selected_entries)
    focus_label = focus_entry.compare_label if focus_entry is not None else "无"
    split_label = "测试集" if signal_dataset_split == "test" else "训练集"

    best_title = best_entry.compare_label if best_entry is not None else "暂无可比策略"
    best_eval = best_entry.artifact.eval if best_entry is not None else {}
    metrics = [
        ("当前最佳", best_title, "按测试期累计收益优先，夏普作为并列时的次级排序"),
        ("参与策略数", str(len(selected_entries)), f"主策略 {focus_label}"),
        ("买卖点读取", split_label, "热图和买卖点细看都跟随当前主策略"),
        ("累计收益", format_pct(best_eval.get("cumret")) if best_entry is not None else "N/A", "测试期结果"),
        ("最大回撤", format_pct(best_eval.get("maxdd")) if best_entry is not None else "N/A", "越低越稳"),
        ("夏普", _fmt_eval_metric(best_eval.get("sharpe"), "sharpe") if best_entry is not None else "N/A", "风险调整后表现"),
    ]
    metrics_markup = "".join(
        f"""
<div class="analysis-kv-item">
  <span class="analysis-kv-label">{html.escape(label)}</span>
  <span class="analysis-kv-value">{html.escape(value)}</span>
  <span class="analysis-kv-meta">{html.escape(meta)}</span>
</div>
        """
        for label, value, meta in metrics
    )
    render_html(
        f"""
<div class="analysis-subsurface">
  <h4 class="analysis-callout-title">策略比对模式</h4>
  <p class="analysis-callout-copy">左侧保留策略库选择器，右侧只切换结果内容。当前最佳候选：{html.escape(best_title)}。</p>
  <div class="analysis-kv-grid">{metrics_markup}</div>
</div>
        """
    )
    return best_entry


def _render_strategy_compare_result(
    *,
    selected_entries: list[ArtifactLibraryEntry],
    focus_entry: ArtifactLibraryEntry | None,
    current_artifact: StrategyArtifact,
    saved_artifacts: list[StrategyArtifact],
    signal_dataset_split: str,
    artifact_payload: dict[str, dict],
    active_artifacts: list[str],
) -> tuple[str, go.Figure, go.Figure]:
    if len(selected_entries) < 2:
        render_status_note("当前只有 1 条策略参与比较。继续保存更多快照后，再观察曲线差异会更有价值。", tone="warning")

    _render_strategy_library_overview(selected_entries, current_artifact, saved_artifacts, focus_entry, signal_dataset_split)
    best_entry = _render_strategy_compare_summary(selected_entries, focus_entry, signal_dataset_split)

    equity_fig = _render_test_performance(
        artifact_payload,
        active_models=active_artifacts,
        title="多策略净值 / 回撤",
    )
    _render_periodic_returns_heatmap(focus_entry)
    _render_artifact_comparison_table(artifact_payload, active_artifacts)

    detail_view_default = _ensure_segmented_value(
        COMPARE_DETAIL_VIEW_KEY,
        ["signals", "ml"],
        "signals",
    )
    detail_view = st.segmented_control(
        "比对细看",
        options=["signals", "ml"],
        format_func=lambda value: {"signals": "买卖点比较", "ml": "ML 质量"}[value],
        default=detail_view_default,
        key=COMPARE_DETAIL_VIEW_KEY,
        width="stretch",
    ) or detail_view_default
    signal_fig = go.Figure()
    if detail_view == "signals":
        signal_fig = _render_trade_signal_comparison(selected_entries, focus_entry, signal_dataset_split)
    else:
        if any(payload.get("ml_quality") is not None for payload in artifact_payload.values()):
            _render_ml_quality(artifact_payload, active_artifacts)
        else:
            render_status_note("当前所选策略没有 ML 过滤质量指标。", tone="info")

    suggestion = best_entry.compare_label if best_entry is not None else current_artifact.display_label
    return suggestion, equity_fig, signal_fig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 图表构建
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _prepare_chart_dataframe(
    df_raw: pd.DataFrame,
    indicator_kwargs: dict[str, Any],
    period_key: str,
) -> pd.DataFrame:
    frame = df_raw.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if frame.empty:
        return frame

    if period_key == "D":
        return add_indicators(frame, **indicator_kwargs)

    frame = frame.set_index("date")
    aggregations: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in frame.columns:
        aggregations["volume"] = "sum"
    resample_rule = "W-FRI" if period_key == "W" else "ME"
    resampled = (
        frame.resample(resample_rule)
        .agg(aggregations)
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    if resampled.empty:
        return resampled
    return add_indicators(resampled, **indicator_kwargs)


def _build_empty_chart(message: str, *, height: int = 220) -> go.Figure:
    return create_empty_state_chart(message, height=height)


def _apply_analysis_chart_layout(fig: go.Figure, *, height: int) -> go.Figure:
    return style_analysis_figure(fig, height=height)


def _build_candlestick_chart(
    *,
    chart_df: pd.DataFrame,
    symbol: str,
    period_key: str,
    split_date: pd.Timestamp | None,
) -> go.Figure:
    """构建 K 线主图。"""
    return create_candlestick_chart(
        chart_df=chart_df,
        symbol=symbol,
        period_key=period_key,
        split_date=split_date,
        height=520,
    )


def _build_indicator_mini_chart(
    *,
    chart_df: pd.DataFrame,
    indicator_view: str,
    period_key: str,
    rsi_upper: float,
    rsi_lower: float,
    visible_range: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> go.Figure:
    """构建指标小图。"""
    if chart_df.empty:
        return _build_empty_chart("暂无可展示的指标数据。")

    tokens = get_plotly_theme_tokens()
    if indicator_view == "RSI":
        if "rsi" not in chart_df.columns or chart_df["rsi"].isna().all():
            return _build_empty_chart("当前周期下没有可用的 RSI 指标。")
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=chart_df["date"],
                y=chart_df["rsi"],
                name="RSI",
                line=dict(color=tokens["muted_text"], width=1.8),
            )
        )
        fig.add_hline(y=rsi_upper, line_dash="dash", line_color=tokens["market_up"])
        fig.add_hline(y=rsi_lower, line_dash="dash", line_color=tokens["market_down"])
        fig.update_yaxes(title="RSI")
        _apply_analysis_chart_layout(fig, height=220)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])] if period_key == "D" else [])
        if visible_range is not None:
            fig.update_xaxes(range=list(visible_range))
        return fig

    if indicator_view == "VOL":
        if "volume" not in chart_df.columns or chart_df["volume"].isna().all():
            return _build_empty_chart("当前周期下没有可用的成交量数据。")
        transform, axis_config, is_compressed = _build_axis_transform(
            [chart_df["volume"]],
            positive_only=True,
        )
        colors = np.where(
            chart_df["close"] >= chart_df["open"],
            f"rgba({int(tokens['market_up'][1:3], 16)}, {int(tokens['market_up'][3:5], 16)}, {int(tokens['market_up'][5:7], 16)}, 0.72)",
            f"rgba({int(tokens['market_down'][1:3], 16)}, {int(tokens['market_down'][3:5], 16)}, {int(tokens['market_down'][5:7], 16)}, 0.72)",
        )
        volume_values = _identity_transform(chart_df["volume"])
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=chart_df["date"],
                y=transform(volume_values),
                marker_color=colors,
                name="成交量",
                customdata=volume_values,
                hovertemplate="<b>成交量</b><br>日期: %{x|%Y-%m-%d}<br>数值: %{customdata:,.0f}<extra></extra>",
            )
        )
        fig.update_yaxes(title="成交量（压缩）" if is_compressed else "成交量", **axis_config)
        _apply_analysis_chart_layout(fig, height=220)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])] if period_key == "D" else [])
        if visible_range is not None:
            fig.update_xaxes(range=list(visible_range))
        return fig

    required = {"macd", "signal", "histogram"}
    if not required.issubset(chart_df.columns) or chart_df[list(required)].isna().all().all():
        return _build_empty_chart("当前周期下没有可用的 MACD 指标。")

    histogram_colors = np.where(
        chart_df["histogram"] >= 0,
        f"rgba({int(tokens['market_down'][1:3], 16)}, {int(tokens['market_down'][3:5], 16)}, {int(tokens['market_down'][5:7], 16)}, 0.62)",
        f"rgba({int(tokens['market_up'][1:3], 16)}, {int(tokens['market_up'][3:5], 16)}, {int(tokens['market_up'][5:7], 16)}, 0.58)",
    )
    transform, axis_config, is_compressed = _build_axis_transform(
        [chart_df["macd"], chart_df["signal"], chart_df["histogram"]],
        positive_only=False,
    )
    histogram_values = _identity_transform(chart_df["histogram"])
    macd_values = _identity_transform(chart_df["macd"])
    signal_values = _identity_transform(chart_df["signal"])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_df["date"],
            y=transform(histogram_values),
            name="Histogram",
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
            line=dict(color=tokens["accent_primary"], width=1.45),
            customdata=signal_values,
            hovertemplate="<b>Signal</b><br>日期: %{x|%Y-%m-%d}<br>数值: %{customdata:.3f}<extra></extra>",
        )
    )
    fig.update_yaxes(title="MACD（压缩）" if is_compressed else "MACD", **axis_config)
    _apply_analysis_chart_layout(fig, height=220)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])] if period_key == "D" else [])
    if visible_range is not None:
        fig.update_xaxes(range=list(visible_range))
    return fig


def _build_factor_score_chart(df: pd.DataFrame, *, score_label: str = "因子评分") -> go.Figure:
    """构建评分 + 分位数图。"""
    tokens = get_plotly_theme_tokens()
    score_fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4]
    )
    score_fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["factor_score"],
            name=score_label,
            line=dict(color=tokens["accent_warm"], width=1.8),
        ),
        row=1,
        col=1,
    )
    score_quantiles = df["factor_score"].dropna().quantile([0.2, 0.5, 0.8])
    if not score_quantiles.empty:
        score_fig.add_hline(
            y=float(score_quantiles.loc[0.2]), line_dash="dot", line_color=tokens["market_down"], row=1, col=1
        )
        score_fig.add_hline(
            y=float(score_quantiles.loc[0.5]), line_dash="dash", line_color=tokens["muted_text"], row=1, col=1
        )
        score_fig.add_hline(
            y=float(score_quantiles.loc[0.8]), line_dash="dot", line_color=tokens["market_up"], row=1, col=1
        )
    score_fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["factor_percentile"] * 100,
            name="评分分位数%",
            line=dict(color=tokens["accent_primary"], width=1.5),
        ),
        row=2,
        col=1,
    )
    score_fig.update_yaxes(title="评分", row=1, col=1)
    score_fig.update_yaxes(title="分位数 %", row=2, col=1)
    _apply_analysis_chart_layout(score_fig, height=360)
    return score_fig


def _build_result_factor_score_figure(
    *,
    artifact: StrategyArtifact | None,
    split_idx: int,
    signal_dataset_split: str,
) -> tuple[go.Figure, str]:
    if artifact is None or artifact.full_signal_df.empty:
        return go.Figure(), "评分"

    score_df = artifact.full_signal_df.copy()
    if signal_dataset_split == "train":
        score_df = score_df.iloc[:split_idx].copy()
    elif signal_dataset_split == "test":
        score_df = score_df.iloc[split_idx:].copy()

    score_input_df, score_label = _build_score_chart_input(score_df)
    required = {"date", "factor_score", "factor_percentile"}
    if score_input_df is None or score_input_df.empty or not required.issubset(score_input_df.columns):
        return go.Figure(), score_label

    score_input_df["date"] = pd.to_datetime(score_input_df["date"], errors="coerce")
    score_input_df = score_input_df.dropna(subset=["date"]).reset_index(drop=True)
    if score_input_df.empty or score_input_df[["factor_score", "factor_percentile"]].dropna(how="all").empty:
        return go.Figure(), score_label

    return _build_factor_score_chart(score_input_df, score_label=score_label), score_label


def _render_result_factor_score_panel(
    *,
    artifact: StrategyArtifact | None,
    artifact_label: str,
    split_idx: int,
    signal_dataset_split: str,
) -> go.Figure:
    split_label = "测试集" if signal_dataset_split == "test" else "训练集"
    score_fig, score_label = _build_result_factor_score_figure(
        artifact=artifact,
        split_idx=split_idx,
        signal_dataset_split=signal_dataset_split,
    )

    with st.expander("评分（可选）", expanded=False):
        if artifact is None:
            render_status_note("生成策略后可查看评分走势。", tone="info")
        elif not score_fig.data:
            render_status_note(f"{artifact_label} 当前没有可展示的 {split_label}{score_label}。", tone="warning")
        else:
            st.caption(f"当前展示 {artifact_label} 的 {split_label}{score_label}与分位数走势。")
            st.plotly_chart(score_fig, width="stretch")
    return score_fig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试集 + Walk-Forward + 信号
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _fmt_eval_metric(value: object, kind: str) -> str:
    """评估区 KPI 展示：kind = pct | sharpe | ratio | days"""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(v):
        return "—"
    if kind == "pct":
        return format_pct(v)
    if kind == "sharpe":
        return f"{v:.2f}"
    if kind == "ratio":
        return f"{v:.2f}"
    if kind == "days":
        return f"{v:.1f}"
    return str(v)
def _render_test_performance(
    model_payload: dict[str, dict],
    *,
    active_models: list[str],
    title: str = "回测净值 / 回撤",
) -> go.Figure:
    """基于已选 artifact 渲染多策略净值/回撤比较。"""
    st.subheader(title)

    if not model_payload:
        st.warning("当前没有可比较的 artifact，跳过净值与回撤。")
        return go.Figure()

    st.markdown("##### 核心指标")
    kpi_specs = [
        ("累计收益率", "cumret", "pct"),
        ("年化收益率", "annret", "pct"),
        ("最大回撤", "maxdd", "pct"),
        ("夏普比率", "sharpe", "sharpe"),
        ("胜率", "winrate", "pct"),
        ("盈亏比", "pnl_ratio", "ratio"),
    ]
    for row in range(0, 6, 3):
        cols = st.columns(3)
        for j in range(3):
            if row + j >= len(kpi_specs):
                break
            title, key, kind = kpi_specs[row + j]
            with cols[j]:
                st.caption(title)
                lines = []
                for model_name in active_models:
                    payload = model_payload[model_name]
                    metric_value = payload["eval"].get(key)
                    lines.append(
                        f"<span style='color:{payload['color']};font-weight:600'>"
                        f"{payload['short_label']}</span>　{_fmt_eval_metric(metric_value, kind)}"
                    )
                st.markdown(
                    "<p style='margin:0;font-size:0.95rem;line-height:1.45'>"
                    + "<br>".join(lines)
                    + "</p>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    st.markdown("##### 净值与回撤")
    series_specs = [
        {
            "name": payload["short_label"],
            "hover_name": model_name,
            "series": payload["equity_series"],
            "color": payload["color"],
            "dash": payload.get("dash", "solid"),
        }
        for model_name in active_models
        for payload in [model_payload[model_name]]
    ]
    equity_fig = create_equity_drawdown_chart(series_specs)
    st.plotly_chart(equity_fig, width="stretch")
    return equity_fig


def _render_periodic_returns_heatmap(focus_entry: ArtifactLibraryEntry | None) -> None:
    st.markdown("##### 月度收益热图")
    if focus_entry is None:
        st.info("请先选定一个主策略，再查看收益热图。")
        return

    heatmap_fig = create_periodic_returns_heatmap(
        returns_series={focus_entry.compare_label: focus_entry.artifact.returns_series},
        period="M",
    )
    if heatmap_fig:
        st.plotly_chart(heatmap_fig, width="stretch")
        st.caption("按主策略测试集日收益率复利聚合到月份；绿色代表正收益，红色代表负收益。")
    else:
        st.info("当前主策略的测试集跨度不足以生成月度收益热图。")


def _render_artifact_comparison_table(model_payload: dict[str, dict], active_models: list[str]) -> None:
    st.markdown("##### 指标对比表")
    if not model_payload:
        st.info("当前没有可展示的策略指标。")
        return

    comp = build_comparison_table([model_payload[name]["eval"] for name in active_models])
    comp_view = comp.copy()
    _scale_pct_cols = [
        "cumret",
        "annret",
        "maxdd",
        "bench_cumret",
        "bench_annret",
        "bench_maxdd",
        "excess_return",
        "winrate",
        "turnover",
    ]
    for c in _scale_pct_cols:
        if c in comp_view.columns:
            comp_view[c] = pd.to_numeric(comp_view[c], errors="coerce") * 100.0

    st.dataframe(
        comp_view,
        width="stretch",
        hide_index=True,
        column_config={
            "label": st.column_config.TextColumn("模型"),
            "cumret": st.column_config.NumberColumn("累计收益 %", format="%.2f"),
            "annret": st.column_config.NumberColumn("年化收益 %", format="%.2f"),
            "maxdd": st.column_config.NumberColumn("最大回撤 %", format="%.2f"),
            "sharpe": st.column_config.NumberColumn("夏普", format="%.2f"),
            "winrate": st.column_config.NumberColumn("胜率 %", format="%.2f"),
            "pnl_ratio": st.column_config.NumberColumn("盈亏比", format="%.2f"),
            "avg_hold": st.column_config.NumberColumn("均持仓(日)", format="%.1f"),
            "turnover": st.column_config.NumberColumn("换手 %", format="%.2f"),
            "bench_cumret": st.column_config.NumberColumn("基准累计 %", format="%.2f"),
            "bench_annret": st.column_config.NumberColumn("基准年化 %", format="%.2f"),
            "bench_maxdd": st.column_config.NumberColumn("基准回撤 %", format="%.2f"),
            "bench_sharpe": st.column_config.NumberColumn("基准夏普", format="%.2f"),
            "excess_return": st.column_config.NumberColumn("超额 %", format="%.2f"),
        },
    )
    st.caption("表中累计/年化/回撤/胜率/换手/超额等为 ×100 后的百分比数值；夏普与盈亏比为原始比率，未缩放。")


def _render_ml_quality(model_payload: dict[str, dict], active_models: list[str]) -> None:
    active_ml_models = [name for name in active_models if model_payload[name].get("ml_quality") is not None]
    if not active_ml_models:
        return

    st.markdown("##### ML 质量展示")
    ml_specs = [
        ("Precision", "precision"),
        ("Recall", "recall"),
        ("F1", "f1"),
        ("PR-AUC", "pr_auc"),
        ("通过率", "signal_pass_rate"),
    ]
    ml_cols = st.columns(5)
    for col, (title, key) in zip(ml_cols, ml_specs):
        with col:
            st.caption(title)
            lines = []
            for model_name in active_ml_models:
                payload = model_payload[model_name]
                metric_value = payload["ml_quality"].get(key)
                lines.append(
                    f"<span style='color:{payload['color']};font-weight:600'>"
                    f"{payload['short_label']}</span>　{_fmt_eval_metric(metric_value, 'pct')}"
                )
            st.markdown(
                "<p style='margin:0;font-size:0.92rem;line-height:1.4'>"
                + "<br>".join(lines)
                + "</p>",
                unsafe_allow_html=True,
            )

    low_pass_models = []
    for model_name in active_ml_models:
        pass_rate = model_payload[model_name]["ml_quality"].get("signal_pass_rate")
        if pass_rate is not None and pass_rate < 0.30:
            low_pass_models.append(f"{model_payload[model_name]['short_label']} {format_pct(pass_rate)}")
    if low_pass_models:
        st.markdown(
            "<div style='margin:0.5rem 0 1rem 0;padding:0.75rem 1rem;"
            "background:#fff4e6;border-left:4px solid #f39c12;border-radius:0.35rem;"
            "color:#8a4f08;font-size:0.92rem'>"
            f"以下 ML 过滤器信号通过率低于 30%，可能过度过滤：{'；'.join(low_pass_models)}"
            "</div>",
            unsafe_allow_html=True,
        )


def _render_walk_forward(artifact: StrategyArtifact | None) -> None:
    """渲染 Walk-Forward 回测区域。"""
    st.markdown("---")
    st.subheader("Walk-Forward 回测")

    if artifact is None:
        st.info("请先生成当前策略，再执行 Walk-Forward。")
        return

    df = artifact.full_signal_df
    stop_loss_mult = float(artifact.params_snapshot.get("stop_loss_mult", 0.0))
    take_profit_mult = float(artifact.params_snapshot.get("take_profit_mult", 0.0))

    enable_walk = st.checkbox("启用 Walk-Forward", value=True)
    if not enable_walk:
        st.info("已关闭 Walk-Forward 回测。")
        return

    max_window = max(5, len(df) - 1)
    min_train = min(20, max_window)
    min_test = min(5, max_window)

    if max_window <= min_train:
        st.info("数据量较少，已固定训练/测试窗口。")
        train_window = max_window
        test_window = max_window
    else:
        wf_col1, wf_col2 = st.columns(2)
        with wf_col1:
            train_window = st.slider(
                "训练窗口（交易日）",
                min_train,
                max_window,
                min(252, max_window),
                help="每次用训练窗口后接测试窗口滚动回测。",
            )
        with wf_col2:
            test_window = st.slider(
                "测试窗口（交易日）",
                min_test,
                max_window,
                min(63, max_window),
                help="每次滚动的测试区间长度。",
            )

    if train_window + test_window > len(df):
        st.warning("训练窗口 + 测试窗口超过数据长度，请调小窗口。")
        return

    wf_results, wf_equity = walk_forward_backtest(
        df,
        train_window=train_window,
        test_window=test_window,
        stop_loss_mult=stop_loss_mult,
        take_profit_mult=take_profit_mult,
    )
    if wf_equity.empty:
        st.warning("Walk-Forward 回测未产生结果。")
        return

    wf_return = wf_equity["strategy_equity"].iloc[-1] - 1
    wf_bh_return = wf_equity["buy_hold_equity"].iloc[-1] - 1
    st.write(
        f"Walk-Forward 策略收益：{format_pct(wf_return)} | "
        f"买入并持有收益：{format_pct(wf_bh_return)}"
    )

    wf_fig = go.Figure()
    wf_fig.add_trace(
        go.Scatter(
            x=wf_equity["date"],
            y=wf_equity["strategy_equity"],
            name="Walk-Forward 策略",
            line=dict(color="#17becf"),
        )
    )
    wf_fig.add_trace(
        go.Scatter(
            x=wf_equity["date"],
            y=wf_equity["buy_hold_equity"],
            name="买入并持有",
            line=dict(color="#bcbd22"),
        )
    )
    wf_fig.update_layout(height=420, xaxis_title="日期", yaxis_title="净值（起始=1.0）")
    _apply_analysis_chart_layout(wf_fig, height=420)
    st.plotly_chart(wf_fig, width="stretch")

    if not wf_results.empty:
        wf_results_display = wf_results.copy()
        wf_results_display["test_return"] = wf_results_display["test_return"].map(format_pct)
        wf_results_display["test_max_drawdown"] = wf_results_display["test_max_drawdown"].map(format_pct)
        st.dataframe(wf_results_display, width="stretch")


def _render_trade_signals(
    focus_entry: ArtifactLibraryEntry | None,
    signal_dataset_split: str,
) -> go.Figure:
    """渲染主 artifact 的训练/测试集交易信号图。"""
    st.subheader("买卖点查看")
    if focus_entry is None:
        st.info("请先选定一个主策略，再查看买卖点。")
        return go.Figure()

    signal_df = (
        focus_entry.artifact.test_sim_df
        if signal_dataset_split == "test"
        else focus_entry.artifact.train_sim_df
    )
    if signal_df is None or signal_df.empty:
        st.info("当前主策略没有可用的买卖点数据。")
        return go.Figure()

    color, _dash = _artifact_style(focus_entry, 0)
    split_label = "测试集" if signal_dataset_split == "test" else "训练集"

    signal_fig = go.Figure(
        data=[
            go.Scatter(
                x=signal_df["date"],
                y=signal_df["close"],
                mode="lines",
                name="Close",
                line=dict(color=color, width=2.0),
            )
        ]
    )
    signal_fig.add_trace(
        go.Scatter(
            x=signal_df.loc[signal_df["buy_signal"], "date"],
            y=signal_df.loc[signal_df["buy_signal"], "close"],
            mode="markers",
            name=f"{focus_entry.compare_label} Buy",
            marker=dict(color="#2ca02c", size=8, symbol="triangle-up"),
        )
    )
    signal_fig.add_trace(
        go.Scatter(
            x=signal_df.loc[signal_df["sell_signal"], "date"],
            y=signal_df.loc[signal_df["sell_signal"], "close"],
            mode="markers",
            name=f"{focus_entry.compare_label} Sell",
            marker=dict(color="#d62728", size=8, symbol="triangle-down"),
        )
    )
    signal_fig.update_layout(
        height=420,
        xaxis_title="日期",
        yaxis_title="价格",
        title=f"{focus_entry.compare_label} {split_label}买卖点",
    )
    _apply_analysis_chart_layout(signal_fig, height=420)
    st.plotly_chart(signal_fig, width="stretch")
    return signal_fig


def _render_trade_signal_comparison(
    selected_entries: list[ArtifactLibraryEntry],
    focus_entry: ArtifactLibraryEntry | None,
    signal_dataset_split: str,
) -> go.Figure:
    st.subheader("买卖点比较")
    if not selected_entries:
        st.info("请先在左侧策略库中勾选至少一条策略。")
        return go.Figure()
    if focus_entry is None:
        st.info("请先指定主策略，再查看多策略买卖点。")
        return go.Figure()

    split_label = "测试集" if signal_dataset_split == "test" else "训练集"
    base_df = (
        focus_entry.artifact.test_sim_df
        if signal_dataset_split == "test"
        else focus_entry.artifact.train_sim_df
    )
    if base_df is None or base_df.empty:
        st.info("当前主策略没有可用于比较的价格与信号数据。")
        return go.Figure()

    comparison_fig = go.Figure()
    comparison_fig.add_trace(
        go.Scatter(
            x=base_df["date"],
            y=base_df["close"],
            mode="lines",
            name=f"{focus_entry.compare_label} Close",
            line=dict(color=get_plotly_theme_tokens()["accent_primary"], width=2.1),
        )
    )

    buy_symbols = ("triangle-up", "diamond", "circle", "square", "star")
    sell_symbols = ("triangle-down", "diamond-open", "circle-open", "square-open", "x")
    rendered_count = 0
    for order_index, entry in enumerate(selected_entries):
        signal_df = (
            entry.artifact.test_sim_df
            if signal_dataset_split == "test"
            else entry.artifact.train_sim_df
        )
        if signal_df is None or signal_df.empty:
            continue

        color, _dash = _artifact_style(entry, order_index)
        buy_mask = pd.Series(signal_df.get("buy_signal", False), index=signal_df.index).fillna(False).astype(bool)
        sell_mask = pd.Series(signal_df.get("sell_signal", False), index=signal_df.index).fillna(False).astype(bool)
        buy_points = signal_df.loc[buy_mask]
        sell_points = signal_df.loc[sell_mask]

        if not buy_points.empty:
            comparison_fig.add_trace(
                go.Scatter(
                    x=buy_points["date"],
                    y=buy_points["close"],
                    mode="markers",
                    name=f"{entry.compare_label} 买点",
                    marker=dict(
                        color=color,
                        size=9,
                        symbol=buy_symbols[order_index % len(buy_symbols)],
                        line=dict(color="#fff9f0", width=0.8),
                    ),
                )
            )
        if not sell_points.empty:
            comparison_fig.add_trace(
                go.Scatter(
                    x=sell_points["date"],
                    y=sell_points["close"],
                    mode="markers",
                    name=f"{entry.compare_label} 卖点",
                    marker=dict(
                        color=color,
                        size=9,
                        symbol=sell_symbols[order_index % len(sell_symbols)],
                        line=dict(color="#fff9f0", width=0.8),
                    ),
                )
            )
        rendered_count += 1

    if rendered_count == 0:
        st.info("所选策略都没有可展示的买卖点数据。")
        return go.Figure()

    comparison_fig.update_layout(
        title=f"{split_label}多策略买卖点比较",
        xaxis_title="日期",
        yaxis_title="价格",
    )
    _apply_analysis_chart_layout(comparison_fig, height=460)
    st.plotly_chart(comparison_fig, width="stretch")
    render_status_note(f"主价格曲线读取 {focus_entry.compare_label} 的 {split_label} 数据，买卖点叠加展示所有已选策略。", tone="info")
    return comparison_fig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTML 报告导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_single_stock_export(
    *,
    symbol: str,
    df: pd.DataFrame,
    test_df: pd.DataFrame,
    model_payload: dict[str, dict],
    active_models: list[str],
    candle: go.Figure,
    ind_fig: go.Figure,
    score_fig: go.Figure,
    equity_fig: go.Figure,
    signal_fig: go.Figure,
    suggestion: str,
    indicator_title: str = "指标小图",
) -> None:
    """渲染单股票 HTML 报告导出区域。"""
    st.markdown("---")
    st.subheader("📤 导出分析报告")

    if not model_payload and (test_df is None or test_df.empty):
        st.info("请先生成策略后再导出 HTML 报告。")
        return

    single_col1, single_col2, _single_col3 = st.columns([1, 1, 2])
    with single_col1:
        single_export_title = st.text_input(
            "报告标题", value=f"单股策略分析 - {symbol}", key="single_export_title"
        )
    with single_col2:
        single_include_date = st.checkbox("包含生成日期", value=True, key="single_include_date")

    if not st.button("🎁 生成并下载HTML报告", type="primary", width="stretch", key="single_export_btn"):
        return

    with st.spinner("正在生成HTML报告..."):
        generated_at = datetime.now()
        full_html = build_single_stock_export_html(
            title=single_export_title,
            symbol=symbol,
            df=df,
            test_df=test_df,
            model_payload=model_payload,
            active_models=active_models,
            candle=candle,
            ind_fig=ind_fig,
            score_fig=score_fig,
            equity_fig=equity_fig,
            signal_fig=signal_fig,
            suggestion=suggestion,
            indicator_title=indicator_title,
            include_date=single_include_date,
            language=get_ui_language(),
            theme=get_ui_theme(),
            generated_at=generated_at,
        )

        st.download_button(
            label="⬇️ 下载HTML报告",
            data=full_html,
            file_name=f"strategy_report_{symbol}_{generated_at.strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
        st.success("✅ HTML报告已生成！点击上方按钮下载")
