"""
侧边栏 UI 模块
================
渲染 Streamlit 侧边栏的所有控件，返回完整的参数字典。
"""

import os
import re
from datetime import date as _date, timedelta as _timedelta

import numpy as np
import pandas as pd
import streamlit as st
from ui.i18n import tr
try:
    from st_keyup import st_keyup
except ImportError:  # pragma: no cover - fallback for environments without the component
    st_keyup = None

from core.config import DATA_DIR, DEFAULT_A_STOCKS, DEFAULT_SYMBOL, STRATEGY_PRESETS
from core.data import (
    fetch_a_stock,
    fetch_data,
    get_stock_label_map,
    load_csv,
    search_stock_candidates,
)
from core.utils import load_or_fetch_stock, get_available_stocks


def _render_live_search_input(market: str) -> str:
    """ui.searchInputFallback"""
    label = tr("placeholder.search_stock")
    placeholder = tr("example.tickerOrName")
    key = f"new_symbol_input_{market}"

    if st_keyup is not None:
        value = st_keyup(
            label,
            key=key,
            debounce=250,
            placeholder=placeholder,
        )
    else:
        value = st.text_input(
            label,
            placeholder=placeholder,
            key=key,
        )

    return str(value or "").strip()


@st.fragment
def _render_stock_search_fragment(market: str, adjust: str, available_stocks: tuple[str, ...]) -> None:
    """component.stockSearch.description"""
    resolved_symbol = ""
    selected_stock_label = ""
    search_query = _render_live_search_input(market)

    matched_candidates = pd.DataFrame(columns=["symbol", "name", "label"])
    candidate_label_map: dict[str, str] = {}

    if search_query:
        try:
            matched_candidates = search_stock_candidates(search_query, market=market, limit=8)
            candidate_label_map = {
                row.symbol: row.label for row in matched_candidates.itertuples(index=False)
            }
        except Exception as exc:
            st.warning(f"{tr("market.cn_stock") if market == 'A' else tr("market.us_stocks")}搜索索引加载失败：{exc}")

        if not matched_candidates.empty:
            resolved_symbol = st.radio(
                tr("search.matches"),
                options=matched_candidates["symbol"].tolist(),
                format_func=lambda symbol: candidate_label_map.get(symbol, symbol),
                index=0,
                label_visibility="collapsed",
            )
            selected_stock_label = candidate_label_map.get(resolved_symbol, resolved_symbol)
        elif market == "A" and re.fullmatch(r"\d{6}", search_query):
            resolved_symbol = search_query
            selected_stock_label = search_query
            st.caption(tr("data.download.fallbackByCode"))
        elif market == "US":
            resolved_symbol = search_query.upper()
            selected_stock_label = resolved_symbol
            st.caption(tr("data.download.fallbackByCode"))
        else:
            st.info(tr("error.no_matching_stock"))

    add_stock_btn = st.button(tr("stockList.addAction"), width="stretch", key=f"add_stock_{market}")

    if add_stock_btn:
        if market == "US" and not resolved_symbol:
            st.warning(tr("validation.enterUsStockCode"))
        elif market == "A" and not resolved_symbol:
            st.warning(tr("search.a_share_prompt"))
        elif resolved_symbol not in available_stocks:
            with st.spinner(f"正在下载 {selected_stock_label or resolved_symbol} 数据..."):
                new_df = load_or_fetch_stock(resolved_symbol, adjust, market=market)
                if new_df is not None:
                    st.success(f"✓ {selected_stock_label or resolved_symbol} 添加成功")
                    st.session_state[f"new_symbol_input_{market}"] = ""
                    st.rerun()
        else:
            st.info(f"✓ {selected_stock_label or resolved_symbol} 已在数据库中")


