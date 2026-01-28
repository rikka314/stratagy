# 策略开发者工作任务书

## 👤 角色定位
你是一位**资深量化策略开发者**，擅长策略设计、回测优化和参数调优。现在加入一个量化交易策略诊断项目。

## 📋 项目背景
当前的量化交易策略表现不佳（不如买入并持有）。问题可能在于：
1. 策略过于复杂（5 个入场条件）
2. 参数设置不当
3. 固定参数不适应市场变化

你负责的是**策略层面和参数层面**的诊断工作。

## 🎯 你的任务

你需要完成 **2 个任务**：
- **Task 3**: 简化策略对比实验（4-5 小时）
- **Task 4**: 参数敏感性分析（5-6 小时）

**截止时间**：1 周内完成  
**工作模式**：等待 Task 1 完成后开始，Task 3 和 Task 4 可并行

---

## 🧪 Task 3: 简化策略对比实验

### 目标
验证假设：**简单策略是否比复杂策略更好？**

通过对比不同复杂度的策略，找出最佳的策略结构。

### 原策略回顾
当前策略的入场条件（需要**同时满足 5 个**）：
1. 趋势过滤：`ema_fast > ema_slow`
2. 强度过滤：`adx >= adx_threshold`
3. RSI 区间：`rsi_lower < rsi < rsi_upper`
4. MACD 条件：`macd > signal`
5. 因子评分：`factor_score >= entry_threshold`

**问题**：条件太多，是否导致过度保守？

### 具体工作

#### 3.1 实现 5 个基准策略

**S1: Buy & Hold（基准）**
```python
# 始终持有，不做任何交易
position = 1  # 永远持仓
```

**S2: MACD Only（单指标）**
```python
# 只用 MACD 金叉死叉
buy_signal = (macd > signal) & (macd.shift(1) <= signal.shift(1))  # 金叉
sell_signal = (macd < signal) & (macd.shift(1) >= signal.shift(1))  # 死叉
```

**S3: RSI Only（单指标）**
```python
# 只用 RSI 超买超卖
buy_signal = rsi < 30  # 超卖
sell_signal = rsi > 70  # 超买
```

**S4: Trend Only（趋势跟踪）**
```python
# 只用均线趋势
buy_signal = close > ema_50
sell_signal = close < ema_50
```

**S5: Original（原复杂策略）**
```python
# 当前的 5 个条件
filter_ok = (trend_ok & strength_ok & rsi_ok & macd_above & score_ok)
```

#### 3.2 统一回测框架
为确保公平对比：
- [ ] 相同的时间区间（1984-2026）
- [ ] 相同的训练/测试切分（70/30）
- [ ] 相同的交易成本假设（0.1% 双边）
- [ ] 记录详细交易日志

```python
class Strategy:
    def __init__(self, name):
        self.name = name
    
    def generate_signals(self, df):
        """生成买卖信号"""
        raise NotImplementedError
    
    def backtest(self, df, cost=0.001):
        """统一的回测函数"""
        df = df.copy()
        df['signal'] = self.generate_signals(df)
        df['position'] = df['signal'].fillna(method='ffill').fillna(0)
        
        # 计算收益（扣除交易成本）
        df['strategy_return'] = df['position'].shift(1) * df['close'].pct_change()
        df['strategy_return'] -= np.abs(df['position'].diff()) * cost
        
        df['equity'] = (1 + df['strategy_return']).cumprod()
        return df
```

#### 3.3 性能全面对比
计算所有策略的指标：

| 指标 | 说明 | 目标 |
|------|------|------|
| 累计收益 | 总收益率 | 越高越好 |
| 年化收益 | 年化后的收益 | 越高越好 |
| 年化波动率 | 风险 | 越低越好 |
| 夏普比率 | 风险调整收益 | > 1.0 |
| Sortino 比率 | 只考虑下行风险 | > 1.5 |
| 最大回撤 | 最大亏损 | 越小越好 |
| Calmar 比率 | 收益/回撤 | > 1.0 |
| 胜率 | 盈利交易占比 | > 50% |
| 盈亏比 | 平均盈利/平均亏损 | > 1.5 |
| 交易次数 | 全周期交易次数 | 适中 |

