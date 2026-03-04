"""
回测引擎模块
============
策略回测模拟、评估指标（最大回撤/夏普比率）、Walk-Forward 回测。
"""

import numpy as np
import pandas as pd


def simulate_strategy(
    df: pd.DataFrame,
    initial_position: int = 0,
    stop_loss_mult: float = 0.0,
    take_profit_mult: float = 0.0,
) -> pd.DataFrame:
    """
    模拟策略执行，计算收益曲线
    
    支持动态仓位、ATR止损止盈、策略收益 vs 买入持有对比。
    """
    df = df.copy()
    position = np.zeros(len(df))
    in_position = initial_position == 1
    entry_price = df["close"].iloc[0] if in_position and len(df) > 0 else np.nan
    entry_atr = df["atr"].iloc[0] if in_position and len(df) > 0 else np.nan
    
    if len(df) > 0:
        position[0] = initial_position
    
    for i in range(1, len(df)):
        if "target_position" in df.columns:
            desired_pos = float(np.clip(df["target_position"].iloc[i], 0.0, 1.0))
            
            if not in_position:
                if desired_pos > 0:
                    in_position = True
                    entry_price = df["close"].iloc[i]
                    entry_atr = df["atr"].iloc[i]
                    position[i] = desired_pos
            else:
                exit_triggered = desired_pos == 0
                
                if "sell_signal" in df.columns and df["sell_signal"].iloc[i]:
                    exit_triggered = True
                
                if not np.isnan(entry_atr):
                    if stop_loss_mult > 0:
                        stop_price = entry_price - stop_loss_mult * entry_atr
                        if df["low"].iloc[i] <= stop_price:
                            exit_triggered = True
                    if take_profit_mult > 0:
                        take_price = entry_price + take_profit_mult * entry_atr
                        if df["high"].iloc[i] >= take_price:
                            exit_triggered = True
                
                if exit_triggered:
                    in_position = False
                    entry_price = np.nan
                    entry_atr = np.nan
                    position[i] = 0.0
                else:
                    position[i] = desired_pos
        else:
            if not in_position:
                if df["buy_signal"].iloc[i]:
                    in_position = True
                    entry_price = df["close"].iloc[i]
                    entry_atr = df["atr"].iloc[i]
            else:
                exit_triggered = df["sell_signal"].iloc[i]
                
                if not np.isnan(entry_atr):
                    if stop_loss_mult > 0:
                        stop_price = entry_price - stop_loss_mult * entry_atr
                        if df["low"].iloc[i] <= stop_price:
                            exit_triggered = True
                    if take_profit_mult > 0:
                        take_price = entry_price + take_profit_mult * entry_atr
                        if df["high"].iloc[i] >= take_price:
                            exit_triggered = True
                
                if exit_triggered:
                    in_position = False
                    entry_price = np.nan
                    entry_atr = np.nan
            
            position[i] = 1 if in_position else 0
    
    df["position"] = position
    returns = df["close"].pct_change().fillna(0)
    df["strategy_return"] = df["position"].shift(1).fillna(initial_position) * returns
    df["strategy_equity"] = (1 + df["strategy_return"]).cumprod()
    df["buy_hold_equity"] = (1 + returns).cumprod()
    
    return df


def max_drawdown(equity: pd.Series) -> float:
    """
    计算最大回撤
    返回负数（如 -0.25 表示回撤 25%）。
    """
    roll_max = equity.cummax()
    drawdown = equity / roll_max - 1
    return float(drawdown.min())


def sharpe_ratio(returns: pd.Series) -> float:
    """
    计算年化夏普比率
    Sharpe = (平均日收益 / 日收益标准差) × √252
    """
    std = returns.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((returns.mean() / std) * np.sqrt(252))


def walk_forward_backtest(
    df: pd.DataFrame,
    train_window: int,
    test_window: int,
    stop_loss_mult: float,
    take_profit_mult: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Walk-Forward 回测（滚动窗口回测）
    
    训练/测试分离，滚动验证策略稳定性。
    返回：(结果汇总 DataFrame, 完整净值曲线 DataFrame)
    """
    results = []
    equity_curve = []
    start_idx = 0
    
    while start_idx + train_window < len(df):
        train_end = start_idx + train_window
        test_end = min(train_end + test_window, len(df))
        test_slice = df.iloc[train_end:test_end]
        
        if test_slice.empty:
            break
        
        test_sim = simulate_strategy(
            test_slice,
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        total_return = test_sim["strategy_equity"].iloc[-1] - 1
        
        results.append(
            {
                "window_start": test_slice["date"].iloc[0],
                "window_end": test_slice["date"].iloc[-1],
                "test_return": total_return,
                "test_sharpe": sharpe_ratio(test_sim["strategy_return"]),
                "test_max_drawdown": max_drawdown(test_sim["strategy_equity"]),
            }
        )
        
        segment = test_sim[["date", "strategy_equity", "buy_hold_equity"]].copy()
        
        if equity_curve:
            prev_end = equity_curve[-1]["strategy_equity"].iloc[-1]
            prev_bh_end = equity_curve[-1]["buy_hold_equity"].iloc[-1]
            segment["strategy_equity"] *= prev_end
            segment["buy_hold_equity"] *= prev_bh_end
        
        equity_curve.append(segment)
        start_idx += test_window
    
    if equity_curve:
        equity_df = pd.concat(equity_curve, ignore_index=True)
    else:
        equity_df = pd.DataFrame(columns=["date", "strategy_equity", "buy_hold_equity"])
    
    return pd.DataFrame(results), equity_df
