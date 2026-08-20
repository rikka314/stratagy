# Transformer State v3 - Phase 1 实验结果总结

> **日期**：2026-08-20  
> **市场**：US  
> **状态**：✅ 实验完成  
> **决策**：准入 Phase 2 诊断，不准入 Phase 3 训练

---

## 📊 实验结果

### 运行概况
- **方法数**：3（B01, B02, B03）
- **Fold 数**：4（wf_01, wf_02, wf_03, wf_04）
- **总任务数**：12（3 methods × 4 folds）
- **Validation 查询数**：960 per fold
- **邻居记录数**：14,400 per fold（960 × 15）

### 主要指标

| Method | PCA components | Utility consistency | Query utility | Regret |
|---|---:|---:|---:|---:|
| B01 single day | 16 | -0.065086 | -0.005851 | 0.023804 |
| B02 20-day summary | 49 | -0.066369 | -0.006135 | 0.024087 |
| B03 random | n/a | -0.082239 | -0.002756 | 0.020709 |

**指标说明**：
- **Utility consistency**：邻居 utility 一致性（越高越好，负值表示离散）
- **Query utility**：选中专家的实际 utility（越高越好）
- **Regret**：相对最优专家的遗憾（越低越好）

---

## 🔬 统计检验结果

**Bootstrap 配对测试（1,000 次迭代，32 个独立验证日期簇）**：

| 对比 vs B03 | 指标 | 差异 | 95% CI | 单侧 p 值 | 结果 |
|---|---|---:|---:|---:|---:|
| B01 | Utility consistency | +0.0175 | [0.0158, 0.0192] | 0.001 | ✅ 显著 |
| B02 | Utility consistency | +0.0209 | [0.0162, 0.0248] | 0.001 | ✅ 显著 |
| B01 | Query utility | -0.0033 | [-0.0058, -0.0005] | 0.984 | ❌ 显著更差 |
| B02 | Query utility | -0.0054 | [-0.0099, -0.0008] | 0.993 | ❌ 显著更差 |

---

## ⚠️ 关键矛盾

### 发现的矛盾
1. **一致性提升**：PCA 邻居的 utility 一致性显著优于随机（+0.0175 ~ +0.0209）
2. **收益下降**：但实际选中专家的 utility 反而更差（-0.0033 ~ -0.0054）
3. **停止规则通过**：一致性指标通过 Phase 1 停止规则
4. **经济价值缺失**：但未转化为经济价值

### 可能原因（待 Phase 2 诊断）
1. **Winner 选择偏差**：一致性高但选错方向（都选了低收益专家）
2. **特征语义问题**：PCA 捕获"风险一致性"而非"收益一致性"
3. **采样偏差**：stride=20 导致某些时间段过度表征
4. **单目标局限**：只看 `future_5d_utility`，忽略其他 7 个专家表现

---

## 🎯 研究决策

### 正式决策
**✅ 准入 Phase 2 诊断**  
**🛑 不准入 Phase 3 训练**

### 决策理由
1. **通过停止规则**：一致性显著提升 → 不在 Phase 1 停止研究
2. **发现矛盾信号**：utility 无改善 → 需要深入诊断
3. **风险控制**：在诊断前不准入昂贵的 Transformer 训练

### Phase 3 准入条件（新增）
Phase 2 诊断后的标签/stride 重构实验必须满足：
- **正向 Validation query utility**，或
- **显著更低的 regret**（相对 B03）

---

## 📋 验证确认

```text
Phase 1 targeted tests:       13 passed ✅
Transformer-adjacent tests:   78 passed ✅
Full repository tests:       323 passed ✅
Artifact rehash:              76/76 matched ✅
Method-fold shape audit:      12/12 passed ✅
```

---

## 📁 输出位置

### 实验输出
```
model-test/outputs/transformer_state_v3_us/baseline_artifacts/
├── pca_single_day/
│   ├── fold_wf_01/ ... fold_wf_04/
├── pca_summary_20d/
│   ├── fold_wf_01/ ... fold_wf_04/
├── random_neighbor/
│   ├── fold_wf_01/ ... fold_wf_04/
├── baseline_comparison.csv
├── baseline_comparison_report.md
└── baseline_comparison_report.json
```

### 验收文档
```
document/acceptance/transformer_state_v3_phase1_baselines_20260820.md
```

---

## 🚀 下一步：Phase 2 诊断

### D01 诊断任务（必需）

1. **多专家分解**：
   - 检查 8 个专家在 PCA 邻居中的分布
   - 是否某些专家提升，某些下降？
   - Winner 选择是否有系统性偏差？

2. **采样偏差分析**：
   - stride=20 是否导致时间段过度表征？
   - Top-1 相似度分布是否极端集中？
   - 独立日期数 vs 样本数比例

3. **特征语义检查**：
   - PCA 前几个主成分捕获什么？
   - 与哪些原始特征相关？
   - 是否捕获"防御性"而非"进攻性"信号？

### 输出
- `document/phase2_diagnostic_report.md`
- 明确建议路径：
  - ✅ 继续 Phase 3（修正后重新 baseline）
  - ⚠️ 多目标重构
  - 🛑 停止研究

---

## 📊 Phase 1 最终状态

- **实验状态**：✅ 完成
- **代码状态**：✅ 完成
- **文档状态**：✅ 完成
- **验收状态**：✅ 完成
- **决策状态**：✅ 准入 Phase 2 诊断

---

**完成日期**：2026-08-20  
**分支**：`transformer-state-v3`  
**下一阶段**：Phase 2 - 诊断分析（待新窗口执行）

---

_本文件总结 Phase 1 实验结果，供路线图更新和 Phase 2 规划参考。_
