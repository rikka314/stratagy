# 三个方案的快速对比

> **创建日期**: 2026-08-21
> **目的**: 澄清三个不同的优化方向

---

## 一句话区分

| 方案 | 优化对象 | 一句话描述 |
|------|---------|-----------|
| **Transformer State v3** | Meta-learner (状态检索) | 用深度学习检索历史相似状态，复用当时最优专家 |
| **Adaptive Router 重构** | Meta-learner (专家路由) | 改进专家选择器，但专家池不变 |
| **因子与专家优化** | Base learners (因子+专家) | 重新设计因子体系和专家池本身 |

---

## 详细对比

### 方案 1: Transformer State v3 ❌ (已终止)

**问题**: 检索历史相似状态

**假设**: 
- 技术指标相似的状态 → 专家表现相似
- 可以从历史中学习

**为什么失败**:
- 技术指标相似 ≠ 未来收益相似 (市场非平稳)
- 专家池同质化严重 (8个专家都是技术指标的超参数变体)
- 5日 horizon 太短，信噪比极低

**Phase 2 诊断结论**: 
- 邻居一致性提升 ✓
- Query utility 恶化 ✗
- 状态相似性不预测专家效果

**决策**: STOP，不进入 Phase 3-6

---

### 方案 2: Adaptive Router / Expert System 重构

**问题**: 改进专家选择器

**假设**:
- 现有专家池是合理的
- 问题在于选择逻辑 (adaptive_router_v1 不够好)
- 加入宏观特征可以改善选择

**优化内容**:
```
现有专家池 (不变)
  ↓
更好的选择器 (改进)
  - 加入宏观特征 (VIX, 市场广度)
  - 延长 horizon (5日 → 20日)
  - 用监督学习直接预测每个专家的 sharpe
```

**适用场景**:
- 如果 Phase 0 发现 adaptive_router 表现很差 (Sharpe < 0.5)
- 但你**不想改动现有 sm/fsm 专家**

**问题**:
- 如果专家本身同质化严重，再好的选择器也无法解决根本问题
- 类比: 8 个专家都是 iPhone 不同颜色，选择器无论多智能，也给不了 Android 用户想要的

---

### 方案 3: 因子与专家优化 ✅ (推荐)

**问题**: 因子和专家设计本身有问题

**诊断**:
1. **因子同质化**: 10个因子中8个是技术指标，携带的独立信息很少
2. **专家同质化**: sm/fsm 系列本质是同一模型的超参数变体
3. **缺少宏观维度**: 所有因子都是个股技术指标，无法区分市场环境

**优化内容**:

```
Phase 1: 因子分层与筛选
  - 将 10 因子按金融学原理分为 3 层
    * 第一层: 趋势动量 (mom_short, mom_long, macd)
    * 第二层: 均值回归 (rsi, bb_position, price_position)
    * 第三层: 风险与量 (vol, drawdown, obv, volume)
  - 新增第四层: 宏观与相对
    * vix_level, vix_regime
    * rel_strength_spy (相对 SPY 强度)
    * beta_20d
    * sector_momentum
  - 每层筛选出最有效的因子

Phase 2: 因子权重优化
  - Grid Search (粗筛)
  - Bayesian Optimization (精调)
  - Feature Selection (自动去冗余)

Phase 3: 专家池重构
  - 不再是同一模型的超参数变体
  - 每个专家基于不同信息源
    * momentum: 只用动量因子
    * mean_reversion: 只用均值回归因子
    * macro_defensive: 只用宏观因子
    * composite: 全因子集成

Phase 4: 验证与上线
  - Validation 测试
  - Test 揭盲
  - 灰度上线
```

**核心思路**:
```
❌ 旧设计
10 因子 (8个技术指标) 
  → 线性加权 
  → 8 个专家 (只是权重不同)
  → 平均相关性 > 0.6

✅ 新设计
分层因子 (技术 + 宏观 + 相对)
  → 每层筛选最优
  → 4-6 个正交专家 (不同信息源)
  → 平均相关性 < 0.5
```

