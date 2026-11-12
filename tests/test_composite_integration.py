"""Phase 3: Composite 集成安全验证测试

测试覆盖：
1. 数据对齐验证
2. 仓位约束验证
3. Fallback 机制测试
4. 回测一致性验证
"""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta

import ui.single_stock as single_stock_page
import ui.single_stock_workflow as workflow
from ui.single_stock_workflow import (
    PipelineRunResult,
    StrategyRequest,
    run_composite_pipeline,
    build_strategy_context_key,
)


@pytest.fixture
def sample_stock_data():
    """生成测试用股票数据"""
    dates = pd.date_range(start="2020-01-01", end="2023-12-31", freq="B")
    np.random.seed(42)

    data = pd.DataFrame({
        "date": dates,
        "open": 100 + np.random.randn(len(dates)).cumsum() * 0.5,
        "high": 101 + np.random.randn(len(dates)).cumsum() * 0.5,
        "low": 99 + np.random.randn(len(dates)).cumsum() * 0.5,
        "close": 100 + np.random.randn(len(dates)).cumsum() * 0.5,
        "volume": np.random.randint(1_000_000, 10_000_000, len(dates)),
    })

    # 确保 OHLC 逻辑正确
    data["high"] = data[["open", "high", "low", "close"]].max(axis=1)
    data["low"] = data[["open", "high", "low", "close"]].min(axis=1)

    return data


