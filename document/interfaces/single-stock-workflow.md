# Single-Stock Workflow Interfaces

> 最近更新：2026-04-01
> 适用范围：`ui/single_stock_workflow.py`、`ui/single_stock.py` 的 request / stage / artifact / workspace / stage cache，以及 adaptive regime 在单股 workflow 的接入语义。

## 入口与责任分层

- `ui/single_stock.py`
  作用：页面壳层、工作台、结果板、策略库、导出。
- `ui/single_stock_workflow.py`
  作用：请求校验、上下文失效、stage cache、流水线串联、artifact 组装、degraded fallback。

页面不要自行复制 pipeline 逻辑；策略生成统一经过 `run_strategy_pipeline()`。

## 核心状态键

| state key | 位置 | 作用 |
|---|---|---|
| `single_stock_strategy_workspace` | `ui/single_stock_workflow.py` | 当前上下文的 `current_artifact` 与 `saved_artifacts` |
| `single_stock_stage_cache` | `ui/single_stock_workflow.py` | 按 stage 分桶的缓存 |
| `single_stock_selected_artifact_ids` | `ui/single_stock.py` | 参与下游比较的 artifact |
| `single_stock_focus_artifact_id` | `ui/single_stock.py` | 当前主策略 |
| `single_stock_signal_dataset_split` | `ui/single_stock.py` | 买卖点读取训练集还是测试集 |
| `single_stock_workflow_regime_kind` | `ui/single_stock.py` | 当前 regime 路径选择；默认 `adaptive_router_v1` |

## 主数据结构

### `StrategyRequest`

一次单股工作流请求的最小描述。当前稳定字段：

- `family`: `"baseline" / "search" / "regime"`
- `baseline_kind`: `"naive" / "mean" / "drift"`
- `search_base`: `"sm" / "fsm"`
- `regime_kind`: `"adaptive_router_v1" / "dual_state_router" / "no_market" / "no_router"`
- `use_search`
- `search_method`: `"bayesian" / "genetic" / "random"`
- `use_news`
- `news_fusion_mode`: `"residual_gate"`
- `news_factor_path`
- `news_weight`
- `news_lookback`
- `use_ml`
- `ml_model_type`: `"logistic" / "lgbm"`
- `ml_horizon_days`
- `ml_min_excess_samples`
- `search_trials`
- `ga_population_size`
- `ga_generations`

补充约定：

- UI 默认 regime request 走 `adaptive_router_v1`。
- UI 若未显式传两个 ML 字段，仍使用 `10 / 20`。
- `model-test` 可通过 Stage B request payload 覆盖 ML 字段。
- `params_snapshot` 允许带 `hold_until_exit / hold_min_position`；旧快照缺省时由 workflow 兜底为 `False / 0.2`。

### `StageResult`

表示一次阶段性产物。当前稳定字段：

- `stage_key`
- `display_label`
- `short_label`
- `params_snapshot`
- `train_sim_df`
- `test_sim_df`
- `trades_df`
- `eval`
- `equity_series`
- `returns_series`
- `ml_quality`
- `upstream_stage_key`
- `full_signal_df`
- `metadata`

### `StrategyArtifact`

表示最终可提交到页面结果区和策略库的对象。当前稳定字段：

- `id`
- `context_key`
- `display_label`
- `pipeline_lineage`
- `params_snapshot`
- `train_sim_df`
- `test_sim_df`
- `trades_df`
- `eval`
- `equity_series`
- `returns_series`
- `ml_quality`
- `full_signal_df`
- `request_signature`

`current_artifact` 和 `saved_artifacts` 都保存这个结构。

### `PipelineRunResult`

- `artifact`
- `status`: `"success" / "degraded" / "failed"`
- `warnings`
- `info_messages`
- `error_message`

约定：

- 只有最终无结果时才返回 `failed`。
- adaptive regime 触发 legacy fallback 时返回 `degraded`，但仍会给出可消费的 artifact。

## 上下文与签名

### `build_strategy_context_key(...)`

```python
build_strategy_context_key(
    *,
    market: str,
    symbol: str,
    adjust: str,
    df_raw: pd.DataFrame,
    train_ratio: float,
    uploaded_file: Any = None,
) -> str
```