**适用场景**:
- 你的根本问题是**因子和专家设计**，而非选择逻辑
- 你愿意推翻现有 sm/fsm 专家池，重新设计
- 你想要**可解释、可维护**的系统

**优势**:
1. 解决根本问题 (同质化)
2. 引入独立信息源 (宏观、相对强度)
3. 可解释性强 (每个专家有明确的金融学逻辑)
4. CPU only，成本低

---

## 你的实际需求分析

根据你说的：

> "那么你根据我的项目，深度研究一下有没有已知的金融学关系是可以用于我这个因子系统的，或者我这个因子系统和专家体系本身就有很大的问题"

**我的判断**: 你需要的是**方案 3: 因子与专家优化**

**理由**:

1. **你关心的是因子和专家本身**，而非选择器
2. **Transformer State v3 的失败已经暴露了根本问题**:
   - 8 个专家高度相关 (都基于相同的 10 因子)
   - 10 因子中 8 个是技术指标 (信息冗余)
   - 缺少宏观维度 (无法区分市场 regime)

3. **方案 2 (Adaptive Router 重构) 治标不治本**:
   - 改进选择器无法解决专家同质化
   - 类比: 选一个最不烂的苹果，不如去买橙子

4. **方案 3 直击根本**:
   - 重新设计因子体系 (加入宏观、相对强度)
   - 重新设计专家池 (每个专家用不同信息源)
   - 基于金融学原理 (Regime-Switching, Multi-Factor)

---

## 具体执行建议

### 如果你同意方案 3，立即开始：

**Week 1 (最关键)**:
```bash
# Day 1-2: 下载宏观数据
python data-pipeline/download_macro_data.py

# Day 3-5: 实现 core/macro_factors.py

# Day 6-7: 快速验证 (10 只股票)
python model-test/run_factor_layered_selection.py \
    --market US \
    --symbols AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,V,JNJ \
    --quick
```

**Week 1 结束时你会知道**:
1. 宏观因子是否有增量价值
2. 哪些技术因子真正有效
3. 是否值得继续 Phase 2-3

**如果 Week 1 验证失败**:
- 损失: 1 周
- 收获: 明确证据证明当前因子体系的天花板
- 决策: STOP，或尝试完全不同的方向 (基本面、情绪)

**如果 Week 1 验证成功**:
- 进入 Phase 2 (权重优化)
- 进入 Phase 3 (专家重构)
- 总计 6-8 周完成

---

## 我给你的三份文档

1. **`transformer_state_v3_implementation_roadmap.md`** ❌
   - Transformer State v3 的完整计划
   - **Phase 2 已 STOP**，不再执行
   - 保留作为负向结果的完整记录

2. **`expert_system_reconstruction_roadmap.md`** ⚠️
   - Adaptive Router 重构计划
   - 适用场景: 专家池不变，只改选择器
   - **如果你想保留现有 sm/fsm 专家，用这个**

3. **`factor_and_expert_optimization_plan.md`** ✅
   - 因子与专家优化计划 (推荐)
   - 适用场景: 重新设计因子体系和专家池
   - **如果你想解决根本问题，用这个**

---

## 最终建议

**我的推荐**: 执行**方案 3 (因子与专家优化)**

**执行路径**:

```
Week 1: Phase 1.1-1.3 (分层筛选)
  ↓
  验证: 宏观因子是否有效？
  ↓
如果有效 → Week 2-4: Phase 2 (权重优化)
如果无效 → STOP，重新思考方向
  ↓
Week 5-6: Phase 3 (专家重构)
  ↓
Week 7-8: Phase 4 (验证上线)
```

**理由**:
1. Phase 1 只需 1 周，快速验证
2. 每个 Phase 都有 Early Stop
3. 解决根本问题 (同质化)
4. 成本可控 (CPU only)
5. 可解释性强

---

**下一步**: 你确认要执行方案 3 吗？如果确认，我立即帮你：

1. 创建 `data-pipeline/download_macro_data.py`
2. 实现 `core/macro_factors.py`
3. 创建 Phase 1 快速验证脚本

还是你想先做 Phase 0，审计一下 adaptive_router 是否已经足够好？
