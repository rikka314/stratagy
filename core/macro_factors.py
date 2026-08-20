"""
宏观特征模块
============
实现市场层面的宏观因子，用于捕捉市场环境和个股相对表现

Phase 1 新增 5 个核心宏观维度：
1. 市场波动率 regime (VIX)
2. 相对强度 vs SPY
3. 市场广度
4. 个股 beta
5. 行业相对表现
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)


class MacroFactors:
    """宏观特征计算器"""

    def __init__(self, macro_data_dir: str = "data/macro"):
        """
        初始化宏观特征计算器

        Args:
            macro_data_dir: 宏观数据存储目录
        """
        self.macro_data_dir = Path(macro_data_dir)
        self._vix_data: Optional[pd.DataFrame] = None
        self._spy_data: Optional[pd.DataFrame] = None
        self._cache = {}

    def _load_vix(self) -> pd.DataFrame:
        """加载 VIX 数据（延迟加载）"""
        if self._vix_data is None:
            vix_path = self.macro_data_dir / "vix_daily.parquet"
            if vix_path.exists():
                self._vix_data = pd.read_parquet(vix_path)
                if not isinstance(self._vix_data.index, pd.DatetimeIndex):
                    self._vix_data.index = pd.to_datetime(self._vix_data.index)
            else:
                # 返回空 DataFrame，后续会处理
                self._vix_data = pd.DataFrame()
        return self._vix_data

    def _load_spy(self) -> pd.DataFrame:
        """加载 SPY 数据（延迟加载）"""
        if self._spy_data is None:
            spy_path = self.macro_data_dir / "spy_daily.parquet"
            if spy_path.exists():
                self._spy_data = pd.read_parquet(spy_path)
                if not isinstance(self._spy_data.index, pd.DatetimeIndex):
                    self._spy_data.index = pd.to_datetime(self._spy_data.index)
            else:
                self._spy_data = pd.DataFrame()
        return self._spy_data

    def get_vix(self, date: pd.Timestamp) -> float:
        """
        获取指定日期的 VIX 值

        Args:
            date: 查询日期

        Returns:
            VIX 收盘价，如果不可用返回 NaN
        """
        vix = self._load_vix()
        if vix.empty:
            return np.nan

        # 确保 date 是 Timestamp
        if not isinstance(date, pd.Timestamp):
            date = pd.to_datetime(date)

        # 向前填充到最近的可用日期
        valid_dates = vix.index[vix.index <= date]
        if len(valid_dates) == 0:
            return np.nan

        latest_date = valid_dates[-1]
        return float(vix.loc[latest_date, 'Close'])

    def classify_vix_regime(self, date: pd.Timestamp) -> str:
        """
        分类 VIX regime

        Args:
            date: 查询日期

        Returns:
            'low' (VIX < 15), 'med' (15 <= VIX < 25), 'high' (VIX >= 25)
        """
        vix_level = self.get_vix(date)

        if np.isnan(vix_level):
            return 'med'  # 默认中等波动

        if vix_level < 15:
            return 'low'
        elif vix_level < 25:
            return 'med'
        else:
            return 'high'

    def compute_relative_strength(
        self,
        stock_data: pd.DataFrame,
        date: pd.Timestamp,
        window: int = 20
    ) -> float:
        """
        计算个股相对 SPY 的强度

        相对强度 = (个股20日收益 - SPY 20日收益) / SPY 20日波动率

        Args:
            stock_data: 个股 OHLCV 数据，index 为日期
            date: 查询日期
            window: 回溯窗口（交易日）

        Returns:
            相对强度得分，标准化后的超额收益
        """
        spy = self._load_spy()
        if spy.empty or stock_data.empty:
            return np.nan

        # 确保日期对齐
        stock_data = stock_data.copy()
        if not isinstance(stock_data.index, pd.DatetimeIndex):
            stock_data.index = pd.to_datetime(stock_data.index)

        # 获取窗口内的数据
        end_date = date
        stock_window = stock_data[stock_data.index <= end_date].tail(window + 1)
        spy_window = spy[spy.index <= end_date].tail(window + 1)

        if len(stock_window) < 2 or len(spy_window) < 2:
            return np.nan

        # 计算收益率
        stock_return = (stock_window['Close'].iloc[-1] / stock_window['Close'].iloc[0]) - 1
        spy_return = (spy_window['Close'].iloc[-1] / spy_window['Close'].iloc[0]) - 1

        # 计算 SPY 波动率（用于标准化）
        spy_daily_returns = spy_window['Close'].pct_change().dropna()
        spy_vol = spy_daily_returns.std() * np.sqrt(252) if len(spy_daily_returns) > 1 else 0.01

        # 相对强度 = 超额收益 / 市场波动率
        excess_return = stock_return - spy_return
        rel_strength = excess_return / (spy_vol + 1e-8)

        return float(rel_strength)

    def compute_rolling_beta(
        self,
        stock_data: pd.DataFrame,
        date: pd.Timestamp,
        window: int = 20
    ) -> float:
        """
        计算个股相对 SPY 的 beta

        Beta = Cov(stock, SPY) / Var(SPY)

        Args:
            stock_data: 个股 OHLCV 数据
            date: 查询日期
            window: 回溯窗口（交易日）

        Returns:
            Beta 系数
        """
        spy = self._load_spy()
        if spy.empty or stock_data.empty:
            return np.nan

        # 确保日期对齐
        stock_data = stock_data.copy()
        if not isinstance(stock_data.index, pd.DatetimeIndex):
            stock_data.index = pd.to_datetime(stock_data.index)

        # 获取窗口内的数据
        end_date = date
        stock_window = stock_data[stock_data.index <= end_date].tail(window + 1)
        spy_window = spy[spy.index <= end_date].tail(window + 1)

        if len(stock_window) < 3 or len(spy_window) < 3:
            return np.nan

        # 计算日收益率
        stock_returns = stock_window['Close'].pct_change().dropna()
        spy_returns = spy_window['Close'].pct_change().dropna()

        # 对齐日期（取交集）
        common_dates = stock_returns.index.intersection(spy_returns.index)
        if len(common_dates) < 3:
            return np.nan

        stock_returns = stock_returns.loc[common_dates]
        spy_returns = spy_returns.loc[common_dates]

        # 计算 beta
        covariance = np.cov(stock_returns, spy_returns)[0, 1]
        spy_variance = np.var(spy_returns)

        if spy_variance < 1e-8:
            return 1.0  # 默认 beta

        beta = covariance / spy_variance
        return float(beta)

    def compute(
        self,
        date: pd.Timestamp,
        stock_data: pd.DataFrame,
        stock_symbol: str = None
    ) -> Dict[str, float]:
        """
        计算所有宏观特征

        Args:
            date: 查询日期
            stock_data: 个股 OHLCV 数据
            stock_symbol: 股票代码（可选，用于行业分类）

        Returns:
            包含 5 个宏观特征的字典
        """
        features = {}

        # 1. VIX 市场波动率
        features['vix_level'] = self.get_vix(date)
        vix_regime = self.classify_vix_regime(date)
        features['vix_regime_low'] = 1.0 if vix_regime == 'low' else 0.0
        features['vix_regime_med'] = 1.0 if vix_regime == 'med' else 0.0
        features['vix_regime_high'] = 1.0 if vix_regime == 'high' else 0.0

        # 2. 相对强度 vs SPY
        features['rel_strength_vs_spy'] = self.compute_relative_strength(
            stock_data, date, window=20
        )

        # 3. 个股 beta
        features['beta_20d'] = self.compute_rolling_beta(
            stock_data, date, window=20
        )

        # 4. 市场广度（暂时使用 SPY 的动量作为代理）
        spy = self._load_spy()
        if not spy.empty:
            spy_window = spy[spy.index <= date].tail(21)
            if len(spy_window) >= 2:
                spy_momentum = (spy_window['Close'].iloc[-1] / spy_window['Close'].iloc[0]) - 1
                features['market_breadth'] = float(spy_momentum)
            else:
                features['market_breadth'] = 0.0
        else:
            features['market_breadth'] = 0.0

        # 5. 行业相对表现（暂时用个股 vs 市场的相对动量）
        # TODO: 如果有行业分类数据，可以改进此特征
        rel_strength = features['rel_strength_vs_spy']
        if not np.isnan(rel_strength):
            features['sector_momentum'] = rel_strength * 0.5  # 缩放到合理范围
        else:
            features['sector_momentum'] = 0.0

        return features

    def compute_batch(
        self,
        stock_data: pd.DataFrame,
        dates: pd.DatetimeIndex = None
    ) -> pd.DataFrame:
        """
        批量计算宏观特征（用于回测）

        Args:
            stock_data: 个股 OHLCV 数据
            dates: 要计算的日期列表，如果为 None 则使用 stock_data 的所有日期

        Returns:
            包含所有宏观特征的 DataFrame，index 为日期
        """
        if dates is None:
            dates = stock_data.index

        # 确保 dates 是 DatetimeIndex
        if not isinstance(dates, pd.DatetimeIndex):
            dates = pd.to_datetime(dates)

        results = []
        for date in dates:
            features = self.compute(date, stock_data)
            features['date'] = date
            results.append(features)

        df = pd.DataFrame(results)
        df.set_index('date', inplace=True)
        return df


def download_macro_data(start_date: str = "2015-01-01", end_date: str = "2026-01-01"):
    """
    下载宏观数据（VIX 和 SPY）

    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("需要安装 yfinance: pip install yfinance")

    import time

    print(f"下载宏观数据: {start_date} 到 {end_date}")

    # 创建目录
    macro_dir = Path("data/macro")
    macro_dir.mkdir(parents=True, exist_ok=True)

    # 下载 VIX（带重试）
    print("下载 VIX 数据...")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            vix = yf.download("^VIX", start=start_date, end=end_date, progress=False)
            if not vix.empty:
                vix_path = macro_dir / "vix_daily.parquet"
                vix.to_parquet(vix_path)
                print(f"[OK] VIX 数据已保存: {vix_path} ({len(vix)} 行)")
                break
            else:
                print(f"[警告] VIX 数据为空，尝试 {attempt + 1}/{max_retries}")
                time.sleep(5)
        except Exception as e:
            print(f"[错误] VIX 下载失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                print("[警告] VIX 下载失败，将使用空数据")
                vix = pd.DataFrame()

    # 下载 SPY（带重试）
    print("下载 SPY 数据...")
    for attempt in range(max_retries):
        try:
            spy = yf.download("SPY", start=start_date, end=end_date, progress=False)
            if not spy.empty:
                spy_path = macro_dir / "spy_daily.parquet"
                spy.to_parquet(spy_path)
                print(f"[OK] SPY 数据已保存: {spy_path} ({len(spy)} 行)")
                break
            else:
                print(f"[警告] SPY 数据为空，尝试 {attempt + 1}/{max_retries}")
                time.sleep(5)
        except Exception as e:
            print(f"[错误] SPY 下载失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                print("[警告] SPY 下载失败，将使用空数据")
                spy = pd.DataFrame()

    print("\n宏观数据下载完成!")
    return vix, spy


if __name__ == "__main__":
    # 测试下载功能
    download_macro_data()
