# A 股因子与 Composite 对齐实施计划

> 计划类型：跨窗口执行手册
> 目标：在不改变当前生产默认策略的前提下，为 CN_A 建立与 US 对称、但市场参数和权重独立的因子重构与 Composite advisory 研究链
> 当前状态：Phase 1 完成，Phase 2 待执行
> 适用市场：`CN_A`
> 主要研究市场：`US`、`CN_A` 分开训练、分开验证、分开解释
> 文档版本：v1.0

---

## 1. 执行摘要

Transformer state v2/v3 研究失败或停止后，项目继续推进了因子重构、异构专家池和 Composite advisory，但这些新模块主要围绕 US 构建：

- `core/macro_factors.py` 直接依赖 SPY、VIX 和 US sector map；
- `core/factor_pipeline.py` 没有 market-aware context contract；
- `core/expert_pool_v2.py` 使用 US Phase 2.5 权重；
- `model-test/configs/expert_pool_v2.json` 明确锁定 `market: US`；
- `document/interfaces/composite-advisory-research.md` 明确规定 `Market: US frozen universe`。

与此同时，CN_A 并非完全没有模型：

- CN_A 已有独立的 `full_cn_a_deans_60` / `full_cn_a_admission_60` 数据源；
- 已有 CN_A `MoE Phase A-F` research artifacts；
- 已有 CN_A-native `rsm_adaptive_v1` admission artifact；
- 但尚未有以 CN_A 独立因子权重为基础的 `composite_optimized` 和 Composite-centric advisory chain。

本计划的核心原则是：

> **共享接口，不共享未经验证的权重、宏观数据和专家结论。**

最终目标不是把 US 配置中的 `market` 字段改成 `CN_A`，而是建立：

```text
market-neutral factor interface
        |
        +-- US MarketContext
        |     +-- SPY / VIX / US sector map
        |
        +-- CN_A MarketContext
              +-- 000300 或冻结 universe benchmark
              +-- realized volatility / breadth
              +-- CN_A sector context

market-native factor panel
        |
        +-- US Composite + US advisory
        |
        +-- CN_A Composite + CN_A advisory
```

本计划完成后，CN_A 应具备独立、可审计、可回放的：

1. market-aware factor pipeline；
2. CN_A factor panel 和数据质量报告；
3. CN_A 独立 Composite-only baseline；
4. CN_A Composite advisory ablation；
5. 与 CN_A 现有 `SM/FSM/MoE` 的统一 walk-forward 比较；
6. 明确的 `ready / pending / failed / passed` 研究状态。

本计划不自动授权：

- Transformer 重新训练；
- dynamic MoE 替换现有策略；
- Streamlit 接入；
- production 默认策略修改；
- 跨市场共享权重。

---

## 2. 当前状态与问题边界

### 2.1 已存在且可复用的 CN_A 基础设施

以下内容已经存在，不应重复建设：

| 能力 | 现有位置 | 复用方式 |
|---|---|---|
| CN_A 标准行情加载 | `core/data.py`、`core/utils.py` | 保持标准字段 `date/open/high/low/close/volume` |
| CN_A 市场枚举 | `model-test/model_test/config.py` | 继续使用 canonical market `CN_A` |
| CN_A full universe | `model-test/outputs/full_cn_a_deans_60` | 作为正式 source lock 候选 |
| CN_A admission universe | `model-test/outputs/full_cn_a_admission_60` | 作为 admission / replay 对照源 |
| CN_A 成本 | `core/market_rules.py`、研究 config | `3 bps commission + 5 bps slippage` |
| CN_A MoE baseline | `model-test/outputs/moe_admission_cn_a` | 作为现有专家组合对照组 |
| CN_A v1/v2 MoE | `model-test/outputs/moe_v1_admission_cn_a`、`moe_v2_admission_cn_a` | 作为研究证据，不直接视为准入成功 |
| CN_A adaptive artifact | `model-test/outputs/transformer_state_cn_a/` source lineage / admission artifacts | 仅使用明确 market-matched、hash-verified artifact |
| 市场代理映射 | `core/regime_model.py` | 可参考 `CN_A -> 000300`，但不得假设其数据已在所有因子路径可用 |

### 2.2 已确认的问题

#### 问题 A：因子模块的市场依赖未抽象

`core/macro_factors.py` 目前的核心逻辑是：

```text
个股行情 -> SPY 对齐 -> VIX 对齐 -> US sector map
```

其字段包括：

- `vix_level`；
- `vix_regime`；
- `rel_strength_spy`；
- `market_breadth`（当前实际使用 SPY 动量近似）；
- `beta_20d`；
- `sector_momentum`（当前简化为 0）。

这些字段不能直接被解释为 CN_A 的市场因子。

#### 问题 B：Composite 权重是 US 样本权重

`core/expert_pool_v2.py` 中的 `PHASE25_WEIGHTS` 来自 US Phase 2.5。尤其是：

- `macd_z` 的负权重；
- `vix_level` 的权重；
- `volume_ratio_rank` 与动量的 interaction weight；

都必须在 CN_A 重新训练和验证，不能跨市场复制。

#### 问题 C：专家执行语义不适合直接搬到 A 股

当前部分专家定义为：

```text
market_neutral_signed
```

而 CN_A 普通股票策略通常应优先使用：

```text
long_only_or_cash
```

CN_A 版本的均值回归、相对强度和 advisory 不应默认产生空头仓位。

#### 问题 D：已有 CN_A MoE 不能等同于 CN_A Composite

