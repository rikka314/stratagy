# 第3周计划 · 5模型架构 + 评估基础设施 + 课程基线

**生成日期：** 2026-03-25（修订版，含架构调整）  
**工作量：** ≈ 原 W3+W4（约2倍），对应加速节奏  
**参考文件：** `plan/金融学期总计划.md` 第3周 + `AI_CONTEXT.md` + `document/LECTURE_MODELS.md`

---

### 第3周 · 主题：5模型架构 + 评估基础设施 + 课程基线

**本周目标（一句话）：** 定义5模型统一接口，实现3个课程基线（Naive/Mean/Drift），建立多模型评估模块，在单股页落地 SM vs Naive 首版评估区块，为 W4 FSM/ML 对接预留所有入口。

---

## 大任务 1：架构设计 + `core/backtest.py` trade-level 补全

> 背景：W3 新增 3 个 core 模块（baselines / evaluation / fa_filter / ml_filter），模块间需要统一的数据传递结构。现有 `simulate_strategy()` 缺少逐笔交易记录，胜率/盈亏比/持仓天数无法计算。这两件事是所有后续工作的地基，必须先完成。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 1.1 | 设计 `ModelResult` 统一数据结构：`{"label": str, "equity_series": pd.Series, "returns": pd.Series, "trades_df": pd.DataFrame或None, "metrics": dict或None}`；写入新文档 `document/MODEL_INTERFACES.md` | GPT-5 | 接口设计是架构决策，用GPT-5做独立验证，避免设计过早固化；文档写作也适合GPT-5 |
| 1.2 | 在 `core/backtest.py` 新增 `extract_trades(df)` 函数：输入带 `position` 列的 df，返回 `trades_df`（列：entry_date / exit_date / hold_days / trade_return / is_win）；逻辑：position 连续非零段 = 一笔交易 | 云端 DeepSeek | 独立工具函数，输入输出明确，单文件实现 |
| 1.3 | 在 `simulate_strategy()` 新增可选参数 `return_trades: bool = False`，True 时内部调用 `extract_trades()` 并返回 `(df, trades_df)` tuple；False 时行为完全不变 | Claude Pro | 需要同时看 `backtest.py` 现有签名 + `optimizer.py` 的3处调用，保证默认值兼容，改完跑 AAPL 贝叶斯优化冒烟测试 |

**产出物：** `document/MODEL_INTERFACES.md`；`backtest.py` 新增 `extract_trades()` + `simulate_strategy(return_trades=False)` 扩展。

---

## 大任务 2：课程基线模型 `core/baselines.py`

> 背景：课件要求（`document/LECTURE_MODELS.md` §A）：复杂模型必须先和简单基线对比，否则不合格。3个基线作为"下限"——SM/FSM/ML-SM 必须全部跑赢这些基线才有意义。  
> 基线的仓位策略：把课程的"价格预测"翻译成"仓位规则"——高于某个预测水平时持仓，否则空仓。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 2.1 | 实现 `naive_baseline(df) -> ModelResult`：永远满仓，equity = `buy_hold_equity`，wrap `simulate_strategy()` 已有结果即可；label = "Naive（买入持有）" | 云端 DeepSeek | 简单封装，单文件 |
| 2.2 | 实现 `mean_baseline(df, window: int = 60) -> ModelResult`：收盘价 > 过去 `window` 日均值时持仓，否则空仓；用 `simulate_strategy()` 驱动回测；label = "Mean（均值基线）" | 云端 DeepSeek | 纯仓位规则，单文件实现，不涉及多文件联动 |
| 2.3 | 实现 `drift_baseline(df, split_idx: int) -> ModelResult`：在训练集（`df[:split_idx]`）上估计漂移斜率 `β = (y_T - y_1)/(T-1)`；测试集上，若 `close[t] + β < close[t]` 即预测下跌则空仓，否则持仓；label = "Drift（漂移基线）" | 云端 DeepSeek | 有 split_idx 参数，需遵守训练/测试分离，逻辑清晰，单文件 |
| 2.4 | 实现 `run_all_baselines(df, split_idx) -> list[ModelResult]`：一次性返回3个基线结果列表，供 UI 层一次性调用 | 云端 DeepSeek | 简单聚合函数 |

