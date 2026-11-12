# Transformer State v3 - Phase 1 完成报告

> 日期：2026-08-20
> 阶段：Phase 1 - Baseline 建立
> 状态：✅ 代码完成，待执行
> 下一步：运行 baseline 实验并评估结果

---

## ✅ 已完成的交付物

### 1. 核心模块

| 模块 | 路径 | 大小 | 状态 |
|---|---|---|---|
| Baseline 核心逻辑 | `model-test/model_test/transformer_state_baseline.py` | ~15KB | ✅ 已实现 |
| Phase 1 运行脚本 | `model-test/run_baseline_phase1.py` | ~12KB | ✅ 已实现 |
| 单元测试 | `tests/test_transformer_state_baseline.py` | ~7KB | ✅ 已实现 |

### 2. 实现的 Baseline 方法

#### B01: PCA Single Day
```python
# 输入：决策日 t 的最后一日 28 维特征
# 处理：Train-only StandardScaler → Train-only PCA(0.95) → L2 normalize
# 检索：Validation query → Train memory，Top-15 cosine similarity
# 输出：neighbor utility 一致性、coverage-quality 曲线
```

**关键函数**：
- `_extract_single_day_features()`: 提取序列最后一天特征
- `_fit_pca_baseline()`: 在 Train-only 数据上拟合 scaler 和 PCA
- `_transform_and_normalize()`: 应用 scaler、PCA 和 L2 归一化

#### B02: PCA Summary 20d
```python
# 输入：20 日序列的 7 种统计摘要特征
# 摘要：[last, mean, std, min, max, trend, diff_half]
# 处理：同 B01（Train-only scaler → PCA → L2 normalize）
# 检索：同 B01
```

**关键函数**：
- `_compute_summary_features()`: 计算序列统计摘要
  - `last`: 最后一天值
  - `mean`: 20 日均值
  - `std`: 20 日标准差
  - `min/max`: 最小/最大值
  - `trend`: 后半段均值 - 前半段均值
  - `diff_half`: 最后一天 - 第一天

#### B03: Random Neighbor
```python
# 输入：不使用特征
# 处理：从 Train memory 随机选择 15 个邻居
# 目的：Null hypothesis baseline（零假设基线）
```

**关键函数**：
- `run_random_baseline()`: 随机邻居选择
- 使用固定随机种子确保可重复性

### 3. 输出结构

每个 baseline 方法对每个 fold 输出：

```
baseline_artifacts/
├── pca_single_day/
│   ├── fold_wf_01/
│   │   ├── embeddings_train.npy          # Train embeddings (n_train, n_components)
│   │   ├── embeddings_query.npy          # Query embeddings (n_query, n_components)
│   │   ├── neighbors.parquet             # Top-k neighbors with similarity
│   │   └── baseline_metadata.json        # Method config, PCA params, utility stats
│   ├── fold_wf_02/
│   ├── fold_wf_03/
│   └── fold_wf_04/
├── pca_summary_20d/
│   └── [same structure]
├── random_neighbor/
│   └── [same structure]
├── baseline_comparison.csv               # Summary statistics across all methods/folds
├── baseline_comparison_report.md         # Human-readable comparison
└── baseline_comparison_report.json       # Machine-readable comparison
```

### 4. 评估指标

每个 baseline 结果包含以下统计量：

| 指标 | 含义 | 期望 |
|---|---|---|
| **mean_neighbor_utility** | 检索到的邻居的平均 5 日 future utility | 越高越好 |
| **std_neighbor_utility** | 邻居 utility 的标准差 | 越低越好（邻居更一致） |
| **utility_consistency** | -std_neighbor_utility（正值表示一致性） | 越高越好 |
| **mean_similarity** | 平均余弦相似度（仅 PCA） | 参考值 |
| **n_components** | PCA 保留的主成分数（仅 PCA） | 参考值 |

---

## 🎯 执行指南

### Step 1: 环境准备

确保已安装研究依赖：
```bash
# 检查 sklearn 是否可用
python -c "import sklearn; print(f'sklearn: {sklearn.__version__}')"

# 如果缺失，安装
pip install scikit-learn==1.3.2
```

### Step 2: 数据准备

确认 Phase-B artifacts 已存在：
```bash
# 检查 source artifacts
ls model-test/outputs/transformer_state_source_us/

# 应包含：
# - state_sequence_panel.parquet
# - state_label_panel.parquet
# - transformer_state_walk_forward_splits.csv
# - state_feature_schema.json
```

### Step 3: 运行 Baseline 实验

```bash
# 运行所有三个 baseline (B01, B02, B03)
python model-test/run_baseline_phase1.py \
  --config model-test/configs/transformer_state_v3_us.json
```

**预计运行时间**：5-10 分钟（4 folds × 3 methods，无需 GPU）

