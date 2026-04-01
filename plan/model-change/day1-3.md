# 模型逻辑重构工作单（Day 1-3）

> 目标周期：单股页策略工作流重构第 1-3 天  
> 文档定位：把“模型层级、状态语义、主区顺序”先定死，再进入实现  
> 关联范围：`ui/single_stock.py`、策略编排层、会话状态管理

---

## 先锁定的接口

### `StrategyRequest`
- 用途：描述一次用户发起的策略生成请求。
- 只包含：模型层级选择、开关项、搜索方式、ML 方式。
- 不包含：回测结果、指标、图表对象、缓存结果。

### `StrategyArtifact`
- 用途：描述一次已经生成完成、可进入下游分析和对比的策略实体。
- 至少包含：`id`、`display_label`、`pipeline_lineage`、`params_snapshot`、`train_sim_df`、`test_sim_df`、`trades_df`、`eval`、`equity_series`、`returns_series`、`ml_quality`。

### `strategy_workspace`
- 用途：作为会话级状态容器。
- 固定包含：`context_key`、`current_artifact`、`saved_artifacts`。
- 约束：下游所有展示区只消费 artifact，不再消费页面启动时一次性算出的全模型 payload。

---

## Day 1

### 当天目标
- 把策略逻辑的产品规则和状态规则彻底定死，先停掉“页面加载即全模型计算”的旧思路。

### Day 1 定稿结论

#### 1. 模型层级命名定稿

| 层级 | 名称 | 可选值 | 是否必选 | 说明 |
|------|------|------|------|------|
| 第一层 | 模型家族 `Family` | `Baseline / Search` | 是 | 用户进入策略区后的第一步，只决定走哪条大路径 |
| 第二层 | 搜索基础模型 `Search Base` | `SM / FSM` | 条件必选 | 仅当 `Family=Search` 时出现；`Baseline` 路径不进入本层 |
| 第三层 | 增强层 `Enhancement` | `参数搜索 / ML` | 否 | 仅当 `Family=Search` 时出现，可单独启用，也可同时启用 |

- 第一层的 `Search` 指“搜索模型家族”。
- 第三层原文里的 `Search` 后续统一改写为 `参数搜索（Param Search）`，避免和第一层重名。
- `Baseline` 家族内部再选 `Naive / Mean / Drift`，但不进入 `SM / FSM / ML` 这条链。
- `FSM` 的合法起点固定为 `FA -> FSM基础策略`，不存在跳过 `FA` 的 `FSM` artifact。
- `ML` 的合法输入固定为最近一步已生成的 artifact；如果同时启用 `参数搜索 + ML`，执行顺序固定为 `基础策略 -> 参数搜索 -> ML`。

#### 2. 三个核心语义定稿

- `current strategy`：当前上下文中最近一次成功生成、且已经提交到 `current_artifact` 的最终策略。它始终是下游分析默认读取对象。
- `saved strategy`：用户显式点击保存后，从某个 artifact 冻结出来的会话内快照。保存后不再被后续生成动作覆盖，也不会反向修改 `current_artifact`。
- `context reset`：当 `context_key` 发生变化时触发的整包失效。触发后 `current_artifact` 与 `saved_artifacts` 一并清空，不允许跨上下文继续比较。

#### 3. 提交与可见性原则

- 生成动作采用“成功后提交”语义：只有整条链路成功，才替换 `current_artifact`。
- 同一上下文内改动请求参数，不立即清空旧结果；旧结果继续作为“上一次成功生成结果”存在，直到用户重新生成或上下文失效。
- `saved_artifacts` 只接受显式保存，不允许“生成即自动保存”。
- 当前策略默认立即可见；保存只是让它进入会话内长期比较列表，不做文件持久化。

### 工作流状态表

