# 第5周计划 · 单股页策略工作流重构落地 + UI 第一轮收束

**生成日期：** 2026-03-26  
**工作量：** ≈ 原 W6 前半 + 单股页重构实现  
**参考文件：** `plan/金融学期总计划.md` 第5周 + `AI_CONTEXT.md` + `plan/model-change/workflow-restructure.md` + `plan/model-change/day1-3.md` + `plan/model-change/day4-5.md` + `plan/model-change/day6-7.md`

---

### 第5周 · 主题：单股页策略工作流重构落地 + UI 第一轮收束

**本周目标（一句话）：** 把当前单股页从“页面加载即一次性计算多模型”改成“先选模型、再生成策略、再基于 artifact 做分析与比较”的工作流，并完成第一轮界面收束与回归验收。

---

## 当前起步判断（2026-03-26）

- W4 已按“功能落地 + 2 组样本外结果留痕”收口，W5 不再继续补 FSM / ML-SM 新功能。
- 当前 [`ui/single_stock.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\ui\single_stock.py) 仍是“页面加载 -> 直接算指标 -> 直接算 SM/FSM/ML 测试期 payload -> 直接渲染结果”的旧结构，和 `plan/model-change/` 已冻结的工作流语义不一致。
- 当前高级搜索结果仍通过 [`app.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\app.py) 的 `apply_best_params` / `best_params` 回写侧边栏，这与 W5 文档里“搜索结果默认不回写 widget”存在明确冲突。
- 因此 W5 主线不是“加模型”，而是“改单股页的编排方式、状态边界、下游读取口径和交互顺序”。

### W5 范围冻结

- 只改单股页策略工作流及其直接依赖模块。
- `Walk-Forward` 只保留为 `current_artifact` 专属区块，不并入策略库。
- 多股页模型汇总看板、策略库持久化、自定义保存名称、整体视觉大改版继续顺延，不纳入 W5 完成标准。

---

## 大任务 1：落地策略编排层与 `strategy_workspace`

> 背景：W5 的核心不是“再写几个 if-else”，而是把策略生成从 [`ui/single_stock.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\ui\single_stock.py) 中抽出来，形成可维护的请求对象、artifact 对象、stage runner 和会话级 workspace。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 1.1 | 确定新模块落点，建议新增单独的编排模块（如 `ui/single_stock_workflow.py` 或同等职责文件），不要继续把 `run_strategy_pipeline()`、stage runner 和 `session_state` 操作塞回 `single_stock.py` | Claude Pro | 这是跨文件架构落点决策，会影响后续所有实现和文档同步 |
| 1.2 | 定义 `StrategyRequest`、`stage_result`、`StrategyArtifact`、`strategy_workspace` 的最小字段，字段严格对齐 `plan/model-change/day1-5` 已冻结语义 | Claude Pro | 字段一旦定错，后面下游区块和 cache 都会返工 |
| 1.3 | 实现 `context_key` 生成与 workspace 初始化/清空辅助函数，至少覆盖 `market / symbol或uploaded_data / date_range / train_ratio / adjust` 等失效边界 | 云端 DeepSeek-v3.1 | 规则已经在文档中冻结，适合按规格实现辅助函数骨架 |
| 1.4 | 实现 `run_baseline_path()`、`run_sm_base_stage()`、`run_fsm_base_stage()`、`run_search_stage()`、`run_ml_stage()` 与 `assemble_strategy_artifact()` | Claude Pro | 这里要同时理解 `core/signals.py`、`core/fa_filter.py`、`core/ml_filter.py`、`core/backtest.py`、`core/evaluation.py` 的接口拼接 |
| 1.5 | 把当前 `_build_test_model_payloads()` 中的 SM/FSM/ML 测试期逻辑拆成“按请求触发”的 stage 组合，不再保留“页面加载就把 7 个模型都算完”的默认流程 | Claude Pro | 这是 W5 的实质性结构变更，需要重写 `single_stock.py` 的数据流 |

**产出物：** 独立的策略编排层模块；`StrategyRequest / StrategyArtifact / strategy_workspace` 落地；单股页不再默认全模型 eager compute。

---

## 大任务 2：把单股页改成五段式主区工作流

> 背景：目前单股页的 `策略建议`、`高级策略搜索`、`测试集表现`、`交易信号` 是直接堆叠的，用户没有先完成模型路径选择，也没有 artifact 概念。W5 需要按文档改成“生成前”和“生成后”两个区域。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 2.1 | 重排 [`ui/single_stock.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\ui\single_stock.py) 主区顺序为：工作台入口/空状态 → 模型配置区 → 生成区 → 当前工作流比较 → 策略库与下游分析 | Claude Pro | 需要通读现有页面结构并做大块重排，属于跨区块联动修改 |
| 2.2 | 在模型配置区按条件渲染 `Baseline / Search`、`Naive / Mean / Drift`、`SM / FSM`、参数搜索开关、ML 开关，未满足最小请求前只允许显示禁用态“生成策略”按钮 | Claude Pro | 需要同时处理状态机、交互顺序和 Streamlit rerun 行为 |
| 2.3 | 把现有 `策略建议` 区块迁移为“当前策略摘要”，只在 `current_artifact` 存在时显示；空状态下不再展示策略建议文案 | 云端 DeepSeek-v3.1 | 区块文案与渲染迁移明确，适合做单文件 UI 调整 |
| 2.4 | 把现有“高级策略搜索 / 搜索结果”改造成配置区里的参数搜索步骤卡 + `pipeline_lineage` stage 卡，不再让搜索结果成为常驻独立大区块 | Claude Pro | 这里既涉及 UI 命名迁移，也涉及和编排层/lineage 的数据对接 |
| 2.5 | 明确保留 K 线、RSI/MACD、因子评分这些“行情与指标可视化”区块，但它们不再承担“多模型结果区”的入口语义 | GPT-5 | 适合做结构复核，避免把市场数据图和策略工作流混成一层 |

