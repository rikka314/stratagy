# Post-Gate-2 动态专家组合 v1：跨窗口执行手册

> 文档角色：研究产品计划 / 跨窗口执行手册（对应 RPRS `docs/product-plans` 的组织方式）。
> 更新日期：2026-08-18。执行单位是一个可交接的研究窗口，而不是一次不可恢复的长命令。
> 状态：US W00–W07 与 CN_A W08–W10 已完成；本窗口额外完成了全新的四折 admission evidence chain。CN_A 以冻结的 `full_cn_a_deans_60` snapshot replay 生成 market-native adaptive artifact（60/60 main records success），US/CN_A 的 admission-specific Phase A–F 均为 ready。W11 严格四折结论为 US 1/4、CN_A 2/4 不劣于 adaptive router，均未达到 3/4；回撤与同口径换手门槛虽通过，W12 仍因前置条件不成立而 `blocked`，未启动 shadow mode。
>
> 当前起点：本项目的单股、多股、模型评估和报告页面已经可以运行。动态专家组合 Phase C–F 只存在于 `model-test`，没有改变 Streamlit 默认策略。W11 已用新输出目录完成严格市场内比较；下一步是保持 W12 blocked，并仅在新的、预先冻结的研究窗口出现时重新考虑准入。
>
> 产品边界：本计划只负责研究证据、市场隔离、可复现 source lock 和准入判断。只有通过研究准入后，才进入 Phase G 的 shadow mode；不在 UI rerun 时训练，不把未验证的新模型设为默认。

## 1. 这份手册解决什么

前置实现已经完成动态专家组合的研究代码，但还没有一份可以安全交给后续窗口执行的真实证据计划。本手册解决以下问题：

- 不把新 MoE / Bandit 策略混入原始 Phase 3B 基线，导致比较口径漂移；
- 不把工程代码 `complete` 误写成真实市场结果 `passed`；
- 不把两条市场链路的完成误写成跨市场准入结论；
- 不用 `--allow-pending` 生成看似完整的模型、权重或收益报告；
- 在 US 与 CN_A 各自独立完成后，再决定是否进入产品化 shadow mode；
- 让每个输出都能追溯到 config、seed、代码版本、数据快照、市场、股票和日期。

执行单位是“研究窗口”，不是一次长命令。长时间 full-run 必须先通过 preflight，并保留可暂停、可恢复的 campaign 状态。

### 1.1 这份计划完成后可以操作什么

以下能力只有在对应窗口通过验收后才可使用；它们不是当前 Phase C–F 代码已经自动拥有的线上功能。

| 可操作能力 | 入口 / 产物 | 可用条件与边界 |
|---|---|---|
| 本地网站与健康检查 | `run.bat`、`http://localhost:8501/strategy`、`/strategy/_stcore/health` | 用于页面和导出验收；网站可启动不代表研究证据已通过 |
| 可复现的市场专属研究 | `model-test` CLI、source manifest、逐日 artifacts | 同一市场的 config、seed、代码版本与数据快照均为 `ready` 且 hash 可验证 |
| A–F 阶段对照报告 | `model-test/outputs/moe_*_<market>/`、`report.md` | US 与 CN_A 分开运行；W11 前只生成市场专属研究结论 |
| 专家权重、动作和降级原因追踪 | daily weights / decision trace / manifest | 可检查 Cash、权重上限、换手、fallback 和 selected-action-only 反馈 |
| 研究证据只读展示 | `/strategy/model-evaluation`（后续 W12 接入） | 只读取冻结 artifact，不在 Streamlit rerun 时训练 |
| 非默认 shadow mode | 单股 workflow 的实验选项（W12） | 至少一个市场通过准入；异常自动回退 `adaptive_router_v1` |
| 报告与回滚 | HTML 导出、模型版本 / 数据哈希 / 生成时间、旧策略回退 | 未通过准入的结果只能作为研究消融，不得设为默认策略 |

### 1.2 当前的下一步决策

“重新带上新策略做全量测试”需要拆成两层，不能直接把 Phase C–F 混入原始 Phase 3B 基线：

