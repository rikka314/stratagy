"""
单股票策略分析页面
==================
选中单只股票时展示的完整策略分析界面，包含：
- 训练/测试集切分
- K线图 + RSI/MACD + 因子评分
- 策略建议
- 高级策略搜索（贝叶斯/遗传/随机）
- 测试集表现
- Walk-Forward 回测
- 交易信号
- HTML 报告导出
"""

import multiprocessing
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.backtest import max_drawdown, sharpe_ratio, simulate_strategy, walk_forward_backtest
from core.indicators import add_indicators
from core.optimizer import (
    bayesian_optimize_params,
    evaluate_presets_for_optimization,
    genetic_algorithm_optimize_params,
    random_search_params,
)
from core.signals import compute_signals
from core.utils import format_pct


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 公共入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def render_single_stock_page(params: dict, df_raw: pd.DataFrame, symbol: str) -> None:
    """
    渲染单股票策略分析页面。

    Parameters
    ----------
    params : dict
        ``render_sidebar()`` 返回的完整参数字典。
    df_raw : pd.DataFrame
        原始 OHLCV 数据（已筛选日期范围）。
    symbol : str
        当前分析的股票代码。
    """
    # ── 展开策略参数 ──
    p = params  # 简写

    # 技术指标参数
    rsi_period = p["rsi_period"]
    macd_fast = p["macd_fast"]
    macd_slow = p["macd_slow"]
    macd_signal = p["macd_signal"]
    ema_fast = p["ema_fast"]
    ema_slow = p["ema_slow"]
    adx_period = p["adx_period"]
    atr_period = p["atr_period"]
    bb_period = p["bb_period"]
    bb_std = p["bb_std"]
    indicator_period = p["indicator_period"]

    # 信号参数
    rsi_lower = p["rsi_lower"]
    rsi_upper = p["rsi_upper"]
    adx_threshold = p["adx_threshold"]
    momentum_short = p["momentum_short"]
    momentum_long = p["momentum_long"]
    score_lookback = p["score_lookback"]
    score_mid_pct = p["score_mid_pct"]
    score_high_pct = p["score_high_pct"]
    entry_threshold = p["entry_threshold"]
    exit_threshold = p["exit_threshold"]

    # 因子权重
    weight_mom_short = p["weight_mom_short"]
    weight_mom_long = p["weight_mom_long"]
    weight_macd = p["weight_macd"]
    weight_rsi = p["weight_rsi"]
    weight_vol = p["weight_vol"]
    weight_bb = p["weight_bb"]
    weight_obv = p["weight_obv"]
    weight_volume = p["weight_volume"]
    weight_price = p["weight_price"]
    weight_drawdown = p["weight_drawdown"]

    # 止损止盈
    stop_loss_mult = p["stop_loss_mult"]
    take_profit_mult = p["take_profit_mult"]

    # 过滤器
    use_trend_filter = p["use_trend_filter"]
    use_strength_filter = p["use_strength_filter"]
    use_rsi_filter = p["use_rsi_filter"]
    use_macd_filter = p["use_macd_filter"]
    use_voting_entry = p["use_voting_entry"]
    entry_vote_threshold = p["entry_vote_threshold"]
    exit_min_signals = p["exit_min_signals"]
    entry_min_signals = p["entry_min_signals"]

    strategy_preset = p["strategy_preset"]

    # ── 计算技术指标与策略信号 ──
    df_indicators = add_indicators(
        df_raw,
        rsi_period=rsi_period,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        adx_period=adx_period,
        atr_period=atr_period,
        bb_period=bb_period,
        bb_std=bb_std,
        indicator_period=indicator_period,
    )
    df = compute_signals(
        df_indicators,
        rsi_lower=rsi_lower,
        rsi_upper=rsi_upper,
        adx_threshold=adx_threshold,
        momentum_short=momentum_short,
        momentum_long=momentum_long,
        score_lookback=score_lookback,
        score_mid_pct=score_mid_pct,
        score_high_pct=score_high_pct,
        weight_mom_short=weight_mom_short,
        weight_mom_long=weight_mom_long,
        weight_macd=weight_macd,
        weight_rsi=weight_rsi,
        weight_vol=weight_vol,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        use_trend_filter=use_trend_filter,
        use_strength_filter=use_strength_filter,
        use_rsi_filter=use_rsi_filter,
        use_macd_filter=use_macd_filter,
        use_voting_entry=use_voting_entry,
        entry_vote_threshold=entry_vote_threshold if use_voting_entry else 2.5,
        exit_min_signals=exit_min_signals,
        entry_min_signals=entry_min_signals,
        weight_bb=weight_bb,
        weight_obv=weight_obv,
        weight_volume=weight_volume,
        weight_price=weight_price,
        weight_drawdown=weight_drawdown,
    )

    # ── 训练集比例 ──
    train_ratio = st.slider(
        "训练集比例",
        min_value=0.6,
        max_value=0.9,
        value=0.7,
        step=0.05,
        help="按时间顺序切分训练/测试集。",
    )

    # ── 训练/测试集切分与回测模拟 ──
    split_idx = int(len(df) * train_ratio)
    train_df = simulate_strategy(
        df.iloc[:split_idx],
        initial_position=0,
        stop_loss_mult=stop_loss_mult,
        take_profit_mult=take_profit_mult,
    )
    test_df = simulate_strategy(
        df.iloc[split_idx:],
        initial_position=0,
        stop_loss_mult=stop_loss_mult,
        take_profit_mult=take_profit_mult,
    )

    # ── 数据集概览 ──
    st.subheader("数据集概览")
    if pd.api.types.is_datetime64_any_dtype(df["date"]):
        date_range = f"{df['date'].min().date()} 到 {df['date'].max().date()}"
    else:
        date_range = "行索引"
    st.write(
        f"行数：{len(df):,} | 训练：{len(train_df):,} | 测试：{len(test_df):,} | "
        f"日期范围：{date_range}"
    )

    # ── 蜡烛图 ──
    candle = _build_candlestick_chart(train_df, symbol)
    st.subheader("训练集：蜡烛图")
    st.plotly_chart(candle, width="stretch")

    # ── RSI + MACD ──
    ind_fig = _build_rsi_macd_chart(train_df, rsi_upper, rsi_lower)
    st.subheader("训练集：RSI + MACD")
    st.plotly_chart(ind_fig, width="stretch")

    # ── 因子评分 ──
    score_fig = _build_factor_score_chart(df)
    st.subheader("因子评分")
    st.plotly_chart(score_fig, width="stretch")

    # ── 策略建议 ──
    suggestion = _render_strategy_suggestion(df, strategy_preset)

    # ── 高级策略搜索 ──
    _render_advanced_search(
        df_raw,
        df_indicators,
        split_idx,
        params,
    )

    # ── 测试集表现 ──
    equity_fig = _render_test_performance(test_df)

    # ── Walk-Forward 回测 ──
    _render_walk_forward(df, stop_loss_mult, take_profit_mult)

    # ── 测试集交易信号 ──
    signal_fig = _render_trade_signals(test_df)

    # ── 导出 HTML 报告 ──
    _render_single_stock_export(
        symbol=symbol,
        df=df,
        test_df=test_df,
        candle=candle,
        ind_fig=ind_fig,
        score_fig=score_fig,
        equity_fig=equity_fig,
        signal_fig=signal_fig,
        suggestion=suggestion,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 图表构建
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_candlestick_chart(train_df: pd.DataFrame, symbol: str) -> go.Figure:
    """构建 K 线图（含成交量子图）。"""
    show_volume = "volume" in train_df.columns and not train_df["volume"].isna().all()

    if show_volume:
        candle = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=[0.75, 0.25],
        )
        candle.add_trace(
            go.Candlestick(
                x=train_df["date"],
                open=train_df["open"],
                high=train_df["high"],
                low=train_df["low"],
                close=train_df["close"],
                name=symbol,
                increasing_line_color="#d62728",
                increasing_fillcolor="#d62728",
                decreasing_line_color="#2ca02c",
                decreasing_fillcolor="#2ca02c",
            ),
            row=1,
            col=1,
        )
        vol_colors = np.where(train_df["close"] >= train_df["open"], "#d62728", "#2ca02c")
        candle.add_trace(
            go.Bar(
                x=train_df["date"],
                y=train_df["volume"],
                marker_color=vol_colors,
                name="成交量",
                opacity=0.6,
            ),
            row=2,
            col=1,
        )
    else:
        candle = go.Figure(
            data=[
                go.Candlestick(
                    x=train_df["date"],
                    open=train_df["open"],
                    high=train_df["high"],
                    low=train_df["low"],
                    close=train_df["close"],
                    name=symbol,
                    increasing_line_color="#d62728",
                    increasing_fillcolor="#d62728",
                    decreasing_line_color="#2ca02c",
                    decreasing_fillcolor="#2ca02c",
                )
            ]
        )

    candle.update_layout(
        height=520,
        xaxis_title="日期",
        yaxis_title="价格",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        hovermode="x unified",
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.08),
            rangeselector=dict(
                buttons=list(
                    [
                        dict(count=1, label="1月", step="month", stepmode="backward"),
                        dict(count=3, label="3月", step="month", stepmode="backward"),
                        dict(count=6, label="6月", step="month", stepmode="backward"),
                        dict(count=1, label="1年", step="year", stepmode="backward"),
                        dict(step="all", label="全部"),
                    ]
                )
            ),
            showgrid=True,
            gridcolor="#e6e6e6",
        ),
        yaxis=dict(showgrid=True, gridcolor="#e6e6e6"),
        showlegend=False,
    )
    if show_volume:
        candle.update_yaxes(title_text="成交量", row=2, col=1, showgrid=True, gridcolor="#f0f0f0")
    else:
        candle.update_yaxes(showgrid=True, gridcolor="#e6e6e6")

    return candle


