# Task 2 技术指标有效性分析报告（草稿）

## 数据与口径
- 指标基于正价过滤后的 AAPL 日线数据计算（与 Task 1 一致）
- IC 分析：预测窗口 1/3/5/10 日，IC_IR 为 20 日滚动相关均值/波动

## IC 结果摘要
- Top 因子（按 |IC| 最大值排序）：
  - volatility_20: max|IC|=0.213, 有效窗口=1d,3d,5d,10d
  - atr: max|IC|=0.097, 有效窗口=3d,5d,10d
  - ema_10: max|IC|=0.085, 有效窗口=3d,5d,10d
  - ema_20: max|IC|=0.085, 有效窗口=3d,5d,10d
  - ema_50: max|IC|=0.084, 有效窗口=3d,5d,10d
- 低效因子：RSI 系列、MACD/Signal/Histogram、ADX 均未达到 |IC|>0.05

## 单因子回测（简版）
- RSI_30_70: Sharpe=0.328, 年化收益=0.087, 最大回撤=-0.625
- MACD_Cross: Sharpe=0.680, 年化收益=0.261, 最大回撤=-0.716
- Trend_EMA50: Sharpe=0.774, 年化收益=0.342, 最大回撤=-0.610

## 因子相关性与冗余
- EMA 系列高度相关（几乎完全一致）
- RSI 14/21/28 高度相关
- MACD 与 Signal 高度相关
- ATR 与 EMA 系列相关性较高（>0.9）

## 建议保留的独立因子组合（候选）
- 组合 A：volatility_20 + momentum_10 + ema_50
- 组合 B：volatility_20 + momentum_20 + atr（与 EMA 二选一，避免冗余）

## 文件产出
- IC 统计：diagnosis/results/task2_ic_values.csv
- IC 可视化：diagnosis/figures/task2_ic_analysis.png
- 单因子回测：diagnosis/results/task2_factor_performance.csv
- 相关性矩阵：diagnosis/results/task2_correlation_matrix.csv
- 相关性热图：diagnosis/figures/task2_correlation_matrix.png
- 冗余因子清单：diagnosis/results/task2_redundant_factors.csv