# CN_A Factor Composite Phase 2 验收报告

> 执行日期：2026-08-23
> 阶段：Phase 2 - CN_A Market Context 和因子实现
> 状态：✅ **PASSED**

---

## 1. 执行摘要

Phase 2 已完成 CN_A 市场原生因子的实现，包括：

- ✅ Benchmark returns 和 volatility 计算
- ✅ Market volatility level 和 regime 分类
- ✅ Relative strength vs benchmark
- ✅ Market beta 计算
- ✅ Market breadth（基于 frozen universe）
- ✅ CN_A tradability status（停牌、涨跌停检测）
- ✅ 完整的单元测试覆盖（22 个测试全部通过）

所有实现严格遵循 Phase 2 要求：
- 不使用 SPY/VIX 数据
- 使用 `market_*` 命名约定
- 支持 000300 benchmark 或 equal-weight fallback
- 所有计算都是 point-in-time，无未来数据泄漏

---

## 2. 交付产物

### 2.1 核心模块

| 文件 | 行数 | 用途 |
|------|------|------|
| `core/cn_a_market_factors.py` | 463 | CN_A 市场因子计算主模块 |
| `tests/test_cn_a_market_factors.py` | 358 | 完整单元测试套件 |

### 2.2 已实现函数

#### Benchmark 相关
- `compute_benchmark_returns()` - 计算 benchmark 的 1/5/20 日收益、波动率、回撤、趋势
- `compute_market_volatility_level()` - 实现 realized volatility 和三档 regime 分类（low/medium/high）

#### 相对指标
- `compute_relative_strength()` - 计算股票 vs benchmark 的相对强度
- `compute_market_beta()` - 计算滚动 beta（默认 20 日）

#### 市场宽度
- `compute_market_breadth()` - 从 universe 提取 breadth_up_ratio、constituent_count

#### A 股特有
- `compute_cn_a_tradability_status()` - 检测停牌、涨停、跌停状态

#### 集成接口
- `build_cn_a_market_context()` - 构建 CN_A MarketFactorContext
- `compute_cn_a_market_factors()` - 为单个股票计算所有市场因子
- `export_cn_a_market_context_quality_report()` - 生成质量报告

---

## 3. 测试覆盖

### 3.1 测试统计

```
22 passed in 0.82s
```

### 3.2 测试类别

| 类别 | 测试数量 | 状态 |
|------|----------|------|
| 单函数正确性 | 8 | ✅ PASSED |
| Context 构建 | 3 | ✅ PASSED |
| 集成计算 | 3 | ✅ PASSED |
| 安全性与隔离 | 3 | ✅ PASSED |
| 边界条件 | 5 | ✅ PASSED |

### 3.3 关键测试验证

#### ✅ 数据隔离
- `test_cn_a_no_spy_vix_leakage` - 验证 CN_A 不读取 SPY/VIX artifacts
- `test_compute_cn_a_market_factors_wrong_market` - 验证 market mismatch 会失败

#### ✅ 命名规范
- `test_cn_a_factor_names_no_us_aliases` - 验证不生成 `vix_level`、`rel_strength_spy` 等 US 别名

#### ✅ Point-in-time
- `test_benchmark_returns_no_forward_looking` - 验证 return_20 只使用历史数据
- `test_relative_strength_symmetry` - 验证 stock==benchmark 时相对强度为 0

#### ✅ A 股特性
- `test_compute_cn_a_tradability_suspended` - 验证停牌检测
- `test_compute_cn_a_tradability_limit_up` - 验证涨停检测
- `test_tradability_mutually_exclusive` - 验证状态互斥性

---

## 4. 因子输出字段

### 4.1 Benchmark 派生字段

```python
market_return_1          # 1 日收益
market_return_5          # 5 日收益
market_return_20         # 20 日收益
market_vol_level         # 20 日 realized volatility
market_vol_regime        # low / medium / high
market_drawdown_60       # 60 日最大回撤
```

### 4.2 相对强度与 Beta

```python
rel_strength_market      # stock_return_20 - benchmark_return_20
market_beta_20d          # 20 日滚动 beta
```

### 4.3 市场宽度（如果提供 universe）

