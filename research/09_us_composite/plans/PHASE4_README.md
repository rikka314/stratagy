# Phase 4 快速启动指南

> 目标：跨 fold 验证 Composite 策略的稳定性和可重复性  
> 前置条件：Phase 2 和 Phase 3 已完成  
> 预计时间：5-10 分钟（取决于数据大小）

## 1. 前置检查

### 1.1 确认 Phase 2 输出

```bash
ls model-test/outputs/composite_stability_phase2/
```

必须存在：
- `nested_optimization_manifest.json` 或 `manifest.json`
- `weight_paths.parquet`
- `weight_stability.csv`

### 1.2 确认 Phase 3 输出

```bash
ls model-test/outputs/composite_stability_phase3/
```

必须存在：
- `manifest.json`
- `position_map_ablation.csv`（如果 Phase 3 已实际运行）

### 1.3 确认数据可用

```bash
ls data/demo_factors_output.parquet
```

数据必须包含：
- `date` 列（索引或列）
- 因子列：`mom_short_z`, `rsi_z`, `macd_z`, `vix_level`, `volume_ratio_rank`
- `return` 列或 `close` 列（用于计算收益）

## 2. 配置文件

### 2.1 默认配置

`model-test/configs/composite_stability_phase4.json`

关键参数：

```json
{
  "phase2_output_dir": "model-test/outputs/composite_stability_phase2",
  "phase3_output_dir": "model-test/outputs/composite_stability_phase3",
  "data_path": "data/demo_factors_output.parquet",
  "base_commission": 0.001,
  "base_slippage": 0.0005,
  "folds": [
    {
      "fold_id": "fold_01",
      "train_start": "2019-01-01",
      "train_end": "2020-09-30",
      "test_start": "2020-10-01",
      "test_end": "2021-12-31",
      "purge_days": 20,
      "embargo_days": 20
    }
    // ... 3 more folds
  ],
  "admission_gate": {
    "min_fold_pass_rate": 0.75,
    "min_sharpe_ratio": 0.3,
    "max_drawdown_threshold": 0.30,
    "max_near_max_rate": 0.90
  }
}
```

### 2.2 自定义配置

如需修改：

```bash
cp configs/composite_stability_phase4.json configs/my_phase4.json
# 编辑 my_phase4.json
```

## 3. 运行 Phase 4

### 3.1 基础运行

```bash
cd model-test
python run_composite_stability_phase4.py
```

### 3.2 指定配置

```bash
python run_composite_stability_phase4.py --config configs/my_phase4.json
```

### 3.3 预期输出

控制台会显示：

```
============================================================
Phase 4: Cross-Fold Admission Testing
============================================================

Loading Phase 2 results from: model-test/outputs/composite_stability_phase2
Loaded 5 factor weights from Phase 2

Loading Phase 3 results from: model-test/outputs/composite_stability_phase3
Loaded Phase 3 best config: quantile_5bin

Loading data from: data/demo_factors_output.parquet

============================================================
Processing fold_01
============================================================
Train: 2019-01-01 to 2020-09-30 (XXX days)
Test:  2020-10-01 to 2021-12-31 (XXX days)

Evaluating: cash
  Sharpe: 0.000
  Max DD: 0.0%
  Turnover: 0.00
  Near-max rate: 0.0%

Evaluating: composite_only
  Sharpe: 0.650
  Max DD: 18.5%
  Turnover: 5.20
  Near-max rate: 8.3%

...
```

## 4. 检查结果

### 4.1 输出文件

```bash
ls model-test/outputs/composite_stability_phase4/
```

生成文件：
- `fold_metrics.csv` - 所有 fold 的详细指标
- `admission_summary.csv` - 策略级别的准入结果
- `phase4_manifest.json` - 运行元数据

### 4.2 查看准入摘要

```bash
cat model-test/outputs/composite_stability_phase4/admission_summary.csv
```

