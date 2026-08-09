# Strategy Lab 网页性能深度诊断与执行计划

> 日期：2026-08-07  
> 交付性质：供另一个 AI 窗口直接执行的实施计划  
> 当前边界：本次会话只完成诊断与计划，没有修改业务代码  
> 目标站点：本地 `/strategy` 及线上 `https://www.gfm156.com/strategy`

## 1. 先给结论

当前“网页加载很慢”不是单一函数导致，而是四层延迟叠加：

1. **首页把首个可见内容放在所有外部请求之后**。新闻、市场快照、推荐股票、焦点股票 K 线在 `render_html()` 之前同步执行；任一上游慢，用户先看到空白。
2. **Python 冷启动存在过度导入**。`app.py` 在选定路由前导入单股、多股、模型评估、报告和 sidebar；而任意 `core.*` 导入都会先执行 `core/__init__.py`，后者又把 sklearn、AkShare、优化器、图表等全量导入。
3. **报告页一次性注入完整大文档**。当前英文报告正文约 419k 字符，浏览器生成约 7,005 个 DOM 节点和 85 张表；搜索每次输入还会重跑并重新发送大正文。
4. **Streamlit 的固定客户端/会话成本仍然存在**。即使服务端数据与模块均已热，本机浏览器刷新仍需约 3.5–4.0 秒；应用可以通过尽早输出壳层、缩小增量、限制 rerun 范围改善体感，但无法仅靠某个 `@st.cache_data` 消除全部框架成本。

因此执行顺序必须是：

`建立测量基线 -> 缩短冷导入 -> 首页先渲染且并行取数 -> 报告按章加载 -> 收窄分析页 rerun -> 再做 CSS/部署优化`

不要先调颜色、删动画或盲目增加缓存；这些都不是当前最高收益点。

## 2. 诊断范围与保护边界

### 2.1 本计划覆盖

- `app.py` 路由壳层和导入链
- `core/__init__.py`、`core/market_context.py` 的启动与外部请求
- `ui/home.py` 首页首屏
- `ui/final_report.py` 完整报告与搜索
- `ui/sidebar.py`、`ui/single_stock.py`、`ui/multi_stock.py` 的 rerun 范围
- `ui/theme.py` 的全局 CSS 负载
- `run.bat`、`requirements.txt`、`deploy/*`、Nginx 的启动与传输行为

### 2.2 不允许破坏

- 公开路由与 `/strategy` base path
- `route_single_state`、`route_multi_state` payload shape
- 单股 `StrategyRequest / StageResult / StrategyArtifact / workspace / stage cache` 语义
- 多股 `portfolio_result`、优化结果和 workspace key
- 首页真实行情、失败空态、不使用伪造数据的约定
- 中英双语和 `?lang=zh|en` 路由传播
- 报告的完整内容来源；可以按章加载，但不能删章、改结论或丢表
- 当前用户尚未提交的工作树修改

## 3. 已测基线

### 3.1 测试环境

| 项目 | 值 |
|---|---|
| OS | Windows |
| Python | 3.13.7 |
| Streamlit | 1.60.0 |
| 本地端口 | 8501；另启干净进程 8502 做冷启动测试 |
| 浏览器工具 | Playwright CLI，独立 session |
| 工作树 | 已有大量用户未提交修改；不得 reset 或覆盖 |

### 3.2 端到端时间

