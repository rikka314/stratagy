"""测试宏观因子计算模块

验证 MacroFactors 类的核心功能
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from core.macro_factors import MacroFactors, get_macro_factors, add_macro_factors


class TestMacroFactors:
    """测试 MacroFactors 类"""

    def test_initialization(self):
        """测试初始化和数据加载"""
        macro = MacroFactors()

        # 验证 VIX 数据
        assert not macro.vix_data.empty
        assert 'date' in macro.vix_data.columns
        assert 'close' in macro.vix_data.columns

        # 验证 SPY 数据
        assert not macro.spy_data.empty
        assert 'date' in macro.spy_data.columns
        assert 'close' in macro.spy_data.columns

        # 验证行业映射 (可能为空)
        assert 'symbol' in macro.sector_map.columns or macro.sector_map.empty

    def test_compute_basic(self):
        """测试基本计算功能"""
        macro = MacroFactors()

        # 创建测试数据 (2020-01-02 到 2020-03-31, 约60个交易日)
        dates = pd.date_range(start='2020-01-02', end='2020-03-31', freq='B')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(len(dates)).cumsum(),
            'high': 102 + np.random.randn(len(dates)).cumsum(),
            'low': 98 + np.random.randn(len(dates)).cumsum(),
            'close': 100 + np.random.randn(len(dates)).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, len(dates)),
        })

        # 计算宏观因子
        result = macro.compute(df, symbol='AAPL')

        # 验证新增列
        expected_cols = [
            'vix_level',
            'vix_regime',
            'rel_strength_spy',
            'market_breadth',
            'beta_20d',
            'sector_momentum',
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

        # 验证数据类型和范围
        assert result['vix_level'].dtype == float
        assert result['vix_regime'].isin([0.0, 1.0, 2.0]).all() or result['vix_regime'].isna().any()
        assert result['beta_20d'].dtype == float

    def test_vix_regime_binning(self):
        """测试 VIX regime 分类"""
        macro = MacroFactors()

        # 创建简单测试数据
        df = pd.DataFrame({
            'date': pd.date_range('2020-01-02', periods=5, freq='D'),
            'close': [100, 101, 102, 103, 104],
            'open': [99, 100, 101, 102, 103],
            'high': [101, 102, 103, 104, 105],
            'low': [98, 99, 100, 101, 102],
            'volume': [1000000] * 5,
        })

        result = macro.compute(df, symbol='TEST')

        # VIX regime 应该在 0, 1, 2 之间
        assert result['vix_regime'].isin([0.0, 1.0, 2.0]).all() or result['vix_regime'].isna().any()

        # 验证 VIX level 存在
        assert result['vix_level'].notna().any()

    def test_relative_strength(self):
        """测试相对 SPY 强度计算"""
        macro = MacroFactors()

        # 创建30天数据 (确保有足够数据计算20日收益)
        dates = pd.date_range('2020-01-02', periods=30, freq='B')
        df = pd.DataFrame({
            'date': dates,
            'close': 100 * (1 + np.arange(30) * 0.01),  # 稳定上涨
            'open': 100 * (1 + np.arange(30) * 0.01) - 0.5,
            'high': 100 * (1 + np.arange(30) * 0.01) + 0.5,
            'low': 100 * (1 + np.arange(30) * 0.01) - 1,
            'volume': [1000000] * 30,
        })

        result = macro.compute(df, symbol='TEST')

        # rel_strength_spy 应该存在
        assert 'rel_strength_spy' in result.columns

        # 前20行可能是 NaN (需要20日窗口)
        assert result['rel_strength_spy'].iloc[20:].notna().any()

    def test_beta_calculation(self):
        """测试 beta 计算"""
        macro = MacroFactors()

        # 创建30天数据
        dates = pd.date_range('2020-01-02', periods=30, freq='B')
        df = pd.DataFrame({
            'date': dates,
            'close': 100 + np.random.randn(30).cumsum(),
            'open': 100 + np.random.randn(30).cumsum(),
            'high': 102 + np.random.randn(30).cumsum(),
            'low': 98 + np.random.randn(30).cumsum(),
            'volume': [1000000] * 30,
        })

        result = macro.compute(df, symbol='TEST')

        # Beta 应该存在
        assert 'beta_20d' in result.columns

        # Beta 应该在合理范围 (-5 到 5)
        valid_beta = result['beta_20d'].dropna()
        if len(valid_beta) > 0:
            assert (valid_beta.abs() < 5).all(), "Beta out of reasonable range"

    def test_get_macro_factors_singleton(self):
        """测试单例模式"""
        macro1 = get_macro_factors()
        macro2 = get_macro_factors()

        # 应该返回同一个实例
        assert macro1 is macro2

    def test_add_macro_factors_convenience(self):
        """测试便捷函数"""
        dates = pd.date_range('2020-01-02', periods=30, freq='B')
        df = pd.DataFrame({
            'date': dates,
            'close': 100 + np.random.randn(30).cumsum(),
            'open': 100 + np.random.randn(30).cumsum(),
            'high': 102 + np.random.randn(30).cumsum(),
            'low': 98 + np.random.randn(30).cumsum(),
            'volume': [1000000] * 30,
        })

        result = add_macro_factors(df, symbol='AAPL')

        # 应该包含宏观因子列
        assert 'vix_level' in result.columns
        assert 'rel_strength_spy' in result.columns
        assert 'beta_20d' in result.columns

    def test_missing_data_handling(self):
        """测试缺失数据处理"""
        macro = MacroFactors()

        # 创建未来日期数据 (VIX/SPY 可能没有)
        future_dates = pd.date_range('2027-01-01', periods=5, freq='D')
        df = pd.DataFrame({
            'date': future_dates,
            'close': [100, 101, 102, 103, 104],
            'open': [99, 100, 101, 102, 103],
            'high': [101, 102, 103, 104, 105],
            'low': [98, 99, 100, 101, 102],
            'volume': [1000000] * 5,
        })

        result = macro.compute(df, symbol='TEST')

        # 缺少未来宏观观测时不应合成 VIX 值
        assert 'vix_level' in result.columns
        assert result['vix_level'].isna().all()