**产出物：** 单股页五段式主区首版；空状态、草稿态、生成中、当前结果态的显示边界清晰；“先选模型后生成”路径可走通。

---

## 大任务 3：用 artifact 接管下游分析与策略库比较

> 背景：W5 成败的分界线在于，下游区块是否真正只读 `current_artifact + saved_artifacts`。如果净值图、热图、信号区仍偷偷读旧的全模型 payload，这次重构就只改了皮，没有改骨架。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 3.1 | 实现 `selected_artifact_ids`、`focus_artifact_id`、`signal_dataset_split` 三个下游展示状态，并把它们从生成链路状态中分离 | Claude Pro | 这直接决定展示层是否会误触发重算 |
| 3.2 | 让净值/回撤图、周期收益热图、指标比较表、买卖点查看、ML 质量区块统一从 artifact 读取，不再从 `_build_test_model_payloads()` 或页面级全局变量读取 | Claude Pro | 需要跨多个旧区块改数据源，属于高耦合改造 |
| 3.3 | 加入“当前策略 + 已保存策略”的策略库选择器，默认只勾选 `current_artifact`；保存后不自动重复勾选相同内容曲线 | 云端 DeepSeek-v3.1 | 交互规则已写死在 Day4/5，可按文档实现 UI 读取层 |
| 3.4 | 落地保存幂等规则：同一个 `artifact.id` 重复保存不新增快照；同名不同 id 的快照按序号派生展示名 | 云端 DeepSeek-v3.1 | 逻辑清晰，适合实现会话内列表辅助函数 |
| 3.5 | 保持 `Walk-Forward` 独立，只绑定 `current_artifact`，不进入多策略选择器和 saved 快照列表 | Claude Pro | 需要防止新旧数据流相互污染，属于边界控制点 |

**产出物：** artifact 驱动的下游分析首版；策略库可保存、可勾选、可聚焦；`Walk-Forward` 边界不被破坏。

---

## 大任务 4：收口搜索回写、失败降级与 stage cache 语义

