# 第 1 周详细计划：定范围 + 打底稳定

> 对应总计划：[金融学期总计划.md](金融学期总计划.md) 第 1 周
> 时间：2026-03-18 ~ 2026-03-24（7 天）
> 预估工时：8~12h（正常节奏）

> **📌 进度追踪**：本文档以 `[x]` 标记为准——标记了 `[x]` 的任务表示已实际完成，`[ ]` 的任务表示尚未开始或进行中。查看最新进度时，请直接看各任务条目前的勾选状态。

---

## 本周目标

冻结 8 周项目范围，确定交付边界，补齐核心技术底座。

具体来说：
1. 把"要做什么、不做什么"写成文档，后续不再讨论范围
2. 梳理现有代码接口，确认哪些模块需要改、哪些不动
3. 统一美股/A 股数据字段规范，为第 2 周 A 股接入铺路
4. 列出评估模块指标清单，明确多模型评估方式，并画出 UI 改版页面结构

---

## 当前项目状态（Week 1 起点）

| 维度 | 现状 |
|------|------|
| 项目结构 | `app.py` + `core/`(9模块) + `ui/`(3模块)，模块化完成 |
| 数据源 | 仅美股（`ak.stock_us_daily`），A 股获取未实现 |
| 数据标准化 | `standardize_columns` 已映射 `trade_date→date`、`vol→volume`，有 A 股 CSV 兼容基础 |
| 策略逻辑 | `compute_signals` 市场无关，只要 DataFrame 列名对就能跑 |
| 回测 | `simulate_strategy` + `walk_forward_backtest` 已完成 |
| 优化器 | 随机搜索 + 贝叶斯(Optuna) + 遗传算法 三种均已实现 |
| ML | 尚未开始，核心代码尚未接入 ML；`requirements.txt` 已提前加入 scikit-learn / lightgbm |
| 评估 | `sharpe_ratio` + `max_drawdown` 已有，缺完整评估模块 |
| UI | 功能完整但风格偏实验页面，未系统优化 |
| 部署 | 服务器 115.191.68.122:8501 可运行 |

## 状态维护约定

- 本文档中的任务在实际完成后，需同步将对应标记从 `[ ]` 更新为 `[x]`
- 如完成状态为补记，应在相关条目下补充简短说明或把结果落到对应产出文档

---

## 每日任务拆解

### Day 1（周二）：范围冻结

**目标**：产出范围冻结文档，把 8 周的交付边界写死。

- [x] **任务 1.1**：确认"做 / 建议做 / 不做"清单
  - 必做：A 股接入、信号过滤 ML、基础评估、UI 一轮优化
  - 建议做：市场状态识别原型、新轻量策略模式
  - 不做：LSTM/Transformer、RL、复杂多资产框架、生产级归因系统
- [x] **任务 1.2**：写范围冻结文档 → `document/SCOPE_FREEZE.md`
  - 内容：项目定位、最低/标准/理想三档交付目标、明确排除项
  - 篇幅：1~2 页，简洁即可
- [x] **任务 1.3**：确认 ML 主模块选择
  - 结论：第一模块 = 信号过滤（Logistic + LightGBM）
  - 记录理由：最贴合现有 `compute_signals` 输出，改动最小，可验证性最高
  - 已落盘到 `document/SCOPE_FREEZE.md`

**产出**：`document/SCOPE_FREEZE.md`

---

### Day 2（周三）：模块接口梳理

**目标**：理清现有代码的接口边界和依赖方向。

- [x] **任务 2.1**：梳理核心模块接口
  - `core/data.py`：5 个函数，输入/输出类型，当前只有 `fetch_data` 调用 `stock_us_daily`
  - `core/indicators.py`：`add_indicators(df, params)` → 返回带指标列的 df
  - `core/signals.py`：`compute_signals(df, ~30个参数)` → 返回带信号列的 df
  - `core/backtest.py`：`simulate_strategy(df, ...)` → 返回带权益曲线的 df
  - `core/optimizer.py`：3 种优化函数，均接受 df + 参数范围 + callback
- [x] **任务 2.2**：画模块依赖图（文字版或 Mermaid）
  ```
  config ← data ← indicators ← signals ← backtest ← optimizer
                                                    ← portfolio
  ui/sidebar → params dict → app.py → ui/single_stock
                                     → ui/multi_stock
  ```
