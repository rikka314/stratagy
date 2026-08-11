# Frontend Contracts

> 最近更新：2026-08-06
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

`app.py` 通过 `st.navigation` 暴露五条真实路由：

- `/strategy`
- `/strategy/stock-analysis`
- `/strategy/stocks-analysis`
- `/strategy/model-evaluation`
- `/strategy/final-report`
- `/strategy/experiment-monitor`（仅本地控制模式）

页面 callable 只负责轻量路由注册；`ui.home`、`ui.single_stock*`、`ui.multi_stock*`、`ui.sidebar`、`ui.model_evaluation` 与 `ui.final_report` 均在对应 route wrapper 执行时局部导入。`MODEL_EVALUATION_ROUTE` 的公开 path 固定为 `model-evaluation`，不再为读取常量提前导入页面模块。

### 路由状态键

| state key | 结构 | 用途 |
|---|---|---|
| `route_single_state` | `{view, market, symbol, name, uploaded_name, uploaded_bytes, source}` | 单股入口页与主分析页切换；推荐入口可把名称带到分析页作为目录缺失时的本地化回退 |
| `route_multi_state` | `{view, market, symbols, uploads}` | 多股入口页与主分析页切换 |

### 临时工作区恢复

- 所有站内路由链接会在保留 `lang` 的同时传播可选 `ws=<opaque-token>` 查询参数。
- `ws` 对应服务器磁盘上的临时工作区：默认保存 24 小时，可跨首页跳转、刷新和 Streamlit 重连恢复；它不是用户登录或分享链接。
- 工作区保存 route state、sidebar/页面选择、单股 artifact 与多股组合结果；stage cache、Plotly figure 与页面展示缓存不落盘，恢复后按已有数据懒重建。
- `ws` 是短期 bearer 标识。页面必须提示用户不要分享包含该参数的 URL；“开始新的临时分析”会删除当前工作区并清除该参数。

`/strategy/model-evaluation` 是只读浏览页，不新增 route state key；页面只维护本地 selector 的 widget 状态。

### 语言状态与路由传播

- 支持语言：`zh`、`en`
- 查询参数：`?lang=zh` / `?lang=en`
- 会话状态键：`ui_language`
- `ui/i18n.py` 以合法查询参数优先，其次读取会话状态；无显式语言时默认英文。
- 顶部语言切换保留当前真实路由；首页、单股、多股、模型评估和报告链接均继续传播当前语言。

### 公共壳层 helper

- `_validate_strategy_params(params)`
  作用：在进入页面前兜住 EMA / MACD / RSI / 动量 / 分位数关系。
- `_apply_date_filter(df_raw, selected_range)`
  作用：统一把 `selected_range` 转成 `(filtered_df, is_datetime, start_ts, end_ts)`。
- `_ensure_valid_dataframe(df_raw, empty_message=...)`
  作用：校验 `open/high/low/close` 必需列。

### 顶部导航结构

- `render_route_nav(current)` 统一输出三段式无边界 header：左侧 `Strategy Lab`、居中的首页/单股/多股/报告、右侧研究证据入口与 `中 / EN`。
- “浏览研究证据”固定指向 `/strategy/model-evaluation`，并继续传播当前语言。
- 首页正文不再重复输出路由 CTA；首页先渲染固定平台标题和三个稳定 loading slot，再由并行 fragment 填充单行新闻轮播、强势股票星图与三幕市场镜头（地区指数 / 观察池日内领先 / 市场温度）。

### 首页每日新闻

- `ui/home.py::get_daily_market_headlines()` 读取服务端环境变量 `NEWS_API_KEY`，不把密钥写入浏览器 HTML。
- NewsAPI 请求走 `/v2/everything`，通过 `X-Api-Key` header 鉴权，按当前 `zh/en`、股票市场关键词和 `publishedAt` 获取最近新闻。
- 中文页面通过 OpenCC `t2s` 在服务端把 NewsAPI 标题统一转换为简体，再执行去重与每日缓存；英文标题保持原文。
- Windows 本机已启用系统代理但未设置 `HTTP_PROXY` / `HTTPS_PROXY` 时，首页请求会读取当前用户的 Internet Settings 代理；显式环境变量仍保持最高优先级。
- `st.cache_data` TTL 为 24 小时，并把本地日期加入缓存键；每日首次访问会生成新缓存。NewsAPI 请求使用显式 connect/read timeout，失败时只影响新闻 fragment。
- API 未配置、超时、返回错误或可用标题不足时，页面自动使用内置双语新闻补齐到四条，首页不得空白。
- 首页固定显示平台名称；每日新闻只在其下方以单行小字轮换。

### 首页市场镜头

