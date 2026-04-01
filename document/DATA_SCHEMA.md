# 数据字段规范（Week 1 · Day 3 产出）

> 整理时间：2026-03-18
> 目的：统一美股 / A 股进入策略管道前的 DataFrame 列结构、类型约束和字段映射规则

---

## 1. 结论先行

本项目后续统一采用一套标准行情表结构，核心管道只认以下必需列：

- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

这意味着：

1. `core/indicators.py`、`core/signals.py`、`core/backtest.py` 无需区分美股或 A 股。
2. 第 2 周 A 股接入的重点在 `core/data.py` 和 `core/utils.py`，不是策略层。
3. `standardize_columns()` 需要扩展，但只负责“低风险列名归一化”，不负责带业务含义的单位换算。

---

## 2. 标准 DataFrame 结构

### 2.1 必需列

| 列名 | 类型 | 单位/约束 | 说明 |
|------|------|-----------|------|
| `date` | `datetime64[ns]` | 非空，升序 | 交易日 |
| `open` | `float64` | 非空，>= 0 | 开盘价 |
| `high` | `float64` | 非空，>= 0 | 最高价 |
| `low` | `float64` | 非空，>= 0 | 最低价 |
| `close` | `float64` | 非空，>= 0 | 收盘价 |
| `volume` | `float64` | 非空，>= 0，统一为“股” | 成交量 |

### 2.2 推荐可选列

| 列名 | 类型 | 单位/约束 | 用途 |
|------|------|-----------|------|
| `symbol` | `string` / `object` | 股票代码 | 展示、缓存键、导出 |
| `market` | `string` / `object` | `US` / `CN_A` | 路由与显示 |
| `currency` | `string` / `object` | `USD` / `CNY` | 展示说明 |
| `amount` | `float64` | 保留源市场货币单位 | A 股成交额等扩展字段 |
| `amplitude_pct` | `float64` | 百分点，3.5 表示 3.5% | 波动信息 |
| `pct_change` | `float64` | 百分点 | 涨跌幅 |
| `price_change` | `float64` | 源市场货币单位 | 涨跌额 |
| `turnover_pct` | `float64` | 百分点 | 换手率 |
| `adjust` | `string` / `object` | `""` / `qfq` / `hfq` | 记录复权方式 |

说明：

- 核心策略只依赖必需列。
- 可选列主要服务于 UI 展示、后续评估模块和导出。
- `amount`、`price_change` 涉及不同市场货币，不应直接跨市场比较。

---

## 3. 全局规范

### 3.1 排序与唯一性

- `date` 必须转为 `datetime64[ns]`
- 数据按 `date` 升序排序
- 若同一 `date` 出现重复，保留最后一条

### 3.2 数值类型

- OHLCV 统一转为 `float64`
- 百分比字段保留“百分点”口径，不转成 0~1 小数
- `symbol` 一律按字符串处理，避免 `000001` 被读成 `1`

### 3.3 缺失值规则

- 正式行情数据路径中，缺失任一必需列时应报错
- 行级缺失处理建议：`date/open/high/low/close/volume` 任一缺失则丢弃该行
- 用户上传 CSV 若缺少必需列，可在 UI 层提前提示，不建议在策略层静默兜底

### 3.4 成交量单位统一

这是本次 Day 3 最需要提前定死的点：

- 美股 `stock_us_daily.volume` 本身就是股数
- A 股 `stock_zh_a_hist.成交量` 的官方文档单位是“手”
- 标准列 `volume` 统一定义为“股”

因此，第 2 周接入 A 股时应在 `fetch_a_stock()` 中执行：

```python
df["volume"] = pd.to_numeric(df["volume"], errors="coerce") * 100
```

这样做的原因：

- 对当前指标体系最稳妥，避免后续把“手”和“股”混在一起
- `OBV`、`volume_ratio` 等指标即便主要看相对变化，统一单位仍更干净
- 未来若做跨市场统计或导出，数据含义不会漂移

---

## 4. 美股源字段映射

数据源：AKShare `stock_us_daily`

根据 AKShare 官方文档，`stock_us_daily` 的历史行情输出字段已经基本符合项目标准列。

| 源字段 | 标准字段 | 是否必需 | 处理规则 |
|------|------|------|------|
| `date` | `date` | 是 | 转 `datetime64[ns]` |
| `open` | `open` | 是 | 转 `float64` |
| `high` | `high` | 是 | 转 `float64` |
| `low` | `low` | 是 | 转 `float64` |
| `close` | `close` | 是 | 转 `float64` |
| `volume` | `volume` | 是 | 转 `float64` |

补充约定：

- `symbol` 不在返回表中，需要从函数入参补回
- `market` 固定写入 `US`
- `currency` 固定写入 `USD`
- `adjust` 直接记录函数入参

---

## 5. A 股源字段映射

数据源：AKShare `stock_zh_a_hist`

根据 AKShare 官方文档，A 股日线历史行情字段如下：`日期`、`股票代码`、`开盘`、`收盘`、`最高`、`最低`、`成交量`、`成交额`、`振幅`、`涨跌幅`、`涨跌额`、`换手率`。

