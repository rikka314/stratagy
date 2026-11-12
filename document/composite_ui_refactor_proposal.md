# Composite UI 重构方案

## 📋 当前问题分析

### 1. **逻辑混乱问题**
- ❌ 选择 `composite` 后仍然显示 `search_base` 选择（sm/fsm）
- ❌ Composite 不需要 search_base，但代码 fallthrough 到 search 逻辑
- ❌ 训练集范围选择器放在所有策略前面，实际只有 search 需要
- ❌ ML/News 增强选项对所有 family 可见，实际只适用于 search

### 2. **用户体验问题**
- ❌ 不同策略的配置界面没有明确隔离
- ❌ 用户需要理解哪些选项适用于当前选择的策略
- ❌ Composite 的配置被 search 配置淹没

### 3. **代码结构问题**
```python
def _build_strategy_request(family: str) -> StrategyRequest:
    if family == "baseline":
        return ...
    if family == "composite":
        return ...
    if family == "regime":
        return ...
    
    # ❌ 问题：没有明确的 if family == "search"
    # search 逻辑是 fallthrough，任何未匹配的 family 都会进入
    search_base = st.selectbox(...)  # 所有其他 family 都会看到这个
```

---

## 🎯 重构目标

### 1. **策略配置隔离**
每个策略 family 有独立的配置区域，互不干扰

### 2. **渐进式展开**
用户选择 family 后，只看到该策略相关的配置

### 3. **清晰的视觉层级**
```
Step 1: 选择策略类型 [Baseline | Search | Composite | Regime]
  ↓
Step 2: 该策略的专属配置
  ↓
Step 3: 运行按钮
```

---

## 📐 重构方案

### 方案 A: **最小改动方案**（推荐）

#### 改动内容
1. 修复 `_build_strategy_request` 的逻辑分支
2. 将 search 特定的配置移入 `if family == "search"` 分支
3. 保持现有 UI 布局，只调整逻辑

#### 代码结构
```python
def _build_strategy_request(family: str) -> StrategyRequest:
    if family == "baseline":
        # Baseline 配置
        return StrategyRequest(family="baseline", ...)
    
    elif family == "composite":
        # Composite 配置（已完成，无需改动）
        return StrategyRequest(family="composite", ...)
    
    elif family == "regime":
        # Regime 配置
        return StrategyRequest(family="regime", ...)
    
    elif family == "search":
        # ✅ 明确的 search 分支
        search_base = st.selectbox(...)  # 只在 search 时显示
        
        # 训练集范围（search 专属）
        if st.checkbox("自定义训练集范围"):
            train_ratio = st.slider(...)
        
        # 参数优化
        use_search = st.checkbox("参数搜索")
        
        # ML 增强
        use_ml = st.checkbox("ML 过滤")
        
        # News 增强
        use_news = st.checkbox("News 融合")
        
        return StrategyRequest(
            family="search",
            search_base=search_base,
            use_search=use_search,
            use_ml=use_ml,
            use_news=use_news,
            ...
        )
    
    else:
        # ✅ 明确的 fallback
        st.error(f"未知策略类型: {family}")
        return StrategyRequest()
```

#### 优点
- ✅ 改动最小（~50 行代码）
- ✅ 不影响现有 UI 布局
- ✅ 立即修复逻辑混乱问题
- ✅ 不需要测试 UI 交互

#### 缺点
- ⚠️ 不解决"训练集范围放在前面"的视觉问题
- ⚠️ 配置项仍然比较多

---

### 方案 B: **完整重构方案**

#### 改动内容
1. 完全重构 `_render_model_configuration_section`
2. 每个策略 family 独立的渲染函数
3. 重新设计 UI 布局层级

#### 代码结构
```python
def _render_model_configuration_section(family: str | None) -> StrategyRequest:
    if family is None:
        st.info("👆 请先选择策略类型")
        return StrategyRequest()
    
    # 策略专属渲染函数
    if family == "baseline":
        return _render_baseline_config()
    elif family == "search":
        return _render_search_config()
    elif family == "composite":
        return _render_composite_config()
    elif family == "regime":
        return _render_regime_config()
    else:
        st.error(f"未知策略类型: {family}")
        return StrategyRequest()


def _render_search_config() -> StrategyRequest:
    """Search 策略专属配置"""
    st.markdown("### 🔍 Search 策略配置")
    
    # Step 1: 基础模型
    search_base = st.selectbox("基础模型", ["sm", "fsm"], ...)
    
    # Step 2: 训练集范围（Search 专属）
    with st.expander("⚙️ 训练集设置", expanded=False):
        train_ratio = st.slider("训练集比例", 0.5, 0.9, 0.7)
    
    # Step 3: 参数优化
    use_search = st.checkbox("启用参数搜索")
    if use_search:
        search_method = st.selectbox(...)
    
    # Step 4: 增强选项
    with st.expander("🚀 增强选项", expanded=False):
        use_ml = st.checkbox("ML 过滤")
        use_news = st.checkbox("News 融合")
    
    return StrategyRequest(family="search", ...)


def _render_composite_config() -> StrategyRequest:
    """Composite 策略专属配置（已完成）"""
    st.markdown("### 🎯 Composite 策略配置")
    
    st.caption("使用多因子融合，自动训练权重（CN_A）或使用预定义专家池（US）")
    
    # Advisory 策略
    composite_policy = st.selectbox("Advisory 策略", ...)
    
    # 高级设置
    with st.expander("⚙️ 高级设置", expanded=False):
        composite_risk_budget = st.slider(...)
        composite_position_method = st.selectbox(...)
    
    return StrategyRequest(family="composite", ...)
```

