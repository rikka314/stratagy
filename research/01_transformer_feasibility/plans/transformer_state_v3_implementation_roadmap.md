# Transformer State v3 实施路线图

> 日期：2026-08-20
> 基于：transformer_state_similarity_diagnosis_and_v3_solution_review_20260820.md
> 状态：Phase 1 实验完成；仅准入 Phase 2 诊断，尚未准入 Phase 3 训练
> 预计周期：4-6 周

---

## 阶段 0：治理与冻结（Week 1，Day 1-2）

### 目标
确保 v2/W18 不可变，建立 v3 独立分支

### 交付物
- [ ] 冻结 W13-W18 manifests（只读验证）
- [ ] 新建 v3 config：`model-test/configs/transformer_state_v3_{us,cn_a}.json`
- [ ] 新建 v3 output：`model-test/outputs/transformer_state_v3_us/`
- [ ] 定义新 Test 时间窗口（建议：2026-06-01 至 2026-07-31，未被任何先前实验观察）
- [ ] 更新 manifest schema version：`3.0.0`
- [ ] 编写 `v3_research_protocol.md`：明确一次揭盲原则

### 验收
- Git tag：`transformer-state-v2-final`
- v3 config 校验脚本通过
- 新旧 output 目录完全隔离

---

## 阶段 1：Baseline 建立（Week 1，Day 3-7）

### 目标
在任何 Transformer 训练前，建立非深度学习 baseline

### 实验清单

#### B01：单日 PCA baseline
- **输入**：决策日 t 的最后一日 28 维特征
- **处理**：Train-only scaler → Train-only PCA → L2 normalize
- **检索**：固定 Train memory，Validation query，Top-15 cosine
- **输出**：neighbor utility 一致性、coverage-quality 曲线、regret

#### B02：20 日摘要 baseline
- **输入**：20 日序列的统计摘要（均值、std、趋势、min/max、前后半段差）
- **处理**：同 B01
- **对比**：是否优于单日？是否优于当前 Transformer？

#### B03：随机邻居
- **输入**：不使用特征
- **处理**：从 Train memory 随机选 15 个
- **目的**：衡量"有状态相似"相对"无状态"的增益下限

### 交付物
- `baseline_comparison_report.md`
- `baseline_artifacts/b01_pca_single_day/`
- `baseline_artifacts/b02_pca_summary/`
- `baseline_artifacts/b03_random/`

### 停止条件
如果 B01/B02 在 Validation 上无法证明邻居 utility 一致性优于 B03，**暂停 Transformer 开发**，重新评估产品假设。

### 实验结果（2026-08-20）

- B01 utility consistency 相对 B03 改善 `+0.017500`，95% CI
  `[0.015764, 0.019229]`，单侧 `p=0.000999`。
- B02 utility consistency 相对 B03 改善 `+0.020940`，95% CI
  `[0.016201, 0.024814]`，单侧 `p=0.000999`。
- 正式一致性停止条件未触发，但实际 Validation query-selected utility
  未改善：B01 相对 B03 为 `-0.003283`，B02 为 `-0.005354`。
- 因此只准入 Phase 2 的 label / stride 重构诊断；Phase 3 训练前必须新增并通过
  预声明的 query utility / regret gate。正式记录见
  `document/acceptance/transformer_state_v3_phase1_baselines_20260820.md`。

---

## 阶段 2：标签与样本重构 + 诊断（Week 2，Day 1-5）

**状态：已完成 D01 诊断；决策为 STOP；L01/S01 不执行**

### 目标（已调整）
**原目标**：构建完整 utility 向量，降低样本重叠

**新增诊断目标**（2026-08-20 完成）：
基于 Phase 1 实验发现（一致性提升 +0.021 但 utility 下降 -0.005），Phase 2 调整为：
1. **诊断优先**：分析为什么邻居更一致但收益更差
2. **多维评估**：不只看单一 future_5d_utility，查看 8 个专家的表现
3. **采样修正**：实验 stride 策略，识别采样偏差
4. **决策分支**：
   - 如果找到并修正问题 → 重新 baseline → 准入 Phase 3
   - 如果确认方法失败 → 停止研究
   - 如果发现多目标有效 → 调整为多目标优化继续

