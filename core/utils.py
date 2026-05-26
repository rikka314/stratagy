"""
辅助工具函数模块
================
格式化、股票数据加载缓存、归一化等工具函数。
"""

import os
import re
import time

import pandas as pd
import streamlit as st

from core.config import DATA_DIR, DEFAULT_A_STOCKS, DEFAULT_STOCKS
from core.data import fetch_a_stock, fetch_data, load_csv


def format_pct(value: float) -> str:
    """格式化百分比显示（如 0.1234 → "12.34%"）"""
    return f"{value * 100:.2f}%"


def _normalize_market(market: str | None) -> str:
    """统一市场代码，兼容后续 UI 使用的 A / US 取值。"""
    market_value = str(market or "US").strip().upper()
    if market_value in {"A", "CN_A", "CN"}:
        return "CN_A"
    return "US"


def _normalize_adjust(adjust: str | None) -> str:
    """统一复权字段，兼容 UI 中的 none 取值。"""
    adjust_value = str(adjust or "none").strip().lower()
    return adjust_value or "none"


def _normalize_symbol(symbol: str | None, market: str) -> str:
    """统一不同市场的股票代码格式。"""
    market_key = _normalize_market(market)
    symbol_value = str(symbol or "").strip()
    if market_key == "US":
        return symbol_value.upper()

    digits = "".join(ch for ch in symbol_value if ch.isdigit())
    if not digits:
        return ""
    return digits.zfill(6)[-6:]


def _cache_matches_request(df: pd.DataFrame, market: str, adjust: str) -> bool:
    """检查缓存中的市场和复权信息是否匹配当前请求。"""
    if df is None or df.empty:
        return False

    if market == "CN_A" and "market" not in df.columns:
        return False

    if "market" in df.columns:
        market_values = df["market"].dropna()
        if market_values.empty:
            return False
        cached_market = str(market_values.iloc[0]).strip().upper()
        if cached_market != market:
            return False

    if "adjust" in df.columns:
        adjust_values = df["adjust"].dropna()
        if adjust_values.empty:
            return False
        cached_adjust = _normalize_adjust(adjust_values.iloc[0])
        if cached_adjust != adjust:
            return False
    elif adjust != "qfq":
        return False

    return True


def load_or_fetch_stock(symbol: str, adjust: str, market: str = "US") -> pd.DataFrame | None:
    """
    加载或下载股票数据，优先使用临时缓存

    1. 先尝试从临时目录缓存加载
    2. 缓存超过 24 小时视为过期，重新下载
    3. 缓存不存在则从网络下载并保存
    """
    CACHE_TTL_SECONDS = 24 * 3600  # 24 小时

    market_key = _normalize_market(market)
    adjust_key = _normalize_adjust(adjust)
    symbol_key = _normalize_symbol(symbol, market_key)

    if market_key == "CN_A" and not re.fullmatch(r"\d{6}", symbol_key):
        st.error("A 股代码无效，请输入 6 位代码或从候选结果中选择。")
        return None

    os.makedirs(DATA_DIR, exist_ok=True)
    data_path = os.path.join(DATA_DIR, f"{symbol_key.lower()}_daily.csv")

    if os.path.exists(data_path):
        file_age = time.time() - os.path.getmtime(data_path)
        if file_age > CACHE_TTL_SECONDS:
            # 缓存过期，删除后重新下载
            try:
                os.remove(data_path)
            except Exception:
                pass
        else:
            try:
                df = load_csv(data_path)
                if _cache_matches_request(df, market_key, adjust_key):
                    return df
                st.info(f"检测到 {symbol_key} 缓存与当前市场或复权方式不一致，重新下载最新数据。")
            except Exception as e:
                st.warning(f"加载缓存数据失败 ({symbol_key}): {e}，尝试重新下载...")

    try:
        with st.spinner(f"正在下载 {symbol_key} 数据..."):
            if market_key == "CN_A":
                df = fetch_a_stock(symbol_key, adjust_key)
            else:
                df = fetch_data(symbol_key, adjust_key)

            if df is None or df.empty:
                return None

            df.to_csv(data_path, index=False)
        return df
    except Exception as e:
        st.error(f"下载 {symbol_key} 数据失败: {e}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def get_available_stocks(market: str = "US") -> list:
    """
    获取可用的股票列表（默认列表 + 用户添加的股票）
    """
    market_key = _normalize_market(market)
    default_stocks = DEFAULT_STOCKS if market_key == "US" else DEFAULT_A_STOCKS
    stocks = list(default_stocks)

    if os.path.exists(DATA_DIR):
        files = [f for f in os.listdir(DATA_DIR) if f.endswith('_daily.csv')]
        for filename in files:
            cache_path = os.path.join(DATA_DIR, filename)
            try:
                cached_head = pd.read_csv(cache_path, nrows=1)
            except Exception:
                continue

            if cached_head.empty:
                continue

            if "market" in cached_head.columns:
                cached_market = _normalize_market(cached_head["market"].iloc[0])
            else:
                cached_market = "US"

            if cached_market != market_key:
                continue

            if "symbol" in cached_head.columns:
                cached_symbol = _normalize_symbol(cached_head["symbol"].iloc[0], market_key)
            else:
                cached_symbol = _normalize_symbol(filename.replace("_daily.csv", ""), market_key)

            if cached_symbol and cached_symbol not in stocks:
                stocks.append(cached_symbol)

    return stocks


def normalize_prices(df_dict: dict) -> pd.DataFrame:
    """
    归一化多个股票的价格到起点=100
    """
    normalized_data = {}

    for symbol, df in df_dict.items():
        if df is not None and not df.empty:
            first_close = df['close'].iloc[0]
            normalized_data[symbol] = (df['close'] / first_close * 100).values

    if not normalized_data:
        return pd.DataFrame()

    base_dates = list(df_dict.values())[0]['date']
    result_df = pd.DataFrame({'date': base_dates})

    for symbol, values in normalized_data.items():
        result_df[symbol] = values

    return result_df
