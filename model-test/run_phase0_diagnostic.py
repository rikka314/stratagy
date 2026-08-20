"""Phase 0: 前置验证 - 确认是否需要重构

目标:
1. 评估 adaptive_router_v1 基线性能
2. 审计专家同质性
3. 决定是否继续重构

执行: python model-test/run_phase0_diagnostic.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import json
from datetime import datetime

# 尝试导入 seaborn，如果不存在则使用 matplotlib
try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False
    print("Warning: seaborn not installed, using matplotlib fallback")


def analyze_adaptive_router_baseline():
    """P0.1: Adaptive Router 性能基准"""

    print("=" * 80)
    print("Phase 0.1: Adaptive Router Baseline Performance")
    print("=" * 80)

    # 读取 US 市场的 model summary
    us_path = Path("model-test/outputs/full_us_deans_60/model_summary.csv")

    if not us_path.exists():
        print(f"ERROR Error: {us_path} not found")
        return None

    df = pd.read_csv(us_path)

    # 筛选核心专家
    core_experts = [
        'naive', 'drift',
        'sm_bayesian', 'sm_genetic', 'sm_random',
        'fsm_bayesian', 'fsm_genetic', 'fsm_random',
        'adaptive_router_v1', 'rsm_adaptive_v1',
        'cash'
    ]

    # 实际存在的专家（可能名称略有不同）
    available = df[df['model_id'].str.contains('|'.join([
        'naive', 'drift', 'sm_', 'fsm_', 'adaptive', 'cash'
    ]), case=False, na=False)]

    print(f"\n找到 {len(available)} 个相关专家:")
    print(available[['model_id', 'median_sharpe', 'median_annret', 'median_maxdd', 'success_rate']].to_string(index=False))

    # 重点关注 adaptive_router
    adaptive = df[df['model_id'].str.contains('adaptive', case=False, na=False)]

    if len(adaptive) == 0:
        print("\nWARN  Warning: No adaptive_router found in results")
        print("   Using rsm_adaptive_v1 as proxy")
        adaptive = df[df['model_id'] == 'rsm_adaptive_v1']

    if len(adaptive) > 0:
        print("\n" + "=" * 80)
        print("Adaptive Router Performance:")
        print("=" * 80)

        for _, row in adaptive.iterrows():
            model_id = row['model_id']
            sharpe = row['median_sharpe']
            annret = row['median_annret']
            maxdd = row['median_maxdd']
            success_rate = row['success_rate']

            print(f"\nModel: {model_id}")
            print(f"  Sharpe Ratio:    {sharpe:.3f}  {'PASS' if sharpe > 0.5 else 'FAIL'} (target > 0.5)")
            print(f"  Annual Return:   {annret:.1%}")
            print(f"  Max Drawdown:    {maxdd:.1%}  {'PASS' if maxdd > -0.15 else 'FAIL'} (target > -15%)")
            print(f"  Success Rate:    {success_rate:.1%}")

            # 计算通过项数
            gates_passed = 0
            gates_passed += 1 if sharpe > 0.5 else 0
            gates_passed += 1 if maxdd > -0.15 else 0
            gates_passed += 1 if success_rate > 0.55 else 0

            print(f"\n  Gates Passed: {gates_passed}/3")

            # P0.1 决策
            print("\n" + "-" * 80)
            print("P0.1 Decision:")
            if gates_passed >= 3:
                print("  PASS STOP - Adaptive router is already good enough")
                decision = "STOP"
            elif gates_passed >= 2:
                print("  -> PROCEED to Phase 1 (incremental improvement)")
                decision = "PHASE_1"
            else:
                print("  -> PROCEED to Phase 1-2 (full reconstruction needed)")
                decision = "PHASE_1_2"

            # 保存结果
            result = {
                "model_id": model_id,
                "sharpe": float(sharpe),
                "annret": float(annret),
                "maxdd": float(maxdd),
                "success_rate": float(success_rate),
                "gates_passed": int(gates_passed),
                "decision": decision,
                "timestamp": datetime.now().isoformat()
            }

            output_path = Path("model-test/outputs/phase0_diagnostic/adaptive_router_baseline.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)

            print(f"\nPASS Saved to: {output_path}")

            return result, available

    return None, available


def analyze_expert_correlation(available_df):
    """P0.2: 专家同质性审计

    注意: 由于没有 daily return 数据，我们使用聚合指标作为代理
    """

    print("\n" + "=" * 80)
    print("Phase 0.2: Expert Homogeneity Audit")
    print("=" * 80)

    print("\n注意: 使用聚合指标作为同质性代理")
    print("(理想情况下应该用 daily returns 计算相关性)")

    # 选择技术策略专家
    tech_experts = available_df[
        available_df['model_id'].str.contains('sm_|fsm_', case=False, na=False) &
        ~available_df['model_id'].str.contains('ml_', case=False, na=False)
    ].copy()

    if len(tech_experts) < 2:
        print("\nERROR Not enough experts for correlation analysis")
        return None

    print(f"\n分析 {len(tech_experts)} 个技术策略专家:")
    print(tech_experts['model_id'].tolist())

    # 使用多个维度的聚合指标
    features = tech_experts[['median_annret', 'median_sharpe', 'median_maxdd']].values
    feature_names = tech_experts['model_id'].values

    # 计算相关性（使用归一化的特征）
    # StandardScaler 等效实现
    features_mean = features.mean(axis=0)
    features_std = features.std(axis=0)
    features_scaled = (features - features_mean) / (features_std + 1e-8)

    # 计算余弦相似度作为相关性代理
    # cosine_similarity 等效实现
    norms = np.linalg.norm(features_scaled, axis=1, keepdims=True)
    features_normalized = features_scaled / (norms + 1e-8)
    similarity_matrix = features_normalized @ features_normalized.T

    # 转换为 DataFrame
    corr_df = pd.DataFrame(
        similarity_matrix,
        index=feature_names,
        columns=feature_names
    )

    # 可视化
    plt.figure(figsize=(12, 10))

    if HAS_SEABORN:
        import seaborn as sns
        sns.heatmap(
            corr_df,
            annot=True,
            fmt='.2f',
            cmap='RdBu_r',
            vmin=-1, vmax=1,
            center=0,
            square=True,
            cbar_kws={"shrink": 0.8}
        )
    else:
        # Matplotlib fallback
        im = plt.imshow(similarity_matrix, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
        plt.colorbar(im, shrink=0.8)
        plt.xticks(range(len(feature_names)), feature_names, rotation=45, ha='right')
        plt.yticks(range(len(feature_names)), feature_names)

        # Add text annotations
        for i in range(len(feature_names)):
            for j in range(len(feature_names)):
                text = plt.text(j, i, f'{similarity_matrix[i, j]:.2f}',
                               ha="center", va="center", color="black", fontsize=9)

    plt.title('Expert Similarity (based on aggregate metrics)\nNote: Not as reliable as daily return correlation',
              fontsize=14)
    plt.tight_layout()

    output_path = Path("model-test/outputs/phase0_diagnostic/expert_similarity.png")
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nPASS Saved heatmap: {output_path}")
    plt.close()

    # 统计分析
    upper_triangle = np.triu(similarity_matrix, k=1)
    upper_values = upper_triangle[upper_triangle != 0]

    avg_similarity = upper_values.mean()
    max_similarity = upper_values.max()
    high_similarity_count = (upper_values > 0.8).sum()

    print("\n" + "=" * 80)
    print("Similarity Analysis (Aggregate Metrics Proxy):")
    print("=" * 80)
    print(f"  Average pairwise similarity: {avg_similarity:.3f}")
    print(f"  Maximum similarity:          {max_similarity:.3f}")
    print(f"  High similarity pairs (>0.8): {high_similarity_count}")

    # 识别高度相似的专家对
    if high_similarity_count > 0:
        print("\n  High similarity pairs:")
        for i in range(len(feature_names)):
            for j in range(i+1, len(feature_names)):
                if similarity_matrix[i, j] > 0.8:
                    print(f"    {feature_names[i]} <-> {feature_names[j]}: {similarity_matrix[i, j]:.3f}")

    # P0.2 决策
    print("\n" + "-" * 80)
    print("P0.2 Decision:")

    homogeneity_issue = False
    if avg_similarity > 0.7:  # 更宽松的阈值（因为用的是代理指标）
        print("  WARN  WARN: Average similarity > 0.7 (potential homogeneity)")
        homogeneity_issue = True
    if high_similarity_count > 3:
        print("  WARN  WARN: Multiple high-similarity pairs found")
        homogeneity_issue = True

    if not homogeneity_issue:
        print("  PASS Experts show reasonable diversity in aggregate metrics")
    else:
        print("  -> Suggests expert homogeneity problem")
        print("  -> Recommend Phase 2 (diversified expert pool)")

    # 保存结果
    result = {
        "num_experts": int(len(tech_experts)),
        "avg_similarity": float(avg_similarity),
        "max_similarity": float(max_similarity),
        "high_similarity_count": int(high_similarity_count),
        "homogeneity_issue": bool(homogeneity_issue),
        "expert_list": tech_experts['model_id'].tolist(),
        "note": "Using aggregate metrics as proxy; daily return correlation would be more reliable",
        "timestamp": datetime.now().isoformat()
    }

    output_path = Path("model-test/outputs/phase0_diagnostic/expert_similarity.json")
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\nPASS Saved to: {output_path}")

    corr_df.to_csv("model-test/outputs/phase0_diagnostic/expert_similarity.csv")

    return result


def generate_phase0_report(baseline_result, similarity_result):
    """生成 Phase 0 最终报告"""

    print("\n" + "=" * 80)
    print("PHASE 0 FINAL REPORT")
    print("=" * 80)

    report_lines = []
    report_lines.append("# Phase 0 Diagnostic Report")
    report_lines.append(f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("\n---\n")

    report_lines.append("## P0.1: Adaptive Router Baseline\n")

    if baseline_result:
        report_lines.append(f"**Model**: {baseline_result['model_id']}\n")
        report_lines.append("| Metric | Value | Target | Pass |")
        report_lines.append("|--------|-------|--------|------|")
        report_lines.append(f"| Sharpe Ratio | {baseline_result['sharpe']:.3f} | > 0.5 | {'PASS' if baseline_result['sharpe'] > 0.5 else 'FAIL'} |")
        report_lines.append(f"| Max Drawdown | {baseline_result['maxdd']:.1%} | > -15% | {'PASS' if baseline_result['maxdd'] > -0.15 else 'FAIL'} |")
        report_lines.append(f"| Success Rate | {baseline_result['success_rate']:.1%} | > 55% | {'PASS' if baseline_result['success_rate'] > 0.55 else 'FAIL'} |")
        report_lines.append(f"\n**Gates Passed**: {baseline_result['gates_passed']}/3")
        report_lines.append(f"\n**P0.1 Decision**: `{baseline_result['decision']}`")
    else:
        report_lines.append("ERROR No adaptive router data available")

    report_lines.append("\n---\n")
    report_lines.append("## P0.2: Expert Homogeneity Audit\n")

    if similarity_result:
        report_lines.append(f"**Number of Experts Analyzed**: {similarity_result['num_experts']}\n")
        report_lines.append(f"**Average Similarity**: {similarity_result['avg_similarity']:.3f}")
        report_lines.append(f"**Maximum Similarity**: {similarity_result['max_similarity']:.3f}")
        report_lines.append(f"**High Similarity Pairs (>0.8)**: {similarity_result['high_similarity_count']}")
        report_lines.append(f"\n**Homogeneity Issue**: {'Yes WARN' if similarity_result['homogeneity_issue'] else 'No PASS'}")
        report_lines.append(f"\n*Note*: {similarity_result['note']}")

        report_lines.append("\n**Experts Analyzed**:")
        for expert in similarity_result['expert_list']:
            report_lines.append(f"- {expert}")
    else:
        report_lines.append("ERROR Not enough data for correlation analysis")

    report_lines.append("\n---\n")
    report_lines.append("## Final Decision\n")

    # 综合决策
    if baseline_result and similarity_result:
        baseline_decision = baseline_result['decision']
        has_homogeneity = similarity_result['homogeneity_issue']

        if baseline_decision == "STOP" and not has_homogeneity:
            final_decision = "**STOP** - No reconstruction needed"
            next_steps = "- Adaptive router is sufficient\n- Focus on other improvements"
        elif baseline_decision == "PHASE_1" and not has_homogeneity:
            final_decision = "**PROCEED to Phase 1** - Incremental improvement"
            next_steps = "- Add macro features (VIX, market breadth, etc.)\n- Extend horizon to 20 days\n- Keep existing expert pool"
        else:
            final_decision = "**PROCEED to Phase 1-2** - Full reconstruction"
            next_steps = "- Phase 1: Add macro features + extend horizon\n- Phase 2: Build diversified expert pool\n- Address homogeneity problem"

        report_lines.append(f"### {final_decision}\n")
        report_lines.append("**Rationale**:")
        report_lines.append(f"- Baseline performance: {baseline_result['gates_passed']}/3 gates passed")
        report_lines.append(f"- Expert diversity: {'Issue detected' if has_homogeneity else 'Acceptable'}")

        report_lines.append("\n**Next Steps**:")
        report_lines.append(next_steps)

    report_lines.append("\n---\n")
    report_lines.append("## Artifacts\n")
    report_lines.append("- `adaptive_router_baseline.json` - Performance metrics")
    report_lines.append("- `expert_similarity.json` - Correlation analysis")
    report_lines.append("- `expert_similarity.png` - Similarity heatmap")
    report_lines.append("- `expert_similarity.csv` - Similarity matrix")

    # 保存报告
    report_text = "\n".join(report_lines)

    output_path = Path("document/phase0_reports/phase0_diagnostic_report.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    print(report_text)
    print(f"\nPASS Full report saved to: {output_path}")

    return report_text


def main():
    """执行 Phase 0 诊断"""

    print("\n" + "╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "PHASE 0: 前置验证" + " " * 38 + "║")
    print("║" + " " * 15 + "Expert System Reconstruction" + " " * 33 + "║")
    print("╚" + "=" * 78 + "╝\n")

    # P0.1: Adaptive Router 基线
    baseline_result, available_experts = analyze_adaptive_router_baseline()

    # P0.2: 专家同质性
    if available_experts is not None and len(available_experts) > 0:
        similarity_result = analyze_expert_correlation(available_experts)
    else:
        similarity_result = None

    # 生成最终报告
    generate_phase0_report(baseline_result, similarity_result)

    print("\n" + "=" * 80)
    print("Phase 0 诊断完成!")
    print("=" * 80)
    print("\n查看完整报告: document/phase0_reports/phase0_diagnostic_report.md")
    print("查看诊断数据: model-test/outputs/phase0_diagnostic/")


if __name__ == "__main__":
    main()
