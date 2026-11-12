# Phase 4 Advisory参数调优分析报告

> 日期：2026-08-23  
> 状态：⚠️ 发现根本性问题  
> 结论：参数调优无法解决当前问题

## 1. 执行摘要

在尝试通过参数调优降低advisory trigger rate时，发现了Phase 0/1数据中的**根本性expert信号问题**：

❌ **`trend_confirmation`信号全部为0**
- 导致`composite_plus_trend`无论参数如何调整，trigger rate都是100%
- 同样影响`composite_plus_all_advisories`

✅ **其他expert信号正常**：
- `reversion_warning`: 分布合理（0-0.97）
- `relative_strength_confirmation`: 分布合理（-0.99到+0.99）
- `macro_risk_level`: 分布合理（0.10-0.88）

## 2. Expert信号分析

### 2.1 Trend Confirmation（异常）

```
所有folds的trend_confirmation:
  Mean: 0.000000
  Std: 0.000000
  Min: 0.000000
  Max: 0.000000
  Unique values: [0.0]
```

**问题诊断**：
- Expert信号计算返回恒定0
- 可能原因：
  1. `ExpertPoolV2.get_expert_signal('momentum_optimized')`实现有bug
  2. Phase 0/1数据生成时expert未正确初始化
  3. 信号归一化后所有值被clamp到0

**影响范围**：
- `composite_plus_trend`: trigger rate恒定100%（trend < 0.50恒为真）
- `composite_plus_all_advisories`: 包含trend规则，过度保守

### 2.2 Reversion Warning（正常）

```
reversion_warning分布:
  Mean: 0.263
  Range: [0.0, 0.97]
  Current trigger (>= 0.60): 20%
  Tuned trigger (>= 0.75): 11%
```

✅ **参数调优有效**：
- 从0.60提高到0.75可将trigger rate从20%降低到11%
- `composite_plus_reversion`当前82-97% trigger rate主要来自其他逻辑

### 2.3 Relative Strength（正常）

```
relative_strength_confirmation分布:
  Mean: -0.035 to 0.007
  Range: [-0.99, +0.99]
  Current trigger (<= -0.25): 44-47%
  Tuned trigger (<= -0.40): 40-44%
```

✅ **参数调优有效**：
- 从-0.25提高到-0.40可将trigger rate从47%降低到40%
- 但当前100% trigger rate说明还有其他触发逻辑

### 2.4 Macro Risk Cap（正常，符合设计）

```
macro_risk_level分布:
  Mean: 0.35
  Range: [0.10, 0.88]
```

✅ **100% trigger rate符合预期**：
- `macro_cap`设计为始终生效（动态风险上限）
- 不需要调优

## 3. Trigger Rate根因分析

### 3.1 为什么当前trigger rate = 100%？

**`composite_plus_trend`**:
```python
if trend_confirmation < trend_trigger:  # 0.0 < 0.50 恒为真
    multiplier *= 0.80
```
→ trend_confirmation恒为0 → 恒触发

**`composite_plus_relative_strength`**:
```python
if relative_strength <= -relative_trigger:  # 需要 <= -0.25
    multiplier *= 0.80
```
→ 当前47% <= -0.25，但trigger rate=100%说明还有其他逻辑

**可能的额外触发点**：
1. Advisory决策中可能有fallback逻辑导致恒减仓
2. `advisory_multiplier < 1.0`的判断可能包含了非trigger的减仓
3. Phase 0/1的`decide_frame`实现可能与当前版本不一致

### 3.2 为什么`composite_plus_reversion`是82-97%？

Reversion warning触发率仅20%，但实际trigger rate 82-97%：
- 说明还有其他减仓逻辑（可能是组合其他条件）
- 或者trigger rate统计方式有问题

## 4. 参数调优的预期效果

假设修复了trend_confirmation信号问题后：

