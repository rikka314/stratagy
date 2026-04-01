# model-test 代码级介绍

> 适用范围：`model-test/` 离线研究工作区  
> 目标：解释这个模块“是什么、为什么存在、怎么跑、怎么复用主项目、怎么评分、会产出什么”，并尽量下钻到当前代码实现，而不是只停留在概念层。

## 1. 它是什么

`model-test` 不是一个独立的新策略引擎，而是一个“离线批量研究外壳”。

它做的事情是：

1. 从股票池里挑出一批股票。
2. 为每只股票构造主窗口和滚动窗口。
3. 为每个窗口批量构造多个 `StrategyRequest`。
4. 复用 `ui/single_stock_workflow.py` 里的 `run_strategy_pipeline()` 跑策略。
5. 把结果结构化保存成 `runs.csv / model_summary.csv / report.json` 等研究产物。
6. 可选补充 QuantStats、MLflow、adaptive regime artifacts。

所以它的定位不是“在线分析页”，也不是“新的 core 策略模块”，而是：

- 上游复用 `core/*` 和 `ui/single_stock_workflow.py`
- 下游服务 `model-test/outputs/*`
- 再由 `ui/model_evaluation.py` 只读消费已有研究结果

这也是为什么它被放在 `model-test/` 工作区，而不是直接塞进 `app.py` 路由逻辑里。

## 2. 先看入口

最外层入口非常薄：

```python
# model-test/run_research.py
from model_test.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
```

真正的主流程在 `model-test/model_test/runner.py` 的 `run_research()`。

运行方式来自 `model-test/docs/README.md`：

```bash
python model-test/run_research.py --config model-test/configs/us_v2.json
python model-test/run_research.py --config model-test/configs/us_v2_locked_240.json
python model-test/run_research.py --config model-test/configs/us_v2_fast.json
```

## 3. 目录职责

`model-test/` 目录里最重要的文件分工如下：

| 文件 | 责任 |
|---|---|
| `run_research.py` | CLI 薄入口 |
| `model_test/__init__.py` | 设置 `WORKSPACE_ROOT / REPO_ROOT`，把路径插入 `sys.path`，压低 Streamlit 日志噪音 |
| `model_test/models.py` | dataclass 定义，规定 config / task / run record / summary 的数据骨架 |
| `model_test/config.py` | 读取 JSON 配置，构造 `ResearchConfig`、Stage A/Stage B 模型列表、窗口规格、冻结参数快照 |
| `model_test/universe.py` | 构建研究股票池，处理 sample / catalog / cache / bucket / balanced sampling |
| `model_test/execution.py` | 批量执行任务，按 `symbol + window` 分组，调用 `run_strategy_pipeline()` |
| `model_test/summarize.py` | 从 `runs.csv` 风格的记录表聚合模型评分、segment 结论、robustness 结论 |
| `model_test/reporting.py` | 把 summary 组装成 `report.json` 和 `report.md` |
| `model_test/observability.py` | 写每个 run 的最小分析包，生成 QuantStats，记录 MLflow |
| `model_test/adaptive_router.py` | 离线训练 adaptive regime router 的状态模型和路由策略 |
| `configs/*.json` | 研究配置模板 |

## 4. 和主项目的关系

`model-test` 最关键的设计是“复用现有单股工作流”。

它没有自己重写一套 baseline / SM / FSM / ML / regime 流程，而是直接调用：

```python
# ui/single_stock_workflow.py
run_strategy_pipeline(
    *,
    context_key: str,
    request: StrategyRequest,
    request_params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
) -> PipelineRunResult
```

`StrategyRequest` 当前支持三条大路径：

```python
class StrategyRequest:
    family: Literal["baseline", "search", "regime"] | None = None
    baseline_kind: Literal["naive", "mean", "drift"] | None = None
    search_base: Literal["sm", "fsm"] | None = None
    regime_kind: Literal["dual_state_router", "no_market", "no_router", "adaptive_router_v1"] | None = None
    use_search: bool = False
    search_method: Literal["bayesian", "genetic", "random"] | None = None
    use_ml: bool = False
    ml_model_type: Literal["logistic", "lgbm"] | None = None
```

`model-test` 做的是：

- 批量构造这些 request
- 控制输入窗口
- 管理并行
- 汇总输出

策略本身的计算仍走主链。

## 5. 总调用链

当前代码的主调用链可以概括成：