- [x] **任务 2.3**：标注每个模块在 8 周中需要改动的范围
  - `data.py`：第 2 周改（加 A 股 fetch）
  - `config.py`：第 2 周改（加 A 股默认列表 + 市场选择）
  - `signals.py`：不改（市场无关）
  - `backtest.py`：第 3 周微调（统一评估输出）
  - 新增 `core/evaluation.py`：第 3 周
  - 新增 `core/ml_filter.py`：第 4 周
  - `ui/sidebar.py`：第 2、6 周改
  - `ui/single_stock.py`：第 3、4、6 周改
  - 已落盘到 `document/MODULE_INTERFACES.md`

**产出**：接口梳理记录（可写入技术任务拆解表）

---

### Day 3（周四）：数据字段规范

**目标**：定义美股/A 股共用的标准 DataFrame 列结构。

- [x] **任务 3.1**：调研 AkShare A 股 API
  - `ak.stock_zh_a_hist(symbol, period, start_date, end_date, adjust)`
  - 返回列名：日期、开盘、收盘、最高、最低、成交量、成交额、振幅、涨跌幅、涨跌额、换手率
  - 需要映射到标准列：date, open, high, low, close, volume
- [x] **任务 3.2**：写数据字段规范草案 → `document/DATA_SCHEMA.md`
  - 标准列定义（必须列 + 可选列）
  - 美股源字段映射表
  - A 股源字段映射表
  - 数据类型约束（date=datetime64, OHLCV=float64）
  - 缺失值处理规则
- [x] **任务 3.3**：确认 `standardize_columns` 是否需要扩展
  - 当前映射：`trade_date→date`, `datetime→date`, `vol→volume`, `volumn→volume`
  - A 股新增映射：`日期→date`, `开盘→open`, `收盘→close`, `最高→high`, `最低→low`, `成交量→volume`
  - 已落盘到 `document/DATA_SCHEMA.md`

**产出**：`document/DATA_SCHEMA.md`

---

### Day 4（周五）：A 股数据源验证 + 技术任务拆解

**目标**：实际跑通 A 股数据获取，产出 8 周技术任务拆解表。

- [x] **任务 4.1**：本地验证 A 股数据获取
  - 在 Python REPL 中测试 `ak.stock_zh_a_hist("000001", period="daily", adjust="qfq")`
  - 确认返回字段、数据量、耗时
  - 测试 2-3 只股票，记录差异
  - 2026-03-20 已在本地 `.venv` 中完成验证：Python 3.13.7，`akshare 1.18.21`
  - 实测样本：`000001`（8358 行，0.677s）、`600519`（5883 行，0.662s）、`300750`（1886 行，0.537s）
  - 返回字段稳定为 12 列：`日期/股票代码/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率`
  - 已记录差异：数据量随上市时间变化；`adjust="qfq"` 的极早期数据可能出现负价格或极端百分比，W2 接入时需作为已知风险处理
- [x] **任务 4.2**：产出技术任务拆解表 → `document/TASK_BREAKDOWN.md`
  - 按周拆解，每周列出：改哪些文件、新增哪些文件、预估工时
  - 标注前后依赖关系
  - 格式：Markdown 表格

| 周 | 主要改动文件 | 新增文件 | 预估工时 |
|----|------------|---------|---------|
| W2 | data.py, config.py, sidebar.py | — | 12-20h |
| W3 | backtest.py, single_stock.py | core/evaluation.py | 20-32h |
| W4 | — | core/ml_filter.py | 24-40h |
| W5 | ml_filter.py, single_stock.py | — | 16-28h |
| W6 | sidebar.py, single_stock.py | core/strategy_modes.py | 16-24h |
| W7 | evaluation.py, UI 各页面 | — | 12-20h |
| W8 | bug fixes, 文档 | 演示材料 | 16-24h |

**产出**：`document/TASK_BREAKDOWN.md`

---

### Day 5（周六）：评估模块指标清单

**目标**：定义评估模块要算哪些指标、怎么展示，以及如何比较多个模型。

- [x] **任务 5.1**：列出评估指标清单
  - **第一批（W3 必做）**：累计收益、年化收益、最大回撤、夏普比率、胜率、盈亏比、换手率
  - **第二批（W7 增强）**：Calmar 比率、Sortino 比率、平均持有天数、最大连续亏损次数
  - **模型质量层（W5/W7）**：Precision、Recall、F1、PR-AUC、校准、信号通过率
  - **对比维度**：策略 vs 买入持有、原策略 vs ML 增强、Logistic vs LightGBM、不同参数组对比、单股 vs 多股
