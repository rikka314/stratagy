# 美股策略研究基线（2026-08-11）

## 结论先行

`full_us_deans_60` 已完成，形成后续策略功能的**美股离线研究基线**。当前最稳妥的产品定位不是“已经找到稳定跑赢市场的策略”，而是：

- `SM+Bayesian` 是当前综合评分第一的**离线候选**，可作为默认比较对象；
- 买入持有（`Naive`）必须始终保留为基准，不能被排名页或推荐页隐藏；
- 现有结果尚未证明任一候选在全样本上稳定取得正的中位超额收益，不能据此给出收益承诺或自动交易建议；
- A 股与跨市场研究已按当前决定暂缓。本文件只适用于这批美股、这套成本和这套窗口，不能外推至 A 股或其他市场。

## 1. 冻结口径与可追溯性

| 项目 | 口径 |
| --- | --- |
| 研究输出 | `model-test/outputs/full_us_deans_60/` |
| 市场与股票池 | US，60 只股票 |
| 主窗口 | 1,260 个交易日 |
| 稳健性窗口 | 4 个 rolling 窗口，每个 756 日，步长 126 日 |
| 搜索公平性 | Random / Bayesian 各 240 次；Genetic 为 24 x (9 + 1) = 240 次目标评估；固定 seed 42 |
| 交易假设 | commission 1 bps、slippage 2 bps；`hold_until_exit=true`、`hold_min_position=0.2` |
| 最低数据新鲜度 | `2026-07-31`；每个入选行情已冻结到本次输出的 `data_snapshot/` |
| 综合评分 | 有 rolling 记录的模型：主窗口 60% + 稳健性 40%；评分同时考虑 beat-naive、超额收益、Sharpe、回撤、稳定性、过拟合纪律和可靠性 |

运行记录共 5,460 条：主窗口 1,140 条全部成功；rolling 4,320 条中 4,318 成功、2 条降级。19 个模型在主窗口均覆盖完整；`rsm_adaptive_v1` 按设计不参加 rolling，因此 rolling 覆盖为 18/19。

两条降级都在 `SHOP / rolling_1` 的 FSM+Genetic Stage B ML 路径，原因为训练样本为空；系统保留上一步成功结果。这是 ML 数据边界，不是主窗口研究失败。

## 2. 综合排名：候选不等于收益承诺

| 排名 | 模型 | 总分 | 主窗口分 | rolling 分 | 主窗口中位超额收益 | 主窗口中位 Sharpe | 跑赢 Naive 比例 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | SM+Bayesian | 72.67 | 70.00 | 76.67 | -7.95% | 0.03 | 40.00% |
| 2 | SM+Bayesian+ML-LGBM | 68.99 | 72.76 | 63.33 | -11.08% | 0.00 | 41.67% |
| 3 | SM+Bayesian+ML-LR | 67.44 | 66.84 | 68.33 | -11.08% | 0.00 | 40.00% |
| 4 | SM+Genetic | 64.49 | 60.26 | 70.83 | -7.41% | 0.14 | 35.00% |
| 5 | FSM+Genetic+ML-LGBM | 60.81 | 70.79 | 45.83 | -9.96% | 0.00 | 40.00% |
| 基准 | Naive（买入持有） | 54.68 | 44.47 | 70.00 | 0.00% | 0.44 | — |

`SM+Bayesian` 的 rolling 中位年化收益为 11.44%、中位 Sharpe 为 0.82、中位回撤为 -8.60%，所以在风险调整后的滚动表现中领先；但其主窗口中位超额收益为 -7.95%，仅在 40% 标的上跑赢 Naive。后续界面必须同时展示“绝对/超额收益、回撤、Sharpe、覆盖率、窗口数”，并把综合分定位为多目标排序工具，而不是“预期收益排名”。

家族层面，SM 的平均总分最高（60.27），FSM 为 54.96，RSM 为 49.59，基础策略为 36.91；横向搜索方法中 Bayesian 的平均总分最高（64.39），Genetic 次之（61.46）。这支持将 `SM+Bayesian` 作为默认研究候选，但不足以替代基准或覆盖状态差异。

## 3. ML 的结论：保留为条件化候选，不设为默认增强

