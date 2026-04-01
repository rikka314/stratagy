# 第4周计划 · FSM + ML-SM 两个增强模型上线

**生成日期：** 2026-03-25  
**工作量：** ≈ 原 W5+W6 前半（约1.5倍），对应加速节奏  
**参考文件：** `plan/金融学期总计划.md` 第4周 + `AI_CONTEXT.md`

---

### 第4周 · 主题：FSM + ML-SM 两个增强模型上线

**本周目标（一句话）：** 完成 FA 因子提炼（FSM）和 ML 信号过滤（ML-SM）两个增强模型，在单股页跑通 5~6 模型净值曲线同台对比首版。

---

## 大任务 1：`core/fa_filter.py` — FA 因子提炼层（FSM 的核心）

> 背景：SM 用固定权重手工加权 10 个因子；FSM 改为用因子分析（FA/PCA）在训练集上学习 k 个潜在因子，再用这 k 个因子的线性合成分数替代原有的 `factor_score`。数据泄露是最大风险：FA 的 `fit` 只能在训练集上执行，测试集只能 `transform`。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 1.1 | 设计 `fa_filter.py` 的对外接口：`fit_fa(df_train, n_components=3) -> FAModel`；`transform_fa(fa_model, df) -> pd.Series`（输出与 `factor_score` 同形 Series）；决定用 `sklearn.decomposition.FactorAnalysis` 还是 `PCA`（PCA 更稳，FA 更接近因子模型） | GPT-5 | 接口设计决策，用 GPT-5 独立验证方向，避免 PCA/FA 选择错误 |
| 1.2 | 实现 `fa_filter.py`：输入为 `df_train`（含 10 因子列）→ `fit` sklearn `FactorAnalysis(n_components=k)`；内部对 10 因子做标准化（`StandardScaler`，同样只在训练集 `fit`）；输出 `FAModel = namedtuple("FAModel", ["fa", "scaler", "n_components"])`；`transform` 时先 `scaler.transform` 再 `fa.transform`，最终把 k 列潜在因子取均值（或加权）为标量 `fsm_score` | 云端 DeepSeek | 单文件实现，sklearn 接口清晰，DeepSeek 擅长生成结构化代码 |
| 1.3 | 在 `compute_signals()` 中新增 `fsm_mode: bool = False` 参数和 `fa_model` 参数；`fsm_mode=True` 时用 `transform_fa(fa_model, df)` 的输出替代手工加权的 `factor_score`，其余仓位逻辑完全不变；`fsm_mode=False` 时行为不变 | Claude Pro | 需要同时看 `core/signals.py` 的完整 `compute_signals()` 签名（~182行）+ `optimizer.py` 的调用点，保证默认值兼容不破坏已有流程 |
| 1.4 | 在 `core/__init__.py` 导出 `fit_fa`、`transform_fa` | 云端 DeepSeek | 单行导出 |

**产出物：** `core/fa_filter.py`（`fit_fa` + `transform_fa`，k 可配置，默认 k=3）；`compute_signals()` 支持 FSM 模式

---

## 大任务 2：`core/ml_filter.py` — ML 信号过滤层（ML-SM 的核心）

> 背景：ML-SM 的逻辑是"SM 先产生信号 → ML 过滤掉低置信度信号"。关键挑战：①特征和标签对齐时间点，②训练/测试必须时序切分，③标签定义要贴近"信号是否真的赚钱"而不只是"未来涨跌"。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 2.1 | 设计标签：在有买入信号（`position > 0` 且前一日 `position == 0`）的日期上，计算"未来 10 日策略收益是否大于 Naive 收益"（超额收益正负）作为二分类标签；在信号稀少时，退化为"未来 10 日收益是否为正"；写明标签定义逻辑（保留到注释中） | GPT-5 | 标签设计是 ML-SM 成败的关键，用 GPT-5 做方案确认，避免数据泄露或无效标签 |
| 2.2 | 实现 `build_feature_table(df_signals) -> pd.DataFrame`：输入含完整指标列的 df（来自 `add_indicators` + `compute_signals`），提取 20~30 个特征列（factor_score、factor_percentile、10 因子分量、rsi、macd/signal、adx、atr/close、volume_ratio、entry_count、trend_ok）；对每个有买入信号的日期生成一行样本 | 云端 DeepSeek | 特征列表已在总计划中定义，提取逻辑明确，单文件 |
| 2.3 | 实现 `fit_ml_filter(feature_df, labels, model_type="logistic") -> MLModel`：支持 `logistic`（`LogisticRegression`）和 `lgbm`（`LightGBMClassifier`），内部做 `StandardScaler`（仅对 logistic）；输出 `MLModel = namedtuple("MLModel", ["model", "scaler", "model_type", "threshold"])`；`threshold` 默认 0.5 | 云端 DeepSeek | 双模型封装，结构清晰，sklearn/lgbm 接口标准 |
| 2.4 | 实现 `predict_filter(ml_model, feature_df) -> pd.Series`（概率序列）和 `apply_filter(df_signals, ml_model, feature_df, threshold) -> pd.DataFrame`（修改 position 列：低于 threshold 的信号置0）；输出可直接送 `simulate_strategy()` | Claude Pro | 需要同时理解 `signals.py` 的 position 结构 + `backtest.py` 的输入格式，是两个模块的胶水层，需要 Claude 做接口对齐 |
| 2.5 | 实现 `evaluate_ml_quality(y_true, y_pred_proba) -> dict`：返回 `precision/recall/f1/pr_auc/signal_pass_rate`；`signal_pass_rate = 过滤后信号数 / 原始信号数` | 云端 DeepSeek | 纯指标计算，sklearn.metrics 接口 |
| 2.6 | 在 `core/__init__.py` 导出 `build_feature_table`、`fit_ml_filter`、`apply_filter`、`evaluate_ml_quality` | 云端 DeepSeek | 单行导出 |

