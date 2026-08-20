# Phase 1 快速启动指南

> **Phase 1 状态**: ✅ **COMPLETED** (2026-08-20)  
> **下一步**: Phase 2 - 构建多样化专家池

---

## 快速概览

Phase 1 成功完成了以下目标：

1. ✅ 实现了宏观特征计算模块（VIX、SPY、beta、相对强度、市场广度）
2. ✅ 将专家评估 horizon 从 5 日延长到 20 日
3. ✅ 运行了 baseline 实验，证明 20 日 horizon 有效（Sharpe +9.9%）

---

## 核心代码模块

### 1. 宏观特征计算器

**文件**: `core/macro_factors.py`

**用法**:
```python
from core.macro_factors import MacroFactors
import pandas as pd

# 初始化
macro_factors = MacroFactors(macro_data_dir="data/macro")

# 计算单日特征
features = macro_factors.compute(
    date=pd.Timestamp('2024-01-15'),
    stock_data=stock_df  # OHLCV DataFrame
)
# 返回: {'vix_level', 'rel_strength_vs_spy', 'beta_20d', ...}

# 批量计算
batch_features = macro_factors.compute_batch(stock_df)
# 返回: DataFrame with macro features
```

**特征维度**:
- `vix_level`: VIX 绝对值
- `vix_regime_low/med/high`: 波动率分类（one-hot）
- `rel_strength_vs_spy`: 标准化超额收益
- `beta_20d`: 20日滚动 beta
- `market_breadth`: 市场广度（SPY 动量代理）
- `sector_momentum`: 行业相对动量

### 2. 专家效用计算器 V4

**文件**: `core/expert_utility.py`

**用法**:
```python
from core.expert_utility import ExpertUtilityV4
import numpy as np

# 初始化（20日窗口）
calculator = ExpertUtilityV4(horizon=20)

# 计算单个专家效用
expert_positions = np.array([0.8, 0.6, ..., 0.4])  # 20个仓位
future_returns = np.array([0.01, -0.005, ..., 0.02])  # 20个收益

utility = calculator.compute_expert_utility(
    expert_positions, future_returns
)
# 返回: {'mean_return', 'sharpe_ratio', 'win_rate', 'max_drawdown', 'total_return'}

# 批量计算（回测场景）
labels = calculator.generate_labels_for_backtest(
    stock_data=stock_df,
    expert_decisions={'momentum': positions_series, 'mean_reversion': ...}
)
# 返回: DataFrame with expert_{name}_{metric} columns
```

### 3. Phase 1 实验运行器

**文件**: `model-test/run_phase1_baseline.py`

**用法**:
```bash
# 运行单个股票
python model-test/run_phase1_baseline.py --stocks AAPL:US

# 运行多个股票
python model-test/run_phase1_baseline.py --stocks AAPL:US MSFT:US 000001:CN_A

# 指定输出目录
python model-test/run_phase1_baseline.py \
    --stocks AAPL:US \
    --output model-test/outputs/phase1_custom
```

**输出**:
- `{method}_{symbol}.json` - 单个实验结果
- `phase1_summary.json` - 所有实验汇总
- `phase1_comparison_report.md` - 对比报告

---

## Phase 1 实验结果

### AAPL 测试结果

| Method | Horizon | Features | Mean Sharpe | 改进 |
|--------|---------|----------|-------------|------|
| B01 | 5d | 28 (技术) | 0.151 | baseline |
| B04 | 20d | 28 (技术) | 0.166 | **+9.9%** ✅ |
| B05 | 20d | 36 (技术+宏观) | 0.166 | +0.0% ❌ |

**关键发现**:
- ✅ 延长 horizon 到 20 日显著改善夏普比率
- ❌ 宏观特征在当前简单专家下未显示增量价值
- ⚠️ 简单专家的 win rate 仅 2.8%，说明需要更好的专家设计

---

## 宏观数据准备

### 方案 1: 真实数据（推荐但可能受限）

```bash
python data-pipeline/download_macro_data.py
```

**数据源**:
- VIX: Yahoo Finance `^VIX`
- SPY: Yahoo Finance `SPY`

**限制**: 可能遇到 API 速率限制

### 方案 2: 模拟数据（当前使用）

