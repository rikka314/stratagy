# 因子与功能字典

> 依据代码整理：`core/indicators.py`、`core/signals.py`、`core/fa_filter.py`、`core/ml_filter.py`、`ui/sidebar.py`、`ui/single_stock.py`、`ui/multi_stock.py`
> 更新时间：2026-05-26
> 说明：本文只记录当前代码中已经存在并被策略链路或 UI 使用的指标、因子、信号和过滤特征，不添加代码中不存在的因子。

## 1. 已有功能清点

| 功能 | 代码位置 | 当前作用 | 主要产出 |
|---|---|---|---|
| 技术指标计算 | `core/indicators.py:add_indicators` | 基于标准行情表生成 RSI、MACD、EMA、ATR、ADX、布林带、OBV、成交量比率、回撤和价格位置 | 指标列写回 `DataFrame` |
| 10 因子评分 | `core/signals.py:compute_signals` | 将动量、MACD、RSI、波动率、布林带、OBV、成交量、价格位置、回撤等标准化特征合成为 `factor_score` | `factor_score`、`factor_percentile` |
| 入场 / 出场信号 | `core/signals.py:compute_signals` | 用因子分数、趋势、强度、RSI、MACD 等条件决定目标仓位和买卖点 | `target_position`、`buy_signal`、`sell_signal`、`entry_count`、`exit_count` |
| FA / FSM 因子提炼 | `core/fa_filter.py` | 在训练集上用 FactorAnalysis 将 10 个标准化因子压缩为单一 FSM 分数 | `fsm_score`，在 FSM 模式下写入 `factor_score` |
| ML 信号过滤 | `core/ml_filter.py` | 只对买入信号抽样，训练 Logistic / LightGBM 判断开仓信号是否保留 | `ml_proba`、`ml_pass`、ML 质量指标 |
| 单股分析页面 | `ui/single_stock.py` | 运行单股策略工作流，展示指标、因子分数、信号、回测、Walk-Forward、ML 质量和 HTML 导出 | 单股结果面板和导出报告 |
| 多股分析页面 | `ui/multi_stock.py` | 对多个股票生成比较图、因子评分横向对比、组合模拟、组合优化和多股 HTML 导出 | 多股比较、组合 KPI、周期收益热力图 |
| 参数入口 | `ui/sidebar.py` | 暴露策略预设、指标窗口、因子权重、入场 / 出场规则、止损止盈等参数 | `params` 字典传给单股 / 多股链路 |

## 2. 输入数据约定

核心策略层默认输入是已经标准化的行情表。必需字段来自 `document/DATA_SCHEMA.md`：

| 字段 | 含义 | 使用位置 |
|---|---|---|
| `date` | 交易日 | 图表、回测、导出、ML 样本日期 |
| `open` | 开盘价 | K 线与价格展示 |
| `high` | 最高价 | ATR、ADX、价格区间位置、K 线 |
| `low` | 最低价 | ATR、ADX、价格区间位置、K 线 |
| `close` | 收盘价 | 大多数指标、收益、回测、因子计算 |
| `volume` | 成交量，统一为“股” | OBV、成交量比率 |

可选字段如 `symbol`、`market`、`currency`、`adjust` 主要用于 UI 展示、路由状态、缓存和导出，不直接参与 10 因子评分。

## 3. 技术指标字典

这些指标由 `core/indicators.py:add_indicators()` 生成，是后续 `compute_signals()`、多股因子图、ML 特征和导出的基础。

