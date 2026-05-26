# Strategy Pipeline Interfaces

> 最近更新：2026-04-01
> 适用范围：`core/data.py` 到 `core/backtest.py` 的主链，以及 `core/regime_model.py`、`core/adaptive_regime.py`、FA / ML / baseline / evaluation / optimizer。

## 共享前提

- 标准行情字段：`date/open/high/low/close/volume`
- 常见元数据字段：`symbol`、`market`、`currency`、`adjust`
- UI 常用数据入口：
  - `core.utils.load_or_fetch_stock(symbol, adjust, market="US")`
  - `core.utils.get_available_stocks(market="US")`
- 统一评估载体：`document/MODEL_INTERFACES.md` 里的 `ModelResult`

## 主链总览

```text
data / utils
  -> indicators
  -> signals
  -> backtest
  -> evaluation / baselines / optimizer
```

增强链路：

- FSM：`signals` 预处理 + `fa_filter` + `signals(fsm_mode=True)`
- News Fusion：`signals/search` 输出 + `news_factor` residual gate + `backtest`
- ML-SM：`signals` + `ml_filter` + `backtest`
- Legacy Regime / RSM：`regime_model` + `backtest`
- Adaptive Regime Router：`adaptive_regime` + workflow candidate routing + `backtest`

## 分阶段 contract

| 阶段 | 主要接口 | 输入 | 输出 | 主要消费者 |
|---|---|---|---|---|
| 数据加载与标准化 | `standardize_columns`、`ensure_date_column`、`fetch_data`、`fetch_a_stock`、`load_csv`、`load_uploaded_bytes`、`load_or_fetch_stock` | 原始 CSV / AkShare 数据 / `symbol + market + adjust` | 标准化行情 `DataFrame` | sidebar、单股页、多股页、workflow |
| 指标扩展 | `add_indicators` | 标准行情 df + 指标参数 | 增加 RSI / MACD / EMA / ATR / ADX / BB / OBV 等列的 df | `signals`、`baselines`、`portfolio` |
| 信号生成 | `compute_signals` | 已过 `add_indicators` 的 df + 信号参数 | `target_position`、`buy_signal`、`sell_signal`、`factor_score` 等列 | `backtest`、`ml_filter`、single-stock workflow |
| Legacy Regime 路由 | `build_market_proxy_frame`、`compute_regime_features`、`compute_regime_signals`、`summarize_regime_diagnostics` | 标准行情 df + `split_idx` + SPY 代理规则 | `execution_regime`、`regime_score`、`regime_summary` 等列 / metadata | single-stock workflow、model-test |
| Adaptive Regime 状态建模 | `build_adaptive_feature_frame`、`train_adaptive_state_model`、`predict_adaptive_states`、`aggregate_candidate_state_day_rows`、`score_candidate_state_metrics`、`select_routing_policy` | 标准行情 df、候选模型逐日结果、离线 main-window 训练样本 | `state_id`、state classifier、routing policy、`regime_artifacts/` | model-test、single-stock workflow |
| FA 增强 | `fit_fa`、`transform_fa` | 训练期信号表 / 同结构信号表 | `FAModel` / `fsm_score` | FSM 路径 |
| 新闻因子融合 | `apply_news_fusion` | search 上游 `full_signal_df` + FinGPT 日频新闻因子 CSV | `fused_factor_score`、`news_delta`、重算后的 `target_position` / metadata | 单股 search workflow |
| ML 过滤 | `build_feature_table`、`fit_ml_filter`、`predict_filter`、`apply_filter`、`evaluate_ml_quality` | `compute_signals()` 输出表 | 过滤后的信号表、概率、质量指标 | ML-SM 路径、单股结果区 |
| 回测 | `simulate_strategy`、`extract_trades`、`walk_forward_backtest` | 含 `target_position` 或买卖信号的 df | 净值曲线、日收益、逐笔交易表、滚动回测结果 | workflow、评估、结果区 |
| 课程基线 | `naive_baseline`、`mean_baseline`、`drift_baseline`、`run_all_baselines` | 标准行情 df + split | `ModelResult` | 单股 workflow、对比区 |
| 评估 | `compute_performance_metrics`、`compute_trade_stats`、`evaluate_strategy`、`build_comparison_table` | 净值 / 基准 / 逐笔表 | KPI dict / 对比表 | 单股页、报告导出 |
| 优化 | `evaluate_presets_for_optimization`、`random_search_params`、`bayesian_optimize_params`、`genetic_algorithm_optimize_params` | 原始 df + split + sidebar 参数 | `best params / score / train-val metrics / full_signal_df` | single-stock workflow、model-test |

