"""
投资组合模块
============
组合模拟（多股票加权合成策略净值）和组合级别贝叶斯优化。
"""

import numpy as np
import pandas as pd
import streamlit as st

from core.indicators import add_indicators
from core.signals import compute_signals
from core.backtest import simulate_strategy, sharpe_ratio, max_drawdown
from core.visualization import create_equity_drawdown_chart


def build_portfolio_figure(portfolio_result: dict | None):
    """Rebuild the presentation figure from persisted portfolio result data."""
    if not isinstance(portfolio_result, dict):
        return None
    portfolio_equity = portfolio_result.get("portfolio_equity")
    bh_equity = portfolio_result.get("bh_equity")
    individual_results = portfolio_result.get("individual_results") or {}
    if not isinstance(portfolio_equity, pd.Series) or portfolio_equity.empty:
        return None
    if not isinstance(bh_equity, pd.Series) or bh_equity.empty:
        return None

    colors_list = [
        '#8c674a', '#b28762', '#6d5a49', '#c49a73', '#5a4c3f',
        '#8e725d', '#b89d85', '#9a8268', '#735f4b', '#c1a17d',
    ]
    figure_specs = [
        {
            'name': '组合策略', 'series': portfolio_equity, 'color': '#ba7349',
            'dash': 'solid', 'width': 3.0, 'fill_alpha': 0.18, 'drawdown_fill': True,
        },
        {
            'name': '买入持有基准', 'series': bh_equity, 'color': '#1f1914',
            'dash': 'dash', 'width': 2.4, 'fill_alpha': 0.10, 'drawdown_fill': True,
        },
    ]
    for index, (symbol, result) in enumerate(individual_results.items()):
        strategy_return = result.get("strategy_return") if isinstance(result, dict) else None
        if not isinstance(strategy_return, pd.Series):
            continue
        equity = (1 + strategy_return.reindex(portfolio_equity.index).fillna(0)).cumprod()
        figure_specs.append(
            {
                'name': f'{symbol} 策略', 'hover_name': symbol, 'series': equity,
                'color': colors_list[index % len(colors_list)], 'dash': 'dot',
                'width': 1.45, 'fill_alpha': 0.08, 'drawdown_fill': False,
            }
        )
    return create_equity_drawdown_chart(
        figure_specs,
        height=620,
        subplot_titles=('组合净值', '组合回撤'),
    )


