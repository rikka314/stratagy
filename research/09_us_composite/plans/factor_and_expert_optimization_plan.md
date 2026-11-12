# 因子系统与专家体系优化计划

> **创建日期**: 2026-08-21
> **背景**: Transformer State v3 Phase 2 诊断发现当前因子和专家存在根本性问题
> **核心目标**: 优化 10 因子体系和专家池设计，而非构建新的 meta-learner

---

## 问题诊断总结

### 当前系统架构

```python
# 现有 10 因子
factors = [
    "mom_short",      # 短期动量
    "mom_long",       # 长期动量
    "macd",           # MACD
    "rsi",            # RSI
    "vol",            # 波动率
    "bb",             # 布林带位置
    "obv",            # 成交量趋势
    "volume",         # 成交量比率
    "price",          # 价格位置
    "drawdown",       # 回撤
]

# 现有专家池 (约 10-11 个)
experts = [
    # Baseline
    "naive", "mean", "drift",
    
    # SM 系列（单一模型，不同优化器）
    "sm",                    # 默认权重
    "sm_bayesian",           # 贝叶斯优化权重
    "sm_random",             # 随机搜索权重
    "sm_genetic",            # 遗传算法优化权重
    
    # FSM 系列（FA 降维 + SM）
    "fsm",                   # 默认 FA + SM
    "fsm_bayesian",          # FA + 贝叶斯优化
    "fsm_random",            # FA + 随机搜索
    "fsm_genetic",           # FA + 遗传算法
    
    # ML 增强
    "ml_lgbm",               # LightGBM 过滤 SM
    
    # Meta
    "adaptive_router_v1",    # 自适应路由
]
```

### 三个根本问题

#### 问题 1: 因子同质化

**现状**: 10 个因子中有 8 个是技术指标，且高度相关

```python
# 动量类 (3个)
mom_short, mom_long, macd  # 都在捕捉趋势

# 超买超卖类 (2个)
rsi, bb_position  # 都在测量价格极值

# 成交量类 (2个)
obv, volume_ratio  # 都在看量能

# 风险类 (2个)
vol, drawdown  # 都在测量波动/风险

# 相对位置 (1个)
price_position  # 在通道内的位置
```

**问题**: 这些因子携带的**独立信息**很少，大部分是同一信息的不同表达。

#### 问题 2: 专家同质化

**现状**: SM/FSM 系列本质是**同一个线性模型**的超参数变体

```python
# 所有 SM 专家都是这个公式
factor_score = w1*mom_short + w2*mom_long + ... + w10*drawdown
target_position = map_score_to_position(factor_score)

# 区别仅在于权重 w1...w10 的优化方法
sm_bayesian:  w = bayesian_optimize(w)
sm_genetic:   w = genetic_algorithm(w)
sm_random:    w = random_search(w)

# FSM 只是在 SM 前面加了一个 FA 降维
fsm = FA(10 factors -> 3~5 factors) + SM
```

**问题**: 8 个专家(sm/fsm 各 4 个)都基于**相同的 10 因子**，只是权重不同，信息源高度重叠。

#### 问题 3: 缺少宏观和相对维度

**现状**: 所有因子都是**个股自身的技术指标**

```python
# 现有因子只看个股
for factor in factors:
    factor_value = compute_from_single_stock_ohlcv(df)

# 缺失维度
market_regime = ?          # 市场整体环境 (VIX, 市场广度)
relative_strength = ?      # 相对 SPY 的强弱
sector_rotation = ?        # 行业轮动
cross_asset_signal = ?     # 美债、商品、汇率
```

**问题**: 技术指标在**不同宏观环境**下有效性完全不同，但当前系统无法区分。

---

## 优化方案

### 方案架构