| 状态 | 进入条件 | `current_artifact` | `saved_artifacts` | 页面语义 |
|------|------|------|------|------|
| `EMPTY` | 首次进入页面，或上下文刚被重置 | `None` | `[]` | 只显示模型选择和步骤提示，不显示任何结果区 |
| `REQUEST_DRAFT` | 同一上下文下，用户已完成或改动了请求配置，但尚未生成当前草稿 | 若存在上一次成功结果则保留，否则为 `None` | 保留原列表 | 若已有旧结果，应提示“当前展示的是上次生成结果”；若没有旧结果，则继续停留在空结果态 |
| `GENERATING` | 用户点击“生成策略”后，当前链路正在执行 | 保留上一次成功结果，待新结果成功后替换 | 保留原列表 | 显示执行中状态；禁止重复触发生成；不清空已提交结果 |
| `CURRENT_READY` | 当前上下文下已成功生成一个最新策略，且还没有保存快照 | 最新成功 artifact | `[]` | 下游默认消费 `current_artifact` |
| `CURRENT_AND_SAVED` | 当前上下文下已成功生成最新策略，且至少存在一个已保存快照 | 最新成功 artifact | 至少 1 个冻结快照 | 下游比较器可同时读取“当前策略 + 已保存策略” |
| `INVALIDATED` | `context_key` 变化，旧上下文被判定失效 | 清空 | 清空 | 这是一个瞬时清空动作；完成后立即回到 `EMPTY` |

### Artifact 生命周期表

| 阶段 | 触发 | 存放位置 | 是否参与下游分析 | 覆盖规则 | 说明 |
|------|------|------|------|------|------|
| `Request Draft` | 用户只是在配置路径，还未点击生成 | 不创建 artifact | 否 | 不适用 | 这只是请求草稿，不是策略实体 |
| `Current Artifact` | 一次生成链路成功结束 | `current_artifact` | 是 | 下一次成功生成可替换 | 当前策略立即进入下游分析区 |
| `Saved Snapshot` | 用户点击保存 | `saved_artifacts` | 是 | 不被后续生成覆盖 | 保存的是冻结快照，不跟随后续参数变化自动更新 |
| `Superseded Current` | 新的 `current_artifact` 生成成功，而旧 current 未被保存 | 移出 workspace | 否 | 直接丢弃 | 如果需要保留旧版本，必须先显式保存 |
| `Invalidated Artifact` | `context_key` 变化 | 移出 workspace | 否 | 直接清空 | 不允许跨股票、跨数据上下文复用或比较 |
| `Session End` | 浏览器刷新、会话结束或 Streamlit session 丢失 | 移出 workspace | 否 | 全部丢失 | 本轮不做持久化恢复 |

### 上下文失效规则

#### 1. `context_key` 的最小组成

- `market`
- `symbol` 或 `uploaded_data_fingerprint`
- `data_source_kind`（缓存数据 / 上传数据）
- `adjust`（若单股页暴露复权方式）
- `date_range`
- `train_split_ratio`

#### 2. 失效分类表

| 变更类型 | 典型字段 | 是否清空 `current_artifact` | 是否清空 `saved_artifacts` | 处理规则 |
|------|------|------|------|------|
| 上下文变更 | 股票、市场、上传数据、复权方式、日期范围、训练集比例 | 是 | 是 | 重建 `context_key`，整包失效，回到 `EMPTY` |
| 请求变更 | `Baseline/Search` 选择、`Naive/Mean/Drift`、`SM/FSM`、是否启用参数搜索、搜索方法、是否启用 ML、ML 模型类型、策略参数 | 否 | 否 | 只把工作台标记为 `REQUEST_DRAFT`，等待用户重新生成 |
| 展示变更 | 下游勾选策略、训练/测试切换、买卖点来源切换、图表展示选项 | 否 | 否 | 只读现有 artifact，不允许触发重算或清空 |

#### 3. 失效边界补充

- `saved_artifacts` 的比较边界严格等于当前 `context_key`，不能跨上下文混比。
- 切换股票后，旧股票的 `current_artifact` 和 `saved_artifacts` 必须一起消失，不允许保留“历史对比”幻觉。
- 同一上下文内修改策略参数，只会让“请求草稿”变脏，不会自动宣布旧 artifact 无效。

### 当日产出

- 工作流状态表：见上文 `工作流状态表`。
- artifact 生命周期表：见上文 `Artifact 生命周期表`。
- 上下文失效规则：见上文 `上下文失效规则`。