| 名称 / 输出列 | 输入字段 | 计算含义 | 方向解释 | 使用位置 | 局限 |
|---|---|---|---|---|---|
| RSI / `rsi` | `close` | 对收盘价涨跌幅做 Wilder 风格 EWMA，得到 0-100 的相对强弱值 | 中间区间通常更健康；代码中 `rsi_ok` 要求 `rsi_lower < rsi < rsi_upper` | 入场过滤、出场过滤、`rsi_z`、ML 特征、单股技术快照 | 阈值依赖市场环境，震荡和趋势行情解释不同 |
| MACD / `macd` | `close` | 快 EMA 减慢 EMA | 越高代表短期均线相对长期更强 | `macd_z`、`macd_above`、入场 / 出场过滤、ML 特征 | 滞后指标，震荡行情容易反复穿越 |
| MACD signal / `signal` | `close` | `macd` 的 EMA 信号线 | `macd > signal` 被视为 MACD 条件通过 | `macd_above`、入场 / 出场过滤、ML 特征 | 信号线本身不是独立收益预测 |
| MACD histogram / `histogram` | `close` | `macd - signal` | 越高表示 MACD 相对信号线越强 | `macd_z` 因子、单股图表 | 对参数 `macd_fast/slow/signal` 敏感 |
| EMA fast / `ema_fast` | `close` | 快速指数移动均线 | `ema_fast > ema_slow` 表示趋势向上 | `trend_ok`、入场 / 出场过滤、ML 的 `ema_spread_pct` | 均线滞后；横盘时假信号多 |
| EMA slow / `ema_slow` | `close` | 慢速指数移动均线 | 与 `ema_fast` 比较判断趋势方向 | `trend_ok`、入场 / 出场过滤、ML 的 `ema_spread_pct` | 参数过长会反应慢，过短会噪声高 |
| ATR / `atr` | `high/low/close` | 真实波幅的 EWMA | 越高表示绝对波动越大 | `volatility = atr / close`、ML `atr_pct`、回测止损止盈参数 | 只衡量波动，不区分上涨或下跌 |
| ADX / `adx` | `high/low/close` | 基于 +DM/-DM 和 TR 的趋势强度指标 | 越高表示趋势强度越强；代码中 `adx >= adx_threshold` 为 `strength_ok` | 入场过滤、ML 特征 | 不表示趋势方向，只表示强度 |
| Bollinger upper / `bb_upper` | `close` | 收盘价滚动均值 + `bb_std` 倍标准差 | 上轨越高代表价格波动区间上沿越远 | 计算 `bb_position`、图表 | 依赖滚动窗口和标准差倍数 |
| Bollinger middle / `bb_middle` | `close` | 收盘价滚动均值 | 中轨是价格相对布林带位置的基准 | 图表、布林带展示 | 非交易信号本身 |
| Bollinger lower / `bb_lower` | `close` | 收盘价滚动均值 - `bb_std` 倍标准差 | 下轨是价格相对布林带位置的下沿 | 计算 `bb_position`、图表 | 极端行情下标准差区间会快速扩大 |
| Bollinger position / `bb_position` | `close/bb_upper/bb_lower` | `(close - bb_lower) / (bb_upper - bb_lower)` | 越高表示价格越靠近布林带上沿；作为正向位置因子 | `bb_position_rank`、ML 特征、多股因子评分 | 靠近上沿可能代表强势，也可能代表短期过热 |
| Bollinger width / `bb_width` | `bb_upper/bb_lower/close` | 布林带宽度占收盘价比例 | 越高表示波动带更宽 | ML 特征 | 当前手工 10 因子评分未直接使用，只进入 ML |
| OBV / `obv` | `close/volume` | 按收盘涨跌方向累计成交量 | 上行代表成交量更多跟随上涨日 | `obv_trend`、图表扩展 | 对成交量异常和复权数据敏感 |
| OBV trend / `obv_trend` | `obv` | `obv.pct_change(indicator_period)` | 越高表示 OBV 在窗口内更强 | `obv_trend_rank` 因子 | 当 OBV 接近 0 或成交量异常时可能不稳定 |
| Volume ratio / `volume_ratio` | `volume` | 当前成交量 / `indicator_period` 滚动均量 | 越高表示成交量相对近期均量放大 | `volume_ratio_rank` 因子、ML 特征 | 放量不一定代表上涨，也可能是下跌放量 |
| Drawdown / `drawdown` | `close` | `close / close.cummax() - 1` | 越接近 0 表示离历史高点越近；越负表示回撤越深 | `drawdown_rank` 因子、ML 特征 | 使用全样本至今高点，不能单独解释买入价值 |
| Price position / `price_position` | `high/low/close` | 收盘价在 `indicator_period` 高低区间中的位置 | 越高表示越靠近近期高点 | `price_position_rank` 因子、ML 特征 | 越高可能是强势，也可能是追高风险 |