### D01 诊断结果（2026-08-20）

**决策：STOP - 不进入 Phase 3**

**核心发现**：
- PCA 邻居检索显著改善一致性（B01: +0.0175, B02: +0.0209, p<0.001）
- 但 query utility 显著恶化（B01: -0.0033, B02: -0.0054）
- Regret 增加 15-16%（0.0238/0.0241 vs 0.0207 random）
- Expert match rate 提升 5-7%，但不转化为 utility 改善

**诊断结论**：
状态相似性不预测专家 utility。邻居更一致，但一致地更差。这表明：
1. 特征捕捉了某种相似性，但该相似性与未来收益无关
2. 5 日决策窗口可能太短，状态模式无法预测
3. 专家 utility 信号噪声可能超过状态模式信息量

**采样偏差评估**：
虽然 stride=1 可能导致时间聚类，但：
- 一致性改善是真实的（统计显著）
- Utility 恶化也是真实的
- 降低聚类不会改变负向 utility 的符号

Stride=5 可能进一步降低方差，但无法使负 utility 变正。

**详细报告**：`document/phase1_diagnostic_report.md`

### L01：完整 expert utility 向量

**新 schema**：
```python
# state_label_panel_v3.parquet
columns = [
    'date', 'symbol', 'market', 'sequence_id',
    'utility_naive', 'utility_drift', 'utility_sm', 'utility_fsm',
    'utility_best_search', 'utility_ml_filter', 'utility_adaptive_router', 'utility_cash',
    'availability_naive', 'availability_drift', ...,  # 8 个 bool mask
    'best_expert_5d',  # 保留用于对照
    'utility_margin',  # top1 - top2
    'utility_dispersion',  # std across available experts
    'is_ambiguous',  # margin < threshold
    'label_quality'  # ready/ambiguous/unavailable
]
```

**生成逻辑**：
- 对每个 t+1..t+5 窗口，计算每个专家的 source-net utility
- 不删除 ambiguous；标记 `is_ambiguous=True`
- Cash 必须存在且 available=True

### S01：五日 stride 采样

**实验组**：
- S01-A：stride=1（当前）
- S01-B：stride=5（主推荐）
- S01-C：stride=1 + 五日块权重归一化

**对比指标**：
- Train strictly-prior Top-1 相似度分布（预期 S01-B 降低极端集中）
- Validation neighbor utility 一致性（预期 S01-B 不劣于 S01-A）
- Memory 行数与独立日期数

### 交付物
- **D01（已完成）**：`document/phase1_diagnostic_report.md`
- **L01（未执行）**：完整 utility 向量标签生成已跳过
- **S01（未执行）**：stride 采样实验已跳过

### 验收（已完成）
- **D01 验收**：
  - [x] 基于 Phase 1 aggregate 数据完成诊断
  - [x] 一致性 vs utility divergence 分析完成
  - [x] 采样偏差潜在影响评估完成
  - [x] 明确建议路径：**STOP**
  
- **L01/S01 验收（不适用）**：
  - Phase 2 诊断决策为 STOP，L01/S01 不执行

### Phase 2 终止原因

根据 D01 诊断结果，研究在 Phase 2 终止，原因如下：

1. **无检索价值**：PCA baseline 显示状态相似性不预测专家 utility
2. **负向 utility**：两种 PCA 方法均显著差于随机选择（p>0.98）
3. **成本收益分析**：Phase 3 需要完整 utility 向量、Transformer 训练、
   geometry gate、calibration 和 Test admission，在 Phase 1 零价值证据下不合理
4. **替代方案存在**：`adaptive_router_v1` 已提供 regime-aware 专家选择，
   无需状态检索

---

## 阶段 3：表示学习重构（Week 2-3，Day 6-14）

**状态：未执行 - Phase 2 决策为 STOP**

