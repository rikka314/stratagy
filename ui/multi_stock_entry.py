"""
多股入口页
==========
"""

from __future__ import annotations

import html
import re
from typing import Any

import pandas as pd
import streamlit as st
from ui.i18n import tr

from core.data import search_stock_candidates
from core.market_context import get_market_context_snapshot
from ui.theme import render_html, render_status_note


MULTI_ENTRY_MARKET_KEY = "multi_entry_market"
MULTI_ENTRY_QUERY_KEY = "multi_entry_query"
MULTI_ENTRY_SELECTED_SYMBOL_KEY = "multi_entry_selected_symbol"
MULTI_ENTRY_SELECTED_LIST_KEY = "multi_entry_selected_symbols"
MULTI_ENTRY_LAST_MARKET_KEY = "multi_entry_last_market"


def _ensure_selected_list() -> list[str]:
    symbols = st.session_state.get(MULTI_ENTRY_SELECTED_LIST_KEY)
    if not isinstance(symbols, list):
        symbols = []
        st.session_state[MULTI_ENTRY_SELECTED_LIST_KEY] = symbols
    return symbols


def _add_symbol_to_selection(symbol: str) -> None:
    symbols = _ensure_selected_list()
    normalized = str(symbol or "").strip().upper()
    if normalized and normalized not in symbols:
        symbols.append(normalized)
        st.session_state[MULTI_ENTRY_SELECTED_LIST_KEY] = symbols


def _remove_symbols_from_selection(symbols_to_remove: list[str]) -> None:
    symbols = [item for item in _ensure_selected_list() if item not in set(symbols_to_remove)]
    st.session_state[MULTI_ENTRY_SELECTED_LIST_KEY] = symbols


def _sanitize_upload_symbol(filename: str, fallback_index: int) -> str:
    stem = filename.rsplit(".", 1)[0]
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    stem = stem.upper() or f"UPLOAD_{fallback_index}"
    return stem[:24]


def _render_surface_header(kicker: str, title: str, copy: str) -> None:
    render_html(
        f"""
<div class="surface-kicker">{html.escape(kicker)}</div>
<div class="surface-title">{html.escape(title)}</div>
<p class="surface-copy">{html.escape(copy)}</p>
        """
    )


def _render_section_header(title: str, copy: str) -> None:
    render_html(
        f"""
<div class="entry-section-title">{html.escape(title)}</div>
<p class="entry-section-copy">{html.escape(copy)}</p>
        """
    )


def _render_snapshot(indices: list[dict[str, Any]]) -> None:
    if not indices:
        render_status_note(tr("data.market.loading"), tone="info")
        return

    blocks = []
    for item in indices:
        delta_class = ""
        if item.get("is_positive") is True:
            delta_class = "up"
        elif item.get("is_positive") is False:
            delta_class = "down"
        blocks.append(
            f"""
<div class="snapshot-item">
  <span class="snapshot-label">{html.escape(item['label'])}</span>
  <span class="snapshot-value">{html.escape(item['close_text'])}</span>
  <span class="snapshot-delta {delta_class}">{html.escape(item['pct_text'])}</span>
</div>
            """
        )
    st.markdown(f"<div class='snapshot-grid'>{''.join(blocks)}</div>", unsafe_allow_html=True)


def _render_recommendation_rows(recommendations: list[dict[str, Any]]) -> None:
    if not recommendations:
        render_status_note(tr("recommendation.unavailable"), tone="warning")
        return

    with st.container(key="multi-recommend-scroll"):
        for item in recommendations:
            info_col, action_col = st.columns([5.9, 0.95], gap="small")
            info_col.markdown(
                f"<div class='recommend-row'><div class='recommend-row-title'>{html.escape(item['symbol'])} · {html.escape(item['name'])}</div><div class='recommend-row-meta'>现价 {html.escape(item['price_text'])} · 涨跌 {html.escape(item['pct_text'])}</div></div>",
                unsafe_allow_html=True,
            )
            if action_col.button(tr("action.add"), key=f"multi_entry_rec_{item['symbol']}"):
                _add_symbol_to_selection(item["symbol"])
                st.rerun()