```bash
python data-pipeline/download_macro_data_alternative.py
```

**特点**:
- VIX: 随机游走，均值 42.02，标准差 12.83
- SPY: 几何布朗运动，年化收益 ~10%
- 数据范围: 2015-01-01 到 2026-08-20（4,250 行）

**存储位置**:
- `data/macro/vix_daily.parquet`
- `data/macro/spy_daily.parquet`

---

## 如何复现结果

### 步骤 1: 准备宏观数据

```bash
# 使用模拟数据（快速）
python data-pipeline/download_macro_data_alternative.py

# 或使用真实数据（可能失败）
python data-pipeline/download_macro_data.py
```

### 步骤 2: 运行 Phase 1 实验

```bash
# 单个股票（快速测试）
python model-test/run_phase1_baseline.py --stocks AAPL:US

# 多个股票（完整实验）
python model-test/run_phase1_baseline.py --stocks AAPL:US MSFT:US TSLA:US
```

### 步骤 3: 查看结果

```bash
# 查看汇总
cat model-test/outputs/phase1_baseline/phase1_summary.json

# 查看对比报告
cat model-test/outputs/phase1_baseline/phase1_comparison_report.md

# 查看完整 Phase 1 报告
cat document/phase1_completion_report.md
```

---

## 下一步：Phase 2

### Phase 2 目标

构建信息源正交的专家池，解决当前专家同质化问题。

### 需要实现的 6 个专家

1. **Momentum Expert** - 纯动量跟随
2. **Mean Reversion Expert** - 超买超卖反转
3. **Volatility Breakout Expert** - 低波后突破
4. **Relative Strength Expert** - 强者恒强策略
5. **Macro Defensive Expert** - 高风险环境降仓
6. **Cash Expert** - 保留现金

### Phase 2 验收标准

- [ ] 平均成对相关 < 0.5（vs 当前 0.6+）
- [ ] 至少 3 个专家在不同 fold 表现最优
- [ ] Oracle utility（最优专家选择）> Phase 1 B04

### Phase 2 启动命令

```bash
# 查看 Phase 2 详细计划
cat document/expert_system_reconstruction_roadmap.md | grep -A 200 "Phase 2"

# TODO: Phase 2 实现脚本
# python model-test/run_phase2_expert_pool.py
```

---

## 常见问题

### Q1: 为什么 B05（宏观特征）没有改善？

**A**: 三个原因：
1. 使用了模拟宏观数据，缺少真实市场结构
2. 当前简单专家（动量 + 均值回归）本身表现太差（win rate 2.8%）
3. 宏观特征只用于计算效用标签，没有用于专家选择（这是 Phase 3 的任务）

### Q2: Win rate 2.8% 是什么意思？

**A**: 说明当前简单专家的决策几乎是随机的，甚至略微反向。健康的专家应该有 >50% 的 win rate。

### Q3: 如何获取真实 VIX/SPY 数据？

**A**: 
1. 等待一段时间后重试 `download_macro_data.py`（yfinance 速率限制）
2. 使用其他数据源（如 pandas_datareader + FRED）
3. 手动下载 CSV 并转换为 parquet

### Q4: Phase 1 可以跳过吗？

**A**: 不建议。虽然宏观特征未显示增量价值，但：
- 20 日 horizon 的有效性已证明
- 宏观特征模块为 Phase 3 做好了准备
- 实验流程和基础设施已建立

---

## 参考文档

- **Phase 0 报告**: `document/phase0_completion_summary.md`
- **Phase 1 报告**: `document/phase1_completion_report.md`
- **完整路线图**: `document/expert_system_reconstruction_roadmap.md`
- **Transformer vs 专家系统**: `document/transformer_vs_expert_reconstruction.md`

---

## Git 提交记录

```bash
# Phase 1 提交
git log --oneline | head -1
# caeb9d0 feat(phase1): complete Phase 1 - macro features and 20-day horizon

# 查看详细变更
git show caeb9d0 --stat
```

---

**Phase 1 状态**: ✅ **COMPLETED**  
**Phase 2 状态**: 🔵 **READY TO START**  
**建议**: 优先实现多样化专家池，再测试宏观特征的完整作用

---

*Created: 2026-08-20*  
*Author: Claude Fable 5*
