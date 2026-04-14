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
import tempfile  # 用于创建临时目录（数据缓存不占用持久存储）

import akshare as ak  # AkShare：国产金融数据接口库，用于下载股票数据
import numpy as np  # NumPy：数值计算库
import pandas as pd  # Pandas：数据分析库，处理表格数据
import plotly.graph_objects as go  # Plotly：交互式图表库
from plotly.subplots import make_subplots  # 用于创建子图
import streamlit as st  # Streamlit：快速构建 Web 应用的框架


# ============ 全局常量配置 ============
# 使用系统临时目录缓存股票数据，不占用持久磁盘空间
# 服务重启后缓存自动清理，数据按需重新下载
DATA_DIR = os.path.join(tempfile.gettempdir(), "stratagy_cache")
DEFAULT_SYMBOL = "AAPL"  # 默认股票代码（苹果公司）
DEFAULT_ADJUST = "qfq"  # 默认复权方式：前复权（qfq=前复权，hfq=后复权，none=不复权）

# 默认股票列表（硬编码，无需预下载 CSV 文件）
# 用户可以通过界面添加更多股票
DEFAULT_STOCKS = ["AAPL", "TSLA", "NVDA", "GOOGL", "META", "ORCL", "ADM", "NTR", "CTVA"]

# ===== 预设策略参数（供高级策略预评估使用）=====
# 注意：这些参数与 UI 中的 STRATEGY_PRESETS 保持一致
_PRESET_PARAMS_FOR_OPTIMIZATION = {
    "趋势跟随（保守）": {
        "entry_threshold": 0.2, "exit_threshold": -0.3,
        "adx_threshold": 15, "stop_loss_mult": 1.5, "take_profit_mult": 3.0,
        "ema_fast": 20, "ema_slow": 60,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "rsi_period": 14, "rsi_lower": 35, "rsi_upper": 65,
        "adx_period": 14, "atr_period": 14,
        "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
        "weight_bb": 0.8, "weight_obv": 1.0,
        "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
    },
    "均衡策略（默认）": {
        "entry_threshold": 0.5, "exit_threshold": -0.5,
        "adx_threshold": 20, "stop_loss_mult": 2.0, "take_profit_mult": 4.0,
        "ema_fast": 20, "ema_slow": 60,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "rsi_period": 14, "rsi_lower": 30, "rsi_upper": 70,
        "adx_period": 14, "atr_period": 14,
        "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
        "weight_bb": 0.8, "weight_obv": 1.0,
        "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
    },
    "动量突破（激进）": {
        "entry_threshold": 0.8, "exit_threshold": -0.2,
        "adx_threshold": 25, "stop_loss_mult": 3.0, "take_profit_mult": 6.0,
        "ema_fast": 15, "ema_slow": 50,
        "macd_fast": 10, "macd_slow": 22, "macd_signal": 8,
        "rsi_period": 12, "rsi_lower": 25, "rsi_upper": 75,
        "adx_period": 12, "atr_period": 12,
        "bb_period": 18, "bb_std": 2.2, "indicator_period": 18,
        "weight_bb": 0.6, "weight_obv": 1.2,
        "weight_volume": 0.8, "weight_price": 0.5, "weight_drawdown": 0.3,
    },
}


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
    bb_period: int = 20,
    bb_std: float = 2.0,
    indicator_period: int = 20,
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
    - 布林带、OBV趋势、成交量比率、价格位置
    
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
        bb_period: 布林带计算周期（默认20）
        bb_std: 布林带标准差倍数（默认2.0）
        indicator_period: OBV趋势/成交量均量/价格位置的计算周期（默认20）
    
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
        df["close"], period=bb_period, std_dev=bb_std
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
    
    # OBV 趋势（indicator_period日变化率）
    df["obv_trend"] = df["obv"].pct_change(indicator_period)
    
    # 成交量变化率（相对于indicator_period日均量）
    avg_volume = df["volume"].rolling(indicator_period).mean()
    df["volume_ratio"] = df["volume"] / avg_volume
    
    # 最大回撤（从历史最高点的跌幅）
    cummax = df["close"].cummax()
    df["drawdown"] = (df["close"] / cummax - 1)
    
    # 价格相对位置（在近期高低点的位置）
    period_high = df["high"].rolling(indicator_period).max()
    period_low = df["low"].rolling(indicator_period).min()
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
    # 新增：出场信号计数阈值
    exit_min_signals: int = 2,
    # 新增：入场信号计数阈值（0=使用旧逻辑，>0=计数制）
    entry_min_signals: int = 3,
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
            df["factor_percentile"] >= 0.80,  # 极强信号
            df["factor_percentile"] >= 0.65,  # 强信号
            df["factor_percentile"] >= 0.55,  # 较强信号
            df["factor_percentile"] >= 0.45,  # 中等信号
            df["factor_percentile"] >= 0.35,  # 弱信号
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
    
    # ========== 步骤7：应用入场过滤条件（计数制）==========
    # MACD 在信号线上方
    macd_above = df["macd"] > df["signal"]
    
    if entry_min_signals > 0:
        # ========== 计数制入场（新逻辑）==========
        # 每个条件计 1 分，达到 entry_min_signals 个即可入场
        entry_count = pd.Series(0, index=df.index, dtype=int)
        
        # 条件1：因子评分达标
        entry_count += (df["factor_score"] >= entry_threshold).astype(int)
        
        # 条件2：趋势向上
        entry_count += df["trend_ok"].astype(int)
        
        # 条件3：强度足够
        entry_count += df["strength_ok"].astype(int)
        
        # 条件4：RSI 正常
        entry_count += df["rsi_ok"].astype(int)
        
        # 条件5：MACD 向上
        entry_count += macd_above.astype(int)
        
        # 达到最少信号数才允许入场
        filter_ok = entry_count >= entry_min_signals
    
    elif use_voting_entry:
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
    
    # ========== 步骤8：应用出场条件（计数制，至少N个信号才出场）==========
    # 每个出场条件独立计数，达到 exit_min_signals 个才触发出场
    exit_count = pd.Series(0, index=df.index, dtype=int)
    
    # 基础条件：评分过低
    exit_count += (df["factor_score"] <= exit_threshold).astype(int)
    
    # 可选条件：趋势反转
    if use_trend_filter:
        exit_count += (df["ema_fast"] < df["ema_slow"]).astype(int)
    
    # 可选条件：RSI 超出范围
    if use_rsi_filter:
        exit_count += ((df["rsi"] > rsi_upper) | (df["rsi"] < rsi_lower)).astype(int)
    
    # 可选条件：MACD 转弱
    if use_macd_filter:
        exit_count += (df["macd"] < df["signal"]).astype(int)
    
    # 达到最少信号数才触发出场
    exit_block = exit_count >= exit_min_signals
    
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


# ============ 预设策略预评估 ============

def evaluate_presets_for_optimization(
    df_raw: pd.DataFrame,
    split_idx: int,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
) -> tuple[dict, str, list[tuple[str, float]]]:
    """
    快速评估 3 个预设策略在训练集上的表现，返回最佳预设参数。
    
    【用途】
    在贝叶斯优化/遗传算法开始前调用，选出最优起点，减少搜索次数。
    
    参数：
        df_raw: 原始价格数据
        split_idx: 训练/测试集分割点
        其他：固定策略参数
    
    返回：
        (best_params_dict, best_name, scores_list)
        - best_params_dict: 最佳预设的参数字典
        - best_name: 最佳预设名称
        - scores_list: [(名称, 评分), ...] 所有预设的评分
    """
    # 防过拟合：使用子训练集+子验证集
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx

    best_score = -np.inf
    best_name = ""
    best_params = None
    scores = []

    for name, params in _PRESET_PARAMS_FOR_OPTIMIZATION.items():
        try:
            df_ind = add_indicators(
                df_raw,
                rsi_period=params["rsi_period"],
                macd_fast=params["macd_fast"],
                macd_slow=params["macd_slow"],
                macd_signal=params["macd_signal"],
                ema_fast=params["ema_fast"],
                ema_slow=params["ema_slow"],
                adx_period=params["adx_period"],
                atr_period=params["atr_period"],
                bb_period=params["bb_period"],
                bb_std=params["bb_std"],
                indicator_period=params["indicator_period"],
            )
            df_sig = compute_signals(
                df_ind,
                rsi_lower=params["rsi_lower"],
                rsi_upper=params["rsi_upper"],
                adx_threshold=params["adx_threshold"],
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
                entry_threshold=params["entry_threshold"],
                exit_threshold=params["exit_threshold"],
                use_trend_filter=use_trend_filter,
                use_strength_filter=use_strength_filter,
                use_rsi_filter=use_rsi_filter,
                use_macd_filter=use_macd_filter,
                weight_bb=params["weight_bb"],
                weight_obv=params["weight_obv"],
                weight_volume=params["weight_volume"],
                weight_price=params["weight_price"],
                weight_drawdown=params["weight_drawdown"],
                exit_min_signals=2,
                entry_min_signals=3,
            )

            # 子训练集回测
            train_sim = simulate_strategy(
                df_sig.iloc[:sub_train_end],
                initial_position=0,
                stop_loss_mult=params["stop_loss_mult"],
                take_profit_mult=params["take_profit_mult"],
            )
            train_return = train_sim["strategy_equity"].iloc[-1] - 1
            train_sharpe = sharpe_ratio(train_sim["strategy_return"])
            train_dd = max_drawdown(train_sim["strategy_equity"])
            train_score = train_sharpe + train_return - abs(train_dd) * 0.5

            # 子验证集
            if sub_train_end < split_idx:
                val_sim = simulate_strategy(
                    df_sig.iloc[sub_train_end:split_idx],
                    initial_position=0,
                    stop_loss_mult=params["stop_loss_mult"],
                    take_profit_mult=params["take_profit_mult"],
                )
                val_return = val_sim["strategy_equity"].iloc[-1] - 1
                val_sharpe = sharpe_ratio(val_sim["strategy_return"])
                val_dd = max_drawdown(val_sim["strategy_equity"])
                val_score = val_sharpe + val_return - abs(val_dd) * 0.5
                score = 0.4 * train_score + 0.6 * val_score - 0.3 * abs(train_score - val_score)
            else:
                score = train_score

            scores.append((name, score))
            if score > best_score:
                best_score = score
                best_name = name
                best_params = params.copy()
        except Exception:
            scores.append((name, -np.inf))

    return best_params or {}, best_name, scores


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
    progress_callback=None,
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
    
    # ===== 防过拟合：将训练集拆为子训练集(70%)和子验证集(30%) =====
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx  # 数据太少时不拆分
    
    # 参数默认值和范围，用于正则化
    _rs_param_defaults = {
        "entry_threshold": (0.5, -1.0, 1.5), "exit_threshold": (-0.5, -1.5, 0.5),
        "adx_threshold": (20, 10, 35), "stop_loss_mult": (2.0, 0.0, 4.0),
        "take_profit_mult": (4.0, 0.0, 6.0),
    }
    
    # ========== 主循环：随机搜索 ==========
    for trial_i in range(trials):
        if progress_callback:
            progress_callback(trial_i, trials)
        
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
            exit_min_signals=2,
            entry_min_signals=3,
        )
        
        # 防过拟合：在子训练集上回测
        train_sim = simulate_strategy(
            df_signals.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        # 计算表现指标
        train_return = train_sim["strategy_equity"].iloc[-1] - 1
        train_sharpe = sharpe_ratio(train_sim["strategy_return"])
        train_score = train_sharpe + train_return
        
        # 如果有子验证集，验证泛化能力
        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                df_signals.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=stop_loss_mult,
                take_profit_mult=take_profit_mult,
            )
            val_return = val_sim["strategy_equity"].iloc[-1] - 1
            val_sharpe = sharpe_ratio(val_sim["strategy_return"])
            val_score = val_sharpe + val_return
            score = 0.4 * train_score + 0.6 * val_score - 0.3 * abs(train_score - val_score)
        else:
            score = train_score
            val_sharpe = train_sharpe
            val_return = train_return
        
        # 正则化惩罚
        reg_penalty = 0.0
        for pname, pval in [("entry_threshold", entry_threshold), ("exit_threshold", exit_threshold),
                            ("adx_threshold", adx_candidate), ("stop_loss_mult", stop_loss_mult),
                            ("take_profit_mult", take_profit_mult)]:
            if pname in _rs_param_defaults:
                default, lo, hi = _rs_param_defaults[pname]
                span = hi - lo
                if span > 0:
                    reg_penalty += ((pval - default) / span) ** 2
        score -= 0.02 * reg_penalty
        
        # 更新最佳参数
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "sharpe": train_sharpe,
                "return": train_return,
                "val_sharpe": val_sharpe,
                "val_return": val_return,
                "adx_threshold": adx_candidate,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "stop_loss_mult": stop_loss_mult,
                "take_profit_mult": take_profit_mult,
            }
    
    return best


