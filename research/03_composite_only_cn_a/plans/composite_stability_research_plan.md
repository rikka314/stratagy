# Composite Stability and Position-Mapping Research Plan

> 状态：待在后续窗口执行
> 范围：Composite score、因子、权重、交互项、仓位映射、成本和跨 fold 验证
> 市场：第一阶段 US；通过 US gate 后再复制到 CN_A
> 运行边界：research-only；不接入 Streamlit、不修改 production 默认策略
> 基准：`composite_only`，并保留 `cash` safety baseline
> 主预测周期：20 trading days；执行收益严格按决策时点后的收益计算

## 1. 目标与核心判断

本计划要解决的不是“再找一组更高 Sharpe 的权重”，而是先证明 Composite 的分数、方向、仓位和收益之间具有可解释、可复现、跨时间稳定的关系。

当前代码和输出已经暴露出以下结构性问题：

1. **Composite 到 position 的尺度错配**
   - Phase 2.5 优化器在 `model-test/phase2_5_advanced_optimization.py` 中先按全样本 `score_std` 做缩放，再用 `tanh`。
   - `core/expert_pool_v2.py` 的 `composite_optimized` 却直接使用原始加权分数，再调用 `_bounded_long()` 的 `tanh(score / temperature)`。
   - `vix_level` 是约 15--80 的原始水平，权重为正；它与其他 z-score / rank 因子不在同一尺度，主导 Composite 分数。
   - 当前 Phase 1 audit 中，`composite_base_position > 0.99` 约为 99.56%，`>0.999` 约为 97.45%；Composite score 中位数约 8.76，最大约 44.75。该结果不是有效的连续仓位信号，而是近似恒定满仓。

2. **Baseline 的低换手是饱和伪象，advisory 的高换手是映射断裂**
   - `composite_only` 的累计 turnover 几乎为零，因为饱和后的仓位长期等于 1。
   - advisory 从接近 1 的 base position 频繁压到 0.75/0.80/宏观 cap，再恢复，累计 turnover 大幅增加；Phase 1 的 turnover multiple 达到数十到数十万，说明当前基准不适合比较 overlay。
   - `max_single_decision_change` 只限制单日变化，不限制最小持仓期、触发抖动、恢复滞后或单位时间 turnover。

3. **权重和交互项证据不足以支持冻结**
   - Phase 2.5 的权重来自单一标的/研究脚本的 in-sample Sharpe 优化；Bayesian 100 次迭代和交互项网格没有 nested walk-forward、bootstrap stability 或多标的一致性证据。
   - `volume_ratio_rank * mom_short_z` 未做中心化/正交化，交互项会同时承担主效应、尺度和极端值的影响；只测试 `[-1,-0.5,0.5,1]`，且只在同一个优化流程中选择最佳项。
   - 负的 `macd_z` 可能是真实方向，也可能是数据调整、时滞、共线性或样本偶然性，必须通过方向稳定性和反事实测试确认。

4. **因子方向和命名语义存在冲突**
   - `rsi_z` 在 Composite 中为正，但 `mean_reversion` 专家把 RSI 解释为反向暴露；Composite 公式没有明确“高分代表收益方向还是风险/超买程度”。
   - `vix_level` 在报告中被称作风险调制器，但 Composite 正权重会在高 VIX 时提高 long score；`macro_defensive` 专家则以风险升高降低 exposure。二者语义不一致。
   - `rel_strength_spy`、`volume_confirmed`、`mom_short_z` 存在潜在重复信息；Phase 3 已出现 Composite SPY beta 约 0.925、专家正交性 gate failed。

5. **PIT 大体有基础，但没有形成可审计的全链路 contract**
   - rolling/pct_change 使用当前及过去数据，若收盘后下一时点执行，原则上可以使用；若在开盘前决策，则不能使用当天 close。
   - `MacroFactors` 通过日期 merge + `ffill` 对齐 benchmark/VIX，仍需验证观测发布时间、交易日历、缺失日和 adjusted/unadjusted 语义。
   - 当前研究需要明确 `decision_timestamp -> execution_timestamp -> return interval`，并在每行输出 feature availability cutoff、source date 和 lag。