CN_A MoE 已经存在，但它的专家来源主要是：

```text
naive / drift / sm / fsm / sm_bayesian / fsm_genetic /
adaptive_router / cash
```

这是一条基于既有策略 artifact 的动态组合链，不是基于 CN_A 独立因子权重训练出的 `composite_optimized`。它应作为对照，不应被错误描述为新的 CN_A Composite。

#### 问题 E：Transformer 不是本计划的前置依赖

当前 Transformer 研究状态：

- US primary `state_match_balanced` coverage 为 0%，研究停止；
- CN_A panel 已生成，但 W15 因 PyTorch 缺失而 unavailable；
- Transformer 即使未来重启，也不能修复因子模块的 US hard-code。

因此本计划不依赖 Transformer，不以 Transformer 结果作为 CN_A Composite 的准入条件。

---

## 3. 目标与非目标

### 3.1 目标

#### G1：建立市场无关的因子接口

同一套 pipeline API 能接收 US 或 CN_A 的 `MarketFactorContext`，但每个市场拥有自己的 benchmark、波动率、breadth、sector source 和质量状态。

#### G2：生成 CN_A market-native factor panel

基于冻结的 CN_A universe 生成 point-in-time 因子数据，确保：

- 没有未来数据泄漏；
- 因子来源、shift、lookback 和 missing policy 可追溯；
- 60/60 标的覆盖情况可机器检查；
- 缺失数据不会被静默填零或替换成 US 数据。

#### G3：独立训练和验证 CN_A Composite

CN_A 使用自己的训练折、成本和市场 context，重新获得 Composite 权重，并单独评估 `composite_only`。

#### G4：建立 CN_A Composite advisory

Composite 负责方向，advisory 负责确认、风险提示和减仓；CN_A 默认采用 long-only / cash 语义。

#### G5：统一对照和准入

在相同 CN_A universe、fold、horizon、成本和数据锁下比较：

- `SM`；
- `FSM`；
- 既有 CN_A MoE controls；
- `composite_only`；
- Composite advisory variants。

#### G6：保持生产安全边界

所有新产物保持 research-only，直到单独完成 review、准入和部署 contract。

### 3.2 非目标

本计划不包含：

- 把 US 权重复制到 CN_A；
- 把 SPY 或 US VIX 改名后伪装成 CN_A 数据；
- 将 CN_A 直接接入 Streamlit 默认策略；
- 删除或覆盖已有失败研究产物；
- 通过单一高收益 fold 宣布准入；
- 为了“补齐 A 股”而绕过 source/hash/PIT 校验；
- 重新启动 Transformer 训练作为优先事项；
- 直接重构现有 `MoE Phase A-F` 的研究 contract。

---

## 4. 总体架构

### 4.1 分层结构

```text
raw OHLCV / market artifacts
        |
        v
MarketFactorContext
        |
        v
market-aware FactorPipeline
        |
        v
market-native factor panel
        |
        +-- Composite weight fitting
        |       |
        |       +-- composite_only
        |       +-- advisory ablations
        |
        +-- existing SM/FSM/MoE controls
        |
        v
walk-forward evaluator
        |
        v
manifest + daily audit + quality report + decision
```

### 4.2 市场隔离原则

每个研究 run 必须同时锁定：

```text
market
universe
benchmark
factor source
execution config
horizon
fold membership
random seed
code version
source hashes
```

以下内容禁止跨市场共享：

- Composite 权重；
- benchmark return；
- macro factor artifact；
- sector mapping；
- model selection result；
- fold test result；
- adaptive/router artifact。

可跨市场共享的仅包括：

- Python interface；
- 因子名称和 schema 约定；
- 计算函数结构；
- 审计和 manifest 验证工具；
- evaluator 的通用实现。

---

## 5. 文件级工作范围

### 5.1 建议新增文件

| 文件 | 用途 |
|---|---|
| `core/market_factor_context.py` | 定义 `MarketFactorContext`、market normalization、source availability 和 benchmark context contract |
| `core/cn_a_market_factors.py` | CN_A benchmark、realized volatility、breadth、relative strength、sector context 计算/加载 |
| `core/composite_advisory_cn_a.py` | CN_A long-only Composite advisory 规则和不可变 decision interface |
| `model-test/configs/composite_cn_a.json` | CN_A Composite 研究配置 |
| `model-test/configs/composite_advisory_cn_a.json` | CN_A advisory 研究配置 |
| `model-test/build_cn_a_factor_panel.py` | 构建 CN_A factor panel 的 CLI |
| `model-test/run_cn_a_composite.py` | CN_A Composite-only 和权重训练 runner |
| `model-test/run_cn_a_composite_advisory.py` | CN_A advisory ablation runner |
| `model-test/model_test/cn_a_factor_panel.py` | panel schema、PIT 检查、quality report、manifest helper |
| `tests/test_market_factor_context.py` | market context 单元测试 |
| `tests/test_cn_a_market_factors.py` | CN_A benchmark/breadth/volatility 测试 |
| `tests/test_composite_cn_a.py` | CN_A Composite 计算和边界测试 |
| `tests/test_composite_advisory_cn_a.py` | advisory rule、fallback、long-only 测试 |
| `tests/test_cn_a_factor_panel.py` | panel completeness、PIT、hash 和 missingness 测试 |
| `document/interfaces/cn-a-factor-composite-research.md` | 冻结 CN_A 因子和 Composite contract |
| `document/acceptance/cn_a_factor_composite_phase*.md` | 每阶段验收记录 |

