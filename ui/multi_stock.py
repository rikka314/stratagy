"""
多股票对比分析页面
==================
选中多只股票时展示的完整对比分析界面。
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.data import get_stock_label_map, search_stock_candidates
from core.market_context import get_market_indices
from core.portfolio import bayesian_optimize_portfolio, run_portfolio_simulation
from core.utils import load_or_fetch_stock
from core.visualization import (
    create_correlation_heatmap,
    create_factor_score_comparison,
    create_multi_stock_comparison_chart,
    create_periodic_returns_heatmap,
    create_relative_strength_chart,
    create_risk_return_scatter,
)
from ui.export_reports import build_multi_stock_export_html
from ui.theme import (
    apply_plotly_theme,
    get_ui_language,
    get_ui_theme,
    render_analysis_date_range_control,
    render_html,
    render_status_note,
)


MULTI_ROUTE_STATE_KEY = "route_multi_state"
MULTI_STRATEGY_WORKSPACE_KEY = "multi_stock_strategy_workspace"
MULTI_ANALYSIS_SECTION_KEY = "multi_stock_analysis_section"
MULTI_ANALYSIS_CACHE_KEY = "multi_stock_analysis_cache"


def _prepare_multi_stock_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """为多股票页统一清洗日期和价格列，避免静默缺图。"""
    if df is None or df.empty:
        return pd.DataFrame()

    prepared = df.copy()

    if "date" in prepared.columns:
        prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
        prepared = prepared.dropna(subset=["date"])
        prepared = prepared.sort_values("date")
        prepared = prepared.drop_duplicates(subset=["date"], keep="last")

    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    required_columns = [column for column in ["date", "close"] if column in prepared.columns]
    if required_columns:
        prepared = prepared.dropna(subset=required_columns)

    return prepared.reset_index(drop=True)


def _normalize_market_key(market: str | None) -> str:
    return "A" if str(market or "US").strip().upper() in {"A", "CN", "CN_A"} else "US"


def _ensure_segmented_value(key: str, options: list[str], default: str) -> str:
    current = st.session_state.get(key)
    if current not in options:
        st.session_state[key] = default
        return default
    return str(current)


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


def _format_date_text(value: object) -> str:
    if value is None:
        return "N/A"
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "N/A"
    return timestamp.strftime("%Y-%m-%d")


def _delta_class_from_pct(value: object) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return ""
    if numeric > 0:
        return "up"
    if numeric < 0:
        return "down"
    return ""


def _serialize_signature_value(value: object) -> str:
    if value is None:
        return "None"
    timestamp = pd.to_datetime(value, errors="coerce")
    if not pd.isna(timestamp):
        return timestamp.isoformat()
    return str(value)


def _summarize_dataframe_map(df_dict: dict[str, pd.DataFrame]) -> tuple[tuple[str, int, str, str, float | None], ...]:
    summary: list[tuple[str, int, str, str, float | None]] = []
    for symbol, df in sorted(df_dict.items()):
        if df is None or df.empty:
            summary.append((symbol, 0, "N/A", "N/A", None))
            continue

        date_min = _format_date_text(df["date"].min()) if "date" in df.columns else "N/A"
        date_max = _format_date_text(df["date"].max()) if "date" in df.columns else "N/A"
        latest_close = _safe_float(df["close"].iloc[-1]) if "close" in df.columns else None
        summary.append((symbol, int(len(df)), date_min, date_max, latest_close))
    return tuple(summary)


def _render_surface_header(kicker: str, title: str, copy: str) -> None:
    render_html(
        f"""