Phase 2 诊断决定不进入 Phase 3 Transformer 训练。原计划的 R01 loss 设计、
geometry gate、消融实验均不执行。

### 原目标（未达到前置条件）
训练能保证余弦空间语义的 encoder

### 未执行原因

Phase 1 baseline 确立：
- 状态特征相似性 ≠ 专家 utility 相似性
- PCA 降维后的检索反而恶化 utility
- 深度学习不能修复特征-目标根本性不对齐

即使 Transformer 学到更好的 embedding geometry，如果底层假设（相似状态 → 相似最优专家）不成立，训练也不会产生有用的检索系统。

---

## 阶段 4：检索校准（Week 3-4，Day 15-21）

**状态：未执行 - Phase 2 决策为 STOP**

---

## 阶段 5：Test 一次揭盲（Week 4-5，Day 22-30）

**状态：未执行 - Phase 2 决策为 STOP**

---

## 阶段 6：CN_A W19 处理（Week 5-6，Day 31-40，可选）

**状态：未执行 - Phase 2 决策为 STOP**

推荐方案 W19-B（诊断 only）在 US Phase 1-2 结果下也不再推荐。CN_A 市场
可能有不同的状态-utility 关系，但在没有 US 正向证据的情况下，不建议投入
CN_A 全量研究资源。

如果未来重新评估状态匹配假设（更长horizon、不同特征、不同市场），可以
将 CN_A 作为独立验证市场。

### R01：Utility regression + ranking

**Loss 设计**：
```python
L_total = (
    lambda_u * HuberLoss(U_pred, U_true, delta=0.5)
    + lambda_r * PairwiseRankingLoss(U_pred, U_true, margin=0.1)
    + lambda_v * VarianceFloorLoss(Z, min_var=0.01)
    + lambda_cov * CovariancePenaltyLoss(Z, off_diag_weight=0.1)
)
```

**超参候选**：
- lambda_u: [1.0]
- lambda_r: [0.5, 1.0, 2.0]
- lambda_v: [0.1, 0.5, 1.0]
- lambda_cov: [0.01, 0.1]

**消融顺序**：
1. R01-A：只有 utility regression
2. R01-B：+ ranking
3. R01-C：+ variance
4. R01-D：+ covariance（推荐 primary）

### Geometry Gate（硬停止条件）

每个 fold 的 Train embedding 必须满足：
- Effective rank ≥ 4.0 / 16
- PC1 variance share ≤ 70%
- 每维 std ≥ 0.01
- Train→Validation centroid shift (L2) < 0.5

**未通过处理**：fold 标记为 `geometry_collapsed`，不进入检索阶段

### 交付物
- 四折 checkpoint：`transformer_state_v3_us/fold_{wf_01..04}/encoder.pt`
- `geometry_report_v3.csv`（包含 effective rank、PC1 share、drift）
- `loss_ablation_comparison.md`

### 验收
- 至少 3/4 折通过 geometry gate
- R01-D 相对 R01-A 在 Validation neighbor utility 一致性上有显著改善
- 多个随机种子（至少 3 个）的 geometry 指标方向一致

---

## 阶段 4：检索校准（Week 3-4，Day 15-21）

### 目标
使用 Validation→Train memory 校准 Top-k 和阈值

### C01：Primary match score 选择

**候选**：
- C01-1：Top-1 max（v2 当前，对照）
- C01-2：Top-5 mean（主推荐）
- C01-3：第 5 近邻（密度辅助）

**评估**：
- Validation matched coverage
- Matched-only utility mean
- Utility regret vs full-run-best
- 对候选数量的敏感性（11 vs 15 vs 20）

### C02：Coverage-aligned threshold

**Validation 目标**：balanced coverage = 35%-40%

**校准流程**：
1. 对每个 Validation query，计算其 Top-5 mean similarity
2. 取所有 Validation query 的 Top-5 mean 的 qX 作为阈值
3. 迭代搜索 qX，使 matched coverage 落在目标区间
4. 同时要求 matched utility > fallback utility baseline

