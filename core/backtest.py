"""
回测引擎模块
============
策略回测模拟、评估指标（最大回撤/夏普比率）、Walk-Forward 回测。
"""

from typing import Literal, overload

import numpy as np
import pandas as pd

from core.market_rules import MarketExecutionConfig, get_active_execution_config


@overload
def simulate_strategy(
    df: pd.DataFrame,
    initial_position: int = 0,
    stop_loss_mult: float = 0.0,
    take_profit_mult: float = 0.0,
    return_trades: Literal[False] = False,
    *,
    execution_config: MarketExecutionConfig | None = None,
) -> pd.DataFrame: ...


@overload
def simulate_strategy(
    df: pd.DataFrame,
    initial_position: int = 0,
    stop_loss_mult: float = 0.0,
    take_profit_mult: float = 0.0,
    *,
    return_trades: Literal[True],
    execution_config: MarketExecutionConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]: ...


def simulate_strategy(
    df: pd.DataFrame,
    initial_position: int = 0,
    stop_loss_mult: float = 0.0,
    take_profit_mult: float = 0.0,
    return_trades: bool = False,
    *,
    execution_config: MarketExecutionConfig | None = None,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """
    模拟策略执行，计算收益曲线

    支持动态仓位、ATR止损止盈、策略收益 vs 买入持有对比。
    return_trades=True 时额外返回 extract_trades(df) 的逐笔明细。
    """
    df = df.copy()
    # The interactive/UI default remains zero-cost.  Offline research opts in
    # through a context-local configuration so every nested pipeline backtest
    # uses the same frozen market assumptions.
    if execution_config is None:
        execution_config = get_active_execution_config()
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
    gross_strategy_return = df["position"].shift(1).fillna(initial_position) * returns

    if execution_config is not None:
        previous_position = df["position"].shift(1).fillna(0.0)
        turnover = (df["position"] - previous_position).abs()
        transaction_cost = turnover * execution_config.total_cost_rate
        df["turnover"] = turnover
        df["transaction_cost"] = transaction_cost
        df["gross_strategy_return"] = gross_strategy_return
        df["strategy_return"] = gross_strategy_return - transaction_cost
    else:
        df["strategy_return"] = gross_strategy_return

    df["strategy_equity"] = (1 + df["strategy_return"]).cumprod()
    df["buy_hold_equity"] = (1 + returns).cumprod()

    if return_trades:
        trades_df = extract_trades(df, initial_position=initial_position)
        return df, trades_df
    return df


def extract_trades(
    df: pd.DataFrame,
    position_col: str = "position",
    eps: float = 1e-8,
    initial_position: int = 0,
) -> pd.DataFrame:
    """
    从回测结果 df 中提取逐笔交易明细。

    规则（与 week3 计划对齐）：
    - `position` 连续的非零段（position > eps）视为“一笔交易”
    - 输出逐笔交易的 entry/exit/持有天数/收益/胜负

    trade_return 的口径与 `simulate_strategy` 的 `strategy_return` 对齐：
    - 先用 `close.pct_change()` 得到日收益
    - 用 `position.shift(1).fillna(initial_position)` 缩放日收益（与 `simulate_strategy` 一致）
    - 对每笔交易区间做复利累积，得到 trade_return

    注意：平仓当日 `position` 已为 0，但当日 `strategy_return` 仍按前一日仓位计入涨跌，
    因此复利区间需包含「平仓日」这一行，否则会漏掉最后一日的策略收益。
    """
    if position_col not in df.columns:
        raise ValueError(f"extract_trades: missing required column `{position_col}`")
    if "close" not in df.columns:
        raise ValueError("extract_trades: missing required column `close`")

    has_execution_details = any(
        column in df.columns for column in ("turnover", "transaction_cost", "gross_strategy_return")
    )
    base_columns = ["entry_date", "exit_date", "hold_days", "trade_return", "is_win"]
    execution_columns = [
        "gross_trade_return",
        "trade_turnover",
        "trade_transaction_cost",
    ]

    if df.empty:
        columns = base_columns[:4] + execution_columns + base_columns[4:] if has_execution_details else base_columns
        return pd.DataFrame(columns=columns)

    # 强制数值化，避免 position 为 object/字符串导致比较异常
    pos = pd.to_numeric(df[position_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    close = df["close"]

    if has_execution_details and "strategy_return" in df.columns:
        strategy_return = pd.to_numeric(df["strategy_return"], errors="coerce").fillna(0.0)
    else:
        daily_returns = close.pct_change().fillna(0.0)
        pos_prev = pd.to_numeric(df[position_col].shift(1), errors="coerce").fillna(float(initial_position))
        strategy_return = pos_prev * daily_returns

    turnover = pd.to_numeric(df.get("turnover", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0)
    transaction_cost = pd.to_numeric(
        df.get("transaction_cost", pd.Series(0.0, index=df.index)), errors="coerce"
    ).fillna(0.0)
    gross_strategy_return = pd.to_numeric(
        df.get("gross_strategy_return", strategy_return), errors="coerce"
    ).fillna(0.0)

    active = pos > eps
    n = len(active)

    dates = df["date"] if "date" in df.columns else pd.Series(range(n))

    trades = []
    start_idx = None

    for i in range(n):
        if active[i] and start_idx is None:
            start_idx = i
        # 当从 active -> inactive，结束当前交易段
        if start_idx is not None and (not active[i]):
            end_idx = i - 1  # 最后一行仍持仓（position > eps）
            exit_row = i  # 平仓当日 position==0，但 strategy_return 仍含当日损益
            trade_returns = strategy_return.iloc[start_idx : exit_row + 1]
            trade_equity = (1.0 + trade_returns).cumprod()
            trade_ret = float(trade_equity.iloc[-1] - 1.0)
            gross_trade_return = float(
                (1.0 + gross_strategy_return.iloc[start_idx : exit_row + 1]).prod() - 1.0
            )

            entry_date = dates.iloc[start_idx] if len(dates) == n else start_idx
            exit_date = dates.iloc[end_idx] if len(dates) == n else end_idx
            hold_days = int(end_idx - start_idx + 1)

            trade = {
                "entry_date": entry_date,
                "exit_date": exit_date,
                "hold_days": hold_days,
                "trade_return": trade_ret,
                "is_win": bool(trade_ret > 0),
            }
            if has_execution_details:
                trade.update(
                    gross_trade_return=gross_trade_return,
                    trade_turnover=float(turnover.iloc[start_idx : exit_row + 1].sum()),
                    trade_transaction_cost=float(transaction_cost.iloc[start_idx : exit_row + 1].sum()),
                )
            trades.append(trade)
            start_idx = None

    # 若最后一个区间一直 active 到末尾
    if start_idx is not None:
        end_idx = n - 1
        trade_returns = strategy_return.iloc[start_idx : end_idx + 1]
        trade_equity = (1.0 + trade_returns).cumprod()
        trade_ret = float(trade_equity.iloc[-1] - 1.0)
        gross_trade_return = float(
            (1.0 + gross_strategy_return.iloc[start_idx : end_idx + 1]).prod() - 1.0
        )

        entry_date = dates.iloc[start_idx] if len(dates) == n else start_idx
        exit_date = dates.iloc[end_idx] if len(dates) == n else end_idx
        hold_days = int(end_idx - start_idx + 1)

        trade = {
            "entry_date": entry_date,
            "exit_date": exit_date,
            "hold_days": hold_days,
            "trade_return": trade_ret,
            "is_win": bool(trade_ret > 0),
        }
        if has_execution_details:
            trade.update(
                gross_trade_return=gross_trade_return,
                trade_turnover=float(turnover.iloc[start_idx : end_idx + 1].sum()),
                trade_transaction_cost=float(transaction_cost.iloc[start_idx : end_idx + 1].sum()),
            )
        trades.append(trade)

    columns = base_columns[:4] + execution_columns + base_columns[4:] if has_execution_details else base_columns
    return pd.DataFrame(trades, columns=columns)


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
    execution_config: MarketExecutionConfig | None = None,
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
            execution_config=execution_config,
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