## 关键稳定接口

### 数据层

- `load_or_fetch_stock(symbol, adjust, market="US") -> pd.DataFrame | None`
  作用：UI 默认数据入口；根据市场决定走美股还是 A 股路径。
- `get_available_stocks(market="US") -> list[str]`
  作用：sidebar 股票池来源。

### 指标层

```python
add_indicators(
    df,
    rsi_period,
    macd_fast,
    macd_slow,
    macd_signal,
    ema_fast,
    ema_slow,
    adx_period,
    atr_period,
    bb_period=20,
    bb_std=2.0,
    indicator_period=20,
) -> pd.DataFrame
```

最重要的 contract 是：下游 `compute_signals()` 假设指标列已经准备好。

### 信号层

```python
compute_signals(df, ..., fsm_mode=False, fa_model=None) -> pd.DataFrame
```

前后端最常依赖的输出列：

- `target_position`
- `buy_signal`
- `sell_signal`
- `factor_score`
- `factor_percentile`
- `macd_above`
- `entry_count`
- `exit_count`

补充约定：

- `hold_until_exit=False` 时保持旧逻辑：入场条件失效会把 `target_position` 拉回 0。
- `hold_until_exit=True` 时启用 V2 持仓状态机：
  - 空仓只看 `entry_ok`
  - 持仓只看 `exit_ok`
  - 持仓维持仓位时使用 `max(score_position, hold_min_position * vol_adjustment)`
- `entry_count` / `exit_count` 只统计已启用条件；实际门槛取 `min(configured_threshold, enabled_condition_count)`。
- `score_mid_pct` / `score_high_pct` 直接驱动仓位分层，不再写死在函数内部。

### Legacy Regime / RSM

`core/regime_model.py` 当前稳定输出列：

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

补充约定：

- v1 只支持 `US`，默认市场代理固定为 `SPY`。
- 代理不可用时，regime 路径降级为 `stock-only` 路由，不回退到别的 family。
- `summarize_regime_diagnostics()` 现在接受动态 `execution_regime` 标签；adaptive 路径里的 `state_0` 一类标签不会破坏诊断汇总。

### Adaptive Regime Router

共享 helper 位于 `core/adaptive_regime.py`。当前稳定常量：

- `ADAPTIVE_REGIME_KIND = "adaptive_router_v1"`
- `ADAPTIVE_MODEL_ID = "rsm_adaptive_v1"`
- `ADAPTIVE_ARTIFACT_DIRNAME = "regime_artifacts"`
- `ADAPTIVE_ARTIFACT_ENV_VAR = "STRATAGY_ADAPTIVE_REGIME_ARTIFACT_DIR"`

离线候选池固定为：

- `naive`
- `mean`
- `drift`
- `sm`
- `fsm`
- `sm_bayesian`
- `sm_random`
- `sm_genetic`
- `fsm_bayesian`
- `fsm_random`
- `fsm_genetic`

在线默认候选别名固定为：

- `naive`
- `mean`
- `drift`
- `sm`
- `fsm`
- `sm_best_search`
- `fsm_best_search`

在线 full 候选别名固定为：

- `naive`
- `mean`
- `drift`
- `sm`
- `fsm`
- `sm_bayesian`
- `sm_random`
- `sm_genetic`
- `fsm_bayesian`
- `fsm_random`
- `fsm_genetic`

状态特征列固定为：