- [x] **任务 5.2**：定义评估指标的计算口径
  - 年化收益：`(最终净值/初始净值)^(252/交易天数) - 1`
  - 最大回撤：`max((peak - trough) / peak)`（已有 `max_drawdown` 函数）
  - 夏普比率：`mean(daily_return) / std(daily_return) * sqrt(252)`（已有 `sharpe_ratio` 函数）
  - 胜率：`盈利交易次数 / 总交易次数`
  - 盈亏比：`平均盈利金额 / 平均亏损金额`
  - PR-AUC：基于预测概率与标签的 precision-recall 曲线面积
  - 校准：预测概率与真实命中率的一致性，可用 reliability curve / Brier score 辅助
- [x] **任务 5.3**：确认现有代码中已有和缺失的指标
  - 已有：`max_drawdown`、`sharpe_ratio`（在 `backtest.py`）
  - 缺失：年化收益、胜率、盈亏比、换手率、Calmar、Sortino
  - 已补充核对结论：`simulate_strategy()` 已输出 `position/strategy_return/strategy_equity/buy_hold_equity`，足够支撑累计收益、年化收益和基准对比；逐笔型指标仍需 W3 在 `core/evaluation.py` 中重建 trade-level 信息
  - 额外结论：模型质量层指标与多模型比较结构不应塞进 `backtest.py`，应由后续 `core/evaluation.py` + `core/ml_filter.py` 统一输出比较结果

**产出**：评估指标清单（写入技术文档或单独文件）

---

### Day 6（周日）：UI 设计方案

**目标**：诊断现有 UI 问题，产出完整的 UI 设计指导文档。

> 本日任务聚焦两个核心问题：①侧边栏和主页面都需要频繁下拉；②视觉风格缺乏统一设计。
> 详细方案见 `document/UI_DESIGN_GUIDE.md`。

- [x] **任务 6.1**：诊断现有 UI 问题
  - 侧边栏：~30 个 slider + 长文字说明，纵向约 2500px，需滚动 4-5 屏
  - 单股页：10 个区块线性堆叠，主内容区超过 4000px
  - 共性问题：无 KPI 摘要卡、图表配色不统一、无 tab 分区、缺乏视觉层次
  - 已落盘到 `document/UI_DESIGN_GUIDE.md` 第 1 节

- [x] **任务 6.2**：确定配色方案
  - 参考用户喜欢的学术笔记 HTML 配色（暖米色 `#f4f1ea` + 青绿 `#2f5d62` + 赤陶 `#8f3b2e`）
  - 定义完整色板：背景色、文字色、强调色、金融语义色（涨跌/基准）、功能色
  - 定义图表配色规则和 KPI 卡片配色规则
  - 提供 3 套方案供选择：A-暖色学术风（推荐）、B-深色专业风、C-极简白色风
  - 已落盘到 `document/UI_DESIGN_GUIDE.md` 第 2 节

- [x] **任务 6.3**：设计布局重构方案
  - **侧边栏**：渐进式展示（3 级递进），从 ~2500px 压缩到 ~800px
    - L1 始终可见：股票选择 + 日期 + 策略预设 + 入场/出场 slider
    - L2 折叠：添加/上传、复权方式
    - L3 折叠：高级参数（2 列并排布局）
  - **单股页**：KPI 摘要卡 + `st.tabs` 5 分区（图表/回测/滚动验证/策略优化/导出）
  - **多股页**：同样 tab 分区（价格对比/风险分析/因子对比/组合模拟）
  - 已落盘到 `document/UI_DESIGN_GUIDE.md` 第 3 节

- [x] **任务 6.4**：定义图表统一规范 + 实施优先级
  - Plotly 图表模板（统一 layout、配色、图例）
  - 图表高度规范（K线 480px、指标 400px、净值 380px 等）
  - Phase 1（W6）：结构性改动 ~10h / Phase 2（W7）：视觉打磨 ~5h
  - 改动影响范围和兼容性确认（core/ 逻辑模块全部不动）
  - 已落盘到 `document/UI_DESIGN_GUIDE.md` 第 5-8 节

**产出**：`document/UI_DESIGN_GUIDE.md`

---

### Day 7（周一）：汇总 + 自检 + 依赖确认

**目标**：确认所有产出物齐全，检查第 2 周依赖项。

- [x] **任务 7.1**：汇总本周产出物，逐项检查

  | 产出物 | 文件 | 状态 |
  |--------|------|------|
  | 范围冻结文档 | `document/SCOPE_FREEZE.md` | ✅ 完成 |
  | 技术任务拆解表 | `document/TASK_BREAKDOWN.md` | ✅ 完成 |
  | 数据字段规范草案 | `document/DATA_SCHEMA.md` | ✅ 完成 |
  | UI 设计指导文档 | `document/UI_DESIGN_GUIDE.md` | ✅ 完成 |