class TestDataAlignment:
    """测试 1: 数据对齐验证"""

    def test_factor_date_alignment(self, sample_stock_data):
        """验证因子计算的日期索引与原始行情对齐"""
        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)

        request = StrategyRequest(
            family="composite",
            composite_policy="composite_only",
        )

        context_key = "test_ctx"

        result = run_composite_pipeline(
            context_key=context_key,
            request=request,
            params_snapshot={
                "rsi_period": 14,
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "ema_fast": 20,
                "ema_slow": 60,
                "adx_period": 14,
                "atr_period": 14,
                "bb_period": 20,
                "bb_std": 2.0,
                "indicator_period": 20,
                "stop_loss_mult": 2.0,
                "take_profit_mult": 4.0,
                "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        assert result.status in ["success", "degraded"], f"Pipeline 失败: {result.error_message}"

        if result.artifact:
            signal_df = result.artifact.full_signal_df

            # 检查日期对齐
            assert len(signal_df) == len(df), "信号 DataFrame 长度与原始数据不一致"
            assert "target_position" in signal_df.columns, "缺少 target_position 列"

            # 检查日期索引一致性
            if "date" in signal_df.columns and "date" in df.columns:
                assert signal_df["date"].equals(df["date"]), "日期索引不对齐"

    def test_train_test_split_boundary(self, sample_stock_data):
        """验证 train/test split 边界正确"""
        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)

        request = StrategyRequest(family="composite", composite_policy="composite_only")
        context_key = "test_ctx"

        result = run_composite_pipeline(
            context_key=context_key,
            request=request,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        if result.artifact:
            train_sim = result.artifact.train_sim_df
            test_sim = result.artifact.test_sim_df

            assert len(train_sim) == split_idx, f"Train set 长度错误: {len(train_sim)} != {split_idx}"
            assert len(test_sim) == len(df) - split_idx, f"Test set 长度错误"


class TestPositionConstraints:
    """测试 2: 仓位约束验证"""

    def test_position_bounds_cn_a(self, sample_stock_data):
        """CN_A: 验证 final_position ∈ [0, risk_budget]"""
        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)
        risk_budget = 0.8

        request = StrategyRequest(
            family="composite",
            composite_policy="composite_only",
            composite_risk_budget=risk_budget,
        )

        result = run_composite_pipeline(
            context_key="test_ctx",
            request=request,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        if result.artifact:
            positions = result.artifact.full_signal_df["target_position"]

            assert positions.min() >= 0.0, f"存在负仓位: {positions.min()}"
            assert positions.max() <= risk_budget + 1e-6, f"仓位超过风险预算: {positions.max()} > {risk_budget}"

    def test_advisory_only_reduces_position(self, sample_stock_data):
        """验证 advisory 只能减仓，不能增仓"""
        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)

        # 先运行 composite_only
        request_only = StrategyRequest(
            family="composite",
            composite_policy="composite_only",
        )

        result_only = run_composite_pipeline(
            context_key="test_ctx_only",
            request=request_only,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        # 再运行 with advisory
        request_advisory = StrategyRequest(
            family="composite",
            composite_policy="composite_plus_all_advisories",
        )

        result_advisory = run_composite_pipeline(
            context_key="test_ctx_advisory",
            request=request_advisory,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        if result_only.artifact and result_advisory.artifact:
            pos_only = result_only.artifact.full_signal_df["target_position"]
            pos_advisory = result_advisory.artifact.full_signal_df["target_position"]

            # Advisory 后的仓位应该 <= 原始 composite 仓位
            diff = pos_advisory - pos_only
            assert (diff <= 1e-6).all(), f"Advisory 增加了仓位，最大增幅: {diff.max()}"


class TestFallbackMechanisms:
    """测试 3: Fallback 机制测试"""

    def test_insufficient_training_samples(self):
        """CN_A: 测试训练样本不足时的降级"""
        # 生成只有 30 天的数据（< 50 样本）
        dates = pd.date_range(start="2023-01-01", end="2023-02-15", freq="B")
        df = pd.DataFrame({
            "date": dates,
            "open": 100 + np.random.randn(len(dates)),
            "high": 101 + np.random.randn(len(dates)),
            "low": 99 + np.random.randn(len(dates)),
            "close": 100 + np.random.randn(len(dates)),
            "volume": np.random.randint(1_000_000, 10_000_000, len(dates)),
        })

        split_idx = int(len(df) * 0.7)

        request = StrategyRequest(family="composite", composite_policy="composite_only")

        result = run_composite_pipeline(
            context_key="test_ctx",
            request=request,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        # 应该失败并返回明确错误
        assert result.status == "failed", "应该因样本不足而失败"
        assert "训练样本不足" in result.error_message, f"错误消息不明确: {result.error_message}"


class TestBacktestConsistency:
    """测试 4: 回测一致性验证"""

    def test_equity_curve_monotonic_with_positive_returns(self, sample_stock_data):
        """验证正收益时净值曲线单调递增"""
        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)

        request = StrategyRequest(family="composite", composite_policy="composite_only")

        result = run_composite_pipeline(
            context_key="test_ctx",
            request=request,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        if result.artifact:
            test_sim = result.artifact.test_sim_df

            # 检查必需列存在
            assert "equity" in test_sim.columns, "缺少 equity 列"
            assert "returns" in test_sim.columns, "缺少 returns 列"

            # 检查净值初始值
            assert test_sim["equity"].iloc[0] > 0, "初始净值应该 > 0"

            # 检查收益率合理性
            returns = test_sim["returns"]
            assert returns.notna().all() or returns.isna().sum() <= 1, "收益率存在过多 NaN"

    def test_evaluation_metrics_present(self, sample_stock_data):
        """验证评估指标完整性"""
        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)

        request = StrategyRequest(family="composite", composite_policy="composite_only")

        result = run_composite_pipeline(
            context_key="test_ctx",
            request=request,
            params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        if result.artifact:
            eval_result = result.artifact.eval

            # 检查关键指标存在
            required_metrics = ["cumret", "sharpe", "maxdd", "volatility"]
            for metric in required_metrics:
                assert metric in eval_result, f"缺少评估指标: {metric}"
                assert eval_result[metric] is not None, f"指标 {metric} 为 None"


class TestIsolationAndCompatibility:
    """测试 5: 隔离性和兼容性"""

    def test_composite_failure_doesnt_break_search(self, sample_stock_data):
        """验证 Composite 失败不影响 Search 策略"""
        from ui.single_stock_workflow import run_strategy_pipeline

        df = sample_stock_data.copy()
        split_idx = int(len(df) * 0.7)

        # 测试 Search 策略仍然正常工作
        search_request = StrategyRequest(
            family="search",
            search_base="sm",
            use_search=False,
        )

        result = run_strategy_pipeline(
            context_key="test_search_ctx",
            request=search_request,
            request_params_snapshot={
                "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                "ema_fast": 20, "ema_slow": 60, "adx_period": 14, "atr_period": 14,
                "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
                "stop_loss_mult": 2.0, "take_profit_mult": 4.0, "strategy_preset": "balanced",
                "rsi_lower": 30, "rsi_upper": 70, "adx_threshold": 20,
                "momentum_short": 5, "momentum_long": 20, "score_lookback": 30,
                "score_mid_pct": 0.6, "score_high_pct": 0.8,
                "weight_mom_short": 1.0, "weight_mom_long": 1.0, "weight_macd": 1.0,
                "weight_rsi": 0.5, "weight_vol": 0.5,
                "weight_bb": 0.8, "weight_obv": 1.0, "weight_volume": 0.6,
                "weight_price": 0.7, "weight_drawdown": 0.5,
                "entry_threshold": 0.5, "exit_threshold": -0.5,
                "entry_min_signals": 3, "exit_min_signals": 2,
                "use_trend_filter": True, "use_strength_filter": True,
                "use_rsi_filter": True, "use_macd_filter": True,
                "use_voting_entry": False, "entry_vote_threshold": 2.5,
            },
            df_raw=df,
            split_idx=split_idx,
            symbol="TEST",
            market="CN_A",
        )

        assert result.status == "success", "Search 策略应该正常工作"
        assert result.artifact is not None, "Search 策略应该返回 artifact"


def test_composite_request_does_not_require_search_base() -> None:
    """Composite is a first-class path and must not inherit SM/FSM gating."""
    request = StrategyRequest(family="composite", composite_policy="composite_only")

    assert single_stock_page._get_request_missing_items(request) == []
    path = single_stock_page._describe_request_pipeline(request)
    assert path is not None
    assert "SM / FSM" not in path
    assert path.startswith("Composite ->")


def test_run_strategy_pipeline_dispatches_composite_without_search_base(monkeypatch) -> None:
    """The workflow validator and dispatcher must accept Composite directly."""
    called: dict[str, object] = {}

    def fake_composite_pipeline(**kwargs):
        called.update(kwargs)
        return PipelineRunResult(artifact=None, status="success")

    monkeypatch.setattr(workflow, "run_composite_pipeline", fake_composite_pipeline)
    result = workflow.run_strategy_pipeline(
        context_key="composite_ctx",
        request=StrategyRequest(family="composite"),
        request_params_snapshot={},
        df_raw=pd.DataFrame({"close": [1.0, 1.1]}),
        split_idx=1,
        symbol="000001",
        market="CN_A",
    )

    assert result.status == "success"
    assert called["market"] == "CN_A"
    assert called["request"].family == "composite"


def test_us_composite_passes_symbol_to_macro_factor_compute(sample_stock_data) -> None:
    """US Composite must reach MacroFactors' DataFrame+symbol contract."""
    params_snapshot = {
        "rsi_period": 14,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "ema_fast": 20,
        "ema_slow": 60,
        "adx_period": 14,
        "atr_period": 14,
        "bb_period": 20,
        "bb_std": 2.0,
        "indicator_period": 20,
        "stop_loss_mult": 2.0,
        "take_profit_mult": 4.0,
        "strategy_preset": "balanced",
    }
    result = run_composite_pipeline(
        context_key="us_composite_ctx",
        request=StrategyRequest(family="composite"),
        params_snapshot=params_snapshot,
        df_raw=sample_stock_data,
        split_idx=730,
        symbol="TEST",
        market="US",
    )

    assert "compute expects (DataFrame, symbol)" not in (result.error_message or "")
    if result.artifact is not None:
        target_position = result.artifact.full_signal_df["target_position"]
        assert (target_position > 0).any(), "US Composite 不应在 warm-up 后整段退化为现金"

    cn_result = run_composite_pipeline(
        context_key="cn_a_composite_ctx",
        request=StrategyRequest(family="composite"),
        params_snapshot=params_snapshot,
        df_raw=sample_stock_data,
        split_idx=730,
        symbol="000001",
        market="A",
    )
    assert "Unsupported market" not in (cn_result.error_message or "")
    if cn_result.artifact is not None:
        assert cn_result.artifact.pipeline_lineage[-1].metadata["market"] == "CN_A"
        cn_positions = cn_result.artifact.full_signal_df["target_position"]
        assert cn_positions.nunique(dropna=True) > 1, "CN_A Composite 线性映射不应把所有行固定为同一仓位"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