- `ret_5`、`ret_20`、`ret_60`
- `spy_ret_5`、`spy_ret_20`、`spy_ret_60`
- `realized_vol_20`、`realized_vol_60`
- `atr_pct`
- `ema_spread_pct`
- `adx`
- `rsi`
- `drawdown_rank`
- `bb_width_rank`
- `volume_ratio_rank`
- `efficiency_ratio_20`
- `relative_strength_vs_spy_20`
- `beta_60`
- `corr_60`

离线产物稳定写入 `regime_artifacts/`：

- `state_feature_schema.json`
- `state_cluster_centroids.csv`
- `state_classifier.pkl`
- `routing_policy.csv`
- `routing_policy_summary.json`
- `candidate_state_metrics.csv`

补充约定：

- 状态聚类默认是 `MiniBatchKMeans`；在线分类优先 LightGBM，多分类不可用时回退到 `LogisticRegression`。
- `select_routing_policy()` 的回退层级固定为 `symbol -> segment -> global -> mean`。
- `load_adaptive_regime_artifacts()` 找不到或读不通产物时抛异常；workflow 负责把异常转成 degraded fallback。

### FA / FSM

- `fit_fa(df_train, n_components=3) -> FAModel`
- `transform_fa(fa_model, df) -> pd.Series`

约束：

- `fit` 只允许训练集。
- `transform` 复用训练好的模型，不把测试集信息回灌。

### ML-SM

- `build_feature_table(...)` 只从 `buy_signal` 行抽取特征。
- `build_feature_bundle(...)` / `build_feature_view(...)` 是内部复用层：先对同一份 `full_signal_df` 做一次昂贵特征预计算，再派生 train / full / test 视图。
- `build_feature_bundle(..., horizon, min_excess_samples)` 支持研究侧自定义标签窗口和 `excess_return -> absolute_return` 的回退门槛；UI 默认仍是 `10 / 20`。
- `fit_ml_filter(...)` 可能返回常数概率模型，不能默认训练总成功。
- `apply_filter(...)` 过滤的是整段持仓块，不是单个孤立买点。
- 训练视图的标签边界不能跨过 `split_idx`。

### 优化层

- `SearchMetrics` 同时产出 `sharpe / total_return / excess_return / max_drawdown / turnover`。
- 单个 split 的候选评分固定为：
  `sharpe + 2.0 * excess_return - 0.5 * abs(max_drawdown) - 0.25 * turnover`
- train / validation 联合目标固定为：
  `0.25 * train_score + 0.75 * validation_score - 0.20 * abs(train_score - validation_score)`
- 请求级缓存仍由 `SearchEvaluationCache` 持有；best candidate 直接复用缓存里的 `full_signal_df`。
- 扩展搜索空间只在 `hold_until_exit=True` 的研究路径启用；UI 默认搜索仍走 legacy 参数空间。

### 回测层

```python
simulate_strategy(df, ..., return_trades=False)
```

稳定输出列：

- `position`
- `strategy_return`
- `strategy_equity`
- `buy_hold_equity`

当 `return_trades=True` 时返回 `(sim_df, trades_df)`，其中 `trades_df` 由 `extract_trades()` 结构化生成。

## ModelResult 边界

`core/baselines.py` 和评估层对外统一使用 `ModelResult`：

- `label`
- `equity_series`
- `returns`
- `trades_df`
- `metrics`

详细字段定义以 `document/MODEL_INTERFACES.md` 为准。

## 与前端 / workflow 的边界

- 核心策略链不关心 Streamlit route state。
- 单股 workflow 通过 `params_snapshot + request_signature + context_key` 消费主链结果。
- adaptive regime 的在线候选执行、路由拼接和 degraded fallback 都在 `ui/single_stock_workflow.py`，不写回 `core/` 主链。
- 多股组合通过 `run_portfolio_simulation()` 在多股页内部消费核心链，不复用单股 artifact。

如果任务只是在 UI 层消费这些输出，优先读 `document/interfaces/frontend-contracts.md` 或 `document/interfaces/single-stock-workflow.md`，不要直接深挖全部核心模块。
