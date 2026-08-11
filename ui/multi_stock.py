"""
多股票对比分析页面
==================
选中多只股票时展示的完整对比分析界面。
"""

from __future__ import annotations

import html
from collections import OrderedDict
from time import perf_counter
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from ui.i18n import tr

from core.data import get_stock_label_map, search_stock_candidates
from core.market_context import get_market_indices
from core.perf import emit_performance_event, performance_span
from core.portfolio import build_portfolio_figure, bayesian_optimize_portfolio, run_portfolio_simulation
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
MULTI_APPLIED_ADJUSTMENTS_KEY = "multi_stock_applied_adjustments"
MULTI_HEADER_DETAILS_KEY = "multi_stock_header_details_expanded"


def _prepare_multi_stock_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """data.multiStockCleaning"""
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
    market_label = tr("market.cn_stock") if market_key == "A" else tr("market.us_stocks")
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
                "source_label": tr("action.uploadData"),
            }
            continue

        full_label = label_map.get(symbol, symbol)
        display_name = full_label
        if full_label.startswith(f"{symbol} "):
            display_name = full_label[len(symbol) + 1 :].strip() or symbol

        symbol_meta[symbol] = {
            "display_name": display_name,
            "display_label": full_label,
            "source_label": tr("data.marketData"),
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
        meta = symbol_meta.get(symbol, {"display_name": symbol, "display_label": symbol, "source_label": tr("data.marketData")})

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
    market_label = tr("market.cn_stock") if market_key == "A" else tr("market.us_stocks")
    loaded_count = len(comparison_stats)
    uploaded_count = len([item for item in comparison_stats if item["symbol"] in upload_symbols])
    avg_days = int(np.mean([item["data_days"] for item in comparison_stats])) if comparison_stats else 0
    best_entry = next((item for item in comparison_stats if item.get("total_return") is not None), None)
    global_start = min((item["date_min"] for item in comparison_stats if item.get("date_min") is not None), default=None)
    global_end = max((item["date_max"] for item in comparison_stats if item.get("date_max") is not None), default=None)

    display_names = [item["display_name"] for item in comparison_stats]
    if len(display_names) <= 4:
        title_suffix = " · ".join(display_names) if display_names else tr("instruments.noneAvailable")
    else:
        title_suffix = " · ".join(display_names[:4]) + f" +{len(display_names) - 4}"

    quick_items = [
        {
            "label": tr("portfolio.involved_symbols"),
            "value": str(loaded_count),
            "meta": f"{uploaded_count} 个上传源，{loaded_count - uploaded_count} 个市场标的",
        },
        {
            "label": tr("data.averageDays"),
            "value": f"{avg_days}",
            "meta": tr("data.filteredSamples"),
        },
        {
            "label": tr("performance.best"),
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
  <span class="analysis-market-label">{html.escape(str(item.get('label') or tr("market.index")))}</span>
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

    details_expanded = bool(st.session_state.get(MULTI_HEADER_DETAILS_KEY, False))
    details_label = tr("analysis.hide_details") if details_expanded else tr("analysis.show_details")
    details_icon = ":material/expand_less:" if details_expanded else ":material/expand_more:"

    with st.container(key="multi-stock-analysis-hero"):
        with st.container(key="multi-stock-hero-compact"):
            identity_col, range_col, toggle_col = st.columns([1.1, 0.9, 0.28], gap="medium", vertical_alignment="center")
            with identity_col:
                render_html(
                    f"""
<div class="analysis-compact-identity">
  <h1 class="analysis-title">多股主分析页</h1>
  <div class="analysis-subtitle">{html.escape(title_suffix)}</div>
</div>
                    """
                )
            with range_col:
                render_analysis_date_range_control(
                    current_range=selected_range,
                    key_prefix="multi_stock",
                    label=tr("time.range"),
                    in_hero=True,
                )
            with toggle_col:
                with st.container(key="multi-stock-hero-toggle"):
                    if st.button(
                        details_label,
                        key="multi_stock_header_details_toggle",
                        icon=details_icon,
                    ):
                        st.session_state[MULTI_HEADER_DETAILS_KEY] = not details_expanded
                        st.rerun()

        if details_expanded:
            render_html(
                f"""
<div class="analysis-hero-details">
<div class="analysis-hero-topline">
  <span class="analysis-pill accent">{tr("analysis.multiStock")}</span>
  <span class="analysis-pill">{html.escape(market_label)}</span>
  <span class="analysis-pill">{loaded_count} 个对比标的</span>
  <span class="analysis-pill">{uploaded_count} 个上传数据源</span>
</div>
<div class="analysis-chart-meta">
  <span class="analysis-chart-chip">数据区间 {_format_date_text(global_start)} 到 {_format_date_text(global_end)}</span>
  <span class="analysis-chart-chip">当前市场 {html.escape(market_label)}</span>
</div>
<div class="analysis-quick-grid">{quick_markup}</div>
<div class="analysis-market-strip">{''.join(index_cards)}</div>
</div>
                """
            )


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
            "heatmap_cache": OrderedDict(),
        },
    )
    workspace.setdefault("signature", None)
    workspace.setdefault("portfolio_result", None)
    workspace.setdefault("optimization_signature", None)
    workspace.setdefault("optimization_result", None)
    heatmap_cache = workspace.setdefault("heatmap_cache", OrderedDict())
    if not isinstance(heatmap_cache, OrderedDict):
        workspace["heatmap_cache"] = OrderedDict(heatmap_cache)
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
            "figure_cache": OrderedDict(),
        },
    )
    cache.setdefault("data_signature", None)
    cache.setdefault("stock_data_dict", {})
    cache.setdefault("factor_stock_data_dict", {})
    cache.setdefault("symbol_meta", {})
    cache.setdefault("comparison_stats", [])
    figure_cache = cache.setdefault("figure_cache", OrderedDict())
    if not isinstance(figure_cache, OrderedDict):
        cache["figure_cache"] = OrderedDict(figure_cache)
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
    figure_cache: OrderedDict[str, go.Figure | None] = analysis_cache.setdefault("figure_cache", OrderedDict())
    cache_key = _build_multi_chart_cache_key(
        chart_key,
        stock_data_dict=stock_data_dict,
        factor_stock_data_dict=factor_stock_data_dict,
        params=params,
        benchmark=benchmark,
    )
    if cache_key in figure_cache:
        figure_cache.move_to_end(cache_key)
        emit_performance_event("multi", "figure_build", 0.0, cache="hit", chart_key=chart_key)
        return figure_cache[cache_key]

    with performance_span("multi", "figure_build", cache="miss", chart_key=chart_key):
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
    while len(figure_cache) > 8:
        figure_cache.popitem(last=False)
    return figure