```text
run_research.py
  -> model_test.runner.main()
  -> model_test.runner.run_research(config_path)
     -> load_research_config()
     -> build_stock_profiles()
     -> build_stage_a_model_specs()
     -> execute_tasks(stage A main)
        -> run_task_batch()
           -> run_strategy_pipeline()
     -> build_model_summary()
     -> pick_stage_b_winners()
     -> build_stage_b_model_specs()
     -> execute_tasks(stage B main)
     -> build_rolling_tasks()
     -> execute_tasks(rolling robustness)
     -> generate_quantstats_outputs()
     -> build_report_payload()
     -> render_report_markdown()
     -> write runs.csv / report.json / report.md ...
```

如果打开 adaptive regime，还会在 Stage A 常规模型跑完后额外进入：

```text
train_adaptive_router_artifacts()
  -> collect candidate stage outputs
  -> train adaptive state model
  -> build candidate_state_day_rows
  -> select_routing_policy()
  -> save_adaptive_regime_artifacts()
```

## 6. 核心数据结构

### 6.1 `ResearchConfig`

`model-test/model_test/models.py` 里的 `ResearchConfig` 是整个研究运行时的总开关。当前字段很多，但可以按功能分组理解：

**基础运行**

- `name`
- `market`
- `adjust`
- `preset_name`
- `train_ratio`
- `parallelism`
- `output_subdir`

**可观测性**

- `enable_mlflow`
- `mlflow_experiment_name`
- `mlflow_tracking_uri`
- `enable_quantstats`
- `quantstats_top_n`

**股票池与样本**

- `sample_data_dir`
- `catalog_path`
- `smoke_symbols`
- `smoke_mode`
- `main_pool_size`
- `min_history_days`
- `profile_lookback_days`
- `min_avg_dollar_volume`
- `max_catalog_candidates`
- `cache_dir`
- `universe_parallelism`

**阶段控制**

- `run_stage_b`
- `run_robustness`

**窗口控制**

- `main_window_days`
- `minimum_window_days`
- `allow_short_main_window`
- `rolling_window_days`
- `rolling_step_days`
- `rolling_window_count`
- `robustness_top_n`

**搜索与评分**

- `search_trials`
- `ga_population_size`
- `ga_generations`
- `robustness_weight`
- `score_weights`

**研究专用覆盖**

- `request_params_overrides`
- `stage_b_request_overrides`
- `selected_model_ids`
- `merge_into_existing_output`

`load_research_config()` 会把 JSON 读成这个 dataclass，并做几件关键事：

1. `parallelism=0` 或 `"auto"` 会转成硬件自适应值。
2. `universe_parallelism` 也会自动解到 `min(16, max(4, parallelism))` 风格的值。
3. `score_weights` 会用默认权重补全。
4. 当前强制只支持 `US`，否则直接报错。

### 6.2 `ModelSpec`

`ModelSpec` 表示“一个要跑的模型方案”：

- `model_id`
- `display_name`
- `stage`
- `family_group`
- `request_payload`
- `notes`

其中 `build_request()` 会把 `request_payload` 直接转成 `StrategyRequest`。

### 6.3 `WindowSpec`

`WindowSpec` 用于描述某个时间窗口：

- `window_id`
- `kind`: `"main"` 或 `"rolling"`
- `start_idx`
- `end_idx`
- `train_ratio`
- `available`
- `reason`

如果窗口不可用，任务不会硬跑，而是生成 `SKIPPED` 记录。

### 6.4 `TaskSpec`

`TaskSpec` 是真正送进执行器的最小任务单元，包含：

- 股票信息：`symbol/company_name/segment_key/...`
- 数据定位：`data_path/market/adjust`
- 策略定义：`model`
- 窗口定义：`window`
- 冻结参数：`params_snapshot`

### 6.5 `RunRecord`

`RunRecord` 是 `runs.csv` 的行级结构，也是整个研究系统最重要的落盘 contract。它包含：

- 基本定位：股票、模型、阶段、窗口
- 状态信息：`status/error_message/warnings_json/info_messages_json`
- 可追踪信息：`lineage_json/params_snapshot_json/metadata_json/ml_quality_json`
- 产物路径：`artifact_dir/returns_path/equity_path/...`
- 训练指标：`train_annret/train_sharpe/...`
- 测试指标：`test_annret/test_sharpe/test_excess_return/...`
- ML 指标：`ml_precision/ml_recall/ml_f1/ml_pr_auc/...`
- 泛化差：`train_test_gap`