### 5.1 A 股到标准列映射表

| 源字段 | 标准字段 | 是否必需 | 处理规则 |
|------|------|------|------|
| `日期` | `date` | 是 | 转 `datetime64[ns]` |
| `开盘` | `open` | 是 | 转 `float64` |
| `最高` | `high` | 是 | 转 `float64` |
| `最低` | `low` | 是 | 转 `float64` |
| `收盘` | `close` | 是 | 转 `float64` |
| `成交量` | `volume` | 是 | 先转数值，再乘 `100`，统一到“股” |
| `股票代码` | `symbol` | 否 | 转字符串，A 股代码保留前导零 |
| `成交额` | `amount` | 否 | 转 `float64`，单位保留“元” |
| `振幅` | `amplitude_pct` | 否 | 转 `float64`，保留百分点 |
| `涨跌幅` | `pct_change` | 否 | 转 `float64`，保留百分点 |
| `涨跌额` | `price_change` | 否 | 转 `float64`，单位保留“元” |
| `换手率` | `turnover_pct` | 否 | 转 `float64`，保留百分点 |

### 5.2 A 股补充约定

- `market` 固定写入 `CN_A`
- `currency` 固定写入 `CNY`
- `adjust` 记录 `""` / `qfq` / `hfq`
- `symbol` 统一保存为 6 位字符串，如 `000001`

---

## 6. 任务 3.3 的权衡结论：`standardize_columns()` 到底怎么改

这部分不建议“全放进去”，也不建议“完全不改”。

### 方案 A：只扩展 `standardize_columns()`

做法：

- 把所有中文字段、英文别名、单位逻辑、市场逻辑都塞进一个函数

优点：

- 修改点少
- W2 接入速度快

缺点：

- 函数职责会膨胀
- 后续新增别的数据源时会继续堆逻辑
- “列名映射”和“业务语义转换”混在一起，不利于维护

### 方案 B：完全不改 `standardize_columns()`，全部放到 `fetch_a_stock()`

做法：

- `standardize_columns()` 继续只处理现有英文别名
- A 股中文列映射、单位换算都写在新函数里

优点：

- 职责清晰
- 业务语义和数据源耦合合理

缺点：

- 上传 CSV、未来其他中文数据源不能复用
- 一些低风险别名归一化会分散到多个入口

### 推荐方案：折中方案

**结论：`standardize_columns()` 要扩展，但只扩展到“通用别名归一化”；单位换算和市场补充字段留在 `fetch_a_stock()`。**

#### `standardize_columns()` 负责：

- 小写化、去空格
- 中英文常见别名统一到标准列名
- 不做单位换算，不写市场常量，不补业务字段

建议扩展到下面这组映射：

| 原字段 | 标准字段 |
|------|------|
| `trade_date` | `date` |
| `datetime` | `date` |
| `日期` | `date` |
| `开盘` | `open` |
| `最高` | `high` |
| `最低` | `low` |
| `收盘` | `close` |
| `vol` | `volume` |
| `volumn` | `volume` |
| `成交量` | `volume` |
| `股票代码` | `symbol` |
| `成交额` | `amount` |
| `振幅` | `amplitude_pct` |
| `涨跌幅` | `pct_change` |
| `涨跌额` | `price_change` |
| `换手率` | `turnover_pct` |

#### `fetch_a_stock()` 负责：

- 调 `ak.stock_zh_a_hist()`
- 调 `standardize_columns()`
- 将 `volume` 从“手”转换为“股”
- 补 `market/currency/adjust`
- 把 `symbol` 规整为字符串

### 为什么我建议这个折中方案

- 它和当前项目结构最匹配，W2 改动最小
- `standardize_columns()` 仍然保持“列名清洗器”角色，不会变成大杂烩
- 中文 CSV 上传场景也能直接受益
- 未来如果增加港股、指数、ETF 数据源，也还能继续复用

---

## 7. 对第 2 周实现的直接约束

第 2 周 A 股接入时，建议按以下顺序实现：

1. 在 `core/data.py` 新增 `fetch_a_stock(symbol, adjust)`
2. 先调用 `ak.stock_zh_a_hist(...)`
3. 再调用 `standardize_columns(df)`
4. 执行 `date` 转换、排序、去重
5. 执行 `volume *= 100`
6. 统一把必需列转为数值
7. 补写 `symbol/market/currency/adjust`
8. 丢弃必需列缺失行

这能保证新接入路径与现有 `fetch_data()` 返回结构一致。

---

## 8. 本次 Day 3 产出清单

- A 股 API 字段已完成官方文档层面的调研
- 美股 / A 股统一标准列已确定
- `standardize_columns()` 的扩展边界已明确
- `document/DATA_SCHEMA.md` 已落盘

---

## 参考

- AKShare `stock_zh_a_hist` 官方文档：https://akshare.akfamily.xyz/data/stock/stock.html
- AKShare `stock_us_daily` 官方文档：https://akshare.akfamily.xyz/data/stock/stock.html