def _get_multi_strategy_heatmap_figure(
    *,
    workspace: dict[str, Any],
    strategy_signature: str,
    portfolio_result: dict[str, Any],
    period: str,
) -> go.Figure | None:
    heatmap_cache: OrderedDict[str, go.Figure | None] = workspace.setdefault("heatmap_cache", OrderedDict())
    cache_key = f"{strategy_signature}::{period}"
    if cache_key in heatmap_cache:
        heatmap_cache.move_to_end(cache_key)
        return heatmap_cache[cache_key]

    heatmap_returns: dict[str, pd.Series] = {}
    portfolio_returns = portfolio_result.get("portfolio_strat_ret")
    if isinstance(portfolio_returns, pd.Series) and not portfolio_returns.empty:
        heatmap_returns[tr("strategy.portfolioStrategy")] = portfolio_returns
    for symbol, result in (portfolio_result.get("individual_results") or {}).items():
        strategy_return = result.get("strategy_return")
        if isinstance(strategy_return, pd.Series) and not strategy_return.empty:
            heatmap_returns[f"{symbol} 策略"] = strategy_return

    figure = _style_display_figure(
        create_periodic_returns_heatmap(returns_series=heatmap_returns, period=period),
        height=460,
    )
    heatmap_cache[cache_key] = figure
    while len(heatmap_cache) > 4:
        heatmap_cache.popitem(last=False)
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
        render_status_note(tr("message.no_stocks_to_remove"), tone="warning")
        return

    if total_count <= 2:
        render_status_note(tr("stockPool.warning.removeAfterAdd"), tone="warning")

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
                tr("common.remove"),
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
        tr("placeholder.search_stock"),
        value=st.session_state.get("multi_stock_edit_query", ""),
        placeholder=tr("input.stock.example"),
        key="multi_stock_edit_query",
    ).strip()

    if not query:
        render_status_note(tr("stock.pool.addInstruction"), tone="info")
        return

    try:
        matched = search_stock_candidates(query, market=_normalize_market_key(market), limit=8)
    except Exception as exc:
        matched = pd.DataFrame(columns=["symbol", "name", "label"])
        render_status_note(f"候选搜索失败：{exc}", tone="warning")

    if matched.empty:
        fallback_symbol = query.zfill(6)[-6:] if _normalize_market_key(market) == "A" and query.isdigit() else query.upper()
        if fallback_symbol in existing_symbols:
            render_status_note(tr("stockPool.duplicateWarning"), tone="warning")
        else:
            render_status_note(tr("index.mismatch.addDirectly"), tone="warning")
            if st.button(tr("action.add_with_current_input"), key="multi_stock_add_direct", use_container_width=True):
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
                tr("action.add"),
                key=f"multi_stock_add_{symbol}",
                use_container_width=True,
                disabled=symbol in existing_symbols,
            ):
                _add_multi_route_symbol(symbol, market=market)


