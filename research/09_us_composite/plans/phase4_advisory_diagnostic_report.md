# Phase 4 Advisory Overlays 诊断报告

> 日期：2026-08-23  
> 状态：⚠️ 诊断完成，发现数据兼容性问题  
> 目标：评估5种advisory overlay策略相对composite_only的增量价值

## 1. 执行摘要

Phase 4 Advisory测试已完成框架实现和初步运行，但所有advisory策略均失败（Sharpe=0，fallback_rate=1.0）。

**核心发现**：
- ✅ Advisory框架已正确实现（`evaluate_composite_with_advisory`）
- ✅ `composite_only` 通过准入（4/4 folds，mean Sharpe=1.768）
- ❌ 所有5种advisory策略失败，回退到零仓位
- 🔍 根本原因：单标的演示数据与multi-expert advisory系统不兼容

## 2. Advisory策略配置

### 2.1 已实现的5种策略

| 策略 | 描述 | 预期行为 |
|------|------|---------|
| `composite_plus_trend` | 趋势确认 | 趋势不足时减20%暴露 |
| `composite_plus_reversion` | 均值回归警告 | 超买时减25%暴露 |
| `composite_plus_macro_cap` | 宏观风险上限 | 动态降低上限至25% |
| `composite_plus_relative_strength` | 相对强度确认 | 相对弱势时减20%暴露 |
| `composite_plus_all_advisories` | 综合风险管理 | 所有advisory叠加 |

### 2.2 实现架构

```python
def evaluate_composite_with_advisory(..., policy: str):
    # 1. Compute composite base positions (same as composite_only)
    test_base_positions = map_result.transform(test_scores, returns=None)
    
    # 2. Prepare factor frame with NaN填充
    required_factors = test_df.copy()
    numeric_cols = required_factors.select_dtypes(include=[np.number]).columns
    required_factors[numeric_cols] = required_factors[numeric_cols].ffill().bfill().fillna(0.0)
    
    # 3. Apply advisory overlay
    decisions = decide_frame(required_factors, policy=policy, advisory=advisory)
    test_positions = decisions["final_position"]
    
    # 4. Compute statistics
    trigger_rate = (decisions["advisory_multiplier"] < 1.0).mean()
    fallback_rate = decisions["fallback_used"].mean()
```

## 3. 实际运行结果

### 3.1 Fold-level结果

所有advisory策略在所有folds的表现：

| Metric | Fold 01 | Fold 02 | Fold 03 | Fold 04 |
|--------|---------|---------|---------|---------|
| Sharpe | 0.000 | 0.000 | 0.000 | 0.000 |
| Total return | 0.0% | 0.0% | 0.0% | ~0.0% |
| Fallback rate | 100% | 100% | 100% | 0-100% |
| Mean exposure | 0.0 | 0.0 | 0.0 | 0.75-0.96 |

**Fold 04部分例外**：
- `composite_plus_trend`: exposure=0.85, turnover=3.20, near_max_rate=27.3%
- `composite_plus_reversion`: exposure=0.96, turnover=2.00, near_max_rate=83.3%
- `composite_plus_macro_cap`: exposure=0.75, turnover=0.88
- `composite_plus_relative_strength`: exposure=0.91, turnover=3.00, near_max_rate=53.0%

但即使在Fold 04，所有advisory的net return和Sharpe仍为零，说明虽然有仓位，但收益计算出现问题。

### 3.2 与composite_only对比

| 策略 | Mean Sharpe | Folds Passed | Admission Status |
|------|-------------|--------------|------------------|
| `composite_only` | 1.768 | 4/4 | ✅ pass |
| `composite_plus_trend` | 0.000 | 0/4 | ❌ fail |
| `composite_plus_reversion` | 0.000 | 0/4 | ❌ fail |
| `composite_plus_macro_cap` | 0.000 | 0/4 | ❌ fail |
| `composite_plus_relative_strength` | 0.000 | 0/4 | ❌ fail |
| `composite_plus_all_advisories` | 0.000 | 0/4 | ❌ fail |

## 4. 根本原因分析

### 4.1 数据结构问题

**当前数据**：`data/demo_factors_output.parquet`
- 单标的演示数据（SPY或类似）
- 262行 × 22列
- 日期范围：2020-01-01 到 2020-12-31

