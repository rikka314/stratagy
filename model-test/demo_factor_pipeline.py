"""因子计算演示脚本

展示如何使用 FactorPipeline 计算四层因子
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from core.factor_pipeline import FactorPipeline, compute_all_factors


def demo_factor_computation():
    """演示因子计算流程"""
    print("=" * 80)
    print("因子计算 Pipeline 演示 - Phase 1")
    print("=" * 80)

    # 1. 初始化 pipeline
    print("\n[步骤 1] 初始化 FactorPipeline...")
    pipeline = FactorPipeline()

    # 2. 展示因子架构
    print("\n[步骤 2] 四层因子架构:")
    all_factors = pipeline.get_all_factors()
    for layer_name, factors in all_factors.items():
        print(f"\n  {layer_name}:")
        for factor in factors:
            print(f"    - {factor}")

    total_factors = sum(len(f) for f in all_factors.values())
    print(f"\n  总计: {total_factors} 个因子")

    # 3. 创建示例数据
    print("\n[步骤 3] 创建示例数据 (AAPL, 2020-01-01 到 2020-12-31)...")
    dates = pd.date_range('2020-01-01', '2020-12-31', freq='B')

    # 模拟真实股价走势
    np.random.seed(42)
    n_days = len(dates)
    close_prices = 100 * np.exp(np.random.randn(n_days).cumsum() * 0.02)

    df = pd.DataFrame({
        'date': dates,
        'open': close_prices * (1 + np.random.randn(n_days) * 0.01),
        'high': close_prices * (1 + np.abs(np.random.randn(n_days)) * 0.015),
        'low': close_prices * (1 - np.abs(np.random.randn(n_days)) * 0.015),
        'close': close_prices,
        'volume': 50000000 + np.random.randint(-10000000, 10000000, n_days),
    })

    print(f"  数据行数: {len(df)}")
    print(f"  日期范围: {df['date'].min()} 到 {df['date'].max()}")
    print(f"  价格范围: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

    # 4. 计算所有因子
    print("\n[步骤 4] 计算所有四层因子...")
    result = compute_all_factors(df, symbol='AAPL')

    print(f"  输入列数: {len(df.columns)}")
    print(f"  输出列数: {len(result.columns)}")
    print(f"  新增因子数: {len(result.columns) - len(df.columns)}")

    # 5. 验证因子质量
    print("\n[步骤 5] 验证因子质量...")

    # Layer 1: 趋势动量
    layer1_factors = pipeline.get_layer_factors(1)
    print(f"\n  Layer 1 (趋势动量) - {len(layer1_factors)} 个因子:")
    for factor in layer1_factors:
        valid_count = result[factor].notna().sum()
        mean_val = result[factor].mean()
        std_val = result[factor].std()
        print(f"    {factor:20s}: 有效值={valid_count:3d}, 均值={mean_val:7.3f}, 标准差={std_val:6.3f}")

    # Layer 2: 均值回归
    layer2_factors = pipeline.get_layer_factors(2)
    print(f"\n  Layer 2 (均值回归) - {len(layer2_factors)} 个因子:")
    for factor in layer2_factors:
        valid_count = result[factor].notna().sum()
        mean_val = result[factor].mean()
        std_val = result[factor].std()
        print(f"    {factor:20s}: 有效值={valid_count:3d}, 均值={mean_val:7.3f}, 标准差={std_val:6.3f}")

    # Layer 3: 风险与成交量
    layer3_factors = pipeline.get_layer_factors(3)
    print(f"\n  Layer 3 (风险与成交量) - {len(layer3_factors)} 个因子:")
    for factor in layer3_factors:
        valid_count = result[factor].notna().sum()
        mean_val = result[factor].mean()
        std_val = result[factor].std()
        print(f"    {factor:20s}: 有效值={valid_count:3d}, 均值={mean_val:7.3f}, 标准差={std_val:6.3f}")

    # Layer 4: 宏观与相对
    layer4_factors = pipeline.get_layer_factors(4)
    print(f"\n  Layer 4 (宏观与相对) - {len(layer4_factors)} 个因子:")
    for factor in layer4_factors:
        valid_count = result[factor].notna().sum()
        if valid_count > 0:
            mean_val = result[factor].mean()
            std_val = result[factor].std()
            print(f"    {factor:20s}: 有效值={valid_count:3d}, 均值={mean_val:7.3f}, 标准差={std_val:6.3f}")
        else:
            print(f"    {factor:20s}: 有效值={valid_count:3d} (全部缺失)")

    # 6. 展示样例数据
    print("\n[步骤 6] 展示因子样例 (最后10行):")
    display_cols = ['date', 'close', 'mom_short_z', 'rsi_z', 'vol_z', 'vix_level', 'rel_strength_spy']
    print(result[display_cols].tail(10).to_string(index=False))

    # 7. 因子相关性分析
    print("\n[步骤 7] 层间相关性分析:")

    # 计算每层的代表因子相关性
    layer_representatives = {
        'Layer1': 'mom_short_z',
        'Layer2': 'rsi_z',
        'Layer3': 'vol_z',
        'Layer4': 'vix_level',
    }

    corr_matrix = result[[f for f in layer_representatives.values()]].corr()
    print("\n  层间相关性矩阵 (代表因子):")
    print(corr_matrix.to_string())

    # 8. 保存结果
    print("\n[步骤 8] 保存结果...")
    output_path = Path("data/demo_factors_output.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path, index=False)
    print(f"  结果已保存到: {output_path}")

    print("\n" + "=" * 80)
    print("演示完成！")
    print("=" * 80)

    return result


if __name__ == "__main__":
    result = demo_factor_computation()
