# Task 3 简化策略对比实验 - 分析报告

## 1. 实验设置概述
- **数据**：`data/aapl_daily.csv`（使用 `utils.load_data` 读取），全样本回测。  
- **指标**：`utils.add_all_indicators`（RSI/MACD/ADX/ATR/EMA 等）。  
- **交易成本**：双边 0.1%（`cost=0.001`）。  
- **策略集合**：
  - S1 Buy&Hold
  - S2 MACD Only（金叉死叉）
  - S3 RSI Only（<30 买入，>70 卖出）
  - S4 Trend Only（价>EMA50）
  - S5 Original（趋势+强度+RSI+MACD+评分，含分档仓位）

> **重要异常**：`aapl_daily.csv` 中存在大量负价格（`close <= 0` 约 6013 行）。为保证 Task 3 指标有效性，本次已生成清洗版数据 `data/aapl_clean_daily.csv`（对 open/high/low/close 取绝对值并重算 high/low 一致性），并基于清洗数据重新回测。以下结论以 **clean 结果** 为准。

---

## 2. 全样本策略表现对比（含交易成本，clean 数据）

| strategy      |   total_return |   annual_return |   sharpe_ratio |   max_drawdown |   num_trades |   avg_holding_days |
|:--------------|---------------:|----------------:|---------------:|---------------:|-------------:|-------------------:|
| S1_BuyHold    |         24.215 |           0.973 |          0.211 |         -0.999 |            1 |             9868.0 |
| S2_MACD_Only  |         -0.934 |           0.033 |          0.088 |         -0.998 |          378 |               13.0 |
| S3_RSI_Only   |         -0.772 |           0.811 |          0.176 |         -0.999 |           31 |              170.0 |
| S4_Trend_Only |          4.825 |           0.090 |          0.303 |         -0.853 |          354 |               14.6 |
| S5_Original   |          0.124 |           0.004 |          0.084 |         -0.156 |          155 |                3.2 |

**关键观察（clean）**：
- **S4 (Trend Only)** 的 Sharpe 最高（≈0.303），整体风险调整收益最好。  
- **S1 (Buy&Hold)** 累计收益最高，但最大回撤接近 -100%，风险极高。  
- **S5 (Original)** 回撤显著更小（≈-0.156），但收益与 Sharpe 偏低，显示“更防御、更保守”。  

---

## 3. 分市场状态表现
市场状态来自 `task1_market_states.csv`（牛市/熊市/震荡市）。

### 3.1 牛市
- **最佳 Sharpe**：S4_Trend_Only（Sharpe≈0.634）  
- **最小回撤**：S5_Original（max_drawdown≈-0.124）  
- 结论：牛市中趋势策略收益质量最佳，复杂策略回撤控制更强。  

### 3.2 熊市
- **最小回撤**：S5_Original（max_drawdown≈-0.066）  
- **Sharpe**：整体为负，熊市难以盈利。  
- 结论：复杂策略仍最抗跌。  

### 3.3 震荡市
- **最佳 Sharpe**：S1_BuyHold（Sharpe≈0.379）  
- **最小回撤**：S5_Original（max_drawdown≈-0.095）  
- 结论：震荡期收益整体不高，复杂策略偏防御。  

---

## 4. 关键问题回答
1. **原策略（S5）的表现是最好的吗？**  
   否。S5 的 Sharpe 较低（≈0.084），整体不如 S4。  

2. **如果不是，差距有多大？**  
   S4 Sharpe≈0.303，S5 Sharpe≈0.084；累计收益 S4≈4.825，S5≈0.124，差距明显。

3. **单指标策略（S2, S3, S4）谁最好？**  
   **S4 Trend Only**（风险调整收益最优）。

4. **简化策略的最优结构是什么？（1 条件？2 条件？3 条件？）**  
   目前结果显示**“单条件（趋势）”最优**。建议下一步验证“趋势 + RSI”作为 2 条件结构。

5. **在熊市中，哪个策略最抗跌？**  
   **S5 Original**（最小回撤）。但收益仍为负。

---

## 5. 结论与建议
- **结论（clean）**：趋势策略（S4）在风险调整收益上领先；原策略（S5）回撤控制最好但收益偏弱。  
- **建议**：
  1) 以趋势为核心，尝试“趋势 + RSI”轻量组合。  
  2) 若目标是抗跌，可保留原策略的防御结构，但需减少过度出场与成本影响。  
  3) 后续参数敏感性分析统一使用清洗后的价格数据。  

---

## 6. 交付物
- `diagnosis/results/task3_backtest_results.csv`（原始数据版）  
- `diagnosis/results/task3_market_state_performance.csv`（原始数据版）  
- `diagnosis/results/task3_backtest_results_clean.csv`（清洗数据版）  
- `diagnosis/results/task3_market_state_performance_clean.csv`（清洗数据版）  

（如需图表版总结，可继续生成权益曲线/指标热图。）
