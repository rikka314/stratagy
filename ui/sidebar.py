"""
侧边栏 UI 模块
================
渲染 Streamlit 侧边栏的所有控件，返回完整的参数字典。
"""

import os
from datetime import date as _date, timedelta as _timedelta

import numpy as np
import pandas as pd
import streamlit as st

from core.config import DATA_DIR, DEFAULT_SYMBOL, STRATEGY_PRESETS
from core.data import fetch_data, load_csv
from core.utils import load_or_fetch_stock, get_available_stocks


def render_sidebar() -> dict:
    """
    渲染侧边栏全部控件，返回包含所有参数的字典。

    Returns
    -------
    dict
        包含以下 key：
        - compare_stocks, symbol, adjust, selected_range, uploaded_file
        - 所有策略参数（ema_fast, rsi_period, entry_threshold 等）
        - strategy_preset（当前选择的预设名称）
    """
    with st.sidebar:
        st.header("📊 控制面板")

        # ===== 日期选择 =====
        st.subheader("📅 时间范围")
        _default_end = _date.today()
        _default_start = _default_end - _timedelta(days=3 * 365)
        selected_range = st.date_input(
            "选择时间区间",
            value=(_default_start, _default_end),
            min_value=_date(2015, 1, 1),
            max_value=_date.today(),
            help="选择回测数据的起止日期",
        )

        # ===== 股票选择 =====
        st.markdown("---")
        st.subheader("🔍 股票选择")

        adjust = st.selectbox(
            "复权方式",
            options=["qfq", "hfq", "none"],
            index=0,
            help="影响数据下载的复权方式。",
        )
        st.session_state["adjust"] = adjust

        available_stocks = get_available_stocks()

        # 添加新股票 / 上传 CSV
        with st.expander("➕ 添加股票 / 上传数据", expanded=False):
            new_symbol = (
                st.text_input(
                    "输入股票代码",
                    placeholder="例如: TSLA, NVDA, MSFT",
                    help="输入股票代码后点击添加",
                )
                .upper()
                .strip()
            )

            add_stock_btn = st.button("添加到股票列表", width="stretch")

            if add_stock_btn and new_symbol:
                if new_symbol not in available_stocks:
                    with st.spinner(f"正在下载 {new_symbol} 数据..."):
                        new_df = load_or_fetch_stock(new_symbol, adjust)
                        if new_df is not None:
                            available_stocks = get_available_stocks()
                            st.success(f"✓ {new_symbol} 添加成功")
                else:
                    st.info(f"✓ {new_symbol} 已在数据库中")

            st.markdown("---")

            uploaded_file = st.file_uploader(
                "上传 CSV（列名：open, close, volumn/volume, high, low）",
                type=["csv"],
                help="上传自定义CSV数据文件",
            )
            if uploaded_file:
                st.info("✓ 将使用上传的CSV数据")

        # 选择股票
        compare_stocks: list[str] = []
        if available_stocks:
            compare_stocks = st.multiselect(
                "选择股票",
                options=available_stocks,
                default=[available_stocks[0]] if available_stocks else [],
                help="选择一只股票进行策略分析，或多只股票进行对比分析",
                key="compare_stocks_selector",
            )
            if len(compare_stocks) == 1:
                st.info(f"✓ 将分析 {compare_stocks[0]} 的交易策略")
            elif len(compare_stocks) > 1:
                st.info(f"✓ 已选择 {len(compare_stocks)} 只股票进行对比")
        else:
            st.warning("暂无股票数据，请先添加股票")

        # 刷新所有已选股票数据
        if compare_stocks:
            if st.button("🔄 刷新所选股票数据", width="stretch"):
                with st.spinner("正在刷新数据..."):
                    success_count = 0
                    fail_count = 0

                    for stock_symbol in compare_stocks:
                        try:
                            df_temp = fetch_data(stock_symbol, adjust)
                            os.makedirs(DATA_DIR, exist_ok=True)
                            cache_path = os.path.join(
                                DATA_DIR, f"{stock_symbol.lower()}_daily.csv"
                            )
                            df_temp.to_csv(cache_path, index=False)

                            if not df_temp.empty and "date" in df_temp.columns:
                                latest_date = df_temp["date"].max()
                                st.info(
                                    f"✓ {stock_symbol}: 已更新至 "
                                    f"{latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else latest_date}"
                                )
                            success_count += 1
                        except Exception as e:
                            st.error(f"✗ {stock_symbol} 刷新失败: {e}")
                            fail_count += 1

                    load_csv.clear()
                    st.cache_data.clear()

                    if success_count > 0:
                        st.success(
                            f"✓ 数据刷新完成：成功 {success_count} 个，失败 {fail_count} 个"
                        )
                    st.rerun()

        st.session_state["compare_stocks"] = compare_stocks
        symbol = compare_stocks[0] if compare_stocks else DEFAULT_SYMBOL

        # 检测股票切换，清除旧的搜索结果
        if st.session_state.get("_last_symbol") != symbol:
            st.session_state["_last_symbol"] = symbol
            st.session_state.pop("best_params", None)

        st.markdown("---")

        # ===== 策略选择 =====
        st.subheader("📋 策略选择")

        strategy_preset = st.selectbox(
            "选择预设策略",
            options=list(STRATEGY_PRESETS.keys()),
            index=1,
            help="预设策略模板会自动填充入场/出场规则和高级设置中的所有参数。选择「自定义参数」可手动调节。",
            key="strategy_preset_selector",
        )

        preset_info = STRATEGY_PRESETS[strategy_preset]
        st.caption(f"💡 {preset_info['description']}")

        # 预设参数同步到 session_state
        if strategy_preset != "自定义参数":
            preset = STRATEGY_PRESETS[strategy_preset]
            _preset_key_map = {
                "ema_fast": "ema_fast_slider",
                "ema_slow": "ema_slow_slider",
                "macd_fast": "macd_fast_slider",
                "macd_slow": "macd_slow_slider",
                "macd_signal": "macd_signal_slider",
                "rsi_period": "rsi_period_slider",
                "rsi_lower": "rsi_lower_slider",
                "rsi_upper": "rsi_upper_slider",
                "adx_period": "adx_period_slider",
                "atr_period": "atr_period_slider",
                "bb_period": "bb_period_slider",
                "bb_std": "bb_std_slider",
                "indicator_period": "indicator_period_slider",
            }
            for param_name, slider_key in _preset_key_map.items():
                if param_name in preset:
                    st.session_state[slider_key] = preset[param_name]
            for direct_key in [
                "adx_threshold",
                "stop_loss_mult",
                "take_profit_mult",
                "entry_threshold",
                "exit_threshold",
                "weight_bb",
                "weight_obv",
                "weight_volume",
                "weight_price",
                "weight_drawdown",
            ]:
                if direct_key in preset:
                    st.session_state[direct_key] = preset[direct_key]
        else:
            preset = STRATEGY_PRESETS["均衡策略（默认）"]

        st.markdown("---")

        _preset_entry_min = (
            preset.get("entry_min_signals", 3)
            if strategy_preset != "自定义参数"
            else 3
        )
        _preset_exit_min = (
            preset.get("exit_min_signals", 2)
            if strategy_preset != "自定义参数"
            else 2
        )

        # ===== 入场规则 =====
        st.subheader("📈 入场规则")
        st.caption("入场需满足以下信号中的至少 N 个：")
        st.markdown(
            """
1. 📊 因子评分达标
2. 📈 趋势向上（EMA快>慢）
3. 💪 趋势强度足够（ADX）
4. 🎯 RSI在合理区间
5. 📉 MACD在信号线上方
        """
        )
        entry_min_signals = st.slider(
            "入场最少信号数",
            1,
            5,
            _preset_entry_min,
            help="需要同时满足的入场条件数量。数值越大入场越严格，1=最宽松（任一满足即入场），5=最严格（全部满足才入场）",
        )

        st.markdown("---")

        # ===== 出场规则 =====
        st.subheader("📉 出场规则")
        st.caption("出场需满足以下信号中的至少 N 个：")
        st.markdown(
            """
1. 📊 因子评分过低
2. 📉 趋势反转（EMA快<慢）
3. ⚠️ RSI超出合理区间
4. 📉 MACD跌破信号线
        """
        )
        exit_min_signals = st.slider(
            "出场最少信号数",
            1,
            4,
            _preset_exit_min,
            help="需要同时满足的出场条件数量。数值越大出场越宽松（不容易被踢出），1=原始逻辑（任一触发就出场），4=全部满足才出场",
        )

        st.markdown("---")

        # ===== 高级设置 =====
        with st.expander(
            "⚙️ 高级设置（自定义参数 / 查看当前值）", expanded=False
        ):
            if strategy_preset != "自定义参数":
                st.caption(
                    f"当前使用「{strategy_preset}」预设，以下参数已自动填充。切换为「自定义参数」可手动修改。"
                )
            else:
                st.caption(
                    "手动调整所有策略参数，或使用高级策略自动搜索最优值。"
                )

            st.markdown("**EMA 趋势参数**")
            ema_fast = st.slider(
                "EMA 快线周期", 5, 50, 20, help="趋势过滤的短周期 EMA。", key="ema_fast_slider"
            )
            ema_slow = st.slider(
                "EMA 慢线周期", 20, 200, 60, help="趋势过滤的长周期 EMA。", key="ema_slow_slider"
            )

            st.markdown("**MACD 参数**")
            macd_fast = st.slider(
                "MACD 快线周期", 5, 20, 12, help="MACD 快线 EMA 周期。", key="macd_fast_slider"
            )
            macd_slow = st.slider(
                "MACD 慢线周期", 10, 40, 26, help="MACD 慢线 EMA 周期。", key="macd_slow_slider"
            )
            macd_signal = st.slider(
                "MACD 信号周期", 5, 20, 9, help="MACD 信号线 EMA 周期。", key="macd_signal_slider"
            )

            st.markdown("**RSI 参数**")
            rsi_period = st.slider(
                "RSI 周期", 5, 30, 14, help="RSI 计算周期。", key="rsi_period_slider"
            )
            rsi_lower = st.slider(
                "RSI 下限阈值", 10, 50, 30, help="RSI 低于该值视为偏弱。", key="rsi_lower_slider"
            )
            rsi_upper = st.slider(
                "RSI 上限阈值", 50, 90, 70, help="RSI 高于该值视为偏强。", key="rsi_upper_slider"
            )

            st.markdown("**ADX 强度参数**")
            adx_period = st.slider(
                "ADX 周期", 5, 30, 14, help="趋势强度指标的计算周期。", key="adx_period_slider"
            )
            adx_threshold = st.slider(
                "ADX 阈值", 10, 40, 20,
                help="ADX 高于该值才认为趋势有效。",
                key="adx_threshold",
            )

            st.markdown("**ATR 止损止盈**")
            atr_period = st.slider(
                "ATR 周期", 5, 30, 14, help="波动率（ATR）计算周期。", key="atr_period_slider"
            )

            st.markdown("**布林带 / 高级指标参数**")
            bb_period = st.slider(
                "布林带周期", 5, 50, 20, help="布林带移动平均线的计算周期。", key="bb_period_slider"
            )
            bb_std = st.slider(
                "布林带标准差倍数", 1.0, 3.0, 2.0, step=0.1,
                help="布林带上下轨的标准差倍数。",
                key="bb_std_slider",
            )
            indicator_period = st.slider(
                "OBV/成交量/价格位置周期", 5, 60, 20,
                help="OBV 趋势变化率、成交量均量、价格高低点位置的共用计算周期。",
                key="indicator_period_slider",
            )

            stop_loss_mult = st.slider(
                "ATR 止损倍数", 0.0, 5.0, 2.0, step=0.5,
                help="止损距离=ATR×倍数。",
                key="stop_loss_mult",
            )
            take_profit_mult = st.slider(
                "ATR 止盈倍数", 0.0, 8.0, 4.0, step=0.5,
                help="止盈距离=ATR×倍数。",
                key="take_profit_mult",
            )

            st.markdown("**因子评分参数**")
            momentum_short = st.slider("短期动量窗口", 2, 20, 5, help="短期收益率窗口。")
            momentum_long = st.slider("中期动量窗口", 10, 60, 20, help="中期收益率窗口。")
            score_lookback = st.slider(
                "评分标准化窗口", 10, 120, 30, help="用于计算滚动 Z 分数的窗口。"
            )
            score_mid_pct = st.slider(
                "评分分位数-中档", 0.5, 0.9, 0.6, step=0.05,
                help="评分分位数达到该值进入中档仓位。",
            )
            score_high_pct = st.slider(
                "评分分位数-高档", 0.6, 0.95, 0.8, step=0.05,
                help="评分分位数达到该值进入高档仓位。",
            )
            weight_mom_short = st.slider(
                "短期动量权重", 0.0, 3.0, 1.0, step=0.1, help="短期动量在评分中的权重。"
            )
            weight_mom_long = st.slider(
                "中期动量权重", 0.0, 3.0, 1.0, step=0.1, help="中期动量在评分中的权重。"
            )
            weight_macd = st.slider(
                "MACD 权重", 0.0, 3.0, 1.0, step=0.1, help="MACD 柱在评分中的权重。"
            )
            weight_rsi = st.slider(
                "RSI 权重", 0.0, 3.0, 0.5, step=0.1, help="RSI 在评分中的权重。"
            )
            weight_vol = st.slider(
                "波动惩罚权重", 0.0, 3.0, 0.5, step=0.1, help="波动率越高，评分惩罚越大。"
            )

            st.markdown("**Phase 1 新因子权重**")
            weight_bb = st.slider(
                "布林带位置权重", 0.0, 2.0, 0.8, step=0.1,
                help="布林带位置在评分中的权重。",
                key="weight_bb",
            )
            weight_obv = st.slider(
                "OBV 趋势权重", 0.0, 2.0, 1.0, step=0.1,
                help="OBV 趋势在评分中的权重。",
                key="weight_obv",
            )
            weight_volume = st.slider(
                "成交量比率权重", 0.0, 1.5, 0.6, step=0.1,
                help="成交量比率在评分中的权重。",
                key="weight_volume",
            )
            weight_price = st.slider(
                "价格位置权重", 0.0, 1.5, 0.7, step=0.1,
                help="价格在近期高低范围中的位置权重。",
                key="weight_price",
            )
            weight_drawdown = st.slider(
                "回撤惩罚权重", 0.0, 1.5, 0.5, step=0.1,
                help="回撤越大，评分惩罚越大。",
                key="weight_drawdown",
            )

            st.markdown("**入场/出场评分阈值**")
            entry_threshold = st.slider(
                "入场评分阈值", -2.0, 2.0, 0.5, step=0.1,
                help="因子评分高于该值才视为入场信号之一。",
                key="entry_threshold",
            )
            exit_threshold = st.slider(
                "出场评分阈值", -2.0, 2.0, -0.5, step=0.1,
                help="因子评分低于该值视为出场信号之一。",
                key="exit_threshold",
            )

        # 固定值
        use_trend_filter = True
        use_strength_filter = True
        use_rsi_filter = True
        use_macd_filter = True
        use_voting_entry = False
        entry_vote_threshold = 2.5

    # ── 组装并返回参数字典 ──
    result = {
        # UI 状态
        "compare_stocks": compare_stocks,
        "symbol": symbol,
        "adjust": adjust,
        "selected_range": selected_range,
        "uploaded_file": uploaded_file,
        "strategy_preset": strategy_preset,
        # 技术指标参数
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "macd_fast": macd_fast,
        "macd_slow": macd_slow,
        "macd_signal": macd_signal,
        "rsi_period": rsi_period,
        "rsi_lower": rsi_lower,
        "rsi_upper": rsi_upper,
        "adx_period": adx_period,
        "adx_threshold": adx_threshold,
        "atr_period": atr_period,
        "bb_period": bb_period,
        "bb_std": bb_std,
        "indicator_period": indicator_period,
        "stop_loss_mult": stop_loss_mult,
        "take_profit_mult": take_profit_mult,
        # 因子评分参数
        "momentum_short": momentum_short,
        "momentum_long": momentum_long,
        "score_lookback": score_lookback,
        "score_mid_pct": score_mid_pct,
        "score_high_pct": score_high_pct,
        "weight_mom_short": weight_mom_short,
        "weight_mom_long": weight_mom_long,
        "weight_macd": weight_macd,
        "weight_rsi": weight_rsi,
        "weight_vol": weight_vol,
        # Phase 1 因子权重
        "weight_bb": weight_bb,
        "weight_obv": weight_obv,
        "weight_volume": weight_volume,
        "weight_price": weight_price,
        "weight_drawdown": weight_drawdown,
        # 入场/出场规则
        "entry_threshold": entry_threshold,
        "exit_threshold": exit_threshold,
        "entry_min_signals": entry_min_signals,
        "exit_min_signals": exit_min_signals,
        # 过滤器
        "use_trend_filter": use_trend_filter,
        "use_strength_filter": use_strength_filter,
        "use_rsi_filter": use_rsi_filter,
        "use_macd_filter": use_macd_filter,
        "use_voting_entry": use_voting_entry,
        "entry_vote_threshold": entry_vote_threshold,
    }

    # ===== 反馈与建议 =====
    with st.sidebar:
        st.markdown("---")
        with st.expander("💬 反馈与建议", expanded=False):
            feedback_type = st.selectbox(
                "类型",
                ["🐛 Bug 报告", "💡 功能建议", "📝 其他反馈"],
                key="feedback_type",
            )
            feedback_text = st.text_area(
                "描述",
                placeholder="请描述你遇到的问题或建议...",
                height=120,
                key="feedback_text",
            )
            if st.button("📤 提交反馈", key="submit_feedback", use_container_width=True):
                if feedback_text.strip():
                    # 构造 GitHub Issue URL（预填标题和正文）
                    import urllib.parse
                    type_label = feedback_type.split(" ", 1)[1]
                    title = urllib.parse.quote(f"[{type_label}] 用户反馈")
                    body = urllib.parse.quote(
                        f"**类型**：{feedback_type}\n\n"
                        f"**描述**：\n{feedback_text}\n\n"
                        f"---\n*通过应用内反馈提交*"
                    )
                    issue_url = f"https://github.com/rikka314/stratagy/issues/new?title={title}&body={body}"
                    st.success("✅ 感谢反馈！点击下方链接提交到 GitHub：")
                    st.markdown(f"[📋 前往提交 Issue]({issue_url})")
                else:
                    st.warning("请先填写反馈内容")

            st.caption("反馈将通过 [GitHub Issues](https://github.com/rikka314/stratagy/issues) 追踪")

    return result
