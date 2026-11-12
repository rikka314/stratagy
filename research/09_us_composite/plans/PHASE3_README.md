# Phase 3 快速启动指南

> 目标：运行仓位映射和执行约束研究，解决饱和问题  
> 前置：Phase 2 已完成并生成 `weight_paths.parquet`  
> 输出：position_map_ablation.csv、cost_sensitivity.csv、mapping_decision.md

## 1. 快速运行

```bash
# 1. 确认 Phase 2 输出存在
ls model-test/outputs/composite_stability_phase2_*/manifest.json

# 2. 检查配置文件
cat model-test/configs/composite_stability_phase3.json

# 3. 运行 Phase 3
python model-test/run_composite_stability_phase3.py \
  --config model-test/configs/composite_stability_phase3.json

# 4. 查看结果
ls model-test/outputs/phase3_*/
```

## 2. 配置说明

### 2.1 必需配置项

```json
{
  "phase2_output_dir": "model-test/outputs/composite_stability_phase2_20260822",
  "data_path": "data/demo_factors_output.parquet",
  "test_start_date": "2025-01-01",
  "output_dir": "model-test/outputs"
}
```

### 2.2 Position Map 候选

- `quantile_5bin`：五分位数映射
- `dead_zone_softsign`：死区 softsign（推荐）
- `vol_target`：波动率目标
- `monotone_calibrated`：单调校准

### 2.3 Execution Constraints

```python
# 示例 1：Baseline（日频、小 band）
ExecutionConstraints(
    no_trade_band=0.02,
    max_daily_delta_increase=0.20,
    max_daily_delta_decrease=0.20,
    rebalance_cadence_days=1,
)

# 示例 2：Conservative（更宽 band、更小 delta）
ExecutionConstraints(
    no_trade_band=0.05,
    max_daily_delta_increase=0.10,
    max_daily_delta_decrease=0.15,
    rebalance_cadence_days=1,
)

# 示例 3：Low Frequency（3 天调仓）
ExecutionConstraints(
    no_trade_band=0.02,
    rebalance_cadence_days=3,
)
```

## 3. 输出文件

### 3.1 position_map_ablation.csv

包含所有（map × execution × cost）组合的诊断指标：

```csv
variant,execution_label,cost_multiplier,sharpe_ratio,net_return,max_drawdown,near_max_rate,total_turnover,...
quantile_5bin,ntb0.020_cad1_delta0.20,1.0,0.85,0.12,-0.08,0.15,2.3
dead_zone_softsign,ntb0.020_cad1_delta0.20,1.0,0.92,0.15,-0.06,0.25,1.8
...
```

### 3.2 cost_sensitivity.csv

最佳 map 在不同成本假设下的表现：

```csv
cost_multiplier,sharpe_ratio,net_return,transaction_cost,cost_to_gross_ratio
1.0,0.92,0.15,0.005,0.03
2.0,0.78,0.12,0.010,0.06
4.0,0.55,0.08,0.020,0.12
```

### 3.3 mapping_decision.md

包含：
- 最佳配置（map + execution）
- 饱和度 gate 结果（near_max_rate <= 90%）
- 成本敏感性摘要
- 下一步建议

### 3.4 manifest.json

运行元数据：
```json
{
  "phase": "phase3_position_mapping",
  "status": "ready",
  "best_result": {
    "variant": "dead_zone_softsign",
    "sharpe_ratio": 0.92,
    "near_max_rate": 0.25
  },
  "saturation_gate": "PASS"
}
```

## 4. 关键检查点

### 4.1 Phase 2 依赖

```bash
# 检查 Phase 2 manifest
cat model-test/outputs/composite_stability_phase2_*/manifest.json | jq '.status'
# 必须为 "ready"

# 检查权重文件
ls -lh model-test/outputs/composite_stability_phase2_*/weight_paths.parquet
# 文件必须存在
```