> 背景：当前高级搜索结果仍通过 [`app.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\app.py) 的 `apply_best_params` 机制回写侧边栏；同时，W5 文档要求搜索结果默认只写入 lineage / artifact。若这个冲突不解决，新的工作流会被旧状态通道反向污染。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 4.1 | 评估并重构 `best_params` / `apply_best_params` 逻辑：W5 主线要求“搜索结果默认不回写侧边栏”；如需保留同步入口，必须改成显式动作，不再作为默认主流程 | Claude Pro | 同时涉及 [`ui/single_stock.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\ui\single_stock.py) 与 [`app.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\app.py) 的 session_state 协同 |
| 4.2 | 为 baseline、SM 基础、FSM 基础、参数搜索、ML 五类 stage 建立独立 cache key 骨架：`stage_key + context_key + stage_request_slice + stage_input_params_snapshot` | Claude Pro | 这里要严格按 Day2/Day6 规则落地，否则最容易出现错误命中 |
| 4.3 | 落地失败与降级路径：`FA` 失败不提交新 artifact；搜索失败回退到基础 stage；ML 失败回退到最近一步成功上游 | 云端 DeepSeek-v3.1 | 规则已经定稿，适合按表编码 |
| 4.4 | 确保展示层动作不会触发重算：切换已选策略、切换主策略、切换训练/测试信号来源、点击保存都只能重渲染，不能重新训练 FA / 搜索 / ML | Claude Pro | 这是行为级性能验收核心，需要结合 stage cache 和 workspace 一起检查 |
| 4.5 | 补一轮缓存与状态边界复核，重点检查 `train_ratio`、日期范围、股票切换后是否整包失效，且新 `context_key` 不读旧桶 | GPT-5 | 适合做边界条件复核，降低单点遗漏 |

**产出物：** 搜索回写行为与 W5 文档一致；stage cache 与 workspace 语义分离；失败降级路径可解释、可复用。

---

## 大任务 5：执行 W5 自测矩阵并同步文档

> 背景：W5 不是“代码能跑就算完成”。`plan/model-change/day6-7.md` 已经把 9 条主路径、失败补测、cache/rerun/refresh 边界写死，本周必须至少留下一份可复核的执行记录。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 5.1 | 按 Day6 的 `C1-C9` 路径矩阵完成最小自测，逐条确认 lineage 顺序、`current_artifact` 替换、下游默认选择状态、`ml_quality` 出现条件 | 手动（UI 操作）+ Claude Pro | 这是工作流验收，不是纯代码任务；需要一边点 UI 一边对照文档检查 |
| 5.2 | 按 Day6 的 `E1-E8` 失败/边界用例补测 `FA` 失败、搜索失败、ML 失败、重复保存、context reset、会话 rerun、浏览器刷新 | 手动（UI 操作） | 必须验证状态迁移和缓存边界，不能只看 happy path |
| 5.3 | 留存一份 W5 工作流验证记录，建议新增 `document/archive/feature-notes/W5_WORKFLOW_VALIDATION.md` 或同类文档，简要记录通过项/未通过项/降级说明 | 云端 DeepSeek-v3.1 | 中文执行记录写作适合外包，Claude 负责最后审核 |
| 5.4 | 如新增了编排模块或改变了下游读取方式，同步更新 `document/MODULE_INTERFACES.md` 与 `AI_CONTEXT.md`，只写稳定事实，不记施工笔记 | Claude Pro | 这是项目级事实同步，必须由理解全局上下文的工具收口 |
| 5.5 | 根据实际完成度，给出 W5 “本周完成 / 未完成 / 明确顺延”的三栏结论，避免把 W6 内容混进 W5 验收 | GPT-5 | 适合做收口复核，降低范围漂移 |

**产出物：** W5 自测记录；必要的接口/上下文文档同步；本周完成边界明确。

---

## 本周资源分配建议

| 工具 | 预计用量 | 主要用途 |
|------|---------|---------|
| Claude Pro | 高 | 策略编排层落地、`single_stock.py` 主区重排、artifact 数据流改造、`best_params/apply_best_params` 冲突处理、cache/workspace 边界收口 |
| 云端 DeepSeek-v3.1 | 中 | 会话辅助函数、保存/命名/列表逻辑、部分 UI 渲染迁移、自测记录和接口文档草稿 |
| GPT-5 | 低 | 布局/边界复核、W5 完成定义和风险清单二次校验 |
| Gemini | 低（备用） | 如需一次性通读大型 `single_stock.py` 重构前后差异或长文档交叉检查 |

**可外包给其他 AI 的比例：约 25%**

---

## 风险提示

### 风险1：旧的页面级全模型 payload 和新的 artifact 流并存，导致双轨逻辑长期共存

当前 [`ui/single_stock.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\ui\single_stock.py) 里 `_build_test_model_payloads()` 已经承担了结果构建职责。如果 W5 只是再包一层工作流 UI，而不真正下沉/替换旧 payload，后续会出现“页面显示用 artifact，图表细节仍读旧变量”的隐性分叉。

**应对：** W5 必须明确哪些旧函数被删除、哪些被改造成 stage runner、哪些只保留为下游渲染辅助函数；不要接受“双系统并存”的临时状态跨周遗留。

### 风险2：`best_params / apply_best_params` 回写机制破坏新的请求-生成-分析语义

当前搜索结果会通过 [`app.py`](d:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy\app.py) 回写侧边栏参数，这与 W5 文档要求冲突，最容易让用户误以为“当前 artifact 已自动等于侧边栏状态”。

**应对：** W5 必须先决定该机制是“下线默认回写”还是“显式同步动作”，不能两套语义同时保留。

### 风险3：`stage cache` 与 `strategy_workspace` 混淆，导致跨上下文污染

W5 会同时引入“生成链路复用”和“会话内策略库”两层缓存语义；如果没有严格区分，股票切换或日期范围变化后最容易出现旧 artifact 被误读为新结果。

**应对：** 先实现 `context_key` 与 reset，再接 stage cache；所有展示层切换动作都应在日志或调试信息里能证明“未触发重算”。

---

## 落后时裁剪优先级

1. “同步搜索结果到侧边栏”的显式动作可以不在 W5 落地，只保留默认不回写语义。
2. `Walk-Forward` 保持 `current_artifact` 专属即可，不把它强行并入策略库。
3. UI 第一轮收束只做工作流重排、状态文案和必要布局，不做整体视觉升级或动画。
4. 自测记录至少完成 9 条主路径 + 关键失败降级；更细的性能量化指标可放到 W6。
5. 多股页模型汇总看板继续顺延到 W6/W7，不得回流进入 W5 主线。
