"""Phase 1: 因子分层筛选实验

按照 factor_and_expert_optimization_plan.md 的要求:
- 实验 E1: 单因子测试
- 实验 E2: 双因子测试
- 实验 E3: 最优组合选择

目标: 从每层选出最有效的因子，控制总数在 6-10 个
"""

import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from itertools import combinations
from typing import List, Tuple, Dict
from core.factor_pipeline import FactorPipeline


class FactorSelector:
    """因子筛选器"""

    def __init__(self, pipeline: FactorPipeline):
        self.pipeline = pipeline

    def evaluate_single_factor(
        self,
        df: pd.DataFrame,
        factor: str,
        forward_return_days: int = 20
    ) -> Dict[str, float]:
        """
        评估单因子表现

        参数:
            df: 包含因子的 DataFrame
            factor: 因子名称
            forward_return_days: 前瞻收益期

        返回:
            包含 IC, Sharpe, Win Rate 等指标的字典
        """
        # 计算前瞻收益
        df = df.copy()
        df['forward_return'] = df['close'].pct_change(forward_return_days).shift(-forward_return_days)

        # 去除缺失值
        valid_data = df[[factor, 'forward_return']].dropna()

        if len(valid_data) < 30:
            return {
                'factor': factor,
                'ic': 0.0,
                'ic_mean': 0.0,
                'ic_std': 0.0,
                'sharpe': 0.0,
                'win_rate': 0.0,
                'n_samples': len(valid_data),
            }

        # 1. IC (Information Coefficient)
        ic = valid_data[factor].corr(valid_data['forward_return'])

        # 2. 滚动 IC (每20天计算一次)
        rolling_ic = []
        window = 20
        for i in range(window, len(valid_data), window):
            window_data = valid_data.iloc[i-window:i]
            if len(window_data) >= 10:
                window_ic = window_data[factor].corr(window_data['forward_return'])
                if not pd.isna(window_ic):
                    rolling_ic.append(window_ic)

        ic_mean = np.mean(rolling_ic) if rolling_ic else 0.0
        ic_std = np.std(rolling_ic) if rolling_ic else 1.0
        ic_sharpe = ic_mean / (ic_std + 1e-6) if ic_std > 0 else 0.0

        # 3. 分组收益测试
        # 按因子值分为5组，看高组 vs 低组收益
        valid_data['quintile'] = pd.qcut(valid_data[factor], q=5, labels=False, duplicates='drop')
        group_returns = valid_data.groupby('quintile')['forward_return'].mean()

        if len(group_returns) >= 2:
            long_short_return = group_returns.iloc[-1] - group_returns.iloc[0]  # 高组 - 低组
            win_rate = (long_short_return > 0) * 1.0
        else:
            win_rate = 0.5

        return {
            'factor': factor,
            'ic': ic,
            'ic_mean': ic_mean,
            'ic_std': ic_std,
            'ic_sharpe': ic_sharpe,
            'win_rate': win_rate,
            'n_samples': len(valid_data),
        }

    def evaluate_factor_pair(
        self,
        df: pd.DataFrame,
        factor1: str,
        factor2: str,
        forward_return_days: int = 20
    ) -> Dict[str, float]:
        """
        评估双因子组合表现

        策略: 等权组合 score = factor1 + factor2
        """
        df = df.copy()
        df['forward_return'] = df['close'].pct_change(forward_return_days).shift(-forward_return_days)

        # 组合因子 (先标准化)
        f1_std = (df[factor1] - df[factor1].mean()) / (df[factor1].std() + 1e-6)
        f2_std = (df[factor2] - df[factor2].mean()) / (df[factor2].std() + 1e-6)
        df['combined_score'] = f1_std + f2_std

        valid_data = df[['combined_score', 'forward_return']].dropna()

        if len(valid_data) < 30:
            return {
                'factors': f"{factor1} + {factor2}",
                'ic': 0.0,
                'ic_sharpe': 0.0,
                'win_rate': 0.0,
                'n_samples': len(valid_data),
            }

        # IC
        ic = valid_data['combined_score'].corr(valid_data['forward_return'])

        # 滚动 IC Sharpe
        rolling_ic = []
        window = 20
        for i in range(window, len(valid_data), window):
            window_data = valid_data.iloc[i-window:i]
            if len(window_data) >= 10:
                window_ic = window_data['combined_score'].corr(window_data['forward_return'])
                if not pd.isna(window_ic):
                    rolling_ic.append(window_ic)

        ic_mean = np.mean(rolling_ic) if rolling_ic else 0.0
        ic_std = np.std(rolling_ic) if rolling_ic else 1.0
        ic_sharpe = ic_mean / (ic_std + 1e-6)

        # 分组收益
        valid_data['quintile'] = pd.qcut(valid_data['combined_score'], q=5, labels=False, duplicates='drop')
        group_returns = valid_data.groupby('quintile')['forward_return'].mean()

        if len(group_returns) >= 2:
            long_short_return = group_returns.iloc[-1] - group_returns.iloc[0]
            win_rate = (long_short_return > 0) * 1.0
        else:
            win_rate = 0.5

        return {
            'factors': f"{factor1} + {factor2}",
            'ic': ic,
            'ic_sharpe': ic_sharpe,
            'win_rate': win_rate,
            'n_samples': len(valid_data),
        }

    def select_best_from_layer(
        self,
        df: pd.DataFrame,
        layer: int,
        top_k: int = 2
    ) -> List[str]:
        """
        从指定层选择最佳因子

        参数:
            df: 包含所有因子的 DataFrame
            layer: 层号 (1-4)
            top_k: 保留前 k 个因子

        返回:
            选中的因子列表
        """
        factors = self.pipeline.get_layer_factors(layer)

        print(f"\n{'='*80}")
        print(f"Layer {layer} 单因子评估")
        print(f"{'='*80}")

        # 评估每个因子
        results = []
        for factor in factors:
            if factor not in df.columns:
                print(f"  跳过 {factor} (未计算)")
                continue

            metrics = self.evaluate_single_factor(df, factor)
            results.append(metrics)

            print(f"  {factor:25s}: IC={metrics['ic']:7.4f}, "
                  f"IC_Sharpe={metrics['ic_sharpe']:7.4f}, "
                  f"Win={metrics['win_rate']:.2f}, "
                  f"N={metrics['n_samples']}")

        if not results:
            return []

        # 按 IC_Sharpe 排序
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('ic_sharpe', ascending=False)

        # 选择 top_k
        selected = results_df.head(top_k)['factor'].tolist()

        print(f"\n  [OK] 选中: {selected}")

        return selected


