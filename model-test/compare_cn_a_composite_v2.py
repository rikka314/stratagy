#!/usr/bin/env python3
"""
CN_A Composite Phase 6: 统一比较（使用 fold_summary）

从 Phase 4 已有的 fold_summary 数据进行比较：
- baseline_fold_summary.csv (sm, fsm, cash)
- composite_fold_summary.csv (composite_only)

Usage:
    python model-test/compare_cn_a_composite_v2.py \\
      --config model-test/configs/composite_cn_a.json
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np

# Add model-test to path
sys.path.insert(0, str(Path(__file__).parent))


def load_config(config_path: Path) -> dict:
    """加载配置文件"""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def get_model_category(model_name: str) -> str:
    """获取模型分类"""
    categories = {
        "基础策略": ["sm", "fsm"],
        "课程基线": ["naive", "drift", "cash"],
        "新因子主模型": ["composite_only"],
    }

    for category, models in categories.items():
        if model_name in models:
            return category

    return "未分类"


def main() -> int:
    """Main entry point"""
    # Fix Windows console encoding
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="CN_A Composite Phase 6: 统一比较",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to composite_cn_a.json config",
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
        print(f"[Error] Config market must be CN_A, got {market}")
        return 1

    universe = config.get("universe", "unknown")
    print(f"   Market: {market}")
    print(f"   Universe: {universe}")

    # 设置目录
    model_test_dir = Path(__file__).parent
    outputs_dir = model_test_dir / "outputs"
    composite_dir = outputs_dir / config.get("output_subdir", "composite_cn_a")
    comparison_dir = outputs_dir / args.output_subdir

    print(f"\n[Dir] Directories:")
    print(f"   Source: {composite_dir}")
    print(f"   Output: {comparison_dir}")

    # 加载 baseline_fold_summary
    print("\n" + "=" * 80)
    print("Phase 6.1: 加载 Baseline Fold Summary")
    print("=" * 80)

    baseline_file = composite_dir / "baseline_fold_summary.csv"
    if not baseline_file.exists():
        print(f"[Error] File not found: {baseline_file}")
        return 1

    baseline_df = pd.read_csv(baseline_file)
    print(f"[OK] Loaded baseline: {len(baseline_df)} rows")
    print(f"   Strategies: {baseline_df['strategy'].unique().tolist()}")
    print(f"   Folds: {baseline_df['fold_id'].unique().tolist()}")

    # 加载 composite_fold_summary
    print("\n" + "=" * 80)
    print("Phase 6.2: 加载 Composite Fold Summary")
    print("=" * 80)

    composite_file = composite_dir / "composite_fold_summary.csv"
    if not composite_file.exists():
        print(f"[Error] File not found: {composite_file}")
        return 1

    composite_df = pd.read_csv(composite_file)
    print(f"[OK] Loaded composite: {len(composite_df)} rows")
    print(f"   Folds: {composite_df['fold_id'].unique().tolist()}")

    # 合并数据
    print("\n" + "=" * 80)
    print("Phase 6.3: 合并数据")
    print("=" * 80)

    combined_df = pd.concat([baseline_df, composite_df], ignore_index=True)
    print(f"[OK] Combined: {len(combined_df)} rows")
    print(f"   Strategies: {sorted(combined_df['strategy'].unique())}")

    # 保存 fold-level 比较
    comparison_dir.mkdir(parents=True, exist_ok=True)
    fold_metrics_file = comparison_dir / "comparison_fold_metrics.csv"
    combined_df.to_csv(fold_metrics_file, index=False, float_format="%.6f")
    print(f"[OK] Saved fold metrics: {fold_metrics_file}")

    # 聚合到模型级别
    print("\n" + "=" * 80)
    print("Phase 6.4: 聚合模型级别指标")
    print("=" * 80)

    agg_rows = []
    for strategy in combined_df["strategy"].unique():
        strategy_df = combined_df[combined_df["strategy"] == strategy]

        agg_rows.append({
            "model_name": strategy,
            "category": get_model_category(strategy),
            "n_folds": len(strategy_df),
            "sharpe_mean": strategy_df["sharpe_ratio"].mean(),
            "sharpe_std": strategy_df["sharpe_ratio"].std(ddof=1),
            "sharpe_min": strategy_df["sharpe_ratio"].min(),
            "sharpe_max": strategy_df["sharpe_ratio"].max(),
            "return_mean": strategy_df["total_return"].mean(),
            "return_std": strategy_df["total_return"].std(ddof=1),
            "drawdown_mean": strategy_df["max_drawdown"].mean(),
            "drawdown_worst": strategy_df["max_drawdown"].min(),
            "turnover_mean": strategy_df.get("avg_turnover", pd.Series([0])).mean(),
            "folds_positive_sharpe": (strategy_df["sharpe_ratio"] > 0).sum(),
            "folds_sharpe_above_03": (strategy_df["sharpe_ratio"] >= 0.3).sum(),
        })

    agg_df = pd.DataFrame(agg_rows)
    agg_df = agg_df.sort_values("sharpe_mean", ascending=False)

    # 保存聚合指标
    model_metrics_file = comparison_dir / "comparison_metrics.csv"
    agg_df.to_csv(model_metrics_file, index=False, float_format="%.6f")
    print(f"[OK] Saved model metrics: {model_metrics_file}")

    # 生成 Markdown 报告
    print("\n" + "=" * 80)
    print("Phase 6.5: 生成 Markdown 报告")
    print("=" * 80)

    report_file = comparison_dir / "comparison_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# CN_A Composite 统一比较报告\n\n")
        f.write("## 1. 执行摘要\n\n")
        f.write(f"- 比较模型数量: {len(agg_df)}\n")
        f.write(f"- Fold 数量: {len(combined_df['fold_id'].unique())}\n")
        f.write(f"- 市场: CN_A\n")
        f.write(f"- Universe: {universe}\n")
        f.write(f"- Horizon: 20 trading days\n")
        f.write(f"- 执行成本: 3 bps commission + 5 bps slippage\n\n")

        f.write("## 2. 模型排名（按 Sharpe 均值）\n\n")
        f.write("| 排名 | 模型 | 分类 | Sharpe 均值 | Sharpe 标准差 | 收益均值 | 最大回撤均值 |\n")
        f.write("|------|------|------|-------------|---------------|----------|-------------|\n")

        for rank, row in enumerate(agg_df.itertuples(), start=1):
            f.write(
                f"| {rank} | {row.model_name} | {row.category} | "
                f"{row.sharpe_mean:.4f} | {row.sharpe_std:.4f} | "
                f"{row.return_mean:.4f} | {row.drawdown_mean:.4f} |\n"
            )

        f.write("\n## 3. Fold 一致性分析\n\n")
        f.write("| 模型 | Fold 数量 | Sharpe>0 | Sharpe≥0.3 | 一致性比例 |\n")
        f.write("|------|-----------|----------|------------|------------|\n")

        for row in agg_df.itertuples():
            consistency = row.folds_sharpe_above_03 / row.n_folds if row.n_folds > 0 else 0.0
            f.write(
                f"| {row.model_name} | {row.n_folds} | "
                f"{row.folds_positive_sharpe} | {row.folds_sharpe_above_03} | "
                f"{consistency:.1%} |\n"
            )

        f.write("\n## 4. 关键发现\n\n")

        # 找出最优模型
        best_model = agg_df.iloc[0]
        f.write(f"**最优模型**: {best_model['model_name']} ({best_model['category']})\n\n")
        f.write(f"- Sharpe 均值: {best_model['sharpe_mean']:.4f} ± {best_model['sharpe_std']:.4f}\n")
        f.write(f"- 总收益均值: {best_model['return_mean']:.4f}\n")
        f.write(f"- 最大回撤均值: {best_model['drawdown_mean']:.4f}\n\n")

        # Composite vs Baseline
        composite_row = agg_df[agg_df["model_name"] == "composite_only"]
        if not composite_row.empty:
            composite_sharpe = composite_row.iloc[0]["sharpe_mean"]

            sm_row = agg_df[agg_df["model_name"] == "sm"]
            fsm_row = agg_df[agg_df["model_name"] == "fsm"]

            if not sm_row.empty:
                sm_sharpe = sm_row.iloc[0]["sharpe_mean"]
                improvement_sm = (composite_sharpe - sm_sharpe) / abs(sm_sharpe) if sm_sharpe != 0 else 0
                f.write(f"**Composite vs SM**: Sharpe {composite_sharpe:.4f} vs {sm_sharpe:.4f} "
                       f"({improvement_sm:+.1%})\n\n")

            if not fsm_row.empty:
                fsm_sharpe = fsm_row.iloc[0]["sharpe_mean"]
                improvement_fsm = (composite_sharpe - fsm_sharpe) / abs(fsm_sharpe) if fsm_sharpe != 0 else 0
                f.write(f"**Composite vs FSM**: Sharpe {composite_sharpe:.4f} vs {fsm_sharpe:.4f} "
                       f"({improvement_fsm:+.1%})\n\n")

        f.write("## 5. 结论与建议\n\n")
        f.write("### 5.1 准入状态\n\n")

        # 判断 Composite 准入
        composite_row = agg_df[agg_df["model_name"] == "composite_only"]
        if not composite_row.empty:
            composite_data = composite_row.iloc[0]
            sm_row = agg_df[agg_df["model_name"] == "sm"]
            fsm_row = agg_df[agg_df["model_name"] == "fsm"]

            passed = False
            if not sm_row.empty and not fsm_row.empty:
                sm_sharpe = sm_row.iloc[0]["sharpe_mean"]
                fsm_sharpe = fsm_row.iloc[0]["sharpe_mean"]
                baseline_sharpe = max(sm_sharpe, fsm_sharpe)

                if composite_data["sharpe_mean"] > baseline_sharpe:
                    consistency = composite_data["folds_sharpe_above_03"] / composite_data["n_folds"]
                    if consistency >= 0.75:  # 3/4 folds
                        f.write("- ✅ **Composite PASSED**: 优于 baseline 且 fold consistency ≥75%\n")
                        passed = True
                    else:
                        f.write(f"- ⚠️ **Composite 未通过**: fold consistency {consistency:.1%} < 75%\n")
                else:
                    f.write("- ⚠️ **Composite 未通过**: Sharpe 未优于 baseline\n")

            if passed:
                f.write("- 建议：考虑 Phase 7 production review\n\n")
            else:
                f.write("- 建议：保持现有策略或进一步优化\n\n")

        f.write("### 5.2 下一步\n\n")
        f.write("- 本次比较基于相同的 market/universe/fold/horizon/execution config\n")
        f.write("- 结果为 research-only，不代表生产就绪\n")
        f.write("- 若 Composite 通过，可考虑接入 Streamlit read-only 展示\n")
        f.write("- 不得自动修改生产默认策略\n")
        f.write("- 跨市场结论需独立验证，不得外推\n")

    print(f"[OK] Report saved: {report_file}")

    # 生成 manifest
    print("\n" + "=" * 80)
    print("Phase 6.6: 生成 Manifest")
    print("=" * 80)

    manifest = {
        "phase": "phase6_comparison",
        "market": market,
        "universe": universe,
        "n_strategies": len(combined_df["strategy"].unique()),
        "n_folds": len(combined_df["fold_id"].unique()),
        "strategies": sorted(combined_df["strategy"].unique()),
        "folds": sorted(combined_df["fold_id"].unique()),
        "config_path": str(args.config),
        "output_dir": str(comparison_dir),
        "status": "ready",
    }

    manifest_file = comparison_dir / "comparison_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[OK] Manifest saved: {manifest_file}")

    # 输出摘要
    print("\n" + "=" * 80)
    print("Phase 6 完成摘要")
    print("=" * 80)

    print(f"\n[Metrics] 比较统计:")
    print(f"   - 模型数量: {len(combined_df['strategy'].unique())}")
    print(f"   - Fold 数量: {len(combined_df['fold_id'].unique())}")
    print(f"   - 总行数: {len(combined_df)}")

    print(f"\n[Output] 输出文件:")
    print(f"   - {comparison_dir / 'comparison_fold_metrics.csv'}")
    print(f"   - {comparison_dir / 'comparison_metrics.csv'}")
    print(f"   - {comparison_dir / 'comparison_report.md'}")
    print(f"   - {comparison_dir / 'comparison_manifest.json'}")

    # 显示排名
    print(f"\n[Ranking] 模型排名（按 Sharpe 均值）:")
    for rank, row in enumerate(agg_df.itertuples(), start=1):
        print(f"   {rank}. {row.model_name}: Sharpe={row.sharpe_mean:.4f}")

    print("\n" + "=" * 80)
    print("[OK] Phase 6 完成")
    print("=" * 80)
    print("\n下一步:")
    print("  1. 查看 comparison_report.md 了解详细分析")
    print("  2. 检查 Composite 准入状态")
    print("  3. 若通过，考虑 Phase 7 production review")
    print("  4. 更新 AI_CONTEXT.md 记录 Phase 6 完成状态")

    return 0


if __name__ == "__main__":
    sys.exit(main())