### 5.2 建议修改文件

| 文件 | 修改方向 |
|---|---|
| `core/factor_pipeline.py` | 增加 `market` / `market_context` 参数，保留旧 US 调用兼容性 |
| `core/macro_factors.py` | 从 US-specific class 拆出通用 market factor interface；US alias 保持兼容 |
| `core/expert_pool_v2.py` | 保留 US pool，不直接改写；必要时抽取 market-neutral expert policy helper |
| `document/interfaces/strategy-pipeline.md` | 增加 market-aware factor interface 和 CN_A factor contract |
| `document/interfaces/composite-advisory-research.md` | 保留 US contract，并注明 CN_A 使用独立 contract |
| `AI_CONTEXT.md` | 仅在实际阶段完成后更新 durable facts，不提前写“已完成” |

### 5.3 明确不应修改的边界

在本计划阶段不修改：

- `app.py` 默认 route；
- `ui/single_stock_workflow.py` 默认 family；
- `ui/multi_stock.py` 默认组合策略；
- production artifact selection；
- `adaptive_router_v1` US 默认行为；
- 现有 CN_A MoE source artifacts；
- 历史失败报告；
- Transformer v2/v3 研究结论。

---

## 6. 分阶段执行计划

## Phase 0：研究边界和 source lock 清点

### 目标

在编写新代码前，把 CN_A 的权威数据源、现有模型 artifact 和成本口径锁定，防止后续出现“同名不同源”。

### 工作项

1. 检查 `full_cn_a_deans_60` 和 `full_cn_a_admission_60` 的 manifest、snapshot、config SHA-256。
2. 明确本次 CN_A Composite 主研究使用哪个 source：
   - 推荐：先使用 `full_cn_a_admission_60` 做 admission development；
   - 完成参数冻结后，使用 `full_cn_a_deans_60` 做正式确认层。
3. 记录 60 个 symbol、日期区间、缺失日期、停牌、异常价格和字段完整性。
4. 检查 benchmark 来源：
   - 优先使用 `000300` 的 market-native 历史行情；
   - 如果 benchmark 覆盖不足，使用冻结 universe equal-weight close-return benchmark；
   - 两者都记录来源，不得隐式切换。
5. 明确 CN_A execution contract：

```text
commission_bps = 3
slippage_bps = 5
cost_treatment = source_net_no_recharge  # 对已有 strategy_return
                         或
cost_treatment = ohlcv_gross_charge_once # 对 OHLCV 重算实验
```

### 输出

```text
model-test/outputs/cn_a_factor_composite_source_lock/
  source_lock.json
  source_quality.json
  source_quality.md
```

### 停止条件

- source snapshot 缺失或 hash 不匹配；
- 60 标的无法完整确定；
- benchmark source 无法重建；
- execution config 与已有 CN_A contract 不一致。

### 验收

- source manifest 状态为 `ready`；
- snapshot aggregate hash 可重算；
- 60 个标的和日期边界明确；
- source、benchmark、cost 三者均有 machine-readable 记录。

---

## Phase 1：建立 MarketFactorContext

### 目标

让因子 pipeline 不再直接依赖 SPY/VIX，而是依赖市场上下文对象。

### 建议接口

```python
@dataclass(frozen=True)
class MarketFactorContext:
    market: str
    benchmark_symbol: str
    benchmark_frame: pd.DataFrame
    volatility_frame: pd.DataFrame | None
    breadth_frame: pd.DataFrame | None
    sector_frame: pd.DataFrame | None
    factor_availability: Mapping[str, str]
    source_manifest_sha256: str | None
```

建议提供：

```python
build_market_factor_context(
    market: str,
    *,
    data_dir: str | Path,
    universe_frame: pd.DataFrame | None = None,
    benchmark_frame: pd.DataFrame | None = None,
) -> MarketFactorContext
```

### 字段命名规则

新通用字段：

```text
market_vol_level
market_vol_regime
rel_strength_market
market_breadth
market_beta_20d
sector_momentum
```

US compatibility aliases：

```text
vix_level       -> market_vol_level for US only
vix_regime      -> market_vol_regime for US only
rel_strength_spy -> rel_strength_market for US only
```

CN_A 不得生成带有误导含义的 `rel_strength_spy` 或 `vix_level`。

### 兼容要求

- 旧 `compute_all_factors(df, symbol)` 调用继续工作，但默认只允许 US compatibility path；
- CN_A 必须显式传入 `market="CN_A"` 或 `MarketFactorContext`；
- CN_A 缺 context 时 fail-closed，不自动加载 US macro artifact；
- 所有输出 DataFrame 必须是 input 的 copy，不就地修改原始对象。

### 测试

- US legacy call regression；
- CN_A missing context fails clearly；
- context market mismatch fails；
- benchmark dates duplicate / unsorted fails；
- no US artifact is loaded for CN_A；
- factor aliases only appear in permitted market。

### 输出

```text
core/market_factor_context.py
更新后的 core/factor_pipeline.py
更新后的 core/macro_factors.py
tests/test_market_factor_context.py
```

### 验收门槛

- 现有 US 因子测试全部通过；
- 新增 context 测试全部通过；
- `CN_A` 请求不能读取 `spy_daily.parquet` 作为 benchmark；
- 无默认静默 fallback。

---

## Phase 2：实现 CN_A Market Context 和因子

### 目标