def _build_rsi_macd_chart(train_df: pd.DataFrame, rsi_upper: float, rsi_lower: float) -> go.Figure:
    """构建 RSI + MACD 指标图。"""
    ind_fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.4, 0.6]
    )
    ind_fig.add_trace(
        go.Scatter(x=train_df["date"], y=train_df["rsi"], name="RSI", line=dict(color="#1f77b4")),
        row=1,
        col=1,
    )
    ind_fig.add_hline(y=rsi_upper, line_dash="dash", line_color="#d62728", row=1, col=1)
    ind_fig.add_hline(y=rsi_lower, line_dash="dash", line_color="#2ca02c", row=1, col=1)
    ind_fig.add_trace(
        go.Scatter(x=train_df["date"], y=train_df["macd"], name="MACD", line=dict(color="#2ca02c")),
        row=2,
        col=1,
    )
    ind_fig.add_trace(
        go.Scatter(x=train_df["date"], y=train_df["signal"], name="Signal", line=dict(color="#ff7f0e")),
        row=2,
        col=1,
    )
    ind_fig.add_trace(
        go.Bar(x=train_df["date"], y=train_df["histogram"], name="Histogram", marker_color="#7f7f7f"),
        row=2,
        col=1,
    )
    ind_fig.update_layout(height=520, xaxis_title="日期")
    return ind_fig


