# AI 快速上下文（薄路由版）

> 最近更新：2026-08-11
> 用途：项目级路由文档。先读本文件，再按任务跳到对应 skill 和接口文档。
> 约定：详细接口统一维护在 `document/interfaces/`，本文件只保存 durable project facts。

## 项目一句话

这是一个基于 Streamlit 的模块化量化策略分析应用，覆盖美股 / A 股数据加载、指标与信号生成、回测与评估、单股工作流、多股组合、离线 `model-test` 研究与 HTML 导出；线上部署在 `/strategy` 子路径。

## 关键运行事实

- **本地一键启动**：Windows 使用项目根目录 `run.bat`，macOS / Linux 使用 `./run.sh`；两者都会自动创建 `.venv`、按 `requirements.txt` 指纹安装依赖并启动 Streamlit，`--setup-only` 可只做环境验收
- 公开路径：`/strategy`、`/strategy/stock-analysis`、`/strategy/stocks-analysis`、`/strategy/model-evaluation`
- 本地控制路径：`/strategy/experiment-monitor`；`run.bat` / `run.sh` 设置 `STRATAGY_RESEARCH_CONTROL=1` 时注册，生产默认不暴露
- Streamlit 配置：`server.baseUrlPath = "strategy"`
- 服务器 SSH 别名：`stratagy`
- 服务器应用目录：`/opt/stratagy`
- 常用增量部署：`deploy/sync.bat`
- 常用全量上传：`deploy/upload_and_deploy.bat`
- 两个部署脚本都会在本地存在时同步 `model-test/outputs/`
- Nginx 子路径模板：`deploy/nginx_strategy.conf`

## 仓库地图

- `run.bat`
  作用：Windows 一键安装 + 启动脚本（创建 venv → 安装依赖 → 启动 Streamlit）。
- `run.sh`
  作用：macOS / Linux 一键安装 + 启动脚本，与 `run.bat` 共享依赖指纹和本地实验监控约定。
- `app.py`
  作用：路由壳层、入口页、单股 / 多股 route state。
- `core/`
  作用：数据、指标、信号、regime、回测、评估、优化、可视化、组合、市场上下文。
- `ui/`
  作用：入口页、侧边栏、单股分析、多股分析、模型评估、共享主题、共享 HTML 导出。
- `deploy/`
  作用：部署脚本、Nginx 模板、远端 bootstrap。
- `reports/`
  作用：最终提交用离线 HTML 报告与后续导出物。
- `scripts/`
  作用：本地 setup/start 脚本、最终打包脚本、legacy i18n/fix 工具脚本。
- `document/`
  作用：风格标准、数据 / 模型约定、接口文档、验收记录、归档（含 `archive/app_original.py` 重构前备份）。
- `docs/`
  作用：README 展示资产与交付辅助文档（如架构图、因子字典）。
- `plan/`
  作用：学期计划与分周执行计划。
- `model-test/`
  作用：离线单股策略批量研究工作区，包含 CLI 入口、研究配置、执行器、评分汇总与报告输出。
- `data/`
  作用：本地样例与缓存股票 CSV 数据。
- `tests/`
  作用：Pytest 测试套件。

## 当前冻结模块边界

- 路由与页面入口：`app.py`
- 公共参数出口：`ui/sidebar.py`
- 单股策略编排：`ui/single_stock_workflow.py`
- 单股主分析页：`ui/single_stock.py`
- 多股主分析页与组合结果：`ui/multi_stock.py`
- 模型评估只读页：`ui/model_evaluation.py`
- 共享 HTML / 主题壳层：`ui/theme.py`
- 共享离线 HTML 导出 builder：`ui/export_reports.py`
- 核心数据主链：`core/data.py -> core/indicators.py -> core/signals.py -> core/backtest.py`
- Legacy Regime / RSM：`core/regime_model.py`
- Adaptive regime helper：`core/adaptive_regime.py`
- 增强层：`core/fa_filter.py`、`core/news_factor.py`、`core/ml_filter.py`、`core/evaluation.py`、`core/portfolio.py`、`core/visualization.py`、`core/market_context.py`

## 当前 durable facts

