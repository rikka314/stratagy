# 因子说明文档

> 适用范围：当前仓库中 `core/indicators.py` 与 `core/signals.py` 实现的 10 因子评分策略  
> 相关代码：`core/indicators.py`、`core/signals.py`、`ui/sidebar.py`

---

## 1. 先看结论

当前项目里的“因子”不是单独拿来直接交易的买卖信号，而是：

1. 先从价格和成交量数据中计算出 10 个因子
2. 再把它们标准化到可比较的尺度
3. 再按权重合成 `factor_score`
4. 再把 `factor_score` 转成分位数、仓位和买卖信号

也就是说：

- **指标** 是中间计算结果，比如 RSI、MACD、ATR、布林带、OBV
- **因子** 是从这些指标和价格行为中提炼出的可打分特征
- **`factor_score`** 是 10 个因子的综合分
- **策略信号** 是对综合分再叠加趋势/强度/风控过滤后得到的结果

可以把它理解成这条链路：

```text
OHLCV 原始行情
-> 技术指标
-> 10 个因子原始值
-> 标准化
-> factor_score
-> factor_percentile
-> target_position
-> buy_signal / sell_signal
```

---

## 2. 读这份文档前先分清几个概念

### 2.1 原始行情数据

当前策略最核心依赖的是标准 OHLCV：

- `open`
- `high`
- `low`
- `close`
- `volume`

它们是所有技术指标和因子的输入。

### 2.2 滚动窗口

很多因子都不是看“今天一个点”，而是看“最近 N 天”。

例如：

- `momentum_short=5` 表示看近 5 天收益
- `indicator_period=20` 表示看近 20 天的成交量均值、价格区间、OBV 变化
- `score_lookback=30` 表示用近 30 天的历史来做标准化

### 2.3 标准化

不同因子的量纲不一样：

- RSI 在 0 到 100 之间
- 动量是收益率
- 回撤是负百分比
- 成交量比通常大于 0

如果直接相加，会失真，所以策略先把它们变成可比较的尺度。

当前项目用了两种方式：

- **滚动 Z-score**：衡量“当前值比自己最近历史高/低多少个标准差”
- **滚动排名 `rolling_rank`**：把当前值放到自己最近历史里，映射到 `0~1`

### 2.4 正向因子和负向因子

- **正向因子**：值越大越偏多，得分越高
- **负向因子**：值越大越不好，得分要扣分

当前两个明确的负向因子是：

- 波动率 `volatility`
- 回撤 `drawdown`

### 2.5 因子、指标、过滤条件的区别

这三者很容易混：

- RSI 既是一个**技术指标**
- `rsi_z` 是把 RSI 转成了一个**因子分量**
- `rsi_ok = (rsi > rsi_lower) & (rsi < rsi_upper)` 则是一个**过滤条件**

同一个基础指标可以同时参与：

- 因子打分
- 入场过滤
- 出场过滤

---

## 3. 10 个因子的总表

| 因子 | 原始定义 | 标准化方式 | 方向 | 主要参数 | 直觉 |
|------|----------|------------|------|----------|------|
| 短期动量 | `close.pct_change(momentum_short)` | Z-score | 正向 | `momentum_short`, `score_lookback` | 近期涨得快，加分 |
| 长期动量 | `close.pct_change(momentum_long)` | Z-score | 正向 | `momentum_long`, `score_lookback` | 中期趋势强，加分 |
| MACD | `histogram = macd - signal` | Z-score | 正向 | `macd_fast/slow/signal`, `score_lookback` | 多头动能增强，加分 |
| RSI | `compute_rsi(close)` | Z-score | 正向 | `rsi_period`, `score_lookback` | 相对强弱偏强，加分 |
| 波动率 | `atr / close` | Z-score | 负向 | `atr_period`, `score_lookback` | 波动越大，惩罚越大 |
| 布林带位置 | `(close - bb_lower) / (bb_upper - bb_lower)` | rolling_rank | 正向 | `bb_period`, `bb_std`, `score_lookback` | 越靠上轨，越强 |
| OBV 趋势 | `obv.pct_change(indicator_period)` | rolling_rank | 正向 | `indicator_period`, `score_lookback` | 量能趋势越强，加分 |
| 成交量比 | `volume / avg_volume` | rolling_rank | 正向 | `indicator_period`, `score_lookback` | 放量更值得关注 |
| 价格位置 | `(close - period_low) / (period_high - period_low)` | rolling_rank | 正向 | `indicator_period`, `score_lookback` | 越靠近近期高点越强 |
| 回撤 | `close / close.cummax() - 1` | rolling_rank | 负向 | `score_lookback` | 回撤越深，惩罚越大 |

---

## 4. 每个因子是怎么计算的

## 4.1 短期动量

公式：

```text
ret_short = close[t] / close[t - momentum_short] - 1
```

代码实现：

```python
df["ret_short"] = df["close"].pct_change(momentum_short)
```

含义：

- 衡量最近一小段时间价格涨了多少
- 值越大，说明短线趋势越强