**Test admission 下限**：30%（留 5-10% 漂移缓冲）

### C03：邻居聚合

**当前**：只用硬 best_expert 分组投票

**v3**：完整 utility 加权平均
```python
U_pred_expert_e = sum(w_i * U_i_expert_e) / sum(w_i)
# w_i = softmax(similarity_i / temperature)
# temperature 在 Validation 选择：[0.01, 0.05, 0.1]
```

### 交付物
- `state_retrieval_calibration_v3.csv`（记录每个 qX 的 coverage/utility/regret）
- `selected_primary_score`：Top-5 mean（或经实验选择的其他）
- `selected_threshold_quantile`：qX 值
- `selected_temperature`：softmax 温度

### 验收
- Validation balanced coverage 在 35%-40%
- Validation matched utility > adaptive baseline + margin
- ESS（有效样本量）中位数 ≥ 5

---

## 阶段 5：Test 一次揭盲（Week 4-5，Day 22-30）

### 目标
在新 Test 窗口（2026-06-01 至 2026-07-31）一次性评估

### 执行流程

1. **冻结所有参数**
   - scaler、encoder checkpoint
   - memory bank
   - primary score、threshold、temperature
   - utility aggregation 逻辑
   - fallback 路径

2. **Test 决策**
   - 对每个 Test query，使用冻结 encoder 生成 embedding
   - 查询固定 Train memory
   - 计算 Top-5 mean similarity
   - 与阈值比较，决定 matched/fallback

3. **五日执行**
   - 复用现有 W17 execution 逻辑
   - 记录 position、turnover、return、attribution

4. **Admission 评估**
   - Balanced coverage ≥ 30%（四折均通过）
   - Matched utility > adaptive baseline
   - Drawdown、turnover 不超过容忍度
   - Symbol breadth ≥ 40/60

### 交付物
- `state_match_decisions_v3.parquet`
- `state_execution_daily_v3.parquet`
- `state_execution_summary_v3.csv`
- `transformer_state_v3_evidence_manifest.json`

### Admission Gate

| 指标 | 门槛 | 检查方式 |
|---|---|---|
| Coverage | ≥30% 每折 | 四折独立通过，不看总平均 |
| Matched utility | > adaptive + 0.5% | 年化主动收益 |
| Drawdown | < adaptive × 1.2 | 五日窗口最大回撤 |
| Turnover | < 1.5x | 相对当前 adaptive |
| Symbol breadth | ≥ 40/60 | Test 期间覆盖的独立标的数 |
| Geometry | Pass | 全部折通过 geometry gate |
| Hash consistency | 100% | Source/code/artifact 哈希匹配 |

**Fail-closed 原则**：任一指标未通过，整体 `not_ready`，不进入 W20 admission

---

## 阶段 6：CN_A W19 处理（Week 5-6，Day 31-40，可选）

### 推荐方案：W19-C

**做法**：
- 等待 US v3 冻结并通过 Test admission
- 使用相同 v3 协议（完整 utility、stride=5、R01-D loss、Top-5 mean）
- CN_A 作为独立市场验证
- 预先声明：CN Test 只揭盲一次，不根据 CN 结果回调 US v3

**替代方案**：W19-B（诊断 only）
- 如果 US v3 未通过，CN 可先运行旧 v2 协议
- 目的：验证塌缩/阈值错位是否跨市场
- 不提交 admission，只记录诊断数据

**不推荐**：W19-A（旧协议全量）
- 成本高但无新信息

---

## 资源与时间估算

### 计算资源

| 阶段 | GPU 需求 | CPU 核心 | 内存 | 磁盘 | 预计时间 |
|---|---|---|---|---|---|
| Baseline (B01-B03) | 0 | 16 | 64GB | 50GB | 2-3 天 |
| 标签重构 (L01, S01) | 0 | 32 | 128GB | 100GB | 3-4 天 |
| Encoder 训练 (R01) | 1×V100 | 16 | 64GB | 200GB | 5-7 天 |
| 检索校准 (C01-C03) | 0 | 32 | 128GB | 100GB | 3-4 天 |
| Test 执行 | 0 | 16 | 64GB | 50GB | 2-3 天 |
| CN_A W19-C | 同上 | 同上 | 同上 | 100GB | 7-10 天 |