**产出物：** `core/baselines.py` 包含4个函数，输出标准 `ModelResult` 格式。

---

## 大任务 3：评估模块 `core/evaluation.py`（多模型版）

> 背景：评估模块是整个5模型对比的"裁判"，必须支持多模型同时输出标准化结果，且接口要稳定到 W4 FSM/ML 对接不需要改。标准 key 要参照最终5模型全集设计。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 3.1 | 实现 `compute_performance_metrics(equity_series, benchmark_series, risk_free=0.0) -> dict`：累计收益率、年化收益率（×252交易日）、最大回撤、夏普比率（×√252）；**复用** `backtest.py` 已有 `max_drawdown()` 和 `sharpe_ratio()`，不重复实现 | Claude Pro | 需要同时看 `backtest.py` 已有函数签名 + `TASK_BREAKDOWN.md` 附录A的指标口径，避免重复且口径对齐 |
| 3.2 | 实现 `compute_trade_stats(trades_df) -> dict`：胜率、盈亏比（平均盈利 / 平均亏损绝对值）、平均持仓天数、换手率（开仓次数 / 总交易日数） | 云端 DeepSeek | 纯统计，输入结构来自大任务1的 `trades_df` |
| 3.3 | 实现顶层 `evaluate_strategy(label, equity_series, benchmark_series, trades_df=None) -> dict`：合并以上两个 dict，统一 key = `label/cumret/annret/maxdd/sharpe/winrate/pnl_ratio/avg_hold/turnover`；无 trades_df 时 winrate/pnl_ratio/avg_hold/turnover 填 None | Claude Pro | 接口设计影响 W4 FSM/ML 对接，需全局理解评估模块 + 未来扩展场景 |
| 3.4 | 实现 `build_comparison_table(results: list[dict]) -> pd.DataFrame`：输入多个 `evaluate_strategy()` 返回值列表，输出多行对比 DataFrame，列 = 所有标准 key；供 `st.dataframe()` 直接展示 | 云端 DeepSeek | 纯数据处理，独立于 UI 层 |
| 3.5 | 在 `core/__init__.py` 导出 `evaluation` 和 `baselines` 模块的公开函数 | 云端 DeepSeek | 单行导出，参照现有格式 |

**产出物：** `core/evaluation.py` 4个函数；`core/__init__.py` 更新。

---

## 大任务 4：单股页评估区块 + 模型选择控件（UI 层）

> 背景：`ui/single_stock.py`（~1030行）的 `_render_test_performance()` 是评估区块的落脚点。本周先实现 SM + Naive 两条线的完整评估视图，并加入模型选择控件入口，为 W4 接入 FSM/ML 预留 UI 位置。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 4.1 | 在 `_render_test_performance()` 里调用 `evaluate_strategy()` 和 `naive_baseline()`，用 `build_comparison_table()` 生成对比 DataFrame，`st.dataframe()` 展示（SM行 vs Naive行），启用 column_config 数字格式化 | Claude Pro | 需要同时看 single_stock.py 现有区块结构 + evaluation.py / baselines.py 接口，保证数据流完整 |
| 4.2 | 加入 KPI 指标卡：`st.columns(3)` 渲染6个核心指标（累计收益、年化收益、最大回撤、夏普、胜率、盈亏比），SM 值 vs Naive 值对比；配色参照 `UI_DESIGN_GUIDE.md` 暖色学术风 | Claude Pro | 涉及 single_stock.py 布局改动，同一文件内联动 |
| 4.3 | 加入净值曲线 + 回撤曲线：从 equity_series 计算 drawdown_series，用 Plotly 双子图（上净值/下回撤填充面积），颜色用 `#2f5d62`（策略）/ `#f39c12`（基准） | 云端 DeepSeek | 独立图表，颜色已定义，给定数据结构后直接实现 |
| 4.4 | 加入月度收益热图：strategy_return 按年×月聚合，调用 `core/visualization.py` 的 `create_periodic_returns_heatmap()`；若接口不兼容新增 `returns_series` 入参支持 | Claude Pro | 修改 visualization.py 接口需要同时看 multi_stock.py 的现有调用，避免破坏多股页 |
| 4.5 | 在单股页顶部或评估区顶部加"模型对比选择"多选框（`st.multiselect`）：选项 = Naive / Mean / Drift / SM（固定）/ FSM（灰色待实现）/ ML-SM（灰色待实现）；本周只激活 Naive + SM，其余 W4 接入时解锁 | Claude Pro | 涉及 single_stock.py + 参数传递，需要理解现有页面结构 |

