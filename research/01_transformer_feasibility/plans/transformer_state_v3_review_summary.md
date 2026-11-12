# Transformer State v3 审查总结与补充建议

> 日期：2026-08-20
> 审查对象：transformer_state_similarity_diagnosis_and_v3_solution_review_20260820.md
> 审查员：Claude Code
> 状态：待用户最终批准

---

## 一、总体评价

### GPT 诊断报告的质量

**评级：优秀（A）**

该报告展现了以下优点：

1. **诊断准确**：正确识别了 5 个核心根因（标签退化、表示塌缩、样本重叠、校准错位、目标错配）
2. **证据充分**：所有结论均有 artifact 数据支撑，可复算
3. **方案全面**：列出 38 个候选解决方案，覆盖标签、模型、检索、校准各层
4. **风险意识**：明确区分"必须修复"与"可选研究"，设置硬停止条件
5. **研究诚信**：强调 v2/W18 不可变，新 Test 一次揭盲，禁止事后调参

### 主要不足

1. **实施路线图不够具体**：缺少明确的周计划、交付物清单和检查点
2. **模块接口未明确**：未说明哪些现有代码可复用，哪些需要重写
3. **停止条件模糊**：虽然提到"baseline 先行"，但未明确何时放弃 Transformer
4. **CN_A W19 决策悬置**：三个选项都没有明确推荐优先级

**上述不足已在 `transformer_state_v3_implementation_roadmap.md` 中补充。**

---

## 二、对套餐 B 的补充建议

### 补充 1：Baseline 必须作为硬门槛

**原报告遗漏**：虽然提到 PCA/摘要 baseline，但未明确其作为"Transformer 准入门槛"的地位。

**补充建议**：

在阶段 1 完成后，必须回答：

| 问题 | 通过标准 | 未通过处理 |
|---|---|---|
| PCA 邻居 utility 是否优于随机？ | p < 0.05，bootstrap 1000 次 | 停止整个研究，重新评估产品假设 |
| Transformer 是否优于 PCA？ | Validation regret 改善 >10% | 降级到 PCA baseline，不再训练 Transformer |
| Top-5 mean 是否优于 Top-1？ | Coverage-utility 曲线面积更大 | 保留 Top-1，但必须重新校准阈值 |

**理由**：

- 如果简单 PCA 已经足够，继续投入 Transformer 是浪费
- 如果 PCA 也不行，说明"状态相似检索"假设本身有问题

### 补充 2：Geometry Gate 的具体实现

**原报告建议**：effective rank ≥ 4/16，PC1 ≤ 70%

**补充细节**：

```python
def check_geometry_gate(embeddings: np.ndarray, fold_id: str) -> dict:
    """
    Args:
        embeddings: (N, 16) 中心化后的 embedding
    
    Returns:
        {
            'passed': bool,
            'effective_rank': float,
            'pc1_variance_share': float,
            'min_dim_std': float,
            'reason': str  # 失败原因
        }
    """
    # 1. 有效秩
    cov = np.cov(embeddings.T)
    eigenvalues = np.linalg.eigvalsh(cov)
    eigenvalues = eigenvalues[eigenvalues > 0]
    eff_rank = (eigenvalues.sum() ** 2) / (eigenvalues ** 2).sum()
    
    # 2. PC1 方差占比
    pca = PCA(n_components=16)
    pca.fit(embeddings)
    pc1_share = pca.explained_variance_ratio_[0]
    
    # 3. 每维最小 std
    min_std = embeddings.std(axis=0).min()
    
    # 4. 判断
    passed = (eff_rank >= 4.0) and (pc1_share <= 0.70) and (min_std >= 0.01)
    
    if not passed:
        reason = []
        if eff_rank < 4.0:
            reason.append(f"effective_rank={eff_rank:.2f} < 4.0")
        if pc1_share > 0.70:
            reason.append(f"PC1={pc1_share:.2%} > 70%")
        if min_std < 0.01:
            reason.append(f"min_std={min_std:.4f} < 0.01")
        reason = "; ".join(reason)
    else:
        reason = "passed"
    
    return {
        'passed': passed,
        'effective_rank': eff_rank,
        'pc1_variance_share': pc1_share,
        'min_dim_std': min_std,
        'reason': reason
    }
```

**使用方式**：

