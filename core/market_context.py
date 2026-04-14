"""
市场上下文数据层
================
为首页和入口页提供：
- 大盘指数快照
- 推荐股票列表
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time
from typing import Any

import akshare as ak
import pandas as pd
import requests
from requests.exceptions import ProxyError, RequestException, Timeout
import streamlit as st

from core.config import DEFAULT_A_STOCKS, DEFAULT_STOCKS
from core.data import get_stock_label_map


A_INDEX_CONFIG = [
    {"symbol": "sh000001", "label": "上证指数", "aliases": {"000001", "sh000001", "上证指数"}},
    {"symbol": "sz399001", "label": "深证成指", "aliases": {"399001", "sz399001", "深证成指"}},
    {"symbol": "sz399006", "label": "创业板指", "aliases": {"399006", "sz399006", "创业板指"}},
]

US_INDEX_CONFIG = [
    {"symbol": "DJIA", "label": "道琼斯", "aliases": {"DJIA", "道琼斯"}},
    {"symbol": "NDX", "label": "纳斯达克", "aliases": {"NDX", "纳斯达克"}},
    {"symbol": "SPX", "label": "标普 500", "aliases": {"SPX", "标普500", "标普 500"}},
]

US_FAMOUS_CATEGORY_CONFIG = (
    "科技类",
    "金融类",
    "医药食品类",
    "媒体类",
    "汽车能源类",
    "制造零售类",
)

DEFAULT_RECOMMENDATION_LABEL = "实时涨幅前十"
MARKET_CONTEXT_SESSION_KEY = "market_context_snapshot_cache"
MARKET_CONTEXT_SESSION_TTL_SECONDS = 900
MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS = 3.0


def _coerce_float(value: Any) -> float | None:
    """尽量把不同格式的数值转换为 float。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_market_call(loader, *, timeout_seconds: float = MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS) -> Any:
    """统一捕获 AkShare 网络异常。"""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(loader)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        return None
    except (Timeout, ProxyError, RequestException, ValueError):
        return None
    except Exception:
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """在 DataFrame 中寻找第一个存在的候选列。"""
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _empty_index_snapshot(configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": config["symbol"],
            "label": config["label"],
            "close": None,
            "pct_change": None,
        }
        for config in configs
    ]


