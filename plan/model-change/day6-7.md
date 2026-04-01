# 模型逻辑重构工作单（Day 6-7）

> 目标周期：单股页策略工作流重构第 6-7 天  
> 文档定位：固化回归测试、性能要求、最终验收口径  
> 关联范围：自测矩阵、缓存验证、文档同步、下一周 backlog

---

## Day 6

### 当天目标
- 把重构后的回归测试和性能要求写成可执行清单。

### Day 6 定稿结论

#### 1. 回归测试维度定稿

- Day 6 的回归验证固定拆成三层：`路径正确性`、`展示/性能行为`、`会话与缓存边界`。
- “把 9 条路径都点一遍”只覆盖第一层，不等于 Day 6 完成；若不补展示切换、保存、上下文失效与 cache 行为，验收仍不成立。
- Day 6 先定义“行为级性能口径”，不强行写死毫秒级 SLA；第一周的性能目标是“不多算、不重算、不串错上游”。

| 维度 | 验证对象 | 最低通过标准 |
|------|------|------|
| `路径正确性` | 请求校验、stage 串联顺序、artifact 产出 | 只生成被请求的链路；`pipeline_lineage` 与请求完全一致；`current_artifact` 立即进入下游 |
| `展示/性能行为` | 下游勾选、训练/测试切换、保存动作 | 展示层动作只读已有 artifact，不触发 `FA` / 搜索 / `ML` / 回测重算 |
| `会话与缓存边界` | rerun、浏览器刷新、`context reset`、stage cache 命中 | 同会话 rerun 保留策略库；刷新后 workspace 消失；新 `context_key` 不读旧桶 |

#### 2. 最小路径测试矩阵定稿

- Day 6 的最小矩阵固定为 9 条路径，覆盖 `Baseline`、`SM`、`FSM` 及两种增强步骤的全部合法组合。
- 每一条矩阵用例默认都要同时检查 4 个共性结果：
- 成功后 `current_artifact` 被替换为新结果。
- `selected_artifact_ids` 自动重置为 `[current_artifact.id]`。
- `focus_artifact_id` 自动切到 `current_artifact.id`。
- `signal_dataset_split` 重置为 `test`。

| 用例 | 请求路径 | 期望 lineage | 必验点 |
|------|------|------|------|
| `C1` | `Baseline` | 仅 1 张 `baseline_kind` stage 卡 | 至少用 1 个 baseline 跑通；不出现 `FSM` / 搜索 / `ML` stage；当前策略立即进入下游 |
| `C2` | `SM` | `SM基础` | 只产出基础 `SM` artifact；无搜索 stage；`ml_quality=None` |
| `C3` | `SM + Search` | `SM基础 -> SM+Search` | 搜索结果来自 `SM基础`；不自动回写侧边栏；无 `ML` stage |
| `C4` | `SM + ML` | `SM基础 -> SM+ML` | `ML` 直接消费 `SM基础`；无搜索 stage；存在 `ml_quality` |
| `C5` | `SM + Search + ML` | `SM基础 -> SM+Search -> SM+Search+ML` | `ML` 消费 `SM+Search` 而不是 `SM基础`；最终 artifact 带 `ml_quality` |
| `C6` | `FSM` | `FSM基础` | `FA` 必须发生但不单独渲染 stage 卡；无搜索 stage；无 `ML` stage |
| `C7` | `FSM + Search` | `FSM基础 -> FSM+Search` | 搜索结果来自 `FSM基础`；不允许跳过 `FA` 直出 `FSM+Search` |
| `C8` | `FSM + ML` | `FSM基础 -> FSM+ML` | `ML` 直接消费 `FSM基础`；无搜索 stage；存在 `ml_quality` |
| `C9` | `FSM + Search + ML` | `FSM基础 -> FSM+Search -> FSM+Search+ML` | `ML` 消费 `FSM+Search`；不允许越过搜索结果直接绑定基础 `FSM` |

补充约束：