def run_phase1_selection():
    """运行 Phase 1 因子筛选实验"""

    print("="*80)
    print("Phase 1: 因子分层筛选实验")
    print("="*80)

    # 1. 准备数据
    print("\n[步骤 1] 准备测试数据...")
    pipeline = FactorPipeline()

    # 使用更长的历史数据 (2019-2020 两年)
    dates = pd.date_range('2019-01-01', '2020-12-31', freq='B')
    np.random.seed(42)
    n_days = len(dates)

    # 模拟真实波动
    returns = np.random.randn(n_days) * 0.015
    close_prices = 100 * np.exp(returns.cumsum())

    df = pd.DataFrame({
        'date': dates,
        'open': close_prices * (1 + np.random.randn(n_days) * 0.005),
        'high': close_prices * (1 + np.abs(np.random.randn(n_days)) * 0.01),
        'low': close_prices * (1 - np.abs(np.random.randn(n_days)) * 0.01),
        'close': close_prices,
        'volume': 50000000 + np.random.randint(-10000000, 10000000, n_days),
    })

    print(f"  数据行数: {len(df)}")
    print(f"  日期范围: {df['date'].min()} 到 {df['date'].max()}")

    # 2. 计算所有因子
    print("\n[步骤 2] 计算所有四层因子...")
    df = pipeline.compute_all_factors(df, symbol='TEST')
    print(f"  总列数: {len(df.columns)}")

    # 3. 初始化筛选器
    selector = FactorSelector(pipeline)

    # 4. 逐层筛选
    print("\n[步骤 3] 逐层筛选因子...")

    selected_factors = {}

    # Layer 1: 趋势动量 (保留 top 2)
    selected_factors['layer1'] = selector.select_best_from_layer(df, layer=1, top_k=2)

    # Layer 2: 均值回归 (保留 top 2)
    selected_factors['layer2'] = selector.select_best_from_layer(df, layer=2, top_k=2)

    # Layer 3: 风险与成交量 (保留 top 1)
    selected_factors['layer3'] = selector.select_best_from_layer(df, layer=3, top_k=1)

    # Layer 4: 宏观与相对 (保留 top 2)
    selected_factors['layer4'] = selector.select_best_from_layer(df, layer=4, top_k=2)

    # 5. 总结
    print(f"\n{'='*80}")
    print("筛选结果总结")
    print(f"{'='*80}")

    all_selected = []
    for layer_name, factors in selected_factors.items():
        print(f"\n  {layer_name}: {factors}")
        all_selected.extend(factors)

    print(f"\n  总计: {len(all_selected)} 个因子")
    print(f"  因子列表: {all_selected}")

    # 6. 验证层间相关性
    print(f"\n{'='*80}")
    print("层间相关性验证")
    print(f"{'='*80}")

    corr_matrix = df[all_selected].corr()
    print("\n相关性矩阵:")
    print(corr_matrix.to_string())

    # 检查是否满足 < 0.5 的要求
    max_corr = 0.0
    for i, f1 in enumerate(all_selected):
        for j, f2 in enumerate(all_selected):
            if i < j:
                corr_val = abs(corr_matrix.loc[f1, f2])
                if corr_val > max_corr:
                    max_corr = corr_val

    print(f"\n  最大层间相关性: {max_corr:.4f}")
    if max_corr < 0.5:
        print("  [OK] 满足相关性要求 (<0.5)")
    else:
        print(f"  [X] 超过相关性阈值 (>0.5)")

    print("\n" + "="*80)
    print("Phase 1 筛选实验完成！")
    print("="*80)

    return selected_factors, all_selected


if __name__ == "__main__":
    selected_factors, all_selected = run_phase1_selection()