```python
breadth_up_ratio_1       # 当日上涨比例
breadth_up_ratio_20      # 20 日均值
market_breadth           # 主要宽度信号（= breadth_up_ratio_1）
market_constituent_count # 有效成分股数量
```

### 4.4 Sector（当前 unavailable）

```python
sector_momentum          # 当前为 NaN，预留接口
```

### 4.5 可交易性状态

```python
is_suspended             # 停牌标志
is_limit_up              # 涨停标志
is_limit_down            # 跌停标志
has_valid_close          # 有效收盘价
tradability_status       # normal / suspended / limit_up / limit_down
```

---

## 5. Benchmark 策略

根据执行计划 Phase 2.1，CN_A benchmark 优先级：

### 5.1 优先级

1. **000300 沪深300**（market-native）
   - 状态：当前 `unavailable`
   - 需要外部数据源
   - 未来可补充

2. **Frozen universe equal-weight**（✅ 已实现）
   - 基于 `full_cn_a_deans_60` 的 60 个股票
   - 使用日收益率等权平均
   - 自动计算 breadth indicators
   - Snapshot SHA-256: `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`

3. **失败模式**
   - 如果两者都不可用，`build_cn_a_market_context()` 明确失败
   - 不伪造 benchmark

### 5.2 当前实现

Phase 2 使用 **frozen universe equal-weight** 作为 benchmark：

```python
context = build_cn_a_market_context(
    universe_frame=cn_a_60_stocks_frame
)

# context.benchmark_symbol == "frozen_universe_equal_weight"
# context.factor_availability["benchmark"] == "frozen_universe_equal_weight_close_return"
# context.factor_availability["breadth"] == "frozen_universe"
```

---

## 6. 市场隔离验证

### 6.1 CN_A 禁止读取的 US artifacts

✅ 已验证以下文件不会被 CN_A context 读取：

- `data/macro/spy_daily.parquet`
- `data/macro/vix_daily.parquet`
- `data/macro/us_sector_map.csv`

### 6.2 命名空间隔离

✅ CN_A 输出字段使用独立命名：

| US 字段 | CN_A 对应字段 | 状态 |
|---------|--------------|------|
| `vix_level` | `market_vol_level` | ✅ 隔离 |
| `vix_regime` | `market_vol_regime` | ✅ 隔离 |
| `rel_strength_spy` | `rel_strength_market` | ✅ 隔离 |

### 6.3 Market context 校验

```python
# 正确：CN_A context + CN_A 调用
context = build_cn_a_market_context(universe_frame=df)
factors = compute_cn_a_market_factors(stock_df, context)  # ✅

# 错误：US context + CN_A 调用
us_context = MarketFactorContext(market="US", ...)
factors = compute_cn_a_market_factors(stock_df, us_context)  # ❌ ValueError
```

---

## 7. Phase 2 停止门检查

根据执行计划 10.2，Phase 2 的停止门：

| 条件 | 检查结果 | 状态 |
|------|----------|------|
| PIT violation | 无 | ✅ PASS |
| 核心因子缺失无解释 | 所有因子都有明确来源 | ✅ PASS |
| 日期/symbol 主键重复 | 无重复 | ✅ PASS |
| CN_A 误读 US macro artifact | 测试验证隔离 | ✅ PASS |
| Sector/volatility 字段无法解释 | Volatility 使用 realized，sector 标记 unavailable | ✅ PASS |
| Source manifest 状态非 ready | Phase 0 source lock 为 ready | ✅ PASS |

**结论：Phase 2 未触发任何停止门，准入 Phase 3。**

---

## 8. Volatility 实现细节

### 8.1 为什么不使用中国 VIX

CN_A 不依赖中国波动率指数（如 iVIX），原因：

1. 数据可获得性不稳定
2. 历史覆盖范围有限
3. 计算方法不统一

### 8.2 Realized Volatility 替代方案

Phase 2 使用 **benchmark realized volatility**：

```python
volatility_20 = benchmark["return_1"].rolling(20, min_periods=20).std()
```

### 8.3 Regime 分类

使用 252 日滚动百分位数：

- **Low**: < 33rd percentile
- **Medium**: 33-66th percentile
- **High**: > 66th percentile

