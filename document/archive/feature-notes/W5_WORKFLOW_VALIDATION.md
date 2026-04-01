# W5 工作流验证记录

> 记录日期：2026-03-26  
> 目标：完成 `plan/week5.md` 大任务 5 的最小留痕，给出 Day6 `C1-C9`、`E1-E8` 与关键行为约束的可复核执行记录。

---

## 1. 验证口径

- 执行命令：`.\.venv\Scripts\python.exe scripts/validate_w5_workflow.py`
- 数据样本：仓库内 `data/aapl_clean_daily.csv` 尾部 `800` 行
- 市场 / 标的：`US / AAPL`
- 切分方式：时间顺序 `70%` 训练、`30%` 测试
- 搜索参数：`search_trials=3`
- 预设参数：复用侧边栏默认可运行预设；脚本内部固定 `use_trend_filter/use_strength_filter/use_rsi_filter/use_macd_filter=True`
- 验证分层：
  - 编排层直跑：`C1-C9`、`E1-E4`、`B2`
  - 页面级 `AppTest`：`E5-E8`、`B1`

补充说明：

- `C1-C9` 逐条校验 `pipeline_lineage`、`current_artifact` 提交、下游默认选中状态，以及 `ml_quality` 出现条件。
- `E1-E4` 通过 `unittest.mock.patch` 注入 `FA / Search / ML` 故障，验证失败或降级路径。
- `E5-E8` 使用 `streamlit.testing.v1.AppTest` 验证保存幂等、`context reset`、同会话 rerun 与新会话刷新行为。
- 在本轮验证中发现并修复了 1 个语义偏差：
  - `context reset` 原先只清空 `workspace` 与下游展示状态，未清空请求草稿控件，页面会回到 `REQUEST_DRAFT` 而不是 `EMPTY`。
  - 现已在 [`ui/single_stock.py`](/d:/Learn/20_Projects/2026_SPRING/AIE1902/课堂内容/stratagy/ui/single_stock.py) 中补充请求草稿状态清理，`context reset` 后会同时清空 `family / baseline / search / ml` 相关 widget 状态。

---

## 2. C 路径矩阵

| 用例 | 请求路径 | 实际 lineage | 结果 |
|------|----------|--------------|------|
| `C1` | `Baseline` | `Naive（买入持有）` | 通过 |
| `C2` | `SM` | `SM基础` | 通过 |
| `C3` | `SM + Search` | `SM基础 -> SM+Search` | 通过 |
| `C4` | `SM + ML` | `SM基础 -> SM+ML-LR` | 通过 |
| `C5` | `SM + Search + ML` | `SM基础 -> SM+Search -> SM+Search+ML-LR` | 通过 |
| `C6` | `FSM` | `FSM基础` | 通过 |
| `C7` | `FSM + Search` | `FSM基础 -> FSM+Search` | 通过 |
| `C8` | `FSM + ML` | `FSM基础 -> FSM+ML-LR` | 通过 |
| `C9` | `FSM + Search + ML` | `FSM基础 -> FSM+Search -> FSM+Search+ML-LR` | 通过 |

共性检查结果：

- 9 条路径全部只生成被请求的 stage 组合，未出现串跑到未选 family 的情况。
- 每条成功路径都会提交新的 `current_artifact`，并把：
  - `selected_artifact_ids` 重置为 `[current_artifact.id]`
  - `focus_artifact_id` 重置为 `current_artifact.id`
  - `signal_dataset_split` 重置为 `test`
- `FSM` 系列路径均未把 `FA` 渲染为独立 lineage stage。
- 所有带 `ML` 的路径都产出非空 `ml_quality`；不带 `ML` 的路径 `ml_quality=None`。
- 所有带 `Search` 的路径均未写入旧版 `best_params / apply_best_params` session_state 键。

---

## 3. E 失败与边界矩阵

| 用例 | 场景 | 实际结果 | 结果 |
|------|------|----------|------|
| `E1` | `Baseline` 非法携带 `use_search=True` | 校验失败，不生成 artifact，保留旧 `current_artifact` | 通过 |
| `E2` | `FSM` 路径 `FA` 失败 | 返回 `failed`，不提交新 artifact，保留旧 `current_artifact` | 通过 |
| `E3` | `Search` stage 失败 | 返回 `degraded`，回退到基础 `SM` stage | 通过 |
| `E4` | `ML` stage 失败 | 返回 `degraded`，回退到最近成功上游 `SM+Search` | 通过 |
| `E5` | 重复保存同一 `artifact.id` | `saved_artifacts` 保持 `1` 条，不新增重复快照 | 通过 |
| `E6` | `context reset` | 清空 `current_artifact / saved_artifacts / 请求草稿 / 下游展示状态`，页面回到 `EMPTY` | 通过 |
| `E7` | 同会话 rerun | `current_artifact` 与 `saved_artifacts` 保留 | 通过 |
| `E8` | 新会话 / 刷新 | 新 `AppTest` 会话不恢复旧策略库，页面从空状态开始 | 通过 |

关键降级文案摘录：

- `E3`：`参数搜索失败，已回退到基础策略：forced search failure`
- `E4`：`ML 失败，已保留最近一步成功结果：forced ML failure`

---

## 4. 行为与缓存补充检查

| 用例 | 检查项 | 实际结果 | 结果 |
|------|--------|----------|------|
| `B1` | 同会话生成新策略替换当前策略 | `current_artifact` 从 `Naive` 替换为 `SM基础`，且下游默认选中同步重置到新 artifact | 通过 |
| `B2` | stage cache 命中边界 | `SM基础` 在追加 `Search + ML` 时命中缓存；同一完整请求再次执行时 `SM/Search/ML` 三阶段全部命中缓存 | 通过 |

`B2` 的命中口径如下：

- 第 1 次生成 `SM` 基础路径：无 cache 命中提示
- 第 2 次在同一上下文生成 `SM + Search + ML`：提示 `SM基础 命中缓存。`
- 第 3 次重复生成相同 `SM + Search + ML` 请求：提示 `SM基础 命中缓存。`、`参数搜索阶段命中缓存。`、`ML 阶段命中缓存。`

---

## 5. 收口结论

- `scripts/validate_w5_workflow.py` 已把 W5 的最小回归矩阵固化为可重复执行脚本。
- 本次执行结果为 `19/19` 通过：
  - `C1-C9`：`9/9`
  - `E1-E8`：`8/8`
  - 补充行为检查：`2/2`
- W5 大任务 5 的最低交付已完成：
  - 自测矩阵已有执行记录
  - `context reset` 的页面语义已与 Day6/Day7 文档对齐
  - 项目级上下文已同步，可供后续 W6 继续复用

本轮未新增公开接口，因此未同步修改 `document/MODULE_INTERFACES.md`；该文档在 W5 大任务 1-4 完成时的接口说明仍然成立。