- `Baseline` 最低要求是验证 1 条代表路径即可；若 `Naive / Mean / Drift` 三者已同时落地，建议各补 1 次轻量 smoke，但不把它们计作额外工作流组合数。
- `FSM` 系列用例一律要顺带确认：`FA` 只是前置计算，不是独立 artifact，也不是 Day 3 的单独 lineage 卡。
- `Search + ML` 组合一律要确认：`ML` 的上游绑定的是“最近一步成功 stage”，而不是“最初基础参数草稿”。

#### 3. 边界与失败补测定稿

- Day 6 不允许只测 happy path；以下补测用例与 9 条主路径同级，缺任一项都不能算回归闭环。

| 用例 | 场景 | 期望结果 |
|------|------|------|
| `E1` | 非法请求组合：`Baseline` 下仍携带 `use_search=True` 或 `use_ml=True` | 按钮不可提交，或提交前校验失败；不替换 `current_artifact` |
| `E2` | `FSM` 路径的 `FA` 失败 | 不提交新 `current_artifact`；页面回到 `REQUEST_DRAFT`；保留旧结果并提示 `FA` 失败 |
| `E3` | `SM / FSM + Search` 的搜索 stage 失败 | 提交基础 stage 作为降级结果；显示 warning；不伪造搜索结果 |
| `E4` | `SM / FSM + ML` 的 `ML` stage 失败 | 提交最近一步成功上游结果；显示 warning；不伪造带 `ML` 的 artifact |
| `E5` | 对同一 `current_artifact.id` 重复点击保存 | 不新增重复快照；策略库定位到既有保存项并提示“已在策略库中” |
| `E6` | 上下文变化触发 `context reset` | `current_artifact`、`saved_artifacts`、下游选择状态全部清空，页面回到 `EMPTY` |
| `E7` | 同一浏览器会话内正常 rerun | `current_artifact` 与 `saved_artifacts` 仍在；不因为脚本 rerun 丢失策略库 |
| `E8` | 浏览器刷新或新会话重开 | `strategy_workspace` 失效；页面回到空状态；不会自动恢复旧策略库 |

#### 4. 性能检查清单定稿

- Day 6 的性能验收以“行为约束”而不是“绝对耗时”定义。
- 若一次用户动作触发了不该发生的重算，即使总耗时尚可，也判定为性能不通过。

| 动作 | 允许发生 | 明确禁止 | 验收信号 |
|------|------|------|------|
| 点击生成 `Baseline` | 只跑 baseline 链路 | 偷跑 `SM` / `FSM` / 搜索 / `ML` | `pipeline_lineage` 仅含 1 个 baseline stage；无其他阶段副产物 |
| 点击生成 `SM` 或 `FSM` 基础路径 | 只跑所选 family 的基础 stage | 页面加载时全模型一起算；未选 family 的另一条 family 被动执行 | 仅出现被请求 family 的基础 lineage |
| 点击生成带 `Search` / `ML` 的路径 | 按固定顺序串联被请求 stage | 跳步执行、重复执行、串到未选 family | lineage 顺序严格等于请求顺序，且每个 stage 只出现一次 |
| 切换 `selected_artifact_ids` / `focus_artifact_id` | 只读已有 artifact 重新渲染下游 | 重建 artifact、重新训练、重跑回测 | artifact `id` 不变；无新 lineage、无新 warning |
| 切换 `signal_dataset_split` 或买卖点来源 | 只在 `train_sim_df / test_sim_df` 间切换读取 | 重新训练 `FA` / 搜索 / `ML`，或重跑回测 | 只改变展示数据切片；主策略 `id` 与评估结果不变 |
| 点击保存当前策略 | 只修改 `saved_artifacts` 或命中幂等逻辑 | 重新生成 `current_artifact`、重跑 stage | 保存前后 `current_artifact.id` 不变；只新增或定位保存项 |
| 同上下文下再次生成同一请求 | 允许命中 stage cache，允许只补写 miss 的 stage | 为了保险整链路全量重算 | lineage 与上次一致；侧边栏值不被搜索结果偷偷回写 |

#### 5. stage cache 命中规则定稿

