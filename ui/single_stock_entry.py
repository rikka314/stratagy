"""
单股入口页
==========
"""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st
from ui.i18n import tr

from core.data import search_stock_candidates
from core.market_context import get_market_context_snapshot
from ui.theme import render_html, render_status_note


SINGLE_ENTRY_MARKET_KEY = "single_entry_market"
SINGLE_ENTRY_QUERY_KEY = "single_entry_query"
SINGLE_ENTRY_SELECTED_SYMBOL_KEY = "single_entry_selected_symbol"
SINGLE_ENTRY_LAST_MARKET_KEY = "single_entry_last_market"


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


def _render_recommendation_rows(recommendations: list[dict[str, Any]], market: str) -> dict[str, Any] | None:
    if not recommendations:
        render_status_note(tr("recommendation.unavailable"), tone="warning")
        return None

    clicked_action: dict[str, Any] | None = None
    with st.container(key="single-recommend-scroll"):
        for item in recommendations:
            info_col, action_col = st.columns([5.9, 0.95], gap="small")
            info_col.markdown(
                (
                    "<div class='recommend-row'>"
                    f"<div class='recommend-row-title'>{html.escape(item['symbol'])} &middot; {html.escape(item['name'])}</div>"
                    f"<div class='recommend-row-meta'>现价 {html.escape(item['price_text'])} &middot; 涨跌 {html.escape(item['pct_text'])}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            if action_col.button(tr("button.analyze"), key=f"single_entry_rec_{item['symbol']}"):
                clicked_action = {
                    "kind": "symbol",
                    "market": market,
                    "symbol": item["symbol"],
                    "source": "recommended",
                }
    return clicked_action


def render_single_stock_entry_page(initial_market: str = "US") -> dict[str, Any] | None:
    """ui.singleStockEntry.description"""
    render_market = "A" if str(initial_market).upper() in {"A", "CN", "CN_A"} else "US"
    if SINGLE_ENTRY_MARKET_KEY not in st.session_state:
        st.session_state[SINGLE_ENTRY_MARKET_KEY] = render_market
    if SINGLE_ENTRY_LAST_MARKET_KEY not in st.session_state:
        st.session_state[SINGLE_ENTRY_LAST_MARKET_KEY] = st.session_state[SINGLE_ENTRY_MARKET_KEY]

    render_html(
        f"""
<section class="entry-intro">
  <div class="page-kicker">{tr("entry.single.routeKicker")}</div>
  <h1 class="entry-title">{tr("entry.single.title")}</h1>
  <p class="entry-copy">{tr("entry.single.copy")}</p>
</section>
        """
    )

    selected_action: dict[str, Any] | None = None
    left_col, right_col = st.columns([1.02, 0.98], gap="large")

    with left_col:
        with st.container(key="single-action-card"):
            _render_surface_header(
                tr("surface.actionCard"),
                tr("onboarding.clearEntry"),
                tr("ui.main_card_design"),
            )

            market = st.segmented_control(
                tr("action.research_market"),
                options=["US", "A"],
                format_func=lambda value: tr("market.us_stocks") if value == "US" else tr("market.cn_stock"),
                key=SINGLE_ENTRY_MARKET_KEY,
                width="stretch",
            )
            market = "A" if market == "A" else "US"
            if st.session_state.get(SINGLE_ENTRY_LAST_MARKET_KEY) != market:
                st.session_state[SINGLE_ENTRY_LAST_MARKET_KEY] = market
                st.session_state[SINGLE_ENTRY_SELECTED_SYMBOL_KEY] = None
                st.session_state[SINGLE_ENTRY_QUERY_KEY] = ""

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                tr("action.searchConfirmTarget"),
                tr("search.fallbackToCode"),
            )

            search_query = st.text_input(
                tr("placeholder.stockInput"),
                placeholder=tr("placeholder.stock_example"),
                key=SINGLE_ENTRY_QUERY_KEY,
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
                        key=SINGLE_ENTRY_SELECTED_SYMBOL_KEY,
                        label_visibility="collapsed",
                    )
                elif market == "A" and search_query.isdigit():
                    st.session_state[SINGLE_ENTRY_SELECTED_SYMBOL_KEY] = search_query.zfill(6)[-6:]
                    render_status_note(tr("analysis.fallback.noIndexMatch"), tone="info")
                elif market == "US":
                    st.session_state[SINGLE_ENTRY_SELECTED_SYMBOL_KEY] = search_query.upper()
                    render_status_note(tr("warning.no_index_match_fallback"), tone="info")
                else:
                    render_status_note(tr("search.noMatchingStocks"), tone="warning")
            else:
                st.caption(tr("ui.stockSearchHint"))

            selected_symbol = st.session_state.get(SINGLE_ENTRY_SELECTED_SYMBOL_KEY)
            if selected_symbol:
                st.markdown(
                    f"<p class='selection-note'>当前准备分析：<strong>{html.escape(selected_symbol)}</strong></p>",
                    unsafe_allow_html=True,
                )

            if st.button(tr("action.startSingleStockAnalysis"), type="primary", use_container_width=True):
                if not selected_symbol:
                    render_status_note(tr("stock_selection.required"), tone="warning")
                else:
                    selected_action = {
                        "kind": "symbol",
                        "market": market,
                        "symbol": selected_symbol,
                        "source": "search",
                    }

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                tr("action.upload_local_csv"),
                tr("instruction.uploadReadyData"),
            )

            uploaded_file = st.file_uploader(
                tr("action.upload_single_stock_csv"),
                type=["csv"],
                key="single_entry_upload_file",
                help=tr("data.columnName.standard"),
            )
            if uploaded_file is not None:
                st.markdown(
                    f"<p class='selection-note'>已选择文件：<strong>{html.escape(uploaded_file.name)}</strong></p>",
                    unsafe_allow_html=True,
                )
                if st.button(tr("analysis.startWithUploadedData"), use_container_width=True, key="single_entry_upload_btn"):
                    selected_action = {
                        "kind": "upload",
                        "market": market,
                        "name": uploaded_file.name,
                        "bytes": uploaded_file.getvalue(),
                        "source": "upload",
                    }
            else:
                st.caption(tr("upload.noFileSelected"))

            render_html(
                f"""
<p class="plain-helper">{tr("entry.single.helper")}</p>
                """
            )

    if selected_action is not None:
        return selected_action

    with right_col:
        with st.container(key="single-showcase-board"):
            _render_surface_header(
                tr("surface.showcaseBoard"),
                tr("section.market_snapshot_and_entry"),
                tr("ui.unifiedPreviewArea"),
            )

            market_col, refresh_col = st.columns([1.0, 0.34], gap="small")
            with market_col:
                _render_section_header(
                    tr("section.title.marketSnapshot"),
                    tr("onboarding.market_overview_flow"),
                )
            with refresh_col:
                refresh_context = st.button(
                    tr("action.refreshMarketSnapshot"),
                    key="single_entry_refresh_market_context",
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

            with st.container(key="single-recommend-sheet"):
                _render_section_header(
                    tr("recommendation.stocks"),
                    tr("ui.recommendationSheet"),
                )
                recommendation_action = _render_recommendation_rows(context["recommendations"], market=market)
                if recommendation_action is not None:
                    selected_action = recommendation_action

    return selected_action