#### UI 效果示意
```
┌─────────────────────────────────────────┐
│ Step 1: 选择策略类型                     │
│ [Baseline] [Search] [Composite] [Regime]│
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ 🎯 Composite 策略配置                    │
│ ─────────────────────────────────────── │
│ 使用多因子融合，自动训练权重             │
│                                          │
│ Advisory 策略:                           │
│ ◉ Composite Only                        │
│ ○ Composite + Trend Advisory            │
│ ○ ...                                    │
│                                          │
│ ▼ ⚙️ 高级设置                            │
│   └─ 风险预算: [====|====] 1.0          │
│   └─ 仓位映射: 线性归一化                │
└─────────────────────────────────────────┘
                  ↓
           [▶️ 运行策略]
```

#### 优点
- ✅ 完全隔离的配置界面
- ✅ 清晰的视觉层级
- ✅ 更好的用户体验
- ✅ 代码结构清晰，易维护

#### 缺点
- ⚠️ 改动较大（~200-300 行代码）
- ⚠️ 需要完整回归测试所有策略
- ⚠️ 可能影响现有用户习惯

---

### 方案 C: **混合方案**（平衡）

#### 改动内容
1. 采用方案 A 的逻辑修复
2. 将 Search 特定配置收入 `st.expander`
3. 视觉上区分不同策略，但不完全重构

#### 代码示例
```python
def _build_strategy_request(family: str) -> StrategyRequest:
    if family == "baseline":
        # ... 现有代码
        
    elif family == "composite":
        # ... 现有代码（无需改动）
        
    elif family == "regime":
        # ... 现有代码
        
    elif family == "search":
        st.markdown("### 🔍 Search 策略配置")
        
        search_base = st.selectbox("基础模型", ["sm", "fsm"], ...)
        
        # 所有 search 特定配置收入 expander
        with st.expander("⚙️ Search 配置选项", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                use_search = st.checkbox("参数搜索")
                use_ml = st.checkbox("ML 过滤")
            with col2:
                use_news = st.checkbox("News 融合")
                # 训练集范围也移到这里
                train_ratio = st.slider(...)
        
        return StrategyRequest(family="search", ...)
```

#### 优点
- ✅ 改动适中（~100 行代码）
- ✅ 视觉上有所改进
- ✅ 逻辑完全修复
- ✅ 测试工作量适中

#### 缺点
- ⚠️ 仍需要回归测试 search 策略
- ⚠️ 视觉改进有限

---

## 📊 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| 改动量 | ~50 行 | ~300 行 | ~100 行 |
| 逻辑修复 | ✅ 完全 | ✅ 完全 | ✅ 完全 |
| 视觉改进 | ❌ 无 | ✅ 显著 | 🟡 中等 |
| 测试工作量 | 🟢 低 | 🔴 高 | 🟡 中 |
| 用户习惯影响 | 🟢 无 | 🔴 高 | 🟡 中 |
| 代码可维护性 | 🟡 中 | ✅ 高 | 🟡 中 |
| 实施时间 | 10 分钟 | 2 小时 | 30 分钟 |

---

## 🎯 推荐实施路径

### 阶段 1: 立即修复（方案 A）
**目标**: 修复逻辑混乱问题，让 Composite 可以正常测试

**改动**:
1. 将 search 逻辑改为 `elif family == "search"`
2. 添加 `else` 分支处理未知 family

**时间**: 10 分钟  
**风险**: 🟢 极低

### 阶段 2: 视觉优化（方案 C）（可选）
**目标**: 改进 UI 布局，提升用户体验

**改动**:
1. 将 Search 配置收入 expander
2. 添加视觉分隔符和标题

**时间**: 30 分钟  
**风险**: 🟡 中等

### 阶段 3: 完整重构（方案 B）（长期规划）
**目标**: 彻底重构 UI，支持未来更多策略类型

**改动**:
1. 完全重构 `_render_model_configuration_section`
2. 每个策略独立渲染函数
3. 统一的配置模式

**时间**: 2 小时  
**风险**: 🔴 高

---

## 💡 我的建议

**立即执行**: **阶段 1（方案 A）**
- 现在就修复逻辑问题
- 让你能够正常测试 Composite
- 改动最小，风险最低

**后续考虑**: **阶段 2（方案 C）**
- 在完成 Composite 功能测试后
- 如果用户反馈 UI 混乱，再执行
- 不急于现在做

**长期规划**: **阶段 3（方案 B）**
- 当需要添加更多策略类型时
- 或者用户反馈强烈要求时
- 作为大版本更新的一部分

---

## 🚀 立即行动方案（阶段 1）

我可以立即为你实施方案 A，预计 10 分钟完成：

### 改动清单
1. ✅ 修改 `_build_strategy_request` 添加 `elif family == "search"`
2. ✅ 添加 `else` 分支处理未知 family
3. ✅ 确保 Composite 不会进入 search 逻辑
4. ✅ 快速回归测试

### 验证方式
- 选择 Composite → 不应该看到 search_base 选择器
- 选择 Search → 应该看到完整的 search 配置
- 选择 Baseline → 只看到 baseline 配置
- 选择 Regime → 只看到 regime 配置

---

## ❓ 请你决策

请告诉我：
1. 是否立即执行**阶段 1（方案 A）**？
2. 是否在测试完成后考虑**阶段 2（方案 C）**？
3. 或者你有其他想法？

我在等待你的指示。
