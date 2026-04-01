# UI 设计指导文档

> 产出日期：2026-03-20（W1 Day 6）
> 状态：初版方案，待用户确认后进入实施

---

## 1. 现状诊断

### 1.1 核心问题：频繁下拉

| 区域 | 当前状态 | 问题 |
|------|---------|------|
| 侧边栏 | ~30 个 slider + 多个 expander，纵向约 2500px | 用户需要滚动 4-5 屏才能看完所有控件 |
| 单股页 | 10 个区块线性堆叠（K线520px + RSI/MACD 520px + 因子520px + 搜索 + 测试420px + WF 420px + 信号420px + 导出） | 主内容区超过 4000px，找到特定区块需要反复滚动 |
| 多股页 | 7-8 个图表 + 表格 + 组合模拟 | 同样的纵向堆叠问题 |
| 视觉风格 | 纯 Streamlit 默认白底 + 蓝色主题 | 缺乏品牌感和视觉层次，看久了疲劳 |

### 1.2 具体问题清单

**侧边栏 (`sidebar.py`)**
- 入场/出场规则各有一段长文字说明（5 条 + 4 条），占据大量空间但用户看过一次就不再需要
- 高级设置 expander 展开后有 ~30 个 slider，即使折叠也有"入场规则"和"出场规则"两大段始终可见
- 策略预设切换后，大量 slider 只是被自动填充但仍然显示
- 反馈区块占据侧边栏底部空间

**单股页 (`single_stock.py`)**
- 训练集比例 slider 放在主页面顶部，但它本质上是配置参数
- 数据集概览只有一行文字，位置不够突出
- K线图、RSI/MACD、因子评分三张大图依次排列，高度合计 1560px
- 策略建议是纯文字，视觉优先级不够
- 高级搜索区块和搜索结果在页面中间，不易找到
- 测试集表现、Walk-Forward、交易信号三个区块都有各自的图表和控件，进一步拉长页面
- 导出区在最底部，用户常找不到

**共性问题**
- 没有 KPI 摘要卡（最关键的 4-5 个数字应该在最顶部一眼看到）
- 图表配色不统一（K线用红绿，净值用青绿+黄绿，RSI 用蓝，分散且无系统性）
- 各区块之间只有 `st.markdown("---")` 分隔，层次感弱
- 没有利用 Streamlit 的 `st.tabs` 组件来组织内容

---

## 2. 配色方案

### 2.1 设计理念

参考用户喜欢的学术笔记风格（暖色调、纸张质感、养眼），适配金融分析场景：
- 保持暖色基底的舒适感
- 用专业色彩标识涨跌、风险、信号
- 减少视觉噪音，让数据和图表成为视觉焦点

### 2.2 色板定义

```
主色板（从参考 HTML 适配）
├── 背景色
│   ├── page-bg:     #f4f1ea   (暖米色页面底色)
│   ├── card-bg:     #fffdf8   (暖白卡片底色)
│   └── sidebar-bg:  #ebe3d3   (暖灰侧边栏)
│
├── 文字色
│   ├── ink:         #21303a   (主文字，深蓝灰)
│   ├── muted:       #5a6974   (次要文字，灰)
│   └── line:        #d5cec0   (分割线，暖灰)
│
├── 强调色
│   ├── accent:      #2f5d62   (主强调色，青绿，用于标题、按钮、active状态)
│   ├── accent-2:    #8f3b2e   (辅强调色，赤陶色，用于警告、重要标注)
│   └── accent-soft: #e0eeef   (主强调色浅底，用于卡片背景)
│
├── 金融语义色
│   ├── bull:        #c0392b   (涨/看多，中国红)
│   ├── bear:        #27ae60   (跌/看空，绿)
│   ├── neutral:     #7f8c8d   (中性/持平，灰)
│   └── benchmark:   #f39c12   (基准/买入持有，琥珀)
│
└── 功能色
    ├── info-bg:     #eef4f7   (信息卡片底色，浅蓝)
    ├── success-bg:  #edf7f1   (成功/正面底色，浅绿)
    ├── warning-bg:  #fff4e5   (警告底色，浅黄)
    └── danger-bg:   #fde8e8   (危险/风险底色，浅红)
```

### 2.3 图表配色规则