1. W00 已完成环境、配置、source lineage 和成本口径盘点，未启动新的长时间 full-run；
2. W01 已将可验证的 `full_us_deans_60` 固定为唯一权威 US source；旧 Window 3B smoke 只保留历史记录；
3. US W03–W07 已在不使用 `--allow-pending` 的情况下完成，仍只产出 US-specific research evidence；
4. CN_A W08–W10 已在独立 clean worktree 完成，source snapshot、A–F manifest 与 artifact 均已锁定；
5. 现在才进入 W11 准入比较；只有通过准入的市场才进入 W12 shadow mode。

因此，当前不启动新的长时间 full-run，也不把 US 结果包装成跨市场有效。

## 2. 当前完成度与目标差距

| 能力 / 证据 | 当前状态 | 下一步 |
|---|---|---|
| US Phase 3B 全量实验 | `full_us_deans_60` source lock ready；旧 Window 3B 为非权威 smoke 记录 | W11 四折结果为 1/4，保持 research-only |
| CN_A Phase 3B 全量实验 | `full_cn_a_deans_60` ready，60 个冻结 CSV；admission replay 复用该 snapshot 并生成 native adaptive router | W11 四折结果为 2/4，保持 research-only |
| Phase A baseline materializer | 工程完成 | 只接受 ready、hash-verified 的 US/CN_A source |
| Phase B–F（US/CN_A） | admission-specific 两市场 A–F 均已完成并生成 ready、hash-verified artifacts | W11 已否决，保持 research-only |
| 产品化 Phase G | 未开始 | W12 blocked；不得启动 shadow mode |

“工程完成”不等于“研究准入通过”；W11 前所有结论必须保持市场专属，不能外推跨市场或产品默认化。

## 3. 统一执行协议

### 3.1 每个研究窗口的启动提示词

```text
执行 plan/post_gate2_model_upgrade_v1_execution.md 中的 WXX。

先读：
1. AI_CONTEXT.md
2. document/interfaces/dynamic-ensemble-research.md
3. 本计划的固定决策、依赖图、状态表与 WXX
4. 对应 Phase acceptance 文档和已有 source manifest

要求：
- 只完成 WXX，不提前启动后续长任务；
- 保留 US / CN_A 市场隔离，不把 CN_A 未完成包装成跨市场结论；
- 不使用 --allow-pending 生成研究证据；
- strategy_return 已经是净收益，不重复扣交易成本；
- 任何模型、权重和报告都必须记录 source manifest hash；
- 完成后运行本窗口验收命令并写交接记录；
- 只有整合窗口更新本计划状态表和 AI_CONTEXT.md。
```

### 3.2 研究窗口交接模板

```markdown
# WXX 交接

- 状态：complete / partial / blocked
- 市场：US / CN_A
- 完成范围：
- 未完成范围：
- 输入 config 与 source manifest：
- 关键决策：
- 修改文件：
- 产出目录与 artifact hash：
- 验收命令与结果：
- 收益与成本口径：
- 数据快照 / 代码版本 / seed：
- 后续窗口可依赖的接口：
- 已知风险或待人工处理：
```

### 3.3 完成定义

窗口只有同时满足以下条件才可标记 `complete`：

1. 依赖窗口已完成，或依赖接口已冻结并有可复核交接；
2. 市场、config、seed、数据 snapshot 和代码版本均可回溯；
3. ready manifest、artifact hash 和 source lineage 全部通过；
4. walk-forward、purge、embargo、成本口径和缺失专家检查通过；
5. 报告明确区分工程完成、真实证据完成、pending 和 blocked；
6. 测试通过且没有修改线上默认策略；
7. 两市场均完成后仍不得在 W11 前生成跨市场胜出或产品准入结论。

## 4. 固定决策与禁止事项

### 4.1 先修 source lock，再跑新策略

原始 Phase 3B / full-run 是专家池的输入，不是 Phase C–F 的被测策略。修复 US 时必须保持：

- 原专家候选和代表专家选择；
- 原训练 / rolling 窗口；
- seed、市场成本和净收益字段；
- 原始代码版本和 config 语义。

允许补充冻结数据快照、manifest 哈希和可审计的 lineage；不允许为了让 MoE 胜出而改测试窗口、成本、股票池或评分公式。

### 4.2 US / CN_A 独立运行

- US 可以在 CN_A 完成之前单独完成 A → F，并且只能写成 US-specific 研究结论；
- CN_A 的 Phase C–F 已完成真实 source-locked 运行，但在 W11 前不得宣称其跨市场胜出或产品准入；
- 跨市场模型只作为额外消融，不替代两个市场的主结果。

