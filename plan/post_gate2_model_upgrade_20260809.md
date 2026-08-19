# Gate 2 后下一代策略模型改进计划

> 制定日期：2026-08-09  
> 前置条件：Gate 2 已通过，现有双市场研究结果、报告字段和发布版本已冻结。  
> 核心方向：从“单策略参数搜索 / 状态下硬切换”升级为“不确定性感知的动态专家组合”。

## 1. 总体结论

下一代主模型采用 **Regime-aware Mixture of Experts（动态混合专家，MoE）**：

1. 保留现有 SM、FSM、搜索模型、ML Filter、基线和 Adaptive Router，不推倒重写。
2. 把现有模型视为候选专家，由 LightGBM 门控模型预测各专家在当前市场环境下的未来风险调整效用。
3. 将预测效用转换为受约束的软权重，并加入现金专家、权重平滑、换手约束和不确定性收缩。
4. MoE 稳定后先测试 Hedge / Exponentiated Gradient 在线专家加权；Contextual Bandit 只作为后续对照实验。
5. PPO / SAC 等深度强化学习不进入近期主线，仅在数据规模、模拟真实性和 MoE 基线成熟后重新评估。

## 2. 发布线与研究线隔离

### 2.1 2026-08-15 至 2026-08-23：保护当前交付

- Gate 2 后的发布分支只允许修复 P0/P1 缺陷。
- 8 月 17 日冻结 RC、ZIP、SHA-256 和回滚包。
- 8 月 18–22 日优先完成项目介绍、演示视频、材料数字溯源与提交检查。
- 下一代模型只允许进行方案设计、数据 contract 设计和只读分析，不接入线上 workflow。

### 2.2 2026-08-24 起：独立研究分支

- 建议分支：`codex/post-gate2-dynamic-ensemble`。
- 新模型首先只存在于 `model-test`，不得直接改变线上默认策略。
- 通过研究准入门槛后，再分阶段接入 `core`、单股 workflow 和评估页。

## 3. 目标架构

```text
行情 / 指标 / 市场状态
        |
        +--> 专家 1：SM
        +--> 专家 2：FSM
        +--> 专家 3：Best Search
        +--> 专家 4：ML Filter
        +--> 专家 5：Adaptive Router
        +--> 专家 6：基线
        +--> 专家 7：Cash
                        |
                        v
             LightGBM 门控模型
             预测各专家未来效用
                        |
                        v
           Softmax + 风险与权重约束
                        |
                        v
                最终目标仓位
```

第一版不应把所有高度相关的搜索变体全部放入专家池。先从 Window 3B 中选择 6–8 个行为差异明显、数据完整且滚动表现稳定的代表专家，防止重复专家稀释权重或制造虚假多样性。

## 4. 分阶段执行计划

### Phase A：冻结基线与研究 contract（2–3 天）

> 实现状态（2026-08-12）：Phase-A contract、双市场配置、三项对照和可追溯 baseline materializer 已完成；验收记录见 `document/acceptance/post_gate2_model_upgrade_phase_a_20260812.md`。被 Git 忽略的源 run 不在当前 checkout 时会明确保持 `pending`，不会伪造研究结果。

**目标：** 确保以后所有提升都能与同一套 Gate 2 结果公平比较。

任务：

1. 冻结 US / CN_A 的 Window 3B 与 full-run 输出、config、seed、代码版本和数据 SHA-256。
2. 冻结三个主要对照：
   - 训练期选择的最佳单一专家；
   - 等权专家组合；
   - 当前 `adaptive_router_v1` 硬路由。
3. 冻结收益口径：
   - 若使用 `strategy_return`，它已代表扣费后净收益，不再重复扣交易成本；
   - 若使用 gross return，则成本只扣一次，并在字段名中明确标记。
4. 冻结主预测周期为 20 个交易日，5 日和 60 日只作为消融实验。
5. 冻结 US / CN_A 分市场训练为主，跨市场联合模型只作为额外实验。

产出：

- `document/interfaces/dynamic-ensemble-research.md`
- `model-test/configs/moe_baseline_us.json`
- `model-test/configs/moe_baseline_cn_a.json`
- 基线结果与数据 manifest

完成标准：同一命令、相同 seed 和冻结数据可重现基线；所有收益均能确认是否已扣成本。

### Phase B：构建无泄漏的专家逐日面板（3–5 天）

> 实现状态（2026-08-12）：Phase-B 面板 materializer、逐日 simulation export、point-in-time 特征、20 日 future utility 标签、purged walk-forward/embargo split、source lineage、质量报告与缺失专家 unavailable contract 已完成；验收记录见 `document/acceptance/post_gate2_model_upgrade_phase_b_20260812.md`。当前仍只存在于 `model-test`，未接入线上 workflow。

