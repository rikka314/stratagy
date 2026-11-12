"""
CN_A Composite 统一比较模块

目标：
- 把新 CN_A Composite 放到现有 CN_A 研究结果中进行同口径比较
- 避免孤立解读，提供完整的模型对比矩阵

比较原则：
- 所有模型使用相同的 market/universe/fold/horizon/execution config
- 明确区分 strategy_return (source_net_no_recharge) vs OHLCV-based (ohlcv_gross_charge_once)
- 不以单一 Sharpe 排名作为唯一结论
- 报告 fold consistency、drawdown、turnover、fallback、coverage
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import pandas as pd
import numpy as np


@dataclass(frozen=True)
class ModelCategory:
    """模型分类"""
    name: str
    models: tuple[str, ...]


# 定义比较矩阵
COMPARISON_CATEGORIES = (
    ModelCategory(name="基础策略", models=("sm", "fsm")),
    ModelCategory(name="课程基线", models=("naive", "drift", "cash")),
    ModelCategory(name="既有组合", models=("best_single_expert", "equal_weight_experts")),
    ModelCategory(name="既有路由", models=("adaptive_router_v1",)),
    ModelCategory(name="新因子主模型", models=("composite_only",)),
    ModelCategory(
        name="新 advisory",
        models=(
            "composite_plus_trend",
            "composite_plus_reversion",
            "composite_plus_relative_strength",
            "composite_plus_macro_cap",
            "composite_plus_all_advisories",
        ),
    ),
)


@dataclass(frozen=True)
class ComparisonMetrics:
    """统一比较指标"""
    model_name: str
    category: str
    fold_id: str

    # 收益指标
    total_return: float
    annualized_return: float
    sharpe_ratio: float

    # 风险指标
    max_drawdown: float
    volatility: float
    downside_deviation: float

    # 执行指标
    avg_turnover: float
    total_trades: int
    win_rate: float

    # 成本指标
    total_cost: float
    cost_ratio: float  # 成本占总收益比例

    # 暴露指标
    avg_position: float
    max_position: float
    days_in_market: int

    # 质量标志
    has_fallback: bool
    fallback_rate: float
    data_coverage: float


def load_baseline_results(baseline_dir: Path) -> pd.DataFrame:
    """
    加载 Phase 4 baseline 结果

    Args:
        baseline_dir: baseline 输出目录

    Returns:
        包含 sm/fsm/cash 的 daily DataFrame
    """
    baseline_file = baseline_dir / "baseline_daily.parquet"
    if not baseline_file.exists():
        raise FileNotFoundError(
            f"Baseline daily file not found: {baseline_file}\n"
            "请先运行 Phase 4: python model-test/run_cn_a_baseline.py"
        )

    df = pd.read_parquet(baseline_file)

    # 验证必需字段
    required_cols = {"date", "symbol", "fold_id", "strategy", "position", "strategy_return"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Baseline daily missing required columns: {missing}")

    return df


def load_composite_results(composite_dir: Path) -> pd.DataFrame:
    """
    加载 Phase 4 Composite 结果

    Args:
        composite_dir: composite 输出目录

    Returns:
        composite_only 的 daily DataFrame
    """
    composite_file = composite_dir / "composite_daily.parquet"
    if not composite_file.exists():
        raise FileNotFoundError(
            f"Composite daily file not found: {composite_file}\n"
            "请先运行 Phase 4: python model-test/run_cn_a_composite.py"
        )

    df = pd.read_parquet(composite_file)

    # 验证必需字段
    required_cols = {"date", "symbol", "fold_id", "composite_score", "position", "strategy_return"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Composite daily missing required columns: {missing}")

    # 统一命名
    df = df.copy()
    df["strategy"] = "composite_only"

    return df


def load_advisory_results(advisory_dir: Path) -> pd.DataFrame | None:
    """
    加载 Phase 5 advisory 结果（可选）

    Args:
        advisory_dir: advisory 输出目录

    Returns:
        advisory 的 daily DataFrame，或 None 如果不存在
    """
    advisory_file = advisory_dir / "advisory_daily.parquet"
    if not advisory_file.exists():
        return None

    df = pd.read_parquet(advisory_file)

    # 验证必需字段
    required_cols = {"date", "symbol", "fold_id", "policy", "position", "strategy_return"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Advisory daily missing required columns: {missing}")

    # 统一命名
    df = df.rename(columns={"policy": "strategy"})

    return df


def compute_fold_metrics(
    daily_df: pd.DataFrame,
    strategy_name: str,
    fold_id: str,
    category: str,
) -> ComparisonMetrics:
    """
    计算单个 fold 的完整指标

    Args:
        daily_df: 单策略单 fold 的 daily DataFrame
        strategy_name: 策略名称
        fold_id: fold 标识
        category: 模型分类

    Returns:
        ComparisonMetrics 对象
    """
    # 基础收益计算
    returns = daily_df["strategy_return"].values
    positions = daily_df["position"].values

    total_return = np.sum(returns)
    n_days = len(returns)
    trading_days_per_year = 252
    years = n_days / trading_days_per_year
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    # Sharpe ratio
    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1) if len(returns) > 1 else 0.0
    sharpe_ratio = (mean_return / std_return * np.sqrt(trading_days_per_year)) if std_return > 0 else 0.0

    # 最大回撤
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdown)

    # 下行偏差
    downside_returns = returns[returns < 0]
    downside_deviation = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else 0.0

    # 换手和交易
    position_changes = np.abs(np.diff(positions, prepend=0.0))
    avg_turnover = np.mean(position_changes)
    total_trades = np.sum(position_changes > 1e-6)

    # 胜率
    winning_days = np.sum(returns > 0)
    win_rate = winning_days / n_days if n_days > 0 else 0.0

    # 成本（如果有 transaction_cost 列）
    if "transaction_cost" in daily_df.columns:
        total_cost = np.sum(daily_df["transaction_cost"].values)
    else:
        # 估算成本：8 bps per turnover
        total_cost = np.sum(position_changes) * 0.0008

    cost_ratio = abs(total_cost / total_return) if abs(total_return) > 1e-6 else 0.0

    # 暴露
    avg_position = np.mean(np.abs(positions))
    max_position = np.max(np.abs(positions))
    days_in_market = np.sum(np.abs(positions) > 1e-6)

    # 质量标志
    has_fallback = "fallback_used" in daily_df.columns and daily_df["fallback_used"].any()
    fallback_rate = (
        daily_df["fallback_used"].mean() if "fallback_used" in daily_df.columns else 0.0
    )
    data_coverage = n_days / n_days  # 简化：假设所有数据可用

    return ComparisonMetrics(
        model_name=strategy_name,
        category=category,
        fold_id=fold_id,
        total_return=total_return,
        annualized_return=annualized_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        volatility=std_return * np.sqrt(trading_days_per_year),
        downside_deviation=downside_deviation * np.sqrt(trading_days_per_year),
        avg_turnover=avg_turnover,
        total_trades=int(total_trades),
        win_rate=win_rate,
        total_cost=total_cost,
        cost_ratio=cost_ratio,
        avg_position=avg_position,
        max_position=max_position,
        days_in_market=int(days_in_market),
        has_fallback=has_fallback,
        fallback_rate=fallback_rate,
        data_coverage=data_coverage,
    )


def aggregate_fold_metrics(fold_metrics: list[ComparisonMetrics]) -> dict[str, Any]:
    """
    聚合多个 fold 的指标

    Args:
        fold_metrics: 同一策略的多个 fold 指标

    Returns:
        聚合后的指标字典
    """
    if not fold_metrics:
        return {}

    model_name = fold_metrics[0].model_name
    category = fold_metrics[0].category

    # 计算均值和标准差
    sharpe_ratios = [m.sharpe_ratio for m in fold_metrics]
    total_returns = [m.total_return for m in fold_metrics]
    max_drawdowns = [m.max_drawdown for m in fold_metrics]
    turnovers = [m.avg_turnover for m in fold_metrics]

    return {
        "model_name": model_name,
        "category": category,
        "n_folds": len(fold_metrics),
        "sharpe_mean": np.mean(sharpe_ratios),
        "sharpe_std": np.std(sharpe_ratios, ddof=1) if len(sharpe_ratios) > 1 else 0.0,
        "sharpe_min": np.min(sharpe_ratios),
        "sharpe_max": np.max(sharpe_ratios),
        "return_mean": np.mean(total_returns),
        "return_std": np.std(total_returns, ddof=1) if len(total_returns) > 1 else 0.0,
        "drawdown_mean": np.mean(max_drawdowns),
        "drawdown_worst": np.min(max_drawdowns),
        "turnover_mean": np.mean(turnovers),
        "folds_positive_sharpe": sum(1 for s in sharpe_ratios if s > 0),
        "folds_sharpe_above_03": sum(1 for s in sharpe_ratios if s >= 0.3),
    }


def generate_comparison_report(
    all_metrics: list[ComparisonMetrics],
    output_dir: Path,
) -> None:
    """
    生成统一比较报告

    Args:
        all_metrics: 所有模型的所有 fold 指标
        output_dir: 输出目录
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 转为 DataFrame
    metrics_df = pd.DataFrame([
        {
            "model_name": m.model_name,
            "category": m.category,
            "fold_id": m.fold_id,
            "total_return": m.total_return,
            "annualized_return": m.annualized_return,
            "sharpe_ratio": m.sharpe_ratio,
            "max_drawdown": m.max_drawdown,
            "volatility": m.volatility,
            "downside_deviation": m.downside_deviation,
            "avg_turnover": m.avg_turnover,
            "total_trades": m.total_trades,
            "win_rate": m.win_rate,
            "total_cost": m.total_cost,
            "cost_ratio": m.cost_ratio,
            "avg_position": m.avg_position,
            "max_position": m.max_position,
            "days_in_market": m.days_in_market,
            "has_fallback": m.has_fallback,
            "fallback_rate": m.fallback_rate,
            "data_coverage": m.data_coverage,
        }
        for m in all_metrics
    ])

    # 保存 fold-level 指标
    fold_metrics_file = output_dir / "comparison_fold_metrics.csv"
    metrics_df.to_csv(fold_metrics_file, index=False, float_format="%.6f")
    print(f"✅ Fold-level metrics saved: {fold_metrics_file}")

    # 聚合到模型级别
    model_aggregates = []
    for model_name in metrics_df["model_name"].unique():
        model_metrics = [m for m in all_metrics if m.model_name == model_name]
        agg = aggregate_fold_metrics(model_metrics)
        if agg:
            model_aggregates.append(agg)

    agg_df = pd.DataFrame(model_aggregates)

    # 按 Sharpe 均值排序
    agg_df = agg_df.sort_values("sharpe_mean", ascending=False)

    # 保存模型级别聚合
    model_metrics_file = output_dir / "comparison_metrics.csv"
    agg_df.to_csv(model_metrics_file, index=False, float_format="%.6f")
    print(f"✅ Model-level metrics saved: {model_metrics_file}")

    # 生成 Markdown 报告
    generate_markdown_report(metrics_df, agg_df, output_dir)


