"""
量化交易策略分析应用
====================
这是一个基于 Streamlit 的 Web 应用，用于分析和回测股票交易策略。
主要功能：
1. 从 AkShare 下载美股数据
2. 计算技术指标（RSI、MACD、EMA、ATR、ADX等）
3. 基于因子评分的量化交易策略
4. 回测策略表现并与买入持有策略对比
5. 多股票对比分析和相关性分析
"""

# 导入必需的库
import io  # 用于处理字节流（上传文件时使用）
import os  # 用于文件和目录操作

import akshare as ak  # AkShare：国产金融数据接口库，用于下载股票数据
import numpy as np  # NumPy：数值计算库
import pandas as pd  # Pandas：数据分析库，处理表格数据
import plotly.graph_objects as go  # Plotly：交互式图表库
from plotly.subplots import make_subplots  # 用于创建子图
import streamlit as st  # Streamlit：快速构建 Web 应用的框架


# ============ 全局常量配置 ============
DATA_DIR = "data"  # 数据存储目录
DEFAULT_SYMBOL = "AAPL"  # 默认股票代码（苹果公司）
DEFAULT_ADJUST = "qfq"  # 默认复权方式：前复权（qfq=前复权，hfq=后复权，none=不复权）


# ============ 数据预处理函数 ============

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化 DataFrame 的列名
    
    功能说明：
    1. 将所有列名转换为小写并去除空格
    2. 统一不同数据源的列名差异（如 trade_date → date, vol → volume）
    
    参数：
        df: 原始 DataFrame
    
    返回：
        标准化后的 DataFrame
    """
    df = df.copy()  # 创建副本，避免修改原始数据
    
    # 步骤1：将所有列名转为小写并去除首尾空格
    df.columns = [c.strip().lower() for c in df.columns]
    
    # 步骤2：建立列名映射字典，统一不同数据源的命名差异
    rename_map = {}
    
    # 日期列的统一：trade_date 或 datetime → date
    if "trade_date" in df.columns and "date" not in df.columns:
        rename_map["trade_date"] = "date"
    if "datetime" in df.columns and "date" not in df.columns:
        rename_map["datetime"] = "date"
    
    # 成交量列的统一：vol 或 volumn → volume
    if "vol" in df.columns and "volume" not in df.columns:
        rename_map["vol"] = "volume"
    if "volumn" in df.columns and "volume" not in df.columns:
        rename_map["volumn"] = "volume"
    
    # 步骤3：应用列名重命名
    if rename_map:
        df = df.rename(columns=rename_map)
    
    return df


def ensure_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保 DataFrame 有合法的日期列
    
    功能说明：
    1. 如果有 date 列，转换为日期格式并排序
    2. 如果没有 date 列，创建一个索引序列（1, 2, 3...）
    
    参数：
        df: 输入 DataFrame
    
    返回：
        包含 date 列的 DataFrame
    """
    df = df.copy()
    
    # 情况1：如果已有 date 列
    if "date" in df.columns:
        # 转换为日期时间格式，errors='coerce' 表示无法转换的值设为 NaT（Not a Time）
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        
        # 删除日期转换失败的行
        df = df.dropna(subset=["date"])
        
        # 按日期排序（确保数据按时间顺序）
        df = df.sort_values("date")
        return df
    
    # 情况2：如果没有 date 列，创建一个数字索引作为"日期"
    df["date"] = pd.RangeIndex(start=1, stop=len(df) + 1, step=1)
    return df


def fetch_data(symbol: str, adjust: str) -> pd.DataFrame:
    """
    从 AkShare 下载美股日线数据
    
    参数：
        symbol: 股票代码（如 'AAPL', 'TSLA'）
        adjust: 复权方式 ('qfq'=前复权, 'hfq'=后复权, 'none'=不复权)
    
    返回：
        包含开高低收成交量的 DataFrame
    
    注意：
        - 复权是指调整历史价格以反映分红、拆股等公司行为
        - 前复权：保持最新价格不变，调整历史价格
        - 后复权：保持历史价格不变，调整最新价格
    """
    # 从 AkShare 下载数据
    df = ak.stock_us_daily(symbol=symbol, adjust=adjust)
    
    # 标准化列名
    df = standardize_columns(df)
    
    # 确保第一列是 date
    if "date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "date"})
    
    # 确保日期列正确
    df = ensure_date_column(df)
    
    # 将价格和成交量列转换为数值类型
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # 删除价格数据缺失的行
    df = df.dropna(subset=["open", "high", "low", "close"])
    
    return df


@st.cache_data(show_spinner=False, ttl=3600)  # Streamlit 缓存装饰器：避免重复读取同一文件，1小时后缓存失效
def load_csv(path: str) -> pd.DataFrame:
    """
    从本地 CSV 文件加载数据
    
    参数：
        path: CSV 文件路径
    
    返回：
        标准化后的 DataFrame
    
    注意：
        缓存有效期为1小时（3600秒），确保数据不会过时
    """
    df = pd.read_csv(path)
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


@st.cache_data(show_spinner=False)  # 缓存上传的文件，避免重复处理
def load_uploaded_bytes(data: bytes) -> pd.DataFrame:
    """
    从上传的字节数据加载 CSV
    
    参数：
        data: 文件的字节数据
    
    返回：
        标准化后的 DataFrame
    """
    # 使用 BytesIO 将字节数据转换为文件对象
    df = pd.read_csv(io.BytesIO(data))
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


# ============ 技术指标计算函数 ============

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    计算 RSI（相对强弱指标）
    
    RSI 原理：
    - RSI 衡量价格上涨和下跌的相对强度
    - 取值范围 0-100
    - 通常 RSI > 70 表示超买（可能下跌），RSI < 30 表示超卖（可能上涨）
    
    计算公式：
        RSI = 100 - 100 / (1 + RS)
        其中 RS = 平均涨幅 / 平均跌幅
    
    参数：
        series: 价格序列（通常是收盘价）
        period: 计算周期（默认14天）
    
    返回：
        RSI 值序列
    """
    # 计算价格变化量（今日价格 - 昨日价格）
    delta = series.diff()
    
    # 分离涨跌：涨幅为正数，跌幅取绝对值
    gain = delta.clip(lower=0)  # 只保留正数（涨幅）
    loss = -delta.clip(upper=0)  # 只保留负数并取反（跌幅）
    
    # 计算指数移动平均（EWM = Exponentially Weighted Moving Average）
    # alpha=1/period 是平滑系数
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    
    # 计算相对强度 RS = 平均涨幅 / 平均跌幅
    rs = avg_gain / avg_loss
    
    # 计算 RSI
    return 100 - (100 / (1 + rs))


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """
    计算滚动 Z 分数（标准化得分）
    
    Z 分数原理：
    - 衡量当前值相对于历史平均值的偏离程度
    - Z = (当前值 - 均值) / 标准差
    - Z > 0 表示高于平均，Z < 0 表示低于平均
    - |Z| > 2 通常被认为是异常值
    
    参数：
        series: 数据序列
        window: 滚动窗口大小
    
    返回：
        Z 分数序列
    """
    # 计算滚动均值
    mean = series.rolling(window=window, min_periods=window).mean()
    
    # 计算滚动标准差
    std = series.rolling(window=window, min_periods=window).std()
    
    # 计算 Z 分数
    z = (series - mean) / std
    
    # 替换无穷值为 NaN（避免除以0的情况）
    return z.replace([np.inf, -np.inf], np.nan)


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """
    计算滚动百分位数（分位数排名）
    
    百分位数原理：
    - 衡量当前值在历史数据中的排名位置
    - 取值范围 0-1（或 0%-100%）
    - 0.8 表示超过历史 80% 的数据
    
    参数：
        series: 数据序列
        window: 滚动窗口大小
    
    返回：
        百分位数序列（0-1之间的值）
    """
    def last_percentile(values: pd.Series) -> float:
        """计算窗口内最后一个值的百分位排名"""
        ranked = values.rank(pct=True)  # pct=True 返回百分比排名
        return float(ranked.iloc[-1])  # 返回最后一个值的排名
    
    # 对每个滚动窗口应用 last_percentile 函数
    return series.rolling(window=window, min_periods=window).apply(last_percentile, raw=False)


def compute_macd(series: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算 MACD（指数平滑异同移动平均线）
    
    MACD 原理：
    - MACD 是趋势跟踪指标，用于判断买卖时机
    - 由三部分组成：
      1. MACD 线（快线）= 快速EMA - 慢速EMA
      2. 信号线（慢线）= MACD 线的 EMA
      3. 柱状图 = MACD 线 - 信号线
    
    交易信号：
    - MACD 线上穿信号线：看涨信号（金叉）
    - MACD 线下穿信号线：看跌信号（死叉）
    - 柱状图由负转正：趋势增强
    
    参数：
        series: 价格序列（通常是收盘价）
        fast: 快速 EMA 周期（默认12）
        slow: 慢速 EMA 周期（默认26）
        signal: 信号线 EMA 周期（默认9）
    
    返回：
        (MACD线, 信号线, 柱状图) 三个序列
    """
    # 计算快速和慢速指数移动平均线
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    
    # MACD 线 = 快线 - 慢线
    macd_line = ema_fast - ema_slow
    
    # 信号线 = MACD 线的 EMA
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    
    # 柱状图 = MACD 线 - 信号线
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """
    计算 ATR（平均真实波幅）
    
    ATR 原理：
    - ATR 衡量市场波动性（价格变化的剧烈程度）
    - 用于设置止损和止盈位置
    - ATR 越大，市场波动越剧烈
    
    计算方法：
    - 真实波幅 TR = max(最高-最低, |最高-昨收|, |最低-昨收|)
    - ATR = TR 的指数移动平均
    
    参数：
        df: 包含 high, low, close 列的 DataFrame
        period: 计算周期（默认14天）
    
    返回：
        ATR 值序列
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)  # 前一日收盘价
    
    # 计算真实波幅的三个候选值，取最大值
    tr = pd.concat(
        [
            (high - low).abs(),           # 当日最高价 - 最低价
            (high - prev_close).abs(),    # 当日最高价 - 昨日收盘价
            (low - prev_close).abs()      # 当日最低价 - 昨日收盘价
        ],
        axis=1,
    ).max(axis=1)
    
    # 计算 TR 的指数移动平均
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int) -> pd.Series:
    """
    计算 ADX（平均趋向指标）
    
    ADX 原理：
    - ADX 衡量趋势的强度（不是方向！）
    - 取值范围 0-100
    - ADX > 25 通常表示有明显趋势
    - ADX < 20 表示震荡市，没有明显趋势
    
    计算步骤：
    1. 计算 +DM（上升动向）和 -DM（下降动向）
    2. 计算 +DI 和 -DI（方向指标）
    3. 计算 DX = |+DI - -DI| / (+DI + -DI)
    4. ADX = DX 的移动平均
    
    参数：
        df: 包含 high, low, close 列的 DataFrame
        period: 计算周期（默认14天）
    
    返回：
        ADX 值序列
    """
    high = df["high"]
    low = df["low"]
    
    # 步骤1：计算上升和下降动向
    up_move = high.diff()      # 今日最高 - 昨日最高
    down_move = -low.diff()    # 昨日最低 - 今日最低
    
    # 计算 +DM 和 -DM
    # 只有当上升动向大于下降动向且为正时，+DM 才等于上升动向，否则为0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    # 步骤2：计算真实波幅 TR
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - df["close"].shift(1)).abs(),
            (low - df["close"].shift(1)).abs()
        ],
        axis=1,
    ).max(axis=1)
    
    # 计算 ATR（TR 的移动平均）
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    
    # 步骤3：计算 +DI 和 -DI（方向指标）
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
    
    # 步骤4：计算 DX（方向指数）
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    
    # 步骤5：计算 ADX（DX 的移动平均）
    return (100 * dx).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


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
) -> pd.DataFrame:
    """
    为数据添加所有技术指标
    
    功能说明：
    这是一个"指标工厂"函数，一次性计算所有需要的技术指标：
    - RSI：相对强弱指标（超买超卖）
    - MACD：趋势跟踪指标
    - EMA：指数移动平均线（趋势判断）
    - ATR：波动率指标（用于止损止盈）
    - ADX：趋势强度指标
    
    参数：
        df: 原始价格数据
        rsi_period: RSI 计算周期
        macd_fast: MACD 快线周期
        macd_slow: MACD 慢线周期
        macd_signal: MACD 信号线周期
        ema_fast: 快速 EMA 周期
        ema_slow: 慢速 EMA 周期
        adx_period: ADX 计算周期
        atr_period: ATR 计算周期
    
    返回：
        添加了所有指标列的 DataFrame
    """
    df = df.copy()
    
    # 计算 RSI 指标
    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    
    # 计算 MACD 指标（返回三个值）
    df["macd"], df["signal"], df["histogram"] = compute_macd(
        df["close"], fast=macd_fast, slow=macd_slow, signal=macd_signal
    )
    
    # 计算两条 EMA 均线（用于判断趋势方向）
    df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
    
    # 计算 ATR 波动率指标
    df["atr"] = compute_atr(df, period=atr_period)
    
    # 计算 ADX 趋势强度指标
    df["adx"] = compute_adx(df, period=adx_period)
    
    # ========== 新增：高级指标 ==========
    
    # 计算布林带
    df["bb_upper"], df["bb_middle"], df["bb_lower"] = compute_bollinger_bands(
        df["close"], period=20, std_dev=2.0
    )
    
    # 布林带位置（0-1之间，0.5表示在中轨）
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = np.where(
        bb_range > 0,
        (df["close"] - df["bb_lower"]) / bb_range,
        0.5
    )
    
    # 布林带宽度（标准化）
    df["bb_width"] = bb_range / df["close"]
    
    # 计算 OBV 能量潮
    df["obv"] = compute_obv(df)
    
    # OBV 趋势（20日变化率）
    df["obv_trend"] = df["obv"].pct_change(20)
    
    # 成交量变化率（相对于20日均量）
    avg_volume = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / avg_volume
    
    # 最大回撤（从历史最高点的跌幅）
    cummax = df["close"].cummax()
    df["drawdown"] = (df["close"] / cummax - 1)
    
    # 价格相对位置（在近期高低点的位置）
    period_high = df["high"].rolling(20).max()
    period_low = df["low"].rolling(20).min()
    price_range = period_high - period_low
    df["price_position"] = np.where(
        price_range > 0,
        (df["close"] - period_low) / price_range,
        0.5
    )
    
    return df


# ============ 新增：高级技术指标 ============

def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算布林带（Bollinger Bands）
    
    布林带原理：
    - 中轨 = 移动平均线
    - 上轨 = 中轨 + N倍标准差
    - 下轨 = 中轨 - N倍标准差
    
    作用：
    - 价格接近上轨：超买信号
    - 价格接近下轨：超卖信号
    - 布林带收窄：波动率降低，可能即将突破
    - 布林带扩张：波动率增加
    
    参数：
        series: 价格序列（通常是收盘价）
        period: 计算周期（默认20天）
        std_dev: 标准差倍数（默认2倍）
    
    返回：
        (上轨, 中轨, 下轨) 三个序列
    """
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """
    计算 OBV（能量潮指标，On-Balance Volume）
    
    OBV 原理：
    - 价格上涨日：OBV += 当日成交量
    - 价格下跌日：OBV -= 当日成交量
    - 价格不变：OBV 不变
    
    作用：
    - OBV 上升 + 价格上升 = 趋势健康（量价齐升）
    - OBV 下降 + 价格上升 = 量价背离（警告信号）
    - 用于确认趋势强度
    
    参数：
        df: 包含 close 和 volume 列的 DataFrame
    
    返回：
        OBV 序列
    """
    # 计算价格变化方向
    price_change = df['close'].diff()
    direction = np.sign(price_change)  # +1, 0, -1
    
    # OBV = 累积（方向 × 成交量）
    obv = (direction * df['volume']).fillna(0).cumsum()
    
    return obv