建立可审计的 CN_A market-native 因子来源。

### 2.1 Benchmark

推荐优先级：

1. `000300` 沪深 300 market-native daily frame；
2. 冻结 CN_A universe equal-weight close-return benchmark；
3. 如果两者均不可用，状态为 `pending`，不得伪造 benchmark。

benchmark 输出至少包括：

```text
date
close
return_1
return_5
return_20
volatility_20
drawdown_60
trend_20
```

### 2.2 Relative strength

```text
rel_strength_market_20
  = stock_return_20 - benchmark_return_20
```

只使用决策日及之前的数据。若 benchmark 是 universe equal-weight，必须记录当日有效 constituent count。

### 2.3 Market volatility

首版不依赖不可审计的中国 VIX。使用：

```text
market_vol_level = benchmark realized volatility
market_vol_regime = rolling percentile / frozen threshold regime
```

可以补充横截面波动：

```text
cross_sectional_volatility_20
```

但不能把 realized volatility 重命名为 VIX。

### 2.4 Market breadth

基于冻结 universe 和当日可用行情计算：

```text
breadth_up_ratio_1
breadth_up_ratio_20
breadth_new_high_ratio
breadth_new_low_ratio
```

分母必须是当日有效、非停牌、具备完整 lookback 的 constituent 数量，并输出 `market_constituent_count`。

### 2.5 Sector context

优先顺序：

1. 可验证的 A 股行业映射 + 行业指数历史；
2. 可验证的行业分类 + 同行业冻结 universe 横截面收益；
3. 不可用时字段状态为 `unavailable`，不填 0 假装中性。

### 2.6 A 股交易语义

因子层不负责交易执行，但必须提供字段供 advisory 使用：

```text
is_suspended
is_limit_up
is_limit_down
has_valid_close
tradability_status
```

### 输出

```text
core/cn_a_market_factors.py
data/macro/cn_a_market_manifest.json  # 如果使用独立 market artifacts
model-test/outputs/cn_a_factor_composite_source_lock/market_context.parquet
model-test/outputs/cn_a_factor_composite_source_lock/market_context_quality.json
```

### 停止条件

- benchmark 与个股日期对齐失败；
- breadth 分母不可解释；
- sector source 与 market 不匹配；
- 因子来源无法记录；
- 通过 forward fill 产生未来信息；
- 缺失率超过预注册上限且没有明确 pending 状态。

---

## Phase 3：构建 CN_A Factor Pipeline 和 panel

### 目标

为 60 个 CN_A 标的生成 point-in-time、可回放的完整 factor panel。

### 基础技术因子

继续复用通用技术因子，但明确每个字段的 lookback 和 source：

```text
mom_short_z
mom_long_z
macd_z
rsi_z
bb_position_rank
price_position_rank
vol_z
drawdown_rank
obv_trend_rank
volume_ratio_rank
```

### CN_A market-native 因子

建议首版字段：

```text
market_vol_level
market_vol_regime
rel_strength_market
market_breadth
breadth_up_ratio_1
breadth_up_ratio_20
market_beta_20d
sector_momentum
market_return_1
market_return_5
market_return_20
market_drawdown_60
market_constituent_count
```

### Panel 主键

```text
date
symbol
market
```

必须包含：

```text
source_market
source_symbol
lookback_metadata
availability_status
missing_reason
factor_schema_version
```

### PIT contract

每个因子必须记录：

```text
factor_name
source
lookback_days
shift_days
available_at_decision
missing_policy
```

默认规则：

- 当日收盘后产生的决策只用于下一交易日执行；
- 不允许用未来完整 horizon 的标签构造 factor；
- 训练 scaler、填充值和降维对象只能在 train fold 拟合；
- 任何外部 macro/sector 数据必须按 prior available date 对齐。

### 推荐 CLI

```bash
python model-test/build_cn_a_factor_panel.py \
  --config model-test/configs/composite_cn_a.json
```

### 输出

```text
model-test/outputs/composite_cn_a/
  cn_a_factor_panel.parquet
  factor_manifest.json
  factor_quality.json
  factor_quality.md
  factor_schema.json
  source_lineage.json
```

### 质量门槛

建议预注册：

- universe coverage：`60/60`；
- 每个 symbol 至少有完整主窗口；
- 核心技术因子在 warm-up 后缺失率不超过 `1%`；
- market context 因子缺失率单独报告，不静默并入技术因子；
- 日期重复率为 0；
- symbol/date 主键重复率为 0；
- 所有 finite-required 字段均为 finite；
- forward-looking audit 为 0 条；
- limit/停牌状态可解释。

如果缺失率不达标，应输出 `pending` 或 `failed`，不能输出 `ready`。

---

## Phase 4：CN_A Composite-only baseline

### 目标

先证明 CN_A Composite 本身有稳定、可重复的价值，再加入 advisory。此阶段不做复杂动态 gating。

### 配置

新增：

```text
model-test/configs/composite_cn_a.json
```

最低字段：

```json
{
  "schema_version": "1.0",
  "name": "composite_cn_a",
  "market": "CN_A",
  "universe": "full_cn_a_admission_60",
  "random_seed": 42,
  "horizon_days": 20,
  "execution": {
    "commission_bps": 3,
    "slippage_bps": 5,
    "cost_treatment": "ohlcv_gross_charge_once"
  },
  "benchmark": {
    "policy": "cn_a_native_then_frozen_universe_equal_weight"
  },
  "position_policy": "long_only",
  "selection_scope": "train_only",
  "output_subdir": "composite_cn_a"
}
```