| 子路径 | 相对父模型 | 综合分变化 | 中位超额收益变化 | 中位 Sharpe 变化 | 产品结论 |
| --- | --- | ---: | ---: | --- |
| SM+Bayesian+ML-LGBM | SM+Bayesian | -3.68 | -3.13% | -0.03 | 不默认启用 |
| SM+Bayesian+ML-LR | SM+Bayesian | -5.23 | -3.13% | -0.03 | 不默认启用 |
| FSM+Genetic+ML-LGBM | FSM+Genetic | +2.37 | +0.23% | -0.31 | 仅作为回撤/稳定性权衡候选 |
| FSM+Genetic+ML-LR | FSM+Genetic | -4.42 | +0.23% | -0.31 | 不默认启用 |

因此，ML 应作为可解释的 ablation/条件分支：界面展示启用前后的指标变化、样本数与降级原因；当训练样本不足时，明确降级并回退到父策略。不能把“带 ML”当作更高级或默认更优。

## 4. 状态与分段：不要为所有市场状态指定同一策略

分段结果只有 4 条被标记为 `suitable`，且都来自下跌状态：

| 状态 | 候选 | 样本数 | 中位超额收益 | 中位回撤 |
| --- | --- | ---: | ---: | ---: |
| Down / High volatility | FSM+Random | 7 | +44.52% | -14.07% |
| Down / High volatility | SM+Random | 7 | +40.13% | -15.31% |
| Down / Mid volatility | RSM | 7 | +31.06% | -3.25% |
| Down / Mid volatility | RSM-NoMarket | 7 | +22.38% | -3.36% |

这些结果的分段样本量只有 7，属于研究线索，不是可直接上线的状态规则。上涨和震荡状态没有出现 `suitable` 的统一赢家；特别是 Up/High 与 Up/Mid 的分段首位仍为 `neutral`，部分甚至相对 Naive 为负。

Adaptive router 的训练产物已生成：6 个状态，特征以 ADX、RSI、drawdown rank 为主，路由优先级为 `symbol -> segment -> global -> mean`。它适合承担“状态感知的候选路由/解释”能力，而不是在未独立验证前取代固定策略或基准。

## 5. 后续功能的产品基线

1. 研究总览：默认选中 `SM+Bayesian`，并固定并列显示 `Naive`；提供 Top 5、家族、搜索方法、ML 增量和原始 run 的追溯入口。
2. 策略卡与推荐：展示综合分之外的超额收益、Sharpe、最大回撤、跑赢基准比例、成功/降级率和样本窗口；当中位超额收益不为正时，使用“研究候选”而非“推荐/最优”。
3. 状态感知面板：展示当前状态、router 选择、作用层级（symbol/segment/global/fallback）、置信/样本量和回退链路；状态规则必须标注为离线研究。
4. ML 实验面板：以父策略为对照，展示 score / excess return / Sharpe delta、训练样本量、pass rate 和降级原因，并允许关闭 ML。
5. 风险与可复现页：链接 `config_snapshot.json`、`data_manifest.json`、`runs.csv`、`report.json`、per-run artifacts 和 QuantStats tear sheets；明确成本、窗口、数据冻结日期和市场范围。

## 6. 不可越过的边界

- 不把本次美股结果延伸为 A 股结论；A 股与跨市场实验保持暂停，后续若恢复须建立独立的冻结数据与比较报告。
- 不以“成功率/覆盖率 100%”替代策略效果验证；它只说明执行覆盖完整。
- 不只按总分、单期年化或单个标的展示策略；必须与 Naive 对照，并同时展示跨窗口与分段样本量。
- 不把分段小样本和 adaptive router 当作生产 alpha 证据；需额外的时间外、样本外验证后才能提高决策权重。
- 不自动恢复本次 campaign，也不改动已有 stash；已完成的美股输出是本基线的冻结来源。

## 7. 证据索引

- `model-test/outputs/full_us_deans_60/report.json`：正式结构化结论、评分、ML 增量、adaptive router。
- `model-test/outputs/full_us_deans_60/model_summary.csv`：19 个模型的主窗口、rolling 和总分。
- `model-test/outputs/full_us_deans_60/robustness_summary.csv`：18 个模型的滚动稳健性。
- `model-test/outputs/full_us_deans_60/segment_summary.csv`：趋势/波动分段与适用性。
- `model-test/outputs/full_us_deans_60/runs.csv`：5,460 条可回溯运行记录及 artifact 路径。
- `model-test/outputs/full_us_deans_60/regime_artifacts/`：状态分类与路由策略产物。
- `model-test/outputs/full_us_deans_60/quantstats/`：前五模型的 pooled tear sheets。

本文件记录研究和产品边界，不构成投资建议。
