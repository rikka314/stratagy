# 数据分析师工作任务书

## 👤 角色定位
你是一位**资深数据分析师**，擅长金融数据分析、统计建模和可视化。现在加入一个量化交易策略诊断项目。

## 📋 项目背景
当前的量化交易策略表现不佳，甚至不如简单的"买入并持有"。我们需要通过数据分析找出问题根源。

你负责的是**数据层面和因子层面**的诊断工作。

## 🎯 你的任务

你需要完成 **3 个任务**：
- **Task 1**: 数据质量检查与基础分析（3-4 小时）
- **Task 2**: 技术指标有效性分析（4-5 小时）
- **Task 5**: 交易行为分析（3-4 小时）

**截止时间**：1 周内完成  
**工作模式**：并行开展（Task 1 完成后，Task 2 和 Task 5 可同时进行）

---

## 📊 Task 1: 数据质量检查与基础分析

### 目标
建立数据基线，了解市场特征，为后续分析提供基础。

### 具体工作

#### 1.1 数据完整性检查
- [ ] 加载 `data/aapl_daily.csv`（约 9871 行，1984-2026）
- [ ] 检查缺失值、异常值（负价格、零成交量等）
- [ ] 检查重复日期
- [ ] 生成数据质量报告

#### 1.2 市场状态识别
- [ ] 计算年度收益率、波动率、夏普比率
- [ ] 按年份标注市场状态（牛市/熊市/震荡市）
  - 牛市：年度收益 > 15% 且夏普 > 0.5
  - 熊市：年度收益 < -5%
  - 震荡：其他
- [ ] 统计各市场状态的分布

#### 1.3 基础统计指标
计算 Buy & Hold 策略的表现：
- [ ] 总收益率
- [ ] 年化收益率
- [ ] 年化波动率
- [ ] 最大回撤
- [ ] 夏普比率
- [ ] Calmar 比率

#### 1.4 可视化（至少 3 张图）
- [ ] 长期价格走势图 + 累计收益曲线
- [ ] 年度收益柱状图（标注牛熊市）
- [ ] 收益率分布直方图 + Q-Q 图

### 交付物
1. `task1_data_quality_report.csv` - 数据质量统计
2. `task1_market_states.csv` - 各年份市场状态标注
3. `task1_yearly_stats.csv` - 年度统计指标
4. `task1_*.png` - 至少 3 张图表
5. **分析报告**（1-2 页）：
   - 数据质量结论
   - 市场特征总结
   - 对后续分析的建议

### 工具提示
```python
from utils import load_data, calculate_max_drawdown, save_results_to_csv

# 加载数据
df = load_data('aapl', data_dir='data')

# 检查质量
print(df.isnull().sum())
print(df.describe())

# 计算指标
df['daily_return'] = df['close'].pct_change()
annual_return = df['daily_return'].mean() * 252
annual_vol = df['daily_return'].std() * np.sqrt(252)
```

---

## 🔬 Task 2: 技术指标有效性分析

### 目标
评估各个技术指标的预测能力，找出真正有效的因子。

### 具体工作

#### 2.1 计算所有技术指标
使用 `utils.py` 中的函数计算：
- [ ] RSI (14, 21, 28 周期)
- [ ] MACD (12/26/9)
- [ ] EMA (快线 20, 慢线 60, 还有 10, 50, 200)
- [ ] ATR (14)
- [ ] ADX (14)
- [ ] 短期/中期动量 (5, 10, 20 天)
- [ ] 波动率 (20 天)

```python
from utils import add_all_indicators
df = add_all_indicators(df)
```

#### 2.2 因子有效性测试 - IC 分析 ⭐ 核心
计算每个指标与未来收益的相关性（Information Coefficient）：

- [ ] 测试不同预测窗口（1天、3天、5天、10天）
- [ ] 对每个指标计算 IC 值
- [ ] 计算 IC 的稳定性（IC_IR = IC_mean / IC_std）
- [ ] 找出 IC 绝对值 > 0.05 的有效因子