- `ui/home.py::get_home_market_snapshot()` 服务端读取腾讯行情公开报价，覆盖标普 500、纳斯达克、上证、深证和恒生指数，以及固定的美股 / A 股高流动性观察池；该请求在市场镜头 fragment 内独立执行，不阻塞首页壳层。
- 行情缓存 TTL 为 15 分钟；请求失败时返回完整指数标签和空报价，页面统一显示“待更新”。
- 观察池只按最新单日涨跌幅做相对排序，并在页面注明样本边界和“不构成投资建议”；它不是全市场选股器。
- 市场温度只由当前可用指数的上涨数量、平均涨跌和最大离散度归纳；缺少全部报价时显示等待状态。
- 三幕以 24 秒周期连续交叉淡化；`prefers-reduced-motion` 下只显示第一幕。

### 首页强势股票星图

- 星图从 `core.market_context.get_recommended_stocks()` 派生的 `get_home_recommendation_pool()` 中按当前市场取最多 5 个入口页同源推荐；这是同源推荐池的相对动量，不是全市场选股结论。推荐请求与 K 线请求位于股票 fragment，K 线只在焦点股票确定后串行读取。
- 中央股票由 `home_stock_focus_market` 与 `home_stock_focus_index` 两个 session state key 驱动。
- `ui/home.py::get_home_stock_candles()` 从腾讯前复权 K 线接口读取当前股票最近 20 个交易日的真实 OHLC，缓存 15 分钟；美股请求使用交易所限定的 `.OQ` symbol，数据失败或少于两根时显示“K 线暂不可用”。
- 中央内容以本地化公司名为主、代码和涨跌幅为辅；K 线使用 HTML/CSS 直角柱体，避免 `st.html()` 对 SVG 子节点的清理。
- `ui/home.py::_render_stock_controls()` 输出真实 Streamlit 按钮：切换美股、切换 A 股、循环到下一只股票；按钮不得依赖被 HTML sanitizer 处理的内联跳转。按钮与星图统一放在 `home-stage-shell` 相对定位容器内，滚动时必须保持固定相对间距。
- 外围股票同时显示公司名、代码和涨跌幅，使用日期 + 市场 + 当前股票生成稳定位置顺序；移动端隐藏后两个外围项。

### 报告中心

- `/strategy/final-report` 继续以 `reports/Final_Report_zh.html` / `reports/Final_Report.html` 为唯一内容源，并通过 `ui.final_report` 的 `load_embeddable_report(path, mtime_ns)` 解析；源文件修改时间变化会自动失效缓存。
- reader 保留归档 HTML 的完整 section markup、表格、引用、附录与原始锚点，但默认只在 DOM 中渲染当前章节；`final_report_active_section` 保存当前 section，合法 `?section=<id>` 可深链接打开章节，非法值回退第一章。
- `lang` 与 `section` 查询参数可共存；两种语言使用同构 chapter ID，切换语言时尝试保留合法 section。
- 搜索采用提交式 `st.form`，draft 输入不会触发全文筛选。提交后只显示命中章节标题和可见文本 snippet；选择结果后通过其 section 深链接加载完整原始章节。无结果显示双语空态。
- 报告继续只使用共享 `render_html(..., localize=False)`，不使用 iframe；`.native-report-shell`、`.native-report-reading` 与 `.report-reading-document` 是稳定 DOM hook。

## 共享 HTML 与站点壳：`ui/theme.py`

| 接口 | 约定 |
|---|---|
| `route_href(url_path="", *, language=None)` | 统一拼接 `/strategy/...` 路径，并传播当前或显式指定的 `lang` 查询参数 |
| `render_html(markup)` | 大块 HTML 的唯一共享入口；优先走 `st.html()`，回退到 `st.markdown(..., unsafe_allow_html=True)` |
| `inject_base_styles()` | 每次应用执行注入 token、站点壳、header、共享控件和响应式基础 |
| `inject_home_styles()` | 仅首页注入市场舞台、星图、市场镜头与低动态规则 |
| `inject_entry_styles()` | 仅单股 / 多股入口注入 split layout、action card、showcase 与推荐列表规则 |
| `inject_analysis_styles()` | 仅单股 / 多股分析和模型评估注入分析 hero、结果板、图表与研究浏览规则 |
| `inject_report_styles()` | 仅报告中心注入 `.native-report-*` reader、目录、rail、搜索与阅读排版规则 |
| `inject_global_styles()` | 旧调用兼容入口；新路由不得使用，避免重新发送完整 CSS |

前端任务默认不要在页面里另起一套 HTML 渲染路径；大块 HTML 统一复用 `render_html()`。

### Route CSS 映射

- `/strategy`：`base + home`
- `/strategy/stock-analysis`、`/strategy/stocks-analysis`：入口态 `base + entry`，分析态 `base + analysis`
- `/strategy/model-evaluation`：`base + analysis`
- `/strategy/experiment-monitor`：`base + analysis`，仅本地控制模式注册
- `/strategy/final-report`：`base + report`

`get_style_bundle_css()` 是性能测试与浏览器 QA 的只读检查接口。selector 编译保持源规则顺序；同一规则被多个页面消费时会进入对应多个 bundle。非报告 bundle 不得包含 `.native-report-*`，报告 bundle 不得包含首页动画。

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

