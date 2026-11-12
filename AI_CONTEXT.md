# AI 快速上下文（薄路由版）

> 最近更新：2026-09-15（JavaScript 前端与 Python API 已远端发布，公网接口验收通过）
> 用途：项目级路由文档。先读本文件，再按任务跳到对应 skill 和接口文档。
> 约定：详细接口统一维护在 `document/interfaces/`，本文件只保存 durable project facts。

## 最新进展 (Phase 2.5 完成 - 重大突破)

**因子系统优化 Phase 1 - 因子分层与筛选** ✅ 已完成
- ✅ 实现宏观因子模块 (`core/macro_factors.py`)：VIX、相对强度、beta、市场广度
- ✅ 实现四层因子 Pipeline (`core/factor_pipeline.py`)：趋势动量、均值回归、风险成交量、宏观相对
- ✅ 因子筛选实验验证：识别出技术因子高度同质化问题 (相关性 0.83)
- 📝 完整报告：`document/phase1_completion_report.md`

**因子系统优化 Phase 2 - 稳健权重和交互项研究（2026-08-22）** ✅ 已执行，保持 research-only
- ✅ 新增 `model-test/model_test/robust_weight_research.py`：train-only robust clipping/scaling、方向/家族预算、多目标 utility、多 seed/method、固定主效应交互消融、block bootstrap 和稳定性统计。
- ✅ 新增 `model-test/run_composite_stability_phase2.py` 与 `model-test/configs/composite_stability_phase2.json`：US 60 标的、20-day horizon、3 个 purged folds、20-day purge/embargo。
- ✅ 最终产出：2,784 weight paths、2,088 interaction rows；测试 `22 passed`。
- ⚠️ manifest 状态为 `data_quality_blocked`：6 个 symbol/fold 因 warm-up 或覆盖不足不可用（APP/HON/PLTR fold_01，RUBI 三个 fold），因此不能宣称 Phase 2 gate 通过，也不接入 production/Streamlit。
- ⚠️ 当前结果仅为 validation research diagnostic；配置只有 3 个 folds，未把 test 段纳入本轮调参或准入结论。交互项的 `permuted`/`all` ablation 已输出，但仍需独立的跨 fold utility gate 才能冻结。

**因子系统优化 Phase 2.5 - 深入优化** ✅ 已完成 🚀
- ✅ 扩展 Grid Search 允许负权重 [-2, 2]：发现 MACD 需要反向使用 (权重 -1.85)
- ✅ Bayesian Optimization 完整运行：激活 RSI (0.68) 和 volume_ratio_rank (0.72)
- ✅ 交互项测试：发现成交量×动量交互效应 (权重 -0.50)，用于风险控制
- ✅ 改进评估函数：tanh 平滑映射 + 交易成本，更接近真实交易
- 🎯 **重大突破**: Sharpe Ratio 从 0.42 提升到 **0.99** (+134%)
- 📝 完整报告：`document/phase2_5_completion_report.md`
- 💡 核心发现：
  - 负权重的必要性 (MACD 反向)
  - 多因子平衡组合 (5个因子 + 1个交互项)
  - 交互项风险控制机制 (防止追高)
  - 评估函数决定优化效果

**因子系统优化 Phase 3 - 仓位映射和执行约束（2026-08-22）** ✅ 已完成
- ✅ 新增 `model-test/model_test/position_map_research.py`：4 种仓位映射方法（quantile_5bin、dead_zone_softsign、vol_target、monotone_calibrated）
- ✅ 实现参数化执行约束：no-trade band、rebalance cadence、delta limits
- ✅ 成本敏感性分析框架：base、2x、4x 成本倍数
- ✅ 完整诊断指标体系：score/position 分布、执行统计、绩效指标
- ✅ 新增 `model-test/run_composite_stability_phase3.py` 与 `model-test/configs/composite_stability_phase3.json`
- ✅ 12 项测试全部通过：`tests/test_position_map_research.py`
- 🎯 **核心目标**：解决 Phase 1 发现的饱和问题（near_max_rate 99.56% → 目标 ≤ 90%）
- 📝 完整报告：`document/phase3_position_mapping_completion_report.md`
- 📋 快速启动：`document/PHASE3_README.md`
- ⚠️ 框架已建立，待实际 run 生成 ablation results 和通过饱和度 gate
- 🎯 下一步：实际运行 Phase 3，选择最佳 map + execution，进入 Phase 4 跨 fold 验证

