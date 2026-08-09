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
from core.market_context import RECOMMENDATION_SOURCE_I18N_KEYS, get_market_context_snapshot
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


def _render_surface_header(kicker: str | None, title: str, copy: str | None = None) -> None:
    parts = []
    if kicker:
        parts.append(f'<div class="surface-kicker">{html.escape(kicker)}</div>')
    parts.append(f'<div class="surface-title">{html.escape(title)}</div>')
    if copy:
        parts.append(f'<p class="surface-copy">{html.escape(copy)}</p>')
    render_html("".join(parts))


def _render_section_header(title: str, copy: str | None = None) -> None:
    parts = [f'<div class="entry-section-title">{html.escape(title)}</div>']
    if copy:
        parts.append(f'<p class="entry-section-copy">{html.escape(copy)}</p>')
    render_html("".join(parts))


def _render_csv_requirements_popover() -> None:
    with st.container(key="multi-csv-requirements"):
        with st.popover(tr("entry.csvRequirements.trigger")):
            st.markdown(f"**{tr('entry.csvRequirements.title')}**")
            st.markdown(tr("entry.csvRequirements.body"))
            st.code(
                "date,open,high,low,close,volume\n"
                "2026-08-05,100.20,102.10,99.80,101.60,1250000\n"
                "2026-08-06,101.70,103.00,100.90,102.40,1380000",
                language="csv",
            )
            st.caption(tr("entry.csvRequirements.source"))


def _render_snapshot(indices: list[dict[str, Any]]) -> None:
    if not indices:
        render_status_note(tr("award.entry.marketEmpty"), tone="warning")
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
  <span class="snapshot-label">{html.escape(str(item.get('label') or tr('award.common.noData')))}</span>
  <span class="snapshot-value">{html.escape(str(item.get('close_text') or tr('award.common.noData')))}</span>
  <span class="snapshot-delta {delta_class}">{html.escape(str(item.get('pct_text') or tr('award.common.noData')))}</span>
