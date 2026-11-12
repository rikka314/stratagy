# Phase 1 快速启动指南

> **目标受众**: 需要使用新因子系统的开发者
> **前置条件**: Python 3.10+, 已安装依赖 (`requirements.txt`)
> **预计时间**: 5 分钟

---

## 快速开始

### 1. 计算单股因子

```python
from core.factor_pipeline import compute_all_factors
import pandas as pd

# 准备你的 OHLCV 数据
df = pd.DataFrame({
    'date': [...],
    'open': [...],
    'high': [...],
    'low': [...],
    'close': [...],
    'volume': [...],
})

# 一行代码计算所有 16 个因子
result = compute_all_factors(df, symbol='AAPL')

# result 包含原始列 + 16 个新因子
print(result.columns)
```

### 2. 查看因子架构

```python
from core.factor_pipeline import get_factor_pipeline

pipeline = get_factor_pipeline()

# 查看所有层的因子
all_factors = pipeline.get_all_factors()
for layer_name, factors in all_factors.items():
    print(f"{layer_name}: {factors}")

# 查看特定层
layer1_factors = pipeline.get_layer_factors(1)  # 趋势动量
layer4_factors = pipeline.get_layer_factors(4)  # 宏观相对
```

### 3. 运行演示

```bash
# 完整因子计算演示
python model-test/demo_factor_pipeline.py

# 因子筛选实验
python model-test/phase1_factor_selection.py
```

### 4. 运行测试

```bash
# 测试宏观因子
pytest tests/test_macro_factors.py -v

# 测试完整 pipeline
pytest tests/test_factor_pipeline.py -v

# 运行所有测试
pytest tests/test_macro_factors.py tests/test_factor_pipeline.py -v
```

---

## 因子清单

### Layer 1: 趋势动量 (3 个因子)

| 因子 | 说明 | 范围 |
|---|---|---|
| `mom_short_z` | 10 日动量，z-score 标准化 | 约 -3 到 +3 |
| `mom_long_z` | 60 日动量，z-score 标准化 | 约 -3 到 +3 |
| `macd_z` | MACD (EMA12 - EMA26)，z-score 标准化 | 约 -3 到 +3 |

### Layer 2: 均值回归 (3 个因子)

| 因子 | 说明 | 范围 |
|---|---|---|
| `rsi_z` | RSI (14 日)，z-score 标准化 | 约 -3 到 +3 |
| `bb_position_rank` | 布林带内位置，百分位排名 | 0 到 1 |
| `price_position_rank` | 60 日价格通道位置，百分位排名 | 0 到 1 |

### Layer 3: 风险与成交量 (4 个因子)

| 因子 | 说明 | 范围 |
|---|---|---|
| `vol_z` | 20 日波动率，z-score 标准化 | 约 -3 到 +3 |
| `drawdown_rank` | 当前回撤，百分位排名 | 0 到 1 |
| `obv_trend_rank` | OBV 趋势，百分位排名 | 0 到 1 |
| `volume_ratio_rank` | 成交量比率，百分位排名 | 0 到 1 |

### Layer 4: 宏观与相对 (6 个因子)

| 因子 | 说明 | 范围 |
|---|---|---|
| `vix_level` | VIX 水平 | 实际值 |
| `vix_regime` | VIX 区制 | 0=低, 1=中, 2=高 |
| `rel_strength_spy` | 相对 SPY 的 20 日强度 | 约 -0.5 到 +0.5 |
| `market_breadth` | 市场广度 (上涨股票占比) | 0 到 1 |
| `beta_20d` | 20 日 beta | 约 -2 到 +2 |
| `sector_momentum` | 行业 20 日动量 | 约 -0.5 到 +0.5 |

**注意**: 
- `z-score` 因子均值约为 0，标准差约为 1
- `rank` 因子是百分位排名，0 表示最低，1 表示最高
- 宏观因子使用实际值或分类值

---

## 数据要求

### 输入格式

```python
df = pd.DataFrame({
    'date': pd.date_range('2020-01-01', periods=200, freq='B'),  # 必须
    'open': [...],    # 必须
    'high': [...],    # 必须
    'low': [...],     # 必须
    'close': [...],   # 必须
    'volume': [...],  # 必须
})
```

### 最小数据量

- **Layer 1-3 (技术因子)**: 至少 60 天数据
- **Layer 4 (宏观因子)**: 需要对应日期的 VIX 和 SPY 数据
  - VIX 数据路径: `data/macro/vix_daily.parquet`
  - SPY 数据路径: `data/macro/spy_daily.parquet`

### 宏观数据下载

```bash
# 如果宏观数据不存在，运行下载脚本
python data-pipeline/download_macro_data.py
# 或使用备用方案
python data-pipeline/download_macro_data_alternative.py
```