- [x] **任务 7.2**：确认第 2 周前置条件
  - [x] AkShare A 股 API 已本地验证可用
  - [x] 列名映射方案已确定
  - [x] `standardize_columns` 扩展方案已记录
  - [x] 项目在 macOS 和 Windows 均可稳定运行（`streamlit run app.py`）
    - 2026-03-20 已在 Windows 本地 `.venv` 短时启动验证，成功返回 `Local URL: http://localhost:8765`
    - macOS 未在本会话中实机重跑；基于 `app.py + core/ + ui/` 无明显 OS 绑定代码路径、且项目已有双端协作记录，判断可运行（推断）
- [x] **任务 7.3**：更新 `AI_CONTEXT.md`（如有结构变化）
- [x] **任务 7.4**：更新 `requirements.txt`（如需提前加入 ML 依赖）
  - 建议提前加入：`scikit-learn>=1.3.0`、`lightgbm>=4.0.0`
  - 不急着加：`catboost`（体积大，等真正用到再加）
  - 2026-03-20 已提前加入 `scikit-learn` 和 `lightgbm`，并在当前 `.venv` 安装验证（`scikit-learn 1.8.0`、`lightgbm 4.6.0`）

**产出**：本周总结 + 第 2 周 ready 检查

**Week 2 ready 结论**：
- A 股 API、字段规范、列名映射、UI 设计方案均已准备完成
- Windows 本地启动检查通过；macOS 依据代码路径与协作现状判断可运行
- W2 可直接进入 A 股接入实现

---

## 本周产出物汇总

| # | 产出物 | 文件路径 | 完成日 |
|---|--------|---------|-------|
| 1 | 范围冻结文档 | `document/SCOPE_FREEZE.md` | Day 1 |
| 2 | 模块接口梳理 | `document/MODULE_INTERFACES.md` | Day 2 |
| 3 | 数据字段规范草案 | `document/DATA_SCHEMA.md` | Day 3 |
| 4 | 技术任务拆解表 | `document/TASK_BREAKDOWN.md` | Day 4 |
| 5 | 评估指标清单 | `document/TASK_BREAKDOWN.md`（附录 A） | Day 5 |
| 6 | UI 设计指导文档 | `document/UI_DESIGN_GUIDE.md` | Day 6 |
| 7 | 第 2 周 ready 检查 | 本节 Day 7 记录 + `AI_CONTEXT.md` | Day 7 |

---

## AI 工具分工建议

| 任务 | 推荐工具 | 理由 |
|------|---------|------|
| 范围冻结文档撰写 | DeepSeek-v3.1 | 中文文档撰写，单文件，不需要项目上下文 |
| 模块接口梳理 | Claude Pro | 需要读多文件、理解跨模块依赖 |
| A 股 API 调研 | DeepSeek-v3.1 / GPT-5 | 信息检索类，查 AkShare 文档 |
| 数据字段规范草案 | DeepSeek-v3.1 | 文档撰写，基于调研结果 |
| 技术任务拆解表 | Claude Pro | 需要理解整体项目架构来拆解 |
| 评估指标清单 | DeepSeek-v3.1 | 标准金融知识，不依赖代码上下文 |
| UI 页面结构设计 | Claude Pro | 需要理解现有 UI 代码结构 |
| A 股数据本地验证 | 手动 / Claude Pro | 实际跑代码 |

**原则**：Claude Pro 只用于需要跨文件上下文理解的任务，文档类和调研类优先外包。

---

## 依赖项

- [x] 当前项目可稳定运行（macOS + Windows）
- [x] AkShare 版本 ≥ 1.12.0，支持 `stock_zh_a_hist`
- [x] 网络可访问 AkShare 数据源

## 风险

| 风险 | 影响 | 应对 |
|------|------|------|
| A 股数据源字段差异大 | 第 2 周 A 股接入工作量增加 | Day 3 提前调研，写好映射表 |
| 范围膨胀 | 整体延期 | Day 1 严格冻结，写入文档 |
| AkShare A 股 API 不稳定 | 无法按时获取数据 | Day 4 实际测试，备选方案：CSV 手动导入 |
| 本周文档工作量被低估 | 挤占后续开发时间 | 文档控制在 1~2 页，不追求完美 |

## 落后时裁剪

如果本周进度不及预期，按以下顺序裁剪：
1. UI 页面清单推迟到第 2 周初
2. 评估指标清单简化为一个列表（不写详细计算口径）
3. 模块接口梳理只做关键 3 个模块（data, signals, backtest）
4. **不能砍**：范围冻结文档、数据字段规范草案