这个方法：
- 完全基于历史数据
- 自适应市场环境
- 可审计和重现

---

## 9. Breadth 实现

### 9.1 Frozen Universe Breadth

当使用 equal-weight benchmark 时，自动计算 breadth：

```python
breadth_up_ratio_1 = (daily_returns > 0).mean(axis=1)
breadth_up_ratio_20 = breadth_up_ratio_1.rolling(20).mean()
market_constituent_count = valid_prices_count_per_day
```

### 9.2 缺失 Universe 时的处理

如果只提供 benchmark_frame 而不提供 universe_frame：

- `breadth_up_ratio_1` = NaN
- `breadth_up_ratio_20` = NaN
- `market_breadth` = NaN
- `market_constituent_count` = NaN

状态明确标记为 `unavailable`，不伪造数据。

---

## 10. Tradability Status

### 10.1 停牌检测

```python
is_suspended = (
    close <= 0 or isna(close) or
    volume <= 0 or isna(volume) or
    open <= 0 or isna(open)
)
```

### 10.2 涨跌停检测（简化版）

```python
daily_return = close / prev_close - 1

is_limit_up = daily_return >= 0.095    # ~10%
is_limit_down = daily_return <= -0.095  # ~-10%
```

**注意**：真实 A 股有不同板块的涨跌停限制（10%/20%/30%），Phase 2 使用简化版本。Phase 3 可根据需要细化。

---

## 11. 代码质量

### 11.1 不可变性

所有函数返回新 DataFrame，不修改输入：

```python
stock = stock_frame.loc[:, ["date", "close"]].copy()  # 显式 copy
result = merged.loc[:, output_cols].copy()            # 输出也 copy
```

### 11.2 错误处理

- 明确的 ValueError 消息
- Market mismatch 会失败
- 必需字段缺失会失败
- 无静默 fallback

### 11.3 类型安全

```python
from __future__ import annotations  # 支持前向引用

def compute_relative_strength(
    stock_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    ...
```

---

## 12. 与 Phase 1 的集成

Phase 2 完全兼容 Phase 1 的 `MarketFactorContext`：

```python
# Phase 1 提供的接口
from core.market_factor_context import build_market_factor_context

# Phase 2 使用该接口
context = build_market_factor_context(
    market="CN_A",
    universe_frame=df,
)

# Phase 2 的专用计算
from core.cn_a_market_factors import compute_cn_a_market_factors

factors = compute_cn_a_market_factors(stock_df, context)
```

---

## 13. 下一步：Phase 3

Phase 2 已完成，准入 Phase 3 - 构建 CN_A Factor Pipeline 和 panel。

Phase 3 工作项：

1. 为 60 个 CN_A 标的生成完整 factor panel
2. 整合技术因子（mom_short_z, macd_z, rsi_z, ...）
3. 整合 Phase 2 的 market factors
4. PIT audit 和 missingness audit
5. Schema/source hash lock
6. 输出到 `model-test/outputs/composite_cn_a/cn_a_factor_panel.parquet`

参考执行计划 Phase 3 章节（第 580-696 行）。

---

## 14. 验收签名

| 项目 | 状态 | 备注 |
|------|------|------|
| CN_A market context 实现 | ✅ READY | 463 行代码 |
| 单元测试覆盖 | ✅ PASSED | 22/22 通过 |
| US artifact 隔离 | ✅ VERIFIED | 测试确认 |
| Benchmark 策略 | ✅ IMPLEMENTED | Equal-weight fallback |
| Volatility 实现 | ✅ IMPLEMENTED | Realized volatility |
| Breadth 实现 | ✅ IMPLEMENTED | Frozen universe |
| Tradability 实现 | ✅ IMPLEMENTED | 停牌、涨跌停 |
| 命名规范 | ✅ COMPLIANT | market_* 命名 |
| PIT 合规 | ✅ VERIFIED | 无未来数据泄漏 |
| Phase 2 停止门 | ✅ PASSED | 所有条件满足 |

**Phase 2 状态：✅ READY**

**决策：✅ 准入 Phase 3**

---

生成时间：2026-08-23
报告版本：v1.0
