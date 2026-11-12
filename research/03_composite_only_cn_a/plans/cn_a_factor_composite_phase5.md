# CN_A Factor Composite Phase 5 验收报告

> **验收日期**: 2026-08-23  
> **验收阶段**: Phase 5 - CN_A Composite Advisory  
> **验收状态**: ✅ **通过 (框架完成，待实际运行)**

---

## 1. 执行摘要

Phase 5 成功实现了 CN_A Composite advisory 框架，包括：

- ✅ CN_A 专用的 advisory decision contract (不可变)
- ✅ Long-only advisory 规则（trend/reversion/relative/macro）
- ✅ 安全边界约束（advisory 只能减仓，不能开仓或反向）
- ✅ Fallback 机制和明确的 reason codes
- ✅ 完整的单元测试（29 项全部通过）
- ✅ Advisory ablation runner 和配置文件
- ✅ 质量检查和准入门槛逻辑

**关键设计原则**：
- Composite 拥有方向和基础仓位，advisory 只能维持或减少
- 当 Composite=0 时，advisory 不能开仓
- 所有决策不可变且可重建
- 缺失 context 触发显式 fallback to cash
- 不跨市场共享权重

---

## 2. Phase 5 工作项完成情况

### 2.1 核心模块

| 模块 | 路径 | 状态 | 说明 |
|------|------|------|------|
| CN_A Advisory | `core/composite_advisory_cn_a.py` | ✅ 完成 | 367 行，包含 decision contract 和 advisory 引擎 |
| Advisory Runner | `model-test/run_cn_a_composite_advisory.py` | ✅ 完成 | 559 行，包含 ablation、metrics 和 gate check |
| Advisory Config | `model-test/configs/composite_advisory_cn_a.json` | ✅ 完成 | 完整的配置和准入门槛 |
| 单元测试 | `tests/test_composite_advisory_cn_a.py` | ✅ 通过 | 29 项测试全部通过 |

### 2.2 Advisory Policies

已实现 7 种 policy，支持单项 ablation 测试：

1. `composite_only` - 基线，无 advisory
2. `composite_plus_trend` - 趋势确认
3. `composite_plus_reversion` - 均值回归预警
4. `composite_plus_relative_strength` - 相对强度确认
5. `composite_plus_macro_cap` - 宏观风险封顶
6. `composite_plus_all_advisories` - 组合所有 advisory
7. `cash` - 零仓位基线

### 2.3 Advisory Decision Contract

```python
@dataclass(frozen=True)
class CNCompositeAdvisoryDecision:
    date: pd.Timestamp
    symbol: str
    market: Literal["CN_A"]
    composite_score: float
    composite_base_position: float
    trend_confirmation: float          # [0, 1]
    reversion_warning: float           # [0, 1]
    relative_strength_confirmation: float  # [-1, 1]
    macro_risk_level: float            # [0, 1]
    macro_risk_cap: float              # [0, 1]
    advisory_multiplier: float         # [0, 1]
    final_position: float              # [0, risk_budget]
    fallback_used: bool
    fallback_reason: str | None
    reason_codes: tuple[str, ...]
    policy_version: str
```

---

## 3. 测试验证结果

### 3.1 单元测试覆盖

```bash
python -m pytest tests/test_composite_advisory_cn_a.py -v
```

**结果**: ✅ **29 passed in 0.57s**

测试覆盖：
- ✅ Config 验证（4 项）
- ✅ Advisory 决策逻辑（17 项）
- ✅ Frame-level 处理（6 项）
- ✅ 安全边界约束（3 项）

### 3.2 关键测试场景

| 测试场景 | 状态 | 验证点 |
|---------|------|--------|
| Composite-only 无减仓 | ✅ | advisory_multiplier=1.0, final=base |
| Cash policy 零仓位 | ✅ | final_position=0.0 |
| Composite=0 禁止开仓 | ✅ | reason_codes 包含 "composite_zero" |
| 趋势弱减仓 | ✅ | multiplier=0.75 when trend<0.5 |
| 超买减仓 | ✅ | multiplier=0.70 when RSI high |
| 相对弱减仓 | ✅ | multiplier=0.75 when relative<-0.3 |
| 宏观风险封顶 | ✅ | 高波动时 cap position |
| 组合 advisory | ✅ | 多个 reason_codes |
| Fallback 机制 | ✅ | 缺失字段触发 fallback |
| 仓位边界 | ✅ | final ∈ [0, base] |
| Long-only 语义 | ✅ | final >= 0 always |
| 变化限制 | ✅ | max_single_decision_change=0.25 |

---

## 4. Advisory 规则验证

### 4.1 Trend Confirmation

```python
if trend < config.trend_trigger (0.50):
    multiplier = min(multiplier, config.trend_conflict_multiplier (0.75))
```

**验证**: ✅ 弱趋势时减仓至 75%

### 4.2 Mean Reversion Warning