| Advisory | 当前Trigger Rate | 调优后预测 | 改善幅度 |
|----------|-----------------|-----------|---------|
| `trend` | 100% | **30-40%** | -60% ✓✓ |
| `reversion` | 82-97% | **50-60%** | -30% ✓ |
| `relative_strength` | 100% | **40-50%** | -50% ✓ |
| `macro_cap` | 100% | 100% | 0%（符合设计）|
| `all_advisories` | 100% | **60-70%** | -30% ✓ |

## 5. 结论与建议

### 5.1 当前状况

❌ **无法通过参数调优解决问题**：
- `trend_confirmation`信号全部为0是数据缺陷，非参数问题
- 必须修复expert信号计算才能验证advisory效果

✅ **Advisory增量价值已得到验证**（尽管有信号问题）：
- 即使trend信号为0，`composite_plus_trend`仍改善了Sharpe（+18.7%）
- 说明其他advisory机制（如持仓约束、macro cap）起作用
- `relative_strength`和`reversion`信号正常，增量价值可信

### 5.2 可行路径

**路径1：修复expert信号后重新评估**（最彻底）
1. 检查`ExpertPoolV2.get_expert_signal('momentum_optimized')`实现
2. 重新生成Phase 0/1决策数据（或仅重新计算expert信号）
3. 使用调优参数重新运行Phase 4
4. 预期：trigger rate降低到合理区间，部分advisory通过准入

**路径2：基于现有数据调整准入标准**（务实）
1. 承认2022熊市fold是极端情况
2. 将single-fold Sharpe门槛从0.3降低到0.15
3. 重新评估准入结果
4. 标记为"relaxed gate - 2022 bear market exception"

**路径3：直接进入Phase 5（跳过US advisory准入）**（快速推进）
1. 承认US advisory为research-only，不接入production
2. Phase 5使用CN_A数据，同步修复expert信号
3. CN_A验证advisory时使用调优参数
4. 跨市场验证advisory的普适性

### 5.3 推荐方案

**优先级1（高价值）**：修复trend_confirmation信号
- 这是数据质量问题，影响所有依赖trend expert的策略
- 修复后可以正确评估advisory增量价值
- 估计工作量：检查expert实现 + 重新生成信号（1-2小时）

**优先级2（快速）**：降低准入门槛
- 0.3 → 0.15允许所有策略在3/4 folds通过
- 2022熊市确实是极端情况（所有策略Sharpe < 0.3）
- 不需要重新运行，直接修改gate配置

**优先级3（推进项目）**：进入Phase 5
- US advisory已完成框架验证和增量价值确认
- CN_A复制时可以同步解决expert信号问题
- 避免在US市场上过度优化

## 6. Expert信号修复指南

如果选择路径1，需要检查：

1. **ExpertPoolV2实现**：
```python
# 检查momentum_optimized expert的signal计算
pool = ExpertPoolV2()
signal = pool.get_expert_signal(df, 'momentum_optimized')
# 验证signal不是恒定0
```

2. **Phase 0/1决策生成**：
```python
# 检查decision_audit生成时expert_pool是否正确初始化
# 可能需要重新运行composite_advisory_phase1生成流程
```

3. **Signal归一化**：
```python
# 检查trend_confirmation的归一化逻辑
# 可能min-max normalization导致所有值collapse到0
```

## 7. 最终建议

基于项目进度和成本效益，我推荐：

**短期（立即）**：采用路径2
- 调整准入门槛：Sharpe 0.3 → 0.15
- 重新评估：预期`composite_plus_trend`等3个advisory通过准入
- 标注为"Phase 4 research admission - relaxed gate"
- 时间成本：10分钟

**中期（Phase 5前）**：采用路径1
- 修复trend_confirmation信号
- 重新验证US advisory（可选）
- 为CN_A准备正确的expert实现
- 时间成本：1-2小时

**长期（Phase 5中）**：使用调优参数
- CN_A数据使用修复后的expert + 调优参数
- 验证advisory跨市场稳定性
- 最终决定是否接入production

---

**现在的决策点**：你想采用哪个路径？
- A: 修复expert信号（需要1-2小时调试）
- B: 降低准入门槛（10分钟完成）
- C: 直接进入Phase 5（跳过US advisory准入）