- 单股 workflow 的 `family="regime"` 现在同时支持 legacy `dual_state_router / no_market / no_router` 和新 `adaptive_router_v1`。
- 单股页默认 regime 选项为 `adaptive_router_v1`；若最近一次离线 `regime_artifacts/` 缺失或损坏，workflow 自动降级到 legacy `dual_state_router`，并把 `PipelineRunResult.status` 标记为 `degraded`。
- `core/adaptive_regime.py` 统一维护 adaptive state 特征、状态分类器训练 / 预测、candidate state 指标聚合、路由策略选择，以及 `regime_artifacts/` 的读写。
- `model-test` Stage A 现在包含 `rsm_adaptive_v1`，会在 run 输出目录写 `regime_artifacts/`。
- 同一次研究 run 内，adaptive Stage A 会通过环境变量 `STRATAGY_ADAPTIVE_REGIME_ARTIFACT_DIR` 读取刚生成的 `regime_artifacts/`。
- `rsm_adaptive_v1` 不参加 rolling robustness；`robustness_summary.csv` 不包含它，`report.json` / `report.md` 额外包含 adaptive state / routing 摘要。
- **Phase 4 rerun isolation（2026-08-08）**：sidebar 高级策略参数通过 `sidebar_strategy_parameters` form 批量提交，保持原参数 key 集合；多股权重通过 `multi_stock_portfolio_weights` form 批量提交。单股纯展示图使用 `single_stock_display_cache`，context reset 只清展示缓存，不清 workflow stage cache；多股既有 `figure_cache` / `heatmap_cache` 与组合 workspace contract 保持不变。
- **Web 性能 Phase 5（2026-08-09）**：`ui/theme.py` 的单一主题源按 selector 编译为 `base / home / entry / analysis / report` 五个 CSS bundle；`app.py` 每条真实 route 只注入 `base + 当前页面 bundle`，单股 / 多股入口态与分析态分别使用 entry / analysis。`inject_global_styles()` 仅保留兼容用途。首页实际 CSS payload 约 30.6k 字符（原完整源约 77.5k），非报告 bundle 不含 `.native-report-*`，报告 bundle 不含首页动画；移动端首页通过增加舞台垂直节奏保持标题、星图、控件和市场镜头不重叠。验收记录见 `document/acceptance/web_performance_phase_5_20260809.md`。
- **Web 性能 Phase 6（2026-08-09）**：本地 `run.bat` 与远端增量同步都以 `requirements.txt` SHA-256 指纹跳过未变化的依赖安装；全量部署写入相同指纹。`requirements.txt` 固定支持 `streamlit>=1.60.0,<1.62.0`。`deploy/check_runtime.sh` 统一输出 Python / Streamlit 版本并轮询 `/strategy/_stcore/health`；Nginx 模板把 content-hashed `/strategy/static/` 长期 immutable 缓存与 no-store、无缓冲的 `/strategy/_stcore/` 明确分离，真实主机的 HTML / JS / CSS gzip 由全局配置承载。详细 contract 见 `document/interfaces/deploy-runtime.md`。
- **Web 性能 Phase 7（2026-08-09）**：本地最终矩阵以 `156 passed` 收口，冷 `import app` p50 为 `736 ms`；首页固定壳层再次与三个 `st.fragment(parallel=True)` 数据区解耦，三次独立服务进程首访的壳层 p50 `2.235 s`、完整数据 p50 `5.859 s`，外部接口慢时页面不再空白。报告默认章为 `1424` 个 DOM 节点、约 `115.8k` 页面 HTML。功能与原始冷/热样本见 `document/acceptance/web_performance_phase_7_20260809.md`；生产未部署，发布后仍需单独复测。
- **共享图表无标题约定（2026-08-11）**：所有 Plotly 图表默认不渲染内置 `layout.title`；页面上下文标题由外层 surface 文案承载，避免图表出现重复标题或 `undefined`。
- **性能优化（W9+）**：`rolling_rank` / `rolling_percentile`（`core/indicators.py`）改用 `raw=True + numpy` 实现，比 `raw=False + pandas.rank` 快约 5-10x；`add_indicators` 在 UI 层（`ui/single_stock.py`）包装为 `@st.cache_data` cached wrapper，消除每次 slider 交互的重复计算；`get_available_stocks`（`core/utils.py`）加 `@st.cache_data(ttl=300)`，避免每次 rerun 重复扫描缓存文件目录。
- **临时分析工作区与缓存（2026-08-11）**：`core/workspace_cache.py` + `ui/workspace.py` 为无登录单机站点提供 24 小时、URL `ws` 驱动的临时工作区恢复；单股/多股 route、参数、选择、已完成策略/组合结果与上传 CSV 可跨首页、刷新和重连恢复，stage/展示图缓存不落盘。工作区单项上限 160 MiB、全局 LRU 上限 1.5 GiB；`ws` 是不可分享的短期 bearer 标识。`core/market_cache.py` 以 `market/symbol/adjust` 隔离日线磁盘缓存：24 小时 fresh、7 天 stale-while-refresh，且在 4 GiB 服务器上为 session stage/figure 与 `st.cache_data` 明确设置 LRU 上限。
- **依赖变更**：`requirements.txt` 新增 `yfinance>=0.2.0`（可选，仅在 HTML 导出时 lazy import，失败则 ticker_info 回退为空 dict）。
- 站点 UI 支持中文 / 英文双语；顶部语言切换通过 `?lang=zh` / `?lang=en` 保留当前页面，并由 `ui/i18n.py` 的 `ui_language` 会话状态与查询参数共同驱动。共享 `route_href()` 会在站内路由间继续传播当前语言。
- 单股分析页的标的身份区按当前语言切换主次名称：中文页显示“中文名 → 英文名 → 代码”，英文页显示“英文名 → 中文名 → 代码”；推荐入口会把名称写入 `route_single_state.name`，在本地股票目录暂未覆盖新标的时作为回退。
- **报告中心（2026-08-08，Web 性能 Phase 3）**：`/strategy/final-report` 由 `ui/final_report.py` 从当前 `ui_language` 对应的归档 HTML 构建缓存 reader；reader 以文件 path + `mtime_ns` 失效，完整保留原始 section、表格、引用、附录和锚点，但默认只把当前 section 注入 DOM。`final_report_active_section` 与安全 `?section=<id>` 支持章节深链接，非法 section 回退首章；`lang` 与 `section` 可共存，英中文件 ID 同构时切语言保留章节。完整目录链接会加载锚点所属章节，宽屏 rail 继续保留当前章节高亮和已有阅读 timeline。搜索改为提交式 form：输入不 rerun 全文，提交后仅显示命中章节标题/短 snippet，点击结果加载对应完整原始章节；无结果显示明确空态。仍通过共享 `render_html(..., localize=False)` 直接渲染，不使用 iframe。目录、八章正文、表格、引用和附录内容保持以归档 HTML 为唯一内容源；视觉样式由 `ui/theme.py` 的站点 token 统一接管。
- **首页视觉与新闻方向（2026-08-07）**：`ui/home.py` 固定显示“股票策略分析平台”（英文 `Stock Strategy Analysis Platform`），下方用单行小字轮换每日新闻；`NEWS_API_KEY` 配置后由 NewsAPI `/v2/everything` 服务端拉取，中文标题经 OpenCC `t2s` 统一为简体，再按日期 + 24 小时 TTL 缓存，失败时回退内置双语新闻。Windows 本机仅配置 Internet Settings 代理时，新闻请求会自动读取当前用户代理，显式 `HTTP_PROXY` / `HTTPS_PROXY` 仍优先。标题与市场镜头之间是可交互推荐股票星图：它与单股分析入口共用 `core.market_context.get_recommended_stocks()`，优先今日热搜、失败时回退实时涨幅榜，中央以公司名为主、代码和涨跌幅为辅，并通过腾讯前复权 K 线接口展示最近 20 个交易日真实 OHLC；K 线与报价均缓存 15 分钟，失败时显示明确空态，不使用默认股票池。外围位置按日期/市场/股票稳定错落并显示公司名。真实 Streamlit 按钮通过 `home_stock_focus_market` / `home_stock_focus_index` 切换美股、A 股和下一只，按钮与星图统一置于 `home-stage-shell` 相对定位容器并随页面同步滚动，移动端只保留两个外围项。下方 24 秒循环三幕市场镜头展示地区指数、同一单股推荐来源的观察项和市场温度；腾讯行情失败时只显示“待更新”，推荐观察明确不构成投资建议，低动态模式固定第一幕。原 hero、action card、showcase board 和底部说明区已移除。`ui/theme.py::render_route_nav()` 使用“左品牌 / 居中首页、单股、多股、帮助 / 右研究证据与语言”的无边界三段式 header；“浏览研究证据”固定进入 `/strategy/model-evaluation`。
- **入口页推荐来源（2026-08-07）**：`core/market_context.py` 为单股和多股入口统一提供推荐股票；A 股与美股优先按百度股市通当日综合热度排序，热搜不可用时分别降级到 A 股实时涨幅榜和知名美股实时涨幅榜，两级实时来源都失败时显示明确空态，不再使用默认股票池。单股入口标题精简为“单股策略分析”，CSV 上传要求通过轻量 popover 展示。
- **Web 性能 Phase 1（2026-08-07）**：`app.py` 只在顶层保留轻量路由壳层、主题、i18n、`core.config` 与 perf tracing；首页、单股、多股、模型评估和报告页面均通过 route wrapper 局部导入。`core/__init__.py` 改为 PEP 562 lazy compatibility facade，保留旧 `from core import ...` 和 `from core import ml_filter` 用法但不在包初始化时加载 sklearn / LightGBM / Optuna / AkShare。`core.market_context` 仅在 AkShare fallback 路径内导入 AkShare；`ui.sidebar` 仅在实时搜索输入实际渲染时导入 `st_keyup`。Phase 1 验收记录见 `document/acceptance/web_performance_phase_1_20260807.md`。
- **Web 性能 Phase 2（2026-08-07）**：首页 `render_home_page()` 先输出平台标题、新闻 / 星图 / 市场镜头 loading slot，再用 `st.fragment(parallel=True)` 分别加载新闻、推荐股票 + K 线、市场镜头；慢数据失败只替换对应 fragment，不再阻塞整页壳层。首页 NewsAPI、腾讯行情与 K 线请求使用显式 connect/read timeout，并限制 `st.cache_data` entries。`core.market_context._load_us_famous_recommendations()` 与 `build_market_context()` 改为整批总 deadline，不再按多个 future 逐项累加等待。Phase 2 依赖 `streamlit>=1.60.0,<1.62.0`，验收记录见 `document/acceptance/web_performance_phase_2_20260807.md`。
- **参数可调性（W9）**：单股 Search 模型和多股策略面板均内联了关键参数 slider（入场/出场阈值、止损/止盈、因子权重）。单股使用 `search_adj_` 前缀 key，多股使用 `multi_adj_` 前缀 key，均与 sidebar 高级设置的 key 互不冲突。单股通过 `_apply_search_adj_overrides()` 在 pipeline 调用前覆盖 `params_snapshot`；多股直接写回 `params` dict。
- **HTML 导出增强（W9+）**：单股导出新增 Stock Profile section 扩展版（代码+名称、市场+币种、数据区间、最新收盘价+涨跌、52周高/低+均量、区间总回报+年化回报、年化波动率、最大回撤）；若 `ticker_info` 由调用方提供（US 股通过 yfinance 可选获取），还额外显示行业/市值/PE/Beta/股息率/业务描述。`build_single_stock_export_html` 新增 `ticker_info: dict | None = None` 参数；`_render_single_stock_export` 在按钮点击时调用 `_fetch_ticker_info(symbol, market)` 并传入。
- **News Fusion（2026-05-26）**：单股 `family="search"` 路径新增可选 `News Fusion` stage，顺序固定为 `SM/FSM base -> optional Parameter Search -> optional News Fusion -> optional ML Filter`。`core/news_factor.py` 从 FinGPT 侧 `news_sentiment_daily.csv` 读取日频新闻因子，保留原始 `factor_score`，新增 `fused_factor_score/news_delta/news_gate/news_residual` 并重算仓位；`baseline` 和 `regime/adaptive_router_v1` 不直接接入新闻。
- **Dean's Award Gate 0（2026-08-03）**：跨窗口的 `US` / `CN_A`、执行成本和研究输出 contract 冻结在 `document/interfaces/deans-award-research-contract.md`；开发测试入口为 `requirements-dev.txt`（`pytest==8.4.1`）和 `pytest.ini`。全量基线记录在 `document/acceptance/gate_0_20260803.md`（55 passed / 5 failed / 0 skipped）；失败项按窗口归属处理，不由总控跨界修复。
- **Dean's Award Gate 1（2026-08-03）**：`MarketExecutionConfig` 已支持 US/CN_A 成本；`model-test` 通过 context-local config 将同一成本口径传至嵌套回测，并输出 `config_snapshot.json` 与 `data_manifest.json`。`smoke_us_deans_gate1.json` 和 `smoke_cn_a_deans_gate1.json` 均已生成可读报告；验收记录见 `document/acceptance/gate_1_20260803.md`。
- **Dean's Award Window 4（2026-08-09）**：`core/news_factor.py` 已冻结 US/CN_A 新闻 schema 校验、按股票交易日历滞后对齐、无新闻/零权重上游仓位回退和独立 `run_news_ablation()` API；输出遵循 `news_ablation_summary.csv` contract，零覆盖或缺失文件使用明确 `skipped` 原因。接口说明见 `document/news_sentiment_schema.md`，验收记录见 `document/acceptance/window_4_news_factor_20260809.md`。
- **Dean's Award full-run 准备（2026-08-09）**：市场推荐与 shared benchmark 已拆分，US/CN_A 分别从本市场已验证候选中选策略，共同候选只用于横向比较。标准 full tier 为每市场 60 只（1,260 日主窗口、4 个 756 日 rolling、统一 240 次搜索预算），120 只为参数冻结后的确认层；正式 config 要求 clean worktree、行情至少覆盖到 `minimum_data_end_date=2026-07-31`（旧 sample/cache 自动重拉），并把入选行情冻结到 run 的 `data_snapshot/`、在 manifest 记录 SHA-256。`model-test/preflight_research.py` 统一检查目录、依赖、预算、数据新鲜度门槛、磁盘、Git 与 LightGBM device。GPU 仅可选加速 LightGBM 路径；当前本机 LightGBM 4.7.0 wheel 为 CPU-only，`gpu/cuda` probe 会明确失败，不能静默降级。
- **Window 3B 本地 campaign（2026-08-09）**：`model-test/manage_campaign.py` 独立于 Streamlit 顺序调度 `full_us_deans_60 -> full_cn_a_deans_60 -> full_cross_market_deans_60`，状态与日志位于 `model-test/outputs/_campaigns/<campaign_id>/`。runner 支持可选 control directory、有限在途批次和退出码 `75` 的任务边界安全暂停；恢复要求相同 clean Git commit 与 config SHA-256，并复用现有 checkpoint。`/strategy/experiment-monitor` 每 2 秒展示阶段、进度、日志和 Stage A / Stage B / rolling / final 分榜。
- **美股研究基线（2026-08-11）**：`full_us_deans_60` 已完成（60 只、1,260 日主窗口、4 个 756 日 rolling、统一 240 次搜索预算），输出冻结在 `model-test/outputs/full_us_deans_60/`。策略与后续产品边界见 `document/strategy_research_baseline_us_20260811.md`：`SM+Bayesian` 是当前离线综合第一候选，但主窗口中位超额收益为负，必须持续与 `Naive` 并列展示；ML 为条件化候选，adaptive router 仅作为状态感知路由。`/strategy/model-evaluation` 会在明细证据前展示这份冻结结论；本地监控页将旧 manager failure 映射为“美股已完成 / 研究范围已冻结”。A 股与跨市场研究当前暂停，不从本结论外推。

