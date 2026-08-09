"""
市场上下文数据层
================
为首页和入口页提供：
- 大盘指数快照
- 推荐股票列表
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, wait
from datetime import datetime
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.exceptions import ProxyError, RequestException, Timeout
import streamlit as st

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
BAIDU_HOT_SEARCH_URL = "https://finance.pae.baidu.com/selfselect/listsugrecomm"
BAIDU_HOT_SEARCH_TIMEZONE = ZoneInfo("Asia/Shanghai")
RECOMMENDATION_SOURCE_HOT_SEARCH = "baidu_hot_search_today"
RECOMMENDATION_SOURCE_A_MOVERS = "a_realtime_top_movers"
RECOMMENDATION_SOURCE_US_MOVERS = "us_famous_realtime_top_movers"
RECOMMENDATION_SOURCE_UNAVAILABLE = "unavailable"
RECOMMENDATION_SOURCE_I18N_KEYS = {
    RECOMMENDATION_SOURCE_HOT_SEARCH: "recommendation.source.hotSearchToday",
    RECOMMENDATION_SOURCE_A_MOVERS: "recommendation.source.aRealtimeMovers",
    RECOMMENDATION_SOURCE_US_MOVERS: "recommendation.source.usRealtimeMovers",
    RECOMMENDATION_SOURCE_UNAVAILABLE: "recommendation.source.unavailable",
}
MARKET_CONTEXT_SESSION_KEY = "market_context_snapshot_cache"
MARKET_CONTEXT_SESSION_TTL_SECONDS = 900
MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS = 3.0
RECOMMENDATION_TOTAL_DEADLINE_SECONDS = 3.0
HTTP_CONNECT_READ_TIMEOUT = (1.0, 2.0)


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


def _load_akshare() -> Any | None:
    try:
        import akshare as ak
    except ImportError:
        return None
    return ak


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


def _fetch_us_indices_direct() -> pd.DataFrame | None:
    """直接调用腾讯财经 API 获取美股三大指数（DJIA/Nasdaq/SPX）。

    腾讯财经接口在大陆服务器上稳定可用，作为 ak.index_global_spot_em() 的备用。
    返回与 _normalize_index_snapshot 兼容的 DataFrame（含 代码/名称/最新价/涨跌幅 列）。
    腾讯 symbol: usDJI=道琼斯, usIXIC=纳斯达克, usINX=标普500
    """
    TENCENT_SYMBOLS = [
        ("usDJI", "DJIA"),
        ("usIXIC", "NDX"),
        ("usINX", "SPX"),
    ]
    try:
        sym_str = ",".join(s for s, _ in TENCENT_SYMBOLS)
        url = f"https://qt.gtimg.cn/q={sym_str}"
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
            timeout=HTTP_CONNECT_READ_TIMEOUT,
        )
        resp.raise_for_status()
        rows: list[dict] = []
        for line in resp.text.strip().splitlines():
            # 格式: v_usXXX="200~名称~代码~最新价~...~涨跌额~涨跌幅~..."
            if "=" not in line or '"' not in line:
                continue
            key_part = line.split("=", 1)[0].strip()  # e.g. v_usDJI
            val_part = line.split('"', 1)[1].rstrip('";')
            fields = val_part.split("~")
            if len(fields) < 33 or fields[0] != "200":
                continue
            tencent_key = key_part.replace("v_", "")  # usDJI
            symbol = next((code for sym, code in TENCENT_SYMBOLS if sym == tencent_key), tencent_key)
            try:
                price = float(fields[3])
                pct = float(fields[32])
            except (ValueError, IndexError):
                continue
            rows.append({"代码": symbol, "名称": fields[1], "最新价": price, "涨跌幅": pct})
        return pd.DataFrame(rows) if rows else None
    except Exception:
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
    prepared["rank"] = prepared.index + 1
    prepared["label"] = prepared["symbol"] + " " + prepared["name"]
    return prepared.to_dict("records")


def _load_baidu_hot_search_recommendations(market: str, limit: int) -> list[dict[str, Any]]:
    """读取百度股市通今日热搜，并保留 AkShare 包装层未暴露的股票代码。"""
    normalized_limit = max(int(limit), 0)
    if normalized_limit == 0:
        return []

    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
    now = datetime.now(BAIDU_HOT_SEARCH_TIMEZONE)
    params = {
        "bizType": "wisexmlnew",
        "dsp": "iphone",
        "product": "search",
        "style": "tablelist",
        "market": "ab" if market_key == "A" else "us",
        "type": "今日",
        "day": now.strftime("%Y%m%d"),
        "hour": str(now.hour),
        "pn": "0",
        "rn": str(max(normalized_limit, 12)),
        "finClientType": "pc",
    }
    try:
        response = requests.get(
            BAIDU_HOT_SEARCH_URL,
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=HTTP_CONNECT_READ_TIMEOUT,
        )
        response.raise_for_status()
        data_json = response.json()
        records = data_json.get("Result", {}).get("list", {}).get("body") or []
    except (Timeout, ProxyError, RequestException, ValueError, AttributeError, TypeError):
        return []
    except Exception:
        return []

    recommendations: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_symbol = str(record.get("code") or "").strip().upper()
        if market_key == "A":
            digits = "".join(character for character in raw_symbol if character.isdigit())
            symbol = digits.zfill(6)[-6:] if digits else ""
        else:
            symbol = raw_symbol
        heat = _coerce_float(record.get("heat"))
        if not symbol or heat is None or pd.isna(heat):
            continue
        name = str(record.get("name") or symbol).strip() or symbol
        recommendations.append(
            {
                "symbol": symbol,
                "name": name,
                "label": f"{symbol} {name}",
                "price": None,
                "pct_change": _coerce_float(record.get("pxChangeRate")),
                "heat": int(heat) if float(heat).is_integer() else float(heat),
            }
        )

    recommendations.sort(key=lambda item: float(item["heat"]), reverse=True)
    limited = recommendations[:normalized_limit]
    for rank, item in enumerate(limited, start=1):
        item["rank"] = rank
    return limited


@st.cache_data(show_spinner=False, ttl=900)
def get_market_indices(market: str) -> list[dict[str, Any]]:
    """获取入口页右侧的大盘指数快照。"""
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
    if market_key == "US":
        snapshot_df = _fetch_us_indices_direct()
        if snapshot_df is None or snapshot_df.empty:
            ak = _load_akshare()
            snapshot_df = _safe_market_call(ak.index_global_spot_em) if ak is not None else None
        return _normalize_index_snapshot(snapshot_df, US_INDEX_CONFIG)

    ak = _load_akshare()
    snapshot_df = _safe_market_call(ak.stock_zh_index_spot_sina) if ak is not None else None
    return _normalize_index_snapshot(snapshot_df, A_INDEX_CONFIG)


def _load_us_famous_recommendations(limit: int) -> list[dict[str, Any]]:
    """从知名美股分组里拼出一份轻量推荐池，再按涨跌幅排序。"""
    ak = _load_akshare()
    if ak is None:
        return []

    executor = ThreadPoolExecutor(max_workers=len(US_FAMOUS_CATEGORY_CONFIG))
    future_map = {
        executor.submit(ak.stock_us_famous_spot_em, category): category
        for category in US_FAMOUS_CATEGORY_CONFIG
    }
    frames: list[pd.DataFrame] = []
    try:
        done, _pending = wait(
            future_map,
            timeout=RECOMMENDATION_TOTAL_DEADLINE_SECONDS,
        )
        for future in done:
            try:
                df = future.result()
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
        response = requests.get(url, params=params, timeout=HTTP_CONNECT_READ_TIMEOUT)
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
    """获取推荐股票，优先使用今日热搜，失败时回退实时涨幅榜。"""
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
    recommendations = _load_baidu_hot_search_recommendations(market_key, limit)
    if recommendations:
        return {
            "source_kind": RECOMMENDATION_SOURCE_HOT_SEARCH,
            "source_label": "今日热搜综合热度",
            "items": recommendations,
        }

    if market_key == "A":
        recommendations = _load_a_top_movers(limit)
        if recommendations:
            return {
                "source_kind": RECOMMENDATION_SOURCE_A_MOVERS,
                "source_label": DEFAULT_RECOMMENDATION_LABEL,
                "items": recommendations,
            }
    else:
        recommendations = _load_us_famous_recommendations(limit)
        if recommendations:
            return {
                "source_kind": RECOMMENDATION_SOURCE_US_MOVERS,
                "source_label": "知名美股实时涨幅前十",
                "items": recommendations,
            }

    return {
        "source_kind": RECOMMENDATION_SOURCE_UNAVAILABLE,
        "source_label": "暂时无法获取推荐股票",
        "items": [],
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


def _format_heat(value: float | int | None) -> str | None:
    """格式化热搜综合热度；实时涨幅榜没有该字段。"""
    if value is None or pd.isna(value):
        return None
    return f"{float(value):,.0f}"


def build_market_context(market: str, limit: int = 10) -> dict[str, Any]:
    """构建入口页所需的大盘和推荐股票上下文。

    指数快照和推荐股票通过线程池并行获取，将冷启动延迟从
    ~12 s（串行 2×6 s）降至 ~3 s（并行 1×3 s 超时）。
    """
    market_key = "A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"

    # ── 并行获取指数 + 推荐 ──
    indices: list[dict[str, Any]] = []
    recommendations: dict[str, Any] = {
        "source_kind": RECOMMENDATION_SOURCE_UNAVAILABLE,
        "source_label": "暂时无法获取推荐股票",
        "items": [],
    }

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        future_indices = executor.submit(get_market_indices, market_key)
        future_recs = executor.submit(get_recommended_stocks, market_key, limit)
        done, _pending = wait(
            {future_indices, future_recs},
            timeout=MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS + 1,
        )

        if future_indices in done:
            try:
                indices = future_indices.result()
            except Exception:
                indices = []

        if future_recs in done:
            try:
                recommendations = future_recs.result()
            except Exception:
                pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    for item in indices:
        item["close_text"] = _format_index_value(item.get("close"))
        item["pct_text"] = _format_pct_change(item.get("pct_change"))
        item["is_positive"] = (item.get("pct_change") or 0) >= 0 if item.get("pct_change") is not None else None

    for item in recommendations["items"]:
        item["price_text"] = _format_index_value(item.get("price"))
        item["pct_text"] = _format_pct_change(item.get("pct_change"))
        item["heat_text"] = _format_heat(item.get("heat"))
        item["is_positive"] = (item.get("pct_change") or 0) >= 0 if item.get("pct_change") is not None else None

    return {
        "market": market_key,
        "indices": indices,
        "recommendation_source_kind": recommendations.get("source_kind", RECOMMENDATION_SOURCE_UNAVAILABLE),
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
