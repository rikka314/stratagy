# AI 快速上下文（薄路由版）

> 最近更新：2026-04-11
> 用途：项目级路由文档。先读本文件，再按任务跳到对应 skill 和接口文档。
> 约定：详细接口统一维护在 `document/interfaces/`，本文件只保存 durable project facts。

## 项目一句话

这是一个基于 Streamlit 的模块化量化策略分析应用，覆盖美股 / A 股数据加载、指标与信号生成、回测与评估、单股工作流、多股组合、离线 `model-test` 研究与 HTML 导出；线上部署在 `/strategy` 子路径。

## 关键运行事实

- 公开路径：`/strategy`、`/strategy/stock-analysis`、`/strategy/stocks-analysis`、`/strategy/model-evaluation`
- Streamlit 配置：`server.baseUrlPath = "strategy"`
- 服务器 SSH 别名：`stratagy`
- 服务器应用目录：`/opt/stratagy`
- **开发方式：SSH 远程连接**，不创建新的本地工作区；使用 VS Code / Cursor Remote-SSH 连接 `stratagy`，打开 `/opt/stratagy`
- SSH 远程开发配置指南：`deploy/ssh_remote_dev.md`
- 常用增量部署：`deploy/sync.bat`
- 常用全量上传：`deploy/upload_and_deploy.bat`
- 两个部署脚本都会在本地存在时同步 `model-test/outputs/`
- Nginx 子路径模板：`deploy/nginx_strategy.conf`

## 仓库地图

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
- `document/`
  作用：风格标准、数据 / 模型约定、接口文档、验收记录、归档。
- `plan/`
  作用：学期计划与分周执行计划。
- `model-test/`
  作用：离线单股策略批量研究工作区，包含 CLI 入口、研究配置、执行器、评分汇总与报告输出。
- `app_original.py`
  作用：重构前备份，只读，不删除。

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
- 增强层：`core/fa_filter.py`、`core/ml_filter.py`、`core/evaluation.py`、`core/portfolio.py`、`core/visualization.py`、`core/market_context.py`

## 当前 durable facts

- 单股 workflow 的 `family="regime"` 现在同时支持 legacy `dual_state_router / no_market / no_router` 和新 `adaptive_router_v1`。
- 单股页默认 regime 选项为 `adaptive_router_v1`；若最近一次离线 `regime_artifacts/` 缺失或损坏，workflow 自动降级到 legacy `dual_state_router`，并把 `PipelineRunResult.status` 标记为 `degraded`。
- `core/adaptive_regime.py` 统一维护 adaptive state 特征、状态分类器训练 / 预测、candidate state 指标聚合、路由策略选择，以及 `regime_artifacts/` 的读写。
- `model-test` Stage A 现在包含 `rsm_adaptive_v1`，会在 run 输出目录写 `regime_artifacts/`。
- 同一次研究 run 内，adaptive Stage A 会通过环境变量 `STRATAGY_ADAPTIVE_REGIME_ARTIFACT_DIR` 读取刚生成的 `regime_artifacts/`。
- `rsm_adaptive_v1` 不参加 rolling robustness；`robustness_summary.csv` 不包含它，`report.json` / `report.md` 额外包含 adaptive state / routing 摘要。
- 仓库现已包含 `reports/Final_Report.html` 作为最终提交 ZIP 的离线报告入口，`scripts/prepare_final_zip.ps1` 用于生成清理后的 `Final_gpXX.zip` 提交包。
- 站点 UI 语言现固定为英文；顶部中英切换已移除，路由不再传播 `lang` 查询参数。

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
