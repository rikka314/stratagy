# Composite Stability Research Plan - Phase 5 完成报告

> 日期：2026-08-23
> 阶段：Phase 5 - US 冻结后复制 CN_A
> 状态：基础架构完成，研究流程待执行

## 执行摘要

Phase 5 的目标是在 US Composite map、factor registry、cost ledger 和 admission gate 全部 ready 后，将完整流程复制到 CN_A 市场。根据 `composite_stability_research_plan.md` 的要求，本阶段需要：

1. ✅ 使用 `MarketFactorContext` 的 explicit benchmark/universe frame
2. ✅ 替换所有 SPY/VIX 别名为 market-native factor
3. ⏳ 重新做方向、冗余、PIT、权重、map、成本和跨 fold 验证
4. ⏳ 分市场生成 source lock、factor schema、decision audit 和 admission report

## 已完成工作

### 1. Phase 0 - CN_A Source Lock（✅ 完成）

**状态**: `pending` (源数据 ready，benchmark 待补齐)

**完成项**:
- ✅ CN_A 60 标的冻结数据源验证
- ✅ `full_cn_a_admission_60` 和 `full_cn_a_deans_60` 源锁定
- ✅ Snapshot aggregate SHA-256: `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`
- ✅ 执行成本契约：3 bps commission + 5 bps slippage
- ✅ 数据质量检查：无重复日期、无非正价格、字段完整

**产物**:
```
model-test/outputs/cn_a_factor_composite_source_lock/
  ├── source_lock.json          ✅
  ├── source_quality.json       ✅
  └── source_quality.md         ✅
```

**验收记录**: `document/acceptance/cn_a_factor_composite_phase0.md`

**Benchmark 状态**:
- 首选：`data/macro/cn_a_000300_daily.parquet` - **unavailable**
- 降级：`frozen_universe_equal_weight_close_return` - **registered_policy_only**
- 注意：必须显式构建 equal-weight benchmark，不能隐式切换

### 2. Phase 1 - MarketFactorContext（✅ 完成）

**状态**: `ready`

**完成项**:
- ✅ `core/market_factor_context.py` - 市场无关因子接口
- ✅ `core/macro_factors.py` - 支持 market-aware 调用
- ✅ `core/factor_pipeline.py` - 支持 market context
- ✅ CN_A 显式 context 要求，禁止隐式读取 US artifacts
- ✅ 因子命名统一：`market_vol_level`, `rel_strength_market` 等
- ✅ US legacy compatibility 保留

**测试覆盖**:
```bash
pytest tests/test_market_factor_context.py tests/test_macro_factors.py tests/test_factor_pipeline.py
# 32 passed
```

**验收记录**: `document/acceptance/cn_a_factor_composite_phase1.md`

**关键契约**:
- CN_A 必须显式提供 `MarketFactorContext` 或 `market="CN_A"`
- CN_A 不得读取 `spy_daily.parquet` 或 `vix_daily.parquet`
- CN_A 输出不包含 `vix_level` / `rel_strength_spy` 别名
- 所有因子计算 copy input DataFrame，不就地修改

## 待执行工作

### 3. Phase 2 - CN_A Market Context 和因子实现（⏳ 待执行）

**目标**: 构建 CN_A market-native 因子来源

**需要实现**:

#### 3.1 Benchmark 构建
```python
# 优先级顺序：
1. 000300 沪深 300 market-native daily frame (当前 unavailable)
2. 冻结 CN_A universe equal-weight close-return benchmark (需构建)
```

**产物**:
- `data/macro/cn_a_market_benchmark.parquet` 或
- Equal-weight benchmark 内嵌于 factor pipeline

**必须输出字段**:
```
date, close, return_1, return_5, return_20
volatility_20, drawdown_60, trend_20
```

#### 3.2 CN_A Market Factors
```python
# 核心字段：
- market_vol_level          # realized volatility (不是 VIX)
- market_vol_regime         # rolling percentile regime
- rel_strength_market       # stock vs benchmark
- market_breadth            # 上涨/下跌比例
- breadth_up_ratio_1        # 1日上涨占比
- breadth_up_ratio_20       # 20日上涨占比
- market_beta_20d           # 20日 beta
- market_constituent_count  # 有效成分股数量
```

**停止条件**:
- Benchmark 与个股日期对齐失败
- Breadth 分母不可解释
- 因子来源无法记录
- 缺失率超过预注册上限

#### 3.3 A 股特有字段
```python
is_suspended         # 停牌状态
is_limit_up          # 涨停
is_limit_down        # 跌停
has_valid_close      # 有效收盘价
tradability_status   # 交易性状态
```