```
┌─────────────────────────────────────────────────────┐
│  Phase 1: 因子分层与筛选                              │
│  - 按金融学原理将 10 因子分为 3 层                    │
│  - 每层独立测试，筛选出最有效的因子                   │
│  - 加入宏观和相对强度因子                             │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 2: 因子权重优化                                │
│  - Grid Search: 穷举重要因子组合                      │
│  - Bayesian Optimization: 精细调优                    │
│  - Feature Selection: 自动筛选冗余因子                │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 3: 专家池重构                                  │
│  - 不再是同一模型的超参数变体                         │
│  - 每个专家基于不同的信息源                           │
│  - 构建正交的专家集合                                 │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Phase 4: 验证与上线                                  │
│  - Validation 集测试                                  │
│  - Test 集一次揭盲                                    │
│  - 灰度上线                                           │
└─────────────────────────────────────────────────────┘
```

---

## Phase 1: 因子分层与筛选（Week 1-2）

### 1.1 因子分层

**按金融学原理分为三层**：

```python
# 第一层: 趋势动量 (Trend & Momentum)
layer_1 = {
    "mom_short_z",    # 短期动量 (5-10日)
    "mom_long_z",     # 长期动量 (20-60日)
    "macd_z",         # MACD (趋势强度)
}

# 第二层: 均值回归 (Mean Reversion)
layer_2 = {
    "rsi_z",              # RSI (超买超卖)
    "bb_position_rank",   # 布林带位置
    "price_position_rank", # 价格通道位置
}

# 第三层: 风险与成交量 (Risk & Volume)
layer_3 = {
    "vol_z",              # 波动率
    "drawdown_rank",      # 回撤
    "obv_trend_rank",     # 成交量趋势
    "volume_ratio_rank",  # 成交量比率
}

# 新增第四层: 宏观与相对 (Macro & Relative) ← 重点！
layer_4 = {
    "vix_level",          # VIX 水平
    "vix_regime",         # VIX regime (低/中/高)
    "rel_strength_spy",   # 相对 SPY 强度 (20日)
    "market_breadth",     # 市场广度 (上涨股票占比)
    "beta_20d",           # 20 日 beta
    "sector_momentum",    # 行业相对动量
}
```

### 1.2 分层筛选实验

**目标**: 确定每层最有效的因子

**实验设计**:

```python
# 实验 E1: 第一层单因子测试
for factor in layer_1:
    score = factor  # 单因子策略
    result = backtest(score)
    report(factor, sharpe, win_rate, max_dd)

# 实验 E2: 第一层双因子测试
for (f1, f2) in combinations(layer_1, 2):
    score = f1 + f2  # 等权
    result = backtest(score)
    report((f1, f2), sharpe, ...)

# 实验 E3: 第一层最优组合
best_layer_1 = select_best_from_E1_E2()

# 重复 E1-E3 对 layer_2, layer_3, layer_4
```

**验收标准**:

```python
# 每层至少保留 1 个因子
assert len(selected_layer_1) >= 1
assert len(selected_layer_2) >= 1
assert len(selected_layer_3) >= 1
assert len(selected_layer_4) >= 1  # 新增宏观层

# 总因子数控制在 6-10 个
assert 6 <= total_factors <= 10

# 层间相关性 < 0.5
for (layer_i, layer_j) in combinations(layers, 2):
    assert correlation(layer_i, layer_j) < 0.5
```

### 1.3 宏观因子实现

**新增模块**: `core/macro_factors.py`

