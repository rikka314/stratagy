# Phase 4: Cross-Fold Admission Testing - Completion Report

> 日期：2026-08-22  
> 状态：✅ 已完成  
> 目标：跨 fold 验证 Composite 策略的收益、回撤、换手和稳定性

## 1. 执行摘要

Phase 4 成功完成了跨 fold 准入测试框架的建设，包括：

- ✅ 完整的 fold 评估指标体系（30+ 指标）
- ✅ 多策略候选比较框架
- ✅ 准入门槛检查机制
- ✅ 质量阻断逻辑（数据质量/PIT/审计）
- ✅ 18 项测试全部通过

**核心成果**：建立了严格的跨 fold 验证管道，确保策略在多个时间段的稳定性和可重复性。

## 2. 评估指标体系

### 2.1 收益指标

| 指标 | 说明 |
|------|------|
| `total_return` | 净总收益（扣除成本后） |
| `net_return` | 同 total_return |
| `gross_return` | 毛收益（成本前） |

### 2.2 风险调整指标

| 指标 | 说明 |
|------|------|
| `sharpe_ratio` | 年化夏普比率 |
| `sortino_ratio` | 年化索提诺比率（仅考虑下行波动） |
| `annualized_volatility` | 年化波动率 |

### 2.3 回撤指标

| 指标 | 说明 |
|------|------|
| `max_drawdown` | 最大回撤（正值） |
| `max_drawdown_duration_days` | 最大回撤持续天数 |
| `recovery_time_days` | 从最大回撤恢复时间（None 表示未恢复） |

### 2.4 胜率指标

| 指标 | 说明 |
|------|------|
| `daily_win_rate` | 日频胜率 |
| `monthly_win_rate` | 月频胜率（可选） |

### 2.5 仓位暴露指标

| 指标 | 说明 |
|------|------|
| `mean_exposure` | 平均仓位 |
| `median_exposure` | 中位数仓位 |
| `max_exposure` | 最大仓位 |
| `near_zero_rate` | 仓位 ≤ 0.01 的比例 |
| `near_max_rate` | 仓位 ≥ 0.99 的比例（**饱和度指标**） |

### 2.6 执行统计

| 指标 | 说明 |
|------|------|
| `total_turnover` | 累计换手 |
| `daily_avg_turnover` | 日均换手 |
| `trade_count` | 交易次数 |
| `rebalance_count` | 实际调仓次数 |

### 2.7 成本指标

| 指标 | 说明 |
|------|------|
| `transaction_cost` | 总交易成本 |
| `cost_to_gross_ratio` | 成本/毛收益比率 |

### 2.8 Beta 指标（可选）

| 指标 | 说明 |
|------|------|
| `beta` | 整体 beta |
| `upside_beta` | 基准上涨时的 beta |
| `downside_beta` | 基准下跌时的 beta |

### 2.9 分数-收益关系

| 指标 | 说明 |
|------|------|
| `score_return_rank_ic` | Rank IC（Spearman 相关） |
| `score_return_spearman` | 同上 |
| `monotonicity_violations` | 单调性违反次数 |

### 2.10 质量标志

| 指标 | 说明 |
|------|------|
| `has_data_quality_issue` | 数据质量问题（重复日期、极端收益） |
| `has_pit_violation` | PIT 违规（未来数据泄漏） |
| `has_audit_failure` | 审计失败（equity/turnover/cost 重建不匹配） |
| `quality_notes` | 质量问题描述 |

## 3. 策略候选类型

### 3.1 基准策略

```python
StrategyVariant = Literal[
    "cash",                              # 现金基准（零仓位）
    "composite_only",                    # Phase 3 最佳 map 的 Composite
    "composite_equal_weight",            # 等权 Composite（无优化）
    "composite_no_interaction",          # 无交互项 Composite
]
```

### 3.2 Advisory 叠加策略

```python
    "composite_plus_trend",              # Composite + 趋势专家
    "composite_plus_reversion",          # Composite + 均值回归专家
    "composite_plus_macro_cap",          # Composite + 宏观风险上限
    "composite_plus_relative_strength",  # Composite + 相对强度
    "composite_plus_all_advisories",     # Composite + 所有 advisory
```

### 3.3 参考策略

```python
    "sm_reference",                      # SM / 已冻结参考策略
```

## 4. 准入门槛（AdmissionGate）

### 4.1 Fold 通过率

```python
min_fold_pass_rate: float = 0.75  # >= 3/4 folds 必须通过
```

### 4.2 收益门槛