def run_portfolio_simulation(stock_data_dict: dict, **kwargs) -> dict | None:
    """
    投资组合模拟：对每只股票独立跑完整策略流程，然后按权重合成组合净值

    【原理说明】
    1. 对每只股票分别调用 add_indicators → compute_signals → simulate_strategy
    2. 取各股票的策略日收益率，按权重加权平均得到组合日收益率
    3. 累积得到组合策略净值，同时计算等权买入持有基准
    4. 输出组合的夏普比率、最大回撤、总收益等指标

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        **kwargs: 策略参数 + weights(可选, dict {symbol: weight})

    返回：
        dict 包含 portfolio_fig, metrics, individual_results 等，失败返回 None
    """
    weights = kwargs.pop('weights', None)
    symbols = list(stock_data_dict.keys())

    if len(symbols) < 2:
        return None

    # 默认等权
    if weights is None:
        w = 1.0 / len(symbols)
        weights = {sym: w for sym in symbols}

    # 归一化权重
    total_w = sum(weights.values())
    weights = {sym: wt / total_w for sym, wt in weights.items()}

    individual_results = {}

    for sym, df in stock_data_dict.items():
        if df is None or len(df) <= 50:
            continue
        try:
            df_ind = add_indicators(
                df,
                rsi_period=kwargs.get('rsi_period', 14),
                macd_fast=kwargs.get('macd_fast', 12),
                macd_slow=kwargs.get('macd_slow', 26),
                macd_signal=kwargs.get('macd_signal', 9),
                ema_fast=kwargs.get('ema_fast', 20),
                ema_slow=kwargs.get('ema_slow', 60),
                adx_period=kwargs.get('adx_period', 14),
                atr_period=kwargs.get('atr_period', 14),
                bb_period=kwargs.get('bb_period', 20),
                bb_std=kwargs.get('bb_std', 2.0),
                indicator_period=kwargs.get('indicator_period', 20),
            )
            df_sig = compute_signals(
                df_ind,
                rsi_lower=kwargs.get('rsi_lower', 30),
                rsi_upper=kwargs.get('rsi_upper', 70),
                adx_threshold=kwargs.get('adx_threshold', 20),
                momentum_short=kwargs.get('momentum_short', 5),
                momentum_long=kwargs.get('momentum_long', 20),
                score_lookback=kwargs.get('score_lookback', 30),
                score_mid_pct=kwargs.get('score_mid_pct', 0.6),
                score_high_pct=kwargs.get('score_high_pct', 0.8),
                weight_mom_short=kwargs.get('weight_mom_short', 1.0),
                weight_mom_long=kwargs.get('weight_mom_long', 1.0),
                weight_macd=kwargs.get('weight_macd', 1.0),
                weight_rsi=kwargs.get('weight_rsi', 0.5),
                weight_vol=kwargs.get('weight_vol', 0.5),
                entry_threshold=kwargs.get('entry_threshold', 0.5),
                exit_threshold=kwargs.get('exit_threshold', -0.5),
                use_trend_filter=kwargs.get('use_trend_filter', True),
                use_strength_filter=kwargs.get('use_strength_filter', True),
                use_rsi_filter=kwargs.get('use_rsi_filter', True),
                use_macd_filter=kwargs.get('use_macd_filter', True),
                use_voting_entry=kwargs.get('use_voting_entry', True),
                entry_vote_threshold=kwargs.get('entry_vote_threshold', 2.5),
                exit_min_signals=kwargs.get('exit_min_signals', 2),
                entry_min_signals=kwargs.get('entry_min_signals', 3),
            )
            df_bt = simulate_strategy(
                df_sig,
                initial_position=0,
                stop_loss_mult=kwargs.get('stop_loss_mult', 2.0),
                take_profit_mult=kwargs.get('take_profit_mult', 4.0),
            )
            # 以 date 为索引
            ret_series = df_bt.set_index('date')['strategy_return'].sort_index()
            bh_ret = df_bt.set_index('date')['close'].sort_index().pct_change().fillna(0)
            individual_results[sym] = {
                'strategy_return': ret_series,
                'buy_hold_return': bh_ret,
                'total_return': float(df_bt['strategy_equity'].iloc[-1] - 1),
                'sharpe': sharpe_ratio(df_bt['strategy_return']),
                'max_dd': max_drawdown(df_bt['strategy_equity']),
            }
        except Exception:
            continue

    if len(individual_results) < 2:
        return None

    # 合并所有策略日收益率（按日期对齐取交集）
    strat_ret_df = pd.DataFrame({sym: r['strategy_return'] for sym, r in individual_results.items()})
    bh_ret_df = pd.DataFrame({sym: r['buy_hold_return'] for sym, r in individual_results.items()})
    strat_ret_df = strat_ret_df.dropna()
    bh_ret_df = bh_ret_df.dropna()

    if len(strat_ret_df) < 2:
        return None

    # 组合策略收益 = 加权平均
    w_arr = np.array([weights.get(sym, 0) for sym in strat_ret_df.columns])
    portfolio_strat_ret = (strat_ret_df.values * w_arr).sum(axis=1)
    portfolio_strat_ret = pd.Series(portfolio_strat_ret, index=strat_ret_df.index)

    # 组合买入持有收益 = 加权平均
    w_arr_bh = np.array([weights.get(sym, 0) for sym in bh_ret_df.columns])
    portfolio_bh_ret = (bh_ret_df.values * w_arr_bh).sum(axis=1)
    portfolio_bh_ret = pd.Series(portfolio_bh_ret, index=bh_ret_df.index)

    # 累积净值
    portfolio_equity = (1 + portfolio_strat_ret).cumprod()
    bh_equity = (1 + portfolio_bh_ret).cumprod()

    # 组合指标
    port_sharpe = sharpe_ratio(portfolio_strat_ret)
    port_max_dd = max_drawdown(portfolio_equity)
    port_total_return = float(portfolio_equity.iloc[-1] - 1)
    bh_total_return = float(bh_equity.iloc[-1] - 1)
    bh_sharpe = sharpe_ratio(portfolio_bh_ret)
    bh_max_dd = max_drawdown(bh_equity)

    colors_list = [
        '#8c674a', '#b28762', '#6d5a49', '#c49a73', '#5a4c3f',
        '#8e725d', '#b89d85', '#9a8268', '#735f4b', '#c1a17d',
    ]
    figure_specs = [
        {
            'name': '组合策略',
            'series': portfolio_equity,
            'color': '#ba7349',
            'dash': 'solid',
            'width': 3.0,
            'fill_alpha': 0.18,
            'drawdown_fill': True,
        },
        {
            'name': '买入持有基准',
            'series': bh_equity,
            'color': '#1f1914',
            'dash': 'dash',
            'width': 2.4,
            'fill_alpha': 0.10,
            'drawdown_fill': True,
        },
    ]

    for i, sym in enumerate(individual_results.keys()):
        sym_ret = individual_results[sym]['strategy_return']
        sym_ret_aligned = sym_ret.reindex(portfolio_equity.index).fillna(0)
        sym_equity = (1 + sym_ret_aligned).cumprod()
        figure_specs.append(
            {
                'name': f'{sym} 策略',
                'hover_name': sym,
                'series': sym_equity,
                'color': colors_list[i % len(colors_list)],
                'dash': 'dot',
                'width': 1.45,
                'fill_alpha': 0.08,
                'drawdown_fill': False,
            }
        )

    fig = create_equity_drawdown_chart(
        figure_specs,
        height=620,
        subplot_titles=('组合净值', '组合回撤'),
    )

    return {
        'fig': fig,
        'portfolio_equity': portfolio_equity,
        'bh_equity': bh_equity,
        'port_total_return': port_total_return,
        'port_sharpe': port_sharpe,
        'port_max_dd': port_max_dd,
        'bh_total_return': bh_total_return,
        'bh_sharpe': bh_sharpe,
        'bh_max_dd': bh_max_dd,
        'individual_results': individual_results,
        'weights': weights,
        'portfolio_strat_ret': portfolio_strat_ret,
    }