**总计**：4-6 周（US only），6-8 周（含 CN_A）

### 人力

- 研究员 1 名（全程）
- 工程师 0.5 名（阶段 2-3 支持）
- 审核员 1 名（阶段 0、4、5 验收）

---

## 风险与回退

### 风险 1：Baseline 优于 Transformer

**触发**：B01/B02 在 Validation neighbor utility 上不劣于或优于 R01-D

**处理**：
- 暂停 Transformer 复杂化
- 将 PCA/摘要 baseline 作为 primary 方案
- 重新评估"深度时序编码"的必要性

### 风险 2：Geometry gate 持续失败

**触发**：调整 lambda_v/lambda_cov 后，仍有 >50% 折 effective rank < 4

**处理**：
- 尝试 whitening 后处理（Train-only）
- 如仍失败，降级到 B01/B02
- 记录"Transformer 在当前数据规模下无法学习多维表示"

### 风险 3：Validation coverage 与 utility 不可兼得

**触发**：qX 使 coverage=35% 时，matched utility < fallback

**处理**：
- 检查是否 memory 标签质量问题
- 尝试 same-symbol memory（但需要足够历史）
- 如无解，承认"状态匹配不优于固定策略"，停止准入

### 风险 4：Test admission 失败

**触发**：US v3 Test 未通过 4/4 折 coverage 或 utility 门槛

**处理**：
- 记录完整 failure evidence
- 不再尝试 v4；将研究结论改为：
  > "在当前数据与专家结构下，Transformer 状态匹配未能证明相对 adaptive router 的增量价值。推荐继续使用 adaptive_router_v1 作为 production 默认策略。"
- 保留全部 v3 artifacts 供未来方法参考

---

## 检查清单

### 开工前（P0）
- [x] v2/W18 已冻结，tag 已创建
- [x] v3 config、output、protocol 文档已建立
- [x] 新 Test 时间窗口已选定且未被观察
- [x] 审核员已审阅本路线图并批准

### 阶段 1 完成
- [x] B01/B02/B03 baseline 已运行
- [x] Baseline comparison report 已生成
- [x] 决定：仅进入 Phase 2 诊断；Phase 3 训练暂不准入

### 阶段 2 完成
- [x] D01 诊断已完成（`document/phase1_diagnostic_report.md`）
- [x] 决策：STOP - 不进入 Phase 3
- [x] L01/S01 未执行（条件不满足）
- [x] 研究终止理由已记录

### 阶段 3-6（未执行）
- [ ] Phase 3-6 不执行
- [ ] 原因：Phase 2 决策为 STOP

---

## 研究终止总结

### 终止时点
**Phase 2 诊断（D01）完成后**，日期：2026-08-20

### 终止决策
Phase 1 baseline 证据显示：
- 状态相似性检索改善邻居一致性（+0.018 to +0.021, p<0.001）
- 但显著恶化 query utility（-0.003 to -0.005, p>0.98）
- Regret 增加 15-16%

诊断结论：**状态特征相似性不预测专家 utility 相似性**。

### 核心假设验证结果
**假设**："相似市场状态 → 相似最优专家选择"

**结果**：**假设不成立**

Phase 1 使用两种 PCA baseline（单日特征、20 日摘要特征）验证检索价值，
发现：
1. 检索到的邻居确实更相似（cosine similarity 0.61-0.72 vs 0.0 random）
2. 邻居的 utility 方差更小（std 0.065-0.066 vs 0.082 random）
3. 但邻居的平均 utility 更差（-0.006 vs -0.003 random）
4. 导致 query 选择的专家表现更差（regret 0.024 vs 0.021 random）

