# Frontend Contracts

> 最近更新：2026-04-01
> 适用范围：路由壳层、入口页、主分析页、共享 HTML、共享图表、页面导出。

## 推荐读取顺序

1. `AI_CONTEXT.md`
2. `document/FRONTEND_STYLE_STANDARD.md`
3. 本文档
4. 仅在需要时补读：
   - `document/interfaces/single-stock-workflow.md`
   - `document/interfaces/multi-stock-portfolio.md`
   - `document/interfaces/strategy-pipeline.md`

## 路由壳层：`app.py`

### 公开页面

`app.py` 通过 `st.navigation` 暴露四条真实路由：

- `/strategy`
- `/strategy/stock-analysis`
- `/strategy/stocks-analysis`
- `/strategy/model-evaluation`

### 路由状态键

| state key | 结构 | 用途 |
|---|---|---|
| `route_single_state` | `{view, market, symbol, uploaded_name, uploaded_bytes, source}` | 单股入口页与主分析页切换 |
| `route_multi_state` | `{view, market, symbols, uploads}` | 多股入口页与主分析页切换 |

`/strategy/model-evaluation` 是只读浏览页，不新增 route state key；页面只维护本地 selector 的 widget 状态。

### 公共壳层 helper

- `_validate_strategy_params(params)`
  作用：在进入页面前兜住 EMA / MACD / RSI / 动量 / 分位数关系。
- `_apply_date_filter(df_raw, selected_range)`
  作用：统一把 `selected_range` 转成 `(filtered_df, is_datetime, start_ts, end_ts)`。
- `_ensure_valid_dataframe(df_raw, empty_message=...)`
  作用：校验 `open/high/low/close` 必需列。

## 共享 HTML 与站点壳：`ui/theme.py`

| 接口 | 约定 |
|---|---|
| `route_href(url_path="")` | 统一拼接 `/strategy/...` 路径 |
| `render_html(markup)` | 大块 HTML 的唯一共享入口；优先走 `st.html()`，回退到 `st.markdown(..., unsafe_allow_html=True)` |
| `inject_global_styles()` | 全局 token、站点壳、导航、surface 样式注入 |

前端任务默认不要在页面里另起一套 HTML 渲染路径；大块 HTML 统一复用 `render_html()`。

## 共享导出 builder：`ui/export_reports.py`

| 接口 | 约定 |
|---|---|
| `build_single_stock_export_html(...)` | 单股页离线 HTML 报告共享 builder |
| `build_multi_stock_export_html(...)` | 多股页离线 HTML 报告共享 builder |

单股 / 多股页面仍保留自己的导出触发入口，但导出结构、响应式 CSS、`zh/en` 文案和 `light/dark` 皮肤统一下沉到 `ui/export_reports.py`。

## 侧边栏 contract：`ui/sidebar.py`

### 入口

```python
render_sidebar(
    *,
    initial_market: str | None = None,
    initial_symbols: list[str] | None = None,
    route_seed_token: str | None = None,
) -> dict
```

### 输入语义

- `initial_market`
  作用：路由刚切换时预种子市场。
- `initial_symbols`
  作用：路由刚切换时预种子已选股票。
- `route_seed_token`
  作用：只在 token 变化时重置 sidebar 预种子，并清理旧 route 下的选择残留。

`render_sidebar()` 还会主动清理旧版搜索回写残留键：`best_params`、`apply_best_params`。

### 输出参数包

`params` 是前端页面与核心策略链之间的统一参数袋。稳定分组如下：

- UI / 路由态：
  - `market`
  - `compare_stocks`
  - `symbol`
  - `adjust`
  - `selected_range`
  - `uploaded_file`
  - `strategy_preset`
- 技术指标参数：
  - `ema_fast`
  - `ema_slow`
  - `macd_fast`
  - `macd_slow`
  - `macd_signal`
  - `rsi_period`
  - `rsi_lower`
  - `rsi_upper`
  - `adx_period`
  - `adx_threshold`
  - `atr_period`
  - `bb_period`
  - `bb_std`
  - `indicator_period`
  - `stop_loss_mult`
  - `take_profit_mult`
- 因子评分参数：
  - `momentum_short`
  - `momentum_long`
  - `score_lookback`
  - `score_mid_pct`
  - `score_high_pct`
  - `weight_mom_short`
  - `weight_mom_long`
  - `weight_macd`
  - `weight_rsi`
  - `weight_vol`
  - `weight_bb`
  - `weight_obv`
  - `weight_volume`
  - `weight_price`
  - `weight_drawdown`
- 入出场 / 过滤器：
  - `entry_threshold`
  - `exit_threshold`
  - `entry_min_signals`
  - `exit_min_signals`
  - `use_trend_filter`
  - `use_strength_filter`
  - `use_rsi_filter`
  - `use_macd_filter`
  - `use_voting_entry`
  - `entry_vote_threshold`

如果要改 sidebar 的输出 key，同步更新本文档和使用这些 key 的页面 / workflow。

## 单股页 contract：`ui/single_stock.py`

### 页面入口

```python
render_single_stock_page(params: dict, df_raw: pd.DataFrame, symbol: str) -> None
```