**因子系统优化 Phase 4 - 跨 fold 准入测试（2026-08-22）** ✅ 框架完成
- ✅ 新增 `model-test/model_test/cross_fold_admission.py`：30+ fold 评估指标、准入判定逻辑、质量阻断机制（600+ 行）
- ✅ 新增 `model-test/run_composite_stability_phase4.py`：策略候选评估、4 个 purged folds、输出生成（350+ 行）
- ✅ 新增 `model-test/configs/composite_stability_phase4.json`：4 folds 配置（2019-2023）、准入门槛（≥75% folds）
- ✅ 18 项测试全部通过（1.56s）：`tests/test_cross_fold_admission.py`
- 🎯 **核心目标**：确认 Composite 是可重复的研究对象，而非单个样本曲线
- 📊 **评估体系**：收益（3 指标）、风险调整（3）、回撤（3）、胜率（2）、仓位暴露（5）、执行统计（4）、成本（2）、Beta（3）、分数关系（3）、质量标志（4）
- 🚪 **准入逻辑**：质量阻断 → 单 fold 门槛（Sharpe≥0.3, DD≤30%, 饱和≤90%）→ ≥3/4 folds 通过
- ✅ **已实现策略**：cash baseline、composite_only、composite_equal_weight、composite_no_interaction
- 🟡 **待实现策略**：composite_plus_trend/reversion/macro_cap/relative_strength/all_advisories、sm_reference
- 📝 完整报告：`document/phase4_completion_report.md`、`document/phase4_summary.md`
- 📋 快速启动：`document/PHASE4_README.md`
- ⚠️ 框架已完成，待 Phase 3 实际运行并选定 best map 后运行 Phase 4
- 📝 该“US 通过后复制到 CN_A”的下一步是当时的历史路线，已被下方独立完成的 CN_A Phase 1-6 记录取代。

## 项目一句话

这是一个 JavaScript（React/Vite）前端与 Python（FastAPI）后端的模块化量化策略分析应用，覆盖美股 / A 股数据加载、指标与信号生成、回测与评估、单股工作流、多股组合、离线 `model-test` 研究与 HTML 导出；部署路径为 `/strategy`。计算继续复用 `core/` 和现有 Python workflow，Streamlit 保留为兼容入口。

## 关键运行事实

- **生产发布（2026-09-15）**：`stratagy` 服务已切换为 Uvicorn，监听 `127.0.0.1:8501`；主站 Nginx 已应用 API、静态资源和 SPA 分流。公网页面、健康接口、最终报告及 10 个研究报告接口通过检查，前端文件哈希与本地构建一致。发布前备份位于 `/opt/stratagy-backups/20260915-release/`。现有上传脚本仅选择含 `report.json` 的输出目录，发布时须另行补齐全部所需 `model-test/outputs/` 证据及 `document/`；本次已用压缩包补齐。
- **导航交互（2026-09-15）**：JavaScript 桌面导航在鼠标靠近顶部或键盘聚焦时展开；窄屏/触屏常显。`RouteSlide` 按导航顺序提供左右退场/入场动画，查询参数变化不重挂页面，尊重减少动态效果设置。
- **阅读页面（2026-09-15）**：报告与研究证据共用居中的 1180px 最大宽度阅读布局；`useReadingSection` 随滚动/内容尺寸变化追踪当前报告子章节或研究章节，侧目录逐行显示并标注当前位置。报告保持按章加载，目录使用箭头展开子项。
- **本地一键启动**：Windows 使用 `run.bat`，macOS / Linux 使用 `./run.sh`；自动创建 `.venv`、按指纹安装 Python/npm 依赖、构建前端并启动 Uvicorn（默认 8501）。`--setup-only` 只安装与构建；`--legacy-streamlit` 显式回退旧页面。详见 `document/JS_FRONTEND_RUNTIME.md`。
- **新运行边界**：`frontend/src/` 负责交互与图表；`api/` 暴露 `/strategy/api` 并服务 `frontend/dist/`。单股后台任务、数据集和组合结果按不可猜测 ID 保存于服务端，默认 24 小时；浏览器仅持久化轻量状态和结果 ID，刷新恢复不自动重算。
- **迁移边界**：2026-09-13 用户明确纠正：JavaScript 迁移必须保留原 Streamlit 布局、内容、操作顺序和默认视图；gfm156.com 只参考字体与配色。不可借换框架删除图表/内容或重写为宣传页。原 `ui/` 和下文页面结构仍是对照源。
- 公开路径：`/strategy`、`/strategy/stock-analysis`、`/strategy/stocks-analysis`、`/strategy/model-evaluation`
- 本地控制路径：`/strategy/experiment-monitor`；新 API 仅在显式设置 `STRATAGY_RESEARCH_CONTROL=1` 时允许实验控制，默认关闭。
- 兼容入口 Streamlit 配置：`server.baseUrlPath = "strategy"`
- 服务器 SSH 别名：`stratagy`
- 服务器应用目录：`/opt/stratagy`
- 常用增量部署：`deploy/sync.bat`
- 常用全量上传：`deploy/upload_and_deploy.bat`
- 两个部署脚本都会在本地存在时同步 `model-test/outputs/`
- Nginx 子路径模板：`deploy/nginx_strategy.conf`；`/strategy` 到 `/strategy/` 的重定向保留查询参数，确保首页语言与临时工作区链接不丢失