| 场景 | 实测 | 解释 |
|---|---:|---|
| 当前工作树，干净 Streamlit 进程的第一个首页会话 | 12.788 s | 包含冷导入、首页冷缓存外部请求、Streamlit 首次会话与浏览器渲染 |
| 当前工作树，服务缓存已热、全新浏览器 | 4.608 s | 主要是客户端静态资源、WebSocket 会话和页面增量 |
| 当前工作树，服务与浏览器均已热 | 3.473–4.024 s | 首页稳定热刷新范围 |
| Python `AppTest` 首次完整执行 `app.py` | 5.456 s | 无真实浏览器，主要反映冷导入 + 首页数据链 |
| 同一 `AppTest` 进程后续执行 | 26–29 ms | 证明当前 `st.cache_data` 命中后，纯 Python 重跑不是首页热刷新 3.5 s 的主因 |
| 当前工作树报告页出现正文 | 4.988 s | 大 HTML/DOM 是主要因素 |
| 当前线上站点，全新浏览器出现旧版首页标题 | 5.353 s | 线上仍是较旧首页，不等于当前工作树 |
| 当前线上站点热刷新 | 0.933–1.404 s | 只能作为旧版对照，不可当作当前代码验收结果 |

线上页面标题仍是 `Turn the stock strategy entry into a real product homepage.`，而当前工作树首页标题是 `Stock Strategy Analysis Platform`。这说明**线上部署版本与本地工作树不一致**。后续 AI 必须分别记录本地优化结果与部署后结果，不能混用。

### 3.3 冷导入证据

使用 `python -X importtime -c "import app"` 得到的关键累计时间：

| 导入链 | 累计时间 |
|---|---:|
| `app` | 约 2.400 s |
| 任意 `core.*` 触发的 `core/__init__.py` 全量导入 | 约 0.965 s |
| `core.fa_filter -> sklearn` | 约 0.701 s |
| `ui.sidebar -> st_keyup` | 约 0.563 s |
| `streamlit` | 约 0.380 s |
| `pandas` | 约 0.352 s |
| `core.data -> akshare` | 约 0.239 s |

关键事实：`app.py` 进入首页前就导入 `ui.single_stock`、`ui.multi_stock`、`ui.model_evaluation`、`ui.sidebar`、`ui.final_report`；首页用户为未访问路由支付了完整导入成本。

### 3.4 首页外部请求证据

`ui/home.py::render_home_page()` 当前顺序是：

1. `get_daily_market_headlines()`
2. `get_home_market_snapshot()`
3. `get_recommended_stocks()`
4. 确定焦点股票
5. `get_home_stock_candles()`
6. 最后才 `render_html()` 输出首页主体

一次本机独立网络样本：

| 调用 | 时间 |
|---|---:|
| 新闻 | 816 ms |
| 首页市场快照 | 316 ms |
| 推荐股票 | 642 ms |
| K 线请求 | 776 ms |

健康网络下这些调用已经能累计到秒级；网络异常时，上限更严重：新闻 timeout 6 s、首页行情与 K 线各 5 s、推荐热搜 3 s 后还可能进入 AkShare fallback。

`core/market_context.py::_load_us_famous_recommendations()` 对 6 个 future 逐个调用 `future.result(timeout=3)`。这里的 timeout 是**每个 future 的等待**，不是整批任务的总 deadline；当 AkShare 内部请求长期挂起时，理论等待会累加，而且 `shutdown(wait=False)` 不能真正终止已经运行的线程。反复强制刷新还可能留下仍在等待网络的 worker。

### 3.5 浏览器负载证据

当前 Streamlit 1.60 首次浏览器客户端：

- 114 个 resource entry
- 传输约 796 KB
- 解码后约 2.43 MB
- 这是 Streamlit 客户端基线，应用只能通过缓存头和版本稳定性优化，不能完全消除

首页完成后：

- 约 377 个 DOM 元素
- 页面 HTML 约 110k 字符
- 全局 style block 约 77.6k 字符
- 首页主体 HTML 约 12.4k 字符

报告页完成后：

- 约 7,005 个 DOM 元素
- 页面 HTML 约 521k 字符
- 85 张表
- 报告正文 `st.html` block 约 423.7k 字符
- 全局 style block 约 77.6k 字符

报告拆分是安全的：英文报告当前可提取 10 个 `<section>`，单节最大约 83.4k 字符；按节渲染可把单次正文发送量降到当前的约 1/5 或更低。

