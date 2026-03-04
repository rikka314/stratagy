"""
策略信号计算模块
================
10因子加权评分 → 7档仓位 → 买卖信号生成。
"""

import numpy as np
import pandas as pd

from core.indicators import rolling_zscore, rolling_percentile, rolling_rank


def compute_signals(
    df: pd.DataFrame,
    rsi_lower: float,
    rsi_upper: float,
    adx_threshold: float,
    momentum_short: int,
    momentum_long: int,
    score_lookback: int,
    score_mid_pct: float,
    score_high_pct: float,
    weight_mom_short: float,
    weight_mom_long: float,
    weight_macd: float,
    weight_rsi: float,
    weight_vol: float,
    entry_threshold: float,
    exit_threshold: float,
    # 指标开关参数
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    # Phase 1 新因子权重参数
    weight_bb: float = 0.8,
    weight_obv: float = 1.0,
    weight_volume: float = 0.6,
    weight_price: float = 0.7,
    weight_drawdown: float = 0.5,
    # 入场逻辑选择
    use_voting_entry: bool = False,
    entry_vote_threshold: float = 2.5,
    # 出场信号计数阈值
    exit_min_signals: int = 2,
    # 入场信号计数阈值（0=使用旧逻辑，>0=计数制）
    entry_min_signals: int = 3,
) -> pd.DataFrame:
    """
    计算交易信号和目标仓位（核心策略函数）
    
    10因子评分系统 → 7档仓位管理 → 入场/出场信号生成。
    """
    df = df.copy()
    
    # ========== 步骤1：计算过滤条件 ==========
    df["trend_ok"] = df["ema_fast"] > df["ema_slow"]
    df["strength_ok"] = df["adx"] >= adx_threshold
    df["rsi_ok"] = (df["rsi"] > rsi_lower) & (df["rsi"] < rsi_upper)
    
    # ========== 步骤2：计算动量和波动率因子 ==========
    df["ret_short"] = df["close"].pct_change(momentum_short)
    df["ret_long"] = df["close"].pct_change(momentum_long)
    df["volatility"] = df["atr"] / df["close"]
    
    # ========== 步骤3：标准化因子 ==========
    # 原有因子：Z-score
    df["mom_short_z"] = rolling_zscore(df["ret_short"], score_lookback)
    df["mom_long_z"] = rolling_zscore(df["ret_long"], score_lookback)
    df["macd_z"] = rolling_zscore(df["histogram"], score_lookback)
    df["rsi_z"] = rolling_zscore(df["rsi"], score_lookback)
    df["vol_z"] = rolling_zscore(df["volatility"], score_lookback)
    
    # 新增因子：排名法
    df["bb_position_rank"] = rolling_rank(df["bb_position"], score_lookback)
    df["obv_trend_rank"] = rolling_rank(df["obv_trend"], score_lookback)
    df["volume_ratio_rank"] = rolling_rank(df["volume_ratio"], score_lookback)
    df["price_position_rank"] = rolling_rank(df["price_position"], score_lookback)
    df["drawdown_rank"] = rolling_rank(df["drawdown"], score_lookback)
    
    # ========== 步骤4：计算综合因子评分 ==========
    df["factor_score"] = (
        weight_mom_short * df["mom_short_z"]
        + weight_mom_long * df["mom_long_z"]
        + weight_macd * df["macd_z"]
        + weight_rsi * df["rsi_z"]
        - weight_vol * df["vol_z"]
        + weight_bb * (df["bb_position_rank"] - 0.5) * 2
        + weight_obv * (df["obv_trend_rank"] - 0.5) * 2
        + weight_volume * (df["volume_ratio_rank"] - 0.5) * 2
        + weight_price * (df["price_position_rank"] - 0.5) * 2
        - weight_drawdown * (df["drawdown_rank"] - 0.5) * 2
    )
    df["factor_score"] = df["factor_score"].fillna(0.0)
    
    # ========== 步骤5：因子评分分位数 ==========
    df["factor_percentile"] = rolling_percentile(df["factor_score"], score_lookback).fillna(0.0)
    
    # ========== 步骤6：7档仓位管理 ==========
    score_position = np.select(
        [
            df["factor_percentile"] >= 0.80,
            df["factor_percentile"] >= 0.65,
            df["factor_percentile"] >= 0.55,
            df["factor_percentile"] >= 0.45,
            df["factor_percentile"] >= 0.35,
        ],
        [1.0, 0.8, 0.6, 0.4, 0.2],
        default=0.0
    )
    
    # 波动率调整
    volatility_percentile = rolling_percentile(df["volatility"], score_lookback).fillna(0.5)
    vol_adjustment = np.where(volatility_percentile > 0.8, 0.7, 1.0)
    score_position = score_position * vol_adjustment
    
    # ========== 步骤7：入场过滤 ==========
    macd_above = df["macd"] > df["signal"]
    
    if entry_min_signals > 0:
        # 计数制入场
        entry_count = pd.Series(0, index=df.index, dtype=int)
        entry_count += (df["factor_score"] >= entry_threshold).astype(int)
        entry_count += df["trend_ok"].astype(int)
        entry_count += df["strength_ok"].astype(int)
        entry_count += df["rsi_ok"].astype(int)
        entry_count += macd_above.astype(int)
        filter_ok = entry_count >= entry_min_signals
    
    elif use_voting_entry:
        # 评分制入场
        df["entry_vote_score"] = 0.0
        df["entry_vote_score"] += np.where(df["factor_score"] >= entry_threshold, 2.0, 0.0)
        if use_trend_filter:
            df["entry_vote_score"] += np.where(df["trend_ok"], 1.0, 0.0)
        if use_strength_filter:
            df["entry_vote_score"] += np.where(df["strength_ok"], 1.0, 0.0)
        if use_rsi_filter:
            df["entry_vote_score"] += np.where(df["rsi_ok"], 0.5, 0.0)
        if use_macd_filter:
            df["entry_vote_score"] += np.where(macd_above, 0.5, 0.0)
        filter_ok = df["entry_vote_score"] >= entry_vote_threshold
        
    else:
        # 严格AND入场
        filter_conditions = [df["factor_score"] >= entry_threshold]
        if use_trend_filter:
            filter_conditions.append(df["trend_ok"])
        if use_strength_filter:
            filter_conditions.append(df["strength_ok"])
        if use_rsi_filter:
            filter_conditions.append(df["rsi_ok"])
        if use_macd_filter:
            filter_conditions.append(macd_above)
        
        if len(filter_conditions) > 0:
            filter_ok = filter_conditions[0]
            for condition in filter_conditions[1:]:
                filter_ok = filter_ok & condition
        else:
            filter_ok = pd.Series([True] * len(df), index=df.index)
    
    df["target_position"] = np.where(filter_ok, score_position, 0.0)
    
    # ========== 步骤8：出场条件（计数制）==========
    exit_count = pd.Series(0, index=df.index, dtype=int)
    exit_count += (df["factor_score"] <= exit_threshold).astype(int)
    if use_trend_filter:
        exit_count += (df["ema_fast"] < df["ema_slow"]).astype(int)
    if use_rsi_filter:
        exit_count += ((df["rsi"] > rsi_upper) | (df["rsi"] < rsi_lower)).astype(int)
    if use_macd_filter:
        exit_count += (df["macd"] < df["signal"]).astype(int)
    
    exit_block = exit_count >= exit_min_signals
    df.loc[exit_block, "target_position"] = 0.0
    
    # ========== 步骤9：生成买卖信号 ==========
    df["buy_signal"] = (df["target_position"] > 0) & (df["target_position"].shift(1) <= 0)
    df["sell_signal"] = (df["target_position"] <= 0) & (df["target_position"].shift(1) > 0)
    
    return df