- Day 6 明确把 `stage cache` 和 `strategy_workspace` 分开验收：前者服务“生成链路复用”，后者服务“会话展示与快照”，两者不是同一层缓存。
- `stage cache` 的统一骨架仍沿用 Day 2：`stage_key + context_key + stage_request_slice + stage_input_params_snapshot`。

| 阶段 | 命中前提 | 不应导致 miss 的变化 | 命中后的期望 |
|------|------|------|------|
| `Baseline` stage | 同一 `context_key`、同一 `baseline_kind`、同一 baseline 参数快照 | 下游勾选变化、保存动作、训练/测试视图切换 | 直接复用同一 baseline `stage_result` |
| `SM基础` stage | 同一 `context_key`、`family=search`、`search_base=sm`、同一基础参数快照 | `use_search`、`search_method`、`use_ml`、展示项变化 | 直接复用 `SM基础` 结果，供后续 stage 继续消费 |
| `FSM基础` stage | 同一 `context_key`、`family=search`、`search_base=fsm`、同一 `FA` 参数与基础参数快照 | `use_search`、`use_ml`、展示项变化 | 直接复用 `FSM基础` 结果；`FA` 不应重复拟合 |
| `参数搜索` stage | 同一 `context_key`、`use_search=True`、同一搜索方法/超参、同一上游 stage 身份与有效参数 | `use_ml`、下游展示变化、保存动作 | 直接复用搜索 stage 结果；不自动回写侧边栏 |
| `ML` stage | 同一 `context_key`、`use_ml=True`、同一 `ml_model_type`/ML 参数、同一“最近成功上游”身份与有效参数 | 展示项变化、保存动作、只切换下游比较对象 | 直接复用 `ML` stage 结果，且绑定最近一步成功上游 |

补充约束：

- `SM基础` 与 `FSM基础` 的 cache 命中不能被下游增强开关误伤；`use_search=True` 或 `use_ml=True` 只影响后续 stage，不应让基础 stage 无故 miss。
- `参数搜索` 与 `ML` 的命中都必须绑定“最近一步成功上游 stage”；不允许只看初始请求草稿而忽略上游已生效参数。
- stage cache 验证只针对编排层；数据层 `load_csv()` / `load_uploaded_bytes()` 的 `@st.cache_data` 不在 Day 6 主验收口径内。

#### 6. stage cache 与 workspace 行为边界定稿

| 行为 | stage cache | `strategy_workspace` | 结论 |
|------|------|------|------|
| 同上下文、同请求再次点击生成 | 允许读命中；若局部 miss，允许只补写缺失 stage | 成功后用新 artifact 替换 `current_artifact` | 这是唯一默认允许主动命中 stage cache 的用户动作 |
| 同上下文内修改请求草稿但未点击生成 | 不读、不写 | 保留旧 `current_artifact` 与 `saved_artifacts`，页面进入 `REQUEST_DRAFT` | 草稿变脏不等于结果失效 |
| 切换 `selected_artifact_ids` / `focus_artifact_id` / `signal_dataset_split` | 不读、不写 | 只读已有 artifact 与展示状态 | 纯展示行为，不能借机重算 |
| 点击保存或重复保存 | 不读、不写 | 只改 `saved_artifacts`，或命中幂等提示 | 保存不是生成动作 |
| 触发 `context reset` | 旧 context 桶可物理保留，但新 `context_key` 下绝不能读取 | 清空 `current_artifact`、`saved_artifacts`、下游选择状态 | 这是 Day 6 唯一必须做“整包失效”验证的场景 |
| 同会话内脚本 rerun | 不要求清理 | 保留整个 workspace | rerun 不应被视作刷新页面 |
| 浏览器刷新 / 新会话 | 不要求清理进程级 cache | workspace 随会话结束而失效 | 即使 stage cache 仍在，也不能自动恢复旧策略库 |

### 当日产出
- 测试矩阵：见上文 `最小路径测试矩阵定稿` 与 `边界与失败补测定稿`。
- 性能检查清单：见上文 `性能检查清单定稿`。
- 缓存命中规则：见上文 `stage cache 命中规则定稿` 与 `stage cache 与 workspace 行为边界定稿`。

