# 策略诊断实验 - 任务分解计划

## 📋 项目概述
对现有量化交易策略进行全面诊断，找出表现不佳的根本原因，为后续优化提供数据支持。

**目标**：
- 识别当前策略的核心问题
- 评估各个因子的有效性
- 找出最优参数范围
- 建立改进基线

**时间安排**：2-3 天  
**参与人数**：3-5 人  
**技能要求**：Python、Pandas、基础统计知识

---

## 🎯 任务列表

### Task 1: 数据质量检查与基础分析 ⭐
**负责人**：_________  
**优先级**：🔴 High  
**预计时长**：3-4 小时  
**依赖**：无  

#### 工作内容
1. **数据完整性检查**
   - 检查 `aapl_daily.csv` 和 `tsla_daily.csv` 的缺失值
   - 统计数据时间跨度和记录数
   - 检查是否有异常值（如价格为负、成交量为 0）

2. **市场状态标注**
   - 按年份统计收益率和波动率
   - 识别牛市/熊市/震荡市场区间
   - 计算关键统计指标：
     - 年化收益率
     - 年化波动率
     - 最大回撤
     - Calmar 比率

3. **可视化**
   - 绘制长期价格走势图
   - 标注不同市场状态
   - 收益分布直方图

#### 交付物
- `task1_data_quality_report.ipynb` - Jupyter Notebook
- `task1_market_states.csv` - 市场状态标注文件
- `figures/task1_*.png` - 可视化图表

#### 代码模板
```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. 数据加载
df = pd.read_csv('data/aapl_daily.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

# 2. 缺失值检查
print("缺失值统计：")
print(df.isnull().sum())

# 3. 时间跨度
print(f"数据时间范围：{df['date'].min()} 到 {df['date'].max()}")
print(f"总记录数：{len(df)}")

# 4. 计算年化指标
df['daily_return'] = df['close'].pct_change()
annual_return = df['daily_return'].mean() * 252
annual_vol = df['daily_return'].std() * np.sqrt(252)

# 5. 市场状态识别
df['year'] = df['date'].dt.year
yearly_stats = df.groupby('year').agg({
    'close': lambda x: (x.iloc[-1] / x.iloc[0] - 1),  # 年度收益
    'daily_return': 'std'  # 波动率
})
```

---

### Task 2: 技术指标有效性分析 ⭐⭐
**负责人**：_________  
**优先级**：🔴 High  
**预计时长**：4-5 小时  
**依赖**：Task 1（数据清洗）

#### 工作内容
1. **计算所有技术指标**
   - RSI (14, 21, 28 周期)
   - MACD (12/26/9)
   - EMA (快线 20, 慢线 60)
   - ATR (14)
   - ADX (14)

2. **因子有效性测试 - IC 分析**
   - 计算每个指标与未来收益的相关性（IC - Information Coefficient）
   - 测试不同预测窗口（1天、3天、5天、10天）
   - 计算 IC 的稳定性（IC_IR）

3. **因子单独回测**
   - 每个指标单独构建简单策略
   - 对比各指标的表现
   - 找出最有效的 Top 3 指标

4. **因子相关性分析**
   - 计算指标之间的相关系数矩阵
   - 识别冗余因子
   - 建议保留的独立因子组合

#### 交付物
- `task2_factor_analysis.ipynb`
- `task2_ic_values.csv` - IC 值统计表
- `task2_correlation_matrix.png` - 相关性热图
- `task2_factor_performance.csv` - 单因子策略表现

#### 代码模板
```python
# IC 计算
def calculate_ic(factor, forward_return, method='pearson'):
    """计算信息系数"""
    return factor.corr(forward_return, method=method)

# 测试不同预测窗口
forward_windows = [1, 3, 5, 10]
ic_results = {}

for window in forward_windows:
    df[f'forward_ret_{window}d'] = df['close'].pct_change(window).shift(-window)
    
    ic_results[f'{window}d'] = {
        'rsi': calculate_ic(df['rsi'], df[f'forward_ret_{window}d']),
        'macd': calculate_ic(df['macd'], df[f'forward_ret_{window}d']),
        'histogram': calculate_ic(df['histogram'], df[f'forward_ret_{window}d']),
        # ... 其他指标
    }

# 转换为 DataFrame
ic_df = pd.DataFrame(ic_results).T
print("\n信息系数（IC）统计：")
print(ic_df)
print(f"\n平均 IC：\n{ic_df.mean()}")
```

