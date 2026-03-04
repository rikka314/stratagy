"""
技术指标计算模块
================
RSI、MACD、EMA、ATR、ADX、布林带、OBV 等技术指标的计算。
"""

import numpy as np
import pandas as pd


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    计算 RSI（相对强弱指标）
    
    RSI 原理：
    - RSI 衡量价格上涨和下跌的相对强度
    - 取值范围 0-100
    - 通常 RSI > 70 表示超买，RSI < 30 表示超卖
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """
    计算滚动 Z 分数（标准化得分）
    Z = (当前值 - 均值) / 标准差
    """
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    z = (series - mean) / std
    return z.replace([np.inf, -np.inf], np.nan)


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """
    计算滚动百分位数（分位数排名，0-1之间）
    """
    def last_percentile(values: pd.Series) -> float:
        ranked = values.rank(pct=True)
        return float(ranked.iloc[-1])
    
    return series.rolling(window=window, min_periods=window).apply(last_percentile, raw=False)


def compute_macd(series: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算 MACD（指数平滑异同移动平均线）
    返回：(MACD线, 信号线, 柱状图)
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """
    计算 ATR（平均真实波幅）
    衡量市场波动性，用于设置止损和止盈位置。
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ],
        axis=1,
    ).max(axis=1)
    
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int) -> pd.Series:
    """
    计算 ADX（平均趋向指标）
    衡量趋势的强度（不是方向），ADX > 25 通常表示有明显趋势。
    """
    high = df["high"]
    low = df["low"]
    
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - df["close"].shift(1)).abs(),
            (low - df["close"].shift(1)).abs()
        ],
        axis=1,
    ).max(axis=1)
    
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    
    plus_di = (
        100
        * pd.Series(plus_dm, index=df.index)
        .ewm(alpha=1 / period, min_periods=period, adjust=False)
        .mean()
        / atr
    )
    minus_di = (
        100
        * pd.Series(minus_dm, index=df.index)
        .ewm(alpha=1 / period, min_periods=period, adjust=False)
        .mean()
        / atr
    )
    
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    
    return (100 * dx).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算布林带（Bollinger Bands）
    返回：(上轨, 中轨, 下轨)
    """
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """
    计算 OBV（能量潮指标，On-Balance Volume）
    OBV = 累积（方向 × 成交量）
    """
    price_change = df['close'].diff()
    direction = np.sign(price_change)
    obv = (direction * df['volume']).fillna(0).cumsum()
    return obv


def rolling_rank(series: pd.Series, window: int) -> pd.Series:
    """
    滚动排名标准化（更稳健的替代Z-score）
    取值范围：0-1（0=最小值，1=最大值）
    """
    def last_percentile(values: pd.Series) -> float:
        if len(values) < 2:
            return 0.5
        ranked = values.rank(pct=True)
        return float(ranked.iloc[-1])
    
    return series.rolling(window=window, min_periods=max(1, window//2)).apply(
        last_percentile, raw=False
    )


def add_indicators(
    df: pd.DataFrame,
    rsi_period: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    ema_fast: int,
    ema_slow: int,
    adx_period: int,
    atr_period: int,
    bb_period: int = 20,
    bb_std: float = 2.0,
    indicator_period: int = 20,
) -> pd.DataFrame:
    """
    为数据添加所有技术指标（"指标工厂"函数）
    
    一次性计算 RSI/MACD/EMA/ATR/ADX/布林带/OBV/成交量比率/价格位置 等。
    """
    df = df.copy()
    
    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    df["macd"], df["signal"], df["histogram"] = compute_macd(
        df["close"], fast=macd_fast, slow=macd_slow, signal=macd_signal
    )
    df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
    df["atr"] = compute_atr(df, period=atr_period)
    df["adx"] = compute_adx(df, period=adx_period)
    
    # 布林带
    df["bb_upper"], df["bb_middle"], df["bb_lower"] = compute_bollinger_bands(
        df["close"], period=bb_period, std_dev=bb_std
    )
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = np.where(bb_range > 0, (df["close"] - df["bb_lower"]) / bb_range, 0.5)
    df["bb_width"] = bb_range / df["close"]
    
    # OBV
    df["obv"] = compute_obv(df)
    df["obv_trend"] = df["obv"].pct_change(indicator_period)
    
    # 成交量比率
    avg_volume = df["volume"].rolling(indicator_period).mean()
    df["volume_ratio"] = df["volume"] / avg_volume
    
    # 回撤
    cummax = df["close"].cummax()
    df["drawdown"] = (df["close"] / cummax - 1)
    
    # 价格相对位置
    period_high = df["high"].rolling(indicator_period).max()
    period_low = df["low"].rolling(indicator_period).min()
    price_range = period_high - period_low
    df["price_position"] = np.where(price_range > 0, (df["close"] - period_low) / price_range, 0.5)
    
    return df
