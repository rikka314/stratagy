"""测试因子计算 Pipeline

验证四层因子架构的完整性和正确性
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from core.factor_pipeline import (
    FactorPipeline,
    get_factor_pipeline,
    compute_all_factors,
)


class TestFactorPipeline:
    """测试 FactorPipeline 类"""

    def test_initialization(self):
        """测试初始化"""
        pipeline = FactorPipeline()
        assert pipeline.macro_factors is not None

    def test_get_layer_factors(self):
        """测试获取层因子列表"""
        pipeline = FactorPipeline()

        # Layer 1: 趋势动量
        layer1 = pipeline.get_layer_factors(1)
        assert 'mom_short_z' in layer1
        assert 'mom_long_z' in layer1
        assert 'macd_z' in layer1

        # Layer 2: 均值回归
        layer2 = pipeline.get_layer_factors(2)
        assert 'rsi_z' in layer2
        assert 'bb_position_rank' in layer2
        assert 'price_position_rank' in layer2

        # Layer 3: 风险与成交量
        layer3 = pipeline.get_layer_factors(3)
        assert 'vol_z' in layer3
        assert 'drawdown_rank' in layer3
        assert 'obv_trend_rank' in layer3
        assert 'volume_ratio_rank' in layer3

        # Layer 4: 宏观与相对
        layer4 = pipeline.get_layer_factors(4)
        assert 'vix_level' in layer4
        assert 'vix_regime' in layer4
        assert 'rel_strength_spy' in layer4
        assert 'beta_20d' in layer4

    def test_get_all_factors(self):
        """测试获取所有因子"""
        pipeline = FactorPipeline()
        all_factors = pipeline.get_all_factors()

        assert 'layer1_trend_momentum' in all_factors
        assert 'layer2_mean_reversion' in all_factors
        assert 'layer3_risk_volume' in all_factors
        assert 'layer4_macro_relative' in all_factors

        # 验证总因子数
        total = sum(len(factors) for factors in all_factors.values())
        assert total >= 10  # 至少10个因子

    def test_compute_layer1_trend_momentum(self):
        """测试 Layer 1: 趋势动量因子"""
        pipeline = FactorPipeline()

        # 创建测试数据 (150天，确保有足够历史)
        dates = pd.date_range('2020-01-01', periods=150, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(150).cumsum(),
            'high': 102 + np.random.randn(150).cumsum(),
            'low': 98 + np.random.randn(150).cumsum(),
            'close': 100 + np.random.randn(150).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, 150),
        })

        result = pipeline._compute_layer1_trend_momentum(df)

        # 验证因子存在
        assert 'mom_short_z' in result.columns
        assert 'mom_long_z' in result.columns
        assert 'macd_z' in result.columns

        # 验证数据类型
        assert result['mom_short_z'].dtype == float
        assert result['mom_long_z'].dtype == float
        assert result['macd_z'].dtype == float

    def test_compute_layer2_mean_reversion(self):
        """测试 Layer 2: 均值回归因子"""
        pipeline = FactorPipeline()

        dates = pd.date_range('2020-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(100).cumsum(),
            'high': 102 + np.random.randn(100).cumsum(),
            'low': 98 + np.random.randn(100).cumsum(),
            'close': 100 + np.random.randn(100).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, 100),
        })

        result = pipeline._compute_layer2_mean_reversion(df)

        # 验证因子存在
        assert 'rsi_z' in result.columns
        assert 'bb_position_rank' in result.columns
        assert 'price_position_rank' in result.columns

        # 验证 rank 在 [0, 1] 范围
        valid_bb = result['bb_position_rank'].dropna()
        if len(valid_bb) > 0:
            assert (valid_bb >= 0).all() and (valid_bb <= 1).all()

        valid_price = result['price_position_rank'].dropna()
        if len(valid_price) > 0:
            assert (valid_price >= 0).all() and (valid_price <= 1).all()

    def test_compute_layer3_risk_volume(self):
        """测试 Layer 3: 风险与成交量因子"""
        pipeline = FactorPipeline()

        dates = pd.date_range('2020-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(100).cumsum(),
            'high': 102 + np.random.randn(100).cumsum(),
            'low': 98 + np.random.randn(100).cumsum(),
            'close': 100 + np.random.randn(100).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, 100),
        })

        result = pipeline._compute_layer3_risk_volume(df)

        # 验证因子存在
        assert 'vol_z' in result.columns
        assert 'drawdown_rank' in result.columns
        assert 'obv_trend_rank' in result.columns
        assert 'volume_ratio_rank' in result.columns

        # 验证 drawdown 为负或零
        valid_dd = result['drawdown_rank'].dropna()
        if len(valid_dd) > 0:
            assert (valid_dd >= 0).all() and (valid_dd <= 1).all()

    def test_compute_all_factors(self):
        """测试完整的四层因子计算"""
        pipeline = FactorPipeline()

        # 创建测试数据 (150天)
        dates = pd.date_range('2020-01-01', periods=150, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(150).cumsum(),
            'high': 102 + np.random.randn(150).cumsum(),
            'low': 98 + np.random.randn(150).cumsum(),
            'close': 100 + np.random.randn(150).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, 150),
        })

        result = pipeline.compute_all_factors(df, symbol='AAPL')

        # 验证所有层的因子都存在
        all_factors = pipeline.get_all_factors()
        for layer_name, factors in all_factors.items():
            for factor in factors:
                assert factor in result.columns, f"Missing factor: {factor} from {layer_name}"

        # 验证原始列保留
        assert 'date' in result.columns
        assert 'close' in result.columns

    def test_rolling_percentiles_do_not_use_future_rows(self):
        """追加未来数据不应改变已有 rolling rank 因子。"""
        pipeline = FactorPipeline()
        periods = 180
        dates = pd.date_range('2020-01-01', periods=periods, freq='D')
        base = pd.DataFrame({
            'date': dates,
            'open': np.linspace(100.0, 130.0, periods),
            'high': np.linspace(102.0, 132.0, periods),
            'low': np.linspace(98.0, 128.0, periods),
            'close': np.linspace(100.0, 130.0, periods),
            'volume': np.linspace(1_000_000.0, 1_200_000.0, periods),
        })
        extended = pd.concat([
            base,
            pd.DataFrame({
                'date': pd.date_range(dates[-1] + pd.Timedelta(days=1), periods=10),
                'open': np.linspace(50.0, 51.0, 10),
                'high': np.linspace(52.0, 53.0, 10),
                'low': np.linspace(48.0, 49.0, 10),
                'close': np.linspace(50.0, 51.0, 10),
                'volume': np.linspace(5_000_000.0, 6_000_000.0, 10),
            }, index=range(periods, periods + 10)),
        ], ignore_index=True)

        base_ranks = pipeline._compute_layer3_risk_volume(base)
        extended_ranks = pipeline._compute_layer3_risk_volume(extended)
        for column in ('drawdown_rank', 'obv_trend_rank', 'volume_ratio_rank'):
            pd.testing.assert_series_equal(
                base_ranks[column], extended_ranks.loc[:periods - 1, column],
                check_names=False,
            )

    def test_zscore_calculation(self):
        """测试 z-score 标准化"""
        pipeline = FactorPipeline()

        # 创建简单序列
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 10)
        zscore = pipeline._zscore(series, window=10)

        # z-score 应该存在
        assert zscore.notna().any()

        # z-score 应该围绕 0
        valid_z = zscore.dropna()
        if len(valid_z) > 10:
            assert abs(valid_z.mean()) < 1.0  # 平均值接近0

    def test_singleton_pattern(self):
        """测试单例模式"""
        pipeline1 = get_factor_pipeline()
        pipeline2 = get_factor_pipeline()

        assert pipeline1 is pipeline2

    def test_convenience_function(self):
        """测试便捷函数"""
        dates = pd.date_range('2020-01-01', periods=150, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(150).cumsum(),
            'high': 102 + np.random.randn(150).cumsum(),
            'low': 98 + np.random.randn(150).cumsum(),
            'close': 100 + np.random.randn(150).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, 150),
        })

        result = compute_all_factors(df, symbol='AAPL')

        # 应该包含所有因子
        assert 'mom_short_z' in result.columns
        assert 'rsi_z' in result.columns
        assert 'vol_z' in result.columns
        assert 'vix_level' in result.columns

    def test_invalid_layer(self):
        """测试无效的层号"""
        pipeline = FactorPipeline()

        with pytest.raises(ValueError):
            pipeline.get_layer_factors(0)

        with pytest.raises(ValueError):
            pipeline.get_layer_factors(5)

    def test_real_data_integration(self):
        """测试真实数据集成 (使用2020年数据)"""
        pipeline = FactorPipeline()

        # 使用真实日期范围 (确保宏观数据覆盖)
        dates = pd.date_range('2020-01-02', periods=100, freq='B')
        df = pd.DataFrame({
            'date': dates,
            'open': 100 + np.random.randn(100).cumsum(),
            'high': 102 + np.random.randn(100).cumsum(),
            'low': 98 + np.random.randn(100).cumsum(),
            'close': 100 + np.random.randn(100).cumsum(),
            'volume': 1000000 + np.random.randint(-100000, 100000, 100),
        })

        result = pipeline.compute_all_factors(df, symbol='AAPL')

        # 验证宏观因子被正确添加
        assert 'vix_level' in result.columns
        assert 'rel_strength_spy' in result.columns
        assert 'beta_20d' in result.columns

        # 验证数据不全是 NaN
        assert result['vix_level'].notna().any()