### Step 4: 审查结果

```bash
# 查看比较报告
cat model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison_report.md

# 查看详细统计
cat model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison.csv
```

---

## 📊 决策标准

### ✅ 继续 Transformer 开发的条件

**主要标准**：
1. B01 OR B02 的 `utility_consistency` > B03（随机）
2. 差异在统计上显著（p < 0.05，bootstrap 1000 次）
3. Bootstrap 95% CI 不包含零改善

**次要标准**：
4. B01 或 B02 的 `mean_neighbor_utility` > B03
5. 至少 3/4 folds 显示一致的改善方向

**如果满足**：
- ✅ 证明"状态相似检索"优于随机
- ✅ 继续到 Phase 2：标签与样本重构
- ✅ 继续到 Phase 3：Transformer 表示学习

### ⚠️ 降级到 PCA Baseline 的条件

**触发条件**：
1. B01 或 B02 有效（优于 B03）
2. **但是** 后续 Transformer（Phase 3）相对 PCA 改善 <10%

**处理方式**：
- ⚠️ 停止 Transformer 开发
- ⚠️ 直接使用 PCA baseline 作为 primary 方案
- ⚠️ 节省 3-4 周开发时间
- ⚠️ 记录："简单方案已足够，无需深度学习复杂性"

### 🛑 停止研究的条件

**触发条件**：
1. B01 AND B02 的 `utility_consistency` ≤ B03（随机）
2. 或者 B01/B02 的 `mean_neighbor_utility` ≤ B03
3. 差异在统计上不显著或方向相反

**处理方式**：
- 🛑 **立即停止整个 Transformer 研究**
- 🛑 不继续到 Phase 2、Phase 3
- 🛑 上报用户：重新评估"状态相似匹配"的产品假设
- 🛑 考虑其他路径：
  - 直接优化 `adaptive_router_v1`
  - 探索其他特征工程
  - 放弃状态匹配，使用全局策略

---

## 🔬 技术细节

### PCA 参数选择

- **Variance threshold**: 0.95（保留 95% 方差）
- **Scaler**: StandardScaler（Train-only mean/std）
- **Normalization**: L2 normalize（确保余弦相似度有效）
- **Top-k**: 15（与 v3 config 一致）

**为什么选择 95% 方差阈值？**
- 平衡信息保留与降维效果
- 典型降维：28 维 → 预计 8-12 维
- 避免过度压缩（如 90%）或压缩不足（如 99%）

### 序列摘要特征设计

B02 使用 7 种统计量，每个特征 28 维：
- 总维度：28 × 7 = **196 维**
- PCA 后：预计 **15-20 维**（95% 方差）

**为什么 B02 可能更好？**
- 单日（B01）容易受短期噪音影响
- 摘要（B02）捕获 20 日趋势和波动模式
- 如果 B02 > B01，说明**时序信息很重要** → 支持 Transformer

### 随机 Baseline 的作用

B03 不是"无用的对照"，而是关键的**零假设检验**：

**如果 PCA ≈ Random**：
- 说明：特征本身无信息
- 或者：状态相似度与未来 utility 无关
- 结论：**停止研究**

**如果 PCA > Random**：
- 说明：特征捕获了有用信号
- 并且：相似状态确实有相似 utility
- 结论：**继续 Transformer**（探索更强表示）

---

## 📋 代码审查清单

### 已验证的安全边界

- [x] Train-only fitting（scaler 和 PCA 只在 Train 上拟合）
- [x] Validation query → Train memory（严格 prior）
- [x] 无未来信息泄漏（只使用 `sequence` 列，不用 `future_*` 列）
- [x] L2 归一化（确保余弦相似度有效）
- [x] Top-k 正确性（降序排列，返回最相似的 k 个）
- [x] 随机种子固定（确保 B03 可重复）

### 已实现的接口契约

- [x] `BaselineConfig` 数据类（冻结配置）
- [x] `BaselineResult` 数据类（统一输出）
- [x] `run_baseline_experiment()` 统一入口
- [x] `compare_baselines()` 跨方法比较
- [x] `save_baseline_artifacts()` 磁盘持久化
- [x] Parquet 格式（neighbors）+ NumPy（embeddings）+ JSON（metadata）

### 待执行的验证

- [ ] 实际运行 `run_baseline_phase1.py`
- [ ] 验证 4 个 fold 的输出一致性
- [ ] 检查 `baseline_comparison_report.md` 是否生成
- [ ] 统计检验：PCA vs Random（bootstrap）
- [ ] 人工审查：utility distribution、similarity distribution

---

## 🚀 下一步（Phase 1 执行后）

### 如果决策：✅ 继续 Transformer

