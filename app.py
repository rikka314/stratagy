import io
import os

import akshare as ak
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


DATA_DIR = "data"
DEFAULT_SYMBOL = "AAPL"
DEFAULT_ADJUST = "qfq"


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    rename_map = {}
    if "trade_date" in df.columns and "date" not in df.columns:
        rename_map["trade_date"] = "date"
    if "datetime" in df.columns and "date" not in df.columns:
        rename_map["datetime"] = "date"
    if "vol" in df.columns and "volume" not in df.columns:
        rename_map["vol"] = "volume"
    if "volumn" in df.columns and "volume" not in df.columns:
        rename_map["volumn"] = "volume"
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def ensure_date_column(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.sort_values("date")
        return df
    df["date"] = pd.RangeIndex(start=1, stop=len(df) + 1, step=1)
    return df


def fetch_data(symbol: str, adjust: str) -> pd.DataFrame:
    df = ak.stock_us_daily(symbol=symbol, adjust=adjust)
    df = standardize_columns(df)
    if "date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "date"})
    df = ensure_date_column(df)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df


@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


@st.cache_data(show_spinner=False)
def load_uploaded_bytes(data: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(data))
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    z = (series - mean) / std
    return z.replace([np.inf, -np.inf], np.nan)


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def last_percentile(values: pd.Series) -> float:
        ranked = values.rank(pct=True)
        return float(ranked.iloc[-1])

    return series.rolling(window=window, min_periods=window).apply(last_percentile, raw=False)


def compute_macd(series: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat(
        [(high - low).abs(), (high - df["close"].shift(1)).abs(), (low - df["close"].shift(1)).abs()],
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
    df = df.copy()
    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    df["macd"], df["signal"], df["histogram"] = compute_macd(
        df["close"], fast=macd_fast, slow=macd_slow, signal=macd_signal
    )
    df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
    df["atr"] = compute_atr(df, period=atr_period)
    df["adx"] = compute_adx(df, period=adx_period)
    return df


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
) -> pd.DataFrame:
    df = df.copy()
    df["trend_ok"] = df["ema_fast"] > df["ema_slow"]
    df["strength_ok"] = df["adx"] >= adx_threshold
    df["rsi_ok"] = (df["rsi"] > rsi_lower) & (df["rsi"] < rsi_upper)
    df["ret_short"] = df["close"].pct_change(momentum_short)
    df["ret_long"] = df["close"].pct_change(momentum_long)
    df["volatility"] = df["atr"] / df["close"]
    df["mom_short_z"] = rolling_zscore(df["ret_short"], score_lookback)
    df["mom_long_z"] = rolling_zscore(df["ret_long"], score_lookback)
    df["macd_z"] = rolling_zscore(df["histogram"], score_lookback)
    df["rsi_z"] = rolling_zscore(df["rsi"], score_lookback)
    df["vol_z"] = rolling_zscore(df["volatility"], score_lookback)
    df["factor_score"] = (
        weight_mom_short * df["mom_short_z"]
        + weight_mom_long * df["mom_long_z"]
        + weight_macd * df["macd_z"]
        + weight_rsi * df["rsi_z"]
        - weight_vol * df["vol_z"]
    )
    df["factor_score"] = df["factor_score"].fillna(0.0)
    df["factor_percentile"] = rolling_percentile(df["factor_score"], score_lookback).fillna(0.0)
    score_position = np.select(
        [df["factor_percentile"] >= score_high_pct, df["factor_percentile"] >= score_mid_pct],
        [1.0, 0.5],
        default=0.0,
    )
    macd_above = df["macd"] > df["signal"]
    filter_ok = (
        df["trend_ok"]
        & df["strength_ok"]
        & df["rsi_ok"]
        & macd_above
        & (df["factor_score"] >= entry_threshold)
    )
    df["target_position"] = np.where(filter_ok, score_position, 0.0)
    exit_block = (
        (df["factor_score"] <= exit_threshold)
        | (df["ema_fast"] < df["ema_slow"])
        | (df["rsi"] > rsi_upper)
        | (df["rsi"] < rsi_lower)
        | (df["macd"] < df["signal"])
    )
    df.loc[exit_block, "target_position"] = 0.0
    df["buy_signal"] = (df["target_position"] > 0) & (df["target_position"].shift(1) <= 0)
    df["sell_signal"] = (df["target_position"] <= 0) & (df["target_position"].shift(1) > 0)
    return df


def simulate_strategy(
    df: pd.DataFrame,
    initial_position: int = 0,
    stop_loss_mult: float = 0.0,
    take_profit_mult: float = 0.0,
) -> pd.DataFrame:
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
    roll_max = equity.cummax()
    drawdown = equity / roll_max - 1
    return float(drawdown.min())


def sharpe_ratio(returns: pd.Series) -> float:
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
) -> dict | None:
    rng = np.random.default_rng(7)
    best = None
    for _ in range(trials):
        entry_threshold = round(rng.uniform(-1.0, 1.5), 2)
        exit_threshold = round(rng.uniform(-1.5, 0.5), 2)
        if entry_threshold <= exit_threshold:
            continue
        adx_candidate = round(rng.uniform(10, 35), 0)
        stop_loss_mult = round(rng.uniform(0.0, 4.0), 1)
        take_profit_mult = round(rng.uniform(0.0, 6.0), 1)

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
        )
        train_sim = simulate_strategy(
            df_signals.iloc[:split_idx],
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        total_return = train_sim["strategy_equity"].iloc[-1] - 1
        sharpe = sharpe_ratio(train_sim["strategy_return"])
        score = sharpe + total_return
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


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def load_or_fetch_stock(symbol: str, adjust: str) -> pd.DataFrame:
    """加载或下载股票数据，优先使用本地缓存"""
    data_path = os.path.join(DATA_DIR, f"{symbol.lower()}_daily.csv")
    
    if os.path.exists(data_path):
        try:
            df = load_csv(data_path)
            return df
        except Exception as e:
            st.warning(f"加载本地数据失败 ({symbol}): {e}，尝试重新下载...")
    
    try:
        with st.spinner(f"正在下载 {symbol} 数据..."):
            df = fetch_data(symbol, adjust)
            df.to_csv(data_path, index=False)
            st.success(f"✓ {symbol} 数据已保存")
        return df
    except Exception as e:
        st.error(f"下载 {symbol} 数据失败: {e}")
        return None


def get_available_stocks() -> list:
    """获取本地已有的股票列表"""
    if not os.path.exists(DATA_DIR):
        return []
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('_daily.csv')]
    return [f.replace('_daily.csv', '').upper() for f in files]