```python
from utils import calculate_ic

# 计算未来收益
df['forward_ret_1d'] = df['close'].pct_change(1).shift(-1)
df['forward_ret_5d'] = df['close'].pct_change(5).shift(-5)

# 计算 IC
ic_rsi_1d = calculate_ic(df['rsi'], df['forward_ret_1d'])
ic_rsi_5d = calculate_ic(df['rsi'], df['forward_ret_5d'])
```

#### 2.3 单因子回测
为每个指标构建简单策略并回测：
- [ ] RSI 策略：< 30 买入，> 70 卖出
- [ ] MACD 策略：金叉买入，死叉卖出
- [ ] 趋势策略：价格 > EMA(50) 持有
- [ ] 比较各单因子策略的夏普比率

#### 2.4 因子相关性分析
- [ ] 计算所有指标之间的相关系数矩阵
- [ ] 绘制热图
- [ ] 识别高度相关的冗余因子（相关性 > 0.7）
- [ ] 建议保留的独立因子组合

### 交付物
1. `task2_ic_values.csv` - IC 值统计表（指标×预测窗口）
2. `task2_factor_performance.csv` - 单因子策略表现对比
3. `task2_correlation_matrix.png` - 相关性热图
4. `task2_ic_analysis.png` - IC 值可视化
5. **分析报告**（2-3 页）：
   - 哪些因子有效？（Top 3-5）
   - 哪些因子无效或冗余？
   - 建议使用的因子组合
   - 对原策略因子选择的评价

### 关键问题
请在报告中回答：
1. 原策略使用的因子（RSI, MACD, 动量等）是否真的有效？
2. 多个动量因子是否信息冗余？
3. 最优的预测窗口是多少天？
4. 应该保留哪 2-3 个核心因子？

---

## 📈 Task 5: 交易行为分析

### 目标
分析原策略的交易行为，找出具体的问题点。

### 具体工作

#### 5.1 交易统计分析
基于原策略的回测结果：
- [ ] 总交易次数
- [ ] 平均持仓天数
- [ ] 胜率（盈利交易占比）
- [ ] 盈亏比（平均盈利 / 平均亏损）
- [ ] 最大单笔盈利/亏损
- [ ] 连续盈利/亏损次数

#### 5.2 入场/出场原因统计 ⭐ 核心
修改回测代码，记录每笔交易的触发条件：
- [ ] 统计哪个条件最常阻止入场？
  - 趋势过滤（EMA）？
  - 强度过滤（ADX）？
  - RSI 区间？
  - MACD 条件？
  - 因子评分？
- [ ] 统计哪个条件最常触发出场？
  - 因子评分下降？
  - 趋势反转？
  - RSI 超限？
  - MACD 死叉？
  - 止损/止盈？

#### 5.3 时间特征分析
- [ ] 按月份统计策略表现（是否有季节性？）
- [ ] 按年份统计（在牛市/熊市/震荡市的表现）
- [ ] 计算策略在不同市场状态的夏普比率

#### 5.4 失败案例分析
- [ ] 找出最大的 10 笔亏损交易
- [ ] 分析这些交易的共同特征：
  - 发生在什么市场环境？
  - 持仓多久？
  - 是止损出场还是信号出场？
- [ ] 提出改进建议

### 交付物
1. `task5_trade_statistics.csv` - 交易统计汇总
2. `task5_entry_exit_reasons.csv` - 入场出场原因统计
3. `task5_monthly_performance.csv` - 月度表现
4. `task5_worst_trades.csv` - 失败案例清单
5. `task5_*.png` - 相关图表（2-3 张）
6. **分析报告**（2-3 页）：
   - 交易行为的主要问题
   - 哪些条件过于严格导致错过机会？
   - 哪些条件效果不佳？
   - 针对性的改进建议

### 关键问题
请在报告中回答：
1. 策略交易次数是太多还是太少？
2. 5 个入场条件中，哪些是"罪魁祸首"（频繁阻止入场）？
3. 止损是否过于频繁？
4. 在什么市场环境下策略表现最差？