```python
"""宏观与相对强度因子"""

import pandas as pd
import numpy as np
from pathlib import Path

class MacroFactors:
    """宏观因子计算器"""
    
    def __init__(self):
        self.vix_data = self._load_vix()
        self.spy_data = self._load_spy()
        self.sector_map = self._load_sector_map()
    
    def compute(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        在个股 OHLCV 上扩展宏观因子
        
        输入:
            df: 标准行情 DataFrame (date, open, high, low, close, volume)
            symbol: 股票代码
        
        输出:
            添加以下列的 df:
            - vix_level: VIX 水平
            - vix_regime: VIX regime (0=low <15, 1=med 15-25, 2=high >25)
            - rel_strength_spy: 20日相对 SPY 收益率
            - market_breadth: 市场广度 (上涨股票占比，如果有数据)
            - beta_20d: 20日 beta
            - sector_momentum: 行业20日动量
        """
        df = df.copy()
        
        # 1. VIX
        df = df.merge(
            self.vix_data[['date', 'close']].rename(columns={'close': 'vix_level'}),
            on='date',
            how='left'
        )
        df['vix_level'] = df['vix_level'].fillna(method='ffill')
        df['vix_regime'] = pd.cut(
            df['vix_level'],
            bins=[0, 15, 25, 100],
            labels=[0, 1, 2]  # low/med/high
        ).astype(float)
        
        # 2. 相对 SPY 强度
        spy_ret = self.spy_data.set_index('date')['close'].pct_change(20)
        stock_ret = df.set_index('date')['close'].pct_change(20)
        df['rel_strength_spy'] = (stock_ret - spy_ret).values
        
        # 3. Beta
        df['beta_20d'] = self._compute_rolling_beta(
            df['close'], 
            self.spy_data.set_index('date')['close'],
            window=20
        )
        
        # 4. 行业动量
        sector = self._get_sector(symbol)
        df['sector_momentum'] = self._compute_sector_momentum(
            sector, df['date']
        )
        
        # 5. 市场广度 (如果有数据，否则用 SPY 20 日动量代替)
        df['market_breadth'] = self._compute_market_breadth(df['date'])
        
        return df
    
    def _load_vix(self) -> pd.DataFrame:
        """从 data/macro/vix_daily.parquet 加载 VIX"""
        path = Path("data/macro/vix_daily.parquet")
        if not path.exists():
            raise FileNotFoundError(
                f"VIX data not found at {path}. "
                "Run: python data-pipeline/download_macro_data.py"
            )
        return pd.read_parquet(path)
    
    def _load_spy(self) -> pd.DataFrame:
        """从 data/macro/spy_daily.parquet 加载 SPY"""
        path = Path("data/macro/spy_daily.parquet")
        if not path.exists():
            raise FileNotFoundError(
                f"SPY data not found at {path}. "
                "Run: python data-pipeline/download_macro_data.py"
            )
        return pd.read_parquet(path)
    
    def _load_sector_map(self) -> pd.DataFrame:
        """从 data/macro/us_sector_map.csv 加载行业分类"""
        path = Path("data/macro/us_sector_map.csv")
        if not path.exists():
            # 如果没有，返回空映射
            return pd.DataFrame(columns=['symbol', 'sector'])
        return pd.read_csv(path)
    
    def _compute_rolling_beta(self, stock_prices, spy_prices, window=20):
        """计算滚动 beta"""
        stock_ret = stock_prices.pct_change()
        spy_ret = spy_prices.pct_change()
        
        # 滚动协方差 / 滚动方差
        cov = stock_ret.rolling(window).cov(spy_ret)
        var = spy_ret.rolling(window).var()
        
        beta = cov / var
        return beta.fillna(1.0)  # 缺失时用 1.0
    
    def _get_sector(self, symbol: str) -> str:
        """获取股票所属行业"""
        match = self.sector_map[self.sector_map['symbol'] == symbol]
        if len(match) == 0:
            return "Unknown"
        return match.iloc[0]['sector']
    
    def _compute_sector_momentum(self, sector: str, dates: pd.Series) -> pd.Series:
        """计算行业20日动量"""
        # 简化版: 返回 0
        # 完整版: 需要行业指数数据
        return pd.Series(0.0, index=dates.index)
    
    def _compute_market_breadth(self, dates: pd.Series) -> pd.Series:
        """计算市场广度"""
        # 简化版: 用 SPY 20 日收益率代替
        # 完整版: 需要全市场涨跌统计
        spy_ret = self.spy_data.set_index('date')['close'].pct_change(20)
        return dates.map(spy_ret.to_dict()).fillna(0.0)


# 全局实例
_macro_factors_instance = None

def get_macro_factors() -> MacroFactors:
    """获取全局 MacroFactors 实例"""
    global _macro_factors_instance
    if _macro_factors_instance is None:
        _macro_factors_instance = MacroFactors()
    return _macro_factors_instance
```