def bayesian_optimize_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    n_trials: int,
    # 以下为固定参数（不参与优化）
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    progress_callback=None,
    seed_params: dict | None = None,
) -> dict | None:
    """
    使用贝叶斯优化（Optuna）搜索最优参数
    
    【热启动】
    如果提供 seed_params（预评估最佳预设参数），会作为第一个试验点注入 Optuna，
    让优化器从已知较优解出发，显著加快收敛速度。
    
    【优化范围】
    本函数同时优化两个层级的参数：
    
    一、指标层参数（技术指标的计算周期）：
    - ema_fast / ema_slow: EMA 快慢线周期
    - macd_fast / macd_slow / macd_signal: MACD 三线周期
    - rsi_period / rsi_lower / rsi_upper: RSI 周期与阈值
    - adx_period / adx_threshold: ADX 周期与阈值
    - atr_period: ATR 周期
    - bb_period / bb_std: 布林带周期与标准差倍数
    - indicator_period: OBV/成交量/价格位置共用周期
    
    二、策略层参数（信号生成与风控）：
    - entry_threshold / exit_threshold: 入场/出场评分阈值
    - stop_loss_mult / take_profit_mult: ATR 止损/止盈倍数
    - weight_bb / weight_obv / weight_volume / weight_price / weight_drawdown: 因子权重
    
    参数：
        df_raw: 原始价格数据（未计算指标）
        split_idx: 训练/测试集分割点
        n_trials: 优化试验次数（建议 80-150 次）
        其他参数：固定的策略参数（不参与优化搜索）
    
    返回：
        最佳参数字典
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        st.error("需要安装 optuna 库。请运行：pip install optuna")
        return None
    
    best_result = {"score": -np.inf}
    
    # ===== 防过拟合：将训练集拆为子训练集(70%)和子验证集(30%) =====
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx  # 数据太少时不拆分
    
    # 参数默认值和范围，用于正则化惩罚
    _param_defaults = {
        "ema_fast": (12, 5, 50), "ema_slow": (60, 20, 200),
        "macd_fast": (12, 5, 20), "macd_slow": (26, 10, 40), "macd_signal": (9, 5, 20),
        "rsi_period": (14, 5, 30), "rsi_lower": (30, 10, 50), "rsi_upper": (70, 50, 90),
        "adx_period": (14, 5, 30), "atr_period": (14, 5, 30),
        "bb_period": (20, 5, 50), "bb_std": (2.0, 1.0, 3.0), "indicator_period": (20, 5, 60),
        "entry_threshold": (0.5, -1.0, 2.0), "exit_threshold": (-0.5, -2.0, 0.5),
        "adx_threshold": (20, 10, 35), "stop_loss_mult": (2.0, 0.5, 4.0), "take_profit_mult": (4.0, 1.0, 6.0),
        "weight_bb": (0.8, 0.0, 2.0), "weight_obv": (1.0, 0.0, 2.0),
        "weight_volume": (0.6, 0.0, 1.5), "weight_price": (0.7, 0.0, 1.5), "weight_drawdown": (0.5, 0.0, 1.5),
    }
    
    def _regularization_penalty(params_dict: dict, lam: float = 0.02) -> float:
        """计算 L2 正则化惩罚：参数偏离默认值越远，惩罚越大"""
        penalty = 0.0
        for name, value in params_dict.items():
            if name in _param_defaults:
                default, lo, hi = _param_defaults[name]
                span = hi - lo
                if span > 0:
                    penalty += ((value - default) / span) ** 2
        return lam * penalty
    
    def objective(trial):
        """Optuna 优化目标函数（含防过拟合机制）"""
        
        # ===== 1. 指标层参数 =====
        ema_fast = trial.suggest_int("ema_fast", 5, 50)
        ema_slow = trial.suggest_int("ema_slow", 20, 200)
        if ema_fast >= ema_slow:
            return -np.inf
        
        macd_fast = trial.suggest_int("macd_fast", 5, 20)
        macd_slow = trial.suggest_int("macd_slow", 10, 40)
        macd_signal = trial.suggest_int("macd_signal", 5, 20)
        if macd_fast >= macd_slow:
            return -np.inf
        
        rsi_period = trial.suggest_int("rsi_period", 5, 30)
        rsi_lower = trial.suggest_float("rsi_lower", 10, 50)
        rsi_upper = trial.suggest_float("rsi_upper", 50, 90)
        
        adx_period = trial.suggest_int("adx_period", 5, 30)
        atr_period = trial.suggest_int("atr_period", 5, 30)
        
        bb_period = trial.suggest_int("bb_period", 5, 50)
        bb_std = trial.suggest_float("bb_std", 1.0, 3.0)
        indicator_period = trial.suggest_int("indicator_period", 5, 60)
        
        # ===== 2. 策略层参数 =====
        entry_threshold = trial.suggest_float("entry_threshold", -1.0, 2.0)
        exit_threshold = trial.suggest_float("exit_threshold", -2.0, 0.5)
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
        
        # ===== 3. 用试验参数重新计算指标 =====
        try:
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
                bb_period=bb_period,
                bb_std=bb_std,
                indicator_period=indicator_period,
            )
        except Exception:
            return -np.inf
        
        # ===== 4. 计算信号 =====
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
            weight_bb=weight_bb,
            weight_obv=weight_obv,
            weight_volume=weight_volume,
            weight_price=weight_price,
            weight_drawdown=weight_drawdown,
            exit_min_signals=2,
            entry_min_signals=3,
        )
        
        # ===== 5. 防过拟合：子训练集 + 子验证集分别回测 =====
        train_sim = simulate_strategy(
            df_signals.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        train_return = train_sim["strategy_equity"].iloc[-1] - 1
        train_sharpe = sharpe_ratio(train_sim["strategy_return"])
        train_dd = max_drawdown(train_sim["strategy_equity"])
        train_score = train_sharpe + train_return - abs(train_dd) * 0.5
        
        # 如果有子验证集，额外验证泛化能力
        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                df_signals.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=stop_loss_mult,
                take_profit_mult=take_profit_mult,
            )
            val_return = val_sim["strategy_equity"].iloc[-1] - 1
            val_sharpe = sharpe_ratio(val_sim["strategy_return"])
            val_dd = max_drawdown(val_sim["strategy_equity"])
            val_score = val_sharpe + val_return - abs(val_dd) * 0.5
            
            # 加权评分：验证集权重更高（0.6），训练集权重0.4
            blended_score = 0.4 * train_score + 0.6 * val_score
            # 过拟合惩罚：训练集与验证集差距越大扣分越多
            gap_penalty = 0.3 * abs(train_score - val_score)
            score = blended_score - gap_penalty
        else:
            score = train_score
            val_sharpe = train_sharpe
            val_return = train_return
            val_dd = train_dd
        
        # ===== 6. 正则化惩罚：偏离默认值的参数受罚 =====
        trial_params = {
            "ema_fast": ema_fast, "ema_slow": ema_slow,
            "macd_fast": macd_fast, "macd_slow": macd_slow, "macd_signal": macd_signal,
            "rsi_period": rsi_period, "rsi_lower": rsi_lower, "rsi_upper": rsi_upper,
            "adx_period": adx_period, "atr_period": atr_period,
            "bb_period": bb_period, "bb_std": bb_std, "indicator_period": indicator_period,
            "entry_threshold": entry_threshold, "exit_threshold": exit_threshold,
            "adx_threshold": adx_candidate, "stop_loss_mult": stop_loss_mult,
            "take_profit_mult": take_profit_mult,
            "weight_bb": weight_bb, "weight_obv": weight_obv,
            "weight_volume": weight_volume, "weight_price": weight_price,
            "weight_drawdown": weight_drawdown,
        }
        score -= _regularization_penalty(trial_params)
        
        # ===== 7. 更新最佳结果 =====
        nonlocal best_result
        if score > best_result["score"]:
            best_result = {
                "score": score,
                "sharpe": train_sharpe,
                "return": train_return,
                "max_drawdown": train_dd,
                "val_sharpe": val_sharpe,
                "val_return": val_return,
                "val_max_drawdown": val_dd,
                # 指标层参数
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "macd_fast": macd_fast,
                "macd_slow": macd_slow,
                "macd_signal": macd_signal,
                "rsi_period": rsi_period,
                "rsi_lower": rsi_lower,
                "rsi_upper": rsi_upper,
                "adx_period": adx_period,
                "atr_period": atr_period,
                "bb_period": bb_period,
                "bb_std": bb_std,
                "indicator_period": indicator_period,
                # 策略层参数
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
    study = optuna.create_study(direction="maximize")
    
    # 热启动：将预评估最佳预设参数作为第一个试验点注入
    if seed_params:
        _seed_trial = {}
        _optuna_param_keys = [
            "ema_fast", "ema_slow", "macd_fast", "macd_slow", "macd_signal",
            "rsi_period", "rsi_lower", "rsi_upper", "adx_period", "atr_period",
            "bb_period", "bb_std", "indicator_period",
            "entry_threshold", "exit_threshold", "adx_threshold",
            "stop_loss_mult", "take_profit_mult",
            "weight_bb", "weight_obv", "weight_volume", "weight_price", "weight_drawdown",
        ]
        for k in _optuna_param_keys:
            if k in seed_params:
                _seed_trial[k] = seed_params[k]
        if _seed_trial:
            study.enqueue_trial(_seed_trial)
    
    _trial_counter = [0]
    def _optuna_callback(study, trial):
        _trial_counter[0] += 1
        if progress_callback:
            progress_callback(_trial_counter[0], n_trials)
    
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False, callbacks=[_optuna_callback])
    
    return best_result if best_result["score"] > -np.inf else None


# ============ 遗传算法优化 ============

def genetic_algorithm_optimize_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    population_size: int = 30,
    generations: int = 20,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.2,
    # 以下为固定参数（不参与优化）
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    progress_callback=None,
    seed_params: dict | None = None,
) -> dict | None:
    """
    使用遗传算法（Genetic Algorithm）搜索最优参数
    
    【热启动】
    如果提供 seed_params（预评估最佳预设参数），会将其作为初始种群的前几个个体，
    让进化从已知较优解出发，显著加快收敛。
    
    【并行评估】
    使用 ThreadPoolExecutor 并行评估种群中的个体，充分利用多核 CPU。

    【遗传算法原理】
    模拟生物进化过程：维持一个"种群"（一组参数），通过选择、交叉、变异
    不断迭代进化，逐代筛选出表现更好的参数组合。

    【进化流程】
    1. 初始化：随机生成一个种群（population_size 个个体）
    2. 评估：对每个个体计算适应度（策略回测表现）
    3. 选择：用锦标赛选择法挑选优秀父代
    4. 交叉：BLX-α 混合交叉产生子代
    5. 变异：高斯变异为子代引入随机扰动
    6. 精英保留：每代最优的 2 个个体直接晋级
    7. 重复 2-6 步共 generations 代

    【优势】
    - vs 随机搜索：在好的解附近持续探索，不是盲目采样
    - vs 贝叶斯优化：天然维持种群多样性，不容易陷入局部最优
    - 交叉操作能发现非显式的参数组合关系

    【优化参数】（与贝叶斯优化相同的参数空间）
    一、指标层参数（13个）：EMA、MACD、RSI、ADX、ATR、布林带周期
    二、策略层参数（5个）：入场/出场阈值、ADX阈值、止损/止盈倍数
    三、因子权重（5个）：布林带、OBV、成交量、价格位置、回撤

    参数：
        df_raw: 原始价格数据（未计算指标）
        split_idx: 训练/测试集分割点
        population_size: 种群大小（建议 20-50）
        generations: 进化代数（建议 15-30）
        crossover_rate: 交叉概率（0-1）
        mutation_rate: 变异概率（0-1）
        其他参数：固定的策略参数（不参与优化搜索）
        progress_callback: 进度回调函数 callback(current, total)

    返回：
        最佳参数字典
    """
    rng = np.random.default_rng(42)

    # ===== 防过拟合：将训练集拆为子训练集(70%)和子验证集(30%) =====
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx

    # ===== 参数空间定义：(默认值, 最小值, 最大值, 类型) =====
    _param_space = {
        # 指标层参数
        "ema_fast":         (12,   5,   50,  "int"),
        "ema_slow":         (60,   20,  200, "int"),
        "macd_fast":        (12,   5,   20,  "int"),
        "macd_slow":        (26,   10,  40,  "int"),
        "macd_signal":      (9,    5,   20,  "int"),
        "rsi_period":       (14,   5,   30,  "int"),
        "rsi_lower":        (30.0, 10,  50,  "float"),
        "rsi_upper":        (70.0, 50,  90,  "float"),
        "adx_period":       (14,   5,   30,  "int"),
        "atr_period":       (14,   5,   30,  "int"),
        "bb_period":        (20,   5,   50,  "int"),
        "bb_std":           (2.0,  1.0, 3.0, "float"),
        "indicator_period": (20,   5,   60,  "int"),
        # 策略层参数
        "entry_threshold":  (0.5,  -1.0, 2.0,  "float"),
        "exit_threshold":   (-0.5, -2.0, 0.5,  "float"),
        "adx_threshold":    (20.0, 10,   35,   "float"),
        "stop_loss_mult":   (2.0,  0.5,  4.0,  "float"),
        "take_profit_mult": (4.0,  1.0,  6.0,  "float"),
        # 因子权重
        "weight_bb":        (0.8, 0.0, 2.0, "float"),
        "weight_obv":       (1.0, 0.0, 2.0, "float"),
        "weight_volume":    (0.6, 0.0, 1.5, "float"),
        "weight_price":     (0.7, 0.0, 1.5, "float"),
        "weight_drawdown":  (0.5, 0.0, 1.5, "float"),
    }
    param_names = list(_param_space.keys())

    # ===== 工具函数 =====
    def _random_individual():
        """随机生成一个合法个体"""
        ind = {}
        for name, (default, lo, hi, ptype) in _param_space.items():
            val = rng.uniform(lo, hi)
            if ptype == "int":
                val = int(round(val))
            ind[name] = val
        return ind

    def _clip_individual(ind):
        """将个体参数裁剪到合法范围"""
        for name, (default, lo, hi, ptype) in _param_space.items():
            val = np.clip(ind[name], lo, hi)
            if ptype == "int":
                val = int(round(val))
            ind[name] = val if ptype != "int" else int(val)
        return ind

    def _is_valid(ind):
        """检查个体参数约束"""
        if ind["ema_fast"] >= ind["ema_slow"]:
            return False
        if ind["macd_fast"] >= ind["macd_slow"]:
            return False
        if ind["entry_threshold"] <= ind["exit_threshold"]:
            return False
        return True

    def _regularization_penalty(ind, lam=0.02):
        """L2 正则化惩罚"""
        penalty = 0.0
        for name, (default, lo, hi, ptype) in _param_space.items():
            span = hi - lo
            if span > 0:
                penalty += ((ind[name] - default) / span) ** 2
        return lam * penalty

    def _evaluate(ind):
        """计算一个个体的适应度（含防过拟合）"""
        if not _is_valid(ind):
            return -np.inf

        try:
            df_indicators = add_indicators(
                df_raw,
                rsi_period=int(ind["rsi_period"]),
                macd_fast=int(ind["macd_fast"]),
                macd_slow=int(ind["macd_slow"]),
                macd_signal=int(ind["macd_signal"]),
                ema_fast=int(ind["ema_fast"]),
                ema_slow=int(ind["ema_slow"]),
                adx_period=int(ind["adx_period"]),
                atr_period=int(ind["atr_period"]),
                bb_period=int(ind["bb_period"]),
                bb_std=ind["bb_std"],
                indicator_period=int(ind["indicator_period"]),
            )
        except Exception:
            return -np.inf

        df_signals = compute_signals(
            df_indicators,
            rsi_lower=ind["rsi_lower"],
            rsi_upper=ind["rsi_upper"],
            adx_threshold=ind["adx_threshold"],
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
            entry_threshold=ind["entry_threshold"],
            exit_threshold=ind["exit_threshold"],
            use_trend_filter=use_trend_filter,
            use_strength_filter=use_strength_filter,
            use_rsi_filter=use_rsi_filter,
            use_macd_filter=use_macd_filter,
            weight_bb=ind["weight_bb"],
            weight_obv=ind["weight_obv"],
            weight_volume=ind["weight_volume"],
            weight_price=ind["weight_price"],
            weight_drawdown=ind["weight_drawdown"],
            exit_min_signals=2,
            entry_min_signals=3,
        )

        # 子训练集回测
        train_sim = simulate_strategy(
            df_signals.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=ind["stop_loss_mult"],
            take_profit_mult=ind["take_profit_mult"],
        )

        train_return = train_sim["strategy_equity"].iloc[-1] - 1
        train_sharpe = sharpe_ratio(train_sim["strategy_return"])
        train_dd = max_drawdown(train_sim["strategy_equity"])
        train_score = train_sharpe + train_return - abs(train_dd) * 0.5

        # 子验证集
        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                df_signals.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=ind["stop_loss_mult"],
                take_profit_mult=ind["take_profit_mult"],
            )
            val_return = val_sim["strategy_equity"].iloc[-1] - 1
            val_sharpe = sharpe_ratio(val_sim["strategy_return"])
            val_dd = max_drawdown(val_sim["strategy_equity"])
            val_score = val_sharpe + val_return - abs(val_dd) * 0.5

            blended_score = 0.4 * train_score + 0.6 * val_score
            gap_penalty = 0.3 * abs(train_score - val_score)
            score = blended_score - gap_penalty
        else:
            score = train_score
            val_sharpe = train_sharpe
            val_return = train_return
            val_dd = train_dd

        score -= _regularization_penalty(ind)

        return score

    def _get_result_dict(ind, score):
        """将个体转换为结果字典（含回测指标）"""
        if not _is_valid(ind):
            return None
        try:
            df_indicators = add_indicators(
                df_raw,
                rsi_period=int(ind["rsi_period"]),
                macd_fast=int(ind["macd_fast"]),
                macd_slow=int(ind["macd_slow"]),
                macd_signal=int(ind["macd_signal"]),
                ema_fast=int(ind["ema_fast"]),
                ema_slow=int(ind["ema_slow"]),
                adx_period=int(ind["adx_period"]),
                atr_period=int(ind["atr_period"]),
                bb_period=int(ind["bb_period"]),
                bb_std=ind["bb_std"],
                indicator_period=int(ind["indicator_period"]),
            )
            df_signals = compute_signals(
                df_indicators,
                rsi_lower=ind["rsi_lower"],
                rsi_upper=ind["rsi_upper"],
                adx_threshold=ind["adx_threshold"],
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
                entry_threshold=ind["entry_threshold"],
                exit_threshold=ind["exit_threshold"],
                use_trend_filter=use_trend_filter,
                use_strength_filter=use_strength_filter,
                use_rsi_filter=use_rsi_filter,
                use_macd_filter=use_macd_filter,
                weight_bb=ind["weight_bb"],
                weight_obv=ind["weight_obv"],
                weight_volume=ind["weight_volume"],
                weight_price=ind["weight_price"],
                weight_drawdown=ind["weight_drawdown"],
                exit_min_signals=2,
                entry_min_signals=3,
            )

            train_sim = simulate_strategy(
                df_signals.iloc[:sub_train_end],
                initial_position=0,
                stop_loss_mult=ind["stop_loss_mult"],
                take_profit_mult=ind["take_profit_mult"],
            )
            train_return = train_sim["strategy_equity"].iloc[-1] - 1
            train_sharpe = sharpe_ratio(train_sim["strategy_return"])
            train_dd = max_drawdown(train_sim["strategy_equity"])

            if sub_train_end < split_idx:
                val_sim = simulate_strategy(
                    df_signals.iloc[sub_train_end:split_idx],
                    initial_position=0,
                    stop_loss_mult=ind["stop_loss_mult"],
                    take_profit_mult=ind["take_profit_mult"],
                )
                val_return = val_sim["strategy_equity"].iloc[-1] - 1
                val_sharpe = sharpe_ratio(val_sim["strategy_return"])
                val_dd = max_drawdown(val_sim["strategy_equity"])
            else:
                val_sharpe = train_sharpe
                val_return = train_return
                val_dd = train_dd
        except Exception:
            return None

        return {
            "score": score,
            "sharpe": train_sharpe,
            "return": train_return,
            "max_drawdown": train_dd,
            "val_sharpe": val_sharpe,
            "val_return": val_return,
            "val_max_drawdown": val_dd,
            # 指标层参数
            "ema_fast": int(ind["ema_fast"]),
            "ema_slow": int(ind["ema_slow"]),
            "macd_fast": int(ind["macd_fast"]),
            "macd_slow": int(ind["macd_slow"]),
            "macd_signal": int(ind["macd_signal"]),
            "rsi_period": int(ind["rsi_period"]),
            "rsi_lower": ind["rsi_lower"],
            "rsi_upper": ind["rsi_upper"],
            "adx_period": int(ind["adx_period"]),
            "atr_period": int(ind["atr_period"]),
            "bb_period": int(ind["bb_period"]),
            "bb_std": ind["bb_std"],
            "indicator_period": int(ind["indicator_period"]),
            # 策略层参数
            "adx_threshold": ind["adx_threshold"],
            "entry_threshold": ind["entry_threshold"],
            "exit_threshold": ind["exit_threshold"],
            "stop_loss_mult": ind["stop_loss_mult"],
            "take_profit_mult": ind["take_profit_mult"],
            # 因子权重
            "weight_bb": ind["weight_bb"],
            "weight_obv": ind["weight_obv"],
            "weight_volume": ind["weight_volume"],
            "weight_price": ind["weight_price"],
            "weight_drawdown": ind["weight_drawdown"],
            # 标记：遗传算法产出
            "_method": "genetic_algorithm",
        }

    def _tournament_select(population, fitnesses, k=3):
        """锦标赛选择：随机取 k 个个体，返回最优"""
        indices = rng.choice(len(population), size=k, replace=False)
        best_idx = indices[0]
        for idx in indices[1:]:
            if fitnesses[idx] > fitnesses[best_idx]:
                best_idx = idx
        return population[best_idx].copy()

    def _blx_alpha_crossover(parent1, parent2, alpha=0.5):
        """BLX-α 混合交叉：子代在父代区间扩展 α 范围内随机采样"""
        child = {}
        for name in param_names:
            p1, p2 = parent1[name], parent2[name]
            lo_val, hi_val = min(p1, p2), max(p1, p2)
            span = hi_val - lo_val
            new_lo = lo_val - alpha * span
            new_hi = hi_val + alpha * span
            child[name] = rng.uniform(new_lo, new_hi)
        return _clip_individual(child)

    def _gaussian_mutate(ind, rate):
        """高斯变异：以 rate 概率对每个基因添加高斯噪声"""
        mutated = ind.copy()
        for name, (default, lo, hi, ptype) in _param_space.items():
            if rng.random() < rate:
                span = hi - lo
                noise = rng.normal(0, span * 0.1)
                mutated[name] = ind[name] + noise
        return _clip_individual(mutated)

    # ===== 1. 初始化种群（含热启动）=====
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import multiprocessing
    _max_workers = min(multiprocessing.cpu_count(), population_size, 8)

    population = []

    # 热启动：将种子参数（最佳预设）注入种群前几个位置
    if seed_params:
        # 种子个体 1：最佳预设原样
        seed_ind = {}
        for name, (default, lo, hi, ptype) in _param_space.items():
            if name in seed_params:
                val = seed_params[name]
            else:
                val = default
            if ptype == "int":
                val = int(round(val))
            seed_ind[name] = val
        seed_ind = _clip_individual(seed_ind)
        if _is_valid(seed_ind):
            population.append(seed_ind)

        # 种子个体 2-4：最佳预设的轻微变异版本
        for _ in range(3):
            mutated_seed = _gaussian_mutate(seed_ind.copy(), 0.5)
            if _is_valid(mutated_seed):
                population.append(mutated_seed)

    # 补充随机个体
    max_init_attempts = population_size * 10
    attempts = 0
    while len(population) < population_size and attempts < max_init_attempts:
        ind = _random_individual()
        if _is_valid(ind):
            population.append(ind)
        attempts += 1
    if len(population) < population_size:
        return None  # 无法生成足够合法个体

    # 进度追踪
    total_evals = population_size + generations * population_size
    current_eval = [0]

    def _eval_and_track(ind):
        """评估个体并更新进度"""
        return _evaluate(ind)

    # ===== 2. 并行评估初始种群 =====
    fitnesses = [0.0] * len(population)
    with ThreadPoolExecutor(max_workers=_max_workers) as executor:
        future_to_idx = {executor.submit(_eval_and_track, ind): i for i, ind in enumerate(population)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            fitnesses[idx] = future.result()
            current_eval[0] += 1
            if progress_callback:
                progress_callback(current_eval[0], total_evals)

    # ===== 3. 进化循环 =====
    elite_count = 2  # 精英保留数量
    best_ever_score = -np.inf
    best_ever_ind = None

    for gen in range(generations):
        # 记录全局最优
        gen_best_idx = int(np.argmax(fitnesses))
        if fitnesses[gen_best_idx] > best_ever_score:
            best_ever_score = fitnesses[gen_best_idx]
            best_ever_ind = population[gen_best_idx].copy()

        # 精英保留：取当代 Top-N 直接晋级
        sorted_indices = np.argsort(fitnesses)[::-1]
        new_population = [population[i].copy() for i in sorted_indices[:elite_count]]
        new_fitnesses = [fitnesses[i] for i in sorted_indices[:elite_count]]

        # 生成剩余子代
        children_to_eval = []
        while len(new_population) + len(children_to_eval) < population_size:
            # 选择两个父代
            parent1 = _tournament_select(population, fitnesses)
            parent2 = _tournament_select(population, fitnesses)

            # 交叉
            if rng.random() < crossover_rate:
                child = _blx_alpha_crossover(parent1, parent2)
            else:
                child = parent1.copy()

            # 变异
            child = _gaussian_mutate(child, mutation_rate)

            # 合法性修复尝试（最多 5 次重新变异）
            for _ in range(5):
                if _is_valid(child):
                    break
                child = _gaussian_mutate(_random_individual(), mutation_rate)

            if not _is_valid(child):
                child = _random_individual()
                if not _is_valid(child):
                    continue

            children_to_eval.append(child)

        # 并行评估本代所有子代
        child_fitnesses = [0.0] * len(children_to_eval)
        with ThreadPoolExecutor(max_workers=_max_workers) as executor:
            future_to_idx = {executor.submit(_eval_and_track, c): i for i, c in enumerate(children_to_eval)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                child_fitnesses[idx] = future.result()
                current_eval[0] += 1
                if progress_callback:
                    progress_callback(current_eval[0], total_evals)

        new_population.extend(children_to_eval)
        new_fitnesses.extend(child_fitnesses)

        population = new_population
        fitnesses = new_fitnesses

    # 最后一代检查全局最优
    final_best_idx = int(np.argmax(fitnesses))
    if fitnesses[final_best_idx] > best_ever_score:
        best_ever_score = fitnesses[final_best_idx]
        best_ever_ind = population[final_best_idx].copy()

    if best_ever_ind is None or best_ever_score <= -np.inf:
        return None

    return _get_result_dict(best_ever_ind, best_ever_score)


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
    加载或下载股票数据，优先使用临时缓存
    
    功能说明：
    1. 先尝试从临时目录缓存加载数据（节省时间）
    2. 如果缓存不存在或损坏，从网络下载
    3. 下载后保存到临时目录，供同一运行周期内复用
    
    注意：
    - 缓存存放在系统临时目录，不占用持久磁盘空间
    - 服务重启后缓存可能被清理，数据会按需重新下载
    
    参数：
        symbol: 股票代码
        adjust: 复权方式
    
    返回：
        股票数据 DataFrame，失败返回 None
    """
    # 确保临时缓存目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 构造缓存文件路径
    data_path = os.path.join(DATA_DIR, f"{symbol.lower()}_daily.csv")
    
    # 尝试加载缓存文件
    if os.path.exists(data_path):
        try:
            df = load_csv(data_path)
            return df
        except Exception as e:
            st.warning(f"加载缓存数据失败 ({symbol}): {e}，尝试重新下载...")
    
    # 从网络下载数据
    try:
        with st.spinner(f"正在下载 {symbol} 数据..."):
            df = fetch_data(symbol, adjust)
            # 保存到临时缓存
            df.to_csv(data_path, index=False)
            st.success(f"✓ {symbol} 数据已下载")
        return df
    except Exception as e:
        st.error(f"下载 {symbol} 数据失败: {e}")
        return None


