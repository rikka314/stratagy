# 专家系统重构路线图

> **创建日期**: 2026-08-20
> **背景**: Transformer State v3 Phase 2 诊断发现三个根本问题
> **目标**: 构建基于金融学原理的多维专家系统

---

## 执行摘要

### 诊断出的三个核心问题

1. **信息循环**: 用生成专家决策的技术指标特征去预测专家结果
2. **专家同质化**: 8个专家本质是1个技术策略的超参数变体
3. **信噪比极低**: 5日horizon + 纯技术指标 = 信号被噪音淹没

### 解决方案框架

**不做**: ❌ 深度学习状态检索（已证明无效）

**要做**: ✅ 三层重构
1. **立即可做** (1-2周): 加入宏观特征 + 延长horizon
2. **中期重构** (3-4周): 构建多样化专家池
3. **长期优化** (5-6周): 直接预测专家表现

---

## Phase 0: 前置验证（Day 1-2）

**目标**: 确认 adaptive_router_v1 是否已经足够好，避免过度优化

### P0.1: Adaptive Router 性能基准

**任务**: 
```bash
# 提取 adaptive_router_v1 在 US Validation 上的表现
python model-test/run_adaptive_router_baseline.py \
    --market US \
    --window_id wf_01,wf_02,wf_03,wf_04 \
    --output document/adaptive_router_baseline.json
```

**验收标准**:
- [ ] Sharpe > 0.5
- [ ] Win rate > 55%
- [ ] Max drawdown < 15%
- [ ] Turnover < 100% (年化)

**决策分支**:
- 如果全部通过 → **STOP，无需重构**
- 如果 2-3 项通过 → 进入 Phase 1（增量改进）
- 如果 ≤1 项通过 → 进入 Phase 1+2（完整重构）

### P0.2: 专家同质性审计

**任务**:
```python
# 计算 8 个专家的 daily return 相关矩阵
# 位置: model-test/model_test/expert_correlation_audit.py
```

**验收标准**:
- [ ] 生成 8x8 相关矩阵热力图
- [ ] 识别高度相关对 (corr > 0.8)
- [ ] 报告平均成对相关系数

**预期发现**:
- `sm_*` 专家之间 corr > 0.85
- `fsm_*` 专家之间 corr > 0.80
- 整体平均相关 > 0.60 → 确认同质化问题

---

## Phase 1: 立即改进 - 加入宏观维度（Week 1，Day 3-7）

**状态**: ✅ **EXECUTED / GATE FAILED / STOP** (2026-08-21)

**目标**: 最小代价验证“宏观+微观”框架是否有效

**正式结果**: 四折、60 标的、8 个真实专家的 source-locked 实验已完成；跨 horizon 的 B04 准入按 per-day Query utility 比较，相对 B01 为 `+0.001293`，低于 `+0.002` 门槛；B05 相对 B04 为 `+0.000023`，低于 `+0.003` 门槛。两项组合 gate 均失败，因此按本路线图停止，不进入 Phase 2。B04 raw 累积 utility `-0.004106` 只作诊断。正式证据见 `model-test/outputs/expert_system_phase1_us/` 和 `document/phase1_completion_report.md`。

### P1.1: 宏观特征工程

**新增特征** (5个核心维度):

```python
# 文件: core/macro_factors.py

class MacroFactors:
    def compute(self, date, stock_symbol):
        return {
            # 1. 市场波动率 regime
            "vix_level": self.get_vix(date),
            "vix_regime": self.classify_vix_regime(date),  # low/med/high
            
            # 2. 相对强度
            "rel_strength_vs_spy": self.compute_relative_strength(
                stock_symbol, "SPY", window=20
            ),
            
            # 3. 市场广度
            "market_breadth": self.compute_breadth_indicator(date),
            # (上涨股票数 / 总股票数，需要市场宽度数据)
            
            # 4. 个股 beta
            "beta_20d": self.compute_rolling_beta(
                stock_symbol, "SPY", window=20
            ),
            
            # 5. 行业相对表现
            "sector_momentum": self.compute_sector_relative_momentum(
                stock_symbol, date, window=20
            ),
        }
```