后面的所有 summary 基本都从这个结构聚合。

## 7. 配置系统是怎么装配的

### 7.1 冻结参数快照

`build_request_params_snapshot(config)` 会从 `core.config.STRATEGY_PRESETS` 取 preset，然后再叠加：

```python
{
    "strategy_preset": preset_name,
    "use_trend_filter": True,
    "use_strength_filter": True,
    "use_rsi_filter": True,
    "use_macd_filter": True,
    "use_voting_entry": False,
    "entry_vote_threshold": 2.5,
}
```

最后再叠加 `config.request_params_overrides`，并调用 `freeze_params_snapshot()` 冻结。

这意味着：

- `model-test` 并不是把 UI 的整个 session state 搬过来
- 它只保留 workflow 关心的稳定参数子集
- 研究配置可以覆盖这些冻结参数

### 7.2 当前默认主评分权重

`model-test/model_test/config.py` 当前默认主评分权重是：

```python
DEFAULT_SCORE_WEIGHTS = {
    "beat_naive_rate": 20.0,
    "median_excess_return": 15.0,
    "median_sharpe": 15.0,
    "drawdown_control": 15.0,
    "stability": 20.0,
    "overfit_discipline": 10.0,
    "reliability": 5.0,
}
DEFAULT_ROBUSTNESS_WEIGHT = 0.4
```

这和旧版本相比，当前实现更强调：

- `stability`
- rolling robustness 的最终合成权重

### 7.3 搜索预算摘要

`build_search_budget_summary()` 会统一算出：

- `random_trials`
- `bayesian_trials`
- `ga_population_size`
- `ga_generations`
- `ga_total_evals = ga_population_size * (ga_generations + 1)`
- `effective_search_budget = min(search_trials, ga_total_evals)`
- `uniform_objective_budget`
- `search_seed = 42`

这个摘要后来会写进：

- `report.json`
- 部分 run 的 `metadata_json.search_budget`

## 8. 股票池构建逻辑

### 8.1 smoke 模式

`build_stock_profiles(config)` 在 `smoke_mode=true` 时会走 `build_smoke_profiles()`：

- 直接遍历 `smoke_symbols`
- 优先读 `sample_data_dir`
- 生成每只股票的 `StockProfile`
- 再打 `trend_bucket / volatility_bucket / segment_key`

### 8.2 主研究池模式

非 smoke 模式走 `build_main_research_profiles()`：

1. 从 `catalog_path` 读取股票目录。
2. 过滤掉 ETF、ETN、TRUST、SPAC 等非普通股票候选。
3. 最多取 `max_catalog_candidates` 个候选。
4. 并发加载或构建每只股票的 profile。
5. 过滤掉不满足以下条件的股票：
   - 历史长度不足
   - 近一年样本不足
   - 平均成交额不足
6. 给剩余股票打 bucket。
7. 用 `_select_balanced_sample()` 按 `Up/Flat/Down x Low/Mid/High` 轮转抽样。

### 8.3 profile 是怎么计算的

`_compute_recent_profile()` 用近 `profile_lookback_days` 天计算：

- `total_return_1y`
- `annualized_vol_1y`
- `max_drawdown_1y`
- `avg_dollar_volume_1y`

之后 `_assign_buckets()` 会把：

- 收益 > 20% 判成 `Up`
- 收益 < -10% 判成 `Down`
- 中间判成 `Flat`

波动率用三分位切成：

- `Low`
- `Mid`
- `High`

最终拼成 `segment_key = f"{trend_bucket}__{volatility_bucket}"`。

### 8.4 universe cache

这里有两层 cache：

**profile cache**

- 路径：`model-test/cache/profiles/<signature>/<SYMBOL>.json`
- 失效条件：
  - 源 CSV 不存在
  - 源 CSV 的 `mtime` 或 `size` 变化
  - `market/adjust/profile_lookback_days` 变化

**pool cache**

- 路径：`model-test/cache/research_pool/<signature>.json`
- 失效条件：
  - catalog 文件元信息变化
  - pool 相关配置变化

这两层 cache 的目的不是改变结果，而是减少重复 profile 计算和 pool 过滤耗时。

## 9. 窗口构建逻辑

### 9.1 主窗口

`build_main_window(config, df_len)` 的规则是：

