# Transformer State v3 vs 专家系统重构：方案对比

> **日期**: 2026-08-20
> **背景**: Phase 2 诊断发现 Transformer 方案的根本性问题

---

## 一句话总结

| 方案 | 核心思路 | 结果 |
|------|---------|------|
| **Transformer State v3** | 检索历史相似状态，复用当时的最优专家 | ❌ Phase 2 STOP（状态相似≠专家有效）|
| **专家系统重构** | 用宏观+技术特征直接预测每个专家的未来表现 | ✅ 可执行，基于金融学原理 |

---

## 详细对比表

### 1. 问题假设

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **核心假设** | 相似市场状态 → 相似最优专家 | 当前特征(技术+宏观+跨资产) → 预测未来专家表现 |
| **假设验证** | ❌ Phase 1 证伪（一致性↑但utility↓） | ✅ 符合监督学习标准框架 |
| **金融学基础** | 弱（忽略非平稳性、regime切换） | 强（Regime-Switching, Factor Models） |

**Phase 1 证据**:
```
PCA检索结果：
- 邻居一致性提升: +0.018 to +0.021 (p<0.001) ✓
- Query utility恶化: -0.003 to -0.005 (p>0.98)  ✗
- 结论: 技术指标相似性不预测专家收益
```

---

### 2. 特征空间

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **特征维度** | 28维（纯技术指标） | 40+维（技术+宏观+跨资产） |
| **技术指标** | RSI, MACD, 布林带, ATR, EMA等 | 同左，但作为子集 |
| **宏观指标** | ❌ 无 | ✅ VIX, 市场广度, 期限利差, 行业轮动 |
| **相对指标** | ❌ 无 | ✅ 相对SPY强度, 行业内排名, 跨资产相关性 |
| **信息增量** | 低（状态特征 ≈ 专家决策依据） | 高（宏观维度独立于个股技术） |

**关键差异**:
- Transformer v3: 用**生成专家决策的特征**去预测**专家结果** → 信息循环
- 专家重构: 引入**独立信息源**(VIX、市场广度) → 打破循环

---

### 3. 专家池设计

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **专家数量** | 8个 | 6-8个 |
| **信息源** | 1个（技术分析的超参数变体） | 5-6个（技术、宏观、相对强度、波动率、情绪） |
| **平均相关性** | >0.60（高度同质化） | <0.50（目标：正交） |
| **专家列表** | naive, drift, sm_*, fsm_*, ml_filter, adaptive_router, cash | momentum, mean_reversion, volatility_breakout, relative_strength, macro_defensive, sentiment_contrarian, cash |

**Transformer v3的问题**:
```python
# 8个专家的相关性矩阵 (预期)
            sm_bay  sm_gen  sm_rand  fsm_bay  fsm_gen  fsm_rand  ml_filter
sm_bayesian  1.00    0.87    0.82     0.75     0.68     0.65      0.78
sm_genetic   0.87    1.00    0.85     0.70     0.73     0.68      0.80
# ... 全部>0.6

# 根因: 都基于相同的10因子 (mom, rsi, macd, bb, obv, vol, dd)
```

**专家重构的目标**:
```python
# 新专家池的相关性矩阵 (目标)
                  momentum  mean_rev  vol_break  rel_str  macro_def
momentum           1.00      0.15      0.30       0.45     -0.10
mean_reversion     0.15      1.00     -0.20       0.10      0.25
volatility_break   0.30     -0.20      1.00       0.35      0.15
relative_strength  0.45      0.10      0.35       1.00      0.20
macro_defensive   -0.10      0.25      0.15       0.20      1.00

# 平均相关性: 0.20 (远低于0.5)
```

---

### 4. 时间Horizon

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **Horizon** | 5 days | 20 days |
| **Oracle Utility** | 0.013-0.020 | (待测，预期更高) |
| **Signal/Noise** | 0.19 (极低) | (待测，预期>0.3) |
| **专家稳定性** | Match rate 15-24% | (待测，预期>30%) |
| **金融学依据** | 弱（5日噪音大） | 强（20日接近月度，技术分析有效窗口） |

**Phase 1证据**:
- 5日Oracle utility只有1.3-2%
- 远低于8%的标准差
- 说明"完美专家"也只能赚1-2%，大部分是噪音

---

### 5. 方法论

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **核心方法** | 检索（Retrieval） | 预测（Prediction） |
| **模型类型** | Transformer Encoder + 多loss | LightGBM多输出回归 |
| **训练复杂度** | 高（需GPU、geometry gate、消融实验） | 低（CPU、标准监督学习） |
| **可解释性** | 低（黑盒embedding） | 高（特征重要性、SHAP） |
| **过拟合风险** | 高（深度模型+小样本） | 中（树模型本身抗过拟合） |

**方法对比**:

