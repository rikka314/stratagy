"""
Phase 1 Baseline 实验
=====================
测试延长 horizon 和加入宏观特征的效果

实验设计：
- B01: 28维技术特征 + 5日horizon（原始，对照组）
- B04: 28维技术特征 + 20日horizon（测试horizon效果）
- B05: 33维（28技术 + 5宏观）+ 20日horizon（测试宏观特征效果）
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import json
from datetime import datetime
from typing import Dict, List, Optional

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data import fetch_data
from core.indicators import add_indicators
from core.macro_factors import MacroFactors
from core.expert_utility import ExpertUtilityV4


class Phase1BaselineRunner:
    """Phase 1 基线实验运行器"""

    def __init__(self, output_dir: str = "model-test/outputs/phase1_baseline"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.macro_factors = MacroFactors()

    def prepare_features(
        self,
        stock_data: pd.DataFrame,
        include_macro: bool = False
    ) -> pd.DataFrame:
        """
        准备特征

        Args:
            stock_data: 原始 OHLCV 数据
            include_macro: 是否包含宏观特征

        Returns:
            包含所有特征的 DataFrame
        """
        # 添加技术指标（28维）- 使用默认参数
        data_with_indicators = add_indicators(
            stock_data,
            rsi_period=14,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            ema_fast=12,
            ema_slow=26,
            adx_period=14,
            atr_period=14,
            bb_period=20,
            bb_std=2.0,
            indicator_period=20
        )

        if include_macro:
            # 添加宏观特征（5维）
            print("  添加宏观特征...")
            macro_features = self.macro_factors.compute_batch(stock_data)

            # 合并特征
            data_with_indicators = data_with_indicators.join(
                macro_features,
                how='left'
            )

            # 填充缺失值
            macro_cols = [
                'vix_level', 'vix_regime_low', 'vix_regime_med', 'vix_regime_high',
                'rel_strength_vs_spy', 'beta_20d', 'market_breadth', 'sector_momentum'
            ]
            for col in macro_cols:
                if col in data_with_indicators.columns:
                    data_with_indicators[col].fillna(0, inplace=True)

        return data_with_indicators

    def run_single_baseline(
        self,
        method: str,
        stock_symbol: str,
        market: str = "US",
        horizon: int = 5,
        include_macro: bool = False
    ) -> Dict:
        """
        运行单个 baseline 实验

        Args:
            method: 方法名称（B01, B04, B05）
            stock_symbol: 股票代码
            market: 市场
            horizon: 评估窗口（天）
            include_macro: 是否包含宏观特征

        Returns:
            结果字典
        """
        print(f"\n{'='*60}")
        print(f"运行 {method}: {stock_symbol} (horizon={horizon}d, macro={include_macro})")
        print(f"{'='*60}")

        # 加载数据
        print("1. 加载股票数据...")
        adjust = "hfq" if market == "CN_A" else "qfq"
        stock_data = fetch_data(stock_symbol, adjust=adjust)

        if stock_data is None or len(stock_data) < 100:
            print(f"  [跳过] {stock_symbol} 数据不足")
            return None

        print(f"  数据范围: {stock_data.index[0]} 到 {stock_data.index[-1]} ({len(stock_data)} 行)")

        # 准备特征
        print("2. 准备特征...")
        features = self.prepare_features(stock_data, include_macro=include_macro)

        feature_count = len([col for col in features.columns if col not in ['Open', 'High', 'Low', 'Close', 'Volume']])
        print(f"  特征维度: {feature_count}")

        # 模拟专家决策（简单示例）
        print("3. 生成专家决策...")
        expert_decisions = self._generate_mock_expert_decisions(features)

        # 计算专家效用
        print(f"4. 计算专家效用 (horizon={horizon}d)...")
        utility_calculator = ExpertUtilityV4(horizon=horizon)
        utility_labels = utility_calculator.generate_labels_for_backtest(
            stock_data, expert_decisions
        )

        if utility_labels.empty:
            print(f"  [警告] 无法生成效用标签")
            return None

        print(f"  生成标签数: {len(utility_labels)}")

        # 计算汇总统计
        print("5. 计算统计...")
        stats = self._compute_statistics(utility_labels)

        result = {
            'method': method,
            'stock_symbol': stock_symbol,
            'market': market,
            'horizon': horizon,
            'include_macro': include_macro,
            'feature_count': feature_count,
            'label_count': len(utility_labels),
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        }

        # 保存结果
        result_path = self.output_dir / f"{method}_{stock_symbol}.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  结果已保存: {result_path}")

        return result

    def _generate_mock_expert_decisions(self, features: pd.DataFrame) -> dict:
        """生成模拟的专家决策（用于测试）"""
        # 简单的动量专家
        momentum_signal = features.get('mom_short', pd.Series(0, index=features.index))
        momentum_positions = (momentum_signal > 0).astype(float) * 0.8

        # 简单的均值回归专家
        rsi = features.get('rsi', pd.Series(50, index=features.index))
        mean_reversion_positions = ((rsi < 30).astype(float) * 0.8 +
                                   (rsi > 70).astype(float) * 0.2)

        return {
            'momentum': momentum_positions,
            'mean_reversion': mean_reversion_positions,
            'cash': pd.Series(0, index=features.index)
        }

    def _compute_statistics(self, utility_labels: pd.DataFrame) -> dict:
        """计算汇总统计"""
        stats = {}

        # 提取所有专家的 sharpe 列
        sharpe_cols = [col for col in utility_labels.columns if col.endswith('_sharpe_ratio')]

        if sharpe_cols:
            sharpe_values = utility_labels[sharpe_cols].mean()
            stats['mean_sharpe'] = float(sharpe_values.mean())
            stats['std_sharpe'] = float(sharpe_values.std())
            stats['max_sharpe'] = float(sharpe_values.max())
            stats['min_sharpe'] = float(sharpe_values.min())

        # 提取 win_rate
        win_rate_cols = [col for col in utility_labels.columns if col.endswith('_win_rate')]
        if win_rate_cols:
            win_rate_values = utility_labels[win_rate_cols].mean()
            stats['mean_win_rate'] = float(win_rate_values.mean())

        # 提取 max_drawdown
        dd_cols = [col for col in utility_labels.columns if col.endswith('_max_drawdown')]
        if dd_cols:
            dd_values = utility_labels[dd_cols].mean()
            stats['mean_max_dd'] = float(dd_values.mean())

        return stats

    def run_full_experiment(self, test_stocks: list = None):
        """运行完整的 Phase 1 实验"""

        if test_stocks is None:
            # 默认测试股票
            test_stocks = [
                ('AAPL', 'US'),
                ('MSFT', 'US'),
                ('000001', 'CN_A'),
            ]

        results = []

        print("=" * 60)
        print("Phase 1 Baseline 实验开始")
        print("=" * 60)

        for stock_symbol, market in test_stocks:
            # B01: 原始（5日 + 28维技术）
            result_b01 = self.run_single_baseline(
                method='B01',
                stock_symbol=stock_symbol,
                market=market,
                horizon=5,
                include_macro=False
            )
            if result_b01:
                results.append(result_b01)

            # B04: 20日 + 28维技术
            result_b04 = self.run_single_baseline(
                method='B04',
                stock_symbol=stock_symbol,
                market=market,
                horizon=20,
                include_macro=False
            )
            if result_b04:
                results.append(result_b04)

            # B05: 20日 + 33维（技术+宏观）
            result_b05 = self.run_single_baseline(
                method='B05',
                stock_symbol=stock_symbol,
                market=market,
                horizon=20,
                include_macro=True
            )
            if result_b05:
                results.append(result_b05)

        # 保存汇总结果
        summary_path = self.output_dir / "phase1_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n汇总结果已保存: {summary_path}")

        # 生成对比报告
        self._generate_comparison_report(results)

        return results

    def _generate_comparison_report(self, results: list):
        """生成对比报告"""
        if not results:
            return

        report_path = self.output_dir / "phase1_comparison_report.md"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# Phase 1 Baseline 对比报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # 按股票分组
            stocks = set((r['stock_symbol'], r['market']) for r in results)

            for stock_symbol, market in stocks:
                f.write(f"## {stock_symbol} ({market})\n\n")

                stock_results = [r for r in results if r['stock_symbol'] == stock_symbol]

                if not stock_results:
                    continue

                # 创建对比表格
                f.write("| Method | Horizon | Features | Mean Sharpe | Win Rate | Max DD |\n")
                f.write("|--------|---------|----------|-------------|----------|--------|\n")

                for r in stock_results:
                    method = r['method']
                    horizon = r['horizon']
                    features = r['feature_count']
                    stats = r['stats']

                    mean_sharpe = stats.get('mean_sharpe', 0)
                    win_rate = stats.get('mean_win_rate', 0) * 100
                    max_dd = stats.get('mean_max_dd', 0) * 100

                    f.write(f"| {method} | {horizon}d | {features} | {mean_sharpe:.3f} | {win_rate:.1f}% | {max_dd:.1f}% |\n")

                f.write("\n")

        print(f"对比报告已生成: {report_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Phase 1 Baseline 实验')
    parser.add_argument('--output', default='model-test/outputs/phase1_baseline',
                       help='输出目录')
    parser.add_argument('--stocks', nargs='+',
                       help='测试股票，格式: AAPL:US MSFT:US')

    args = parser.parse_args()

    # 解析股票列表
    test_stocks = None
    if args.stocks:
        test_stocks = []
        for stock_str in args.stocks:
            if ':' in stock_str:
                symbol, market = stock_str.split(':')
                test_stocks.append((symbol, market))

    # 运行实验
    runner = Phase1BaselineRunner(output_dir=args.output)
    results = runner.run_full_experiment(test_stocks=test_stocks)

    print("\n" + "=" * 60)
    print(f"Phase 1 实验完成！共 {len(results)} 个结果")
    print("=" * 60)
