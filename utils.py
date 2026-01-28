"""
共享工具函数库 - 策略诊断实验
所有任务都可以导入使用这些函数
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Tuple, Dict, List
import warnings
warnings.filterwarnings('ignore')


# ============ 数据加载与预处理 ============

def load_data(symbol: str = 'aapl', data_dir: str = 'data') -> pd.DataFrame:
    """
    标准化数据加载函数
    
    Parameters:
    -----------
    symbol : str
        股票代码，例如 'aapl', 'tsla'
    data_dir : str
        数据目录路径
        
    Returns:
    --------
    pd.DataFrame
        标准化的数据框，包含 date, open, high, low, close, volume 列
    """
    df = pd.read_csv(f'{data_dir}/{symbol}_daily.csv')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    # 确保必需列存在
    required_cols = ['date', 'open', 'high', 'low', 'close']
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(f"缺少必需列: {missing}")
    
    return df


def split_train_test(df: pd.DataFrame, train_ratio: float = 0.7) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    按时间顺序切分训练集和测试集
    
    Parameters:
    -----------
    df : pd.DataFrame
        完整数据集
    train_ratio : float
        训练集比例，默认 0.7
        
    Returns:
    --------
    train_df, test_df : tuple of pd.DataFrame
    """
    split_idx = int(len(df) * train_ratio)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()
    
    return train_df, test_df


# ============ 技术指标计算 ============

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    计算相对强弱指数 (RSI)
    
    Parameters:
    -----------
    series : pd.Series
        价格序列（通常是收盘价）
    period : int
        RSI 周期，默认 14
        
    Returns:
    --------
    pd.Series
        RSI 值序列 (0-100)
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算 MACD 指标
    
    Parameters:
    -----------
    series : pd.Series
        价格序列
    fast : int
        快线周期
    slow : int
        慢线周期
    signal : int
        信号线周期
        
    Returns:
    --------
    macd, signal_line, histogram : tuple of pd.Series
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均真实波幅 (ATR)
    
    Parameters:
    -----------
    df : pd.DataFrame
        包含 high, low, close 列的数据框
    period : int
        ATR 周期
        
    Returns:
    --------
    pd.Series
        ATR 值序列
    """
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    return atr


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均趋向指数 (ADX)
    
    Parameters:
    -----------
    df : pd.DataFrame
        包含 high, low, close 列的数据框
    period : int
        ADX 周期
        
    Returns:
    --------
    pd.Series
        ADX 值序列
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 计算 +DM 和 -DM
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    # 计算 TR
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    
    # 计算平滑的 ATR 和 DI
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1/period, min_periods=period, adjust=False
    ).mean() / atr
    
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1/period, min_periods=period, adjust=False
    ).mean() / atr
    
    # 计算 DX 和 ADX
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = (100 * dx).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    return adx


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    一次性添加所有常用技术指标
    
    Parameters:
    -----------
    df : pd.DataFrame
        原始价格数据
        
    Returns:
    --------
    pd.DataFrame
        包含所有指标的数据框
    """
    df = df.copy()
    
    # 价格指标
    df['daily_return'] = df['close'].pct_change()
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    
    # 技术指标
    df['rsi'] = compute_rsi(df['close'], 14)
    df['rsi_21'] = compute_rsi(df['close'], 21)
    df['rsi_28'] = compute_rsi(df['close'], 28)
    df['macd'], df['signal'], df['histogram'] = compute_macd(df['close'])
    df['atr'] = compute_atr(df, 14)
    df['adx'] = compute_adx(df, 14)

    # 均线
    for period in [10, 20, 50, 60, 200]:
        df[f'sma_{period}'] = df['close'].rolling(period).mean()
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    
    # 动量指标
    for period in [5, 10, 20]:
        df[f'momentum_{period}'] = df['close'].pct_change(period)
    
    # 波动率
    df['volatility_20'] = df['daily_return'].rolling(20).std()
    
    return df


# ============ 绩效指标计算 ============

