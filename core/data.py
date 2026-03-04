"""
数据预处理模块
==============
股票数据的获取、加载和标准化。
"""

import io
import os

import akshare as ak
import pandas as pd
import streamlit as st

from core.config import DATA_DIR


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化 DataFrame 的列名
    
    功能说明：
    1. 将所有列名转换为小写并去除空格
    2. 统一不同数据源的列名差异（如 trade_date → date, vol → volume）
    """
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    
    rename_map = {}
    if "trade_date" in df.columns and "date" not in df.columns:
        rename_map["trade_date"] = "date"
    if "datetime" in df.columns and "date" not in df.columns:
        rename_map["datetime"] = "date"
    if "vol" in df.columns and "volume" not in df.columns:
        rename_map["vol"] = "volume"
    if "volumn" in df.columns and "volume" not in df.columns:
        rename_map["volumn"] = "volume"
    
    if rename_map:
        df = df.rename(columns=rename_map)
    
    return df


def ensure_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保 DataFrame 有合法的日期列
    """
    df = df.copy()
    
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.sort_values("date")
        return df
    
    df["date"] = pd.RangeIndex(start=1, stop=len(df) + 1, step=1)
    return df


def fetch_data(symbol: str, adjust: str) -> pd.DataFrame:
    """
    从 AkShare 下载美股日线数据
    
    参数：
        symbol: 股票代码（如 'AAPL', 'TSLA'）
        adjust: 复权方式 ('qfq'=前复权, 'hfq'=后复权, 'none'=不复权)
    """
    df = ak.stock_us_daily(symbol=symbol, adjust=adjust)
    df = standardize_columns(df)
    
    if "date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "date"})
    
    df = ensure_date_column(df)
    
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    df = df.dropna(subset=["open", "high", "low", "close"])
    
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_csv(path: str) -> pd.DataFrame:
    """从本地 CSV 文件加载数据（缓存1小时）"""
    df = pd.read_csv(path)
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


@st.cache_data(show_spinner=False)
def load_uploaded_bytes(data: bytes) -> pd.DataFrame:
    """从上传的字节数据加载 CSV"""
    df = pd.read_csv(io.BytesIO(data))
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df
