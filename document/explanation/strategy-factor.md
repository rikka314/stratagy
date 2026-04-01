# 策略与因子链路说明文档

> 适用范围：当前仓库里的主策略实现  
> 相关代码：`core/signals.py`、`core/backtest.py`、`core/optimizer.py`、`ui/sidebar.py`、`core/config.py`

---

## 1. 先给一句话结论

当前项目的主策略是：

**规则型多因子评分策略，不是黑箱机器学习模型。**

它的工作方式是：

1. 算出 10 个因子
2. 按权重合成 `factor_score`
3. 再把分数转换成分位数和仓位
4. 再叠加趋势、强度、RSI、MACD 等过滤条件
5. 最后进入 ATR 止损止盈和回测

所以它既“看因子”，也“看因子评分之后的结果”，而不是只看最后结果。

---

## 2. 整条策略链路

```text
原始行情数据
-> add_indicators() 计算技术指标
-> compute_signals() 计算 10 因子与 factor_score
-> factor_percentile / target_position
-> buy_signal / sell_signal
-> simulate_strategy() 回测持仓、止损止盈、净值曲线
-> optimizer.py 用历史表现搜索更优参数
```

可以按模块理解：

- `core/indicators.py`：把行情变成技术指标
- `core/signals.py`：把技术指标变成因子分数、仓位和信号
- `core/backtest.py`：把信号变成历史回测结果
- `core/optimizer.py`：自动搜索一组更好的参数

---

## 3. 术语对照

| 术语 | 当前项目中的含义 |
|------|------------------|
| 技术指标 | RSI、MACD、EMA、ATR、ADX、布林带、OBV 等中间量 |
| 因子 | 用来给股票当前状态打分的特征 |
| 因子分量 | 某个因子标准化后的值，如 `mom_short_z`、`bb_position_rank` |
| `factor_score` | 10 个因子分量按权重加总后的综合分 |
| `factor_percentile` | 当前综合分在最近窗口历史中的分位数 |
| `target_position` | 策略想要持有的目标仓位 |
| `buy_signal` / `sell_signal` | 目标仓位从 0 切到正值或从正值切回 0 时产生的交易信号 |
| 回测评分 `score` | 优化器用来比较参数组合优劣的历史表现分，不等于 `factor_score` |

最容易混淆的是两个 “score”：

- `factor_score`：单个时间点的综合因子分
- 优化器 `score`：整段历史回测之后的策略表现分

这两个完全不是一回事。

---

## 4. `factor_score` 具体怎么算

当前核心公式在 `core/signals.py` 中：

```python
df["factor_score"] = (
    weight_mom_short * df["mom_short_z"]
    + weight_mom_long * df["mom_long_z"]
    + weight_macd * df["macd_z"]
    + weight_rsi * df["rsi_z"]
    - weight_vol * df["vol_z"]
    + weight_bb * (df["bb_position_rank"] - 0.5) * 2
    + weight_obv * (df["obv_trend_rank"] - 0.5) * 2
    + weight_volume * (df["volume_ratio_rank"] - 0.5) * 2
    + weight_price * (df["price_position_rank"] - 0.5) * 2
    - weight_drawdown * (df["drawdown_rank"] - 0.5) * 2
)
```

把它拆开看：

### 4.1 前 5 个因子直接用 Z-score

- `mom_short_z`
- `mom_long_z`
- `macd_z`
- `rsi_z`
- `vol_z`

这些本身已经是中心化后的连续值，所以直接乘权重。

### 4.2 后 5 个因子先把 `0~1` 排名转成 `-1~1`

例如：

```text
(rank - 0.5) * 2
```

含义：

- `rank = 0.5` 时，对应 0 分
- `rank > 0.5` 时，转成正值
- `rank < 0.5` 时，转成负值

这样它们就能和前面的 Z-score 因子一起加总。

### 4.3 为什么有的前面是减号