---

## 🛠️ 工具和资源

### 已准备的文件
1. **DIAGNOSIS_TASKS.md** - 任务详细说明（15+ 页）
2. **utils.py** - 共享工具库（30+ 函数）
3. **diagnosis/README.md** - 工作指南
4. **task1_data_quality.ipynb** - Task 1 示例模板

### 常用函数
```python
# 数据加载
from utils import load_data, add_all_indicators
df = load_data('aapl', data_dir='data')
df = add_all_indicators(df)

# 因子分析
from utils import calculate_ic, calculate_ic_ir
ic = calculate_ic(factor, forward_return)

# 性能计算
from utils import calculate_all_metrics
metrics = calculate_all_metrics(returns, equity)

# 可视化
from utils import plot_equity_curves, plot_correlation_matrix
plot_equity_curves({'Strategy': equity})
plot_correlation_matrix(df, columns=['rsi', 'macd', 'adx'])

# 保存结果
from utils import save_results_to_csv
save_results_to_csv(df, 'task1_results.csv')
```

### 文件路径
- 数据：`data/aapl_daily.csv`
- 保存结果：`diagnosis/results/`
- 保存图表：`diagnosis/figures/`
- 工作目录：`diagnosis/notebooks/`

---

## 📅 工作计划建议

### Day 1-2: Task 1
- 2 小时：数据加载和质量检查
- 2 小时：计算统计指标和市场状态
- 1 小时：可视化
- 1 小时：撰写分析报告

### Day 3-4: Task 2
- 2 小时：计算所有技术指标
- 3 小时：IC 分析和单因子回测
- 2 小时：相关性分析
- 1 小时：撰写分析报告

### Day 5-6: Task 5
- 2 小时：交易统计
- 2 小时：入场出场原因分析
- 1 小时：时间特征和失败案例
- 1 小时：撰写分析报告

### Day 7: 整理和汇报
- 整理所有结果
- 准备汇报材料

---

## 📊 汇报要求

### 定期汇报（建议每 2 天）
请提供：
1. **进度更新**：完成了哪些任务
2. **初步发现**：有什么关键发现（3-5 条）
3. **遇到的问题**：需要帮助的地方
4. **下一步计划**：接下来做什么

### 汇报格式（示例）
```
【数据分析师进度汇报 - Day 2】

✅ 已完成：
- Task 1 数据质量检查
- Task 1 市场状态识别

📊 初步发现：
1. 数据质量良好，无缺失值
2. 40 年数据中，牛市 15 年，熊市 8 年，震荡 17 年
3. Buy & Hold 年化收益 12%，夏普 0.65
4. 最大回撤 -52%（2008 年金融危机）

❓ 问题：
- 无

📅 下一步：
- 开始 Task 2 IC 分析
```

---

## 🎯 成功标准

### 最低要求
- ✅ 3 个任务全部完成
- ✅ 所有交付物齐全
- ✅ 每个任务有简短总结（1-2 页）

### 优秀标准
- ⭐ 发现了关键问题（如"某些因子完全无效"）
- ⭐ 提供了数据支持的改进建议
- ⭐ 图表清晰专业
- ⭐ 分析报告有洞察力

---

## 💡 重要提示

1. **优先级**：Task 1 > Task 2 > Task 5
2. **关注重点**：IC 分析是核心，直接决定因子选择
3. **数据说话**：所有结论必须有数据/图表支持
4. **问题导向**：不只是分析，更要找出"为什么策略表现差"

## ❓ 有问题随时联系项目经理

- 不清楚任务？→ 查看 `DIAGNOSIS_TASKS.md`
- 不会写代码？→ 参考 `task1_data_quality.ipynb`
- 函数不会用？→ 查看 `utils.py` 的文档字符串
- 还有疑问？→ 随时汇报

---

**祝工作顺利！期待你的分析洞察！💪**

---
**发布日期**：2026-01-22  
**项目经理**：AI PM  
**截止时间**：1 周内（2026-01-29）
