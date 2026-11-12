#!/usr/bin/env python3
"""
CN_A Composite Phase 6: 统一比较

将新 CN_A Composite 与既有 CN_A 模型进行同口径比较：
- 基础策略: sm, fsm
- 课程基线: naive, drift, cash
- 既有组合: best_single_expert, equal_weight_experts
- 既有路由: adaptive_router_v1
- 新因子主模型: composite_only
- 新 advisory: composite_plus_*

所有模型使用相同的：
- market = CN_A
- frozen universe
- fold boundaries
- primary horizon = 20 trading days
- execution config = 3 + 5 bps

Usage:
    python model-test/compare_cn_a_composite.py \\
      --config model-test/configs/composite_cn_a.json \\
      [--advisory-config model-test/configs/composite_advisory_cn_a.json]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Add model-test to path
sys.path.insert(0, str(Path(__file__).parent))

from model_test.cn_a_comparison import (
    COMPARISON_CATEGORIES,
    ComparisonMetrics,
    compute_fold_metrics,
    generate_comparison_report,
    load_advisory_results,
    load_baseline_results,
    load_composite_results,
)


def load_config(config_path: Path) -> dict[str, Any]:
    """加载配置文件"""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    return config


def get_model_category(model_name: str) -> str:
    """获取模型分类"""
    for category in COMPARISON_CATEGORIES:
        if model_name in category.models:
            return category.name

    return "未分类"


def main() -> int:
    """Main entry point"""
    # Fix Windows console encoding
    import sys
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="CN_A Composite Phase 6: 统一比较",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to composite_cn_a.json config",
    )
    parser.add_argument(
        "--advisory-config",
        type=Path,
        help="Path to composite_advisory_cn_a.json config (optional)",
    )
    parser.add_argument(
        "--output-subdir",
        type=str,
        default="cn_a_factor_composite_comparison",
        help="Output subdirectory name",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("CN_A Composite Phase 6: 统一比较")
    print("=" * 80)

    # 加载配置
    print(f"\n[Config] Loading config: {args.config}")
    config = load_config(args.config)

    market = config.get("market", "CN_A")
    if market != "CN_A":
        print(f"[Error] Error: Config market must be CN_A, got {market}")
        return 1

    universe = config.get("universe", "unknown")
    print(f"   Market: {market}")
    print(f"   Universe: {universe}")

    # 设置输出目录
    model_test_dir = Path(__file__).parent
    outputs_dir = model_test_dir / "outputs"
    composite_dir = outputs_dir / config.get("output_subdir", "composite_cn_a")
    comparison_dir = outputs_dir / args.output_subdir

    print(f"\n[Dir] Directories:")
    print(f"   Composite: {composite_dir}")
    print(f"   Comparison: {comparison_dir}")

    # Phase 6.1: 加载 baseline 结果
    print("\n" + "=" * 80)
    print("Phase 6.1: 加载 Baseline 结果")
    print("=" * 80)

    try:
        baseline_df = load_baseline_results(composite_dir)
        print(f"[OK] Loaded baseline results: {len(baseline_df)} rows")
        print(f"   Strategies: {baseline_df['strategy'].unique().tolist()}")
        print(f"   Folds: {baseline_df['fold_id'].unique().tolist()}")
    except Exception as e:
        print(f"[Error] Error loading baseline results: {e}")
        return 1

    # Phase 6.2: 加载 Composite 结果
    print("\n" + "=" * 80)
    print("Phase 6.2: 加载 Composite 结果")
    print("=" * 80)

    try:
        composite_df = load_composite_results(composite_dir)
        print(f"[OK] Loaded composite results: {len(composite_df)} rows")
        print(f"   Folds: {composite_df['fold_id'].unique().tolist()}")
    except Exception as e:
        print(f"[Error] Error loading composite results: {e}")
        return 1

    # Phase 6.3: 加载 Advisory 结果（可选）
    print("\n" + "=" * 80)
    print("Phase 6.3: 加载 Advisory 结果（可选）")
    print("=" * 80)

    advisory_df = None
    if args.advisory_config:
        advisory_config = load_config(args.advisory_config)
        advisory_subdir = advisory_config.get("output_subdir", "composite_advisory_cn_a")
        advisory_dir = outputs_dir / advisory_subdir

        try:
            advisory_df = load_advisory_results(advisory_dir)
            if advisory_df is not None:
                print(f"[OK] Loaded advisory results: {len(advisory_df)} rows")
                print(f"   Policies: {advisory_df['strategy'].unique().tolist()}")
            else:
                print("[Warning] Advisory results not found (Phase 5 未运行)")
        except Exception as e:
            print(f"[Warning] Error loading advisory results: {e}")
            print("   继续使用 baseline + composite only")

    # Phase 6.4: 合并所有结果
    print("\n" + "=" * 80)
    print("Phase 6.4: 合并所有结果")
    print("=" * 80)

    all_dfs = [baseline_df, composite_df]
    if advisory_df is not None:
        all_dfs.append(advisory_df)

    combined_df = pd.concat(all_dfs, ignore_index=True)
    print(f"[OK] Combined results: {len(combined_df)} rows")
    print(f"   Total strategies: {len(combined_df['strategy'].unique())}")
    print(f"   Strategies: {sorted(combined_df['strategy'].unique())}")

    # 保存合并后的 daily 数据
    comparison_dir.mkdir(parents=True, exist_ok=True)
    combined_daily_file = comparison_dir / "comparison_daily.csv"
    combined_df.to_csv(combined_daily_file, index=False, float_format="%.8f")
    print(f"[OK] Saved combined daily: {combined_daily_file}")

    # Phase 6.5: 计算每个模型每个 fold 的指标
    print("\n" + "=" * 80)
    print("Phase 6.5: 计算指标")
    print("=" * 80)

    all_metrics: list[ComparisonMetrics] = []

    for strategy_name in combined_df["strategy"].unique():
        strategy_df = combined_df[combined_df["strategy"] == strategy_name]
        category = get_model_category(strategy_name)

        print(f"\n[Metrics] {strategy_name} ({category})")

        for fold_id in strategy_df["fold_id"].unique():
            fold_df = strategy_df[strategy_df["fold_id"] == fold_id]

            try:
                metrics = compute_fold_metrics(fold_df, strategy_name, fold_id, category)
                all_metrics.append(metrics)

                print(f"   {fold_id}: Sharpe={metrics.sharpe_ratio:.4f}, "
                      f"Return={metrics.total_return:.4f}, "
                      f"DD={metrics.max_drawdown:.4f}")
            except Exception as e:
                print(f"   [Error] Error computing metrics for {fold_id}: {e}")

    print(f"\n[OK] Computed {len(all_metrics)} fold-level metrics")

    # Phase 6.6: 生成比较报告
    print("\n" + "=" * 80)
    print("Phase 6.6: 生成比较报告")
    print("=" * 80)

    try:
        generate_comparison_report(all_metrics, comparison_dir)
        print("[OK] Comparison report generated")
    except Exception as e:
        print(f"[Error] Error generating report: {e}")
        return 1

    # Phase 6.7: 生成 manifest
    print("\n" + "=" * 80)
    print("Phase 6.7: 生成 Manifest")
    print("=" * 80)

    manifest = {
        "phase": "phase6_comparison",
        "market": market,
        "universe": universe,
        "n_strategies": len(combined_df["strategy"].unique()),
        "n_folds": len(combined_df["fold_id"].unique()),
        "n_metrics": len(all_metrics),
        "strategies": sorted(combined_df["strategy"].unique()),
        "folds": sorted(combined_df["fold_id"].unique()),
        "config_path": str(args.config),
        "advisory_config_path": str(args.advisory_config) if args.advisory_config else None,
        "output_dir": str(comparison_dir),
        "status": "ready",
    }

    manifest_file = comparison_dir / "comparison_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[OK] Manifest saved: {manifest_file}")

    # Phase 6.8: 输出摘要
    print("\n" + "=" * 80)
    print("Phase 6 完成摘要")
    print("=" * 80)

    print(f"\n[Metrics] 比较统计:")
    print(f"   - 模型数量: {len(combined_df['strategy'].unique())}")
    print(f"   - Fold 数量: {len(combined_df['fold_id'].unique())}")
    print(f"   - 总行数: {len(combined_df)}")
    print(f"   - 指标计算: {len(all_metrics)} 个 fold-level metrics")

    print(f"\n[Output] 输出文件:")
    print(f"   - {comparison_dir / 'comparison_daily.csv'}")
    print(f"   - {comparison_dir / 'comparison_fold_metrics.csv'}")
    print(f"   - {comparison_dir / 'comparison_metrics.csv'}")
    print(f"   - {comparison_dir / 'comparison_report.md'}")
    print(f"   - {comparison_dir / 'comparison_manifest.json'}")

    print("\n" + "=" * 80)
    print("[OK] Phase 6 完成")
    print("=" * 80)
    print("\n下一步:")
    print("  1. 查看 comparison_report.md 了解模型排名")
    print("  2. 检查 Composite 是否优于 SM/FSM baseline")
    print("  3. 若通过，考虑 Phase 7 production review")
    print("  4. 更新 AI_CONTEXT.md 记录 Phase 6 完成状态")

    return 0


if __name__ == "__main__":
    sys.exit(main())