```python
# Transformer v3
state_embedding = transformer_encoder(state_sequence)
similar_states = cosine_search(state_embedding, memory_bank)
selected_expert = similar_states[0].expert_id

# 问题: 如果相似状态的专家不work，检索无意义

# 专家重构
features = concat([technical, macro, cross_sectional])
predicted_sharpes = lgbm_model.predict(features)  # shape: (6,)
selected_expert = argmax(predicted_sharpes)

# 优势: 直接优化目标（预测sharpe），不依赖相似性假设
```

---

### 6. 成本与风险

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **研究周期** | 4-6周（全流程） | 6-8周（分6个Phase） |
| **实际执行** | 2周（Phase 1-2后STOP） | (待执行) |
| **计算资源** | GPU 5-7天 | CPU only |
| **存储需求** | ~500MB | ~1GB |
| **外部数据** | 无（用现有v2 panel） | VIX, SPY (免费) + 可选基本面 |
| **Early Stop** | ✅ Phase 1-2 | ✅ 每个Phase |
| **失败成本** | 2周（已发生） | 最多2周/Phase |

---

### 7. 验证标准

| 维度 | Transformer v3 | 专家重构 |
|------|---------------|----------|
| **Phase 1** | Baseline一致性 gate | Baseline utility gate |
| **Phase 2** | 诊断分析 | 专家正交性 |
| **Phase 3** | Transformer训练 | 预测模型训练 |
| **Validation** | Top-k retrieval utility | Predicted vs realized sharpe |
| **Test** | Admission gate (5项) | Admission gate (5项) |

**Phase 1对比**:

| Method | Transformer v3 | 专家重构 (待测) |
|--------|---------------|----------------|
| B01 PCA单日 | ✓ 一致性+0.018, ✗ utility-0.003 | N/A |
| B02 PCA摘要 | ✓ 一致性+0.021, ✗ utility-0.005 | N/A |
| B04 20日horizon | N/A | (待测) |
| B05 20日+宏观 | N/A | (待测) |

---

### 8. 为什么Transformer失败了？

#### 原因1: 特征-目标不对齐

```
技术指标 → factor_score → target_position → 专家决策
                ↓
         (用同样的技术指标)
                ↓
     检索相似状态 → 预测专家结果
     
问题: 技术指标已经**决定了**专家会怎么做
     但不能预测**做的结果**（市场非平稳）
```

**类比**:
```
❌ 用"今天的天气"预测"今天穿什么衣服最舒服"
   → 即使找到天气相似的历史日期，那天穿的衣服可能随机

✅ 用"今天的天气+季节+场合"预测"哪种穿衣风格更舒服"
   → 问题变成监督学习，有规律可循
```

#### 原因2: 专家同质化

8个专家都基于相同的10个因子，只是优化方法不同：
- `sm_bayesian`: 贝叶斯优化权重
- `sm_genetic`: 遗传算法优化权重
- `fsm_bayesian`: 贝叶斯 + FA降维

**结果**: 它们在相同的技术形态下做出**高度相似的决策**。

如果技术形态预测不了收益（Phase 1已证明），那再怎么优化这8个专家也没用。

#### 原因3: Horizon太短

5日窗口内：
- 技术指标模式还没展开
- 市场噪音主导
- 专家优势无法体现

类比股票交易：
- 1分钟K线 → 噪音为主
- 日K线 → 技术分析开始有效
- 周/月K线 → 趋势明确

5日相当于"日K线里的1分钟"。

---

### 9. 专家重构为什么可能成功？

#### 优势1: 信息增量

```python
# Transformer v3 (失败)
features = [rsi, macd, bb_position, ema_spread, ...]  # 28维技术
# 这些已经决定了sm/fsm怎么做，无法预测结果

# 专家重构 (有希望)
features = [
    # 个股技术 (28维)
    rsi, macd, ...,
    
    # 宏观环境 (5维) ← 新增！
    vix, market_breadth, term_spread, sector_rotation, spy_momentum,
    
    # 相对位置 (7维) ← 新增！
    rel_strength_vs_spy, sector_rank, beta_regime, ...
]

# VIX=30 vs VIX=15，同样的RSI=70含义完全不同
# 这些信息在sm/fsm决策中没有，是真正的增量
```

**金融学依据**: 
- **Fama-French**: 市场、规模、价值、动量在不同环境下轮动
- **Regime-Switching**: 技术策略在高波vs低波regime下表现相反
- **Flight to Quality**: 市场恐慌时，相对强度失效，防御为王

#### 优势2: 专家正交

新专家池设计原则：
1. **momentum**: 纯趋势跟随（trending regime）
2. **mean_reversion**: 纯均值回归（ranging regime）
3. **volatility_breakout**: 低波后扩张（breakout regime）
4. **relative_strength**: 强者恒强（bull market）
5. **macro_defensive**: 高VIX降仓（bear market / uncertainty）