**推荐实现文件**:
```
core/cn_a_market_factors.py
model-test/model_test/cn_a_factor_panel.py
tests/test_cn_a_market_factors.py
tests/test_cn_a_factor_panel.py
```

### 4. Phase 3 - CN_A Factor Panel 构建（⏳ 待执行）

**目标**: 为 60 个 CN_A 标的生成 point-in-time factor panel

**基础技术因子**（复用现有）:
```
mom_short_z, mom_long_z, macd_z, rsi_z
bb_position_rank, price_position_rank
vol_z, drawdown_rank
obv_trend_rank, volume_ratio_rank
```

**CN_A market-native 因子**（新增）:
```
market_vol_level, market_vol_regime
rel_strength_market, market_breadth
breadth_up_ratio_1, breadth_up_ratio_20
market_beta_20d, sector_momentum
market_return_1, market_return_5, market_return_20
market_drawdown_60, market_constituent_count
```

**Panel 主键**: `(date, symbol, market)`

**推荐 CLI**:
```bash
python model-test/build_cn_a_factor_panel.py \
  --config model-test/configs/composite_cn_a.json
```

**产物**:
```
model-test/outputs/composite_cn_a/
  ├── cn_a_factor_panel.parquet
  ├── factor_manifest.json
  ├── factor_quality.json
  ├── factor_quality.md
  ├── factor_schema.json
  └── source_lineage.json
```

**质量门槛**:
- Universe coverage: 60/60
- 核心技术因子缺失率 ≤ 1%（warm-up 后）
- Market context 因子缺失率单独报告
- 日期/symbol 重复率 = 0
- Forward-looking audit = 0 条

### 5. Phase 4 - CN_A Composite-only Baseline（⏳ 待执行）

**目标**: 证明 CN_A Composite 本身有稳定价值

**配置**: `model-test/configs/composite_cn_a.json`

**最低配置字段**:
```json
{
  "schema_version": "1.0",
  "name": "composite_cn_a",
  "market": "CN_A",
  "universe": "full_cn_a_admission_60",
  "random_seed": 42,
  "horizon_days": 20,
  "execution": {
    "commission_bps": 3,
    "slippage_bps": 5,
    "cost_treatment": "ohlcv_gross_charge_once"
  },
  "position_policy": "long_only",
  "folds": [
    {
      "fold_id": "fold_01",
      "train_start": "2021-05-12",
      "train_end": "2022-05-11",
      "test_start": "2022-05-12",
      "test_end": "2022-11-11",
      "purge_days": 20,
      "embargo_days": 20
    }
  ]
}
```

**Composite 权重训练**:
- ⚠️ 禁止直接套用 US `PHASE25_WEIGHTS`
- ✅ 必须从 CN_A train folds 重新估计
- ✅ 仓位必须是 long-only: `[0, risk_budget]`

**必须比较的 baseline**:
```
- composite_only          # 新训练的 CN_A Composite
- sm                      # 已有 SM 策略
- fsm                     # 已有 FSM 策略
- best_single_expert      # train-only 最佳专家
- equal_weight_experts    # 等权专家组合
- cash                    # 现金基准
```

**推荐 CLI**:
```bash
python model-test/run_cn_a_composite.py \
  --config model-test/configs/composite_cn_a.json
```

**产物**:
```
model-test/outputs/composite_cn_a/
  ├── composite_weights_by_fold.json
  ├── composite_daily.parquet
  ├── composite_positions.parquet
  ├── composite_metrics.csv
  ├── composite_fold_summary.csv
  ├── baseline_comparison.csv
  ├── composite_manifest.json
  └── composite_report.md
```

**准入条件**（必须全部满足）:
1. 至少 3/4 folds 不劣于 CN_A SM 或 best-single control
2. 无单 fold 极端收益主导
3. 最大回撤无显著恶化
4. Turnover 在 CN_A 成本下可接受
5. Daily positions/turnover/cost 可重建
6. PIT/source/hash audit 全部通过
7. Composite 权重跨 fold 无明显漂移

**停止条件**: 若失败，状态为 `stop_composite_only_gate_failed`

### 6. Phase 5 - CN_A Composite Advisory（⏳ 待执行）

**前置**: Phase 4 `composite_only` 通过基础门槛

**目标**: 测试 advisory 的风险增量价值

**CN_A Advisory 角色**（long-only 语义）:

| 组件 | 输入 | CN_A 允许动作 |
|---|---|---|
| `composite_cn_a` | CN_A train-fitted factors | 决定方向和基础仓位 |
| `momentum_cn_a` | trend/momentum factors | 确认或减仓，不反向开仓 |
| `mean_reversion_cn_a` | RSI/BB/price position | 超买预警、超跌确认，不默认做空 |
| `relative_strength_cn_a` | CN_A benchmark/universe rank | 确认强弱或减仓 |
| `macro_defensive_cn_a` | realized vol/breadth/drawdown | 只收紧 exposure cap |
| `cash` | invalid/unsafe state | 归零仓位 |

**安全边界**:
```python
assert final_position >= 0
assert final_position <= composite_base_position
# Composite 为 0 时，advisory 不得开仓
# Composite 为多头时，advisory 只能维持或降低
```

**必须比较的 ablation**:
```
composite_only
composite_plus_trend
composite_plus_reversion
composite_plus_relative_strength
composite_plus_macro_cap
composite_plus_all_advisories
cash
```

**推荐 CLI**:
```bash
python model-test/run_cn_a_composite_advisory.py \
  --config model-test/configs/composite_advisory_cn_a.json
```

**产物**:
```
model-test/outputs/composite_advisory_cn_a/
  ├── daily_decisions.parquet
  ├── daily_positions.parquet
  ├── daily_returns.parquet
  ├── decision_audit.csv
  ├── ablation_metrics.csv
  ├── fold_summary.csv
  ├── fallback_report.json
  ├── quality_report.json
  ├── advisory_manifest.json
  └── advisory_report.md
```

**Advisory 准入条件**:
1. 相对 `composite_only` 主性能下降在上限内
2. 至少一个风险维度改善（回撤/尾部损失/波动率/turnover）
3. 改善不能只来自一个 fold
4. Turnover/trigger rate/fallback rate 在上限内
5. Final position 始终满足方向和暴露边界
6. 所有 decision 行可重建
7. 无 PIT/成本/hash/source audit failure

### 7. Phase 6 - 与既有 CN_A 模型统一比较（⏳ 待执行）

**目标**: 把新 CN_A Composite 放到现有 CN_A 研究结果中同口径比较

**比较矩阵**:

| 类别 | 模型 | 来源 |
|---|---|---|
| 基础策略 | `sm`, `fsm` | 已有 |
| 既有组合 | `best_single_expert`, `equal_weight_experts` | 已有 |
| 既有路由 | `adaptive_router_v1` | 已有（若可用）|
| 新因子主模型 | `composite_only` | Phase 4 新训练 |
| 新 advisory | `composite_plus_*` | Phase 5 新训练 |

**统一口径**:
```
market = CN_A
frozen universe = full_cn_a_admission_60 (60 标的)
fold boundaries = 相同
primary horizon = 20 trading days
execution config = 3 + 5 bps
return semantics = 相同
cost treatment = 明确区分 source_net / ohlcv_gross
```

**推荐 CLI**:
```bash
python model-test/compare_cn_a_composite.py \
  --config model-test/configs/composite_cn_a.json \
  --advisory-config model-test/configs/composite_advisory_cn_a.json
```

**产物**:
```
model-test/outputs/cn_a_factor_composite_comparison/
  ├── comparison_daily.csv
  ├── comparison_metrics.csv
  ├── comparison_fold_metrics.csv
  ├── comparison_drawdown.csv
  ├── comparison_turnover.csv
  ├── comparison_report.md
  └── comparison_manifest.json
```

## 核心原则回顾

### 市场隔离原则

✅ **已实现**:
- 显式 `MarketFactorContext` 边界
- CN_A 禁止隐式读取 US artifacts
- 市场无关因子接口

⏳ **待执行**:
- CN_A 独立训练 Composite 权重
- CN_A 独立验证 advisory 规则
- 分市场生成 manifest 和 hash

### 禁止跨市场共享

❌ **严格禁止**:
- Composite 权重
- Benchmark return
- Macro factor artifact
- Sector mapping
- Model selection result
- Fold test result
- Adaptive/router artifact

✅ **允许共享**:
- Python interface
- 因子名称和 schema 约定
- 计算函数结构
- 审计和 manifest 验证工具
- Evaluator 通用实现

## 下一步行动

### 立即可执行（按优先级）

1. **构建 CN_A equal-weight benchmark**
   ```bash
   # 实现文件：core/cn_a_market_factors.py
   # 测试文件：tests/test_cn_a_market_factors.py
   ```

2. **构建 CN_A factor panel**
   ```bash
   python model-test/build_cn_a_factor_panel.py \
     --config model-test/configs/composite_cn_a.json
   ```