<div class="surface-kicker">{html.escape(kicker)}</div>
<div class="surface-title">{html.escape(title)}</div>
<p class="surface-copy">{html.escape(copy)}</p>
        """
    )


def _resolve_symbol_meta(
    symbols: list[str],
    *,
    market: str,
    upload_symbols: set[str],
) -> dict[str, dict[str, str]]:
    market_key = _normalize_market_key(market)
    market_label = "A 股" if market_key == "A" else "美股"
    lookup_symbols = [symbol for symbol in symbols if symbol not in upload_symbols]

    try:
        label_map = get_stock_label_map(lookup_symbols, market=market_key) if lookup_symbols else {}
    except Exception:
        label_map = {symbol: symbol for symbol in lookup_symbols}

    symbol_meta: dict[str, dict[str, str]] = {}
    for symbol in symbols:
        if symbol in upload_symbols:
            symbol_meta[symbol] = {
                "display_name": symbol,
                "display_label": f"{symbol} · {market_label} · 上传数据",
                "source_label": "上传数据",
            }
            continue

        full_label = label_map.get(symbol, symbol)
        display_name = full_label
        if full_label.startswith(f"{symbol} "):
            display_name = full_label[len(symbol) + 1 :].strip() or symbol

        symbol_meta[symbol] = {
            "display_name": display_name,
            "display_label": full_label,
            "source_label": "市场数据",
        }
    return symbol_meta


def _build_comparison_stats(
    stock_data_dict: dict[str, pd.DataFrame],
    *,
    symbol_meta: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    comparison_stats: list[dict[str, Any]] = []

    for symbol, df in stock_data_dict.items():
        if df is None or df.empty:
            continue

        close = pd.to_numeric(df.get("close"), errors="coerce")
        if close.empty:
            continue

        start_price = _safe_float(close.iloc[0])
        latest_price = _safe_float(close.iloc[-1])
        total_return = None
        if start_price not in {None, 0} and latest_price is not None:
            total_return = latest_price / start_price - 1.0

        periods = max(len(close) - 1, 1)
        annualized_return = None
        if start_price not in {None, 0} and latest_price not in {None, 0} and start_price > 0 and latest_price > 0:
            try:
                annualized_return = (latest_price / start_price) ** (252 / periods) - 1.0
            except (OverflowError, ZeroDivisionError, ValueError):
                annualized_return = None

        high_series = pd.to_numeric(df.get("high", close), errors="coerce")
        low_series = pd.to_numeric(df.get("low", close), errors="coerce")
        meta = symbol_meta.get(symbol, {"display_name": symbol, "display_label": symbol, "source_label": "市场数据"})

        comparison_stats.append(
            {
                "symbol": symbol,
                "display_name": meta["display_name"],
                "display_label": meta["display_label"],
                "source_label": meta["source_label"],
                "start_price": start_price,
                "latest_price": latest_price,
                "total_return": total_return,
                "annualized_return": annualized_return,
                "high_price": _safe_float(high_series.max()),
                "low_price": _safe_float(low_series.min()),
                "data_days": int(len(df)),
                "date_min": df["date"].min() if "date" in df.columns else None,
                "date_max": df["date"].max() if "date" in df.columns else None,
            }
        )

    return sorted(
        comparison_stats,
        key=lambda item: (item.get("total_return") is None, -(item.get("total_return") or 0.0)),
    )


def _style_display_figure(fig: go.Figure | None, *, height: int | None = None) -> go.Figure | None:
    if fig is None:
        return None
    return apply_plotly_theme(
        fig,
        height=height or fig.layout.height or 520,
        margin=dict(l=56, r=32, t=32, b=64),
        transparent_paper=True,
    )


def _render_multi_stock_header(
    *,
    market: str,
    comparison_stats: list[dict[str, Any]],
    upload_symbols: set[str],
    selected_range: object,
) -> None:
    market_key = _normalize_market_key(market)
    market_label = "A 股" if market_key == "A" else "美股"
    loaded_count = len(comparison_stats)
    uploaded_count = len([item for item in comparison_stats if item["symbol"] in upload_symbols])
    avg_days = int(np.mean([item["data_days"] for item in comparison_stats])) if comparison_stats else 0
    best_entry = next((item for item in comparison_stats if item.get("total_return") is not None), None)
    global_start = min((item["date_min"] for item in comparison_stats if item.get("date_min") is not None), default=None)
    global_end = max((item["date_max"] for item in comparison_stats if item.get("date_max") is not None), default=None)

    display_names = [item["display_name"] for item in comparison_stats]
    if len(display_names) <= 4:
        title_suffix = " · ".join(display_names) if display_names else "当前没有可展示标的"
    else:
        title_suffix = " · ".join(display_names[:4]) + f" +{len(display_names) - 4}"

    quick_items = [
        {
            "label": "参与标的",
            "value": str(loaded_count),
            "meta": f"{uploaded_count} 个上传源，{loaded_count - uploaded_count} 个市场标的",
        },
        {
            "label": "平均数据天数",
            "value": f"{avg_days}",
            "meta": "当前日期筛选后的有效样本",
        },
        {
            "label": "最佳表现",
            "value": best_entry["symbol"] if best_entry is not None else "N/A",
            "meta": _format_signed_pct((best_entry["total_return"] or 0.0) * 100.0 if best_entry is not None else None),
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
    try:
        market_indices = get_market_indices(market_key)
    except Exception:
        market_indices = []
    for item in market_indices:
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

    with st.container(key="multi-stock-analysis-hero"):
        render_html(
            f"""
<div class="analysis-hero-topline">
  <span class="analysis-pill accent">Multi Stock Analysis</span>
  <span class="analysis-pill">{html.escape(market_label)}</span>
  <span class="analysis-pill">{loaded_count} 个对比标的</span>
  <span class="analysis-pill">{uploaded_count} 个上传数据源</span>
</div>
            """
        )
        summary_col, quick_col = st.columns([1.08, 0.92], gap="large")
        with summary_col:
            render_html(
                f"""
<h1 class="analysis-title">多股主分析页</h1>
<div class="analysis-subtitle">{html.escape(title_suffix)}</div>
<div class="analysis-chart-meta">
  <span class="analysis-chart-chip">数据区间 {_format_date_text(global_start)} 到 {_format_date_text(global_end)}</span>
  <span class="analysis-chart-chip">当前市场 {html.escape(market_label)}</span>