## 4. 10 因子评分字典

`core/signals.py` 中的手工评分函数 `_compute_manual_factor_score()` 使用 10 个标准化因子合成 `factor_score`。其中部分因子是 Z-score，部分因子是滚动排名转换到 [-1, 1] 后参与评分。

| 因子名称 | 代码列 / 权重参数 | 输入字段 | 计算含义 | 方向解释 | 使用位置 | 局限 |
|---|---|---|---|---|---|---|
| 短期动量 | `mom_short_z` / `weight_mom_short` | `close` | `ret_short = close.pct_change(momentum_short)` 后做滚动 Z-score | 越高越偏多 | `factor_score`、FA、ML | 短窗口容易受噪声影响 |
| 中期动量 | `mom_long_z` / `weight_mom_long` | `close` | `ret_long = close.pct_change(momentum_long)` 后做滚动 Z-score | 越高越偏多 | `factor_score`、FA、ML | 趋势反转时滞后 |
| MACD 动能 | `macd_z` / `weight_macd` | `histogram` | MACD 柱状图滚动 Z-score | 越高越偏多 | `factor_score`、FA、ML | 震荡市容易频繁变化 |
| RSI 强弱 | `rsi_z` / `weight_rsi` | `rsi` | RSI 滚动 Z-score | 当前评分中越高越加分 | `factor_score`、FA、ML | 高 RSI 也可能代表过热，需结合 `rsi_ok` 区间过滤 |
| 波动率惩罚 | `vol_z` / `weight_vol` | `atr/close` | `volatility = atr / close` 后做滚动 Z-score | 越高在评分中扣分，偏好低波动 | `factor_score`、FA、ML | 低波动不必然带来更好收益，强趋势也可能伴随高波动 |
| 布林带位置 | `bb_position_rank` / `weight_bb` | `bb_position` | 对价格在布林带中的位置做滚动排名，再映射为 [-1, 1] | 越高越加分 | `factor_score`、FA、ML、多股参数微调 | 高位置可能混合“强势”和“超买”两种含义 |
| OBV 趋势 | `obv_trend_rank` / `weight_obv` | `obv_trend` | 对 OBV 变化率做滚动排名，再映射为 [-1, 1] | 越高越加分 | `factor_score`、FA、ML、多股参数微调 | 成交量数据异常会影响结果 |
| 成交量放大 | `volume_ratio_rank` / `weight_volume` | `volume_ratio` | 对成交量比率做滚动排名，再映射为 [-1, 1] | 越高越加分 | `factor_score`、FA、ML、多股参数微调 | 放量方向未区分，需结合价格趋势 |
| 价格区间位置 | `price_position_rank` / `weight_price` | `price_position` | 对价格在近期高低区间的位置做滚动排名，再映射为 [-1, 1] | 越高越加分 | `factor_score`、FA、ML、多股参数微调 | 可能偏向追涨，对回撤反弹不敏感 |
| 回撤惩罚 | `drawdown_rank` / `weight_drawdown` | `drawdown` | 对回撤做滚动排名，再映射为 [-1, 1] 后取负号参与评分 | 当前实现中高 `drawdown_rank` 会扣分，低排名会加分 | `factor_score`、FA、ML、多股参数微调 | 语义需要结合 `drawdown` 为负值理解；深回撤可能是风险，也可能是反弹机会 |

综合评分公式来自代码：

```text
factor_score =
  weight_mom_short * mom_short_z
+ weight_mom_long  * mom_long_z
+ weight_macd      * macd_z
+ weight_rsi       * rsi_z
- weight_vol       * vol_z
+ weight_bb        * (bb_position_rank - 0.5) * 2
+ weight_obv       * (obv_trend_rank - 0.5) * 2
+ weight_volume    * (volume_ratio_rank - 0.5) * 2
+ weight_price     * (price_position_rank - 0.5) * 2
- weight_drawdown  * (drawdown_rank - 0.5) * 2
```

