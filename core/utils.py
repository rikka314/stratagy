"""
辅助工具函数模块
================
格式化、股票数据加载缓存、归一化等工具函数。
"""

import os

import pandas as pd
import streamlit as st

from core.config import DATA_DIR, DEFAULT_STOCKS
from core.data import fetch_data, load_csv


def format_pct(value: float) -> str:
    """格式化百分比显示（如 0.1234 → "12.34%"）"""
    return f"{value * 100:.2f}%"


def load_or_fetch_stock(symbol: str, adjust: str) -> pd.DataFrame:
    """
    加载或下载股票数据，优先使用临时缓存
    
    1. 先尝试从临时目录缓存加载
    2. 缓存不存在则从网络下载并保存
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    data_path = os.path.join(DATA_DIR, f"{symbol.lower()}_daily.csv")
    
    if os.path.exists(data_path):
        try:
            df = load_csv(data_path)
            return df
        except Exception as e:
            st.warning(f"加载缓存数据失败 ({symbol}): {e}，尝试重新下载...")
    
    try:
        with st.spinner(f"正在下载 {symbol} 数据..."):
            df = fetch_data(symbol, adjust)
            df.to_csv(data_path, index=False)
            st.success(f"✓ {symbol} 数据已下载")
        return df
    except Exception as e:
        st.error(f"下载 {symbol} 数据失败: {e}")
        return None


def get_available_stocks() -> list:
    """
    获取可用的股票列表（默认列表 + 用户添加的股票）
    """
    stocks = list(DEFAULT_STOCKS)
    
    if os.path.exists(DATA_DIR):
        files = [f for f in os.listdir(DATA_DIR) if f.endswith('_daily.csv')]
        cached = [f.replace('_daily.csv', '').upper() for f in files]
        for s in cached:
            if s not in stocks:
                stocks.append(s)
    
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