def bayesian_optimize_portfolio(
    stock_data_dict: dict,
    n_trials: int = 50,
    **fixed_params,
) -> dict | None:
    """
    贝叶斯优化组合参数：统一一套参数，优化目标为组合整体的夏普+收益-回撤

    参数：
        stock_data_dict: {股票代码: DataFrame}
        n_trials: 优化试验次数
        **fixed_params: 固定不变的策略参数

    返回：
        最佳参数字典，失败返回 None
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        st.error("需要安装 optuna 库。请运行：pip install optuna")
        return None

    best_result = {"score": -np.inf}

    def objective(trial):
        # 优化参数
        entry_threshold = trial.suggest_float("entry_threshold", -1.0, 2.0)
        exit_threshold = trial.suggest_float("exit_threshold", -2.0, 0.5)
        if entry_threshold <= exit_threshold:
            return -np.inf

        adx_threshold = trial.suggest_float("adx_threshold", 10, 35)
        stop_loss_mult = trial.suggest_float("stop_loss_mult", 0.5, 4.0)
        take_profit_mult = trial.suggest_float("take_profit_mult", 1.0, 6.0)
        weight_bb = trial.suggest_float("weight_bb", 0.0, 2.0)
        weight_obv = trial.suggest_float("weight_obv", 0.0, 2.0)
        weight_volume = trial.suggest_float("weight_volume", 0.0, 1.5)
        weight_price = trial.suggest_float("weight_price", 0.0, 1.5)
        weight_drawdown = trial.suggest_float("weight_drawdown", 0.0, 1.5)

        # 构建参数字典
        params = dict(fixed_params)
        params.update(
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            adx_threshold=adx_threshold,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
            weight_bb=weight_bb,
            weight_obv=weight_obv,
            weight_volume=weight_volume,
            weight_price=weight_price,
            weight_drawdown=weight_drawdown,
        )

        result = run_portfolio_simulation(stock_data_dict, **params)
        if result is None:
            return -np.inf

        score = result['port_sharpe'] + result['port_total_return'] - abs(result['port_max_dd']) * 0.5

        nonlocal best_result
        if score > best_result["score"]:
            best_result = {
                "score": score,
                "sharpe": result['port_sharpe'],
                "return": result['port_total_return'],
                "max_drawdown": result['port_max_dd'],
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "adx_threshold": adx_threshold,
                "stop_loss_mult": stop_loss_mult,
                "take_profit_mult": take_profit_mult,
                "weight_bb": weight_bb,
                "weight_obv": weight_obv,
                "weight_volume": weight_volume,
                "weight_price": weight_price,
                "weight_drawdown": weight_drawdown,
            }

        return score

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    return best_result if best_result["score"] > -np.inf else None