### 4.2 数据要求

```bash
# 检查因子数据
python -c "import pandas as pd; df = pd.read_parquet('data/demo_factors_output.parquet'); print(f'Rows: {len(df)}, Columns: {df.columns.tolist()}')"

# 必需列：date, symbol, future_return_20d, close
# 必需因子：与 Phase 2 权重中的因子匹配
```

### 4.3 饱和度 Gate

```bash
# 运行后检查饱和度
cat model-test/outputs/phase3_*/manifest.json | jq '.best_result.near_max_rate'
# 必须 <= 0.90 才能通过
```

## 5. 常见问题

### Q1: Phase 2 manifest not found

```bash
# 检查 Phase 2 输出目录
ls model-test/outputs/composite_stability_phase2_*

# 如果不存在，需要先运行 Phase 2
python model-test/run_composite_stability_phase2.py
```

### Q2: 因子数据缺失

```bash
# 检查数据文件
ls data/demo_factors_output.parquet

# 如果不存在，运行因子生成
python model-test/demo_factor_pipeline.py
```

### Q3: 饱和度 gate 未通过

如果 `near_max_rate > 0.90`：

1. 调整 dead_zone_softsign 参数：
   - 增大 `threshold`（如 0.5）
   - 增大 `scale`（如 1.5）

2. 使用 quantile_5bin 强制分位数映射

3. 检查 Phase 2 权重是否合理

### Q4: 成本侵蚀严重

如果 4x cost 下 Sharpe < 0.3：

1. 增大 no_trade_band（如 0.05）
2. 增大 rebalance_cadence（如 3 或 5 天）
3. 减小 max_daily_delta
4. 考虑选择换手更低的 map

## 6. 测试验证

```bash
# 运行单元测试
python -m pytest tests/test_position_map_research.py -v

# 预期：12 passed
```

## 7. 下一步（Phase 4）

**前置条件**：
- Phase 3 运行完成
- 饱和度 gate 通过（near_max_rate <= 90%）
- 选定最佳 map + execution config

**Phase 4 任务**：
- 跨 fold 验证
- 与 advisory candidates 对比
- 准入决策

**命令**：
```bash
# Phase 4 尚未实现，等待 Phase 3 结果
# python model-test/run_composite_stability_phase4.py
```

## 8. 完整示例

```bash
# 完整 Phase 3 运行流程
cd D:/Learn/20_Projects/2026_SPRING/AIE1902/课堂内容/stratagy

# 1. 验证环境
python -m pytest tests/test_position_map_research.py -v

# 2. 检查依赖
ls model-test/outputs/composite_stability_phase2_*/manifest.json
ls data/demo_factors_output.parquet

# 3. 运行 Phase 3
python model-test/run_composite_stability_phase3.py

# 4. 查看结果
cat model-test/outputs/phase3_*/mapping_decision.md

# 5. 检查 gate
cat model-test/outputs/phase3_*/manifest.json | jq '.best_result.near_max_rate'
```

## 9. 调试技巧

### 9.1 详细日志

在运行脚本中添加：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 9.2 小规模测试

修改 config 减少组合数：
```json
{
  "position_maps": ["dead_zone_softsign"],
  "execution_constraints": [{"no_trade_band": 0.02, "rebalance_cadence_days": 1}],
  "cost_multipliers": [1.0]
}
```

### 9.3 中间结果检查

在 `run_composite_stability_phase3.py` 中添加：
```python
# 查看 composite score 分布
print(f"Score stats: {train_score.describe()}")

# 查看 target position 分布
print(f"Position stats: {test_target.describe()}")
```

## 10. 参考文档

- 完整报告：`document/phase3_position_mapping_completion_report.md`
- 研究计划：`document/composite_stability_research_plan.md`（Phase 3 部分）
- 代码实现：`model-test/model_test/position_map_research.py`
- 测试套件：`tests/test_position_map_research.py`