**立即行动**：
1. 开始 Phase 2：标签与样本重构
2. 生成完整 8 专家 utility 向量
3. 实验 stride=5 vs stride=1 采样

**时间表**：
- Phase 2 预计：3-4 天
- 交付物：`state_label_panel_v3.parquet`、`stride_comparison_report.md`

### 如果决策：⚠️ 降级 PCA

**立即行动**：
1. 选择 B01 或 B02 作为 primary
2. 跳过 Phase 2-3（标签重构 + Transformer 训练）
3. 直接进入 Phase 4：检索校准（使用 PCA embeddings）

**时间表**：
- 节省：~2 周（跳过 Transformer 训练）
- 直接到 Phase 4：3-4 天

### 如果决策：🛑 停止研究

**立即行动**：
1. 编写失败报告：`transformer_state_v3_phase1_failure.md`
2. 记录原因：PCA/Random 无差异
3. 建议：重新评估产品假设或探索其他路径
4. 保留 Phase 0-1 artifacts 供未来参考

---

## ⚠️ 风险与缓解

### 风险 1：Phase-B artifacts 缺失
**概率**：低（已验证存在）
**影响**：无法运行 baseline
**缓解**：运行前检查 `transformer_state_source_us/` 目录

### 风险 2：PCA 降维过度
**概率**：中等
**影响**：信息损失，utility consistency 下降
**缓解**：已设置 95% 方差阈值；如有问题可调整到 98%

### 风险 3：B01/B02 都失败
**概率**：低-中等
**影响**：触发停止条件
**缓解**：这是**预设的科学决策点**，不是失败

### 风险 4：统计检验不显著
**概率**：中等
**影响**：无法判断 PCA > Random
**缓解**：
- 已使用 4 个 fold（增加样本量）
- Bootstrap 1000 次（稳健估计）
- 如果仍不显著，说明效应太小 → 应停止

---

## 📊 预期结果示例

### 乐观场景（继续 Transformer）

```
Method              | Mean Utility | Utility Consistency | Mean Similarity
--------------------|--------------|---------------------|----------------
pca_single_day      | 0.0045       | 0.0025              | 0.45
pca_summary_20d     | 0.0052       | 0.0031              | 0.48
random_neighbor     | 0.0008       | -0.0102             | N/A

✅ PCA Summary > Random (p < 0.001)
✅ Continue to Transformer development
```

### 中立场景（降级 PCA）

```
Method              | Mean Utility | Utility Consistency
--------------------|--------------|--------------------
pca_summary_20d     | 0.0042       | 0.0028
random_neighbor     | 0.0015       | -0.0085

✅ PCA > Random (sufficient)
⚠️ But if Transformer improvement < 10% in Phase 3
→ Use PCA as primary, skip Transformer
```

### 悲观场景（停止研究）

```
Method              | Mean Utility | Utility Consistency
--------------------|--------------|--------------------
pca_single_day      | 0.0012       | -0.0055
pca_summary_20d     | 0.0018       | -0.0042
random_neighbor     | 0.0021       | -0.0048

🛑 PCA ≈ Random (p = 0.34, not significant)
🛑 Stop research: State similarity does not help
```

---

## ✅ Phase 1 验收

### 代码交付验收

- [x] `transformer_state_baseline.py` 已实现（~500 行）
- [x] `run_baseline_phase1.py` 已实现（~350 行）
- [x] `test_transformer_state_baseline.py` 已实现（~250 行）
- [x] 所有函数有 docstring
- [x] 类型提示完整
- [x] 错误处理到位

### 功能验收（待运行）

- [ ] B01 在 4 个 fold 上运行成功
- [ ] B02 在 4 个 fold 上运行成功
- [ ] B03 在 4 个 fold 上运行成功
- [ ] `baseline_comparison.csv` 生成
- [ ] `baseline_comparison_report.md` 生成
- [ ] 统计检验完成
- [ ] 决策建议明确

---

## 📞 执行负责人

**负责人**：用户
**执行者**：Claude Code（本会话）
**审核员**：用户

**下次汇报**：Phase 1 实验运行完成后（预计 1 小时内）

---

## 附录：快速执行命令

### 环境检查
```bash
# 检查依赖
python -c "import sklearn, numpy, pandas; print('✓ All dependencies ready')"

# 检查 source artifacts
ls -lh model-test/outputs/transformer_state_source_us/*.parquet
```

### 运行实验
```bash
# 完整运行（约 5-10 分钟）
python model-test/run_baseline_phase1.py \
  --config model-test/configs/transformer_state_v3_us.json
```

### 查看结果
```bash
# Markdown 报告
cat model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison_report.md

# CSV 详情
cat model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison.csv
```

---

**Phase 1 状态**：✅ 代码完成，待执行
**下一里程碑**：运行实验 → 评估结果 → 决策路径