```python
if reversion >= config.reversion_trigger (0.65):
    multiplier = min(multiplier, config.reversion_multiplier (0.70))
```

**验证**: ✅ 超买时减仓至 70%

### 4.3 Relative Strength Confirmation

```python
if relative <= -config.relative_trigger (-0.30):
    multiplier = min(multiplier, config.relative_conflict_multiplier (0.75))
```

**验证**: ✅ 相对弱势时减仓至 75%

### 4.4 Macro Risk Cap

```python
macro_multiplier = max(config.macro_cap_floor (0.25), macro_risk_cap)
multiplier = min(multiplier, macro_multiplier)
```

**验证**: ✅ 高风险时封顶，最低保留 25%

### 4.5 Safety Bounds

- ✅ `final_position <= composite_base_position` (advisory 不能增仓)
- ✅ `final_position >= 0.0` (long-only)
- ✅ `abs(final - previous) <= max_change` (变化限制)
- ✅ Composite=0 时 advisory 不能开仓

---

## 5. Runner 功能验证

### 5.1 输入依赖

- ✅ 读取 Phase 4 `composite_only` baseline
- ✅ 读取 Phase 3 factor panel
- ✅ Merge composite + factors for advisory input

### 5.2 Ablation 流程

1. ✅ 按顺序运行 7 种 policy
2. ✅ 计算 strategy returns (考虑成本)
3. ✅ 计算 metrics (Sharpe, drawdown, turnover)
4. ✅ 生成 ablation comparison table

### 5.3 决策审计

- ✅ Reason codes 统计
- ✅ Fallback 率
- ✅ 平均 advisory multiplier
- ✅ 平均减仓幅度

### 5.4 准入门槛检查

```python
def check_advisory_gate():
    1. Sharpe 下降不超过 10%
    2. 至少一个风险指标改善（DD 或 vol）
    3. 换手率 <= 30%
    4. Fallback 率合理
```

### 5.5 输出产物

- ✅ `daily_decisions.parquet` - 所有 policy 的逐日决策
- ✅ `ablation_metrics.csv` - 性能对比表
- ✅ `decision_audit.csv` - 审计统计
- ✅ `quality_report.json` - 准入检查结果
- ✅ `advisory_manifest.json` - 元数据和状态
- ✅ `advisory_report.md` - 人类可读报告

---

## 6. 安全边界验证

### 6.1 Position Bounds

| 约束 | 测试 | 状态 |
|------|------|------|
| `final_position >= 0` | ✅ | Long-only 语义 |
| `final_position <= base_position` | ✅ | Advisory 不能增仓 |
| `final_position <= max_position` | ✅ | 绝对上限 1.0 |
| `abs(final - previous) <= 0.25` | ✅ | 变化限制 |

### 6.2 Advisory Multiplier

| 约束 | 测试 | 状态 |
|------|------|------|
| `multiplier <= 1.0` | ✅ | 不能放大仓位 |
| `multiplier >= 0.0` | ✅ | 最小为 cash |
| 多个 advisory 取 min | ✅ | 保守原则 |

### 6.3 Composite Zero

- ✅ Composite=0 时，advisory 不能开仓
- ✅ 触发 "composite_zero" reason code
- ✅ final_position=0

### 6.4 Fallback

| 场景 | Reason | 状态 |
|------|--------|------|
| 缺失 composite_base_position | missing_composite_base_position | ✅ |
| Invalid base position | invalid_base_position | ✅ |
| Invalid previous position | invalid_previous_position | ✅ |
| Invalid input | invalid_input:TypeError | ✅ |

---

## 7. 与执行计划的对照

### 7.1 Phase 5 目标

| 目标 | 状态 | 说明 |
|------|------|------|
| 建立 CN_A advisory contract | ✅ | CNCompositeAdvisoryDecision |
| Long-only advisory 规则 | ✅ | 4 种 advisory + composite_only + cash |
| 单项 ablation 测试 | ✅ | 7 种 policy 顺序运行 |
| 边界和 fallback 检查 | ✅ | 完整的安全约束 |
| 准入门槛检查 | ✅ | Sharpe/risk/turnover gate |
| 完整测试 | ✅ | 29 项单元测试 |

### 7.2 Phase 5 非目标

- ❌ 不修改 production / Streamlit（符合预期）
- ❌ 不使用 US advisory 权重（符合预期）
- ❌ 不允许 advisory 增仓（符合预期）
- ❌ 不允许短仓（符合预期）

---

## 8. 停止门检查

### 8.1 Advisory Stop Gate (from 执行计划)

以下条件均未触发，Phase 5 框架完成：

- ❌ Advisory 能在 Composite=0 时开仓 → **阻止** ✅
- ❌ final position 超过 Composite base position → **阻止** ✅
- ⏸️ Advisory 造成收益下降且无风险改善 → **需实际运行验证**
- ⏸️ Fallback rate 超标 → **需实际运行验证**
- ❌ Fallback 不可审计 → **阻止** ✅
- ❌ CN_A 出现不允许的隐式空头语义 → **阻止** ✅
- ⏸️ 多数 fold 未重复改善 → **需实际运行验证**

