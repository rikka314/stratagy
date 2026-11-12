# 因子-专家-Adaptive 集成优化计划

> **创建日期**: 2026-08-21
> **背景**: Phase 1 宏观特征验证失败后的务实路径
> **核心思路**: 因子优化 → 专家重构 → Adaptive 改进（三阶段串联）

---

## 执行摘要

### Phase 1 实际结果（已完成）

**已实现**：
- ✅ 5 维宏观特征（VIX, rel_strength_spy, market_breadth, beta_20d, sector_momentum）
- ✅ 20 日 horizon 标签生成
- ✅ 四折交叉验证框架
- ✅ 60 只 US 股票 + 8 个真实专家

**验证结果**：
- ❌ B04 (20日) vs B01 (5日): per-day utility +0.001293，低于 +0.002 门槛
- ❌ B05 (20日+宏观) vs B04: utility +0.000023，低于 +0.003 门槛
- ✅ Match rate 提升 10.92 pp（但单独通过不算）

**诊断结论**：
1. **20日 horizon 帮助不大**：可能是因为专家本身在 5 日和 20 日都不稳定
2. **宏观特征无增量**：5 维宏观在当前检索框架下没有价值
3. **根本问题未解决**：专家同质化 + 因子冗余

---

## 新计划架构

```
Phase 0: 已完成 ✅
  - 宏观数据下载
  - 宏观特征实现
  - 20日horizon验证
  结论: 在检索框架下无效，但可用于后续

Phase 2: 因子分层筛选（Week 1-2）← 从这里开始
  - 不是检索，而是直接回测
  - 测试哪些因子真正有效
  - 目标: 从 10 个因子筛选出 5-7 个

Phase 3: 专家池重构（Week 3-4）
  - 基于 Phase 2 筛选的因子
  - 构建正交专家（不同信息源）
  - 目标: 4-6 个低相关专家

Phase 4: Adaptive Router v2（Week 5-6）
  - 基于新专家池
  - 不是检索，而是监督学习预测
  - 目标: 提升专家选择准确率

Phase 5: Validation & Test（Week 7-8）
  - 完整验证
  - 一次揭盲
  - 上线决策
```

---

## Phase 2: 因子分层筛选（Week 1-2）

### 2.1 核心思路

**不做**: ❌ 用因子去检索历史状态（Phase 1 已证明无效）

**要做**: ✅ 直接测试每个因子的回测表现

```python
# Phase 1 的问题
state_embedding = PCA(features)  # 降维
similar_states = search(state_embedding)  # 检索
expert = similar_states[0].expert  # 复用
# → 即使特征好，检索框架也可能失效

# Phase 2 的方法
for factor in all_factors:
    strategy = build_strategy(factor)  # 直接用因子构建策略
    result = backtest(strategy)  # 回测
    report(factor, sharpe, win_rate)  # 看哪个因子真正有效
```

### 2.2 因子分层

**基于金融学原理，将现有因子分为 4 层**：

```python
# 第一层: 趋势动量（3个）
layer_1_trend = {
    "mom_short": "短期动量 (5-10日)",
    "mom_long": "长期动量 (20-60日)",
    "macd": "MACD (趋势强度)",
}

# 第二层: 均值回归（3个）
layer_2_reversion = {
    "rsi": "RSI (超买超卖)",
    "bb_position": "布林带位置",
    "price_position": "价格通道位置",
}

# 第三层: 风险与成交量（4个）
layer_3_risk_volume = {
    "vol": "波动率",
    "drawdown": "回撤",
    "obv": "成交量趋势",
    "volume_ratio": "成交量比率",
}

# 第四层: 宏观与相对（5个）← Phase 1 已实现
layer_4_macro = {
    "vix_level": "VIX 水平",
    "rel_strength_spy": "相对 SPY 强度",
    "market_breadth": "市场广度",
    "beta_20d": "20日 beta",
    "sector_momentum": "行业动量",
}
```

**总计**: 15 个候选因子（10 个原有 + 5 个宏观）

### 2.3 单因子测试

**目标**: 确定每一层中最有效的因子

**实验设计**:

```python
# 对每个因子，构建单因子策略
for layer_id, factors in enumerate([layer_1, layer_2, layer_3, layer_4]):
    for factor_name in factors:
        # 策略: 只用这一个因子
        def strategy(df):
            score = df[factor_name + "_z"]  # 标准化
            return map_score_to_position(score)
        
        # 回测
        result = backtest_on_60_stocks(strategy)
        
        # 记录
        results[layer_id][factor_name] = {
            "median_sharpe": result.median_sharpe,
            "median_win_rate": result.median_win_rate,
            "median_max_dd": result.median_max_dd,
            "success_rate": result.success_rate,  # 多少只股票 Sharpe > 0
        }
```

**验收标准**:

每层至少保留 1 个因子，最多保留 2 个：

```python
# 每层选 top-1 或 top-2
for layer_id, layer_results in results.items():
    sorted_factors = sorted(
        layer_results.items(),
        key=lambda x: x[1]["median_sharpe"],
        reverse=True
    )
    
    # 如果 top-1 Sharpe > 0.3，且 top-2 与 top-1 相关性 < 0.7，保留 2 个
    # 否则只保留 top-1
    
    if sorted_factors[0][1]["median_sharpe"] > 0.3:
        if len(sorted_factors) > 1:
            corr = compute_correlation(sorted_factors[0], sorted_factors[1])
            if corr < 0.7:
                selected[layer_id] = [sorted_factors[0], sorted_factors[1]]
            else:
                selected[layer_id] = [sorted_factors[0]]
        else:
            selected[layer_id] = [sorted_factors[0]]
    else:
        # Sharpe 太低，这一层可能整体无效
        selected[layer_id] = []
```

**预期结果**:

```python
# 示例（实际需要跑实验）
selected_factors = {
    "layer_1": ["mom_long"],  # 长期动量最好
    "layer_2": ["rsi"],  # RSI 最稳定
    "layer_3": [],  # 风险/成交量层可能整体无效
    "layer_4": ["vix_level", "rel_strength_spy"],  # 宏观中这两个可能有效
}

# 总计: 4 个因子
```

### 2.4 因子组合测试

**目标**: 测试层间因子的组合效果

**实验设计**:

```python
# 从每层选出的因子，测试组合
selected_flat = flatten(selected_factors)  # ["mom_long", "rsi", "vix_level", "rel_strength_spy"]

# 测试等权组合
def combined_strategy(df):
    score = 0
    for factor in selected_flat:
        score += df[factor + "_z"]
    score /= len(selected_flat)
    return map_score_to_position(score)

result_combined = backtest_on_60_stocks(combined_strategy)

# 对比单因子
print(f"最优单因子 Sharpe: {best_single_factor_sharpe}")
print(f"组合因子 Sharpe: {result_combined.median_sharpe}")

# 验收: 组合 Sharpe 应该 > 最优单因子 * 1.1
assert result_combined.median_sharpe > best_single_factor_sharpe * 1.1
```

### 2.5 Phase 2 交付

**输出**:

1. **因子筛选报告**: `document/phase2_factor_selection_report.md`
   ```markdown
   ## 单因子测试结果
   
   | Layer | Factor | Median Sharpe | Win Rate | Success Rate |
   |-------|--------|---------------|----------|--------------|
   | 1 | mom_long | 0.45 | 54% | 65% |
   | 1 | mom_short | 0.32 | 52% | 58% |
   | 2 | rsi | 0.38 | 53% | 62% |
   | ...
   
   ## 筛选结果
   
   最终保留 4 个因子: mom_long, rsi, vix_level, rel_strength_spy
   
   组合 Sharpe: 0.52 (vs 最优单因子 0.45)
   ```

2. **筛选脚本**: `model-test/run_factor_selection_phase2.py`

3. **因子权重**: `model-test/configs/selected_factors_phase2.json`
   ```json
   {
     "selected_factors": [
       {"name": "mom_long", "weight": 1.0, "layer": "trend"},
       {"name": "rsi", "weight": 1.0, "layer": "reversion"},
       {"name": "vix_level", "weight": 1.0, "layer": "macro"},
       {"name": "rel_strength_spy", "weight": 1.0, "layer": "macro"}
     ],
     "total_factors": 4,
     "baseline_sharpe_single_best": 0.45,
     "baseline_sharpe_combined": 0.52
   }
   ```

**验收标准**:

- [ ] 至少保留 3 个因子
- [ ] 至少 2 个层有因子入选
- [ ] 组合 Sharpe > 最优单因子 * 1.1
- [ ] 层间因子相关性 < 0.7

**决策**:
- 通过 → 进入 Phase 3
- 未通过 → 可能当前 10 因子都无效，需要引入新因子（基本面、情绪）

---

## Phase 3: 专家池重构（Week 3-4）

### 3.1 核心思路

**Phase 1 的问题**: 8 个专家都基于相同的 10 因子，只是权重不同

**Phase 3 的方案**: 每个专家只用**不同层的因子子集**

```python
# 旧专家池（同质化）
sm_bayesian  = optimize_weights(10_factors, method="bayesian")
sm_genetic   = optimize_weights(10_factors, method="genetic")
sm_random    = optimize_weights(10_factors, method="random")
# → 都是线性加权 10 因子

# 新专家池（正交化）
expert_trend      = only_use(layer_1_factors)  # 只用趋势
expert_reversion  = only_use(layer_2_factors)  # 只用均值回归
expert_macro      = only_use(layer_4_factors)  # 只用宏观
expert_composite  = use(selected_all_factors)  # 用筛选后的全部
```

### 3.2 新专家定义

**基于 Phase 2 筛选结果**，假设最终选了 4 个因子：

```python
# Phase 2 筛选结果（示例）
selected_factors = {
    "mom_long": "trend",
    "rsi": "reversion",
    "vix_level": "macro",
    "rel_strength_spy": "macro",
}

# 新专家池
new_expert_pool = {
    # 1. 纯趋势专家
    "trend_momentum": {
        "factors": ["mom_long"],
        "weights": {"mom_long": 1.0},
        "logic": "只用长期动量",
        "适用": "trending market",
    },
    
    # 2. 纯均值回归专家
    "mean_reversion": {
        "factors": ["rsi"],
        "weights": {"rsi": 1.0},
        "logic": "只用 RSI 超买超卖",
        "适用": "ranging market",
    },
    
    # 3. 纯宏观防御专家
    "macro_defensive": {
        "factors": ["vix_level", "rel_strength_spy"],
        "weights": {
            "vix_level": -0.6,  # VIX 高时降仓
            "rel_strength_spy": 0.4,  # 弱势股回避
        },
        "logic": "VIX 高或相对弱时防守",
        "适用": "high uncertainty",
    },
    
    # 4. 全因子复合专家
    "composite_optimized": {
        "factors": ["mom_long", "rsi", "vix_level", "rel_strength_spy"],
        "weights": {
            # 通过 Bayesian Optimization 调优
            "mom_long": 1.2,
            "rsi": 0.8,
            "vix_level": -0.5,
            "rel_strength_spy": 0.6,
        },
        "logic": "集成所有筛选因子",
        "适用": "all market",
    },
    
    # 5-6. Baseline（保留对比）
    "naive": {...},
    "cash": {...},
}
```

**专家数量**: 4 个新专家 + 2 个 baseline = 6 个

### 3.3 专家实现

**文件**: `core/expert_pool_v2.py`