6. **收益、回撤、换手的当前比较可能被实现细节污染**
   - Phase 1 的 OHLCV runner 明确只扣一次成本，这是正确方向，但仓位已因饱和而失去辨识度。
   - Phase 3 曾出现数据质量阻断和极端 total return，说明任何新的结论都必须先经过价格异常、调整方式和 compound-return sanity gate。
   - 必须同时报告 gross/net return、turnover、transaction cost、exposure、hit rate、max drawdown、downside risk 和 fold dispersion，不能只看 Sharpe。

## 2. 研究原则

- **先修语义，再优化参数**：在 position mapping、factor direction、PIT、cost ledger 未通过前，不允许重新搜索权重。
- **所有统计量按训练窗口估计**：均值、标准差、winsorization 边界、rank reference、温度和阈值都必须由 train window 产生；validation/test 只 transform。
- **保留原始因子与变换后因子**：原始列不能覆盖；记录 transform version、fit window、参数和缺失处理。
- **只允许方向保持的 advisory**：Composite 决定方向；advisory 只能减仓或不变，不能用错误的 overlay 结果掩盖 Composite 的方向问题。
- **每个候选都与同口径 baseline 比较**：baseline 也必须使用同一 position map、rebalance cadence 和 cost model。
- **跨 fold 采用分布和最差 fold 约束**：平均值提升不足以准入；不能把单个 fold 的巨大收益视为证据。
- **所有结果可重建**：配置、代码、数据 manifest、因子 schema、训练窗口和 artifact hash 必须进入 output manifest。

## 3. 推荐的目标架构

### 3.1 因子层：先得到可比较的 signed signal

对每个因子定义三项：`raw_value`、`economic_direction`、`transformed_signal`。

建议默认变换（参数只在 train fit）：

```text
x_raw
 -> availability/PIT validation
 -> cross-sectional or trailing time-series reference
 -> robust clip (train quantile, e.g. 1%/99%)
 -> robust scale (median/MAD or train std)
 -> signed signal in [-1, 1]
```

方向必须显式注册，而不是由优化器随意选择：

```python
FactorSpec(
    name="mom_short_z",
    direction=+1,
    family="trend",
    normalization="rolling_robust",
    availability_lag=0,
)
```

对 `rsi_z`、`macd_z`、`vix_level` 做方向审计：

- `rsi_z`：决定它是趋势确认、超买风险还是 contrarian signal；不能同时在不同模块隐含不同方向。
- `macd_z`：先测试原方向、反向方向和滞后方向；只有方向在多数 train/validation fold 稳定时才冻结。
- `vix_level`：不作为 Composite directional alpha；建议拆成 `market_risk_level`，只进入 exposure cap / risk budget。若保留为因子，方向必须是“风险越高，仓位越低”，不能用正权重增加 long score。
- `rel_strength_spy`：在 US 使用明确名称；CN_A 使用 `rel_strength_market`，不能跨市场复用 SPY 语义。

### 3.2 冗余控制：先按 family，再做 residualization

不直接对所有列做一次相关性筛选。建议顺序：

1. 计算 train-only Pearson、Spearman、mutual information 和 rolling correlation。
2. 每个因子家族最多保留一个主因子和一个补充因子；高相关因子优先按 PIT、稳定性和解释性选择。
3. 对保留的补充因子做 train-only residualization：
   `x_residual = x - projection(x | selected_primary)`。
4. 检查 variance inflation、condition number、effective number of bets。
5. 在 validation/test 只应用冻结的 projection；禁止重新拟合。

必须区分“因子相关”与“仓位相关”：二者都要报告，后者要在经过同一 position map 和 cadence 后计算。

### 3.3 Composite score：使用可比较、可约束的组合

推荐先实现两个候选并保留 ablation：

**A. bounded linear score**

```text
s_t = sum_i w_i * z_i,t + sum_j gamma_j * interaction_j,t
s_scaled = s_t / sqrt(w' Sigma_train w + eps)
```

其中 `Sigma_train` 为 train-only covariance；权重约束为：

- `||w||_1 <= W_max`
- 每个 family 总 absolute contribution <= family budget
- 单因子 contribution <= factor budget
- interaction absolute budget <= interaction budget
- 可选 `w_i * registered_direction_i >= 0`，除非反向方向已通过独立 gate

**B. gated risk-aware score**

```text
alpha_t = bounded_linear_signal_t
risk_cap_t = clip(1 - risk_model_t, cap_floor, 1)
score_t = alpha_t * risk_cap_t
```

