# 模型逻辑重构工作单（Day 4-5）

> 目标周期：单股页策略工作流重构第 4-5 天  
> 文档定位：把 artifact 真正接入下游分析，并补齐状态边界  
> 关联范围：下游图表区、比较区、买卖点区、会话状态管理

---

## Day 4

### 当天目标
- 让“当前策略 + 已保存策略”真正进入后面的所有分析区。

### Day 4 定稿结论

#### 1. 策略库结构定稿

- Day 4 不新增第三份策略存储；“策略库”只是对 `strategy_workspace` 的一个读取视图，不是新的持久化容器。
- 底层状态仍然只有 `current_artifact` 和 `saved_artifacts` 两部分。
- `current_artifact` 是当前上下文里最新一次成功生成的最终策略，固定置顶，默认进入所有下游分析。
- `saved_artifacts` 是用户显式点击保存后冻结的会话内快照，只负责长期保留，不会被后续生成覆盖。
- “保存”不会把当前策略从下游拿掉；它只是让当前结果额外获得一个可长期保留的快照身份。

| 存储槽位 | 进入方式 | 是否会被覆盖 | 是否默认参与下游 | 说明 |
|------|------|------|------|------|
| `current_artifact` | 一次完整生成链路成功提交 | 会，被下一次成功生成替换 | 是 | 始终代表“当前最新策略” |
| `saved_artifacts[]` | 用户显式点击保存 | 不会被生成动作覆盖 | 否 | 只在用户勾选后参与多策略比较 |

#### 2. 下游统一读取源定稿

- 下游统一只读 `artifact`，不再读取页面初始化时的一次性全模型 payload。
- 下游候选集固定由 `current_artifact + saved_artifacts` 组合得到。
- 读取顺序固定为：`current_artifact` 在前，`saved_artifacts` 在后。
- `saved_artifacts` 的展示顺序固定为“最新保存的在前”，但其底层存储仍保持追加式列表；UI 层只负责倒序展示。
- 如果当前策略刚被保存成快照，策略库中允许同时存在“当前”和“已保存”两个逻辑入口；默认只自动选中“当前”，避免出现重复曲线。

#### 3. 下游展示状态定稿

- Day 4 额外引入的是“下游展示状态”，不是新的策略实体状态。
- 这组状态只服务展示，不参与生成链路和 artifact 生命周期。

| 状态键 | 含义 | 默认值 | 变更是否触发重算 |
|------|------|------|------|
| `selected_artifact_ids` | 当前勾选参与下游比较的 artifact 列表 | `[current_artifact.id]`（若存在） | 否 |
| `focus_artifact_id` | 当前用于单策略细看区块的主 artifact | 等于第一个被勾选的 artifact | 否 |
| `signal_dataset_split` | 买卖点查看读取 `train` 还是 `test` | `test` | 否 |

- `selected_artifact_ids` 面向多策略区块使用。
- `focus_artifact_id` 面向只能单策略展示的区块使用。
- `signal_dataset_split` 只影响读取 `train_sim_df` 还是 `test_sim_df`，不允许触发重新训练或重新回测。

#### 4. artifact 最小消费字段定稿

> Day 1 里 `StrategyArtifact` 的最小字段集合继续成立；Day 4 只把这些字段和具体下游区块一一绑定。

| 字段 | 用途 | 最低要求 | 首批消费区块 |
|------|------|------|------|
| `id` | 选择器状态、去重、主从定位 | 会话内唯一 | 全部区块 |
| `display_label` | 选择器文案、图例、表格行名 | 稳定可读 | 全部区块 |
| `pipeline_lineage` | 当前策略摘要、来源解释 | 可还原本次链路顺序 | 当前策略摘要 |
| `params_snapshot` | 当前策略摘要、参数说明 | 对应最终生效参数 | 当前策略摘要 |
| `equity_series` | 净值/回撤图 | 单条可对齐时间序列 | 回测净值/回撤 |
| `returns_series` | 周期收益热图 | 单条日收益序列 | 月度或周期收益热图 |
| `eval` | 指标比较表 | 标准化评估字典 | 指标比较表 |
| `train_sim_df` | 训练集买卖点查看 | 含日期、仓位、买卖信号等必要列 | 买卖点查看 |
| `test_sim_df` | 测试集买卖点查看 | 含日期、仓位、买卖信号等必要列 | 买卖点查看 |
| `ml_quality` | ML 质量展示 | `dict` 或 `None` | ML 质量展示 |

