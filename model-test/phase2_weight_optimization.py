"""Phase 2: 因子权重优化

三阶段优化:
1. Grid Search - 分层粗筛选
2. Bayesian Optimization - 精细调优
3. Feature Selection - 自动筛选冗余因子
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

# Phase 1 筛选出的 7 个因子
SELECTED_FACTORS = [
    # Layer 1: 趋势动量
    "mom_short_z",
    "macd_z",
    # Layer 2: 均值回归
    "rsi_z",
    "bb_position_rank",
    # Layer 3: 风险成交量
    "volume_ratio_rank",
    # Layer 4: 宏观相对
    "vix_regime",
    "vix_level",
]

# 因子分层
LAYER_MAPPING = {
    "layer_1_3": ["mom_short_z", "macd_z", "rsi_z", "bb_position_rank", "volume_ratio_rank"],
    "layer_4": ["vix_regime", "vix_level"],
}


class WeightOptimizer:
    """因子权重优化器"""

    def __init__(self, output_dir: str = "model-test/outputs/phase2_weight_optimization"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.results = {
            "grid_search": {},
            "bayesian_opt": {},
            "feature_selection": {},
        }

    def stage1_grid_search(
        self,
        df: pd.DataFrame,
        grid_values: List[float] = [0.0, 0.5, 1.0, 1.5, 2.0]
    ) -> Dict:
        """
        Stage 1: 分层 Grid Search

        策略: 先优化技术因子(Layer 1-3)，再优化宏观因子(Layer 4)
        """
        print("=" * 60)
        print("Stage 1: Grid Search (分层)")
        print("=" * 60)

        # Step 1: 优化 Layer 1-3 (技术因子)
        print("\nStep 1: 优化技术因子 (Layer 1-3)...")
        layer_1_3_factors = LAYER_MAPPING["layer_1_3"]

        # 生成 Layer 1-3 的 grid
        grid_1_3 = list(itertools.product(grid_values, repeat=len(layer_1_3_factors)))
        print(f"  Grid 大小: {len(grid_1_3)} 组合")

        best_1_3_score = -np.inf
        best_1_3_weights = None

        for i, weights in enumerate(grid_1_3):
            if i % 100 == 0:
                print(f"  进度: {i}/{len(grid_1_3)}")

            weight_dict = dict(zip(layer_1_3_factors, weights))
            score = self._evaluate_weights(df, weight_dict)

            if score > best_1_3_score:
                best_1_3_score = score
                best_1_3_weights = weight_dict

        print(f"\n  [OK] Layer 1-3 最优权重:")
        for factor, weight in best_1_3_weights.items():
            print(f"    {factor}: {weight:.2f}")
        print(f"  [OK] Score: {best_1_3_score:.4f}")

        # Step 2: 固定 Layer 1-3，优化 Layer 4 (宏观因子)
        print("\nStep 2: 优化宏观因子 (Layer 4)...")
        layer_4_factors = LAYER_MAPPING["layer_4"]

        grid_4 = list(itertools.product(grid_values, repeat=len(layer_4_factors)))
        print(f"  Grid 大小: {len(grid_4)} 组合")

        best_4_score = -np.inf
        best_4_weights = None

        for i, weights in enumerate(grid_4):
            weight_dict = {**best_1_3_weights}  # 固定 Layer 1-3
            weight_dict.update(dict(zip(layer_4_factors, weights)))

            score = self._evaluate_weights(df, weight_dict)

            if score > best_4_score:
                best_4_score = score
                best_4_weights = dict(zip(layer_4_factors, weights))

        print(f"\n  [OK] Layer 4 最优权重:")
        for factor, weight in best_4_weights.items():
            print(f"    {factor}: {weight:.2f}")
        print(f"  [OK] Score: {best_4_score:.4f}")

        # 合并最优权重
        best_weights = {**best_1_3_weights, **best_4_weights}

        result = {
            "method": "grid_search",
            "best_weights": best_weights,
            "best_score": best_4_score,
            "layer_1_3_score": best_1_3_score,
            "layer_4_score": best_4_score,
        }

        self.results["grid_search"] = result
        return result

    def stage2_bayesian_optimization(
        self,
        df: pd.DataFrame,
        initial_weights: Dict[str, float],
        n_iter: int = 100
    ) -> Dict:
        """
        Stage 2: Bayesian Optimization (精调)

        在 Grid Search 最优解附近精调
        """
        print("\n" + "=" * 60)
        print("Stage 2: Bayesian Optimization (精调)")
        print("=" * 60)

        try:
            from bayes_opt import BayesianOptimization
        except ImportError:
            print("  [WARN]  bayesian-optimization 未安装，跳过此阶段")
            print("  安装命令: pip install bayesian-optimization")
            return {"method": "bayesian_opt", "skipped": True}

        # 定义优化边界 (在初始值 ±0.5 范围内)
        pbounds = {}
        for factor, init_weight in initial_weights.items():
            pbounds[f"w_{factor}"] = (
                max(0.0, init_weight - 0.5),
                init_weight + 0.5
            )

        # 定义目标函数
        def objective(**kwargs):
            weights = {
                factor: kwargs[f"w_{factor}"]
                for factor in SELECTED_FACTORS
            }
            return self._evaluate_weights(df, weights)

        # Bayesian 优化
        optimizer = BayesianOptimization(
            f=objective,
            pbounds=pbounds,
            random_state=42,
        )

        print(f"\n  开始优化 (n_iter={n_iter})...")
        optimizer.maximize(init_points=5, n_iter=n_iter)

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

        result = {
            "method": "bayesian_opt",
            "best_weights": best_weights,
            "best_score": best_score,
            "n_iter": n_iter,
        }

        self.results["bayesian_opt"] = result
        return result

    def stage3_feature_selection(
        self,
        df: pd.DataFrame,
        weights: Dict[str, float]
    ) -> Dict:
        """
        Stage 3: Feature Selection (自动筛选冗余因子)

        使用 LightGBM 特征重要性筛选
        """
        print("\n" + "=" * 60)
        print("Stage 3: Feature Selection (筛选冗余)")
        print("=" * 60)

        try:
            from lightgbm import LGBMRegressor
        except ImportError:
            print("  [WARN]  lightgbm 未安装，跳过此阶段")
            print("  安装命令: pip install lightgbm")
            return {"method": "feature_selection", "skipped": True}

        # 准备训练数据
        X = df[SELECTED_FACTORS].fillna(0)
        y = df['close'].pct_change(20).shift(-20).fillna(0)  # 20日未来收益

        # 移除缺失行
        valid_idx = ~(X.isna().any(axis=1) | y.isna())
        X = X[valid_idx]
        y = y[valid_idx]

        print(f"\n  训练数据: {len(X)} 行")

        # 训练 LightGBM
        model = LGBMRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
            verbose=-1,
        )
        model.fit(X, y)

        # 特征重要性
        importance = pd.Series(
            model.feature_importances_,
            index=SELECTED_FACTORS
        ).sort_values(ascending=False)

        print("\n  特征重要性:")
        for factor, imp in importance.items():
            print(f"    {factor}: {imp:.4f}")

        # 筛选: 保留累积重要性 >= 90% 的因子
        cumsum = importance.cumsum() / importance.sum()
        selected_final = importance[cumsum <= 0.9].index.tolist()

        # 如果筛选后少于 3 个，保留 top 3
        if len(selected_final) < 3:
            selected_final = importance.head(3).index.tolist()

        print(f"\n  [OK] 筛选后因子 ({len(selected_final)} 个):")
        for factor in selected_final:
            print(f"    - {factor}")

        # 重新评估筛选后的权重
        filtered_weights = {k: v for k, v in weights.items() if k in selected_final}
        filtered_score = self._evaluate_weights(df, filtered_weights)

        print(f"\n  [OK] 筛选后 Score: {filtered_score:.4f}")

        result = {
            "method": "feature_selection",
            "importance": importance.to_dict(),
            "selected_factors": selected_final,
            "filtered_weights": filtered_weights,
            "filtered_score": filtered_score,
            "removed_factors": [f for f in SELECTED_FACTORS if f not in selected_final],
        }

        self.results["feature_selection"] = result
        return result

    def _evaluate_weights(self, df: pd.DataFrame, weights: Dict[str, float]) -> float:
        """
        评估因子权重组合

        返回: Sharpe Ratio
        """
        # 计算因子得分
        factor_score = pd.Series(0.0, index=df.index)
        for factor, weight in weights.items():
            if factor in df.columns:
                factor_score += weight * df[factor].fillna(0)

        # 简化版回测: 按得分分位数建仓
        # 得分 > 60th percentile: 做多
        # 得分 < 40th percentile: 做空
        positions = pd.Series(0.0, index=df.index)
        positions[factor_score > factor_score.quantile(0.6)] = 1.0
        positions[factor_score < factor_score.quantile(0.4)] = -1.0

        # 计算策略收益
        returns = df['close'].pct_change()
        strategy_returns = positions.shift(1) * returns

        # Sharpe Ratio
        sharpe = strategy_returns.mean() / (strategy_returns.std() + 1e-10) * np.sqrt(252)

        return sharpe

    def save_results(self):
        """保存优化结果"""
        output_file = self.output_dir / "optimization_results.json"

        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)

        print(f"\n[OK] 结果已保存: {output_file}")

    def generate_report(self):
        """生成优化报告"""
        report_file = self.output_dir / "optimization_report.md"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write("# Phase 2: 因子权重优化报告\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            # Stage 1
            if "grid_search" in self.results and self.results["grid_search"]:
                gs = self.results["grid_search"]
                f.write("## Stage 1: Grid Search\n\n")
                f.write(f"**最优 Score**: {gs['best_score']:.4f}\n\n")
                f.write("**最优权重**:\n\n")
                for factor, weight in gs['best_weights'].items():
                    f.write(f"- `{factor}`: {weight:.2f}\n")
                f.write("\n---\n\n")

            # Stage 2
            if "bayesian_opt" in self.results and self.results["bayesian_opt"]:
                bo = self.results["bayesian_opt"]
                if not bo.get("skipped"):
                    f.write("## Stage 2: Bayesian Optimization\n\n")
                    f.write(f"**最优 Score**: {bo['best_score']:.4f}\n\n")
                    f.write("**最优权重**:\n\n")
                    for factor, weight in bo['best_weights'].items():
                        f.write(f"- `{factor}`: {weight:.4f}\n")
                    f.write("\n---\n\n")

            # Stage 3
            if "feature_selection" in self.results and self.results["feature_selection"]:
                fs = self.results["feature_selection"]
                if not fs.get("skipped"):
                    f.write("## Stage 3: Feature Selection\n\n")
                    f.write(f"**筛选后 Score**: {fs['filtered_score']:.4f}\n\n")
                    f.write(f"**筛选后因子** ({len(fs['selected_factors'])} 个):\n\n")
                    for factor in fs['selected_factors']:
                        imp = fs['importance'][factor]
                        f.write(f"- `{factor}`: 重要性 {imp:.4f}\n")
                    f.write("\n")
                    if fs['removed_factors']:
                        f.write(f"**移除因子**: {', '.join(fs['removed_factors'])}\n\n")
                    f.write("\n---\n\n")

            f.write("## 结论\n\n")
            f.write("Phase 2 完成了因子权重的三阶段优化。\n\n")
            f.write("下一步: Phase 3 - 专家池重构\n")

        print(f"[OK] 报告已生成: {report_file}")


def main():
    """主函数: 运行完整的 Phase 2 优化"""
    print("=" * 60)
    print("Phase 2: 因子权重优化")
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
    optimizer = WeightOptimizer()

    # Stage 1: Grid Search
    gs_result = optimizer.stage1_grid_search(df)

    # Stage 2: Bayesian Optimization
    bo_result = optimizer.stage2_bayesian_optimization(
        df,
        initial_weights=gs_result["best_weights"],
        n_iter=50
    )

    # Stage 3: Feature Selection
    final_weights = bo_result.get("best_weights", gs_result["best_weights"])
    fs_result = optimizer.stage3_feature_selection(df, final_weights)

    # 保存结果
    optimizer.save_results()
    optimizer.generate_report()

    print("\n" + "=" * 60)
    print("[OK] Phase 2 优化完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