风险 cap 不改变 alpha 的经济方向，只限制 exposure。

### 3.4 Position mapping：用“目标仓位 + 执行仓位”两层

不要再把未缩放的 score 直接送入 `tanh`。先定义 target position，再定义 execution position。

候选 map 必须统一比较：

1. **分位数/单调分段 map**：按 train-only score quantile 映射到 `{0, 0.25, 0.5, 0.75, 1}`，容易解释，饱和可控。
2. **dead-zone softsign map**：
   `p_target = p_max * sign(s) * max(|s|-tau, 0)/(k + |s|)`；long-only 版本先取 positive part。比 tanh 更容易控制中间段和尾部斜率。
3. **volatility-targeted map**：
   `p_target = clip(alpha / forecast_vol, 0, p_max)`，再乘风险 cap；forecast volatility 只能使用 PIT 数据。
4. **calibrated monotonic map**：用 train-only isotonic/monotone spline 将 score 映射到未来收益或成功概率，必须强制单调、做 nested validation。

优先顺序：先用 1/2 建立稳定基准，再评估 3/4；不建议一开始引入复杂概率校准。

必须输出：score quantile、position quantile、`p=0/near_max` 比例、map slope、saturation ratio、mean/median exposure。

### 3.5 执行层：成本感知、低抖动

```text
p_target_t
 -> risk cap
 -> minimum holding / rebalance cadence
 -> turnover penalty / no-trade band
 -> max daily delta
 -> p_exec_t
```

建议初始规则：

- 只有 `abs(p_target - p_exec_prev) > no_trade_band` 才调仓。
- 每个 symbol 独立维护 previous position；禁止跨 symbol 复用状态。
- 支持 `rebalance_days`，Composite baseline 与所有 candidates 使用同一 cadence。
- 对降仓和加仓可分别设置 delta limit；风险触发时允许更快降仓，但要单独记录 reason code。
- 以单位时间 turnover、每次 rebalance turnover 和 cost-to-gross-return 作为硬指标。
- 成本模型至少做 base / 2x / 4x sensitivity；若高成本情景崩溃，不准称为稳定 alpha。

## 4. 分阶段执行计划

### Phase 0：语义、数据和基线修复（P0，必须先做）

**目标**：建立可信的 reference replay，证明当前异常来自尺度/实现而不是数据。

**涉及文件**：

- `core/expert_pool_v2.py`
- `core/composite_advisory.py`
- `model-test/phase2_5_advanced_optimization.py`
- `model-test/run_composite_advisory_phase1.py`
- 新增 `model-test/model_test/composite_mapping.py`
- 新增 `model-test/model_test/composite_quality.py`
- 新增/扩展 `tests/test_composite_advisory.py`

**任务**：

1. 将 Phase 2.5 的 score transform 参数化并保存；修复 optimizer 与 ExpertPool 的 train/serve mismatch。
2. 明确 `vix_level` 的单位、方向和角色；先做 `vix_as_alpha` vs `vix_as_risk_cap` ablation。
3. 为每个 symbol、date 生成 `decision_timestamp`, `feature_cutoff`, `execution_timestamp`, `return_start`, `return_end`。
4. 加入价格异常、重复日期、非正价格、adjustment、超大日收益和 compound equity sanity checks。
5. 用同一个 map/cadence/cost 重跑 `composite_only`，输出 raw score 与 transformed score 两套审计列。
6. 为 score/position 饱和建立硬失败阈值。初始诊断阈值建议：`near_max_position_rate <= 0.90`，目标阈值在 Phase 2 冻结。

**输出**：

- `composite_reference_replay.parquet`
- `factor_transform_manifest.json`
- `quality_report.json`
- `mapping_diagnostics.csv`
- `phase0_summary.md`

**停止条件**：PIT、数据质量或收益/成本语义失败时，停止所有权重研究。

### Phase 1：因子方向与冗余审计（P0）

**目标**：把每个因子的经济含义、方向和独立信息量冻结成 contract。

**任务**：

1. 对每个候选方向做 train-only IC、rank IC、sign hit rate、conditional return 和 fold direction consistency。
2. 比较 raw factor、反向 factor、lagged factor；输出方向投票而不是只看 pooled IC。
3. 计算 family 内外 Spearman/Pearson、rolling correlation、VIF/condition number 和 residual correlation。
4. 执行 family budget 与 residualized factor ablation。
5. 分离 alpha 因子和 risk/cap 因子；宏观风险变量默认不进入方向 score。
6. 检查 US 与 CN_A 名称/来源语义，CN_A 只使用 explicit `MarketFactorContext`。

