"""
评估模块
========
多模型统一评估接口。复用 backtest.py 已有指标函数，不重复实现。
"""

from __future__ import annotations

import pandas as pd

from core.backtest import max_drawdown, sharpe_ratio


def compute_performance_metrics(
    equity_series: pd.Series,
    benchmark_series: pd.Series,
    risk_free: float = 0.0,
) -> dict:
    """
    计算策略绩效指标。

    参数
    ----
    equity_series   : 策略净值曲线（起点=1，如 strategy_equity）
    benchmark_series: 基准净值曲线（起点=1，如 buy_hold_equity）
    risk_free       : 无风险利率（年化，默认0）

    返回
    ----
    dict，key：
        cumret      累计收益率
        annret      年化收益率（×252交易日）
        maxdd       最大回撤（负数，如 -0.25）
        sharpe      年化夏普比率（×√252）
        bench_cumret    基准累计收益率
        bench_annret    基准年化收益率
        bench_maxdd     基准最大回撤
        bench_sharpe    基准夏普比率
        excess_return   超额收益（cumret - bench_cumret）
    """
    def _metrics(eq: pd.Series) -> tuple[float, float, float, float]:
        n = len(eq)
        cumret = float(eq.iloc[-1] / eq.iloc[0] - 1) if n > 0 else 0.0
        annret = float((eq.iloc[-1] / eq.iloc[0]) ** (252 / n) - 1) if n > 1 else 0.0
        mdd = max_drawdown(eq)
        daily_ret = eq.pct_change().fillna(0.0)
        if risk_free != 0.0:
            daily_ret = daily_ret - risk_free / 252
        sp = sharpe_ratio(daily_ret)
        return cumret, annret, mdd, sp

    s_cumret, s_annret, s_mdd, s_sharpe = _metrics(equity_series)
    b_cumret, b_annret, b_mdd, b_sharpe = _metrics(benchmark_series)

    return {
        "cumret": s_cumret,
        "annret": s_annret,
        "maxdd": s_mdd,
        "sharpe": s_sharpe,
        "bench_cumret": b_cumret,
        "bench_annret": b_annret,
        "bench_maxdd": b_mdd,
        "bench_sharpe": b_sharpe,
        "excess_return": s_cumret - b_cumret,
    }


def compute_trade_stats(
    trades_df: pd.DataFrame | None,
    n_trading_days: int | None = None,
) -> dict[str, float | None]:
    """
    基于 `extract_trades()` 输出的逐笔表汇总交易统计。

    参数
    ----
    trades_df       : 列含 entry_date / exit_date / hold_days / trade_return / is_win（可为空表）
    n_trading_days  : 回测区间总交易日数；用于换手率 = 开仓次数 / 总交易日数。
                      不传则 turnover 为 None（由上层用净值序列长度等填入）。

    返回
    ----
    dict，key 与 week3 `evaluate_strategy` 对齐预留：
        winrate    胜率（盈利笔数 / 总笔数）
        pnl_ratio  盈亏比 = 盈利笔平均收益率 / 亏损笔平均收益率的绝对值；无亏损笔或无盈利笔时 None
        avg_hold   平均持仓天数（hold_days 均值）
        turnover   换手率 = 开仓次数（笔数）/ n_trading_days；n_trading_days 缺省为 None
    """
    empty_stats: dict[str, float | None] = {
        "winrate": None,
        "pnl_ratio": None,
        "avg_hold": None,
        "turnover": None,
    }

    if trades_df is None or trades_df.empty:
        if n_trading_days is not None and n_trading_days > 0:
            empty_stats["turnover"] = 0.0
        return empty_stats

    required = {"hold_days", "trade_return"}
    missing = required - set(trades_df.columns)
    if missing:
        raise ValueError(f"compute_trade_stats: trades_df 缺少列 {sorted(missing)}")

    n_trades = len(trades_df)
    ret = pd.to_numeric(trades_df["trade_return"], errors="coerce")

    if "is_win" in trades_df.columns:
        is_win = trades_df["is_win"]
        if is_win.dtype != bool:
            is_win = pd.to_numeric(is_win, errors="coerce")
        wins = int(pd.Series(is_win).fillna(0).astype(int).clip(lower=0, upper=1).sum())
    else:
        wins = int((ret > 0).sum())

    winrate = float(wins / n_trades) if n_trades else None

    gains = ret[ret > 0]
    losses = ret[ret < 0]
    avg_gain = float(gains.mean()) if len(gains) else None
    avg_loss_abs = float(losses.abs().mean()) if len(losses) else None

    if avg_gain is not None and avg_loss_abs is not None and avg_loss_abs > 0:
        pnl_ratio = float(avg_gain / avg_loss_abs)
    else:
        pnl_ratio = None

    hold = pd.to_numeric(trades_df["hold_days"], errors="coerce")
    avg_hold = float(hold.mean()) if hold.notna().any() else None

    turnover: float | None
    if n_trading_days is not None and n_trading_days > 0:
        turnover = float(n_trades / n_trading_days)
    else:
        turnover = None

    return {
        "winrate": winrate,
        "pnl_ratio": pnl_ratio,
        "avg_hold": avg_hold,
        "turnover": turnover,
    }