- 数据足够长：取最后 `main_window_days`
- 不够长但允许短主窗口：只要 `>= minimum_window_days` 就整段使用
- 否则标记 `available=False`

也就是说，主窗口默认更偏“固定长度后视研究”，不是从上市第一天一路全跑。

### 9.2 滚动窗口

`build_rolling_windows(config, df_len)` 会构造：

- `rolling_1`
- `rolling_2`
- `rolling_3`

每个窗口长度是 `rolling_window_days`，相邻窗口按 `rolling_step_days` 错开。

如果某个窗口切不出来，就记成 `available=False`，后续生成 `SKIPPED`。

## 10. 模型清单是怎么生成的

### 10.1 Stage A

`build_stage_a_model_specs(config)` 当前会生成：

**baseline**

- `naive`
- `mean`
- `drift`

**基础搜索族**

- `sm`
- `fsm`

**regime 族**

- `rsm`
- `rsm_no_market`
- `rsm_no_router`
- `rsm_adaptive_v1`

**带搜索器的方案**

- `sm_bayesian`
- `sm_random`
- `sm_genetic`
- `fsm_bayesian`
- `fsm_random`
- `fsm_genetic`

如果配置里给了 `selected_model_ids`，这里会直接过滤。

### 10.2 Stage B

`build_stage_b_model_specs(config, winners)` 不会盲目扩展所有搜索模型，而是：

1. 先从 Stage A summary 里选出 `sm` 和 `fsm` 两个 family 的搜索冠军。
2. 只对冠军继续扩成 ML 版本。

扩出来的形态是：

- `<winner>_ml_logistic`
- `<winner>_ml_lgbm`

并把 `stage_b_request_overrides` 合并进 request payload。

这就是为什么 Stage B 本质上是“先挑搜索冠军，再做 ML 扩展”，而不是“所有搜索方案都接 ML”。

## 11. 执行器怎么跑任务

### 11.1 任务批处理键

`execution.py` 里最重要的优化点是 `_task_batch_key()`：

```python
(
    task.data_path,
    task.market,
    task.adjust,
    task.symbol,
    task.window.window_id,
    task.window.kind,
    task.window.start_idx,
    task.window.end_idx,
    round(float(task.window.train_ratio), 6),
)
```

也就是说，同一只股票、同一个窗口下的多个模型不会各自重复切片、重复准备 context，而是打成一个 batch。

### 11.2 为什么这样分组

因为 `run_strategy_pipeline()` 复用的是单股 workflow，它内部有 stage cache 和 context 逻辑。

按 `symbol + window` 分组以后：

- 同一 worker 只需要加载一次数据窗口
- 同一个 `context_key` 可以复用
- Streamlit 的 stage cache 更容易命中
- 减少重复读取 CSV 和重复预处理

### 11.3 单个 batch 的执行过程

`run_task_batch(task_batch)` 的流程是：

1. `st.session_state.clear()`，避免跨任务污染。
2. 加载 `data_path` 对应的 CSV，并通过 `_FRAME_CACHE` 做 worker 内缓存。
3. 按窗口切片出 `df_window`。
4. 计算 `split_idx = int(len(df_window) * train_ratio)`，并强制夹在 `1` 到 `len-1` 之间。
5. 用 `build_strategy_context_key()` 生成上下文键。
6. 遍历 batch 里的每个模型，调用 `run_strategy_pipeline()`。
7. 把结果转成 `RunRecord`。

### 11.4 状态语义

当前有四种常见状态：

- `success`
- `degraded`
- `failed`
- `SKIPPED`

其中：

- `SKIPPED` 多半是窗口不可用
- `degraded` 多半表示“部分流程失败，但保留最近成功产物”
- `failed` 表示连可回退产物都没拿到

## 12. 和 `run_strategy_pipeline()` 的对接细节

`ui/single_stock_workflow.py` 当前的降级语义非常重要：

- `baseline`：直接跑基线路径
- `regime`：跑单步 regime stage，可能返回 `degraded`
- `search`：
  - 先跑 `sm_base` 或 `fsm_base`
  - 如果搜索失败，返回基础 stage 对应的 `degraded artifact`
  - 如果 ML 失败，返回最近成功 stage 对应的 `degraded artifact`

所以 `model-test` 不是简单地“成或败”，而是保留了 workflow 的“有条件降级”语义。

这也是为什么 summary 统计里会单独保留：