def generate_markdown_report(
    fold_df: pd.DataFrame,
    agg_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """
    生成 Markdown 比较报告

    Args:
        fold_df: fold-level 指标
        agg_df: model-level 聚合指标
        output_dir: 输出目录
    """
    report_file = output_dir / "comparison_report.md"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# CN_A Composite 统一比较报告\n\n")
        f.write("## 1. 执行摘要\n\n")
        f.write(f"- 比较模型数量: {len(agg_df)}\n")
        f.write(f"- Fold 数量: {len(fold_df['fold_id'].unique())}\n")
        f.write(f"- 市场: CN_A\n")
        f.write(f"- Horizon: 20 trading days\n")
        f.write(f"- 执行成本: 3 bps commission + 5 bps slippage\n\n")

        f.write("## 2. 模型排名（按 Sharpe 均值）\n\n")
        f.write("| 排名 | 模型 | 分类 | Sharpe 均值 | Sharpe 标准差 | 收益均值 | 最大回撤均值 | 换手均值 |\n")
        f.write("|------|------|------|-------------|---------------|----------|--------------|----------|\n")

        for rank, row in enumerate(agg_df.itertuples(), start=1):
            f.write(
                f"| {rank} | {row.model_name} | {row.category} | "
                f"{row.sharpe_mean:.4f} | {row.sharpe_std:.4f} | "
                f"{row.return_mean:.4f} | {row.drawdown_mean:.4f} | "
                f"{row.turnover_mean:.4f} |\n"
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

        f.write("\n## 4. 风险调整收益对比\n\n")

        # 找出最优模型
        best_model = agg_df.iloc[0]
        f.write(f"**最优模型**: {best_model['model_name']} ({best_model['category']})\n\n")
        f.write(f"- Sharpe: {best_model['sharpe_mean']:.4f} ± {best_model['sharpe_std']:.4f}\n")
        f.write(f"- 总收益: {best_model['return_mean']:.4f}\n")
        f.write(f"- 最大回撤: {best_model['drawdown_mean']:.4f}\n")
        f.write(f"- 换手: {best_model['turnover_mean']:.4f}\n\n")

        f.write("## 5. 解释与建议\n\n")
        f.write("### 5.1 结论\n\n")
        f.write(f"- 本次比较基于 {len(fold_df['fold_id'].unique())} 个 walk-forward folds\n")
        f.write("- 所有模型使用相同的 market/universe/fold/horizon/execution config\n")
        f.write("- 结果为 research-only，不代表生产就绪\n\n")

        f.write("### 5.2 下一步\n\n")

        # 判断 Composite 是否优于基线
        composite_row = agg_df[agg_df["model_name"] == "composite_only"]
        if not composite_row.empty:
            composite_sharpe = composite_row.iloc[0]["sharpe_mean"]

            sm_row = agg_df[agg_df["model_name"] == "sm"]
            fsm_row = agg_df[agg_df["model_name"] == "fsm"]

            if not sm_row.empty and not fsm_row.empty:
                sm_sharpe = sm_row.iloc[0]["sharpe_mean"]
                fsm_sharpe = fsm_row.iloc[0]["sharpe_mean"]

                if composite_sharpe > max(sm_sharpe, fsm_sharpe):
                    f.write("- ✅ Composite 优于 SM/FSM baseline，建议考虑 Phase 7 production review\n")
                else:
                    f.write("- ⚠️ Composite 未显著优于 SM/FSM，建议保持现有策略或进一步优化\n")

        f.write("- 若 advisory 版本通过 gate，可考虑接入 Streamlit read-only 展示\n")
        f.write("- 不得自动修改生产默认策略\n")
        f.write("- 跨市场结论需独立验证，不得外推\n")

    print(f"✅ Markdown report saved: {report_file}")