### 1.4 Phase 1 执行步骤

**Day 1-2**: 下载宏观数据

```bash
# 创建脚本
cat > data-pipeline/download_macro_data.py << 'EOF'
"""下载 VIX 和 SPY 数据"""

import yfinance as yf
import pandas as pd
from pathlib import Path

def download_macro_data():
    # 创建目录
    Path("data/macro").mkdir(parents=True, exist_ok=True)
    
    # 下载 VIX
    print("Downloading VIX...")
    vix = yf.download("^VIX", start="2015-01-01", end="2026-12-31", progress=False)
    vix = vix.reset_index()
    vix.columns = ['date'] + [c.lower() for c in vix.columns[1:]]
    vix.to_parquet("data/macro/vix_daily.parquet", index=False)
    print(f"✓ Saved VIX: {len(vix)} rows")
    
    # 下载 SPY
    print("Downloading SPY...")
    spy = yf.download("SPY", start="2015-01-01", end="2026-12-31", progress=False)
    spy = spy.reset_index()
    spy.columns = ['date'] + [c.lower() for c in spy.columns[1:]]
    spy.to_parquet("data/macro/spy_daily.parquet", index=False)
    print(f"✓ Saved SPY: {len(spy)} rows")
    
    # 生成 manifest
    manifest = {
        "vix_daily.parquet": {
            "rows": len(vix),
            "date_range": [str(vix['date'].min()), str(vix['date'].max())],
        },
        "spy_daily.parquet": {
            "rows": len(spy),
            "date_range": [str(spy['date'].min()), str(spy['date'].max())],
        },
    }
    
    import json
    with open("data/macro/macro_data_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    print("\n✓ Macro data download complete")
    print("  - data/macro/vix_daily.parquet")
    print("  - data/macro/spy_daily.parquet")
    print("  - data/macro/macro_data_manifest.json")

if __name__ == "__main__":
    download_macro_data()
EOF

python data-pipeline/download_macro_data.py
```

**Day 3-5**: 实现 `core/macro_factors.py` (上面已给出)

**Day 6-10**: 运行分层筛选实验

```bash
# 创建实验脚本
python model-test/run_factor_layered_selection.py \
    --market US \
    --symbols AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,V,JNJ \
    --window 2020-01-01_to_2024-12-31 \
    --output model-test/outputs/phase1_factor_selection/
```

**Day 11-14**: 分析结果，确定最终因子集

---

## Phase 2: 因子权重优化（Week 3-4）

### 2.1 优化方法对比

| 方法 | 优势 | 劣势 | 何时用 |
|------|------|------|--------|
| **Grid Search** | 穷举，不遗漏 | 慢，组合爆炸 | 因子数 ≤ 5 |
| **Random Search** | 快，可并行 | 不保证最优 | 快速baseline |
| **Bayesian Optimization** | 样本高效 | 串行，黑盒 | 精细调优 |
| **Genetic Algorithm** | 全局搜索 | 超参数多 | 高维非凸 |
| **Feature Selection** | 自动筛选冗余 | 需要模型 | 因子数 > 10 |

### 2.2 三阶段优化

**Stage 1: Grid Search (粗筛选)**

```python
# 假设 Phase 1 筛选出 6 个因子
selected_factors = [
    "mom_long_z",         # 第一层: 动量
    "rsi_z",              # 第二层: 均值回归
    "vol_z",              # 第三层: 风险
    "vix_regime",         # 第四层: 宏观
    "rel_strength_spy",   # 第四层: 相对
    "beta_20d",           # 第四层: beta
]

# Grid Search: 每个因子 [0, 0.5, 1.0, 1.5, 2.0]
grid = {
    f"weight_{factor}": [0, 0.5, 1.0, 1.5, 2.0]
    for factor in selected_factors
}

# 总组合数: 5^6 = 15,625
# 太多了，需要分层
```