关键列：
- `strategy_variant`: 策略名称
- `folds_passed`: 通过的 fold 数
- `pass_rate`: 通过率
- `mean_sharpe`: 平均夏普
- `admission_status`: **pass / fail / blocked**

### 4.3 查看 fold 详情

```bash
# 在 Python 中查看
import pandas as pd
df = pd.read_csv('model-test/outputs/composite_stability_phase4/fold_metrics.csv')

# 筛选某个策略
composite_metrics = df[df['strategy_variant'] == 'composite_only']
print(composite_metrics[['fold_id', 'sharpe_ratio', 'max_drawdown', 'near_max_rate']])
```

## 5. 准入判定

### 5.1 Pass 条件

策略通过准入需要：

✅ **至少 3/4 folds 通过所有单 fold 门槛：**
- Sharpe ≥ 0.3
- Sortino ≥ 0.4
- Max Drawdown ≤ 30%
- Volatility ≤ 40%
- Cost/Gross ≤ 50%
- Near-max rate ≤ 90%
- Mean exposure ≥ 5%

✅ **无质量阻断：**
- 无数据质量问题
- 无 PIT 违规
- 无审计失败

### 5.2 Fail 原因

如果策略 `admission_status = fail`，检查：

```python
import pandas as pd
df = pd.read_csv('model-test/outputs/composite_stability_phase4/fold_metrics.csv')

# 查看每个 fold 是否通过各项指标
failed_strategy = df[df['strategy_variant'] == 'composite_equal_weight']
print(failed_strategy[['fold_id', 'sharpe_ratio', 'max_drawdown', 'near_max_rate']])
```

常见失败原因：
- Sharpe 太低（< 0.3）
- Max Drawdown 过大（> 30%）
- Near-max rate 饱和（> 90%）
- 通过率不足（< 75%）

### 5.3 Blocked 原因

如果策略 `admission_status = blocked`，检查 `quality_notes`：

```python
blocked_folds = df[df['has_data_quality_issue'] == True]
print(blocked_folds[['fold_id', 'quality_notes']])
```

可能原因：
- 重复日期
- 极端收益（> 50%）
- PIT 违规（未来数据泄漏）
- Equity 重建失败

## 6. 常见问题

### Q1: Phase 3 manifest 不存在怎么办？

**A**: Phase 3 必须先运行：

```bash
python run_composite_stability_phase3.py
```

或者修改 Phase 4 配置，手动指定 position map：

```python
# 在 run_composite_stability_phase4.py 的 load_phase3_best_config() 中
# 如果 manifest 不存在，使用默认 map
```

### Q2: 数据日期范围不足怎么办？

**A**: 修改 `configs/composite_stability_phase4.json` 的 fold 日期：

```json
{
  "folds": [
    {
      "fold_id": "fold_01",
      "train_start": "2020-01-01",  // 调整到数据实际范围
      "train_end": "2021-06-30",
      "test_start": "2021-07-01",
      "test_end": "2021-12-31"
    }
  ]
}
```

### Q3: 如何只测试部分策略？

**A**: 修改配置文件的 `strategy_candidates`：

```json
{
  "strategy_candidates": [
    {
      "variant": "cash",
      "description": "Cash baseline"
    },
    {
      "variant": "composite_only",
      "description": "Composite with Phase 3 best map"
    }
    // 移除不需要的策略
  ]
}
```

### Q4: 如何调整准入门槛？

**A**: 修改配置文件的 `admission_gate`：

```json
{
  "admission_gate": {
    "min_fold_pass_rate": 0.50,        // 降低到 2/4 folds
    "min_sharpe_ratio": 0.2,           // 降低 Sharpe 要求
    "max_drawdown_threshold": 0.40,    // 放宽回撤上限
    "max_near_max_rate": 0.95          // 放宽饱和度
  }
}
```

### Q5: 如何增加更多 folds？

**A**: 在配置文件的 `folds` 数组中添加：