---

### Task 3: 简化策略对比实验 ⭐⭐
**负责人**：_________  
**优先级**：🟡 Medium  
**预计时长**：4-5 小时  
**依赖**：Task 2（指标计算）

#### 工作内容
1. **实现 5 个基准策略**
   - **S1_BuyHold**：买入并持有
   - **S2_MACD_Only**：仅使用 MACD 交叉
   - **S3_RSI_Only**：仅使用 RSI 超买超卖
   - **S4_Trend_Only**：仅使用 EMA 趋势过滤
   - **S5_Original**：当前复杂策略（5 个条件）

2. **统一回测框架**
   - 相同的时间区间
   - 相同的交易成本假设（0.1% 双边）
   - 记录详细交易日志

3. **性能对比**
   - 计算所有策略的：
     - 累计收益
     - 夏普比率
     - 最大回撤
     - 胜率
     - 平均持仓天数
     - 年化交易次数

4. **分市场状态分析**
   - 牛市表现
   - 熊市表现
   - 震荡市表现

#### 交付物
- `task3_simple_strategies.py` - 策略实现代码
- `task3_backtest_results.csv` - 回测结果汇总
- `task3_equity_curves.png` - 权益曲线对比图
- `task3_performance_report.md` - 分析报告

#### 代码模板
```python
class Strategy:
    def __init__(self, name):
        self.name = name
        self.trades = []
    
    def generate_signals(self, df):
        """生成交易信号"""
        raise NotImplementedError
    
    def backtest(self, df, cost=0.001):
        """回测函数"""
        df = df.copy()
        df['signal'] = self.generate_signals(df)
        df['position'] = df['signal'].fillna(0)
        
        # 计算收益
        df['strategy_return'] = df['position'].shift(1) * df['close'].pct_change()
        df['strategy_return'] -= np.abs(df['position'].diff()) * cost  # 交易成本
        
        df['equity'] = (1 + df['strategy_return']).cumprod()
        
        return df

class MACD_Strategy(Strategy):
    def generate_signals(self, df):
        """MACD 金叉死叉"""
        buy = (df['macd'] > df['signal']) & (df['macd'].shift(1) <= df['signal'].shift(1))
        sell = (df['macd'] < df['signal']) & (df['macd'].shift(1) >= df['signal'].shift(1))
        
        signals = pd.Series(0, index=df.index)
        signals[buy] = 1
        signals[sell] = -1
        
        return signals.replace(0, np.nan).ffill().fillna(0)

# 对比所有策略
strategies = [
    BuyHold_Strategy('S1_BuyHold'),
    MACD_Strategy('S2_MACD_Only'),
    RSI_Strategy('S3_RSI_Only'),
    Trend_Strategy('S4_Trend_Only'),
    Original_Strategy('S5_Original')
]

results = []
for strategy in strategies:
    result_df = strategy.backtest(df)
    metrics = calculate_metrics(result_df)
    results.append({
        'strategy': strategy.name,
        **metrics
    })

comparison = pd.DataFrame(results)
print(comparison)
```

---

### Task 4: 参数敏感性分析 ⭐⭐⭐
**负责人**：_________  
**优先级**：🟡 Medium  
**预计时长**：5-6 小时  
**依赖**：Task 3（策略实现）

#### 工作内容
1. **关键参数识别**
   - 从原策略中提取所有参数（约 15 个）
   - 按类别分组：趋势、动量、风控等

2. **单参数扫描**
   - 固定其他参数，逐个测试每个参数的影响
   - 参数范围：
     - `entry_threshold`: -2.0 到 2.0，步长 0.2
     - `exit_threshold`: -2.0 到 1.0，步长 0.2
     - `adx_threshold`: 10 到 40，步长 5
     - `stop_loss_mult`: 0 到 5，步长 0.5
     - `take_profit_mult`: 0 到 8，步长 1

3. **绘制敏感性曲线**
   - X 轴：参数值
   - Y 轴：夏普比率 / 总收益
   - 找出最优参数区间