def _build_factor_score_chart(df: pd.DataFrame) -> go.Figure:
    """构建因子评分 + 分位数图。"""
    score_fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4]
    )
    score_fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["factor_score"],
            name="因子评分",
            line=dict(color="#1f77b4"),
        ),
        row=1,
        col=1,
    )
    score_quantiles = df["factor_score"].dropna().quantile([0.2, 0.5, 0.8])
    if not score_quantiles.empty:
        score_fig.add_hline(
            y=float(score_quantiles.loc[0.2]), line_dash="dot", line_color="#2ca02c", row=1, col=1
        )
        score_fig.add_hline(
            y=float(score_quantiles.loc[0.5]), line_dash="dash", line_color="#7f7f7f", row=1, col=1
        )
        score_fig.add_hline(
            y=float(score_quantiles.loc[0.8]), line_dash="dot", line_color="#d62728", row=1, col=1
        )
    score_fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["factor_percentile"] * 100,
            name="评分分位数%",
            line=dict(color="#ff7f0e"),
        ),
        row=2,
        col=1,
    )
    score_fig.update_layout(height=520, xaxis_title="日期")
    return score_fig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 策略建议
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_strategy_suggestion(df: pd.DataFrame, strategy_preset: str) -> str:
    """根据最新因子评分输出策略建议文本，返回 suggestion 用于 HTML 报告。"""
    st.subheader(f"策略建议 —「{strategy_preset}」")
    st.caption("基于当前策略参数的最新信号判断。")

    latest = df.iloc[-1]
    target_pos = float(latest.get("target_position", 0.0))

    if target_pos >= 0.8:
        suggestion = "强势看多/积极持仓"
        reason = "评分位于高分位，趋势与强度过滤通过，MACD 上方且 RSI 在区间内。"
    elif target_pos >= 0.5:
        suggestion = "偏多/可考虑买入"
        reason = "评分位于中高分位，趋势与强度过滤通过。"
    elif target_pos > 0:
        suggestion = "轻仓试探"
        reason = "评分略有优势，但强度不足或条件一般。"
    else:
        suggestion = "观望/降低风险"
        reason = "评分或过滤条件不满足。"

    st.write(f"建议：**{suggestion}**")
    st.caption(reason)
    st.write(f"最新因子评分：{latest['factor_score']:.2f}")
    if not np.isnan(latest.get("factor_percentile", np.nan)):
        st.write(f"最新评分分位数：{latest['factor_percentile'] * 100:.1f}%")
    st.write(f"目标仓位：{target_pos:.1f}")

    return suggestion


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 高级策略搜索
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_advanced_search(
    df_raw: pd.DataFrame,
    df_indicators: pd.DataFrame,
    split_idx: int,
    params: dict,
) -> None:
    """渲染高级策略搜索控件并执行优化。"""
    p = params

    st.markdown("---")
    st.subheader("🔬 高级策略")
    st.caption("使用智能搜索算法自动寻找最优参数组合。内置防过拟合机制（子验证集 + 正则化），结果更可靠。")

    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        optimization_method = st.radio(
            "搜索方法 ⓘ",
            ["贝叶斯优化 (推荐)", "遗传算法", "随机搜索"],
            help=(
                "贝叶斯优化：智能搜索，收敛快，适合优化多个参数\n"
                "遗传算法：模拟生物进化，种群多样性好，不易陷入局部最优\n"
                "随机搜索：简单但效率低\n\n三者均内置防过拟合机制"
            ),
        )

    search_trials = 60
    ga_pop_size = 30
    ga_generations = 20

    with opt_col2:
        if optimization_method == "贝叶斯优化 (推荐)":
            search_trials = st.slider("优化次数", 20, 150, 60, help="贝叶斯优化试验次数，建议 50-100 次。")
        elif optimization_method == "遗传算法":
            ga_col_a, ga_col_b = st.columns(2)
            with ga_col_a:
                ga_pop_size = st.slider(
                    "种群大小", 10, 60, 30, help="每代维持多少个候选参数个体，越大多样性越好但更慢。"
                )
            with ga_col_b:
                ga_generations = st.slider(
                    "进化代数", 5, 40, 20, help="进化迭代多少代，越大搜索越充分。"
                )
        else:
            search_trials = st.slider("搜索次数", 10, 200, 40, help="随机搜索次数，越大越耗时。")

    run_search = st.button("🚀 运行高级策略搜索", type="primary")

    if run_search:
        if split_idx < 50:
            st.warning("训练数据太少，无法进行参数搜索。")
        else:
            _execute_search(
                optimization_method=optimization_method,
                search_trials=search_trials,
                ga_pop_size=ga_pop_size,
                ga_generations=ga_generations,
                df_raw=df_raw,
                df_indicators=df_indicators,
                split_idx=split_idx,
                params=p,
            )

    # ── 搜索结果展示 ──
    _render_search_results()