### 4.3 收益和成本口径

`strategy_return` 已经包含源策略的执行成本。Phase B–F 不得再次扣同一笔成本。Phase F 的 `incremental_action_switch_cost_bps` 只有在有独立部署成本模型时才启用，并且必须单独列出。

### 4.4 不得提前产品化

- 不在 Streamlit rerun 时训练模型；
- 不把 Phase C–F artifact 直接接入默认单股 workflow；
- artifact 缺失、损坏、schema 不匹配时必须回退到稳定旧路径；
- 只有通过准入门槛的市场才可以进入 shadow mode；
- 不因为单个股票、单个窗口或单一 Sharpe 指标好看就晋级。

## 5. 依赖图

```text
US Phase 3B source repair / freeze ─┐
                                    ├─> Phase A baseline ─> Phase B panel
CN_A full-scale experiment ─────────┘                         │
                                                             v
                                          Phase C MoE v1 ─> Phase D MoE v2
                                                             │
                                                             v
                                                   Phase E Hedge / EG
                                                             │
                                                             v
                                             Phase F contextual bandit
                                                             │
                                         market admission / comparison
                                                             │
                                                             v
                                                   Phase G shadow mode
```

US 与 CN_A 的每条链都必须使用本市场的 panel、source manifest 和 output directory；不能把 US panel 交给 CN_A config，反之亦然。

## 6. 状态表

状态只使用 `pending / in_progress / complete / blocked`。`complete` 表示该窗口交付并通过验收，不代表策略已经获准进入产品。

| 窗口 | 主题 | 市场 | 依赖 | 当前状态 |
|---|---|---|---|---|
| W00 | 研究环境、clean worktree、config 与 source 盘点 | US/CN_A | — | complete |
| W01 | US Phase 3B source lock 修复与冻结 | US | W00 | complete |
| W02 | US Phase A baseline materializer | US | W01 | complete |
| W03 | US Phase B expert-day panel | US | W02 | complete |
| W04 | US Phase C MoE v1 | US | W03 | complete |
| W05 | US Phase D MoE v2 | US | W04 | complete |
| W06 | US Phase E Hedge / EG | US | W05 | complete |
| W07 | US Phase F Bandit | US | W06 | complete |
| W08 | CN_A Phase 3B full-scale experiment | CN_A | W00 | complete |
| W09 | CN_A Phase A–B source chain | CN_A | W08 | complete |
| W10 | CN_A Phase C–F source chain | CN_A | W09 | complete |
| W11 | US/CN_A admission comparison与结论 | US/CN_A | W07、W10 | complete（无市场获准） |
| W12 | Product shadow mode 设计与回滚验证 | 通过准入的市场 | W11 | blocked（无市场通过 W11） |

W08–W10 仅在真实 full-run、source snapshot、ready manifest 和声明 artifact 哈希全部通过后标记 `complete`；这不代表 W11 准入通过。

## 7. Phase A：source lock 与基线冻结

### W00｜环境、状态和成本口径盘点

**目标：** 在启动长任务前确认工作树、依赖、配置、磁盘、数据日期和 source 目录状态。

**检查：**

```powershell
.\.venv\Scripts\python.exe model-test\preflight_research.py --config model-test\configs\full_us_deans_60.json
git status --short
```

当前 full-run config 有 `require_clean_worktree=true`；工作树有既有改动时，不能通过 `--allow-dirty` 伪装成正式冻结。先记录变更归属，再决定提交、隔离 worktree 或只做只读 preflight。

**完成记录（2026-08-16）：** preflight 对已有 full-run 正确返回非 ready：worktree 不 clean，且 output 已存在；CPU LightGBM、依赖、60 标的配置、最小数据日期 `2026-07-31` 和 D 盘约 267 GiB 可用空间均通过。未启动长时间 full-run。盘点确认 CN_A full-scale output 不存在；US `full_us_deans_60` 有 60 个冻结 CSV、16,751,317 bytes 和可复算 aggregate SHA-256。

**完成标准：** 明确 US source 的缺口、CN_A full-run 未完成、所需数据日期和预计磁盘；未启动长时间全量任务。

### W01｜US Phase 3B source lock 修复与冻结

**目标：** 把已完成的 US Phase 3B 全量实验变成可验证的 source lock。

**规则：**