4. **参数交互分析**
   - 测试 `entry_threshold` vs `exit_threshold` 的组合
   - 绘制 2D 热图

#### 交付物
- `task4_parameter_scan.ipynb`
- `task4_sensitivity_curves.png` - 敏感性曲线图集
- `task4_optimal_params.json` - 最优参数建议
- `task4_interaction_heatmap.png` - 参数交互热图

#### 代码模板
```python
def parameter_scan(df, param_name, param_range, base_params):
    """单参数扫描"""
    results = []
    
    for value in param_range:
        params = base_params.copy()
        params[param_name] = value
        
        # 运行回测
        strategy = Original_Strategy(**params)
        result_df = strategy.backtest(df)
        
        metrics = calculate_metrics(result_df)
        results.append({
            'param_value': value,
            'sharpe': metrics['sharpe'],
            'total_return': metrics['total_return'],
            'max_drawdown': metrics['max_drawdown']
        })
    
    return pd.DataFrame(results)

# 扫描所有参数
base_params = {
    'entry_threshold': 0.5,
    'exit_threshold': -0.5,
    'adx_threshold': 20,
    # ... 其他默认参数
}

param_ranges = {
    'entry_threshold': np.arange(-2.0, 2.1, 0.2),
    'exit_threshold': np.arange(-2.0, 1.1, 0.2),
    'adx_threshold': range(10, 41, 5),
    # ...
}

sensitivity_results = {}
for param_name, param_range in param_ranges.items():
    print(f"正在扫描参数: {param_name}")
    sensitivity_results[param_name] = parameter_scan(
        df, param_name, param_range, base_params
    )

# 绘制曲线
fig, axes = plt.subplots(2, 3, figsize=(15, 10))
for idx, (param_name, result_df) in enumerate(sensitivity_results.items()):
    ax = axes.flatten()[idx]
    ax.plot(result_df['param_value'], result_df['sharpe'], 'o-')
    ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
    ax.set_xlabel(param_name)
    ax.set_ylabel('Sharpe Ratio')
    ax.grid(True, alpha=0.3)
```

---

### Task 5: 交易行为分析 ⭐
**负责人**：_________  
**优先级**：🟢 Low  
**预计时长**：3-4 小时  
**依赖**：Task 3（策略回测）

#### 工作内容
1. **交易统计分析**
   - 总交易次数
   - 平均持仓天数
   - 胜率（盈利交易占比）
   - 盈亏比（平均盈利 / 平均亏损）

2. **入场/出场原因统计**
   - 修改代码记录每笔交易的触发条件
   - 统计：
     - 哪个条件最常阻止入场？
     - 哪个条件最常触发出场？
     - 止损 vs 止盈 vs 信号出场的占比

3. **时间特征分析**
   - 按月份统计策略表现（季节性）
   - 按星期统计（日内效应）
   - 按年份统计（长期趋势）

4. **失败案例分析**
   - 找出最大的 10 笔亏损交易
   - 分析这些交易的共同特征
   - 提出改进建议

#### 交付物
- `task5_trade_analysis.ipynb`
- `task5_trade_log.csv` - 详细交易日志
- `task5_entry_exit_stats.json` - 入场出场统计
- `task5_worst_trades.md` - 失败案例分析报告

#### 代码模板
```python
def analyze_trades(df):
    """详细交易分析"""
    trades = []
    position = 0
    entry_price = None
    entry_date = None
    entry_reason = None
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # 入场逻辑
        if position == 0 and row['buy_signal']:
            position = 1
            entry_price = row['close']
            entry_date = row['date']
            entry_reason = get_entry_reason(row)
        
        # 出场逻辑
        elif position == 1 and row['sell_signal']:
            exit_price = row['close']
            exit_date = row['date']
            exit_reason = get_exit_reason(row)
            
            pnl = (exit_price / entry_price - 1) * 100
            holding_days = (exit_date - entry_date).days
            
            trades.append({
                'entry_date': entry_date,
                'entry_price': entry_price,
                'entry_reason': entry_reason,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'pnl_pct': pnl,
                'holding_days': holding_days
            })
            
            position = 0
    
    trade_df = pd.DataFrame(trades)
    
    # 统计分析
    stats = {
        'total_trades': len(trade_df),
        'win_rate': (trade_df['pnl_pct'] > 0).mean(),
        'avg_pnl': trade_df['pnl_pct'].mean(),
        'avg_holding_days': trade_df['holding_days'].mean(),
        'profit_factor': trade_df[trade_df['pnl_pct'] > 0]['pnl_pct'].sum() / 
                        abs(trade_df[trade_df['pnl_pct'] < 0]['pnl_pct'].sum())
    }
    
    return trade_df, stats

# 入场/出场原因统计
entry_reasons = trade_df['entry_reason'].value_counts()
exit_reasons = trade_df['exit_reason'].value_counts()

print("入场原因统计：")
print(entry_reasons)
print("\n出场原因统计：")
print(exit_reasons)
```

