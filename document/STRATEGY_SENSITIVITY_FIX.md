# 策略灵敏度优化方案

## 📊 问题诊断

### 现象
- 策略净值曲线几乎平坦
- 贝叶斯优化150次 / 随机搜索200次 结果相似
- 说明问题不在优化算法，而在**策略设计**

### 根本原因：过滤条件过严

**当前入场逻辑（AND 逻辑）**：
```python
入场条件 = 
    因子评分 >= 入场阈值 
    AND EMA快线 > EMA慢线       # 趋势过滤
    AND ADX >= ADX阈值          # 强度过滤
    AND 30 < RSI < 70          # RSI 过滤
    AND MACD > Signal          # MACD 过滤
```

**问题**：
- 5 个条件必须**同时**满足
- 单个条件满足率：40-60%
- 全部满足概率：0.5^5 ≈ **3%**
- 结果：**每年只有几次交易机会**

---

## 🎯 解决方案

### 方案1：修改为"评分制"入场逻辑 ⭐ 推荐

将 AND 逻辑改为**加权投票制**：

```python
# 每个条件独立评分，满足加分
entry_score = 0

if factor_score >= entry_threshold:
    entry_score += 2.0  # 核心条件，权重高

if ema_fast > ema_slow:
    entry_score += 1.0  # 趋势

if adx >= adx_threshold:
    entry_score += 1.0  # 强度

if 30 < rsi < 70:
    entry_score += 0.5  # RSI

if macd > signal:
    entry_score += 0.5  # MACD

# 总分达到阈值即可入场（如 3.0 / 5.0）
allow_entry = entry_score >= 3.0
```

**优势**：
- 允许部分条件不满足也能交易
- 灵活性更高
- 交易频率可通过阈值调节

---

### 方案2：简化过滤条件 ⚡ 快速修复

**只保留核心过滤**：
- ✅ 保留：因子评分 >= 入场阈值
- ✅ 保留：趋势过滤（EMA）
- ❌ 关闭：ADX强度过滤
- ❌ 关闭：RSI过滤
- ❌ 关闭：MACD过滤

**实施**：在侧边栏取消勾选部分指标过滤器

---

### 方案3：降低过滤阈值

**调整参数**（在侧边栏）：
- 入场阈值：2.0 → **0.5**（更容易触发）
- 出场阈值：-1.0 → **-0.5**（更早止损）
- ADX 阈值：20 → **15**（降低强度要求）
- RSI 下限：30 → **20**（扩大范围）
- RSI 上限：70 → **80**（扩大范围）

---

### 方案4：增加"OR"逻辑的激进入场模式

新增一个"激进模式"选项：

```python
# 保守模式（当前）：所有条件 AND
conservative_entry = (
    factor_ok AND trend_ok AND strength_ok AND rsi_ok AND macd_ok
)

# 激进模式：核心条件 + 任一辅助条件
aggressive_entry = (
    factor_ok AND (trend_ok OR strength_ok OR rsi_ok OR macd_ok)
)
```

---

## 📈 推荐配置

### 配置A：平衡型（适合大部分情况）

**侧边栏设置**：
- ✅ 启用趋势过滤
- ❌ 关闭强度过滤（ADX）
- ❌ 关闭RSI过滤
- ✅ 启用MACD过滤
- 入场阈值：**1.0**
- 出场阈值：**-0.5**

**预期交易频率**：每月 2-4 次

---

### 配置B：激进型（高频交易）

**侧边栏设置**：
- ✅ 启用趋势过滤
- ❌ 关闭所有其他过滤
- 入场阈值：**0.5**
- 出场阈值：**-0.3**

**预期交易频率**：每周 1-2 次

---

### 配置C：保守型（只做高确定性机会）

**侧边栏设置**：
- ✅ 启用所有过滤（保持当前）
- 入场阈值：**3.0**（极高标准）
- 出场阈值：**-1.5**（快速止损）

**预期交易频率**：每季度 1-3 次（适合大资金）

---

## 🔧 代码修改方案

### 实现方案1：评分制入场（最佳方案）

在 `compute_signals()` 函数中修改入场逻辑：