**输出**：

- `factor_direction_report.csv`
- `factor_redundancy_matrix.parquet`
- `factor_registry.json`
- `factor_ablation_metrics.csv`
- `factor_semantics_decision.md`

**建议 gate**：

- 方向在至少 3/4 validation folds 一致，或明确标记为 regime-conditional。
- 删除/替换高冗余因子后，validation utility 不出现系统性恶化。
- 任何依赖 pooled full-sample direction 的因子不得进入冻结 Composite。

### Phase 2：稳健权重和交互项研究（P0）

**目标**：测量权重不确定性，而不是寻找单一最优点。

**任务**：

1. 使用 purged walk-forward + 20-day embargo；每个 fold 内再切 train/validation，禁止 test 调参。
2. 优化 objective 改为多目标或惩罚目标：

```text
utility = validation_sharpe
          - lambda_dd * drawdown_penalty
          - lambda_turnover * turnover_penalty
          - lambda_cost * cost_to_gross_penalty
          - lambda_complexity * l1_weight_penalty
```

3. 使用 block bootstrap / date-cluster bootstrap 估计权重置信区间。
4. 运行多 seed、不同初始点和不同 optimization method；报告 sign stability、coefficient CV、rank stability、selection frequency。
5. 交互项必须先中心化/标准化：
   `interaction = centered(x1) * centered(x2)`，并与主效应同时正则化。
6. 对交互项做 nested ablation：无交互、单交互、全部交互、随机置换交互；至少报告增量收益、风险、换手和跨 fold 一致性。
7. 设 interaction hierarchy：交互项只有在对应主效应存在且稳定时才允许进入。

**输出**：

- `weight_paths.parquet`
- `weight_stability.csv`
- `interaction_stability.csv`
- `bootstrap_weight_intervals.csv`
- `nested_optimization_manifest.json`

**建议 gate**：

- 重要权重 sign stability >= 75%；否则退化为零/非方向性权重或 regime-specific candidate。
- 交互项必须在至少 3/4 validation folds 方向一致，且增量 utility 的 bootstrap 下界 > 0，或只作为 risk overlay 而非 alpha。
- 最佳点与稳健区间中心相差过大时，使用稳健区间中心/简化权重，不使用尖峰最优点。

### Phase 3：仓位映射和执行约束比较（P0）

**目标**：解决饱和、抖动和成本侵蚀，并建立统一 execution contract。

**任务**：

1. 对每个冻结候选权重比较 quantile map、dead-zone softsign、vol-target map、monotone calibrated map。
2. 所有 map 只在 train fit 参数；validation/test 只 transform。
3. 比较 no-trade band、minimum holding、rebalance cadence、asymmetric delta limit。
4. 记录：exposure、near-zero/near-max rate、turnover、trade count、holding duration、cost、gross/net Sharpe、drawdown。
5. 进行成本敏感性：base、2x、4x commission+slippage；必要时加入 spread/market-impact proxy。
6. 确认 `composite_only` 和 advisory candidate 使用相同 map；否则无法解释 overlay 的增量效果。

**输出**：

- `position_map_ablation.csv`
- `execution_constraint_ablation.csv`
- `daily_position_audit.parquet`
- `cost_sensitivity.csv`
- `mapping_decision.md`

**建议初始候选约束**：

- `p_max <= 1.0`
- `max_daily_delta` 先测试 0.05/0.10/0.20
- no-trade band 先测试 0.02/0.05/0.10
- cadence 先测试 1/3/5 trading days
- 不把 `max_single_decision_change` 当作唯一 turnover 控制

**选择原则**：优先选择在 base cost 和 2x cost 下均保持可接受、且 worst-fold 风险不过度恶化的 map，而不是 pooled Sharpe 最高者。

### Phase 4：跨 fold 收益、回撤、换手和稳定性准入（P1）

**目标**：确认 Composite 是可重复的研究对象，而不是单个样本的曲线。

**必须比较**：

- `cash`
- `composite_only`
- `composite_plus_trend`
- `composite_plus_reversion`
- `composite_plus_macro_cap`
- `composite_plus_relative_strength`
- `composite_plus_all_advisories`
- 简化 Composite（等权/无交互/正则权重）
- `SM` / 已冻结参考策略（同成本语义）