**优化**: 分层 Grid Search

```python
# 先固定第四层(宏观)为等权，优化前三层
layer_1_3_grid = {
    "weight_mom_long": [0, 0.5, 1.0, 1.5, 2.0],
    "weight_rsi": [0, 0.5, 1.0, 1.5, 2.0],
    "weight_vol": [0, 0.5, 1.0, 1.5, 2.0],
}
# 组合数: 5^3 = 125 ✓

best_1_3 = grid_search(layer_1_3_grid)

# 固定前三层，优化第四层
layer_4_grid = {
    "weight_vix_regime": [0, 0.5, 1.0, 1.5, 2.0],
    "weight_rel_strength_spy": [0, 0.5, 1.0, 1.5, 2.0],
    "weight_beta_20d": [0, 0.5, 1.0, 1.5, 2.0],
}
# 组合数: 5^3 = 125 ✓

best_4 = grid_search(layer_4_grid, fixed_weights=best_1_3)

# 最优组合
best_weights = {**best_1_3, **best_4}
```

**Stage 2: Bayesian Optimization (精调)**

```python
# 在 Grid Search 最优解附近精调
from bayes_opt import BayesianOptimization

def objective(weight_mom_long, weight_rsi, weight_vol,
              weight_vix_regime, weight_rel_strength_spy, weight_beta_20d):
    # 回测
    factor_score = (
        weight_mom_long * df["mom_long_z"]
        + weight_rsi * df["rsi_z"]
        + weight_vol * df["vol_z"]
        + weight_vix_regime * df["vix_regime"]
        + weight_rel_strength_spy * df["rel_strength_spy"]
        + weight_beta_20d * df["beta_20d"]
    )
    result = backtest(factor_score)
    return result.sharpe_ratio

# Bayesian 优化
optimizer = BayesianOptimization(
    f=objective,
    pbounds={
        "weight_mom_long": (best_1_3["weight_mom_long"] - 0.5, 
                            best_1_3["weight_mom_long"] + 0.5),
        # ... 同样对其他权重
    },
    random_state=42,
)

optimizer.maximize(n_iter=100)
best_weights_tuned = optimizer.max['params']
```

**Stage 3: Feature Selection (自动筛选)**

```python
# 用 LightGBM 特征重要性筛选
from lightgbm import LGBMRegressor

X = df[selected_factors]
y = df['future_20d_return']  # 20日未来收益

model = LGBMRegressor(n_estimators=100)
model.fit(X, y)

# 特征重要性
importance = pd.Series(model.feature_importances_, index=selected_factors).sort_values(ascending=False)

# 只保留累积重要性 >= 90% 的因子
cumsum = importance.cumsum() / importance.sum()
selected_final = importance[cumsum <= 0.9].index.tolist()

print(f"筛选后因子: {selected_final}")
```

### 2.3 Phase 2 验收

**成功标准**:

```python
# 1. Sharpe 提升 > 20%
assert tuned_sharpe > baseline_sharpe * 1.2

# 2. 因子数减少 (去冗余)
assert len(selected_final) <= len(selected_factors)

# 3. 权重分布合理 (无单一因子主导)
max_weight = max(best_weights_tuned.values())
assert max_weight < 0.4  # 最大权重 < 40%

# 4. Validation 稳定性
assert val_sharpe > train_sharpe * 0.8
```

---

## Phase 3: 专家池重构（Week 5-6）

### 3.1 新专家设计原则

**核心**: 每个专家基于**不同的信息源**，而非同一模型的超参数变体

