"""因子计算 Pipeline - Phase 1 实现

四层因子架构:
- Layer 1: 趋势动量 (Trend & Momentum)
- Layer 2: 均值回归 (Mean Reversion)
- Layer 3: 风险与成交量 (Risk & Volume)
- Layer 4: 宏观与相对 (Macro & Relative)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List
from pathlib import Path

from core.market_factor_context import MarketFactorContext, normalize_market
from core.macro_factors import MacroFactors


class FactorPipeline:
    """完整的因子计算 pipeline"""

    def __init__(self, data_dir: str | Path = "data/macro"):
        """初始化，加载宏观因子计算器。"""
        self.macro_factors = MacroFactors(data_dir)

    def compute_all_factors(
        self,
        df: pd.DataFrame,
        symbol: str,
        *,
        market: str | None = None,
        market_context: MarketFactorContext | None = None,
    ) -> pd.DataFrame:
        """
        计算所有四层因子

        输入:
            df: 标准行情 DataFrame (date, open, high, low, close, volume)
            symbol: 股票代码

        输出:
            添加所有因子列的 DataFrame
        """
        df = df.copy()

        # Layer 1: 趋势动量
        df = self._compute_layer1_trend_momentum(df)

        # Layer 2: 均值回归
        df = self._compute_layer2_mean_reversion(df)

        # Layer 3: 风险与成交量
        df = self._compute_layer3_risk_volume(df)

        # Layer 4: 宏观与相对
        df = self.macro_factors.compute(
            df,
            symbol,
            market=market,
            market_context=market_context,
        )

        return df

    def _compute_layer1_trend_momentum(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Layer 1: 趋势动量因子

        - mom_short_z: 短期动量 (5-10日)
        - mom_long_z: 长期动量 (20-60日)
        - macd_z: MACD
        """
        # 短期动量 (10日收益率，z-score标准化)
        mom_short = df['close'].pct_change(10)
        df['mom_short_z'] = self._zscore(mom_short, window=60)

        # 长期动量 (60日收益率，z-score标准化)
        mom_long = df['close'].pct_change(60)
        df['mom_long_z'] = self._zscore(mom_long, window=120)

        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        df['macd_z'] = self._zscore(macd, window=60)

        return df

    def _rolling_percentile(self, series: pd.Series, window: int = 60) -> pd.Series:
        """Return the percentile of each value within its trailing window."""
        def percentile(values: np.ndarray) -> float:
            if not np.isfinite(values).all():
                return np.nan
            return float(np.mean(values <= values[-1]))

        return series.rolling(window=window, min_periods=window).apply(percentile, raw=True)

    def _compute_layer2_mean_reversion(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Layer 2: 均值回归因子

        - rsi_z: RSI (超买超卖)
        - bb_position_rank: 布林带位置
        - price_position_rank: 价格通道位置
        """
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        df['rsi_z'] = self._zscore(rsi, window=60)

        # 布林带位置
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        bb_upper = sma_20 + 2 * std_20
        bb_lower = sma_20 - 2 * std_20
        bb_position = (df['close'] - bb_lower) / (bb_upper - bb_lower + 1e-10)
        df['bb_position_rank'] = self._rolling_percentile(bb_position)

        # 价格通道位置 (60日)
        high_60 = df['high'].rolling(window=60).max()
        low_60 = df['low'].rolling(window=60).min()
        price_position = (df['close'] - low_60) / (high_60 - low_60 + 1e-10)
        df['price_position_rank'] = self._rolling_percentile(price_position)

        return df

    def _compute_layer3_risk_volume(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Layer 3: 风险与成交量因子

        - vol_z: 波动率
        - drawdown_rank: 回撤
        - obv_trend_rank: 成交量趋势
        - volume_ratio_rank: 成交量比率
        """
        # 波动率 (20日收益率标准差)
        returns = df['close'].pct_change()
        vol = returns.rolling(window=20).std()
        df['vol_z'] = self._zscore(vol, window=60)

        # 回撤
        cum_max = df['close'].cummax()
        drawdown = (df['close'] - cum_max) / cum_max
        df['drawdown_rank'] = self._rolling_percentile(drawdown)

        # OBV 趋势
        obv = (np.sign(df['close'].diff()) * df['volume']).cumsum()
        obv_ma = obv.rolling(window=20).mean()
        obv_trend = obv - obv_ma
        df['obv_trend_rank'] = self._rolling_percentile(obv_trend)

        # 成交量比率
        vol_ma = df['volume'].rolling(window=20).mean()
        volume_ratio = df['volume'] / (vol_ma + 1e-10)
        df['volume_ratio_rank'] = self._rolling_percentile(volume_ratio)

        return df

    def _zscore(self, series: pd.Series, window: int = 60) -> pd.Series:
        """
        计算滚动 z-score

        z = (x - mean) / std
        """
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        zscore = (series - mean) / (std + 1e-10)
        return zscore

    def get_layer_factors(self, layer: int, *, market: str = "US") -> List[str]:
        """
        返回指定层的因子列表

        参数:
            layer: 层号 (1-4)

        返回:
            因子名列表
        """
        market = normalize_market(market)
        layers = {
            1: ['mom_short_z', 'mom_long_z', 'macd_z'],
            2: ['rsi_z', 'bb_position_rank', 'price_position_rank'],
            3: ['vol_z', 'drawdown_rank', 'obv_trend_rank', 'volume_ratio_rank'],
            4: (
                [
                    "market_vol_level",
                    "market_vol_regime",
                    "rel_strength_market",
                    "market_breadth",
                    "market_beta_20d",
                ]
                if market == "CN_A"
                else ['vix_level', 'vix_regime', 'rel_strength_spy', 'market_breadth', 'beta_20d', 'sector_momentum']
            ),
        }

        if layer not in layers:
            raise ValueError(f"Invalid layer: {layer}. Must be 1-4.")

        return layers[layer]

    def get_all_factors(self, *, market: str = "US") -> Dict[str, List[str]]:
        """
        返回所有层的因子字典

        返回:
            {layer_name: [factor1, factor2, ...]}
        """
        return {
            'layer1_trend_momentum': self.get_layer_factors(1, market=market),
            'layer2_mean_reversion': self.get_layer_factors(2, market=market),
            'layer3_risk_volume': self.get_layer_factors(3, market=market),
            'layer4_macro_relative': self.get_layer_factors(4, market=market),
        }


# 全局实例 (lazy initialization)
_factor_pipeline_instance: Optional[FactorPipeline] = None


def get_factor_pipeline() -> FactorPipeline:
    """获取全局 FactorPipeline 实例 (单例模式)"""
    global _factor_pipeline_instance
    if _factor_pipeline_instance is None:
        _factor_pipeline_instance = FactorPipeline()
    return _factor_pipeline_instance


def compute_all_factors(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    便捷函数: 计算所有四层因子

    输入:
        df: 标准行情 DataFrame
        symbol: 股票代码

    输出:
        添加所有因子列的 DataFrame
    """
    pipeline = get_factor_pipeline()
    return pipeline.compute_all_factors(df, symbol)