- `equity_series / returns_series / eval` 在第一周固定服务“下游比较口径”，默认沿用当前单股页测试期比较语义。
- `train_sim_df / test_sim_df` 保留双切片能力，仅在“买卖点查看”中按 `训练集 / 测试集` 切换消费。
- `ml_quality` 是条件字段；非 ML artifact 可以为 `None`，下游不强行补空卡片。
- `trades_df` 仍然保留在 artifact 里，但不属于 Day 4 首批强制接管区块的最小消费字段。

#### 5. artifact 消费矩阵定稿

| 区块 | 读取对象 | 选择粒度 | 必需字段 | 行为规则 |
|------|------|------|------|------|
| `当前策略摘要` | `current_artifact` | 单策略 | `display_label`、`pipeline_lineage`、`params_snapshot`、`eval` | 只解释“当前最新策略”，不混入 saved 快照 |
| `回测净值 / 回撤` | `selected_artifacts` | 多策略 | `id`、`display_label`、`equity_series` | 同一张图允许多条曲线；曲线顺序跟随选择器顺序 |
| `月度或周期收益热图` | `focus_artifact` | 单策略 | `display_label`、`returns_series` | 不把多条收益序列硬挤进一张热图；默认跟随主策略 |
| `指标比较表` | `selected_artifacts` | 多策略 | `id`、`display_label`、`eval` | 每个 artifact 一行，统一口径输出 |
| `买卖点查看` | `focus_artifact` | 单策略 | `display_label`、`train_sim_df`、`test_sim_df` | 通过 `signal_dataset_split` 在训练集 / 测试集间切换 |
| `ML 质量展示` | `selected_artifacts_with_ml` | 多策略筛选后展示 | `display_label`、`ml_quality` | 只渲染带 `ml_quality` 的 artifact；非 ML 策略直接跳过 |

- Day 4 首批被 artifact 接管的就是上表 6 类区块；它们必须全部改成“从 artifact 读数据”。
- `Walk-Forward` 暂不纳入多策略选择器；它在第一周仍按“当前最终策略专属区块”处理，边界放到 Day 5 再正式定稿。

#### 6. 多策略选择器行为规则定稿

| 规则 | 定稿结论 |
|------|------|
| 数据源 | 只来自 `current_artifact + saved_artifacts` |
| 选项顺序 | 固定 `当前策略` 在前，随后是 `已保存策略` 倒序列表 |
| 选项标签 | 使用 `display_label`，并在 UI 上补前缀 `当前` / `已保存`，而不是改写 artifact 内部字段 |
| 默认勾选 | 新生成成功后，默认只勾选 `current_artifact` |
| 保存动作后的勾选 | 保存当前策略后，不自动额外勾选新快照，避免同内容重复画线 |
| 允许空勾选吗 | 不允许；若用户全部取消，立即回退到 `current_artifact`，若不存在则回退到第一条已保存策略 |
| 主策略来源 | `focus_artifact_id` 必须始终属于 `selected_artifact_ids` |
| 主策略失效处理 | 若当前主策略被取消勾选，则自动回退到新的第一个被勾选策略 |
| 变更性质 | 纯展示行为，不触发任何重算、重新训练或 cache 失效 |

- 多策略选择器只解决“当前要看哪些 artifact”，不承担“生成哪个 artifact”的职责。
- 下游所有比较区块都先消费 `selected_artifact_ids`，再各自决定是多策略展示还是单策略细看。
- 单策略细看区块统一服从 `focus_artifact_id`，避免每个区块再做一套独立模型下拉框。

#### 7. 下游区块顺序定稿

Day 4 落地后，第 5 段“策略库与下游分析”内部顺序固定为：

1. `当前策略摘要`
2. `策略库 / 多策略选择器`
3. `回测净值 / 回撤`
4. `月度或周期收益热图`
5. `指标比较表`
6. `买卖点查看`
7. `ML 质量展示（按需出现）`