作用：决定当前页面是不是同一组策略上下文。输入包括：

- 市场
- 股票代码或上传数据 fingerprint
- 复权方式
- 数据日期范围
- 训练集比例

### `freeze_params_snapshot(params)`

作用：从 sidebar 参数里抽取 workflow 关心的冻结参数子集，避免 UI 态污染签名。

### `build_request_signature(request, params_snapshot)`

作用：把请求语义与冻结参数合成稳定签名，用于判断当前 artifact 是否过期。

## workspace 生命周期

### workspace 结构

```python
{
    "context_key": str | None,
    "current_artifact": StrategyArtifact | None,
    "saved_artifacts": list[StrategyArtifact],
}
```

### 关键函数

- `ensure_strategy_workspace(context_key) -> (workspace, was_reset)`
  语义：上下文变更时清空 `current_artifact` 和 `saved_artifacts`。
- `commit_current_artifact(artifact)`
  语义：只更新当前结果，不自动进入策略库。
- `save_current_artifact() -> ("saved" | "exists" | "missing", artifact | None)`
  语义：把当前结果拷贝到会话内策略库，按 `artifact.id` 幂等。

### workspace 状态值

`get_workspace_status(workspace, request, params_snapshot)` 当前返回：

- `REQUEST_DRAFT`
- `CURRENT_READY`
- `CURRENT_AND_SAVED`

如果 `request_signature` 与当前 artifact 不匹配，也会退回 `REQUEST_DRAFT`。

### 临时持久化恢复

- `single_stock_strategy_workspace` 的 `context_key/current_artifact/saved_artifacts` 会随路由临时工作区保存 24 小时；恢复后仍遵循同一 `request_signature` stale 判定。
- `single_stock_stage_cache` 和 `single_stock_display_cache` 均只保留在当前进程会话，不参与快照。stage cache 全局 LRU 上限为 12 条，展示图缓存上限为 12 组。
- 上传 CSV 的原始字节按内容哈希保存在对应临时工作区，并在恢复时重新注入 route state；过期或清除工作区后不再可用。

## stage cache contract

### 分桶方式

`single_stock_stage_cache` 按 `stage_key` 分桶；桶内元素是 `StageResult`。

### cache key 组成

stage cache key 由以下三部分组合哈希：

- `context_key`
- `stage_request_slice`
- `stage_input_params_snapshot`

这意味着：

- 切换股票 / 上传数据 / 训练比例会失效。
- 上游阶段输入变化会失效。
- 下游 ML / 搜索不会回写污染基础 stage。
- ML 阶段 cache key 还显式包含 `ml_model_type / ml_horizon_days / ml_min_excess_samples`。
- regime 阶段 cache key 显式包含 `regime_kind`；adaptive 与 legacy 不共享同一桶。

## 流水线入口

```python
run_strategy_pipeline(
    *,
    context_key: str,
    request: StrategyRequest,
    request_params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
) -> PipelineRunResult
```

当前流程：

- `baseline` 路径：直接生成基线 stage。
- `search` 路径：
  - 先跑 `sm_base` 或 `fsm_base`
  - 可选进入搜索阶段
  - 可选进入 News Fusion 阶段
  - 可选进入 ML 阶段
  - 出错时允许降级回最近成功的上游 stage
- `regime` 路径：单步生成 regime stage，并复用 `StageResult / StrategyArtifact / cache`

生成成功后，`pipeline_lineage` 会保留所有成功阶段；最终 artifact 只提交最新成功阶段。

## `run_news_stage()` 语义

`use_news=True` 只允许在 `family="search"` 下启用，且默认使用 `residual_gate`。