def normalize_prices(df_dict: dict) -> pd.DataFrame:
    """归一化多个股票的价格到起点=100"""
    normalized_data = {}
    
    for symbol, df in df_dict.items():
        if df is not None and not df.empty:
            first_close = df['close'].iloc[0]
            normalized_data[symbol] = (df['close'] / first_close * 100).values
    
    if not normalized_data:
        return pd.DataFrame()
    
    # 使用第一个股票的日期作为基准
    base_dates = list(df_dict.values())[0]['date']
    result_df = pd.DataFrame({'date': base_dates})
    
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
                font=dict(size=13, color='#2c3e50')
            ),
            titleside="right",
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
    
    # ===== 多股票对比功能 =====
    st.markdown("---")
    st.subheader("🔍 多股票对比")
    
    # 获取已有股票列表
    available_stocks = get_available_stocks()
    
    # 添加新股票
    with st.expander("➕ 添加股票", expanded=False):
        new_symbol = st.text_input(
            "输入股票代码",
            placeholder="例如: TSLA, NVDA, MSFT",
            help="输入股票代码后按回车添加"
        ).upper().strip()
        
        add_stock_btn = st.button("添加到对比列表", use_container_width=True)
        
        if add_stock_btn and new_symbol:
            if new_symbol not in available_stocks:
                # 下载新股票数据
                adjust_for_new = st.session_state.get("adjust", "qfq")
                new_df = load_or_fetch_stock(new_symbol, adjust_for_new)
                if new_df is not None:
                    available_stocks = get_available_stocks()
            else:
                st.info(f"✓ {new_symbol} 已在数据库中")
    
    # 选择对比股票
    compare_stocks = []
    if available_stocks:
        compare_stocks = st.multiselect(
            "选择对比股票",
            options=available_stocks,
            default=[available_stocks[0]] if available_stocks else [],
            help="可选择多个股票进行对比分析",
            key="compare_stocks_selector"
        )
        
        if len(compare_stocks) > 1:
            st.info(f"✓ 已选择 {len(compare_stocks)} 只股票进行对比")
    else:
        st.warning("暂无股票数据，请先添加股票")
    
    # 保存到session state
    st.session_state['compare_stocks'] = compare_stocks
    
    st.markdown("---")
    
    # ===== 主分析股票选择 =====
    st.subheader("📈 主分析股票")
    symbol = st.text_input("标的代码", value=DEFAULT_SYMBOL, help="用于策略分析的主股票。").upper().strip()
    adjust = st.selectbox("复权方式", options=["qfq", "hfq", "none"], index=0, help="仅影响 AkShare 下载。")
    st.session_state["adjust"] = adjust
    
    train_ratio = st.slider(
        "训练集比例",
        min_value=0.6,
        max_value=0.9,
        value=0.7,
        step=0.05,
        help="按时间顺序切分训练/测试集。",
    )
    st.markdown("**策略参数（趋势过滤 + MACD/RSI/ATR）**")
    ema_fast = st.slider("趋势 EMA 快线", 5, 50, 20, help="趋势过滤的短周期 EMA。")
    ema_slow = st.slider("趋势 EMA 慢线", 20, 200, 60, help="趋势过滤的长周期 EMA。")
    adx_period = st.slider("ADX 周期", 5, 30, 14, help="趋势强度指标的计算周期。")
    adx_threshold = st.slider(
        "ADX 阈值",
        10,
        40,
        20,
        help="ADX 高于该值才认为趋势有效。",
        key="adx_threshold",
    )
    macd_fast = st.slider("MACD 快线周期", 5, 20, 12, help="MACD 快线 EMA 周期。")
    macd_slow = st.slider("MACD 慢线周期", 10, 40, 26, help="MACD 慢线 EMA 周期。")
    macd_signal = st.slider("MACD 信号周期", 5, 20, 9, help="MACD 信号线 EMA 周期。")
    rsi_period = st.slider("RSI 周期", 5, 30, 14, help="RSI 计算周期。")
    rsi_lower = st.slider("RSI 下限阈值", 10, 50, 30, help="RSI 低于该值视为偏弱。")
    rsi_upper = st.slider("RSI 上限阈值", 50, 90, 70, help="RSI 高于该值视为偏强。")
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
    uploaded_file = st.file_uploader(
        "上传 CSV（列名：open, close, volumn/volume, high, low）",
        type=["csv"],
    )
    refresh = st.button("下载/刷新 AkShare 数据")

data_path = os.path.join(DATA_DIR, f"{symbol.lower()}_daily.csv")

if uploaded_file is not None:
    df_raw = load_uploaded_bytes(uploaded_file.getvalue())
    st.info("已使用上传的数据集。")
else:
    if refresh or not os.path.exists(data_path):
        with st.spinner("正在从 AkShare 下载数据..."):
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
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date = selected_range
        end_date = selected_range
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
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

# ===== 多股票对比图表区域 =====
compare_stocks = st.session_state.get('compare_stocks', [])
if len(compare_stocks) > 1:
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
    
    st.markdown("---")

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
        with st.spinner("正在搜索参数..."):
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
            )
        st.session_state["best_params"] = best_params

st.subheader("参数推荐")
best = st.session_state.get("best_params")
if best:
    st.write(
        "基于训练集的随机搜索结果（供参考，需自行验证）。"
    )
    st.write(
        f"评分：{best['score']:.2f} | 训练集收益：{format_pct(best['return'])} | "
        f"夏普：{best['sharpe']:.2f}"
    )
    st.write(
        f"ADX 阈值：{best['adx_threshold']:.0f} | 入场阈值：{best['entry_threshold']:.2f} | "
        f"出场阈值：{best['exit_threshold']:.2f}"
    )
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