```python
"""Phase 3 重构的专家池"""

import pandas as pd
import numpy as np
from typing import Dict

class ExpertPoolV2:
    """基于分层因子的正交专家池"""
    
    def __init__(self, selected_factors: Dict[str, str]):
        """
        参数:
            selected_factors: {"factor_name": "layer", ...}
            例如: {"mom_long": "trend", "rsi": "reversion", ...}
        """
        self.selected_factors = selected_factors
        self.factor_by_layer = self._group_by_layer(selected_factors)
    
    def _group_by_layer(self, factors: Dict[str, str]) -> Dict[str, list]:
        """按层分组因子"""
        grouped = {}
        for factor, layer in factors.items():
            if layer not in grouped:
                grouped[layer] = []
            grouped[layer].append(factor)
        return grouped
    
    def compute_trend_expert(self, df: pd.DataFrame) -> pd.Series:
        """纯趋势专家：只用 layer_1 因子"""
        if "trend" not in self.factor_by_layer:
            return pd.Series(0.0, index=df.index)
        
        factors = self.factor_by_layer["trend"]
        score = 0.0
        for f in factors:
            score += df[f + "_z"]
        
        return score / len(factors)
    
    def compute_reversion_expert(self, df: pd.DataFrame) -> pd.Series:
        """纯均值回归专家：只用 layer_2 因子"""
        if "reversion" not in self.factor_by_layer:
            return pd.Series(0.0, index=df.index)
        
        factors = self.factor_by_layer["reversion"]
        score = 0.0
        for f in factors:
            score += df[f + "_z"]
        
        return score / len(factors)
    
    def compute_macro_expert(self, df: pd.DataFrame) -> pd.Series:
        """纯宏观防御专家：只用 layer_4 因子"""
        if "macro" not in self.factor_by_layer:
            return pd.Series(0.0, index=df.index)
        
        # VIX 高时降仓（负权重）
        vix_signal = -df["vix_level_z"] if "vix_level" in df.columns else 0
        
        # 相对强度弱时回避（正权重）
        rel_signal = df["rel_strength_spy_z"] if "rel_strength_spy" in df.columns else 0
        
        return 0.6 * vix_signal + 0.4 * rel_signal
    
    def compute_composite_expert(self, df: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        """全因子复合专家：用所有筛选因子"""
        score = 0.0
        for factor, weight in weights.items():
            if factor + "_z" in df.columns:
                score += weight * df[factor + "_z"]
        
        return score
    
    def get_all_expert_signals(self, df: pd.DataFrame, composite_weights: Dict[str, float]) -> Dict[str, pd.Series]:
        """获取所有专家的信号"""
        return {
            "trend_momentum": self.compute_trend_expert(df),
            "mean_reversion": self.compute_reversion_expert(df),
            "macro_defensive": self.compute_macro_expert(df),
            "composite_optimized": self.compute_composite_expert(df, composite_weights),
        }
```

### 3.4 专家相关性验证

**目标**: 确认新专家池的正交性

```python
# 脚本: model-test/validate_expert_orthogonality_phase3.py

import pandas as pd
import numpy as np
from core.expert_pool_v2 import ExpertPoolV2

def validate_orthogonality():
    """验证专家正交性"""
    
    # 回测所有专家，获取 daily returns
    expert_returns = {}
    
    for expert_name in ["trend_momentum", "mean_reversion", "macro_defensive", "composite_optimized"]:
        result = backtest_expert_on_60_stocks(expert_name)
        expert_returns[expert_name] = result.aggregated_daily_returns
    
    # 相关性矩阵
    df_returns = pd.DataFrame(expert_returns)
    corr_matrix = df_returns.corr(method='spearman')
    
    print("=== Expert Correlation Matrix ===")
    print(corr_matrix)
    
    # 平均成对相关性
    upper_triangle = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
    )
    avg_corr = upper_triangle.stack().mean()
    
    print(f"\n平均成对相关性: {avg_corr:.3f}")
    
    # 验收
    assert avg_corr < 0.5, f"专家相关性过高: {avg_corr:.3f}"
    
    return corr_matrix
```

### 3.5 Phase 3 交付

**输出**:

1. **专家池模块**: `core/expert_pool_v2.py`
2. **专家配置**: `model-test/configs/expert_pool_v2.json`
3. **相关性报告**: `document/phase3_expert_orthogonality_report.md`
4. **回测报告**: `document/phase3_expert_backtest_report.md`

**验收标准**:

- [ ] 专家平均相关性 < 0.5
- [ ] 至少 3 个专家 Sharpe > 0.3
- [ ] 不同专家在不同 fold 表现最优（分散性）
- [ ] Composite expert Sharpe > Phase 2 组合因子 Sharpe

**决策**:
- 通过 → 进入 Phase 4
- 未通过 → 调整专家定义，或增加专家数量

---

## Phase 4: Adaptive Router v2（Week 5-6）

### 4.1 核心思路

**Phase 1 的问题**: 用 PCA 检索历史状态，复用当时的专家

**Phase 4 的方案**: 直接用监督学习预测每个专家的未来表现

```python
# Phase 1（失败）
state_embedding = PCA(features)
similar_states = search(state_embedding)
best_expert = similar_states[0].expert  # 复用历史

# Phase 4（新方案）
X = current_state_features  # 33 维（28 + 5 宏观）
Y_pred = model.predict(X)   # 预测 4 个专家的未来 sharpe
best_expert = argmax(Y_pred)  # 选择预测最好的
```