- 优先复核现有实际完成 run 的 config、code version、数据文件和逐日 artifact；
- 若无法证明 snapshot 来自同一 run，则按原窗口和成本口径重建冻结 source；
- 不能把旧目录手工写成 ready，也不能伪造 `data.snapshot_sha256`；
- `deans_window3b_us` 当前配置若仍是 smoke 级别，不能把它冒充正式 full source。

**完成记录（2026-08-16）：** `full_us_deans_60` 是实际完成的 60 标的 full source：run ID `full_us_deans_60-20260810T102451Z`、source code version `1b3c1d3`、seed `42`、data snapshot `adb08e44cad749c275bdcad972bcb2898ad6014a587a5dbb1318ccb856bedc16`、source manifest `31aadc6d97479bf22c048a8b36e6e830382a1c938d32fedea72f50efeef088d9`。新增校验会逐个复算 60 个 CSV 的 hash / size 并复算 aggregate hash。`deans_window3b_us` 经复核为 6 标的 smoke run、没有 snapshot hash；它被显式迁为 `historical_runs` 的 `non_authoritative_smoke`，未写入任何伪造 hash，也不再阻塞或污染 Phase-A 权威 lineage。

**验收：** 权威 US full-run manifest、逐日 returns / trades / daily artifact、数据快照和聚合 SHA-256 可互相验证；`prepare_moe_baseline.py` 不再因 pending/hash 缺失失败。

### W02｜US Phase A baseline materializer

```powershell
.\.venv\Scripts\python.exe model-test\prepare_moe_baseline.py --config model-test\configs\moe_baseline_us.json
```

不得使用 `--allow-pending`。输出必须是 ready Phase-A manifest、三项冻结对照、专家池、成本口径和源 artifact lineage。

**完成记录（2026-08-16）：** strict materializer 退出码 `0`，写入 `model-test/outputs/moe_baseline_us/`。manifest 为 `ready`，source fingerprint 为 `865875dbf3b95e79fe239ed3cd4bee579a60da04a6c06d10e1f1272be4216b22`；三项 control 均为 ready，best single expert 为 `sm_bayesian`。详见 `document/acceptance/post_gate2_model_upgrade_w00_w02_20260816.md`。

### W03｜US Phase B 无泄漏专家面板

```powershell
.\.venv\Scripts\python.exe model-test\prepare_expert_panel.py --config model-test\configs\moe_baseline_us.json
```

重点验收 20 日 future utility、purged walk-forward、至少 20 日 embargo、point-in-time 特征、不可用专家显式标记和 `expert_day_panel.parquet` hash。失败专家不得填成零收益或优秀结果。

## 8. Phase C–F：US 新策略研究链

以下窗口都只消费 ready 的 US source，不改原始 full-run；每个命令失败关闭时先修输入，不用 pending 输出继续跑。

### W04｜US Phase C MoE v1

```powershell
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble.py --config model-test\configs\moe_v1_us.json
```

验证 no-state / regime-aware、best single expert、equal-weight 和 adaptive router 四类结果；确认 Cash、40% 单专家上限、权重和、缺失专家归一化、平滑与 fallback 原因。

### W05｜US Phase D MoE v2

```powershell
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble_v2.py --config model-test\configs\moe_v2_us.json
```

验证 quantile uncertainty、OOD、Cash/equal-weight/adaptive fallback、最大换手、权重变化、最小持有期、回撤去风险和 v1/v2 消融。风险控制改善必须来自多个窗口，而不是单一股票。

**完成记录（2026-08-17）：** 已复核 ready 的 `model-test/outputs/moe_v2_us/moe_v2_manifest.json`，manifest SHA-256 为 `8f1b7a8de08b4fdf499141ec55e78c21f3ae07a5cd6a37c240edf818434dffb9`，其 8 个声明 artifact 均存在且哈希匹配。它严格锁定同一 US Phase-A/B/C 输入，保持 20 日 horizon、`strategy_return` 与 `source_net_no_recharge`；40% 单风险专家上限以及 uncertainty / OOD / fallback 风险记录均保留。

### W06｜US Phase E Hedge / EG

```powershell
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble_online.py --config model-test\configs\moe_online_us.json
```

比较 Soft-MoE、Hedge、EG、固定/波动率自适应学习率和遗忘因子；确认完整反馈只在决策后进入更新，普通权重变化不超过 15%，漂移恢复测量不回灌模型。