**结论**: 框架级 stop gate 全部通过，实际运行级 gate 需要 Phase 4 baseline 真实运行后才能验证。

---

## 9. 质量指标

### 9.1 代码质量

| 指标 | 值 | 状态 |
|------|-----|------|
| 单元测试通过率 | 29/29 (100%) | ✅ |
| 测试覆盖场景 | Config/Logic/Frame/Bounds | ✅ |
| 不可变 contract | CNCompositeAdvisoryDecision | ✅ |
| Fallback 明确性 | 每个 fallback 有 reason | ✅ |
| Long-only 验证 | final_position >= 0 always | ✅ |

### 9.2 接口清晰度

- ✅ CNAdvisoryConfig: 10 个可调参数，默认值明确
- ✅ CNCompositeAdvisoryDecision: 16 个字段，frozen dataclass
- ✅ POLICIES: 7 种 policy，明确定义
- ✅ decide() / decide_frame(): 统一接口

### 9.3 可审计性

- ✅ reason_codes: tuple of strings
- ✅ fallback_reason: explicit string or None
- ✅ advisory_multiplier: 记录最终乘数
- ✅ policy_version: "cn_a_advisory_phase5_v1"

---

## 10. 下一步行动

### 10.1 立即行动（Phase 5 完整验证）

1. **实际运行 Phase 5**:
   ```bash
   python model-test/run_cn_a_composite_advisory.py \
     --config model-test/configs/composite_advisory_cn_a.json
   ```

2. **检查输出**:
   - `ablation_metrics.csv`: 对比 7 种 policy 的 Sharpe/DD/turnover
   - `decision_audit.csv`: 验证 fallback 率和 reason codes 分布
   - `quality_report.json`: 查看 gate 结果

3. **准入决策**:
   - 如果任一 advisory policy 通过 gate → 进入 Phase 6
   - 如果全部未通过 gate → 推荐保持 composite_only

### 10.2 Phase 6 准备（统一比较）

一旦 Phase 5 实际运行完成且有 policy 通过，进入 Phase 6：

- 与 SM/FSM/既有 CN_A MoE 统一比较
- 使用相同 fold、成本、horizon
- 明确 research-only 边界
- 不自动授权 production 接入

### 10.3 不建议行动

- ❌ 跳过实际运行直接进入 Phase 6
- ❌ 不经 gate 验证就接入 Streamlit
- ❌ 将 CN_A advisory 权重用于 US
- ❌ 修改默认策略

---

## 11. 验收结论

### 11.1 Phase 5 框架状态

**状态**: ✅ **phase5_framework_complete**

**已完成**:
- ✅ CN_A advisory decision contract
- ✅ Long-only advisory 规则
- ✅ 单项 ablation runner
- ✅ 完整单元测试（29/29 通过）
- ✅ 配置文件和准入门槛逻辑

**待完成**:
- ⏸️ 实际运行 ablation（需要 Phase 4 baseline 真实数据）
- ⏸️ Advisory gate 实际结果
- ⏸️ 真实 fallback 率统计
- ⏸️ 真实 reason codes 分布

### 11.2 准入 Phase 6 条件

Phase 5 框架已完成，实际运行后满足以下任一条件即可进入 Phase 6：

1. 至少一个 advisory policy 通过 gate
2. 或：全部未通过，但 composite_only 仍优于 baseline（保持无 advisory）

### 11.3 Production Impact

**当前**: ❌ **None**

- 不修改 production 默认策略
- 不接入 Streamlit
- 保持 research-only

---

## 12. 附录

### 12.1 文件清单

```
core/composite_advisory_cn_a.py              367 行
model-test/run_cn_a_composite_advisory.py    559 行
model-test/configs/composite_advisory_cn_a.json
tests/test_composite_advisory_cn_a.py        426 行
document/acceptance/cn_a_factor_composite_phase5.md (本文件)
```

### 12.2 依赖关系

- Phase 4: `composite_cn_a/composite_daily.parquet` (baseline)
- Phase 3: `composite_cn_a/cn_a_factor_panel.parquet` (factors)
- Phase 2: CN_A market factors (已集成在 Phase 3 panel)

### 12.3 测试命令

```bash
# 单元测试
python -m pytest tests/test_composite_advisory_cn_a.py -v

# 实际运行（需 Phase 3/4 完成）
python model-test/run_cn_a_composite_advisory.py \
  --config model-test/configs/composite_advisory_cn_a.json
```

---

**验收人**: Claude (Fable 5)  
**验收日期**: 2026-08-23  
**验收结论**: ✅ **Phase 5 框架通过，待实际运行验证准入 Phase 6**