**金融学依据**:

这不是"状态相似 → 专家相似"，而是"当前特征 → 专家表现"的监督学习。

类比: 不是找"天气相似的历史日期穿什么"，而是学习"在当前天气+季节+场合下，哪种穿衣风格更舒服"。

### 4.2 训练数据构建

**特征 X**: 33 维

```python
X_features = [
    # 28 维原有 state features（Phase 1 已冻结）
    ...
    
    # 5 维宏观特征（Phase 1 已实现）
    "vix_level",
    "rel_strength_spy",
    "market_breadth",
    "beta_20d",
    "sector_momentum",
]
```

**标签 Y**: 每个专家的未来 Sharpe

```python
# 对每个 date-symbol 决策点
for date, symbol in decision_points:
    # 特征
    X[i] = state_features[date, symbol]
    
    # 标签: 每个专家在未来 20 日的 Sharpe
    Y[i] = {
        "trend_momentum": future_20d_sharpe(expert="trend_momentum", date=date, symbol=symbol),
        "mean_reversion": future_20d_sharpe(expert="mean_reversion", date=date, symbol=symbol),
        "macro_defensive": future_20d_sharpe(expert="macro_defensive", date=date, symbol=symbol),
        "composite_optimized": future_20d_sharpe(expert="composite_optimized", date=date, symbol=symbol),
    }
```

### 4.3 模型选择

**三种模型对比**:

| 模型 | 类型 | 优势 | 劣势 |
|------|------|------|------|
| **LightGBM** | 多输出回归 | 快速、可解释、特征重要性 | 需要调参 |
| **Random Forest** | 集成学习 | 稳定、少调参 | 慢 |
| **Linear Ridge** | 线性模型 | 最简单、baseline | 表达能力弱 |

**推荐**: 先用 **LightGBM**

```python
from lightgbm import LGBMRegressor

# 多输出回归
model = LGBMRegressor(
    objective="regression",
    n_estimators=100,
    max_depth=5,
    learning_rate=0.05,
    random_state=42,
)

# 训练
model.fit(X_train, Y_train)  # Y_train shape: (N, 4)

# 预测
Y_pred = model.predict(X_test)  # shape: (M, 4)

# 选择最优专家
best_experts = np.argmax(Y_pred, axis=1)
```

### 4.4 评估指标

**核心指标**:

```python
metrics = {
    # 1. 专家选择准确率
    "match_rate": sum(selected == oracle) / len(selected),
    
    # 2. Top-3 捕获率
    "top3_capture_rate": sum(oracle in top3[i] for i in range(len(selected))),
    
    # 3. Query utility（实际获得的收益）
    "query_utility_mean": mean(selected_expert_returns),
    
    # 4. Regret（与 oracle 的差距）
    "regret": oracle_utility - query_utility,
    
    # 5. Sharpe Ratio（策略层面）
    "sharpe_ratio": mean(returns) / std(returns) * sqrt(252),
}
```

### 4.5 Phase 4 交付

**输出**:

1. **Adaptive Router v2 模块**: `core/adaptive_router_v2.py`
2. **训练脚本**: `model-test/train_adaptive_router_v2.py`
3. **配置文件**: `model-test/configs/adaptive_router_v2.json`
4. **Validation 报告**: `document/phase4_adaptive_v2_validation_report.md`

**验收标准**:

与 Phase 3 的 `composite_optimized` 专家（固定用全部因子）对比：

- [ ] Match rate > composite + 10%
- [ ] Query utility > composite + 0.005
- [ ] Sharpe > composite * 1.2
- [ ] 4 个 fold 中至少 3 个表现更优

**决策**:
- 通过 → 进入 Phase 5（Test 揭盲）
- 未通过 → 可能新专家池本身就不够好，回到 Phase 3 调整

---

## Phase 5: Validation & Test（Week 7-8）

### 5.1 Validation 完整测试

**已在 Phase 4 完成**，这里做最终确认：

```bash
python model-test/run_adaptive_v2_final_validation.py \
    --market US \
    --symbols <60 stocks> \
    --folds wf_01,wf_02,wf_03,wf_04 \
    --output model-test/outputs/adaptive_v2_final_validation/
```