---

### Task 6: 整合报告与可视化 Dashboard ⭐⭐
**负责人**：_________（建议由项目负责人完成）  
**优先级**：🔴 High  
**预计时长**：4-5 小时  
**依赖**：所有前置任务

#### 工作内容
1. **收集所有任务结果**
   - 汇总各任务的 CSV、JSON 输出
   - 整理所有图表

2. **生成综合报告**
   - 执行摘要（1 页）
   - 数据质量报告（Task 1）
   - 因子有效性报告（Task 2）
   - 策略对比报告（Task 3）
   - 参数优化建议（Task 4）
   - 交易行为洞察（Task 5）
   - 改进建议清单

3. **创建交互式 Dashboard**
   - 使用 Streamlit 创建可视化界面
   - 集成所有分析结果
   - 支持参数调整和实时回测

4. **准备演示材料**
   - PPT（10-15 页）
   - 核心发现和建议
   - 下一步行动计划

#### 交付物
- `DIAGNOSIS_REPORT.md` - 完整诊断报告（15-20 页）
- `diagnosis_dashboard.py` - Streamlit Dashboard
- `DIAGNOSIS_PRESENTATION.pdf` - 演示文稿
- `IMPROVEMENT_ROADMAP.md` - 改进路线图

#### 报告结构模板
```markdown
# 策略诊断综合报告

## 执行摘要
- 核心发现 (3-5 条)
- 主要问题
- 关键建议

## 1. 数据质量分析
- [Task 1 结果]

## 2. 技术指标有效性
- [Task 2 结果]
- IC 值排名
- 建议保留的指标

## 3. 策略简化实验
- [Task 3 结果]
- 性能对比表格
- 权益曲线对比

## 4. 参数优化
- [Task 4 结果]
- 敏感性分析
- 推荐参数组合

## 5. 交易行为洞察
- [Task 5 结果]
- 问题识别
- 改进方向

## 6. 总结与建议
- 短期优化（1-2 周）
- 中期改进（1 月）
- 长期规划（3 月）
```

---

## 📊 任务依赖关系图

```
Task 1 (数据清洗)
    ├── Task 2 (因子分析)
    │       └── Task 3 (策略对比)
    │               ├── Task 4 (参数扫描)
    │               └── Task 5 (交易分析)
    └── Task 6 (整合报告) ← 依赖所有任务
```

---

## 🛠️ 环境准备

### 统一依赖安装
```bash
pip install pandas numpy matplotlib seaborn plotly jupyter
pip install scikit-learn scipy statsmodels
```

### 文件夹结构
```
stratagy/
├── diagnosis/
│   ├── notebooks/          # 各任务的 Jupyter Notebooks
│   │   ├── task1_*.ipynb
│   │   ├── task2_*.ipynb
│   │   └── ...
│   ├── results/            # 输出结果
│   │   ├── task1_*.csv
│   │   ├── task2_*.csv
│   │   └── ...
│   ├── figures/            # 图表
│   │   ├── task1_*.png
│   │   └── ...
│   └── reports/            # 报告文档
│       ├── DIAGNOSIS_REPORT.md
│       └── ...
├── data/                   # 原始数据
├── app.py                  # 原始应用
└── utils.py               # 共享工具函数
```

---

## 📝 协作规范