**产出物：** `core/ml_filter.py`（特征表构建 + 双模型训练 + 信号过滤 + 质量评估）；`core/__init__.py` 更新

---

## 大任务 3：单股页 5 模型同台对比视图（UI 层）

> 背景：`ui/single_stock.py` 的 `_render_test_performance()` 已有 SM vs Naive 评估区块和模型选择控件（FSM/ML-SM 入口已预留为灰色）。本周解锁 FSM 和 ML-SM，实现 5~6 条净值曲线同台对比，并加 ML 模型质量指标卡。

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 3.1 | 在单股页的测试集计算流程中加入 FSM 路线：训练集 `fit_fa()` → 测试集 `transform_fa()` → `compute_signals(fsm_mode=True, fa_model=...)` → `simulate_strategy()` → `evaluate_strategy()`；把 FSM ModelResult 加入 `_render_test_performance()` 的对比表 | Claude Pro | 涉及 single_stock.py 训练/测试切分逻辑 + fa_filter / signals / backtest / evaluation 4个模块联动，必须 Claude 做全局联调 |
| 3.2 | 在单股页加入 ML-SM 路线：训练集 `build_feature_table()` + `fit_ml_filter()` → 测试集 `apply_filter()` + `simulate_strategy()` → `evaluate_strategy()`；加入 Logistic 和 LightGBM 两个变体 | Claude Pro | 需要同时看 signals.py position 结构 + single_stock.py 现有流程，是跨模块联调核心 |
| 3.3 | 更新净值/回撤双子图：把所有激活模型（最多6条）叠加到一张 Plotly 图上；Naive/Mean/Drift 用浅色虚线，SM 用主色 `#2f5d62`，FSM 用 `#8f3b2e`，ML-LR 用 `#f39c12`，ML-LGBM 用紫色 `#7d5a9e`；图例自动显示激活模型 | 云端 DeepSeek | 独立图表，颜色方案已定义，给定数据结构后直接实现 |
| 3.4 | 新增 ML 模型质量指标卡：在 ML-SM 激活时展示 `precision / recall / f1 / pr_auc / signal_pass_rate`，用 `st.columns(5)` 渲染 5 个小卡片；过滤率 < 30% 时橙色警告提示 | 云端 DeepSeek | 纯 UI 展示，`evaluate_ml_quality()` 已计算好数据 |
| 3.5 | 更新模型选择控件：FSM / ML-LR / ML-LGBM 从"灰色待实现"变为可选；选中后显示对应净值曲线和 KPI 行 | Claude Pro | 需要理解现有 multiselect 控件的条件渲染逻辑，和前面 3.1/3.2 的计算流程联动 |

**产出物：** 单股页 5~6 模型净值曲线同台对比首版；ML 质量指标卡；模型选择控件完整解锁

---

## 大任务 4：样本外验证 + 文档更新

| 子任务 | 具体内容 | 推荐工具 | 理由 |
|--------|---------|---------|------|
| 4.1 | 手动验证：用 AAPL（美股）和一只 A 股（如 600519 茅台）各跑一次 5 模型对比，记录每个模型的年化收益/夏普/最大回撤/胜率；确认 SM/FSM/ML-SM 都跑赢 Naive 基线（或记录哪个没跑赢及原因） | 手动（UI 操作） | 这是功能验收，不是代码任务 |
| 4.2 | 更新 `document/MODULE_INTERFACES.md`：补充 `fa_filter.py` 和 `ml_filter.py` 的函数签名与输入输出说明 | 云端 DeepSeek | 文档写作，中文 |
| 4.3 | 更新 `AI_CONTEXT.md`：代码地图新增 `fa_filter.py` / `ml_filter.py` 条目；文档维护状态补 W4 完成记录 | Claude Pro（本对话结束时） | 项目最高优先上下文 |

**产出物：** 5 模型样本外对比验证记录；文档同步完成

---

## 当前收尾判断（2026-03-26）