```python
from utils import calculate_all_metrics

strategies = [
    BuyHold_Strategy('S1_BuyHold'),
    MACD_Strategy('S2_MACD'),
    RSI_Strategy('S3_RSI'),
    Trend_Strategy('S4_Trend'),
    Original_Strategy('S5_Original')
]

results = []
for strategy in strategies:
    df_result = strategy.backtest(df)
    metrics = calculate_all_metrics(
        df_result['strategy_return'].dropna(),
        df_result['equity']
    )
    results.append({'strategy': strategy.name, **metrics})

comparison_df = pd.DataFrame(results)
```

#### 3.4 分市场状态分析 ⭐ 核心
策略在不同市场的表现：

- [ ] **牛市表现**（年度收益 > 15%）
  - 哪个策略收益最高？
  - 是否跟上市场？
  
- [ ] **熊市表现**（年度收益 < -5%）
  - 哪个策略回撤最小？
  - 是否有防御能力？
  
- [ ] **震荡市表现**（其他）
  - 哪个策略最稳定？
  - 交易是否过度？

```python
# 使用 Task 1 的市场状态标注
market_states = pd.read_csv('diagnosis/results/task1_market_states.csv')

# 分市场状态计算
for state in ['牛市', '熊市', '震荡']:
    state_years = market_states[market_states['市场状态'] == state].index
    state_df = df[df['year'].isin(state_years)]
    
    # 对每个策略在该市场状态回测
    ...
```

### 交付物
1. `task3_simple_strategies.py` - 5 个策略的完整实现
2. `task3_backtest_results.csv` - 性能对比表
3. `task3_market_state_performance.csv` - 分市场状态表现
4. `task3_equity_curves.png` - 权益曲线对比图
5. `task3_metrics_heatmap.png` - 指标热图
6. **分析报告**（2-3 页）：
   - 哪个策略表现最好？
   - 简单策略 vs 复杂策略的结论
   - 原策略的主要问题
   - 建议的策略结构

### 关键问题
请在报告中回答：
1. 原策略（S5）的表现是最好的吗？
2. 如果不是，差距有多大？
3. 单指标策略（S2, S3, S4）谁最好？
4. 简化策略的最优结构是什么？（1 个条件？2 个？3 个？）
5. 在熊市中，哪个策略最抗跌？

---

## 🎛️ Task 4: 参数敏感性分析

### 目标
找出**关键参数**和**最优参数区间**。

理解每个参数对策略表现的影响，为参数优化提供依据。

### 原策略参数回顾
当前策略有 15+ 个参数，主要包括：

**趋势参数**：
- `ema_fast`: 20（快线）
- `ema_slow`: 60（慢线）

**指标参数**：
- `rsi_period`: 14
- `rsi_lower`: 30
- `rsi_upper`: 70
- `macd_fast`: 12
- `macd_slow`: 26
- `macd_signal`: 9
- `adx_threshold`: 20
- `atr_period`: 14

**策略参数**：
- `entry_threshold`: 0.5（入场评分阈值）
- `exit_threshold`: -0.5（出场评分阈值）
- `stop_loss_mult`: 2.0（ATR 止损倍数）
- `take_profit_mult`: 4.0（ATR 止盈倍数）

### 具体工作

#### 4.1 关键参数识别
按影响程度分类：

**一级参数**（预期影响大）：
- `entry_threshold`
- `exit_threshold`
- `adx_threshold`
- `stop_loss_mult`
- `take_profit_mult`

**二级参数**（预期影响中）：
- `ema_fast`, `ema_slow`
- `rsi_lower`, `rsi_upper`

**三级参数**（预期影响小）：
- `rsi_period`, `macd_fast` 等周期参数

#### 4.2 单参数扫描 ⭐ 核心
对每个一级参数进行扫描：

**示例：entry_threshold 扫描**
```python
def parameter_scan(df, param_name, param_range, base_params):
    """单参数扫描"""
    results = []
    
    for value in param_range:
        # 更新参数
        params = base_params.copy()
        params[param_name] = value
        
        # 运行回测
        strategy = Original_Strategy(**params)
        df_result = strategy.backtest(df)
        
        # 计算指标
        metrics = calculate_all_metrics(
            df_result['strategy_return'].dropna(),
            df_result['equity']
        )
        
        results.append({
            'param_value': value,
            'sharpe': metrics['sharpe_ratio'],
            'total_return': metrics['total_return'],
            'max_drawdown': metrics['max_drawdown']
        })
    
    return pd.DataFrame(results)

# 扫描 entry_threshold
base_params = {
    'entry_threshold': 0.5,
    'exit_threshold': -0.5,
    'adx_threshold': 20,
    # ... 其他默认参数
}

entry_scan = parameter_scan(
    df, 
    'entry_threshold', 
    np.arange(-2.0, 2.1, 0.2),  # -2.0 到 2.0，步长 0.2
    base_params
)
```