```python
min_sharpe_ratio: float = 0.3      # 最低夏普比率
min_sortino_ratio: float = 0.4     # 最低索提诺比率
```

### 4.3 风险限制

```python
max_drawdown_threshold: float = 0.30   # 最大回撤上限
max_volatility: float = 0.40           # 最大波动率
```

### 4.4 执行限制

```python
max_cost_to_gross_ratio: float = 0.50      # 成本/毛收益上限
max_turnover_multiple: float = 50.0        # 相对基准的换手倍数
```

### 4.5 暴露合理性

```python
max_near_max_rate: float = 0.90      # 最大饱和率
min_mean_exposure: float = 0.05      # 最小平均仓位
```

### 4.6 质量要求

```python
allow_data_quality_issues: bool = False    # 不允许数据质量问题
allow_pit_violations: bool = False         # 不允许 PIT 违规
allow_audit_failures: bool = False         # 不允许审计失败
```

## 5. 准入判定逻辑

### 5.1 质量阻断（Blocked）

任何一个 fold 出现以下问题，策略状态为 **blocked**：

- 数据质量问题（且 `allow_data_quality_issues=False`）
- PIT 违规（且 `allow_pit_violations=False`）
- 审计失败（且 `allow_audit_failures=False`）

### 5.2 Fold 通过判定

单个 fold 通过需要满足所有条件：

- ✅ `sharpe_ratio >= min_sharpe_ratio`
- ✅ `sortino_ratio >= min_sortino_ratio`
- ✅ `max_drawdown <= max_drawdown_threshold`
- ✅ `annualized_volatility <= max_volatility`
- ✅ `cost_to_gross_ratio <= max_cost_to_gross_ratio`
- ✅ `near_max_rate <= max_near_max_rate`
- ✅ `mean_exposure >= min_mean_exposure`

### 5.3 策略通过判定（Pass）

- 通过的 fold 数量 / 总 fold 数量 >= `min_fold_pass_rate`（0.75）
- 即：**至少 3/4 folds 通过所有单 fold 条件**

### 5.4 策略失败（Fail）

- 无质量阻断，但通过率 < 75%

## 6. 核心函数

### 6.1 `evaluate_fold()`

评估单个 fold 的完整指标：

```python
def evaluate_fold(
    fold_id: str,
    df: pd.DataFrame,
    positions: pd.Series,
    returns: pd.Series,
    scores: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> FoldMetrics:
    """评估单个 fold，返回 30+ 指标."""
```

### 6.2 `check_admission()`

检查策略是否通过准入：

```python
def check_admission(
    candidate: StrategyCandidate,
    gate: AdmissionGate,
) -> tuple[Literal["pass", "fail", "blocked"], str]:
    """返回 (状态, 原因)."""
```

### 6.3 `aggregate_candidate_metrics()`

聚合跨 fold 的统计量：

```python
def aggregate_candidate_metrics(candidate: StrategyCandidate) -> None:
    """计算 mean/median/worst Sharpe, std, pass_rate 等."""
```

## 7. 输出文件

### 7.1 `fold_metrics.csv`

所有策略在所有 fold 的详细指标：

| 列 | 说明 |
|----|------|
| `strategy_variant` | 策略类型 |
| `fold_id` | Fold ID |
| `start_date` / `end_date` | 测试窗口 |
| `sharpe_ratio` | 夏普比率 |
| `max_drawdown` | 最大回撤 |
| ... | 30+ 指标 |

### 7.2 `admission_summary.csv`

策略级别的聚合结果和准入决策：

| 列 | 说明 |
|----|------|
| `strategy_variant` | 策略类型 |
| `total_folds` | 总 fold 数 |
| `folds_passed` | 通过的 fold 数 |
| `pass_rate` | 通过率 |
| `mean_sharpe` | 平均夏普 |
| `median_sharpe` | 中位数夏普 |
| `worst_sharpe` | 最差夏普 |
| `sharpe_std` | 夏普标准差 |
| `admission_status` | pass / fail / blocked |
| `admission_notes` | 准入原因 |

### 7.3 `phase4_manifest.json`

运行元数据：

```json
{
  "phase": "phase4_cross_fold_admission",
  "timestamp": "2026-08-22T...",
  "config": {...},
  "phase2_dir": "...",
  "phase3_dir": "...",
  "status": "ready",
  "total_folds": 4,
  "candidates_evaluated": 4,
  "candidates_passed": 2
}
```

## 8. Fold 配置

### 8.1 Purged Walk-Forward

每个 fold 包含：

- `train_start` / `train_end`：训练窗口
- `test_start` / `test_end`：测试窗口
- `purge_days`：训练结束和测试开始之间的清洗期（20 日）
- `embargo_days`：测试结束后的禁运期（20 日）

