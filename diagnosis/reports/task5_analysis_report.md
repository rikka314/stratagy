# Task 5 交易行为分析报告（草稿）

## 5.1 交易统计概览
- 总交易次数：71
- 平均持仓天数：4.75
- 胜率：0.549
- 盈亏比（平均盈利/平均亏损）：1.319
- 最大单笔盈利/亏损：0.124 / -0.071
- 最大连续盈利/亏损：8 / 4

## 5.2 入场/出场原因统计（核心）
- 入场最常阻塞条件（Top 3）：
  - score_percentile_low：2176 次（60.3%）
  - factor_score_entry：2075 次（57.5%）
  - macd_filter：1874 次（51.9%）
- 出场最常触发原因（Top 3）：
  - rsi_breach：29 次（40.8%）
  - score_percentile_low：19 次（26.8%）
  - factor_score_drop：9 次（12.7%）

## 5.3 时间特征
- 月度季节性（按平均月收益 Top/Bottom 3）：
  - 最优月份：12月(0.014), 8月(0.009), 5月(0.004)
  - 最弱月份：2月(-0.003), 4月(-0.005), 9月(-0.008)
- 市场状态表现（按年化夏普排序）：
  - 牛市: Sharpe=0.526, Vol=0.076
  - 震荡市: Sharpe=0.065, Vol=0.055
  - 熊市: Sharpe=-0.614, Vol=0.036

## 5.4 失败案例（最差 10 笔）
- 平均持仓天数：3.00，中位数：2.00
- 市场环境分布：牛市:8, 震荡市:2
- 出场类型分布：signal:6, stop_loss:4

## 主要问题判断
- 入场阻塞主要来自评分分位与评分阈值，说明“打分门槛过高/分位门槛过严”导致错过机会。
- 出场主要由 RSI 超限与评分分位回落触发，显示策略对短期波动较敏感。
- 最差交易多为短持仓且在牛市中出现，说明止损或信号过早反转导致“追涨回撤”。

## 改进建议（方向）
- 放宽分位门槛或降低 entry_threshold，减少被动空仓。
- 优化 RSI 出场条件（例如使用更宽容阈值或加上持仓最小天数）。
- 对止损/止盈进行敏感性测试，避免牛市中过早止损。

## 文件产出
- 交易统计：diagnosis/results/task5_trade_statistics.csv
- 入场/出场原因：diagnosis/results/task5_entry_exit_reasons.csv
- 月度表现：diagnosis/results/task5_monthly_performance.csv
- 年度表现：diagnosis/results/task5_yearly_performance.csv
- 市场状态表现：diagnosis/results/task5_market_state_performance.csv
- 失败案例清单：diagnosis/results/task5_worst_trades.csv