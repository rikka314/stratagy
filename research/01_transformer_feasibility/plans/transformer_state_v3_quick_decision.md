# Transformer State v3 快速决策表

> 日期：2026-08-20
> 用途：用户快速审批清单，无需阅读完整 40 页报告
> 基于：transformer_state_similarity_diagnosis_and_v3_solution_review_20260820.md
> 审查：transformer_state_v3_review_summary.md

---

## 核心问题：为什么 W18 失败了？

**简短回答**：不是"找不到邻居"或"相似度太低"，而是：

1. **标签只剩 2 类**：17,000/22,604 条状态被标记为 ambiguous 后删除，最终 memory 中 8 个专家只剩 naive 和 cash
2. **表示塌缩成 1 维**：16 维 embedding 的有效秩只有 1.25，第一主成分占 89%
3. **阈值设置错误**：用 Train→prior Train 的 Top-1 最大值（~0.999）去卡 Test→full Train 的查询（~0.98），统计含义不一致
4. **目标不对齐**：训练目标是硬分类，但没有直接优化余弦空间的邻居检索质量

**结果**：四折 balanced coverage 全部为 0%，但每个 query 都找到了 15 个邻居，相似度中位数约 0.98

---

## 推荐方案：套餐 B（最小可信 v3）

| 修复项 | 具体做法 | 解决的问题 |
|---|---|---|
| 完整 utility 向量 | 保存所有 8 个专家的五日净收益，不只保存赢家 | 标签退化 |
| Stride=5 采样 | 每 5 个交易日采样一次，而非每日滑窗 | 样本重叠 |
| Utility regression + ranking | 训练目标改为预测 utility 向量 + 专家排序 | 目标错配 |
| Variance + covariance 正则 | 防止 embedding 塌缩到一维 | 表示塌缩 |
| Validation→Train 校准 | 用 Validation query 查 Train memory 来校准阈值 | 校准错位 |
| Top-5 mean 作为匹配分数 | 不只看最近邻，而看前 5 个的平均相似度 | 降低偶然噪声 |
| PCA baseline 先行 | 先验证简单方法是否已足够 | 避免过度工程 |

**预期改善**：

- Memory 标签多样性：从 2 类 → 6-8 类
- Effective rank：从 1.25 → ≥4.0
- Train Top-1 阈值：从 ~0.999 → ~0.99（降低极端集中）
- Test coverage：从 0% → ≥30%

---

## 需要您立即决策的 3 个问题

### 问题 1：是否批准套餐 B 作为 v3 方案？

- [ ] **批准**：立即启动 v3 开发，预计 4-6 周
- [ ] **修改后批准**：请在下方注明具体修改意见
- [ ] **拒绝**：请说明原因

**修改意见**：
```
（如果选择"修改后批准"，请在此处填写）
```

---

### 问题 2：CN_A W19 如何处理？

- [ ] **W19-C（推荐）**：等待 US v3 冻结后，CN 使用相同协议，作为独立验证
- [ ] **W19-B（诊断）**：先运行旧协议，只看根因是否跨市场，不提交 admission
- [ ] **暂停 W19**：等待 US v3 结果再决定

**选择理由**：
```
（请简要说明您的选择）
```

---

### 问题 3：新 Test 窗口的时间范围？

**推荐**：2026-06-01 至 2026-07-31

**理由**：
- 未被任何先前实验观察
- 与 Train/Validation 时间有足够间隔
- 覆盖约 2 个月交易数据

- [ ] **批准推荐时间**
- [ ] **修改为其他时间**：请在下方填写

**修改的时间范围**：
```
开始日期：
结束日期：
```

---

## 关键里程碑与时间表

| 阶段 | 目标 | 交付物 | 预计耗时 | 停止条件 |
|---|---|---|---|---|
| 0️⃣ 治理 | 冻结 v2，建立 v3 独立分支 | v3 config、manifest schema 3.0 | 2 天 | 无 |
| 1️⃣ Baseline | 验证 PCA 是否已足够 | PCA/摘要 baseline report | 3-5 天 | PCA 不优于随机 → 停止 |
| 2️⃣ 标签 | 生成完整 utility 向量 | state_label_panel_v3.parquet | 3-4 天 | 无 |
| 3️⃣ 表示 | 训练防塌缩 encoder | 四折 checkpoint + geometry report | 5-7 天 | >50% 折 geometry 失败 → 降级 PCA |
| 4️⃣ 检索 | Validation 校准阈值 | 冻结的 threshold/temperature | 3-4 天 | Matched utility < fallback → 停止 |
| 5️⃣ Test | 一次揭盲评估 | Test admission evidence | 2-3 天 | 任一 gate 失败 → 不准入 |
| 🇨🇳 CN_A | CN 独立验证（可选） | CN v3 evidence | 7-10 天 | 依赖 US v3 结果 |

**总计**：4-6 周（US only），6-8 周（含 CN）

---

## 硬停止条件（预先声明）

| 阶段 | 触发条件 | 处理方式 |
|---|---|---|
| 阶段 1 | PCA 邻居 utility 不优于随机 | **停止整个研究**，Transformer 无意义 |
| 阶段 3 | 超过 50% 折 geometry gate 失败 | **降级到 PCA baseline**，不再训练 Transformer |
| 阶段 4 | Validation matched utility < fallback | **记录失败**，状态匹配无效 |
| 阶段 5 | Test admission 任一指标未通过 | **不进入 W20**，保留 adaptive_router_v1 作为默认策略 |