- 输入：上游 `full_signal_df`、`news_factor_path`、当前 symbol、`news_weight`、`news_lookback` 和 `split_idx`。
- 数据来源：FinGPT 侧生成的 `news_sentiment_daily.csv`，字段至少包含 `symbol/date/news_count/sentiment_ewm_3/confidence_mean`。
- 合并规则：按 `symbol + date` 对齐；若某个交易日缺少新闻，`news_delta=0`，该日退化为上游技术策略。
- 输出列：保留原始 `factor_score`，新增 `fused_factor_score`、`news_sentiment_z`、`news_technical_proxy`、`news_residual`、`news_gate`、`news_delta`，并基于 `fused_factor_score` 重算 `factor_percentile/target_position/buy_signal/sell_signal`。
- metadata：记录 `news_rows_loaded/news_rows_matched/news_coverage_ratio/news_weight/news_lookback/news_fusion_mode/news_factor_path/news_symbol/news_beta`。

## `run_regime_stage()` 语义

### Legacy 路径

`regime_kind in {"dual_state_router", "no_market", "no_router"}` 时：

- 继续走 `core/regime_model.py`
- 产出 US-only `Regime (Experimental)` 单步 stage
- `full_signal_df` 稳定包含：
  - `stock_trend_state`
  - `stock_vol_state`
  - `market_trend_state`
  - `market_vol_state`
  - `execution_regime`
  - `anchor_mean_position`
  - `anchor_drift_position`
  - `regime_score`
  - `regime_score_percentile`
  - `target_position`
- `stage.metadata["regime_summary"]` 保存诊断汇总
- `SPY` 代理不可用时不回退到别的 family，而是在 metadata 里标记 fallback_stock_only

### Adaptive 路径

`regime_kind == "adaptive_router_v1"` 时，固定流程为：

1. `load_adaptive_regime_artifacts()` 读取最近一次离线 `regime_artifacts/`
2. `build_adaptive_feature_frame()` 构建当前 symbol 全窗口 state 特征
3. `predict_adaptive_states()` 对全窗口预测 `state_id`
4. 运行在线 candidate pool，并拿到各候选模型的 `full_signal_df`
5. 用训练段表现生成当前 symbol 的本地路由表
6. 对测试段逐日选择 candidate model
7. 拷贝被选中模型当日的 `target_position`
8. 统一调用内部刷新逻辑重算 `buy_signal / sell_signal`
9. 回测并组装 stage / artifact

当前在线默认 candidate pool 固定为 `default`，不是 full。

### Adaptive metadata contract

adaptive stage 当前稳定补充：

- `metadata["family"] = "regime"`
- `metadata["regime_kind"] = "adaptive_router_v1"`
- `metadata["adaptive_artifact_dir"]`
- `metadata["adaptive_alias_to_model"]`
- `metadata["global_search_winners"]`
- `metadata["run_status"] = "success" | "degraded"`
- `metadata["regime_summary"]` 额外带：
  - `candidate_pool_mode`
  - `segment_key`
  - `latest_selected_model_id`
  - `latest_predicted_state_id`
  - `latest_policy_source`
  - `state_distribution`
  - `model_usage_distribution`
  - `policy_source_distribution`

adaptive 的 `full_signal_df` 还会补充：

- `predicted_state_id`
- `selected_model_id`
- `policy_source`
- `candidate_pool_mode`
- `execution_regime`

### Adaptive degraded fallback

若 adaptive artifact 缺失、损坏或在线拼接失败：

- workflow 自动回退到 `dual_state_router`
- 返回的 `PipelineRunResult.status` 为 `degraded`
- fallback stage 仍可进入结果区和策略库
- metadata 固定补充：
  - `requested_regime_kind = "adaptive_router_v1"`
  - `effective_regime_kind = "dual_state_router"`
  - `run_status = "degraded"`
  - `adaptive_fallback_reason`
- `warning_messages` 会明确写出 fallback 原因

## 页面消费方式

- `ui/single_stock.py` 左侧工作台负责构造 `StrategyRequest`
- 右侧结果板默认消费 `current_artifact`
- 比较模式消费 `current_artifact + saved_artifacts`
- `build_lineage_model_payloads(artifact)` 用于把 lineage 转成结果区可复用 payload
- 页面若看到 `PipelineRunResult.status == "degraded"`，应把 warning 暴露给用户，而不是把结果当成完全失败

如果任务只是找单股页某个图表或展示块的输入来源，应优先从本文件定位到 artifact / workspace / lineage，再决定是否下探到 `document/interfaces/strategy-pipeline.md`。