**扫描范围建议**：
- `entry_threshold`: -2.0 ~ 2.0，步长 0.2
- `exit_threshold`: -2.0 ~ 1.0，步长 0.2
- `adx_threshold`: 10 ~ 40，步长 5
- `stop_loss_mult`: 0 ~ 5，步长 0.5
- `take_profit_mult`: 0 ~ 8，步长 1

#### 4.3 绘制敏感性曲线
对每个参数绘制 3 条曲线：
- X 轴：参数值
- Y 轴：
  - 夏普比率（主要指标）
  - 总收益率
  - 最大回撤

```python
fig, axes = plt.subplots(2, 3, figsize=(15, 10))

for idx, (param_name, result_df) in enumerate(scan_results.items()):
    ax = axes.flatten()[idx]
    
    ax.plot(result_df['param_value'], result_df['sharpe'], 'o-', label='Sharpe')
    ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
    ax.set_xlabel(param_name)
    ax.set_ylabel('Sharpe Ratio')
    ax.set_title(f'{param_name} Sensitivity')
    ax.grid(True, alpha=0.3)
    
    # 标注最优值
    best_idx = result_df['sharpe'].idxmax()
    best_value = result_df.loc[best_idx, 'param_value']
    best_sharpe = result_df.loc[best_idx, 'sharpe']
    ax.plot(best_value, best_sharpe, 'r*', markersize=15, label=f'Best: {best_value}')
    ax.legend()
```

#### 4.4 参数交互分析
测试 2 个参数的组合效果：

**示例：entry_threshold × exit_threshold**
```python
entry_range = np.arange(-1.0, 2.0, 0.2)
exit_range = np.arange(-2.0, 1.0, 0.2)

sharpe_matrix = np.zeros((len(entry_range), len(exit_range)))

for i, entry_val in enumerate(entry_range):
    for j, exit_val in enumerate(exit_range):
        if entry_val <= exit_val:
            sharpe_matrix[i, j] = np.nan
            continue
        
        params = base_params.copy()
        params['entry_threshold'] = entry_val
        params['exit_threshold'] = exit_val
        
        strategy = Original_Strategy(**params)
        df_result = strategy.backtest(df)
        metrics = calculate_all_metrics(...)
        sharpe_matrix[i, j] = metrics['sharpe_ratio']

# 绘制热图
plt.figure(figsize=(10, 8))
sns.heatmap(sharpe_matrix, 
            xticklabels=exit_range.round(1),
            yticklabels=entry_range.round(1),
            cmap='RdYlGn', center=0,
            annot=True, fmt='.2f')
plt.xlabel('exit_threshold')
plt.ylabel('entry_threshold')
plt.title('Sharpe Ratio Heatmap')
```

#### 4.5 最优参数推荐
基于扫描结果，给出最优参数组合：

```python
optimal_params = {
    'entry_threshold': ...,  # 夏普最高的值
    'exit_threshold': ...,
    'adx_threshold': ...,
    'stop_loss_mult': ...,
    'take_profit_mult': ...,
}

# 用最优参数回测
optimized_strategy = Original_Strategy(**optimal_params)
df_optimized = optimized_strategy.backtest(df)

# 对比原参数 vs 最优参数
```

### 交付物
1. `task4_parameter_scan_results.csv` - 所有参数扫描结果
2. `task4_optimal_params.json` - 最优参数建议
3. `task4_sensitivity_curves.png` - 敏感性曲线（2×3 子图）
4. `task4_interaction_heatmap.png` - 参数交互热图
5. `task4_before_after_comparison.png` - 优化前后对比
6. **分析报告**（2-3 页）：
   - 哪些参数影响最大？
   - 当前参数是否合理？
   - 推荐的参数区间
   - 优化后的性能提升

