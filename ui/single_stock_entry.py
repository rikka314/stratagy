"""
单股入口页
==========
"""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

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
        render_status_note("正在加载最新市场数据。", tone="info")
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
        render_status_note("暂时无法获取推荐股票。", tone="warning")
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
            if action_col.button("分析", key=f"single_entry_rec_{item['symbol']}"):
                clicked_action = {
                    "kind": "symbol",
                    "market": market,
                    "symbol": item["symbol"],
                    "source": "recommended",
                }
    return clicked_action


def render_single_stock_entry_page(initial_market: str = "US") -> dict[str, Any] | None:
    """渲染单股入口页，并在用户发起分析时返回动作。"""
    render_market = "A" if str(initial_market).upper() in {"A", "CN", "CN_A"} else "US"
    if SINGLE_ENTRY_MARKET_KEY not in st.session_state:
        st.session_state[SINGLE_ENTRY_MARKET_KEY] = render_market
    if SINGLE_ENTRY_LAST_MARKET_KEY not in st.session_state:
        st.session_state[SINGLE_ENTRY_LAST_MARKET_KEY] = st.session_state[SINGLE_ENTRY_MARKET_KEY]

    render_html(
        """
<section class="entry-intro">
  <div class="page-kicker">Single Stock Route</div>
  <h1 class="entry-title">先确定一个标的，再进入单股分析。</h1>
  <p class="entry-copy">
    这个入口页只负责建立研究上下文。左侧完成市场切换、搜索和上传，右侧持续展示当前市场快照与推荐入口。
  </p>
</section>
        """
    )

    selected_action: dict[str, Any] | None = None
    left_col, right_col = st.columns([1.02, 0.98], gap="large")

    with left_col:
        with st.container(key="single-action-card"):
            _render_surface_header(
                "Action Card",
                "从一个清楚的入口动作开始",
                "市场切换、搜索确认、开始分析和本地上传都放在同一张主操作卡里。",
            )

            market = st.segmented_control(
                "研究市场",
                options=["US", "A"],
                format_func=lambda value: "美股" if value == "US" else "A 股",
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
                "搜索并确认标的",
                "支持名称或代码检索。没有索引命中时，也会按代码直接进入分析。",
            )

            search_query = st.text_input(
                "输入股票名称或代码",
                placeholder="例如：AAPL / Apple / 贵州茅台 / 600519",
                key=SINGLE_ENTRY_QUERY_KEY,
            ).strip()

            if search_query:
                try:
                    matched = search_stock_candidates(search_query, market=market, limit=8)
                except Exception as exc:
                    matched = pd.DataFrame(columns=["symbol", "name", "label"])
                    render_status_note(f"搜索索引加载失败：{exc}", tone="warning")

                if not matched.empty:
                    candidate_options = matched["symbol"].tolist()
                    candidate_map = {row.symbol: row.label for row in matched.itertuples(index=False)}
                    st.radio(
                        "匹配结果",
                        options=candidate_options,
                        format_func=lambda symbol: candidate_map.get(symbol, symbol),
                        key=SINGLE_ENTRY_SELECTED_SYMBOL_KEY,
                        label_visibility="collapsed",
                    )
                elif market == "A" and search_query.isdigit():
                    st.session_state[SINGLE_ENTRY_SELECTED_SYMBOL_KEY] = search_query.zfill(6)[-6:]
                    render_status_note("未找到索引匹配，将按该 A 股代码直接尝试分析。", tone="info")
                elif market == "US":
                    st.session_state[SINGLE_ENTRY_SELECTED_SYMBOL_KEY] = search_query.upper()
                    render_status_note("未找到索引匹配，将按该美股代码直接尝试分析。", tone="info")
                else:
                    render_status_note("没有找到匹配股票。", tone="warning")
            else:
                st.caption("输入股票名称或代码后，这里会出现可直接进入分析的候选项。")

            selected_symbol = st.session_state.get(SINGLE_ENTRY_SELECTED_SYMBOL_KEY)
            if selected_symbol:
                st.markdown(
                    f"<p class='selection-note'>当前准备分析：<strong>{html.escape(selected_symbol)}</strong></p>",
                    unsafe_allow_html=True,
                )

            if st.button("开始单股分析", type="primary", use_container_width=True):
                if not selected_symbol:
                    render_status_note("请先从搜索结果中选择一只股票。", tone="warning")
                else:
                    selected_action = {
                        "kind": "symbol",
                        "market": market,
                        "symbol": selected_symbol,
                        "source": "search",
                    }

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                "上传本地单股 CSV",
                "如果你已经准备好标准化数据文件，可以直接用上传结果进入分析。",
            )

            uploaded_file = st.file_uploader(
                "上传单只股票 CSV",
                type=["csv"],
                key="single_entry_upload_file",
                help="列名需兼容 date/open/high/low/close/volume 标准。",
            )
            if uploaded_file is not None:
                st.markdown(
                    f"<p class='selection-note'>已选择文件：<strong>{html.escape(uploaded_file.name)}</strong></p>",
                    unsafe_allow_html=True,
                )
                if st.button("用上传数据开始分析", use_container_width=True, key="single_entry_upload_btn"):
                    selected_action = {
                        "kind": "upload",
                        "market": market,
                        "name": uploaded_file.name,
                        "bytes": uploaded_file.getvalue(),
                        "source": "upload",
                    }
            else:
                st.caption("还没有选择上传文件。")

            render_html(
                """
<p class="plain-helper">
  入口页只负责把研究对象和市场背景整理清楚。进入主分析页后，原有策略工作流、artifact 和下游分析继续保持不变。
</p>
                """
            )

    if selected_action is not None:
        return selected_action

    with right_col:
        with st.container(key="single-showcase-board"):
            _render_surface_header(
                "Showcase Board",
                "当前市场的快照和推荐入口",
                "右侧只保留一个大的展示区，用来支撑进入分析前的判断，不再把说明拆成多张卡片。",
            )

            market_col, refresh_col = st.columns([1.0, 0.34], gap="small")
            with market_col:
                _render_section_header(
                    "市场快照",
                    "先看大盘快照，再往下进入推荐股票和分析入口。",
                )
            with refresh_col:
                refresh_context = st.button(
                    "刷新市场快照",
                    key="single_entry_refresh_market_context",
                    use_container_width=False,
                )

            try:
                context = get_market_context_snapshot(market, force_refresh=refresh_context)
            except Exception as exc:
                context = {
                    "indices": [],
                    "recommendation_source": "市场快照暂不可用",
                    "recommendations": [],
                }
                render_status_note(f"市场快照加载失败：{exc}", tone="warning")

            _render_snapshot(context["indices"])
            st.markdown(
                f"<p class='source-note'>当前推荐口径：<strong>{html.escape(context['recommendation_source'])}</strong></p>",
                unsafe_allow_html=True,
            )

            with st.container(key="single-recommend-sheet"):
                _render_section_header(
                    "推荐股票",
                    "推荐列表放在同一个轻量 sheet 里，点击右侧小按钮即可直接进入分析。",
                )
                recommendation_action = _render_recommendation_rows(context["recommendations"], market=market)
                if recommendation_action is not None:
                    selected_action = recommendation_action

    return selected_action