## 5. 信号与仓位字段

这些字段不是单独的“因子”，但直接决定交易建议和回测结果。

| 名称 / 输出列 | 输入字段 | 计算含义 | 方向解释 | 使用位置 | 局限 |
|---|---|---|---|---|---|
| 趋势过滤 / `trend_ok` | `ema_fast/ema_slow` | `ema_fast > ema_slow` | True 表示趋势向上 | 入场计数、严格入场、ML 特征 | 均线滞后，横盘易假突破 |
| 强度过滤 / `strength_ok` | `adx` | `adx >= adx_threshold` | True 表示趋势强度达标 | 入场计数、严格入场、ML 特征 | 不判断方向，只判断强弱 |
| RSI 区间过滤 / `rsi_ok` | `rsi` | `rsi_lower < rsi < rsi_upper` | True 表示未处在过弱或过热区间 | 入场计数、严格入场、ML 特征 | 参数不同会改变“合理区间”的含义 |
| MACD 过滤 / `macd_above` | `macd/signal` | `macd > signal` | True 表示 MACD 处于信号线上方 | 入场计数、出场计数、ML 特征 | 震荡时频繁切换 |
| 入场计数 / `entry_count` | `factor_score/trend_ok/strength_ok/rsi_ok/macd_above` | 统计启用条件中通过的数量 | 越高表示入场条件越充分 | 入场条件、单股结果解释、ML 特征 | 只是条件数量，不代表条件质量相同 |
| 出场计数 / `exit_count` | `factor_score/EMA/RSI/MACD` | 统计出场条件中触发的数量 | 越高表示离场条件越充分 | 出场条件、策略结果 | 阈值低会更频繁离场，阈值高会更迟钝 |
| 因子分位 / `factor_percentile` | `factor_score` | `factor_score` 在 `score_lookback` 窗口内的百分位 | 越高表示相对近期更强 | 仓位分层、图表、ML 特征 | 只与近期窗口比较，跨股票绝对值不可直接等同 |
| 目标仓位 / `target_position` | `factor_percentile`、入场/出场条件、波动率分位 | 将分位映射为 0/0.2/0.4/0.6/0.8/1.0，并在高波动时乘 0.7 | 越高表示策略建议仓位越重 | 回测、多股组合、ML 特征、图表和报告 | 不是实际订单；未考虑真实成交约束 |
| 买入信号 / `buy_signal` | `target_position` | 当前仓位从 0 变为大于 0 | True 表示开仓点 | 图表、ML 样本抽取、交易展示 | 只标记开仓，不表示每次加仓 |
| 卖出信号 / `sell_signal` | `target_position` | 当前仓位从大于 0 变为 0 | True 表示平仓点 | 图表、交易展示 | 不表达减仓到非零仓位 |
| 持仓状态机 / `hold_until_exit` | UI / 研究参数 | 空仓时只看入场，持仓时只看出场，未触发出场则维持至少 `hold_min_position` | 减少因入场条件短暂失效导致的频繁清仓 | 研究配置、单股 workflow | UI 默认路径不一定启用；持仓更久也可能扩大回撤 |

## 6. FA / FSM 特征字典

`core/fa_filter.py` 只使用 `compute_signals()` 已生成的 10 个标准化因子列，不直接读取原始行情。`fit_fa()` 只能在训练集拟合，`transform_fa()` 将同样结构的数据映射为 `fsm_score`。

| 名称 | 输入字段 | 计算含义 | 方向解释 | 使用位置 | 局限 |
|---|---|---|---|---|---|
| FA 输入矩阵 | `FA_SOURCE_COLUMNS` 中 10 列 | 将动量、MACD、RSI、波动率、布林带、OBV、成交量、价格位置、回撤转成统一特征矩阵 | 代码对波动率和回撤做负向处理，使更高的特征均值更偏多 | `fit_fa()`、`transform_fa()` | 依赖上游 `compute_signals()` 已完成标准化 |
| FSM 分数 / `fsm_score` | FA 输入矩阵 | FactorAnalysis 低维潜在因子均值，并用训练集均值 / 标准差标准化 | 通过训练集“正向因子均值”校正方向，越高越偏多 | FSM 模式下作为 `factor_score` | FA 是无监督降维，不保证直接对应收益最大化 |