def _execute_search(
    *,
    optimization_method: str,
    search_trials: int,
    ga_pop_size: int,
    ga_generations: int,
    df_raw: pd.DataFrame,
    df_indicators: pd.DataFrame,
    split_idx: int,
    params: dict,
) -> None:
    """执行策略搜索（贝叶斯/遗传/随机）。"""
    p = params

    # 公共参数
    common_kw = dict(
        momentum_short=p["momentum_short"],
        momentum_long=p["momentum_long"],
        score_lookback=p["score_lookback"],
        score_mid_pct=p["score_mid_pct"],
        score_high_pct=p["score_high_pct"],
        weight_mom_short=p["weight_mom_short"],
        weight_mom_long=p["weight_mom_long"],
        weight_macd=p["weight_macd"],
        weight_rsi=p["weight_rsi"],
        weight_vol=p["weight_vol"],
        use_trend_filter=p["use_trend_filter"],
        use_strength_filter=p["use_strength_filter"],
        use_rsi_filter=p["use_rsi_filter"],
        use_macd_filter=p["use_macd_filter"],
    )

    # 进度条
    progress_bar = st.progress(0)
    progress_text = st.empty()

    def _update_progress(current, total):
        pct = min(current / max(total, 1), 1.0)
        progress_bar.progress(pct)
        progress_text.text(f"搜索进度：{current}/{total}（{pct * 100:.0f}%）")

    # ── 阶段 1：预评估预设策略 ──
    seed_params = None
    _preset_name = "默认"
    if optimization_method != "随机搜索":
        progress_text.text("⚡ 预评估预设策略，选择最佳起点...")
        _preset_best, _preset_name, _preset_scores = evaluate_presets_for_optimization(
            df_raw,
            split_idx=split_idx,
            **common_kw,
        )
        if _preset_best:
            seed_params = _preset_best
            _scores_str = " | ".join([f"{n}: {s:.2f}" for n, s in _preset_scores])
            progress_text.text(f"⚡ 最佳起点：{_preset_name}（{_scores_str}）")

    # ── 阶段 2：正式优化 ──
    if optimization_method == "贝叶斯优化 (推荐)":
        progress_text.text(
            f"正在进行贝叶斯优化（{search_trials} 次试验，从「{_preset_name}」热启动）..."
        )
        best_params = bayesian_optimize_params(
            df_raw,
            split_idx=split_idx,
            n_trials=search_trials,
            progress_callback=_update_progress,
            seed_params=seed_params,
            **common_kw,
        )
    elif optimization_method == "遗传算法":
        progress_text.text(
            f"正在进行遗传算法优化（种群 {ga_pop_size} × {ga_generations} 代，"
            f"从「{_preset_name}」热启动，{multiprocessing.cpu_count()} 核并行）..."
        )
        best_params = genetic_algorithm_optimize_params(
            df_raw,
            split_idx=split_idx,
            population_size=ga_pop_size,
            generations=ga_generations,
            progress_callback=_update_progress,
            seed_params=seed_params,
            **common_kw,
        )
    else:
        progress_text.text(f"正在随机搜索参数（{search_trials} 次）...")
        best_params = random_search_params(
            df_indicators,
            split_idx=split_idx,
            rsi_lower=p["rsi_lower"],
            rsi_upper=p["rsi_upper"],
            adx_threshold=p["adx_threshold"],
            trials=search_trials,
            progress_callback=_update_progress,
            **common_kw,
        )

    # 清理进度条
    progress_bar.progress(1.0)
    progress_text.empty()

    if best_params:
        st.session_state["best_params"] = best_params
        st.success("✓ 高级策略搜索完成！")
    else:
        st.error("策略搜索失败，请检查数据。")