### 验收标准
- 实现者不需要再猜“哪个块先出现”“哪个步骤可选”“换股票后是否保留旧策略”。
- 所有人对 `current_artifact` 和 `saved_artifacts` 的职责理解一致。

### 风险/依赖
- 依赖：现有单股页区块顺序和多模型结果载荷已确认。
- 风险：如果第一天不把状态语义定死，后面 UI 和缓存会反复返工。

---

## Day 2

### 当天目标
- 把计算逻辑从 UI 里拆出来，形成独立的策略流水线编排层。

### Day 2 定稿结论

#### 1. 编排层职责边界定稿

- UI 层只负责 4 件事：收集 `StrategyRequest`、冻结本次 `params_snapshot`、触发“生成策略”、消费编排层返回的 artifact / 状态 / 提示。
- 编排层只负责 4 件事：校验请求是否合法、按固定顺序串联计算步骤、读取/写入阶段缓存、把最终结果组装成 `StrategyArtifact`。
- `core/*` 继续保持“单步能力层”定位：指标、信号、FA、参数搜索、ML、回测、评估仍然是原子函数，不负责 `session_state` 和页面展示。
- 约束：`ui/single_stock.py` 不再自己手写 `compute_signals -> optimize -> apply_filter -> evaluate` 这类链路；编排层也不直接调用 `st.*` 渲染控件。

#### 2. 路径合法性与执行顺序定稿

| 路径 | 合法请求 | 固定执行顺序 | 禁止项 | 提交到 `current_artifact` 的对象 |
|------|------|------|------|------|
| `Baseline` | `family=baseline` 且 `baseline_kind` 已选定 | `基线仓位生成 -> 回测 -> 评估 -> artifact组装` | `FA / 参数搜索 / ML` | baseline 最终 artifact |
| `SM` | `family=search` 且 `search_base=sm` | `SM基础策略 -> 可选参数搜索 -> 可选ML -> artifact组装` | 跳过基础 `SM` 直接搜索或直接 `ML` | 最后一步成功 stage 对应的最终 artifact |
| `FSM` | `family=search` 且 `search_base=fsm` | `FA拟合 -> FSM基础策略 -> 可选参数搜索 -> 可选ML -> artifact组装` | 跳过 `FA` 直接进入 `FSM` 或直接 `ML` | 最后一步成功 stage 对应的最终 artifact |

- `Baseline` 路径收到 `use_search=True` 或 `use_ml=True` 时，不做“静默忽略”，而是视为非法请求组合。
- `FSM` 的合法起点永远是“训练集 `fit_fa()` + 全样本 `compute_signals(fsm_mode=True)`”；不存在“无 `FA` 的 `FSM` 基础结果”。
- `current_artifact` 仍然只保存整条链路的最终结果；链路中的中间结果按顺序写入最终 artifact 的 `pipeline_lineage`，供 Day3 的“当前工作流比较”区读取。

#### 3. 上游结果消费规则定稿

- 编排层内部固定使用一个 `latest_stage_result` 指针，语义是“最近一步成功产出的中间结果”。
- 若路径为 `SM + Search + ML`，则 `ML` 的输入固定为 `SM+Search` 的结果，而不是初始 `SM基础`。
- 若路径为 `FSM + Search + ML`，则 `ML` 的输入固定为 `FSM+Search` 的结果，而不是 `FSM基础`。
- 若只启用 `ML`、未启用参数搜索，则 `ML` 直接消费 `SM基础` 或 `FSM基础`。
- 任一步失败时，不允许跳过失败 stage 继续向下游硬跑；是否保留上游结果作为降级展示，放到 Day5 的失败语义里统一定义。

#### 4. 参数快照与侧边栏回写原则

- 编排层要区分两类参数快照：
- `request params_snapshot`：用户点击“生成策略”时从侧边栏冻结下来的输入快照，用于请求校验与 cache 查找。
- `effective params_snapshot`：某个 stage 真正生效的参数快照，用于写入 `pipeline_lineage` 和最终 artifact。
- 对 `Baseline`、`SM基础`、`FSM基础` 来说，这两者通常相同。
- 对“参数搜索” stage 来说，这两者默认不同：输入快照来自侧边栏，输出快照是搜索后选中的最佳参数。
- 搜索结果默认只写入 `pipeline_lineage` / `current_artifact`，不自动回写侧边栏，也不修改当前页面控件值。
- 预留显式“同步到侧边栏参数”动作：用户可在某个 lineage stage 上主动点击，把该 stage 的 `effective params_snapshot` 写回 widget state；这个动作不属于默认生成主流程，也不反向修改已生成 artifact。