**承诺**：

- 一旦触发停止条件，立即停止，不尝试"再调调看"
- 失败结果完整记录，不删除、不隐藏
- 保留所有 artifacts 供未来方法参考

---

## 资源需求

### 计算资源

- **GPU**：1 张 V100（仅阶段 3 需要，5-7 天）
- **CPU**：16-32 核
- **内存**：64-128 GB
- **磁盘**：500 GB（含 baseline、v3 outputs、CN_A artifacts）

### 人力

- **研究员**：1 名全职（4-6 周）
- **工程师**：0.5 名（阶段 2-3 支持）
- **审核员**：1 名（阶段 0/4/5 验收）

### 成本估算

- 计算：约 $500-800（GPU + 云服务器）
- 人力：按内部标准
- 总计：低成本试错（相比继续盲目调参）

---

## 风险与回退

### 最坏情况：v3 全面失败

**如果发生**：

1. PCA baseline 不行
2. Transformer 也不行
3. Test admission 失败

**处理**：

- 承认"状态相似检索选择专家"在当前数据规模和专家结构下无效
- 保留 `adaptive_router_v1` 或 `full-run-best` 作为 production 默认策略
- 将研究结论改为：
  > "在 60 标的、1,260 日主窗口、8 专家结构下，Transformer 状态匹配未能证明相对 adaptive router 的增量价值。推荐继续使用 adaptive_router_v1。"

**影响**：

- W20 不准入 Transformer 路径
- 不影响已通过的 Phase A-F（MoE/bandit）
- 不影响其他研究窗口

**成本**：4-6 周时间 + $500-800，但获得明确的阴性结论（也是科学价值）

---

## 如果您现在时间有限

### 30 秒决策

**最简选择**：

1. ✅ 批准套餐 B
2. ✅ 选择 W19-C（等待 US v3）
3. ✅ 批准推荐 Test 时间（2026-06-01~07-31）

**下一步**：研究员立即启动阶段 0（冻结 v2），2 周后汇报 Baseline 结果

---

### 5 分钟决策

**如果您想更谨慎**：

1. 先只批准阶段 0-1（治理 + Baseline）
2. 2 周后根据 Baseline 结果决定是否继续 Transformer
3. W19 暂停，等待 US 明确

**理由**：

- Baseline 成本低（3-5 天），风险低
- 如果 PCA 已足够，节省 Transformer 开发时间
- 如果 PCA 不行，说明产品假设有问题

---

### 15 分钟决策

**如果您想深入理解**：

**建议阅读顺序**：

1. 本文档（快速决策表）← 您在这里
2. `transformer_state_v3_review_summary.md`（第一、二、七节，约 10 分钟）
3. `transformer_state_v3_implementation_roadmap.md`（阶段 0-5，约 15 分钟）
4. 原 GPT 报告的执行摘要和第 21 节最终建议（约 10 分钟）

**总计阅读时间**：约 35 分钟（相比完整 40 页报告的 2-3 小时）

---

## 批准表单

### 您的决策

**日期**：____________

**姓名**：____________

**决策**：

- [ ] 批准套餐 B + 路线图，立即启动
- [ ] 批准阶段 0-1，先看 Baseline 结果再决定后续
- [ ] 需要修改，见下方意见
- [ ] 拒绝，见下方原因

**W19 选择**：

- [ ] W19-C（等待 US v3）
- [ ] W19-B（诊断 only）
- [ ] 暂停 W19

**Test 窗口**：

- [ ] 批准 2026-06-01~07-31
- [ ] 修改为：__________

**备注**：
```
（任何额外说明或要求）
```

---

## 常见问题（FAQ）

### Q1：为什么不能直接降低阈值？

**A**：降低阈值会增加 coverage，但无法保证选出的专家更正确。根因是标签退化和表示塌缩，不是阈值本身。

### Q2：为什么要花时间做 Baseline？

**A**：如果简单 PCA 已经足够，继续投入 Transformer 是浪费。Baseline 是"必要性检验"。

### Q3：如果 v3 失败了怎么办？

**A**：保留 adaptive_router_v1 作为 production 默认，记录 Transformer 在当前条件下无效，不影响其他研究。

### Q4：CN_A 为什么不立即运行？

**A**：如果 CN 在 US v3 冻结前运行旧协议，会浪费其独立验证价值。等 US v3 成熟后，CN 可作为真正的外部测试。

### Q5：6 周时间太长了，能压缩吗？

**A**：可以先只运行阶段 0-1（1 周），根据 Baseline 结果决定是否继续。如果 PCA 已足够，总时间反而更短。

---

## 附录：与原报告的对应关系

| 本表格内容 | 原报告章节 |
|---|---|
| 核心问题 | 第 0 节（执行摘要）、第 5 节（数据诊断） |
| 套餐 B | 第 13.2 节 |
| 里程碑 | 第 10 节（v3 完整流程）、第 11 节（实验路线） |
| 停止条件 | 第 21.4 节 |
| W19 决策 | 第 15 节 |
| 硬停止条件 | 第 12 节（候选 Gate） |

**完整文档位置**：

- 原 GPT 诊断：`document/transformer_state_similarity_diagnosis_and_v3_solution_review_20260820.md`
- 审查总结：`document/transformer_state_v3_review_summary.md`
- 实施路线图：`document/transformer_state_v3_implementation_roadmap.md`
- 快速决策表：`document/transformer_state_v3_quick_decision.md`（本文档）
