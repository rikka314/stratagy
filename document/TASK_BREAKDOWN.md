# 技术任务拆解表

> 基于 `document/SCOPE_FREEZE.md` 和 `document/MODULE_INTERFACES.md` 整合
> 整理时间：2026-03-19（Week 1 · Day 2/4 合并产出）
> 周期：2026-03-18 ~ 2026-05-12（8 周）

---

## 总览：每周改动文件 × 预估工时

| 周 | 主题 | 改动文件 | 新增文件 | 预估工时 |
|----|------|---------|---------|---------|
| W1 | 定范围 + 打底稳定 | optimizer.py, single_stock.py, AI_CONTEXT.md | SCOPE_FREEZE.md, MODULE_INTERFACES.md, TASK_BREAKDOWN.md, DATA_SCHEMA.md | 8-12h |
| W2 | A 股接入 | data.py, config.py, utils.py, sidebar.py, app.py | — | 12-20h |
| W3 | 评估模块 MVP | backtest.py, single_stock.py | core/evaluation.py | 20-32h |
| W4 | ML 信号过滤 MVP | single_stock.py, app.py | core/ml_filter.py | 24-40h |
| W5 | ML 样本外验证 | ml_filter.py, single_stock.py | — | 16-28h |
| W6 | 新策略模式 + UI 升级 | config.py, sidebar.py, single_stock.py, signals.py(可能) | core/strategy_modes.py | 16-24h |
| W7 | 评估增强 + UI 打磨 + 文档 | evaluation.py, visualization.py, single_stock.py, multi_stock.py | README/文档 | 12-20h |
| W8 | 验收 + bug 修复 + 交付 | 全模块 bugfix | 演示材料 | 16-24h |

**累计预估**：124-200h（8 周平均 15-25h/周）

---

## W1：定范围 + 打底稳定（03-18 ~ 03-24）

### 目标
冻结 8 周项目范围，梳理模块接口，统一数据规范。

### 技术任务

| 任务 | 涉及文件 | 改动类型 | 状态 |
|------|---------|---------|------|
| 范围冻结文档 | document/SCOPE_FREEZE.md | 新建 | ✅ 完成 |
| 模块接口梳理 + 依赖图 + 8 周改动标注 | document/MODULE_INTERFACES.md | 新建 | ✅ 完成 |
| 随机搜索接口对齐（23 参数全搜索 + 热启动） | core/optimizer.py | 重写函数 | ✅ 完成 |
| 调用方式对齐 + 方法检测修复 | ui/single_stock.py | 修改 | ✅ 完成 |
| 贝叶斯结果加 _method 标识 | core/optimizer.py | 修改 | ✅ 完成 |
| 依赖链描述 + 优化器说明修正 | AI_CONTEXT.md | 修改 | ✅ 完成 |
| 技术任务拆解表 | document/TASK_BREAKDOWN.md | 新建 | ✅ 完成 |
| 数据字段规范草案 | document/DATA_SCHEMA.md | 新建 | 待做 |
| 调研 AkShare A 股 API | — | 调研 | 待做 |
| A 股数据本地验证 | — | 测试 | 待做 |
| 评估指标清单 | 写入本文件 | 文档 | 待做 |
| UI 改版页面清单 | 写入本文件 | 文档 | 待做 |
| 提前加入 ML 依赖 | requirements.txt | 修改 | 待做 |

### 产出物

| 产出物 | 文件路径 | 完成日 |
|--------|---------|-------|
| 范围冻结文档 | `document/SCOPE_FREEZE.md` | Day 1 ✅ |
| 模块接口梳理 | `document/MODULE_INTERFACES.md` | Day 2 ✅ |
| 技术任务拆解表 | `document/TASK_BREAKDOWN.md` | Day 2 ✅ |
| 数据字段规范草案 | `document/DATA_SCHEMA.md` | Day 3 |
| 评估指标清单 | 本文件附录 A | Day 5 |
| UI 改版页面清单 | 本文件附录 B | Day 6 |