**完成记录（2026-08-17）：** strict runner 成功生成 `model-test/outputs/moe_online_us/`，Phase-E manifest SHA-256 为 `20034b1eb3e70b535ad5b427369ffc363d8b85c67b725f6fdcb4800243c7771d`，5 个声明 artifact 全部哈希匹配。它从上述 Phase-D manifest 初始化，比较 Soft-MoE、Hedge、EG 的固定 / 波动率自适应学习率与遗忘因子；Cash、40% 风险专家上限和 15% 普通单日权重变化约束仍为冻结策略，漂移结果仅作为 evaluation-only 输出。

### W07｜US Phase F contextual bandit

```powershell
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble_bandit.py --config model-test\configs\moe_bandit_us.json
```

比较 LinUCB 与 Contextual Thompson Sampling；只使用所选 action 的下一时点反馈，Cash 永远可选，未选 action 只可出现在 evaluation-only 漂移测量中。若扣除探索/切换成本后不能稳定优于 Hedge / EG，保留为研究消融，不产品化。

**完成记录（2026-08-17）：** 配置的旧 context 列 `ret_5/state_id` 不存在于已冻结 US Phase-B panel，已改为实际存在且 point-in-time 的 `market_return_5/state_market_regime_id_20/target_position`；严格 runner 随后成功生成 `model-test/outputs/moe_bandit_us/`。Phase-F manifest SHA-256 为 `cebd726303e24b6cde44e6b1714652c59ef6c3f1b2f242aa1374eba306cb6edb`，7 个声明 artifact 全部哈希匹配，并锁定同一 Phase-E manifest。LinUCB / Contextual Thompson Sampling 只消费 selected-action-only 反馈，Cash 始终可选，action-switch cost 保持独立披露的 0。三个 walk-forward 中并未显示可稳定晋级 Hedge / EG 的证据，因此 Phase F 保持研究消融，不进入产品化。

## 9. CN_A 研究链

### W08｜CN_A Phase 3B full-scale experiment

**状态：** complete（2026-08-17，CN_A-specific evidence）。

使用市场专属 `full_cn_a_deans_60.json` 完成 60 只主池、1,260 日主窗口、4 个 rolling、统一 240 搜索预算、CN_A 3 bps commission + 5 bps slippage 和冻结 snapshot。隔离 worktree 为 `D:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy_w8_cn_a_20260817`，campaign 为 `post-gate2-w08-cn-a-20260817`。campaign 最终 `completed`，输出 4,740 条记录（4,474 success、240 SKIPPED、26 degraded）；60 个 snapshot CSV、23,520,695 bytes。

- snapshot SHA-256：`961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`
- source `data_manifest.json` SHA-256：`f46e4d677bbd051e91b27fd07625fa87f3b98ea9af45b28d67d4ef066e1d1aa`
- MLflow 3.15 file-store 兼容性通过 `MLFLOW_ALLOW_FILE_STORE=true` 完成 direct replay；source config、commit、snapshot、task records、成本和结果文件未改变，恢复说明保留在 campaign metadata。
- 完整输出已安全复制到主工作区 `model-test/outputs/full_cn_a_deans_60/`，并与隔离 worktree manifest / snapshot 一致；未覆盖不一致目录。

### W09–W10｜CN_A A → F

W08 source lock ready 后，严格按依赖、禁用 `--allow-pending` 依次完成：

```powershell
.\.venv\Scripts\python.exe model-test\prepare_moe_baseline.py --config model-test\configs\moe_baseline_cn_a.json
.\.venv\Scripts\python.exe model-test\prepare_expert_panel.py --config model-test\configs\moe_baseline_cn_a.json
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble.py --config model-test\configs\moe_v1_cn_a.json
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble_v2.py --config model-test\configs\moe_v2_cn_a.json
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble_online.py --config model-test\configs\moe_online_cn_a.json
.\.venv\Scripts\python.exe model-test\run_dynamic_ensemble_bandit.py --config model-test\configs\moe_bandit_cn_a.json
```

CN_A adaptive router 当前可以保持显式 unavailable；不得用 US SPY artifact 填补 CN_A。

**完成记录（2026-08-17）：** W09 Phase A/B 与 W10 Phase C–F 均为 `status=ready`、`market=CN_A`，每个 manifest 声明 artifact 均存在且 SHA-256 复算一致。Phase-A source lock 以独立 `build_phase_a_manifest(..., generated_at=<stored>)` 重算并与落盘 manifest 完全相等。