**数据需求**:
- VIX 历史数据（Cboe 官方日线 CSV）
- SPY 日线数据（AkShare `stock_us_daily`）
- 行业分类（Nasdaq stock screener）

**实现步骤**:

1. **Day 3**: 下载 VIX、SPY 与 sector map
   ```bash
   python data-pipeline/download_macro_data.py
   ```

   下载链 fail-closed，并写入 `data/macro/macro_data_manifest.json`；禁止以模拟数据替代正式证据。

2. **Day 4**: 实现 macro_factors.py（5个特征）

3. **Day 5**: 集成到 research-only Phase 1 pipeline
   ```python
   # 实际入口: model-test/run_phase1_baseline.py
   
   # 原有 28 维技术指标
   tech_features = self.compute_technical_factors(...)
   
   # 新增 5 维宏观特征
   macro_features = self.macro_factors.compute(date, symbol)
   
   # 合并为 33 维状态特征
   state_features = {**tech_features, **macro_features}
   ```

### P1.2: 延长 Horizon 到 20 日

**修改标签生成**:

```python
# 文件: core/expert_utility.py

class ExpertUtilityV4:
    """
    V4 改动:
    - horizon: 5 days → 20 days
    - target: single utility → {sharpe, win_rate, return}
    """
    
    def compute_expert_utility(self, expert_decisions, future_prices):
        # 20 日窗口
        window = 20
        
        returns = []
        for d in range(window):
            daily_ret = self.compute_daily_return(
                expert_decisions[d], future_prices[d]
            )
            returns.append(daily_ret)
        
        return {
            "mean_return": np.mean(returns),
            "sharpe_ratio": np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252/20),
            "win_rate": np.mean([r > 0 for r in returns]),
            "max_drawdown": self.compute_max_dd(returns),
        }
```

**重新生成标签**:

```bash
# Day 6-7: 重新生成 20 日 utility labels
python model-test/run_phase1_baseline.py \
    --config model-test/configs/expert_system_phase1_us.json
```

### P1.3: Baseline 重跑（20日 + 宏观特征）

**实验设计**:

| Method | 特征维度 | Horizon | 说明 |
|--------|---------|---------|------|
| **B04** | 28 (冻结 state features) | 20 days | 对照组：延长 horizon |
| **B05** | 33 (冻结 state + 5 个 observed macro) | 20 days | 实验组：加入宏观 |
| **B01** | 28 (冻结 state features) | 5 days | 原 baseline (对比) |

> 仓库事实修正：冻结的 28 维 state schema 并非“纯技术指标”，其中已经包含市场与专家上下文。Phase 1 保持该 schema 不变，只在 B05 新增 VIX、SPY 相对强度、市场广度、SPY beta 和行业相对动量五维，以确保可和既有 evidence 对齐。

**执行**:

```bash
python model-test/run_phase1_baseline.py \
    --config model-test/configs/expert_system_phase1_us.json
```

### P1.4: Phase 1 验收

**成功标准** (与 B01 比较):

1. **B04 vs B01**: 
   - Per-day normalized Query utility 提升 > +0.002 → 20日horizon有效
   - Match rate 提升 > 5% → 专家稳定性改善

2. **B05 vs B04**:
   - Query utility 提升 > +0.003 → 宏观特征有增量价值
   - Regret 下降 → 特征对齐改善

> Oracle utility 只由相同 query rows 和标签决定，B04/B05 的 oracle 必然相同；不能把“oracle 提升”作为新增特征的验收条件。正式实现用 selected Query utility 与 regret 判断增量价值。

**决策**:
- 两项均通过 → 进入 Phase 2
- 仅 B04 通过 → 只延长horizon，Phase 2 简化
- 均未通过 → STOP，问题更深层

**2026-08-21 正式验收**:

| 对比 | Gate Query utility Δ | Match rate Δ | Regret Δ | 结论 |
|---|---:|---:|---:|---|
| B04 vs B01 | +0.001293（per-day） | +10.92 pp | +0.008245 | FAIL |
| B05 vs B04 | +0.000023 | +0.13 pp | -0.000023 | FAIL |