### 3.6 分析页 rerun 证据

| 文件 | widget 调用点 | slider 调用点 |
|---|---:|---:|
| `ui/sidebar.py` | 46 | 35 |
| `ui/single_stock.py` | 45 | 18 |
| `ui/multi_stock.py` | 23 | 10 |

折叠 `st.expander` 不等于不执行其中代码。当前 sidebar 高级参数虽然默认折叠，控件仍会被创建；控件变化默认触发整页 rerun。

已有正确基础：

- 单股指标 `add_indicators` 已有 `st.cache_data`
- 单股 workflow stage cache 语义清楚，不能推倒重建
- 多股已有 `multi_stock_analysis_cache`、`figure_cache`、`heatmap_cache`
- sidebar 搜索已有 `st.fragment`

需要优化的是展示层 rerun 和图表构建，不是重写策略算法。

## 4. 根因优先级

| ID | 优先级 | 根因 | 证据置信度 | 处理方式 |
|---|---|---|---|---|
| RC-1 | P0 | 首页在外部请求完成后才输出首屏 | 高 | 先渲染静态壳；独立慢区用 parallel fragment/并发取数 |
| RC-2 | P0 | `app.py` 与 `core/__init__.py` 过度导入 | 高 | 保留兼容 API 的 lazy import；路由本地导入 |
| RC-3 | P0 | 外部请求没有统一总 deadline，AkShare fallback 可能留下挂起线程 | 高 | 总 deadline、显式 connect/read timeout、可取消/可降级结构 |
| RC-4 | P0 | 报告正文一次性发送和构建 7k DOM，搜索每键重发 | 高 | 报告预解析、按章渲染、提交式/fragment 搜索 |
| RC-5 | P1 | sidebar 和分析控件扩大整页 rerun | 高 | form 批量提交；结果区 fragment；缓存纯图表/Walk-Forward |
| RC-6 | P1 | 启动和部署依赖版本不稳定 | 高 | 修正 Streamlit 最低版本或 lock；按 requirements hash 安装 |
| RC-7 | P2 | 每条路由都注入约 77.6k 全局 CSS | 高 | 基础 CSS + 路由 CSS 拆分，去重死规则 |
| RC-8 | P2 | Nginx 模板没有单独定义 hashed static 缓存/压缩 | 中 | 在真实 vhost 核验后增加静态资源规则 |
| RC-9 | 非主因 | 首个 HTML/health TTFB | 高 | 线上 curl 约 130–139 ms，不是当前主要瓶颈 |

## 5. 分阶段实施计划

## Phase 0 — 先建立可重复性能门禁

### 目标

让后续每一阶段都能证明“真的更快且结果没变”，避免凭感觉修改。

### 文件

- 新增 `core/perf.py`
- 新增 `scripts/measure_app_performance.py`
- 新增 `tests/test_web_performance_contracts.py`
- 可选新增 `document/acceptance/web_performance_20260807.md`

### 实施

1. 在 `core/perf.py` 提供环境变量控制的计时器，例如 `STRATAGY_PERF_TRACE=1` 时输出 JSON line：
   - route
   - phase
   - elapsed_ms
   - cache/status/source
   - 不记录 API key、上传内容、完整 symbol 列表
2. 至少覆盖这些 phase：
   - `app.route_imports`
   - `home.headlines`
   - `home.market_snapshot`
   - `home.recommendations`
   - `home.candles`
   - `report.parse`
   - `report.render_section`
   - `single.indicators`
   - `single.figure_build`
   - `single.walk_forward`
   - `multi.data_load`
   - `multi.figure_build`
3. `scripts/measure_app_performance.py` 用子进程测：
   - `import app`
   - `AppTest` 冷执行
   - 同进程第二次执行
   - 输出 JSON，不把机器相关阈值直接写成普通单元测试的脆弱 hard fail