def rolling_rank(series: pd.Series, window: int) -> pd.Series:
    """
    滚动排名标准化（更稳健的替代Z-score）
    
    排名法原理：
    - 计算当前值在滚动窗口内的排名百分位
    - 取值范围：0-1（0=最小值，1=最大值）
    - 不假设数据分布，对极端值不敏感
    
    优势：
    - 比 Z-score 更稳健
    - 不受异常值影响
    - 适用于任何分布
    
    参数：
        series: 数据序列
        window: 滚动窗口大小
    
    返回：
        排名序列（0-1之间）
    """
    def last_percentile(values: pd.Series) -> float:
        """计算窗口内最后一个值的百分位排名"""
        if len(values) < 2:
            return 0.5
        ranked = values.rank(pct=True)
        return float(ranked.iloc[-1])
    
    return series.rolling(window=window, min_periods=max(1, window//2)).apply(
        last_percentile, raw=False
    )


# ============ 策略信号计算 ============

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
    # 新增：指标开关参数
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    # 新增：Phase 1 新因子权重参数
    weight_bb: float = 0.8,
    weight_obv: float = 1.0,
    weight_volume: float = 0.6,
    weight_price: float = 0.7,
    weight_drawdown: float = 0.5,
    # 新增：入场逻辑选择
    use_voting_entry: bool = False,
    entry_vote_threshold: float = 2.5,
) -> pd.DataFrame:
    """
    计算交易信号和目标仓位
    
    【策略核心逻辑】
    这是一个多因子量化策略，综合考虑以下因素：
    
    1. 因子评分系统（Factor Score）：
       - 短期动量：近期价格涨跌趋势
       - 长期动量：中期价格涨跌趋势
       - MACD 柱状图：趋势变化强度
       - RSI：超买超卖状态
       - 波动率：市场稳定性（波动越大，评分惩罚越大）
    
    2. 过滤条件（必须全部满足才能开仓）：
       - 趋势过滤：快速EMA > 慢速EMA（上升趋势）
       - 强度过滤：ADX >= 阈值（趋势足够强）
       - RSI 过滤：RSI 在合理区间内（不过度超买/超卖）
       - MACD 过滤：MACD > Signal（趋势向上）
       - 评分过滤：因子评分 >= 入场阈值
    
    3. 仓位管理（动态调整）：
       - 高评分（分位数 >= 80%）：满仓（1.0）
       - 中评分（分位数 >= 60%）：半仓（0.5）
       - 低评分：空仓（0.0）
    
    4. 出场条件（任一触发则平仓）：
       - 因子评分 <= 出场阈值
       - 快速EMA < 慢速EMA（趋势反转）
       - RSI 超出合理区间
       - MACD < Signal（趋势转弱）
    
    参数：
        df: 包含技术指标的 DataFrame
        rsi_lower: RSI 下限（如30）
        rsi_upper: RSI 上限（如70）
        adx_threshold: ADX 最小阈值（如20）
        momentum_short: 短期动量窗口（天数）
        momentum_long: 长期动量窗口（天数）
        score_lookback: 评分标准化窗口
        score_mid_pct: 中档仓位分位数阈值
        score_high_pct: 高档仓位分位数阈值
        weight_mom_short: 短期动量权重
        weight_mom_long: 长期动量权重
        weight_macd: MACD 权重
        weight_rsi: RSI 权重
        weight_vol: 波动率惩罚权重
        entry_threshold: 入场评分阈值
        exit_threshold: 出场评分阈值
    
    返回：
        添加了信号列的 DataFrame
    """
    df = df.copy()
    
    # ========== 步骤1：计算过滤条件 ==========
    
    # 趋势过滤：快线在慢线上方表示上升趋势
    df["trend_ok"] = df["ema_fast"] > df["ema_slow"]
    
    # 强度过滤：ADX 足够大表示趋势明显
    df["strength_ok"] = df["adx"] >= adx_threshold
    
    # RSI 过滤：在合理区间内（不过度超买/超卖）
    df["rsi_ok"] = (df["rsi"] > rsi_lower) & (df["rsi"] < rsi_upper)
    
    # ========== 步骤2：计算动量和波动率因子 ==========
    
    # 计算收益率（百分比变化）
    df["ret_short"] = df["close"].pct_change(momentum_short)  # 短期收益率
    df["ret_long"] = df["close"].pct_change(momentum_long)    # 长期收益率
    
    # 计算相对波动率（ATR / 价格）
    df["volatility"] = df["atr"] / df["close"]
    
    # ========== 步骤3：标准化因子（混合使用 Z-score 和排名法）==========
    # 使用排名法（更稳健）标准化新因子
    
    # 原有因子：使用 Z-score
    df["mom_short_z"] = rolling_zscore(df["ret_short"], score_lookback)
    df["mom_long_z"] = rolling_zscore(df["ret_long"], score_lookback)
    df["macd_z"] = rolling_zscore(df["histogram"], score_lookback)
    df["rsi_z"] = rolling_zscore(df["rsi"], score_lookback)
    df["vol_z"] = rolling_zscore(df["volatility"], score_lookback)
    
    # 新增因子：使用排名法（0-1之间，更稳健）
    df["bb_position_rank"] = rolling_rank(df["bb_position"], score_lookback)
    df["obv_trend_rank"] = rolling_rank(df["obv_trend"], score_lookback)
    df["volume_ratio_rank"] = rolling_rank(df["volume_ratio"], score_lookback)
    df["price_position_rank"] = rolling_rank(df["price_position"], score_lookback)
    
    # 回撤因子（负向，回撤越大越不好）
    df["drawdown_rank"] = rolling_rank(df["drawdown"], score_lookback)
    
    # ========== 步骤4：计算增强的综合因子评分 ==========
    # 评分 = 原有因子 + 新增因子
    # 注意：波动率和回撤是负向因子（用减号）
    
    df["factor_score"] = (
        # 原有因子（Z-score标准化）
        weight_mom_short * df["mom_short_z"]  # 短期动量
        + weight_mom_long * df["mom_long_z"]  # 长期动量
        + weight_macd * df["macd_z"]          # MACD 趋势
        + weight_rsi * df["rsi_z"]            # RSI
        - weight_vol * df["vol_z"]            # 波动率惩罚
        
        # 新增因子（排名法标准化，需要转换到 -1~1 范围）
        + weight_bb * (df["bb_position_rank"] - 0.5) * 2      # 布林带位置
        + weight_obv * (df["obv_trend_rank"] - 0.5) * 2       # OBV趋势
        + weight_volume * (df["volume_ratio_rank"] - 0.5) * 2 # 成交量比率
        + weight_price * (df["price_position_rank"] - 0.5) * 2 # 价格位置
        - weight_drawdown * (df["drawdown_rank"] - 0.5) * 2   # 回撤惩罚（负号）
    )
    
    # 填充缺失值为 0
    df["factor_score"] = df["factor_score"].fillna(0.0)
    
    # ========== 步骤5：计算因子评分的分位数排名 ==========
    # 分位数表示当前评分在历史数据中的排名位置
    df["factor_percentile"] = rolling_percentile(df["factor_score"], score_lookback).fillna(0.0)
    
    # ========== 步骤6：改进的仓位管理（3档→7档）==========
    # 使用 np.select 实现更精细的条件赋值
    score_position = np.select(
        [
            df["factor_percentile"] >= 0.95,  # 极强信号
            df["factor_percentile"] >= 0.85,  # 强信号
            df["factor_percentile"] >= 0.75,  # 较强信号
            df["factor_percentile"] >= 0.60,  # 中等信号（原中档）
            df["factor_percentile"] >= 0.50,  # 弱信号
        ],
        [
            1.0,   # 极强 → 满仓
            0.8,   # 强 → 80%仓位
            0.6,   # 较强 → 60%仓位
            0.4,   # 中等 → 40%仓位
            0.2,   # 弱 → 20%仓位
        ],
        default=0.0  # 其他 → 空仓
    )
    
    # 波动率调整：波动率过高时降低仓位
    volatility_percentile = rolling_percentile(df["volatility"], score_lookback).fillna(0.5)
    vol_adjustment = np.where(
        volatility_percentile > 0.8,  # 波动率过高（前20%）
        0.7,  # 仓位打7折
        1.0   # 正常
    )
    
    score_position = score_position * vol_adjustment
    
    # ========== 步骤7：应用入场过滤条件（支持两种模式）==========
    # MACD 在信号线上方
    macd_above = df["macd"] > df["signal"]
    
    if use_voting_entry:
        # ========== 模式1：评分制入场（推荐）==========
        # 每个条件独立评分，满足加分，总分达标即可入场
        
        df["entry_vote_score"] = 0.0
        
        # 核心条件：因子评分达标（权重 2.0，最重要）
        df["entry_vote_score"] += np.where(
            df["factor_score"] >= entry_threshold,
            2.0,
            0.0
        )
        
        # 辅助条件1：趋势向上（权重 1.0）
        if use_trend_filter:
            df["entry_vote_score"] += np.where(df["trend_ok"], 1.0, 0.0)
        
        # 辅助条件2：强度足够（权重 1.0）
        if use_strength_filter:
            df["entry_vote_score"] += np.where(df["strength_ok"], 1.0, 0.0)
        
        # 辅助条件3：RSI 正常（权重 0.5）
        if use_rsi_filter:
            df["entry_vote_score"] += np.where(df["rsi_ok"], 0.5, 0.0)
        
        # 辅助条件4：MACD 向上（权重 0.5）
        if use_macd_filter:
            df["entry_vote_score"] += np.where(macd_above, 0.5, 0.0)
        
        # 入场条件：评分达到阈值
        filter_ok = df["entry_vote_score"] >= entry_vote_threshold
        
    else:
        # ========== 模式2：严格AND入场（原逻辑）==========
        # 所有条件必须同时满足才能入场
        
        # 根据用户选择的指标，动态构建过滤条件
        filter_conditions = []
        
        # 基础条件：评分达标（始终需要）
        filter_conditions.append(df["factor_score"] >= entry_threshold)
        
        # 可选条件：趋势过滤
        if use_trend_filter:
            filter_conditions.append(df["trend_ok"])  # ✓ 上升趋势
        
        # 可选条件：强度过滤
        if use_strength_filter:
            filter_conditions.append(df["strength_ok"])  # ✓ 趋势足够强
        
        # 可选条件：RSI 过滤
        if use_rsi_filter:
            filter_conditions.append(df["rsi_ok"])  # ✓ RSI 在合理区间
        
        # 可选条件：MACD 过滤
        if use_macd_filter:
            filter_conditions.append(macd_above)  # ✓ MACD 向上
        
        # 合并所有启用的过滤条件（使用 AND 逻辑）
        if len(filter_conditions) > 0:
            filter_ok = filter_conditions[0]
            for condition in filter_conditions[1:]:
                filter_ok = filter_ok & condition
        else:
            # 如果没有任何过滤条件，默认为 True（允许所有信号）
            filter_ok = pd.Series([True] * len(df), index=df.index)
    
    # 只有过滤条件满足时，才使用计算出的仓位；否则仓位为0
    df["target_position"] = np.where(filter_ok, score_position, 0.0)
    
    # ========== 步骤8：应用出场条件（支持可选指标）==========
    # 根据用户选择的指标，动态构建出场条件
    exit_conditions = []
    
    # 基础条件：评分过低（始终需要）
    exit_conditions.append(df["factor_score"] <= exit_threshold)
    
    # 可选条件：趋势反转
    if use_trend_filter:
        exit_conditions.append(df["ema_fast"] < df["ema_slow"])
    
    # 可选条件：RSI 超出范围
    if use_rsi_filter:
        exit_conditions.append((df["rsi"] > rsi_upper) | (df["rsi"] < rsi_lower))
    
    # 可选条件：MACD 转弱
    if use_macd_filter:
        exit_conditions.append(df["macd"] < df["signal"])
    
    # 合并所有启用的出场条件（使用 OR 逻辑，任一触发则平仓）
    if len(exit_conditions) > 0:
        exit_block = exit_conditions[0]
        for condition in exit_conditions[1:]:
            exit_block = exit_block | condition
    else:
        # 如果没有任何出场条件，默认为 False（不触发出场）
        exit_block = pd.Series([False] * len(df), index=df.index)
    
    # 出场条件触发时，强制仓位为0
    df.loc[exit_block, "target_position"] = 0.0
    
    # ========== 步骤9：生成买卖信号 ==========
    # 买入信号：从无仓位（或空仓）变为有仓位
    df["buy_signal"] = (df["target_position"] > 0) & (df["target_position"].shift(1) <= 0)
    
    # 卖出信号：从有仓位变为无仓位
    df["sell_signal"] = (df["target_position"] <= 0) & (df["target_position"].shift(1) > 0)
    
    return df


