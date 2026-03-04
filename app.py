"""
量化交易策略分析应用 — 入口文件
================================
这是一个基于 Streamlit 的 Web 应用，用于分析和回测股票交易策略。
主要功能：
1. 从 AkShare 下载美股数据
2. 计算技术指标（RSI、MACD、EMA、ATR、ADX等）
3. 基于因子评分的量化交易策略
4. 回测策略表现并与买入持有策略对比
5. 多股票对比分析和相关性分析

模块结构：
- core/   : 数据、指标、信号、回测、优化、可视化、组合等核心逻辑
- ui/     : 侧边栏、多股票页、单股票页界面组件
"""

import os

import pandas as pd
import streamlit as st

from core.config import DATA_DIR
from core.data import load_uploaded_bytes
from core.utils import load_or_fetch_stock
from ui.sidebar import render_sidebar
from ui.multi_stock import render_multi_stock_page
from ui.single_stock import render_single_stock_page


# ── 页面配置 ──
st.set_page_config(page_title="策略实验室", layout="wide")
st.title("📊 策略实验室")
st.caption("训练集上绘制蜡烛图与 RSI/MACD，测试集验证策略并对比买入并持有。")

os.makedirs(DATA_DIR, exist_ok=True)

# ── 应用高级搜索结果（需要在 sidebar 渲染之前执行） ──
if st.session_state.get("apply_best_params"):
    best = st.session_state.get("best_params")
    if best:
        st.session_state["adx_threshold"] = int(best["adx_threshold"])
        st.session_state["entry_threshold"] = float(best["entry_threshold"])
        st.session_state["exit_threshold"] = float(best["exit_threshold"])
        st.session_state["stop_loss_mult"] = float(best["stop_loss_mult"])
        st.session_state["take_profit_mult"] = float(best["take_profit_mult"])
        if "weight_bb" in best:
            st.session_state["weight_bb"] = float(best["weight_bb"])
            st.session_state["weight_obv"] = float(best["weight_obv"])
            st.session_state["weight_volume"] = float(best["weight_volume"])
            st.session_state["weight_price"] = float(best["weight_price"])
            st.session_state["weight_drawdown"] = float(best["weight_drawdown"])
        if "ema_fast" in best:
            st.session_state["ema_fast_slider"] = int(best["ema_fast"])
            st.session_state["ema_slow_slider"] = int(best["ema_slow"])
            st.session_state["macd_fast_slider"] = int(best["macd_fast"])
            st.session_state["macd_slow_slider"] = int(best["macd_slow"])
            st.session_state["macd_signal_slider"] = int(best["macd_signal"])
            st.session_state["rsi_period_slider"] = int(best["rsi_period"])
            st.session_state["rsi_lower_slider"] = int(best["rsi_lower"])
            st.session_state["rsi_upper_slider"] = int(best["rsi_upper"])
            st.session_state["adx_period_slider"] = int(best["adx_period"])
            st.session_state["atr_period_slider"] = int(best["atr_period"])
            st.session_state["bb_period_slider"] = int(best["bb_period"])
            st.session_state["bb_std_slider"] = float(best["bb_std"])
            st.session_state["indicator_period_slider"] = int(best["indicator_period"])
        st.session_state["strategy_preset_selector"] = "自定义参数"
    st.session_state["apply_best_params"] = False

# ── 侧边栏 ──
params = render_sidebar()

compare_stocks = params["compare_stocks"]
symbol = params["symbol"]
adjust = params["adjust"]
selected_range = params["selected_range"]
uploaded_file = params["uploaded_file"]

# ── 数据加载 ──
if not compare_stocks:
    st.warning("请在侧边栏选择至少一只股票进行分析。")
    st.stop()

if uploaded_file is not None:
    df_raw = load_uploaded_bytes(uploaded_file.getvalue())
    st.info("已使用上传的数据集。")
else: 
    df_raw = load_or_fetch_stock(symbol, adjust)
    if df_raw is None:
        st.error(f"无法获取 {symbol} 的数据，请检查网络连接。")
        st.stop()

if df_raw.empty:
    st.warning("没有加载到数据。")
    st.stop()

required_cols = {"open", "high", "low", "close"}
missing_cols = required_cols - set(df_raw.columns)
if missing_cols:
    st.error(f"缺少必需列：{', '.join(sorted(missing_cols))}")
    st.stop()

# ── 参数校验 ──
if params["ema_fast"] >= params["ema_slow"]:
    st.sidebar.error("趋势 EMA 快线需要小于慢线。")
    st.stop()
if params["macd_fast"] >= params["macd_slow"]:
    st.sidebar.error("MACD 快线周期需要小于慢线周期。")
    st.stop()
if params["rsi_lower"] >= params["rsi_upper"]:
    st.sidebar.error("RSI 下限需要小于上限。")
    st.stop()
if params["momentum_short"] >= params["momentum_long"]:
    st.sidebar.error("短期动量窗口需要小于中期动量窗口。")
    st.stop()
if params["score_mid_pct"] >= params["score_high_pct"]:
    st.sidebar.error("中档分位数需要小于高档分位数。")
    st.stop()

# ── 日期筛选 ──
is_datetime = pd.api.types.is_datetime64_any_dtype(df_raw["date"])
start_ts = end_ts = None
if is_datetime and isinstance(selected_range, tuple) and len(selected_range) == 2:
    start_ts = pd.Timestamp(selected_range[0])
    end_ts = pd.Timestamp(selected_range[1])
    df_raw = df_raw[(df_raw["date"] >= start_ts) & (df_raw["date"] <= end_ts)]
elif is_datetime and isinstance(selected_range, tuple) and len(selected_range) == 1:
    start_ts = pd.Timestamp(selected_range[0])
    df_raw = df_raw[df_raw["date"] >= start_ts]

if df_raw.empty:
    st.warning("所选时间区间内没有数据。")
    st.stop()

# ── 路由到对应页面 ──
if len(compare_stocks) > 1:
    render_multi_stock_page(params, is_datetime, start_ts, end_ts)
else:
    render_single_stock_page(params, df_raw, symbol)