- `success_rate`
- `degraded_rate`
- `reliability_raw = success_rate - 0.5 * degraded_rate`

## 13. `RunRecord` 是怎么从 artifact 落出来的

`_record_from_result()` 会把 `PipelineRunResult` 拆成 `RunRecord`。

重点映射关系如下：

| 来源 | 去向 |
|---|---|
| `result.status` | `RunRecord.status` |
| `result.error_message` | `RunRecord.error_message` |
| `result.warnings` | `warnings_json` |
| `result.info_messages` | `info_messages_json` |
| `artifact.pipeline_lineage` | `lineage_json` |
| `artifact.params_snapshot` | `params_snapshot_json` |
| `final_stage.metadata` | `metadata_json` |
| `artifact.ml_quality` | `ml_quality_json` |
| `final_stage.train_sim_df` | 训练集指标 |
| `artifact.eval` | 测试集指标 |

此外它还会：

- 计算 `train_test_gap = max(train_annret - test_annret, 0.0)`
- 对搜索模型补写 `metadata.search_budget`
- 调用 `export_run_artifact_bundle()` 把最小分析包落盘

## 14. 评分系统

### 14.1 有效样本是怎么定义的

`summarize.py` 里 summary 并不是对所有记录都算：

- 只看 `window_kind == "main"` 的主窗口记录
- `SKIPPED` 不算 attempted
- 只有 `success/degraded` 且 `test_annret` 非空才算 valid

然后它会把 `naive` 的 `test_annret` merge 回来，计算：

```python
beat_naive = test_annret > naive_annret
```

### 14.2 主评分原始统计量

每个模型会聚合出：

- `attempted_count`
- `valid_count`
- `success_rate`
- `degraded_rate`
- `beat_naive_rate`
- `median_annret`
- `median_excess_return`
- `median_sharpe`
- `median_maxdd`
- `annret_iqr`
- `sharpe_iqr`
- `median_train_test_gap`
- `reliability_raw`

### 14.3 主评分公式

主评分先把每个维度转成百分位分数，再加权：

```python
total_score = (
    20 * beat_naive_score
    + 15 * excess_return_score
    + 15 * sharpe_score
    + 15 * drawdown_score
    + 20 * stability_score
    + 10 * overfit_score
    +  5 * reliability_score
) / 100
```

其中：

- `drawdown_score` 来自 `-abs(median_maxdd)` 的百分位
- `stability_score` 来自 `-(annret_iqr + sharpe_iqr)` 的百分位
- `overfit_score` 来自 `-median_train_test_gap` 的百分位
- `reliability_score` 来自 `reliability_raw` 的百分位

### 14.4 rolling robustness 评分

rolling robustness 会单独算一套 summary，只看：

- `window_kind == "rolling"`
- 非 `SKIPPED`

当前 robustness 评分权重是：

```python
ROBUSTNESS_SCORE_WEIGHTS = {
    "median_excess_return": 30.0,
    "median_sharpe": 30.0,
    "drawdown_control": 15.0,
    "stability": 15.0,
    "reliability": 10.0,
}
```

注意这里没有：

- `beat_naive_rate`
- `overfit_discipline`

因为 rolling 阶段更偏“稳定性和跨窗口表现”。

### 14.5 最终总分怎么合成

`_merge_robustness_scores()` 的逻辑是：

1. 先把主窗口得分保存成 `main_total_score`
2. 再 merge `robustness_total_score`
3. 对有 rolling robustness 的模型按以下方式合成：

```python
total_score = (1 - robustness_weight) * main_total_score + robustness_weight * robustness_total_score
```

当前默认：

```python
robustness_weight = 0.4
```

也就是：

```text
final total_score = 60% main + 40% robustness
```

`report.json` 的 `score_policy` 也会显式记录这件事。

### 14.6 当前排序规则

`build_model_summary()` 里最终排序顺序是：

1. `total_score`
2. `robustness_total_score`
3. `main_total_score`
4. `beat_naive_rate`
5. `median_excess_return`
6. `median_sharpe`

所以当总分接近时，rolling robustness 的存在和强弱会影响最终名次。

## 15. segment summary 在做什么

`build_segment_summary()` 会在每个 `segment_key` 内重新评分和排序，然后给出：

- `segment_rank`
- `suitability`

规则大致是：

- `valid_count < 5` -> `insufficient_sample`
- 排名前 2 且 `beat_naive_rate >= 0.60` -> `suitable`
- 排名在后 30% 且 `beat_naive_rate < 0.40` -> `not_suitable`
- 否则 -> `neutral`