- 波动率是负向因子：波动越大越扣分
- 回撤是负向因子：回撤越深越扣分

所以综合分不是简单相加，而是“强势特征加分，风险特征扣分”。

### 4.4 缺失值怎么处理

最后有一句：

```python
df["factor_score"] = df["factor_score"].fillna(0.0)
```

这意味着前期窗口不足导致的空值，会在最终综合分上先按 0 处理。

---

## 5. `factor_score` 之后发生了什么

## 5.1 先变成历史分位数

```python
df["factor_percentile"] = rolling_percentile(df["factor_score"], score_lookback).fillna(0.0)
```

含义：

- 不是只看绝对分数有多大
- 还看它在“最近一段历史里处于什么位置”

这一步很重要，因为：

- 不同股票的绝对分数尺度可能不同
- 同一只股票在不同阶段的分数波动也可能不同

所以策略更依赖“相对高低”而不是“绝对数值”。

## 5.2 再变成基础仓位档

当前代码写死为：

- `>= 0.80 -> 1.0`
- `>= 0.65 -> 0.8`
- `>= 0.55 -> 0.6`
- `>= 0.45 -> 0.4`
- `>= 0.35 -> 0.2`
- 其他 `-> 0.0`

这一步产出的是 `score_position`。

### 当前实现注意

`compute_signals()` 虽然接收了：

- `score_mid_pct`
- `score_high_pct`

但当前实际仓位分档仍然使用了代码里写死的 `0.80/0.65/0.55/0.45/0.35`。  
也就是说，这两个参数现在在 UI 中可调、在 `app.py` 中会做校验，但**尚未真正影响仓位分档逻辑**。

## 5.3 再做一次高波动折扣

代码：

```python
volatility_percentile = rolling_percentile(df["volatility"], score_lookback).fillna(0.5)
vol_adjustment = np.where(volatility_percentile > 0.8, 0.7, 1.0)
score_position = score_position * vol_adjustment
```

含义：

- 如果当前波动率已经处在最近历史的高分位
- 即使因子评分很高，也把仓位打 7 折

这一步体现的是：

- 因子评分负责找机会
- 波动折扣负责防止在风险太高时仓位过大

---

## 6. 入场和出场是怎么做的

## 6.1 入场不是只看 `factor_score`

当前默认入场条件有 5 个：

1. `factor_score >= entry_threshold`
2. `ema_fast > ema_slow`
3. `adx >= adx_threshold`
4. `rsi` 落在 `[rsi_lower, rsi_upper]`
5. `macd > signal`

默认 UI 使用的是**计数制入场**：

```python
entry_count >= entry_min_signals
```

也就是至少满足 N 个条件才允许入场。

当前默认预设通常是：

- 均衡：`entry_min_signals = 3`
- 保守：`2`
- 激进：`4`

所以当前策略不是：

- “分数高就买”

而是：

- “分数高是必要信息之一，还要过趋势、强度、RSI、MACD 过滤”

## 6.2 出场也是计数制

出场条件有 4 个：

1. `factor_score <= exit_threshold`
2. `ema_fast < ema_slow`
3. `rsi > rsi_upper` 或 `rsi < rsi_lower`
4. `macd < signal`

只要满足的数量达到 `exit_min_signals`，目标仓位就会被清到 0。

这意味着：

- 入场和出场并不是镜像的
- 出场更像“多重风险信号叠加后的保护”

## 6.3 `buy_signal` / `sell_signal` 的定义

它们不是独立预测器，而是目标仓位变化的结果：

- `buy_signal`：`target_position` 从 `<= 0` 变成 `> 0`
- `sell_signal`：`target_position` 从 `> 0` 变成 `<= 0`

---

## 7. 回测层怎么接住这些信号

`simulate_strategy()` 的职责不是重新判断因子，而是执行：

- 持有多少仓位
- 什么时候平仓
- ATR 止损/止盈是否触发
- 最终净值曲线怎么走