def _render_search_results() -> None:
    """展示搜索结果及"应用"按钮。"""
    st.subheader("搜索结果")
    best = st.session_state.get("best_params")
    if not best:
        st.info("点击上方「🚀 运行高级策略搜索」按钮开始自动搜索最优参数。")
        return

    # 推断优化方法
    if best.get("_method") == "genetic_algorithm":
        optimization_info = "遗传算法"
    elif "weight_bb" in best:
        optimization_info = "贝叶斯优化"
    else:
        optimization_info = "随机搜索"
    st.write(f"基于**{optimization_info}**的结果（含防过拟合验证）。")

    # 性能指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("综合评分", f"{best['score']:.2f}")
    with col2:
        st.metric("训练集收益", format_pct(best["return"]))
    with col3:
        st.metric("训练集夏普", f"{best['sharpe']:.2f}")
    with col4:
        if "val_sharpe" in best:
            st.metric("验证集夏普", f"{best['val_sharpe']:.2f}")

    # 验证集指标
    if "val_return" in best:
        val_col1, val_col2, val_col3 = st.columns(3)
        with val_col1:
            st.metric("验证集收益", format_pct(best["val_return"]))
        with val_col2:
            if "val_max_drawdown" in best:
                st.metric("验证集回撤", format_pct(best["val_max_drawdown"]))
        with val_col3:
            gap = abs(best["sharpe"] - best.get("val_sharpe", best["sharpe"]))
            gap_label = "✅ 低" if gap < 0.5 else "⚠️ 中" if gap < 1.0 else "🔴 高"
            st.metric("过拟合风险", gap_label, delta=f"夏普差距 {gap:.2f}")

    if "max_drawdown" in best:
        st.write(f"**训练集最大回撤**: {format_pct(best['max_drawdown'])}")

    # 核心参数
    st.markdown("**核心参数**")
    st.write(
        f"ADX 阈值：{best['adx_threshold']:.0f} | "
        f"入场阈值：{best['entry_threshold']:.2f} | "
        f"出场阈值：{best['exit_threshold']:.2f}"
    )
    st.write(
        f"ATR 止损倍数：{best['stop_loss_mult']:.1f} | "
        f"ATR 止盈倍数：{best['take_profit_mult']:.1f}"
    )

    # 技术指标参数
    if "ema_fast" in best:
        with st.expander("📈 技术指标参数（优化结果）", expanded=False):
            st.write(f"EMA 快/慢线: {best['ema_fast']} / {best['ema_slow']}")
            st.write(
                f"MACD 快/慢/信号: {best['macd_fast']} / {best['macd_slow']} / {best['macd_signal']}"
            )
            st.write(
                f"RSI 周期: {best['rsi_period']} | 下限: {best['rsi_lower']:.0f} | 上限: {best['rsi_upper']:.0f}"
            )
            st.write(f"ADX 周期: {best['adx_period']} | ATR 周期: {best['atr_period']}")
            st.write(f"布林带周期: {best['bb_period']} | 标准差: {best['bb_std']:.1f}")
            st.write(f"OBV/成交量/价格周期: {best['indicator_period']}")
            st.caption("💡 这些参数由高级策略自动搜索得出")

    # 新因子权重
    if "weight_bb" in best:
        with st.expander("📊 新因子权重（Phase 1）", expanded=False):
            st.write(f"布林带位置权重: {best['weight_bb']:.2f}")
            st.write(f"OBV 趋势权重: {best['weight_obv']:.2f}")
            st.write(f"成交量比率权重: {best['weight_volume']:.2f}")
            st.write(f"价格位置权重: {best['weight_price']:.2f}")
            st.write(f"回撤惩罚权重: {best['weight_drawdown']:.2f}")
            st.caption("💡 这些权重由高级策略自动搜索得出")

    # 应用按钮
    apply_params = st.button(
        "📥 应用搜索结果到当前策略",
        key="apply_params_main",
        help="将搜索到的最优参数写入侧边栏，策略选择将自动切换为「自定义参数」。",
        type="primary",
    )
    if apply_params:
        st.session_state["apply_best_params"] = True
        st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试集 + Walk-Forward + 信号
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_test_performance(test_df: pd.DataFrame) -> go.Figure:
    """渲染测试集表现，返回 equity_fig 供 HTML 导出。"""
    st.subheader("测试集表现")
    strategy_return = test_df["strategy_equity"].iloc[-1] - 1
    buy_hold_return = test_df["buy_hold_equity"].iloc[-1] - 1
    st.write(
        f"策略收益：{format_pct(strategy_return)} | "
        f"买入并持有收益：{format_pct(buy_hold_return)} | "
        f"最大回撤：{format_pct(max_drawdown(test_df['strategy_equity']))} | "
        f"夏普比率：{sharpe_ratio(test_df['strategy_return']):.2f}"
    )

    equity_fig = go.Figure()
    equity_fig.add_trace(
        go.Scatter(
            x=test_df["date"],
            y=test_df["strategy_equity"],
            name="Strategy",
            line=dict(color="#17becf"),
        )
    )
    equity_fig.add_trace(
        go.Scatter(
            x=test_df["date"],
            y=test_df["buy_hold_equity"],
            name="Buy & Hold",
            line=dict(color="#bcbd22"),
        )
    )
    equity_fig.update_layout(height=420, xaxis_title="日期", yaxis_title="净值（起始=1.0）")
    st.plotly_chart(equity_fig, width="stretch")
    return equity_fig