| 用途 | 颜色 | 说明 |
|------|------|------|
| 策略净值线 | `#2f5d62` (accent) | 主角，最醒目 |
| 买入持有基准 | `#f39c12` (benchmark) | 对比线，与主线区分 |
| K线涨 | `#c0392b` (bull) | 中国市场习惯 |
| K线跌 | `#27ae60` (bear) | 中国市场习惯 |
| RSI 线 | `#2f5d62` (accent) | 与主色一致 |
| MACD 柱 | `#95a5a6` (neutral gray) | 辅助信息，不抢主图 |
| 买入信号标记 | `#c0392b` (bull) | 三角上 |
| 卖出信号标记 | `#27ae60` (bear) | 三角下 |
| 因子评分线 | `#2f5d62` (accent) | 主信息 |
| 评分分位数 | `#f39c12` (benchmark) | 辅助信息 |

### 2.4 KPI 卡片配色

```
正面指标（正收益、高夏普）:   accent (#2f5d62) 底 + 白字
负面指标（回撤、亏损）:       accent-2 (#8f3b2e) 底 + 白字
中性指标（信号数、数据量）:   muted gray 底 + 深字
```

---

## 3. 布局重构方案

### 3.1 侧边栏重构

**核心策略：渐进式展示（Progressive Disclosure）**

把侧边栏从"全部展开"改为"三级递进"：

```
侧边栏结构（重构后）
│
├── 🔍 股票与时间（始终可见，最紧凑）
│   ├── 市场选择: 美股 / A股（W2 新增，radio_button 水平排列）
│   ├── 股票选择: multiselect
│   ├── 日期范围: date_input
│   └── [➕ 添加/上传] expander（默认折叠）
│
├── 📋 策略配置（始终可见，紧凑）
│   ├── 策略预设: selectbox
│   ├── 入场信号数: slider（1行，无长文说明）
│   └── 出场信号数: slider（1行，无长文说明）
│
└── ⚙️ 高级参数（expander，默认折叠）
    ├── 每组参数用 2 列并排布局（如 EMA 快/慢 同行）
    └── 非"自定义参数"模式时显示提示"使用预设值"
```

**关键改动：**
1. 删除入场/出场规则的长文字说明（移到 help tooltip）
2. 复权方式从独立 selectbox 移入"添加/上传" expander
3. 高级参数区用 `st.columns(2)` 并排，将 30 个 slider 压缩到约 15 行
4. 反馈区块移到主页面底部或完全移除（用 GitHub link 替代）
5. 刷新按钮合并到股票选择区域

**预估效果**：侧边栏总高度从 ~2500px 降到 ~800px，常用操作无需滚动。

### 3.2 单股页面重构

**核心策略：Tab 分区 + 顶部 KPI**

```
单股页面结构（重构后）
│
├── 顶部 KPI 摘要卡（始终可见，一行 4-5 个指标卡）
│   ├── 策略收益  ├── 基准收益  ├── 夏普比率
│   ├── 最大回撤  └── 策略建议（文字标签）
│
├── st.tabs 分区
│   ├── [📊 图表分析]
│   │   ├── K线图范围选择器（数据集/训练集，水平 radio）
│   │   ├── K线蜡烛图
│   │   ├── RSI + MACD 图
│   │   └── 因子评分图
│   │
│   ├── [📈 回测结果]
│   │   ├── 训练集比例 slider
│   │   ├── 数据集概览
│   │   ├── 测试集净值对比图
│   │   ├── 测试集统计指标（4 列 metrics）
│   │   └── 测试集交易信号图
│   │
│   ├── [🔄 滚动验证]
│   │   ├── Walk-Forward 参数设置
│   │   ├── Walk-Forward 净值图
│   │   └── 分窗口结果表
│   │
│   ├── [🔬 策略优化]
│   │   ├── 搜索方法选择
│   │   ├── 搜索参数
│   │   ├── 运行按钮
│   │   └── 搜索结果 + 应用按钮
│   │
│   └── [📤 导出]
│       └── 报告生成与下载
│
└── （底部无其他内容，干净收尾）
```

**关键改动：**
1. KPI 卡片提到最顶部，用户打开页面就能看到核心数字
2. 用 `st.tabs` 将 10 个区块分成 5 个 tab，每个 tab 只显示 2-3 个区块
3. 每个 tab 内容高度控制在 1-2 屏以内
4. 策略建议从独立区块变为 KPI 卡片中的一个标签