### Git 工作流
1. 每个任务创建独立分支：`task1-data-quality`、`task2-factor-analysis` 等
2. 完成后提交 Pull Request
3. Code Review 后合并到 `diagnosis` 分支
4. 最终合并到 `main`

### 命名规范
- 文件名：`task{n}_{description}.{ext}`
- 变量名：小写下划线（`snake_case`）
- 函数名：小写下划线（`snake_case`）
- 类名：大驼峰（`PascalCase`）

### 代码注释
- 每个函数必须有 docstring
- 关键计算步骤添加注释
- 复杂逻辑提供示例

### 提交信息格式
```
[Task{n}] 简短描述

详细说明：
- 完成了什么
- 发现了什么问题
- 下一步建议
```

---

## 🎯 成功标准

### Task 1
- ✅ 数据质量报告完整
- ✅ 市场状态标注准确
- ✅ 至少 3 张可视化图表

### Task 2
- ✅ IC 值计算正确（多个预测窗口）
- ✅ 相关性矩阵清晰
- ✅ 单因子回测完成
- ✅ 给出 Top 3 有效因子

### Task 3
- ✅ 5 个基准策略全部实现
- ✅ 性能对比表完整
- ✅ 权益曲线可视化
- ✅ 分市场状态分析

### Task 4
- ✅ 至少扫描 5 个关键参数
- ✅ 敏感性曲线清晰
- ✅ 给出最优参数区间
- ✅ 参数交互热图

### Task 5
- ✅ 交易日志详细
- ✅ 入场/出场原因统计
- ✅ 失败案例分析深入
- ✅ 给出改进建议

### Task 6
- ✅ 综合报告结构完整（15+ 页）
- ✅ Dashboard 可运行
- ✅ 演示材料专业
- ✅ 改进路线图清晰

---

## 📅 时间线（建议）

### Day 1
- 上午：Task 1（数据分析）
- 下午：Task 2（因子分析）开始

### Day 2
- 上午：Task 2 完成，Task 3（策略对比）开始
- 下午：Task 3 继续，Task 4（参数扫描）开始

### Day 3
- 上午：Task 4、Task 5 并行
- 下午：Task 6（整合报告）

---

## 🔗 共享资源

### 工具函数库 (`utils.py`)
```python
# 共享的工具函数，所有任务可以使用

def calculate_sharpe_ratio(returns, rf_rate=0.0, periods=252):
    """计算夏普比率"""
    excess_return = returns - rf_rate / periods
    return np.sqrt(periods) * excess_return.mean() / excess_return.std()

def calculate_max_drawdown(equity_curve):
    """计算最大回撤"""
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max
    return drawdown.min()

def calculate_calmar_ratio(returns, max_dd):
    """计算 Calmar 比率"""
    annual_return = returns.mean() * 252
    return annual_return / abs(max_dd)

# 更多共享函数...
```

### 数据加载函数
```python
def load_data(symbol='aapl'):
    """标准化数据加载"""
    df = pd.read_csv(f'data/{symbol}_daily.csv')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df
```

---

## 💬 沟通渠道

- **每日站会**：每天上午 10:00，同步进度和问题
- **问题讨论**：使用 GitHub Issues 或项目群聊
- **代码审查**：完成后在 PR 中相互审查
- **最终汇报**：Day 3 下午 16:00 集体演示

---

## 📚 参考资料

- 原项目文档：`PROJECT_LOG.md`、`STRATEGY_ANALYSIS.md`
- 量化回测：[Quantopian Lectures](https://www.quantopian.com/lectures)
- 因子分析：[Alpha101 Factors](https://arxiv.org/abs/1601.00991)
- Python 金融分析：[Python for Finance](https://github.com/yhilpisch/py4fi2nd)

---

**最后更新**：2026-01-22  
**项目负责人**：_________  
**联系方式**：_________

---

## ✅ 检查清单

开始前确认：
- [ ] 所有人都安装了必要的 Python 包
- [ ] 每个人都能访问数据文件
- [ ] 文件夹结构已创建
- [ ] Git 仓库已配置
- [ ] 理解了任务目标和交付物

完成后确认：
- [ ] 所有代码可以运行
- [ ] 所有图表清晰可读
- [ ] 报告格式统一
- [ ] 结论有数据支撑
- [ ] 提供了改进建议