### 8.2 示例配置

```json
{
  "fold_id": "fold_01",
  "train_start": "2019-01-01",
  "train_end": "2020-09-30",
  "test_start": "2020-10-01",
  "test_end": "2021-12-31",
  "purge_days": 20,
  "embargo_days": 20
}
```

### 8.3 4 Folds 覆盖

- **Fold 01**: Train 2019-01 ~ 2020-09, Test 2020-10 ~ 2021-12
- **Fold 02**: Train 2019-06 ~ 2021-03, Test 2021-04 ~ 2022-06
- **Fold 03**: Train 2020-01 ~ 2021-09, Test 2021-10 ~ 2022-12
- **Fold 04**: Train 2020-06 ~ 2022-03, Test 2022-04 ~ 2023-06

## 9. 与计划文档的对应

| 计划项 | 实现状态 | 说明 |
|--------|---------|------|
| Cash baseline | ✅ | `evaluate_cash_baseline()` |
| Composite_only | ✅ | `evaluate_composite_only()` |
| Advisory overlays | 🟡 | 框架已建立，待实现具体 advisory |
| 简化 Composite | ✅ | `evaluate_equal_weight_composite()` |
| SM reference | 🟡 | 接口已定义，待接入 |
| 30+ fold 指标 | ✅ | `FoldMetrics` dataclass |
| Admission gate | ✅ | `check_admission()` |
| 质量阻断 | ✅ | `check_fold_quality()` |
| 跨 fold 聚合 | ✅ | `aggregate_candidate_metrics()` |
| ≥ 3/4 folds 准入 | ✅ | `min_fold_pass_rate=0.75` |

## 10. 测试覆盖

✅ **18 项测试全部通过**（1.56s）：

### 10.1 收益和成本（3 tests）

1. `test_compute_returns_and_equity_zero_position` - 零仓位零收益
2. `test_compute_returns_and_equity_constant_position` - 恒定仓位换手
3. `test_compute_returns_and_equity_varying_position` - 变化仓位成本

### 10.2 回撤统计（2 tests）

4. `test_compute_drawdown_stats_no_drawdown` - 无回撤场景
5. `test_compute_drawdown_stats_simple_drawdown` - 单次回撤恢复

### 10.3 风险调整指标（2 tests）

6. `test_compute_sharpe_sortino` - Sharpe/Sortino 计算
7. `test_compute_sharpe_sortino_all_positive_returns` - 全正收益

### 10.4 Beta 计算（2 tests）

8. `test_compute_beta_perfect_correlation` - 完全相关 beta=1
9. `test_compute_beta_zero_correlation` - 无相关 beta≈0

### 10.5 Rank IC（1 test）

10. `test_compute_rank_ic` - 分数-收益相关性

### 10.6 质量检查（3 tests）

11. `test_check_fold_quality_clean_data` - 干净数据
12. `test_check_fold_quality_duplicate_dates` - 检测重复日期
13. `test_check_fold_quality_extreme_returns` - 检测极端收益

### 10.7 Fold 评估（1 test）

14. `test_evaluate_fold_basic` - 基础 fold 评估

### 10.8 准入检查（3 tests）

15. `test_check_admission_pass` - 通过场景（4/4 folds 通过）
16. `test_check_admission_fail_low_pass_rate` - 失败场景（通过率不足）
17. `test_check_admission_blocked_data_quality` - 阻断场景（数据质量问题）

### 10.9 聚合统计（1 test）

18. `test_aggregate_candidate_metrics` - 跨 fold 聚合

## 11. 代码结构

```
model-test/
├── model_test/
│   ├── cross_fold_admission.py           # 核心模块（600+ 行）
│   └── position_map_research.py          # Phase 3 依赖
├── configs/
│   └── composite_stability_phase4.json   # Phase 4 配置
├── run_composite_stability_phase4.py     # 主运行脚本（350+ 行）
tests/
└── test_cross_fold_admission.py          # 测试套件（18 tests）
```

## 12. 关键设计决策

### 12.1 为什么是 ≥ 3/4 folds 准入？

- **目标**：证明策略在多个时间段稳定，而非单个样本曲线拟合
- **标准**：至少 75% 的 folds 通过所有门槛
- **容错**：允许 1 个 fold 失败，但不能是质量问题

### 12.2 为什么区分 blocked / fail？

- **blocked**：数据质量/PIT/审计问题，不能作为有效证据
- **fail**：策略本身不满足门槛，但数据和流程正确
- **pass**：策略和数据都通过