**预估效果**：任何时候页面可见内容不超过 1.5 屏，用户通过 tab 切换而不是滚动。

### 3.3 多股页面重构

```
多股页面结构（重构后）
│
├── 顶部 KPI 行
│   ├── 对比股票数  ├── 最佳表现  └── 相关性范围
│
├── st.tabs 分区
│   ├── [📊 价格对比]
│   │   ├── 归一化价格图
│   │   └── 关键统计表
│   │
│   ├── [📈 风险分析]
│   │   ├── 风险收益散点图
│   │   ├── 相关性热图
│   │   └── 相对强弱图
│   │
│   ├── [🎯 因子对比]
│   │   ├── 因子评分柱状图
│   │   └── 周期收益热图
│   │
│   └── [💼 组合模拟]
│       ├── 组合模拟设置
│       ├── 模拟结果
│       └── 贝叶斯优化
```

---

## 4. 自定义 CSS 注入

Streamlit 支持通过 `st.markdown` 注入 CSS。以下是建议的全局样式：

```css
/* 在 app.py 顶部注入 */

/* 页面背景 */
.stApp {
    background-color: #f4f1ea;
}

/* 侧边栏背景 */
[data-testid="stSidebar"] {
    background-color: #ebe3d3;
}

/* 主区域卡片感 */
.stMainBlockContainer {
    background-color: #fffdf8;
    border-radius: 16px;
    padding: 24px 32px;
    margin: 12px;
    box-shadow: 0 4px 12px rgba(33, 48, 58, 0.06);
}

/* KPI 指标卡片 */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #2f5d62 0%, #3a7d83 100%);
    color: white;
    padding: 16px;
    border-radius: 12px;
    box-shadow: 0 4px 8px rgba(47, 93, 98, 0.15);
}

[data-testid="stMetricLabel"] {
    color: rgba(255, 255, 255, 0.85);
}

[data-testid="stMetricValue"] {
    color: white;
    font-weight: 700;
}

/* Tab 标签页样式 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: rgba(235, 227, 211, 0.5);
    border-radius: 12px;
    padding: 4px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}

/* 主标题 */
h1 {
    color: #21303a;
    border-bottom: 3px solid #2f5d62;
    padding-bottom: 8px;
}

/* 副标题 */
h2 {
    color: #21303a;
    border-left: 4px solid #2f5d62;
    padding-left: 12px;
}

/* 按钮 */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2f5d62 0%, #3a7d83 100%);
    border: none;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgba(47, 93, 98, 0.2);
}
```

> 注意：Streamlit 的 CSS 选择器可能随版本变化，上述为参考实现，实施时需验证。

---

## 5. 图表统一规范

### 5.1 Plotly 图表模板

建议创建一个统一的图表主题函数，在 `core/visualization.py` 或新建 `core/chart_theme.py`：

```python
CHART_LAYOUT = dict(
    height=480,
    plot_bgcolor="#fffdf8",
    paper_bgcolor="#fffdf8",
    font=dict(family="Source Sans Pro, sans-serif", color="#21303a", size=13),
    title_font=dict(size=16, color="#21303a"),
    xaxis=dict(
        showgrid=True,
        gridcolor="rgba(213, 206, 192, 0.5)",
        title_font=dict(color="#5a6974"),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(213, 206, 192, 0.5)",
        title_font=dict(color="#5a6974"),
    ),
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=12),
    ),
    margin=dict(l=60, r=20, t=50, b=50),
)

COLORS = dict(
    strategy="#2f5d62",
    benchmark="#f39c12",
    bull="#c0392b",
    bear="#27ae60",
    neutral="#95a5a6",
    factor="#2f5d62",
    percentile="#f39c12",
    rsi="#2f5d62",
    macd="#27ae60",
    signal="#f39c12",
    histogram="#95a5a6",
)
```

### 5.2 图表高度规范

| 图表类型 | 高度 | 说明 |
|---------|------|------|
| K线主图（含成交量） | 480px | 降低 40px，给 tab 空间 |
| RSI + MACD | 400px | 从 520 降到 400，更紧凑 |
| 因子评分 | 400px | 从 520 降到 400 |
| 净值对比 | 380px | 从 420 降到 380 |
| 交易信号 | 380px | 从 420 降到 380 |
| Walk-Forward | 380px | 从 420 降到 380 |
| 散点图 / 热图 | 400px | 保持 |