**目标：** 把 3B 的策略输出转成门控模型可训练的数据。

建议每行表示：`date × symbol × market × expert_id`。

输入字段：

- 日期、股票、市场、专家 ID；
- 只使用当日或更早可获得的 adaptive regime 特征；
- 各专家当日 `target_position`、近期净收益、回撤、换手和稳定性；
- 新闻特征只能使用已完成交易日滞后对齐的数据；
- 市场代理、波动率、趋势、相关性、流动性等上下文。

标签字段：

```text
future_utility
  = future_net_return
  - lambda_downside * future_downside
  - lambda_turnover * future_turnover_penalty
```

交易成本若已包含在 `future_net_return` 中，不再单列重复扣除。

必须实现的检查：

- 标签窗口不能进入特征窗口；
- 训练样本不能跨越 train / validation / test 边界；
- 使用 purged walk-forward，并在相邻窗口之间设置至少一个预测周期的 embargo；
- 当某专家缺失或失败时显式记录 `unavailable`，不得静默填入优秀结果；
- 每个样本能回溯到原始 run、模型、股票和日期。

产出：

- `expert_day_panel.parquet`
- `expert_panel_manifest.json`
- 数据质量报告：缺失率、专家覆盖率、标签分布、市场和状态分布
- 数据泄漏单元测试

完成标准：随机抽查样本可逐日还原；未来数据泄漏测试全部通过。

### Phase C：LightGBM Soft-Gating MoE v1（4–6 天）

> 实现状态（2026-08-16）：研究线实现已完成：`model-test/model_test/dynamic_ensemble.py` 与 `run_dynamic_ensemble.py` 严格消费 ready Phase-A/B source lock，分别训练无状态与 regime-aware LightGBM 长表门控，输出五类计划 artifact、特征重要性、三项冻结对照、权重变化/降级原因。单一风险专家上限 40%，Cash 强制可用，缺失专家重归一化，指数平滑在权重约束前执行。Phase-B 默认 validation/test 段调整为 40 个交易日，确保每段至少容纳一个完整 20 日标签窗口；purge/embargo 仍为 20 日。US 已完成 Phase 3B 全量实验；CN_A 全量实验未完成。当前实证还被旧 `deans_window3b_us` 缺少 `data.snapshot_sha256`（且无冻结快照）阻塞，严格命令拒绝生成伪造结果；未接入线上 workflow。

**目标：** 建立最小可用、可解释的动态专家组合。

建模步骤：

1. 用 LightGBM 回归各专家未来 `utility`；第一版可使用长表模型，将 `expert_id` 编码为分类特征。
2. 对同一日期、股票下各专家的预测分数做 softmax：

   ```text
   weight_k = softmax(predicted_utility_k / temperature)
   ```

3. 加入以下硬约束：
   - 单一风险专家最大权重建议 40%；
   - 权重之和必须等于 1；
   - Cash 始终可用；
   - 缺失专家权重自动重新归一化；
   - 使用指数平滑或最小再平衡阈值减少权重抖动。
4. 最终仓位：

   ```text
   final_target_position
     = sum(expert_weight_k * expert_target_position_k)
   ```

5. 输出特征重要性、每期专家权重、权重变化原因和 fallback 原因。

必须比较：

- 最佳训练期单一专家；
- 等权组合；
- `adaptive_router_v1`；
- 无状态特征的 MoE；
- 完整 Regime-aware MoE。

产出：

- `moe_model.pkl`
- `moe_feature_schema.json`
- `moe_daily_weights.parquet`
- `moe_summary.csv`
- `moe_report.md`

完成标准：模型只使用时点可得数据；权重和仓位约束始终成立；缺失模型时可以安全降级。

### Phase D：风险与不确定性感知 MoE v2（3–5 天）

> 实现状态（2026-08-16）：研究线实现已完成：`model-test/model_test/dynamic_ensemble_v2.py` 与 `run_dynamic_ensemble_v2.py` 只消费 ready 且 hash-verified 的 Phase-A/B/C source lock。每个 purged walk-forward fold 分别训练 lower-quantile / median LightGBM gate，记录保守分数、fold-train OOD z-score、三类降级触发、权重 / 换手 / 持仓 / 回撤风险状态；正常换仓强制执行单专家权重变化和等权标的聚合换手上限，安全降级、缺失专家与 drawdown 去风险仅可为降低风险绕过限制且会记录原因。输出校准、temperature/cap/smoothing 消融、v1/v2 对照和完整 manifest；未接入线上 workflow。真实实证仍等待与 Phase C 相同的重新冻结 source run，严格命令不会生成伪造结果。

**目标：** 避免门控模型对不可靠的高分预测过度下注。