- 先给出当前策略解释，再进入策略库勾选，是为了让用户先知道“当前这条线是什么”。
- 回测曲线和比较表属于多策略主区块，放在前面。
- 热图和买卖点属于单策略细看区块，统一跟随 `focus_artifact_id`。
- `ML 质量展示` 不是所有路径都有，因此保持条件渲染。

### 当日产出
- artifact 消费矩阵：见上文 `artifact 消费矩阵定稿`。
- 下游区块读取字段说明：见上文 `artifact 最小消费字段定稿`。
- 多策略选择器的行为规则：见上文 `多策略选择器行为规则定稿`。

### 验收标准
- 实现者知道一个已生成策略要带哪些数据，才能被所有后续区块复用。
- 下游任一区块都不再依赖一次性全模型 payload。
- 实现者能够明确回答“哪些区块吃多策略集合，哪些区块只吃主策略”。
- 保存当前策略后，不会默认生成两条内容完全相同的对比线。

### 风险/依赖
- 依赖：`StrategyArtifact` 字段定义已经稳定。
- 风险：如果 artifact 字段不够完整，后面会重新引入“某个区块单独重算一遍”的坏味道。

---

## Day 5

### 当天目标
- 把状态边界、异常情况和会话行为补齐，避免重构后出现“能跑但状态全乱”。

### Day 5 定稿结论

#### 1. 保存命名与幂等规则定稿

- 第一周不引入用户自定义保存名称输入框。
- 保存动作不修改 artifact 内部的 `display_label`；`display_label` 仍然只表示策略本身，不表示“第几次保存”。
- “保存名称”是策略库 UI 层的派生标签，不反写回 artifact。
- 保存列表项的基准命名固定为：`已保存 · {display_label}`。
- 当 `saved_artifacts` 中已经存在同一基准名称但 `artifact.id` 不同的快照时，按出现顺序自动加序号：`已保存 · {display_label} (2)`、`(3)`。
- 若用户对同一个 `current_artifact.id` 重复点击保存，不新增重复快照；直接定位到已有保存项，并给出“当前策略已在策略库中”的提示。

| 场景 | 结果 |
|------|------|
| 第一次保存某个 `display_label` | `已保存 · {display_label}` |
| 保存另一个 `display_label` 相同但 `id` 不同的 artifact | `已保存 · {display_label} (2)` |
| 再保存第三个同名 artifact | `已保存 · {display_label} (3)` |
| 重复保存同一个 `artifact.id` | 不新增快照，只提示已存在 |

- `当前策略` 的展示标签仍然固定派生为 `当前 · {display_label}`。
- 编号只作用于“已保存策略”列表，不污染 `current_artifact` 的当前展示标签。

#### 2. 上下文变化后的清空规则定稿

> Day 1 已定义哪些字段构成 `context_key`；Day 5 只把“切换后到底清什么、留什么”补成执行规则。

以下任一变更都视为 `context reset`：

- 股票变化
- 市场变化
- 上传数据内容变化
- 日期范围变化
- 训练集比例变化

`context reset` 触发后必须立即处理：

| 键 / 状态 | 处理方式 | 说明 |
|------|------|------|
| `strategy_workspace.context_key` | 替换为新值 | 作为新的上下文边界 |
| `strategy_workspace.current_artifact` | 清空 | 不允许跨上下文沿用当前策略 |
| `strategy_workspace.saved_artifacts` | 清空 | 不允许跨上下文混比旧快照 |
| `selected_artifact_ids` | 清空 | 避免旧策略仍被勾选 |
| `focus_artifact_id` | 清空 | 避免焦点指向失效 artifact |
| `signal_dataset_split` | 重置为 `test` | 回到下游默认值 |

以下内容必须保留：

- 触发本次上下文变化的 widget 当前值
- 当前请求草稿配置
- 与旧 `context_key` 隔离后的 stage cache 骨架

补充约束：

- stage cache 不要求在物理上立刻删除旧上下文桶，但新 `context_key` 下绝不能读取旧桶结果。
- 如实现层有低成本清理旧 context bucket 的能力，可以做 opportunistic prune；这不是 Day 5 的必需行为。
- 上下文变化是“整包失效”，不是“只清当前策略、保留 saved”。