# ============ 回测模拟函数 ============

def simulate_strategy(
    df: pd.DataFrame,
    initial_position: int = 0,
    stop_loss_mult: float = 0.0,
    take_profit_mult: float = 0.0,
) -> pd.DataFrame:
    """
    模拟策略执行，计算收益曲线
    
    【回测原理】
    回测是用历史数据模拟交易，验证策略的有效性。
    这个函数逐日遍历数据，根据信号决定是否买入/卖出，并计算收益。
    
    【功能说明】
    1. 根据买卖信号执行交易
    2. 支持动态仓位（0.5 半仓，1.0 满仓）
    3. 支持止损和止盈（基于 ATR 倍数）
    4. 计算策略收益曲线
    5. 对比买入持有策略
    
    【止损止盈机制】
    - 止损价 = 入场价 - ATR × 止损倍数
    - 止盈价 = 入场价 + ATR × 止盈倍数
    - 当价格触及止损/止盈价时，自动平仓
    
    参数：
        df: 包含信号的 DataFrame
        initial_position: 初始仓位（0=空仓，1=满仓）
        stop_loss_mult: 止损倍数（如 2.0 表示 2倍ATR）
        take_profit_mult: 止盈倍数（如 4.0 表示 4倍ATR）
    
    返回：
        添加了仓位、收益、净值等列的 DataFrame
    """
    df = df.copy()
    
    # 初始化仓位数组
    position = np.zeros(len(df))
    
    # 初始状态
    in_position = initial_position == 1  # 是否持仓
    entry_price = df["close"].iloc[0] if in_position and len(df) > 0 else np.nan  # 入场价格
    entry_atr = df["atr"].iloc[0] if in_position and len(df) > 0 else np.nan      # 入场时的 ATR
    
    # 设置初始仓位
    if len(df) > 0:
        position[0] = initial_position
    
    # ========== 主循环：逐日模拟交易 ==========
    for i in range(1, len(df)):
        
        # 情况1：如果策略有 target_position 列（动态仓位策略）
        if "target_position" in df.columns:
            # 获取目标仓位（限制在 0-1 之间）
            desired_pos = float(np.clip(df["target_position"].iloc[i], 0.0, 1.0))
            
            # 子情况A：当前空仓
            if not in_position:
                # 如果目标仓位 > 0，则买入
                if desired_pos > 0:
                    in_position = True
                    entry_price = df["close"].iloc[i]  # 记录买入价格
                    entry_atr = df["atr"].iloc[i]      # 记录买入时的 ATR
                    position[i] = desired_pos
                    
            # 子情况B：当前持仓
            else:
                exit_triggered = desired_pos == 0  # 检查是否需要平仓
                
                # 检查卖出信号
                if "sell_signal" in df.columns and df["sell_signal"].iloc[i]:
                    exit_triggered = True
                
                # 检查止损止盈条件
                if not np.isnan(entry_atr):
                    # 止损检查：最低价 <= 止损价
                    if stop_loss_mult > 0:
                        stop_price = entry_price - stop_loss_mult * entry_atr
                        if df["low"].iloc[i] <= stop_price:
                            exit_triggered = True
                    
                    # 止盈检查：最高价 >= 止盈价
                    if take_profit_mult > 0:
                        take_price = entry_price + take_profit_mult * entry_atr
                        if df["high"].iloc[i] >= take_price:
                            exit_triggered = True
                
                # 执行出场
                if exit_triggered:
                    in_position = False
                    entry_price = np.nan
                    entry_atr = np.nan
                    position[i] = 0.0
                else:
                    # 继续持仓
                    position[i] = desired_pos
        
        # 情况2：如果没有 target_position 列（简单买卖信号策略）
        else:
            # 子情况A：当前空仓
            if not in_position:
                # 检查买入信号
                if df["buy_signal"].iloc[i]:
                    in_position = True
                    entry_price = df["close"].iloc[i]
                    entry_atr = df["atr"].iloc[i]
            
            # 子情况B：当前持仓
            else:
                exit_triggered = df["sell_signal"].iloc[i]  # 检查卖出信号
                
                # 检查止损止盈
                if not np.isnan(entry_atr):
                    if stop_loss_mult > 0:
                        stop_price = entry_price - stop_loss_mult * entry_atr
                        if df["low"].iloc[i] <= stop_price:
                            exit_triggered = True
                    
                    if take_profit_mult > 0:
                        take_price = entry_price + take_profit_mult * entry_atr
                        if df["high"].iloc[i] >= take_price:
                            exit_triggered = True
                
                # 执行出场
                if exit_triggered:
                    in_position = False
                    entry_price = np.nan
                    entry_atr = np.nan
            
            # 设置仓位（简单策略只有 0 或 1）
            position[i] = 1 if in_position else 0
    
    # ========== 计算收益和净值 ==========
    
    # 保存仓位到 DataFrame
    df["position"] = position
    
    # 计算每日收益率
    returns = df["close"].pct_change().fillna(0)
    
    # 计算策略收益：仓位 × 收益率
    # 注意：使用前一日的仓位（因为是收盘后才知道今日收益）
    df["strategy_return"] = df["position"].shift(1).fillna(initial_position) * returns
    
    # 计算策略净值曲线（从 1.0 开始累积）
    df["strategy_equity"] = (1 + df["strategy_return"]).cumprod()
    
    # 计算买入持有策略的净值曲线（对比基准）
    df["buy_hold_equity"] = (1 + returns).cumprod()
    
    return df


# ============ 策略评估指标 ============

def max_drawdown(equity: pd.Series) -> float:
    """
    计算最大回撤（Maximum Drawdown）
    
    【回撤原理】
    回撤衡量投资组合从峰值下跌的最大幅度。
    例如：净值从 1.5 跌到 1.2，回撤 = (1.2 - 1.5) / 1.5 = -20%
    
    【风险意义】
    - 最大回撤越小，策略越稳定
    - 反映了策略可能遭受的最大损失
    - 投资者需要有心理准备承受这个回撤
    
    计算方法：
    1. 计算每个时刻的历史最高净值
    2. 计算当前净值相对历史最高的跌幅
    3. 取所有跌幅的最小值（最大回撤）
    
    参数：
        equity: 净值曲线序列
    
    返回：
        最大回撤（负数，如 -0.25 表示回撤 25%）
    """
    # 计算截至当前的历史最高净值
    roll_max = equity.cummax()
    
    # 计算当前净值相对历史最高的回撤比例
    drawdown = equity / roll_max - 1
    
    # 返回最大回撤（最小的负数）
    return float(drawdown.min())