def evaluate_strategy(
    label: str,
    equity_series: pd.Series,
    benchmark_series: pd.Series,
    trades_df: pd.DataFrame | None = None,
    risk_free: float = 0.0,
) -> dict:
    """
    统一的多模型评估顶层接口。

    参数
    ----
    label            : 模型/策略名称（如 "SM"、"Naive"）
    equity_series    : 策略净值曲线
    benchmark_series : 基准净值曲线
    trades_df        : 逐笔交易明细表（可选）
    risk_free        : 无风险利率

    返回
    ----
    合并的指标字典，包含核心及交易层指标，统一供展示使用。
    """
    metrics = compute_performance_metrics(
        equity_series=equity_series,
        benchmark_series=benchmark_series,
        risk_free=risk_free,
    )

    n_days = len(equity_series) if equity_series is not None and len(equity_series) > 0 else None

    trade_stats = compute_trade_stats(
        trades_df=trades_df,
        n_trading_days=n_days,
    )

    return {
        "label": label,
        "cumret": metrics["cumret"],
        "annret": metrics["annret"],
        "maxdd": metrics["maxdd"],
        "sharpe": metrics["sharpe"],
        "bench_cumret": metrics["bench_cumret"],
        "bench_annret": metrics["bench_annret"],
        "bench_maxdd": metrics["bench_maxdd"],
        "bench_sharpe": metrics["bench_sharpe"],
        "excess_return": metrics["excess_return"],
        "winrate": trade_stats["winrate"],
        "pnl_ratio": trade_stats["pnl_ratio"],
        "avg_hold": trade_stats["avg_hold"],
        "turnover": trade_stats["turnover"],
    }


def build_comparison_table(results: list[dict]) -> pd.DataFrame:
    """
    将多个 `evaluate_strategy()` 的结果字典转成可直接展示的对比表。

    约束
    ----
    - 自动补齐缺失 key（填 pd.NA）
    - 列顺序稳定：label → 收益/回撤/夏普 → 逐笔统计 → 基准四项 → excess_return；其余 key 排在末尾
    """
    columns = [
        "label",
        "cumret",
        "annret",
        "maxdd",
        "sharpe",
        "winrate",
        "pnl_ratio",
        "avg_hold",
        "turnover",
        "bench_cumret",
        "bench_annret",
        "bench_maxdd",
        "bench_sharpe",
        "excess_return",
    ]

    if not results:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(results)
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA

    extra_cols = [c for c in df.columns if c not in columns]
    df = df[columns + extra_cols]

    # 尝试把数值列转为 numeric，便于排序/格式化；失败的保持原样
    numeric_cols = [c for c in columns if c != "label"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df

