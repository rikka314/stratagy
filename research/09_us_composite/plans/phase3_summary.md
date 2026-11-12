# Composite Stability Research Plan - Phase 3 完成总结

> 日期：2026-08-22  
> 状态：✅ Phase 3 框架完成  
> 下一步：实际运行生成 ablation results，验证饱和度 gate

## Phase 3 完成清单

### ✅ 核心模块实现

1. **position_map_research.py** (420 行)
   - `PositionMapConfig`：4 种映射方法的参数化配置
   - `PositionMapResult`：训练后的映射器，包含 fitted 参数
   - `ExecutionConstraints`：执行层约束（no-trade band、cadence、delta limits）
   - `fit_position_map()`：train-only 参数拟合
   - `compute_diagnostics()`：完整诊断指标计算
   - `run_position_map_ablation()`：全网格搜索主函数

2. **run_composite_stability_phase3.py** (280 行)
   - 加载 Phase 2 冻结权重
   - 计算 composite score
   - Train/test 分割
   - 调用 ablation 主函数
   - 生成 manifest 和决策报告

3. **composite_stability_phase3.json**
   - Phase 2 依赖路径
   - Map/execution/cost 配置
   - 饱和度 gate 阈值

4. **test_position_map_research.py**
   - 12 项测试全部通过
   - 覆盖所有 4 种 map 的 fit/transform
   - 覆盖所有执行约束
   - 验证诊断指标计算
   - 验证配置参数检查

### ✅ 文档交付

1. **phase3_position_mapping_completion_report.md**
   - 14 章完整报告
   - 实现原理、设计决策、已知限制

2. **PHASE3_README.md**
   - 快速启动指南
   - 配置说明
   - 输出文件格式
   - 常见问题排查

3. **AI_CONTEXT.md 更新**
   - 记录 Phase 3 完成状态

## Phase 3 核心价值

### 1. 解决 Phase 1 饱和问题

**Phase 1 发现**：
- `composite_base_position > 0.99` 约为 99.56%
- 近似恒定满仓，失去仓位信号辨识度

**Phase 3 解决方案**：
- 4 种 position map 控制饱和度
- 饱和度 gate: `near_max_rate <= 90%`
- 保留足够的仓位动态范围

### 2. 建立统一执行框架

**执行约束**：
- No-trade band：过滤小幅波动
- Rebalance cadence：控制调仓频率
- Delta limits：限制单日最大变化

**优势**：
- `composite_only` 和 advisory 使用相同约束
- 换手和成本可对比
- Advisory overlay 效果可解释

### 3. 成本敏感性分析

**三级成本测试**：
- Base (1.0x)：标准成本假设
- 2x：保守成本假设
- 4x：极端成本假设

**选择原则**：
- 在 base 和 2x cost 下均表现良好
- Worst-case 不出现灾难性退化
- 不只看 pooled Sharpe 最高者

### 4. Train-Only Fit 范式

**所有参数在训练集估计**：
- Quantile 断点
- Volatility median
- Monotone calibration knots

**验证/测试集只 transform**：
- 避免前视偏差
- 符合生产部署语义
- 无偏估计未来性能

## 4 种 Position Map 对比

| Map | 优势 | 适用场景 | 参数数量 |
|-----|------|---------|---------|
| **Quantile 5-bin** | 最可解释、饱和可控 | 首选基准 | 2（位置数组） |
| **Dead-zone softsign** | 易控制斜率、过滤噪声 | 与 Phase 2.5 一致 | 3（threshold/scale/p_max） |
| **Vol-target** | 风险调整、自动降低高波动 exposure | 多资产组合 | 2（target_vol/window） |
| **Monotone calibrated** | 直接校准到收益 | 非线性关系 | 1（increasing） |

## 待完成工作

### Phase 3 实际运行

**前置条件**：
- Phase 2 已完成，manifest 状态为 `ready`
- 因子数据覆盖训练和测试期

**运行命令**：
```bash
python model-test/run_composite_stability_phase3.py \
  --config model-test/configs/composite_stability_phase3.json
```

**预期输出**：
- `position_map_ablation.csv`：~60 行（5 maps × 4 executions × 3 costs）
- `cost_sensitivity.csv`：最佳 map 的成本曲线
- `mapping_decision.md`：决策报告
- `manifest.json`：包含饱和度 gate 结果

### 饱和度 Gate 验证

**检查命令**：
```bash
cat model-test/outputs/phase3_*/manifest.json | jq '.best_result.near_max_rate'
```

**通过标准**：`<= 0.90`

**如果未通过**：
1. 调整 dead_zone_softsign 参数（增大 threshold/scale）
2. 强制使用 quantile_5bin
3. 检查 Phase 2 权重是否合理