这表明：
- 28 维技术指标特征在 20 日窗口内确实捕捉了某种状态模式
- 该模式使得相似状态的专家 utility **更一致**
- 但这种一致性是"一致地差"，而非"一致地好"
- 状态相似性与未来 5 日专家收益的关系是负向或不存在的

### 未来方向建议

如果重新评估状态匹配假设，建议考虑：

1. **更长决策 horizon**
   - 5 日窗口可能太短，状态模式无法体现
   - 尝试 20 日或月度决策窗口
   - 给予状态模式更多时间展现预测力

2. **不同特征集**
   - 当前 28 维技术指标可能不是最优特征
   - 考虑宏观指标、跨市场信号、情绪因子
   - 或完全数据驱动的特征学习（VAE、对比学习）

3. **不同市场验证**
   - CN_A 市场可能有不同的状态-utility 关系
   - 但建议先在其他维度（horizon、特征）验证假设
   - 再投入跨市场研究资源

4. **专家稳定性审计**
   - 如果专家 utility 本身在相似状态下高度不稳定
   - 检索系统无法工作
   - 需先确认专家信号是否足够稳定可预测

5. **替代问题框架**
   - 当前是"检索历史相似状态 → 复用其专家选择"
   - 可尝试"预测当前状态的专家表现 → 直接选择"
   - 或"状态 → 风险度量"而非"状态 → 专家"

### 生产影响

**无变更**。

- `adaptive_router_v1` 保持为默认策略
- Streamlit 单股 workflow 的 regime="adaptive_router_v1" 路径不变
- W18 evidence 维持 `not_ready` 状态
- 不接入任何 Transformer state matching 到线上

### 交付物清单

Phase 1-2 完成的输出：

1. **Phase 1 Baseline Artifacts**
   - 路径：`model-test/outputs/transformer_state_v3_us/baseline_artifacts/`
   - 内容：12 个 method-fold 完整输出（B01/B02/B03 × wf_01/02/03/04）
   - 包含：embeddings、neighbors、query metrics、coverage-quality curves
   - Evidence manifest：76 artifacts，SHA-256 verified

2. **Phase 1 Reports**
   - `baseline_comparison.csv`：汇总统计
   - `baseline_comparison_report.json`：完整结果
   - `baseline_comparison_report.md`：可读报告
   - `baseline_statistical_tests.csv`：bootstrap 检验
   - `baseline_evidence_manifest.json`：artifact 清单

3. **Phase 1 Acceptance**
   - `document/acceptance/transformer_state_v3_phase1_baselines_20260820.md`
   - 正式验收记录，包含决策逻辑和统计证据

4. **Phase 2 Diagnostic**
   - `document/phase1_diagnostic_report.md`
   - 完整诊断分析和 STOP 决策理由

5. **Implementation Artifacts**
   - `model-test/model_test/transformer_state_diagnostic.py`：诊断模块
   - `model-test/run_diagnostic_phase2.py`：诊断运行脚本
   - `tests/test_transformer_state_diagnostic.py`：单元测试

### 归档建议

1. **Git Tag**
   - 创建 `transformer-state-v3-phase2-final` tag
   - 标记研究终止时点

2. **Evidence 保留**
   - 保留全部 Phase 1-2 artifacts（约 50-100 MB）
   - 作为"状态匹配不工作"的证据
   - 未来类似研究可参考

3. **代码保留**
   - Phase 1-2 代码保留在主分支
   - `transformer_state_diagnostic.py` 可供未来诊断参考
   - Phase 3+ 未实现的模块不创建

### 资源消耗

**实际消耗**（Phase 1-2）：
- 人力：研究员 0.5 周
- 计算：CPU-only，约 2-3 天
- 存储：~100 MB artifacts

**节省资源**（Phase 3-6 未执行）：
- 人力：研究员 3-4 周
- 计算：GPU 5-7 天（R01）+ CPU 5-7 天（C01-C03, Test）
- 存储：~500 MB（encoder checkpoints + Test execution）

**总结**：Phase 1-2 early stop 节省了 80%+ 的计划资源投入。