#### 5. 编排层内部中间对象定稿

- 编排层内部统一流转 `stage_result`，它不是 workspace 对象，只是串步骤时的中间结果。
- `stage_result` 最少包含：
- `stage_key`
- `display_label`
- `params_snapshot`
- `train_sim_df`
- `test_sim_df`
- `trades_df`
- `eval`
- `equity_series`
- `returns_series`
- `ml_quality`
- `upstream_stage_key`
- 约束：`stage_result` 的最小字段要足够让 `assemble_strategy_artifact()` 直接组装出 Day4 所需消费字段，避免后面为了下游净值图、收益热图、训练/测试买卖点切换再单独重算一次。

#### 6. 策略编排函数清单

> 为避免和第一层 `Family=Search` 重名，下文 `search stage` 一律指“参数搜索 stage”，不是第一层模型家族名。

| 函数 | 输入 | 输出 | 职责边界 |
|------|------|------|------|
| `run_strategy_pipeline(...)` | `context_key`、`StrategyRequest`、`request params_snapshot`、`df_raw`、`split_idx` | `StrategyArtifact` + `pipeline_lineage` + 提示信息 | 编排入口；只做校验、分发、串联、提交 |
| `run_baseline_path(...)` | baseline 相关请求 + `df_raw` + `split_idx` | 单个 `stage_result` | 只负责 `Naive / Mean / Drift` 路径，不处理 `FA / 搜索 / ML` |
| `run_sm_base_stage(...)` | `df_raw` + 基础信号参数 + `split_idx` | `SM基础` 的 `stage_result` | 负责 `add_indicators -> compute_signals -> simulate/evaluate` |
| `run_fsm_base_stage(...)` | `df_raw` + 基础信号参数 + `split_idx` + `fa` 参数 | `FSM基础` 的 `stage_result` | 负责 `fit_fa -> compute_signals(fsm_mode=True) -> simulate/evaluate` |
| `run_search_stage(upstream_stage, ...)` | 上游 `stage_result` + 搜索配置 | 搜索后的 `stage_result` | 只负责基于上游结果执行参数搜索，再回算并产出新的有效参数快照 |
| `run_ml_stage(upstream_stage, ...)` | 上游 `stage_result` + `ml_model_type` + ML 配置 | `ML` 后的 `stage_result` | 只负责 `build_feature_table -> fit_ml_filter -> apply_filter -> simulate/evaluate` |
| `assemble_strategy_artifact(...)` | stage 链、`context_key`、`StrategyRequest` | 最终 `StrategyArtifact` | 负责把最后一步结果和 `pipeline_lineage` 组装成可提交对象 |

#### 7. 每条路径的输入/输出说明

| 路径 | 起点输入 | 从哪里开始 | 在何处结束 | 最终 artifact 至少保存什么 |
|------|------|------|------|------|
| `Baseline` | `baseline_kind` + baseline 参数 + `df_raw` + `split_idx` | `run_baseline_path()` | 基线 `stage_result` 被 `assemble_strategy_artifact()` 提交 | 最终基线结果 + 单步 `pipeline_lineage` |
| `SM` | `search_base=sm` + 基础参数 + 可选搜索/ML 配置 + `df_raw` + `split_idx` | `run_sm_base_stage()` | 最后一个成功 stage 被 `assemble_strategy_artifact()` 提交 | `SM基础` 必在 lineage 中；若启用搜索/ML，则顺序追加 |
| `FSM` | `search_base=fsm` + `fa` 参数 + 基础参数 + 可选搜索/ML 配置 + `df_raw` + `split_idx` | `run_fsm_base_stage()` | 最后一个成功 stage 被 `assemble_strategy_artifact()` 提交 | `FSM基础` 必在 lineage 中；若启用搜索/ML，则顺序追加 |

#### 8. 缓存策略定稿