**每个 fold 输出**：

- total/net/gross return
- annualized Sharpe、Sortino、volatility
- max drawdown、drawdown duration、recovery time
- daily/monthly win rate
- mean/median/max exposure
- total and daily turnover、trade count、holding duration
- transaction cost、cost/gross return
- beta/upside beta/downside beta
- trigger/fallback/saturation rate
- score-to-return monotonicity and rank IC

**准入建议**：

1. 不以 pooled total return 单独准入。
2. 至少 3/4 validation/test folds 通过收益与风险的预注册门槛。
3. 最差 fold 不得出现数据质量、PIT、成本或审计失败。
4. Advisory 必须相对同 map 的 `composite_only` 在至少一个风险维度改善，同时 total return/Sharpe 降幅受限，且 turnover multiple 受限。
5. 只要 improvement 依赖一个 fold、一个 symbol 或一个极端行情段，状态为 `rejected` 或 `diagnostic_only`。
6. `pending`、`failed` 和 `data_quality_blocked` 不得被汇总为通过。

#### Advisory 策略详细说明

Advisory 策略基于 `core/composite_advisory.py` 实现，遵循"Composite 决定方向，advisory 只减仓或不变"的保守原则。

**实现架构**：

```python
composite_base_position = transform(composite_score)
advisory_multiplier = compute_multiplier(trend, reversion, relative, macro)
final_position = min(base, base * multiplier, max_position)
```

**五种 advisory 策略**：

1. **composite_plus_trend**
   - 角色：趋势确认
   - 信号来源：`momentum_optimized` expert 的归一化信号
   - 触发条件：`trend_confirmation < trend_trigger`（默认 0.50）
   - 行动：`multiplier *= trend_conflict_multiplier`（默认 0.80）
   - 语义：趋势不足时减少 20% 暴露
   - 换手特征：中等（rebalance_cadence = 5 交易日）

2. **composite_plus_reversion**
   - 角色：均值回归警告
   - 信号来源：`mean_reversion` expert 的反向归一化信号
   - 触发条件：`reversion_warning >= reversion_trigger`（默认 0.60）
   - 行动：`multiplier *= reversion_multiplier`（默认 0.75）
   - 语义：检测超买风险，减少 25% 暴露
   - 换手特征：高（rebalance_cadence = 2 交易日）

3. **composite_plus_macro_cap**
   - 角色：宏观风险上限
   - 信号来源：`macro_defensive` expert 的风险缓冲
   - 触发条件：始终生效
   - 行动：`multiplier = min(multiplier, max(macro_cap_floor, macro_risk_cap))`
   - 语义：市场风险升高时动态降低上限，最低保留 `macro_cap_floor`（默认 0.25）
   - 换手特征：中等（rebalance_cadence = 1 交易日）

4. **composite_plus_relative_strength**
   - 角色：相对强度确认
   - 信号来源：`volume_confirmed` expert 的双向信号
   - 触发条件：`relative_strength_confirmation <= -relative_trigger`（默认 -0.25）
   - 行动：`multiplier *= relative_conflict_multiplier`（默认 0.80）
   - 语义：相对弱势时减少 20% 暴露
   - 换手特征：高（rebalance_cadence = 5 交易日）

5. **composite_plus_all_advisories**
   - 角色：综合风险管理
   - 行动：按顺序应用所有 advisory 规则，取最小 multiplier
   - 语义：多重风险过滤，保守叠加
   - 换手特征：最高（各 advisory 独立触发）

**执行约束（Phase 4 统一）**：

- `max_single_decision_change = 0.25`：单日最大变化 25%
- `max_position = 1.0`：绝对上限
- Previous-position bounding：当前决策相对前一日持仓也受 `max_single_decision_change` 约束
- Cost treatment：`ohlcv_gross_charge_once`，1 bps commission + 2 bps slippage

**Advisory 评估标准**：

Phase 4 必须回答以下问题，才能判断 advisory 是否有价值：

1. **风险降维是否有效**：
   - 相对 `composite_only`，advisory 是否降低了 max drawdown？
   - Sortino ratio 是否改善（下行风险控制）？
   - 最差 fold 的回撤是否受控？