### 验收标准
- 实现者能按文档独立完成自测，而不是只验证 happy path。
- 任意人都能明确回答“某条路径应该出现哪些 lineage stage”“某次展示动作为什么不该触发重算”“某个 cache 命中到底绑定了哪个上游结果”。
- 文档已经覆盖“正确性 + 性能 + 会话行为”三类验证，不只剩 UI 肉眼检查。

### 风险/依赖
- 依赖：前五天已经完成工作流、artifact、下游读取和状态边界定义。
- 风险：如果不把 `stage cache` 和 `strategy_workspace` 分开写清，后续最容易把“展示层状态丢失”误判成“缓存失效”，或者反过来把旧 cache 错当成旧策略库恢复。
- 风险：如果没有明确测试矩阵，重构后最容易漏掉 `FSM + ML`、`Search + ML` 这类复合路径。

---

## Day 7

### 当天目标
- 收口文档和验收口径，给这一周重构一个可交付结束点。

### Day 7 定稿结论

#### 1. 执行基线文档包定稿

- Day 7 收口后，本轮单股页策略工作流重构的执行基线固定为“1 份总说明 + 3 份工作单”。
- 后续实现者应先读总说明，再按 3 份工作单推进；Day 7 的目标就是让实现不再依赖口头补规则。

| 文档 | 角色 | 回答的问题 |
|------|------|------|
| `workflow-restructure.md` | 总入口 | 这轮重构为什么做、总工作流是什么、本周范围到哪里为止 |
| `day1-3.md` | 规则与结构基线 | 模型层级如何组织、主区顺序如何重排、编排层和 stage cache 如何定义 |
| `day4-5.md` | artifact 与状态基线 | 下游如何统一读 artifact、保存/比较如何工作、失败和 `context reset` 如何处理 |
| `day6-7.md` | 验收与收口基线 | 自测矩阵是什么、性能行为怎么验、这一周什么算完成、什么明确不做 |

补充约束：

- 如果实现与上述 4 份文档冲突，优先回到文档修正规则，不允许靠临时口头约定推进。
- Day 7 不再新增新的工作流语义，只负责把已有规则冻结成最终验收口径。

#### 2. 最终验收表定稿

- Day 7 的最终验收不是“看上去差不多”，而是下面每一项都有明确通过标准。
- 任一 `P0` 项未通过，都不能宣称本轮单股页工作流重构完成。

| 编号 | 优先级 | 验收项 | 通过标准 |
|------|------|------|------|
| `A1` | `P0` | 空状态正确 | 首次进入或 `context reset` 后只显示工作台入口/空状态，不显示旧结果区块 |
| `A2` | `P0` | 层级显示正确 | `Baseline` 只出现 baseline 相关控件；`Search` 先选 `SM/FSM`，再出现搜索/ML 开关 |
| `A3` | `P0` | 生成链路正确 | 点击“生成策略”时只运行被请求链路；`pipeline_lineage` 与请求顺序完全一致 |
| `A4` | `P0` | 当前策略即时进入下游 | 新 `current_artifact` 生成成功后，立即成为默认下游分析对象，并重置下游选择状态 |
| `A5` | `P0` | 保存快照可对比 | 保存后 `saved_artifacts` 新增或命中幂等；`current_artifact` 不被移出下游；多策略比较可显式勾选 |
| `A6` | `P0` | 上下文变化会清空 | 股票/市场/上传数据/日期范围/训练比例变化时，workspace 与下游选择状态整包失效 |
| `A7` | `P0` | 训练/测试买卖点可切换 | `signal_dataset_split` 只切换 `train_sim_df / test_sim_df` 的读取，不触发重训或重算 |
| `A8` | `P0` | 搜索结果不污染侧边栏 | 搜索 stage 命中缓存或成功生成后，只写入 lineage / artifact，不自动回写 widget |
| `A9` | `P0` | Day 6 自测闭环完成 | 9 条主路径矩阵 + 失败/降级补测 + cache / rerun / refresh 验证都已有执行记录 |
| `A10` | `P1` | `Walk-Forward` 边界正确 | `Walk-Forward` 只绑定 `current_artifact`，不进入策略库、多策略选择器与 saved 快照 |
| `A11` | `P1` | 文档同步完成 | 若实现改变了稳定事实，`AI_CONTEXT.md` 与必要的接口/计划文档已同步，不留口头差异 |
| `A12` | `P1` | 范围冻结未破坏 | 本周明确不做项没有被偷偷混入主线实现或验收标准 |