| 窗口 / 阶段 | 输出目录 | manifest SHA-256 | 声明 artifact | 关键结果 |
|---|---|---|---:|---|
| W09 / A | `model-test/outputs/moe_baseline_cn_a/` | `a9bf77abf4d715776941f33adc41d3d6815d6826dcc030f16955709e5bab423c` | baseline + source files | `best_single_expert=sm_bayesian`；`adaptive_router_v1=unavailable` |
| W09 / B | `model-test/outputs/moe_baseline_cn_a/` | `0161132c1498426aee311d453a8bac8d449eeee353be9a6bb9dd6f953e89c9bb` | 3 | 181,440 panel rows；3 purged splits；purge/embargo 20 日；validation/test 40 日 |
| W10 / C | `model-test/outputs/moe_v1_cn_a/` | `06f7c3a7b9ebbdc8f3abcf0c9add8dfc70f6503e3884151578a20b6587203067` | 5 | no-state / regime-aware MoE v1 |
| W10 / D | `model-test/outputs/moe_v2_cn_a/` | `c85d67e86323b4b5850e1527c3f50144d14cc2e5207ae05d76ae893282025d42` | 8 | uncertainty/OOD/fallback/risk controls；Cash 保持可用 |
| W10 / E | `model-test/outputs/moe_online_cn_a/` | `63b8061b0ad8c69ec730f5807ff35dfb412bbfc2086cf5f8dbbd12f626b311e3` | 5 | Soft-MoE / Hedge / EG；selected feedback 后更新；15% 普通日变动上限 |
| W10 / F | `model-test/outputs/moe_bandit_cn_a/` | `ecc72154f79414bf4469612843006829ee1e65345218fcfff835f4e0c9d8174c` | 7 | LinUCB / contextual Thompson；selected-action-only；switch cost 0 |

所有阶段使用 `strategy_return` 与 `source_net_no_recharge`，未重复扣成本；CN_A `adaptive_router_v1` 在 A–F 均显式 `known_unavailable`，未填入 US SPY artifact。W10 产出仍为 research-only，尚未产品化。

## 10. W11 研究准入与结论

### 10.1 必须输出的比较

| 维度 | US | CN_A |
|---|---|---|
| Window 3B / full source | ready 且可验证 | frozen `full_cn_a_deans_60` replay ready，native adaptive artifact 已生成 |
| 最佳单专家 / 等权 / adaptive router | 已用四折、同市场 control 比较 | 已用四折、market-native adaptive control 比较 |
| MoE v1 / v2 | admission-specific artifacts ready | admission-specific artifacts ready |
| Hedge / EG | admission-specific artifacts ready | admission-specific artifacts ready |
| LinUCB / CTS | admission-specific artifacts ready | admission-specific artifacts ready |
| 结论类型 | US-specific W11 结论 | CN_A-specific W11 结论；不得跨市场外推 |

### 10.2 准入门槛

新模型至少满足：

1. purged walk-forward、embargo 和时点可得性测试全部通过；
2. 所有收益使用同一净成本口径且无重复扣费；
3. 至少 3/4 rolling windows 不劣于 adaptive router；
4. 改善不能只来自少数股票，必须报告中位数、改善比例和尾部失败案例；
5. 最大回撤不能明显恶化，组合换手原则上不超过 adaptive router 的 1.25 倍；
6. config、seed、data snapshot、代码版本、模型 artifact、报告完整；
7. 缺失或损坏 artifact 能安全回退，旧 workflow 行为保持不变。

未达到时：保留完整研究报告，标注失败原因，停止产品化，不反复修改测试窗口或成本来追求更好曲线。

### 10.3 W11 完成记录（2026-08-18）