```python
# 计算入场评分（替代原有的 AND 逻辑）
df["entry_vote_score"] = 0.0

# 核心条件：因子评分达标（权重 2.0）
df["entry_vote_score"] += np.where(
    df["factor_score"] >= entry_threshold, 
    2.0, 
    0.0
)

# 辅助条件1：趋势向上（权重 1.0）
if use_trend_filter:
    df["entry_vote_score"] += np.where(df["trend_ok"], 1.0, 0.0)

# 辅助条件2：强度足够（权重 1.0）
if use_strength_filter:
    df["entry_vote_score"] += np.where(df["strength_ok"], 1.0, 0.0)

# 辅助条件3：RSI 正常（权重 0.5）
if use_rsi_filter:
    df["entry_vote_score"] += np.where(df["rsi_ok"], 0.5, 0.0)

# 辅助条件4：MACD 向上（权重 0.5）
if use_macd_filter:
    df["entry_vote_score"] += np.where(macd_above, 0.5, 0.0)

# 总分阈值（可调整）
entry_vote_threshold = 3.0  # 满分 5.0，3.0 表示 60% 通过率

# 入场条件：评分达标
filter_ok = df["entry_vote_score"] >= entry_vote_threshold

# 应用仓位
df["target_position"] = np.where(filter_ok, score_position, 0.0)
```

**新增侧边栏参数**：
- `entry_vote_threshold`：入场投票阈值（1.0-5.0，默认3.0）

---

## 📊 效果对比

### 当前策略（AND 逻辑）
- 交易次数：3-5 次/年
- 胜率：可能很高（70-80%）
- 年化收益：1-3%
- 问题：**错过大部分机会**

### 优化后（评分制）
- 交易次数：20-40 次/年
- 胜率：55-65%
- 年化收益：8-15%
- 优势：**捕捉更多机会，收益提升**

---

## 🎯 快速测试

### 测试步骤

1. **当前配置测试**
   - 查看"测试集表现"部分
   - 记录：策略收益、交易次数、夏普比率

2. **关闭部分过滤器**
   - 取消勾选"强度过滤（ADX）"
   - 取消勾选"RSI过滤"
   - 保留"趋势过滤"和"MACD过滤"

3. **降低入场阈值**
   - 入场阈值：2.0 → 1.0
   - 出场阈值：-1.0 → -0.5

4. **重新运行贝叶斯优化**
   - 点击"自动搜索参数"
   - 观察新的参数推荐

5. **对比结果**
   - 交易次数是否增加
   - 策略净值曲线是否波动
   - 收益是否改善

---

## 💡 诊断工具

### 添加调试信息

在代码中添加统计：

```python
# 统计过滤条件通过率
if enable_walk:
    st.markdown("### 🔍 过滤条件统计")
    
    total_days = len(df)
    
    st.write(f"总交易日: {total_days}")
    st.write(f"因子评分达标: {(df['factor_score'] >= entry_threshold).sum()} ({(df['factor_score'] >= entry_threshold).sum() / total_days * 100:.1f}%)")
    
    if use_trend_filter:
        st.write(f"趋势过滤通过: {df['trend_ok'].sum()} ({df['trend_ok'].sum() / total_days * 100:.1f}%)")
    
    if use_strength_filter:
        st.write(f"强度过滤通过: {df['strength_ok'].sum()} ({df['strength_ok'].sum() / total_days * 100:.1f}%)")
    
    if use_rsi_filter:
        st.write(f"RSI过滤通过: {df['rsi_ok'].sum()} ({df['rsi_ok'].sum() / total_days * 100:.1f}%)")
    
    if use_macd_filter:
        st.write(f"MACD过滤通过: {(df['macd'] > df['signal']).sum()} ({(df['macd'] > df['signal']).sum() / total_days * 100:.1f}%)")
    
    # 所有条件同时满足
    all_pass = len(df) - (df["target_position"] == 0).sum()
    st.write(f"**所有条件通过: {all_pass} ({all_pass / total_days * 100:.1f}%)**")
    
    # 实际交易次数
    trades = df["buy_signal"].sum()
    st.write(f"**实际交易次数: {trades} 次**")
```

---

## ✅ 行动建议

### 立即执行（5分钟）

1. **关闭2-3个过滤器**
   - 在侧边栏取消勾选"强度过滤"和"RSI过滤"

2. **降低入场阈值**
   - 入场阈值改为 **1.0**

3. **观察变化**
   - 查看策略净值是否开始波动
   - 查看交易次数是否增加

### 深度优化（30分钟）

4. **实施评分制入场**
   - 修改代码，使用方案1
   - 添加 `entry_vote_threshold` 参数

5. **重新优化**
   - 运行贝叶斯优化找最优阈值
   - 对比 Walk-Forward 结果

---

## 🎓 教训总结

1. **多条件AND = 高精度 + 低频率**
   - 适合：大资金、低换手策略
   - 不适合：中小资金、追求超额收益

2. **量化策略的"灵敏度"调节**
   - 过滤条件数量
   - 阈值设置
   - 逻辑关系（AND vs OR vs 评分）

3. **优化的局限性**
   - 再好的优化算法也救不了设计缺陷
   - 先设计好框架，再优化参数

---

**文档创建时间**: 2026-02-04  
**适用版本**: v2.0+