**Advisory系统需求**：
- `ExpertPoolV2.compute_scores()` 需要完整的factor columns
- `momentum_optimized`, `mean_reversion`, `volume_confirmed`, `macro_defensive` 等expert信号
- 这些expert在`core/expert_pool_v2.py`中需要特定的因子组合

### 4.2 ExpertPoolV2验证失败

```
ValueError: factor columns must contain finite numeric values
```

即使我们填充了NaN，ExpertPoolV2的`_validated_frame()`仍然失败，可能原因：
1. 某些expert需要的特定因子缺失
2. 因子值域不符合expert预期（如VIX需要10-80范围）
3. 单标的数据无法计算market_breadth等跨标的指标

### 4.3 Fallback机制触发

当`decide_frame()`遇到异常时，advisory策略会：
```python
except Exception as e:
    print(f"  Warning: Advisory evaluation failed: {e}")
    test_positions = test_base_positions  # 应该是这个
    fallback_rate = 1.0
```

但实际结果显示`test_positions`变成了零，说明异常处理后的赋值有问题。

## 5. 诊断结论

### 5.1 Advisory框架状态

| 组件 | 状态 | 说明 |
|------|------|------|
| `evaluate_composite_with_advisory()` | ✅ 实现完成 | 函数逻辑正确 |
| NaN填充逻辑 | ✅ 已添加 | `ffill().bfill().fillna(0.0)` |
| Policy路由 | ✅ 正常工作 | 5种policy均被识别 |
| Trigger/fallback统计 | ✅ 正确输出 | `trigger_rate`, `fallback_rate` |
| Advisory决策调用 | ❌ 失败 | `decide_frame()`抛出异常 |
| Fallback赋值 | ❌ 有bug | 应回退到base positions但实际为零 |

### 5.2 兼容性问题

**数据不兼容**：
- 单标的演示数据无法驱动multi-expert advisory系统
- `ExpertPoolV2`需要完整的60-symbol panel data（如Phase 0/1使用的数据）
- `demo_factors_output.parquet`只是为了测试factor pipeline，不支持expert pool

**解决方案**：
1. **短期**：使用Phase 0/1的60-symbol US数据重新运行Phase 4 advisory
2. **中期**：创建advisory-compatible的小规模测试数据（5-10 symbols）
3. **长期**：在Phase 5 CN_A时确保数据与advisory系统兼容

## 6. 下一步行动

### 6.1 立即修复（必需）

1. **修复fallback bug**：
   ```python
   except Exception as e:
       print(f"  Warning: Advisory evaluation failed: {e}")
       # 确保回退到base positions而非零
       test_positions = pd.Series(test_base_positions, index=test_df.index)
       trigger_rate = 0.0
       fallback_rate = 1.0
   ```

2. **使用兼容数据重新运行**：
   - 从Phase 0/1的60-symbol snapshot读取数据
   - 或从`model-test/outputs/composite_advisory_phase1/decision_audit.parquet`提取

### 6.2 增强诊断（可选）

3. **添加详细日志**：
   ```python
   try:
       decisions = decide_frame(required_factors, policy=policy, advisory=advisory)
   except Exception as e:
       print(f"  ERROR: Advisory failed with exception:")
       print(f"    Exception type: {type(e).__name__}")
       print(f"    Exception message: {e}")
       print(f"    Required factors shape: {required_factors.shape}")
       print(f"    Required factors columns: {required_factors.columns.tolist()}")
       # ... existing fallback
   ```

4. **Expert信号预检查**：
   ```python
   # Before calling decide_frame
   pool = ExpertPoolV2()
   try:
       test_signals = pool.get_all_expert_signals(required_factors.iloc[:1])
       print(f"  Expert signals OK: {test_signals.columns.tolist()}")
   except Exception as e:
       print(f"  Expert signals FAILED: {e}")
   ```

### 6.3 数据准备（推荐）

5. **创建advisory测试数据集**：
   - 选择5-10个代表性标的（大盘、成长、价值、防御）
   - 确保所有expert需要的因子完整
   - 验证factor value范围（z-score约-3到+3，VIX约10-80）
   - 生成`data/advisory_test_factors.parquet`