任务：

1. 使用 LightGBM quantile regression 预测效用的低分位数和中位数。
2. 将门控分数调整为：

   ```text
   conservative_score
     = predicted_median_utility
     - gamma * uncertainty_width
   ```

3. 当所有专家置信度低、预测分歧过大或输入超出训练分布时：
   - 增加 Cash 权重；或
   - 收缩到等权组合；或
   - 回退到当前 adaptive router。
4. 增加组合级约束：
   - 最大组合换手；
   - 最小持仓持续期；
   - 最大单日权重变化；
   - 回撤触发的风险缩放。
5. 对 softmax temperature、最大专家权重和权重平滑强度做消融。

产出：

- 不确定性校准报告
- 风险约束消融矩阵
- 降级路径测试
- MoE v1 / v2 对比报告

完成标准：风险控制不是只改善样本内曲线；扣费后的换手、回撤和尾部损失至少有一项稳定改善，且收益不出现不可接受退化。

### Phase E：在线专家加权（4–6 天）

> 实现状态（2026-08-16）：研究线实现已完成：`model-test/model_test/dynamic_ensemble_online.py` 与 `run_dynamic_ensemble_online.py` 严格消费同市场、hash-verified 的 ready Phase-D source（显式 Phase-C 兼容回退仅限研究），以冻结 soft-MoE 初始权重逐日回放 Hedge / EG 完整反馈更新。固定/波动率自适应学习率、遗忘因子、Cash、40% 风险专家上限、15% 常规单日权重变化上限、缺失专家安全退出和固定中点漂移恢复测量均可追溯。输出在线权重、汇总、漂移、对照、报告和 manifest；未接入 Streamlit。真实 US / CN_A 实证仍受 Phase-A/B source-lock 阻塞，严格命令不会生成伪造结果。

**目标：** 让策略权重能够根据新近表现逐步更新，应对市场漂移。

优先实现：

- Hedge；
- Exponentiated Gradient；
- 带遗忘因子的滚动更新。

优先于 Contextual Bandit 的原因：系统可以在后台同时计算所有专家的影子收益，因此每个交易日结束后通常能观察所有专家表现，属于“完整反馈的专家问题”，不必假设只能看到被选策略的奖励。

实验内容：

1. LightGBM MoE 权重作为在线算法初始权重。
2. 使用扣费后专家收益更新权重。
3. 比较固定学习率、波动率自适应学习率和遗忘因子。
4. 限制单日权重变化，避免在线算法追涨杀跌。
5. 设计市场结构突变测试，观察恢复速度。

产出：

- 在线权重轨迹
- 市场漂移响应实验
- Soft MoE、Hedge 和 EG 对比报告

完成标准：在线更新必须在多个滚动窗口中提高适应速度，而不是只追随最近的幸运赢家。

### Phase F：Contextual Bandit 对照实验（可选，5–7 天）

> 实现状态（2026-08-16）：研究线实现已完成：`model-test/model_test/dynamic_ensemble_bandit.py` 与 `run_dynamic_ensemble_bandit.py` 严格消费同市场、hash-verified 的 ready Phase-E source，并重新验证 Phase-A/B panel lock。每个已约束的 Phase-E allocation 是一个 action，Cash 始终可选；LinUCB / contextual Thompson Sampling 只用所选 action 的下一时点净收益更新，未选 action 的收益仅用于明确标记为 evaluation-only 的漂移恢复测量。输出 selected-action decision trace、收敛、汇总、对照、后验状态、报告和 manifest；未接入 Streamlit。真实 US / CN_A 实证仍受上游 Phase-A/B source-lock 阻塞，严格命令不会生成伪造结论。

**启动条件：** Phase E 通过，且确实存在只能观察实际动作奖励的部署场景。

实验顺序：

1. LinUCB；
2. Contextual Thompson Sampling；
3. Neural Contextual Bandit 仅在前两者表现不足且数据量足够时尝试。

对照重点：

- 探索造成的真实交易成本；
- 收敛速度；
- 状态变化后的恢复能力；
- 与完整反馈在线专家算法相比是否有额外价值。

停止条件：若 Bandit 在扣费后不能稳定优于 Hedge / EG，或探索显著增加回撤与换手，则保留为研究消融，不进入产品。

### Phase G：产品化接入（4–6 天）

**启动条件：** Phase C–E 至少一个版本通过研究准入门槛。

建议模块边界：

- `core/dynamic_ensemble.py`：特征校验、门控预测、权重约束与 fallback；
- `model-test/model_test/expert_panel.py`：逐日专家面板；
- `model-test/model_test/dynamic_ensemble.py`：离线训练和 walk-forward 评估；
- `ui/single_stock_workflow.py`：只负责消费已冻结 artifact，不在 UI 现场训练；
- `ui/model_evaluation.py`：展示结论、权重轨迹、不确定性和降级原因。