- 每个 fold 训练完成后，立即检查 Train embedding
- 未通过的 fold 标记为 `geometry_collapsed`，不进入检索阶段
- 如果 4 折中 >2 折失败，停止实验，调整 loss 权重或降级到 baseline

### 补充 3：Loss 权重的 Validation 搜索空间

**原报告建议**：lambda_r, lambda_v, lambda_cov 各有 2-3 个候选

**补充细节**：

```python
# 预注册的超参网格（Validation 前冻结）
LOSS_WEIGHT_GRID = [
    # 只有 utility regression（消融基线）
    {'lambda_u': 1.0, 'lambda_r': 0.0, 'lambda_v': 0.0, 'lambda_cov': 0.0},
    
    # + ranking
    {'lambda_u': 1.0, 'lambda_r': 0.5, 'lambda_v': 0.0, 'lambda_cov': 0.0},
    {'lambda_u': 1.0, 'lambda_r': 1.0, 'lambda_v': 0.0, 'lambda_cov': 0.0},
    
    # + variance（推荐区间）
    {'lambda_u': 1.0, 'lambda_r': 1.0, 'lambda_v': 0.1, 'lambda_cov': 0.0},
    {'lambda_u': 1.0, 'lambda_r': 1.0, 'lambda_v': 0.5, 'lambda_v': 0.0},
    
    # + covariance（主推荐）
    {'lambda_u': 1.0, 'lambda_r': 1.0, 'lambda_v': 0.5, 'lambda_cov': 0.01},
    {'lambda_u': 1.0, 'lambda_r': 1.0, 'lambda_v': 0.5, 'lambda_cov': 0.1},
]

# 选择标准（Validation）
# 1. 通过 geometry gate
# 2. neighbor utility 一致性最高
# 3. Validation regret 最低
# 4. 多随机种子稳定
```

**重要约束**：

- 网格必须在看到任何 Validation 结果前冻结
- 不能根据 Validation 结果动态添加新组合
- 如果所有组合都未通过 geometry gate，停止实验

### 补充 4：W19 决策树

```
CN_A W19 处理决策
│
├─ US v3 是否已冻结并通过 Test admission？
│  │
│  ├─ 是 → W19-C（推荐）
│  │      使用 US v3 冻结协议
│  │      CN Test 只揭盲一次
│  │      不根据 CN 结果回调 US
│  │
│  └─ 否 → US v3 失败原因？
│     │
│     ├─ Baseline 优于 Transformer → W19-B（诊断）
│     │     CN 运行旧 v2 协议
│     │     验证塌缩是否跨市场
│     │     不提交 admission
│     │
│     ├─ Geometry gate 持续失败 → W19-B（诊断）
│     │
│     ├─ Validation coverage < 30% → 暂停 W19
│     │     等待 US 根因修复
│     │
│     └─ US Test admission 失败 → 终止 Transformer 研究
│           不运行 CN W19
│           记录"状态匹配未证明增量价值"
```

**决策优先级**：W19-C > W19-B > 暂停 > W19-A（不推荐）

---

## 三、需要明确的遗留问题

### 问题 1：当前 adaptive_router_v1 的 artifact 是否可用？

**背景**：报告提到 CN_A adaptive router 为 "explicit unavailable"

**需要确认**：

- US adaptive_router_v1 是否已有完整 exact-daily 和 regime artifacts？
- 如果有，v3 的 fallback 可以使用 adaptive 而非 full-run-best
- 如果没有，是否需要在 v3 前补齐 US adaptive artifacts？

**建议**：优先确认，因为 adaptive 通常优于 full-run-best-only

### 问题 2：五日 utility 的成本扣除是否已统一？

**背景**：报告多次强调"source-net 不重复扣费"

**需要确认**：

- 当前 exact-daily 的 `strategy_return` 是否已经是扣费后的净收益？
- v3 的 utility 标签是直接使用 `strategy_return`，还是需要重新计算？
- 如果重新计算，成本口径是否与 Phase-B 一致？

**建议**：在阶段 2 开始前明确，避免标签口径不一致

### 问题 3：新 Test 窗口的选择标准

**当前建议**：2026-06-01 至 2026-07-31

**需要确认**：

- 该窗口是否已被任何先前实验（包括 Phase A-F）观察？
- 该窗口是否覆盖不同市场 regime（牛/熊/震荡）？
- 该窗口的数据质量是否与 Train/Validation 一致？

**建议**：预先审计新 Test 窗口的数据完整性和 regime 分布

