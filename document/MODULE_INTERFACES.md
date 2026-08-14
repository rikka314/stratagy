# 模块接口索引

> 最近更新：2026-08-12
> 用途：作为总索引，告诉你“该去哪里找接口”，而不是在这里堆详细函数签名。

## 使用方式

1. 先判断任务落在哪个上下文边界。
2. 读取对应 skill。
3. 只补读对应的 `document/interfaces/*.md`。
4. 只有跨域任务，才继续扩展到相邻域文档。

如果任务本身只是“这个功能的接口在哪 / 会影响谁 / 应该交给哪个 skill”，优先使用 `strategy-interface-alignment`。

## 共享约定

| 文档 | 角色 |
|---|---|
| `document/DATA_SCHEMA.md` | 标准行情数据列与元数据约定 |
| `document/MODEL_INTERFACES.md` | `ModelResult` 统一结构 |
| `document/FRONTEND_STYLE_STANDARD.md` | W6-W8 前端唯一视觉基线 |
| `AI_CONTEXT.md` | 项目地图、入口、部署事实、协作约定 |

## 分域索引

| 领域 | 主要文件 | 上游输入 | 下游消费者 | 详细接口文档 | 推荐 skill |
|---|---|---|---|---|---|
| 前端壳层与导出 | `app.py`、`ui/theme.py`、`ui/export_reports.py`、`ui/sidebar.py`、`ui/home.py`、`ui/single_stock.py`、`ui/multi_stock.py`、`core/visualization.py` | route state、sidebar 参数、workflow/artifact、portfolio result | 首页、入口页、分析页、HTML 导出 | `document/interfaces/frontend-contracts.md` | `strategy-frontend` |
| 核心策略链路 | `core/data.py`、`core/indicators.py`、`core/signals.py`、`core/regime_model.py`、`core/backtest.py`、`core/fa_filter.py`、`core/ml_filter.py`、`core/baselines.py`、`core/evaluation.py`、`core/optimizer.py` | 行情数据、标准参数、训练/测试切分 | 单股 workflow、多股组合、评估与图表 | `document/interfaces/strategy-pipeline.md` | `strategy-core-pipeline` |
| 动态专家组合研究 | `model-test/model_test/moe_baseline.py`、`model-test/model_test/expert_panel.py`、`model-test/prepare_moe_baseline.py`、`model-test/prepare_expert_panel.py`、`model-test/configs/moe_baseline_*.json` | 冻结 Window 3B / full-run 输出、逐日净收益 artifact 与无泄漏专家面板 | Phase-A 三项对照、source-lock manifest；Phase-B `expert_day_panel`、purged walk-forward splits 与质量报告；后续 Phase C gating | `document/interfaces/dynamic-ensemble-research.md` | `strategy-core-pipeline` |
| 单股 workflow | `ui/single_stock_workflow.py`、`ui/single_stock.py` | sidebar 参数、核心策略链输出、`ModelResult` | `current_artifact`、`saved_artifacts`、比较区、Walk-Forward、单股导出 | `document/interfaces/single-stock-workflow.md` | `strategy-single-stock-workflow` |
| 多股与组合 | `ui/multi_stock.py`、`core/portfolio.py`、`core/market_context.py`、`core/visualization.py` | route state、sidebar 参数、股票池数据、权重 | 多股结果区、组合 KPI、周期热图、导出 | `document/interfaces/multi-stock-portfolio.md` | `strategy-multi-stock` |
| 部署与运行时 | `.streamlit/config.toml`、`deploy/deploy.sh`、`deploy/sync.bat`、`deploy/upload_and_deploy.bat`、`deploy/nginx_strategy.conf` | 公开路由、远端目录、服务名 | 线上站点、systemd、Nginx 子路径代理 | `document/interfaces/deploy-runtime.md` | `strategy-deploy` |

## 典型任务的最小读取路径

- 改首页、入口页、分析页布局：
  读 `strategy-frontend` + `document/interfaces/frontend-contracts.md`
- 改 sidebar 参数或页面入参：
  读 `document/interfaces/frontend-contracts.md`，必要时再补 `document/interfaces/strategy-pipeline.md`
- 改单股 artifact / stage cache / lineage：
  读 `strategy-single-stock-workflow` + `document/interfaces/single-stock-workflow.md`
- 改多股组合生成或结果区：
  读 `strategy-multi-stock` + `document/interfaces/multi-stock-portfolio.md`
- 改数据、信号、回测、评估：
  读 `strategy-core-pipeline` + `document/interfaces/strategy-pipeline.md`
- 改动态专家组合研究 contract、基线或后续门控输入：
  读 `strategy-core-pipeline` + `document/interfaces/dynamic-ensemble-research.md`
- 改子路径、部署脚本、服务：
  读 `strategy-deploy` + `document/interfaces/deploy-runtime.md`

## 修改规则

- 改路由、页面状态键或 sidebar 返回结构：
  同步更新 `document/interfaces/frontend-contracts.md`
- 改核心数据链、信号输出或评估结构：
  同步更新 `document/interfaces/strategy-pipeline.md`
- 改动态专家池、预测周期、收益口径、研究对照或 source-lock 输出：
  同步更新 `document/interfaces/dynamic-ensemble-research.md`
- 改单股 request / artifact / workspace / stage cache：
  同步更新 `document/interfaces/single-stock-workflow.md`
- 改多股 workspace / portfolio result / market context：
  同步更新 `document/interfaces/multi-stock-portfolio.md`
- 改部署路径、服务名、上传清单、Nginx 规则：
  同步更新 `document/interfaces/deploy-runtime.md`