正式 config 需要进一步冻结具体 source hashes、fold policy、factor schema hash 和 acceptance thresholds。

### Composite 计算

Composite 的形式可以保留 Phase 2.5 的结构，但权重必须从 CN_A train folds 重新估计：

```text
composite_score
  = Σ(weight_i * factor_i)
  + interaction_weight * interaction_term
```

仓位必须是 CN_A 适用的 long-only bounded position：

```text
composite_base_position ∈ [0, risk_budget]
```

禁止直接套用 US `PHASE25_WEIGHTS`。

### 训练限制

- 权重拟合只使用 train role；
- validation 用于冻结候选和预注册参数选择；
- test 只用于最终评估；
- 不允许根据 test Sharpe 反向改权重；
- 不允许用 full sample 计算 scaler 后再切 fold；
- interaction term 必须在 config 中显式声明。

### 必须输出的 baseline

```text
composite_only
sm
fsm
best_single_expert
equal_weight_experts
cash
```

`best_single_expert` 必须沿用 market train-only 规则，不能读 test columns。

### 输出

```text
model-test/outputs/composite_cn_a/
  composite_weights_by_fold.json
  composite_daily.parquet
  composite_positions.parquet
  composite_metrics.csv
  composite_fold_summary.csv
  baseline_comparison.csv
  composite_manifest.json
  composite_report.md
```

### 初步准入建议

`composite_only` 只有在以下条件全部满足后，才能进入 advisory 阶段：

1. 至少 `3/4` walk-forward folds 不劣于 CN_A `SM` 或冻结 best-single control；
2. 没有单 fold 极端收益主导整体结论；
3. 最大回撤不显著恶化，或有预注册的风险改善；
4. turnover 在 CN_A 成本下可接受；
5. daily positions、turnover、transaction cost 可重建；
6. PIT/source/hash audit 全部通过；
7. Composite 权重跨 fold 没有明显漂移到不可解释范围。

如果失败：

```text
status = stop_composite_only_gate_failed
```

仍可继续生成诊断报告，但不得进入 advisory 和 UI。

---

## Phase 5：CN_A Composite advisory

### 目标

在 Composite-only 通过基础门槛后，逐项测试 advisory 的风险增量价值。

### CN_A decision contract

建议定义不可变对象：

```python
@dataclass(frozen=True)
class CNCompositeAdvisoryDecision:
    date: pd.Timestamp
    symbol: str
    market: str
    composite_score: float
    composite_base_position: float
    trend_confirmation: float
    reversion_warning: float
    relative_strength_confirmation: float
    macro_risk_level: float
    macro_risk_cap: float
    advisory_multiplier: float
    final_position: float
    fallback_used: bool
    fallback_reason: str | None
    reason_codes: tuple[str, ...]
    policy_version: str
```

### 角色定义

| 组件 | 输入 | CN_A 允许动作 |
|---|---|---|
| `composite_cn_a` | CN_A train-fitted factors | 决定方向和基础仓位 |
| `momentum_cn_a` | trend/momentum factors | 确认或减仓，不反向开仓 |
| `mean_reversion_cn_a` | RSI/BB/price position | 超买预警、超跌确认，不能默认做空 |
| `relative_strength_cn_a` | CN_A benchmark/universe rank | 确认强弱或减仓 |
| `macro_defensive_cn_a` | realized vol/breadth/drawdown | 只收紧 exposure cap |
| `cash` | invalid/unsafe state | 归零仓位 |

### 安全边界

必须满足：

```text
final_position >= 0
final_position <= composite_base_position
```

除非另有单独批准，第一版不得允许 advisory 增加 Composite 的基础暴露。

明确规则：

- Composite 为 0 时，advisory 不得开仓；
- Composite 为多头时，advisory 只能维持或降低；
- macro cap 只能收紧，不能放大；
- reversion 与 relative strength 冲突时取保守降仓结果；
- benchmark/context 缺失时使用注册安全上限或 Cash；
- 交易不可执行、停牌或涨跌停状态不得被静默视为正常 fill；
- 所有 fallback 都要有 reason code。

### 必须比较的 ablation

按以下顺序运行，不得一次性只比较 all-in-one：

```text
composite_only
composite_plus_trend
composite_plus_reversion
composite_plus_relative_strength
composite_plus_macro_cap
composite_plus_all_advisories
cash
```

### 推荐 CLI

```bash
python model-test/run_cn_a_composite_advisory.py \
  --config model-test/configs/composite_advisory_cn_a.json
```

### 输出

```text
model-test/outputs/composite_advisory_cn_a/
  daily_decisions.parquet
  daily_positions.parquet
  daily_returns.parquet
  decision_audit.csv
  ablation_metrics.csv
  fold_summary.csv
  fallback_report.json
  quality_report.json
  advisory_manifest.json
  advisory_report.md
```

### Advisory 准入条件

至少满足：

1. 相对于 `composite_only` 不超过预注册的主性能下降上限；
2. 至少一个风险维度改善：最大回撤、尾部损失、波动率或 turnover；
3. 改善不能只来自一个 fold；
4. turnover、trigger rate、fallback rate 在上限内；
5. final position 始终满足方向和暴露边界；
6. 所有 decision 行可重建；
7. 没有 PIT、成本、hash 或 source audit failure。

如果只降低收益而没有改善风险，结论应为：

```text
Composite-only is preferred; advisory rejected.
```

---

