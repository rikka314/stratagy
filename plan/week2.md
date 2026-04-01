# 第2周计划 · A 股接入 + 核心策略兼容

**生成日期：** 2026-03-21  
**参考文件：** `plan/金融学期总计划.md` 第2周 + `AI_CONTEXT.md`

---

### 第2周 · 主题：A 股接入 + 核心策略兼容

**本周目标（一句话）：** 让系统正式支持 A 股日线数据分析，单股页面对至少 3 只 A 股完整跑通。

---

## 大任务 1：实现 `fetch_a_stock()` 数据层

> 背景：W1 已确认 `ak.stock_zh_a_hist` 可用，字段规范写入了 `DATA_SCHEMA.md`，`standardize_columns()` 的扩展边界也已明确。现在要把约定落成代码。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 1.1 | 在 `core/data.py` 里新写 `fetch_a_stock(symbol, adjust="qfq")`：调用 `ak.stock_zh_a_hist`，处理返回 DataFrame，写入缓存 | Claude Pro | 需要同时看 `data.py` 现有结构 + `DATA_SCHEMA.md` 约定，保持接口一致 |
| 1.2 | 扩展 `standardize_columns()` 的别名映射表，补全 A 股字段：`成交量(手)→volume(股)×100`、`日期→date`、`开盘→open` 等 | 云端 DeepSeek | 单文件修改，查表型任务，中文字段映射文档也在同一对话里 |
| 1.3 | 在 `fetch_a_stock()` 里加异常处理：代码不存在 / AkShare 请求超时 / 极早期 qfq 负价格过滤，输出统一 `st.error()` 提示 | 云端 DeepSeek | 错误提示文案是中文，单文件修改 |
| 1.4 | 扩展 `load_or_fetch_stock()` 支持 market 参数，根据 `market="A"` 路由到 `fetch_a_stock()` | Claude Pro | 跨 `utils.py` 和 `data.py` 保持接口对齐，避免破坏现有美股路径 |

**产出物：** `core/data.py` 新增 `fetch_a_stock()`；`standardize_columns()` 支持 A 股别名；`load_or_fetch_stock()` 支持 market 参数。

---

## 大任务 2：侧边栏 - 市场选择 + A 股代码输入

> 背景：`ui/sidebar.py` 目前只有美股逻辑，`render_sidebar()` 返回的 dict 里没有 market 字段。需要加入市场切换，并让 A 股代码格式正确传入。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 2.1 | 在侧边栏顶部加 `市场选择` Radio（美股 / A 股），`render_sidebar()` 返回 `params["market"]` | Claude Pro | `sidebar.py` 很长（~481行），改 dict 结构会影响 `app.py` 的所有调用点，需要全局视角 |
| 2.2 | 根据 `market` 切换股票输入逻辑：A 股改为 6 位数字代码输入框（如 `600519`），加格式校验（`re.match(r"^\d{6}$")`） | 云端 DeepSeek | 逻辑独立，单段代码修改 |
| 2.3 | 补充 A 股默认样本股列表（至少 5 只：贵州茅台 600519、宁德时代 300750、中国平安 601318、比亚迪 002594、招商银行 600036） | 云端 DeepSeek | 纯内容填充，不涉及架构 |
| 2.4 | `app.py` 路由层：根据 `params["market"]` 选择调用 `load_or_fetch_stock(symbol, market=market)` | Claude Pro | `app.py` 是入口，改这里需要知道 `fetch_a_stock` 和 `load_or_fetch_stock` 的完整接口签名 |

**产出物：** 侧边栏新增市场选择控件；A 股代码输入+校验；`params` dict 新增 `market` 字段；`app.py` 路由更新。

---

## 大任务 3：单股页联调 - 跑通 A 股完整流程