- B04 的 per-day normalized Query utility Δ 为 `+0.001293`，95% CI `[+0.000834, +0.001759]`，未达到 `+0.002` utility gate；raw 累积 utility Δ `-0.004106` 仅作跨 horizon 诊断。
- B05 的 Query utility 95% CI 为 `[-0.002167, +0.001959]`，无显著增量证据。
- **决策**: `stop_phase1_gate_failed`；Phase 2–6 不执行，除非另行制定并审批新的研究假设与预注册 gate。

---

## Phase 2: 中期重构 - 多样化专家池（Week 2-3，Day 8-21）

**目标**: 构建信息源正交的专家集合

### P2.1: 专家池重新设计

**当前专家** (同质化严重):
```python
current_experts = [
    "naive", "drift",           # baseline
    "sm_bayesian", "sm_genetic", "sm_*",   # 技术策略变体
    "fsm_bayesian", "fsm_genetic", "fsm_*", # 技术策略变体
    "ml_filter",                # 技术策略过滤
    "adaptive_router",          # 元策略
    "cash",                     # 防守
]
```

**新专家池** (信息源多样化):

```python
new_expert_pool = {
    # 第一类：技术面 (保留最优1个)
    "momentum": {
        "factors": ["mom_short", "mom_long", "rsi"],
        "logic": "纯动量跟随",
        "适用regime": "trending_market"
    },
    
    # 第二类：均值回归
    "mean_reversion": {
        "factors": ["bb_position", "rsi_oversold", "price_position"],
        "logic": "超买超卖反转",
        "适用regime": "ranging_market"
    },
    
    # 第三类：波动率
    "volatility_breakout": {
        "factors": ["atr_percentile", "bb_width", "volume_surge"],
        "logic": "低波后突破",
        "适用regime": "low_vol_expansion"
    },
    
    # 第四类：相对强度
    "relative_strength": {
        "factors": ["rel_strength_vs_spy", "sector_momentum", "beta"],
        "logic": "强者恒强，弱者恒弱",
        "适用regime": "market_trending"
    },
    
    # 第五类：宏观择时
    "macro_defensive": {
        "factors": ["vix_level", "market_breadth", "term_spread"],
        "logic": "高风险环境降仓",
        "适用regime": "high_uncertainty"
    },
    
    # 第六类：基本面 (如果有数据)
    "value_quality": {
        "factors": ["pe_ratio", "roe", "debt_ratio"],
        "logic": "低估值高质量",
        "适用regime": "value_regime"
    },
    
    # 第七类：情绪
    "sentiment_contrarian": {
        "factors": ["news_sentiment", "analyst_revisions", "social_buzz"],
        "logic": "过度悲观买入",
        "适用regime": "oversold_sentiment"
    },
    
    # 第八类：防守
    "cash": {
        "logic": "保留现金",
        "适用regime": "all"
    },
}
```

### P2.2: 专家实现优先级

**Phase 2.1 (Day 8-14)**: 实现前5个专家（不依赖外部数据）

1. **momentum** (Day 8-9)
   ```python
   # 文件: strategy/experts/momentum_expert.py
   
   class MomentumExpert:
       def compute_target_position(self, factors):
           # 纯动量：20日收益 > 0 且 RSI > 50
           if factors["mom_long"] > 0 and factors["rsi"] > 50:
               return 0.8  # 做多
           elif factors["mom_long"] < 0 and factors["rsi"] < 50:
               return 0.0  # 空仓
           else:
               return 0.4  # 中性
   ```

2. **mean_reversion** (Day 10)
3. **volatility_breakout** (Day 11-12)
4. **relative_strength** (Day 13)
5. **macro_defensive** (Day 14)

**Phase 2.2 (Day 15-18)**: 基本面和情绪专家（可选）

**决策**: 如果没有基本面/情绪数据，Phase 2 只做前5个专家

### P2.3: 正交性验证

**Day 19**: 计算新专家池的相关性

```python
# 脚本: model-test/validate_expert_orthogonality.py

# 1. 回测每个专家（US Validation，20日horizon）
# 2. 计算 daily return 相关矩阵
# 3. 验证平均成对相关 < 0.5

# 验收标准:
assert avg_pairwise_corr < 0.5  # 低于原0.6+
assert max_pairwise_corr < 0.7  # 无高度相关对
```

### P2.4: Phase 2 验收