2. **收益代价是否可接受**：
   - Sharpe ratio 降幅是否在 10% 以内？
   - Total return 降幅是否在 15% 以内？
   - Win rate 是否保持或改善？

3. **换手成本是否合理**：
   - Turnover multiple 相对 `composite_only` 是否在 5x 以内？
   - Cost-to-gross ratio 是否在 0.50 以下？
   - 净收益是否仍为正？

4. **触发逻辑是否合理**：
   - Trigger rate 是否在 10%-40% 之间（过低无效，过高过度保守）？
   - Fallback rate 是否接近零（数据质量）？
   - Saturation trigger rate 是否低于 90%？

5. **跨 fold 稳定性**：
   - 至少 3/4 folds 通过单 fold gate（Sharpe ≥ 0.3, DD ≤ 30%）
   - 改善方向是否一致（不能一个 fold 改善回撤，另一个 fold 恶化回撤）
   - 最差 fold 是否无 data quality / PIT / audit 失败？

**Advisory 准入门槛（Phase 4 冻结）**：

```text
PASS 条件（所有必须同时满足）：
1. 至少 3/4 folds 满足 single-fold gate:
   - Sharpe ≥ 0.3
   - Max drawdown ≤ 30%
   - Near-max position rate ≤ 90%
2. 相对 composite_only（同 map/cost）：
   - Max drawdown 改善 ≥ 5% OR Sharpe 降幅 ≤ 10%
   - Turnover multiple ≤ 5.0
   - Cost-to-gross ratio ≤ 0.50
3. 最差 fold 无 data quality / PIT / audit 失败
4. Trigger rate 在 [0.10, 0.60] 范围内（过低或过高均为异常）

FAIL 条件（任一触发）：
- 少于 3/4 folds 通过 single-fold gate
- Max drawdown 恶化 > 5% 且 Sharpe 降幅 > 10%
- Turnover multiple > 10.0
- Cost-to-gross ratio > 0.50
- 任一 fold 有 data quality / PIT / audit 失败

BLOCKED 条件（诊断专用，不准入）：
- 改善仅来自单一 fold 的极端表现
- Trigger rate < 5%（advisory 几乎不生效）
- Trigger rate > 80%（advisory 过度保守，接近恒定减仓）
- Fallback rate > 5%（数据质量问题）
```

**输出物（Phase 4）**：

```text
model-test/outputs/composite_stability_phase4/
├── fold_metrics.csv              # 每个 fold × strategy 的 30+ 指标
├── advisory_incremental.csv      # advisory 相对 composite_only 的增量效果
├── admission_summary.csv         # 聚合结果与准入决策
├── phase4_manifest.json          # source lock、config、code hash
├── admission_report.md           # 人类可读的结论
└── advisory_diagnostics/
    ├── trigger_timeseries_{policy}.csv  # 逐日 trigger/multiplier/position
    ├── drawdown_comparison.png          # 回撤对比图
    └── turnover_distribution.png        # 换手分布对比
```

**Phase 4 与 Phase 0/1 的关系**：

- Phase 0/1 已完成初步 60-symbol replay，`composite_plus_reversion` 通过 research admission
- Phase 4 必须在 Phase 2/3 完成后，使用冻结的权重和 map 重新验证
- Phase 0/1 的结论不能直接用于 Phase 4 准入，因为 transform/map 已变更
- Phase 4 是最终的跨 fold 收口，Phase 0/1 是早期诊断证据

**Phase 4 不做的事情**：

- 不重新优化权重或交互项
- 不引入新的 advisory 规则或参数
- 不修改 position map 或 execution constraints
- 不接入 Streamlit 或修改 production 默认策略
- 不把 advisory 用于动态专家组合路径

**Phase 4 必须拒绝的情况**：

- Advisory 相对 baseline 的改善依赖单一 symbol
- Advisory 在高波动期表现好、低波动期表现差（或反之），无稳定性
- Advisory 的 turnover 过高，净收益被成本侵蚀
- Advisory 的 trigger 逻辑与专家信号语义不一致（如 trend advisory 在上涨时减仓）

### Phase 5：US 冻结后复制 CN_A（P1）

**前置**：US Composite map、factor registry、cost ledger 和 admission gate 全部 ready。

**任务**：