## Phase 6：与既有 CN_A 模型统一比较

### 目标

把新 CN_A Composite 放到现有 CN_A 研究结果中进行同口径比较，避免孤立解读。

### 比较矩阵

| 类别 | 模型 |
|---|---|
| 基础策略 | `sm`、`fsm` |
| 课程基线 | `naive`、`drift`、`cash` |
| 既有组合 | `best_single_expert`、`equal_weight_experts` |
| 既有路由 | `adaptive_router_v1` |
| 新因子主模型 | `composite_only` |
| 新 advisory | `composite_plus_trend`、`composite_plus_reversion`、`composite_plus_relative_strength`、`composite_plus_macro_cap`、`composite_plus_all_advisories` |

### 统一口径

所有模型必须使用：

```text
same market = CN_A
same frozen universe
same fold boundaries
same primary horizon = 20 trading days
same execution config = 3 + 5 bps
same return semantics
same start/end policy
same symbol aggregation policy
```

对于已有 `strategy_return` artifact：

```text
cost_treatment = source_net_no_recharge
```

对于从 OHLCV 重新计算的 Composite：

```text
cost_treatment = ohlcv_gross_charge_once
```

两者不得混淆。报告必须明确说明是否直接比较 daily net returns，还是重新构造同一层级的 gross/net return。

### 必须输出

```text
model-test/outputs/cn_a_factor_composite_comparison/
  comparison_daily.csv
  comparison_metrics.csv
  comparison_fold_metrics.csv
  comparison_drawdown.csv
  comparison_turnover.csv
  comparison_report.md
  comparison_manifest.json
```

### 解释原则

- 不以单一 Sharpe 排名作为唯一结论；
- 报告 fold consistency、drawdown、turnover、fallback、coverage；
- 明确 `research-only`；
- 若 Composite 只在某些阶段有效，记录适用范围，不泛化到所有 CN_A；
- 不将 CN_A 结果外推至 US，反之亦然。

---

## Phase 7：可选的 production / Streamlit review

### 前置条件

只有在 Phase 0-6 完成且 CN_A Composite/advisory 获得明确 `passed` 后，才能启动此阶段。

必须完成：

1. 独立 code review；
2. security/data integrity review；
3. source manifest 和 artifact hash review；
4. UI fallback 和错误态设计；
5. 单股和多股 workflow contract review；
6. 线上延迟和缓存影响评估；
7. rollback 方案；
8. shadow mode 或只读展示验证。

### 推荐接入顺序

```text
research artifact reader
    -> read-only model evaluation page
    -> shadow mode metrics
    -> opt-in single-stock display
    -> explicit user-selected CN_A Composite
    -> only after separate approval, consider default change
```

禁止直接修改：

- 默认 strategy family；
- 默认 regime；
- 现有 US/A 股回退行为；
- 生产 model selection；
- 现有缓存 key contract。

---

## 7. 数据和模型 Contract

### 7.1 Factor panel schema

最低字段：

```text
date
symbol
market
close
volume
mom_short_z
mom_long_z
macd_z
rsi_z
bb_position_rank
price_position_rank
vol_z
drawdown_rank
obv_trend_rank
volume_ratio_rank
market_vol_level
market_vol_regime
rel_strength_market
market_breadth
market_beta_20d
sector_momentum
market_return_1
market_return_5
market_return_20
market_drawdown_60
market_constituent_count
```

审计字段：

```text
factor_schema_version
source_manifest_sha256
benchmark_source
benchmark_symbol
factor_available_at_decision
factor_missing_reason
lookback_metadata_json
```

### 7.2 Composite output schema

每个决策行至少包含：

```text
date
symbol
market
composite_score
composite_base_position
final_position
turnover
transaction_cost
gross_strategy_return
strategy_return
fold_id
role
fallback_used
fallback_reason
policy_version
config_sha256
source_manifest_sha256
```

### 7.3 Advisory output schema

至少包含：

```text
trend_confirmation
reversion_warning
relative_strength_confirmation
macro_risk_level
macro_risk_cap
advisory_multiplier
final_position
reason_codes
```

### 7.4 Manifest 必须记录

```text
market
universe
benchmark
source paths
source hashes
factor schema hash
config hash
code version
random seed
execution config
horizon
fold policy
return field
cost treatment
expert/advisory policy
artifact hashes
status
reason
```

### 7.5 状态语义

| 状态 | 含义 |
|---|---|
| `ready` | 输入和产物完整，但不代表策略通过准入 |
| `pending` | 依赖缺失，等待补齐 |
| `failed` | 运行或 contract 校验失败 |
| `passed` | 通过预注册准入门槛 |
| `unavailable` | 某组件不能提供有效结果，必须显式记录原因 |
| `stopped` | 触发停止条件，后续阶段不得自动运行 |

`ready` 不等于 `passed`。

---

## 8. 测试与验证计划

### 8.1 单元测试

必须覆盖：

- market normalization；
- context market mismatch；
- benchmark validation；
- date alignment；
- rolling factor warm-up；
- breadth denominator；
- suspended/limit state handling；
- finite numeric validation；
- long-only position bounds；
- Composite zero position cannot be opened by advisory；
- macro cap cannot increase exposure；
- missing context fallback；
- no input DataFrame mutation；
- manifest hash validation；
- cost calculation exactly once。

### 8.2 集成测试

至少覆盖：