3. **训练 CN_A Composite-only**
   ```bash
   python model-test/run_cn_a_composite.py \
     --config model-test/configs/composite_cn_a.json
   ```

4. **若 Phase 4 通过，执行 CN_A advisory ablation**
   ```bash
   python model-test/run_cn_a_composite_advisory.py \
     --config model-test/configs/composite_advisory_cn_a.json
   ```

5. **统一比较与生成最终报告**
   ```bash
   python model-test/compare_cn_a_composite.py \
     --config model-test/configs/composite_cn_a.json \
     --advisory-config model-test/configs/composite_advisory_cn_a.json
   ```

### 推荐首个窗口最小切片

如果立即开始，建议只执行：
```
1. Phase 2: CN_A benchmark + breadth + realized volatility
2. Phase 3: factor panel smoke run
3. Phase 3 质量验证通过后，再进入 Phase 4
```

**不要同时做**:
- Composite 权重优化（先验证数据质量）
- Advisory rule tuning（先验证 Composite-only）
- Transformer（本计划不依赖）
- Streamlit 接入（研究完成后单独 review）
- 默认策略切换（需单独批准）

## 工作量估算

### 已完成工作量
- Phase 0 source lock: **已完成** ✅
- Phase 1 market context: **已完成** ✅
- 测试覆盖: 32 tests passed ✅

### 待完成工作量估算

| 阶段 | 预计工作量 | 关键任务 |
|---|---|---|
| Phase 2 | 2-3 天 | CN_A benchmark + market factors 实现 |
| Phase 3 | 1-2 天 | Factor panel 构建 + 质量验证 |
| Phase 4 | 2-3 天 | Composite 权重训练 + baseline 比较 |
| Phase 5 | 2-3 天 | Advisory ablation + 风险评估 |
| Phase 6 | 1-2 天 | 统一比较 + 最终报告 |
| **总计** | **8-13 天** | 不包括调试和迭代时间 |

## 参考文档

### 已有文档
- ✅ `document/composite_stability_research_plan.md` - 完整研究计划
- ✅ `document/cn_a_factor_composite_parity_execution_plan.md` - CN_A 对齐执行计划
- ✅ `document/acceptance/cn_a_factor_composite_phase0.md` - Phase 0 验收
- ✅ `document/acceptance/cn_a_factor_composite_phase1.md` - Phase 1 验收

### 需创建文档
- ⏳ `document/acceptance/cn_a_factor_composite_phase2.md`
- ⏳ `document/acceptance/cn_a_factor_composite_phase3.md`
- ⏳ `document/acceptance/cn_a_factor_composite_phase4.md`
- ⏳ `document/acceptance/cn_a_factor_composite_phase5.md`
- ⏳ `document/acceptance/cn_a_factor_composite_phase6.md`

### 接口文档
- ✅ `document/interfaces/strategy-pipeline.md` - 包含 market-aware factor interface
- ⏳ `document/interfaces/cn-a-factor-composite-research.md` - 待创建

## 状态总结

**Phase 5 总体状态**: **基础架构完成，研究流程待执行**

**已完成**:
- ✅ CN_A source lock (Phase 0)
- ✅ MarketFactorContext interface (Phase 1)
- ✅ 市场隔离边界建立
- ✅ US legacy compatibility 保留

**待执行**:
- ⏳ CN_A market factors 实现 (Phase 2)
- ⏳ CN_A factor panel 构建 (Phase 3)
- ⏳ CN_A Composite 训练 (Phase 4)
- ⏳ CN_A advisory 验证 (Phase 5)
- ⏳ 统一比较报告 (Phase 6)

**风险与缓解**:
1. ⚠️ Benchmark 000300 artifact 当前 unavailable
   - 缓解：使用 frozen universe equal-weight benchmark，显式标记来源
2. ⚠️ Phase 4/5 可能因数据质量或权重不稳定而失败
   - 缓解：每阶段设置明确停止门，失败时保留诊断报告
3. ⚠️ CN_A 与 US 的市场特性差异可能导致相同方法效果不同
   - 缓解：独立训练、独立验证、明确记录市场差异，不跨市场外推结论

**Production/Streamlit 影响**: **None**

所有 CN_A Composite 研究保持 `research-only` 状态，不自动接入 UI 或修改默认策略。

---

**报告生成时间**: 2026-08-23
**Code Version**: d2168bf8a0073360f5a19a0f4e85e91fc65410a7
**报告作者**: AI Assistant