def get_available_stocks() -> list:
    """
    获取可用的股票列表（默认列表 + 用户添加的股票）
    
    功能：
    1. 返回硬编码的默认股票列表（无需预下载 CSV）
    2. 扫描临时缓存目录，添加用户额外下载的股票
    
    返回：
        股票代码列表（如 ['AAPL', 'TSLA', 'NVDA', ...]）
    """
    # 从默认列表开始
    stocks = list(DEFAULT_STOCKS)
    
    # 扫描缓存目录，添加用户额外下载的股票
    if os.path.exists(DATA_DIR):
        files = [f for f in os.listdir(DATA_DIR) if f.endswith('_daily.csv')]
        cached = [f.replace('_daily.csv', '').upper() for f in files]
        for s in cached:
            if s not in stocks:
                stocks.append(s)
    
    return stocks


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


def create_relative_strength_chart(stock_data_dict: dict, benchmark: str = "equal_weight") -> go.Figure:
    """
    创建相对强弱对比图（Relative Strength Comparison）

    【原理说明】
    相对强弱指标（RS）= 个股归一化价格 / 基准归一化价格。
    - RS 曲线上升 → 该股票跑赢基准（即使股价本身在跌，只要跌得比基准少也算跑赢）
    - RS 曲线下降 → 该股票跑输基准
    - RS = 1.0 水平线表示与基准持平

    【对决策的影响】
    动量交易者倾向于买入相对强势的股票、回避相对弱势的股票。
    通过 RS 曲线可以清晰地看到资金应该往哪个方向分配。

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        benchmark: 基准模式，"equal_weight"=所有股票等权平均，或指定某只股票代码

    返回：
        Plotly 图表对象，失败返回 None
    """
    if len(stock_data_dict) < 2:
        return None

    # 步骤1：构建各股票的归一化收盘价序列（起点=1.0），按日期对齐
    norm_series = {}
    for sym, df in stock_data_dict.items():
        if df is None or len(df) < 2 or 'close' not in df.columns:
            continue
        s = df.set_index('date')['close'].sort_index()
        s = s / s.iloc[0]  # 归一化到起点=1.0
        norm_series[sym] = s

    if len(norm_series) < 2:
        return None

    # 合并成 DataFrame，日期对齐（取交集）
    norm_df = pd.DataFrame(norm_series)
    norm_df = norm_df.dropna()

    if len(norm_df) < 2:
        return None

    # 步骤2：计算基准
    if benchmark == "equal_weight" or benchmark not in norm_df.columns:
        benchmark_series = norm_df.mean(axis=1)  # 等权平均
        benchmark_label = "等权平均基准"
    else:
        benchmark_series = norm_df[benchmark]
        benchmark_label = f"{benchmark} 基准"

    # 步骤3：计算相对强弱 RS = 个股 / 基准
    rs_df = norm_df.div(benchmark_series, axis=0)

    # 步骤4：绘图
    # 使用与项目一致的配色
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#636efa', '#ef553b', '#00cc96', '#ab63fa', '#ffa15a',
    ]

    fig = go.Figure()

    for i, sym in enumerate(rs_df.columns):
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=rs_df.index,
            y=rs_df[sym],
            name=sym,
            mode='lines',
            line=dict(color=color, width=2),
            hovertemplate=(
                f'<b>{sym}</b><br>'
                '日期: %{x|%Y-%m-%d}<br>'
                '相对强弱: %{y:.4f}<br>'
                '<extra></extra>'
            ),
        ))

    # 添加基准线 RS=1.0
    fig.add_hline(
        y=1.0,
        line_dash='dash',
        line_color='rgba(128,128,128,0.6)',
        line_width=1.5,
        annotation_text='基准线 (RS=1.0)',
        annotation_position='top right',
        annotation_font=dict(size=11, color='#7f8c8d'),
    )

    fig.update_layout(
        title=dict(
            text=f'相对强弱对比（基准: {benchmark_label}）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#f0f0f0',
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            title='相对强弱 (RS)',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            hoverformat='.4f',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=500,
        margin=dict(l=60, r=60, t=80, b=80),
        legend=dict(
            orientation='h',
            yanchor='bottom', y=-0.25,
            xanchor='center', x=0.5,
            font=dict(size=12),
        ),
        hovermode='x unified',
    )

    # 底部注释
    fig.add_annotation(
        text=f'RS > 1.0 表示跑赢{benchmark_label}，RS < 1.0 表示跑输{benchmark_label}',
        xref='paper', yref='paper',
        x=0.5, y=-0.32,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=11, color='#7f8c8d', family='Arial'),
    )

    return fig


