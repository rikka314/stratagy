# CN_A Factor Composite Phase 2 - 快速启动指南

> 完成日期：2026-08-23
> 状态：✅ READY
> 下一步：Phase 3 - 构建 CN_A Factor Panel

---

## 1. Phase 2 交付物

### 1.1 核心模块

```
core/cn_a_market_factors.py          # CN_A 市场因子计算（463 行）
tests/test_cn_a_market_factors.py    # 单元测试（358 行，22 个测试）
```

### 1.2 测试状态

```bash
pytest tests/test_cn_a_market_factors.py -v
# 22 passed in 0.82s
```

---

## 2. 快速使用示例

### 2.1 构建 CN_A Market Context

```python
from core.cn_a_market_factors import build_cn_a_market_context
import pandas as pd

# 方案 1：使用显式 benchmark（如 000300）
benchmark_df = pd.DataFrame({
    "date": pd.date_range("2020-01-01", periods=1000, freq="D"),
    "close": [3000 + i * 0.5 for i in range(1000)]
})

context = build_cn_a_market_context(benchmark_frame=benchmark_df)
# context.benchmark_symbol == "provided"

# 方案 2：使用 frozen universe（equal-weight benchmark）
universe_df = pd.DataFrame({
    "date": pd.date_range("2020-01-01", periods=1000, freq="D").repeat(60),
    "symbol": [f"00000{i}" for i in range(1, 61)] * 1000,
    "close": [50 + i * 0.1 for i in range(60000)]
})

context = build_cn_a_market_context(universe_frame=universe_df)
# context.benchmark_symbol == "frozen_universe_equal_weight"
# context.breadth_frame 自动生成
```

### 2.2 计算单股市场因子

```python
from core.cn_a_market_factors import compute_cn_a_market_factors

# 准备股票数据
stock_df = pd.DataFrame({
    "date": pd.date_range("2020-01-01", periods=1000, freq="D"),
    "open": [50 + i * 0.1 for i in range(1000)],
    "high": [52 + i * 0.1 for i in range(1000)],
    "low": [48 + i * 0.1 for i in range(1000)],
    "close": [50 + i * 0.1 for i in range(1000)],
    "volume": [1000000 for _ in range(1000)],
})

# 计算所有 CN_A 市场因子
factors = compute_cn_a_market_factors(stock_df, context)

# 输出字段
print(factors.columns.tolist())
# ['date', 'market_return_1', 'market_return_5', 'market_return_20',
#  'market_vol_level', 'market_vol_regime', 'rel_strength_market',
#  'market_beta_20d', 'market_drawdown_60', 'breadth_up_ratio_1',
#  'breadth_up_ratio_20', 'market_breadth', 'market_constituent_count',
#  'sector_momentum', 'is_suspended', 'is_limit_up', 'is_limit_down',
#  'has_valid_close', 'tradability_status']
```

---

## 3. 输出字段说明

### 3.1 Benchmark 派生字段

| 字段 | 含义 | 类型 |
|------|------|------|
| `market_return_1` | 1 日收益 | float |
| `market_return_5` | 5 日收益 | float |
| `market_return_20` | 20 日收益 | float |
| `market_vol_level` | 20 日 realized volatility | float |
| `market_vol_regime` | 波动率档位（low/medium/high） | str |
| `market_drawdown_60` | 60 日最大回撤 | float |

### 3.2 相对强度与 Beta

| 字段 | 含义 | 计算方式 |
|------|------|----------|
| `rel_strength_market` | 相对强度 | stock_return_20 - benchmark_return_20 |
| `market_beta_20d` | 20 日滚动 beta | cov(stock, benchmark) / var(benchmark) |

### 3.3 市场宽度（如果提供 universe）

| 字段 | 含义 | 范围 |
|------|------|------|
| `breadth_up_ratio_1` | 当日上涨比例 | [0, 1] |
| `breadth_up_ratio_20` | 20 日均值 | [0, 1] |
| `market_breadth` | 主要宽度信号（= breadth_up_ratio_1） | [0, 1] |
| `market_constituent_count` | 有效成分股数量 | int |

### 3.4 可交易性状态

| 字段 | 含义 | 类型 |
|------|------|------|
| `is_suspended` | 是否停牌 | bool |
| `is_limit_up` | 是否涨停 | bool |
| `is_limit_down` | 是否跌停 | bool |
| `has_valid_close` | 是否有有效收盘价 | bool |
| `tradability_status` | 状态（normal/suspended/limit_up/limit_down） | str |

### 3.5 Sector（当前 unavailable）

| 字段 | 含义 | 当前值 |
|------|------|--------|
| `sector_momentum` | 板块动量 | NaN（预留接口） |

---

## 4. 关键设计原则

### 4.1 市场隔离

✅ **CN_A 绝不读取 US artifacts**

```python
# ✅ 正确：CN_A 使用自己的 context
cn_a_context = build_cn_a_market_context(universe_frame=df)
factors = compute_cn_a_market_factors(stock_df, cn_a_context)

# ❌ 错误：CN_A 不能使用 US context
us_context = MarketFactorContext(market="US", ...)
factors = compute_cn_a_market_factors(stock_df, us_context)  # ValueError
```

### 4.2 命名规范

✅ **CN_A 使用 market_* 命名**