> 背景：`ui/single_stock.py`（~1030行）承载了从 K 线到回测到优化的完整单股分析逻辑。A 股在日期格式、涨跌色、代码显示上有差异，需要逐块验证。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 3.1 | 用贵州茅台（600519）跑一遍单股页，记录所有报错（字段缺失、类型错误、日期格式、空数据等）——先不改代码，先收集问题清单 | 本人手动操作 | 这步需要肉眼看报错和页面，AI 无法替代 |
| 3.2 | 修复字段类型/日期问题：A 股 date 列可能是 `object` 类型，确保 `ensure_date_column()` 在 `fetch_a_stock()` 调用时已处理 | Claude Pro | 涉及 `data.py` + `indicators.py` 两个文件的类型流，需要联动 |
| 3.3 | 涨跌色适配：A 股惯例红涨绿跌，检查 `core/visualization.py` 和 `ui/single_stock.py` 的买卖信号颜色，根据 market 参数切换 | 云端 DeepSeek | 配色是局部改动，参考 `UI_DESIGN_GUIDE.md` 里已确认的 `#c0392b`/`#27ae60` |
| 3.4 | 联调测试 3 只 A 股（600519 贵州茅台 / 300750 宁德时代 / 601318 中国平安），确认 K 线、RSI/MACD、因子评分图正常渲染，策略建议区有输出 | 本人手动操作 | 功能验收 |
| 3.5 | 部署到云服务器，验证云端 A 股数据拉取正常（服务器访问 AkShare 是否有网络限制需核实） | Claude Pro | `scp` + `systemctl restart` 需要多步执行，且若有网络问题需要查日志排查 |

**产出物：** A 股单股页面完整跑通；3 只 A 股样例截图/验收记录；云端部署更新。

---

## 大任务 4：文档 + 接口更新（轻量）

> 背景：`AI_CONTEXT.md` 和 `document/MODULE_INTERFACES.md` 记录了模块接口，本周新增的函数签名需要同步。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 4.1 | 更新 `document/MODULE_INTERFACES.md`：补充 `fetch_a_stock()` 签名、`load_or_fetch_stock()` 新增 `market` 参数 | 云端 DeepSeek | 文档写作，中文，单文件 |
| 4.2 | 更新 `AI_CONTEXT.md`：在 `core/data.py` 代码地图里补 `fetch_a_stock`，在文档维护状态里记录 W2 完成内容 | Claude Pro（本对话结束时） | 本文件是项目最高优先上下文，且这是每次会话结束的标准收尾动作 |

**产出物：** `MODULE_INTERFACES.md` 接口更新；`AI_CONTEXT.md` W2 状态记录。

---

## 本周资源分配建议

| 工具 | 预计用量 | 主要用途 |
|------|---------|---------|
| Claude Pro | 高 | `fetch_a_stock()` + `load_or_fetch_stock()` 联动、侧边栏 dict 结构改造、日期类型联调、云端部署排错、`AI_CONTEXT.md` 更新 |
| 云端 DeepSeek-v3.1 | 中 | 字段别名映射表、异常提示文案、A 股默认股票列表、涨跌色局部修改、`MODULE_INTERFACES.md` 文档写作 |
| GPT-5 | 低 | AkShare 接口有疑问时查阅文档或第二意见 |
| Gemini | 低 | 如果 `single_stock.py` 联调需要整体理解这个 1030 行文件 |

**可外包给其他 AI 的比例：约 35%**

---

## 风险提示

### 风险1：云端服务器无法访问 AkShare

AkShare 的 A 股数据源部分依赖国内网络（东方财富等），服务器 IP 是 `115.191.68.122`，需要在部署后立刻用 `journalctl` 查日志确认 `ak.stock_zh_a_hist` 是否能正常返回数据。

**应对**：先在本地 Windows 开发环境跑通大任务 3 的联调（tasks 3.1-3.4），确认逻辑无误后再部署；若云端确实无法访问，考虑把 A 股数据通过本地 CSV 上传功能临时绕过，主流程先通，网络问题再单独解决。

### 风险2：侧边栏 dict 结构改动破坏现有美股逻辑

`render_sidebar()` 返回的 dict 被 `app.py`、`ui/single_stock.py`、`ui/multi_stock.py` 多处使用，新增 `market` 字段如果处理不当会引发 KeyError。

**应对**：在 `market` 字段加默认值 `"US"`，确保所有现有调用路径在未设置 market 时行为不变；改完后先跑美股路径回归验证，再测 A 股。

---

## 落后时裁剪优先级

1. 先只做日线，不支持分钟/周线
2. 先只支持单股页，不扩展多股对比页的 A 股逻辑
3. 涨跌色适配（3.3）可延后到 W6 UI 统一优化时处理
4. 云端部署（3.5）若有网络问题可暂时只在本地验收，不影响主线交付