4. 单元测试只验证：
   - 计时器关闭时无副作用
   - timeout/fallback 在规定 deadline 内返回
   - lazy import 前后 API 兼容
5. 浏览器验收继续使用 Playwright CLI，不需要为此引入新的前端构建系统。

### 初始性能预算

| 指标 | 预算 |
|---|---:|
| `import app` 冷导入 | <= 1.0 s（当前机器） |
| 首页静态壳可见 | <= 1.5 s（服务已启动、本地） |
| 首页健康上游完整数据 | <= 4.0 s |
| 上游全部异常时静态壳 | 仍 <= 1.5 s |
| 上游全部异常时所有 fragment 结束 | <= 4.5 s |
| 报告首章可见 | <= 2.0 s |
| 报告搜索提交后结果 | <= 0.8 s（本地、缓存已热） |

性能测试应记录 p50/p75 和三次样本，不以单次最小值验收。

### 完成条件

- 能复现本计划第 3 节的大类数据
- 日志能区分 Python、外部 I/O、浏览器三层时间
- 默认生产环境不输出调试噪声

## Phase 1 — 消除未访问路由的冷导入成本

### 目标

首页启动时只导入首页真正需要的最小模块。

### 文件

- `core/__init__.py`
- `app.py`
- `core/market_context.py`
- `ui/sidebar.py`
- `tests/test_web_performance_contracts.py`

### 实施

1. 重构 `core/__init__.py`：
   - 不再启动时导入所有 core 模块。
   - 为旧的 `from core import DATA_DIR/add_indicators/...` 入口保留 PEP 562 `__getattr__` lazy mapping，或明确迁移所有消费者后保留兼容 shim。
   - `import core.market_context`、`import core.optimizer` 必须只加载目标子模块及其真实依赖。
2. 重构 `app.py`：
   - 顶层保留 `streamlit`、i18n、最小主题和轻量路由定义。
   - `ui.single_stock`、`ui.multi_stock`、`ui.sidebar`、`ui.model_evaluation`、`ui.final_report` 放到对应 page callable 内局部导入。
   - `pandas`、`core.data`、`core.utils` 放到单股/多股分析路径局部导入；首页不要支付这些成本。
   - `MODEL_EVALUATION_ROUTE` 改成轻量常量模块，或在 `app.py` 固定为现有 path，避免为一个常量导入整个评估页。
3. `core/market_context.py`：
   - 把 `akshare` 改为 fallback 函数内部导入。
   - 直接 HTTP 热搜/行情成功时，不加载 AkShare。
4. `ui/sidebar.py`：
   - `st_keyup` 只在首次真正渲染实时搜索 fragment 时导入。
   - 保留缺包时回退 `st.text_input` 的行为。
5. 增加子进程测试：
   - `python -c "import core.config; assert 'sklearn' not in sys.modules"`
   - `python -c "import app; assert 'lightgbm' not in sys.modules; assert 'optuna' not in sys.modules"`
   - 旧公共导入若声明兼容，逐项 smoke test。

### 风险与回滚

- 风险：外部脚本可能依赖 `from core import X`。
- 控制：先用 lazy compatibility map，不要直接清空 API；全仓 `rg "from core import"` 后再逐步收缩。
- 回滚：只回滚 lazy mapping，不回滚后续首页/报告优化。

### 完成条件

- 冷 `import app` <= 1.0 s
- 首页导入后 `sklearn/lightgbm/optuna/st_keyup` 不在 `sys.modules`
- 所有现有 pytest 通过

## Phase 2 — 首页改成“壳层先到、数据并行、失败有总上限”

### 目标

用户先看到平台标题、新闻/行情占位和控制区；慢数据随后独立填充，不再整页空等。

### 依据

本地 Streamlit 1.60 已支持 `st.fragment(..., parallel=True)`。官方文档说明 parallel fragment 在 full rerun 时可与其他 fragment 及主脚本并发执行；缓存适合避免 API 调用在每次 rerun 重复执行：