### 问题 4：CN_A 的标签退化是否与 US 相同？

**假设**：CN_A 也会出现 memory 只剩 naive/cash

**需要验证**：

- CN_A 的 exact-daily 中，8 个专家的胜率分布是否也极度不均？
- 如果 CN_A 的专家更均衡，是否说明标签退化是市场特定的？

**建议**：W19-B 诊断可以快速回答这个问题，成本低于 W19-A

---

## 四、对原报告决策清单的具体建议

### 版本与边界（D01-D05）

- [x] **D01**：保留 v2/W18 不变 → **批准**
- [x] **D02**：新 Train/Val/Test 边界 → **批准**，建议 Test=2026-06-01~07-31
- [x] **D03**：Test 只揭盲一次 → **批准**
- [x] **D04**：禁止根据 US Test 调整 v3 → **批准**
- [x] **D05**：独立 artifact/manifest → **批准**

### W19 决策（D06-D08）

- [ ] **D06**：W19-A 旧协议全量 → **不推荐**
- [x] **D07**：W19-B 诊断 only → **条件批准**（仅当 US v3 失败且需跨市场验证根因）
- [x] **D08**：W19-C 等待 v3 冻结 → **首选推荐**

**决策**：默认选择 D08；如果 US v3 在阶段 3 失败，可降级到 D07

### 标签（D09-D14）

- [x] **D09**：完整 utility 向量 → **批准**
- [x] **D10**：保留 winner class 仅作辅助 → **批准**
- [x] **D11**：使用 soft label → **批准**，建议温度 T_u=0.5（Validation 校准）
- [x] **D12**：按 margin 加权 → **批准**
- [x] **D13**：不删除 ambiguous → **批准**
- [x] **D14**：availability mask → **批准**

### 样本（D15-D20）

- [x] **D15**：stride=5 主实验 → **批准**
- [ ] **D16**：stride=1 + 块权重 → **批准作为消融对照**，不作为 primary
- [x] **D17**：同日降权 → **批准**
- [ ] **D18**：扩大历史 → **延后**（v3 先用现有数据，通过后再扩大）
- [ ] **D19**：扩大股票池 → **延后**（同上）
- [x] **D20**：暂不跨市场联合 → **批准**

### 模型目标（D21-D27）

- [x] **D21**：utility regression 主任务 → **批准**
- [x] **D22**：+ pairwise ranking → **批准**
- [x] **D23**：+ variance regularization → **批准**
- [x] **D24**：+ covariance regularization → **批准**
- [x] **D25**：contrastive 作为后续消融 → **批准**
- [x] **D26**：自监督延后 → **批准**
- [x] **D27**：当前不扩大 Transformer → **批准**

### Baseline（D28-D34）

- [x] **D28**：单日 PCA baseline → **批准**
- [x] **D29**：20 日摘要 baseline → **批准**
- [x] **D30**：非 Transformer 时序 baseline → **批准**（可选 LSTM/GRU 作为对照）
- [x] **D31**：研究 whitening → **批准作为消融**
- [x] **D32**：effective rank ≥ 4/16 → **批准**
- [x] **D33**：PC1 ≤ 70% → **批准**
- [x] **D34**：先实验校准 → **批准**

### Memory（D35-D38）

- [x] **D35**：固定 Train memory → **批准**
- [x] **D36**：比较 pooled/segment/same-symbol → **批准**
- [ ] **D37**：双通道 → **延后**（先验证单通道，再考虑组合）
- [x] **D38**：去重/降权 → **批准**

### 匹配与阈值（D39-D45）

- [x] **D39**：Validation→Train 校准 → **批准**
- [x] **D40**：Top-5 mean primary → **批准**
- [x] **D41**：第 5 近邻辅助 → **批准**
- [x] **D42**：保留 Top-1 对照 → **批准**
- [x] **D43**：Validation coverage 35%-40% → **批准**
- [x] **D44**：Test coverage ≥ 30% → **批准**
- [x] **D45**：同时优化 coverage 与 utility → **批准**

### 权重与聚合（D46-D53）

- [x] **D46**：比较多种权重 → **批准**，建议 softmax 作为主推荐
- [x] **D47**：温度 Validation 校准 → **批准**
- [x] **D48**：ESS 下限 → **批准**，建议 ESS ≥ 5
- [x] **D49**：完整 utility 聚合 → **批准**
- [x] **D50**：utility dispersion → **批准**
- [x] **D51**：utility margin gate → **批准**
- [ ] **D52**：投票熵 → **可选**（先用 D50/D51，不够再加）
- [x] **D53**：conformal 延后 → **批准**