## 默认阅读路线

| 任务类型 | 先用 skill | 再读文档 |
|---|---|---|
| 找接口 / 找调用链 / 看影响范围 | `strategy-interface-alignment` | `document/MODULE_INTERFACES.md` + 对应 `document/interfaces/*.md` |
| 前端 / 页面 / 图表 / HTML 导出 | `strategy-frontend` | `document/FRONTEND_STYLE_STANDARD.md` + `document/interfaces/frontend-contracts.md` |
| 核心策略链路 | `strategy-core-pipeline` | `document/interfaces/strategy-pipeline.md` + `document/DATA_SCHEMA.md` + `document/MODEL_INTERFACES.md` |
| 单股 workflow / artifact / stage cache | `strategy-single-stock-workflow` | `document/interfaces/single-stock-workflow.md` |
| 多股分析 / 组合 / 市场上下文 | `strategy-multi-stock` | `document/interfaces/multi-stock-portfolio.md` |
| 部署 / 子路径 / Nginx / 同步脚本 | `strategy-deploy` | `document/interfaces/deploy-runtime.md` |

## 文档索引

- `document/MODULE_INTERFACES.md`
  角色：总索引，只列模块边界、上下游和细分接口文档入口。
- `document/interfaces/frontend-contracts.md`
  角色：前端常用 contract，覆盖路由壳层、sidebar 参数、页面输入、共享 HTML 与图表接口。