def _normalize_index_snapshot(df: pd.DataFrame | None, configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把不同来源的指数快照统一成页面所需结构。"""
    if df is None or df.empty:
        return _empty_index_snapshot(configs)

    code_col = _pick_column(df, ["代码", "symbol", "Symbol"])
    name_col = _pick_column(df, ["名称", "name", "Name"])
    close_col = _pick_column(df, ["最新价", "close", "Close"])
    pct_col = _pick_column(df, ["涨跌幅", "涨跌幅%", "pct_change", "Change%"])
    if code_col is None and name_col is None:
        return _empty_index_snapshot(configs)

    code_series = df[code_col].astype(str).str.strip() if code_col is not None else pd.Series("", index=df.index, dtype=str)
    name_series = df[name_col].astype(str).str.strip() if name_col is not None else pd.Series("", index=df.index, dtype=str)
    rows: list[dict[str, Any]] = []
    for config in configs:
        aliases = {str(item).strip() for item in config.get("aliases", set()) if str(item).strip()}
        aliases.add(str(config["symbol"]).strip())
        aliases.add(str(config["label"]).strip())
        matched = df[code_series.isin(aliases) | name_series.isin(aliases)]
        if matched.empty:
            rows.append(
                {
                    "symbol": config["symbol"],
                    "label": config["label"],
                    "close": None,
                    "pct_change": None,
                }
            )
            continue

        row = matched.iloc[0]
        rows.append(
            {
                "symbol": config["symbol"],
                "label": config["label"],
                "close": _coerce_float(row[close_col]) if close_col is not None else None,
                "pct_change": _coerce_float(row[pct_col]) if pct_col is not None else None,
            }
        )
    return rows


def _normalize_recommendation_table(df: pd.DataFrame, market: str, limit: int) -> list[dict[str, Any]]:
    """统一实时行情表字段。"""
    if df is None or df.empty:
        return []

    symbol_col = _pick_column(df, ["代码", "symbol", "Symbol", "代码/Code"])
    name_col = _pick_column(df, ["名称", "name", "Name"])
    price_col = _pick_column(df, ["最新价", "最新", "现价", "price", "Price"])
    pct_col = _pick_column(df, ["涨跌幅", "涨跌幅%", "涨幅", "pct_change", "Change%"])

    if symbol_col is None:
        return []

    prepared = pd.DataFrame(
        {
            "symbol": df[symbol_col].astype(str).str.strip(),
            "name": (
                df[name_col].astype(str).str.strip()
                if name_col is not None
                else df[symbol_col].astype(str).str.strip()
            ),
            "price": df[price_col] if price_col is not None else None,
            "pct_change": df[pct_col] if pct_col is not None else None,
        }
    )

    if market == "A":
        prepared["symbol"] = prepared["symbol"].str.extract(r"(\d+)")[0].fillna("").str.zfill(6).str[-6:]
    else:
        prepared["symbol"] = (
            prepared["symbol"]
            .str.replace(r"^\d+\.", "", regex=True)
            .str.upper()
        )

    prepared["price"] = prepared["price"].map(_coerce_float)
    prepared["pct_change"] = prepared["pct_change"].map(_coerce_float)
    prepared = prepared[(prepared["symbol"] != "") & prepared["pct_change"].notna()].copy()
    prepared = prepared.sort_values("pct_change", ascending=False).head(limit).reset_index(drop=True)
    prepared["label"] = prepared["symbol"] + " " + prepared["name"]
    return prepared.to_dict("records")


def _fallback_recommendations(market: str, limit: int) -> list[dict[str, Any]]:
    """在实时推荐不可用时，回退到默认股票池。"""
    default_symbols = DEFAULT_A_STOCKS if market == "A" else DEFAULT_STOCKS
    symbols = default_symbols[:limit]
    try:
        label_map = get_stock_label_map(symbols, market=market)
    except Exception:
        label_map = {symbol: symbol for symbol in symbols}
    recommendations = []
    for symbol in symbols:
        label = label_map.get(symbol, symbol)
        if " " in label:
            _, name = label.split(" ", 1)
        else:
            name = symbol
        recommendations.append(
            {
                "symbol": symbol,
                "name": name,
                "label": label,
                "price": None,
                "pct_change": None,
            }
        )
    return recommendations


@st.cache_data(show_spinner=False, ttl=900)
def get_market_indices(market: str) -> list[dict[str, Any]]:
    """获取入口页右侧的大盘指数快照。"""
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
    if market_key == "US":
        snapshot_df = _safe_market_call(ak.index_global_spot_em)
        return _normalize_index_snapshot(snapshot_df, US_INDEX_CONFIG)

    snapshot_df = _safe_market_call(ak.stock_zh_index_spot_sina)
    return _normalize_index_snapshot(snapshot_df, A_INDEX_CONFIG)


def _load_us_famous_recommendations(limit: int) -> list[dict[str, Any]]:
    """从知名美股分组里拼出一份轻量推荐池，再按涨跌幅排序。"""
    executor = ThreadPoolExecutor(max_workers=len(US_FAMOUS_CATEGORY_CONFIG))
    future_map = {
        executor.submit(ak.stock_us_famous_spot_em, category): category
        for category in US_FAMOUS_CATEGORY_CONFIG
    }
    frames: list[pd.DataFrame] = []
    try:
        for future in future_map:
            try:
                df = future.result(timeout=MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS)
            except (FuturesTimeoutError, Timeout, ProxyError, RequestException, ValueError):
                continue
            except Exception:
                continue
            if df is not None and not df.empty:
                frames.append(df)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if not frames:
        return []
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["代码", "名称"], keep="first").reset_index(drop=True)
    return _normalize_recommendation_table(combined, "US", limit)


def _load_a_top_movers(limit: int) -> list[dict[str, Any]]:
    """直接请求 A 股涨幅榜首页，避免为入口页推荐区拉取整张市场表。"""
    url = "https://82.push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": str(max(int(limit), 10)),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": "f2,f3,f4,f12,f14",
    }
    try:
        response = requests.get(url, params=params, timeout=MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS)
        data_json = response.json()
    except (Timeout, ProxyError, RequestException, ValueError):
        return []
    except Exception:
        return []

    records = data_json.get("data", {}).get("diff") or []
    if not records:
        return []

    df = pd.DataFrame(records).rename(
        columns={
            "f12": "代码",
            "f14": "名称",
            "f2": "最新价",
            "f3": "涨跌幅",
            "f4": "涨跌额",
        }
    )
    return _normalize_recommendation_table(df, "A", limit)


@st.cache_data(show_spinner=False, ttl=900)
def get_recommended_stocks(market: str, limit: int = 10) -> dict[str, Any]:
    """获取推荐股票，优先使用实时涨幅榜，失败时回退默认列表。"""
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
    if market_key == "A":
        recommendations = _load_a_top_movers(limit)
        if recommendations:
            return {
                "source_label": DEFAULT_RECOMMENDATION_LABEL,
                "items": recommendations,
            }
    else:
        recommendations = _load_us_famous_recommendations(limit)
        if recommendations:
            return {
                "source_label": "知名美股实时涨幅前十",
                "items": recommendations,
            }

    return {
        "source_label": "默认股票池兜底",
        "items": _fallback_recommendations(market_key, limit),
    }


def _format_index_value(value: float | None, digits: int = 2) -> str:
    """格式化指数或价格。"""
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}"


def _format_pct_change(value: float | None) -> str:
    """格式化涨跌幅。"""
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def build_market_context(market: str, limit: int = 10) -> dict[str, Any]:
    """构建入口页所需的大盘和推荐股票上下文。

    指数快照和推荐股票通过线程池并行获取，将冷启动延迟从
    ~12 s（串行 2×6 s）降至 ~3 s（并行 1×3 s 超时）。
    """
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"

    # ── 并行获取指数 + 推荐 ──
    indices: list[dict[str, Any]] = []
    recommendations: dict[str, Any] = {
        "source_label": "默认股票池兜底",
        "items": _fallback_recommendations(market_key, limit),
    }

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        future_indices = executor.submit(get_market_indices, market_key)
        future_recs = executor.submit(get_recommended_stocks, market_key, limit)

        try:
            indices = future_indices.result(timeout=MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS + 1)
        except Exception:
            indices = []

        try:
            recommendations = future_recs.result(timeout=MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS + 1)
        except Exception:
            pass  # keep fallback
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    for item in indices:
        item["close_text"] = _format_index_value(item.get("close"))
        item["pct_text"] = _format_pct_change(item.get("pct_change"))
        item["is_positive"] = (item.get("pct_change") or 0) >= 0 if item.get("pct_change") is not None else None

    for item in recommendations["items"]:
        item["price_text"] = _format_index_value(item.get("price"))
        item["pct_text"] = _format_pct_change(item.get("pct_change"))
        item["is_positive"] = (item.get("pct_change") or 0) >= 0 if item.get("pct_change") is not None else None

    return {
        "market": market_key,
        "indices": indices,
        "recommendation_source": recommendations["source_label"],
        "recommendations": recommendations["items"],
    }


def get_market_context_snapshot(
    market: str,
    limit: int = 10,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """优先读取会话级快照，避免入口页任意交互都重复刷新右侧市场数据。"""
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
    cache = st.session_state.setdefault(MARKET_CONTEXT_SESSION_KEY, {})
    cache_key = f"{market_key}:{int(limit)}"
    now = time.time()

    cached_entry = cache.get(cache_key)
    if (
        not force_refresh
        and isinstance(cached_entry, dict)
        and isinstance(cached_entry.get("payload"), dict)
        and now - float(cached_entry.get("timestamp", 0.0)) < MARKET_CONTEXT_SESSION_TTL_SECONDS
    ):
        return cached_entry["payload"]

    payload = build_market_context(market_key, limit=limit)
    cache[cache_key] = {
        "timestamp": now,
        "payload": payload,
    }
    st.session_state[MARKET_CONTEXT_SESSION_KEY] = cache
    return payload
