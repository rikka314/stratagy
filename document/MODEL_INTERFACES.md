# ModelResult 统一数据结构（Week 3 · 1.1）

> 生成日期：2026-03-25
> 目的：为 W3/W4/W5 的多模型对比建立稳定的数据承载结构，避免 UI/评估模块在字段层面反复改动。

---

## 1. ModelResult 字段定义

建议使用以下统一结构（“强约束字段 + 可选字段”）：

```python
ModelResult = {
    "label": str,
    "equity_series": pd.Series,      # 策略权益曲线（建议以日期为 index）
    "returns": pd.Series,            # 策略日收益率序列（与 equity_series 同频同 index）
    "trades_df": pd.DataFrame | None, # 逐笔交易明细（可选；用于胜率/盈亏比/持仓天数等）
    "metrics": dict | None,          # 评估层汇总指标（可选；用于 KPI 展示/对比表）
}
```

与 week3 计划一致的字段 key：
- `label`
- `equity_series`
- `returns`
- `trades_df`（或 `None`）
- `metrics`（或 `None`）

---

## 2. equity_series / returns 的约束

1. `equity_series`：pandas `Series`
   - 语义：策略权益曲线（例如 `strategy_equity`）
   - index：建议为 `pd.DatetimeIndex`（按交易日递增）
   - 数值：建议为“净值/权益”，应能支持累计收益与回撤计算

2. `returns`：pandas `Series`
   - 语义：日收益率序列（例如 `strategy_return`）
   - index：必须与 `equity_series.index` 一致
   - 用途：最大回撤/夏普/年化收益等指标计算所需的输入

---

## 3. trades_df（可选）的约束

`trades_df`：pandas `DataFrame | None`
- 当 `trades_df is None`：表示尚未抽取逐笔交易信息（此时 trade-level 指标可在评估层填 `None`）
- 当 `trades_df` 存在时，建议列至少包含以下字段：

| 列名 | 类型 | 语义 |
|---|---|---|
| `entry_date` | datetime/date | 开仓日期 |
| `exit_date` | datetime/date | 平仓日期 |
| `hold_days` | int/float | 持仓天数（含开仓至平仓的天数口径需在评估层统一） |
| `trade_return` | float | 单笔交易收益率（可用于胜率/盈亏比/平均持有天数） |
| `is_win` | bool | 是否盈利（`trade_return > 0` 的口径需与 `trade_return` 一致） |

---

## 4. metrics（可选）的约束

`metrics`：`dict | None`
- 建议只由 `core/evaluation.py` 负责填充（UI 不直接“猜测”指标）
- 当 `metrics is None`：表示尚未进入评估阶段或评估失败
- `metrics` 字段 key 的最终集合在 W3 子任务 3.3 里统一规划；本文件只保证 `metrics` 容器存在与类型正确

---

## 5. 对齐原则（为了后续不破坏接口）

1. `ModelResult` 的“字段名稳定”是第一优先级：后续可以扩展，但不要重命名已有 key。
2. `equity_series` 与 `returns` 的 index 必须可对齐，确保 UI/评估层按日期切片时不会错位。
3. `trades_df` 与 `metrics` 都允许为 `None`，这是为了让“先跑通收益曲线，再逐步补齐逐笔统计/增强评估”成为可控的迭代路线。

---

## 6. 与现有 `core/backtest.py` 的对接（核对结论：2026-03-25）

当前 `simulate_strategy()` **只返回** `pd.DataFrame`，尚未返回 `ModelResult`；下列列可直接映射到 `ModelResult` 的 `equity_series` / `returns`（需在适配层从 df 取出并转为 `Series`）：

| DataFrame 列 | 建议映射到 ModelResult |
|---|---|
| `strategy_equity` | `equity_series` |
| `strategy_return` | `returns` |
| `buy_hold_equity` | 不作为 `ModelResult` 字段；评估层对比时作为 **benchmark** 单独传入 `evaluate_strategy(..., benchmark_series=...)` |

**Index 现状**：管线里 `date` 多为**列**，df 常为默认 `RangeIndex`。与本文 §2「建议 DatetimeIndex」的衔接方式：在组装 `ModelResult` 时执行 `df.set_index("date")` 再取列，或显式 `pd.Series(..., index=df["date"])`，保证 `equity_series` 与 `returns` 共用同一时间索引。

**`position` 与逐笔交易**：`simulate_strategy` 在 `target_position` 模式下会写入 **0～1 的连续仓位**；week3 计划的 `extract_trades()` 以「连续非零段」为一笔时，应对 `position > 0`（或大于极小阈值）视为持仓段，单笔 `trade_return` 的口径需在实现或评估层与「按仓位缩放后的收益」一致，避免与二元 0/1 持仓语义混用。

**尚未实现**：`trades_df` 需待 W3 子任务 1.2 `extract_trades(df)`（及可选 1.3 `return_trades`）补齐后，再由基线/SM 等模型填入 `ModelResult`。

