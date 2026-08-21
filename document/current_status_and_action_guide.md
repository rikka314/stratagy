# 当前状态与行动指南

> **更新日期**: 2026-08-21  
> **当前位置**: Phase 0 已完成，准备进入 Phase 1.2

---

## 执行计划总览

我们正在执行 **因子系统与专家体系优化计划**（`document/factor_and_expert_optimization_plan.md`），目标是优化现有的 10 因子体系和专家池设计。

```
Phase 0: 准备工作           ✅ 已完成 (2026-08-21)
  └─ 宏观数据下载
  └─ macro_factors.py 实现

Phase 1: 因子分层与筛选     ⏸️ 准备中
  ├─ 1.1 因子分层          ✅ 已定义
  ├─ 1.2 分层筛选实验      ⏭️ 下一步
  ├─ 1.3 宏观因子实现      ✅ 已完成
  └─ 1.4 执行步骤          ⏸️ 待开始

Phase 2: 因子权重优化       🔲 未开始
Phase 3: 专家池重构         🔲 未开始
Phase 4: 验证与上线         🔲 未开始
```

---

## Phase 0 完成总结

### 交付物

1. **宏观数据** (`data/macro/`)
   - VIX: 2,956 行 (2015-01-02 至 2026-08-19)
   - SPY: 2,923 行 (2015-01-02 至 2026-08-19)
   - 行业分类: 60 个股票，100% 覆盖

2. **宏观因子模块** (`core/macro_factors.py`)
   - 5 个新宏观因子：`vix_level`, `rel_strength_vs_spy`, `market_breadth`, `beta_20d`, `sector_momentum`
   - 单股 API: `compute_batch()`
   - 多股 API: `compute_universe_panel()`
   - Observed-only 设计 + SHA-256 校验

3. **验证结果**
   - ✅ VIX regime 分类正确
   - ✅ 单股批量计算：659 行 × 5 因子
   - ✅ 多股面板计算：14,622 行（2 股票）
   - ✅ 所有因子输出正常

详细报告：`document/phase0_completion_report.md`

---

## 当前问题诊断回顾

### 问题 1: 因子同质化

**现状**: 10 个因子中有 8 个是技术指标，高度相关

- 动量类 (3个): `mom_short`, `mom_long`, `macd`
- 超买超卖类 (2个): `rsi`, `bb_position`
- 成交量类 (2个): `obv`, `volume_ratio`
- 风险类 (2个): `vol`, `drawdown`

**解决方案**: 加入 5 个宏观因子，提供独立信息源

### 问题 2: 专家同质化

**现状**: SM/FSM 系列本质是同一线性模型的超参数变体

```python
# 都是这个公式，只是权重 w1...w10 不同
factor_score = w1*mom_short + w2*mom_long + ... + w10*drawdown
```

**解决方案**: Phase 3 将重构专家池，每个专家基于不同信息源

### 问题 3: 缺少宏观和相对维度

**现状**: 所有因子都是个股自身技术指标

**解决方案**: ✅ 已通过 Phase 0 解决，新增 5 个宏观因子

---

## 下一步：Phase 1.2 分层筛选实验

### 目标

从 15 个因子（10 技术 + 5 宏观）中筛选出 6-10 个最有效的因子

### 因子分层

```python
# 第一层: 趋势动量
layer_1 = ["mom_short_z", "mom_long_z", "macd_z"]

# 第二层: 均值回归
layer_2 = ["rsi_z", "bb_position_rank", "price_position_rank"]

# 第三层: 风险与成交量
layer_3 = ["vol_z", "drawdown_rank", "obv_trend_rank", "volume_ratio_rank"]

# 第四层: 宏观与相对（新增）
layer_4 = [
    "vix_level",           # VIX 水平
    "rel_strength_vs_spy", # 相对 SPY 强度
    "market_breadth",      # 市场广度
    "beta_20d",            # 20日 beta
    "sector_momentum",     # 行业动量
]
```

### 实验设计

```python
# 实验 E1: 单因子测试
for factor in layer_i:
    score = factor
    result = backtest(score)
    report(factor, sharpe, win_rate, max_dd)

# 实验 E2: 双因子测试
for (f1, f2) in combinations(layer_i, 2):
    score = f1 + f2
    result = backtest(score)
    report((f1, f2), sharpe, ...)

# 实验 E3: 确定最优组合
best_layer_i = select_best_from_E1_E2()
```

### 验收标准

```python
# 1. 每层至少保留 1 个因子
assert len(selected_layer_1) >= 1
assert len(selected_layer_2) >= 1
assert len(selected_layer_3) >= 1
assert len(selected_layer_4) >= 1

# 2. 总因子数控制在 6-10 个
assert 6 <= total_factors <= 10

# 3. 层间相关性 < 0.5
for (layer_i, layer_j) in combinations(layers, 2):
    assert correlation(layer_i, layer_j) < 0.5
```

### 需要创建的脚本

```bash
# 主实验脚本（待创建）
model-test/run_factor_layered_selection.py

# 用法
python model-test/run_factor_layered_selection.py \
    --market US \
    --symbols AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,V,JNJ \
    --window 2020-01-01_to_2024-12-31 \
    --output model-test/outputs/phase1_factor_selection/
```

### 预期时间

- **Day 6-10**: 运行实验（10 股票 × 4 层 × 单因子+双因子）
- **Day 11-14**: 分析结果，确定最终因子集

---

## 后续阶段概览

### Phase 2: 因子权重优化 (Week 3-4)

1. **Grid Search**: 粗筛选最优权重组合
2. **Bayesian Optimization**: 精细调优
3. **Feature Selection**: 自动筛选冗余因子

**成功标准**:
- Sharpe 提升 > 20%
- 因子数减少（去冗余）
- 无单一因子主导（最大权重 < 40%）

### Phase 3: 专家池重构 (Week 5-6)

**新专家设计**（正交化）:
- `momentum`: 只用长期动量
- `mean_reversion`: 只用超买超卖
- `macro_defensive`: 只用宏观因子
- `composite`: 使用 Phase 2 筛选的全因子

**成功标准**:
- 专家相关性 < 0.5
- 至少 3 个专家在不同 fold 表现最优
- Oracle utility 提升 > 20%

### Phase 4: 验证与上线 (Week 7-8)

1. Validation 测试
2. Test 揭盲（一次性）
3. Admission Gate 检查
4. 灰度上线

---

## 关键文档

| 文档 | 用途 |
|------|------|
| `document/factor_and_expert_optimization_plan.md` | 完整优化计划 |
| `document/phase0_completion_report.md` | Phase 0 验收报告 |
| `document/phase0_summary.md` | Phase 0 执行总结 |
| `document/current_status_and_action_guide.md` | 当前状态（本文件）|

---

## 快速行动指令

### 如果要继续 Phase 1.2

```bash
# 1. 创建实验脚本框架
# 2. 定义因子标准化逻辑
# 3. 实现分层回测框架
# 4. 运行 10 股票快速验证
# 5. 分析结果并筛选因子
```

### 如果要跳过 Phase 1.2（快速验证）

可以先在 10 只股票上快速验证 Phase 1.2，如果发现现有因子已经足够好，可以直接进入 Phase 2 权重优化。

---

**当前状态**: ✅ Phase 0 完成  
**下一行动**: Phase 1.2 分层筛选实验