## 7. ML 过滤特征字典

`core/ml_filter.py` 的 ML 过滤只对 `buy_signal` 行生成样本，不对每个交易日都训练。标签默认看未来 `horizon` 日策略收益是否跑赢 naive；有效超额样本不足时退化为未来策略收益是否为正。

| 特征 | 输入字段 | 计算含义 | 方向解释 | 使用位置 | 局限 |
|---|---|---|---|---|---|
| `factor_score` | 信号表 | 买入日综合评分 | 越高通常越偏多 | ML 训练 / 预测 | 评分本身来自手工或 FSM，非独立数据源 |
| `factor_percentile` | 信号表 | 买入日评分分位 | 越高表示近期相对更强 | ML 训练 / 预测 | 只在本股票本窗口内比较 |
| `target_position` | 信号表 | 买入日目标仓位 | 越高表示策略原始信号更强 | ML 训练 / 预测 | 由规则生成，可能放大规则偏差 |
| `mom_short_z`、`mom_long_z` | 信号表 | 短 / 中期动量标准化值 | 越高越偏多 | ML 训练 / 预测 | 动量反转时失效 |
| `macd_z`、`rsi_z`、`vol_z` | 信号表 | MACD、RSI、波动率标准化值 | MACD/RSI 越高偏多；`vol_z` 越高代表波动越高 | ML 训练 / 预测 | 模型自行学习方向，不能单独解释为买卖建议 |
| `bb_position_rank`、`obv_trend_rank`、`volume_ratio_rank`、`price_position_rank`、`drawdown_rank` | 信号表 | 10 因子评分中的排名类特征 | 排名越高表示该维度近期相对更高 | ML 训练 / 预测 | 不同维度方向不完全一致，模型需学习组合关系 |
| `rsi`、`macd`、`signal`、`adx` | 指标列 | 原始技术指标值 | 作为模型特征，不强行固定方向 | ML 训练 / 预测 | 单独指标容易受行情阶段影响 |
| `atr_pct` | `atr/close` | ATR 占价格比例 | 越高表示相对波动越大 | ML 训练 / 预测 | 高波动可能是机会也可能是风险 |
| `volume_ratio`、`bb_position`、`bb_width`、`price_position`、`drawdown` | 指标列 | 原始形态与位置指标 | 由模型学习方向 | ML 训练 / 预测 | 与排名类特征有重叠信息 |
| `trend_ok`、`strength_ok`、`rsi_ok`、`macd_above` | 信号表布尔列 | 入场过滤条件是否通过 | 1 表示条件通过 | ML 训练 / 预测 | 条件数量少，不代表所有条件等权有效 |
| `entry_count` | 信号表 | 买入日入场条件通过数 | 越高表示规则确认度越高 | ML 训练 / 预测 | 由规则派生，和其他特征相关 |
| `ema_spread_pct` | `(ema_fast - ema_slow) / close` | 快慢 EMA 差距占价格比例 | 越高表示快线相对慢线更强 | ML 训练 / 预测 | 均线差距扩大后也可能接近回调 |
| `ml_proba` | ML 模型输出 | 模型判断买入信号值得保留的概率 | 越高越可能保留整段持仓 | 单股 ML-SM、ML 质量展示 | 样本少时可能退化为常数概率模型 |
| `ml_pass` | `ml_proba` 与阈值 | 是否通过 ML 过滤 | True 表示保留该买入信号对应的持仓块 | `apply_filter()`、单股结果 | 过滤的是整段持仓块，不是逐日调仓 |

## 8. UI 参数与使用位置