- [Streamlit `st.fragment`](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
- [Streamlit caching overview](https://docs.streamlit.io/develop/concepts/architecture/caching)

### 文件

- `ui/home.py`
- `core/market_context.py`
- `ui/theme.py`（只补 loading/empty slot 所需共享样式）
- `requirements.txt`
- `tests/test_home_news_api.py`
- `tests/test_market_context_recommendations.py`
- 新增首页并发/timeout 测试

### 实施结构

1. `render_home_page()` 最先同步输出：
   - `render_route_nav("home")`
   - 平台标题
   - 固定高度的新闻 slot、股票星图 slot、市场镜头 slot
   - loading/empty 文案，确保布局不跳动
2. 把慢区拆成独立渲染函数：
   - `_render_home_headlines_fragment(language)`
   - `_render_home_stock_cloud_fragment(language, selected_market)`
   - `_render_home_market_lens_fragment(language)`
3. 对互不依赖的区块使用 `@st.fragment(parallel=True)`。
   - 首次 full run 并行获取新闻、推荐与市场快照。
   - 股票 K 线依赖推荐池，只在股票 fragment 内串行执行。
   - 控件只修改自己的 session state；不要在多个并行 fragment 中同时写同一个 mutable dict。
4. 保留原有 TTL：
   - 新闻 24h
   - 行情/推荐/K 线 15min
   - 增加 `max_entries`，避免 symbol 切换长期增长
5. 推荐 fallback 改成**整批总 deadline**：
   - 不再对 6 个 future 分别等待 3 秒。
   - 使用 `wait(..., timeout=TOTAL_DEADLINE)` 或 `as_completed` + `perf_counter` 剩余时间。
   - deadline 到达后立即返回已完成结果/空态；不要继续阻塞页面。
6. 所有 `requests` 使用显式 connect/read timeout，例如 `(1.0, 2.0)`，并在外层保持总 deadline。
7. 延迟敏感页面优先使用当前直接 HTTP 数据源；AkShare 只作为有界 fallback。无法给 AkShare 内部请求设置硬 timeout 的路径，不允许无限创建短命 executor。
8. “刷新市场快照”只能清理相关函数缓存/会话快照，不调用全局 `st.cache_data.clear()`。
9. 数据源失败时：
   - 已有旧快照则标记时间并显示旧快照
   - 没有快照则显示当前 contract 的“待更新”/“K 线暂不可用”
   - 不生成假数据

### 测试

1. 用 monkeypatch 让新闻/行情/推荐分别 sleep，验证总时间接近 `max()` 而不是 `sum()`。
2. 让 6 个 US fallback loader 全部超过 deadline，验证函数在总预算内返回且不会按 6 × timeout 累加。
3. 验证一个 fragment 失败不会阻止其他区块出现。
4. 验证美股/A 股/换一只的状态键仍是：
   - `home_stock_focus_market`
   - `home_stock_focus_index`
5. 验证中文 OpenCC、NewsAPI fallback、腾讯行情解析现有测试不回退。

### 完成条件

- 首页静态壳 <= 1.5 s 可见
- 上游全部超时时页面不空白
- 首页请求从串行关键路径变为并行关键路径
- 无新增后台线程持续增长

## Phase 3 — 报告页按章加载，搜索不再重发整本报告

### 目标

保留完整报告内容，但单次只向浏览器发送当前需要的章节。

### 文件

- `ui/final_report.py`
- `ui/theme.py`
- `tests/test_final_report_page.py`
- `document/interfaces/frontend-contracts.md`
- `AI_CONTEXT.md`（完成后记录 durable reader 语义）

### 实施

1. 把 `load_embeddable_report()` 改为返回结构化、可序列化数据：

   ```python
   {
       "intro_html": str,
       "toc": tuple[...],
       "sections": tuple[{"id", "title", "html", "search_text"}, ...],
       "mtime_ns": int,
   }
   ```

2. 解析仍以归档 HTML 为唯一内容源；不复制报告内容到 Python 常量。
3. 默认只渲染：
   - intro
   - 目录
   - 当前 active chapter（默认第一章正文）
4. 新增 `final_report_active_section` session key，并支持 `?section=<safe-id>` 深链接；切语言时保留合法 section。
5. 搜索改为：
   - `st.form` + submit，避免每个键盘事件整页 rerun；或
   - 独立 `@st.fragment`，只重跑搜索结果区
6. 搜索结果默认先显示命中章节清单和短 snippet；用户点章节后才发送完整章节 HTML。
7. 每章继续调用共享 `render_html(localize=False)`，不回退 iframe，不改变表格/引用/附录内容。
8. 把目录 CSS 和 report CSS 从全局基础 CSS 中拆到报告路由，避免其他页面支付报告样式负载。

### 浏览器预算

| 指标 | 目标 |
|---|---:|
| 默认报告 DOM | < 2,000 nodes |
| 单次正文 HTML block | < 120k 字符 |
| 默认正文出现 | < 2.0 s |
| 搜索提交返回命中列表 | < 0.8 s |
| 切换章节 | < 1.0 s（缓存已热） |

### 测试

- 10 个现有 section 均可按 ID 打开
- 中英报告章节 ID/标题映射合法
- 查询命中数与当前 `filter_report_sections` 口径一致
- 非法 section 回退第一章，不抛异常
- 任何章的表格、引用、附录不丢失
- 报告路径/mtime 变化后缓存失效

### 风险与回滚

- 风险：当前 contract 写着“完整正文直接渲染”。
- 控制：更新 contract 为“完整内容可达、按章原生渲染”，明确不是删减。
- 回滚：保留临时 feature flag `STRATAGY_REPORT_LAZY=0` 一次发布周期；稳定后删除旧路径。

## Phase 4 — 收窄 sidebar、单股、多股 rerun

### 目标

参数输入不再每动一次 slider 就重画整个分析页；只在用户明确“应用参数/生成策略”后触发必要计算。

### 文件

- `ui/sidebar.py`
- `ui/single_stock.py`
- `ui/multi_stock.py`
- `ui/single_stock_workflow.py`（只允许补缓存 helper，不改 artifact contract）
- `document/interfaces/frontend-contracts.md`
- 必要时更新单股/多股接口文档

### Sidebar

1. 搜索 fragment 保留。
2. 将 35 个高级 slider 放进一个或按语义分组的 `st.form`。
3. 使用 `st.form_submit_button("应用参数")` 一次提交。
4. 保持 `render_sidebar() -> params` key 集合完全不变。
5. 市场、股票、日期范围等需要立即改变数据上下文的控件可留在 form 外；策略参数放 form 内。

### 单股

1. 不改 `run_strategy_pipeline()` 与 stage cache。
2. 为纯展示产物增加 session figure cache，key 至少包含：
   - `context_key`
   - `artifact.id`
   - train/test split
   - display mode
   - theme/language（若影响 figure 文案或颜色）
3. 缓存：
   - K 线与指标 figure
   - 净值/回撤 figure
   - 月度热图
   - 因子分数 figure
   - 信号比较 figure
4. Walk-Forward 结果按 `artifact.id + train_window + test_window + stop_loss + take_profit` 缓存。
5. 详细结果切换放入普通 fragment；不要用 `parallel=True` 修改共享 workspace。
6. context reset 时只清理对应展示 cache；不得误清 stage cache 的其他合法桶。

### 多股

1. 保留现有 `multi_stock_analysis_cache / figure_cache / heatmap_cache`。
2. 权重与策略参数使用 form 批量提交。
3. 结果视图与 heatmap period 用 fragment，只重画右侧结果板。
4. `_build_multi_strategy_signature()` 和 `portfolio_result` key 不变。
5. 仅在股票池/日期/复权/上传发生变化时刷新 data cache。

### 完成条件

- 展示切换不调用 FA/ML/搜索/组合优化
- 调 slider 未提交时不触发分析页全量重画
- 单股/多股现有 workspace、stale 判断、导出读取保持一致
- 所有相关接口测试和 W5/W8 回归通过

## Phase 5 — 缩小 CSS 与页面增量

### 目标

让首页、分析页、报告页只接收自己需要的 CSS。

### 文件

- `ui/theme.py`
- 各 route page 的样式注入调用
- `document/FRONTEND_STYLE_STANDARD.md`（只记录加载结构，不改变视觉基线）

### 实施

1. 将当前约 77.6k style block 拆为：
   - `inject_base_styles()`：token、header、通用 surface、响应式基础
   - `inject_home_styles()`
   - `inject_entry_styles()`
   - `inject_analysis_styles()`
   - `inject_report_styles()`
2. 每条真实路由只注入 base + 自己的 bundle。
3. 删除已经没有 DOM 消费者的旧 selector；先用 `rg` 和浏览器 DOM 核验，不能凭名字猜。
4. 不改视觉 token、不恢复旧蓝灰卡片体系。

### 预算

- 首页 style payload 目标 < 40k 字符
- 非报告页不得包含 `.native-report-*` 大段规则
- 报告页不得包含未使用的首页动画规则

## Phase 6 — 启动、依赖与部署链

### 目标

避免每次本机启动重复安装依赖，保证本地和线上运行同一个受支持的 Streamlit 能力集。

### 文件

- `requirements.txt`
- 可新增 `requirements.lock.txt`
- `run.bat`
- `deploy/sync.bat`
- `deploy/upload_and_deploy.bat`
- `deploy/deploy.sh`
- `deploy/nginx_strategy.conf`
- `.streamlit/config.toml`
- `document/interfaces/deploy-runtime.md`

### 实施

1. 因计划使用 `st.fragment(parallel=True)`，修正当前过低的 `streamlit>=1.28.0`：
   - 最低版本至少与实际 API 一致；建议在验证后锁定 `>=1.60,<1.62`，或生成经测试的 lock 文件。
2. `run.bat`：
   - 对 `requirements.txt` 计算 hash。
   - 仅当 venv 不存在或 hash 改变时执行 pip install。
   - 正常二次启动直接运行 Streamlit。
3. `deploy/sync.bat` 当前只上传 requirements 后重启，未保证安装新依赖。改为远端比较 hash，变化时才执行 `${REMOTE_DIR}/venv/bin/pip install -r requirements.txt`。
4. 全量 `deploy.sh` 仍可执行完整 bootstrap，但记录安装版本和启动后 health check。
5. Nginx 在真实主 vhost 核验后再改：
   - `/strategy/static/` 的 hashed asset 可设置长期 cache/immutable
   - `_stcore/health`、`host-config`、WebSocket 不设置长期缓存
   - JS/CSS/HTML 启用 gzip；若站点已有全局 gzip，避免重复冲突
   - 保留 WebSocket upgrade、base path 和 86400 timeout
6. 不要把 `proxy_buffering off` 的 WebSocket规则误用于新增静态缓存 location。

### 完成条件

- 本地第二次 `run.bat` 不执行 pip install
- 增量部署的依赖变化会被实际安装
- 本地/线上输出 Python、Streamlit 版本
- `/strategy` 五条路由和 WebSocket 均通过

## Phase 7 — 最终验收矩阵

### 功能矩阵

| 路由/动作 | 必测 |
|---|---|
| 首页 | zh/en、新闻成功/失败、行情成功/失败、美股/A 股、换一只、reduced motion |
| 单股入口 | 搜索、推荐、上传、刷新市场快照 |
| 单股分析 | basics/strategy、生成、保存、比较、信号、Walk-Forward、导出 |
| 多股入口 | 搜索加入、推荐加入、上传、删除、最少两只校验 |
| 多股分析 | basics/strategy、权重、生成、优化、heatmap、导出 |
| 模型评估 | 无 run、有效 run、缺 quantstats、缺 MLflow |
| 报告 | 10 section、中英、搜索、深链接、回到顶部 |

### 性能矩阵

每个结果记录 3 次，分冷/热：

| 场景 | 冷 | 热 |
|---|---:|---:|
| `import app` | 必测 | N/A |
| 首页壳可见 | 必测 | 必测 |
| 首页数据完整 | 必测 | 必测 |
| 单股入口壳可见 | 必测 | 必测 |
| 报告首章 | 必测 | 必测 |
| 报告切章 | N/A | 必测 |
| sidebar 提交参数 | N/A | 必测 |
| 单股结果视图切换 | N/A | 必测 |
| 多股结果视图切换 | N/A | 必测 |

### 推荐命令

```powershell
.\.venv\Scripts\python.exe -X importtime -c "import app"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\measure_app_performance.py
```

浏览器使用独立 Playwright session，先打开 `about:blank`，再在同一 `run-code` 中记录 `Date.now()`、`page.goto()` 和目标元素 `waitFor()`；不要把 `npx` 启动时间算进页面时间。

## 6. 建议提交顺序

每个阶段单独提交，便于二分与回滚：

1. `perf: add reproducible web latency baseline`
2. `perf: lazy-load routes and core public api`
3. `perf: render home shell before bounded parallel data`
4. `perf: paginate native final report by section`
5. `perf: batch sidebar inputs and isolate result reruns`
6. `perf: split route css payloads`
7. `deploy: lock runtime and cache static assets safely`
8. `docs: record performance acceptance and durable contracts`

不要把 Phase 1–6 压成一个大提交。

## 7. 其他 AI 开工提示词

可直接把下面内容发给新的 AI 窗口：

```text
请严格按 plan/web_performance_optimization_20260807.md 执行。

先读：
1. D:\Learn\20_Projects\AGENTS.md
2. 项目 AI_CONTEXT.md
3. 计划中当前阶段对应的 repo skill 与 interface doc

规则：
- 当前工作树已有大量用户未提交修改，禁止 git reset/checkout 覆盖；先 git status 和 git diff。
- 每次只做一个 Phase，并在该 Phase 验收通过后再进入下一阶段。
- 不改策略口径、artifact/workspace/portfolio result contract。
- 性能改动必须给出修改前后同口径数字；没有数字不算完成。
- 首页必须真实数据优先、失败空态、禁止伪造。
- 报告可以按章加载，但不能删除正文、表格、引用或附录。
- 完成路由、状态键、缓存语义或部署事实变更后，同步对应 interface doc 和 AI_CONTEXT.md。
```

## 8. 最终 Definition of Done

只有同时满足以下条件，才算真正完成：

- 冷 `import app` 降到 1 秒左右或更低
- 首页不再因为外部 API 而整页空白
- 外部失败有统一总 deadline，不出现 timeout 逐项累加
- 报告默认 DOM < 2,000，正文按章完整可达
- sidebar 参数批量提交，展示切换不触发策略重算
- 单股 stage cache、多股 workspace、导出 contract 无回归
- 本地与线上依赖版本可追踪，增量部署能处理 requirements 变化
- Playwright 冷/热数据、pytest、接口文档和验收记录齐全
- 线上部署后重新测量；不能用当前旧版线上数据代替新代码验收

## 9. 本轮不更新 `AI_CONTEXT.md` 的原因

本轮只新增诊断计划，没有改变架构、路由、状态键、部署流程或长期协作约定。实际执行 Phase 后，如果 lazy import、parallel fragment、报告 reader、依赖或部署规则落地，再由实施 AI 按项目规则更新 `AI_CONTEXT.md`。
