# Multi-Stock And Portfolio Interfaces

> 最近更新：2026-03-28
> 适用范围：`ui/multi_stock.py`、`core/portfolio.py`、`core/market_context.py`。

## 页面与结果边界

- `ui/multi_stock.py`
  负责：股票池编辑、基础信息区、组合控制台、结果区、HTML 导出。
- `core/portfolio.py`
  负责：对股票池逐只跑策略，再合成组合结果与优化结果。
- `core/market_context.py`
  负责：入口页和分析页需要的市场指数与推荐股票快照。

多股页不复用单股 artifact / stage cache；它有自己独立的 workspace。

## 关键状态键

| state key | 作用 |
|---|---|
| `route_multi_state` | 路由层的 `{view, market, symbols, uploads}` |
| `multi_stock_strategy_workspace` | 当前组合结果与优化结果缓存 |
| `multi_stock_analysis_section` | 基础信息 / 策略区切换 |

## route state 结构

`route_multi_state` 当前稳定字段：

- `view`
- `market`
- `symbols`
- `uploads`

其中：

- `symbols`：市场数据路径中的股票代码列表
- `uploads`：上传数据列表，供 `prefetched_stock_data` 构建

## 页面入口

```python
render_multi_stock_page(
    params: dict,
    is_datetime: bool,
    start_ts,
    end_ts,
    prefetched_stock_data: dict[str, pd.DataFrame] | None = None,
) -> None
```

### 输入语义

- `params`：来自 `render_sidebar()`
- `params["compare_stocks"]`：市场下载路径下的股票池
- `prefetched_stock_data`：上传文件构建的 `symbol -> DataFrame`
- `is_datetime/start_ts/end_ts`：由 `app.py` 的统一日期过滤逻辑提供

## 多股 workspace

### 结构

```python
{
    "signature": str | None,
    "portfolio_result": dict | None,
    "optimization_signature": str | None,
    "optimization_result": dict | None,
}
```

### 签名函数

```python
_build_multi_strategy_signature(
    stock_data_dict: dict[str, pd.DataFrame],
    params: dict,
    weights: dict[str, float],
) -> str
```

签名由三部分组成：

- 股票池内容
- sidebar 中的策略参数子集
- 组合权重

股票池、参数或权重变化后，旧结果会被视为 stale，需要重新生成。

## 组合生成接口：`core/portfolio.py`

### `run_portfolio_simulation`

```python
run_portfolio_simulation(stock_data_dict: dict, **kwargs) -> dict | None
```

当前结果区稳定消费这些 key：

- `fig`
- `portfolio_strat_ret`
- `individual_results`
- `weights`
- `port_total_return`
- `port_sharpe`
- `port_max_dd`
- `bh_total_return`
- `bh_sharpe`
- `bh_max_dd`

结果区和导出区都依赖这些 key；如果修改返回结构，需要同步更新 `ui/multi_stock.py` 和本文档。

### `bayesian_optimize_portfolio`

```python
bayesian_optimize_portfolio(
    stock_data_dict: dict,
    n_trials: int = 50,
    **fixed_params,
) -> dict | None
```

当前页面已展示并消费的优化 key：

- `score`
- `sharpe`
- `return`
- `max_drawdown`
- `entry_threshold`
- `exit_threshold`
- `adx_threshold`
- `stop_loss_mult`
- `take_profit_mult`
- `weight_bb`
- `weight_obv`
- `weight_volume`
- `weight_price`
- `weight_drawdown`

## 市场上下文接口：`core/market_context.py`

### 指数快照

```python
get_market_indices(market: str) -> list[dict[str, Any]]
```

作用：返回入口页和分析页顶部的大盘指数块。

### 推荐股票

```python
get_recommended_stocks(market: str, limit: int = 10) -> dict[str, Any]
```

当前语义：

- A 股和美股都优先走百度股市通“今日”热搜，按综合热度降序
- 热搜不可用时，A 股降级到实时涨幅榜，美股降级到知名美股分组实时涨幅榜
- 两级实时数据都不可用时返回空列表，不再回退默认股票池

推荐结果包含：

- `source_kind`：稳定来源码，供双语 UI 映射来源说明
- `source_label`
- `items`：保留 `symbol/name/price/pct_change`；热搜项额外包含 `rank/heat`

`get_market_context_snapshot()` 在原有 `recommendation_source` 和 `recommendations` 之外，增加兼容字段 `recommendation_source_kind`。格式化后的热搜项带 `heat_text`；实时涨幅榜项继续使用 `price_text`。

## 多股结果区 contract

多股策略区右侧结果板当前固定两类主图：

- `投资组合模拟`
- `周期收益率热图`

同时固定保留：

- 组合 KPI 摘要
- “各股票独立策略表现”明细表

如果只是改结果区壳层、排序或切换逻辑，优先留在 `ui/multi_stock.py`；只有改结果字典形状时才下探 `core/portfolio.py`。

## 导出 contract

`ui/multi_stock.py` 的导出区 `_render_multi_stock_export(...)` 当前消费：

- `compare_stocks`
- `stock_data_dict`
- `comparison_stats`
- 基础信息区图表
- `periodic_heatmap_fig`
- `portfolio_result`

因此多股页任何结果结构变更，都要同时检查导出区。