- 使用 `MarketFactorContext` 的 explicit benchmark/universe frame。
- 替换所有 SPY/VIX 别名为 market-native factor；不可隐式读取 US macro artifacts。
- 重新做方向、冗余、PIT、权重、map、成本和跨 fold 验证；不把 US 权重直接复制成结论。
- 分市场生成 source lock、factor schema、decision audit 和 admission report。

## 5. 重点验证用例

### 5.1 Saturation regression

构造 score 从 -10 到 +10、不同尺度的因子行，验证：

- map 单调；
- score 平移/尺度变化不会未经注册地改变仓位语义；
- position 不会在绝大多数输入上等于 0 或 1；
- `p_target` 与 `p_exec` 分离；
- no-trade band 不会产生隐形跨 symbol 状态。

### 5.2 Direction regression

对每个因子做 sign flip、permutation、constant 和 lag tests，验证方向注册生效且结果可审计。

### 5.3 PIT regression

- 删除未来日期后，历史日期输出不变；
- benchmark/VIX 缺失日不会使用未来观测；
- ffill 不跨越 source availability cutoff；
- 20 日 future label 不进入 feature frame；
- train fit 参数不被 validation/test 修改。

### 5.4 Cost regression

- gross OHLCV 只扣一次 `turnover * (commission + slippage)`；
- `strategy_return` source path 不重复扣费；
- zero turnover 的成本严格为 zero；
- costs、gross return、net return、equity 可以逐行重建。

### 5.5 Cross-symbol execution regression

在多个 symbol 交错的 frame 上验证 previous position、turnover 和 cadence 按 symbol 隔离；不能沿整张长表使用单一 previous position。

## 6. 计划执行顺序和产物依赖

```text
Phase 0 quality + semantic lock
  -> Phase 1 factor direction/redundancy registry
  -> Phase 2 robust weights/interactions
  -> Phase 3 position map/execution constraints
  -> Phase 4 cross-fold admission
  -> Phase 5 CN_A replication
```

每一阶段只消费前一阶段的 `ready`、hash-verified artifact。任何 `failed`/`pending` source 不得自动降级成零值后继续优化；必须输出明确 fallback reason 或终止该 run。

## 7. 需要特别修复的现有实现点

1. `core/expert_pool_v2.py::_bounded_long()` 当前只做 `tanh(score / temperature)`，必须接入冻结的 score transform 或改为接收已经标准化的 score。
2. `PHASE25_WEIGHTS` 的 `vix_level` 原始尺度不能与 z-score/rank 直接相加；需要在 factor layer 统一变换，或移出 directional Composite。
3. `core/composite_advisory.py` 的 `final = min(base, base * multiplier, max_position)` 只适用于已经正确标定的 long-only base；不能用它掩盖 base 饱和。
4. `decide_frame()` 的 previous-position bounding 需要明确按 symbol 分组的接口；当前单 symbol frame 运行虽然可用，但长表调用必须拒绝或分组。
5. `model-test/phase2_5_advanced_optimization.py` 不能使用 pooled full-sample `score_std` 作为最终部署尺度；应保存每个 fold 的 train-only transform。
6. Phase 1 admission 的 turnover multiple 目前被饱和 baseline 放大，必须在统一 map/cadence 后重算，旧结果只能保留为诊断证据。
7. `ExpertUtilityV4` 的 position 语义是 `[0, 1]` long-only；若研究 signed expert，收益、风险、最大回撤和成本计算必须显式支持 signed position，不能混用解释。

## 8. 最终交付标准

只有同时满足以下条件，才能向另一个窗口建议进入实现或 shadow mode：

- `factor_registry`、PIT contract、source lock 和 cost ledger ready；
- Composite score 不再系统性饱和，position map 单调且可解释；
- 权重和交互项有跨 fold/多 seed/bootstrap 稳定性证据；
- 因子方向、冗余和 Composite beta 风险已量化；
- gross/net return、drawdown、turnover 和 transaction cost 可逐行重建；
- base/2x/4x cost sensitivity 不出现灾难性退化；
- 至少 3/4 fold 通过预注册 gate，且没有 data-quality/PIT/audit failure；
- advisory 相对同口径 `composite_only` 具有稳定风险增量价值；
- 任何 production/Streamlit 接入均另行 review、批准和部署。

在上述条件未全部满足前，结论应保持为 `research_only`，并优先使用修复后的 `composite_only` 作为研究基线，而不是继续叠加 advisory 或动态 gating。
