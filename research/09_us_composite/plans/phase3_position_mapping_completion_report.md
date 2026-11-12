# Phase 3: Position Mapping and Execution Constraints - Completion Report

> 日期：2026-08-22  
> 状态：✅ 已完成  
> 目标：解决饱和、抖动和成本侵蚀问题，建立统一的仓位映射和执行约束框架

## 1. 执行摘要

Phase 3 成功完成了仓位映射和执行约束的研究框架建设，包括：

- ✅ 4 种仓位映射方法的实现和对比框架
- ✅ 多维度执行约束的参数化配置
- ✅ 成本敏感性分析（base、2x、4x）
- ✅ 完整的诊断指标体系
- ✅ 12 项测试全部通过

**核心成果**：建立了训练/测试分离、参数化配置、可复现的仓位映射研究管道。

## 2. 实现的仓位映射方法

### 2.1 Quantile 5-Bin Map

**原理**：
- 在训练集上估计 score 的分位数断点（0%, 35%, 60%, 80%, 100%）
- 将分位数映射到固定的仓位水平（0.0, 0.25, 0.50, 0.75, 1.0）
- 测试集使用训练断点进行线性插值

**优势**：
- 解释性强，饱和可控
- 对训练集和测试集分布差异有一定鲁棒性
- 仓位分布均匀，避免极端饱和

**实现**：
```python
@dataclass(frozen=True)
class PositionMapConfig:
    variant: MapVariant = "quantile_5bin"
    quantiles: tuple[float, ...] = (0.0, 0.35, 0.60, 0.80, 1.0)
    positions: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75, 1.0)
```

### 2.2 Dead-Zone Softsign Map

**原理**：
- 使用 softsign 函数：`p = p_max * max(s - τ, 0) / (k + max(s - τ, 0))`
- `τ` 为死区阈值，负分数和低分数映射为 0
- `k` 控制曲线斜率，避免 tanh 的过快饱和

**优势**：
- 比 tanh 更易控制中间段和尾部斜率
- 死区机制天然过滤噪声信号
- 参数简单，只需调整 threshold 和 scale

**实现**：
```python
PositionMapConfig(
    variant="dead_zone_softsign",
    threshold=0.25,  # 死区阈值
    scale=1.0,       # 斜率控制
)
```

### 2.3 Volatility-Targeted Map

**原理**：
- 计算训练集滚动波动率（20 日窗口）
- 目标仓位 = alpha_score / forecast_volatility
- 训练集统计 median volatility 作为测试集缺失值填充

**优势**：
- 风险调整后的仓位
- 高波动期自动降低 exposure
- 适合多资产组合

**实现**：
```python
PositionMapConfig(
    variant="vol_target",
    target_vol=0.15,
    vol_window=20,
)
```

### 2.4 Monotone Calibrated Map

**原理**：
- 使用 sklearn IsotonicRegression 在训练集上拟合 score → future_return 的单调映射
- 提取拟合的 knots (x_knots, y_knots)
- 测试集使用 knots 进行线性插值
- 将校准后的 return 映射为仓位（简单线性缩放）

**优势**：
- 直接校准到未来收益
- 单调性保证 score 方向一致性
- 适合非线性关系

**实现**：
```python
PositionMapConfig(
    variant="monotone_calibrated",
    increasing=True,
    calibration_clip=(-0.5, 0.5),
)
```

## 3. 执行约束框架

### 3.1 No-Trade Band

**作用**：只有当目标仓位与当前仓位差距超过阈值时才执行调仓

```python
if abs(target - prev) < no_trade_band:
    exec_position = prev  # 不调仓
```

**典型值**：0.02（2%）、0.05（5%）

### 3.2 Rebalance Cadence

**作用**：限制最小调仓间隔，降低交易频率

```python
if days_since_last_rebalance < rebalance_cadence_days:
    exec_position = prev  # 保持当前仓位
```

**典型值**：1、3、5 个交易日

### 3.3 Delta Limits

**作用**：限制单日最大仓位变化，避免剧烈调仓

```python
if delta > 0:
    delta = min(delta, max_daily_delta_increase)
else:
    delta = max(delta, -max_daily_delta_decrease)
```