```python
# ❌ 旧设计 (同质化)
sm_bayesian  = optimize(weights, method="bayesian")
sm_genetic   = optimize(weights, method="genetic")
sm_random    = optimize(weights, method="random")
# 都是线性加权 10 因子，只是权重优化方法不同

# ✅ 新设计 (正交化)
expert_momentum      = only_use(layer_1_factors)  # 纯动量
expert_mean_reversion = only_use(layer_2_factors)  # 纯均值回归
expert_macro_defensive = only_use(layer_4_factors)  # 纯宏观
expert_composite     = use_all_factors()           # 全因子
```

### 3.2 新专家池定义

```python
new_expert_pool = {
    # 1. 纯动量专家
    "momentum": {
        "factors": ["mom_long_z"],
        "logic": "只用长期动量",
        "适用环境": "trending market, VIX < 20",
    },
    
    # 2. 纯均值回归专家
    "mean_reversion": {
        "factors": ["rsi_z", "bb_position_rank"],
        "logic": "只用超买超卖",
        "适用环境": "ranging market, VIX 15-25",
    },
    
    # 3. 纯宏观防御专家
    "macro_defensive": {
        "factors": ["vix_regime", "rel_strength_spy"],
        "logic": "VIX高时降仓，弱势股回避",
        "适用环境": "high uncertainty, VIX > 25",
    },
    
    # 4. 全因子复合专家
    "composite": {
        "factors": selected_final,  # Phase 2 筛选的所有因子
        "weights": best_weights_tuned,  # Phase 2 优化的权重
        "logic": "集成所有维度",
        "适用环境": "all market",
    },
    
    # 5. Baseline (保留)
    "naive": {...},
    "cash": {...},
}
```

### 3.3 专家实现

```python
# 文件: core/expert_pool.py

class ExpertPool:
    """新专家池"""
    
    def __init__(self, factor_weights: dict):
        self.factor_weights = factor_weights
    
    def compute_momentum_expert(self, df: pd.DataFrame) -> pd.Series:
        """纯动量专家"""
        return df["mom_long_z"]
    
    def compute_mean_reversion_expert(self, df: pd.DataFrame) -> pd.Series:
        """纯均值回归专家"""
        return (
            0.5 * df["rsi_z"] 
            + 0.5 * (df["bb_position_rank"] - 0.5) * 2
        )
    
    def compute_macro_defensive_expert(self, df: pd.DataFrame) -> pd.Series:
        """纯宏观防御专家"""
        # VIX > 25 时降仓
        vix_signal = -df["vix_regime"]  # 越高越防守
        
        # 相对强度弱时回避
        rel_signal = df["rel_strength_spy"]
        
        return 0.6 * vix_signal + 0.4 * rel_signal
    
    def compute_composite_expert(self, df: pd.DataFrame) -> pd.Series:
        """全因子复合专家"""
        score = 0.0
        for factor, weight in self.factor_weights.items():
            score += weight * df[factor]
        return score
    
    def get_all_expert_scores(self, df: pd.DataFrame) -> dict:
        """获取所有专家的评分"""
        return {
            "momentum": self.compute_momentum_expert(df),
            "mean_reversion": self.compute_mean_reversion_expert(df),
            "macro_defensive": self.compute_macro_defensive_expert(df),
            "composite": self.compute_composite_expert(df),
        }
```

### 3.4 专家相关性验证

```python
# Day 1: 计算专家相关性
import numpy as np

def validate_expert_orthogonality():
    """验证专家正交性"""
    
    # 回测所有专家
    expert_returns = {}
    for expert_name in ["momentum", "mean_reversion", "macro_defensive", "composite"]:
        result = backtest_expert(expert_name)
        expert_returns[expert_name] = result.daily_returns
    
    # 相关性矩阵
    df_returns = pd.DataFrame(expert_returns)
    corr_matrix = df_returns.corr(method='spearman')
    
    print(corr_matrix)
    
    # 验收
    upper_triangle = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
    )
    avg_corr = upper_triangle.stack().mean()
    
    print(f"\nAverage pairwise correlation: {avg_corr:.3f}")
    
    # 成功标准
    assert avg_corr < 0.5, f"专家相关性过高: {avg_corr:.3f}"
    
    return corr_matrix
```

