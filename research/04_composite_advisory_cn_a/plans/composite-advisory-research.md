# Composite-Centric Advisory Research Contract

> Status: research-only design contract
> Market: US frozen universe
> Primary horizon: 20 trading days
> Decision policy: Composite-led, rule-based advisory overlay

## 1. Scope

本 contract 定义以 `composite_optimized` 为主模型、其他专家提供风险建议的离线研究流程。它不训练 gating model，不做 winner selection，不替换既有 `dynamic-ensemble-research.md` 的 Phase A-F contract，也不接入 Streamlit 或 production。

正式比较必须同时保留 `composite_only` baseline。advisory layer 只有在相对 baseline 提供预注册的风险增量价值时才可准入；没有增量价值时，结论为 Composite-only。

## 2. Decision flow

```text
point-in-time factor frame
  -> composite score / base position
  -> trend confirmation
  -> mean-reversion warning
  -> relative-strength confirmation
  -> macro risk level / exposure cap
  -> bounded advisory overlay
  -> final position
```

Composite 决定方向。Advisory 只能保持方向、降低暴露或在安全规则允许时作有限确认，不能单独把 Composite 的多头变成空头，也不能在 Composite 为零仓位时创建方向仓位。

## 3. Input contract

每个决策行必须标识：

```text
date, symbol, market
```

并只包含决策时点可用的因子和行情字段。核心输入包括：

- `mom_short_z`, `mom_long_z`, `macd_z`
- `rsi_z`, `bb_position_rank`, `price_position_rank`
- `vol_z`, `drawdown_rank`, `volume_ratio_rank`
- `vix_level`, `rel_strength_spy`
- Composite 的冻结 Phase 2.5 权重和交互项

宏观输入必须通过 manifest、date range、artifact hash 和 observed-data 检查。缺失、非 finite、过期或 market 不匹配时必须显式 fallback 或 pending，不得静默填零。

未来收益、未来 expert return、test fold 指标和任何揭盲结果禁止出现在 input frame。它们只能在评估阶段作为标签或对照使用。

## 4. Output contract

每个决策行必须能重建最终仓位，并至少包含：

```text
composite_score
composite_base_position
trend_confirmation
reversion_warning
relative_strength_confirmation
macro_risk_level
macro_risk_cap
advisory_multiplier
final_position
fallback_used
fallback_reason
policy_version
config_sha256
source_manifest_sha256
```

建议的不可变结果接口：

```python
@dataclass(frozen=True)
class AdvisoryDecision:
    composite_score: float
    composite_base_position: float
    trend_confirmation: float
    reversion_warning: float
    relative_strength_confirmation: float
    macro_risk_level: float
    macro_risk_cap: float
    advisory_multiplier: float
    final_position: float
    fallback_reason: str | None
```

## 5. Advisory roles

| Expert | Output | Allowed action |
|---|---|---|
| `momentum_optimized` | trend confirmation/conflict | bounded confirmation or reduction |
| `mean_reversion` | overextension warning | bounded reduction only |
| `volume_confirmed` | relative-strength confirmation/weakness | bounded filter or reduction |
| `macro_defensive` | risk level and cap | reduce maximum exposure |
| `cash` | fallback state | zero position when registered safety rule triggers |

`composite_optimized` 是唯一主方向模型，不作为 advisory voter。

## 6. Rule and bound contract

所有阈值和 bounds 必须在 validation 前冻结。每个 overlay 必须有：

- trigger threshold；
- maximum multiplier increase/decrease；
- maximum single-decision position change；
- risk budget；
- rebalance cadence；
- fallback condition；
- audit reason code。

默认安全原则：

- `final_position` 不得超过 Composite base position 的方向性边界；
- macro cap 只能收紧暴露；
- reversion 和 relative-strength 冲突默认采用降仓的保守结果；
- 数据不可用时不以另一专家结果替代，使用 Composite 的注册安全上限或 cash。

## 7. Return and cost contract

两种输入语义必须严格分离：

1. OHLCV gross experiment：从 close 计算 gross return，runner 只扣一次 `turnover * (commission_bps + slippage_bps) / 10000`，配置为 `ohlcv_gross_charge_once`。
2. Existing source `strategy_return`：该字段已经是 net return，配置为 `source_net_no_recharge`，下游不得再次扣费。

每个报告必须输出 return field、cost treatment、turnover 和 transaction cost audit。

## 8. Validation contract

必须至少比较：

- `composite_only`
- `composite_plus_trend`
- `composite_plus_reversion`
- `composite_plus_macro_cap`
- `composite_plus_relative_strength`
- `composite_plus_all_advisories`
- `cash` safety baseline

Admission 不要求 advisory expert 成为 fold winner。`distinct_fold_winners` 仅保留为 standalone diagnostic。

Advisory 准入需要：

- 不超过预注册的 Composite 主性能下降上限；
- 至少一个风险维度改善；
- 跨 fold 不是单点收益；
- turnover、trigger rate、fallback rate 在上限内；
- 没有 PIT、成本、source、hash 或审计失败。

## 9. Artifact and boundary

每次运行必须隔离输出并生成：

- config/source/code/artifact hashes；
- daily positions and returns；
- decision audit；
- ablation metrics；
- fold summary；
- quality and fallback report；
- machine-readable status (`ready`, `pending`, `failed`, `passed`)。

`pending` 不得被解释为通过。历史 Phase 3 失败结果必须保留。任何 production 或 Streamlit 接入都需要单独 review、风险批准和部署 contract。