这部分是为了回答“哪个模型更适合哪类股票段”。

## 16. rolling robustness 的一个关键实现细节

`runner.py` 里的 `_build_rolling_tasks()` 并不是在 rolling 阶段重新做搜索。

它会：

1. 从主窗口已完成记录里找到对应 `(symbol, model_id)`。
2. 读取主窗口保存的 `params_snapshot_json`。
3. 对搜索模型调用 `_build_frozen_rolling_model_spec()`，把：

```python
request_payload["use_search"] = False
```

也就是说，rolling robustness 是“拿主窗口冻结参数去跨窗口复测”，不是“每个滚动窗口重新调参”。

这和当前 README 中“rolling robustness 复用 main window 冻结参数”完全一致。

## 17. 输出物结构

每次 run 最终会写到：

```text
model-test/outputs/<output_subdir>/
```

主要文件：

- `runs.csv`
- `stocks.csv`
- `model_summary.csv`
- `segment_summary.csv`
- `robustness_summary.csv`
- `report.json`
- `report.md`
- `_checkpoint_runs.csv`
- `_checkpoint_meta.json`

成功或 degraded 的任务还会写：

```text
artifacts/<symbol>/<window_id>/<model_id>/
  returns.csv
  benchmark_returns.csv
  equity.csv
  trades.csv            # 仅有交易明细时
  metadata.json
```

如果启用 QuantStats，会写：

```text
quantstats/<rank>_<model_id>/
  tearsheet.html
  returns.csv
  benchmark_returns.csv
  manifest.json
```

如果启用 MLflow，会写：

- `mlflow_run.json`

如果启用 adaptive regime artifact，还会有：

```text
regime_artifacts/
  state_feature_schema.json
  state_cluster_centroids.csv
  state_classifier.pkl
  routing_policy.csv
  routing_policy_summary.json
  candidate_state_metrics.csv
```

## 18. `report.json` 里有什么

`build_report_payload()` 当前会生成这些顶层键：

- `generated_at`
- `config`
- `search_budget`
- `score_policy`
- `pool`
- `stage_winners`
- `top_models`
- `model_summary`
- `family_summary`
- `search_method_summary`
- `ml_gain`
- `segment_highlights`
- `quantstats`
- `robustness_summary`
- `failures`
- `adaptive_router`

也就是说，页面层如果只读 `report.json`，已经能拿到：

- 排行
- 搜索预算
- pool 概览
- segment 结论
- failure 摘要
- adaptive router 摘要

这也是 `ui/model_evaluation.py` 当前的工作方式：只读 `model-test/outputs` 下已有产物，不重新执行研究。

## 19. QuantStats 和 MLflow

### 19.1 QuantStats

`generate_quantstats_outputs()` 的逻辑不是针对单只股票，而是：

1. 取 `model_summary` 排名前 `quantstats_top_n` 的模型。
2. 找出它们所有 main-window 的成功/降级记录。
3. 把这些记录的 `returns.csv` 做等权平均聚合。
4. 把 `benchmark_returns.csv` 也做等权平均聚合。
5. 生成 pooled tear sheet。

所以 QuantStats 看的不是“单票单次回测”，而是“该模型在主窗口样本上的 pooled 表现”。

### 19.2 MLflow

`log_research_run_to_mlflow()` 只做 run 级记录，不是每条任务一个 run。

它会记录：

- config 的标量参数
- 顶部榜单的 headline metrics
- 状态计数
- 结果文件本身
- 可选的 QuantStats 目录

默认 tracking store 是：

```text
model-test/mlruns/
```

## 20. adaptive router 这一块在做什么

这是 `model-test` 里最“研究框架化”的部分。

`train_adaptive_router_artifacts()` 的思路是：

1. 对每只股票先准备主窗口数据。
2. 构造 adaptive feature frame。
3. 对一组候选模型逐个调用 `run_strategy_pipeline()`，收集训练期阶段结果。
4. 把训练期每天映射到某个 market state。
5. 比较每个 `state_id` 下各候选模型的收益表现。
6. 选出按 `symbol / segment / global` 分层的 routing policy。
7. 保存 classifier、centroid、routing policy、summary。

这里依赖的是 `core/adaptive_regime.py`：