### Phase 4 准备

**Phase 4 任务**：跨 fold 收益、回撤、换手和稳定性准入

**输入**：
- Phase 3 选定的最佳 map + execution config
- Phase 2 的多个 purged folds

**对比**：
- `composite_only` vs `composite_plus_*` advisory candidates
- 要求至少 3/4 folds 通过预注册门槛

## 与计划文档的一致性

参考 `document/composite_stability_research_plan.md` Phase 3 部分：

| 计划项 | 状态 | 说明 |
|--------|------|------|
| Quantile/分段映射 | ✅ | `quantile_5bin` |
| Dead-zone softsign | ✅ | 2 种参数变体 |
| Vol-target | ✅ | 20 日滚动波动率 |
| Monotone calibrated | ✅ | Isotonic regression |
| No-trade band | ✅ | 参数化配置 |
| Rebalance cadence | ✅ | 1/3/5 天候选 |
| Delta limits | ✅ | 增仓/减仓分别限制 |
| Cost sensitivity | ✅ | base/2x/4x |
| Train-only fit | ✅ | 所有 map 符合 |
| Saturation gate | ✅ | near_max_rate <= 0.90 |
| Daily position audit | 🟡 | 框架就绪，待 run 生成 |
| Execution constraint ablation | ✅ | 4 种 execution configs |
| Mapping decision report | ✅ | 自动生成 |

## 关键设计决策回顾

### 1. 为什么不只用 tanh？

Phase 2.5 的优化器使用了 `score_std` + `tanh`，但存在问题：
- 训练集 `score_std` 不能直接用于测试集
- tanh 饱和速度难以控制
- 缺少死区机制

Phase 3 的 dead-zone softsign：
- 参数简单（threshold + scale）
- 死区过滤噪声
- 中间段和尾部斜率分离控制

### 2. 为什么需要 4 种 map？

不同 map 适合不同假设：
- **Quantile**：分布自适应，最稳健
- **Dead-zone**：与优化器一致，易调参
- **Vol-target**：风险调整，理论基础
- **Monotone**：直接校准，非线性友好

多方法对比 → 选择稳健者 → 避免过拟合单一 map

### 3. 为什么同时测试多种执行约束？

同一个 map 在不同约束下表现差异巨大：
- 紧 band (0.02) + 日频 → 高换手
- 宽 band (0.05) + 低频 (5 天) → 低换手

需要找到"多成本场景下均稳健"的配置

## 测试覆盖总结

**12 passed：**
1. Quantile map fit/transform
2. Dead-zone softsign（验证负分数 → 0）
3. Vol-target map
4. Monotone calibrated map
5. No-trade band 约束
6. Delta limits 约束
7. Rebalance cadence 约束
8. 基础诊断指标
9. 零换手场景
10. 配置参数验证
11. 映射单调性
12. 饱和度检测

**覆盖范围**：
- ✅ 所有 4 种 map 的 fit/transform
- ✅ 所有 3 种执行约束
- ✅ 诊断指标计算正确性
- ✅ 边界条件（零换手、饱和、负分数）
- ✅ 参数验证

## 后续里程碑

```
Phase 3 框架完成 (2026-08-22) ✅
  ↓
Phase 3 实际运行 (待执行)
  ↓
饱和度 gate 验证 (near_max_rate <= 0.90)
  ↓
选择最佳 map + execution
  ↓
Phase 4: 跨 fold 验证 (待实现)
  ↓
Advisory vs composite_only 对比
  ↓
Admission decision
```

## 交付清单

### 代码模块
- ✅ `model-test/model_test/position_map_research.py`
- ✅ `model-test/run_composite_stability_phase3.py`
- ✅ `model-test/configs/composite_stability_phase3.json`
- ✅ `tests/test_position_map_research.py`

### 文档
- ✅ `document/phase3_position_mapping_completion_report.md` (14 章)
- ✅ `document/PHASE3_README.md` (快速启动指南)
- ✅ `document/composite_stability_research_plan.md` (Phase 3 部分对应)
- ✅ `AI_CONTEXT.md` 更新

### 测试
- ✅ 12/12 tests passed
- ✅ 覆盖所有核心功能

## 结论

Phase 3 框架已完整建立，包括：
- 4 种可解释、可控饱和的 position map
- 参数化的执行约束体系
- 完整的诊断指标和成本敏感性分析
- Train-only fit 的规范流程
- 12 项测试验证

**下一步**：实际运行 Phase 3，验证饱和度 gate，选择最佳配置，进入 Phase 4 跨 fold 验证。