---

## 附录：与现有系统的接口

### 可复用的模块

| 模块 | 路径 | 用途 | 修改需求 |
|---|---|---|---|
| Exact-daily replay | `model_test/exact_daily_replay.py` | 生成专家日收益 | 无，直接复用 |
| Walk-forward split | `model_test/transformer_state_model.py::create_walk_forward_splits` | 时间切分 | 扩展支持 v3 label schema |
| Execution engine | `model_test/transformer_state_execution.py` | 五日窗口执行 | 扩展 decision schema（增加 utility 向量） |
| Turnover audit | `model_test/transformer_state_execution.py::_verify_turnover` | 换手重建 | 无，直接复用 |

### 需要新建的模块

| 模块 | 路径 | 用途 |
|---|---|---|
| Baseline runner | `model_test/model_test/transformer_state_baseline.py` | 运行 PCA/摘要 baseline |
| Utility label builder | `model_test/model_test/transformer_state_label_v3.py` | 生成完整 utility 向量 |
| Utility loss | `model_test/model_test/transformer_state_losses.py` | 实现 Huber + Ranking + Variance + Cov |
| Geometry gate | `model_test/model_test/transformer_state_geometry.py` | 计算 effective rank、PC1、drift |
| Retrieval calibration | `model_test/model_test/transformer_state_calibration.py` | Validation→Train threshold 校准 |

---

## 下一步

**研究已终止，无下一步行动。**

### 完成的工作

1. ✅ Phase 0：v2 冻结，v3 config 建立
2. ✅ Phase 1：三种 baseline（B01/B02/B03）在 Validation 上完整评估
3. ✅ Phase 2：D01 诊断分析，明确 STOP 决策

### 建议的归档步骤

1. **Git 操作**
   ```bash
   git add -A
   git commit -m "docs(transformer-state-v3): complete Phase 2 diagnostic, decision: STOP
   
   Phase 1 baselines showed neighbor consistency improved (+0.018 to +0.021, p<0.001)
   but query utility degraded (-0.003 to -0.005, p>0.98) vs random. Phase 2 diagnostic
   confirmed state similarity does not predict expert utility. Research terminates at
   Phase 2; Phase 3-6 not executed. Production unaffected.
   
   - Phase 2 diagnostic: document/phase1_diagnostic_report.md
   - Roadmap updated with STOP decision and rationale
   - L01/S01 not executed (condition not met)
   - Phase 3-6 not executed (no retrieval value evidence)
   
   Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
   
   git tag -a transformer-state-v3-phase2-final -m "Transformer State v3 research terminated at Phase 2 diagnostic"
   ```

2. **Evidence 保留**
   - 保留 `model-test/outputs/transformer_state_v3_us/baseline_artifacts/`
   - 作为负向结果的完整证据
   - 未来参考或审计时可用

3. **文档归档**
   - `document/phase1_diagnostic_report.md`：诊断结论
   - `document/acceptance/transformer_state_v3_phase1_baselines_20260820.md`：Phase 1 验收
   - `document/transformer_state_v3_implementation_roadmap.md`：本文件（已更新终止状态）

4. **代码清理（可选）**
   - `transformer_state_diagnostic.py` 保留，可供未来诊断参考
   - Phase 3-6 的占位模块（如有）可删除
   - Phase 1-2 测试保留

### 知识传递

**关键经验教训**：

1. **Early baseline 的价值**
   - Phase 1 non-deep-learning baseline 用 3 天时间发现了核心问题
   - 避免了 4-6 周 Transformer 训练的盲目投入
   - Baseline-first 策略在研究设计中证明有效

2. **Consistency ≠ Utility**
   - 检索系统可以改善"邻居一致性"
   - 但一致性不等于"一致地好"
   - 需要直接测量 utility/regret，而非仅看相似度指标

3. **Feature-target alignment 是前提**
   - 再复杂的模型也无法修复特征与目标的根本性不对齐
   - 状态特征未能捕捉到与专家 utility 相关的信息
   - 需先验证特征-目标关系，再投入模型复杂化

