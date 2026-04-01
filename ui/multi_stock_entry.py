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


def _render_recommendation_rows(recommendations: list[dict[str, Any]]) -> None:
    if not recommendations:
        render_status_note("暂时无法获取推荐股票。", tone="warning")
        return

    with st.container(key="multi-recommend-scroll"):
        for item in recommendations:
            info_col, action_col = st.columns([5.9, 0.95], gap="small")
            info_col.markdown(
                f"<div class='recommend-row'><div class='recommend-row-title'>{html.escape(item['symbol'])} · {html.escape(item['name'])}</div><div class='recommend-row-meta'>现价 {html.escape(item['price_text'])} · 涨跌 {html.escape(item['pct_text'])}</div></div>",
                unsafe_allow_html=True,
            )
            if action_col.button("加入", key=f"multi_entry_rec_{item['symbol']}"):
                _add_symbol_to_selection(item["symbol"])
                st.rerun()


def _render_uploaded_file_rows(uploaded_files) -> None:
    if not uploaded_files:
        st.caption("还没有选择上传文件。")
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
        st.caption("当前还没有已选股票。至少准备 2 个标的后再进入多股分析。")
        return

    with st.container(key="multi-selected-symbols"):
        for symbol in selected_symbols:
            info_col, action_col = st.columns([6.0, 0.95], gap="small")
            info_col.markdown(
                f"<div class='selection-row'><div class='selection-row-title'>{html.escape(symbol)}</div><div class='selection-row-meta'>来源：搜索或推荐加入</div></div>",
                unsafe_allow_html=True,
            )
            if action_col.button("移除", key=f"multi_entry_remove_{symbol}"):
                _remove_symbols_from_selection([symbol])
                st.rerun()


def render_multi_stock_entry_page(initial_market: str = "US") -> dict[str, Any] | None:
    """渲染多股入口页，并在用户发起分析时返回动作。"""
    render_market = "A" if str(initial_market).upper() in {"A", "CN", "CN_A"} else "US"
    if MULTI_ENTRY_MARKET_KEY not in st.session_state:
        st.session_state[MULTI_ENTRY_MARKET_KEY] = render_market
    if MULTI_ENTRY_SELECTED_LIST_KEY not in st.session_state:
        st.session_state[MULTI_ENTRY_SELECTED_LIST_KEY] = []
    if MULTI_ENTRY_LAST_MARKET_KEY not in st.session_state:
        st.session_state[MULTI_ENTRY_LAST_MARKET_KEY] = st.session_state[MULTI_ENTRY_MARKET_KEY]

    render_html(
        """
<section class="entry-intro">
  <div class="page-kicker">Multi Stock Route</div>
  <h1 class="entry-title">先组好股票池，再进入多股分析。</h1>
  <p class="entry-copy">
    左侧负责把待比较股票整理清楚，右侧持续提供当前市场快照和推荐补充入口。
    搜索、上传和推荐最终都会汇到同一个待分析列表。
  </p>
</section>
        """
    )

    selected_action: dict[str, Any] | None = None
    left_col, right_col = st.columns([1.03, 0.97], gap="large")

    with left_col:
        with st.container(key="multi-action-card"):
            _render_surface_header(
                "Action Card",
                "先把股票池整理清楚",
                "市场切换、搜索加入、上传文件和已选股票管理都收进同一张主操作卡，不再拆成多组厚重表单。",
            )

            market = st.segmented_control(
                "研究市场",
                options=["US", "A"],
                format_func=lambda value: "美股" if value == "US" else "A 股",
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
                "搜索并加入股票",
                "支持名称或代码检索。命中索引后加入股票池；没有索引时也支持按代码直接加入。",
            )

            search_query = st.text_input(
                "输入股票名称或代码",
                placeholder="例如：AAPL / NVDA / 贵州茅台 / 600519",
                key=MULTI_ENTRY_QUERY_KEY,
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
                        key=MULTI_ENTRY_SELECTED_SYMBOL_KEY,
                        label_visibility="collapsed",
                    )
                elif market == "A" and search_query.isdigit():
                    st.session_state[MULTI_ENTRY_SELECTED_SYMBOL_KEY] = search_query.zfill(6)[-6:]
                    render_status_note("未找到索引匹配，将按该 A 股代码加入股票池。", tone="info")
                elif market == "US":
                    st.session_state[MULTI_ENTRY_SELECTED_SYMBOL_KEY] = search_query.upper()
                    render_status_note("未找到索引匹配，将按该美股代码加入股票池。", tone="info")
                else:
                    render_status_note("没有找到匹配股票。", tone="warning")
            else:
                st.caption("输入名称或代码后，这里会出现可加入股票池的候选项。")

            if st.button("加入股票池", use_container_width=True):
                selected_symbol = st.session_state.get(MULTI_ENTRY_SELECTED_SYMBOL_KEY)
                if not selected_symbol:
                    render_status_note("请先从搜索结果中选择股票。", tone="warning")
                else:
                    _add_symbol_to_selection(selected_symbol)
                    st.rerun()

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                "上传多个本地 CSV",
                "每个 CSV 会被视为一个独立标的，文件名会自动转换成导入标识。",
            )

            uploaded_files = st.file_uploader(
                "上传多个单股 CSV",
                type=["csv"],
                accept_multiple_files=True,
                key="multi_entry_upload_files",
                help="每个 CSV 视为一只股票，列名需兼容 date/open/high/low/close/volume 标准。",
            )
            _render_uploaded_file_rows(uploaded_files)

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
            _render_section_header(
                "当前已选股票",
                "这里保留待比较股票的轻量行列表。上传文件会在开始分析时一起并入结果。",
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

            if st.button("开始多股分析", type="primary", use_container_width=True):
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
                    render_status_note("多股分析至少需要 2 个标的。可以组合搜索结果与上传文件。", tone="warning")
                else:
                    selected_action = {
                        "kind": "analyze",
                        "market": market,
                        "symbols": list(selected_symbols),
                        "uploads": uploads,
                    }

            render_html(
                """
<p class="plain-helper">
  入口页只负责把股票池整理清楚。进入主分析页后，现有多股图表、组合模拟和后续分析逻辑继续沿用。
</p>
                """
            )

    if selected_action is not None:
        return selected_action

    with right_col:
        with st.container(key="multi-showcase-board"):
            _render_surface_header(
                "Showcase Board",
                "当前市场的快照与推荐补充",
                "右侧保持一个大的上下文展示区，帮助你从搜索之外补充新的比较对象。",
            )
            market_col, refresh_col = st.columns([1.0, 0.34], gap="small")
            with market_col:
                _render_section_header(
                    "市场快照",
                    "先看大盘快照，再往下进入推荐股票和补充股票池。",
                )
            with refresh_col:
                refresh_context = st.button(
                    "刷新市场快照",
                    key="multi_entry_refresh_market_context",
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

            with st.container(key="multi-recommend-sheet"):
                _render_section_header(
                    "推荐股票",
                    "推荐区域保持为单个白色 sheet，内部是轻量行列表和小型加入按钮。",
                )
                _render_recommendation_rows(context["recommendations"])

    return selected_action
