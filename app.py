"""
量化交易策略分析应用 — 路由壳层
================================
W6 起改为基于 Streamlit Navigation 的多路由入口：
- /strategy
- /strategy/stock-analysis
- /strategy/stocks-analysis
- /strategy/model-evaluation
"""

from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd
import streamlit as st
from ui.i18n import tr

from core.config import DATA_DIR
from core.data import load_uploaded_bytes
from core.utils import load_or_fetch_stock
from ui.home import render_home_page
from ui.model_evaluation import MODEL_EVALUATION_ROUTE, render_model_evaluation_page
from ui.multi_stock import render_multi_stock_page
from ui.multi_stock_entry import render_multi_stock_entry_page
from ui.sidebar import render_sidebar
from ui.single_stock import render_single_stock_page
from ui.single_stock_entry import render_single_stock_entry_page
from ui.theme import inject_global_styles, render_route_nav


SINGLE_ROUTE_STATE_KEY = "route_single_state"
MULTI_ROUTE_STATE_KEY = "route_multi_state"


st.set_page_config(
    page_title="Strategy Lab",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_global_styles()
os.makedirs(DATA_DIR, exist_ok=True)


def _default_single_route_state() -> dict[str, Any]:
    return {
        "view": "entry",
        "market": "US",
        "symbol": None,
        "uploaded_name": None,
        "uploaded_bytes": None,
        "source": None,
    }


def _default_multi_route_state() -> dict[str, Any]:
    return {
        "view": "entry",
        "market": "US",
        "symbols": [],
        "uploads": [],
    }


def _get_single_route_state() -> dict[str, Any]:
    state = st.session_state.setdefault(SINGLE_ROUTE_STATE_KEY, _default_single_route_state())
    for key, value in _default_single_route_state().items():
        state.setdefault(key, value)
    return state


def _get_multi_route_state() -> dict[str, Any]:
    state = st.session_state.setdefault(MULTI_ROUTE_STATE_KEY, _default_multi_route_state())
    for key, value in _default_multi_route_state().items():
        state.setdefault(key, value)
    return state


def _derive_symbol_from_filename(filename: str | None) -> str:
    stem = os.path.splitext(os.path.basename(str(filename or "")))[0]
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").upper()
    return normalized or "UPLOADED"


def _validate_strategy_params(params: dict) -> str | None:
    if params["ema_fast"] >= params["ema_slow"]:
        return tr("rule.emaFastBelowSlow")
    if params["macd_fast"] >= params["macd_slow"]:
        return tr("indicator.macdValidation")
    if params["rsi_lower"] >= params["rsi_upper"]:
        return tr("validation.rsi_range")
    if params["momentum_short"] >= params["momentum_long"]:
        return tr("validation.momentum_window_order")
    if params["score_mid_pct"] >= params["score_high_pct"]:
        return tr("validation.quantileOrder")
    return None


def _apply_date_filter(df_raw: pd.DataFrame, selected_range) -> tuple[pd.DataFrame, bool, Any, Any]:
    is_datetime = pd.api.types.is_datetime64_any_dtype(df_raw["date"])
    start_ts = end_ts = None

    if is_datetime and isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_ts = pd.Timestamp(selected_range[0])
        end_ts = pd.Timestamp(selected_range[1])
        df_raw = df_raw[(df_raw["date"] >= start_ts) & (df_raw["date"] <= end_ts)]
    elif is_datetime and isinstance(selected_range, tuple) and len(selected_range) == 1:
        start_ts = pd.Timestamp(selected_range[0])
        df_raw = df_raw[df_raw["date"] >= start_ts]

    return df_raw, is_datetime, start_ts, end_ts


def _ensure_valid_dataframe(df_raw: pd.DataFrame, *, empty_message: str) -> bool:
    if df_raw is None:
        return False
    if df_raw.empty:
        st.warning(empty_message)
        return False

    required_cols = {"open", "high", "low", "close"}
    missing_cols = required_cols - set(df_raw.columns)
    if missing_cols:
        st.error(f"缺少必需列：{', '.join(sorted(missing_cols))}")
        return False
    return True


def _single_seed_token(state: dict[str, Any]) -> str:
    if state.get("uploaded_bytes") is not None:
        return f"single-upload::{state.get('uploaded_name')}"
    return f"single-symbol::{state.get('market')}::{state.get('symbol')}"


def _multi_seed_token(state: dict[str, Any]) -> str:
    uploaded_names = ",".join(item.get("symbol", "") for item in state.get("uploads", []))
    selected_symbols = ",".join(state.get("symbols", []))
    return f"multi::{state.get('market')}::{selected_symbols}::{uploaded_names}"


def _render_single_stock_route() -> None:
    state = _get_single_route_state()
    if state["view"] != "analysis":
        render_route_nav("single")
        action = render_single_stock_entry_page(initial_market=state.get("market", "US"))
        if action is not None:
            if action["kind"] == "upload":
                st.session_state[SINGLE_ROUTE_STATE_KEY] = {
                    "view": "analysis",
                    "market": action["market"],
                    "symbol": _derive_symbol_from_filename(action["name"]),
                    "uploaded_name": action["name"],
                    "uploaded_bytes": action["bytes"],
                    "source": action.get("source"),
                }
            else:
                st.session_state[SINGLE_ROUTE_STATE_KEY] = {
                    "view": "analysis",
                    "market": action["market"],
                    "symbol": action["symbol"],
                    "uploaded_name": None,
                    "uploaded_bytes": None,
                    "source": action.get("source"),
                }
            st.rerun()
        return

    render_route_nav("single")

    initial_symbols = [] if state.get("uploaded_bytes") is not None else ([state["symbol"]] if state.get("symbol") else None)
    params = render_sidebar(
        initial_market=state.get("market", "US"),
        initial_symbols=initial_symbols,
        route_seed_token=_single_seed_token(state),
    )

    validation_error = _validate_strategy_params(params)
    if validation_error is not None:
        st.sidebar.error(validation_error)
        return

    uploaded_file = params.get("uploaded_file")
    symbol = state.get("symbol") or params.get("symbol")

    if uploaded_file is not None:
        state["uploaded_name"] = uploaded_file.name
        state["uploaded_bytes"] = uploaded_file.getvalue()
        state["symbol"] = _derive_symbol_from_filename(uploaded_file.name)
        state["source"] = "upload"
        symbol = state["symbol"]

    if state.get("uploaded_bytes") is not None:
        df_raw = load_uploaded_bytes(state["uploaded_bytes"])
        st.info(tr("message.currentUploadedData", name=state.get("uploaded_name")))
    else:
        compare_stocks = params.get("compare_stocks") or ([symbol] if symbol else [])
        if not compare_stocks:
            st.warning(tr("error.no_stocks_to_analyze"))
            return
        if len(compare_stocks) > 1:
            st.info(tr("routing.single_stock_mode_notice"))
        symbol = compare_stocks[0]
        state["symbol"] = symbol
        state["market"] = params.get("market", state.get("market", "US"))
        df_raw = load_or_fetch_stock(symbol, params["adjust"], market=params.get("market", "US"))
        if df_raw is None:
            st.error(tr("message.dataFetchFailed", symbol=symbol))
            return

    if not _ensure_valid_dataframe(df_raw, empty_message=tr("data.loadingFailed")):
        return

    df_raw, _is_datetime, _start_ts, _end_ts = _apply_date_filter(df_raw, params["selected_range"])
    if df_raw.empty:
        st.warning(tr("error.no_data_in_selected_range"))
        return

    params["compare_stocks"] = [symbol] if symbol else []
    params["symbol"] = symbol
    render_single_stock_page(params, df_raw, symbol)


def _build_uploaded_multi_sources(uploads: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    prefetched: dict[str, pd.DataFrame] = {}
    for item in uploads:
        try:
            df = load_uploaded_bytes(item["bytes"])
        except Exception as exc:
            st.warning(tr("message.uploadReadFailed", name=item["name"], error=str(exc)))
            continue
        if df is None or df.empty:
            continue
        prefetched[item["symbol"]] = df
    return prefetched


def _render_multi_stock_route() -> None:
    state = _get_multi_route_state()
    if state["view"] != "analysis":
        render_route_nav("multi")
        action = render_multi_stock_entry_page(initial_market=state.get("market", "US"))
        if action is not None:
            st.session_state[MULTI_ROUTE_STATE_KEY] = {
                "view": "analysis",
                "market": action["market"],
                "symbols": action["symbols"],
                "uploads": action["uploads"],
            }
            st.rerun()
        return

    render_route_nav("multi")

    params = render_sidebar(
        initial_market=state.get("market", "US"),
        initial_symbols=(state.get("symbols", []) if not state.get("uploads") else state.get("symbols", [])),
        route_seed_token=_multi_seed_token(state),
    )

    validation_error = _validate_strategy_params(params)
    if validation_error is not None:
        st.sidebar.error(validation_error)
        return

    prefetched_sources = _build_uploaded_multi_sources(state.get("uploads", []))
    compare_stocks = params.get("compare_stocks") or state.get("symbols", [])
    state["market"] = params.get("market", state.get("market", "US"))
    state["symbols"] = list(compare_stocks)
    total_count = len(compare_stocks) + len(prefetched_sources)
    if total_count < 2:
        st.warning(tr("stockPool.insufficientWarning"))
        return

    params["compare_stocks"] = compare_stocks
    if compare_stocks:
        params["symbol"] = compare_stocks[0]

    dummy_df = pd.DataFrame({"date": pd.to_datetime([])})
    filtered_dummy, is_datetime, start_ts, end_ts = _apply_date_filter(dummy_df, params["selected_range"])
    _ = filtered_dummy
    render_multi_stock_page(
        params,
        is_datetime,
        start_ts,
        end_ts,
        prefetched_stock_data=prefetched_sources,
    )


pages = [
    st.Page(render_home_page, title=tr("nav.home"), icon="🏠", default=True),
    st.Page(_render_single_stock_route, title=tr("navigation.singleStock.entry"), icon="📈", url_path="stock-analysis"),
    st.Page(_render_multi_stock_route, title=tr("navigation.multiStock.entry"), icon="📚", url_path="stocks-analysis"),
    st.Page(render_model_evaluation_page, title=tr("section.model_evaluation"), icon="🧪", url_path=MODEL_EVALUATION_ROUTE),
]

navigation = st.navigation(pages, position="hidden")
navigation.run()
