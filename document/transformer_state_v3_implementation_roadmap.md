# Transformer State v3 实施路线图

> 日期：2026-08-20
> 基于：transformer_state_similarity_diagnosis_and_v3_solution_review_20260820.md
> 状态：待审批
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

---

## 阶段 2：标签与样本重构（Week 2，Day 1-5）

### 目标
构建完整 utility 向量，降低样本重叠

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
- `state_label_panel_v3.parquet`（完整 utility）
- `stride_comparison_report.md`
- 选定的 stride 策略写入 v3 config

### 验收
- 所有 8 个专家 utility 均有有限值
- ambiguous 比例被审计并记录原因分布
- S01-B 的 Train Top-1 q75 显著低于 v2（目标：< 0.995）

---

## 阶段 3：表示学习重构（Week 2-3，Day 6-14）

### 目标
训练能保证余弦空间语义的 encoder

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
- [ ] v2/W18 已冻结，tag 已创建
- [ ] v3 config、output、protocol 文档已建立
- [ ] 新 Test 时间窗口已选定且未被观察
- [ ] 审核员已审阅本路线图并批准

### 阶段 1 完成
- [ ] B01/B02/B03 baseline 已运行
- [ ] Baseline comparison report 已生成
- [ ] 决定：继续 Transformer 或降级到 baseline

### 阶段 2 完成
- [ ] 完整 utility 向量 schema 已验证
- [ ] Ambiguous 比例已审计
- [ ] Stride 实验已完成，策略已选定

### 阶段 3 完成
- [ ] R01-A/B/C/D 消融已完成
- [ ] 至少 3/4 折通过 geometry gate
- [ ] 多随机种子稳定性已验证

### 阶段 4 完成
- [ ] Validation coverage-utility 曲线已生成
- [ ] Primary score、threshold、temperature 已冻结
- [ ] Validation matched utility > baseline

### 阶段 5 完成
- [ ] Test 一次揭盲已执行
- [ ] Admission gate 逐项检查
- [ ] Evidence manifest 已生成

### CN_A W19 完成（可选）
- [ ] CN v3 使用与 US 相同冻结协议
- [ ] CN Test 只揭盲一次
- [ ] 跨市场比较记录在独立报告

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

**立即行动**：
1. 审核员审阅本路线图
2. 批准或提出修改意见
3. 用户确认 W19 处理方案（A/B/C）
4. 创建 v3 工作分支：`git checkout -b transformer-state-v3`

**首周目标**：
- 完成阶段 0（治理与冻结）
- 启动阶段 1（Baseline 建立）
- 生成第一份 baseline comparison report