---

## W2：A 股接入 + 核心策略兼容（03-25 ~ 03-31）

### 目标
让系统正式支持 A 股基础分析，单股页面跑通 A 股。

### 前置条件
- [x] 数据字段规范已确定（W1 Day 3）
- [ ] AkShare A 股 API 已本地验证（W1 Day 4）
- [ ] `standardize_columns` 扩展方案已记录

### 技术任务

| 任务 | 涉及文件 | 改动详情 |
|------|---------|---------|
| A 股数据获取函数 | core/data.py | 新增 `fetch_a_stock(symbol, adjust)` 调用 `ak.stock_zh_a_hist` |
| 扩展列名映射 | core/data.py | `standardize_columns` 加中文→英文映射（日期→date, 开盘→open 等） |
| A 股默认列表 + 市场常量 | core/config.py | 加 `DEFAULT_A_STOCKS`、市场枚举 |
| 缓存加载适配 | core/utils.py | `load_or_fetch_stock` 加 `market` 参数分发 |
| 市场选择控件 | ui/sidebar.py | 加"美股/A股"单选 + A 股代码输入 |
| 路由传递市场参数 | app.py | 微调参数传递 |

### 不改的模块（确认）
- `indicators.py`：市场无关，只要 OHLCV 列对就行
- `signals.py`：市场无关
- `backtest.py`：市场无关
- `optimizer.py`：市场无关（内部调管道，自动适配）

### 验收标准
- [ ] 输入 A 股代码（如 000001），页面能加载数据并显示 K 线
- [ ] 指标计算、信号生成、回测均正常
- [ ] 美股功能不受影响

---

## W3：评估模块 MVP（04-01 ~ 04-07）

### 目标
抽离统一评估函数，补齐核心指标，嵌入单股页面。

### 前置条件
- [ ] 回测输出结构稳定（W2 完成后确认）

### 技术任务

| 任务 | 涉及文件 | 改动详情 |
|------|---------|---------|
| 统一评估输出格式 | core/backtest.py | 微调 `simulate_strategy` 返回值，确保 evaluation.py 可直接消费 |
| 新建评估模块 | **core/evaluation.py** | 第一批指标：累计收益、年化收益、最大回撤、夏普、胜率、盈亏比、换手率；基准对比 |
| 导出到 __init__.py | core/__init__.py | 加 evaluation 导出 |
| 评估区块嵌入 | ui/single_stock.py | 新增评估区：净值曲线、回撤曲线、统计表 |

### 指标计算口径（附录 A 详细版）

| 指标 | 公式 | 现有/新增 |
|------|------|----------|
| 累计收益 | `最终净值 / 初始净值 - 1` | 新增 |
| 年化收益 | `(最终净值/初始净值)^(252/交易天数) - 1` | 新增 |
| 最大回撤 | `max((peak - trough) / peak)` | 已有 |
| 夏普比率 | `mean(daily_return) / std(daily_return) × √252` | 已有 |
| 胜率 | `盈利交易次数 / 总交易次数` | 新增 |
| 盈亏比 | `平均盈利金额 / 平均亏损金额` | 新增 |
| 换手率 | `总交易次数 / 总天数` | 新增 |

### 验收标准
- [ ] 单股页面能展示完整评估区块
- [ ] 策略 vs 买入持有对比表

---

## W4：ML 信号过滤 MVP（04-08 ~ 04-14）

### 目标
完成第一个可验证的 ML 增强模块。

### 前置条件
- [ ] 指标字段稳定（W3 确认）
- [ ] 回测与标签口径一致

### 技术任务

| 任务 | 涉及文件 | 改动详情 |
|------|---------|---------|
| 新建 ML 过滤模块 | **core/ml_filter.py** | 样本构造 + 特征表构建 + Logistic/LightGBM 训练 + 预测 + 时间切分验证 |
| ML 相关 session_state | app.py | 微调 |
| ML 开关 + 结果展示 | ui/single_stock.py | ML 开关按钮 + 过滤前后对比 + 特征重要性图 |
| ML 依赖 | requirements.txt | `scikit-learn>=1.3.0`, `lightgbm>=4.0.0` |