- 以新的 `moe_admission_*`、`moe_v1_admission_*`、`moe_v2_admission_*`、`moe_online_admission_*`、`moe_bandit_admission_*` 目录完成两市场 A → F；未覆盖旧 W10 outputs。Phase-B / Phase-D manifests 在 admission 工具中重新计算 SHA-256 并验证 source lock。
- Phase-B 固定输出四个 purged test split `wf_01`–`wf_04`（purge=20、embargo=20）。W11 的 `moe_v2_regime_aware` 判断使用同一 0..1 target-position 单位重算候选与 adaptive router 的执行换手。
- CN_A full replay 复用冻结 snapshot `961c865b...92058`，生成 market-native `rsm_adaptive_v1` artifact；main window 为 60/60 success。未使用 US/SPY artifact。
- US：只有 `wf_02` 总收益不劣于 adaptive router，即 **1/4**；所有 split 的最大回撤更浅，换手比为 `0.2804x / 0.2254x / 0.2241x / 0.2606x`。
- CN_A：`wf_02` 与 `wf_04` 总收益不劣，即 **2/4**；所有 split 的最大回撤更浅，换手比为 `0.2310x / 0.2866x / 0.2274x / 0.4119x`。
- 两个市场都未达到冻结的至少 3/4 非劣门槛；不得以较低换手、较浅回撤或个别标的改善比例替代该硬门槛。

结论：**US 与 CN_A 均未获产品 / shadow 准入；Phase C–F 继续保持 research-only。** 四折 evidence、source lock 与 W12 gate 记录见 `document/acceptance/post_gate2_model_upgrade_w11_w12_20260817.md`。

## 11. W12 产品化 shadow mode

只有 US 或 CN_A 至少一个市场通过准入，才可以开始 W12：

1. 新模型只作为单股 workflow 的非默认实验选项；
2. UI 只消费已冻结 artifact，不在页面现场训练；
3. artifact 缺失、损坏、schema 不匹配时自动回退 `adaptive_router_v1`；
4. 页面展示模型版本、训练范围、数据哈希、生成时间、权重和 fallback 原因；
5. 完成单股、模型评估页、HTML 导出和双语文案后，先 shadow mode；
6. 经过线上稳定性和回滚验证，再讨论默认化。

Phase F 本身没有产品接入资格；它只是“只能观察实际动作奖励”的部署场景对照实验。

### W12 gate 记录（2026-08-18）

W11 的四折结果为 US 1/4、CN_A 2/4，均低于 3/4。因此 W12 的“至少一个市场通过准入”前置条件为假。本窗口状态为 `blocked`，而非把没有部署的 shadow mode 写成 `complete`：没有新增单股 workflow 选项、Streamlit artifact reader、模型评估页展示、HTML 导出字段或双语文案，也没有改变 `adaptive_router_v1` 的既有默认 / 降级行为。详细回滚边界见 W11/W12 acceptance 记录。

## 12. 交付物与研究目录

每个市场输出独立目录，建议结构如下：

```text
model-test/outputs/
  moe_baseline_us/      # Phase A
  expert_panel_us/      # Phase B
  moe_v1_us/            # Phase C
  moe_v2_us/            # Phase D
  moe_online_us/        # Phase E
  moe_bandit_us/        # Phase F
```

关键产物必须包括 config snapshot、source manifest hash、数据快照 hash、逐日结果、summary、报告和 artifact manifest。`model-test/outputs/` 被 Git 忽略，不能因为未入 Git 就省略交接记录。

## 13. 验收命令清单

```powershell
# 静态与研究代码回归
.\.venv\Scripts\python.exe -m pytest tests\test_moe_phase_c.py tests\test_moe_phase_d.py tests\test_moe_phase_e.py tests\test_moe_phase_f.py -q

# 真实 full-run 前置检查；正式执行不使用 --allow-dirty
.\.venv\Scripts\python.exe model-test\preflight_research.py --config model-test\configs\full_us_deans_60.json
.\.venv\Scripts\python.exe model-test\preflight_research.py --config model-test\configs\full_cn_a_deans_60.json

# 每个阶段完成后检查对应 manifest status=ready、market、hash 与报告
```

当前 admission-specific US/CN_A A–F 真实执行和 manifest 核验均已完成；W11 用四个 split 完成同口径比较，US 1/4、CN_A 2/4，均没有形成产品准入。W12 因 gate 未通过而保持 blocked。

## 14. 当前最先执行什么

W00–W11 已完成，且没有改动线上默认路径。W12 不能启动；任何后续研究必须在预先冻结的市场内窗口、相同成本口径、同一 3/4 / 回撤 / 换手门槛下形成新的独立证据。CN_A 已具备 market-native adaptive router 基准，因此不得再把“baseline unavailable”当作缺口或借口；不得通过改成本、窗口或事后挑选参数绕开此次拒绝结论。