| 参数类别 | 参数 / 控件 | 代码位置 | 影响范围 |
|---|---|---|---|
| 策略预设 | `STRATEGY_PRESETS`、`strategy_preset` | `ui/sidebar.py`、`core/config.py` | 快速加载保守 / 默认 / 激进 / 自定义参数 |
| 指标窗口 | `ema_fast`、`ema_slow`、`macd_fast`、`macd_slow`、`macd_signal`、`rsi_period`、`adx_period`、`atr_period`、`bb_period`、`bb_std`、`indicator_period` | `ui/sidebar.py` | 影响 `add_indicators()` 输出 |
| 入场 / 出场规则 | `entry_min_signals`、`exit_min_signals`、`entry_threshold`、`exit_threshold` | `ui/sidebar.py` | 影响 `compute_signals()` 的入场、出场和仓位 |
| 风险参数 | `stop_loss_mult`、`take_profit_mult` | `ui/sidebar.py`、回测 / workflow 消费 | 影响回测止损止盈逻辑 |
| 因子权重 | `weight_mom_short`、`weight_mom_long`、`weight_macd`、`weight_rsi`、`weight_vol`、`weight_bb`、`weight_obv`、`weight_volume`、`weight_price`、`weight_drawdown` | `ui/sidebar.py` | 影响 `factor_score` |
| 单股 Search 微调 | `search_adj_entry_threshold`、`search_adj_exit_threshold`、`search_adj_stop_loss_mult`、`search_adj_take_profit_mult`、`search_adj_weight_mom_short`、`search_adj_weight_mom_long`、`search_adj_weight_macd`、`search_adj_weight_rsi`、`search_adj_weight_bb`、`search_adj_weight_obv` | `ui/single_stock.py` | Search family 生成前覆盖 `params_snapshot` |
| 单股模型选择 | base / search / ML / regime 相关工作流控件 | `ui/single_stock.py` | 选择单股策略路径、展示因子图、信号图、Walk-Forward 和 ML 质量 |
| 多股策略微调 | `multi_adj_entry_threshold`、`multi_adj_exit_threshold`、`multi_adj_stop_loss`、`multi_adj_take_profit`、`multi_adj_weight_bb`、`multi_adj_weight_obv`、`multi_adj_weight_volume`、`multi_adj_weight_price`、`multi_adj_weight_drawdown` | `ui/multi_stock.py` | 多股组合模拟前写回 `params` |
| 组合权重 | `multi_stock_weight_<symbol>` | `ui/multi_stock.py` | 归一化后用于组合日收益加权 |
| 组合参数搜索 | `portfolio_n_trials` | `ui/multi_stock.py` | 调用 `bayesian_optimize_portfolio()` 搜索入场/出场、风险和部分因子权重 |

## 9. 使用位置索引

- 单股主流程：`ui/single_stock.py` 先调用 cached `add_indicators()`，再通过 `run_strategy_pipeline()` 生成策略 artifact；结果区展示 `factor_score` / `factor_percentile`、交易信号、回测、Walk-Forward、ML 质量和 HTML 导出。
- 多股因子横向对比：`ui/multi_stock.py` 调用 `core.visualization.create_factor_score_comparison()`，该函数对每只股票执行 `add_indicators()` + `compute_signals()`，取最新 `factor_score`、`factor_percentile` 和 `target_position` 绘图。
- 多股组合模拟：`ui/multi_stock.py` 调用 `core.portfolio.run_portfolio_simulation()`，对每只股票独立执行 `add_indicators()` + `compute_signals()` + `simulate_strategy()`，再按组合权重合成收益。
- HTML 导出：`ui/single_stock.py` 与 `ui/multi_stock.py` 将图表、策略结果、因子评分和组合结果传给 `ui/export_reports.py` 构建离线报告。

## 10. 总体限制

- 因子字典描述的是当前实现，不代表这些因子具有稳定预测能力。
- 所有因子都基于历史行情和成交量，外部数据源缺失、复权口径变化或成交量异常会影响结果。
- `factor_score` 是手工加权或 FA 转换后的综合分数，不应跨股票、跨市场直接按绝对值比较；更适合在同一股票、同一窗口内结合分位数解释。
- ML 过滤器只对买入信号抽样，样本量不足或标签单一时会返回常数概率模型，不能把训练成功等同于模型有效。
- 多股组合结果来自各股票独立策略收益的日期对齐和权重合成，未覆盖真实交易成本、冲击成本、资金容量和再平衡约束。