**Day 20-21**: 完整回测

```bash
python model-test/run_multi_expert_backtest.py \
    --experts momentum,mean_reversion,volatility_breakout,relative_strength,macro_defensive,cash \
    --market US \
    --windows wf_01,wf_02,wf_03,wf_04 \
    --horizon 20 \
    --output model-test/outputs/phase2_multi_expert/
```

**成功标准**:
- [ ] 平均成对相关 < 0.5
- [ ] 至少3个专家在不同fold表现最优（分散性）
- [ ] Oracle utility (最优专家选择) > Phase 1 B05

**决策**:
- 通过 → 进入 Phase 3
- 未通过 → 审视专家设计，可能需要基本面数据

---

## Phase 3: 问题重构 - 直接预测而非检索（Week 4-5，Day 22-35）

**目标**: 用监督学习直接预测每个专家的20日表现

### P3.1: 监督学习框架

**不做**: ❌ 检索历史相似状态

**要做**: ✅ 直接预测

```python
# 训练数据
X = [
    state_features_33d,   # 技术+宏观
    macro_features_5d,    # 宏观单独
    cross_sectional_rank  # 相对排名
]

Y = [
    expert_1_20d_sharpe,
    expert_2_20d_sharpe,
    expert_3_20d_sharpe,
    expert_4_20d_sharpe,
    expert_5_20d_sharpe,
    expert_6_20d_sharpe,
]

# 模型: 多输出回归
model = LGBMRegressor(objective="regression", n_estimators=100)
model.fit(X_train, Y_train)

# 推理
predicted_sharpes = model.predict(X_query)
best_expert = np.argmax(predicted_sharpes)
```

### P3.2: 特征工程增强

**新增维度** (Day 22-24):

```python
# 文件: strategy/features/cross_sectional_features.py

class CrossSectionalFeatures:
    """跨股票相对特征"""
    
    def compute(self, stock, date, universe):
        return {
            # 相对排名
            "momentum_percentile": self.rank_in_universe(
                stock, "mom_long", universe, date
            ),
            
            # 相对波动率
            "volatility_percentile": self.rank_in_universe(
                stock, "atr", universe, date
            ),
            
            # 相对估值 (如果有数据)
            "valuation_percentile": ...,
            
            # 行业内排名
            "sector_rank": self.rank_in_sector(stock, date),
        }
```

### P3.3: 模型实现

**Day 25-28**: 实现三种模型并对比

| 模型 | 类型 | 优势 | 何时用 |
|------|------|------|--------|
| **M01: LightGBM** | 多输出回归 | 快速、可解释 | 默认 |
| **M02: Random Forest** | 集成学习 | 稳定、少调参 | 对比 |
| **M03: Linear Ridge** | 线性模型 | 最简单、baseline | 对照 |

**训练协议**:

```python
# 文件: model-test/model_test/expert_performance_predictor.py

class ExpertPerformancePredictor:
    def __init__(self, model_type="lgbm"):
        self.model_type = model_type
        self.model = self._init_model()
    
    def train(self, X_train, Y_train):
        """
        X_train: (N, 40+) 特征矩阵
        Y_train: (N, 6) 专家20日sharpe矩阵
        """
        self.model.fit(X_train, Y_train)
    
    def predict_best_expert(self, X_query):
        """返回预测最优专家索引"""
        predicted_sharpes = self.model.predict(X_query)
        return np.argmax(predicted_sharpes, axis=1)
    
    def predict_top_k(self, X_query, k=3):
        """返回 top-k 专家索引"""
        predicted_sharpes = self.model.predict(X_query)
        return np.argsort(predicted_sharpes, axis=1)[:, -k:][:, ::-1]
```

### P3.4: 实验设计

**Day 29-32**: 完整实验

| Method | 特征 | 模型 | 输出 |
|--------|------|------|------|
| **M01** | 33d (技术+宏观) | LightGBM | top-1 expert |
| **M02** | 33d | Random Forest | top-1 expert |
| **M03** | 33d | Linear Ridge | top-1 expert |
| **M04** | 45d (33d + 跨资产) | LightGBM | top-1 expert |
| **M05** | 45d | LightGBM | top-3 ensemble |

**验收指标**:

```python
metrics = {
    "query_utility_mean": ...,
    "query_utility_std": ...,
    "sharpe_ratio": ...,
    "regret_vs_oracle": ...,
    "match_rate": ...,  # 是否选到真实最优
    "top3_capture_rate": ...,  # top-3中是否包含最优
}
```

### P3.5: Phase 3 验收

**Day 33-35**: 统计检验和报告

**成功标准** (与 adaptive_router_v1 比较):

1. **Query Utility**:
   - M01/M04 mean utility > adaptive_router + 0.005
   - 置信度 95% (bootstrap)

2. **Sharpe Ratio**:
   - M01/M04 Sharpe > adaptive_router * 1.2

3. **Stability**:
   - 4个fold中至少3个表现最优

4. **Feature Importance**:
   - 宏观特征在 top-10 中占 ≥2个 → 证明宏观有效
   - 技术特征不能dominate全部 → 证明多样性

**决策**:
- 全部通过 → 进入 Phase 4 (Test揭盲)
- 部分通过 → 调整模型/特征，重跑 Phase 3
- 未通过 → STOP，或回到 Phase 2 重新设计专家

---

## Phase 4: Validation 优化（Week 6，Day 36-42）

**目标**: 在 Validation 上调优超参数和集成策略

### P4.1: 超参数调优

**Day 36-38**: 针对 M01 (LightGBM) 调优

```python
# 使用 Optuna 自动调参
param_space = {
    "n_estimators": [50, 100, 200],
    "max_depth": [3, 5, 7],
    "learning_rate": [0.01, 0.05, 0.1],
    "min_child_samples": [10, 20, 50],
}

best_params = optuna_search(
    X_train, Y_train, X_val, Y_val,
    param_space, n_trials=50
)
```

### P4.2: 集成策略

**Day 39-40**: 测试多种集成方法

| 策略 | 说明 | 何时用 |
|------|------|--------|
| **Top-1** | 选择预测sharpe最高的单个专家 | 高置信度 |
| **Top-3 均权** | 前3个专家等权重 | 分散风险 |
| **Top-3 softmax权重** | 按predicted sharpe softmax加权 | 置信度加权 |
| **Threshold过滤** | 预测sharpe < 0.1则选cash | 防守 |

### P4.3: 风险控制

**Day 41**: 加入下行保护

```python
class RiskAwareExpertSelector:
    def select(self, predicted_sharpes, predicted_drawdowns):
        # 1. 过滤高风险专家
        safe_experts = [
            i for i, dd in enumerate(predicted_drawdowns)
            if dd < self.max_dd_threshold
        ]
        
        # 2. 在安全专家中选最优
        if len(safe_experts) == 0:
            return self.cash_expert_id
        
        best = max(safe_experts, key=lambda i: predicted_sharpes[i])
        return best
```

### P4.4: Phase 4 验收

**Day 42**: 生成最终 Validation 报告

```bash
python model-test/run_phase4_final_validation.py \
    --model M01_tuned \
    --ensemble top3_softmax \
    --risk_control enabled \
    --output document/phase4_validation_report.md
```

**成功标准**:
- [ ] Validation Sharpe > 1.0
- [ ] Max Drawdown < 10%
- [ ] Win Rate > 60%
- [ ] 4个fold稳定性 (std < 20% of mean)

---

## Phase 5: Test 一次揭盲（Week 7，Day 43-49）

**目标**: 在未见过的 Test 集上验证最终模型

### P5.1: Test 准备

**Day 43**: 冻结配置

```yaml
# 文件: config/expert_system_v4_frozen.yaml

model:
  type: lgbm
  params: {从Phase 4确定的最优超参数}

features:
  technical: 28d
  macro: 5d
  cross_sectional: 7d
  total: 40d

experts:
  pool: [momentum, mean_reversion, volatility_breakout, 
         relative_strength, macro_defensive, cash]
  count: 6

selection:
  strategy: top3_softmax
  risk_control: enabled
  max_drawdown_threshold: 0.15

horizon: 20 days
```

### P5.2: Test 执行

**Day 44**: 单次揭盲