---

## 使用示例

### 示例 1: 单股完整分析

```python
from core.factor_pipeline import compute_all_factors
import pandas as pd

# 加载你的数据
df = pd.read_parquet('data/us/AAPL.parquet')

# 计算所有因子
df_with_factors = compute_all_factors(df, symbol='AAPL')

# 使用因子
# 例如: 趋势策略
df_with_factors['trend_signal'] = (
    df_with_factors['mom_short_z'] + 
    df_with_factors['macd_z']
) / 2

# 例如: 宏观过滤
df_with_factors['macro_filter'] = (
    df_with_factors['vix_regime'] <= 1  # 只在低/中 VIX 时交易
)

# 生成最终信号
df_with_factors['final_signal'] = (
    df_with_factors['trend_signal'] * 
    df_with_factors['macro_filter']
)
```

### 示例 2: 因子 IC 测试

```python
from core.factor_pipeline import compute_all_factors
import pandas as pd

# 计算因子
df = compute_all_factors(df, symbol='AAPL')

# 计算前瞻收益
df['forward_return'] = df['close'].pct_change(20).shift(-20)

# 计算因子 IC
factor = 'mom_short_z'
ic = df[factor].corr(df['forward_return'])
print(f"{factor} IC: {ic:.4f}")

# 滚动 IC
rolling_ic = df[factor].rolling(60).corr(df['forward_return'])
print(f"Mean IC: {rolling_ic.mean():.4f}")
print(f"IC Sharpe: {rolling_ic.mean() / rolling_ic.std():.4f}")
```

### 示例 3: 分层回测

```python
from core.factor_pipeline import compute_all_factors, get_factor_pipeline
import pandas as pd

pipeline = get_factor_pipeline()
df = compute_all_factors(df, symbol='AAPL')

# 只使用 Layer 1 (趋势动量)
layer1_factors = pipeline.get_layer_factors(1)
df['layer1_score'] = df[layer1_factors].mean(axis=1)

# 只使用 Layer 4 (宏观)
layer4_factors = pipeline.get_layer_factors(4)
df['layer4_score'] = df[layer4_factors].mean(axis=1)

# 对比两种策略的表现
# ... (接入你的回测系统)
```

---

## 常见问题

### Q1: 宏观因子全是 NaN？

**A**: 检查宏观数据是否存在：
```python
from pathlib import Path

vix_path = Path('data/macro/vix_daily.parquet')
spy_path = Path('data/macro/spy_daily.parquet')

print(f"VIX 数据: {vix_path.exists()}")
print(f"SPY 数据: {spy_path.exists()}")

# 如果不存在，运行下载脚本
```

### Q2: 因子值不稳定？

**A**: 确保有足够的历史数据：
- z-score 因子需要至少 60 天历史
- 长期动量 (`mom_long_z`) 需要至少 120 天
- rank 因子需要至少 20 天

### Q3: 计算速度慢？

**A**: Pipeline 使用单例模式，宏观数据只加载一次：
```python
# 好: 复用同一个 pipeline 实例
from core.factor_pipeline import get_factor_pipeline
pipeline = get_factor_pipeline()

for symbol in symbols:
    df = load_data(symbol)
    result = pipeline.compute_all_factors(df, symbol)

# 坏: 每次都创建新实例
from core.factor_pipeline import FactorPipeline
for symbol in symbols:
    pipeline = FactorPipeline()  # 重复加载宏观数据！
    ...
```

### Q4: 如何只计算特定层的因子？

**A**: 直接调用私有方法（用于测试）：
```python
pipeline = get_factor_pipeline()

# 只计算 Layer 1
df = pipeline._compute_layer1_trend_momentum(df)

# 只计算 Layer 4
df = pipeline.macro_factors.compute(df, symbol='AAPL')
```

---

## 相关文档

- **完整报告**: `document/phase1_completion_report.md`
- **优化计划**: `document/factor_and_expert_optimization_plan.md`
- **代码文档**: 
  - `core/macro_factors.py` - 宏观因子实现
  - `core/factor_pipeline.py` - 完整 pipeline
- **测试**: 
  - `tests/test_macro_factors.py`
  - `tests/test_factor_pipeline.py`

---

## 下一步

Phase 1 完成了因子基础设施，下一步是 **Phase 2: 专家体系重构**。

计划内容：
1. 减少同质专家 (sm/fsm 系列)
2. 增加宏观专家和相对强度专家
3. 重新设计专家池 (9-10 个异构专家)
4. 实现专家评估和筛选

参见 `document/factor_and_expert_optimization_plan.md` Phase 2 部分。