### 3.5 Phase 3 验收

**成功标准**:

```python
# 1. 专家相关性 < 0.5
assert avg_pairwise_corr < 0.5

# 2. 至少 3 个专家在不同 fold 表现最优
best_experts_per_fold = [...]
assert len(set(best_experts_per_fold)) >= 3

# 3. Oracle utility 提升
# (如果所有专家都有自己的最优区间，完美选择的收益应该更高)
assert oracle_utility_new > oracle_utility_old * 1.2
```

---

## Phase 4: 验证与上线（Week 7-8）

### 4.1 Validation 测试

```bash
# 完整回测
python model-test/run_expert_pool_v2_validation.py \
    --market US \
    --symbols <60 stocks> \
    --windows wf_01,wf_02,wf_03,wf_04 \
    --output model-test/outputs/expert_pool_v2_validation/
```

### 4.2 Test 揭盲

```bash
# 一次性 Test
python model-test/run_expert_pool_v2_test.py \
    --market US \
    --test_window 2025-07-01_to_2025-12-31 \
    --output model-test/outputs/expert_pool_v2_test/
```

### 4.3 Admission Gate

| Gate | 标准 | 通过条件 |
|------|------|----------|
| G1 | Test Sharpe > 0.8 | 必须 |
| G2 | Test Max DD < 12% | 必须 |
| G3 | Test vs Val 一致性 > 0.7 | 必须 |
| G4 | 专家相关性 < 0.5 | 必须 |

### 4.4 灰度上线

- Week 8: 影子模式 (100% 旧专家池，记录新专家池决策)
- Week 9: 10% 新专家池
- Week 10: 50% 新专家池
- Week 11: 100% 新专家池

---

## 总结对比

### 与 Transformer State v3 的对比

| 维度 | Transformer State v3 | 因子与专家优化 |
|------|---------------------|---------------|
| **问题定位** | 状态检索 | 因子与专家设计 |
| **核心假设** | 相似状态 → 相似专家 | 正交信息源 → 正交专家 |
| **方法** | 深度学习检索 | 分层筛选 + 权重优化 |
| **因子维度** | 28 维纯技术 | 6-10 维 (技术+宏观+相对) |
| **专家设计** | 8 个同质化变体 | 4-6 个正交专家 |
| **成本** | GPU 4-6 周 | CPU 6-8 周 |
| **可解释性** | 低 | 高 |
| **维护性** | 难 | 易 |

### 与 Adaptive Router 重构的对比

| 维度 | Adaptive Router 重构 | 因子与专家优化 |
|------|---------------------|---------------|
| **优化对象** | Meta-learner (路由器) | Base learners (因子+专家) |
| **假设** | 专家已足够好，只需选择 | 专家本身有问题，需重构 |
| **依赖** | 依赖现有专家池 | 重新设计专家池 |
| **增量** | 在现有基础上改进 | 推翻重来 |
| **风险** | 低 (专家池不变) | 中 (专家池变化) |

---

## 执行建议

1. **先做 Phase 1**: 分层筛选最重要，确定哪些因子真正有效
2. **Phase 1 可以快速验证**: 10 只股票 × 4 个 fold，1-2 天出结果
3. **Phase 2-3 可并行**: Phase 2 优化权重的同时，Phase 3 设计新专家
4. **每个 Phase 设 Early Stop**: Phase 1 如果发现现有因子已经很好，可以只做 Phase 2

---

**下一步**: 从哪里开始？

- Option A: 立即执行 Phase 1.1-1.3 (下载宏观数据 + 实现 macro_factors.py)
- Option B: 先在 10 只股票上快速验证 Phase 1.2 (分层筛选实验)
- Option C: 通读完整计划，确认方案可行性

你想怎么做？