---

## 6. 实施优先级

### Phase 1（W6 必做）：结构性改动

| # | 改动 | 文件 | 预估工时 |
|---|------|------|---------|
| 1 | 侧边栏三级递进重构 | `ui/sidebar.py` | 2-3h |
| 2 | 单股页 tab 分区 | `ui/single_stock.py` | 3-4h |
| 3 | KPI 摘要卡添加 | `ui/single_stock.py` | 1h |
| 4 | CSS 全局样式注入 | `app.py` | 1-2h |
| 5 | 图表统一配色 | `core/visualization.py`, `ui/single_stock.py` | 2h |

### Phase 2（W7 增强）：视觉打磨

| # | 改动 | 文件 | 预估工时 |
|---|------|------|---------|
| 6 | 多股页 tab 分区 | `ui/multi_stock.py` | 2h |
| 7 | 图表模板统一函数 | 新建 `core/chart_theme.py` | 1h |
| 8 | 空状态提示美化 | 各 UI 文件 | 1h |
| 9 | 加载动画优化 | 各 UI 文件 | 0.5h |
| 10 | 导出报告样式升级（复用暖色调） | `ui/single_stock.py` 导出部分 | 1-2h |

### Phase 3（W7-W8 锦上添花）：

| # | 改动 | 说明 |
|---|------|------|
| 11 | 响应式布局微调 | 窄屏适配 |
| 12 | 首页摘要区 | 应用启动时的概览 |

---

## 7. 设计方案对比（供用户选择）

### 方案 A：暖色学术风（推荐）

即本文档描述的主方案。

**特点**：
- 暖米色背景 + 青绿强调色 + 赤陶辅助色
- 接近参考 HTML 的养眼感觉
- 专业但不冷硬
- 金融分析的严谨感与学术笔记的舒适感结合

**适合场景**：课程项目展示、作品集

### 方案 B：深色专业风

**特点**：
- 深灰背景 `#1e1e2f` + 亮青强调 `#00d4aa` + 橙色警告
- 类似 Bloomberg Terminal / TradingView 暗色模式
- 数据密度高，适合长时间盯盘
- 更"金融工程"风格

**适合场景**：量化交易演示、专业展示

**配色参考**：
```
page-bg:    #1e1e2f
card-bg:    #2a2a3e
ink:        #e0e0e0
accent:     #00d4aa
accent-2:   #ff6b6b
bull:       #ff4757
bear:       #2ed573
```

### 方案 C：极简白色风

**特点**：
- 纯白背景 + 深蓝强调 + 最小装饰
- 类似 Notion / Linear 的极简风格
- 干净、现代，但可能缺乏金融专业感

**配色参考**：
```
page-bg:    #ffffff
card-bg:    #f8f9fa
ink:        #1a1a2e
accent:     #3366ff
accent-2:   #ff3366
```

---

## 8. 与现有代码的兼容性

### 改动影响范围

| 文件 | 改动类型 | 风险 |
|------|---------|------|
| `app.py` | 添加 CSS 注入（新增 ~30 行） | 低 |
| `ui/sidebar.py` | 重构布局（逻辑不变，UI 调整） | 中 |
| `ui/single_stock.py` | Tab 分区包裹（内部函数不变） | 中 |
| `ui/multi_stock.py` | Tab 分区包裹（内部函数不变） | 中低 |
| `core/visualization.py` | 修改图表颜色和 layout | 低 |

### 不改动的部分

- `core/signals.py`：策略逻辑完全不动
- `core/backtest.py`：回测引擎完全不动
- `core/optimizer.py`：优化器完全不动
- `core/data.py`：数据处理不动
- `core/indicators.py`：指标计算不动
- 所有参数名、session_state key 保持不变
- `render_sidebar()` 返回的 dict 结构不变

---

## 附录：参考配色来源

本文档配色方案参考了以下来源：
- 用户提供的 MAT1002 学术笔记 HTML（暖色调、纸张质感、`#f4f1ea` / `#8f3b2e` / `#2f5d62`）
- 金融行业常用的涨跌色（中国市场惯例：红涨绿跌）
- Streamlit 暗色/亮色主题的最佳实践

将学术笔记的"养眼感"与金融分析的"专业感"融合，是本方案的核心设计思路。