```bash
# 严格协议：只运行一次，不回头
python model-test/run_test_揭盲.py \
    --config config/expert_system_v4_frozen.yaml \
    --market US \
    --test_window 2025-07-01_to_2025-12-31 \
    --output model-test/outputs/test_揭盲_final/
```

### P5.3: Admission Gate

**Day 45-47**: 逐项检查

| Gate | 标准 | 通过条件 |
|------|------|----------|
| **G1: Utility** | Test mean utility > Validation mean utility * 0.8 | 必须 |
| **G2: Sharpe** | Test Sharpe > 0.8 | 必须 |
| **G3: Drawdown** | Test Max DD < 12% | 必须 |
| **G4: Consistency** | Test vs Val metrics 相关 > 0.7 | 必须 |
| **G5: Oracle Gap** | Test regret / oracle utility < 0.6 | 建议 |

**决策逻辑**:
```python
if all([G1, G2, G3, G4]):
    decision = "PASS - 准入生产"
elif all([G1, G2, G3]):
    decision = "CONDITIONAL PASS - 监控上线"
else:
    decision = "FAIL - 不上线"
    reason = [未通过的gate列表]
```

### P5.4: Phase 5 交付

**Day 48-49**: 完整文档

1. **Test 揭盲报告**: `document/expert_system_v4_test_report.md`
2. **Evidence Manifest**: SHA-256校验的所有artifacts
3. **Admission Decision**: 明确的上线/不上线决策
4. **生产部署计划** (如果PASS)

---

## Phase 6: 生产部署（Week 8+，Day 50+）

**目标**: 将验证通过的系统接入线上

### P6.1: 影子模式（2周）

**Day 50-63**: 并行运行但不实际交易

```python
# 配置: 同时运行两套系统
systems = {
    "adaptive_router_v1": {
        "mode": "production",
        "allocation": 100%,
    },
    "expert_system_v4": {
        "mode": "shadow",      # 只记录决策，不执行
        "allocation": 0%,
    },
}

# 每日对比
daily_comparison = {
    "v1_decision": ...,
    "v4_decision": ...,
    "disagreement_rate": ...,
    "v4_hypothetical_pnl": ...,
}
```

**监控指标**:
- 决策差异率 < 30% (太高说明不稳定)
- 影子PnL tracking error < 5%
- 特征计算延迟 < 100ms

### P6.2: 灰度上线（2周）

**Day 64-77**: 10% → 30% → 50% → 100%

| Week | expert_system_v4分配 | adaptive_router_v1分配 | 监控 |
|------|---------------------|------------------------|------|
| Week 9 | 10% | 90% | 每日review |
| Week 10 | 30% | 70% | 每日review |
| Week 11 | 50% | 50% | 每2日review |
| Week 12 | 100% | 0% (降级备份) | 每周review |

### P6.3: 持续监控

**建立监控面板**:

```python
# Grafana / Streamlit 仪表盘

metrics = {
    # 实时性能
    "daily_return": ...,
    "cumulative_return": ...,
    "sharpe_ratio_30d": ...,
    "max_drawdown": ...,
    
    # 专家分布
    "expert_selection_distribution": ...,  # 饼图
    "expert_switching_frequency": ...,
    
    # 特征健康度
    "feature_missing_rate": ...,
    "feature_outlier_rate": ...,
    "macro_data_freshness": ...,
    
    # 模型健康度
    "prediction_confidence": ...,
    "prediction_vs_realized": ...,  # 校准曲线
}
```

**告警规则**:
- Sharpe < 0.5 连续3天 → 警告
- Max DD > 15% → 严重警告，考虑降级
- 特征缺失率 > 5% → 数据质量问题
- 专家选择集中度 > 80% (单一专家) → 多样性丧失

---

## 检查清单

### Phase 0 (Day 1-2)
- [ ] Adaptive router baseline 完成
- [ ] 专家相关性审计完成
- [ ] 决定是否需要重构

### Phase 1 (Day 3-7)
- [x] 宏观数据下载完成（Cboe VIX、AkShare SPY、Nasdaq sector map）
- [x] 5 个 observed 宏观特征实现
- [x] 20 日 horizon 标签生成
- [x] B01/B04/B05 四折 baseline 完成
- [x] Phase 1 验收完成（未通过，触发 STOP）