核心逻辑：

1. 如果有 `target_position`，就优先按目标仓位执行动态仓位
2. 如果已经持仓，再检查：
   - `sell_signal`
   - ATR 止损
   - ATR 止盈
3. 用前一天仓位乘当天收益率，得到策略收益

公式上可以近似理解为：

```text
strategy_return[t] = position[t-1] * close_return[t]
strategy_equity = cumulative_product(1 + strategy_return)
```

所以 `factor_score` 决定的是“想持多少”，`backtest` 决定的是“历史上实际怎么走”。

---

## 8. 技术参数到底是怎么工作的

下面按类别解释用户能在侧边栏看到的主要参数。

## 8.1 趋势参数

### `ema_fast`

- 用在 `EMA(close, ema_fast)`
- 越小，越敏感，越容易快速跟随价格
- 越大，越平滑，越不容易被短期波动带偏

### `ema_slow`

- 用在 `EMA(close, ema_slow)`
- 越大，代表更长期的趋势参考线

### `ema_fast < ema_slow` 为什么必须成立

如果快线周期比慢线还大，快线就不再“快”，趋势过滤逻辑会失去语义。

### 趋势过滤怎么工作

```text
trend_ok = ema_fast > ema_slow
```

它不直接改变 `factor_score`，但会改变能不能入场、会不会触发出场。

---

## 8.2 MACD 参数

### `macd_fast`

- 快 EMA 的周期
- 越小，MACD 对价格变化越敏感

### `macd_slow`

- 慢 EMA 的周期
- 越大，代表更慢的基准趋势

### `macd_signal`

- 对 `macd` 再做一次 EMA 平滑的周期
- 越大，信号线越平滑，交叉越少

### 这三个参数影响什么

它们会同时影响：

1. `histogram`，进而影响 MACD 因子分量
2. `macd > signal` 和 `macd < signal`，进而影响入场/出场过滤

所以它们既改因子，也改过滤条件。

---

## 8.3 RSI 参数

### `rsi_period`

- RSI 的计算窗口
- 越小越敏感，越大越平滑

### `rsi_lower`

- 允许交易的下限
- 太低说明偏弱或过冷

### `rsi_upper`

- 允许交易的上限
- 太高说明偏热

### RSI 在策略里的双重角色

- 先进入 `rsi_z`，作为评分因子
- 再进入 `rsi_ok`，作为入场/出场过滤

因此改 RSI 参数，不是只改一个地方，而是会同时改：

- 因子层
- 过滤层

---

## 8.4 ADX 参数

### `adx_period`

- ADX 计算周期
- 越小越敏感，越大越平滑

### `adx_threshold`

- 趋势强度阈值
- 只有 `adx >= threshold` 才认为趋势足够强

它不进入 `factor_score`，但会进入 `strength_ok` 过滤条件。

也就是说：

- ADX 是策略结构中的“门卫”
- 不是综合评分的一个直接加权项

---

## 8.5 ATR 参数

### `atr_period`

- ATR 的平滑窗口
- 既影响波动率因子，也影响止损止盈距离

### `stop_loss_mult`

止损价大致是：

```text
entry_price - stop_loss_mult * entry_atr
```

越大：

- 止损更宽
- 更不容易被震出去
- 但单笔容忍亏损更大

### `take_profit_mult`

止盈价大致是：

```text
entry_price + take_profit_mult * entry_atr
```

越大：

- 目标利润更远
- 更能吃到大趋势
- 但更容易利润回撤后才退出

### ATR 为什么影响两个层次

- `ATR / close` 进入波动率因子
- `ATR * 倍数` 进入交易风控

所以 ATR 同时影响：

- 打分层的风险惩罚
- 回测层的实际退出方式

---

## 8.6 布林带和高级指标参数

### `bb_period`

- 布林带中轨滚动均值的周期
- 越小越灵敏，越大越平滑