</div>
                """
            )
            render_analysis_date_range_control(
                current_range=selected_range,
                key_prefix="multi_stock",
                label="时间范围",
                in_hero=True,
            )
        with quick_col:
            render_html(f"<div class='analysis-quick-grid'>{quick_markup}</div>")
        render_html(f"<div class='analysis-market-strip'>{''.join(index_cards)}</div>")


def _get_multi_route_state() -> dict[str, Any]:
    state = st.session_state.setdefault(
        MULTI_ROUTE_STATE_KEY,
        {
            "view": "analysis",
            "market": "US",
            "symbols": [],
            "uploads": [],
        },
    )
    state.setdefault("view", "analysis")
    state.setdefault("market", "US")
    state["symbols"] = [str(item).strip().upper() for item in state.get("symbols", []) if str(item).strip()]
    state["uploads"] = list(state.get("uploads", []))
    return state


def _replace_multi_route_state(*, market: str, symbols: list[str], uploads: list[dict[str, Any]]) -> None:
    st.session_state[MULTI_ROUTE_STATE_KEY] = {
        "view": "analysis",
        "market": _normalize_market_key(market),
        "symbols": list(dict.fromkeys(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip())),
        "uploads": list(uploads),
    }


def _remove_multi_route_item(symbol: str, *, source: str) -> None:
    state = _get_multi_route_state()
    symbols = list(state.get("symbols", []))
    uploads = list(state.get("uploads", []))

    if source == "upload":
        uploads = [item for item in uploads if str(item.get("symbol") or "").strip().upper() != symbol]
    else:
        symbols = [item for item in symbols if item != symbol]

    _replace_multi_route_state(
        market=state.get("market", "US"),
        symbols=symbols,
        uploads=uploads,
    )
    st.rerun()


def _add_multi_route_symbol(symbol: str, *, market: str) -> None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return

    state = _get_multi_route_state()
    current_symbols = list(state.get("symbols", []))
    upload_symbols = {
        str(item.get("symbol") or "").strip().upper()
        for item in state.get("uploads", [])
        if str(item.get("symbol") or "").strip()
    }
    if normalized in current_symbols or normalized in upload_symbols:
        return

    current_symbols.append(normalized)
    _replace_multi_route_state(
        market=market,
        symbols=current_symbols,
        uploads=list(state.get("uploads", [])),
    )
    st.session_state["multi_stock_edit_query"] = ""
    st.rerun()


def _get_multi_strategy_workspace() -> dict[str, Any]:
    workspace = st.session_state.setdefault(
        MULTI_STRATEGY_WORKSPACE_KEY,
        {
            "signature": None,
            "portfolio_result": None,
            "optimization_signature": None,
            "optimization_result": None,
            "heatmap_cache": {},
        },
    )
    workspace.setdefault("signature", None)
    workspace.setdefault("portfolio_result", None)
    workspace.setdefault("optimization_signature", None)
    workspace.setdefault("optimization_result", None)
    workspace.setdefault("heatmap_cache", {})
    return workspace


def _get_multi_analysis_cache() -> dict[str, Any]:
    cache = st.session_state.setdefault(
        MULTI_ANALYSIS_CACHE_KEY,
        {
            "data_signature": None,
            "stock_data_dict": {},
            "factor_stock_data_dict": {},
            "symbol_meta": {},
            "comparison_stats": [],
            "figure_cache": {},
        },
    )
    cache.setdefault("data_signature", None)
    cache.setdefault("stock_data_dict", {})
    cache.setdefault("factor_stock_data_dict", {})
    cache.setdefault("symbol_meta", {})
    cache.setdefault("comparison_stats", [])
    cache.setdefault("figure_cache", {})
    return cache


def _build_multi_analysis_data_signature(
    *,
    market: str,
    adjust: str,
    compare_stocks: list[str],
    uploads: list[dict[str, Any]],
    start_ts,
    end_ts,
) -> str:
    upload_signature = tuple(
        sorted(
            (
                str(item.get("symbol") or "").strip().upper(),
                str(item.get("name") or "").strip(),
                len(item.get("bytes") or b""),
            )
            for item in uploads
        )
    )
    return repr(
        (
            _normalize_market_key(market),
            str(adjust or "none").strip().lower(),
            tuple(compare_stocks),
            upload_signature,
            _serialize_signature_value(start_ts),
            _serialize_signature_value(end_ts),
        )
    )


def _build_multi_strategy_signature(
    stock_data_dict: dict[str, pd.DataFrame],
    params: dict,
    weights: dict[str, float],
) -> str:
    stock_signature = []
    for symbol, df in stock_data_dict.items():
        last_date = _format_date_text(df["date"].iloc[-1]) if "date" in df.columns and not df.empty else "N/A"
        latest_close = _safe_float(df["close"].iloc[-1]) if "close" in df.columns and not df.empty else None
        stock_signature.append((symbol, len(df), last_date, latest_close))

    param_signature = []
    for key, value in sorted(_strategy_params(params).items()):
        if isinstance(value, (list, tuple)):
            normalized = tuple(value)
        else:
            normalized = value
        param_signature.append((key, normalized))

    weight_signature = tuple(sorted((symbol, round(float(weight), 6)) for symbol, weight in weights.items()))
    return repr((tuple(stock_signature), tuple(param_signature), weight_signature))


def _build_multi_chart_cache_key(
    chart_key: str,
    *,
    stock_data_dict: dict[str, pd.DataFrame],
    factor_stock_data_dict: dict[str, pd.DataFrame],
    params: dict,
    benchmark: str = "equal_weight",
) -> str:
    strategy_signature = tuple(
        sorted(
            (
                key,
                tuple(value) if isinstance(value, (list, tuple)) else value,
            )
            for key, value in _strategy_params(params).items()
        )
    )
    return repr(
        (
            chart_key,
            benchmark,
            _summarize_dataframe_map(stock_data_dict),
            _summarize_dataframe_map(factor_stock_data_dict) if chart_key == "factor_score" else None,
            strategy_signature if chart_key == "factor_score" else None,
        )
    )


def _get_multi_chart_figure(
    chart_key: str,
    *,
    stock_data_dict: dict[str, pd.DataFrame],
    factor_stock_data_dict: dict[str, pd.DataFrame],
    params: dict,
    benchmark: str = "equal_weight",
) -> go.Figure | None:
    analysis_cache = _get_multi_analysis_cache()
    figure_cache: dict[str, go.Figure | None] = analysis_cache.setdefault("figure_cache", {})
    cache_key = _build_multi_chart_cache_key(
        chart_key,
        stock_data_dict=stock_data_dict,
        factor_stock_data_dict=factor_stock_data_dict,
        params=params,
        benchmark=benchmark,
    )
    if cache_key in figure_cache:
        return figure_cache[cache_key]

    if chart_key == "comparison":
        figure = _style_display_figure(
            create_multi_stock_comparison_chart(
                stock_data_dict,
                title=f"多股票价格对比（共 {len(stock_data_dict)} 只）",
            ),
            height=620,
        )
    elif chart_key == "relative_strength":
        figure = (
            _style_display_figure(
                create_relative_strength_chart(stock_data_dict, benchmark=benchmark),
                height=520,
            )
            if len(stock_data_dict) >= 2
            else None
        )
    elif chart_key == "risk_return":
        figure = _style_display_figure(create_risk_return_scatter(stock_data_dict), height=520) if len(stock_data_dict) >= 2 else None
    elif chart_key == "factor_score":
        figure = (
            _style_display_figure(
                create_factor_score_comparison(
                    factor_stock_data_dict,
                    **_strategy_params(params),
                ),
                height=500,
            )
            if len(stock_data_dict) >= 2
            else None
        )
    elif chart_key == "correlation":
        figure = _style_display_figure(create_correlation_heatmap(stock_data_dict), height=560) if len(stock_data_dict) >= 2 else None
    else:
        figure = None

    figure_cache[cache_key] = figure
    return figure


def _get_multi_strategy_heatmap_figure(
    *,
    workspace: dict[str, Any],
    strategy_signature: str,
    portfolio_result: dict[str, Any],
    period: str,
) -> go.Figure | None:
    heatmap_cache: dict[str, go.Figure | None] = workspace.setdefault("heatmap_cache", {})
    cache_key = f"{strategy_signature}::{period}"
    if cache_key in heatmap_cache:
        return heatmap_cache[cache_key]

    heatmap_returns: dict[str, pd.Series] = {}
    portfolio_returns = portfolio_result.get("portfolio_strat_ret")
    if isinstance(portfolio_returns, pd.Series) and not portfolio_returns.empty:
        heatmap_returns["组合策略"] = portfolio_returns
    for symbol, result in (portfolio_result.get("individual_results") or {}).items():
        strategy_return = result.get("strategy_return")
        if isinstance(strategy_return, pd.Series) and not strategy_return.empty:
            heatmap_returns[f"{symbol} 策略"] = strategy_return

    figure = _style_display_figure(
        create_periodic_returns_heatmap(returns_series=heatmap_returns, period=period),
        height=460,
    )
    heatmap_cache[cache_key] = figure
    return figure


def _render_multi_stock_remove_popover(comparison_stats: list[dict[str, Any]]) -> None:
    state = _get_multi_route_state()
    uploads_by_symbol = {
        str(item.get("symbol") or "").strip().upper(): item
        for item in state.get("uploads", [])
        if str(item.get("symbol") or "").strip()
    }
    total_count = len(state.get("symbols", [])) + len(uploads_by_symbol)

    if not comparison_stats:
        render_status_note("当前没有可移除的股票。", tone="warning")
        return

    if total_count <= 2:
        render_status_note("当前股票池仅剩 2 个标的；先在右侧添加新股票，再执行移除。", tone="warning")

    with st.container(key="multi-stock-remove-list"):
        for item in comparison_stats:
            symbol = item["symbol"]
            source_key = "upload" if symbol in uploads_by_symbol else "market"
            info_col, action_col = st.columns([4.5, 1.0], gap="small")
            info_col.markdown(
                f"<div class='selection-row'><div class='selection-row-title'>{html.escape(symbol)} · {html.escape(item['display_name'])}</div><div class='selection-row-meta'>{html.escape(item['source_label'])} · {html.escape(item['display_label'])}</div></div>",
                unsafe_allow_html=True,
            )
            if action_col.button(
                "移除",
                key=f"multi_stock_remove_{source_key}_{symbol}",
                use_container_width=True,
                disabled=total_count <= 2,
            ):
                _remove_multi_route_item(symbol, source=source_key)


def _render_multi_stock_add_popover(*, market: str) -> None:
    state = _get_multi_route_state()
    existing_symbols = {
        *state.get("symbols", []),
        *[
            str(item.get("symbol") or "").strip().upper()
            for item in state.get("uploads", [])
            if str(item.get("symbol") or "").strip()
        ],
    }

    query = st.text_input(
        "搜索股票名称或代码",
        value=st.session_state.get("multi_stock_edit_query", ""),
        placeholder="例如：AAPL / NVDA / 贵州茅台 / 600519",
        key="multi_stock_edit_query",
    ).strip()

    if not query:
        render_status_note("输入名称或代码后，可把新标的直接加入当前股票池。", tone="info")
        return

    try:
        matched = search_stock_candidates(query, market=_normalize_market_key(market), limit=8)
    except Exception as exc:
        matched = pd.DataFrame(columns=["symbol", "name", "label"])
        render_status_note(f"候选搜索失败：{exc}", tone="warning")

    if matched.empty:
        fallback_symbol = query.zfill(6)[-6:] if _normalize_market_key(market) == "A" and query.isdigit() else query.upper()
        if fallback_symbol in existing_symbols:
            render_status_note("该股票已经在当前股票池里。", tone="warning")
        else:
            render_status_note("没有找到索引匹配，将按当前输入直接加入。", tone="warning")
            if st.button("按当前输入加入", key="multi_stock_add_direct", use_container_width=True):
                _add_multi_route_symbol(fallback_symbol, market=market)
        return

    with st.container(key="multi-stock-add-list"):
        for row in matched.itertuples(index=False):
            symbol = str(row.symbol).strip().upper()
            info_col, action_col = st.columns([4.5, 1.0], gap="small")
            info_col.markdown(
                f"<div class='recommend-row'><div class='recommend-row-title'>{html.escape(symbol)}</div><div class='recommend-row-meta'>{html.escape(str(row.label))}</div></div>",
                unsafe_allow_html=True,
            )
            if action_col.button(
                "加入",
                key=f"multi_stock_add_{symbol}",
                use_container_width=True,
                disabled=symbol in existing_symbols,
            ):
                _add_multi_route_symbol(symbol, market=market)


def _render_multi_stock_section_nav(comparison_stats: list[dict[str, Any]], *, market: str) -> str:
    nav_col, action_col = st.columns([1.4, 1.1], gap="small")
    section_default = _ensure_segmented_value(MULTI_ANALYSIS_SECTION_KEY, ["basics", "strategy"], "basics")
    with nav_col:
        st.caption("分析区切换")
        section_view = st.segmented_control(
            "分析区切换",
            options=["basics", "strategy"],
            format_func=lambda value: "基础信息" if value == "basics" else "策略",
            default=section_default,
            key=MULTI_ANALYSIS_SECTION_KEY,
            width="stretch",
            label_visibility="collapsed",
        ) or section_default
    with action_col:
        st.caption("股票池操作")
        remove_col, add_col = st.columns(2, gap="small")
        with remove_col:
            with st.container(key="multi-stock-remove-popover"):
                with st.popover("移除股票", use_container_width=True):
                    _render_multi_stock_remove_popover(comparison_stats)
        with add_col:
            with st.container(key="multi-stock-add-popover"):
                with st.popover("添加股票", use_container_width=True):
                    _render_multi_stock_add_popover(market=market)
    return section_view


def _render_multi_stock_basic_section(
    *,
    params: dict,
    comparison_stats: list[dict[str, Any]],
    chart_configs: dict[str, dict[str, Any]],
    stock_data_dict: dict[str, pd.DataFrame],
    factor_stock_data_dict: dict[str, pd.DataFrame],
) -> None:
    avg_days = int(np.mean([item["data_days"] for item in comparison_stats])) if comparison_stats else 0
    best_entry = next((item for item in comparison_stats if item.get("total_return") is not None), None)
    global_start = min((item["date_min"] for item in comparison_stats if item.get("date_min") is not None), default=None)
    global_end = max((item["date_max"] for item in comparison_stats if item.get("date_max") is not None), default=None)

    metrics_markup = "".join(
        f"""