### 性能与提交边界

- 高级策略 slider 通过 `sidebar_strategy_parameters` form 批量提交；`render_sidebar()` 返回的参数 key 集合保持不变。
- 股票池、市场、日期、上传等上下文控件仍可即时改变数据上下文；策略高级参数只在提交 form 后作为一组生效。
- 单股纯展示图缓存位于 `single_stock_display_cache`，缓存键包含 workflow `context_key`、artifact ID、split date、周期、数据范围、指标视图、指标参数、语言和主题。context reset 只清理该展示缓存，不清理 stage cache。
- 多股策略权重通过 `multi_stock_portfolio_weights` form 批量提交；`_build_multi_strategy_signature()`、`portfolio_result` 和优化结果状态键保持原语义。

## 单股页 contract：`ui/single_stock.py`

### 页面入口

```python
render_single_stock_page(params: dict, df_raw: pd.DataFrame, symbol: str) -> None
```

### 输入要求

- `df_raw` 至少含 `open/high/low/close`，推荐同时含 `date/volume`
- `params` 来自 `render_sidebar()`，不要自造第二套参数命名
- `symbol` 由路由层归一；单股页会把 `params["compare_stocks"]` 归一成 `[symbol]`
- 行情数据标的名称按当前 `zh/en` 顺序展示：中文页以中文名为主、英文名为辅，英文页反之；代码始终作为末级回退。

### 页面本地状态

| state key | 作用 |
|---|---|
| `single_stock_selected_artifact_ids` | 比较模式选中的 artifact |
| `single_stock_focus_artifact_id` | 当前主策略 |
| `single_stock_signal_dataset_split` | 买卖点图读取 train 还是 test |
| `single_stock_workflow_regime_kind` | regime 工作台当前选择 |

### 策略工作台布局

- 桌面端模型控制台与结果板保持同一固定视窗高度，各自内部滚动；空态与生成态不得改变两栏外框高度。
- 移动端恢复自然纵向高度，不强制内部滚动。
- 训练比例的上下文重建影响写入 slider 帮助；完整路径说明由“如何使用策略模块”弹窗承接，生成、保存与比较规则由“生成与策略库”旁的悬浮问号承接。
- 帮助层只解释操作与模型取舍，不改变 `StrategyRequest`、workspace、artifact 或 stage cache 语义。

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
- `full_us_deans_60` 完整产物在通用明细表之前展示冻结的美股研究基线：当前离线候选、Naive 对照边界、ML 增量结论、adaptive router 状态数和市场适用范围；不得因缺少 CN_A 产物而显示为跨市场证据错误。

兼容约定：

- `quantstats` 缺失时视为空列表。
- `mlflow_run.json` 不存在时视为“未记录 MLflow”。
- `adaptive_router` 可以存在，也可以不存在；前端只读页必须容忍 report payload 的这类扩展字段。

## 本地实验监控页 contract：`ui/experiment_monitor.py`

### 路由与安全边界

- 本地控制路由为 `/strategy/experiment-monitor`。
- 只有 `STRATAGY_RESEARCH_CONTROL=1` 时 `app.py` 才注册该路由；生产默认不暴露启动、暂停或恢复入口。
- 页面关闭或 Streamlit rerun 不影响独立 campaign manager。

### 数据与展示

- campaign 列表来自 `model-test/outputs/_campaigns/*/campaign.json`。
- 页面每 2 秒读取 `campaign.json`、`progress.json`、当前 run checkpoint 与日志尾部。
- checkpoint 并发追加导致瞬时解析失败时，继续展示当前会话最近一次有效快照。
- 排名固定拆为 Stage A、Stage B、rolling robustness 和最终榜；前三者明确标记为临时排名并展示覆盖率。
- A 股 `symbol` 必须按字符串读取，保留前导零。

### 控制语义

- `安全暂停` 只写 cooperative pause request，不终止进程。
- `pause_requested` 与 `paused` 必须分开展示；前者表示仍有在途批次尚未落盘。
- `恢复` 只允许 paused/failed campaign，并由后台校验 Git commit 和 config hash。
- 当 `full_us_deans_60` 已通过完整性校验且当前决策明确暂停 CN_A / CROSS 时，监控页把旧 manager failure 映射为“美股已完成 / 研究范围已冻结”，不再提供恢复按钮；底层 campaign/checkpoint 状态保持不变。

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

这些接口默认返回 Plotly figure；前端只负责展示和主题一致性，不应在页面里重写第二套主题体系。共享 `apply_plotly_theme()` 与 `st.plotly_chart` 展示入口会统一移除内置 `layout.title`，图表上下文标题由外层页面 surface 承载。

## 前端任务的停止边界

- 已经在本文档找到页面入参、状态键、共享 HTML、图表 contract 时，不要继续回扫部署文档。
- 只改页面壳层、布局、导出、图表容器时，不要直接追到核心算法实现。
- 如果发现 contract 不清晰，优先转 `strategy-interface-alignment`，不要重新全仓检索。