- `ADAPTIVE_REGIME_KIND = "adaptive_router_v1"`
- `ADAPTIVE_MODEL_ID = "rsm_adaptive_v1"`
- `ADAPTIVE_STATE_COUNT = 6`
- `ADAPTIVE_MIN_STATE_DAYS = 20`

它不是简单把 `rsm` 又跑一遍，而是在离线阶段先训练出“状态识别 + 路由策略”，再把产物提供给在线或后续运行使用。

## 21. 断点续跑和增量补跑

### 21.1 checkpoint

研究过程中，`runner.py` 会持续维护：

- `_checkpoint_runs.csv`
- `_checkpoint_meta.json`

每完成一个 `RunRecord`，就会：

1. 追加写 checkpoint run
2. 更新内存态 `records_df`
3. 更新 `completed_keys`
4. 重写 checkpoint meta

这使得中途中断后，可以按 `(symbol, window_id, model_id)` 粒度恢复。

### 21.2 merge into existing output

如果配置了：

```json
{
  "selected_model_ids": ["rsm"],
  "merge_into_existing_output": true
}
```

那么当没有 checkpoint 时，runner 会先读现有 `runs.csv`，再只补跑选中的模型，并把结果合并回同一个 output 目录。

这就是 `smoke_us_v2_rsm_incremental.json` 这种配置存在的意义。

## 22. 当前几套典型配置

### `us_v1.json`

- 全量主研究池
- 搜索预算较低：`60 / 30 / 20`
- 开 Stage B
- 开 robustness

### `us_v2.json`

- 搜索预算更高：`120 / 40 / 30`
- 打开 `hold_until_exit=true`
- Stage B 额外固定 `ml_horizon_days=20`、`ml_min_excess_samples=40`

### `us_v2_locked_240.json`

- 强调“公平预算”
- random / bayesian 都是 `240 trials`
- genetic 是 `24 * (9 + 1) = 240 evals`
- robustness 打开

### `us_v2_fast.json`

- 更轻量的日常验证版
- `120 / 12 / 9`
- `main_pool_size=24`
- `run_robustness=false`

### `smoke_*`

- 用 sample universe
- 通常允许短主窗口
- 用于端到端快速自检

## 23. 为什么它能在研究上更高效

当前代码里真正提升效率的点主要有五个：

1. `symbol + window` 分批，避免同窗重复准备。
2. worker 内 `_FRAME_CACHE` 复用 CSV。
3. universe profile cache 和 pool cache 减少股票池重建成本。
4. rolling robustness 直接复用主窗口冻结参数，不重新搜索。
5. 单股主 workflow 已经有 stage cache，离线 runner 借用了这套缓存/上下文机制。

## 24. 它的边界和限制

当前代码层面的边界很明确：

- `load_research_config()` 直接限制只支持 `US`
- `load_symbol_history()` 也只实现了 US fallback fetch
- 最终研究逻辑强依赖 `ui/single_stock_workflow.py`
- 评分是“横向相对评分”，核心维度大量使用 percentile，而不是绝对阈值打分

这意味着：

- 它非常适合做“同一批模型、同一批股票”的横向研究
- 但不适合把不同 run 的 `total_score` 当成绝对跨实验标尺

## 25. 如果要继续扩展，应该看哪里

### 想新增模型族

先看：

- `model_test/config.py`
- `ui/single_stock_workflow.py`

通常需要：

- 新增 `ModelSpec`
- 确保 `StrategyRequest` 能表达这个 family
- 确保 `run_strategy_pipeline()` 能产出稳定 artifact

### 想改评分规则

先看：

- `model_test/config.py`
- `model_test/summarize.py`
- `model_test/reporting.py`

因为：

- 权重默认值在 `config.py`
- 真正打分公式在 `summarize.py`
- 报告解释在 `reporting.py`

### 想改输出协议

先看：

- `model_test/models.py`
- `model_test/observability.py`
- `model_test/reporting.py`
- `ui/model_evaluation.py`

因为页面层已经依赖 `report.json` 和部分文件结构。

## 26. 一句话总结

`model-test` 的本质是：

> 用配置、股票池、窗口调度、并行执行、评分汇总和结果落盘，把单股 workflow 升级成一个可批量跑、可断点续跑、可比较、可报告的离线研究框架。

它最重要的价值不是“又写了一套策略代码”，而是把项目里已有的策略主链变成了一个可以系统化研究、排序、复盘和部署消费的研究生产线。