## 仓库地图

- `run.bat`
  作用：Windows 一键安装、构建 JavaScript 前端、启动 Python API；可显式启动旧 Streamlit。
- `run.sh`
  作用：macOS / Linux 一键安装 + 启动脚本，与 `run.bat` 共享依赖指纹和本地实验监控约定。
- `frontend/`
  作用：React JavaScript 页面、路由、双语主题、Plotly 图表；字体本地打包，Plotly 按需加载。
- `api/`
  作用：FastAPI 路由、任务状态隔离、服务端结果持久化、数据校验、研究目录、诊断和离线 HTML 导出。
- `app.py`
  作用：保留的 Streamlit 路由壳层与兼容入口。
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
- `research/`
  作用：冻结研究的 canonical navigation/provenance 层；按时间线记录各实验线的研究问题、流程、gate、结论、局限、源文件和 `model-test/outputs/` 证据路径。缺失 Git-ignored 输出显式标记为 pending/unavailable，不替代或修改 Streamlit runtime。
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
- **多股数据缓存隔离（2026-08-13）**：`ui/multi_stock.py` 的分析数据签名包含上传字节摘要、session-local 行情刷新代次与每个市场标的的磁盘缓存版本 token；同名同长度上传内容、侧边栏手动刷新，或 stale-while-refresh 后台成功写入行情，都会在下一次 rerun 使旧 DataFrame 缓存失效。组合策略签名使用实际 OHLCV fingerprint，历史行情修订也不会误复用旧组合结果。
- **性能优化（W9+）**：`rolling_rank` / `rolling_percentile`（`core/indicators.py`）改用 `raw=True + numpy` 实现，比 `raw=False + pandas.rank` 快约 5-10x；`add_indicators` 在 UI 层（`ui/single_stock.py`）包装为 `@st.cache_data` cached wrapper，消除每次 slider 交互的重复计算；`get_available_stocks`（`core/utils.py`）加 `@st.cache_data(ttl=300)`，避免每次 rerun 重复扫描缓存文件目录。
- **临时分析工作区与缓存（2026-08-13）**：`core/workspace_cache.py` + `ui/workspace.py` 为无登录单机站点提供 24 小时、URL `ws` 驱动的临时工作区恢复；单股/多股 route、参数、选择、已完成策略/组合结果与上传 CSV 可跨首页、刷新和重连恢复，stage/展示图缓存不落盘。工作区单项上限 160 MiB、全局 LRU 上限 1.5 GiB；checkpoint 先比较轻量 marker，未变化的 rerun 不再重复深拷贝/写入完整结果，且恢复快照会排除 Streamlit 一次性 button/action widget key（单股标的搜索文本仍持久化），避免重连后页面异常；`ws` 是不可分享的短期 bearer 标识。`core/market_cache.py` 以 `market/symbol/adjust` 隔离日线磁盘缓存：24 小时 fresh、7 天 stale-while-refresh，发布数据与 metadata 同步受锁保护并提供轻量版本 token；fresh/stale 命中不显示加载 spinner，侧边栏手动刷新会更新同一磁盘缓存键，策略 context key 同时包含输入数据 fingerprint，且在 4 GiB 服务器上为 session stage/figure 与 `st.cache_data` 明确设置 LRU 上限。
- **前端交互稳定性（2026-08-23）**：单股 / 多股路由不再写入或渲染工作区恢复提示横幅；入口到分析页在同一 rerun 中替换，分析数据加载关闭嵌套 Streamlit spinner，并保留唯一轻量 loading 状态。普通 widget rerun 期间，基础主题保留 stale 树的上一帧并禁用其交互，避免整页先消失再重绘；仅入口到分析页的 route loading 会定向隐藏旧入口 surface，避免重复 CSV 控件。工作区侧栏的“开始新的临时分析”操作仍保留。
- **依赖变更**：`requirements.txt` 新增 `yfinance>=0.2.0`（可选，仅在 HTML 导出时 lazy import，失败则 ticker_info 回退为空 dict）。
- 站点 UI 支持中文 / 英文双语；顶部语言切换通过 `?lang=zh` / `?lang=en` 保留当前页面，并由 `ui/i18n.py` 的 `ui_language` 会话状态与查询参数共同驱动。共享 `route_href()` 会在站内路由间继续传播当前语言。
- 单股分析页的标的身份区按当前语言切换主次名称：中文页显示“中文名 → 英文名 → 代码”，英文页显示“英文名 → 中文名 → 代码”；推荐入口会把名称写入 `route_single_state.name`，在本地股票目录暂未覆盖新标的时作为回退。
- **报告中心（2026-08-23，帮助内容与目录交互刷新；Web 性能 Phase 3）**：`/strategy/final-report` 由 `ui/final_report.py` 从当前 `ui_language` 对应的归档 HTML 构建缓存 reader；reader 以文件 path + `mtime_ns` 失效，完整保留原始 section、表格、引用、附录和锚点，但默认只把当前 section 注入 DOM。`final_report_active_section` 与安全 `?section=<id>` 支持章节深链接，非法 section 回退首章；`lang` 与 `section` 可共存，英中文件 ID 同构时切语言保留章节。网页端从归档 TOC 重建“＋”触发的原生单开 popover，子项改为无 marker 列表；同章 TOC / 宽屏 rail 使用纯 hash 直接滚动，跨章链接保留所属 section 与 fragment，并在新章节挂载后通过默认禁用、仅本地可信脚本显式开启的 `render_html(..., unsafe_allow_javascript=True)` 桥恢复滚动与焦点。搜索采用提交式 form：输入不 rerun 全文，提交后仅显示命中章节标题/短 snippet，点击结果加载对应完整原始章节；无结果显示明确空态。报告不使用 iframe；目录、八章正文、表格和附录仍以双语 HTML 为唯一内容源，视觉由 `ui/theme.py` 的站点 token 统一接管。
- **研究证据浏览器（2026-08-23）**：`/strategy/model-evaluation` 默认读取 `research/RESEARCH_CATALOG.json` 与各实验 README，按 catalog 顺序形成不显示日期的可点击两排研究流程图、直接复用报告中心 `.report-scroll-rail` 的帮助式左侧目录和章节锚点；点击流程图或左侧目录会通过 `?experiment=<id>#research-<id>` 重载并聚焦对应章节。正文按目录连续展开，以轻分隔和无卡片的阅读排版展示，不再额外维护选择器/折叠卡片。`ui/research_browser.py` 同时读取已存在的 `model-test/outputs/` CSV/JSON 生成可复核图表和证据账本。研究标题、摘要、计划、流程、决策、结果、gate 与问题提供中文/英文阅读版本，指标和中文叙述也可搜索。缺失 Git-ignored 输出只显示 `pending/unavailable`，不补零、不推断、不把研究准入写成生产就绪；旧版 run reader 保留给兼容测试和显式非默认输出目录。
- **滚动演示文档（2026-08-23）**：`reports/Strategy_Research_Story_zh.html` 是可离线打开的双幕单页项目演示，开场展示作者提供的 YINCE 品牌板 `reports/strategy-story-assets/brand/yince-brand-board.png`；右上角小型播放键按 `reports/Strategy_Research_Story_Autoplay_Cue_Sheet_zh.md` 的 300 秒口播时间轴驱动稳定 DOM 场景，镜头以 0.8–1.8 秒快速转场和长时间定点停留为主，图表讲解段会优先停住并在段首或段尾快速换页。播放支持开始、暂停、继续与重播，滚轮/触摸/页面交互/导航键及切到后台会暂停，reduced-motion 下改为离散场景切换。第一幕介绍首页、单股、多股与研究证据入口，并为五段真实操作录屏预留 `reports/strategy-story-assets/video/*.mp4`；第二幕依据作者研究总结，以第一人称串联复杂模型、Transformer STOP、五因子 Composite、持仓饱和与 Advisor 再验证，“当前”阶段记录与 Composite 段落对齐。页面当前展示六张由 `scripts/build_strategy_story_assets.py` 从冻结 CSV / JSON 重复生成的核心图；`chart_manifest.json` 继续记录完整生成资产的市场、状态、源路径与摘要哈希。缺失源保持 UNAVAILABLE，不补零或跨市场代换。页面保留滚动进度、响应式布局、原生视频暂停和 reduced-motion 海报降级。
- **作品展海报（2026-08-23）**：`assets/banners/yince-exhibition/yince-exhibition-poster.html` 是 YINCE 智能量化策略分析平台的单页作品展海报源文件，整合作者信息、核心创意、网站四类入口、数据到证据的实现链、冻结研究历程与主要成果，并明确保留 pooled 比较、覆盖不完全配对和 Advisor 待真实数据 gate 的边界。最终交付包括 4200×5700 数字 PNG、轻量预览图、42.6×57.6 cm / 3 mm bleed 的 RGB vector PDF，以及 300 dpi CMYK print PDF；二维码指向公开 `/strategy/` 站点。
- **股票入口与搜索（2026-09-13）**：按用户要求，单股入口与多股入口统一标题、数据设置、左右分栏与市场快照样式。两页共用 `StockSearch`：空查询不请求/不显示结果，260ms 防抖，结果浮层自动向上或向下展示；支持方向键/Enter、Esc、外点关闭，避免结果撑开页面。单股 CSV 上传同样应用入口日期筛选及复权元数据。
- **JavaScript 页面留白（2026-09-13）**：共用 `--page-gutter` 控制桌面 54px / ≤980px 时 24px 的左右留白；多股页面宽度显式扣除两侧留白后再应用 1500px 最大宽度与自动居中，避免窗口缩放后内容贴边。
- **JavaScript 品牌展示（2026-09-13）**：导航 Logo 与 favicon 共用 `frontend/public/yince-logo-white.png`，以原 YINCE 汇聚图形为基础，简化为白底、黑色曲线和单个陶土色焦点；原品牌板与旧图标保留；首页标题使用 600 字重。按用户标注移除市场镜头底部来源说明行，避免不同比例下遮挡。
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
- **市场专属 full-run 基线（2026-08-17）**：`full_us_deans_60` 与 `full_cn_a_deans_60` 均已完成 60 标的、1,260 日主窗口、4 个 rolling、统一 240 搜索预算的冻结研究。CN_A snapshot 为 60 个 CSV、23,520,695 bytes，aggregate SHA-256 `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`；source manifest 为 `f46e4d677bbd051e91b27fd07625fa87f3b98ea9af45b28d67d4ef066e1d1aa`。两市场的证据仍必须独立解读，下一步才是 W11 admission comparison；不得从任一市场外推跨市场结论。
- **Post-Gate-2 动态专家组合 Phase A（2026-08-12）**：`document/interfaces/dynamic-ensemble-research.md` 冻结 US / CN_A 分市场训练、20 日主预测周期、5/60 日消融、已扣费 `strategy_return` 不重复扣成本、6–8 个代表专家与 `best_single_expert / equal_weight_experts / adaptive_router_v1` 三项对照。`model-test/configs/moe_baseline_{us,cn_a}.json` 为唯一配置入口，`model-test/prepare_moe_baseline.py` 校验 Window 3B / full-run 的 config、code version、seed、数据 SHA-256 和逐日 artifact 后生成 Phase-A manifest 与结果；缺失源输出保持 `pending`。CN_A adaptive router 在市场原生 artifact 出现前固定为显式 unavailable。
- **Post-Gate-2 动态专家组合 Phase B（2026-08-12）**：`model-test/model_test/expert_panel.py` 与 `prepare_expert_panel.py` 在 Phase-A source lock 下生成 `expert_day_panel.parquet`、purged walk-forward + 至少一个 20 日 horizon embargo 的 splits、quality report 和 lineage manifest；future label 只使用后续完整 20 日的已扣费 `strategy_return`，不重复扣成本。失败 / 缺失专家和 CN_A adaptive router 保留 `expert_status=unavailable`，可选新闻因子严格按前一完成交易日对齐；source runner 额外导出 `daily.csv` 供 target position / turnover 审计。Phase B 仍只存在于 `model-test`，未接入线上 workflow。
- **Post-Gate-2 动态专家组合 Phase C（2026-08-17）**：`model-test/model_test/dynamic_ensemble.py` 与 `run_dynamic_ensemble.py` 只消费 ready Phase-A/B source lock，以 LightGBM 长表（`expert_id` 分类特征）分别进行 no-state / regime-aware purged walk-forward soft-gating，并与 `best_single_expert / equal_weight_experts / adaptive_router_v1` 对照。CN_A W10 Phase C 已完成，manifest `06f7c3a7b9ebbdc8f3abcf0c9add8dfc70f6503e3884151578a20b6587203067`，所有 5 个 artifact 哈希匹配；Cash 必须可用，非 Cash 专家上限 40%，缺失专家重归一化、指数平滑和 fallback 原因均可追溯。Phase-B 默认验证/测试段为 40 个交易日，以容纳完整 20 日标签，purge/embargo 保持 20 日。US/CN_A 均保持 research-only，未接入线上 workflow。
- **Post-Gate-2 动态专家组合 Phase D（2026-08-17）**：`model-test/model_test/dynamic_ensemble_v2.py` 与 `run_dynamic_ensemble_v2.py` 在相同市场的 ready Phase-A/B panel 和 hash-verified Phase-C output 上，针对 no-state / regime-aware 两种 v2 gate 训练 lower-quantile / median LightGBM，并以 `median - gamma * abs(median - lower)` 形成保守分数。CN_A W10 Phase D 已完成，manifest `c85d67e86323b4b5850e1527c3f50144d14cc2e5207ae05d76ae893282025d42`，8 个 artifact 哈希匹配；逐日 artifact 可回溯不确定性、fold-train numeric OOD、Cash / equal-weight / adaptive-router 降级、最大权重变化、等权标的聚合换手、最小 expert-mix 持续期和 pre-decision drawdown 风险缩放。Phase D 仍只在 `model-test`，不接入 Streamlit；CN_A adaptive router 保持显式 unavailable。
- **Post-Gate-2 动态专家组合 Phase E（2026-08-17）**：`model-test/model_test/dynamic_ensemble_online.py` 与 `run_dynamic_ensemble_online.py` 以市场匹配、hash-verified 的 ready Phase-D 权重初始化，使用 Phase-B 已扣费 `strategy_return` 的下一时点完整专家反馈，回放 Soft-MoE、Hedge 与 EG。CN_A W10 Phase E 已完成，manifest `63b8061b0ad8c69ec730f5807ff35dfb412bbfc2086cf5f8dbbd12f626b311e3`，5 个 artifact 哈希匹配；固定/波动率自适应学习率和遗忘因子均以测试窗口首日的冻结权重开始，Cash 必须存在，缺失专家转入 Cash，普通更新受 40% 单风险专家上限和 15% 单日权重变化上限约束。固定中点漂移响应仅作评估、绝不回灌更新；仍只在 `model-test`，未接入 Streamlit。
- **Post-Gate-2 动态专家组合 Phase F（2026-08-17）**：`model-test/model_test/dynamic_ensemble_bandit.py` 与 `run_dynamic_ensemble_bandit.py` 只消费同市场、hash-verified 的 ready Phase-E allocations，并重验相同 Phase-A/B panel lock。CN_A W10 Phase F 已完成，manifest `ecc72154f79414bf4469612843006829ee1e65345218fcfff835f4e0c9d8174c`，7 个 artifact 哈希匹配。每个已受 Phase-E simplex / 风险专家上限约束的 allocation 是一个 action，Cash 永远可选；LinUCB 与 contextual Thompson Sampling 从配置的 Phase-B 时点特征选择 action，且只在当天全部决策写出后批量消费所选 action 的下一时点净收益，避免跨标的同日泄漏。未选 action 收益不会出现在 decision trace 或学习状态，只能用于 `evaluation_only` 漂移恢复测量；`strategy_return` 不重复扣费，action-switch cost 默认 0。结果仍为 research-only ablation，未接入 Streamlit。
- **Post-Gate-2 v1 W11/W12（2026-08-18）**：`plan/post_gate2_model_upgrade_v1_execution.md` 是后续研究与产品 shadow mode 的唯一跨窗口执行手册。新的 admission-only output chain 未覆盖 W10：US/CN_A 的 Phase A–F 均为 ready、hash-verified，Phase-B 有 4 个 test split（purge/embargo 均为 20）。CN_A admission replay 复用权威 `full_cn_a_deans_60` 的 60 个冻结 CSV（snapshot `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`），并生成 market-native `rsm_adaptive_v1`（main 60/60 success）；未使用 US/SPY artifact。W11 以 Phase-D `moe_v2_regime_aware` 和同口径 target-position turnover 完成严格比较：US 仅 1/4、CN_A 仅 2/4 总收益不劣于各自 adaptive control，虽然两市场的最大回撤和 `<=1.25x` 换手均通过，仍未达到冻结的 3/4 门槛。W12 因没有市场通过而 `blocked`，没有 shadow mode、Streamlit 接入或默认策略改动；验收记录为 `document/acceptance/post_gate2_model_upgrade_w11_w12_20260817.md`。
- **Post-Gate-2 Transformer 状态匹配 v2 W13-W18（2026-08-20）**：US 已在不覆盖 admission/full-run source 的前提下补齐并验证 `60×7=420` 份冻结专家 exact-daily 和 60 份 adaptive exact-daily；`.venv` 使用可选研究依赖 PyTorch `2.13.0+cpu`。`run_transformer_state.py --stage all` 已完成四折 W13–W18：memory `6,989×15`、三阈值 decisions `11,520×44`、严格五日 daily audit `57,600×51`、summary `5,760×29`，所有 manifest/code/source/fold/snapshot hashes、换手与 summary 重建均通过，W18 evidence 为 `ready`。primary `state_match_balanced` 四折 matched coverage 均为 `0%`，低于冻结 `30%`，因此 W20 不准入，不能宣称 Transformer 有效，也不接入 Streamlit；W19 CN_A 仍 pending。正式记录见 `document/acceptance/post_gate2_transformer_state_w16_w18_20260820.md`。
- **Transformer State v3 Phase 1 baseline（2026-08-20）**：B01 单日 PCA、B02 20 日摘要 PCA、B03 随机邻居已在冻结 US v2 panel 的 Validation roles 上完成 `3×4` method-fold run；v2 panel manifest SHA-256 保持 `bc791ff9a0fec54d049d6514ad6e890ac9f1bd72d146c05830af3e72632802b0`，v3 独立 evidence 封存 76 个 artifact。对重复 split signature 去重后的 1,000 次 validation-date cluster bootstrap 显示，B01/B02 的完整八专家 utility consistency 均显著优于随机（差值 `+0.017500 / +0.020940`，单侧 `p=0.000999`），正式 Phase 1 停止条件未触发；但 query-selected utility 相对随机为 `-0.003283 / -0.005354`，没有检索价值证据。因此只准入 Phase 2 label/stride 重构诊断，Phase 3 训练前必须通过预声明的 query utility/regret gate；不改 production / Streamlit。正式记录见 `document/acceptance/transformer_state_v3_phase1_baselines_20260820.md`。
- **Transformer State v3 Phase 2 诊断（2026-08-20）**：D01 诊断基于 Phase 1 baseline 结果完成，发现核心分化模式：PCA 检索改善邻居一致性（+0.018 to +0.021, p<0.001）但显著恶化 query utility（-0.003 to -0.005, p>0.98），regret 增加 15-16%。诊断结论：状态相似性不预测专家 utility，检索到的邻居更一致但一致地更差。Phase 2 决策为 **STOP**，不进入 Phase 3 Transformer 训练；L01（完整 utility 向量）和 S01（stride 采样）条件不满足，未执行。Phase 3-6 全部不执行。研究在 Phase 2 正式终止，生产系统无变更，`adaptive_router_v1` 保持默认策略。完整诊断见 `document/phase1_diagnostic_report.md`，路线图终止状态见 `document/transformer_state_v3_implementation_roadmap.md`，Phase 2 完成总结见 `document/transformer_state_v3_phase2_completion.md`。
- **CN_A Factor Composite Phase 1（2026-08-22）**：新增 `core/market_factor_context.py` 的 `MarketFactorContext` 与显式 benchmark/context builder；`core/macro_factors.py`、`core/factor_pipeline.py` 支持 market-aware 调用。US 两参数 legacy path 和历史 `MacroFactors.compute(date, stock_data, stock_symbol=None)`、`compute_batch_panel(stock_data, dates)` 均保持可用；CN_A 必须显式提供 context 或 benchmark/universe frame，禁止隐式读取 SPY/VIX，CN_A 输出使用 `market_*` / `rel_strength_market` 命名且不暴露 US-only 中间列。新增 explicit-benchmark breadth、US artifact isolation、universe validation 和 unavailable-breadth 覆盖，聚焦测试 32 项通过；仍为 research-only，Phase 2 才构建并验证 CN_A market factors。
- **CN_A Factor Composite Phase 2（2026-08-23）**：✅ 已完成。`core/cn_a_market_factors.py` 实现 CN_A 市场原生因子：benchmark returns/volatility、market volatility level 与 regime（low/medium/high）、relative strength、market beta、breadth（基于 frozen universe）、CN_A tradability status（停牌、涨停、跌停检测）。22 项单元测试全部通过（`tests/test_cn_a_market_factors.py`），验证数据隔离（不读取 SPY/VIX）、命名规范（market_* 而非 vix_*）、PIT 合规（无未来数据泄漏）。Benchmark 使用 frozen universe equal-weight fallback（000300 当前 unavailable）。所有因子输出字段明确来源，sector 当前标记 unavailable。Phase 2 未触发停止门，准入 Phase 3。记录见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase2.md`。
- **CN_A Factor Composite Phase 3（2026-08-23）**：✅ 已完成。`model-test/model_test/cn_a_factor_panel.py` 实现 CN_A factor panel 构建：包含 10 个技术因子和 13 个市场因子的完整元数据注册表、panel 构建、质量验证和产物保存；`model-test/configs/composite_cn_a.json` 是配置入口，`model-test/build_cn_a_factor_panel.py` 是 CLI 工具。15 项测试全部通过（`tests/test_cn_a_factor_panel.py`）。Panel 输出包括 factor panel parquet、manifest、quality report、factor schema 与 source lineage，并以 SHA-256 保持可追溯。实际运行生成 267,162 rows，技术因子平均缺失 1.94%，市场因子平均缺失 0.19%。记录见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase3.md`。
- **CN_A Factor Composite Phase 4（2026-08-23）**：✅ **已完成并成功通过当前 research gate**。初始随机噪声目标是无效研究输入，随后改为真实 20-day forward returns。`core/composite_cn_a.py` 提供不可变 weights/decision、long-only 映射与 Ridge/Lasso/ElasticNet 拟合 API；但冻结 runner 明确只选择 10 个技术因子并使用 Ridge（`alpha=1.0`），`composite_weights_by_fold.json` 也仅含这 10 个权重。因此 **0.5972 Sharpe 不能归因于 panel 中另外 13 个 market-native 因子**。冻结 pooled 结果为 Composite 0.5972、SM 0.5277、FSM 0.4984，平均最大回撤 -54.81% / -74.07% / -64.50%，共 60 个 Composite symbol-fold 结果（3 folds × 20 symbols）。当前权重 artifact 中 RSI 为正、MACD 三折均为正、BB position 符号不稳定，不能据此写成稳定均值回归模式。记录见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase4_fixed.md`。当前只能给出 CN_A pooled research 排名，不能写成 production 推荐。

**CN_A Factor Composite Phase 5（2026-08-23）**：✅ **框架完成，待实际运行**。`core/composite_advisory_cn_a.py` 实现不可变 advisory decision、long-only 语义、4 种 advisory 规则和显式 fallback；`model-test/run_cn_a_composite_advisory.py` 实现 7 种 policy 的 ablation runner 与 gate 检查。29 项单元测试全部通过（`tests/test_composite_advisory_cn_a.py`）。**关键设计**：Composite 拥有方向，advisory 只维持或减少；advisory 行缺少/无效 base input 时显式回退现金；CN_A 主 Composite 的市场 context 缺失则 fail-closed / unavailable；不跨市场共享权重。**Phase 5 状态**：`phase5_framework_complete`，实际运行级 gate 仍需真实数据验证。记录见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase5.md`。