- `document/interfaces/strategy-pipeline.md`
  角色：`data -> indicators -> signals -> backtest` 主链，以及 legacy / adaptive regime、FA / ML / baseline / evaluation / optimizer 的接口边界。
- `document/interfaces/single-stock-workflow.md`
  角色：`StrategyRequest / StageResult / StrategyArtifact / strategy_workspace / stage cache`，以及 adaptive regime 在单股 workflow 的接入方式。
- `document/interfaces/multi-stock-portfolio.md`
  角色：多股页、组合模拟、市场上下文、结果区与导出接口。
- `document/interfaces/deploy-runtime.md`
  角色：部署脚本、服务、子路径、Nginx 与同步流程。
- `document/interfaces/deans-award-research-contract.md`
  角色：Dean's Award 双市场枚举、成本计算、研究输出 schema 与窗口文件所有权的 Gate 0 冻结 contract。
- `model-test/docs/README.md`
  角色：离线研究 runner 的入口说明、配置约束与稳定输出物约定。
- `document/explanation/modeltest.md`
  角色：`model-test` 离线研究工作区的代码级介绍，覆盖入口、配置、任务编排、评分、输出与 adaptive router。
- `document/FRONTEND_STYLE_STANDARD.md`
  角色：W6-W8 前端统一视觉基线。
