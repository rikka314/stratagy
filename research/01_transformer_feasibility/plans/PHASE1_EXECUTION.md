# Phase 1 执行说明

## 状态
✅ **代码完成**，待执行实验

## 快速执行

### 1. 安装研究依赖（如果缺失）
```bash
pip install scikit-learn==1.3.2
```

### 2. 运行 baseline 实验
```bash
python model-test/run_baseline_phase1.py \
  --config model-test/configs/transformer_state_v3_us.json
```

预计运行时间：5-10 分钟

### 3. 查看结果
```bash
# Markdown 报告
cat model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison_report.md

# CSV 数据
cat model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison.csv
```

## 决策路径

根据实验结果，选择以下之一：

### ✅ 继续 Transformer
- 条件：PCA (B01/B02) 的 utility consistency > Random (B03)
- 下一步：Phase 2 - 标签与样本重构

### ⚠️ 降级 PCA
- 条件：PCA 有效，但 Transformer 改善 < 10%
- 下一步：直接使用 PCA baseline，跳过 Transformer 训练

### 🛑 停止研究
- 条件：PCA ≈ Random，无统计显著性
- 结论：状态相似检索假设不成立

## 输出文件
```
model-test/outputs/transformer_state_v3_us/baseline_artifacts/
├── pca_single_day/fold_wf_{01..04}/
│   ├── embeddings_train.npy
│   ├── embeddings_query.npy
│   ├── neighbors.parquet
│   └── baseline_metadata.json
├── pca_summary_20d/fold_wf_{01..04}/
│   └── [同上]
├── random_neighbor/fold_wf_{01..04}/
│   └── [同上]
├── baseline_comparison.csv
├── baseline_comparison_report.md
└── baseline_comparison_report.json
```

详细说明见：`document/transformer_state_v3_phase1_completion.md`