为什么需要它：

- 很多趋势行情开始时，短期收益率会先明显抬升
- 它对“近期正在发生什么”最敏感

局限：

- 对短期噪声也最敏感
- 在震荡市里容易被来回打脸

### 它和长期动量的关系

- 短期动量更敏感，反应快
- 长期动量更稳，抗噪更强
- 两者一起用，是为了同时看“最近爆发”和“中期延续”

---

## 4.2 长期动量

公式：

```text
ret_long = close[t] / close[t - momentum_long] - 1
```

代码实现：

```python
df["ret_long"] = df["close"].pct_change(momentum_long)
```

含义：

- 衡量一段更长周期内的累计涨跌幅
- 值越大，说明中期趋势更偏强

为什么需要它：

- 只看短期动量容易追到短线噪声
- 长期动量可以帮助确认“这不是一天两天的偶然波动”

---

## 4.3 MACD 因子

MACD 先不是因子，而是一个三步指标：

```text
ema_fast = EMA(close, macd_fast)
ema_slow = EMA(close, macd_slow)
macd = ema_fast - ema_slow
signal = EMA(macd, macd_signal)
histogram = macd - signal
```

当前策略真正拿来打分的是：

```text
MACD 因子 = histogram
```

代码实现：

```python
df["macd"], df["signal"], df["histogram"] = compute_macd(...)
df["macd_z"] = rolling_zscore(df["histogram"], score_lookback)
```

含义：

- `macd` 代表快慢均线差
- `signal` 是 `macd` 的平滑线
- `histogram` 代表两者的差距变化

为什么用 `histogram` 而不是只用 `macd`：

- `histogram` 更接近“动能是否还在增强”
- 它能反映趋势加速或减速

---

## 4.4 RSI 因子

RSI 的基本思想是比较一段时间内：

- 平均上涨强度
- 平均下跌强度

公式思路：

```text
RS = average_gain / average_loss
RSI = 100 - 100 / (1 + RS)
```

代码里用 EWMA 平滑实现。

含义：

- RSI 高，说明上涨强度占优
- RSI 低，说明下跌强度占优

当前策略里 RSI 有两层作用：

1. `rsi_z` 作为因子分量参与综合评分
2. `rsi_ok` 作为过滤条件，要求 RSI 落在区间内

这说明 RSI 既被当作“强弱特征”，也被当作“过热/过冷风险过滤器”。

---

## 4.5 波动率因子

当前不是直接用收益率标准差，而是用：

```text
volatility = ATR / close
```

先看 ATR：

```text
TR = max(
    high - low,
    abs(high - prev_close),
    abs(low - prev_close)
)
ATR = TR 的 EWMA
```

含义：

- ATR 衡量价格日内和跳空的真实波动
- `ATR / close` 是把绝对波幅转成相对波幅

为什么它是负向因子：

- 波动太大，通常意味着噪声更强、风险更高
- 所以在综合评分里是扣分项

注意：

- 这里的波动率更多是“交易风险”的代理变量
- 不是统计学意义上唯一的波动率定义

---

## 4.6 布林带位置因子

布林带的定义：

```text
middle = rolling_mean(close, bb_period)
std = rolling_std(close, bb_period)
bb_upper = middle + bb_std * std
bb_lower = middle - bb_std * std
```

当前策略取的位置变量：

```text
bb_position = (close - bb_lower) / (bb_upper - bb_lower)
```

含义：

- 接近 `0`：价格靠近下轨
- 接近 `0.5`：价格在带中间
- 接近 `1`：价格靠近上轨

为什么它是正向因子：

- 在趋势策略语境里，价格站在上半区通常说明更强
- 不是在做均值回归，所以这里没有把“靠上轨”视为反向做空信号

---

## 4.7 OBV 趋势因子

OBV（On-Balance Volume）的思想是：

- 收盘上涨，当天成交量记为正
- 收盘下跌，当天成交量记为负
- 然后累计起来

公式思路：

```text
direction = sign(close.diff())
obv = cumsum(direction * volume)
obv_trend = obv.pct_change(indicator_period)
```

含义：

- 看的是“量能累计趋势是否在改善”
- 不是只看某一天放量，而是看量价关系有没有持续强化

为什么它和成交量比都保留：

- `volume_ratio` 看的是当下是否放量
- `obv_trend` 看的是量能趋势是否持续配合上涨

两者是互补关系。

---

## 4.8 成交量比因子

公式：

```text
avg_volume = rolling_mean(volume, indicator_period)
volume_ratio = volume / avg_volume
```

含义：

- 大于 1：当前成交量高于近期平均
- 小于 1：当前成交量低于近期平均

为什么有用：

- 趋势突破如果伴随放量，通常可信度更高
- 但如果只是单日异常放量，也可能是噪声

所以它单独不能决定交易，只能作为综合评分里的一个维度。

---

## 4.9 价格位置因子

公式：

```text
period_high = rolling_max(high, indicator_period)
period_low = rolling_min(low, indicator_period)
price_position = (close - period_low) / (period_high - period_low)
```