### 5.2 Test 一次揭盲

**冻结配置**:

```yaml
# config/adaptive_router_v2_frozen.yaml

factors:
  selected: ["mom_long", "rsi", "vix_level", "rel_strength_spy"]
  total: 4

experts:
  pool: ["trend_momentum", "mean_reversion", "macro_defensive", "composite_optimized"]
  count: 4

model:
  type: lgbm
  params:
    n_estimators: 100
    max_depth: 5
    learning_rate: 0.05

horizon: 20 days
```

**执行**:

```bash
# 单次揭盲，不回头
python model-test/run_adaptive_v2_test_揭盲.py \
    --config config/adaptive_router_v2_frozen.yaml \
    --test_window 2025-07-01_to_2025-12-31 \
    --output model-test/outputs/adaptive_v2_test_final/
```

### 5.3 Admission Gate

| Gate | 标准 | 通过条件 |
|------|------|----------|
| **G1: Utility** | Test utility > Val utility * 0.8 | 必须 |
| **G2: Sharpe** | Test Sharpe > 0.8 | 必须 |
| **G3: Drawdown** | Test Max DD < 12% | 必须 |
| **G4: Consistency** | Test vs Val 相关 > 0.7 | 必须 |

**决策**:
- 全部通过 → PASS，准入生产
- 3 项通过 → CONDITIONAL PASS，监控上线
- ≤2 项通过 → FAIL，不上线

### 5.4 灰度上线

**如果 PASS**:

```
Week 9:  影子模式（100% adaptive_router_v1, 0% adaptive_router_v2）
Week 10: 10% adaptive_router_v2
Week 11: 50% adaptive_router_v2
Week 12: 100% adaptive_router_v2
```

---

## 关键差异总结

### 与 Phase 1 的差异

| 维度 | Phase 1（已 FAIL） | Phase 2-5（新计划） |
|------|------------------|-------------------|
| **问题框架** | 检索历史状态 | 直接回测 + 监督学习 |
| **因子使用** | 加入宏观，但仍用于检索 | 先筛选有效因子，再构建专家 |
| **专家设计** | 保持原有 8 个专家不变 | 重构为 4 个正交专家 |
| **Adaptive** | 用 PCA 检索 | 用 LightGBM 预测 |
| **验证方式** | Neighbor consistency + Query utility | 直接回测 Sharpe + Match rate |

### 为什么 Phase 2-5 可能成功？

1. **Phase 2 直接测试因子有效性**
   - 不再假设"相似状态"，而是直接看回测
   - 单因子测试 → 筛选掉无效因子
   - Phase 1 失败可能因为 5 个宏观因子本身就不行

2. **Phase 3 构建正交专家**
   - 每个专家用不同层的因子
   - 不再是同一模型的超参数变体
   - 解决同质化问题

3. **Phase 4 用监督学习而非检索**
   - 不依赖"状态相似 → 专家相似"假设
   - 直接学习"特征 → 专家表现"映射
   - LightGBM 可解释，可看特征重要性

---

## 执行建议

### 立即开始（Week 1）

```bash
# Step 1: 创建 Phase 2 实验脚本
cat > model-test/run_factor_selection_phase2.py << 'EOF'
# （我可以帮你写完整代码）
EOF

# Step 2: 运行单因子测试（快速验证，10 只股票）
python model-test/run_factor_selection_phase2.py \
    --market US \
    --symbols AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,V,JNJ \
    --quick \
    --output model-test/outputs/phase2_factor_selection_quick/

# Step 3: 查看结果，决定是否继续
cat model-test/outputs/phase2_factor_selection_quick/summary.txt
```

### Week 1 结束时

你会知道：
- ✅ 哪些因子真正有效
- ✅ 是否值得继续 Phase 3-4
- ✅ 预期改进空间有多大

如果 Week 1 失败 → 损失 1 周，但证明当前因子体系确实无效  
如果 Week 1 成功 → 继续 Phase 3-5，总计 7-8 周

---

**你确认这个计划吗？** 如果确认，我立即帮你创建：

1. `model-test/run_factor_selection_phase2.py`（Phase 2 单因子测试脚本）
2. Phase 2 配置文件
3. Phase 2 快速启动指南

还是你想先看看 Phase 0 的 adaptive_router 审计结果？