产品化步骤：

1. 先作为单股 workflow 的非默认实验选项。
2. artifact 缺失、损坏、schema 不匹配时自动回退到 `adaptive_router_v1`。
3. 增加模型版本、训练范围、数据哈希和生成时间展示。
4. 完成单股、研究页、HTML 导出和双语文案。
5. 经过线上 shadow mode 后，再讨论是否成为默认 regime 模型。

完成标准：新模型关闭时旧结果完全不变；artifact 异常不会导致页面失败；每个推荐权重都能回溯到模型版本和输入时间。

## 5. 研究准入门槛

新模型不得因为单一指标或单一股票表现好就进入线上。建议至少满足：

1. **无泄漏：** purged walk-forward、embargo 和时点可得性测试全部通过。
2. **净收益口径：** 所有主要结论均扣除相同市场成本，且无重复扣费。
3. **跨窗口稳定：** 至少 3/4 rolling windows 不劣于当前 adaptive router，不能只靠一个窗口贡献全部提升。
4. **横截面稳定：** 改善不能只集中在极少数股票；需报告改善股票比例、中位数变化和尾部失败案例。
5. **风险约束：** 最大回撤不能出现明显恶化；若收益提高来自显著加杠杆或高换手，不予晋级。
6. **换手约束：** 组合换手原则上不超过 adaptive router 的 1.25 倍；超过时必须证明扣费后仍有稳定增益。
7. **双市场诚实结论：** 可以只在一个市场晋级，但必须明确标为市场专属模型，不能包装成跨市场通用胜出。
8. **可复现：** config、seed、数据快照、代码版本、模型 artifact 和报告完整。
9. **可降级：** 模型不可用时能够回退到当前稳定路径。

建议把“Sharpe 提高 0.10”或“最大回撤降低 10%”作为值得关注的效果量，而不是唯一硬门槛；最终应结合置信区间、滚动窗口和股票横截面共同判断。

## 6. 必须覆盖的测试

- 标签窗口越界和未来特征泄漏；
- 净收益与交易成本是否重复扣除；
- 专家权重非负、和为 1、单专家不超过上限；
- Cash expert 始终存在；
- 专家缺失、NaN、预测异常和 artifact 损坏；
- softmax 极端分数的数值稳定性；
- 固定 seed 的可复现性；
- US / CN_A 市场隔离；
- 旧 config、旧报告和旧 workflow 行为不变；
- 回撤、换手和交易成本指标可追溯到逐日结果。

## 7. 推荐优先级与预计周期

| 优先级 | 阶段 | 预计时间 | 是否进入近期主线 |
|---|---|---:|---|
| P0 | Phase A：基线与 contract | 2–3 天 | 是 |
| P0 | Phase B：专家逐日面板 | 3–5 天 | 是 |
| P0 | Phase C：LightGBM MoE v1 | 4–6 天 | 是 |
| P1 | Phase D：风险与不确定性 | 3–5 天 | 是 |
| P1 | Phase E：Hedge / EG 在线加权 | 4–6 天 | 研究通过后 |
| P2 | Phase F：Contextual Bandit | 5–7 天 | 对照实验 |
| P1 | Phase G：产品化接入 | 4–6 天 | 通过准入门槛后 |
| P3 | PPO / SAC | 暂不估时 | 否 |

完整路线预计 4–6 周。最小可验证闭环是 Phase A–C，约 2 周；完成该闭环后应先评审实验结果，再决定是否继续 Phase D–G。

## 8. 每阶段决策点

```text
Gate 2 / RC 冻结
    |
    v
Phase A-B：数据是否无泄漏且可复现？
    | 否 -> 修复数据，不训练模型
    v 是
Phase C：MoE 是否稳定优于硬路由/等权？
    | 否 -> 保留研究结论，停止产品化
    v 是
Phase D：不确定性控制是否降低尾部风险？
    | 否 -> 使用 MoE v1，不强加复杂层
    v 是
Phase E：在线更新是否有额外价值？
    | 否 -> 固定使用离线 MoE
    v 是
Phase G：先 shadow mode，再决定是否设为默认
```

## 9. 明确暂缓事项

- 不立即使用 Transformer / LSTM 直接预测价格。
- 不使用随机 train/test split。
- 不在 UI rerun 时现场训练门控模型。
- 不为了得到更好曲线反复修改测试窗口、成本或胜出规则。
- 不在 MoE 基线尚未稳定前引入 PPO / SAC。
- 不让新研究改动污染 Gate 2、RC 或 8 月 23 日提交版本。