- `document/KNOWN_LIMITATIONS.md`
  角色：当前云端版本的已知限制、外部依赖与降级边界。
- `document/acceptance/`
  角色：阶段验收记录、回归结论与部署核对记录。
- `document/DATA_SCHEMA.md`
  角色：标准行情字段约定。
- `docs/factor_dictionary.md`
  角色：代码确认过的技术指标、10 因子评分、信号字段、FA / ML 特征与 UI 参数字典。
- `document/MODEL_INTERFACES.md`
  角色：`ModelResult` 统一结构。
- `AI_CONTROL.md`
  角色：面向人的 AI 使用手册。
- `document/archive/`
  角色：历史 feature note 与阶段性说明；默认不作为首次读取材料。

## 协作约定

- `AI_CONTEXT.md` 只回答“仓库有哪些区块、下一步该看哪里”，不保存细节接口表。
- `document/MODULE_INTERFACES.md` 只做总索引；详细接口统一维护在 `document/interfaces/`。
- 默认使用“最小上下文装载”：1 个 skill + 1 到 2 份接口文档；不要为了找接口先把整仓大文档读满。
- 前端 skill 维持现有视觉规则；接口说明只做增量补充，不回退 W6-W8 风格基线。
- 模糊任务优先用 `strategy-interface-alignment` 定位，再切到具体 skill。
- 如果任务涉及 adaptive regime，优先读 `document/interfaces/strategy-pipeline.md` 与 `document/interfaces/single-stock-workflow.md`。
- 如本次工作改动 durable project facts，结束时同步更新本文件。