### 关键问题
请在报告中回答：
1. 哪个参数对策略表现影响最大？
2. 当前参数（如 `entry_threshold=0.5`）是否在最优区间？
3. `stop_loss_mult` 和 `take_profit_mult` 的最优值是多少？
4. 参数之间有显著的交互效应吗？
5. 使用最优参数后，夏普比率能提升多少？

---

## 🛠️ 工具和资源

### 已准备的文件
1. **DIAGNOSIS_TASKS.md** - 任务详细说明
2. **utils.py** - 共享工具库
3. **app.py** - 原始策略代码（可参考）
4. **diagnosis/results/task1_market_states.csv** - 市场状态标注（Task 1 产出）

### 原策略代码参考
```python
# 在 app.py 中查看
def compute_signals(df, ...):
    """原策略的信号生成逻辑"""
    ...

def simulate_strategy(df, ...):
    """原策略的回测框架"""
    ...
```

### 常用函数
```python
# 性能计算
from utils import calculate_all_metrics
metrics = calculate_all_metrics(returns, equity)
# 返回: {sharpe_ratio, sortino_ratio, max_drawdown, ...}

# 可视化
from utils import plot_equity_curves
plot_equity_curves({
    'S1': equity1,
    'S2': equity2,
    'S3': equity3
}, save_path='diagnosis/figures/task3_comparison.png')

# 保存结果
from utils import save_results_to_csv
save_results_to_csv(results_df, 'task3_results.csv')
```

---

## 📅 工作计划建议

### Day 1-3: Task 3（优先）
- **Day 1**：实现 5 个基准策略（4 小时）
- **Day 2**：统一回测和性能对比（3 小时）
- **Day 3**：分市场状态分析 + 撰写报告（3 小时）

### Day 4-6: Task 4（可与 Task 3 并行）
- **Day 4**：单参数扫描（entry, exit, adx）（3 小时）
- **Day 5**：单参数扫描（stop_loss, take_profit）+ 绘图（4 小时）
- **Day 6**：参数交互分析 + 最优参数测试 + 报告（3 小时）

### Day 7: 整理和汇报
- 整合两个任务的结果
- 准备演示材料

---

## 📊 汇报要求

### 定期汇报（建议每 2-3 天）
请提供：
1. **进度更新**：完成了哪些子任务
2. **初步发现**：策略对比或参数扫描的关键结果
3. **遇到的问题**：需要帮助的地方
4. **下一步计划**：接下来做什么

### 汇报格式（示例）
```
【策略开发者进度汇报 - Day 3】

✅ 已完成：
- Task 3: 实现了 5 个基准策略
- Task 3: 完成了统一回测

📊 初步发现：
1. S2 (MACD Only) 夏普 0.78，优于 S5 (Original) 的 0.52
2. S5 (Original) 交易次数只有 S2 的 30%，过于保守
3. 在牛市中，S1 (Buy&Hold) 表现最好
4. 在熊市中，S4 (Trend) 回撤最小

❓ 问题：
- 分市场状态分析需要等 Task 1 的市场状态标注

📅 下一步：
- 完成分市场状态分析
- 开始 Task 4 参数扫描
```

---

## 🎯 成功标准

### 最低要求
- ✅ 2 个任务全部完成
- ✅ 所有交付物齐全
- ✅ 每个任务有分析报告（2-3 页）

### 优秀标准
- ⭐ 清晰证明了简化策略的优势
- ⭐ 找到了显著提升性能的参数组合
- ⭐ 图表专业，对比清晰
- ⭐ 提供了具体的策略改进建议

---

## 💡 重要提示

1. **优先级**：Task 3 > Task 4（先找结构，再调参数）
2. **关注重点**：简单 vs 复杂的对比是核心发现
3. **公平对比**：确保所有策略用相同的回测设置
4. **参数扫描**：注意计算量，可以先用小范围测试
5. **市场状态**：分市场分析能揭示策略的适用场景

## ❓ 有问题随时联系项目经理

- 不清楚原策略逻辑？→ 查看 `app.py` 中的实现
- 回测框架怎么写？→ 参考 `app.py` 的 `simulate_strategy()`
- 不会用工具函数？→ 查看 `utils.py` 的文档
- 计算太慢？→ 减少扫描范围或使用并行计算
- 还有疑问？→ 随时汇报

---

**祝工作顺利！期待你的策略洞察！🚀**

---
**发布日期**：2026-01-22  
**项目经理**：AI PM  
**截止时间**：1 周内（2026-01-29）