```python
# ✅ CN_A 输出
factors["market_vol_level"]      # 不是 vix_level
factors["market_vol_regime"]     # 不是 vix_regime
factors["rel_strength_market"]   # 不是 rel_strength_spy

# ❌ 这些字段不会出现在 CN_A 输出中
# factors["vix_level"]           # 不存在
# factors["rel_strength_spy"]    # 不存在
```

### 4.3 Point-in-time 保证

所有计算只使用决策日及之前的数据：

```python
# ✅ return_20 at row i only uses data from row i-20 to row i
factors.iloc[i]["market_return_20"]  # 只使用历史数据

# ✅ Beta 计算只使用滚动窗口内的数据
factors.iloc[i]["market_beta_20d"]   # 只使用过去 20 天
```

---

## 5. 与 Phase 1 的集成

Phase 2 完全兼容 Phase 1 的 `MarketFactorContext`：

```python
from core.market_factor_context import build_market_factor_context

# Phase 1 的通用接口
context = build_market_factor_context(
    market="CN_A",
    universe_frame=universe_df,
)

# Phase 2 使用该 context
from core.cn_a_market_factors import compute_cn_a_market_factors
factors = compute_cn_a_market_factors(stock_df, context)
```

---

## 6. Benchmark 策略

### 6.1 优先级

1. **000300 沪深300**（当前 unavailable）
2. **Frozen universe equal-weight** ✅（Phase 2 使用）
3. **失败模式**：两者都不可用时明确失败

### 6.2 当前实现

Phase 2 使用 **frozen universe equal-weight**：

```python
# 从 full_cn_a_deans_60 构建 universe
universe_df = load_cn_a_60_stocks()  # 60 个 CSV

context = build_cn_a_market_context(universe_frame=universe_df)

# Benchmark 信息
context.benchmark_symbol  # "frozen_universe_equal_weight"
context.factor_availability["benchmark"]  # "frozen_universe_equal_weight_close_return"
context.factor_availability["breadth"]    # "frozen_universe"
```

---

## 7. 测试覆盖

### 7.1 关键测试

```bash
# 数据隔离
pytest tests/test_cn_a_market_factors.py::test_cn_a_no_spy_vix_leakage -v

# 命名规范
pytest tests/test_cn_a_market_factors.py::test_cn_a_factor_names_no_us_aliases -v

# PIT 合规
pytest tests/test_cn_a_market_factors.py::test_benchmark_returns_no_forward_looking -v

# A 股特性
pytest tests/test_cn_a_market_factors.py::test_compute_cn_a_tradability_suspended -v
pytest tests/test_cn_a_market_factors.py::test_compute_cn_a_tradability_limit_up -v
```

### 7.2 全量测试

```bash
pytest tests/test_cn_a_market_factors.py -v
# 22 passed in 0.82s
```

---

## 8. Phase 3 准备

Phase 2 已完成，下一步进入 Phase 3：

### 8.1 Phase 3 目标

为 60 个 CN_A 标的生成完整 factor panel：

```
model-test/outputs/composite_cn_a/
  cn_a_factor_panel.parquet      # 完整因子面板
  factor_manifest.json           # 因子来源清单
  factor_quality.json            # 质量报告
  factor_schema.json             # Schema 定义
```

### 8.2 Phase 3 需要做的

1. **整合技术因子**：mom_short_z, macd_z, rsi_z, bb_position_rank, ...
2. **整合 Phase 2 市场因子**：使用 `compute_cn_a_market_factors()`
3. **PIT audit**：确保所有因子都是 point-in-time
4. **Missingness audit**：记录缺失率和原因
5. **Schema lock**：冻结因子 schema 和 source hash

### 8.3 推荐 CLI 入口

```bash
python model-test/build_cn_a_factor_panel.py \
  --config model-test/configs/composite_cn_a.json
```

---

## 9. 常见问题

### Q1: 如果没有 universe，breadth 会是什么？

**A**: 所有 breadth 字段都是 NaN，不伪造数据。

```python
context = build_cn_a_market_context(benchmark_frame=benchmark_df)
factors = compute_cn_a_market_factors(stock_df, context)

factors["market_breadth"].isna().all()  # True
```

### Q2: Volatility regime 的分类标准是什么？

**A**: 基于 252 日滚动百分位数：

- **Low**: < 33rd percentile
- **Medium**: 33-66th percentile
- **High**: > 66th percentile

### Q3: Tradability status 的涨跌停检测准确吗？

**A**: Phase 2 使用简化版本（±10%）。真实 A 股有不同板块的涨跌停限制（10%/20%/30%），Phase 3 可根据需要细化。

### Q4: Sector momentum 什么时候可用？

**A**: 当前 `unavailable`。需要外部提供 A 股行业映射和行业指数历史数据。

### Q5: 如何验证我的实现没有读取 US artifacts？

**A**: 运行隔离测试：

```bash
pytest tests/test_cn_a_market_factors.py::test_cn_a_no_spy_vix_leakage -v
```

---

## 10. 参考文档

- **执行计划**：`document/cn_a_factor_composite_parity_execution_plan.md`（Phase 2 章节：第 474-578 行）
- **验收报告**：`document/acceptance/cn_a_factor_composite_phase2.md`
- **Phase 1 集成**：`core/market_factor_context.py`
- **测试套件**：`tests/test_cn_a_market_factors.py`

---

**Phase 2 状态：✅ READY**

**下一步：Phase 3 - 构建 CN_A Factor Panel**