#### 3. 失败与降级路径定稿

- Day 5 把失败路径拆成两类：`硬失败` 和 `可降级失败`。
- `硬失败`：本次请求没有产出任何可提交的新 stage 结果，因此不替换 `current_artifact`。
- `可降级失败`：增强 stage 失败，但上游已有合法 `stage_result`，允许把最近一步成功结果提交为新的 `current_artifact`。

| 失败类型 | 发生位置 | 是否提交新 `current_artifact` | 保留什么 | 页面状态 | 用户提示 |
|------|------|------|------|------|------|
| `Baseline` 路径失败 | 基线仓位生成 / 回测 / 评估 | 否 | 保留旧 `current_artifact` 与 `saved_artifacts` | 回到 `REQUEST_DRAFT` | 错误提示：本次基线策略生成失败，当前仍显示上次成功结果 |
| `SM` 基础失败 | `SM基础` stage | 否 | 保留旧 `current_artifact` 与 `saved_artifacts` | 回到 `REQUEST_DRAFT` | 错误提示：`SM基础` 未成功生成 |
| `FA` 失败 | `FSM` 路径的 `fit_fa` 或 `FA` 前置处理 | 否 | 保留旧 `current_artifact` 与 `saved_artifacts` | 回到 `REQUEST_DRAFT` | 错误提示：`FA` 失败，本次不生成 `FSM` 结果 |
| `FSM` 基础失败 | `FA` 成功后、`FSM基础` stage 内部 | 否 | 保留旧 `current_artifact` 与 `saved_artifacts` | 回到 `REQUEST_DRAFT` | 错误提示：`FSM基础` 未成功生成 |
| 参数搜索失败 | `SM+Search` 或 `FSM+Search` 的搜索 stage | 是，回退提交基础 stage | 提交 `SM基础` 或 `FSM基础`；保留 `saved_artifacts` | 进入 `CURRENT_READY` 或 `CURRENT_AND_SAVED` | 警告提示：参数搜索失败，已回退到基础策略 |
| `ML` 失败 | `ML` stage | 是，回退提交最近成功上游 stage | 提交 `SM基础 / SM+Search / FSM基础 / FSM+Search`；保留 `saved_artifacts` | 进入 `CURRENT_READY` 或 `CURRENT_AND_SAVED` | 警告提示：`ML` 失败，已保留无 `ML` 的上游结果 |

补充约束：

- `FA` 失败时，不允许偷偷回退成 `SM`；`FSM` 请求失败就是 `FSM` 请求失败。
- 搜索失败时，只能回退到当前链路已成功的基础 stage，不允许回退到更早的历史 `current_artifact` 作为“新结果”提交。
- `ML` 失败时，只能回退到最近一步成功的上游 stage，不允许继续向下游拼装一个“伪 ML artifact”。
- 任一步失败后，都不允许跳过该 stage 继续硬跑后续步骤。

#### 4. `Walk-Forward` 边界定稿

- 第一周明确不把 `Walk-Forward` 结果并入策略库。
- `Walk-Forward` 只绑定 `current_artifact`，不绑定 `saved_artifacts`。
- `Walk-Forward` 不进入 `selected_artifact_ids`，也不受多策略选择器控制。
- 点击“保存当前策略”不会额外保存一份 `Walk-Forward` 快照。
- 当 `current_artifact` 被新的成功结果替换，或 `context reset` 触发时，旧的 `Walk-Forward` 结果视为失效并应清空。
- 页面上 `Walk-Forward` 的显示条件仍然是“当前存在 `current_artifact`”；没有当前策略时直接隐藏，不做空列表比较。

#### 5. 状态迁移表定稿