### Phase 2 (Day 8-21)
- [ ] 至少5个正交专家实现
- [ ] 专家相关性 < 0.5
- [ ] 多专家回测完成
- [ ] Phase 2 验收通过

### Phase 3 (Day 22-35)
- [ ] 跨资产特征实现
- [ ] 3种模型训练完成
- [ ] 统计检验通过
- [ ] Phase 3 验收通过

### Phase 4 (Day 36-42)
- [ ] 超参数调优完成
- [ ] 集成策略确定
- [ ] 风险控制实现
- [ ] Validation报告生成

### Phase 5 (Day 43-49)
- [ ] 配置冻结
- [ ] Test单次揭盲完成
- [ ] Admission gate全部检查
- [ ] 上线决策明确

### Phase 6 (Day 50+)
- [ ] 影子模式2周无问题
- [ ] 灰度上线完成
- [ ] 监控面板建立
- [ ] 告警规则生效

---

## 资源需求

### 人力
- **Phase 0-1**: 0.5周 研究员
- **Phase 2**: 1.5周 研究员 + 0.5周 数据工程师(如需基本面数据)
- **Phase 3**: 1.5周 研究员
- **Phase 4-5**: 1周 研究员
- **Phase 6**: 0.5周 研究员 + 0.5周 SRE(部署监控)

**总计**: ~6周 研究员 + 1周 支持

### 计算
- Phase 0-2: CPU only, ~5-7天
- Phase 3: CPU only (LightGBM), ~3-5天
- Phase 4-5: CPU only, ~2天
- **无GPU需求**

### 存储
- 原始数据: ~200MB (宏观数据)
- 标签: ~500MB (20日horizon)
- 模型checkpoints: ~50MB
- Artifacts: ~300MB
- **总计: ~1GB**

### 外部数据
- **免费来源**:
  - VIX: Cboe 官方日线历史 CSV
  - SPY: AkShare `stock_us_daily`
  - 行业分类: Nasdaq stock screener

- **半免费来源** (如果Phase 2需要):
  - 基本面: Alpha Vantage (免费tier 500 calls/day)
  - 新闻情绪: News API (免费tier 100 calls/day)

---

## 风险与退出机制

### 每个Phase的退出条件

| Phase | 失败信号 | 退出决策 | 损失 |
|-------|---------|----------|------|
| P0 | Adaptive router已足够好 | STOP，无需重构 | 2天 |
| P1 | 20日+宏观均无改善 | STOP，问题更深层 | 1周 |
| P2 | 专家仍高度相关 | 回到诊断，可能需要外部数据 | 2周 |
| P3 | 预测模型无效 | STOP，或尝试regime-switching | 4周 |
| P5 | Test admission fail | 不上线，保留adaptive_router | 7周 |
| P6 | 影子模式异常 | 取消上线 | 8周 |

**最坏情况**: 8周投入后不上线，但学到：
1. 当前专家池的真实天花板
2. 宏观维度的增量价值
3. 20日horizon的稳定性

**最好情况**: 7周后上线，Sharpe从0.5提升到1.0+

---

## 总结

这个计划与 Transformer State v3 的核心区别：

| 维度 | Transformer State v3 | 本计划 |
|------|---------------------|--------|
| **问题假设** | 状态相似 → 专家相似 (❌已证伪) | 状态+宏观 → 预测专家 (✅合理) |
| **专家设计** | 8个同质化技术策略 | 6个正交信息源专家 |
| **特征空间** | 28维纯技术指标 | 40+维 (技术+宏观+跨资产) |
| **Horizon** | 5日 (信噪比0.19) | 20日 (更稳定) |
| **方法论** | 深度学习检索 | 监督学习预测 |
| **Early Stop** | ✅ Phase 1-2 | ✅ 每个Phase |
| **成本** | GPU 5-7天 | CPU only |
| **风险** | 高 (深度学习黑盒) | 低 (可解释的树模型) |

**执行建议**:
1. 严格按Phase顺序，不跳过验收
2. Phase 1-2用最简单方法验证核心假设
3. Phase 3再引入模型复杂度
4. 每个Phase设clear exit条件，避免沉没成本

当前路线图已在 Phase 1 触发 STOP；不得默认继续 Phase 2。
