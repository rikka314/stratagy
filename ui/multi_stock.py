"""
多股票对比分析页面
==================
选中多只股票时展示的完整对比分析界面。
"""

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from core.utils import load_or_fetch_stock
from core.visualization import (
    create_multi_stock_comparison_chart,
    create_correlation_heatmap,
    create_relative_strength_chart,
    create_risk_return_scatter,
    create_periodic_returns_heatmap,
    create_factor_score_comparison,
)
from core.portfolio import run_portfolio_simulation, bayesian_optimize_portfolio


def render_multi_stock_page(params: dict, is_datetime: bool, start_ts, end_ts) -> None:
    """
    渲染多股票对比分析页面。

    Parameters
    ----------
    params : dict
        ``render_sidebar()`` 返回的完整参数字典。
    is_datetime : bool
        df_raw 的 date 列是否为 datetime 类型。
    start_ts, end_ts
        时间筛选的起止 Timestamp。
    """
    compare_stocks = params["compare_stocks"]
    adjust = params["adjust"]

    st.markdown("---")
    st.header("📈 多股票价格对比分析")

    with st.spinner("加载对比股票数据..."):
        stock_data_dict: dict[str, pd.DataFrame] = {}
        for stock_symbol in compare_stocks:
            stock_df = load_or_fetch_stock(stock_symbol, adjust)
            if stock_df is not None and not stock_df.empty:
                if is_datetime and start_ts is not None:
                    stock_df = stock_df[
                        (stock_df["date"] >= start_ts)
                        & (stock_df["date"] <= end_ts)
                    ]
                stock_data_dict[stock_symbol] = stock_df

    # 预初始化图表变量
    risk_return_fig = None
    factor_score_fig = None
    corr_fig = None
    rs_fig = None
    portfolio_result = None
    periodic_heatmap_fig = None
    comparison_stats: list[dict] = []

    if len(stock_data_dict) == 0:
        st.warning("没有加载到有效的股票数据。")
        return

    # ── 归一化价格对比图 ──
    comparison_fig = create_multi_stock_comparison_chart(
        stock_data_dict,
        title=f"多股票价格对比（共 {len(stock_data_dict)} 只）",
    )
    st.plotly_chart(comparison_fig, width="stretch")

    # ── 关键统计 ──
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("对比股票数量", len(stock_data_dict))
    with col2:
        avg_days = int(np.mean([len(df) for df in stock_data_dict.values()]))
        st.metric("平均数据天数", f"{avg_days:,}")
    with col3:
        returns = {}
        for sym, df in stock_data_dict.items():
            if len(df) > 0:
                returns[sym] = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
        if returns:
            best_performer = max(returns, key=returns.get)
            st.metric("最佳表现", f"{best_performer}", f"{returns[best_performer]:.2f}%")

    # ── 详细对比表格 ──
    with st.expander("📊 详细统计对比", expanded=False):
        for sym, df in stock_data_dict.items():
            if len(df) > 0:
                total_return = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
                volatility = df["close"].pct_change().std() * np.sqrt(252) * 100
                comparison_stats.append(
                    {
                        "股票": sym,
                        "起始价格": f"${df['close'].iloc[0]:.2f}",
                        "最新价格": f"${df['close'].iloc[-1]:.2f}",
                        "总收益率": f"{total_return:.2f}%",
                        "年化波动率": f"{volatility:.2f}%",
                        "最高价": f"${df['close'].max():.2f}",
                        "最低价": f"${df['close'].min():.2f}",
                        "数据天数": len(df),
                    }
                )
        if comparison_stats:
            st.dataframe(pd.DataFrame(comparison_stats), width="stretch", hide_index=True)

    # ── 相对强弱对比图 ──
    if len(stock_data_dict) >= 2:
        st.markdown("### 💪 相对强弱对比")
        rs_benchmark_options = ["equal_weight"] + list(stock_data_dict.keys())
        rs_benchmark_choice = st.selectbox(
            "选择基准",
            options=rs_benchmark_options,
            format_func=lambda x: "等权平均" if x == "equal_weight" else x,
            index=0,
            key="rs_benchmark",
        )
        with st.spinner("计算相对强弱..."):
            rs_fig = create_relative_strength_chart(stock_data_dict, benchmark=rs_benchmark_choice)
        if rs_fig:
            st.plotly_chart(rs_fig, width="stretch")
            st.info(
                "💡 **如何阅读此图**：RS曲线**上升**表示该股票正在**跑赢**基准，"
                "**下降**表示正在**跑输**基准。即使股价本身在涨，如果涨幅不如基准，RS也会下降。"
                "动量策略倾向于买入RS上升的股票。"
            )
        else:
            st.warning("⚠️ 数据不足以计算相对强弱")

    # ── 风险收益散点图 ──
    if len(stock_data_dict) >= 2:
        st.markdown("### ⚖️ 风险-收益分析")
        with st.spinner("计算风险收益指标..."):
            risk_return_fig = create_risk_return_scatter(stock_data_dict)
        if risk_return_fig:
            st.plotly_chart(risk_return_fig, width="stretch")
            st.info(
                "💡 **如何阅读此图**：横轴代表风险（波动率），纵轴代表回报（收益率）。"
                "理想的投资标的位于**左上角**（高收益、低风险），应尽量规避位于**右下角**"
                "（低收益、高风险）的标的。虚线代表所选股票的中位数。"
            )
        else:
            st.warning("⚠️ 数据不足以计算风险收益指标")

    # ── 因子评分横向对比 ──
    if len(stock_data_dict) >= 2:
        st.markdown("### 🎯 最新因子评分对比")
        with st.spinner("计算最新因子评分..."):
            factor_score_fig = create_factor_score_comparison(stock_data_dict, **_strategy_params(params))
        if factor_score_fig:
            st.plotly_chart(factor_score_fig, width="stretch")
            st.info(
                "💡 **如何阅读此图**：展示每只股票在**最新一个交易日**的综合因子评分。"
                "柱子越高，说明策略模型认为该股票当前的买入价值越大。颜色代表策略建议的仓位大小。"
            )
        else:
            st.warning("⚠️ 数据不足以计算因子评分")

    # ── 相关性热图 ──
    if len(stock_data_dict) >= 2:
        st.markdown("### 📊 股票相关性分析")
        with st.spinner("计算相关性矩阵..."):
            corr_fig = create_correlation_heatmap(stock_data_dict)
        if corr_fig:
            st.plotly_chart(corr_fig, width="stretch")
        else:
            st.warning("⚠️ 数据不足以计算相关性（需要至少10个共同交易日）")

    # ── 周期收益率热图 ──
    if len(stock_data_dict) >= 1:
        st.markdown("### 📅 周期收益率热图")
        heatmap_period = st.selectbox(
            "选择时间周期",
            options=["M", "Q", "YE"],
            format_func=lambda x: {"M": "月度", "Q": "季度", "YE": "年度"}.get(x, x),
            index=0,
            key="heatmap_period",
        )
        with st.spinner("计算周期收益率..."):
            periodic_heatmap_fig = create_periodic_returns_heatmap(stock_data_dict, period=heatmap_period)
        if periodic_heatmap_fig:
            st.plotly_chart(periodic_heatmap_fig, width="stretch")
            st.info(
                "💡 **如何阅读此图**：绿色表示盈利，红色表示亏损，颜色越深表示幅度越大。"
                "通过观察某只股票在特定月份/季度的表现，可以发现季节性规律或抵御市场下跌的能力。"
            )
        else:
            st.warning("⚠️ 数据不足以生成周期收益率热图")

    # ── 投资组合模拟 ──
    if len(stock_data_dict) >= 2:
        st.markdown("---")
        st.markdown("### 💼 投资组合模拟")

        with st.expander("⚙️ 组合权重设置", expanded=False):
            st.caption("调整各股票在组合中的权重比例，默认等权分配。")
            portfolio_weights: dict[str, float] = {}
            weight_cols = st.columns(min(len(stock_data_dict), 4))
            for i, sym in enumerate(stock_data_dict.keys()):
                with weight_cols[i % len(weight_cols)]:
                    portfolio_weights[sym] = st.number_input(
                        f"{sym} 权重",
                        min_value=0.0,
                        max_value=10.0,
                        value=1.0,
                        step=0.1,
                        key=f"pw_{sym}",
                    )

        with st.spinner("运行组合策略模拟..."):
            portfolio_params = _strategy_params(params)
            portfolio_params["weights"] = portfolio_weights
            portfolio_result = run_portfolio_simulation(stock_data_dict, **portfolio_params)

        if portfolio_result:
            st.plotly_chart(portfolio_result["fig"], width="stretch")

            pcol1, pcol2, pcol3, pcol4, pcol5, pcol6 = st.columns(6)
            with pcol1:
                st.metric("组合总收益", f"{portfolio_result['port_total_return']:.2%}")
            with pcol2:
                st.metric("组合夏普", f"{portfolio_result['port_sharpe']:.2f}")
            with pcol3:
                st.metric("组合最大回撤", f"{portfolio_result['port_max_dd']:.2%}")
            with pcol4:
                st.metric("买入持有收益", f"{portfolio_result['bh_total_return']:.2%}")
            with pcol5:
                st.metric("买入持有夏普", f"{portfolio_result['bh_sharpe']:.2f}")
            with pcol6:
                st.metric("买入持有回撤", f"{portfolio_result['bh_max_dd']:.2%}")

            with st.expander("📋 各股票独立策略表现", expanded=False):
                indiv_stats = []
                for sym, res in portfolio_result["individual_results"].items():
                    indiv_stats.append(
                        {
                            "股票": sym,
                            "权重": f"{portfolio_result['weights'].get(sym, 0):.1%}",
                            "策略收益": f"{res['total_return']:.2%}",
                            "夏普比率": f"{res['sharpe']:.2f}",
                            "最大回撤": f"{res['max_dd']:.2%}",
                        }
                    )
                if indiv_stats:
                    st.dataframe(pd.DataFrame(indiv_stats), width="stretch", hide_index=True)

            st.info(
                "💡 **如何阅读此图**：绿色实线为组合策略净值，红色虚线为等权买入持有基准。"
                "彩色点线为各股票的独立策略净值。组合策略通过分散化通常能降低波动和回撤。"
            )

            # ── 贝叶斯优化组合 ──
            st.markdown("#### 🔬 组合参数优化")
            st.caption("使用贝叶斯优化搜索最优组合参数（统一参数，优化目标为组合整体的夏普+收益-回撤）")

            opt_col1, opt_col2 = st.columns(2)
            with opt_col1:
                portfolio_n_trials = st.slider(
                    "优化试验次数",
                    10,
                    100,
                    30,
                    step=10,
                    key="portfolio_n_trials",
                    help="试验次数越多越精确，但耗时更长。建议 30-50 次。",
                )
            with opt_col2:
                st.markdown("")

            if st.button("🚀 开始优化组合参数", type="primary", key="btn_optimize_portfolio"):
                with st.spinner(f"贝叶斯优化中（{portfolio_n_trials} 次试验）..."):
                    opt_fixed = _strategy_params(params)
                    # 移除 weights — bayesian_optimize_portfolio 不接受 weights
                    opt_fixed.pop("weights", None)
                    opt_fixed.pop("stop_loss_mult", None)
                    opt_fixed.pop("take_profit_mult", None)
                    opt_fixed.pop("entry_threshold", None)
                    opt_fixed.pop("exit_threshold", None)
                    opt_fixed.pop("adx_threshold", None)
                    opt_fixed.pop("weight_bb", None)
                    opt_fixed.pop("weight_obv", None)
                    opt_fixed.pop("weight_volume", None)
                    opt_fixed.pop("weight_price", None)
                    opt_fixed.pop("weight_drawdown", None)
                    opt_result = bayesian_optimize_portfolio(
                        stock_data_dict,
                        n_trials=portfolio_n_trials,
                        **opt_fixed,
                    )

                if opt_result and opt_result.get("score", -np.inf) > -np.inf:
                    st.success("✅ 优化完成！最优组合参数：")

                    res_col1, res_col2, res_col3 = st.columns(3)
                    with res_col1:
                        st.metric(
                            "优化后夏普",
                            f"{opt_result['sharpe']:.2f}",
                            delta=f"{opt_result['sharpe'] - portfolio_result['port_sharpe']:.2f}",
                        )
                    with res_col2:
                        st.metric(
                            "优化后收益",
                            f"{opt_result['return']:.2%}",
                            delta=f"{(opt_result['return'] - portfolio_result['port_total_return']):.2%}",
                        )
                    with res_col3:
                        st.metric(
                            "优化后回撤",
                            f"{opt_result['max_drawdown']:.2%}",
                            delta=f"{(opt_result['max_drawdown'] - portfolio_result['port_max_dd']):.2%}",
                        )

                    with st.expander("📋 最优参数详情", expanded=True):
                        opt_params_display = {
                            "入场阈值": f"{opt_result['entry_threshold']:.2f}",
                            "出场阈值": f"{opt_result['exit_threshold']:.2f}",
                            "ADX阈值": f"{opt_result['adx_threshold']:.1f}",
                            "止损倍数": f"{opt_result['stop_loss_mult']:.2f}",
                            "止盈倍数": f"{opt_result['take_profit_mult']:.2f}",
                            "布林带权重": f"{opt_result['weight_bb']:.2f}",
                            "OBV权重": f"{opt_result['weight_obv']:.2f}",
                            "成交量权重": f"{opt_result['weight_volume']:.2f}",
                            "价格位置权重": f"{opt_result['weight_price']:.2f}",
                            "回撤惩罚权重": f"{opt_result['weight_drawdown']:.2f}",
                        }
                        opt_df = pd.DataFrame(
                            list(opt_params_display.items()),
                            columns=["参数", "最优值"],
                        )
                        st.dataframe(opt_df, width="stretch", hide_index=True)

                    st.markdown("##### 📈 优化后组合表现")
                    with st.spinner("使用最优参数重新模拟..."):
                        opt_sim_params = _strategy_params(params)
                        opt_sim_params.update(
                            entry_threshold=opt_result["entry_threshold"],
                            exit_threshold=opt_result["exit_threshold"],
                            adx_threshold=opt_result["adx_threshold"],
                            stop_loss_mult=opt_result["stop_loss_mult"],
                            take_profit_mult=opt_result["take_profit_mult"],
                            weight_bb=opt_result["weight_bb"],
                            weight_obv=opt_result["weight_obv"],
                            weight_volume=opt_result["weight_volume"],
                            weight_price=opt_result["weight_price"],
                            weight_drawdown=opt_result["weight_drawdown"],
                            weights=portfolio_weights,
                        )
                        opt_portfolio = run_portfolio_simulation(stock_data_dict, **opt_sim_params)

                    if opt_portfolio:
                        st.plotly_chart(opt_portfolio["fig"], width="stretch")
                else:
                    st.warning("⚠️ 优化未找到有效参数，请尝试增加试验次数或调整参数范围。")
        else:
            st.warning("⚠️ 数据不足以运行组合模拟（需要至少2只有效股票）")

    # ── 导出 HTML 报告 ──
    _render_multi_stock_export(
        compare_stocks,
        stock_data_dict,
        comparison_stats,
        rs_fig,
        risk_return_fig,
        factor_score_fig,
        corr_fig,
        periodic_heatmap_fig,
        portfolio_result,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _strategy_params(params: dict) -> dict:
    """从完整 params 中提取策略相关参数子集（去除 UI 状态键）。"""
    _ui_keys = {
        "compare_stocks",
        "symbol",
        "adjust",
        "selected_range",
        "uploaded_file",
        "strategy_preset",
    }
    return {k: v for k, v in params.items() if k not in _ui_keys}


def _render_multi_stock_export(
    compare_stocks,
    stock_data_dict,
    comparison_stats,
    rs_fig,
    risk_return_fig,
    factor_score_fig,
    corr_fig,
    periodic_heatmap_fig,
    portfolio_result,
):
    """在页面底部渲染 HTML 导出区域。"""
    st.markdown("---")
    st.markdown("### 📤 导出分析报告")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        export_title = st.text_input(
            "报告标题",
            value=f"多股票对比分析 - {', '.join(compare_stocks)}",
            key="export_title",
        )
    with col2:
        include_date = st.checkbox("包含生成日期", value=True, key="include_date")

    if not st.button("🎁 生成并下载HTML报告", type="primary", width="stretch"):
        return

    with st.spinner("正在生成HTML报告..."):
        html_parts: list[str] = []

        # HTML 头部
        html_parts.append(
            f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{export_title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{font-family:'Source Sans Pro','Segoe UI',Tahoma,Geneva,Verdana,sans-serif;margin:0;padding:20px;background:#fafafa;color:#31333f;}}
        .container {{max-width:1200px;margin:0 auto;background:#fff;padding:40px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.1);}}
        h1 {{color:#2c3e50;border-bottom:3px solid #3498db;padding-bottom:10px;margin-bottom:30px;}}
        h2 {{color:#34495e;margin-top:40px;margin-bottom:20px;border-left:4px solid #3498db;padding-left:15px;}}
        .metadata {{background:#ecf0f1;padding:15px;border-radius:5px;margin-bottom:30px;font-size:14px;color:#7f8c8d;}}
        .metrics {{display:flex;justify-content:space-around;margin:30px 0;flex-wrap:wrap;}}
        .metric-card {{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px;border-radius:10px;text-align:center;min-width:200px;margin:10px;box-shadow:0 4px 6px rgba(0,0,0,.1);}}
        .metric-label {{font-size:14px;opacity:.9;margin-bottom:8px;}}
        .metric-value {{font-size:32px;font-weight:700;}}
        .metric-delta {{font-size:18px;margin-top:8px;}}
        .chart-container {{margin:30px 0;background:#fff;padding:20px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.05);}}
        table {{width:100%;border-collapse:collapse;margin:20px 0;}}
        th,td {{padding:12px;text-align:left;border-bottom:1px solid #ecf0f1;}}
        th {{background:#34495e;color:#fff;font-weight:600;}}
        tr:hover {{background:#f8f9fa;}}
        .footer {{margin-top:50px;padding-top:20px;border-top:1px solid #ecf0f1;text-align:center;color:#95a5a6;font-size:12px;}}
        .info-box {{background:#e8f4f8;border-left:4px solid #3498db;padding:15px;margin:20px 0;border-radius:4px;}}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 {export_title}</h1>
"""
        )

        if include_date:
            html_parts.append(
                f"""
        <div class="metadata">
            <strong>生成时间：</strong>{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}<br>
            <strong>分析股票：</strong>{', '.join(compare_stocks)}<br>
            <strong>数据来源：</strong>AkShare API
        </div>
"""
            )

        total_stocks = len(stock_data_dict)
        avg_days = (
            sum(len(df) for df in stock_data_dict.values()) / total_stocks
            if total_stocks > 0
            else 0
        )
        returns = {}
        for sym, df_data in stock_data_dict.items():
            if len(df_data) > 0:
                returns[sym] = (
                    df_data["close"].iloc[-1] / df_data["close"].iloc[0] - 1
                ) * 100
        best_performer = max(returns, key=returns.get) if returns else "N/A"
        best_return = returns.get(best_performer, 0)

        html_parts.append(
            f"""
        <h2>📈 关键指标</h2>
        <div class="metrics">
            <div class="metric-card"><div class="metric-label">对比股票数量</div><div class="metric-value">{total_stocks}</div></div>
            <div class="metric-card"><div class="metric-label">平均数据天数</div><div class="metric-value">{int(avg_days)}</div></div>
            <div class="metric-card"><div class="metric-label">最佳表现</div><div class="metric-value">{best_performer}</div><div class="metric-delta">{"↓" if best_return < 0 else "↑"} {best_return:.2f}%</div></div>
        </div>
"""
        )

        # 价格对比图
        comparison_fig = create_multi_stock_comparison_chart(stock_data_dict)
        if comparison_fig:
            html_parts.append(
                f"""
        <h2>📊 价格走势对比（归一化）</h2>
        <div class="info-box">💡 所有股票的起始价格归一化为100，便于直观对比相对涨跌幅</div>
        <div class="chart-container"><div id="price-chart"></div></div>
        <script>
            var priceData = {comparison_fig.to_json()};
            Plotly.newPlot('price-chart', priceData.data, priceData.layout, {{responsive: true}});
        </script>
"""
            )

        # 统计表格
        if comparison_stats:
            rows_html = "".join(
                f"<tr><td><strong>{s['股票']}</strong></td><td>{s['起始价格']}</td>"
                f"<td>{s['最新价格']}</td><td>{s['总收益率']}</td><td>{s['年化波动率']}</td>"
                f"<td>{s['最高价']}</td><td>{s['最低价']}</td><td>{s['数据天数']}</td></tr>"
                for s in comparison_stats
            )
            html_parts.append(
                f"""
        <h2>📋 详细统计对比</h2>
        <table>
            <thead><tr><th>股票</th><th>起始价格</th><th>最新价格</th><th>总收益率</th><th>年化波动率</th><th>最高价</th><th>最低价</th><th>数据天数</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
"""
            )

        # 可选图表
        _chart_pairs = [
            (rs_fig, "rs-chart", "💪 相对强弱对比", "RS曲线上升表示跑赢基准，下降表示跑输基准。"),
            (risk_return_fig, "risk-return-chart", "⚖️ 风险-收益分析", "理想标的位于左上角（高收益、低风险）。"),
            (factor_score_fig, "factor-score-chart", "🎯 最新因子评分对比", "柱子越高，策略认为买入价值越大。"),
            (corr_fig, "correlation-chart", "🔥 股票相关性分析", "接近1正相关，接近-1负相关，接近0无相关。"),
            (periodic_heatmap_fig, "periodic-heatmap", "📅 周期收益率热图", "绿色盈利，红色亏损，可发现季节性规律。"),
        ]
        for fig, div_id, title, tip in _chart_pairs:
            if fig is not None:
                html_parts.append(
                    f"""
        <h2>{title}</h2>
        <div class="info-box">💡 {tip}</div>
        <div class="chart-container"><div id="{div_id}"></div></div>
        <script>
            var d_{div_id.replace('-','_')} = {fig.to_json()};
            Plotly.newPlot('{div_id}', d_{div_id.replace('-','_')}.data, d_{div_id.replace('-','_')}.layout, {{responsive: true}});
        </script>
"""
                )

        # 组合净值图
        if portfolio_result and portfolio_result.get("fig"):
            html_parts.append(
                f"""
        <h2>💼 投资组合模拟</h2>
        <div class="info-box">💡 绿色实线为组合策略净值，红色虚线为基准。</div>
        <div class="chart-container"><div id="portfolio-chart"></div></div>
        <script>
            var portfolioData = {portfolio_result['fig'].to_json()};
            Plotly.newPlot('portfolio-chart', portfolioData.data, portfolioData.layout, {{responsive: true}});
        </script>
        <div class="metrics">
            <div class="metric-card"><div class="metric-label">组合策略收益</div><div class="metric-value">{portfolio_result['port_total_return']:.2%}</div><div class="metric-delta">夏普 {portfolio_result['port_sharpe']:.2f}</div></div>
            <div class="metric-card"><div class="metric-label">组合最大回撤</div><div class="metric-value">{portfolio_result['port_max_dd']:.2%}</div></div>
            <div class="metric-card"><div class="metric-label">买入持有收益</div><div class="metric-value">{portfolio_result['bh_total_return']:.2%}</div><div class="metric-delta">夏普 {portfolio_result['bh_sharpe']:.2f}</div></div>
        </div>
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
            file_name=f"stock_comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            type="primary",
            width="stretch",
        )
        st.success("✅ HTML报告已生成！点击上方按钮下载")