- 缓存粒度按 stage 切分，不再按整页或整套模型一起缓存。
- 每个 stage 先按 `stage_key` 分桶，再在桶内使用 `context_key + stage_request_slice + stage_input_params_snapshot` 作为统一 cache 骨架。
- 这里的 `stage_request_slice` 指“只与当前 stage 有关的请求子集”，而不是整份 `StrategyRequest`。
- 这里的 `stage_input_params_snapshot` 指“进入该 stage 时的输入参数快照”，不是 stage 运行完成后的输出快照。
- `context_key` 负责隔离股票/市场/上传数据/日期范围/训练集比例等上下文边界。
- `stage_request_slice` 负责隔离当前 stage 的路径拓扑，而不是隔离整条链路。
- 例如：`SM基础` stage 只关心 `family=search`、`search_base=sm`；不会因为 `use_ml=True` 或 `search_method` 切换而失效。
- 例如：`参数搜索` stage 关心 `use_search`、`search_method` 与上游 stage 身份；`ML` stage 关心 `use_ml`、`ml_model_type` 与最近一步成功上游 stage 身份。
- `stage_input_params_snapshot` 负责隔离指标参数、信号参数、止损止盈、搜索超参、ML 阈值等数值配置。
- 切换展示选项、切换下游比较勾选、切换买卖点来源时，不允许触发这些 stage cache 的失效；这些动作只能读取已存在 artifact。
- 搜索 stage 命中缓存时，直接返回缓存中的搜索结果 artifact，不自动把最佳参数写回侧边栏。
- `ML` stage 的 cache 命中以“最新上游 stage 标识 + 上游 stage 的有效参数 + 当前 ML 配置”作为输入快照语义，保证 `ML` 永远绑定最近一步成功结果，而不是绑定初始基础参数。

### 当日产出
- 策略编排层职责边界。
- 策略流水线函数清单。
- 每条路径的输入输出说明。
- 缓存策略说明。

### 验收标准
- 实现者能够单独写出 baseline、SM、FSM、ML 四类编排函数，而不需要再参考页面布局。
- 任一模型路径都能明确回答“从哪里开始”“在何处结束”“artifact 里保存什么”。
- 任一增强步骤都能明确回答“它消费的是哪一个上游结果”“是否会回写侧边栏参数”“cache 用什么键命中”。

### 风险/依赖
- 依赖：`core/baselines.py`、`core/signals.py`、`core/fa_filter.py`、`core/ml_filter.py`、`core/evaluation.py` 的现有接口。
- 风险：如果编排层仍然夹在 UI 里，后续状态控制和缓存控制会继续混乱。

---

## Day 3

### 当天目标
- 把主区策略段的页面顺序彻底改成“先选择、后生成、再展示”。

### Day 3 定稿结论

#### 1. 主区五段式布局定稿

| 顺序 | 区块 | 可见条件 | 主要内容 | 明确不放什么 |
|------|------|------|------|------|
| 1 | `策略工作台入口 / 空状态` | 始终显示；在 `EMPTY` 与“无旧结果的 `REQUEST_DRAFT`”下成为主视觉 | `Family` 选择、步骤提示、当前状态提示 | 不放任何回测、搜索结果、交易信号 |
| 2 | `模型配置区` | 选定 `Family` 后按条件展开 | `Baseline` 或 `SM / FSM` 配置、增强步骤开关、必要参数卡 | 不放历史结果卡 |
| 3 | `生成区` | 始终占位；未满足最小请求时按钮禁用 | 单一 `生成策略` 按钮、缺失项提示、执行中状态、草稿已变更提示 | 不自动触发计算 |
| 4 | `当前工作流比较` | `current_artifact` 存在时显示 | 读取 `pipeline_lineage` 的 stage 卡，只展示本次链路各步结果 | 不承担 saved strategy 之间的长期比较 |
| 5 | `策略库与下游分析` | `current_artifact` 或 `saved_artifacts` 存在时显示 | `当前策略摘要`、净值/回撤、收益热图、指标比较表、交易信号、`Walk-Forward` | 不再直接读取页面初始全模型 payload |