### `bb_std`

- 上下轨偏离中轨的标准差倍数
- 越大，带宽越宽

### `indicator_period`

这是一个共享参数，当前同时影响：

- `obv_trend = obv.pct_change(indicator_period)`
- `avg_volume = volume.rolling(indicator_period).mean()`
- `period_high` / `period_low`

也就是说它同时控制：

- OBV 趋势观察窗口
- 成交量均值窗口
- 价格位置的区间窗口

这是一个很重要的“共享时间尺度参数”。

---

## 8.7 因子评分参数

### `momentum_short`

- 短期动量窗口
- 越小，越强调最近几天的爆发性

### `momentum_long`

- 中长期动量窗口
- 越大，越强调趋势延续

### `score_lookback`

- 用于因子标准化和评分分位数的回看窗口
- 越小，标准化更贴近近期环境
- 越大，标准化更稳，但对 regime 切换更迟钝

### `weight_mom_short`

- 短期动量在总分中的权重

### `weight_mom_long`

- 长期动量在总分中的权重

### `weight_macd`

- MACD 因子在总分中的权重

### `weight_rsi`

- RSI 因子在总分中的权重

### `weight_vol`

- 波动率惩罚的权重
- 越大，对高波动环境的惩罚越强

---

## 8.8 Phase 1 新因子权重

这 5 个是后加因子的直接聚合权重：

- `weight_bb`
- `weight_obv`
- `weight_volume`
- `weight_price`
- `weight_drawdown`

它们的作用最直接：

- 数值越大，该因子对 `factor_score` 的影响越大
- 设为 0，相当于暂时关闭这个因子

其中：

- `weight_drawdown` 是负向惩罚权重
- 其余 4 个是正向增强权重

---

## 8.9 入场/出场阈值参数

### `entry_threshold`

- 不是“直接买入阈值”
- 而是“把因子评分算作一个入场条件时所需达到的分数”

在当前默认计数制下，它相当于五个入场条件中的第一项。

### `exit_threshold`

- 当 `factor_score <= exit_threshold` 时，记一个出场信号

### `entry_min_signals`

- 5 个入场条件里至少满足多少个才能开仓

### `exit_min_signals`

- 4 个出场条件里至少满足多少个才清仓

它们控制的不是“分数怎么算”，而是“分数和其他条件如何共同被解释为交易动作”。

---

## 8.10 固定过滤开关

代码里其实还存在这些开关：

- `use_trend_filter`
- `use_strength_filter`
- `use_rsi_filter`
- `use_macd_filter`
- `use_voting_entry`
- `entry_vote_threshold`

但当前 UI 返回的是固定值：

- 四个过滤开关都为 `True`
- `use_voting_entry = False`
- 实际走的是 **计数制入场**，不是投票制

因此当前项目的主路径可以简化理解为：

- 固定启用 4 个过滤器
- 再用计数阈值决定是否入场/出场

---

## 9. 贝叶斯、随机、遗传分别改了什么

一句话：

**三者改的是同一套参数空间，差别只在搜索方法，不在策略结构。**

## 9.1 它们共同优化的参数

当前三种优化器都会搜索：

- `ema_fast`
- `ema_slow`
- `macd_fast`
- `macd_slow`
- `macd_signal`
- `rsi_period`
- `rsi_lower`
- `rsi_upper`
- `adx_period`
- `atr_period`
- `bb_period`
- `bb_std`
- `indicator_period`
- `entry_threshold`
- `exit_threshold`
- `adx_threshold`
- `stop_loss_mult`
- `take_profit_mult`
- `weight_bb`
- `weight_obv`
- `weight_volume`
- `weight_price`
- `weight_drawdown`

总共 23 个。

## 9.2 它们没有优化什么

当前三种优化器**没有**自动搜索：