| 事件 | 进入前状态 | 进入后状态 | 保留 | 清空 / 重置 | 页面表现 |
|------|------|------|------|------|------|
| 首次进入页面 | 无 | `EMPTY` | widget 默认值 | `current_artifact`、`saved_artifacts`、下游展示状态均为空 | 只显示工作台入口和空状态提示 |
| 生成当前策略成功 | `EMPTY` / `REQUEST_DRAFT` / `CURRENT_READY` / `CURRENT_AND_SAVED` | `CURRENT_READY` 或 `CURRENT_AND_SAVED` | `saved_artifacts`、当前 widget 草稿 | 未保存的旧 `current_artifact` 被新结果覆盖；`selected_artifact_ids` 重置为 `[new_current.id]`；`focus_artifact_id=new_current.id`；`signal_dataset_split=test` | 下游立即切到新当前策略 |
| 保存当前策略成功 | `CURRENT_READY` / `CURRENT_AND_SAVED` | `CURRENT_AND_SAVED` | `current_artifact`、现有 `saved_artifacts`、当前下游勾选 | 不自动新增勾选，不重置 `focus_artifact_id` | 策略库新增一个已保存项；当前显示保持不跳动 |
| 重复保存同一当前策略 | `CURRENT_AND_SAVED` 或 `CURRENT_READY` | 原状态不变 | 全部保留 | 无 | 只提示“当前策略已在策略库中” |
| 切换上下文 | 任意状态 | `INVALIDATED` 后立即回到 `EMPTY` | 触发变化的 widget 值 | `current_artifact`、`saved_artifacts`、`selected_artifact_ids`、`focus_artifact_id` 清空；`signal_dataset_split=test` | 旧结果全部消失，回到空状态 |
| 生成失败且无可降级结果 | `GENERATING` | `REQUEST_DRAFT` | 旧 `current_artifact`、`saved_artifacts`、原下游勾选 | 不提交新结果 | 若有旧结果则继续显示并标记“上次结果”；否则回到无结果草稿态 |
| 生成失败但存在可降级上游结果 | `GENERATING` | `CURRENT_READY` 或 `CURRENT_AND_SAVED` | `saved_artifacts`、当前 widget 草稿 | 提交降级后的 `current_artifact`；`selected_artifact_ids` 重置为 `[fallback.id]`；`focus_artifact_id=fallback.id`；`signal_dataset_split=test` | 下游显示降级结果，并展示 warning |
| 切换下游展示项 | `CURRENT_READY` / `CURRENT_AND_SAVED` | 原状态不变 | `current_artifact`、`saved_artifacts` | 只更新 `selected_artifact_ids` / `focus_artifact_id` / `signal_dataset_split` 中对应项 | 只刷新展示，不触发重算 |

#### 6. 空状态文案表定稿

| 场景 | 触发条件 | 文案 |
|------|------|------|
| 无当前策略 | `current_artifact is None` | `请选择模型路径并生成第一条策略。` |
| 无保存策略 | `saved_artifacts` 为空，且存在 `current_artifact` | `当前还没有已保存策略。保存当前策略后，这里会形成本次会话的策略库。` |
| 无可比较策略 | 当前可用 artifact 少于 2 条，或当前只勾选了 1 条策略 | `当前仅有 1 条可比较策略。保存更多快照或额外勾选策略后，可进行多策略比较。` |

补充约束：

- “无当前策略”是主空状态，优先级最高；出现时不再展示“无保存策略”或“无可比较策略”提示。
- “无保存策略”是策略库提示，不阻止当前策略进入下游分析。
- “无可比较策略”是比较提示，不等于页面空状态；单策略图表仍可正常显示。

### 当日产出
- 状态迁移表：见上文 `状态迁移表定稿`。
- 异常处理表：见上文 `失败与降级路径定稿`。
- 空状态文案表：见上文 `空状态文案表定稿`。

### 验收标准
- 实现者不需要自行决定“失败后页面该怎么显示”“旧策略什么时候该清掉”。
- 任何人都能根据状态迁移表判断 session_state 应该保留什么、清掉什么。
- 实现者能够明确回答“硬失败时为什么保留旧结果、可降级失败时为什么提交上游结果”。
- `Walk-Forward` 的边界不会再和策略库、多策略选择器混在一起。

### 风险/依赖
- 依赖：Day 1 已经定义 `current strategy`、`saved strategy`、`context reset` 语义。
- 依赖：Day 4 已经定义下游展示状态和多策略选择器语义。
- 风险：如果第五天不补齐状态边界，后续会出现缓存命中错乱、跨股票混比、旧策略污染新页面。