**典型值**：
- 增仓上限：0.10（10%）、0.20（20%）
- 减仓上限：0.15（15%）、0.20（20%）

### 3.4 组合约束示例

```python
ExecutionConstraints(
    no_trade_band=0.05,
    max_daily_delta_increase=0.10,
    max_daily_delta_decrease=0.15,
    rebalance_cadence_days=3,
)
```

## 4. 诊断指标体系

### 4.1 Score 分布
- `score_min/median/max/std`：分数分布统计

### 4.2 Position 分布
- `near_zero_rate`：仓位 ≤ 0.01 的比例
- `near_max_rate`：仓位 ≥ 0.99 的比例（**饱和度指标**）
- `mean_exposure`：平均仓位
- `median_exposure`：中位数仓位
- `position_unique_count`：唯一仓位值数量

### 4.3 执行统计
- `total_turnover`：累计换手
- `daily_avg_turnover`：日均换手
- `trade_count`：交易次数
- `rebalance_count`：实际调仓次数

### 4.4 绩效指标
- `gross_return`：毛收益
- `net_return`：净收益（扣除成本）
- `transaction_cost`：总交易成本
- `cost_to_gross_ratio`：成本/毛收益比率
- `sharpe_ratio`：夏普比率
- `max_drawdown`：最大回撤
- `volatility`：年化波动率

## 5. 成本敏感性分析

对每个（map, execution, cost_multiplier）组合计算诊断指标：

```python
cost_multipliers = [1.0, 2.0, 4.0]  # base, 2x, 4x

for cost_mult in cost_multipliers:
    cost_rate = (base_commission + base_slippage) * cost_mult
    costs = position_changes * cost_rate
    net_returns = strategy_returns - costs
```

**分析目标**：
- 在 base cost 下表现良好
- 在 2x/4x cost 下不出现灾难性退化
- 优先选择 worst-case 稳健的 map

## 6. 研究管道

### 6.1 输入
- Phase 2 冻结权重（`weight_paths.parquet`）
- 因子数据（`data/demo_factors_output.parquet`）
- 配置文件（`composite_stability_phase3.json`）

### 6.2 流程
1. 加载 Phase 2 最佳权重（取中位数稳定权重）
2. 计算 composite score
3. 分割 train/test（按日期）
4. 对每个 map config：
   - 在 train 上 fit 参数
   - 在 test 上 transform
5. 对每个 execution config：
   - 应用执行约束
   - 模拟真实调仓过程
6. 对每个 cost multiplier：
   - 计算诊断指标
   - 输出到 ablation CSV

### 6.3 输出
- `position_map_ablation.csv`：全部组合的诊断结果
- `cost_sensitivity.csv`：最佳 map 的成本敏感性
- `mapping_decision.md`：决策报告
- `manifest.json`：运行元数据

## 7. 饱和度 Gate

**阈值**：`near_max_position_rate <= 90%`

**判定逻辑**：
```python
saturation_gate_pass = manifest['best_result']['near_max_rate'] <= 0.90
```

**作用**：
- Phase 1 发现 composite_base_position > 0.99 约为 99.56%，几乎恒定满仓
- Phase 3 通过 quantile 或 dead-zone map 控制饱和率
- 只有通过此 gate，才能进入 Phase 4 跨 fold 验证

## 8. 测试覆盖

✅ 12 项测试全部通过：

1. **test_quantile_map_fit_transform**：分位数映射的训练/测试流程
2. **test_dead_zone_softsign_map**：死区 softsign 映射，验证负分数映射为 0
3. **test_vol_target_map**：波动率目标映射
4. **test_monotone_calibrated_map**：单调校准映射
5. **test_execution_constraints_no_trade_band**：no-trade band 约束
6. **test_execution_constraints_delta_limits**：delta 上限约束
7. **test_execution_constraints_rebalance_cadence**：调仓频率约束
8. **test_compute_diagnostics_basic**：基础诊断指标计算
9. **test_compute_diagnostics_zero_turnover**：零换手场景验证
10. **test_position_map_config_validation**：配置参数验证
11. **test_map_monotonicity**：映射单调性验证
12. **test_saturation_detection**：饱和度检测

## 9. 代码结构