- `weight_mom_short`
- `weight_mom_long`
- `weight_macd`
- `weight_rsi`
- `weight_vol`
- `entry_min_signals`
- `exit_min_signals`

这些值目前主要由：

- 预设策略
- UI 手动调整

来决定。

## 9.3 “它们是在改因子还是改权重”这个问题怎么回答

更准确的回答是：**两种都改，但层次不同。**

### 直接改聚合权重

这些参数会直接改 `factor_score` 的加权方式：

- `weight_bb`
- `weight_obv`
- `weight_volume`
- `weight_price`
- `weight_drawdown`

### 间接改因子本身

这些参数会先改变技术指标，再影响因子值：

- `macd_fast/slow/signal`
- `rsi_period`
- `atr_period`
- `bb_period`
- `bb_std`
- `indicator_period`

例如：

- 改 `atr_period` 会改变 ATR
- ATR 变了，`volatility = atr / close` 也会变
- `volatility` 变了，波动率因子就变了

### 改的是“因子之后的解释规则”

这些参数不改 `factor_score` 本身，但会改如何把分数变成交易：

- `entry_threshold`
- `exit_threshold`
- `adx_threshold`
- `stop_loss_mult`
- `take_profit_mult`

所以从策略链路角度看，优化器会同时触及：

1. 指标层
2. 因子层
3. 信号解释层
4. 风控层

但它**不会改变当前策略的基本结构**：

- 依然是先算 10 因子
- 依然是加权求综合分
- 依然是过滤后再交易

---

## 10. 三种优化方法的区别

## 10.1 随机搜索

做法：

- 在参数范围里随机抽样
- 每抽一组就跑一次完整回测评分

特点：

- 简单
- 覆盖面广
- 不会利用“前面试过什么”的信息

## 10.2 贝叶斯优化

做法：

- 用 Optuna 根据前面试验结果，推断下一组更值得尝试的参数

特点：

- 更聪明
- 在试验次数有限时通常更高效
- 适合连续参数较多的场景

## 10.3 遗传算法

做法：

- 把一组参数看成一个“个体”
- 先生成种群
- 再做选择、交叉、变异、精英保留

特点：

- 更适合探索复杂组合空间
- 保留多样性
- 比较像“群体进化式搜索”

---

## 11. 三种优化器用什么标准判断“更好”

当前三者的目标函数本质一致：

### 11.1 先算训练分和验证分

```text
train_score = Sharpe + Return - 0.5 * |MaxDrawdown|
val_score   = Sharpe + Return - 0.5 * |MaxDrawdown|
```

### 11.2 再做组合

```text
final_score = 0.4 * train_score
            + 0.6 * val_score
            - 0.3 * |train_score - val_score|
            - regularization_penalty
```

解释：

- 验证集权重更高，说明更重视样本外表现
- 训练和验证差太大，会被罚，防止过拟合
- 离默认参数太远，也会被正则项轻微惩罚

所以优化器追求的不是“训练集最强”，而是“训练和验证都还不错，并且差距别太大”的参数组。

---

## 12. 预设策略和优化器的关系

当前有 3 个主要预设：

- 保守
- 均衡
- 激进

它们的作用有两层：

1. 给用户一个可直接使用的参数组合
2. 给优化器一个热启动起点

也就是说，优化器不是从完全空白开始，而是可以从已有较合理的参数附近继续搜索。

---

## 13. 最后再用一句话串起来

当前主策略的完整逻辑是：

```text
技术指标定义市场状态
-> 因子把这些状态转成可打分特征
-> factor_score 汇总“强度 + 位置 + 量能 - 风险”
-> factor_percentile 把绝对分转成相对分
-> target_position 把相对分转成仓位
-> 过滤器决定是否允许开平仓
-> ATR 风控决定实盘层面的退出
-> 优化器在历史数据上搜索更合适的参数组合
```

所以：

- `factor.md` 解释“因子是什么”
- 本文解释“因子如何变成策略”