```json
{
  "folds": [
    // ... existing folds
    {
      "fold_id": "fold_05",
      "train_start": "2021-01-01",
      "train_end": "2022-09-30",
      "test_start": "2022-10-01",
      "test_end": "2023-06-30",
      "purge_days": 20,
      "embargo_days": 20
    }
  ]
}
```

**注意**：`min_fold_pass_rate=0.75` 意味着 5 个 folds 需要至少 4 个通过。

## 7. 下一步

### 7.1 如果 composite_only 通过准入

✅ 可以开始测试 advisory overlays：

```json
{
  "strategy_candidates": [
    {"variant": "composite_only", "description": "..."},
    {"variant": "composite_plus_macro_cap", "description": "Composite + macro risk cap"}
  ]
}
```

**前提**：需要先实现 advisory 逻辑（从 `core/composite_advisory.py` 接入）

### 7.2 如果 composite_only 未通过准入

❌ 返回 Phase 3 优化 position map：

- 尝试不同的 map variant（dead_zone_softsign, vol_target）
- 调整 execution constraints（no-trade band, rebalance cadence）
- 检查是否存在饱和问题（near_max_rate > 90%）

### 7.3 如果数据质量 blocked

⚠️ 返回 Phase 0 修复数据：

- 移除重复日期
- 处理极端收益
- 验证 PIT 合规性

### 7.4 准备 Phase 5（CN_A 复制）

当 US `composite_only` 通过准入后，启动 CN_A 市场：

1. 使用 `MarketFactorContext` 替换 SPY/VIX
2. 重新运行 Phase 1-4
3. 不直接复制 US 权重

## 8. 快速诊断命令

### 8.1 检查策略通过情况

```bash
cd model-test/outputs/composite_stability_phase4
cat admission_summary.csv | grep "pass"
```

### 8.2 查看最差 fold

```python
import pandas as pd
df = pd.read_csv('fold_metrics.csv')
composite = df[df['strategy_variant'] == 'composite_only']
worst_fold = composite.loc[composite['sharpe_ratio'].idxmin()]
print(f"Worst fold: {worst_fold['fold_id']}")
print(f"Sharpe: {worst_fold['sharpe_ratio']:.3f}")
print(f"Max DD: {worst_fold['max_drawdown']:.1%}")
```

### 8.3 比较策略

```python
import pandas as pd
summary = pd.read_csv('admission_summary.csv')
print(summary[['strategy_variant', 'mean_sharpe', 'worst_sharpe', 'admission_status']])
```

## 9. 性能优化

### 9.1 并行处理 folds（未实现）

当前实现是顺序处理。如需加速，可修改 `run_composite_stability_phase4.py`：

```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(evaluate_fold, ...) for fold in folds]
    results = [f.result() for f in futures]
```

### 9.2 减少 folds

如果只是快速测试，可以只用 2 个 folds：

```json
{
  "folds": [
    {"fold_id": "fold_01", ...},
    {"fold_id": "fold_02", ...}
  ],
  "admission_gate": {
    "min_fold_pass_rate": 0.50  // 2/2 = 100% 或 1/2 = 50%
  }
}
```

## 10. 总结

✅ **核心流程**：
1. 确认 Phase 2/3 输出存在
2. 运行 `python run_composite_stability_phase4.py`
3. 检查 `admission_summary.csv` 的 `admission_status`
4. 如果通过，进入下一阶段；否则返回优化

✅ **成功标志**：
- `composite_only` 的 `admission_status = pass`
- `folds_passed >= 3/4`
- `mean_sharpe >= 0.3`
- 无质量阻断

✅ **下一步决策树**：
```
composite_only 通过？
├─ 是 → 测试 advisory overlays
└─ 否 → 检查失败原因
    ├─ blocked → 返回 Phase 0（数据质量）
    ├─ fail (饱和) → 返回 Phase 3（position map）
    └─ fail (低 Sharpe) → 返回 Phase 2（权重优化）
```