def calculate_sharpe_ratio(returns: pd.Series, rf_rate: float = 0.0, periods: int = 252) -> float:
    """
    计算夏普比率
    
    Parameters:
    -----------
    returns : pd.Series
        收益率序列
    rf_rate : float
        无风险利率（年化），默认 0
    periods : int
        年化周期数，默认 252（交易日）
        
    Returns:
    --------
    float
        年化夏普比率
    """
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    
    excess_return = returns - rf_rate / periods
    sharpe = np.sqrt(periods) * excess_return.mean() / excess_return.std()
    
    return sharpe


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    计算最大回撤
    
    Parameters:
    -----------
    equity_curve : pd.Series
        权益曲线（累计净值）
        
    Returns:
    --------
    float
        最大回撤（负数，例如 -0.25 表示 25% 回撤）
    """
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max
    max_dd = drawdown.min()
    
    return max_dd


def calculate_calmar_ratio(returns: pd.Series, max_dd: float) -> float:
    """
    计算 Calmar 比率（年化收益 / 最大回撤）
    
    Parameters:
    -----------
    returns : pd.Series
        收益率序列
    max_dd : float
        最大回撤
        
    Returns:
    --------
    float
        Calmar 比率
    """
    if max_dd == 0:
        return np.inf if returns.mean() > 0 else 0.0
    
    annual_return = returns.mean() * 252
    calmar = annual_return / abs(max_dd)
    
    return calmar


def calculate_sortino_ratio(returns: pd.Series, rf_rate: float = 0.0, periods: int = 252) -> float:
    """
    计算 Sortino 比率（只考虑下行波动率）
    
    Parameters:
    -----------
    returns : pd.Series
        收益率序列
    rf_rate : float
        无风险利率（年化）
    periods : int
        年化周期数
        
    Returns:
    --------
    float
        年化 Sortino 比率
    """
    if len(returns) == 0:
        return 0.0
    
    excess_return = returns - rf_rate / periods
    downside_returns = excess_return[excess_return < 0]
    
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return np.inf if excess_return.mean() > 0 else 0.0
    
    sortino = np.sqrt(periods) * excess_return.mean() / downside_returns.std()
    
    return sortino


def calculate_win_rate(returns: pd.Series) -> float:
    """
    计算胜率（盈利交易占比）
    
    Parameters:
    -----------
    returns : pd.Series
        每笔交易的收益率
        
    Returns:
    --------
    float
        胜率（0-1 之间）
    """
    if len(returns) == 0:
        return 0.0
    
    return (returns > 0).sum() / len(returns)


def calculate_profit_factor(returns: pd.Series) -> float:
    """
    计算盈亏比（总盈利 / 总亏损）
    
    Parameters:
    -----------
    returns : pd.Series
        收益率序列
        
    Returns:
    --------
    float
        盈亏比
    """
    profits = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    
    if losses == 0:
        return np.inf if profits > 0 else 0.0
    
    return profits / losses


def calculate_all_metrics(returns: pd.Series, equity_curve: pd.Series = None) -> Dict[str, float]:
    """
    计算所有常用绩效指标
    
    Parameters:
    -----------
    returns : pd.Series
        收益率序列
    equity_curve : pd.Series, optional
        权益曲线
        
    Returns:
    --------
    dict
        包含所有指标的字典
    """
    if equity_curve is None:
        equity_curve = (1 + returns).cumprod()
    
    total_return = equity_curve.iloc[-1] - 1 if len(equity_curve) > 0 else 0.0
    annual_return = returns.mean() * 252
    annual_vol = returns.std() * np.sqrt(252)
    max_dd = calculate_max_drawdown(equity_curve)
    
    metrics = {
        'total_return': total_return,
        'annual_return': annual_return,
        'annual_volatility': annual_vol,
        'sharpe_ratio': calculate_sharpe_ratio(returns),
        'sortino_ratio': calculate_sortino_ratio(returns),
        'max_drawdown': max_dd,
        'calmar_ratio': calculate_calmar_ratio(returns, max_dd),
        'win_rate': calculate_win_rate(returns[returns != 0]),
        'profit_factor': calculate_profit_factor(returns[returns != 0]),
        'num_trades': (returns != 0).sum(),
    }
    
    return metrics


# ============ 因子分析 ============

def calculate_ic(factor: pd.Series, forward_return: pd.Series, method: str = 'pearson') -> float:
    """
    计算信息系数 (IC)
    
    Parameters:
    -----------
    factor : pd.Series
        因子值序列
    forward_return : pd.Series
        未来收益率序列
    method : str
        相关系数方法，'pearson' 或 'spearman'
        
    Returns:
    --------
    float
        IC 值
    """
    # 移除 NaN
    valid = ~(factor.isna() | forward_return.isna())
    if valid.sum() < 10:  # 至少需要 10 个有效值
        return np.nan
    
    return factor[valid].corr(forward_return[valid], method=method)


def calculate_ic_ir(factor: pd.Series, forward_return: pd.Series, window: int = 20) -> float:
    """
    计算 IC 信息比率 (IC_IR = IC_mean / IC_std)
    
    Parameters:
    -----------
    factor : pd.Series
        因子值序列
    forward_return : pd.Series
        未来收益率序列
    window : int
        滚动窗口大小
        
    Returns:
    --------
    float
        IC_IR 值
    """
    # 计算滚动 IC
    rolling_ic = []
    for i in range(window, len(factor)):
        ic = calculate_ic(
            factor.iloc[i-window:i],
            forward_return.iloc[i-window:i]
        )
        rolling_ic.append(ic)
    
    rolling_ic = pd.Series(rolling_ic).dropna()
    
    if len(rolling_ic) == 0 or rolling_ic.std() == 0:
        return np.nan
    
    return rolling_ic.mean() / rolling_ic.std()


# ============ 可视化工具 ============

def plot_equity_curves(curves: Dict[str, pd.Series], title: str = "策略权益曲线对比", 
                       figsize: Tuple[int, int] = (12, 6), save_path: str = None):
    """
    绘制多条权益曲线对比图
    
    Parameters:
    -----------
    curves : dict
        策略名称到权益曲线的映射
    title : str
        图表标题
    figsize : tuple
        图表尺寸
    save_path : str, optional
        保存路径
    """
    plt.figure(figsize=figsize)
    
    for name, curve in curves.items():
        plt.plot(curve.index, curve.values, label=name, linewidth=2)
    
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('日期', fontsize=12)
    plt.ylabel('累计收益', fontsize=12)
    plt.legend(loc='best', fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    
    plt.show()


def plot_drawdown(equity_curve: pd.Series, title: str = "回撤曲线", 
                  figsize: Tuple[int, int] = (12, 4), save_path: str = None):
    """
    绘制回撤曲线
    
    Parameters:
    -----------
    equity_curve : pd.Series
        权益曲线
    title : str
        图表标题
    figsize : tuple
        图表尺寸
    save_path : str, optional
        保存路径
    """
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max
    
    plt.figure(figsize=figsize)
    plt.fill_between(drawdown.index, drawdown.values, 0, alpha=0.3, color='red')
    plt.plot(drawdown.index, drawdown.values, color='red', linewidth=1)
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('日期', fontsize=12)
    plt.ylabel('回撤', fontsize=12)
    plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.1%}'))
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    
    plt.show()


def plot_correlation_matrix(df: pd.DataFrame, columns: List[str] = None,
                            title: str = "相关系数矩阵", 
                            figsize: Tuple[int, int] = (10, 8), 
                            save_path: str = None):
    """
    绘制相关系数热图
    
    Parameters:
    -----------
    df : pd.DataFrame
        数据框
    columns : list, optional
        要分析的列名列表
    title : str
        图表标题
    figsize : tuple
        图表尺寸
    save_path : str, optional
        保存路径
    """
    if columns is not None:
        df = df[columns]
    
    corr_matrix = df.corr()
    
    plt.figure(figsize=figsize)
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='coolwarm', 
                center=0, square=True, linewidths=1, cbar_kws={"shrink": 0.8})
    plt.title(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
    
    plt.show()


# ============ 辅助工具 ============

def print_metrics_table(metrics_dict: Dict[str, Dict[str, float]]):
    """
    打印格式化的指标对比表格
    
    Parameters:
    -----------
    metrics_dict : dict
        策略名称到指标字典的映射
    """
    df = pd.DataFrame(metrics_dict).T
    
    # 格式化输出
    format_dict = {
        'total_return': '{:.2%}',
        'annual_return': '{:.2%}',
        'annual_volatility': '{:.2%}',
        'sharpe_ratio': '{:.3f}',
        'sortino_ratio': '{:.3f}',
        'max_drawdown': '{:.2%}',
        'calmar_ratio': '{:.3f}',
        'win_rate': '{:.2%}',
        'profit_factor': '{:.2f}',
        'num_trades': '{:.0f}',
    }
    
    for col in df.columns:
        if col in format_dict:
            df[col] = df[col].apply(lambda x: format_dict[col].format(x))
    
    print("\n" + "="*80)
    print("策略绩效对比表")
    print("="*80)
    print(df.to_string())
    print("="*80 + "\n")


def save_results_to_csv(data: pd.DataFrame, filename: str, output_dir: str = 'diagnosis/results'):
    """
    保存结果到 CSV 文件
    
    Parameters:
    -----------
    data : pd.DataFrame
        要保存的数据
    filename : str
        文件名（不含路径）
    output_dir : str
        输出目录
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    data.to_csv(filepath, index=True)
    print(f"✅ 结果已保存到: {filepath}")


# ============ 示例使用 ============

if __name__ == "__main__":
    # 加载数据
    df = load_data('aapl')
    print(f"数据加载成功，共 {len(df)} 行")
    
    # 添加指标
    df = add_all_indicators(df)
    print(f"技术指标计算完成，共 {len(df.columns)} 列")
    
    # 计算收益
    df['strategy_return'] = df['daily_return']  # 示例：使用 buy & hold
    df['equity'] = (1 + df['strategy_return']).cumprod()
    
    # 计算指标
    metrics = calculate_all_metrics(df['strategy_return'].dropna(), df['equity'])
    
    print("\n策略绩效指标：")
    for key, value in metrics.items():
        if 'return' in key or 'volatility' in key or 'drawdown' in key or 'win_rate' in key:
            print(f"{key:20s}: {value:>10.2%}")
        else:
            print(f"{key:20s}: {value:>10.3f}")