def render_sidebar(
    *,
    initial_market: str | None = None,
    initial_symbols: list[str] | None = None,
    route_seed_token: str | None = None,
) -> dict:
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
        if route_seed_token is not None and st.session_state.get("_sidebar_route_seed_token") != route_seed_token:
            if initial_market is not None:
                st.session_state["sidebar_market"] = initial_market
            if initial_symbols is not None:
                market_key = str(initial_market or st.session_state.get("sidebar_market", "US")).strip().upper()
                selector_key = f"compare_stocks_selector_{market_key}"
                st.session_state[selector_key] = list(dict.fromkeys(initial_symbols))
            st.session_state["_sidebar_route_seed_token"] = route_seed_token

        # W5 起参数搜索结果不再默认回写侧边栏，清理旧版会话残留键。
        st.session_state.pop("best_params", None)
        st.session_state.pop("apply_best_params", None)

        st.header(tr("section.title.controlPanel"))

        market = st.radio(
            tr("market.selection"),
            options=["US", "A"],
            index=0,
            format_func=lambda x: tr("market.us_stocks") if x == "US" else tr("market.cn_stock"),
            horizontal=True,
            help=tr("market.switch_defaults_notice"),
            key="sidebar_market",
        )
        st.session_state["market"] = market

        # ===== 日期选择 =====
        st.subheader(tr("time.range"))
        _default_end = _date.today()
        _default_start = _default_end - _timedelta(days=3 * 365)
        selected_range = st.date_input(
            tr("common.selectTimeRange"),
            value=(_default_start, _default_end),
            min_value=_date(2015, 1, 1),
            max_value=_date.today(),
            help=tr("backtest.dateRangePicker"),
            key="sidebar_selected_range",
        )

        # ===== 股票选择 =====
        st.markdown("---")
        st.subheader(tr("section.stockSelection"))

        adjust = st.selectbox(
            tr("data.adjustment"),
            options=["qfq", "hfq", "none"],
            index=0,
            help=tr("data.download.adjustmentMethod"),
            key="sidebar_adjust",
        )
        st.session_state["adjust"] = adjust

        available_stocks = get_available_stocks(market=market)
        if initial_symbols is not None:
            available_stocks = list(dict.fromkeys([*initial_symbols, *available_stocks]))
        stock_label_map = get_stock_label_map(available_stocks, market=market)

        # 添加新股票 / 上传 CSV
        with st.expander(tr("action.addStockOrUpload"), expanded=False):
            _render_stock_search_fragment(market, adjust, tuple(available_stocks))

            st.markdown("---")

            uploaded_file = st.file_uploader(
                tr("upload.csvFormat"),
                type=["csv"],
                help=tr("data.upload_custom_csv"),
            )
            if uploaded_file:
                st.info(tr("status.using_uploaded_csv"))

        # 选择股票
        compare_stocks: list[str] = []
        if available_stocks:
            compare_stocks = st.multiselect(
                tr("action.selectStocks"),
                options=available_stocks,
                default=[available_stocks[0]] if available_stocks else [],
                format_func=lambda symbol: stock_label_map.get(symbol, symbol),
                help=tr("stock.selectionPrompt"),
                key=f"compare_stocks_selector_{market}",
            )
            if len(compare_stocks) == 1:
                selected_stock_label = stock_label_map.get(compare_stocks[0], compare_stocks[0])
                st.info(f"✓ 将分析 {selected_stock_label} 的交易策略")
            elif len(compare_stocks) > 1:
                st.info(f"✓ 已选择 {len(compare_stocks)} 只股票进行对比")
        else:
            st.warning(tr("data.stock.empty"))

        # 刷新所有已选股票数据
        if compare_stocks:
            if st.button(tr("action.refreshStockData"), width="stretch"):
                with st.spinner(tr("data.refreshing")):
                    success_count = 0
                    fail_count = 0

                    for stock_symbol in compare_stocks:
                        try:
                            if market == "A":
                                df_temp = fetch_a_stock(stock_symbol, adjust)
                            else:
                                df_temp = fetch_data(stock_symbol, adjust)

                            if df_temp is None or df_temp.empty:
                                raise ValueError(tr("error.noValidData"))

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
        default_symbol = DEFAULT_SYMBOL if market == "US" else DEFAULT_A_STOCKS[0]
        symbol = compare_stocks[0] if compare_stocks else default_symbol

        st.markdown("---")

        # ===== 策略选择 =====
        st.subheader(tr("strategy.selection"))

        strategy_preset = st.selectbox(
            tr("strategy.select_preset"),
            options=list(STRATEGY_PRESETS.keys()),
            index=1,
            help=tr("strategy.template_description"),
            key="strategy_preset_selector",
        )

        preset_info = STRATEGY_PRESETS[strategy_preset]
        st.caption(f"💡 {preset_info['description']}")

        # 预设参数同步到 session_state
        if strategy_preset != tr("parameter.custom"):
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
            preset = STRATEGY_PRESETS[tr("strategy.balanced.default")]

        st.markdown("---")

        _preset_entry_min = (
            preset.get("entry_min_signals", 3)
            if strategy_preset != tr("parameter.custom")
            else 3
        )
        _preset_exit_min = (
            preset.get("exit_min_signals", 2)
            if strategy_preset != tr("parameter.custom")
            else 2
        )

        # ===== 入场规则 =====
        st.subheader(tr("strategy.entryRules"))
        st.caption(tr("strategy.entry_condition"))
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
            tr("param.minEntrySignals"),
            1,
            5,
            _preset_entry_min,
            help=tr("condition.entry_threshold"),
        )

        st.markdown("---")

        # ===== 出场规则 =====
        st.subheader(tr("rules.exit"))
        st.caption(tr("exit.condition.signalCount"))
        st.markdown(
            """
1. 📊 因子评分过低
2. 📉 趋势反转（EMA快<慢）
3. ⚠️ RSI超出合理区间
4. 📉 MACD跌破信号线
        """
        )
        exit_min_signals = st.slider(
            tr("strategy.min_exit_signals"),
            1,
            4,
            _preset_exit_min,
            help=tr("rules.exit.conditions.description"),
        )

        st.markdown("---")

        # ===== 高级设置 =====
        with st.expander(
            tr("button.advancedSettings"), expanded=False
        ):
            if strategy_preset != tr("parameter.custom"):
                st.caption(
                    f"当前使用「{strategy_preset}」预设，以下参数已自动填充。切换为「自定义参数」可手动修改。"
                )
            else:
                st.caption(
                    tr("strategy.param_description")
                )

            st.markdown(tr("params.ema_trend_parameters"))
            ema_fast = st.slider(
                tr("param.emaFastPeriod"), 5, 50, 20, help=tr("description.trend_filter_ema"), key="ema_fast_slider"
            )
            ema_slow = st.slider(
                tr("params.ema_slow_period"), 20, 200, 60, help=tr("indicator.trendFilter.longEma"), key="ema_slow_slider"
            )

            st.markdown(tr("param.macd"))
            macd_fast = st.slider(
                tr("indicator.macd_fast_period"), 5, 20, 12, help=tr("indicator.macdFastPeriod"), key="macd_fast_slider"
            )
            macd_slow = st.slider(
                tr("indicator.macd_slow_period"), 10, 40, 26, help=tr("indicator.macd.slowEma.period"), key="macd_slow_slider"
            )
            macd_signal = st.slider(
                tr("parameter.macdSignalPeriod"), 5, 20, 9, help=tr("param.macd_signal_ema_period"), key="macd_signal_slider"
            )

            st.markdown(tr("section.rsi_parameters"))
            rsi_period = st.slider(
                tr("rsi.period"), 5, 30, 14, help=tr("param.rsi.period.description"), key="rsi_period_slider"
            )
            rsi_lower = st.slider(
                tr("params.rsi_lower_threshold"), 10, 50, 30, help=tr("indicator.rsi_weak_threshold"), key="rsi_lower_slider"
            )
            rsi_upper = st.slider(
                tr("param.rsiUpperThreshold"), 50, 90, 70, help=tr("parameter.rsiStrongThreshold.desc"), key="rsi_upper_slider"
            )

            st.markdown(tr("param.adx_strength"))
            adx_period = st.slider(
                tr("parameter.adxPeriod"), 5, 30, 14, help=tr("indicator.trendStrength.period"), key="adx_period_slider"
            )
            adx_threshold = st.slider(
                tr("indicator.adx.threshold"), 10, 40, 20,
                help=tr("adx.trend_threshold"),
                key="adx_threshold",
            )

            st.markdown(tr("strategy.atr_stop_loss_take_profit"))
            atr_period = st.slider(
                tr("parameter.atr.period"), 5, 30, 14, help=tr("indicator.atr.calculationPeriod"), key="atr_period_slider"
            )

            st.markdown(tr("indicator.bollingerBands.advancedParams"))
            bb_period = st.slider(
                tr("bollinger.period"), 5, 50, 20, help=tr("indicator.bollinger.maPeriod"), key="bb_period_slider"
            )
            bb_std = st.slider(
                tr("bollinger.std_dev_multiplier"), 1.0, 3.0, 2.0, step=0.1,
                help=tr("param.bollinger.stdDev.description"),
                key="bb_std_slider",
            )
            indicator_period = st.slider(
                tr("indicator.obvVolumePriceCycle"), 5, 60, 20,
                help=tr("parameter.obvCommonWindow.desc"),
                key="indicator_period_slider",
            )

            stop_loss_mult = st.slider(
                tr("param.atrStopLossMultiplier"), 0.0, 5.0, 2.0, step=0.5,
                help=tr("param.stopLoss.formula"),
                key="stop_loss_mult",
            )
            take_profit_mult = st.slider(
                tr("strategy.atr.takeProfitMultiplier"), 0.0, 8.0, 4.0, step=0.5,
                help=tr("param.takeProfit.formula"),
                key="take_profit_mult",
            )

            st.markdown(tr("section.factorScoreParameters"))
            momentum_short = st.slider(tr("params.short_momentum_window"), 2, 20, 5, help=tr("label.short_term_return_window"))
            momentum_long = st.slider(tr("param.midTermMomentum.window"), 10, 60, 20, help=tr("metrics.midterm_return_window"))
            score_lookback = st.slider(
                tr("scoring.normalization_window"), 10, 120, 30, help=tr("parameter.zScoreWindow.desc")
            )
            score_mid_pct = st.slider(
                tr("scoring.percentile.mid"), 0.5, 0.9, 0.6, step=0.05,
                help=tr("position.mid_level_threshold"),
            )
            score_high_pct = st.slider(
                tr("score.quantile.high"), 0.6, 0.95, 0.8, step=0.05,
                help=tr("position.high_level_threshold"),
            )
            weight_mom_short = st.slider(
                tr("weight.short_term_momentum"), 0.0, 3.0, 1.0, step=0.1, help=tr("factor.weight_short_term_momentum")
            )
            weight_mom_long = st.slider(
                tr("parameter.midTermMomentumWeight"), 0.0, 3.0, 1.0, step=0.1, help=tr("scoring.weight_midterm_momentum")
            )
            weight_macd = st.slider(
                tr("parameter.macdWeight"), 0.0, 3.0, 1.0, step=0.1, help=tr("param.macdHistogramWeight")
            )
            weight_rsi = st.slider(
                tr("param.rsi_weight"), 0.0, 3.0, 0.5, step=0.1, help=tr("factor.weight_rsi")
            )
            weight_vol = st.slider(
                tr("strategy.volatilityPenalty.weight"), 0.0, 3.0, 0.5, step=0.1, help=tr("scoring.volatilityPenalty")
            )

            st.markdown(tr("factor.weight.phase1.title"))
            weight_bb = st.slider(
                tr("weight.bollinger_position"), 0.0, 2.0, 0.8, step=0.1,
                help=tr("bollinger.weight_in_scoring"),
                key="weight_bb",
            )
            weight_obv = st.slider(
                tr("parameter.obvTrendWeight"), 0.0, 2.0, 1.0, step=0.1,
                help=tr("scoring.weight_obv_trend"),
                key="weight_obv",
            )
            weight_volume = st.slider(
                tr("weight.volume_ratio"), 0.0, 1.5, 0.6, step=0.1,
                help=tr("scoring.weight.volumeRatio"),
                key="weight_volume",
            )
            weight_price = st.slider(
                tr("strategy.pricePositionWeight"), 0.0, 1.5, 0.7, step=0.1,
                help=tr("weight.rangePosition"),
                key="weight_price",
            )
            weight_drawdown = st.slider(
                tr("parameter.drawdownPenaltyWeight"), 0.0, 1.5, 0.5, step=0.1,
                help=tr("scoring.drawdownPenalty"),
                key="weight_drawdown",
            )

            st.markdown(tr("strategy.entryExit.scoreThreshold"))
            entry_threshold = st.slider(
                tr("strategy.entryScoreThreshold"), -2.0, 2.0, 0.5, step=0.1,
                help=tr("param.entryThreshold.description"),
                key="entry_threshold",
            )
            exit_threshold = st.slider(
                tr("threshold.exitScore"), -2.0, 2.0, -0.5, step=0.1,
                help=tr("factor.exit_threshold"),
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
        "market": market,
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
        with st.expander(tr("menu.feedback"), expanded=False):
            feedback_type = st.selectbox(
                tr("common.type"),
                [tr("menu.bugReport"), tr("section.feature_suggestion"), tr("feedback.otherTitle")],
                key="feedback_type",
            )
            feedback_text = st.text_area(
                tr("field.description"),
                placeholder=tr("feedback.placeholder"),
                height=120,
                key="feedback_text",
            )
            if st.button(tr("action.submitFeedback"), key="submit_feedback", use_container_width=True):
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
                    st.success(tr("feedback.thank_you"))
                    st.markdown(f"[📋 前往提交 Issue]({issue_url})")
                else:
                    st.warning(tr("feedback.emptyWarning"))

            st.caption(tr("feedback.githubIssues"))

    return result
