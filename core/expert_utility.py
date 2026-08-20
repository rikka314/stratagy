"""
专家效用计算模块（V4 - 20日horizon）
=====================================
Phase 1: 延长 horizon 从 5 日到 20 日

改动：
1. horizon: 5 days → 20 days
2. target: single utility → {sharpe, win_rate, return, max_dd}
3. 更稳定的信号提取
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


class ExpertUtilityV4:
    """
    专家效用计算器 V4

    相比 V3:
    - 延长 horizon 到 20 日（一个月）
    - 返回多维度指标而非单一 utility
    - 更好的风险调整收益计算
    """

    def __init__(self, horizon: int = 20):
        """
        Args:
            horizon: 评估窗口长度（交易日）
        """
        self.horizon = horizon

    def compute_expert_utility(
        self,
        expert_positions: np.ndarray,
        future_returns: np.ndarray
    ) -> Dict[str, float]:
        """
        计算单个专家在未来 horizon 内的表现

        Args:
            expert_positions: 专家每日目标仓位 (horizon,)，范围 [0, 1]
            future_returns: 未来每日收益率 (horizon,)

        Returns:
            包含多个指标的字典：
            - mean_return: 平均日收益
            - sharpe_ratio: 夏普比率（年化）
            - win_rate: 胜率
            - max_drawdown: 最大回撤
            - total_return: 总收益
        """
        if len(expert_positions) != self.horizon or len(future_returns) != self.horizon:
            raise ValueError(f"输入长度必须为 {self.horizon}")

        # 计算每日策略收益
        strategy_returns = expert_positions * future_returns

        # 基础指标
        mean_return = np.mean(strategy_returns)
        total_return = np.sum(strategy_returns)
        win_rate = np.mean(strategy_returns > 0)

        # 夏普比率（年化）
        if np.std(strategy_returns) > 1e-8:
            sharpe_ratio = mean_return / np.std(strategy_returns) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        # 最大回撤
        cumulative_returns = np.cumsum(strategy_returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = cumulative_returns - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0

        return {
            'mean_return': float(mean_return),
            'sharpe_ratio': float(sharpe_ratio),
            'win_rate': float(win_rate),
            'max_drawdown': float(max_drawdown),
            'total_return': float(total_return),
        }

    def compute_all_experts_utility(
        self,
        expert_positions_dict: Dict[str, np.ndarray],
        future_returns: np.ndarray
    ) -> pd.DataFrame:
        """
        批量计算多个专家的效用

        Args:
            expert_positions_dict: {expert_name: positions} 字典
            future_returns: 未来收益率数组

        Returns:
            DataFrame，每行是一个专家，列为各指标
        """
        results = []

        for expert_name, positions in expert_positions_dict.items():
            utility = self.compute_expert_utility(positions, future_returns)
            utility['expert_name'] = expert_name
            results.append(utility)

        df = pd.DataFrame(results)
        df.set_index('expert_name', inplace=True)
        return df

    def generate_labels_for_backtest(
        self,
        stock_data: pd.DataFrame,
        expert_decisions: Dict[str, pd.Series],
        start_idx: int = 0,
        end_idx: Optional[int] = None
    ) -> pd.DataFrame:
        """
        为回测数据生成专家效用标签

        Args:
            stock_data: 股票 OHLCV 数据，包含 'close' 列（小写）
            expert_decisions: {expert_name: daily_positions} 字典
            start_idx: 开始索引
            end_idx: 结束索引（不含），None 表示到末尾

        Returns:
            DataFrame，index 为日期，列为 {expert_name}_{metric}
        """
        if end_idx is None:
            end_idx = len(stock_data) - self.horizon

        # 计算日收益率 - 兼容大小写列名
        close_col = 'close' if 'close' in stock_data.columns else 'Close'
        returns = stock_data[close_col].pct_change().fillna(0).values

        results = []

        for i in range(start_idx, end_idx):
            date = stock_data.index[i]

            # 获取未来 horizon 的收益
            future_returns = returns[i + 1: i + 1 + self.horizon]

            if len(future_returns) < self.horizon:
                break

            # 获取每个专家的仓位
            expert_positions = {}
            for expert_name, positions_series in expert_decisions.items():
                # 确保日期对齐
                if date in positions_series.index:
                    # 获取从 date 开始的未来 horizon 个仓位
                    date_idx = positions_series.index.get_loc(date)
                    future_positions = positions_series.iloc[date_idx: date_idx + self.horizon].values

                    if len(future_positions) == self.horizon:
                        expert_positions[expert_name] = future_positions

            if expert_positions:
                # 计算所有专家的效用
                utilities = self.compute_all_experts_utility(expert_positions, future_returns)

                # 展平为单行
                row = {'date': date}
                for expert_name in utilities.index:
                    for metric in utilities.columns:
                        col_name = f"{expert_name}_{metric}"
                        row[col_name] = utilities.loc[expert_name, metric]

                results.append(row)

        df = pd.DataFrame(results)
        if not df.empty:
            df.set_index('date', inplace=True)

        return df


def compute_expert_utility_20d(
    stock_data: pd.DataFrame,
    expert_decisions: Dict[str, pd.Series],
    output_path: Optional[str] = None
) -> pd.DataFrame:
    """
    便捷函数：计算 20 日专家效用标签

    Args:
        stock_data: 股票 OHLCV 数据
        expert_decisions: 专家决策字典
        output_path: 可选的输出路径（.parquet 或 .csv）

    Returns:
        专家效用 DataFrame
    """
    calculator = ExpertUtilityV4(horizon=20)
    labels = calculator.generate_labels_for_backtest(stock_data, expert_decisions)

    if output_path:
        from pathlib import Path
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix == '.parquet':
            labels.to_parquet(output_path)
        elif output_path.suffix == '.csv':
            labels.to_csv(output_path)
        else:
            raise ValueError(f"不支持的文件格式: {output_path.suffix}")

        print(f"专家效用标签已保存: {output_path}")

    return labels


if __name__ == "__main__":
    # 简单测试
    np.random.seed(42)

    # 模拟数据
    horizon = 20
    positions = np.random.uniform(0, 1, horizon)
    returns = np.random.randn(horizon) * 0.01

    calculator = ExpertUtilityV4(horizon=horizon)
    utility = calculator.compute_expert_utility(positions, returns)

    print("专家效用计算测试:")
    print(utility)