- 页面首屏默认只激活第 `1-3` 段；第 `4-5` 段必须等 artifact 出现后才显示。
- 主区顺序固定，不再允许把结果区穿插回配置区之前。
- 第 `1-3` 段属于“生成前区域”，第 `4-5` 段属于“生成后区域”。

#### 2. 空状态与旧结果保留提示定稿

| workspace 状态 | 第 1-3 段表现 | 第 4 段 | 第 5 段 | 页面提示 |
|------|------|------|------|------|
| `EMPTY` | 只显示模型选择、步骤提示和禁用态生成按钮 | 隐藏 | 隐藏 | “请选择模型路径并生成第一条策略” |
| `REQUEST_DRAFT` 且无旧结果 | 与 `EMPTY` 相同，但提示当前草稿已配置 | 隐藏 | 隐藏 | “当前请求已完成配置，尚未生成结果” |
| `REQUEST_DRAFT` 且有旧结果 | 配置区显示新草稿；生成区显示“草稿已变更”提示 | 继续显示旧 `current_artifact` 的 lineage，并加“上次结果”标记 | 继续显示旧结果 | “当前展示的是上次生成结果，重新生成后才会更新” |
| `GENERATING` | 配置区可保留当前选择；生成区进入执行中态，按钮禁用 | 若有旧结果则继续显示旧 lineage | 若有旧结果则继续显示旧结果 | “正在生成新策略，请等待当前链路完成” |
| `CURRENT_READY / CURRENT_AND_SAVED` | 正常显示已选路径配置与可再次生成入口 | 显示当前策略的 lineage | 显示当前策略和下游分析 | 不再显示空状态提示 |

- `INVALIDATED` 只是瞬时清空动作；视觉上直接回到 `EMPTY`。
- “空状态”指“页面还没有可消费的当前 artifact”，而不是“所有控件都隐藏”。

#### 3. 模型配置区条件渲染规则表

| 控件 / 步骤卡 | 可见条件 | 说明 |
|------|------|------|
| `Family` 选择卡 | 始终显示 | 固定先选 `Baseline / Search` |
| `Baseline` 类型卡 | `family=baseline` | 只显示 `Naive / Mean / Drift` |
| `Search Base` 选择卡 | `family=search` | 只显示 `SM / FSM` |
| `FA` 说明 / 参数卡 | `family=search` 且 `search_base=fsm` | 只作为 `FSM` 路径的前置步骤说明与参数入口，不单独产出结果区 |
| `参数搜索` 开关 | `family=search` 且 `search_base` 已选 | 属于可选增强步骤 |
| `参数搜索配置卡` | `family=search` 且 `search_base` 已选且 `use_search=True` | 包含 `bayesian / random / genetic` 等搜索配置 |
| `ML` 开关 | `family=search` 且 `search_base` 已选 | 属于可选增强步骤 |
| `ML 配置卡` | `family=search` 且 `search_base` 已选且 `use_ml=True` | 包含 `logistic / lgbm` 等模型配置 |
| `生成策略` 按钮 | 始终显示在第 3 段 | 未满足最小请求时禁用，不隐藏 |

- `Baseline` 选中后，主区只允许出现 baseline 相关控件和统一生成按钮。
- `Search` 选中后，必须先出现 `SM / FSM` 选择；只有基础模型确定后，增强步骤开关才出现。
- `FSM` 在生成前只显示“将先执行 `FA` 再进入 `FSM基础`”的步骤卡，不允许提前出现任何搜索结果卡。

#### 4. 统一“生成策略”交互定稿

- 主区只保留一个入口按钮：`生成策略`。
- 页面加载、切换股票、切换勾选项、切换展示选项时，均不允许自动触发整条链路计算。
- 按钮的最小可点击条件固定为：

| 路径 | 按钮可点击条件 |
|------|------|
| `Baseline` | `family + baseline_kind` 已完整 |
| `Search` | `family + search_base` 已完整；若 `use_search=True` 则 `search_method` 已完整；若 `use_ml=True` 则 `ml_model_type` 已完整 |

- 点击按钮后，先冻结 `request params_snapshot`，再进入 Day2 定义的编排层。
- `GENERATING` 状态下按钮禁用，且不允许重复点击并发启动第二条链路。
- 任何配置改动都只会把页面标记为 `REQUEST_DRAFT`，不会自动替换 `current_artifact`。