### Admission（D54-D60）

- [x] **D54**：四折分别通过 → **批准**
- [x] **D55**：matched > baseline → **批准**
- [x] **D56**：报告 fallback → **批准**
- [x] **D57**：breadth/worst-tail → **批准**
- [x] **D58**：drawdown/turnover/regret → **批准**
- [x] **D59**：hash 漂移 fail closed → **批准**
- [x] **D60**：不能人工改 ready → **批准**

---

## 五、关键修改点汇总

相比原报告，本审查补充了以下内容：

| 维度 | 原报告 | 补充内容 |
|---|---|---|
| 实施路线 | 概念性方案 | 6 周详细计划、交付物、检查点 |
| Baseline 地位 | 提到但不明确 | 明确为 Transformer 准入硬门槛 |
| Geometry gate | 阈值建议 | 具体实现代码、失败处理流程 |
| Loss 权重 | 范围建议 | 预注册网格、Validation 选择标准 |
| W19 决策 | 三选项并列 | 决策树、优先级、触发条件 |
| 停止条件 | 文字描述 | 量化标准、回退方案 |
| 模块复用 | 未提及 | 列出可复用/需新建的具体模块 |

---

## 六、最终推荐

### 立即批准

1. **套餐 B 作为 v3 主方案**
2. **W19-C 作为 CN_A 首选方案**（等待 US v3 冻结）
3. **实施路线图**（见 `transformer_state_v3_implementation_roadmap.md`）

### 需要在第 1 周明确

1. **新 Test 窗口的确切日期**（建议 2026-06-01~07-31，需审计数据质量）
2. **US adaptive_router_v1 artifacts 可用性**（影响 fallback 路径）
3. **五日 utility 成本口径**（确保与 exact-daily 一致）

### 硬停止条件（预先声明）

| 阶段 | 条件 | 处理 |
|---|---|---|
| 阶段 1 | PCA baseline 不优于随机 | 停止整个研究，重新评估产品假设 |
| 阶段 3 | >50% 折 geometry gate 失败 | 降级到 PCA baseline，不再训练 Transformer |
| 阶段 4 | Validation matched utility < fallback | 记录"状态匹配无效"，停止准入 |
| 阶段 5 | Test admission 任一指标失败 | 不进入 W20，保留 adaptive_router_v1 作为 production 默认 |

---

## 七、对用户的建议

### 如果您希望快速决策

**最简方案**：

1. 批准套餐 B + 实施路线图
2. 选择 W19-C（等待 US v3）
3. 确认新 Test 窗口 = 2026-06-01~07-31
4. 立即启动阶段 0（冻结 v2）和阶段 1（Baseline）

**预期**：

- 2 周后知道 PCA baseline 是否有效
- 4 周后知道 Transformer 是否优于 PCA
- 6 周后获得 US v3 Test admission 结果

### 如果您希望保守决策

**谨慎方案**：

1. 先只运行阶段 0 + 阶段 1（Baseline）
2. 根据 Baseline 结果决定是否继续 Transformer
3. 如果 Baseline 已足够，直接准入 PCA 方案
4. W19 暂停，等待 US 方案成熟

**预期**：

- 1 周后完成 v2 冻结
- 2 周后获得 Baseline evidence
- 基于 Baseline 结果再决定后续投入

---

## 附录：审查过程记录

### 审查方法

1. 逐节阅读 GPT 报告（22 节，约 2,300 行）
2. 验证关键数值（effective rank、PC1、coverage）与 W16-W18 artifacts 一致性
3. 评估方案可行性（标签、模型、检索各层的技术可实现性）
4. 识别遗漏项（实施计划、模块接口、停止条件）
5. 生成补充文档（路线图、审查总结）

### 审查耗时

- 阅读与理解：约 45 分钟
- 交叉验证：约 15 分钟
- 生成补充建议：约 30 分钟
- 总计：约 90 分钟

### 审查结论

**GPT 诊断报告质量：优秀**

- 诊断准确、证据充分、方案全面、风险意识强
- 主要不足是缺少实施细节（已补充）

**推荐行动：批准套餐 B + 路线图，立即启动阶段 0-1**