def sharpe_ratio(returns: pd.Series) -> float:
    """
    计算夏普比率（Sharpe Ratio）
    
    【夏普比率原理】
    夏普比率衡量每承受一单位风险，能获得多少超额收益。
    公式：Sharpe = (平均收益 / 收益标准差) × √252
    
    【经验法则】
    - Sharpe > 1：策略较好
    - Sharpe > 2：策略很好
    - Sharpe > 3：策略优秀
    - Sharpe < 0：策略亏损
    
    【为什么乘以 √252？】
    因为这里是日收益率，252 是一年的交易日数。
    乘以 √252 将日夏普转换为年化夏普比率。
    
    参数：
        returns: 收益率序列
    
    返回：
        年化夏普比率
    """
    # 计算收益率的标准差（波动率）
    std = returns.std()
    
    # 如果标准差为 0 或 NaN，无法计算夏普比率
    if std == 0 or np.isnan(std):
        return 0.0
    
    # 计算年化夏普比率
    return float((returns.mean() / std) * np.sqrt(252))


# ============ Walk-Forward 回测 ============

def walk_forward_backtest(
    df: pd.DataFrame,
    train_window: int,
    test_window: int,
    stop_loss_mult: float,
    take_profit_mult: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Walk-Forward 回测（滚动窗口回测）
    
    【Walk-Forward 原理】
    这是一种更真实的回测方法，模拟实际交易中的情况：
    1. 用历史数据训练策略（训练窗口）
    2. 在未来数据上测试策略（测试窗口）
    3. 滚动窗口，重复上述过程
    
    【为什么需要 Walk-Forward？】
    传统回测的问题：
    - 使用全部历史数据优化参数 → 容易过拟合
    - 在同一数据上训练和测试 → 不能反映真实表现
    
    Walk-Forward 的优势：
    - 训练集和测试集分离 → 避免未来信息泄露
    - 滚动测试 → 验证策略在不同市场环境下的稳定性
    
    【执行流程】
    时间线：[---训练窗口---|---测试窗口---|---训练窗口---|---测试窗口---]
             ↑ 优化参数      ↑ 验证表现     ↑ 重新优化     ↑ 再次验证
    
    参数：
        df: 完整的数据集
        train_window: 训练窗口大小（交易日数）
        test_window: 测试窗口大小（交易日数）
        stop_loss_mult: 止损倍数
        take_profit_mult: 止盈倍数
    
    返回：
        (结果汇总 DataFrame, 完整净值曲线 DataFrame)
    """
    results = []         # 存储每个窗口的结果
    equity_curve = []    # 存储完整的净值曲线
    start_idx = 0        # 窗口起始位置
    
    # ========== 主循环：滚动窗口 ==========
    while start_idx + train_window < len(df):
        
        # 计算训练集和测试集的边界
        train_end = start_idx + train_window
        test_end = min(train_end + test_window, len(df))
        
        # 提取测试集数据
        test_slice = df.iloc[train_end:test_end]
        
        # 如果测试集为空，结束循环
        if test_slice.empty:
            break
        
        # 在测试集上模拟策略
        test_sim = simulate_strategy(
            test_slice,
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        # 计算测试集表现
        total_return = test_sim["strategy_equity"].iloc[-1] - 1
        
        # 记录该窗口的结果
        results.append(
            {
                "window_start": test_slice["date"].iloc[0],
                "window_end": test_slice["date"].iloc[-1],
                "test_return": total_return,
                "test_sharpe": sharpe_ratio(test_sim["strategy_return"]),
                "test_max_drawdown": max_drawdown(test_sim["strategy_equity"]),
            }
        )
        
        # 提取净值曲线片段
        segment = test_sim[["date", "strategy_equity", "buy_hold_equity"]].copy()
        
        # 连接各个窗口的净值曲线（保持连续性）
        if equity_curve:
            # 获取上一个窗口的结束净值
            prev_end = equity_curve[-1]["strategy_equity"].iloc[-1]
            prev_bh_end = equity_curve[-1]["buy_hold_equity"].iloc[-1]
            
            # 调整当前窗口的净值，使其从上一窗口结束点开始
            segment["strategy_equity"] *= prev_end
            segment["buy_hold_equity"] *= prev_bh_end
        
        equity_curve.append(segment)
        
        # 窗口向前滚动
        start_idx += test_window
    
    # ========== 合并结果 ==========
    
    # 合并所有窗口的净值曲线
    if equity_curve:
        equity_df = pd.concat(equity_curve, ignore_index=True)
    else:
        equity_df = pd.DataFrame(columns=["date", "strategy_equity", "buy_hold_equity"])
    
    return pd.DataFrame(results), equity_df


# ============ 参数自动优化 ============

def random_search_params(
    df_indicators: pd.DataFrame,
    split_idx: int,
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
    trials: int,
    # 新增：指标开关参数
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
) -> dict | None:
    """
    随机搜索最优参数
    
    【参数优化原理】
    策略有很多参数需要调整（如止损倍数、入场阈值等）。
    随机搜索通过以下步骤找到较优参数：
    1. 随机生成一组参数
    2. 在训练集上测试该参数的表现
    3. 记录表现最好的参数
    4. 重复 N 次，找到最佳参数
    
    【为什么用随机搜索而不是网格搜索？】
    - 网格搜索：遍历所有参数组合 → 速度慢，组合爆炸
    - 随机搜索：随机采样参数空间 → 速度快，效果不错
    
    【优化目标】
    目标函数 = 夏普比率 + 总收益
    这个目标平衡了收益和风险。
    
    【搜索的参数】
    - entry_threshold: 入场评分阈值（-1.0 到 1.5）
    - exit_threshold: 出场评分阈值（-1.5 到 0.5）
    - adx_threshold: ADX 强度阈值（10 到 35）
    - stop_loss_mult: 止损倍数（0 到 4）
    - take_profit_mult: 止盈倍数（0 到 6）
    
    参数：
        df_indicators: 已计算指标的数据
        split_idx: 训练/测试集分割点
        （其他参数）：固定的策略参数
        trials: 随机搜索次数
    
    返回：
        最佳参数字典（包含评分、收益、夏普比率等）
    """
    rng = np.random.default_rng(7)  # 随机数生成器（种子=7，保证可复现）
    best = None  # 存储最佳参数
    
    # ========== 主循环：随机搜索 ==========
    for _ in range(trials):
        
        # 随机生成候选参数
        entry_threshold = round(rng.uniform(-1.0, 1.5), 2)    # 入场阈值
        exit_threshold = round(rng.uniform(-1.5, 0.5), 2)     # 出场阈值
        
        # 参数合法性检查：入场阈值必须 > 出场阈值
        if entry_threshold <= exit_threshold:
            continue  # 跳过不合法的参数组合
        
        adx_candidate = round(rng.uniform(10, 35), 0)         # ADX 阈值
        stop_loss_mult = round(rng.uniform(0.0, 4.0), 1)      # 止损倍数
        take_profit_mult = round(rng.uniform(0.0, 6.0), 1)    # 止盈倍数
        
        # 使用候选参数计算信号
        df_signals = compute_signals(
            df_indicators,
            rsi_lower=rsi_lower,
            rsi_upper=rsi_upper,
            adx_threshold=adx_candidate,
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
            # 传递指标开关参数
            use_trend_filter=use_trend_filter,
            use_strength_filter=use_strength_filter,
            use_rsi_filter=use_rsi_filter,
            use_macd_filter=use_macd_filter,
        )
        
        # 在训练集上回测该参数组合
        train_sim = simulate_strategy(
            df_signals.iloc[:split_idx],
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        # 计算表现指标
        total_return = train_sim["strategy_equity"].iloc[-1] - 1  # 总收益
        sharpe = sharpe_ratio(train_sim["strategy_return"])       # 夏普比率
        
        # 计算综合评分（收益 + 夏普）
        score = sharpe + total_return
        
        # 更新最佳参数
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "sharpe": sharpe,
                "return": total_return,
                "adx_threshold": adx_candidate,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "stop_loss_mult": stop_loss_mult,
                "take_profit_mult": take_profit_mult,
            }
    
    return best


def bayesian_optimize_params(
    df_indicators: pd.DataFrame,
    split_idx: int,
    rsi_lower: float,
    rsi_upper: float,
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
    n_trials: int,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
) -> dict | None:
    """
    使用贝叶斯优化（Optuna）搜索最优参数
    
    【为什么用贝叶斯优化代替随机搜索？】
    
    1. 随机搜索的问题：
       - 盲目采样，不利用历史信息
       - 需要大量试验才能找到好参数
       - 效率低，尤其是参数空间大时
    
    2. 贝叶斯优化的优势：
       - 智能采样：基于历史试验结果，预测下一个最有希望的参数
       - 收敛快：通常 50-100 次试验就能找到接近最优解
       - 平衡探索与利用：既搜索未知区域，又在好的区域精细搜索
    
    3. 工作原理：
       - 构建代理模型（Surrogate Model）预测参数→性能的映射
       - 使用采集函数（Acquisition Function）决定下一个参数
       - 不断更新模型，逐步逼近最优参数
    
    【优化的参数】
    核心参数：
    - entry_threshold: 入场评分阈值（-1.0 到 2.0）
    - exit_threshold: 出场评分阈值（-2.0 到 0.5）
    - adx_threshold: ADX 强度阈值（10 到 35）
    - stop_loss_mult: 止损倍数（0.5 到 4.0）
    - take_profit_mult: 止盈倍数（1.0 到 6.0）
    
    新增因子权重（Phase 1）：
    - weight_bb: 布林带位置权重（0.0 到 2.0）
    - weight_obv: OBV 趋势权重（0.0 到 2.0）
    - weight_volume: 成交量比率权重（0.0 到 1.5）
    - weight_price: 价格位置权重（0.0 到 1.5）
    - weight_drawdown: 回撤惩罚权重（0.0 到 1.5）
    
    参数：
        df_indicators: 已计算指标的数据
        split_idx: 训练/测试集分割点
        其他参数：固定的策略参数
        n_trials: 优化试验次数（建议 50-100）
    
    返回：
        最佳参数字典
    """
    try:
        import optuna
        # 禁用 Optuna 的日志输出，避免干扰 Streamlit
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        st.error("需要安装 optuna 库。请运行：pip install optuna")
        return None
    
    best_result = {"score": -np.inf}  # 用于在目标函数外部跟踪最佳结果
    
    def objective(trial):
        """Optuna 优化目标函数"""
        
        # ===== 1. 建议参数（Optuna 会智能采样）=====
        entry_threshold = trial.suggest_float("entry_threshold", -1.0, 2.0)
        exit_threshold = trial.suggest_float("exit_threshold", -2.0, 0.5)
        
        # 确保入场 > 出场
        if entry_threshold <= exit_threshold:
            return -np.inf
        
        adx_candidate = trial.suggest_float("adx_threshold", 10, 35)
        stop_loss_mult = trial.suggest_float("stop_loss_mult", 0.5, 4.0)
        take_profit_mult = trial.suggest_float("take_profit_mult", 1.0, 6.0)
        
        # Phase 1 新因子权重
        weight_bb = trial.suggest_float("weight_bb", 0.0, 2.0)
        weight_obv = trial.suggest_float("weight_obv", 0.0, 2.0)
        weight_volume = trial.suggest_float("weight_volume", 0.0, 1.5)
        weight_price = trial.suggest_float("weight_price", 0.0, 1.5)
        weight_drawdown = trial.suggest_float("weight_drawdown", 0.0, 1.5)
        
        # ===== 2. 计算信号 =====
        df_signals = compute_signals(
            df_indicators,
            rsi_lower=rsi_lower,
            rsi_upper=rsi_upper,
            adx_threshold=adx_candidate,
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
            # 传递新因子权重
            weight_bb=weight_bb,
            weight_obv=weight_obv,
            weight_volume=weight_volume,
            weight_price=weight_price,
            weight_drawdown=weight_drawdown,
        )
        
        # ===== 3. 在训练集上回测 =====
        train_sim = simulate_strategy(
            df_signals.iloc[:split_idx],
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        # ===== 4. 计算评分指标 =====
        total_return = train_sim["strategy_equity"].iloc[-1] - 1
        sharpe = sharpe_ratio(train_sim["strategy_return"])
        max_dd = max_drawdown(train_sim["strategy_equity"])
        
        # 综合评分：夏普比率 + 收益 - 回撤惩罚
        # 回撤惩罚：回撤越大，扣分越多
        score = sharpe + total_return - abs(max_dd) * 0.5
        
        # ===== 5. 更新最佳结果（用于返回）=====
        nonlocal best_result
        if score > best_result["score"]:
            best_result = {
                "score": score,
                "sharpe": sharpe,
                "return": total_return,
                "max_drawdown": max_dd,
                "adx_threshold": adx_candidate,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "stop_loss_mult": stop_loss_mult,
                "take_profit_mult": take_profit_mult,
                # 新因子权重
                "weight_bb": weight_bb,
                "weight_obv": weight_obv,
                "weight_volume": weight_volume,
                "weight_price": weight_price,
                "weight_drawdown": weight_drawdown,
            }
        
        return score
    
    # ===== 创建并运行优化 =====
    study = optuna.create_study(direction="maximize")  # 最大化目标函数
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    
    return best_result if best_result["score"] > -np.inf else None


# ============ 辅助工具函数 ============

def format_pct(value: float) -> str:
    """
    格式化百分比显示
    
    参数：
        value: 小数值（如 0.1234）
    
    返回：
        百分比字符串（如 "12.34%"）
    """
    return f"{value * 100:.2f}%"


def load_or_fetch_stock(symbol: str, adjust: str) -> pd.DataFrame:
    """
    加载或下载股票数据，优先使用本地缓存
    
    功能说明：
    1. 先尝试从本地文件加载数据（节省时间）
    2. 如果本地文件不存在或损坏，从网络下载
    3. 下载后保存到本地，供下次使用
    
    参数：
        symbol: 股票代码
        adjust: 复权方式
    
    返回：
        股票数据 DataFrame，失败返回 None
    """
    # 构造本地文件路径
    data_path = os.path.join(DATA_DIR, f"{symbol.lower()}_daily.csv")
    
    # 尝试加载本地文件
    if os.path.exists(data_path):
        try:
            df = load_csv(data_path)
            return df
        except Exception as e:
            st.warning(f"加载本地数据失败 ({symbol}): {e}，尝试重新下载...")
    
    # 从网络下载数据
    try:
        with st.spinner(f"正在下载 {symbol} 数据..."):
            df = fetch_data(symbol, adjust)
            # 保存到本地
            df.to_csv(data_path, index=False)
            st.success(f"✓ {symbol} 数据已保存")
        return df
    except Exception as e:
        st.error(f"下载 {symbol} 数据失败: {e}")
        return None


def get_available_stocks() -> list:
    """
    获取本地已有的股票列表
    
    功能：扫描 data 目录，列出所有已下载的股票代码
    
    返回：
        股票代码列表（如 ['AAPL', 'TSLA', 'NVDA']）
    """
    if not os.path.exists(DATA_DIR):
        return []
    
    # 查找所有 *_daily.csv 文件
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('_daily.csv')]
    
    # 提取股票代码（移除 '_daily.csv' 后缀并转大写）
    return [f.replace('_daily.csv', '').upper() for f in files]


def normalize_prices(df_dict: dict) -> pd.DataFrame:
    """
    归一化多个股票的价格到起点=100
    
    【归一化原理】
    不同股票的价格差异很大（如 TSLA $200，NVDA $500），
    难以在同一图表中直观对比。归一化后，所有股票从 100 开始，
    可以直观比较相对涨跌幅。
    
    计算公式：归一化价格 = (当前价格 / 起始价格) × 100
    
    参数：
        df_dict: {股票代码: DataFrame} 字典
    
    返回：
        归一化后的价格 DataFrame
    """
    normalized_data = {}
    
    # 对每只股票进行归一化
    for symbol, df in df_dict.items():
        if df is not None and not df.empty:
            first_close = df['close'].iloc[0]  # 起始价格
            # 归一化：(当前价格 / 起始价格) × 100
            normalized_data[symbol] = (df['close'] / first_close * 100).values
    
    if not normalized_data:
        return pd.DataFrame()
    
    # 使用第一个股票的日期作为基准
    base_dates = list(df_dict.values())[0]['date']
    result_df = pd.DataFrame({'date': base_dates})
    
    # 添加每只股票的归一化价格
    for symbol, values in normalized_data.items():
        result_df[symbol] = values
    
    return result_df


def create_multi_stock_comparison_chart(stock_data_dict: dict, title: str = "多股票价格对比（归一化）") -> go.Figure:
    """
    创建多股票归一化价格对比的交互式图表
    
    Parameters:
    -----------
    stock_data_dict : dict
        {股票代码: DataFrame} 字典
    title : str
        图表标题
    
    Returns:
    --------
    go.Figure
        Plotly 图表对象
    """
    fig = go.Figure()
    
    # 颜色方案 - 使用专业的配色
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    for idx, (symbol, df) in enumerate(stock_data_dict.items()):
        if df is None or df.empty:
            continue
        
        # 归一化价格（起点=100）
        normalized_price = (df['close'] / df['close'].iloc[0]) * 100
        
        # 计算收益率用于hover显示
        total_return = ((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100
        
        # 添加轨迹
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=normalized_price,
            mode='lines',
            name=f'{symbol} ({total_return:+.1f}%)',
            line=dict(color=colors[idx % len(colors)], width=2.5),
            hovertemplate=(
                f'<b>{symbol}</b><br>' +
                '日期: %{x|%Y-%m-%d}<br>' +
                '归一化价格: %{y:.2f}<br>' +
                f'期间收益: {total_return:+.2f}%<br>' +
                '<extra></extra>'
            ),
            legendgroup=symbol,
            showlegend=True,
        ))
    
    # 添加基准线（起点）
    if stock_data_dict:
        first_date = list(stock_data_dict.values())[0]['date'].iloc[0]
        last_date = list(stock_data_dict.values())[0]['date'].iloc[-1]
        
        fig.add_hline(
            y=100,
            line_dash="dash",
            line_color="gray",
            opacity=0.5,
            annotation_text="起点基准 (100)",
            annotation_position="right"
        )
    
    # 更新布局 - 专业金融风格
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=22, color='#2c3e50', family='Arial Black'),
            x=0.5,
            xanchor='center',
            y=0.98,
            yanchor='top'
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True,
            gridcolor='#ecf0f1',
            gridwidth=0.5,
            rangeslider=dict(
                visible=True,
                thickness=0.05,
                bgcolor='#f8f9fa',
                bordercolor='#bdc3c7',
                borderwidth=1
            ),
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1周", step="day", stepmode="backward"),
                    dict(count=1, label="1月", step="month", stepmode="backward"),
                    dict(count=3, label="3月", step="month", stepmode="backward"),
                    dict(count=6, label="6月", step="month", stepmode="backward"),
                    dict(count=1, label="1年", step="year", stepmode="backward"),
                    dict(step="all", label="全部"),
                ]),
                bgcolor='#ecf0f1',
                activecolor='#3498db',
                font=dict(size=10),
                x=0,
                y=1.05,
                xanchor='left',
                yanchor='top'
            ),
        ),
        yaxis=dict(
            title='归一化价格（起点=100）',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True,
            gridcolor='#ecf0f1',
            gridwidth=0.5,
            zeroline=True,
            zerolinecolor='#95a5a6',
            zerolinewidth=1.5,
            tickformat='.1f',
        ),
        hovermode='x unified',
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=650,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(255,255,255,0.95)',
            bordercolor='#bdc3c7',
            borderwidth=1.5,
            font=dict(size=11),
            title=dict(text='股票（期间收益）', font=dict(size=12, color='#2c3e50'))
        ),
        margin=dict(l=70, r=40, t=100, b=60),
        font=dict(family='Arial, sans-serif'),
    )
    
    return fig


def create_correlation_heatmap(stock_data_dict: dict) -> go.Figure:
    """创建股票收益率相关性热图 - 改进版，支持日期对齐"""
    
    # 准备日收益率数据，使用日期作为索引
    returns_series = {}
    for symbol, df in stock_data_dict.items():
        if df is not None and len(df) > 1:
            # 确保有 date 列并设置为索引
            temp_df = df.copy()
            if 'date' in temp_df.columns:
                temp_df['date'] = pd.to_datetime(temp_df['date'])
                temp_df = temp_df.set_index('date')
            
            # 计算日收益率
            returns = temp_df['close'].pct_change().dropna()
            returns_series[symbol] = returns
    
    if len(returns_series) < 2:
        return None
    
    # 使用日期索引对齐所有股票数据
    # 找到所有股票的共同交易日
    returns_df = pd.DataFrame(returns_series)
    
    # 删除任何含有 NaN 的行（确保所有股票在同一天都有数据）
    returns_df = returns_df.dropna()
    
    # 检查是否有足够的数据
    if len(returns_df) < 10:  # 至少需要10天的数据才能计算有意义的相关性
        return None
    
    # 计算相关性矩阵
    corr_matrix = returns_df.corr()
    
    # 创建注释文本（显示相关系数和数据点数）
    annotations_text = []
    for i in range(len(corr_matrix)):
        row_text = []
        for j in range(len(corr_matrix.columns)):
            corr_val = corr_matrix.iloc[i, j]
            if i == j:
                row_text.append(f'{corr_val:.2f}')
            else:
                row_text.append(f'{corr_val:.3f}')
        annotations_text.append(row_text)
    
    # 创建热图
    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns.tolist(),
        y=corr_matrix.index.tolist(),
        colorscale=[
            [0.0, '#d73027'],      # 深红色 (-1)
            [0.25, '#fc8d59'],     # 橙红色 (-0.5)
            [0.5, '#f7f7f7'],      # 白色 (0)
            [0.75, '#91bfdb'],     # 浅蓝色 (0.5)
            [1.0, '#4575b4']       # 深蓝色 (1)
        ],
        zmid=0,
        zmin=-1,
        zmax=1,
        text=annotations_text,
        texttemplate='%{text}',
        textfont={"size": 14, "color": "white", "family": "Arial Black"},
        colorbar=dict(
            title=dict(
                text="相关系数",
                font=dict(size=13, color='#2c3e50'),
                side="right"
            ),
            tickmode="linear",
            tick0=-1,
            dtick=0.25,
            tickfont=dict(size=11),
            len=0.8,
            thickness=15,
        ),
        hovertemplate=(
            '<b>%{y} vs %{x}</b><br>' +
            '相关系数: %{z:.4f}<br>' +
            f'共同交易日: {len(returns_df)}<br>' +
            '<extra></extra>'
        ),
    ))
    
    fig.update_layout(
        title=dict(
            text=f'股票收益率相关性矩阵（基于 {len(returns_df)} 个共同交易日）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5,
            xanchor='center',
            y=0.95,
            yanchor='top'
        ),
        xaxis=dict(
            title='',
            side='bottom',
            tickfont=dict(size=12, color='#2c3e50'),
            showgrid=False,
        ),
        yaxis=dict(
            title='',
            tickfont=dict(size=12, color='#2c3e50'),
            showgrid=False,
        ),
        height=550,
        width=None,  # 自适应宽度
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        margin=dict(l=100, r=100, t=100, b=80),
    )
    
    # 添加说明文本
    fig.add_annotation(
        text='💡 提示：接近1表示正相关，接近-1表示负相关，接近0表示无相关性',
        xref='paper', yref='paper',
        x=0.5, y=-0.12,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=11, color='#7f8c8d', family='Arial'),
    )
    
    return fig


st.set_page_config(page_title="策略实验室", layout="wide")
st.title("📊 策略实验室")
st.caption("训练集上绘制蜡烛图与 RSI/MACD，测试集验证策略并对比买入并持有。")

os.makedirs(DATA_DIR, exist_ok=True)

if st.session_state.get("apply_best_params"):
    best = st.session_state.get("best_params")
    if best:
        st.session_state["adx_threshold"] = int(best["adx_threshold"])
        st.session_state["entry_threshold"] = float(best["entry_threshold"])
        st.session_state["exit_threshold"] = float(best["exit_threshold"])
        st.session_state["stop_loss_mult"] = float(best["stop_loss_mult"])
        st.session_state["take_profit_mult"] = float(best["take_profit_mult"])
    st.session_state["apply_best_params"] = False

with st.sidebar:
    st.header("📊 控制面板")
    
    # ===== 股票选择（统一界面）=====
    st.markdown("---")
    st.subheader("🔍 股票选择")
    
    # 复权方式选择（提前到顶部）
    adjust = st.selectbox("复权方式", options=["qfq", "hfq", "none"], index=0, help="影响数据下载的复权方式。")
    st.session_state["adjust"] = adjust
    
    # 获取已有股票列表
    available_stocks = get_available_stocks()
    
    # 添加新股票/上传CSV（合并到一个折叠中）
    with st.expander("➕ 添加股票 / 上传数据", expanded=False):
        # 添加股票代码
        new_symbol = st.text_input(
            "输入股票代码",
            placeholder="例如: TSLA, NVDA, MSFT",
            help="输入股票代码后点击添加"
        ).upper().strip()
        
        add_stock_btn = st.button("添加到股票列表", use_container_width=True)
        
        if add_stock_btn and new_symbol:
            if new_symbol not in available_stocks:
                # 下载新股票数据
                with st.spinner(f"正在下载 {new_symbol} 数据..."):
                    new_df = load_or_fetch_stock(new_symbol, adjust)
                    if new_df is not None:
                        available_stocks = get_available_stocks()
                        st.success(f"✓ {new_symbol} 添加成功")
            else:
                st.info(f"✓ {new_symbol} 已在数据库中")
        
        st.markdown("---")
        
        # CSV上传（移到这里）
        uploaded_file = st.file_uploader(
            "上传 CSV（列名：open, close, volumn/volume, high, low）",
            type=["csv"],
            help="上传自定义CSV数据文件"
        )
        if uploaded_file:
            st.info("✓ 将使用上传的CSV数据")
    
    # 选择股票
    compare_stocks = []
    if available_stocks:
        compare_stocks = st.multiselect(
            "选择股票",
            options=available_stocks,
            default=[available_stocks[0]] if available_stocks else [],
            help="选择一只股票进行策略分析，或多只股票进行对比分析",
            key="compare_stocks_selector"
        )
        
        if len(compare_stocks) == 1:
            st.info(f"✓ 将分析 {compare_stocks[0]} 的交易策略")
        elif len(compare_stocks) > 1:
            st.info(f"✓ 已选择 {len(compare_stocks)} 只股票进行对比")
    else:
        st.warning("暂无股票数据，请先添加股票")
    
    # 刷新所有已选股票数据
    if compare_stocks:
        if st.button("🔄 刷新所选股票数据", use_container_width=True):
            with st.spinner("正在刷新数据..."):
                success_count = 0
                fail_count = 0
                
                for stock_symbol in compare_stocks:
                    try:
                        # 下载最新数据
                        df_temp = fetch_data(stock_symbol, adjust)
                        data_path = os.path.join(DATA_DIR, f"{stock_symbol.lower()}_daily.csv")
                        
                        # 保存到文件
                        df_temp.to_csv(data_path, index=False)
                        
                        # 显示最新日期
                        if not df_temp.empty and 'date' in df_temp.columns:
                            latest_date = df_temp['date'].max()
                            st.info(f"✓ {stock_symbol}: 已更新至 {latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else latest_date}")
                        
                        success_count += 1
                    except Exception as e:
                        st.error(f"✗ {stock_symbol} 刷新失败: {e}")
                        fail_count += 1
                
                # 清除缓存，确保下次加载使用新数据
                load_csv.clear()
                st.cache_data.clear()
                
                # 显示结果
                if success_count > 0:
                    st.success(f"✓ 数据刷新完成：成功 {success_count} 个，失败 {fail_count} 个")
                st.rerun()
    
    # 保存到session state
    st.session_state['compare_stocks'] = compare_stocks
    
    # 使用选中的第一只股票作为主分析股票
    symbol = compare_stocks[0] if compare_stocks else DEFAULT_SYMBOL
    
    st.markdown("---")
    
    train_ratio = st.slider(
        "训练集比例",
        min_value=0.6,
        max_value=0.9,
        value=0.7,
        step=0.05,
        help="按时间顺序切分训练/测试集。",
    )
    st.markdown("**策略参数（趋势过滤 + MACD/RSI/ATR）**")
    
    # ===== 新增：指标选择器 =====
    st.markdown("##### 🎯 选择使用的入场过滤指标")
    st.caption("勾选后，该指标将作为入场和出场的过滤条件。未勾选的指标仅参与因子评分计算。")
    
    col1, col2 = st.columns(2)
    with col1:
        use_trend_filter = st.checkbox(
            "✓ 趋势过滤 (EMA)",
            value=True,
            help="要求快线>慢线（上升趋势）才允许入场",
            key="use_trend_filter"
        )
        use_rsi_filter = st.checkbox(
            "✓ RSI 过滤",
            value=True,
            help="要求RSI在设定区间内才允许入场",
            key="use_rsi_filter"
        )
    
    with col2:
        use_strength_filter = st.checkbox(
            "✓ 强度过滤 (ADX)",
            value=True,
            help="要求ADX≥阈值（趋势强度足够）才允许入场",
            key="use_strength_filter"
        )
        use_macd_filter = st.checkbox(
            "✓ MACD 过滤",
            value=True,
            help="要求MACD>信号线才允许入场",
            key="use_macd_filter"
        )
    
    # 显示当前启用的过滤器数量
    enabled_count = sum([use_trend_filter, use_strength_filter, use_rsi_filter, use_macd_filter])
    if enabled_count == 4:
        st.info(f"📊 已启用 {enabled_count}/4 个过滤器（完整策略，条件严格）")
    elif enabled_count >= 2:
        st.success(f"📊 已启用 {enabled_count}/4 个过滤器（平衡策略）")
    elif enabled_count == 1:
        st.warning(f"⚠️ 仅启用 {enabled_count}/4 个过滤器（宽松策略，注意风险）")
    else:
        st.error("❌ 未启用任何过滤器（仅依赖因子评分，风险极高）")
    
    st.markdown("---")
    st.markdown("##### 📐 指标参数设置")
    
    # ===== EMA 趋势参数（根据勾选状态显示/折叠）=====
    if use_trend_filter:
        st.markdown("**🔵 趋势 EMA 参数**")
        ema_fast = st.slider("趋势 EMA 快线", 5, 50, 20, help="趋势过滤的短周期 EMA。")
        ema_slow = st.slider("趋势 EMA 慢线", 20, 200, 60, help="趋势过滤的长周期 EMA。")
    else:
        # 未启用时使用默认值
        ema_fast = 20
        ema_slow = 60
        with st.expander("🔘 趋势 EMA 参数（已折叠，点击展开）", expanded=False):
            st.caption("⚠️ 趋势过滤未启用，这些参数仅用于指标计算，不影响入场条件。")
            ema_fast = st.slider("趋势 EMA 快线", 5, 50, 20, help="趋势过滤的短周期 EMA。", key="ema_fast_disabled")
            ema_slow = st.slider("趋势 EMA 慢线", 20, 200, 60, help="趋势过滤的长周期 EMA。", key="ema_slow_disabled")
    
    # ===== ADX 强度参数（根据勾选状态显示/折叠）=====
    if use_strength_filter:
        st.markdown("**🔵 ADX 强度参数**")
        adx_period = st.slider("ADX 周期", 5, 30, 14, help="趋势强度指标的计算周期。")
        adx_threshold = st.slider(
            "ADX 阈值",
            10,
            40,
            20,
            help="ADX 高于该值才认为趋势有效。",
            key="adx_threshold",
        )
    else:
        # 未启用时使用默认值
        adx_period = 14
        adx_threshold = 20
        with st.expander("🔘 ADX 强度参数（已折叠，点击展开）", expanded=False):
            st.caption("⚠️ 强度过滤未启用，这些参数仅用于指标计算，不影响入场条件。")
            adx_period = st.slider("ADX 周期", 5, 30, 14, help="趋势强度指标的计算周期。", key="adx_period_disabled")
            adx_threshold = st.slider(
                "ADX 阈值",
                10,
                40,
                20,
                help="ADX 高于该值才认为趋势有效。",
                key="adx_threshold_disabled",
            )
    
    # ===== MACD 参数（根据勾选状态显示/折叠）=====
    if use_macd_filter:
        st.markdown("**🔵 MACD 参数**")
        macd_fast = st.slider("MACD 快线周期", 5, 20, 12, help="MACD 快线 EMA 周期。")
        macd_slow = st.slider("MACD 慢线周期", 10, 40, 26, help="MACD 慢线 EMA 周期。")
        macd_signal = st.slider("MACD 信号周期", 5, 20, 9, help="MACD 信号线 EMA 周期。")
    else:
        # 未启用时使用默认值
        macd_fast = 12
        macd_slow = 26
        macd_signal = 9
        with st.expander("🔘 MACD 参数（已折叠，点击展开）", expanded=False):
            st.caption("⚠️ MACD 过滤未启用，这些参数仅用于指标计算和因子评分，不影响入场条件。")
            macd_fast = st.slider("MACD 快线周期", 5, 20, 12, help="MACD 快线 EMA 周期。", key="macd_fast_disabled")
            macd_slow = st.slider("MACD 慢线周期", 10, 40, 26, help="MACD 慢线 EMA 周期。", key="macd_slow_disabled")
            macd_signal = st.slider("MACD 信号周期", 5, 20, 9, help="MACD 信号线 EMA 周期。", key="macd_signal_disabled")
    
    # ===== RSI 参数（根据勾选状态显示/折叠）=====
    if use_rsi_filter:
        st.markdown("**🔵 RSI 参数**")
        rsi_period = st.slider("RSI 周期", 5, 30, 14, help="RSI 计算周期。")
        rsi_lower = st.slider("RSI 下限阈值", 10, 50, 30, help="RSI 低于该值视为偏弱。")
        rsi_upper = st.slider("RSI 上限阈值", 50, 90, 70, help="RSI 高于该值视为偏强。")
    else:
        # 未启用时使用默认值
        rsi_period = 14
        rsi_lower = 30
        rsi_upper = 70
        with st.expander("🔘 RSI 参数（已折叠，点击展开）", expanded=False):
            st.caption("⚠️ RSI 过滤未启用，这些参数仅用于指标计算和因子评分，不影响入场条件。")
            rsi_period = st.slider("RSI 周期", 5, 30, 14, help="RSI 计算周期。", key="rsi_period_disabled")
            rsi_lower = st.slider("RSI 下限阈值", 10, 50, 30, help="RSI 低于该值视为偏弱。", key="rsi_lower_disabled")
            rsi_upper = st.slider("RSI 上限阈值", 50, 90, 70, help="RSI 高于该值视为偏强。", key="rsi_upper_disabled")
    
    # ===== ATR 止损止盈参数（始终显示）=====
    st.markdown("**🔵 ATR 止损止盈参数**")
    atr_period = st.slider("ATR 周期", 5, 30, 14, help="波动率（ATR）计算周期。")
    stop_loss_mult = st.slider(
        "ATR 止损倍数",
        0.0,
        5.0,
        2.0,
        step=0.5,
        help="止损距离=ATR×倍数。",
        key="stop_loss_mult",
    )
    take_profit_mult = st.slider(
        "ATR 止盈倍数",
        0.0,
        8.0,
        4.0,
        step=0.5,
        help="止盈距离=ATR×倍数。",
        key="take_profit_mult",
    )
    st.markdown("**因子评分参数**")
    momentum_short = st.slider("短期动量窗口", 2, 20, 5, help="短期收益率窗口。")
    momentum_long = st.slider("中期动量窗口", 10, 60, 20, help="中期收益率窗口。")
    score_lookback = st.slider("评分标准化窗口", 10, 120, 30, help="用于计算滚动 Z 分数的窗口。")
    score_mid_pct = st.slider(
        "评分分位数-中档",
        0.5,
        0.9,
        0.6,
        step=0.05,
        help="评分分位数达到该值进入中档仓位。",
    )
    score_high_pct = st.slider(
        "评分分位数-高档",
        0.6,
        0.95,
        0.8,
        step=0.05,
        help="评分分位数达到该值进入高档仓位。",
    )
    weight_mom_short = st.slider(
        "短期动量权重",
        0.0,
        3.0,
        1.0,
        step=0.1,
        help="短期动量在评分中的权重。",
    )
    weight_mom_long = st.slider(
        "中期动量权重",
        0.0,
        3.0,
        1.0,
        step=0.1,
        help="中期动量在评分中的权重。",
    )
    weight_macd = st.slider(
        "MACD 权重",
        0.0,
        3.0,
        1.0,
        step=0.1,
        help="MACD 柱在评分中的权重。",
    )
    weight_rsi = st.slider(
        "RSI 权重",
        0.0,
        3.0,
        0.5,
        step=0.1,
        help="RSI 在评分中的权重。",
    )
    weight_vol = st.slider(
        "波动惩罚权重",
        0.0,
        3.0,
        0.5,
        step=0.1,
        help="波动率越高，评分惩罚越大。",
    )
    
    st.markdown("**入场逻辑**")
    entry_logic = st.radio(
        "过滤条件组合方式",
        ["严格模式 (AND)", "评分模式 (推荐)"],
        index=1,
        help="严格模式：所有条件必须同时满足\n评分模式：条件加权投票，达到阈值即可"
    )
    
    use_voting_entry = (entry_logic == "评分模式 (推荐)")
    
    if use_voting_entry:
        entry_vote_threshold = st.slider(
            "入场投票阈值",
            1.0,
            5.0,
            2.5,
            step=0.5,
            help="满分5.0分。评分制：因子评分(2分)+趋势(1分)+强度(1分)+RSI(0.5分)+MACD(0.5分)"
        )
    
    entry_threshold = st.slider(
        "入场评分阈值",
        -2.0,
        2.0,
        0.5,
        step=0.1,
        help="评分高于该值才考虑开仓。",
        key="entry_threshold",
    )
    exit_threshold = st.slider(
        "出场评分阈值",
        -2.0,
        2.0,
        -0.5,
        step=0.1,
        help="评分低于该值考虑离场。",
        key="exit_threshold",
    )

# ===== 数据加载逻辑 =====
# 检查是否有选中的股票
if not compare_stocks:
    st.warning("请在侧边栏选择至少一只股票进行分析。")
    st.stop()

data_path = os.path.join(DATA_DIR, f"{symbol.lower()}_daily.csv")

if uploaded_file is not None:
    df_raw = load_uploaded_bytes(uploaded_file.getvalue())
    st.info("已使用上传的数据集。")
else:
    if not os.path.exists(data_path):
        with st.spinner(f"正在从 AkShare 下载 {symbol} 数据..."):
            try:
                df_raw = fetch_data(symbol, adjust)
            except Exception as exc:
                st.error(f"下载失败：{exc}")
                st.stop()
            df_raw.to_csv(data_path, index=False)
            st.success(f"已保存至 {data_path}")
    else:
        df_raw = load_csv(data_path)

if df_raw.empty:
    st.warning("没有加载到数据。")
    st.stop()

required_cols = {"open", "high", "low", "close"}
missing_cols = required_cols - set(df_raw.columns)
if missing_cols:
    st.error(f"缺少必需列：{', '.join(sorted(missing_cols))}")
    st.stop()

if ema_fast >= ema_slow:
    st.sidebar.error("趋势 EMA 快线需要小于慢线。")
    st.stop()
if macd_fast >= macd_slow:
    st.sidebar.error("MACD 快线周期需要小于慢线周期。")
    st.stop()
if rsi_lower >= rsi_upper:
    st.sidebar.error("RSI 下限需要小于上限。")
    st.stop()
if momentum_short >= momentum_long:
    st.sidebar.error("短期动量窗口需要小于中期动量窗口。")
    st.stop()
if score_mid_pct >= score_high_pct:
    st.sidebar.error("中档分位数需要小于高档分位数。")
    st.stop()

is_datetime = pd.api.types.is_datetime64_any_dtype(df_raw["date"])
selected_range = None
if is_datetime:
    min_date = df_raw["date"].min().date()
    max_date = df_raw["date"].max().date()
    default_end = max_date
    default_start_ts = df_raw["date"].max() - pd.Timedelta(days=30)
    default_start = default_start_ts.date()
    if default_start < min_date:
        default_start = min_date
    selected_range = st.sidebar.date_input(
        "时间区间",
        value=(default_start, default_end),
        min_value=min_date,
        max_value=max_date,
        help="选择开始和结束日期来筛选数据"
    )
    
    # 检查用户是否完成了日期选择
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        df_raw = df_raw[(df_raw["date"] >= start_ts) & (df_raw["date"] <= end_ts)]
    elif isinstance(selected_range, tuple) and len(selected_range) == 1:
        # 用户只选择了一个日期，使用该日期作为开始日期，结束日期为最大日期
        st.sidebar.info("💡 请选择结束日期以完成时间区间设置")
        start_date = selected_range[0]
        end_date = max_date
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        df_raw = df_raw[(df_raw["date"] >= start_ts) & (df_raw["date"] <= end_ts)]
    else:
        # 用户正在选择第一个日期，显示提示并使用默认范围
        st.sidebar.info("💡 请选择开始和结束日期")
        start_ts = pd.Timestamp(default_start)
        end_ts = pd.Timestamp(default_end)
        df_raw = df_raw[(df_raw["date"] >= start_ts) & (df_raw["date"] <= end_ts)]
else:
    st.sidebar.info("当前数据不包含日期列，无法进行时间区间筛选。")

if df_raw.empty:
    st.warning("所选时间区间内没有数据。")
    st.stop()

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
    # 新增：传递指标开关参数
    use_trend_filter=use_trend_filter,
    use_strength_filter=use_strength_filter,
    use_rsi_filter=use_rsi_filter,
    use_macd_filter=use_macd_filter,
    # 新增：传递入场逻辑参数
    use_voting_entry=use_voting_entry,
    entry_vote_threshold=entry_vote_threshold if use_voting_entry else 2.5,
)

with st.sidebar:
    st.markdown("**Walk-Forward 回测**")
    enable_walk = st.checkbox("启用 Walk-Forward", value=True)
    max_window = max(5, len(df) - 1)
    min_train = min(20, max_window)
    min_test = min(5, max_window)
    if max_window <= min_train:
        st.info("数据量较少，已固定训练/测试窗口。")
        train_window = max_window
        test_window = max_window
    else:
        train_window = st.slider(
            "训练窗口（交易日）",
            min_train,
            max_window,
            min(252, max_window),
            help="每次用训练窗口后接测试窗口滚动回测。",
        )
        test_window = st.slider(
            "测试窗口（交易日）",
            min_test,
            max_window,
            min(63, max_window),
            help="每次滚动的测试区间长度。",
        )
    st.markdown("**参数自动推荐**")
    
    # 优化方法选择
    optimization_method = st.radio(
        "优化方法",
        ["贝叶斯优化 (推荐)", "随机搜索"],
        help="贝叶斯优化：智能搜索，收敛快，适合优化多个参数\n随机搜索：简单但效率低"
    )
    
    if optimization_method == "贝叶斯优化 (推荐)":
        search_trials = st.slider("优化次数", 20, 150, 60, help="贝叶斯优化试验次数，建议 50-100 次。")
    else:
        search_trials = st.slider("搜索次数", 10, 200, 40, help="随机搜索次数，越大越耗时。")
    
    run_search = st.button("自动搜索参数")
    if st.session_state.get("best_params"):
        apply_params_sidebar = st.button(
            "应用推荐参数",
            key="apply_params_sidebar",
            help="将推荐的阈值与止损止盈写入侧边栏。",
        )
        if apply_params_sidebar:
            st.session_state["apply_best_params"] = True
            st.rerun()
    else:
        st.caption("先运行自动搜索后才能应用推荐参数。")

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

# ===== 根据选择的股票数量显示不同内容 =====
compare_stocks = st.session_state.get('compare_stocks', [])

if len(compare_stocks) > 1:
    # ========================================
    # 多股票对比分析模式
    # ========================================
    st.markdown("---")
    st.header("📈 多股票价格对比分析")
    
    with st.spinner("加载对比股票数据..."):
        # 加载所有选中的股票数据
        stock_data_dict = {}
        for stock_symbol in compare_stocks:
            stock_df = load_or_fetch_stock(stock_symbol, adjust)
            if stock_df is not None and not stock_df.empty:
                # 应用相同的时间筛选
                if is_datetime and selected_range:
                    stock_df = stock_df[(stock_df["date"] >= start_ts) & (stock_df["date"] <= end_ts)]
                stock_data_dict[stock_symbol] = stock_df
    
    if len(stock_data_dict) > 0:
        # 创建归一化价格对比图
        comparison_fig = create_multi_stock_comparison_chart(
            stock_data_dict,
            title=f"多股票价格对比（共 {len(stock_data_dict)} 只）"
        )
        st.plotly_chart(comparison_fig, use_container_width=True)
        
        # 显示关键统计数据
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("对比股票数量", len(stock_data_dict))
        
        with col2:
            if stock_data_dict:
                avg_days = int(np.mean([len(df) for df in stock_data_dict.values()]))
                st.metric("平均数据天数", f"{avg_days:,}")
        
        with col3:
            if stock_data_dict:
                # 计算期间收益率
                returns = {}
                for sym, df in stock_data_dict.items():
                    if len(df) > 0:
                        returns[sym] = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
                if returns:
                    best_performer = max(returns, key=returns.get)
                    st.metric("最佳表现", f"{best_performer}", f"{returns[best_performer]:.2f}%")
        
        # 详细对比表格
        with st.expander("📊 详细统计对比", expanded=False):
            comparison_stats = []
            for sym, df in stock_data_dict.items():
                if len(df) > 0:
                    total_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
                    volatility = df['close'].pct_change().std() * np.sqrt(252) * 100
                    max_price = df['close'].max()
                    min_price = df['close'].min()
                    
                    comparison_stats.append({
                        '股票': sym,
                        '起始价格': f"${df['close'].iloc[0]:.2f}",
                        '最新价格': f"${df['close'].iloc[-1]:.2f}",
                        '总收益率': f"{total_return:.2f}%",
                        '年化波动率': f"{volatility:.2f}%",
                        '最高价': f"${max_price:.2f}",
                        '最低价': f"${min_price:.2f}",
                        '数据天数': len(df),
                    })
            
            if comparison_stats:
                comparison_df = pd.DataFrame(comparison_stats)
                st.dataframe(comparison_df, use_container_width=True, hide_index=True)
        
        # 添加相关性热图
        if len(stock_data_dict) >= 2:
            st.markdown("### 📊 股票相关性分析")
            
            with st.spinner("计算相关性矩阵..."):
                corr_fig = create_correlation_heatmap(stock_data_dict)
            
            if corr_fig:
                st.plotly_chart(corr_fig, use_container_width=True)
            else:
                st.warning("⚠️ 数据不足以计算相关性（需要至少10个共同交易日）")
        
        # 添加导出HTML功能
        st.markdown("---")
        st.markdown("### 📤 导出分析报告")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            export_title = st.text_input("报告标题", value=f"多股票对比分析 - {', '.join(compare_stocks)}", key="export_title")
        with col2:
            include_date = st.checkbox("包含生成日期", value=True, key="include_date")
        
        if st.button("🎁 生成并下载HTML报告", type="primary", use_container_width=True):
            with st.spinner("正在生成HTML报告..."):
                # 生成HTML内容
                html_parts = []
                
                # HTML头部
                html_parts.append(f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{export_title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: 'Source Sans Pro', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #fafafa;
            color: #31333f;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 30px;
        }}
        .metadata {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 30px;
            font-size: 14px;
            color: #7f8c8d;
        }}
        .metrics {{
            display: flex;
            justify-content: space-around;
            margin: 30px 0;
            flex-wrap: wrap;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            min-width: 200px;
            margin: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-label {{
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 8px;
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: bold;
        }}
        .metric-delta {{
            font-size: 18px;
            margin-top: 8px;
        }}
        .chart-container {{
            margin: 30px 0;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }}
        th {{
            background: #34495e;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            color: #95a5a6;
            font-size: 12px;
        }}
        .info-box {{
            background: #e8f4f8;
            border-left: 4px solid #3498db;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 {export_title}</h1>
""")
                
                # 添加元数据
                if include_date:
                    from datetime import datetime
                    html_parts.append(f"""
        <div class="metadata">
            <strong>生成时间：</strong>{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}<br>
            <strong>分析股票：</strong>{', '.join(compare_stocks)}<br>
            <strong>数据来源：</strong>AkShare API
        </div>
""")
                
                # 添加关键指标卡片
                total_stocks = len(stock_data_dict)
                avg_days = sum(len(df) for df in stock_data_dict.values()) / total_stocks if total_stocks > 0 else 0
                returns = {}
                for sym, df_data in stock_data_dict.items():
                    if len(df_data) > 0:
                        returns[sym] = (df_data['close'].iloc[-1] / df_data['close'].iloc[0] - 1) * 100
                best_performer = max(returns, key=returns.get) if returns else "N/A"
                best_return = returns.get(best_performer, 0)
                
                html_parts.append(f"""
        <h2>📈 关键指标</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">对比股票数量</div>
                <div class="metric-value">{total_stocks}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">平均数据天数</div>
                <div class="metric-value">{int(avg_days)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">最佳表现</div>
                <div class="metric-value">{best_performer}</div>
                <div class="metric-delta">{"↓" if best_return < 0 else "↑"} {best_return:.2f}%</div>
            </div>
        </div>
""")
                
                # 添加归一化价格对比图
                html_parts.append("""
        <h2>📊 价格走势对比（归一化）</h2>
        <div class="info-box">
            💡 所有股票的起始价格归一化为100，便于直观对比相对涨跌幅
        </div>
        <div class="chart-container">
            <div id="price-chart"></div>
        </div>
        <script>
""")
                # 将Plotly图表转换为HTML
                comparison_fig = create_multi_stock_comparison_chart(stock_data_dict)
                if comparison_fig:
                    html_parts.append(f"""
            var priceData = {comparison_fig.to_json()};
            Plotly.newPlot('price-chart', priceData.data, priceData.layout, {{responsive: true}});
""")
                
                html_parts.append("        </script>")
                
                # 添加统计表格
                if comparison_stats:
                    html_parts.append("""
        <h2>📋 详细统计对比</h2>
        <table>
            <thead>
                <tr>
                    <th>股票</th>
                    <th>起始价格</th>
                    <th>最新价格</th>
                    <th>总收益率</th>
                    <th>年化波动率</th>
                    <th>最高价</th>
                    <th>最低价</th>
                    <th>数据天数</th>
                </tr>
            </thead>
            <tbody>
""")
                    for stat in comparison_stats:
                        html_parts.append(f"""
                <tr>
                    <td><strong>{stat['股票']}</strong></td>
                    <td>{stat['起始价格']}</td>
                    <td>{stat['最新价格']}</td>
                    <td>{stat['总收益率']}</td>
                    <td>{stat['年化波动率']}</td>
                    <td>{stat['最高价']}</td>
                    <td>{stat['最低价']}</td>
                    <td>{stat['数据天数']}</td>
                </tr>
""")
                    html_parts.append("""
            </tbody>
        </table>
""")
                
                # 添加相关性热图
                if len(stock_data_dict) >= 2 and corr_fig:
                    html_parts.append("""
        <h2>🔥 股票相关性分析</h2>
        <div class="info-box">
            💡 相关系数接近1表示正相关（走势相似），接近-1表示负相关（走势相反），接近0表示无相关性
        </div>
        <div class="chart-container">
            <div id="correlation-chart"></div>
        </div>
        <script>
""")
                    html_parts.append(f"""
            var corrData = {corr_fig.to_json()};
            Plotly.newPlot('correlation-chart', corrData.data, corrData.layout, {{responsive: true}});
""")
                    html_parts.append("        </script>")
                
                # HTML尾部
                html_parts.append("""
        <div class="footer">
            <p>📊 由策略实验室 Streamlit App 生成</p>
            <p>数据来源：AkShare | 图表技术：Plotly.js</p>
        </div>
    </div>
</body>
</html>
""")
                
                # 合并HTML
                full_html = "".join(html_parts)
                
                # 提供下载
                st.download_button(
                    label="⬇️ 下载HTML报告",
                    data=full_html,
                    file_name=f"stock_comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                    mime="text/html",
                    type="primary",
                    use_container_width=True
                )
                st.success("✅ HTML报告已生成！点击上方按钮下载")