def _render_walk_forward(df: pd.DataFrame, stop_loss_mult: float, take_profit_mult: float) -> None:
    """渲染 Walk-Forward 回测区域。"""
    st.markdown("---")
    st.subheader("Walk-Forward 回测")

    enable_walk = st.checkbox("启用 Walk-Forward", value=True)
    if not enable_walk:
        st.info("已关闭 Walk-Forward 回测。")
        return

    max_window = max(5, len(df) - 1)
    min_train = min(20, max_window)
    min_test = min(5, max_window)

    if max_window <= min_train:
        st.info("数据量较少，已固定训练/测试窗口。")
        train_window = max_window
        test_window = max_window
    else:
        wf_col1, wf_col2 = st.columns(2)
        with wf_col1:
            train_window = st.slider(
                "训练窗口（交易日）",
                min_train,
                max_window,
                min(252, max_window),
                help="每次用训练窗口后接测试窗口滚动回测。",
            )
        with wf_col2:
            test_window = st.slider(
                "测试窗口（交易日）",
                min_test,
                max_window,
                min(63, max_window),
                help="每次滚动的测试区间长度。",
            )

    if train_window + test_window > len(df):
        st.warning("训练窗口 + 测试窗口超过数据长度，请调小窗口。")
        return

    wf_results, wf_equity = walk_forward_backtest(
        df,
        train_window=train_window,
        test_window=test_window,
        stop_loss_mult=stop_loss_mult,
        take_profit_mult=take_profit_mult,
    )
    if wf_equity.empty:
        st.warning("Walk-Forward 回测未产生结果。")
        return

    wf_return = wf_equity["strategy_equity"].iloc[-1] - 1
    wf_bh_return = wf_equity["buy_hold_equity"].iloc[-1] - 1
    st.write(
        f"Walk-Forward 策略收益：{format_pct(wf_return)} | "
        f"买入并持有收益：{format_pct(wf_bh_return)}"
    )

    wf_fig = go.Figure()
    wf_fig.add_trace(
        go.Scatter(
            x=wf_equity["date"],
            y=wf_equity["strategy_equity"],
            name="Walk-Forward 策略",
            line=dict(color="#17becf"),
        )
    )
    wf_fig.add_trace(
        go.Scatter(
            x=wf_equity["date"],
            y=wf_equity["buy_hold_equity"],
            name="买入并持有",
            line=dict(color="#bcbd22"),
        )
    )
    wf_fig.update_layout(height=420, xaxis_title="日期", yaxis_title="净值（起始=1.0）")
    st.plotly_chart(wf_fig, width="stretch")

    if not wf_results.empty:
        wf_results_display = wf_results.copy()
        wf_results_display["test_return"] = wf_results_display["test_return"].map(format_pct)
        wf_results_display["test_max_drawdown"] = wf_results_display["test_max_drawdown"].map(format_pct)
        st.dataframe(wf_results_display, width="stretch")