</div>
            """
        )
    st.markdown(f"<div class='snapshot-grid'>{''.join(blocks)}</div>", unsafe_allow_html=True)


def _recommendation_source_text(context: dict[str, Any]) -> str:
    source_kind = str(context.get("recommendation_source_kind") or "").strip()
    translation_key = RECOMMENDATION_SOURCE_I18N_KEYS.get(source_kind)
    if translation_key:
        return tr(translation_key)
    return str(context.get("recommendation_source") or tr("award.common.noData"))


def _recommendation_meta_text(item: dict[str, Any]) -> str:
    heat_text = item.get("heat_text")
    change_text = str(item.get("pct_text") or tr("award.common.noData"))
    if heat_text:
        return tr("award.entry.heatQuote", heat=str(heat_text), change=change_text)
    return tr(
        "award.entry.quote",
        price=str(item.get("price_text") or tr("award.common.noData")),
        change=change_text,
    )


def _render_recommendation_rows(recommendations: list[dict[str, Any]]) -> None:
    if not recommendations:
        render_status_note(tr("recommendation.unavailable"), tone="warning")
        return

    with st.container(key="multi-recommend-scroll"):
        for item in recommendations:
            info_col, action_col = st.columns([5.9, 0.95], gap="small")
            symbol = str(item.get("symbol") or "").strip()
            info_col.markdown(
                f"<div class='recommend-row'><div class='recommend-row-title'>{html.escape(symbol or tr('award.common.noData'))} · {html.escape(str(item.get('name') or tr('award.common.noData')))}</div><div class='recommend-row-meta'>{html.escape(_recommendation_meta_text(item))}</div></div>",
                unsafe_allow_html=True,
            )
            if symbol and action_col.button(
                tr("action.add"),
                key=f"multi_entry_rec_{symbol}",
                type="primary",
            ):
                _add_symbol_to_selection(symbol)
                st.rerun()


def _render_uploaded_file_rows(uploaded_files) -> None:
    if not uploaded_files:
        st.caption(tr("upload.noFileSelected"))
        return

    with st.container(key="multi-upload-list"):
        for index, uploaded_file in enumerate(uploaded_files, start=1):
            symbol = _sanitize_upload_symbol(uploaded_file.name, index)
            st.markdown(
                f"<div class='upload-row'><div class='upload-row-title'>{html.escape(uploaded_file.name)}</div><div class='upload-row-meta'>{html.escape(tr('award.entry.importId', symbol=symbol))}</div></div>",
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
                f"<div class='selection-row'><div class='selection-row-title'>{html.escape(symbol)}</div><div class='selection-row-meta'>{html.escape(tr('award.entry.selectionSource'))}</div></div>",
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
  <h1 class="entry-title">{tr("award.entry.multi.title")}</h1>
</section>
        """
    )

    selected_action: dict[str, Any] | None = None
    with st.container(key="multi-entry-split"):
        left_col, right_col = st.columns([1.02, 0.98], gap="large")

    with left_col:
        with st.container(key="multi-action-card"):
            _render_surface_header(
                None,
                tr("action.selectStocks"),
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
            if st.button(
                tr("stockPool.addAction"),
                type="primary",
                use_container_width=True,
            ):
                selected_symbol = st.session_state.get(MULTI_ENTRY_SELECTED_SYMBOL_KEY)
                if not selected_symbol:
                    render_status_note(tr("stock.selectionFromSearchPrompt"), tone="warning")
                else:
                    _add_symbol_to_selection(selected_symbol)
                    st.rerun()

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                tr("data.upload.multipleCSV"),
            )
            _render_csv_requirements_popover()

            uploaded_files = st.file_uploader(
                tr("upload.multi_csv_title"),
                type=["csv"],
                accept_multiple_files=True,
                key="multi_entry_upload_files",
                help=tr("data.csvFormat"),
                label_visibility="collapsed",
            )
            _render_uploaded_file_rows(uploaded_files)

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            selected_symbols = _ensure_selected_list()
            with st.container(key="multi-selected-stock-popover"):
                with st.popover(tr("section.currentSelectedStocks")):
                    if selected_symbols:
                        _render_selected_symbol_rows(selected_symbols)
                    else:
                        st.caption(tr("award.common.noData"))

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

    if selected_action is not None:
        return selected_action

    with right_col:
        with st.container(key="multi-showcase-board"):
            _render_surface_header(
                tr("award.entry.showcaseBoard"),
                tr("section.market_snapshot_and_entry"),
            )
            with st.container(key="multi-market-heading-row"):
                market_col, refresh_col = st.columns([0.6, 1.4], gap="small")
                with market_col:
                    _render_section_header(tr("section.title.marketSnapshot"))
                with refresh_col:
                    with st.container(key="multi-refresh-market-context"):
                        refresh_context = st.button(
                            tr("action.refreshMarketSnapshot"),
                            key="multi_entry_refresh_market_context",
                            type="primary",
                            use_container_width=True,
                        )

            try:
                context = get_market_context_snapshot(market, force_refresh=refresh_context)
            except Exception as exc:
                context = {
                    "indices": [],
                    "recommendation_source_kind": "unavailable",
                    "recommendation_source": tr("status.marketSnapshotUnavailable"),
                    "recommendations": [],
                }
                render_status_note(tr("entry.marketSnapshotFailed", error=str(exc)), tone="warning")

            _render_snapshot(context.get("indices") or [])
            st.markdown(
                f"<p class='source-note'>{html.escape(tr('award.entry.recommendationSource'))}: <strong>{html.escape(_recommendation_source_text(context))}</strong></p>",
                unsafe_allow_html=True,
            )

            with st.container(key="multi-recommend-sheet"):
                _render_section_header(
                    tr("recommendation.stocks"),
                )
                _render_recommendation_rows(context.get("recommendations") or [])

    return selected_action