这5个专家适用于**不同的市场regime**，天然低相关。

#### 优势3: 监督学习 > 检索

```python
# 检索的问题
if 历史上没有"完全相同"的状态:
    检索失败
    
if 历史上"相似状态"的最优专家是噪音:
    检索到的是噪音

# 监督学习的优势
model.fit(X_train, Y_train)  # 学习"平均规律"
# 即使训练集没有完全相同的样本，模型也能泛化
# 即使某些样本有噪音，集成模型(树)可以平滑
```

#### 优势4: 20日Horizon

更长的时间窗口：
- 技术模式有时间展开
- 噪音被平滑
- 专家表现更稳定
- Sharpe更可预测

**代价**: 
- 换手成本↑（但20日还可接受）
- 反应速度↓（但量化本来就不追求日内）

---

### 10. 风险对比

| 风险类型 | Transformer v3 | 专家重构 |
|---------|---------------|----------|
| **假设不成立** | ✗ 已发生（Phase 1证伪） | 可能（但每个Phase可验证） |
| **过拟合** | 高（深度模型+少样本） | 中（树模型+交叉验证） |
| **数据依赖** | 低（用现有v2） | 中（需VIX等宏观数据） |
| **计算成本** | 高（GPU） | 低（CPU） |
| **黑盒风险** | 高（无法解释embedding） | 低（特征重要性可视化） |
| **维护成本** | 高（Transformer模型复杂） | 低（LightGBM标准流程） |

---

## 决策建议

### 如果你想要...

| 目标 | 推荐方案 | 理由 |
|------|---------|------|
| **最快验证** | 专家重构 Phase 0-1 | 2周内验证核心假设 |
| **最小风险** | 继续用adaptive_router | Phase 0可能发现它已足够 |
| **最大收益** | 专家重构 Phase 0-5 | 系统性解决根本问题 |
| **学术价值** | 两者都做 | Transformer失败也是负向结果 |
| **生产稳定** | 专家重构 | 可解释、可维护 |

### 资源对比

| 资源 | Transformer v3 (已终止) | 专家重构 (完整) |
|------|----------------------|----------------|
| **人力** | 0.5周研究员（实际） | 6周研究员 + 1周支持 |
| **时间** | 2周（Phase 1-2） | 8周（Phase 0-6） |
| **GPU** | 0天（未到Phase 3） | 0天（不需要） |
| **存储** | ~100MB | ~1GB |
| **外部成本** | $0 | $0 (用免费数据) |

---

## 最终建议

### 立即执行：Phase 0 (1-2天)

```bash
# 1. 审计adaptive_router表现
python model-test/phase0_expert_audit.py

# 2. 审计专家相关性
python model-test/phase0_expert_correlation.py

# 3. 根据结果决定
if adaptive_router_sufficient and low_correlation:
    decision = "STOP - 无需重构"
elif adaptive_router_ok:
    decision = "Phase 1 only - 增量改进"
else:
    decision = "Phase 1-5 - 完整重构"
```

### 如果Phase 0决定继续：

**Week 1**: Phase 1 (宏观特征 + 20日horizon)
- 快速验证核心假设
- 如果失败，损失1周

**Week 2-3**: Phase 2 (多样化专家)
- 构建正交专家池
- 如果失败，损失3周

**Week 4-5**: Phase 3-4 (预测模型)
- 训练监督学习模型
- 如果失败，损失5周

**Week 6-7**: Phase 5-6 (Test + 部署)
- 一次揭盲验证
- 影子模式上线

---

## 总结

| 维度 | Transformer State v3 | 专家系统重构 |
|------|---------------------|-------------|
| **状态** | ❌ Phase 2 终止 | ✅ 可执行计划 |
| **核心问题** | 假设不成立（状态相似≠专家有效） | 假设合理（监督学习框架） |
| **金融学基础** | 弱（忽略非平稳性） | 强（Regime-Switching, Multi-Factor） |
| **专家设计** | 同质化（1个技术策略的变体） | 多样化（5-6个信息源） |
| **特征空间** | 28维纯技术 | 40+维（技术+宏观+跨资产） |
| **Horizon** | 5日（信噪比0.19） | 20日（更稳定） |
| **方法** | 深度学习检索 | LightGBM预测 |
| **成本** | GPU + 4-6周 | CPU + 6-8周 |
| **风险** | 高（已失败） | 中（分阶段验证） |
| **可解释性** | 低 | 高 |
| **推荐度** | ❌ 不推荐 | ✅ 推荐 |

**一句话**: Transformer State v3 试图用检索解决预测问题，且专家池同质化严重。专家系统重构直击根本：多样化信息源 + 监督学习预测 + 更长horizon。

---

**下一步**: 执行 Phase 0，见 `document/quickstart_phase0.md`