```
model-test/
├── model_test/
│   └── position_map_research.py      # 核心实现（420 行）
├── configs/
│   └── composite_stability_phase3.json   # 配置文件
├── run_composite_stability_phase3.py     # 主运行脚本（280 行）
tests/
└── test_position_map_research.py         # 测试套件（12 tests）
```

## 10. 与计划文档的对应

| 计划项 | 实现状态 | 说明 |
|--------|---------|------|
| Quantile/分段映射 | ✅ | `quantile_5bin` |
| Dead-zone softsign | ✅ | `dead_zone_softsign` |
| Vol-target map | ✅ | `vol_target` |
| Monotone calibrated map | ✅ | `monotone_calibrated` |
| No-trade band | ✅ | `ExecutionConstraints.no_trade_band` |
| Rebalance cadence | ✅ | `rebalance_cadence_days` |
| Delta limits | ✅ | `max_daily_delta_increase/decrease` |
| Cost sensitivity (base/2x/4x) | ✅ | `cost_multipliers = [1.0, 2.0, 4.0]` |
| Train-only fit | ✅ | `fit_position_map()` 只用 train 数据 |
| Saturation gate | ✅ | `near_max_rate <= 0.90` |
| Daily position audit | 🟡 | 框架已建立，待实际 run 生成 |
| Mapping decision report | ✅ | `mapping_decision.md` 自动生成 |

## 11. 下一步（Phase 4）

**前置条件**：Phase 3 实际运行并通过饱和度 gate

**Phase 4 任务**：跨 fold 收益、回撤、换手和稳定性准入
- 使用 Phase 3 选定的最佳 map + execution config
- 在多个 purged folds 上验证
- 比较 `composite_only` vs advisory candidates
- 要求至少 3/4 folds 通过预注册门槛
- 最差 fold 不得出现 data quality/PIT/audit failure

## 12. 关键设计决策

### 12.1 为什么是 4 种 map？

- **Quantile**：最简单、最可解释、饱和可控
- **Dead-zone softsign**：相比 tanh 更易控制，与 Phase 2.5 优化器一致
- **Vol-target**：风险调整，适合多资产
- **Monotone calibrated**：直接校准到收益，适合非线性

### 12.2 为什么 train-only fit？

- 避免前视偏差
- 符合生产部署语义：只能用历史数据估计参数
- 测试集性能是对未来的无偏估计

### 12.3 为什么关注饱和度？

Phase 1 audit 发现：
- `composite_base_position > 0.99` 约为 99.56%
- 近似恒定满仓，失去仓位信号的辨识度
- advisory 的高换手来自饱和后的频繁压低/恢复

Phase 3 目标：
- 控制 `near_max_rate <= 90%`
- 保留足够的仓位动态范围
- 使 advisory overlay 的效果可解释

### 12.4 为什么同时测试多个 execution config？

- No-trade band 和 rebalance cadence 会显著影响换手和成本
- 同一个 map 在不同约束下表现差异很大
- 需要找到"在多种成本假设下都稳健"的配置

## 13. 已知限制

1. **当前为单标的聚合**：
   - `run_composite_stability_phase3.py` 对多标的取日均值
   - 真实场景需要按标的独立执行，再汇总组合表现

2. **Vol-target 简化**：
   - 使用滚动历史波动率，未考虑条件异方差模型（GARCH）
   - 未考虑相关性和组合效应

3. **Monotone calibrated 简化**：
   - 校准到 return 后，使用简单线性缩放映射为仓位
   - 可改进为直接校准 score → optimal_position

4. **执行仓位模拟**：
   - 假设完全成交，未考虑流动性约束
   - 未考虑市场冲击和 slippage 的非线性

## 14. 总结

Phase 3 成功建立了完整的仓位映射和执行约束研究框架：

✅ **已完成**：
- 4 种 position map 的实现和对比
- 参数化的执行约束
- 成本敏感性分析
- 完整的诊断指标
- 12 项测试覆盖

🎯 **核心价值**：
- 解决 Phase 1 发现的饱和问题
- 建立 train-only fit 的规范流程
- 为 Phase 4 跨 fold 验证提供统一 map

📋 **下一步**：
- 实际运行 Phase 3，生成 ablation results
- 选择通过饱和度 gate 的最佳配置
- 进入 Phase 4 跨 fold 验证