**CN_A Factor Composite Phase 6（2026-08-23）**：✅ **按当前 pooled runner 通过 research gate**。比较产物含 3 个模型、4 个配置 fold ID、100 个汇总源行。Composite Sharpe 0.5972，高于 SM 0.5277（+13.2%）和 FSM 0.4984（+19.8%）；平均最大回撤为 -54.81% / -74.07% / -64.50%，Composite 的 Sharpe≥0.3 symbol-fold 一致性为 76.7%（46/60）。实际覆盖不完全配对：Composite 为 60 行、覆盖 fold_01–fold_03；SM 与 FSM 各 20 行、覆盖 fold_00–fold_03，因此这是 pooled directional comparison。Phase 6 源表只含 return、Sharpe、最大回撤、win rate、n_days 与标识列；`turnover_mean=0` 是缺少 `avg_turnover` 时的默认值，不能作为零换手证据，且本表不单独验证成本敏感性或 fallback。记录见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase6.md`。结果为 research-only，不能外推 US；advisory 尚未实际运行。

**Composite Stability Phase 5 路线图（2026-08-23 更新）**：Phase 0-6 ✅ 已完成；Phase 6 pooled comparison 显示 **Composite 在当前 CN_A 汇总证据中排名第一**（Sharpe 0.5972，symbol-fold consistency 46/60），可进入独立的 Phase 7 production review。关键发现是：真实 forward returns 下的 10 技术因子 Ridge Composite 在当前 pooled 样本中排名领先；13 个 market-native panel 因子尚未进入该冻结 fit，不能把优势归因于它们。由于 Composite 与 SM/FSM 覆盖并不完全配对，这也不是跨 universe 或 production 优越性证明。路线图见 `research/03_composite_only_cn_a/plans/composite_stability_phase5_completion_report.md`，Phase 4 修复记录见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase4_fixed.md`，Phase 6 比较见 `research/03_composite_only_cn_a/plans/cn_a_factor_composite_phase6.md`。

