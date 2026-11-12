# stratagy 课程设计报告分析注记

## 证据优先级

1. `AI_CONTEXT.md`：架构、模块边界、路由、部署与实验状态的项目级事实源。
2. 当前源码：`app.py`、`core/`、`ui/` 与 `model-test/`。
3. 当前测试：`tests/` 与 fresh pytest 输出。
4. 冻结研究与历史验收：`research/`、`document/acceptance/`、`reports/`。

## 建议引用的核心代码位置

- `app.py`：搜索 `_render_home_route`、`_render_single_stock_route`、`_render_multi_stock_route`、`_render_model_evaluation_route`，用于路由壳层代码段。
- `core/data.py`：搜索 `load_stock_data` 与 market/symbol normalization，作为数据加载模块。
- `core/indicators.py`：搜索 `rolling_rank`、`rolling_percentile`、`add_indicators`，作为指标计算与性能优化代码。
- `core/signals.py`：搜索主信号生成函数与 entry/exit/hold 状态，作为信号算法代码。
- `core/backtest.py`：搜索 `simulate_strategy`、`extract_trades`，作为亮点代码（成本、交易与净值闭环）。
- `core/evaluation.py`：搜索 Sharpe、max drawdown、win rate、turnover，作为绩效评估代码。
- `core/adaptive_regime.py`：搜索 state feature、classifier、routing policy 与 artifact 读写，作为难点代码。
- `ui/single_stock_workflow.py`：搜索 `StrategyRequest`、`StageResult`、`StrategyArtifact`、`PipelineRunResult` 与 degraded fallback，作为亮点/难点代码。
- `core/factor_pipeline.py`：搜索四层 factor family 及聚合入口，作为因子管线代码。
- `core/cn_a_market_factors.py`：搜索 breadth、beta、relative strength、tradability，作为 CN_A 市场因子难点代码。
- `core/composite_cn_a.py`：搜索 Ridge fit、frozen weights 与 position mapping，作为组合模型代码。
- `model-test/model_test/position_map_research.py`：搜索四类映射、no-trade band 与 rebalance cadence，作为执行约束代码。
- `model-test/model_test/cross_fold_admission.py`：搜索 quality block 与 admission threshold，作为研究准入代码。
- `core/portfolio.py`：搜索 portfolio simulation 与 Bayesian optimization，作为多股组合代码。
- `core/workspace_cache.py`、`core/market_cache.py`：搜索 snapshot、LRU、fresh/stale，作为缓存与可靠性代码。
- `ui/export_reports.py`、`ui/final_report.py`：搜索 HTML builder、TOC、search、anchor，作为离线报告与阅读器代码。

正式生成大纲前，用 `rg -n "<symbol>" <file>` 获取当前工作树中的精确行号；项目处于 dirty worktree，不能把历史行号硬编码进报告。

## 实验与测试写法

- 本次 fresh 测试命令为 `.venv\\Scripts\\python.exe -m pytest -q`，结果为 `562 passed, 5 failed, 2 warnings in 44.69s`（2026-08-23）；通过率约 99.1%，但矩阵未全绿。
- 五项失败分别属于 Composite 错误提示/列名/指标契约、AkShare 快照目录替换权限、首页 parallel fragment 历史契约；报告须列为当前待修复缺陷。
- `156 passed` 等历史矩阵只能写作“项目文档记录的历史测试结果”。
- Phase 2.5 的 `Sharpe 0.42 -> 0.99` 应写作研究样本中的历史优化结果，同时说明交易成本、样本与过拟合风险。
- Phase 2 标记 `data_quality_blocked`；Phase 3/4 标记“框架完成、真实运行/准入待完成”；Transformer v3 Phase 2 标记 `STOP`。
- CN_A pooled 结果必须保留“不完全配对覆盖”的限制。

## 截图建议

以 1440×900 或 1600×1000 视口捕获当前 Streamlit 界面。优先覆盖首页、单股入口/参数/结果、多股入口/结果、模型评估、研究浏览、最终报告阅读器与实验监控。若实时行情或离线产物不可用，截图中保留系统的降级/空状态并在图注中说明，不伪造成功结果。

## 模板适配提醒

原 `report_template.md` 面向 Spring/Vue 示例。stratagy 报告应将模板中的 SQL/IoC/MyBatis/Vue 技术点替换为 Streamlit rerun 模型、pandas/NumPy 时序计算、Plotly、Optuna、状态路由、回测成本、研究 gate、缓存隔离与 `/strategy` 子路径部署。