def create_risk_return_scatter(stock_data_dict: dict) -> go.Figure:
    """
    创建风险收益散点图（Risk-Return Scatter Plot）
    
    【原理说明】
    风险收益散点图是现代投资组合理论（MPT）中最基础的可视化工具：
    - 横轴：年化波动率（衡量风险，波动越大风险越高）
    - 纵轴：年化收益率（衡量回报）
    - 理想标的位于左上角（高收益 + 低风险）
    - 劣质标的位于右下角（低收益 + 高风险）
    
    【计算方法】
    - 年化收益率 = (1 + 总收益率) ^ (252 / 交易天数) - 1
    - 年化波动率 = 日收益率标准差 × √252
    - 夏普比率 = 年化收益率 / 年化波动率（简化版，无风险利率设为0）
    
    【对决策的影响】
    帮助投资者在多只股票中快速识别风险收益特征最优的标的，
    支持资产配置决策。
    
    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
    
    返回：
        Plotly 散点图对象，失败返回 None
    """
    
    symbols = []
    ann_returns = []    # 年化收益率（百分比）
    ann_vols = []       # 年化波动率（百分比）
    sharpe_ratios = []  # 夏普比率
    
    for symbol, df in stock_data_dict.items():
        if df is None or len(df) < 2:
            continue
        
        try:
            # 计算日收益率
            daily_returns = df['close'].pct_change().dropna()
            if daily_returns.empty:
                continue
            
            # 计算年化收益率（假设一年 252 个交易日）
            total_return = df['close'].iloc[-1] / df['close'].iloc[0] - 1
            trading_days = len(df)
            
            # 安全检查：total_return 不能 <= -1（否则底数为负，幂运算出错）
            if total_return <= -1:
                annualized_return = -0.99  # 钳位到 -99%，避免数学错误
            else:
                annualized_return = (1 + total_return) ** (252 / trading_days) - 1
            
            # 计算年化波动率
            annualized_volatility = daily_returns.std() * np.sqrt(252)
            
            # 计算夏普比率（简化版，无风险利率 = 0）
            if annualized_volatility > 0:
                sr = annualized_return / annualized_volatility
            else:
                sr = 0.0
            
            symbols.append(symbol)
            ann_returns.append(annualized_return * 100)
            ann_vols.append(annualized_volatility * 100)
            sharpe_ratios.append(round(sr, 2))
            
        except Exception:
            # 跳过计算失败的股票，不影响其他股票
            continue
    
    if not symbols:
        return None
    
    fig = go.Figure()
    
    # 添加散点（hover 包含夏普比率）
    fig.add_trace(go.Scatter(
        x=ann_vols,
        y=ann_returns,
        mode='markers+text',
        text=symbols,
        textposition='top center',
        marker=dict(
            size=15,
            color=sharpe_ratios,      # 颜色映射到夏普比率
            colorscale='RdYlGn',      # 红（差）→ 黄 → 绿（好）
            showscale=True,
            colorbar=dict(title='夏普比率'),
            line=dict(width=1.5, color='DarkSlateGrey'),
        ),
        customdata=np.column_stack([sharpe_ratios]),
        hovertemplate=(
            '<b>%{text}</b><br>'
            '年化波动率 (风险): %{x:.2f}%<br>'
            '年化收益率 (回报): %{y:.2f}%<br>'
            '夏普比率: %{customdata[0]:.2f}<br>'
            '<extra></extra>'
        ),
    ))
    
    # 添加象限辅助线（以中位数为界）
    if len(ann_vols) > 1:
        median_vol = np.median(ann_vols)
        median_ret = np.median(ann_returns)
        
        fig.add_vline(x=median_vol, line_dash='dash', line_color='gray', opacity=0.5)
        fig.add_hline(y=median_ret, line_dash='dash', line_color='gray', opacity=0.5)
        
        # 象限标注
        min_vol, max_vol = min(ann_vols), max(ann_vols)
        min_ret, max_ret = min(ann_returns), max(ann_returns)
        
        fig.add_annotation(
            x=min_vol, y=max_ret, text='⭐ 高收益低风险',
            showarrow=False, font=dict(color='green', size=11),
            xanchor='left', yanchor='top', bgcolor='rgba(255,255,255,0.8)',
        )
        fig.add_annotation(
            x=max_vol, y=min_ret, text='⚠️ 低收益高风险',
            showarrow=False, font=dict(color='red', size=11),
            xanchor='right', yanchor='bottom', bgcolor='rgba(255,255,255,0.8)',
        )
    
    fig.update_layout(
        title=dict(
            text='风险-收益散点图（年化）',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='年化波动率（风险）%',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1', zeroline=False,
        ),
        yaxis=dict(
            title='年化收益率（回报）%',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            zeroline=True, zerolinecolor='#95a5a6',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=550,
        margin=dict(l=80, r=80, t=80, b=80),
    )
    
    return fig


def create_periodic_returns_heatmap(stock_data_dict: dict, period: str = "M") -> go.Figure:
    """
    创建周期收益率热图（Periodic Returns Heatmap）

    【原理说明】
    按月/季度/年展示每只股票的收益率：
    - 行 = 股票代码，列 = 时间周期
    - 颜色红绿色阶：绿=盈利，红=亏损

    【对决策的影响】
    帮助发现股票的季节性规律或在特定市场环境下的表现差异。

    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        period: 时间周期，"M"=月度，"Q"=季度，"Y"=年度

    返回：
        Plotly 热图对象，失败返回 None
    """
    if len(stock_data_dict) < 1:
        return None

    period_labels = {"M": "月度", "Q": "季度", "YE": "年度"}
    period_fmt = {"M": "%Y-%m", "Q": "%Y-Q", "YE": "%Y"}

    # 对每只股票计算周期收益率
    all_returns = {}
    for sym, df in stock_data_dict.items():
        if df is None or len(df) < 2 or 'close' not in df.columns or 'date' not in df.columns:
            continue
        s = df.set_index('date')['close'].sort_index()
        # resample 到指定周期，取最后一个收盘价，再算周期收益率
        resampled = s.resample(period).last().dropna()
        pct = resampled.pct_change().dropna() * 100  # 转为百分比
        if len(pct) < 1:
            continue
        # 生成时间标签
        if period == "Q":
            labels = [f"{d.year}-Q{(d.month - 1) // 3 + 1}" for d in pct.index]
        else:
            fmt = period_fmt.get(period, "%Y-%m")
            labels = [d.strftime(fmt) for d in pct.index]
        all_returns[sym] = pd.Series(pct.values, index=labels)

    if not all_returns:
        return None

    # 合并成矩阵（股票 × 周期）
    returns_df = pd.DataFrame(all_returns).T  # 行=股票，列=周期

    # 限制最多显示列数，避免图表过宽
    max_cols = 24
    if returns_df.shape[1] > max_cols:
        returns_df = returns_df.iloc[:, -max_cols:]

    # 生成每个格子的文本标注
    text_matrix = returns_df.applymap(lambda x: f"{x:.1f}%" if pd.notna(x) else "")

    fig = go.Figure(data=go.Heatmap(
        z=returns_df.values,
        x=returns_df.columns.tolist(),
        y=returns_df.index.tolist(),
        text=text_matrix.values,
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorscale=[
            [0.0, '#d32f2f'],    # 深红（大亏）
            [0.3, '#ef5350'],    # 红
            [0.45, '#ffcdd2'],   # 浅红
            [0.5, '#ffffff'],    # 白（零点）
            [0.55, '#c8e6c9'],   # 浅绿
            [0.7, '#66bb6a'],    # 绿
            [1.0, '#2e7d32'],    # 深绿（大涨）
        ],
        zmid=0,  # 白色对应零收益
        colorbar=dict(
            title=dict(text='收益率(%)', side='right'),
            ticksuffix='%',
            len=0.8,
        ),
        hovertemplate=(
            '<b>%{y}</b><br>'
            '周期: %{x}<br>'
            '收益率: %{z:.2f}%<br>'
            '<extra></extra>'
        ),
    ))

    period_name = period_labels.get(period, "月度")

    fig.update_layout(
        title=dict(
            text=f'股票{period_name}收益率热图',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='时间周期',
            title_font=dict(size=14, color='#34495e'),
            tickangle=-45,
            tickfont=dict(size=10),
            side='bottom',
        ),
        yaxis=dict(
            title='股票',
            title_font=dict(size=14, color='#34495e'),
            tickfont=dict(size=12, color='#2c3e50', family='Arial Black'),
            autorange='reversed',  # 第一只股票在顶部
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=max(300, 80 * len(returns_df) + 150),  # 动态高度
        margin=dict(l=80, r=80, t=80, b=120),
    )

    return fig


def create_factor_score_comparison(stock_data_dict: dict, **kwargs) -> go.Figure:
    """
    创建多股票最新因子评分横向对比图
    
    【原理说明】
    使用项目中已有的 10 因子评分体系（动量/MACD/RSI/波动率/布林带/OBV/
    成交量/价格位置/回撤），对每只股票独立计算最新一天的综合因子评分，
    然后以柱状图横向对比，帮助用户在多标的中快速筛选。
    
    【计算流程】
    1. 对每只股票分别调用 add_indicators → compute_signals
    2. 提取最新一行的 factor_score 和 target_position
    3. 按评分降序排列绘制柱状图
    
    【颜色含义】
    - 绿色：策略建议重仓（≥80%）
    - 橙色：策略建议半仓（≥40%）
    - 蓝色：策略建议轻仓（>0%）
    - 灰色：策略建议空仓（0%）
    
    【对决策的影响】
    直接回答"当前哪只股票最值得买"的问题。
    红色虚线标示入场阈值，超过该线的股票是策略推荐买入的标的。
    
    参数：
        stock_data_dict: {股票代码: DataFrame} 字典
        **kwargs: 侧边栏传入的所有策略参数
    
    返回：
        Plotly 柱状图对象，失败返回 None
    """
    
    symbols = []
    scores = []
    target_positions = []
    percentiles = []
    
    for symbol, df in stock_data_dict.items():
        if df is None or len(df) <= 50:
            # 数据不足 50 行时无法可靠计算滚动指标，跳过
            continue
        
        try:
            # 计算技术指标
            df_indicators = add_indicators(
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
            
            # 计算策略信号
            df_signals = compute_signals(
                df_indicators,
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
            
            # 获取最新一天的评分和目标仓位（统一使用 .get 安全访问）
            latest = df_signals.iloc[-1]
            score_val = float(latest.get('factor_score', 0.0))
            pos_val = float(latest.get('target_position', 0.0))
            pct_val = float(latest.get('factor_percentile', 0.0))
            
            symbols.append(symbol)
            scores.append(score_val)
            target_positions.append(pos_val)
            percentiles.append(pct_val)
            
        except Exception:
            # 某只股票计算失败时跳过，不影响其他股票
            continue
    
    if not symbols:
        return None
    
    # 按评分降序排序
    sorted_indices = np.argsort(scores)[::-1]
    symbols = [symbols[i] for i in sorted_indices]
    scores = [scores[i] for i in sorted_indices]
    target_positions = [target_positions[i] for i in sorted_indices]
    percentiles = [percentiles[i] for i in sorted_indices]
    
    # 确定柱子颜色：根据目标仓位分档
    colors = []
    for pos in target_positions:
        if pos >= 0.8:
            colors.append('#2ca02c')   # 绿色（重仓）
        elif pos >= 0.4:
            colors.append('#ff7f0e')   # 橙色（半仓）
        elif pos > 0:
            colors.append('#1f77b4')   # 蓝色（轻仓）
        else:
            colors.append('#7f7f7f')   # 灰色（空仓）
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=symbols,
        y=scores,
        marker_color=colors,
        text=[f'{s:.2f}' for s in scores],
        textposition='auto',
        customdata=np.column_stack([target_positions, [p * 100 for p in percentiles]]),
        hovertemplate=(
            '<b>%{x}</b><br>'
            '因子评分: %{y:.2f}<br>'
            '建议仓位: %{customdata[0]:.0%}<br>'
            '评分分位数: %{customdata[1]:.1f}%<br>'
            '<extra></extra>'
        ),
    ))
    
    # 添加入场阈值辅助线
    entry_thr = kwargs.get('entry_threshold', 0.5)
    fig.add_hline(
        y=entry_thr,
        line_dash='dash',
        line_color='red',
        annotation_text=f'入场阈值 ({entry_thr})',
        annotation_position='top right',
    )
    
    fig.update_layout(
        title=dict(
            text='最新因子评分横向对比',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='股票代码',
            title_font=dict(size=14, color='#34495e'),
            tickfont=dict(size=12, color='#2c3e50', family='Arial Black'),
        ),
        yaxis=dict(
            title='综合因子评分',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=450,
        margin=dict(l=60, r=60, t=80, b=80),
        showlegend=False,
    )
    
    # 底部图例说明
    fig.add_annotation(
        text='颜色说明: 🟩 重仓 (≥80%) | 🟧 半仓 (≥40%) | 🟦 轻仓 (>0%) | ⬜ 空仓 (0%)',
        xref='paper', yref='paper',
        x=0.5, y=-0.18,
        xanchor='center', yanchor='top',
        showarrow=False,
        font=dict(size=12, color='#7f8c8d'),
    )
    
    return fig


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

    # 绘制组合净值图
    colors_list = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    ]

    fig = go.Figure()

    # 组合策略净值（粗线）
    fig.add_trace(go.Scatter(
        x=portfolio_equity.index,
        y=portfolio_equity.values,
        name='组合策略',
        mode='lines',
        line=dict(color='#2ca02c', width=3),
        hovertemplate='<b>组合策略</b><br>日期: %{x|%Y-%m-%d}<br>净值: %{y:.4f}<extra></extra>',
    ))

    # 等权买入持有（粗虚线）
    fig.add_trace(go.Scatter(
        x=bh_equity.index,
        y=bh_equity.values,
        name='买入持有基准',
        mode='lines',
        line=dict(color='#d62728', width=3, dash='dash'),
        hovertemplate='<b>买入持有</b><br>日期: %{x|%Y-%m-%d}<br>净值: %{y:.4f}<extra></extra>',
    ))

    # 各个股独立策略净值（细线，半透明）
    for i, sym in enumerate(individual_results.keys()):
        sym_ret = individual_results[sym]['strategy_return']
        # 对齐到组合时间范围
        sym_ret_aligned = sym_ret.reindex(portfolio_equity.index).fillna(0)
        sym_equity = (1 + sym_ret_aligned).cumprod()
        color = colors_list[i % len(colors_list)]
        fig.add_trace(go.Scatter(
            x=sym_equity.index,
            y=sym_equity.values,
            name=f'{sym} 策略',
            mode='lines',
            line=dict(color=color, width=1.5, dash='dot'),
            opacity=0.5,
            hovertemplate=f'<b>{sym}</b><br>日期: %{{x|%Y-%m-%d}}<br>净值: %{{y:.4f}}<extra></extra>',
        ))

    fig.update_layout(
        title=dict(
            text='投资组合模拟 — 策略净值 vs 买入持有',
            font=dict(size=18, color='#2c3e50', family='Arial Black'),
            x=0.5, xanchor='center', y=0.95, yanchor='top',
        ),
        xaxis=dict(
            title='日期',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#f0f0f0',
        ),
        yaxis=dict(
            title='净值（起点 = 1.0）',
            title_font=dict(size=14, color='#34495e'),
            showgrid=True, gridcolor='#ecf0f1',
            hoverformat='.4f',
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='#fafafa',
        height=550,
        margin=dict(l=60, r=60, t=80, b=100),
        legend=dict(
            orientation='h',
            yanchor='bottom', y=-0.3,
            xanchor='center', x=0.5,
            font=dict(size=11),
        ),
        hovermode='x unified',
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
        # 修复：同步写入贝叶斯优化搜索到的新因子权重
        if "weight_bb" in best:
            st.session_state["weight_bb"] = float(best["weight_bb"])
            st.session_state["weight_obv"] = float(best["weight_obv"])
            st.session_state["weight_volume"] = float(best["weight_volume"])
            st.session_state["weight_price"] = float(best["weight_price"])
            st.session_state["weight_drawdown"] = float(best["weight_drawdown"])
        # 修复：同步写入贝叶斯优化搜索到的技术指标参数
        if "ema_fast" in best:
            st.session_state["ema_fast_slider"] = int(best["ema_fast"])
            st.session_state["ema_slow_slider"] = int(best["ema_slow"])
            st.session_state["macd_fast_slider"] = int(best["macd_fast"])
            st.session_state["macd_slow_slider"] = int(best["macd_slow"])
            st.session_state["macd_signal_slider"] = int(best["macd_signal"])
            st.session_state["rsi_period_slider"] = int(best["rsi_period"])
            st.session_state["rsi_lower_slider"] = int(best["rsi_lower"])
            st.session_state["rsi_upper_slider"] = int(best["rsi_upper"])
            st.session_state["adx_period_slider"] = int(best["adx_period"])
            st.session_state["atr_period_slider"] = int(best["atr_period"])
            st.session_state["bb_period_slider"] = int(best["bb_period"])
            st.session_state["bb_std_slider"] = float(best["bb_std"])
            st.session_state["indicator_period_slider"] = int(best["indicator_period"])
        # 应用搜索结果后自动切换为自定义参数模式
        st.session_state["strategy_preset_selector"] = "自定义参数"
    st.session_state["apply_best_params"] = False

with st.sidebar:
    st.header("📊 控制面板")
    
    # ===== 日期选择（最顶端）=====
    st.subheader("📅 时间范围")
    from datetime import date as _date, timedelta as _timedelta
    _default_end = _date.today()
    _default_start = _default_end - _timedelta(days=3*365)
    selected_range = st.date_input(
        "选择时间区间",
        value=(_default_start, _default_end),
        min_value=_date(2015, 1, 1),
        max_value=_date.today(),
        help="选择回测数据的起止日期"
    )
    
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
        
        add_stock_btn = st.button("添加到股票列表", width="stretch")
        
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
        if st.button("🔄 刷新所选股票数据", width="stretch"):
            with st.spinner("正在刷新数据..."):
                success_count = 0
                fail_count = 0
                
                for stock_symbol in compare_stocks:
                    try:
                        # 下载最新数据
                        df_temp = fetch_data(stock_symbol, adjust)
                        
                        # 保存到临时缓存
                        os.makedirs(DATA_DIR, exist_ok=True)
                        cache_path = os.path.join(DATA_DIR, f"{stock_symbol.lower()}_daily.csv")
                        df_temp.to_csv(cache_path, index=False)
                        
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
    
    # 检测股票切换，清除旧的搜索结果
    if st.session_state.get("_last_symbol") != symbol:
        st.session_state["_last_symbol"] = symbol
        st.session_state.pop("best_params", None)
    
    st.markdown("---")
    
    # ===== 策略选择（预设策略模板）=====
    st.subheader("📋 策略选择")
    
    # 预设策略定义
    STRATEGY_PRESETS = {
        "趋势跟随（保守）": {
            "description": "宽松入场、快速止损，适合震荡市或新手",
            "entry_min_signals": 2, "exit_min_signals": 1,
            "entry_threshold": 0.2, "exit_threshold": -0.3,
            "adx_threshold": 15, "stop_loss_mult": 1.5, "take_profit_mult": 3.0,
            "ema_fast": 20, "ema_slow": 60,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "rsi_period": 14, "rsi_lower": 35, "rsi_upper": 65,
            "adx_period": 14, "atr_period": 14,
            "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
            "momentum_short": 5, "momentum_long": 20,
            "score_lookback": 30, "score_mid_pct": 0.55, "score_high_pct": 0.75,
            "weight_mom_short": 1.0, "weight_mom_long": 1.0,
            "weight_macd": 1.0, "weight_rsi": 0.5, "weight_vol": 0.5,
            "weight_bb": 0.8, "weight_obv": 1.0,
            "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
        },
        "均衡策略（默认）": {
            "description": "攻守兼备的平衡配置，适合大多数场景",
            "entry_min_signals": 3, "exit_min_signals": 2,
            "entry_threshold": 0.5, "exit_threshold": -0.5,
            "adx_threshold": 20, "stop_loss_mult": 2.0, "take_profit_mult": 4.0,
            "ema_fast": 20, "ema_slow": 60,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "rsi_period": 14, "rsi_lower": 30, "rsi_upper": 70,
            "adx_period": 14, "atr_period": 14,
            "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
            "momentum_short": 5, "momentum_long": 20,
            "score_lookback": 30, "score_mid_pct": 0.6, "score_high_pct": 0.8,
            "weight_mom_short": 1.0, "weight_mom_long": 1.0,
            "weight_macd": 1.0, "weight_rsi": 0.5, "weight_vol": 0.5,
            "weight_bb": 0.8, "weight_obv": 1.0,
            "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
        },
        "动量突破（激进）": {
            "description": "严格筛选强趋势、放大利润，适合趋势明确的市场",
            "entry_min_signals": 4, "exit_min_signals": 3,
            "entry_threshold": 0.8, "exit_threshold": -0.2,
            "adx_threshold": 25, "stop_loss_mult": 3.0, "take_profit_mult": 6.0,
            "ema_fast": 15, "ema_slow": 50,
            "macd_fast": 10, "macd_slow": 22, "macd_signal": 8,
            "rsi_period": 12, "rsi_lower": 25, "rsi_upper": 75,
            "adx_period": 12, "atr_period": 12,
            "bb_period": 18, "bb_std": 2.2, "indicator_period": 18,
            "momentum_short": 3, "momentum_long": 15,
            "score_lookback": 25, "score_mid_pct": 0.65, "score_high_pct": 0.85,
            "weight_mom_short": 1.5, "weight_mom_long": 1.2,
            "weight_macd": 1.2, "weight_rsi": 0.3, "weight_vol": 0.3,
            "weight_bb": 0.6, "weight_obv": 1.2,
            "weight_volume": 0.8, "weight_price": 0.5, "weight_drawdown": 0.3,
        },
        "自定义参数": {
            "description": "手动调节所有参数，在下方高级设置中修改",
        },
    }
    
    strategy_preset = st.selectbox(
        "选择预设策略",
        options=list(STRATEGY_PRESETS.keys()),
        index=1,  # 默认选"均衡策略"
        help="预设策略模板会自动填充入场/出场规则和高级设置中的所有参数。选择「自定义参数」可手动调节。",
        key="strategy_preset_selector",
    )
    
    # 显示策略说明
    preset_info = STRATEGY_PRESETS[strategy_preset]
    st.caption(f"💡 {preset_info['description']}")
    
    # 如果选择了预设策略，自动写入 session_state
    if strategy_preset != "自定义参数":
        preset = STRATEGY_PRESETS[strategy_preset]
        # 将预设参数同步到 session_state，侧边栏滑块会自动读取
        _preset_key_map = {
            "ema_fast": "ema_fast_slider", "ema_slow": "ema_slow_slider",
            "macd_fast": "macd_fast_slider", "macd_slow": "macd_slow_slider",
            "macd_signal": "macd_signal_slider",
            "rsi_period": "rsi_period_slider", "rsi_lower": "rsi_lower_slider",
            "rsi_upper": "rsi_upper_slider",
            "adx_period": "adx_period_slider", "atr_period": "atr_period_slider",
            "bb_period": "bb_period_slider", "bb_std": "bb_std_slider",
            "indicator_period": "indicator_period_slider",
        }
        for param_name, slider_key in _preset_key_map.items():
            if param_name in preset:
                st.session_state[slider_key] = preset[param_name]
        # 直接映射到 session_state 的键
        for direct_key in ["adx_threshold", "stop_loss_mult", "take_profit_mult",
                           "entry_threshold", "exit_threshold",
                           "weight_bb", "weight_obv", "weight_volume",
                           "weight_price", "weight_drawdown"]:
            if direct_key in preset:
                st.session_state[direct_key] = preset[direct_key]
    
    st.markdown("---")
    
    # 获取预设的入场/出场默认值
    _preset_entry_min = preset.get("entry_min_signals", 3) if strategy_preset != "自定义参数" else 3
    _preset_exit_min = preset.get("exit_min_signals", 2) if strategy_preset != "自定义参数" else 2
    
    # ===== 入场规则 =====
    st.subheader("📈 入场规则")
    st.caption("入场需满足以下信号中的至少 N 个：")
    st.markdown("""
1. 📊 因子评分达标
2. 📈 趋势向上（EMA快>慢）
3. 💪 趋势强度足够（ADX）
4. 🎯 RSI在合理区间
5. 📉 MACD在信号线上方
    """)
    entry_min_signals = st.slider(
        "入场最少信号数",
        1, 5, _preset_entry_min,
        help="需要同时满足的入场条件数量。数值越大入场越严格，1=最宽松（任一满足即入场），5=最严格（全部满足才入场）"
    )
    
    st.markdown("---")
    
    # ===== 出场规则 =====
    st.subheader("📉 出场规则")
    st.caption("出场需满足以下信号中的至少 N 个：")
    st.markdown("""
1. 📊 因子评分过低
2. 📉 趋势反转（EMA快<慢）
3. ⚠️ RSI超出合理区间
4. 📉 MACD跌破信号线
    """)
    exit_min_signals = st.slider(
        "出场最少信号数",
        1, 4, _preset_exit_min,
        help="需要同时满足的出场条件数量。数值越大出场越宽松（不容易被踢出），1=原始逻辑（任一触发就出场），4=全部满足才出场"
    )
    
    st.markdown("---")
    
    # ===== 高级设置（折叠）=====
    with st.expander("⚙️ 高级设置（自定义参数 / 查看当前值）", expanded=False):
        if strategy_preset != "自定义参数":
            st.caption(f"当前使用「{strategy_preset}」预设，以下参数已自动填充。切换为「自定义参数」可手动修改。")
        else:
            st.caption("手动调整所有策略参数，或使用高级策略自动搜索最优值。")
        
        st.markdown("**EMA 趋势参数**")
        ema_fast = st.slider("EMA 快线周期", 5, 50, 20, help="趋势过滤的短周期 EMA。", key="ema_fast_slider")
        ema_slow = st.slider("EMA 慢线周期", 20, 200, 60, help="趋势过滤的长周期 EMA。", key="ema_slow_slider")
        
        st.markdown("**MACD 参数**")
        macd_fast = st.slider("MACD 快线周期", 5, 20, 12, help="MACD 快线 EMA 周期。", key="macd_fast_slider")
        macd_slow = st.slider("MACD 慢线周期", 10, 40, 26, help="MACD 慢线 EMA 周期。", key="macd_slow_slider")
        macd_signal = st.slider("MACD 信号周期", 5, 20, 9, help="MACD 信号线 EMA 周期。", key="macd_signal_slider")
        
        st.markdown("**RSI 参数**")
        rsi_period = st.slider("RSI 周期", 5, 30, 14, help="RSI 计算周期。", key="rsi_period_slider")
        rsi_lower = st.slider("RSI 下限阈值", 10, 50, 30, help="RSI 低于该值视为偏弱。", key="rsi_lower_slider")
        rsi_upper = st.slider("RSI 上限阈值", 50, 90, 70, help="RSI 高于该值视为偏强。", key="rsi_upper_slider")
        
        st.markdown("**ADX 强度参数**")
        adx_period = st.slider("ADX 周期", 5, 30, 14, help="趋势强度指标的计算周期。", key="adx_period_slider")
        adx_threshold = st.slider(
            "ADX 阈值", 10, 40, 20,
            help="ADX 高于该值才认为趋势有效。",
            key="adx_threshold",
        )
        
        st.markdown("**ATR 止损止盈**")
        atr_period = st.slider("ATR 周期", 5, 30, 14, help="波动率（ATR）计算周期。", key="atr_period_slider")
        
        st.markdown("**布林带 / 高级指标参数**")
        bb_period = st.slider("布林带周期", 5, 50, 20, help="布林带移动平均线的计算周期。", key="bb_period_slider")
        bb_std = st.slider("布林带标准差倍数", 1.0, 3.0, 2.0, step=0.1, help="布林带上下轨的标准差倍数。", key="bb_std_slider")
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
        score_lookback = st.slider("评分标准化窗口", 10, 120, 30, help="用于计算滚动 Z 分数的窗口。")
        score_mid_pct = st.slider(
            "评分分位数-中档", 0.5, 0.9, 0.6, step=0.05,
            help="评分分位数达到该值进入中档仓位。",
        )
        score_high_pct = st.slider(
            "评分分位数-高档", 0.6, 0.95, 0.8, step=0.05,
            help="评分分位数达到该值进入高档仓位。",
        )
        weight_mom_short = st.slider("短期动量权重", 0.0, 3.0, 1.0, step=0.1, help="短期动量在评分中的权重。")
        weight_mom_long = st.slider("中期动量权重", 0.0, 3.0, 1.0, step=0.1, help="中期动量在评分中的权重。")
        weight_macd = st.slider("MACD 权重", 0.0, 3.0, 1.0, step=0.1, help="MACD 柱在评分中的权重。")
        weight_rsi = st.slider("RSI 权重", 0.0, 3.0, 0.5, step=0.1, help="RSI 在评分中的权重。")
        weight_vol = st.slider("波动惩罚权重", 0.0, 3.0, 0.5, step=0.1, help="波动率越高，评分惩罚越大。")
        
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
    
    # 固定值（不再暴露给用户）
    use_trend_filter = True
    use_strength_filter = True
    use_rsi_filter = True
    use_macd_filter = True
    use_voting_entry = False
    entry_vote_threshold = 2.5

# ===== 数据加载逻辑 =====
# 检查是否有选中的股票
if not compare_stocks:
    st.warning("请在侧边栏选择至少一只股票进行分析。")
    st.stop()

if uploaded_file is not None:
    df_raw = load_uploaded_bytes(uploaded_file.getvalue())
    st.info("已使用上传的数据集。")
else:
    df_raw = load_or_fetch_stock(symbol, adjust)
    if df_raw is None:
        st.error(f"无法获取 {symbol} 的数据，请检查网络连接。")
        st.stop()

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
if is_datetime and isinstance(selected_range, tuple) and len(selected_range) == 2:
    start_date, end_date = selected_range
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    df_raw = df_raw[(df_raw["date"] >= start_ts) & (df_raw["date"] <= end_ts)]
elif is_datetime and isinstance(selected_range, tuple) and len(selected_range) == 1:
    start_ts = pd.Timestamp(selected_range[0])
    df_raw = df_raw[df_raw["date"] >= start_ts]

if df_raw.empty:
    st.warning("所选时间区间内没有数据。")
    st.stop()

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
    
    # 预先初始化图表变量，避免 HTML 导出时 NameError
    risk_return_fig = None
    factor_score_fig = None
    corr_fig = None
    rs_fig = None
    portfolio_result = None
    periodic_heatmap_fig = None
    comparison_stats = []
    
    if len(stock_data_dict) > 0:
        # 创建归一化价格对比图
        comparison_fig = create_multi_stock_comparison_chart(
            stock_data_dict,
            title=f"多股票价格对比（共 {len(stock_data_dict)} 只）"
        )
        st.plotly_chart(comparison_fig, width="stretch")
        
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
                st.dataframe(comparison_df, width="stretch", hide_index=True)
        
        # 添加相对强弱对比图
        if len(stock_data_dict) >= 2:
            st.markdown("### 💪 相对强弱对比")

            # 基准选择
            rs_benchmark_options = ["equal_weight"] + list(stock_data_dict.keys())
            rs_benchmark_labels = ["等权平均"] + list(stock_data_dict.keys())
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
                st.info("💡 **如何阅读此图**：RS曲线**上升**表示该股票正在**跑赢**基准，**下降**表示正在**跑输**基准。即使股价本身在涨，如果涨幅不如基准，RS也会下降。动量策略倾向于买入RS上升的股票。")
            else:
                st.warning("⚠️ 数据不足以计算相对强弱")

        # 添加风险收益散点图
        if len(stock_data_dict) >= 2:
            st.markdown("### ⚖️ 风险-收益分析")
            
            with st.spinner("计算风险收益指标..."):
                risk_return_fig = create_risk_return_scatter(stock_data_dict)
            
            if risk_return_fig:
                st.plotly_chart(risk_return_fig, width="stretch")
                st.info("💡 **如何阅读此图**：横轴代表风险（波动率），纵轴代表回报（收益率）。理想的投资标的位于**左上角**（高收益、低风险），应尽量规避位于**右下角**（低收益、高风险）的标的。虚线代表所选股票的中位数。")
            else:
                st.warning("⚠️ 数据不足以计算风险收益指标")
        
        # 添加因子评分横向对比
        if len(stock_data_dict) >= 2:
            st.markdown("### 🎯 最新因子评分对比")
            
            with st.spinner("计算最新因子评分..."):
                # 传递侧边栏的参数给计算函数
                factor_score_fig = create_factor_score_comparison(
                    stock_data_dict,
                    rsi_period=rsi_period,
                    macd_fast=macd_fast,
                    macd_slow=macd_slow,
                    macd_signal=macd_signal,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    adx_period=adx_period,
                    atr_period=atr_period,
                    bb_period=bb_period,
                    bb_std=bb_std,
                    indicator_period=indicator_period,
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
                    use_trend_filter=use_trend_filter,
                    use_strength_filter=use_strength_filter,
                    use_rsi_filter=use_rsi_filter,
                    use_macd_filter=use_macd_filter,
                    use_voting_entry=use_voting_entry,
                    entry_vote_threshold=entry_vote_threshold if use_voting_entry else 2.5,
                    exit_min_signals=exit_min_signals,
                    entry_min_signals=entry_min_signals,
                )
            
            if factor_score_fig:
                st.plotly_chart(factor_score_fig, width="stretch")
                st.info("💡 **如何阅读此图**：展示每只股票在**最新一个交易日**的综合因子评分。柱子越高，说明策略模型认为该股票当前的买入价值越大。颜色代表策略建议的仓位大小。")
            else:
                st.warning("⚠️ 数据不足以计算因子评分")
        
        # 添加相关性热图
        if len(stock_data_dict) >= 2:
            st.markdown("### 📊 股票相关性分析")
            
            with st.spinner("计算相关性矩阵..."):
                corr_fig = create_correlation_heatmap(stock_data_dict)
            
            if corr_fig:
                st.plotly_chart(corr_fig, width="stretch")
            else:
                st.warning("⚠️ 数据不足以计算相关性（需要至少10个共同交易日）")
        
        # 添加周期收益率热图
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
                st.info("💡 **如何阅读此图**：绿色表示盈利，红色表示亏损，颜色越深表示幅度越大。通过观察某只股票在特定月份/季度的表现，可以发现季节性规律或抵御市场下跌的能力。")
            else:
                st.warning("⚠️ 数据不足以生成周期收益率热图")

        # 添加投资组合模拟
        if len(stock_data_dict) >= 2:
            st.markdown("---")
            st.markdown("### 💼 投资组合模拟")

            with st.expander("⚙️ 组合权重设置", expanded=False):
                st.caption("调整各股票在组合中的权重比例，默认等权分配。")
                portfolio_weights = {}
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
                portfolio_params = dict(
                    weights=portfolio_weights,
                    rsi_period=rsi_period,
                    macd_fast=macd_fast,
                    macd_slow=macd_slow,
                    macd_signal=macd_signal,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    adx_period=adx_period,
                    atr_period=atr_period,
                    bb_period=bb_period,
                    bb_std=bb_std,
                    indicator_period=indicator_period,
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
                    stop_loss_mult=stop_loss_mult,
                    take_profit_mult=take_profit_mult,
                    use_trend_filter=use_trend_filter,
                    use_strength_filter=use_strength_filter,
                    use_rsi_filter=use_rsi_filter,
                    use_macd_filter=use_macd_filter,
                    use_voting_entry=use_voting_entry,
                    entry_vote_threshold=entry_vote_threshold if use_voting_entry else 2.5,
                    exit_min_signals=exit_min_signals,
                    entry_min_signals=entry_min_signals,
                )
                portfolio_result = run_portfolio_simulation(stock_data_dict, **portfolio_params)

            if portfolio_result:
                portfolio_fig = portfolio_result['fig']
                st.plotly_chart(portfolio_fig, width="stretch")

                # 关键指标卡片
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

                # 各股票独立表现
                with st.expander("📋 各股票独立策略表现", expanded=False):
                    indiv_stats = []
                    for sym, res in portfolio_result['individual_results'].items():
                        indiv_stats.append({
                            '股票': sym,
                            '权重': f"{portfolio_result['weights'].get(sym, 0):.1%}",
                            '策略收益': f"{res['total_return']:.2%}",
                            '夏普比率': f"{res['sharpe']:.2f}",
                            '最大回撤': f"{res['max_dd']:.2%}",
                        })
                    if indiv_stats:
                        st.dataframe(pd.DataFrame(indiv_stats), width="stretch", hide_index=True)

                st.info("💡 **如何阅读此图**：绿色实线为组合策略净值，红色虚线为等权买入持有基准。彩色点线为各股票的独立策略净值。组合策略通过分散化通常能降低波动和回撤。")

                # 贝叶斯优化组合参数
                st.markdown("#### 🔬 组合参数优化")
                st.caption("使用贝叶斯优化搜索最优组合参数（统一参数，优化目标为组合整体的夏普+收益-回撤）")

                opt_col1, opt_col2 = st.columns(2)
                with opt_col1:
                    portfolio_n_trials = st.slider(
                        "优化试验次数",
                        10, 100, 30, step=10,
                        key="portfolio_n_trials",
                        help="试验次数越多越精确，但耗时更长。建议 30-50 次。",
                    )
                with opt_col2:
                    st.markdown("")  # 占位

                if st.button("🚀 开始优化组合参数", type="primary", key="btn_optimize_portfolio"):
                    with st.spinner(f"贝叶斯优化中（{portfolio_n_trials} 次试验）..."):
                        opt_fixed = dict(
                            rsi_period=rsi_period,
                            macd_fast=macd_fast,
                            macd_slow=macd_slow,
                            macd_signal=macd_signal,
                            ema_fast=ema_fast,
                            ema_slow=ema_slow,
                            adx_period=adx_period,
                            atr_period=atr_period,
                            bb_period=bb_period,
                            bb_std=bb_std,
                            indicator_period=indicator_period,
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
                            use_trend_filter=use_trend_filter,
                            use_strength_filter=use_strength_filter,
                            use_rsi_filter=use_rsi_filter,
                            use_macd_filter=use_macd_filter,
                            use_voting_entry=use_voting_entry,
                            entry_vote_threshold=entry_vote_threshold if use_voting_entry else 2.5,
                            exit_min_signals=exit_min_signals,
                            entry_min_signals=entry_min_signals,
                        )
                        opt_result = bayesian_optimize_portfolio(
                            stock_data_dict,
                            n_trials=portfolio_n_trials,
                            **opt_fixed,
                        )

                    if opt_result and opt_result.get("score", -np.inf) > -np.inf:
                        st.success("✅ 优化完成！最优组合参数：")

                        res_col1, res_col2, res_col3 = st.columns(3)
                        with res_col1:
                            st.metric("优化后夏普", f"{opt_result['sharpe']:.2f}",
                                      delta=f"{opt_result['sharpe'] - portfolio_result['port_sharpe']:.2f}")
                        with res_col2:
                            st.metric("优化后收益", f"{opt_result['return']:.2%}",
                                      delta=f"{(opt_result['return'] - portfolio_result['port_total_return']):.2%}")
                        with res_col3:
                            st.metric("优化后回撤", f"{opt_result['max_drawdown']:.2%}",
                                      delta=f"{(opt_result['max_drawdown'] - portfolio_result['port_max_dd']):.2%}")

                        with st.expander("📋 最优参数详情", expanded=True):
                            opt_params_display = {
                                '入场阈值': f"{opt_result['entry_threshold']:.2f}",
                                '出场阈值': f"{opt_result['exit_threshold']:.2f}",
                                'ADX阈值': f"{opt_result['adx_threshold']:.1f}",
                                '止损倍数': f"{opt_result['stop_loss_mult']:.2f}",
                                '止盈倍数': f"{opt_result['take_profit_mult']:.2f}",
                                '布林带权重': f"{opt_result['weight_bb']:.2f}",
                                'OBV权重': f"{opt_result['weight_obv']:.2f}",
                                '成交量权重': f"{opt_result['weight_volume']:.2f}",
                                '价格位置权重': f"{opt_result['weight_price']:.2f}",
                                '回撤惩罚权重': f"{opt_result['weight_drawdown']:.2f}",
                            }
                            opt_df = pd.DataFrame(
                                list(opt_params_display.items()),
                                columns=['参数', '最优值']
                            )
                            st.dataframe(opt_df, width="stretch", hide_index=True)

                        # 用优化后的参数重新模拟
                        st.markdown("##### 📈 优化后组合表现")
                        with st.spinner("使用最优参数重新模拟..."):
                            opt_sim_params = dict(opt_fixed)
                            opt_sim_params.update(
                                entry_threshold=opt_result['entry_threshold'],
                                exit_threshold=opt_result['exit_threshold'],
                                adx_threshold=opt_result['adx_threshold'],
                                stop_loss_mult=opt_result['stop_loss_mult'],
                                take_profit_mult=opt_result['take_profit_mult'],
                                weight_bb=opt_result['weight_bb'],
                                weight_obv=opt_result['weight_obv'],
                                weight_volume=opt_result['weight_volume'],
                                weight_price=opt_result['weight_price'],
                                weight_drawdown=opt_result['weight_drawdown'],
                                weights=portfolio_weights,
                            )
                            opt_portfolio = run_portfolio_simulation(stock_data_dict, **opt_sim_params)

                        if opt_portfolio:
                            st.plotly_chart(opt_portfolio['fig'], width="stretch")
                    else:
                        st.warning("⚠️ 优化未找到有效参数，请尝试增加试验次数或调整参数范围。")
            else:
                st.warning("⚠️ 数据不足以运行组合模拟（需要至少2只有效股票）")
        
        # 添加导出HTML功能
        st.markdown("---")
        st.markdown("### 📤 导出分析报告")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            export_title = st.text_input("报告标题", value=f"多股票对比分析 - {', '.join(compare_stocks)}", key="export_title")
        with col2:
            include_date = st.checkbox("包含生成日期", value=True, key="include_date")
        
        if st.button("🎁 生成并下载HTML报告", type="primary", width="stretch"):
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
                
                # 添加相对强弱对比图
                if len(stock_data_dict) >= 2 and rs_fig:
                    html_parts.append("""
        <h2>💪 相对强弱对比</h2>
        <div class="info-box">
            💡 RS曲线上升表示跑赢基准，下降表示跑输基准。RS=1.0为基准线。动量策略倾向于买入RS上升的股票。
        </div>
        <div class="chart-container">
            <div id="rs-chart"></div>
        </div>
        <script>
""")
                    html_parts.append(f"""
            var rsData = {rs_fig.to_json()};
            Plotly.newPlot('rs-chart', rsData.data, rsData.layout, {{responsive: true}});
""")
                    html_parts.append("        </script>")

                # 添加风险收益散点图
                if len(stock_data_dict) >= 2 and risk_return_fig:
                    html_parts.append("""
        <h2>⚖️ 风险-收益分析</h2>
        <div class="info-box">
            💡 理想的投资标的位于左上角（高收益、低风险），应尽量规避位于右下角（低收益、高风险）的标的。虚线代表所选股票的中位数。
        </div>
        <div class="chart-container">
            <div id="risk-return-chart"></div>
        </div>
        <script>
""")
                    html_parts.append(f"""
            var riskReturnData = {risk_return_fig.to_json()};
            Plotly.newPlot('risk-return-chart', riskReturnData.data, riskReturnData.layout, {{responsive: true}});
""")
                    html_parts.append("        </script>")
                
                # 添加因子评分横向对比
                if len(stock_data_dict) >= 2 and factor_score_fig:
                    html_parts.append("""
        <h2>🎯 最新因子评分对比</h2>
        <div class="info-box">
            💡 展示每只股票在最新一个交易日的综合因子评分。柱子越高，说明策略模型认为该股票当前的买入价值越大。颜色代表策略建议的仓位大小。
        </div>
        <div class="chart-container">
            <div id="factor-score-chart"></div>
        </div>
        <script>
""")
                    html_parts.append(f"""
            var factorScoreData = {factor_score_fig.to_json()};
            Plotly.newPlot('factor-score-chart', factorScoreData.data, factorScoreData.layout, {{responsive: true}});
""")
                    html_parts.append("        </script>")
                
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
                
                # 添加周期收益率热图
                if periodic_heatmap_fig:
                    html_parts.append("""
        <h2>📅 周期收益率热图</h2>
        <div class="info-box">
            💡 绿色表示盈利，红色表示亏损。通过观察特定周期的表现，可以发现季节性规律或抵御市场下跌的能力。
        </div>
        <div class="chart-container">
            <div id="periodic-heatmap"></div>
        </div>
        <script>
""")
                    html_parts.append(f"""
            var periodicData = {periodic_heatmap_fig.to_json()};
            Plotly.newPlot('periodic-heatmap', periodicData.data, periodicData.layout, {{responsive: true}});
""")
                    html_parts.append("        </script>")

                # 添加投资组合模拟图
                if len(stock_data_dict) >= 2 and portfolio_result and portfolio_result.get('fig'):
                    html_parts.append("""
        <h2>💼 投资组合模拟</h2>
        <div class="info-box">
            💡 绿色实线为组合策略净值，红色虚线为等权买入持有基准。组合策略通过分散化通常能降低波动和回撤。
        </div>
        <div class="chart-container">
            <div id="portfolio-chart"></div>
        </div>
        <script>
""")
                    html_parts.append(f"""
            var portfolioData = {portfolio_result['fig'].to_json()};
            Plotly.newPlot('portfolio-chart', portfolioData.data, portfolioData.layout, {{responsive: true}});
""")
                    html_parts.append("        </script>")

                    # 添加组合指标摘要
                    html_parts.append(f"""
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">组合策略收益</div>
                <div class="metric-value">{portfolio_result['port_total_return']:.2%}</div>
                <div class="metric-delta">夏普 {portfolio_result['port_sharpe']:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">组合最大回撤</div>
                <div class="metric-value">{portfolio_result['port_max_dd']:.2%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">买入持有收益</div>
                <div class="metric-value">{portfolio_result['bh_total_return']:.2%}</div>
                <div class="metric-delta">夏普 {portfolio_result['bh_sharpe']:.2f}</div>
            </div>
        </div>
""")

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
                    width="stretch"
                )
                st.success("✅ HTML报告已生成！点击上方按钮下载")

else:
    # ========================================
    # 单股票策略分析模式
    # ========================================
    
    # 计算技术指标与策略信号（仅单股模式需要）
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
        bb_period=bb_period,
        bb_std=bb_std,
        indicator_period=indicator_period,
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
        use_trend_filter=use_trend_filter,
        use_strength_filter=use_strength_filter,
        use_rsi_filter=use_rsi_filter,
        use_macd_filter=use_macd_filter,
        use_voting_entry=use_voting_entry,
        entry_vote_threshold=entry_vote_threshold if use_voting_entry else 2.5,
        exit_min_signals=exit_min_signals,
        entry_min_signals=entry_min_signals,
        # 修复：传入新因子权重（之前缺失，导致永远使用默认值）
        weight_bb=weight_bb,
        weight_obv=weight_obv,
        weight_volume=weight_volume,
        weight_price=weight_price,
        weight_drawdown=weight_drawdown,
    )
    
    # 训练集比例（单股专属）
    train_ratio = st.slider(
        "训练集比例",
        min_value=0.6,
        max_value=0.9,
        value=0.7,
        step=0.05,
        help="按时间顺序切分训练/测试集。",
    )
    
    # 训练/测试集切分与回测模拟
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
    st.plotly_chart(candle, width="stretch")
    
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
    st.plotly_chart(ind_fig, width="stretch")
    
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
    st.plotly_chart(score_fig, width="stretch")
    
    st.subheader(f"策略建议 —「{strategy_preset}」")
    st.caption("基于当前策略参数的最新信号判断。")
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
    
    # ===== 高级策略（单股专属，右侧主区域）=====
    st.markdown("---")
    st.subheader("🔬 高级策略")
    st.caption("使用智能搜索算法自动寻找最优参数组合。内置防过拟合机制（子验证集 + 正则化），结果更可靠。")
    
    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        optimization_method = st.radio(
            "搜索方法 ⓘ",
            ["贝叶斯优化 (推荐)", "遗传算法", "随机搜索"],
            help="贝叶斯优化：智能搜索，收敛快，适合优化多个参数\n遗传算法：模拟生物进化，种群多样性好，不易陷入局部最优\n随机搜索：简单但效率低\n\n三者均内置防过拟合机制"
        )
    with opt_col2:
        if optimization_method == "贝叶斯优化 (推荐)":
            search_trials = st.slider("优化次数", 20, 150, 60, help="贝叶斯优化试验次数，建议 50-100 次。")
        elif optimization_method == "遗传算法":
            ga_col_a, ga_col_b = st.columns(2)
            with ga_col_a:
                ga_pop_size = st.slider("种群大小", 10, 60, 30, help="每代维持多少个候选参数个体，越大多样性越好但更慢。")
            with ga_col_b:
                ga_generations = st.slider("进化代数", 5, 40, 20, help="进化迭代多少代，越大搜索越充分。")
        else:
            search_trials = st.slider("搜索次数", 10, 200, 40, help="随机搜索次数，越大越耗时。")
    
    run_search = st.button("🚀 运行高级策略搜索", type="primary")
    
    if run_search:
        if split_idx < 50:
            st.warning("训练数据太少，无法进行参数搜索。")
        else:
            # 创建进度条
            progress_bar = st.progress(0)
            progress_text = st.empty()

            def _update_progress(current, total):
                pct = min(current / max(total, 1), 1.0)
                progress_bar.progress(pct)
                progress_text.text(f"搜索进度：{current}/{total}（{pct*100:.0f}%）")

            # ===== 阶段 1：预评估 3 个预设策略，选最佳起点 =====
            seed_params = None
            if optimization_method != "随机搜索":
                progress_text.text("⚡ 预评估预设策略，选择最佳起点...")
                _preset_best, _preset_name, _preset_scores = evaluate_presets_for_optimization(
                    df_raw,
                    split_idx=split_idx,
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
                    use_trend_filter=use_trend_filter,
                    use_strength_filter=use_strength_filter,
                    use_rsi_filter=use_rsi_filter,
                    use_macd_filter=use_macd_filter,
                )
                if _preset_best:
                    seed_params = _preset_best
                    _scores_str = " | ".join([f"{n}: {s:.2f}" for n, s in _preset_scores])
                    progress_text.text(f"⚡ 最佳起点：{_preset_name}（{_scores_str}）")

            # ===== 阶段 2：正式优化 =====
            if optimization_method == "贝叶斯优化 (推荐)":
                progress_text.text(f"正在进行贝叶斯优化（{search_trials} 次试验，从「{_preset_name}」热启动）...")
                best_params = bayesian_optimize_params(
                    df_raw,
                    split_idx=split_idx,
                    n_trials=search_trials,
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
                    use_trend_filter=use_trend_filter,
                    use_strength_filter=use_strength_filter,
                    use_rsi_filter=use_rsi_filter,
                    use_macd_filter=use_macd_filter,
                    progress_callback=_update_progress,
                    seed_params=seed_params,
                )
            elif optimization_method == "遗传算法":
                progress_text.text(f"正在进行遗传算法优化（种群 {ga_pop_size} × {ga_generations} 代，从「{_preset_name}」热启动，{__import__('multiprocessing').cpu_count()} 核并行）...")
                best_params = genetic_algorithm_optimize_params(
                    df_raw,
                    split_idx=split_idx,
                    population_size=ga_pop_size,
                    generations=ga_generations,
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
                    use_trend_filter=use_trend_filter,
                    use_strength_filter=use_strength_filter,
                    use_rsi_filter=use_rsi_filter,
                    use_macd_filter=use_macd_filter,
                    progress_callback=_update_progress,
                    seed_params=seed_params,
                )
            else:
                progress_text.text(f"正在随机搜索参数（{search_trials} 次）...")
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
                    progress_callback=_update_progress,
                )

            # 清理进度条
            progress_bar.progress(1.0)
            progress_text.empty()
            
            if best_params:
                st.session_state["best_params"] = best_params
                st.success("✓ 高级策略搜索完成！")
            else:
                st.error("策略搜索失败，请检查数据。")
    
    st.subheader("搜索结果")
    best = st.session_state.get("best_params")
    if best:
        if best.get("_method") == "genetic_algorithm":
            optimization_info = "遗传算法"
        elif "weight_bb" in best:
            optimization_info = "贝叶斯优化"
        else:
            optimization_info = "随机搜索"
        st.write(f"基于**{optimization_info}**的结果（含防过拟合验证）。")
        
        # 显示性能指标（训练集 + 验证集）
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("综合评分", f"{best['score']:.2f}")
        with col2:
            st.metric("训练集收益", format_pct(best['return']))
        with col3:
            st.metric("训练集夏普", f"{best['sharpe']:.2f}")
        with col4:
            if "val_sharpe" in best:
                st.metric("验证集夏普", f"{best['val_sharpe']:.2f}")
        
        # 验证集指标（防过拟合关键信息）
        if "val_return" in best:
            val_col1, val_col2, val_col3 = st.columns(3)
            with val_col1:
                st.metric("验证集收益", format_pct(best['val_return']))
            with val_col2:
                if "val_max_drawdown" in best:
                    st.metric("验证集回撤", format_pct(best['val_max_drawdown']))
            with val_col3:
                gap = abs(best['sharpe'] - best.get('val_sharpe', best['sharpe']))
                gap_label = "✅ 低" if gap < 0.5 else "⚠️ 中" if gap < 1.0 else "🔴 高"
                st.metric("过拟合风险", gap_label, delta=f"夏普差距 {gap:.2f}")
        
        if "max_drawdown" in best:
            st.write(f"**训练集最大回撤**: {format_pct(best['max_drawdown'])}")
        
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
        
        # 显示优化后的技术指标参数
        if "ema_fast" in best:
            with st.expander("📈 技术指标参数（优化结果）", expanded=False):
                st.write(f"EMA 快/慢线: {best['ema_fast']} / {best['ema_slow']}")
                st.write(f"MACD 快/慢/信号: {best['macd_fast']} / {best['macd_slow']} / {best['macd_signal']}")
                st.write(f"RSI 周期: {best['rsi_period']} | 下限: {best['rsi_lower']:.0f} | 上限: {best['rsi_upper']:.0f}")
                st.write(f"ADX 周期: {best['adx_period']} | ATR 周期: {best['atr_period']}")
                st.write(f"布林带周期: {best['bb_period']} | 标准差: {best['bb_std']:.1f}")
                st.write(f"OBV/成交量/价格周期: {best['indicator_period']}")
                st.caption("💡 这些参数由高级策略自动搜索得出")
        
        # 如果是贝叶斯优化或遗传算法，显示新因子权重
        if "weight_bb" in best:
            with st.expander("📊 新因子权重（Phase 1）", expanded=False):
                st.write(f"布林带位置权重: {best['weight_bb']:.2f}")
                st.write(f"OBV 趋势权重: {best['weight_obv']:.2f}")
                st.write(f"成交量比率权重: {best['weight_volume']:.2f}")
                st.write(f"价格位置权重: {best['weight_price']:.2f}")
                st.write(f"回撤惩罚权重: {best['weight_drawdown']:.2f}")
                st.caption("💡 这些权重由高级策略自动搜索得出")
        apply_params = st.button(
            "📥 应用搜索结果到当前策略",
            key="apply_params_main",
            help="将搜索到的最优参数写入侧边栏，策略选择将自动切换为「自定义参数」。",
            type="primary",
        )
        if apply_params:
            st.session_state["apply_best_params"] = True
            st.rerun()
    else:
        st.info('点击上方「🚀 运行高级策略搜索」按钮开始自动搜索最优参数。')
    
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
    st.plotly_chart(equity_fig, width="stretch")
    
    # ===== Walk-Forward 回测（单股专属，右侧主区域）=====
    st.markdown("---")
    st.subheader("Walk-Forward 回测")
    
    enable_walk = st.checkbox("启用 Walk-Forward", value=True)
    
    if not enable_walk:
        st.info("已关闭 Walk-Forward 回测。")
    else:
        max_window = max(5, len(df) - 1)
        min_train = min(20, max_window)
        min_test = min(5, max_window)
        if max_window <= min_train:
            st.info("数据量较少，已固定训练/测试窗口。")
            train_window = max_window
            test_window = max_window
        else:
            wf_col1, wf_col2 = st.columns(2)
            with wf_col1:
                train_window = st.slider(
                    "训练窗口（交易日）",
                    min_train,
                    max_window,
                    min(252, max_window),
                    help="每次用训练窗口后接测试窗口滚动回测。",
                )
            with wf_col2:
                test_window = st.slider(
                    "测试窗口（交易日）",
                    min_test,
                    max_window,
                    min(63, max_window),
                    help="每次滚动的测试区间长度。",
                )
        
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
                st.plotly_chart(wf_fig, width="stretch")
                if not wf_results.empty:
                    wf_results_display = wf_results.copy()
                    wf_results_display["test_return"] = wf_results_display["test_return"].map(format_pct)
                    wf_results_display["test_max_drawdown"] = wf_results_display["test_max_drawdown"].map(
                        format_pct
                    )
                    st.dataframe(wf_results_display, width="stretch")
    
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
    st.plotly_chart(signal_fig, width="stretch")
    
    # ===== 导出 HTML 报告（单股模式）=====
    st.markdown("---")
    st.subheader("📤 导出分析报告")
    
    single_col1, single_col2, single_col3 = st.columns([1, 1, 2])
    with single_col1:
        single_export_title = st.text_input("报告标题", value=f"单股策略分析 - {symbol}", key="single_export_title")
    with single_col2:
        single_include_date = st.checkbox("包含生成日期", value=True, key="single_include_date")
    
    if st.button("🎁 生成并下载HTML报告", type="primary", width="stretch", key="single_export_btn"):
        with st.spinner("正在生成HTML报告..."):
            from datetime import datetime
            html_parts = []
            
            # HTML头部
            html_parts.append(f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{single_export_title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: 'Source Sans Pro', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 20px; background-color: #fafafa; color: #31333f;
        }}
        .container {{
            max-width: 1200px; margin: 0 auto; background: white;
            padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-bottom: 30px; }}
        h2 {{ color: #34495e; margin-top: 40px; margin-bottom: 20px; border-left: 4px solid #3498db; padding-left: 15px; }}
        .metadata {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 30px; font-size: 14px; color: #7f8c8d; }}
        .metrics {{ display: flex; justify-content: space-around; margin: 30px 0; flex-wrap: wrap; }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 20px; border-radius: 10px; text-align: center;
            min-width: 180px; margin: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-label {{ font-size: 14px; opacity: 0.9; margin-bottom: 8px; }}
        .metric-value {{ font-size: 28px; font-weight: bold; }}
        .metric-delta {{ font-size: 16px; margin-top: 8px; }}
        .chart-container {{ margin: 30px 0; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .info-box {{ background: #e8f4f8; border-left: 4px solid #3498db; padding: 15px; margin: 20px 0; border-radius: 4px; }}
        .footer {{ margin-top: 50px; padding-top: 20px; border-top: 1px solid #ecf0f1; text-align: center; color: #95a5a6; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 {single_export_title}</h1>
""")
            
            # 元数据
            if single_include_date:
                html_parts.append(f"""
        <div class="metadata">
            <strong>生成时间：</strong>{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}<br>
            <strong>分析股票：</strong>{symbol}<br>
            <strong>数据来源：</strong>AkShare API<br>
            <strong>数据范围：</strong>{df['date'].min().date() if pd.api.types.is_datetime64_any_dtype(df['date']) else 'N/A'} 至 {df['date'].max().date() if pd.api.types.is_datetime64_any_dtype(df['date']) else 'N/A'}
        </div>
""")
            
            # 关键指标
            strategy_ret = test_df["strategy_equity"].iloc[-1] - 1
            bh_ret = test_df["buy_hold_equity"].iloc[-1] - 1
            test_sharpe = sharpe_ratio(test_df['strategy_return'])
            test_mdd = max_drawdown(test_df['strategy_equity'])
            
            html_parts.append(f"""
        <h2>📈 关键指标</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">策略收益</div>
                <div class="metric-value">{strategy_ret:.2%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">买入持有收益</div>
                <div class="metric-value">{bh_ret:.2%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">夏普比率</div>
                <div class="metric-value">{test_sharpe:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">最大回撤</div>
                <div class="metric-value">{test_mdd:.2%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">策略建议</div>
                <div class="metric-value">{suggestion}</div>
            </div>
        </div>
""")
            
            # 蜡烛图
            html_parts.append("""
        <h2>📊 训练集蜡烛图</h2>
        <div class="chart-container"><div id="candle-chart"></div></div>
        <script>
""")
            html_parts.append(f"""
            var candleData = {candle.to_json()};
            Plotly.newPlot('candle-chart', candleData.data, candleData.layout, {{responsive: true}});
""")
            html_parts.append("        </script>")
            
            # RSI + MACD
            html_parts.append("""
        <h2>📉 RSI + MACD</h2>
        <div class="chart-container"><div id="indicator-chart"></div></div>
        <script>
""")
            html_parts.append(f"""
            var indData = {ind_fig.to_json()};
            Plotly.newPlot('indicator-chart', indData.data, indData.layout, {{responsive: true}});
""")
            html_parts.append("        </script>")
            
            # 因子评分
            html_parts.append("""
        <h2>🎯 因子评分</h2>
        <div class="chart-container"><div id="score-chart"></div></div>
        <script>
""")
            html_parts.append(f"""
            var scoreData = {score_fig.to_json()};
            Plotly.newPlot('score-chart', scoreData.data, scoreData.layout, {{responsive: true}});
""")
            html_parts.append("        </script>")
            
            # 测试集表现
            html_parts.append("""
        <h2>📊 测试集表现</h2>
        <div class="chart-container"><div id="equity-chart"></div></div>
        <script>
""")
            html_parts.append(f"""
            var eqData = {equity_fig.to_json()};
            Plotly.newPlot('equity-chart', eqData.data, eqData.layout, {{responsive: true}});
""")
            html_parts.append("        </script>")
            
            # 交易信号
            html_parts.append("""
        <h2>🔔 测试集交易信号</h2>
        <div class="chart-container"><div id="signal-chart"></div></div>
        <script>
""")
            html_parts.append(f"""
            var sigData = {signal_fig.to_json()};
            Plotly.newPlot('signal-chart', sigData.data, sigData.layout, {{responsive: true}});
""")
            html_parts.append("        </script>")
            
            # 尾部
            html_parts.append("""
        <div class="footer">
            <p>📊 由策略实验室 Streamlit App 生成</p>
            <p>数据来源：AkShare | 图表技术：Plotly.js</p>
        </div>
    </div>
</body>
</html>
""")
            
            full_html = "".join(html_parts)
            
            st.download_button(
                label="⬇️ 下载HTML报告",
                data=full_html,
                file_name=f"strategy_report_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                type="primary",
                width="stretch"
            )
            st.success("✅ HTML报告已生成！点击上方按钮下载")