def _render_uploaded_file_rows(uploaded_files) -> None:
    if not uploaded_files:
        st.caption(tr("upload.noFileSelected"))
        return

    with st.container(key="multi-upload-list"):
        for index, uploaded_file in enumerate(uploaded_files, start=1):
            symbol = _sanitize_upload_symbol(uploaded_file.name, index)
            st.markdown(
                f"<div class='upload-row'><div class='upload-row-title'>{html.escape(uploaded_file.name)}</div><div class='upload-row-meta'>导入标识：{html.escape(symbol)}</div></div>",
                unsafe_allow_html=True,
            )


def _render_selected_symbol_rows(selected_symbols: list[str]) -> None:
    if not selected_symbols:
        st.caption(tr("stock.selection.insufficientForMulti"))
        return

    with st.container(key="multi-selected-symbols"):
        for symbol in selected_symbols:
            info_col, action_col = st.columns([6.0, 0.95], gap="small")
            info_col.markdown(
                f"<div class='selection-row'><div class='selection-row-title'>{html.escape(symbol)}</div><div class='selection-row-meta'>来源：搜索或推荐加入</div></div>",
                unsafe_allow_html=True,
            )
            if action_col.button(tr("common.remove"), key=f"multi_entry_remove_{symbol}"):
                _remove_symbols_from_selection([symbol])
                st.rerun()