补充约束：

- `A9` 要求有“按表执行过”的证据，可以是手工勾检记录，也可以是 smoke 结果摘要，但不能只写“已自测”。
- `A10`、`A11`、`A12` 不决定主流程能否运行，但决定本轮交付是否干净、边界是否稳定。

#### 3. 本周完成与未完成边界定稿

- Day 7 必须把“本周完成了什么”和“本周明确没做什么”同时写死，避免下周把未完成项混进本周验收。

| 分类 | 内容 | Day 7 定稿结论 |
|------|------|------|
| `本周完成定义` | 工作流语义 | 单股页 `Baseline / Search -> SM / FSM -> 参数搜索 / ML` 的层级、顺序、artifact 语义、状态边界、测试口径均已冻结 |
| `本周完成定义` | 验收口径 | 最小路径矩阵、失败/降级补测、展示层性能约束、cache / workspace 边界均已冻结 |
| `本周完成定义` | 文档交付 | 实现者已可按“总说明 + 3 份工作单”直接推进，不再依赖补充口头说明 |
| `本周明确不做` | `Walk-Forward` 策略库化 | 不纳入本周完成标准；未做不算失败 |
| `本周明确不做` | 自定义保存名称 | 保持系统派生命名；未做不算失败 |
| `本周明确不做` | 新的视觉大改版 | UI 只按工作流重排，不把整体视觉升级混入本轮 |
| `本周明确不做` | 多股页同步重构 | 范围仅限单股页；多股页不纳入本轮验收 |
| `本周明确不做` | 持久化策略库 | `saved_artifacts` 仍然只在会话内有效；刷新页面后消失 |

补充约束：

- 只要 `本周明确不做` 里的事项没有反向破坏主线，本周就不因它们缺失而判失败。
- 若实现过程中不得不触碰这些边界，必须先回写文档并重新定义范围，而不是默认顺手做掉。

#### 4. 文档同步口径定稿

- Day 7 收口时，文档同步遵循“只同步稳定事实，不追加临时施工笔记”。
- 文档同步不是机械全改，而是按变更性质命中对应文档。

| 文档 | 何时必须更新 | 何时不必更新 |
|------|------|------|
| `AI_CONTEXT.md` | 架构事实、模块职责、文档状态、协作约定、部署事实发生稳定变化 | 仅做了一次试验、临时排查、未落地的备选方案 |
| `plan/model-change/*.md` | 工作流语义、验收口径、范围边界发生变化 | 只是按既定文档实现，没有改规则 |
| `document/MODULE_INTERFACES.md` | 公开接口、输入输出结构、artifact 字段或依赖关系变化 | 只有 UI 排版变化，不涉及接口 |
| `plan/week3.md` 或总计划文档 | 周目标、排期、里程碑发生实质偏移，需要留痕 | 只是同周内按计划推进，没有改周目标 |

补充约束：

- Day 7 默认至少要确认 `AI_CONTEXT.md` 的文档状态与当前工作单完成度一致。
- 若实现阶段没有改变周计划，不强制同步 `week3.md` 或总计划，避免制造噪音。

#### 5. 已知限制清单定稿