4. **Negative results 也有价值**
   - 证明"什么不工作"同样重要
   - 完整记录 Phase 1-2 证据，供未来参考
   - 避免重复相同错误

### 后续研究方向（如果重启）

如果未来重新评估状态匹配假设，建议：

1. **更改问题设定**
   - 不是"检索历史相似状态"
   - 而是"预测当前状态各专家表现"
   - 直接建模 state → expert_utilities 的回归/排序

2. **更长时间 horizon**
   - 当前 5 日决策窗口可能太短
   - 尝试 20 日或月度
   - 但需权衡换手成本

3. **专家稳定性前置验证**
   - 先确认专家 utility 在相似条件下是否稳定
   - 如果专家本身不稳定，检索无法工作
   - 可能需要更稳定的目标（如 Sharpe ratio、win rate）

4. **CN_A 独立验证**
   - 在 US 负向结果下，CN_A 全量研究不优先
   - 但 CN_A 可作为快速验证市场（如果改变 horizon/特征）
   - 跨市场 meta-analysis 可能揭示稳健模式

---

## 附录：研究设计回顾

### 什么做对了

1. **Baseline-first 策略**
   - Phase 1 PCA baseline 成功发现核心问题
   - 成本低、速度快、结论明确
   - 避免了盲目深度学习

2. **Pre-registered 停止条件**
   - Phase 1 明确定义 consistency gate
   - Phase 2 设计了诊断分支逻辑
   - 决策透明，避免 p-hacking

3. **严格的 Train-only fitting**
   - Scaler、PCA 均只在 Train 上拟合
   - Validation 严格作为 query 角色
   - 避免 data leakage

4. **完整的统计检验**
   - 1,000 次 bootstrap，paired date-cluster
   - 95% CI 和单侧 p-value
   - 去重 split signature
   - 结论稳健

### 什么可以改进

1. **Per-expert decomposition 未在 Phase 1 完成**
   - Phase 1 只记录了 aggregate 8-expert utility
   - Phase 2 诊断需要 per-expert 数据才能完全分解
   - 如果 Phase 1 就记录每个专家的 neighbor utility，诊断更精确

2. **Sampling bias 未在 Phase 1 直接测试**
   - Phase 1 使用 stride=1 的 v2 panel
   - 如果同时运行 stride=5 baseline，可直接比较
   - 但鉴于最终 STOP 决策，这不影响结论

3. **CN_A 并行验证未启动**
   - 原计划 US 与 CN_A 并行
   - 实际 CN_A 仍 pending
   - 但 US 负向结果下，CN_A 全量投入不合理

4. **更长 horizon 未探索**
   - 当前假设 5 日 horizon
   - 如果预先测试 20 日 horizon baseline，可能发现不同结论
   - 但这需要额外 utility label 生成

### 设计的合理性

**研究设计整体合理**。

- Phase 1-2 的 early diagnostic 设计达到了目标
- 用最小成本（3 天 + ~100 MB）验证了核心假设
- 避免了 Phase 3-6 的大规模投入（4-6 周 + GPU + ~500 MB）
- 决策逻辑清晰，证据完整，可追溯

如果重启类似研究，建议：
- 保持 baseline-first 策略
- 在 Phase 1 记录更细粒度数据（per-expert）
- 预先探索多个 horizon（5/10/20 日）
- 并行测试 stride 采样（如果资源允许）

---

## 最终声明

**Transformer State v3 研究于 2026-08-20 在 Phase 2 诊断后正式终止。**

- Phase 1 baseline 确立：状态相似性不预测专家 utility
- Phase 2 诊断确认：无检索价值证据，不进入 Phase 3
- Phase 3-6 不执行
- 生产系统无变更，`adaptive_router_v1` 保持默认
- 全部证据已归档，供未来参考

研究结论：**在当前特征、horizon 和专家结构下，基于状态检索的专家选择未能证明相对 adaptive router 的增量价值。**