### 输入要求

- `df_raw` 至少含 `open/high/low/close`，推荐同时含 `date/volume`
- `params` 来自 `render_sidebar()`，不要自造第二套参数命名
- `symbol` 由路由层归一；单股页会把 `params["compare_stocks"]` 归一成 `[symbol]`

### 页面本地状态

| state key | 作用 |
|---|---|
| `single_stock_selected_artifact_ids` | 比较模式选中的 artifact |
| `single_stock_focus_artifact_id` | 当前主策略 |
| `single_stock_signal_dataset_split` | 买卖点图读取 train 还是 test |
| `single_stock_workflow_regime_kind` | regime 工作台当前选择 |

### 页面依赖

- 当前 artifact 与策略库不从 sidebar 来，而是从 `ui/single_stock_workflow.py` 的 workspace 读取。
- 大块页面结构、chart toolbar、section header 统一走 `render_html()`。
- 单股页自身不维护第二套 regime 算法，只负责把工作台请求交给 workflow。

### Regime 工作台约定

- `single_stock_workflow_regime_kind` 当前固定可选：
  - `adaptive_router_v1`
  - `dual_state_router`
  - `no_market`
  - `no_router`
- 页面默认选中 `adaptive_router_v1`。
- 页面说明文案必须明确：
  - adaptive 会优先读取最近一次离线 `regime_artifacts/`
  - 产物缺失或损坏时会自动降级到 legacy `dual_state_router`
- 页面若拿到 `PipelineRunResult.status == "degraded"`，应显示 warning，而不是把结果板整体视为失败。

### 单股导出依赖

`_render_single_stock_export(...)` 当前消费：

- `model_payload`
- `active_models`
- `candle`
- `ind_fig`
- `score_fig`
- `equity_fig`
- `signal_fig`

单股页内部的 artifact、lineage、stage cache contract 见 `document/interfaces/single-stock-workflow.md`。

## 多股页 contract：`ui/multi_stock.py`

### 页面入口

```python
render_multi_stock_page(
    params: dict,
    is_datetime: bool,
    start_ts,
    end_ts,
    prefetched_stock_data: dict[str, pd.DataFrame] | None = None,
) -> None
```

### 输入要求

- `params["compare_stocks"]`：市场数据路径下的股票列表
- `prefetched_stock_data`：上传文件路径下的 `symbol -> DataFrame` 映射
- `is_datetime/start_ts/end_ts`：由 `app.py` 的统一时间过滤辅助函数提供

多股页的组合结果、权重、市场上下文 contract 见 `document/interfaces/multi-stock-portfolio.md`。

## 模型评估页 contract：`ui/model_evaluation.py`

### 页面入口

```python
render_model_evaluation_page(
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> None
```

### 输入要求

- 页面是只读 run browser，不触发研究执行。
- 默认扫描 `model-test/outputs/*`，只纳入“可读目录 + 存在 `report.json`”的 run。
- 忽略以下目录：
  - 以下划线开头的内部目录
  - 无 `report.json` 的目录
  - 权限拒绝目录
  - 读取报错目录
- run 列表按 `report.json` 或目录最近修改时间倒序排列。
- 默认选中最新一份可读 run。

### 数据 contract

- 必需：`model-test/outputs/<run>/report.json`
- 可选：`model-test/outputs/<run>/mlflow_run.json`
- 可选：`report.json.quantstats[*].quantstats_html_path`
- 可选：`report.json.adaptive_router`

兼容约定：

- `quantstats` 缺失时视为空列表。
- `mlflow_run.json` 不存在时视为“未记录 MLflow”。
- `adaptive_router` 可以存在，也可以不存在；前端只读页必须容忍 report payload 的这类扩展字段。

## 共享图表 contract：`core/visualization.py`

### 分析页共享图表

| 接口 | 返回 | 典型消费者 |
|---|---|---|
| `create_empty_state_chart(message, *, height=220)` | `go.Figure` | 单股 / 多股空状态 |
| `style_analysis_figure(fig, *, height, margin=None)` | `go.Figure` | 分析页统一暖白主题 |
| `create_candlestick_chart(*, chart_df, symbol, period_key, split_date, height=520)` | `go.Figure` | 单股 K 线主图 |
| `create_equity_drawdown_chart(series_specs, *, height=620, ...)` | `go.Figure` | 单股 / 多股结果区主图 |

### 多股常用图表

- `create_multi_stock_comparison_chart`
- `create_relative_strength_chart`
- `create_risk_return_scatter`
- `create_correlation_heatmap`
- `create_factor_score_comparison`
- `create_periodic_returns_heatmap`

这些接口默认返回 Plotly figure；前端只负责展示和主题一致性，不应在页面里重写第二套主题体系。

## 前端任务的停止边界

- 已经在本文档找到页面入参、状态键、共享 HTML、图表 contract 时，不要继续回扫部署文档。
- 只改页面壳层、布局、导出、图表容器时，不要直接追到核心算法实现。
- 如果发现 contract 不清晰，优先转 `strategy-interface-alignment`，不要重新全仓检索。