def render_multi_stock_entry_page(initial_market: str = "US") -> dict[str, Any] | None:
    """ui.multiStockEntry.render"""
    render_market = "A" if str(initial_market).upper() in {"A", "CN", "CN_A"} else "US"
    if MULTI_ENTRY_MARKET_KEY not in st.session_state:
        st.session_state[MULTI_ENTRY_MARKET_KEY] = render_market
    if MULTI_ENTRY_SELECTED_LIST_KEY not in st.session_state:
        st.session_state[MULTI_ENTRY_SELECTED_LIST_KEY] = []
    if MULTI_ENTRY_LAST_MARKET_KEY not in st.session_state:
        st.session_state[MULTI_ENTRY_LAST_MARKET_KEY] = st.session_state[MULTI_ENTRY_MARKET_KEY]

    render_html(
        f"""
<section class="entry-intro">
  <div class="page-kicker">{tr("entry.multi.routeKicker")}</div>
  <h1 class="entry-title">{tr("entry.multi.title")}</h1>
  <p class="entry-copy">{tr("entry.multi.copy")}</p>
</section>
        """
    )

    selected_action: dict[str, Any] | None = None
    left_col, right_col = st.columns([1.03, 0.97], gap="large")

    with left_col:
        with st.container(key="multi-action-card"):
            _render_surface_header(
                tr("surface.actionCard"),
                tr("action.organizeStockPool"),
                tr("ui.mainOperationCard.desc"),
            )

            market = st.segmented_control(
                tr("action.research_market"),
                options=["US", "A"],
                format_func=lambda value: tr("market.us_stocks") if value == "US" else tr("market.cn_stock"),
                key=MULTI_ENTRY_MARKET_KEY,
                width="stretch",
            )
            market = "A" if market == "A" else "US"
            if st.session_state.get(MULTI_ENTRY_LAST_MARKET_KEY) != market:
                st.session_state[MULTI_ENTRY_LAST_MARKET_KEY] = market
                st.session_state[MULTI_ENTRY_QUERY_KEY] = ""
                st.session_state[MULTI_ENTRY_SELECTED_SYMBOL_KEY] = None
                st.session_state[MULTI_ENTRY_SELECTED_LIST_KEY] = []

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                tr("action.search_and_add_stocks"),
                tr("search.instructions"),
            )

            search_query = st.text_input(
                tr("placeholder.stockInput"),
                placeholder=tr("input.stock.example"),
                key=MULTI_ENTRY_QUERY_KEY,
            ).strip()

            if search_query:
                try:
                    matched = search_stock_candidates(search_query, market=market, limit=8)
                except Exception as exc:
                    matched = pd.DataFrame(columns=["symbol", "name", "label"])
                    render_status_note(tr("entry.searchIndexFailed", error=str(exc)), tone="warning")

                if not matched.empty:
                    candidate_options = matched["symbol"].tolist()
                    candidate_map = {row.symbol: row.label for row in matched.itertuples(index=False)}
                    st.radio(
                        tr("search.matches"),
                        options=candidate_options,
                        format_func=lambda symbol: candidate_map.get(symbol, symbol),
                        key=MULTI_ENTRY_SELECTED_SYMBOL_KEY,
                        label_visibility="collapsed",
                    )
                elif market == "A" and search_query.isdigit():
                    st.session_state[MULTI_ENTRY_SELECTED_SYMBOL_KEY] = search_query.zfill(6)[-6:]
                    render_status_note(tr("stock_pool.add_by_a_share_code"), tone="info")
                elif market == "US":
                    st.session_state[MULTI_ENTRY_SELECTED_SYMBOL_KEY] = search_query.upper()
                    render_status_note(tr("stockPool.addByTicker"), tone="info")
                else:
                    render_status_note(tr("search.noMatchingStocks"), tone="warning")
            else:
                st.caption(tr("stock_pool.candidates_hint"))

            if st.button(tr("stockPool.addAction"), use_container_width=True):
                selected_symbol = st.session_state.get(MULTI_ENTRY_SELECTED_SYMBOL_KEY)
                if not selected_symbol:
                    render_status_note(tr("stock.selectionFromSearchPrompt"), tone="warning")
                else:
                    _add_symbol_to_selection(selected_symbol)
                    st.rerun()

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                tr("data.upload.multipleCSV"),
                tr("import.csv.description"),
            )

            uploaded_files = st.file_uploader(
                tr("upload.multi_csv_title"),
                type=["csv"],
                accept_multiple_files=True,
                key="multi_entry_upload_files",
                help=tr("data.csvFormat"),
            )
            _render_uploaded_file_rows(uploaded_files)

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                tr("section.currentSelectedStocks"),
                tr("comparison.stockList.description"),
            )

            selected_symbols = _ensure_selected_list()
            _render_selected_symbol_rows(selected_symbols)

            upload_count = len(uploaded_files or [])
            total_count = len(selected_symbols) + upload_count
            render_html(
                f"""
<p class="selection-note">
  当前待分析数量：<strong>{total_count}</strong> 个标的
  （手动/推荐 {len(selected_symbols)} 个，上传 {upload_count} 个）。
</p>
                """
            )

            if st.button(tr("action.startMultiStockAnalysis"), type="primary", use_container_width=True):
                uploads = []
                for index, uploaded_file in enumerate(uploaded_files or [], start=1):
                    uploads.append(
                        {
                            "symbol": _sanitize_upload_symbol(uploaded_file.name, index),
                            "name": uploaded_file.name,
                            "bytes": uploaded_file.getvalue(),
                        }
                    )

                total_count = len(selected_symbols) + len(uploads)
                if total_count < 2:
                    render_status_note(tr("multi_stock.minimum_requirement"), tone="warning")
                else:
                    selected_action = {
                        "kind": "analyze",
                        "market": market,
                        "symbols": list(selected_symbols),
                        "uploads": uploads,
                    }

            render_html(
                f"""
<p class="plain-helper">{tr("entry.multi.helper")}</p>
                """
            )

    if selected_action is not None:
        return selected_action

    with right_col:
        with st.container(key="multi-showcase-board"):
            _render_surface_header(
                tr("surface.showcaseBoard"),
                tr("market.snapshotTitle"),
                tr("ui.context_display_area"),
            )
            market_col, refresh_col = st.columns([1.0, 0.34], gap="small")
            with market_col:
                _render_section_header(
                    tr("section.title.marketSnapshot"),
                    tr("workflow.marketSnapshotFirst"),
                )
            with refresh_col:
                refresh_context = st.button(
                    tr("action.refreshMarketSnapshot"),
                    key="multi_entry_refresh_market_context",
                    use_container_width=False,
                )

            try:
                context = get_market_context_snapshot(market, force_refresh=refresh_context)
            except Exception as exc:
                context = {
                    "indices": [],
                    "recommendation_source": tr("status.marketSnapshotUnavailable"),
                    "recommendations": [],
                }
                render_status_note(tr("entry.marketSnapshotFailed", error=str(exc)), tone="warning")

            _render_snapshot(context["indices"])
            st.markdown(
                f"<p class='source-note'>当前推荐口径：<strong>{html.escape(context['recommendation_source'])}</strong></p>",
                unsafe_allow_html=True,
            )

            with st.container(key="multi-recommend-sheet"):
                _render_section_header(
                    tr("recommendation.stocks"),
                    tr("ui.recommendationArea.spec"),
                )
                _render_recommendation_rows(context["recommendations"])

    return selected_action