### 12.3 为什么先做 composite_only？

遵循计划文档的分阶段验证：

1. 先证明 `composite_only` 可重复
2. 再叠加 advisory，证明增量价值
3. 最后与 SM 等参考策略对比

### 12.4 为什么 worst_sharpe 也重要？

- 平均值提升不足以准入
- 最差 fold 不能出现灾难性表现
- 稳健性比单点最优更重要

## 13. 与 Phase 3 的关系

| Phase 3 | Phase 4 |
|---------|---------|
| 单标的/聚合测试 | 跨 fold 验证 |
| 选择最佳 map | 使用冻结 map |
| Train-only fit | 每个 fold 独立 fit/transform |
| 饱和度 gate (90%) | 饱和度作为准入指标之一 |
| Ablation 比较 | 策略候选比较 |

**继承**：Phase 4 使用 Phase 3 选定的最佳 position map 和 execution config。

**新增**：Phase 4 增加了跨 fold 稳定性、质量阻断、准入门槛等维度。

## 14. 下一步（Phase 5）

**前置条件**：Phase 4 的 US `composite_only` 通过准入

**Phase 5 任务**：CN_A 市场复制

1. 使用 `MarketFactorContext` 的显式 benchmark/universe
2. 替换所有 SPY/VIX 为 market-native factors
3. 重新做 Phase 1-4 的完整流程
4. 分市场生成 source lock 和 admission report
5. **不把 US 权重直接复制到 CN_A**

## 15. 已知限制

### 15.1 当前为单标的聚合

- `run_composite_stability_phase4.py` 对多标的取日均值
- 真实场景需要按标的独立执行，再汇总组合表现

### 15.2 Advisory 策略未实现

- 框架已建立，但 `composite_plus_*` 变体需要接入实际 advisory 逻辑
- 需要从 `core/composite_advisory.py` 读取 overlay 规则

### 15.3 SM 参考策略未接入

- 接口已定义，但需要从历史 run 读取 SM 的 daily position 和 return

### 15.4 Beta 计算需要 benchmark

- 当前 `benchmark_returns` 为可选参数
- US 可使用 SPY，CN_A 需要使用沪深 300 或其他基准

### 15.5 Monthly 胜率未实现

- `monthly_win_rate` 当前为 None
- 需要对 returns 做月频 resampling

## 16. 使用示例

### 16.1 运行 Phase 4

```bash
cd model-test
python run_composite_stability_phase4.py --config configs/composite_stability_phase4.json
```

### 16.2 检查输出

```bash
ls outputs/composite_stability_phase4/
# fold_metrics.csv
# admission_summary.csv
# phase4_manifest.json
```

### 16.3 查看准入结果

```bash
cat outputs/composite_stability_phase4/admission_summary.csv
```

示例输出：

| strategy_variant | folds_passed | pass_rate | mean_sharpe | admission_status |
|------------------|--------------|-----------|-------------|------------------|
| cash | 0 | 0.00 | 0.00 | fail |
| composite_only | 3 | 0.75 | 0.65 | pass |
| composite_equal_weight | 2 | 0.50 | 0.45 | fail |
| composite_no_interaction | 3 | 0.75 | 0.60 | pass |

## 17. 质量保证

### 17.1 输入验证

- Phase 2 manifest 状态必须为 `ready` 或 `ready_with_gaps`
- Phase 3 manifest 必须存在
- 数据必须包含 `date` / `return` 列
- Fold 日期必须在数据范围内

### 17.2 输出验证

- 所有 fold 指标必须有限（非 NaN/Inf）
- Turnover 和 cost 必须非负
- Position 必须在 [0, 1] 范围内（long-only）
- Equity curve 必须可重建

### 17.3 一致性检查

- `net_return = gross_return - transaction_cost`
- `cost_to_gross_ratio = transaction_cost / gross_return`
- `total_turnover = sum(abs(position_changes))`

## 18. 总结

Phase 4 成功建立了跨 fold 准入测试框架：

✅ **已完成**：
- 30+ fold 评估指标
- 多策略候选比较
- ≥ 3/4 folds 准入逻辑
- 质量阻断机制
- 18 项测试覆盖

🎯 **核心价值**：
- 证明策略可重复性，而非单个样本过拟合
- 区分数据问题和策略问题
- 为 advisory overlay 和跨市场复制提供严格基准

📋 **下一步**：
- 实际运行 Phase 4，生成 admission results
- 若 `composite_only` 通过，接入 advisory 策略
- 若 US 全部通过，启动 CN_A Phase 5 复制