- 按当前仓库状态，W4 的核心开发项已基本完成：`core/fa_filter.py`、`core/ml_filter.py`、单股页 7 模型测试期同台计算、ML 质量卡与相关文档同步均已落地。
- 因此 W4 不应继续扩写新功能；当前只保留“验收型收尾”，不再把新的页面结构重构或泛 UI 改版混进本周。

### W4 还剩下的 `P0` 收尾项

1. 用 `AAPL` 跑一次 5 模型样本外对比。
2. 用 1 只 A 股样本跑一次 5 模型样本外对比，默认使用 `600519`。
3. 记录 `Naive / SM / FSM / ML-LR / ML-LGBM` 的年化收益、夏普、最大回撤、胜率。
4. 明确写出哪些模型跑赢 `Naive`，哪些没有跑赢，以及已知原因或限制说明。

### W4 可接受的降级口径

- 若 `ML-LGBM` 路径在样本外验证中稳定性不足，W4 仍可按“`Logistic` 路线已跑通、`LGBM` 记录为次优先补强项”收口，不阻塞周切换。
- 若某只样本股票上 `FSM` 或 `ML-SM` 未跑赢 `Naive`，W4 仍可收口，但必须留下验证记录和原因解释，不能只保留“功能可运行”结论。

### 不再计入 W4 的事项

- 单股页策略工作流重构落地
- `StrategyRequest / StrategyArtifact / strategy_workspace` 代码实现
- 单股页五段式主区重排
- 多股页模型汇总看板
- 新一轮整体视觉改版

### W4 完成判定

- 完成 2 组样本外验证留痕后，W4 即视为收口。
- W4 收口后，下一主线不再是继续补模型，而是进入单股页策略工作流重构落地。

### 2026-03-26 已完成留痕

- 已新增 `document/archive/feature-notes/W4_OOS_VALIDATION.md`，按单股页当前实际口径记录 2 组样本外结果：最近 3 年窗口、`70/30` 时序切分、`均衡策略（默认）`、`qfq`。
- `AAPL` 测试段 `2025-03-18 ~ 2026-01-21`：`Naive` 年化 `20.25%`；`SM / FSM / ML-LR / ML-LGBM` 分别为 `-5.97% / -6.90% / 0.62% / -7.36%`，均未跑赢 `Naive`。
- `600519` 测试段 `2025-04-29 ~ 2026-03-23`：`Naive` 年化 `-6.53%`；`SM / FSM / ML-LR / ML-LGBM` 分别为 `-0.24% / -0.50% / -0.26% / 3.02%`，均跑赢 `Naive`，其中 `ML-LGBM` 最优。
- 结论：W4 可按“功能已落地 + 结果已留痕”收口，但不能把当前结果表述成“增强模型普遍优于买入持有”。

---

## 本周资源分配建议

| 工具 | 预计用量 | 主要用途 |
|------|---------|---------|
| Claude Pro | 高 | `compute_signals()` FSM 模式扩展、`apply_filter()` 胶水层、单股页 5 模型联调（3.1/3.2/3.5）、`AI_CONTEXT.md` 更新 |
| 云端 DeepSeek-v3.1 | 高 | `fa_filter.py` 主体实现、`build_feature_table()`、`fit_ml_filter()`、`evaluate_ml_quality()`、净值多曲线图表代码、ML 质量卡 UI、文档写作 |
| GPT-5 | 低 | FA vs PCA 选型验证、ML 标签设计方案确认 |
| Gemini | 低（备用） | 若需要整体阅读 `single_stock.py`（1030行）和 `signals.py` 定位接入点 |

**可外包给其他 AI 的比例：约 45%**

---

## 风险提示

### 风险1：FA/PCA 因子方向不稳定

FA 提炼出的潜在因子可能对应"看跌"（系数为负），导致 FSM 分数与实际含义反向。

**应对：** `fit_fa()` 实现后，打印潜在因子与原始 10 因子的相关性矩阵，手动确认方向。若某个潜在因子与"动量因子"负相关，则对该维度取反。如果 FA 复杂度超预期，降级为 `sklearn.decomposition.PCA`（接口更稳，解释性稍弱）。

### 风险2：ML 数据泄露导致虚假高胜率

`build_feature_table()` 如果用了未来信息，或 `StandardScaler` 在全样本上 fit，样本外表现会虚高然后实盘崩溃。

**应对：** `fit_ml_filter()` 收到的 `feature_df` 必须只含训练集行，`scaler` 只在训练集 `fit`；`apply_filter()` 收到的是测试集行，只做 `transform`。在联调时，打印训练集和测试集的日期范围，确认无重叠。

---

## 落后时裁剪优先级

1. LightGBM 模型（2.3）可先只做 Logistic，LGBM 延后到 W5 补
2. ML 质量指标卡（3.4）若时间不够，先只在对比表里加一行 ML 指标，不做卡片 UI
3. FSM 若 FA 调试超预期，改用 PCA 直接替代（sklearn 接口完全一致，1行改动）
4. 大任务 4 文档（4.2）最后写，核心功能优先