1. CN_A 60-symbol factor panel build；
2. factor panel -> Composite runner；
3. Composite -> advisory runner；
4. existing CN_A MoE baseline -> comparison runner；
5. source manifest drift detection；
6. config market mismatch detection；
7. incomplete daily artifact detection；
8. rerun reproducibility。

### 8.3 PIT / leakage tests

必须验证：

- factor date 不晚于 decision date；
- future label 不进入 input frame；
- rolling benchmark 不包含未来日期；
- scaler/weight fitting 只在 train；
- validation/test 不反向改变训练结果；
- source `strategy_return` 不重复扣成本；
- decision day position 在规定执行时点生效。

### 8.4 质量阈值

建议最低目标：

```text
unit/integration tests: pass
core modified modules coverage: >= 80%
PIT violations: 0
duplicate primary keys: 0
manifest hash mismatch: 0
unexplained missing core factors: 0
cost double-charge: 0
position bound violations: 0
```

### 8.5 回归测试

以下现有测试必须继续通过：

```bash
pytest tests/test_macro_factors.py -q
pytest tests/test_factor_pipeline.py -q
pytest tests/test_expert_pool_v2.py -q
pytest tests/test_model_test_runner.py -q
pytest tests/test_backtest_market_rules.py -q
```

具体测试文件以当前仓库实际存在情况为准，不因新模块而删除旧测试。

---

## 9. 运行顺序和建议命令

以下命令是建议顺序；每个阶段应先确认上一阶段 manifest 状态后再运行下一阶段。

### 9.1 Phase 0 source lock

```bash
python model-test/preflight_research.py \
  --config model-test/configs/composite_cn_a.json
```

若现有 preflight 不支持新 config，则先扩展 preflight 或使用独立只读 source-lock 脚本，不绕过检查。

### 9.2 Phase 1-2 context smoke

```bash
python -m pytest tests/test_market_factor_context.py tests/test_cn_a_market_factors.py -q
```

### 9.3 Phase 3 panel build

```bash
python model-test/build_cn_a_factor_panel.py \
  --config model-test/configs/composite_cn_a.json
```

### 9.4 Phase 3 panel validation

```bash
python -m pytest tests/test_cn_a_factor_panel.py -q
```

### 9.5 Phase 4 Composite-only

```bash
python model-test/run_cn_a_composite.py \
  --config model-test/configs/composite_cn_a.json
```

### 9.6 Phase 5 advisory ablation

仅在 Composite-only gate 未触发停止条件后运行：

```bash
python model-test/run_cn_a_composite_advisory.py \
  --config model-test/configs/composite_advisory_cn_a.json
```

### 9.7 Phase 6 comparison

```bash
python model-test/compare_cn_a_composite.py \
  --config model-test/configs/composite_cn_a.json \
  --advisory-config model-test/configs/composite_advisory_cn_a.json
```

### 9.8 全量验证

```bash
pytest -q
```

如果全量测试中存在与本计划无关的已知失败，必须在验收报告中列出原始输出，不得隐藏。

---

## 10. 预注册准入和停止门

### 10.1 Phase 0 stop gate

触发任一条件即停止：

- source hash mismatch；
- source snapshot 缺失；
- CN_A universe 不完整；
- benchmark 不可审计；
- execution config 不一致。

### 10.2 Factor panel stop gate

触发任一条件即停止：

- PIT violation；
- 核心因子缺失无解释；
- 日期/symbol 主键重复；
- CN_A 误读 US macro artifact；
- 生成的 sector/volatility 字段无法解释；
- source manifest 状态非 `ready`。

### 10.3 Composite-only stop gate

触发任一条件即停止 advisory：

- `composite_only` 在多数 fold 明显劣于 baseline；
- 结果由单一 fold 主导；
- turnover 或 drawdown 超过预注册上限；
- 权重 fitting 读取 test 信息；
- cost double-charge；
- daily position 无法重建。

### 10.4 Advisory stop gate

触发任一条件即停止任何 UI/production 讨论：

- advisory 能在 Composite=0 时开仓；
- final position 超过 Composite base position；
- advisory 造成收益下降且无风险改善；
- fallback rate 超标；
- fallback 不可审计；
- CN_A 出现不允许的隐式空头语义；
- 多数 fold 未重复改善。

### 10.5 不得使用的“通过”表述

以下情况不能写成“模型成功”：

- 只有一个 fold 结果好；
- `ready` 但 acceptance gate 未通过；
- `pending` 产物被补零后可运行；
- 使用 US benchmark 或 US weight 运行 CN_A；
- 只比较累积收益，没有比较成本、换手和回撤；
- Transformer panel ready 但 model stage unavailable。

---

## 11. 研究报告要求

每个阶段都要生成中文报告和机器可读结果。

### 11.1 必须说明

- 本阶段目标；
- 使用的 market/universe/source；
- 代码版本和 config hash；
- 数据日期范围；
- 因子来源和可用性；
- return field 和 cost treatment；
- fold 设计；
- 缺失、fallback 和 unavailable；
- 结果与置信区间（如果已实现）；
- 是否触发 gate；
- 下一阶段是否允许运行。

### 11.2 结论模板

推荐使用以下明确格式：

```text
Status: ready / pending / failed / passed / stopped
Decision: continue / stop / diagnostic_only
Market: CN_A
Source: <source run>
Primary result: <one sentence>
Gate result: <pass/fail and threshold>
Known limitations: <explicit list>
Production impact: none
Streamlit impact: none
```

### 11.3 必须保留历史失败结果

不要删除或覆盖：