def _render_trade_signals(test_df: pd.DataFrame) -> go.Figure:
    """渲染测试集交易信号图，返回 signal_fig 供 HTML 导出。"""
    st.subheader("测试集交易信号")
    signal_fig = go.Figure(
        data=[
            go.Scatter(
                x=test_df["date"],
                y=test_df["close"],
                mode="lines",
                name="Close",
                line=dict(color="#1f77b4"),
            )
        ]
    )
    signal_fig.add_trace(
        go.Scatter(
            x=test_df.loc[test_df["buy_signal"], "date"],
            y=test_df.loc[test_df["buy_signal"], "close"],
            mode="markers",
            name="Buy",
            marker=dict(color="#2ca02c", size=8, symbol="triangle-up"),
        )
    )
    signal_fig.add_trace(
        go.Scatter(
            x=test_df.loc[test_df["sell_signal"], "date"],
            y=test_df.loc[test_df["sell_signal"], "close"],
            mode="markers",
            name="Sell",
            marker=dict(color="#d62728", size=8, symbol="triangle-down"),
        )
    )
    signal_fig.update_layout(height=420, xaxis_title="日期", yaxis_title="价格")
    st.plotly_chart(signal_fig, width="stretch")
    return signal_fig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTML 报告导出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_single_stock_export(
    *,
    symbol: str,
    df: pd.DataFrame,
    test_df: pd.DataFrame,
    candle: go.Figure,
    ind_fig: go.Figure,
    score_fig: go.Figure,
    equity_fig: go.Figure,
    signal_fig: go.Figure,
    suggestion: str,
) -> None:
    """渲染单股票 HTML 报告导出区域。"""
    st.markdown("---")
    st.subheader("📤 导出分析报告")

    single_col1, single_col2, _single_col3 = st.columns([1, 1, 2])
    with single_col1:
        single_export_title = st.text_input(
            "报告标题", value=f"单股策略分析 - {symbol}", key="single_export_title"
        )
    with single_col2:
        single_include_date = st.checkbox("包含生成日期", value=True, key="single_include_date")

    if not st.button("🎁 生成并下载HTML报告", type="primary", width="stretch", key="single_export_btn"):
        return

    with st.spinner("正在生成HTML报告..."):
        strategy_ret = test_df["strategy_equity"].iloc[-1] - 1
        bh_ret = test_df["buy_hold_equity"].iloc[-1] - 1
        test_sharpe = sharpe_ratio(test_df["strategy_return"])
        test_mdd = max_drawdown(test_df["strategy_equity"])

        html_parts: list[str] = []

        # HTML 头部
        html_parts.append(
            f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{single_export_title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{font-family:'Source Sans Pro','Segoe UI',Tahoma,Geneva,Verdana,sans-serif;margin:0;padding:20px;background:#fafafa;color:#31333f;}}
        .container {{max-width:1200px;margin:0 auto;background:#fff;padding:40px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.1);}}
        h1 {{color:#2c3e50;border-bottom:3px solid #3498db;padding-bottom:10px;margin-bottom:30px;}}
        h2 {{color:#34495e;margin-top:40px;margin-bottom:20px;border-left:4px solid #3498db;padding-left:15px;}}
        .metadata {{background:#ecf0f1;padding:15px;border-radius:5px;margin-bottom:30px;font-size:14px;color:#7f8c8d;}}
        .metrics {{display:flex;justify-content:space-around;margin:30px 0;flex-wrap:wrap;}}
        .metric-card {{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px;border-radius:10px;text-align:center;min-width:180px;margin:10px;box-shadow:0 4px 6px rgba(0,0,0,.1);}}
        .metric-label {{font-size:14px;opacity:.9;margin-bottom:8px;}}
        .metric-value {{font-size:28px;font-weight:700;}}
        .metric-delta {{font-size:16px;margin-top:8px;}}
        .chart-container {{margin:30px 0;background:#fff;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.05);}}
        .info-box {{background:#e8f4f8;border-left:4px solid #3498db;padding:15px;margin:20px 0;border-radius:4px;}}
        .footer {{margin-top:50px;padding-top:20px;border-top:1px solid #ecf0f1;text-align:center;color:#95a5a6;font-size:12px;}}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 {single_export_title}</h1>
"""
        )

        if single_include_date:
            date_min = (
                df["date"].min().date()
                if pd.api.types.is_datetime64_any_dtype(df["date"])
                else "N/A"
            )
            date_max = (
                df["date"].max().date()
                if pd.api.types.is_datetime64_any_dtype(df["date"])
                else "N/A"
            )
            html_parts.append(
                f"""
        <div class="metadata">
            <strong>生成时间：</strong>{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}<br>
            <strong>分析股票：</strong>{symbol}<br>
            <strong>数据来源：</strong>AkShare API<br>
            <strong>数据范围：</strong>{date_min} 至 {date_max}
        </div>
"""
            )

        html_parts.append(
            f"""
        <h2>📈 关键指标</h2>
        <div class="metrics">
            <div class="metric-card"><div class="metric-label">策略收益</div><div class="metric-value">{strategy_ret:.2%}</div></div>
            <div class="metric-card"><div class="metric-label">买入持有收益</div><div class="metric-value">{bh_ret:.2%}</div></div>
            <div class="metric-card"><div class="metric-label">夏普比率</div><div class="metric-value">{test_sharpe:.2f}</div></div>
            <div class="metric-card"><div class="metric-label">最大回撤</div><div class="metric-value">{test_mdd:.2%}</div></div>
            <div class="metric-card"><div class="metric-label">策略建议</div><div class="metric-value">{suggestion}</div></div>
        </div>
"""
        )

        # 图表
        _chart_entries = [
            (candle, "candle-chart", "📊 训练集蜡烛图"),
            (ind_fig, "indicator-chart", "📉 RSI + MACD"),
            (score_fig, "score-chart", "🎯 因子评分"),
            (equity_fig, "equity-chart", "📊 测试集表现"),
            (signal_fig, "signal-chart", "🔔 测试集交易信号"),
        ]
        for fig, div_id, title in _chart_entries:
            var_name = div_id.replace("-", "_")
            html_parts.append(
                f"""
        <h2>{title}</h2>
        <div class="chart-container"><div id="{div_id}"></div></div>
        <script>
            var {var_name} = {fig.to_json()};
            Plotly.newPlot('{div_id}', {var_name}.data, {var_name}.layout, {{responsive: true}});
        </script>
"""
            )

        html_parts.append(
            """
        <div class="footer">
            <p>📊 由策略实验室 Streamlit App 生成</p>
            <p>数据来源：AkShare | 图表技术：Plotly.js</p>
        </div>
    </div>
</body>
</html>
"""
        )

        full_html = "".join(html_parts)

        st.download_button(
            label="⬇️ 下载HTML报告",
            data=full_html,
            file_name=f"strategy_report_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
        st.success("✅ HTML报告已生成！点击上方按钮下载")