### ML 过滤核心设计

```
输入：原策略产生的候选入场点
特征：factor_score, factor_percentile, 10 因子分量, RSI, MACD, ADX, ATR/close, volume_ratio, drawdown, trend_ok, entry_count
标签：未来 N 日是否获得正超额收益
模型：Logistic Regression + LightGBM
输出：每个信号的"通过概率"，超过阈值才允许入场
```

### 验收标准
- [ ] ML 开关可切换
- [ ] 能展示过滤前后的收益/回撤/夏普对比
- [ ] 特征重要性可查看

---

## W5：ML 样本外验证 + 策略增强联动（04-15 ~ 04-21）

### 目标
确认 ML 是否真的提升策略表现。

### 技术任务

| 任务 | 涉及文件 | 改动详情 |
|------|---------|---------|
| 滚动训练/验证 | core/ml_filter.py | 时间序列交叉验证 |
| 阈值控制 | core/ml_filter.py | 高置信度信号才放行 |
| 对比展示增强 | ui/single_stock.py | 多区间表现对比 |
| go/no-go 判断 | — | 决定是否进入第二增强项（市场状态识别） |

### 验收标准
- [ ] 样本外评估结果表
- [ ] ML 增强结论初稿

---

## W6：新策略模式 + UI 第一轮升级（04-22 ~ 04-28）

### 目标
补充项目丰富度，提升展示感。

### 技术任务

| 任务 | 涉及文件 | 改动详情 |
|------|---------|---------|
| 新策略模式预设 | core/config.py | 新增预设参数 |
| 新策略逻辑 | **core/strategy_modes.py** | 轻量策略（如均线趋势+波动过滤） |
| 信号扩展（如需） | core/signals.py | 可能 |
| 策略模式切换 + ML 开关 | ui/sidebar.py | UI 控件 |
| 首页摘要卡 + 模式切换 | ui/single_stock.py | UI 改版 |

### 验收标准
- [ ] 至少一个新策略模式可运行
- [ ] UI 页面结构更清晰

---

## W7：评估增强 + UI 打磨 + 文档（04-29 ~ 05-05）

### 技术任务

| 任务 | 涉及文件 | 改动详情 |
|------|---------|---------|
| 评估增强 | core/evaluation.py | 第二批指标：Calmar、Sortino、平均持有天数、最大连续亏损；分区间表现、参数对比 |
| 图表风格统一 | core/visualization.py | 配色、字体、边距、图例位置 |
| UI 打磨 | single_stock.py, multi_stock.py | 空状态提示、加载动画、配色统一 |
| 文档 | README.md + 使用说明 | — |

---

## W8：验收冲刺 + 修 bug + 打包交付（05-06 ~ 05-12）

### 技术任务

| 任务 | 涉及文件 |
|------|---------|
| 全模块 bugfix | 全部 |
| 完整验收：美股/A 股、原策略、新策略、ML、评估、UI | — |
| 演示材料 | document/ |
| 已知问题清单 | document/ |

---

## 模块级改动时间线（速查）

```
                W1    W2    W3    W4    W5    W6    W7    W8
config.py       ·     ██    ·     ·     ·     ██    ·     ·
data.py         ·     ██    ·     ·     ·     ·     ·     ·
indicators.py   ·     ·     ·     ·     ·     ·     ·     ·
signals.py      ·     ·     ·     ·     ·     ░░    ·     ·
backtest.py     ·     ·     ░░    ·     ·     ·     ·     ·
optimizer.py    ██    ·     ·     ·     ·     ·     ·     ·
utils.py        ·     ██    ·     ·     ·     ·     ·     ·
visualization   ·     ·     ·     ·     ·     ·     ██    ·
portfolio.py    ·     ·     ·     ·     ·     ·     ·     ·
evaluation.py   ·     ·     ▓▓    ·     ·     ·     ██    ·
ml_filter.py    ·     ·     ·     ▓▓    ██    ·     ·     ·
strategy_modes  ·     ·     ·     ·     ·     ▓▓    ·     ·
sidebar.py      ·     ██    ·     ·     ·     ██    ·     ·
single_stock    ·     ·     ██    ██    ██    ██    ██    ░░
multi_stock     ·     ·     ·     ·     ·     ·     ██    ░░
app.py          ·     ░░    ·     ░░    ·     ·     ·     ·

██ = 主要改动   ░░ = 微调   ▓▓ = 新建文件   · = 不动
```