def _render_multi_stock_section_nav(comparison_stats: list[dict[str, Any]], *, market: str) -> str:
    section_default = _ensure_segmented_value(MULTI_ANALYSIS_SECTION_KEY, ["basics", "strategy"], "basics")
    with st.container(key="multi-stock-section-nav"):
        nav_col, edit_col = st.columns([1.0, 0.28], gap="small", vertical_alignment="center")
        with nav_col:
            section_view = st.segmented_control(
                tr("analysis.areaSwitch"),
                options=["basics", "strategy"],
                format_func=lambda value: tr("panel.basicInfo") if value == "basics" else tr("common.strategy"),
                default=section_default,
                key=MULTI_ANALYSIS_SECTION_KEY,
                label_visibility="collapsed",
            ) or section_default
        with edit_col:
            with st.container(key="multi-stock-edit-popover"):
                with st.popover(tr("stock.pool"), use_container_width=False):
                    with st.expander(tr("portfolio.removeStock"), expanded=False):
                        _render_multi_stock_remove_popover(comparison_stats)
                    with st.expander(tr("action.addStock"), expanded=False):
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
            (tr("comparison.stockCount"), str(len(comparison_stats)), tr("status.loadedValidSecurities")),
            (tr("data.averageDays"), f"{avg_days}", tr("statistics.dateRange.current")),
            (
                tr("performance.topPerformer"),
                best_entry["symbol"] if best_entry is not None else "N/A",
                _format_signed_pct((best_entry["total_return"] or 0.0) * 100.0 if best_entry is not None else None),
            ),
            (tr("data.coverageRange"), f"{_format_date_text(global_start)} → {_format_date_text(global_end)}", tr("multiStock.sharedFilter")),
        ]
    )
    stock_rows_markup = "".join(
        f"""
<div class="analysis-stock-row">
  <div class="analysis-stock-identity">
    <span class="analysis-stock-symbol">{html.escape(item['symbol'])}</span>
    <span class="analysis-stock-name">{html.escape(item['display_name'])}</span>
    <span class="analysis-stock-meta">{html.escape(item['source_label'])} · {html.escape(_format_date_text(item['date_min']))} — {html.escape(_format_date_text(item['date_max']))} · {item['data_days']} {html.escape(tr("data.days"))}</span>
  </div>
  <div class="analysis-stock-performance">
    <span class="analysis-stock-price">{html.escape(_format_decimal(item['latest_price']))}</span>
    <span class="analysis-stock-return">{html.escape(_format_signed_pct((item['total_return'] or 0.0) * 100.0 if item['total_return'] is not None else None))}</span>
  </div>
</div>
        """
        for item in comparison_stats
    )

    with st.container(key="multi-stock-basic-section"):
        summary_col, chart_col, switch_col = st.columns([0.8, 1.46, 0.42], gap="large")
        with switch_col:
            with st.container(key="multi-stock-chart-switch"):
                st.caption(tr("chart.switch"))
                selected_chart = st.radio(
                    tr("chart.view"),
                    options=list(chart_configs.keys()),
                    format_func=lambda key: chart_configs[key]["label"],
                    key="multi_stock_basic_chart_view",
                    label_visibility="collapsed",
                )
                render_status_note(tr("note.chart_relocation"), tone="info")
        with summary_col:
            render_html(f"<div class='analysis-kv-grid'>{metrics_markup}</div>")
            render_html(
                f"""
<div class="analysis-stock-list">
  <div class="analysis-stock-list-title">{html.escape(tr("table.detailedComparison"))}</div>
  {stock_rows_markup}
</div>
                """
            )

        chart_meta = chart_configs[selected_chart]
        with chart_col:
            with st.container(key="multi-stock-chart-frame"):
                figure = None
                if selected_chart == "relative_strength" and len(stock_data_dict) >= 2:
                    benchmark_options = ["equal_weight"] + list(stock_data_dict.keys())
                    benchmark_choice = st.selectbox(
                        tr("analysis.relativeStrengthBaseline"),
                        options=benchmark_options,
                        format_func=lambda value: tr("method.equalWeightedAvg") if value == "equal_weight" else value,
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
                    render_status_note(chart_meta.get("empty_text", tr("results.notAvailable")), tone="warning")
                else:
                    figure.layout.title = None
                    st.plotly_chart(figure, width="stretch")
                    render_status_note(chart_meta["note"], tone="info")


def _render_multi_stock_strategy_section(
    *,
    params: dict,
    stock_data_dict: dict[str, pd.DataFrame],
) -> tuple[dict[str, Any] | None, Any]:
    workspace = _get_multi_strategy_workspace()
    applied_adjustments = st.session_state.get(MULTI_APPLIED_ADJUSTMENTS_KEY, {})
    params = _apply_multi_adjustments(params, applied_adjustments)
    periodic_heatmap_fig = None

    with st.container(key="multi-stock-strategy-section"):
        render_html(
            """
<div id="multi-stock-strategy"></div>
<div class="analysis-section-header">
  <div class="surface-kicker">{tr("common.strategy")}</div>
  <h2 class="analysis-section-title">多股策略区</h2>
  <p class="analysis-section-copy">左侧固定为模型控制台与组合搜索，右侧固定为结果图区、组合 KPI 摘要和个股表现表，对齐第七周第 8 项的“左控台 / 右结果区”结构。</p>
</div>
            """
        )

        control_col, result_col = st.columns([0.76, 1.24], gap="large")

        with control_col:
            with st.container(key="multi-stock-strategy-panel-control"):
                _render_surface_header(
                    tr("surface.control"),
                    tr("console.multiStockTitle"),
                    tr("layout.unifiedConfiguration"),
                )
                render_status_note(tr("validation.minimumTwoValidInstruments"), tone="info")

                st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
                st.markdown(tr("portfolio.weight.configuration"))
                weights_form = st.form("multi_stock_portfolio_weights")
                weight_cols = weights_form.columns(2, gap="small")
                portfolio_weights: dict[str, float] = {}
                for index, symbol in enumerate(stock_data_dict.keys()):
                    with weight_cols[index % 2]:
                        portfolio_weights[symbol] = weights_form.number_input(
                            f"{symbol} 权重",
                            min_value=0.0,
                            max_value=10.0,
                            value=1.0,
                            step=0.1,
                            key=f"multi_stock_weight_{symbol}",
                        )
                weights_form.form_submit_button("应用权重", width="stretch")

                strategy_signature = _build_multi_strategy_signature(stock_data_dict, params, portfolio_weights)
                if workspace.get("portfolio_result") is not None and workspace.get("signature") != strategy_signature:
                    render_status_note(tr("warning.rebuildStrategy"), tone="warning")

                if st.button(
                    tr("strategy.generatePortfolio"),
                    type="primary",
                    use_container_width=True,
                    key="multi_stock_generate_strategy",
                ):
                    if sum(portfolio_weights.values()) <= 0:
                        st.error(tr("validation.portfolio_weight_sum"))
                    else:
                        with st.spinner(tr("strategy.running_multi_stock_simulation")):
                            portfolio_params = _strategy_params(params)
                            portfolio_params["weights"] = portfolio_weights
                            generated_result = run_portfolio_simulation(stock_data_dict, **portfolio_params)
                        workspace["signature"] = strategy_signature
                        workspace["portfolio_result"] = generated_result
                        if generated_result is not None:
                            st.success(tr("portfolio.generation_complete"))
                        else:
                            st.error(tr("portfolio.insufficientData"))

                st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
                with st.expander(tr("params.multi_stock_adjust"), expanded=False):
                    st.caption(tr("params.multi_stock_adjust.description"))

                    st.markdown(f"**{tr('params.entry_exit')}**")
                    _me_col1, _me_col2 = st.columns(2)
                    with _me_col1:
                        _adj_entry = st.slider(
                            tr("strategy.entryScoreThreshold"), -2.0, 2.0,
                            value=float(params.get("entry_threshold", 0.5)),
                            step=0.1,
                            key="multi_adj_entry_threshold",
                        )
                    with _me_col2:
                        _adj_exit = st.slider(
                            tr("threshold.exitScore"), -2.0, 2.0,
                            value=float(params.get("exit_threshold", -0.5)),
                            step=0.1,
                            key="multi_adj_exit_threshold",
                        )

                    st.markdown(f"**{tr('params.risk_control')}**")
                    _mr_col1, _mr_col2 = st.columns(2)
                    with _mr_col1:
                        _adj_sl = st.slider(
                            tr("param.atrStopLossMultiplier"), 0.0, 5.0,
                            value=float(params.get("stop_loss_mult", 2.0)),
                            step=0.5,
                            key="multi_adj_stop_loss",
                        )
                    with _mr_col2:
                        _adj_tp = st.slider(
                            tr("strategy.atr.takeProfitMultiplier"), 0.0, 8.0,
                            value=float(params.get("take_profit_mult", 4.0)),
                            step=0.5,
                            key="multi_adj_take_profit",
                        )

                    st.markdown(f"**{tr('params.factor_weights')}**")
                    _mw_col1, _mw_col2 = st.columns(2)
                    with _mw_col1:
                        _adj_wbb = st.slider(
                            tr("weight.bollinger_position"), 0.0, 2.0,
                            value=float(params.get("weight_bb", 0.8)),
                            step=0.1,
                            key="multi_adj_weight_bb",
                        )
                        _adj_wvol = st.slider(
                            tr("weight.volume_ratio"), 0.0, 1.5,
                            value=float(params.get("weight_volume", 0.6)),
                            step=0.1,
                            key="multi_adj_weight_volume",
                        )
                        _adj_wdd = st.slider(
                            tr("parameter.drawdownPenaltyWeight"), 0.0, 1.5,
                            value=float(params.get("weight_drawdown", 0.5)),
                            step=0.1,
                            key="multi_adj_weight_drawdown",
                        )
                    with _mw_col2:
                        _adj_wobv = st.slider(
                            tr("parameter.obvTrendWeight"), 0.0, 2.0,
                            value=float(params.get("weight_obv", 1.0)),
                            step=0.1,
                            key="multi_adj_weight_obv",
                        )
                        _adj_wprice = st.slider(
                            tr("strategy.pricePositionWeight"), 0.0, 1.5,
                            value=float(params.get("weight_price", 0.7)),
                            step=0.1,
                            key="multi_adj_weight_price",
                        )

                    adjustments = {
                        "entry_threshold": _adj_entry,
                        "exit_threshold": _adj_exit,
                        "stop_loss_mult": _adj_sl,
                        "take_profit_mult": _adj_tp,
                        "weight_bb": _adj_wbb,
                        "weight_obv": _adj_wobv,
                        "weight_volume": _adj_wvol,
                        "weight_price": _adj_wprice,
                        "weight_drawdown": _adj_wdd,
                    }
                    params = _apply_multi_adjustments(params, adjustments)
                    st.session_state[MULTI_APPLIED_ADJUSTMENTS_KEY] = adjustments

                st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
                st.markdown(tr("section.title.comboParamSearch"))
                portfolio_n_trials = st.slider(
                    tr("param.optimization_trials"),
                    10,
                    100,
                    30,
                    step=10,
                    key="portfolio_n_trials",
                    help=tr("optimization.trialCount.tip"),
                )
                if st.button(tr("action.startComboSearch"), use_container_width=True, key="btn_optimize_portfolio"):
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
                            (tr("metric.optimized_sharpe"), f"{optimization_result['sharpe']:.2f}"),
                            (tr("backtest.optimizedReturn"), f"{optimization_result['return']:.2%}"),
                            (tr("metric.optimizedDrawdown"), f"{optimization_result['max_drawdown']:.2%}"),
                        ],
                    ):
                        column.metric(label, value)
                    with st.expander(tr("action.viewOptimalParams"), expanded=False):
                        opt_params_display = {
                            tr("strategy.entryThreshold"): f"{optimization_result['entry_threshold']:.2f}",
                            tr("strategy.exitThreshold"): f"{optimization_result['exit_threshold']:.2f}",
                            tr("indicators.adx.threshold"): f"{optimization_result['adx_threshold']:.1f}",
                            tr("strategy.stopLossMultiplier"): f"{optimization_result['stop_loss_mult']:.2f}",
                            tr("strategy.takeProfitMultiplier"): f"{optimization_result['take_profit_mult']:.2f}",
                            tr("param.bollingerWeight"): f"{optimization_result['weight_bb']:.2f}",
                            tr("param.obv_weight"): f"{optimization_result['weight_obv']:.2f}",
                            tr("weight.volume"): f"{optimization_result['weight_volume']:.2f}",
                            tr("strategy.pricePositionWeight"): f"{optimization_result['weight_price']:.2f}",
                            tr("parameter.drawdownPenaltyWeight"): f"{optimization_result['weight_drawdown']:.2f}",
                        }
                        st.dataframe(
                            pd.DataFrame(list(opt_params_display.items()), columns=[tr("section.parameters"), tr("performance.optimalValue")]),
                            width="stretch",
                            hide_index=True,
                        )

        portfolio_result = workspace.get("portfolio_result") if workspace.get("signature") == strategy_signature else None

        with result_col:
            with st.container(key="multi-stock-strategy-panel-result"):
                _render_surface_header(
                    tr("surface.result"),
                    tr("results.portfolio_section"),
                    tr("result.mainChart.description"),
                )
                if portfolio_result is None:
                    render_status_note(tr("model.not_ready"), tone="info")
                else:
                    result_view = st.segmented_control(
                        tr("strategy.result_view"),
                        options=[tr("simulation.portfolio"), tr("chart.periodReturnHeatmap")],
                        default=tr("simulation.portfolio"),
                        key="multi_stock_strategy_view",
                        width="stretch",
                    )

                    if result_view == tr("chart.periodReturnHeatmap"):
                        heatmap_period = st.selectbox(
                            tr("chart.heatmap.period"),
                            options=["M", "Q", "YE"],
                            format_func=lambda value: {"M": tr("period.monthly"), "Q": tr("period.quarter"), "YE": tr("time.annual")}.get(value, value),
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
                            render_status_note(tr("chart.insufficientDataForHeatmap"), tone="warning")
                    else:
                        portfolio_fig = portfolio_result.get("fig")
                        if portfolio_fig is None:
                            portfolio_fig = build_portfolio_figure(portfolio_result)
                            portfolio_result["fig"] = portfolio_fig
                        portfolio_fig = _style_display_figure(portfolio_fig, height=520)
                        if portfolio_fig is not None:
                            st.plotly_chart(portfolio_fig, width="stretch")
                            render_status_note(tr("chart.shared_net_drawdown_component"), tone="info")
                        else:
                            render_status_note(tr("chart.portfolioNetValue.missing"), tone="warning")

                    kpi_cols = st.columns(3, gap="small")
                    kpi_items = [
                        (tr("portfolio.totalReturn"), f"{portfolio_result['port_total_return']:.2%}", tr("nav.strategy_portfolio")),
                        (tr("metric.portfolioSharpe"), f"{portfolio_result['port_sharpe']:.2f}", tr("nav.strategy_portfolio")),
                        (tr("metric.portfolio_max_drawdown"), f"{portfolio_result['port_max_dd']:.2%}", tr("nav.strategy_portfolio")),
                        (tr("metric.buyAndHoldReturn"), f"{portfolio_result['bh_total_return']:.2%}", tr("benchmark.equalWeight")),
                        (tr("metric.buy_hold_sharpe"), f"{portfolio_result['bh_sharpe']:.2f}", tr("benchmark.equalWeight")),
                        (tr("metrics.buy_hold_drawdown"), f"{portfolio_result['bh_max_dd']:.2%}", tr("benchmark.equalWeight")),
                    ]
                    for column, (label, value, _help_text) in zip(kpi_cols * 2, kpi_items):
                        column.metric(label, value)

                    with st.expander(tr("performance.individual_stock_strategy"), expanded=False):
                        indiv_stats = []
                        for sym, res in portfolio_result["individual_results"].items():
                            indiv_stats.append(
                                {
                                    tr("instrument.type.stock"): sym,
                                    tr("common.weight"): f"{portfolio_result['weights'].get(sym, 0):.1%}",
                                    tr("metric.strategyReturn"): f"{res['total_return']:.2%}",
                                    tr("metric.sharpe_ratio"): f"{res['sharpe']:.2f}",
                                    tr("metrics.max_drawdown"): f"{res['max_dd']:.2%}",
                                }
                            )
                        if indiv_stats:
                            st.dataframe(pd.DataFrame(indiv_stats), width="stretch", hide_index=True)
                        else:
                            render_status_note(tr("info.no_individual_strategy_performance"), tone="warning")

                    render_status_note(tr("layout.combinedKPIAndStockTable"), tone="positive")

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

    if analysis_cache.get("data_signature") == data_signature:
        emit_performance_event("multi", "data_load", 0.0, cache="hit", market=market, count=len(compare_stocks))

    if analysis_cache.get("data_signature") != data_signature:
        data_load_started_at = perf_counter()
        with st.spinner(tr("data.loadingComparison")):
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
        emit_performance_event(
            "multi",
            "data_load",
            (perf_counter() - data_load_started_at) * 1000,
            cache="miss",
            market=market,
            count=len(stock_data_dict),
        )

    stock_data_dict = analysis_cache.get("stock_data_dict", {})
    factor_stock_data_dict = analysis_cache.get("factor_stock_data_dict", {})
    comparison_stats = analysis_cache.get("comparison_stats", [])

    if len(stock_data_dict) == 0:
        st.warning(tr("data.stocks.invalid"))
        return

    portfolio_result = None

    chart_configs = {
        "comparison": {
            "label": tr("priceComparison.title"),
            "title": tr("chart.multiStockComparison"),
            "copy": tr("strategy.unified_start_comparison"),
            "note": tr("chart.normalizedCurvesNote"),
            "empty_text": tr("chart.priceComparison.insufficientData"),
        },
        "relative_strength": {
            "label": tr("indicator.relative_strength"),
            "title": tr("chart.relativeStrength"),
            "copy": tr("analysis.benchmark_equal_weight_description"),
            "note": tr("relativeStrength.legend"),
            "empty_text": tr("error.insufficientDataForRelativeStrength"),
        },
        "risk_return": {
            "label": tr("metric.riskReturn"),
            "title": tr("chart.riskReturnScatter"),
            "copy": tr("chart.riskReturn.description"),
            "note": tr("chart.scatter_plot_legend"),
            "empty_text": tr("chart.insufficientDataForRiskReturn"),
        },
        "factor_score": {
            "label": tr("factor.score"),
            "title": tr("visualization.latest_factor_score_comparison"),
            "copy": tr("analysis.dailyFactorRanking"),
            "note": tr("chart.factorScore.tooltip"),
            "empty_text": tr("error.insufficientHistory"),
        },
        "correlation": {
            "label": tr("metrics.correlation"),
            "title": tr("analysis.correlationHeatmap"),
            "copy": tr("analysis.correlation_matrix_description"),
            "note": tr("correlation.legend"),
            "empty_text": tr("chart.correlationHeatmap.insufficientData"),
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


def _apply_multi_adjustments(params: dict[str, Any], adjustments: dict[str, float]) -> dict[str, Any]:
    """Return calculation parameters with explicitly applied UI adjustments."""
    return {**params, **adjustments}


def _strategy_params(params: dict) -> dict:
    """function.extractStrategyParams.description"""
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
    """export.htmlZone"""
    st.markdown("---")
    st.markdown(tr("export.report_title"))

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        export_title = st.text_input(
            tr("report.title"),
            value=f"多股票对比分析 - {', '.join(compare_stocks)}",
            key="export_title",
        )
    with col2:
        include_date = st.checkbox(tr("report.include_generation_date"), value=True, key="include_date")

    if not st.button(tr("report.generate_download_html"), type="primary", width="stretch"):
        return

    with st.spinner(tr("report.generatingHtml")):
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
            market=params.get("market", ""),
            language=get_ui_language(),
            theme=get_ui_theme(),
            generated_at=generated_at,
        )

        st.download_button(
            label=tr("action.downloadHtmlReport"),
            data=full_html,
            file_name=f"stock_comparison_report_{generated_at.strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
        st.success(tr("report.html.generated"))
