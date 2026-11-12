"""Phase 2.5: 深入优化

改进点:
1. 扩大 Grid Search 范围 ([-2, 2])，允许负权重
2. 运行 Bayesian Optimization (已安装依赖)
3. 改进评估函数 (完整回测)
4. 添加交互项测试
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import itertools
import json
from datetime import datetime

# Phase 2 筛选后的 5 个因子
SELECTED_FACTORS = [
    "mom_short_z",
    "rsi_z",
    "macd_z",
    "vix_level",
    "volume_ratio_rank",
]


class AdvancedOptimizer:
    """改进的因子权重优化器"""

    def __init__(self, output_dir: str = "model-test/outputs/phase2_5_advanced_optimization"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.results = {
            "expanded_grid_search": {},
            "bayesian_opt": {},
            "interaction_test": {},
        }

    def stage1_expanded_grid_search(
        self,
        df: pd.DataFrame,
        grid_values: List[float] = [-2.0, -1.0, 0.0, 1.0, 2.0]
    ) -> Dict:
        """
        Stage 1: 扩展 Grid Search

        改进: 允许负权重，扩大搜索范围
        """
        print("=" * 60)
        print("Stage 1: Expanded Grid Search (负权重 + 更大范围)")
        print("=" * 60)

        # 使用更大范围的 grid
        print(f"\nGrid 值: {grid_values}")
        print(f"Grid 大小: {len(grid_values) ** len(SELECTED_FACTORS)} = {len(grid_values)}^{len(SELECTED_FACTORS)}")

        # 如果组合数太多，使用采样
        total_combinations = len(grid_values) ** len(SELECTED_FACTORS)
        if total_combinations > 10000:
            print(f"  [WARN] 组合数过多 ({total_combinations})，使用随机采样 10,000 个")
            use_sampling = True
            sample_size = 10000
        else:
            use_sampling = False
            sample_size = total_combinations

        best_score = -np.inf
        best_weights = None

        if use_sampling:
            # 随机采样
            for i in range(sample_size):
                if i % 1000 == 0:
                    print(f"  进度: {i}/{sample_size}")

                weights = np.random.choice(grid_values, size=len(SELECTED_FACTORS))
                weight_dict = dict(zip(SELECTED_FACTORS, weights))
                score = self._evaluate_weights_improved(df, weight_dict)

                if score > best_score:
                    best_score = score
                    best_weights = weight_dict
        else:
            # 完整遍历
            grid = list(itertools.product(grid_values, repeat=len(SELECTED_FACTORS)))
            for i, weights in enumerate(grid):
                if i % 100 == 0:
                    print(f"  进度: {i}/{len(grid)}")

                weight_dict = dict(zip(SELECTED_FACTORS, weights))
                score = self._evaluate_weights_improved(df, weight_dict)

                if score > best_score:
                    best_score = score
                    best_weights = weight_dict

        print(f"\n  [OK] 最优权重:")
        for factor, weight in best_weights.items():
            print(f"    {factor}: {weight:.2f}")
        print(f"  [OK] Score: {best_score:.4f}")

        result = {
            "method": "expanded_grid_search",
            "grid_values": grid_values,
            "total_combinations": total_combinations,
            "sampled": use_sampling,
            "best_weights": best_weights,
            "best_score": best_score,
        }

        self.results["expanded_grid_search"] = result
        return result

    def stage2_bayesian_optimization(
        self,
        df: pd.DataFrame,
        initial_weights: Dict[str, float],
        n_iter: int = 100
    ) -> Dict:
        """
        Stage 2: Bayesian Optimization (完整版)

        在扩展 Grid Search 最优解附近精调
        """
        print("\n" + "=" * 60)
        print("Stage 2: Bayesian Optimization (完整版)")
        print("=" * 60)

        from bayes_opt import BayesianOptimization

        # 定义优化边界 (在初始值 ±1.0 范围内，但限制在 [-2, 2])
        pbounds = {}
        for factor, init_weight in initial_weights.items():
            lower = max(-2.0, init_weight - 1.0)
            upper = min(2.0, init_weight + 1.0)
            pbounds[f"w_{factor}"] = (lower, upper)

        print(f"\n优化边界:")
        for k, v in pbounds.items():
            print(f"  {k}: [{v[0]:.2f}, {v[1]:.2f}]")

        # 定义目标函数
        def objective(**kwargs):
            weights = {
                factor: kwargs[f"w_{factor}"]
                for factor in SELECTED_FACTORS
            }
            return self._evaluate_weights_improved(df, weights)

        # Bayesian 优化
        optimizer = BayesianOptimization(
            f=objective,
            pbounds=pbounds,
            random_state=42,
        )

        print(f"\n开始优化 (n_iter={n_iter})...")
        optimizer.maximize(init_points=10, n_iter=n_iter)

        # 提取最优权重
        best_params = optimizer.max['params']
        best_weights = {
            factor: best_params[f"w_{factor}"]
            for factor in SELECTED_FACTORS
        }
        best_score = optimizer.max['target']

        print(f"\n  [OK] Bayesian 最优权重:")
        for factor, weight in best_weights.items():
            print(f"    {factor}: {weight:.4f}")
        print(f"  [OK] Score: {best_score:.4f}")

        # 与初始权重对比
        improvement = best_score - self._evaluate_weights_improved(df, initial_weights)
        print(f"\n  [OK] 改进: {improvement:+.4f}")

        result = {
            "method": "bayesian_opt",
            "initial_weights": initial_weights,
            "best_weights": best_weights,
            "best_score": best_score,
            "improvement": improvement,
            "n_iter": n_iter,
        }

        self.results["bayesian_opt"] = result
        return result

    def stage3_interaction_test(
        self,
        df: pd.DataFrame,
        base_weights: Dict[str, float]
    ) -> Dict:
        """
        Stage 3: 交互项测试

        测试因子间的交互效应
        """
        print("\n" + "=" * 60)
        print("Stage 3: Interaction Test (交互项)")
        print("=" * 60)

        # 基准得分
        base_score = self._evaluate_weights_improved(df, base_weights)
        print(f"\n基准 Score: {base_score:.4f}")

        # 测试重要的交互项
        interactions_to_test = [
            ("mom_short_z", "vix_level"),      # 动量 × 波动率
            ("rsi_z", "vix_level"),            # RSI × 波动率
            ("volume_ratio_rank", "mom_short_z"),  # 成交量 × 动量
        ]

        interaction_results = []

        for factor1, factor2 in interactions_to_test:
            print(f"\n测试交互: {factor1} × {factor2}")

            # 创建交互项
            df_with_interaction = df.copy()
            interaction_name = f"{factor1}_x_{factor2}"
            df_with_interaction[interaction_name] = (
                df[factor1].fillna(0) * df[factor2].fillna(0)
            )

            # 测试不同的交互权重
            best_interaction_weight = 0.0
            best_interaction_score = base_score

            for w in [-1.0, -0.5, 0.5, 1.0]:
                weights_with_interaction = {**base_weights, interaction_name: w}
                score = self._evaluate_weights_improved(
                    df_with_interaction,
                    weights_with_interaction
                )

                if score > best_interaction_score:
                    best_interaction_score = score
                    best_interaction_weight = w

            improvement = best_interaction_score - base_score
            print(f"  最优交互权重: {best_interaction_weight:.2f}")
            print(f"  改进: {improvement:+.4f}")

            interaction_results.append({
                "factor1": factor1,
                "factor2": factor2,
                "best_weight": best_interaction_weight,
                "score": best_interaction_score,
                "improvement": improvement,
            })

        # 找到最佳交互项
        best_interaction = max(interaction_results, key=lambda x: x['improvement'])

        print(f"\n  [OK] 最佳交互项:")
        print(f"    {best_interaction['factor1']} × {best_interaction['factor2']}")
        print(f"    权重: {best_interaction['best_weight']:.2f}")
        print(f"    改进: {best_interaction['improvement']:+.4f}")

        result = {
            "method": "interaction_test",
            "base_score": base_score,
            "interactions": interaction_results,
            "best_interaction": best_interaction,
        }

        self.results["interaction_test"] = result
        return result

    def _evaluate_weights_improved(
        self,
        df: pd.DataFrame,
        weights: Dict[str, float]
    ) -> float:
        """
        改进的评估函数

        改进点:
        1. 使用完整回测逻辑
        2. 考虑交易成本
        3. 更合理的仓位计算
        """
        # 计算因子得分
        factor_score = pd.Series(0.0, index=df.index)
        for factor, weight in weights.items():
            if factor in df.columns:
                factor_score += weight * df[factor].fillna(0)

        # 标准化得分到 [-1, 1]
        score_std = factor_score.std()
        if score_std > 0:
            factor_score = factor_score / score_std
            factor_score = np.clip(factor_score, -3, 3) / 3  # 归一化
        else:
            factor_score = pd.Series(0.0, index=df.index)

        # 计算目标仓位 (使用 tanh 平滑映射)
        target_position = np.tanh(factor_score)

        # 计算实际收益
        returns = df['close'].pct_change()

        # 考虑换仓成本
        position_change = target_position.diff().abs()
        transaction_cost = position_change * 0.001  # 0.1% 双边成本

        # 策略收益
        strategy_returns = target_position.shift(1) * returns - transaction_cost

        # 计算 Sharpe Ratio
        valid_returns = strategy_returns.dropna()
        if len(valid_returns) > 0 and valid_returns.std() > 0:
            sharpe = valid_returns.mean() / valid_returns.std() * np.sqrt(252)
        else:
            sharpe = 0.0

        return sharpe

    def save_results(self):
        """保存优化结果"""
        output_file = self.output_dir / "advanced_optimization_results.json"

        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)

        print(f"\n[OK] 结果已保存: {output_file}")

    def generate_report(self):
        """生成优化报告"""
        report_file = self.output_dir / "advanced_optimization_report.md"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write("# Phase 2.5: 深入优化报告\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            # Stage 1
            if "expanded_grid_search" in self.results:
                egs = self.results["expanded_grid_search"]
                f.write("## Stage 1: Expanded Grid Search\n\n")
                f.write(f"**Grid 范围**: {egs['grid_values']}\n\n")
                f.write(f"**总组合数**: {egs['total_combinations']}\n\n")
                f.write(f"**采样**: {'是' if egs['sampled'] else '否'}\n\n")
                f.write(f"**最优 Score**: {egs['best_score']:.4f}\n\n")
                f.write("**最优权重**:\n\n")
                for factor, weight in egs['best_weights'].items():
                    f.write(f"- `{factor}`: {weight:.2f}\n")
                f.write("\n---\n\n")

            # Stage 2
            if "bayesian_opt" in self.results:
                bo = self.results["bayesian_opt"]
                f.write("## Stage 2: Bayesian Optimization\n\n")
                f.write(f"**最优 Score**: {bo['best_score']:.4f}\n\n")
                f.write(f"**改进**: {bo['improvement']:+.4f}\n\n")
                f.write("**最优权重**:\n\n")
                for factor, weight in bo['best_weights'].items():
                    f.write(f"- `{factor}`: {weight:.4f}\n")
                f.write("\n---\n\n")

            # Stage 3
            if "interaction_test" in self.results:
                it = self.results["interaction_test"]
                f.write("## Stage 3: Interaction Test\n\n")
                f.write(f"**基准 Score**: {it['base_score']:.4f}\n\n")
                f.write("**测试的交互项**:\n\n")
                for inter in it['interactions']:
                    f.write(f"- `{inter['factor1']}` × `{inter['factor2']}`: "
                           f"权重 {inter['best_weight']:.2f}, "
                           f"改进 {inter['improvement']:+.4f}\n")
                f.write("\n**最佳交互项**:\n\n")
                best = it['best_interaction']
                f.write(f"- `{best['factor1']}` × `{best['factor2']}`\n")
                f.write(f"- 权重: {best['best_weight']:.2f}\n")
                f.write(f"- 改进: {best['improvement']:+.4f}\n")
                f.write("\n---\n\n")

            f.write("## 结论\n\n")
            f.write("Phase 2.5 完成了深入优化，包括负权重搜索、贝叶斯优化和交互项测试。\n\n")

        print(f"[OK] 报告已生成: {report_file}")


def main():
    """主函数: 运行完整的 Phase 2.5 优化"""
    print("=" * 60)
    print("Phase 2.5: 深入优化")
    print("=" * 60)
    print()

    # 加载示例数据 (AAPL)
    from core.data import fetch_data, standardize_columns
    from core.factor_pipeline import compute_all_factors

    print("加载数据...")
    df = fetch_data("AAPL", adjust="qfq")

    if df is None or len(df) == 0:
        print("[ERROR] 数据加载失败")
        return

    df = standardize_columns(df)

    if len(df) < 500:
        print(f"[ERROR] 数据不足: {len(df)} 行 (需要至少 500 行)")
        return

    print(f"[OK] 数据加载成功: {len(df)} 行")

    # 计算因子
    print("计算因子...")
    df = compute_all_factors(df, "AAPL")
    print(f"[OK] 因子计算完成")

    # 初始化优化器
    optimizer = AdvancedOptimizer()

    # Stage 1: Expanded Grid Search
    egs_result = optimizer.stage1_expanded_grid_search(df)

    # Stage 2: Bayesian Optimization
    bo_result = optimizer.stage2_bayesian_optimization(
        df,
        initial_weights=egs_result["best_weights"],
        n_iter=100
    )

    # Stage 3: Interaction Test
    it_result = optimizer.stage3_interaction_test(
        df,
        base_weights=bo_result["best_weights"]
    )

    # 保存结果
    optimizer.save_results()
    optimizer.generate_report()

    print("\n" + "=" * 60)
    print("[OK] Phase 2.5 优化完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