<div class="analysis-kv-item">
  <span class="analysis-kv-label">{html.escape(label)}</span>
  <span class="analysis-kv-value">{html.escape(value)}</span>
  <span class="analysis-kv-meta">{html.escape(meta)}</span>
</div>
        """
        for label, value, meta in [
            ("对比股票数量", str(len(comparison_stats)), "当前成功加载的有效标的"),
            ("平均数据天数", f"{avg_days}", "按当前日期范围统计"),
            (
                "最佳表现股票",
                best_entry["symbol"] if best_entry is not None else "N/A",
                _format_signed_pct((best_entry["total_return"] or 0.0) * 100.0 if best_entry is not None else None),
            ),
            ("覆盖区间", f"{_format_date_text(global_start)} → {_format_date_text(global_end)}", "多股基础信息与右侧图表共用同一筛选结果"),
        ]
    )

    with st.container(key="multi-stock-basic-section"):
        render_html(
            """
<div id="multi-stock-basics"></div>
<div class="analysis-section-header">
  <div class="surface-kicker">Basic Information</div>
  <h2 class="analysis-section-title">多股基础信息区</h2>
  <p class="analysis-section-copy">顶部先给出股票池摘要和明细表，右侧主图在价格对比、相对强弱、风险收益、最新因子评分和相关性之间切换，不再顺序堆叠成长页面。</p>