#### 5. “当前工作流比较”区定稿

- 本区只比较“当前策略内部的 stage 链路”，不比较 `saved_artifacts` 之间的长期版本。
- 数据源固定为 `current_artifact.pipeline_lineage`。
- `FA` 是 `FSM基础` 的前置计算，不单独渲染为可比较 stage 卡。
- “搜索结果区”不再是独立常驻区块；只有 lineage 中真的存在搜索 stage 时，才以 stage 卡形式出现。

| 路径 | 展示的 stage 卡 |
|------|------|
| `Baseline` | 仅 1 张基线卡，对应选中的 `Naive / Mean / Drift` |
| `SM` | `SM基础` |
| `SM + Search` | `SM基础`、`SM+Search` |
| `SM + ML` | `SM基础`、`SM+ML` |
| `SM + Search + ML` | `SM基础`、`SM+Search`、`SM+Search+ML` |
| `FSM` | `FSM基础` |
| `FSM + Search` | `FSM基础`、`FSM+Search` |
| `FSM + ML` | `FSM基础`、`FSM+ML` |
| `FSM + Search + ML` | `FSM基础`、`FSM+Search`、`FSM+Search+ML` |

- 当页面处于“有旧结果的 `REQUEST_DRAFT`”时，本区继续展示旧 lineage，但必须加“上次结果”标记。
- 本区的职责是解释“当前 artifact 是怎么生成出来的”，不是承担 Day4 的多策略长期对比。

#### 6. 旧区块去向与命名定稿

| 旧区块 | 新区块 / 新名称 | 显示条件 | 说明 |
|------|------|------|------|
| `策略建议` | `当前策略摘要` | `current_artifact` 存在时 | 只在 artifact 生成后显示，放入第 5 段顶部 |
| `高级策略搜索` | `模型配置区` 内的“参数搜索步骤卡” | `family=search` 且 `search_base` 已选 | 不再是永远可见的独立区块 |
| `搜索结果` | `当前工作流比较` 中的搜索 stage 卡 | lineage 中存在搜索 stage 时 | `FSM` 未经过 `FA -> FSM基础` 前不允许出现 |
| `测试集表现` | `策略库与下游分析` | 至少存在 1 个可消费 artifact 时 | 统一按 artifact 读取，不再按固定模型 payload 读取 |
| `测试集交易信号` | `策略库与下游分析` | 至少存在 1 个可消费 artifact 时 | 读取 artifact 的 `train/test sim_df`，支持训练/测试切换 |
| `Walk-Forward` | `策略库与下游分析` | `current_artifact` 存在时 | 不属于“当前工作流比较”区 |

#### 7. 主区布局草图

```text
[策略工作台入口 / 空状态]
  Step 1: 选择 Family（Baseline / Search）
  Step 2: 查看当前路径提示
  Step 3: 进入对应配置

[模型配置区]
  if Baseline:
    选择 Naive / Mean / Drift
  if Search:
    选择 SM / FSM
    if FSM:
      FA 说明 / 参数
    参数搜索开关
    if use_search:
      参数搜索配置卡
    ML 开关
    if use_ml:
      ML 配置卡

[生成区]
  生成策略按钮
  缺失项提示 / 草稿已变更提示 / 执行中状态

[当前工作流比较]
  读取 current_artifact.pipeline_lineage
  展示 stage 卡序列

[策略库与下游分析]
  当前策略摘要
  回测净值 / 回撤
  收益热图
  指标比较表
  交易信号
  Walk-Forward
```

### 当日产出
- 主区新布局草图。
- 区块顺序说明。
- 条件显示规则表。
- 旧区块去向与命名表。

### 验收标准
- 实现者能按文档重排页面，不会再把“策略建议”放在策略真正生成之前。
- 页面首次进入时，用户只看到模型选择，不会看到旧版那套默认全展开区块。

### 风险/依赖
- 依赖：现有 `ui/single_stock.py` 区块顺序和 session_state 用法。
- 风险：如果第三天只改展示文案、不改顺序规则，页面逻辑仍会保持旧结构。