## 默认阅读路线

| 任务类型 | 先用 skill | 再读文档 |
|---|---|---|
| 找接口 / 找调用链 / 看影响范围 | `strategy-interface-alignment` | `document/MODULE_INTERFACES.md` + 对应 `document/interfaces/*.md` |
| 前端 / 页面 / 图表 / HTML 导出 | `strategy-frontend` | `document/FRONTEND_STYLE_STANDARD.md` + `document/interfaces/frontend-contracts.md` |
| 核心策略链路 | `strategy-core-pipeline` | `document/interfaces/strategy-pipeline.md` + `document/DATA_SCHEMA.md` + `document/MODEL_INTERFACES.md` |
| 动态专家组合研究 | `strategy-core-pipeline` | `document/interfaces/dynamic-ensemble-research.md` + `document/interfaces/strategy-pipeline.md` |
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
- `document/interfaces/dynamic-ensemble-research.md`
  角色：Post-Gate-2 动态专家组合的市场隔离、收益成本、专家池、三项基线、source-lock manifest、Phase-B 面板、Phase-C gating 与 Phase-D 不确定性 / 风险边界。
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
- `research/README.md`、`research/RESEARCH_CATALOG.md`、`research/RESEARCH_CATALOG.json`
  角色：按时间线排列的冻结研究线结论先行导航、机器可读 provenance catalog 和证据状态规则；研究证据页直接消费该目录。
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
