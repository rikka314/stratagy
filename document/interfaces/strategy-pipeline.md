# Strategy Pipeline Interfaces

> 最近更新：2026-08-18
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
- Dynamic Ensemble Phase A–F：`model-test/model_test/moe_baseline.py` 冻结对照，`expert_panel.py` 生成无泄漏面板，`dynamic_ensemble.py` 训练 v1 soft-gate，`dynamic_ensemble_v2.py` 训练低分位 / 中位 quantile gate 并施加不确定性、降级与组合风险约束，`dynamic_ensemble_online.py` 回放完整反馈 Hedge / EG，`dynamic_ensemble_bandit.py` 仅以所选 Phase-E allocation action 的反馈比较 LinUCB / contextual Thompson Sampling；均不接入 UI

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
- LightGBM runtime 由 `core/lightgbm_runtime.py` 统一解析；默认 `device_type=cpu`。离线研究可通过 config 的 `lightgbm_device_type=cpu|gpu|cuda` 显式选择设备，非 CPU 设备必须先通过 tiny-fit preflight，失败时正式 run 直接停止，不静默回退。
- GPU/CUDA 只覆盖 LightGBM ML filter 与 adaptive state classifier；数据加载、pandas 指标、回测、Logistic Regression 和大部分搜索 objective 仍为 CPU 路径。

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

Dean's Award 的研究运行可通过 `MarketExecutionConfig` 启用市场成本。没有显式 config、且不在
`using_execution_config(...)` 研究上下文中的调用，保持原有零成本数值结果不变。启用后，`sim_df`
额外包含 `turnover`、`transaction_cost` 和 `gross_strategy_return`；`strategy_return` 始终表示扣除成本后的净收益。
成本只在仓位变化时计提，公式是
`abs(position_t - position_(t-1)) * (commission_bps + slippage_bps) / 10_000`，首日之前仓位为 `0`。

离线 `model-test` 将有效成本写入 `config_snapshot.json` 和 `data_manifest.json`，并在同一 run 内以
context-local execution config 传递给所有嵌套回测；这不会改变交互页面的默认结果。

Dean's Award 正式研究配置采用市场内独立推荐：US 与 CN_A 分别从本市场已验证候选中选择；只有单独的 shared benchmark 才限制为共同候选。标准 full tier 为每市场 60 只，经 deterministic hybrid catalog sampling、趋势/波动分桶与流动性排序选取；每个 run 要求行情至少覆盖到 `minimum_data_end_date`（当前为 2026-07-31），旧 sample/cache 会触发重拉，随后将入选 CSV 冻结到 `data_snapshot/` 并在 manifest 记录逐文件及聚合 SHA-256。120 只配置是参数冻结后的确认层。

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
- 动态专家组合 Phase A–F 仅存在于 `model-test`。`prepare_moe_baseline.py` 消费已冻结的 Window 3B / full-run 产物，使用已扣费的 `strategy_return` 且不重复扣成本；`prepare_expert_panel.py` 在同一 source lock 下生成带 purged walk-forward / embargo 的逐日专家面板，缺失专家显式标记 unavailable；`run_dynamic_ensemble.py` 仅消费 ready Phase-A/B source lock，训练 LightGBM soft-gating、输出受约束权重和三项冻结对照；`run_dynamic_ensemble_v2.py` 额外验证 ready Phase-C source lock，以 lower/median quantile LightGBM 计算保守分数、可追溯降级和风险约束 / 消融；`run_dynamic_ensemble_online.py` 则以 hash-verified Phase-D 权重为初始状态，在完整反馈下回放 Hedge / EG；`run_dynamic_ensemble_bandit.py` 只消费 ready Phase-E allocations，把每个已约束 allocation 作为 action，使用所选动作的反馈回放 LinUCB / contextual Thompson Sampling。Phase F 不使用未选动作回报更新，Cash 始终可选，且所有路径均不接入 UI；adaptive control 只有在 artifact 的 market 与研究 config 匹配时才可用。2026-08-18 W11 admission 已完成四折比较：US 1/4、CN_A 2/4，不满足 3/4，W12 保持 blocked。详细 contract 见 `document/interfaces/dynamic-ensemble-research.md`。
- Transformer-state v2 W13-W15 同样只存在于 `model-test`。`run_transformer_state.py` 先验证 market-specific Phase-A/B 与 full-run hash、rank-1 fallback、Cash、adaptive control、snapshot、逐日仓位及 config/code content hash，再从 frozen OHLCV 与 source-net expert panel 生成完整 `t+1..t+5` 标签、最大 20 日同标的序列和四折保护区；所有旧 W11 test 日期从 v2 train/validation 全局排除。`trades.csv` entry/exit 区间不能替代精确逐日 `target_position`/turnover：当前 CN_A W13/W14 ready，US 因此 fail closed。`transformer_state_model.py` 只允许 train-fold scaler/encoder fit 与 validation checkpoint selection；test 不进入 fit API。PyTorch 缺失时 W15 写 `unavailable` manifest 并禁止进入 W16，不静默替换模型或接入 UI。

如果任务只是在 UI 层消费这些输出，优先读 `document/interfaces/frontend-contracts.md` 或 `document/interfaces/single-stock-workflow.md`，不要直接深挖全部核心模块。