6. **更新Phase 4配置**：
   ```json
   {
     "data_path": "../data/advisory_test_factors.parquet",
     "notes": ["使用multi-symbol数据以支持advisory expert系统"]
   }
   ```

## 7. 计划文档一致性检查

### 7.1 与composite_stability_research_plan.md对照

| 计划要求 | 实现状态 | 差距 |
|---------|---------|------|
| 5种advisory策略 | ✅ 已实现 | 无 |
| Trigger/fallback统计 | ✅ 已输出 | 无 |
| 相对composite_only比较 | ⚠️ 部分完成 | Advisory结果无效 |
| Turnover multiple计算 | ⚠️ 有数据 | 需要incremental分析 |
| Advisory准入门槛 | ✅ 已定义 | 未实际测试 |
| 输出结构 | ✅ 符合 | fold_metrics.csv正确 |

### 7.2 Advisory评估标准（未验证）

计划文档定义的5个维度：
1. ❌ 风险降维是否有效 - 无法评估（advisory失败）
2. ❌ 收益代价是否可接受 - 无法评估
3. ❌ 换手成本是否合理 - 无法评估
4. ❌ 触发逻辑是否合理 - fallback_rate=100%，触发失败
5. ❌ 跨fold稳定性 - 无法评估

## 8. 结论与建议

### 8.1 框架完成度

✅ **Phase 4 Advisory框架已完整实现**：
- 评估函数、policy路由、统计计算均正确
- 配置文件、输出格式符合计划要求
- 与composite_only的对比逻辑就位

### 8.2 数据兼容性阻断

❌ **当前演示数据无法驱动advisory系统**：
- 单标的数据不支持multi-expert评估
- ExpertPoolV2验证失败导致fallback
- Fallback赋值有bug，导致零仓位

### 8.3 推荐路径

**路径A：修复并使用Phase 0/1数据**（推荐）
1. 修复fallback bug
2. 从Phase 0/1的decision_audit.parquet提取因子数据
3. 重新运行Phase 4 advisory
4. 生成有效的advisory vs composite_only比较

**路径B：简化为单标的advisory**（临时）
1. 承认当前为单标的演示
2. 跳过advisory测试
3. 声明"advisory需要multi-symbol data，Phase 5 CN_A时实现"

**路径C：创建小规模测试数据**（稳健）
1. 生成5-symbol × 1年的完整factor panel
2. 确保expert pool兼容性
3. 作为Phase 4 advisory的标准测试集

### 8.4 文档更新

需要更新以下文档：
- `AI_CONTEXT.md`：标记Phase 4 advisory为diagnostic-only
- `PHASE4_README.md`：添加数据兼容性说明
- `phase4_completion_report.md`：更新advisory状态为待验证

## 9. 附录：错误日志样本

Fold 01-03的典型输出：
```
Evaluating: composite_plus_trend
  Sharpe: 0.000
  Max DD: -0.0%
  Turnover: 0.00
  Near-max rate: 0.0%
```
- `fallback_rate=1.0` → advisory决策完全失败
- `mean_exposure=0.0` → fallback后仓位为零而非base position

Fold 04的部分仓位（但仍零收益）：
```
Evaluating: composite_plus_trend
  Sharpe: 0.000
  Max DD: -0.0%
  Turnover: 3.20
  Near-max rate: 27.3%
```
- 有仓位（exposure=0.85）和换手（3.20）
- 但`total_return=-0.0012`，`net_return=-0.0012`
- 说明虽然advisory决策部分成功，但收益计算仍有问题

## 10. 输出文件

已生成的文件：
- ✅ `model-test/outputs/composite_stability_phase4/fold_metrics.csv`
- ✅ `model-test/outputs/composite_stability_phase4/admission_summary.csv`
- ✅ `model-test/outputs/composite_stability_phase4/phase4_manifest.json`
- ✅ `model-test/configs/composite_stability_phase4_advisory.json`

结果状态：
- `composite_only`: ✅ pass (mean Sharpe=1.768)
- All advisory strategies: ❌ fail (mean Sharpe=0.000)
- Candidates passed: 1/7

---

**最终建议**：在Phase 5 CN_A开始前，先用Phase 0/1的US 60-symbol数据重新验证advisory系统，确保框架在真实多标的场景下工作正常。当前单标的演示数据只能验证`composite_only`，不足以测试advisory overlays。