---

## 依赖链（周级别）

```
W1 范围冻结 + 数据规范
 └→ W2 A 股接入（依赖：数据规范）
     └→ W3 评估模块（依赖：回测输出稳定）
         └→ W4 ML 信号过滤（依赖：指标字段稳定）
             └→ W5 ML 验证（依赖：W4 模型可跑）
                 └→ W6 新策略 + UI（依赖：评估模块完成）
                     └→ W7 增强 + 文档（依赖：核心功能冻结）
                         └→ W8 验收（依赖：前 7 周稳定）
```

---

## 附录 A：评估指标清单

### 第一批（W3 必做）

| 指标 | 计算口径 | 现有/新增 |
|------|---------|----------|
| 累计收益 | `最终净值 / 初始净值 - 1` | 新增 |
| 年化收益 | `(最终净值/初始净值)^(252/交易天数) - 1` | 新增 |
| 最大回撤 | `max((peak - trough) / peak)` | 已有 `max_drawdown` |
| 夏普比率 | `mean(daily_return) / std(daily_return) × √252` | 已有 `sharpe_ratio` |
| 胜率 | `盈利交易次数 / 总交易次数` | 新增 |
| 盈亏比 | `平均盈利金额 / 平均亏损金额` | 新增 |
| 换手率 | `总交易次数 / 总天数` | 新增 |

### 第二批（W7 增强）

| 指标 | 计算口径 |
|------|---------|
| Calmar 比率 | `年化收益 / \|最大回撤\|` |
| Sortino 比率 | `mean(daily_return) / std(负收益) × √252` |
| 平均持有天数 | `总持有天数 / 总交易次数` |
| 最大连续亏损次数 | 连续亏损交易的最长序列 |

### 对比维度

- 策略 vs 买入持有
- 原策略 vs ML 增强
- 不同参数组对比

---

## 附录 B：UI 改版页面清单

### 改版后页面结构

```
侧边栏（sidebar.py）
├── 市场选择：美股 / A股（W2）
├── 股票代码输入 / 选择
├── 日期范围
├── 策略预设选择
├── 策略模式切换（W6）
├── ML 开关（W4）
└── 高级参数（折叠）

单股分析页（single_stock.py）
├── 顶部：KPI 摘要卡（收益、回撤、夏普、信号状态）
├── 主图区：K线 + 信号标记
├── 指标区：RSI / MACD / 因子评分
├── 评估区（W3）：净值曲线、回撤曲线、统计表
├── ML 区（W4）：过滤前后对比、特征重要性
└── 导出区

多股对比页（multi_stock.py）
├── 归一化价格对比
├── 相关性热图
├── 风险收益散点
└── 组合模拟
```

### UI 改动优先级

| 优先级 | 内容 | 对应周 |
|--------|------|-------|
| P0 | 市场选择控件 | W2 |
| P0 | 评估区块嵌入单股页 | W3 |
| P1 | ML 开关和结果展示区 | W4 |
| P1 | 策略模式切换、首页摘要卡、图表风格统一 | W6 |
| P2 | 配色统一、空状态提示、加载动画 | W7 |

### 配色方向

- 浅底 + 深灰文字 + 单一强调色
- 图表统一：字体大小、边距、图例位置
- 涨跌色：需确认 A 股红涨绿跌 vs 美股绿涨红跌的处理方式