else:
    # ========================================
    # 单股票策略分析模式
    # ========================================
    st.subheader("数据集概览")
    if pd.api.types.is_datetime64_any_dtype(df["date"]):
        date_range = f"{df['date'].min().date()} 到 {df['date'].max().date()}"
    else:
        date_range = "行索引"
    st.write(
        f"行数：{len(df):,} | 训练：{len(train_df):,} | 测试：{len(test_df):,} | "
        f"日期范围：{date_range}"
    )

    st.subheader("训练集：蜡烛图")
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
    
    if show_volume:
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
    st.plotly_chart(candle, use_container_width=True)
    
    st.subheader("训练集：RSI + MACD")
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
    st.plotly_chart(ind_fig, use_container_width=True)
    
    st.subheader("因子评分")
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
    st.plotly_chart(score_fig, use_container_width=True)
    
    st.subheader("策略建议（最新数据）")
    st.caption("策略组合：因子评分/分位数 + 趋势/强度过滤 + MACD 上方 + RSI 区间 + 仓位分档 + ATR 止损止盈。")
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
    
    if run_search:
        if split_idx < 50:
            st.warning("训练数据太少，无法进行参数搜索。")
        else:
            # 根据选择的方法进行优化
            if optimization_method == "贝叶斯优化 (推荐)":
                with st.spinner(f"正在进行贝叶斯优化（{search_trials} 次试验）..."):
                    best_params = bayesian_optimize_params(
                        df_indicators,
                        split_idx=split_idx,
                        rsi_lower=rsi_lower,
                        rsi_upper=rsi_upper,
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
                        n_trials=search_trials,
                        use_trend_filter=use_trend_filter,
                        use_strength_filter=use_strength_filter,
                        use_rsi_filter=use_rsi_filter,
                        use_macd_filter=use_macd_filter,
                    )
            else:
                with st.spinner(f"正在随机搜索参数（{search_trials} 次）..."):
                    best_params = random_search_params(
                        df_indicators,
                        split_idx=split_idx,
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
                        trials=search_trials,
                        use_trend_filter=use_trend_filter,
                        use_strength_filter=use_strength_filter,
                        use_rsi_filter=use_rsi_filter,
                        use_macd_filter=use_macd_filter,
                    )
            
            if best_params:
                st.session_state["best_params"] = best_params
                st.success("✓ 参数优化完成！")
            else:
                st.error("参数优化失败，请检查数据。")
    
    st.subheader("参数推荐")
    best = st.session_state.get("best_params")
    if best:
        optimization_info = "贝叶斯优化" if "weight_bb" in best else "随机搜索"
        st.write(f"基于训练集的**{optimization_info}**结果（供参考，需自行验证）。")
        
        # 显示性能指标
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("综合评分", f"{best['score']:.2f}")
        with col2:
            st.metric("训练集收益", format_pct(best['return']))
        with col3:
            st.metric("夏普比率", f"{best['sharpe']:.2f}")
        
        if "max_drawdown" in best:
            st.write(f"**最大回撤**: {format_pct(best['max_drawdown'])}")
        
        # 显示核心参数
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
        
        # 如果是贝叶斯优化，显示新因子权重
        if "weight_bb" in best:
            with st.expander("📊 新因子权重（Phase 1）", expanded=False):
                st.write(f"布林带位置权重: {best['weight_bb']:.2f}")
                st.write(f"OBV 趋势权重: {best['weight_obv']:.2f}")
                st.write(f"成交量比率权重: {best['weight_volume']:.2f}")
                st.write(f"价格位置权重: {best['weight_price']:.2f}")
                st.write(f"回撤惩罚权重: {best['weight_drawdown']:.2f}")
                st.caption("💡 这些权重由贝叶斯优化自动搜索得出")
        st.write(
            f"ATR 止损倍数：{best['stop_loss_mult']:.1f} | ATR 止盈倍数：{best['take_profit_mult']:.1f}"
        )
        apply_params = st.button(
            "应用推荐参数",
            key="apply_params_main",
            help="将推荐的阈值与止损止盈写入侧边栏。",
        )
        if apply_params:
            st.session_state["apply_best_params"] = True
            st.rerun()
    else:
        st.info("请先点击侧边栏的“自动搜索参数”。")
    
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
            x=test_df["date"], y=test_df["strategy_equity"], name="Strategy", line=dict(color="#17becf")
        )
    )
    equity_fig.add_trace(
        go.Scatter(
            x=test_df["date"], y=test_df["buy_hold_equity"], name="Buy & Hold", line=dict(color="#bcbd22")
        )
    )
    equity_fig.update_layout(height=420, xaxis_title="日期", yaxis_title="净值（起始=1.0）")
    st.plotly_chart(equity_fig, use_container_width=True)
    
    st.subheader("Walk-Forward 回测")
    if not enable_walk:
        st.info("已关闭 Walk-Forward 回测。")
    else:
        if train_window + test_window > len(df):
            st.warning("训练窗口 + 测试窗口超过数据长度，请调小窗口。")
        else:
            wf_results, wf_equity = walk_forward_backtest(
                df,
                train_window=train_window,
                test_window=test_window,
                stop_loss_mult=stop_loss_mult,
                take_profit_mult=take_profit_mult,
            )
            if wf_equity.empty:
                st.warning("Walk-Forward 回测未产生结果。")
            else:
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
                st.plotly_chart(wf_fig, use_container_width=True)
                if not wf_results.empty:
                    wf_results_display = wf_results.copy()
                    wf_results_display["test_return"] = wf_results_display["test_return"].map(format_pct)
                    wf_results_display["test_max_drawdown"] = wf_results_display["test_max_drawdown"].map(
                        format_pct
                    )
                    st.dataframe(wf_results_display, use_container_width=True)
    
    st.subheader("测试集交易信号")
    signal_fig = go.Figure(
        data=[
            go.Scatter(
                x=test_df["date"], y=test_df["close"], mode="lines", name="Close", line=dict(color="#1f77b4")
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
    st.plotly_chart(signal_fig, use_container_width=True)