- US Phase 3 failed orthogonality report；
- Transformer US negative result；
- CN_A MoE W11/W12 failed admission decision；
- 任何 CN_A Composite gate failed 报告。

新研究应使用新的 output directory 和新的 manifest。

---

## 12. 风险清单与缓解方式

| 风险 | 影响 | 缓解 |
|---|---|---|
| 误用 SPY/VIX | CN_A 结论失真 | context market check + source manifest |
| 复制 US 权重 | 跨市场过拟合 | CN_A 独立 train-only fitting |
| sector source 不完整 | macro advisory 失真 | 显式 unavailable/pending |
| A 股 signed exposure | 交易语义错误 | long-only/cash policy |
| 停牌/涨跌停 | 回测高估 | tradability flags + audit |
| double-charge | 净收益错误 | return/cost contract assertion |
| test leakage | 研究无效 | fold/PIT tests |
| single-fold winner | 结论不稳 | 3/4 fold consistency gate |
| benchmark fallback 不可追踪 | 结果不可复现 | benchmark source field + hash |
| 直接接入 UI | 生产风险 | research-only boundary |
| Transformer 依赖缺失 | 项目阻塞 | 本计划完全不依赖 Transformer |
| 旧代码兼容性回归 | US 现有路径受损 | legacy regression tests |

---

## 13. 其他窗口的推荐执行清单

### 开始前

- [ ] 阅读本计划和 `AI_CONTEXT.md`。
- [ ] 阅读 `document/interfaces/strategy-pipeline.md`。
- [ ] 阅读 `document/interfaces/dynamic-ensemble-research.md`。
- [ ] 确认当前 branch 和 dirty changes，不覆盖他人修改。
- [ ] 确认 `full_cn_a_deans_60` / `full_cn_a_admission_60` source lock。
- [ ] 确认不修改生产默认策略。

### Phase 0

- [ ] 完成 CN_A source lock。
- [ ] 完成 benchmark 选择。
- [ ] 完成成本和 return semantics 锁定。
- [ ] 输出 source quality report。

### Phase 1

- [x] 实现 `MarketFactorContext`。
- [x] 保留 US legacy compatibility。
- [x] 禁止 CN_A 隐式读取 US artifact。
- [x] 通过 context 单元测试。

### Phase 2

- [ ] 实现 CN_A benchmark context。
- [ ] 实现 realized volatility。
- [ ] 实现 breadth。
- [ ] 实现 relative strength。
- [ ] 实现 sector context 或明确 unavailable。
- [ ] 完成 market factor quality report。

### Phase 3

- [ ] 构建 60-symbol CN_A factor panel。
- [ ] 完成 PIT audit。
- [ ] 完成 missingness audit。
- [ ] 完成 schema/source hash lock。

### Phase 4

- [ ] 训练 CN_A Composite 权重。
- [ ] 运行 `composite_only`。
- [ ] 与 SM/FSM/既有 controls 对照。
- [ ] 运行 Composite-only gate。
- [ ] 若失败，停止 advisory。

### Phase 5

- [ ] 实现 long-only CN_A advisory。
- [ ] 按单项 ablation 顺序运行。
- [ ] 检查 final position bounds。
- [ ] 检查 fallback/trigger/turnover。
- [ ] 运行 advisory gate。

### Phase 6

- [ ] 生成统一 CN_A comparison。
- [ ] 解释 fold consistency、risk、turnover。
- [ ] 生成最终 recommendation。
- [ ] 保持 research-only。

### 收尾

- [ ] 运行相关单元和集成测试。
- [ ] 运行全量 `pytest -q`，记录所有失败。
- [ ] 运行 `code-review` 和必要的 security/data-integrity review。
- [ ] 更新 `AI_CONTEXT.md`，只写实际完成的 durable facts。
- [ ] 新增 acceptance report，不覆盖历史报告。

---

## 14. 最终交付标准

当且仅当以下内容全部存在时，才可称为“CN_A 因子与 Composite 研究链完成”：

```text
[ ] CN_A source lock ready
[ ] market-aware factor interface ready
[ ] CN_A market context ready
[ ] CN_A factor panel ready
[ ] PIT/source/hash audit passed
[ ] CN_A composite_only artifact ready
[ ] composite_only gate has explicit passed/stopped result
[ ] CN_A advisory ablation artifact ready, or explicitly stopped
[ ] unified comparison report ready
[ ] tests and coverage recorded
[ ] production impact explicitly none, unless separately approved
[ ] Streamlit impact explicitly none, unless separately approved
```

“完成”不代表 Composite 一定优于所有基线。有效结论可以是：

- `Composite passed`；
- `Composite-only preferred`；
- `advisory rejected`；
- `CN_A factor panel ready but Composite gate failed`；
- `research stopped due to data quality`。

所有结论都必须以数据、fold、成本和审计结果为依据。

---

## 15. 推荐首个执行窗口

如果另一个窗口准备立即开始，建议只执行以下最小切片：

```text
1. Phase 0 source lock
2. Phase 1 MarketFactorContext
3. Phase 2 CN_A benchmark + breadth + realized volatility
4. Phase 3 factor panel smoke run
```

首个窗口不要同时做：

- Composite 权重优化；
- advisory rule tuning；
- Transformer；
- Streamlit 接入；
- 默认策略切换。

只有 factor panel 的来源、日期、PIT 和缺失质量通过后，才进入 Composite-only。这样可以把“数据/接口问题”和“模型效果问题”分开定位。