</div>
            """
        )
        summary_col, chart_col, switch_col = st.columns([0.8, 1.46, 0.42], gap="large")

        with switch_col:
            st.caption("图表切换")
            selected_chart = st.radio(
                "查看图表",
                options=list(chart_configs.keys()),
                format_func=lambda key: chart_configs[key]["label"],
                key="multi_stock_basic_chart_view",
                label_visibility="collapsed",
            )
            render_status_note("周期收益率热图已移动到策略区，基础信息区只保留图四对应的多股对比图表。", tone="info")

        with summary_col:
            render_html(f"<div class='analysis-kv-grid'>{metrics_markup}</div>")
            render_status_note("字段缺失会回退为 N/A，不会阻断页面其余部分。", tone="info")

            detail_rows = [
                {
                    "股票代码": item["symbol"],
                    "名称": item["display_name"],
                    "来源": item["source_label"],
                    "起始价格": _format_decimal(item["start_price"]),
                    "最新价格": _format_decimal(item["latest_price"]),
                    "总收益率": _format_signed_pct((item["total_return"] or 0.0) * 100.0 if item["total_return"] is not None else None),
                    "年化收益率": _format_signed_pct((item["annualized_return"] or 0.0) * 100.0 if item["annualized_return"] is not None else None),
                    "最高价": _format_decimal(item["high_price"]),
                    "最低价": _format_decimal(item["low_price"]),
                    "数据天数": item["data_days"],
                }
                for item in comparison_stats
            ]
            with st.expander("详细对比表", expanded=False):
                if detail_rows:
                    st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)
                else:
                    render_status_note("暂无可展示结果。", tone="warning")

        chart_meta = chart_configs[selected_chart]
        with chart_col:
            with st.container(key="multi-stock-chart-frame"):
                figure = None
                if selected_chart == "relative_strength" and len(stock_data_dict) >= 2:
                    benchmark_options = ["equal_weight"] + list(stock_data_dict.keys())
                    benchmark_choice = st.selectbox(
                        "相对强弱基准",
                        options=benchmark_options,
                        format_func=lambda value: "等权平均" if value == "equal_weight" else value,
                        key="multi_stock_rs_benchmark",
                    )
                    figure = _get_multi_chart_figure(
                        "relative_strength",
                        stock_data_dict=stock_data_dict,
                        factor_stock_data_dict=factor_stock_data_dict,
                        params=params,
                        benchmark=benchmark_choice,
                    )
                else:
                    figure = _get_multi_chart_figure(
                        selected_chart,
                        stock_data_dict=stock_data_dict,
                        factor_stock_data_dict=factor_stock_data_dict,
                        params=params,
                    )
                render_html(
                    f"""
<div class="analysis-chart-toolbar">
  <div>
    <div class="analysis-chart-title">{html.escape(chart_meta['title'])}</div>
    <div class="analysis-chart-copy">{html.escape(chart_meta['copy'])}</div>
  </div>
</div>
                    """
                )
                if figure is None:
                    render_status_note(chart_meta.get("empty_text", "暂无可展示结果。"), tone="warning")
                else:
                    st.plotly_chart(figure, width="stretch")
                    render_status_note(chart_meta["note"], tone="info")


def _render_multi_stock_strategy_section(
    *,
    params: dict,
    stock_data_dict: dict[str, pd.DataFrame],
) -> tuple[dict[str, Any] | None, Any]:
    workspace = _get_multi_strategy_workspace()
    periodic_heatmap_fig = None

    with st.container(key="multi-stock-strategy-section"):
        render_html(
            """
<div id="multi-stock-strategy"></div>
<div class="analysis-section-header">
  <div class="surface-kicker">Strategy</div>
  <h2 class="analysis-section-title">多股策略区</h2>
  <p class="analysis-section-copy">左侧固定为模型控制台与组合搜索，右侧固定为结果图区、组合 KPI 摘要和个股表现表，对齐第七周第 8 项的“左控台 / 右结果区”结构。</p>
