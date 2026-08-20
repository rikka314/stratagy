"""
宏观数据下载脚本
================
用于 Phase 1 的宏观特征工程

下载内容：
- VIX (^VIX): 市场波动率指数
- SPY: S&P 500 ETF
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.macro_factors import download_macro_data


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1: 宏观数据下载")
    print("=" * 60)

    # 下载 2015-2026 的数据（覆盖所有回测窗口）
    vix, spy = download_macro_data(
        start_date="2015-01-01",
        end_date="2026-08-20"
    )

    print("\n数据统计:")
    print(f"- VIX 日期范围: {vix.index.min()} 到 {vix.index.max()}")
    print(f"- SPY 日期范围: {spy.index.min()} 到 {spy.index.max()}")
    print(f"- VIX 数据点数: {len(vix)}")
    print(f"- SPY 数据点数: {len(spy)}")

    # 显示最近 5 天的数据作为验证
    print("\nVIX 最近 5 天:")
    print(vix.tail())

    print("\nSPY 最近 5 天:")
    print(spy.tail())

    print("\n✅ 宏观数据下载完成!")