| 编号 | 限制 | 当前处理 | 影响面 |
|------|------|------|------|
| `L1` | 策略库不是持久化存储 | `saved_artifacts` 只在当前会话内有效，浏览器刷新后失效 | 不能把本轮方案当作长期版本管理系统 |
| `L2` | 保存名称不可自定义 | 仍使用 `当前 · {display_label}` / `已保存 · {display_label}` 的派生命名 | 用户无法手工给快照命名 |
| `L3` | `Walk-Forward` 未库化 | 仅绑定 `current_artifact`，不进入多策略比较 | 不能把 `Walk-Forward` 结果当作 saved 快照长期对比 |
| `L4` | 多股页未同步重构 | 本轮只改单股页策略工作流 | 多股页仍沿用现有结构与行为 |
| `L5` | stage cache 只保证逻辑隔离 | 旧 context 桶可物理保留，但新 `context_key` 绝不能读取旧结果 | 需要把“逻辑失效”与“物理删除”区分开 |
| `L6` | 性能口径是行为级约束 | Day 6 只冻结“不多算/不重算/不串算”，不冻结固定毫秒级 SLA | 后续若要做性能优化，还需单独补充定量指标 |
| `L7` | 搜索结果默认不回写侧边栏 | 最佳参数只保留在 lineage / artifact 中 | 若后续需要“同步到侧边栏”，要作为显式动作新增 |

补充约束：

- 已知限制是“当前接受的边界”，不是 bug 列表；它们只要与本周范围一致，就不应在 Day 7 被误判为未完成。
- 后续若要突破这些限制，应先进入 backlog，再进入新一轮范围定义。

#### 6. 下一周 backlog 定稿

- 下一周 backlog 只收“本周文档已经解锁、但尚未实现或尚未产品化落地”的事项，不再掺入新的需求讨论。

| 编号 | 优先级 | backlog | 依赖本周输出的点 | 预期交付 |
|------|------|------|------|------|
| `B1` | `P0` | 在代码中落地 `StrategyRequest` / `StrategyArtifact` / `strategy_workspace` | Day1-Day5 已冻结语义与字段 | 会话状态与 artifact 生命周期实现 |
| `B2` | `P0` | 落地策略编排层：`run_strategy_pipeline` + 各 stage runner | Day2 已冻结合法路径、上游消费与 cache 骨架 | UI 不再手写整条策略链路 |
| `B3` | `P0` | 将单股页重排为五段式主区结构 | Day3 已冻结页面顺序与显示条件 | 单股页生成前后区块彻底分离 |
| `B4` | `P0` | 用 artifact 接管下游摘要、净值/回撤、热图、对比表、买卖点、ML 质量区块 | Day4 已冻结 artifact 消费矩阵 | 下游不再依赖一次性全模型 payload |
| `B5` | `P0` | 落地保存/比较/`context reset`/失败降级/`Walk-Forward` 边界 | Day5 已冻结状态迁移和失败规则 | 会话行为与下游状态稳定 |
| `B6` | `P1` | 按 Day6 矩阵执行完整自测，并沉淀执行记录 | Day6 已冻结测试矩阵与性能口径 | 可复用的 smoke / 手工验收记录 |
| `B7` | `P2` | 评估是否增加“同步到侧边栏参数”显式动作 | Day2 已预留语义，但本周未做 | 是否进入下一轮增强范围的决策 |
| `B8` | `P2` | 评估 `Walk-Forward` 策略库化、自定义命名、持久化快照、多股页同步重构 | Day7 已明确它们都不在本周范围 | 下一轮范围候选清单 |

### 当日产出
- 最终验收表：见上文 `最终验收表定稿`。
- 已知限制清单：见上文 `已知限制清单定稿`。
- 下一周 backlog：见上文 `下一周 backlog 定稿`。

### 验收标准
- 这一周结束时，后续实现者可以直接按“1 份总说明 + 3 份工作单”推进，不再回到口头讨论阶段。
- 本轮重构的“完成”和“未完成”边界清晰，不会把下一周内容偷渡进来。
- 任意人都能据此判断：哪些项必须在本周验收通过，哪些项即使未做也不应阻塞本轮收口。

### 风险/依赖
- 依赖：Day 6 的测试矩阵已经完成。
- 风险：如果没有最终验收表，本周文档会停留在“建议”层，不足以成为执行基线。
- 风险：如果不把“本周不做项”写死，后续最容易把 `Walk-Forward` 策略库化、自定义命名或多股页重构偷渡进本轮，导致范围再次失控。