</div>
            """
        )

        control_col, result_col = st.columns([0.76, 1.24], gap="large")

        with control_col:
            with st.container(key="multi-stock-strategy-panel-control"):
                _render_surface_header(
                    "Control Panel",
                    "多股组合控制台",
                    "组合权重、生成动作和参数搜索收敛到同一侧；策略参数仍统一复用左侧边栏，不再派生第二套配置来源。",
                )
                render_status_note("至少需要 2 个有效标的；如股票池、权重或边栏参数变化，结果区会要求重新生成。", tone="info")

                st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
                st.markdown("**组合权重配置**")
                weight_cols = st.columns(2, gap="small")
                portfolio_weights: dict[str, float] = {}
                for index, symbol in enumerate(stock_data_dict.keys()):
                    with weight_cols[index % 2]:
                        portfolio_weights[symbol] = st.number_input(
                            f"{symbol} 权重",
                            min_value=0.0,
                            max_value=10.0,
                            value=1.0,
                            step=0.1,
                            key=f"multi_stock_weight_{symbol}",
                        )

                strategy_signature = _build_multi_strategy_signature(stock_data_dict, params, portfolio_weights)
                if workspace.get("portfolio_result") is not None and workspace.get("signature") != strategy_signature:
                    render_status_note("检测到股票池、权重或边栏参数变化，请重新生成组合策略。", tone="warning")

                if st.button(
                    "生成组合策略",
                    type="primary",
                    use_container_width=True,
                    key="multi_stock_generate_strategy",
                ):
                    if sum(portfolio_weights.values()) <= 0:
                        st.error("组合权重之和必须大于 0。")
                    else:
                        with st.spinner("正在运行多股组合策略模拟..."):
                            portfolio_params = _strategy_params(params)
                            portfolio_params["weights"] = portfolio_weights
                            generated_result = run_portfolio_simulation(stock_data_dict, **portfolio_params)
                        workspace["signature"] = strategy_signature
                        workspace["portfolio_result"] = generated_result
                        if generated_result is not None:
                            st.success("组合策略已生成，右侧结果区已更新。")
                        else:
                            st.error("当前数据不足以生成组合策略，请检查股票池长度和时间范围。")

                st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
                st.markdown("**组合参数搜索**")
                portfolio_n_trials = st.slider(
                    "优化试验次数",
                    10,
                    100,
                    30,
                    step=10,
                    key="portfolio_n_trials",
                    help="试验次数越多越精确，但耗时更长。建议先用 30 次验证路径。",
                )
                if st.button("开始组合搜索", use_container_width=True, key="btn_optimize_portfolio"):
                    with st.spinner(f"贝叶斯优化中（{portfolio_n_trials} 次试验）..."):
                        opt_fixed = _strategy_params(params)
                        opt_fixed.pop("weights", None)
                        opt_fixed.pop("stop_loss_mult", None)
                        opt_fixed.pop("take_profit_mult", None)
                        opt_fixed.pop("entry_threshold", None)
                        opt_fixed.pop("exit_threshold", None)
                        opt_fixed.pop("adx_threshold", None)
                        opt_fixed.pop("weight_bb", None)
                        opt_fixed.pop("weight_obv", None)
                        opt_fixed.pop("weight_volume", None)
                        opt_fixed.pop("weight_price", None)
                        opt_fixed.pop("weight_drawdown", None)
                        optimization_result = bayesian_optimize_portfolio(
                            stock_data_dict,
                            n_trials=portfolio_n_trials,
                            **opt_fixed,
                        )
                    workspace["optimization_signature"] = strategy_signature
                    workspace["optimization_result"] = optimization_result

                optimization_result = (
                    workspace.get("optimization_result")
                    if workspace.get("optimization_signature") == strategy_signature
                    else None
                )
                if optimization_result and optimization_result.get("score", -np.inf) > -np.inf:
                    opt_cols = st.columns(3, gap="small")
                    for column, (label, value) in zip(
                        opt_cols,
                        [
                            ("优化后夏普", f"{optimization_result['sharpe']:.2f}"),
                            ("优化后收益", f"{optimization_result['return']:.2%}"),
                            ("优化后回撤", f"{optimization_result['max_drawdown']:.2%}"),
                        ],
                    ):
                        column.metric(label, value)
                    with st.expander("查看最优参数", expanded=False):
                        opt_params_display = {
                            "入场阈值": f"{optimization_result['entry_threshold']:.2f}",
                            "出场阈值": f"{optimization_result['exit_threshold']:.2f}",
                            "ADX阈值": f"{optimization_result['adx_threshold']:.1f}",
                            "止损倍数": f"{optimization_result['stop_loss_mult']:.2f}",
                            "止盈倍数": f"{optimization_result['take_profit_mult']:.2f}",
                            "布林带权重": f"{optimization_result['weight_bb']:.2f}",
                            "OBV权重": f"{optimization_result['weight_obv']:.2f}",
                            "成交量权重": f"{optimization_result['weight_volume']:.2f}",
                            "价格位置权重": f"{optimization_result['weight_price']:.2f}",
                            "回撤惩罚权重": f"{optimization_result['weight_drawdown']:.2f}",
                        }
                        st.dataframe(
                            pd.DataFrame(list(opt_params_display.items()), columns=["参数", "最优值"]),
                            width="stretch",
                            hide_index=True,
                        )

        portfolio_result = workspace.get("portfolio_result") if workspace.get("signature") == strategy_signature else None

        with result_col:
            with st.container(key="multi-stock-strategy-panel-result"):
                _render_surface_header(
                    "Result Surface",
                    "组合结果区",
                    "结果主图在投资组合模拟和周期收益率热图之间切换；投资组合模拟现复用单股结果区的共享净值/回撤组件，组合 KPI 摘要和个股表现表保持固定。",
                )
                if portfolio_result is None:
                    render_status_note("模型还没准备好。先在左侧确认权重，再点击“生成组合策略”。", tone="info")
                else:
                    result_view = st.segmented_control(
                        "策略结果视图",
                        options=["投资组合模拟", "周期收益率热图"],
                        default="投资组合模拟",
                        key="multi_stock_strategy_view",
                        width="stretch",
                    )

                    if result_view == "周期收益率热图":
                        heatmap_period = st.selectbox(
                            "热图周期",
                            options=["M", "Q", "YE"],
                            format_func=lambda value: {"M": "月度", "Q": "季度", "YE": "年度"}.get(value, value),
                            index=0,
                            key="multi_stock_strategy_heatmap_period",
                        )
                        periodic_heatmap_fig = _get_multi_strategy_heatmap_figure(
                            workspace=workspace,
                            strategy_signature=strategy_signature,
                            portfolio_result=portfolio_result,
                            period=heatmap_period,
                        )
                        if periodic_heatmap_fig is not None:
                            st.plotly_chart(periodic_heatmap_fig, width="stretch")
                        else:
                            render_status_note("当前结果不足以生成策略周期热图。", tone="warning")
                    else:
                        portfolio_fig = _style_display_figure(portfolio_result.get("fig"), height=520)
                        if portfolio_fig is not None:
                            st.plotly_chart(portfolio_fig, width="stretch")
                            render_status_note("当前主图与单股结果区共用同一套“净值上 / 回撤下”的结果图组件。", tone="info")
                        else:
                            render_status_note("当前结果缺少可展示的组合净值图。", tone="warning")

                    kpi_cols = st.columns(3, gap="small")
                    kpi_items = [
                        ("组合总收益", f"{portfolio_result['port_total_return']:.2%}", "策略组合"),
                        ("组合夏普", f"{portfolio_result['port_sharpe']:.2f}", "策略组合"),
                        ("组合最大回撤", f"{portfolio_result['port_max_dd']:.2%}", "策略组合"),
                        ("买入持有收益", f"{portfolio_result['bh_total_return']:.2%}", "等权基准"),
                        ("买入持有夏普", f"{portfolio_result['bh_sharpe']:.2f}", "等权基准"),
                        ("买入持有回撤", f"{portfolio_result['bh_max_dd']:.2%}", "等权基准"),
                    ]
                    for column, (label, value, _help_text) in zip(kpi_cols * 2, kpi_items):
                        column.metric(label, value)

                    with st.expander("各股票独立策略表现", expanded=False):
                        indiv_stats = []
                        for sym, res in portfolio_result["individual_results"].items():
                            indiv_stats.append(
                                {
                                    "股票": sym,
                                    "权重": f"{portfolio_result['weights'].get(sym, 0):.1%}",
                                    "策略收益": f"{res['total_return']:.2%}",
                                    "夏普比率": f"{res['sharpe']:.2f}",
                                    "最大回撤": f"{res['max_dd']:.2%}",
                                }
                            )
                        if indiv_stats:
                            st.dataframe(pd.DataFrame(indiv_stats), width="stretch", hide_index=True)
                        else:
                            render_status_note("当前没有可展示的个股独立策略表现。", tone="warning")

                    render_status_note("图五要求的“组合 KPI 摘要 + 个股表现表”已固定在同一结果区，切换主图不会打散下方信息。", tone="positive")

    return portfolio_result, periodic_heatmap_fig


def render_multi_stock_page(
    params: dict,
    is_datetime: bool,
    start_ts,
    end_ts,
    prefetched_stock_data: dict[str, pd.DataFrame] | None = None,
) -> None:
    """
    渲染多股票对比分析页面。

    Parameters
    ----------
    params : dict
        ``render_sidebar()`` 返回的完整参数字典。
    is_datetime : bool
        df_raw 的 date 列是否为 datetime 类型。
    start_ts, end_ts
        时间筛选的起止 Timestamp。
    """
    _ = is_datetime
    compare_stocks = params["compare_stocks"]
    market = params.get("market", "US")
    adjust = params["adjust"]
    upload_symbols = set((prefetched_stock_data or {}).keys())
    route_state = _get_multi_route_state()
    analysis_cache = _get_multi_analysis_cache()
    data_signature = _build_multi_analysis_data_signature(
        market=market,
        adjust=adjust,
        compare_stocks=list(compare_stocks),
        uploads=list(route_state.get("uploads", [])),
        start_ts=start_ts,
        end_ts=end_ts,
    )

    if analysis_cache.get("data_signature") != data_signature:
        with st.spinner("加载对比股票数据..."):
            stock_data_dict: dict[str, pd.DataFrame] = {}
            factor_stock_data_dict: dict[str, pd.DataFrame] = {}
            for stock_symbol, prefetched_df in (prefetched_stock_data or {}).items():
                stock_df = _prepare_multi_stock_dataframe(prefetched_df)
                if stock_df.empty:
                    continue

                analysis_df = stock_df
                if "date" in analysis_df.columns and end_ts is not None:
                    analysis_df = analysis_df[analysis_df["date"] <= end_ts]

                if analysis_df.empty:
                    continue

                display_df = analysis_df
                if "date" in display_df.columns and start_ts is not None:
                    display_df = display_df[display_df["date"] >= start_ts]

                display_df = display_df.reset_index(drop=True)
                analysis_df = analysis_df.reset_index(drop=True)
                if display_df.empty:
                    continue

                stock_data_dict[stock_symbol] = display_df
                factor_stock_data_dict[stock_symbol] = analysis_df

            for stock_symbol in compare_stocks:
                if stock_symbol in stock_data_dict:
                    continue
                stock_df = load_or_fetch_stock(stock_symbol, adjust, market=market)
                stock_df = _prepare_multi_stock_dataframe(stock_df)
                if stock_df.empty:
                    continue

                analysis_df = stock_df
                if "date" in analysis_df.columns and end_ts is not None:
                    analysis_df = analysis_df[analysis_df["date"] <= end_ts]

                if analysis_df.empty:
                    continue

                display_df = analysis_df
                if "date" in display_df.columns and start_ts is not None:
                    display_df = display_df[display_df["date"] >= start_ts]

                display_df = display_df.reset_index(drop=True)
                analysis_df = analysis_df.reset_index(drop=True)

                if display_df.empty:
                    continue

                stock_data_dict[stock_symbol] = display_df
                factor_stock_data_dict[stock_symbol] = analysis_df

        ordered_symbols = list(stock_data_dict.keys())
        symbol_meta = _resolve_symbol_meta(ordered_symbols, market=market, upload_symbols=upload_symbols)
        comparison_stats = _build_comparison_stats(stock_data_dict, symbol_meta=symbol_meta)
        analysis_cache.update(
            {
                "data_signature": data_signature,
                "stock_data_dict": stock_data_dict,
                "factor_stock_data_dict": factor_stock_data_dict,
                "symbol_meta": symbol_meta,
                "comparison_stats": comparison_stats,
                "figure_cache": {},
            }
        )

    stock_data_dict = analysis_cache.get("stock_data_dict", {})
    factor_stock_data_dict = analysis_cache.get("factor_stock_data_dict", {})
    comparison_stats = analysis_cache.get("comparison_stats", [])

    if len(stock_data_dict) == 0:
        st.warning("没有加载到有效的股票数据。")
        return

    portfolio_result = None

    chart_configs = {
        "comparison": {
            "label": "价格对比",
            "title": "多股票价格对比分析图",
            "copy": "把所有股票起点统一到同一基准，先判断谁在当前观察区间内跑得更快。",
            "note": "所有曲线都以同一基准起点归一化，适合先看整体强弱排序。",
            "empty_text": "当前没有足够数据生成价格对比图。",
        },
        "relative_strength": {
            "label": "相对强弱",
            "title": "相对强弱对比图",
            "copy": "默认相对基准使用等权平均，判断每只股票是持续跑赢还是持续跑输股票池。",
            "note": "RS 曲线上升代表相对强势，下降代表相对弱势。",
            "empty_text": "数据不足以计算相对强弱（至少需要 2 只有效股票）。",
        },
        "risk_return": {
            "label": "风险收益",
            "title": "风险收益散点图",
            "copy": "在一个平面里同时看年化收益、波动率和夏普，适合快速识别风险收益结构。",
            "note": "越靠左上通常代表越高收益、越低风险；颜色映射到夏普水平。",
            "empty_text": "数据不足以计算风险收益图。",
        },
        "factor_score": {
            "label": "因子评分",
            "title": "最新因子评分对比图",
            "copy": "对每只股票独立计算最新一日综合因子评分，直接回答当前更值得关注谁。",
            "note": "柱子越高，说明当前综合因子评分越强；颜色对应建议仓位。",
            "empty_text": "当前历史窗口不足，无法稳定计算最新因子评分。",
        },
        "correlation": {
            "label": "相关性",
            "title": "股票相关性热图",
            "copy": "用共同交易日收益率构造相关性矩阵，帮助判断股票池是否过于同质化。",
            "note": "接近 1 代表正相关，接近 -1 代表负相关，接近 0 代表相关性弱。",
            "empty_text": "数据不足以计算相关性热图（需要至少 5 个共同交易日）。",
        },
    }

    _render_multi_stock_header(
        market=market,
        comparison_stats=comparison_stats,
        upload_symbols=upload_symbols,
        selected_range=params.get("selected_range"),
    )
    analysis_section = _render_multi_stock_section_nav(comparison_stats, market=market)
    if analysis_section == "basics":
        _render_multi_stock_basic_section(
            params=params,
            comparison_stats=comparison_stats,
            chart_configs=chart_configs,
            stock_data_dict=stock_data_dict,
            factor_stock_data_dict=factor_stock_data_dict,
        )
        return

    portfolio_result, _ = _render_multi_stock_strategy_section(
        params=params,
        stock_data_dict=stock_data_dict,
    )

    _render_multi_stock_export(
        compare_stocks,
        stock_data_dict,
        factor_stock_data_dict,
        comparison_stats,
        params,
        portfolio_result,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _strategy_params(params: dict) -> dict:
    """从完整 params 中提取策略相关参数子集（去除 UI 状态键）。"""
    _ui_keys = {
        "market",
        "compare_stocks",
        "symbol",
        "adjust",
        "selected_range",
        "uploaded_file",
        "strategy_preset",
    }
    return {k: v for k, v in params.items() if k not in _ui_keys}


def _render_multi_stock_export(
    compare_stocks,
    stock_data_dict,
    factor_stock_data_dict,
    comparison_stats,
    params,
    portfolio_result,
):
    """在页面底部渲染 HTML 导出区域。"""
    st.markdown("---")
    st.markdown("### 导出分析报告")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        export_title = st.text_input(
            "报告标题",
            value=f"多股票对比分析 - {', '.join(compare_stocks)}",
            key="export_title",
        )
    with col2:
        include_date = st.checkbox("包含生成日期", value=True, key="include_date")

    if not st.button("生成并下载 HTML 报告", type="primary", width="stretch"):
        return

    with st.spinner("正在生成 HTML 报告..."):
        comparison_fig = _get_multi_chart_figure(
            "comparison",
            stock_data_dict=stock_data_dict,
            factor_stock_data_dict=factor_stock_data_dict,
            params=params,
        )
        rs_fig = _get_multi_chart_figure(
            "relative_strength",
            stock_data_dict=stock_data_dict,
            factor_stock_data_dict=factor_stock_data_dict,
            params=params,
            benchmark="equal_weight",
        )
        risk_return_fig = _get_multi_chart_figure(
            "risk_return",
            stock_data_dict=stock_data_dict,
            factor_stock_data_dict=factor_stock_data_dict,
            params=params,
        )
        factor_score_fig = _get_multi_chart_figure(
            "factor_score",
            stock_data_dict=stock_data_dict,
            factor_stock_data_dict=factor_stock_data_dict,
            params=params,
        )
        corr_fig = _get_multi_chart_figure(
            "correlation",
            stock_data_dict=stock_data_dict,
            factor_stock_data_dict=factor_stock_data_dict,
            params=params,
        )
        periodic_heatmap_fig = None
        workspace = _get_multi_strategy_workspace()
        strategy_signature = workspace.get("signature")
        if portfolio_result is not None and strategy_signature:
            periodic_heatmap_fig = _get_multi_strategy_heatmap_figure(
                workspace=workspace,
                strategy_signature=strategy_signature,
                portfolio_result=portfolio_result,
                period="M",
            )
        generated_at = datetime.now()
        full_html = build_multi_stock_export_html(
            title=export_title,
            compare_stocks=compare_stocks,
            stock_data_dict=stock_data_dict,
            comparison_stats=comparison_stats,
            comparison_fig=comparison_fig,
            rs_fig=rs_fig,
            risk_return_fig=risk_return_fig,
            factor_score_fig=factor_score_fig,
            corr_fig=corr_fig,
            periodic_heatmap_fig=periodic_heatmap_fig,
            portfolio_result=portfolio_result,
            include_date=include_date,
            language=get_ui_language(),
            theme=get_ui_theme(),
            generated_at=generated_at,
        )

        st.download_button(
            label="下载 HTML 报告",
            data=full_html,
            file_name=f"stock_comparison_report_{generated_at.strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
        st.success("HTML 报告已生成。")