含义：

- 接近 `1`：靠近近期区间高点
- 接近 `0`：靠近近期区间低点

它和布林带位置的区别：

- `bb_position` 是相对统计带宽的位置
- `price_position` 是相对最近最高/最低区间的位置

两者都在描述“价格站位”，但参考系不同：

- 一个参考波动带
- 一个参考近期价格区间

---

## 4.10 回撤因子

公式：

```text
cummax = close.cummax()
drawdown = close / cummax - 1
```

含义：

- 始终小于等于 0
- 越接近 0，说明离历史高点越近
- 越负，说明从高点回撤越深

为什么它是负向因子：

- 深回撤往往意味着趋势被破坏、风险增加
- 所以回撤越大，在综合评分里扣分越多

它和价格位置的区别：

- `price_position` 看的是最近一段区间里的位置
- `drawdown` 看的是相对历史累计高点的损失

所以一个偏短中期位置，一个偏全程风险状态。

---

## 5. 标准化是怎么做的

## 5.1 前 5 个因子：滚动 Z-score

当前代码：

```python
df["mom_short_z"] = rolling_zscore(df["ret_short"], score_lookback)
df["mom_long_z"] = rolling_zscore(df["ret_long"], score_lookback)
df["macd_z"] = rolling_zscore(df["histogram"], score_lookback)
df["rsi_z"] = rolling_zscore(df["rsi"], score_lookback)
df["vol_z"] = rolling_zscore(df["volatility"], score_lookback)
```

含义：

```text
z = (当前值 - 最近窗口均值) / 最近窗口标准差
```

解释：

- `z > 0`：高于自己最近均值
- `z < 0`：低于自己最近均值
- 绝对值越大，说明偏离自己历史越明显

为什么适合这 5 个：

- 它们本身是连续数值型特征
- 用 Z-score 可以保留“偏离程度”

## 5.2 后 5 个因子：滚动排名

当前代码：

```python
df["bb_position_rank"] = rolling_rank(df["bb_position"], score_lookback)
df["obv_trend_rank"] = rolling_rank(df["obv_trend"], score_lookback)
df["volume_ratio_rank"] = rolling_rank(df["volume_ratio"], score_lookback)
df["price_position_rank"] = rolling_rank(df["price_position"], score_lookback)
df["drawdown_rank"] = rolling_rank(df["drawdown"], score_lookback)
```

含义：

- 把当前值放进最近一段历史里做百分位排名
- 输出在 `0~1`

解释：

- 接近 `1`：最近窗口里偏高
- 接近 `0`：最近窗口里偏低

为什么适合这 5 个：

- 这些变量通常更适合用相对排序理解
- 用排名法对异常值更稳健

---

## 6. 因子之间是怎么联系起来的

可以按功能分组：

### 6.1 趋势/动量组

- 短期动量
- 长期动量
- MACD

这组回答的是：

- 价格是不是在涨
- 趋势有没有延续
- 动能是不是在增强

### 6.2 强弱/位置组

- RSI
- 布林带位置
- 价格位置

这组回答的是：

- 价格处于强势还是弱势
- 当前站位在带宽和区间中处于什么水平

### 6.3 量能确认组

- OBV 趋势
- 成交量比

这组回答的是：

- 量能有没有配合
- 当前异动是不是有成交支持

### 6.4 风险惩罚组

- 波动率
- 回撤

这组回答的是：

- 当前环境是不是太乱
- 价格虽然涨，但是不是伴随高风险

这 4 组一起，形成了“涨不涨、强不强、量配不配、风险大不大”的完整判断。

---

## 7. 当前实现里的几个重要细节

### 7.1 因子不会直接交易

代码不会说“短期动量大于某值就买”。  
真正的交易决策是：

```text
因子 -> 综合分 -> 分位数 -> 仓位 -> 再叠加过滤条件 -> 信号
```

### 7.2 前期数据会有空值

因为滚动计算需要窗口长度：

- `rolling_zscore` 需要完整窗口
- `rolling_rank` 允许更早开始，但也依赖最少窗口数据

因此：

- 序列前段很多因子会先出现 `NaN`
- 最后 `factor_score` 会对 `NaN` 做 `fillna(0.0)`

### 7.3 相同基础指标可能进入多个环节

例如 RSI：

- 一方面进入 `rsi_z`
- 一方面进入 `rsi_ok`

这不是重复，而是“同一信息从不同角度使用”：

- 因子层回答“有多强”
- 过滤层回答“是否处于允许交易的区间”

---

## 8. 本文档和下一份文档的分工

这份 `factor.md` 主要回答：

- 每个因子是什么
- 它从哪里来
- 它为什么有效
- 因子之间是什么关系

下一份 `strategy-factor.md` 主要回答：

- 这些因子如何合成 `factor_score`
- 因子分数如何变成仓位和买卖信号
- 贝叶斯/随机/遗传到底在优化什么参数
- 侧边栏技术参数分别怎么影响策略