**产出物：** 单股页评估区块可运行（KPI卡 + 净值回撤曲线 + 月度热图 + SM vs Naive 对比表）；模型选择控件就绪。

---

## 大任务 5：文档同步

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 5.1 | 更新 `document/MODULE_INTERFACES.md`：补充 `baselines.py` 和 `evaluation.py` 的函数签名与入参/出参说明 | 云端 DeepSeek | 文档写作，中文，单文件 |
| 5.2 | 更新 `AI_CONTEXT.md`：代码地图新增 `baselines.py` / `evaluation.py` 条目；文档维护状态补 W3 完成记录；新增5模型架构说明 | Claude Pro（本对话结束时） | 项目最高优先上下文，会话结束标准收尾 |

**产出物：** `MODULE_INTERFACES.md` 更新；`AI_CONTEXT.md` W3 状态记录。

---

## 本周资源分配建议

| 工具 | 预计用量 | 主要用途 |
|------|---------|---------|
| Claude Pro | 高 | backtest.py 扩展（保证 optimizer 兼容）、evaluation.py 接口设计、单股页 UI 联动、月度热图接口修改、AI_CONTEXT 更新 |
| 云端 DeepSeek-v3.1 | 高 | baselines.py 全部4函数、extract_trades()、compute_trade_stats()、build_comparison_table()、净值回撤图表代码、文档写作 |
| GPT-5 | 低 | ModelResult 接口设计验证、评估指标口径确认（年化收益252vs365、夏普系数）|
| Gemini | 低（备用）| 若需要整体阅读 single_stock.py（1030行）定位 _render_test_performance 的完整上下文 |

**可外包给其他 AI 的比例：约 40%**

---

## 风险提示

### 风险1：`simulate_strategy()` 改动破坏 optimizer.py

`core/optimizer.py`（~906行）里的三种优化方法均内部调用了 `simulate_strategy()`。新增 `return_trades=False` 参数必须保证默认值下行为完全不变。

**应对：** 改完后立即跑一次 AAPL 的贝叶斯优化（UI 里点"高级搜索 → 贝叶斯优化"，观察是否报错）。若有问题，回退到只新增 `extract_trades()` 独立函数，不修改 `simulate_strategy()` 签名。

### 风险2：评估接口 key 后期需要大改

W4 接入 FSM/ML-SM 时，若 `evaluate_strategy()` 的 key 设计不前瞻，可能需要破坏性修改。

**应对：** 子任务 3.3 定义 key 列表时，参照总计划5模型全集（Naive/Mean/Drift/SM/FSM/ML-SM）设计，保留 `label` 字段，winrate/pnl_ratio 等 trade-level 指标在无 trades_df 时填 `None` 而非报错。

### 风险3：Mean/Drift 基线"交易化"语义歧义

课程基线是价格预测模型，转换为仓位规则时可能有多种合理解读。

**应对：** 子任务 2.2/2.3 实现前先确认逻辑（"收盘价 > 滚动均值 → 持仓"是最直觉的转化）。若实现后结果过于平庸（Drift 和 Naive 相差不大），可在评估区注释说明"基线仅用于论证下限"。

---

## 落后时裁剪优先级

1. 月度热图（4.4）可延后到 W5 UI 优化时处理
2. 模型选择控件（4.5）若时间不够，先用固定显示 SM+Naive，不加 multiselect
3. Drift/Mean 基线若实现超预期复杂，本周只做 Naive（买入持有），Mean/Drift 移到 W4 开头补
4. `document/MODEL_INTERFACES.md`（5.1）最后写，核心功能优先
