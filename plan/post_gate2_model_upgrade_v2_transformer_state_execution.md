# Post-Gate-2 Transformer 状态—策略匹配 v2：跨窗口执行手册

> 状态：**W13/W14 implementation complete；CN_A ready / US source-data blocked；W15 implementation complete / runtime-upstream blocked**（2026-08-18）。CN_A W13 source lock 与 W14 五日标签、最大 20 日序列、四折隔离 panel 已 ready；US Phase-B 的 58 个非 Cash 专家只有 interval-trade reconstruction，不能证明精确逐日 `target_position`/turnover，故 W13-W15 fail closed。W15 encoder、fold-local scaler、train/validation-only fit 与 artifact runner 已实现，但当前 `.venv` 未安装 PyTorch，CN_A 四折 manifest 标记 `unavailable`，未生成 checkpoint。W16 不得启动。本手册不覆盖、不重解释、也不修改 v1 的 US `1/4`、CN_A `2/4` admission 结果。
>
> 当前起点：US/CN_A admission-specific Phase A–F 均已完成且 hash-verified，但 `moe_v2_regime_aware` 未达到“至少 3/4 split 不劣于 adaptive router”的冻结门槛。v2 的目标是学习一段时间内的点时可得市场/标的状态序列，并在严格 walk-forward 中将相似状态映射到其后 5 日最合适的专家策略；未识别到可靠状态时，默认使用同市场上一轮权威 full-run 总榜第 1 名模型。它**不是**用 Transformer 直接预测价格，也不接入 Streamlit。

## 1. 这份手册解决什么

现有 v1 是逐日、逐专家的 LightGBM utility gate：根据当日状态和专家近期统计，对每个专家预测未来 20 日 utility，再以 softmax 和风险约束形成仓位。它已经证明回撤/换手可控，但在收益非劣性上没有超过现有 `adaptive_router_v1`。

v2 研究下列不同假设：

```text
过去 L 日点时可得因子序列
  -> Transformer encoder 的状态 embedding
  -> 只在历史 memory bank 中检索相似状态
  -> 汇总该类状态随后 5 日的最优专家策略
  -> 相似度达到阈值才匹配并持有；否则使用同市场冻结的 full-run 最佳模型
  -> 持有期若出现日线可观察的跳水风险，提前退出到 Cash
```

“市场状态”是一个由连续多日瞬时特征组成的时序对象，而不是单个趋势指标。Transformer 的工作是将该序列压缩成可比较 embedding；状态—策略对应表是可审计的历史 memory bank，不是人工编写的规则表。

### 1.1 这份计划完成后可以操作什么

| 能力 | 输出 | 边界 |
|---|---|---|
| 点时状态序列 | `state_sequence_panel.parquet` | 仅含决策日及以前可得特征；US/CN_A 分开生成 |
| 5 日策略标签 | `best_expert_5d` 与逐专家未来 utility | 只用完整未来 5 交易日标签训练；测试期标签绝不进入 fit/memory |
| Transformer 状态编码 | fold-specific encoder、embedding schema | 每个 walk-forward fold 只由该 fold 的训练段拟合 |
| 状态—策略对应表 | `state_memory_bank.parquet` | 训练段历史 embedding、策略投票/utility、lineage 与日期范围 |
| 三阈值检索实验 | loose / balanced / strict summaries | 使用相同 encoder/source/split；不得用测试收益挑阈值 |
| 未识别状态默认策略 | market-specific `full_run_best_guard` | US/CN_A 各自读取已冻结 full-run 总榜第 1 名；不得跨市场或运行时重选 |
| 五日执行与跳水退出 | `state_match_decisions.parquet` | daily OHLCV 可观察风控；不使用盘中不可得信息 |
| 准入证据 | v2 admission summary / decision | 仍用 v1 的 3/4、回撤、换手硬门槛 |

### 1.2 当前的下一步决策

本计划的下一步不是改线上策略，而是先完成 `W13` 的 contract/source-lock 盘点和 `W14` 的可重放 5 日标签/状态序列。只有在 sequence、label、split、memory bank 的无泄漏测试全部通过后，才允许训练任何 Transformer。

### 1.3 Requirements summary

- **研究目标：** 学习多日点时状态序列的 embedding，并将历史相似状态与未来 5 日最优专家策略建立可回溯关联。
- **研究范围：** 只覆盖离线 `model-test`；US/CN_A 独立 source、独立 encoder、独立 memory bank、独立阈值和独立结论。
- **主候选：** `state_match_balanced + full_run_best_guard`；loose/strict、`adaptive_guard` 与 `cash_on_unmatched` 只作预注册消融。
- **硬门槛：** 延续 v1 的四折、至少 3/4 不劣于 adaptive、回撤不超过 `1.25x`、换手不超过 `1.25x`，并新增最低匹配覆盖率与完整审计要求。
- **非目标：** 不做 Transformer 直接价格预测，不修改现有默认策略，不在本计划内接入 Streamlit，不用测试期结果调参。

### 1.4 未识别状态的默认策略

“未识别到具体状态”包括相似度低于阈值、有效历史邻居少于 `minimum_support`，或检索投票未达到预先冻结的置信条件。primary 不再回退到 adaptive router，而是使用同市场上一轮权威 full-run 的冻结总榜第 1 名：

| 市场 | 权威 full-run | 冻结总榜第 1 名 | v2 expert ID | 当前冻结证据 |
|---|---|---|---|---|
| US | `full_us_deans_60` | `sm_bayesian`（SM+Bayesian） | `best_search` | `rank=1`、60/60 valid、`total_score=72.6667` |
| CN_A | `full_cn_a_deans_60` | `sm`（SM） | `sm` | `rank=1`、60/60 valid、`total_score=66.0667` |

W13 必须把 `model_summary.csv` SHA-256、source manifest SHA-256、`source_model_id -> expert_id` 映射和 `rank=1` 选择规则写入 config。当前 US `model_summary.csv` SHA-256 为 `0a1a24f03ddb1eef784948ca72c2001fe681976de8ce24b4cc74b451bdea0b56`，source manifest SHA-256 为 `31aadc6d97479bf22c048a8b36e6e830382a1c938d32fedea72f50efeef088d9`；CN_A 分别为 `d7a5e985ca7c4fefdddbf7be102cbb3dacfb3019789aa52bbbd4bd1b903a2e38` 与 `f46e4d677bbd051e91b27fd07625fa87f3b98ea9af45b28d67d4ef066e1d1aa9`。任何 hash、市场、排名、专家映射或逐日 `target_position` 不一致都不得静默改选第二名。

`full_run_best_guard` 只是未匹配时的稳定默认路径，不属于 Transformer 的增量贡献。W20 必须同时输出 `full_run_best_only` 独立对照，并把总收益拆成 state match、full-run-best fallback、adaptive/cash 消融三部分；若优势主要来自 fallback，不得表述为 Transformer 有效。若状态模型本身不可用但 full-run-best artifact 仍完整且 hash-verified，可降级到 full-run best；若 full-run-best artifact 也不可验证，则进入 Cash。memory/source hash 漂移仍使整个 runner 失败，而不是降级后继续生成正式证据。

### 1.5 在 Dean's Award 总路线中的位置

```text
Dean's Award 主计划
  Gate 0 contract -> Gate 1 正式实验 -> Gate 2 / RC 冻结与提交基线
    -> Post-Gate-2 动态专家组合 v1（Phase A-F）
      -> W11 未准入，W12 shadow mode blocked
        -> 本计划 Transformer 状态匹配 v2（W13-W20，新研究假设）
          -> 通过市场才进入 W21 非默认 shadow-mode 设计
            -> 后续独立计划：shadow 观察 -> 产品准入复审 -> 是否默认化
```

因此，本计划是 Dean's Award 已冻结作品之后的 **research extension / 下一代模型证据链**，不是 Gate 2、RC 或 8 月 23 日提交的阻塞项，也不能回写或美化已经冻结的 v1 阴性结论。对 Dean's Award 的价值主要是展示：项目不只给出一次排行榜，还能针对失败假设提出新模型、保持市场隔离、预注册门槛、接受阴性结果并保留完整可复现证据。只有 W20/W21 形成完整、可追溯的新证据时，才把它作为“后续研究”补充到答辩或材料；否则只列入 future work，不改原提交结论。

## 2. 固定概念与完成定义

### 2.1 状态、策略与标签

对每个 `date / symbol / market`：

- **瞬时状态向量 `x_t`**：当日收盘后可得的标的趋势/波动/流动性、市场收益/趋势/波动、已有 regime 状态和必要的执行上下文；不含未来收益、future label、测试期结果或人工“赢家”字段。
- **状态序列 `X_t`**：`[x_{t-L+1}, ..., x_t]`，短缺历史行直接不可训练/不可匹配，不用未来值补齐。
- **策略标签 `best_expert_5d`**：在每个可用专家中，选择后续完整 5 个交易日的、已扣源成本 `strategy_return` 所形成的最高风险调整 utility 的专家。Cash 必须作为候选，缺失专家保持 unavailable，不能以零收益伪装成功。
- **状态 embedding `z_t`**：Transformer encoder 对 `X_t` 的定长表示；仅在 fold-train 拟合后产生。
- **状态 memory bank**：过去训练日期的 `(z_t, market, symbol/segment, best_expert_5d, future_5d_utility, future_5d_drawdown, lineage)` 记录。
- **匹配**：当前 `z_t` 与 memory bank 中允许检索的历史 `z_i` 的 cosine similarity。必须是历史记录，且不能匹配自身、同日或未来日期。

### 2.2 5 日 utility（冻结初版）

对每个专家，标签只能在标签期完整时产生：

```text
future_5d_net_return = compound(strategy_return[t+1 ... t+5])
future_5d_downside   = sum(abs(min(strategy_return[t+1 ... t+5], 0)))
future_5d_turnover   = sum(turnover[t+1 ... t+5])
future_5d_utility    = future_5d_net_return
                       - 1.0 * future_5d_downside
                       - 0.1 * future_5d_turnover
best_expert_5d        = argmax(future_5d_utility)
```

`strategy_return` 已是源执行成本后的净收益，禁止再次扣源成本。若 top expert 的 utility 差距小于预先冻结的 `label_margin`，标签必须标记为 `ambiguous`，只可用于诊断或低权重训练，不能被静默当成确定赢家。

### 2.3 完成定义

一个 v2 窗口只有同时满足以下条件，才可标为 `complete`：

1. source config、code version、数据 snapshot、专家可用性、成本口径均已 hash-verified；
2. 所有状态特征都能证明在决策日可得，序列和标签边界通过 no-leakage test；
3. 每个 fold 的 encoder、memory bank、阈值和策略选择只使用该 fold 训练/验证期；
4. 三档阈值均有独立且完整的测试期输出，未以测试收益选阈值；
5. 跳水退出、五日持有、fallback、仓位/换手和未匹配状态均有逐日审计记录；
6. 报告明确区分“工程完成”“研究结果”“未匹配”“fallback”“not admitted”；
7. 没有改动 Streamlit、默认策略或既有 v1 admission 结论。

## 3. 统一执行协议

### 3.1 市场隔离与 source lock

- US 与 CN_A 各自训练、各自建立 memory bank、各自计算 similarity 分布和阈值，绝不共享 embedding、专家标签、SPY/000300 代理或超参数选择结果。
- 优先复用 v1 admission-specific、market-native 的 ready Phase-A/B source；若建立新的 5 日 panel，必须派生到新的输出目录，不能覆盖 `moe_admission_*`。
- 任何 source manifest、专家日线、market context、数据 snapshot 或 artifact SHA-256 不匹配时 fail closed；不得使用 `--allow-pending`。
- 旧 W11 测试段不能用作 encoder pretraining、threshold calibration、memory bank construction 或超参数选择。

### 3.2 Four-fold walk-forward 数据权限

对每个 `wf_01`–`wf_04`，权限严格分开：

| 数据角色 | 允许动作 | 禁止动作 |
|---|---|---|
| Train | fit scaler/encoder/classifier、写 training memory bank、计算训练相似度分布 | 使用 validation/test 日期、未来 5 日不完整标签 |
| Validation | 选择预先枚举的 sequence length / model size / fallback policy；校验三阈值协议 | 参与最终 test 指标、按 test 结果重新调参 |
| Test | 固定 encoder 和选择结果后逐日检索、执行、统计 | fit、threshold 重算、向 memory bank 写 test 行、看 future label 决策 |

每个 train/validation/test 边界至少保留 `max(sequence_length, 5)` 个交易日保护区：5 日防止标签跨界，sequence lookback 防止从边界之前错误拼接不属于该角色的样本。具体 purge/embargo 天数、日期和样本数写入 split manifest。

### 3.3 三阈值协议

使用 L2-normalized embedding 的 cosine similarity。对每一 fold，训练段做 leave-one-out / strictly-prior-neighbor 相似度统计：同一行、自身未来行、同日行均不能成为阈值样本。

| 名称 | 阈值 | 含义 | 用途 |
|---|---|---|---|
| `state_match_loose` | train similarity 的 `q50` | 宽松，覆盖更多状态 | 消融 |
| `state_match_balanced` | train similarity 的 `q75` | 覆盖与精度折中 | **v2 初版 admission primary** |
| `state_match_strict` | train similarity 的 `q90` | 仅接受高度相似状态 | 消融 |

三项 `q50/q75/q90` 是“冻结的计算规则”，不是由测试期选择的数值。每个 fold 的实际数值、样本量、coverage、相似度分布和 embedding-collapse 检查都必须写入 artifact。`0.75 / 0.85 / 0.92` 仅可作为本地 smoke 的固定绝对阈值，不得替代正式 protocol。

为避免“全部 fallback 也宣称不劣”，primary variant 还必须披露：

- `matched_decision_coverage`：达到阈值并实际采用状态对应策略的决定比例；
- `matched_active_coverage`：匹配且非 Cash 的比例；
- `fallback_full_run_best_coverage`、`fallback_adaptive_coverage` 与 `fallback_cash_coverage`；
- matched 子集相对 adaptive 的 5 日 utility 和已实现净收益。

若 primary 在任意市场的四折中 `matched_decision_coverage` 中位数低于预先冻结的最低 coverage，不能以大比例复制 full-run best 的方式申报准入；该阈值的默认候选为 `30%`，正式运行前必须在 config 明确锁定。

### 3.4 策略选择与五日执行

1. 当前日 `t` 输入完整 `X_t`，得 embedding `z_t`；
2. 只查询 memory bank 的 `date < t` 记录，取 top-k 相似邻居；k、相似度聚合和最少支持数均写入 config；
3. 若最高/聚合相似度达到当前阈值，以 similarity-weighted 的历史 utility/投票选择一个 `selected_expert_id`；同分用预先冻结的 expert ID 排序打破；
4. 未达到阈值不叫“预测失败”，而是明确记录 `unmatched`：
   - primary `full_run_best_guard`：使用同市场 frozen full-run 总榜第 1 名；
   - 消融 `adaptive_guard`：沿用同市场 frozen `adaptive_router`；
   - 消融 `cash_on_unmatched`：转 Cash；
5. 匹配成功后，采用所选专家在决策时产生的 `target_position`，最多维持 5 个交易日；不得在这五日内因为未来标签换专家；
6. 每日都执行跳水风控。触发后立即把后续仓位切换至 Cash，直到本次五日 holding window 结束；下一次正常再平衡时才允许重新匹配。

### 3.5 跳水退出（daily-bar 可审计）

本计划只使用项目已有日线，不能伪装为盘中止损。初版保留三个 config 化、市场专属、在 validation 冻结的触发器：

- `single_day_jump_down`：单日 asset return 低于 `-k × ATR_pct`；
- `entry_drawdown_stop`：自进入这次五日 holding window 后的收盘价回撤超过 ATR-normalized 门槛；
- `market_crash_guard`：同市场 benchmark 出现异常下跌且当前非 Cash。

触发器必须只用截至该日收盘能观察到的 OHLCV/benchmark 值；exit 从下一可执行日生效，日线回测不得假设当天收盘前已知当天收盘。每条记录写入 `jump_guard_trigger`、参数、entry date、risk exit date、被保护的仓位和未触发时的反事实结果（evaluation-only）。不同市场的 price-limit 结构不能共享阈值。

## 4. 固定决策与禁止事项

### 4.1 固定决策

- Transformer 是 **encoder + state retrieval**，不是 end-to-end 价格预测器；主输出是 state embedding、相似度和专家选择。
- 初版只使用 market-specific source 和 6–8 个已冻结专家；Cash 永远可选。
- primary 标签 horizon 为 5 个交易日；20/60 日只可作为明示消融，不能替代 primary 后再沿用结论。
- primary admission candidate 是 `state_match_balanced + full_run_best_guard`；loose、strict、adaptive-on-unmatched、cash-on-unmatched 都是公开消融。
- 相似度默认 cosine，embedding L2 normalization、top-k / minimum-support、threshold quantiles、fallback 和跳水触发器全部必须在 config 中冻结。
- US `sm_bayesian -> best_search` 与 CN_A `sm -> sm` 的 full-run-best 映射、排名来源和 hashes 必须在 W13 冻结；正式运行时不得重新看测试结果换 fallback。
- 每一专家收益继续使用同一 market execution config 下的已扣费 `strategy_return`，不重复收费。

### 4.2 禁止事项

- 不用 W11 测试段训练 Transformer、建 memory bank、选阈值、选专家或调跳水门槛；
- 不因某个 split 表现差而改变该 split 的标签、成本、时间窗口或 market proxy；
- 不跨市场训练、拼接 memory bank、引用 US/SPY artifact 给 CN_A；
- 不把无匹配/缺失 embedding/失败 encoder 静默写成成功匹配；
- 不以“与 full-run best 完全一样”的 fallback 大比例覆盖来绕过准入，也不把 fallback 本身的表现归因给 Transformer；
- 不在任何通过 W20 前向 Streamlit、HTML 导出、默认 workflow 或线上运行时接入该模型；
- 不把 Transformer 的 latent state 解释成因果市场规律或投资承诺。

## 5. 依赖图

```text
market-native ready Phase-A/B source + daily OHLCV / benchmark context
  -> W13 source-lock + v2 config freeze
  -> W14 5-day label + sequence state panel + leak tests
  -> W15 Transformer encoder + fold-local embedding schema
  -> W16 memory bank + 3 threshold retrieval + fallback audit
  -> W17 five-day execution + jump-risk guard + attribution
  -> W18 US full evidence chain
  -> W19 CN_A full evidence chain
  -> W20 market-specific admission comparison vs adaptive router
  -> only if admitted: W21 non-default shadow-mode design
```

## 6. 状态表

| 窗口 | 目标 | 市场 | 前置 | 状态 |
|---|---|---|---|---|
| W13 | v2 contract、source lock、config 和测试边界 | US/CN_A | v1 W11 | implementation complete；CN_A ready / US blocked：缺精确逐日执行源 |
| W14 | 5 日 utility、sequence panel、purged four-fold split | US/CN_A | W13 | implementation complete；CN_A ready / US upstream blocked |
| W15 | Transformer state encoder + fold-local fit | US/CN_A | W14 | implementation complete；CN_A blocked：PyTorch missing；US upstream blocked |
| W16 | memory bank、三阈值检索、策略选择与 fallback | US/CN_A | W15 | blocked |
| W17 | 五日执行、跳水退出、归因和风控审计 | US/CN_A | W16 | pending |
| W18 | US source-locked full run 与 reports | US | W13–W17 | pending |
| W19 | CN_A source-locked full run 与 reports | CN_A | W13–W17 | pending |
| W20 | 四折 admission comparison | US/CN_A | W18/W19 | pending |
| W21 | 非默认 shadow mode 设计/回滚验证 | 通过 W20 的市场 | W20 | blocked until admitted |

`complete` 仅表示该窗口已按验收完成，不代表策略已进入产品；`blocked` 表示前置准入条件不成立。

## 7. W13｜v2 contract、数据和实验前置冻结

**目标：** 把用户提出的“状态序列—五日最优策略—相似度匹配”翻译为可复现 contract，且不动 v1 输出。

**实现范围：**

- 新建 market-specific configs，例如 `transformer_state_us.json`、`transformer_state_cn_a.json`；
- 固定 source directories、market、seed、成本口径、候选专家、sequence length 候选、embedding dimension、model-size upper bound、top-k、minimum-support、三阈值规则、fallback、五日 holding 和跳水风控候选；
- 冻结 `full_run_best_guard`：US 为 `full_us_deans_60` 的 `sm_bayesian -> best_search`，CN_A 为 `full_cn_a_deans_60` 的 `sm -> sm`；把 rank、score、summary/source hashes 与逐日 position 可用性写入 manifest；
- 在 admission-specific source 上重新验证 source manifest、daily schema、market context、adaptive control 与 snapshot hashes；
- 明确 Transformer runtime（优先使用现有 PyTorch 依赖；如缺失，仅记录依赖缺口，未经单独确认不新增大型运行时依赖）；
- 写入 config SHA-256 和 code version，所有后续 runner 拒绝 drift。

**验收：** 两市场均能输出 `status=ready` 的 v2 source manifest；任何缺列、无 market-native benchmark、无 daily target position、无 Cash、full-run-best 映射/证据不一致或 source hash 漂移都 fail closed。

## 8. W14｜5 日标签与状态序列面板

**目标：** 建立可证明无泄漏的 `date / symbol / market` state sequence panel 和逐专家 5 日标签。

### 8.1 初版状态特征组

特征仅取现有可审计数据，按 `date / symbol` 聚合；初版至少包括：

- 标的：`asset_return_1`、短/中期趋势、realized volatility、ATR%、liquidity、drawdown、volume ratio；
- 市场：1/5/20 日 benchmark return、20 日 market trend/volatility、market drawdown；
- regime：`state_market_trend_up_20`、`state_market_high_volatility_20`、`state_market_regime_id_20`、状态持续期与最近状态切换标记；
- 相对关系：标的相对市场强弱、rolling beta/correlation、专家 peer correlation；
- 执行可得上下文：当前 `target_position`、过去收益/换手统计可以作为独立 ablation，但不得混入 future label。

`feature_schema.json` 必须逐列标记 source、lookback、shift、缺失策略、是否允许模型输入。所有 rolling 计算只能截至 `t`，会引用 `t+1` 或以后数据的列被拒绝。

### 8.2 Split 与标签边界

- 复用 W11 的四折 chronology，但为 5 日标签单独生成 `transformer_state_walk_forward_splits.csv`；
- 标签在 `t+1..t+5` 完整存在才有效；边界不足 5 日的样本为 `NaN`，不填补；
- sequence 仅使用同一 symbol/market 的历史窗口；不得跨 symbol 拼接；
- train/validation/test memberships 由 `label_end_date` 机器校验；
- 分别报告每个专家、每种 label、ambiguous 状态、市场 regime 的覆盖和样本数。

**输出：** `state_sequence_panel.parquet`、`state_label_panel.parquet`、`transformer_state_walk_forward_splits.csv`、`state_panel_quality.json/.md`、`state_panel_manifest.json`。

**验收：** 单元测试覆盖 label completeness、future-column rejection、role boundary、sequence chronology、同日/未来 memory 禁止条件；四个 split 都有足够 train/validation/test 样本，否则窗口 blocked 而非缩短要求。

## 9. W15｜Transformer 状态 encoder

**目标：** 只从训练段序列学习 fold-local 状态 embedding 与未来五日策略关系。

### 9.1 初版模型边界

```text
numeric state sequence [L, F]
  -> train-fold scaler / missingness mask
  -> linear projection + positional encoding
  -> small encoder-only Transformer
  -> pooled state embedding z_t
  -> auxiliary best_expert_5d classifier + utility-margin head
```

- 初版模型容量必须小、CPU 可跑、seed 可复现；配置锁定层数、heads、embedding dimension、dropout、epoch upper bound、early-stopping rule 和 batch size；
- `best_expert_5d` 是训练监督，但主决策仍由 state retrieval/memory bank 完成；classifier 只作 confidence、baseline 和 embedding-quality 诊断；
- 每个 fold 使用 train scaler / train encoder；validation 只供预先枚举的模型容量、sequence length 和 early stopping 选择；test encoder 不再 fit；
- 保存 train-fold normalization statistics、model hash、label vocabulary、feature schema、训练日志和 calibration metrics；
- 如果 embedding cosine 分布坍缩（近邻 similarity 无有效方差）或 classifier 低于 Cash/majority baseline，输出 `unavailable`，不得继续检索。

### 9.2 训练目标与评估

- 主监督：`best_expert_5d` cross-entropy，只对 non-ambiguous、available-label 行训练；
- 辅助监督：预测 top-1 与次优 expert 的 future utility margin，帮助定义选择置信度；
- 训练/validation 记录 top-1 accuracy、top-2 accuracy、macro-F1、per-expert recall、utility regret、calibration error 和 regime coverage；
- 不允许以 test accuracy / test utility 触发 checkpoint 选择。

**输出：** 每个 split 的 `transformer_encoder.pt`、`state_embedding_schema.json`、`train_metrics.json`、`validation_metrics.json` 与 manifest；全训练 refit 只能作为未来 research artifact，不得用于 walk-forward 指标。

## 10. W16｜状态 memory bank 与三阈值检索

**目标：** 以相似状态而不是未来答案，选择即将执行的专家策略。

### 10.1 memory bank contract

每条 memory 行至少包含：

```text
date, symbol, market, split_id, embedding, embedding_norm,
best_expert_5d, future_5d_utility, future_5d_net_return,
future_5d_drawdown, label_margin, label_status,
source_manifest_sha256, encoder_sha256, feature_schema_sha256
```

测试期逐日匹配只允许查询本 split 的训练期 memory bank；若实现 expanding memory，新增记录也必须是已经完整结算的历史标签，且写入点晚于其 `label_end_date`。没有完整标签的测试行绝不写入 memory。

### 10.2 检索与专家选择

- 计算 `max_similarity`、top-k mean similarity、每个候选专家的 similarity-weighted vote / weighted mean utility；
- 只有 `minimum_support` 个有效历史邻居时才允许匹配；
- 策略选择按 weighted utility 排名，随后用 vote、稳定 expert-ID order 处理平局；
- 记录邻居日期范围、symbol/segment mix、每位邻居的 similarity、label、utility，保证事后可解释；
- 三档阈值使用同一 embedding/memory，产生独立 decisions，不共享测试结果。

### 10.3 未匹配与异常

| 情况 | primary 行为 | 消融行为 | 审计字段 |
|---|---|---|---|
| 相似度不足 / support 不足 / 投票置信不足 | 同市场 `full_run_best_guard` | adaptive / Cash | `unmatched_reason`、`fallback_model_id` |
| embedding 无效 / 维度或 schema 不匹配 | full-run best；其 artifact 也不可验证则 Cash | adaptive / Cash | `embedding_failure_reason`、`fallback_reason` |
| 所选专家不可用 | full-run best；再不可用则 Cash | adaptive / Cash | `expert_unavailable_reason`、`fallback_model_id` |
| memory/source hash 漂移 | runner 失败 | runner 失败 | manifest error |

每条 fallback 决策还必须记录 `fallback_policy`、`fallback_source_run`、`fallback_source_model_id`、`fallback_expert_id`、`fallback_summary_sha256` 和 `fallback_source_manifest_sha256`。正式 summary 必须单列 `full_run_best_only`，使 state match 的增量可从相同 fallback 起点复算。

**输出：** `state_memory_bank.parquet`、`state_similarity_distribution.csv`、`state_thresholds.json`、`state_match_decisions.parquet`、`state_retrieval_report.md`、manifest。

## 11. W17｜五日执行、跳水退出与归因

**目标：** 将“匹配的策略未来执行五日”变成可回放、可审计而不是仅看标签的模拟。

### 11.1 每日执行状态机

```text
idle
  -> match accepted -> hold(selected expert, up to 5 trading days)
  -> unmatched -> full-run best guard（primary）/ adaptive / Cash（ablations）
  -> jump guard -> Cash until holding window end
  -> holding window ends -> next eligible match
```

- 同一 `symbol` 的 hold 不能重叠；matching frequency、是否允许每 5 日一次重选、以及 guard 后 cooldown 由 config 冻结；
- 组合日收益继续从实际 selected expert 的已扣费 `strategy_return` 取得，新的 state-level 仓位变动单独计算 execution turnover；
- 日线 jump guard 只能在观察到当日收盘后为下一可执行日下单；测试中记录 decision date、effective date、exit reason；
- 不能以未来 5 日 realized best expert 替换决策时的 selected expert。

### 11.2 必须输出的归因

- 按 split / market / symbol / regime / threshold 的 total return、max drawdown、turnover、匹配 coverage、fallback coverage、jump exit rate；
- selected expert frequency、actual best-expert hit rate、top-k retrieval consistency、predicted-vs-realized 5 日 utility regret；
- 相对 adaptive 与 `full_run_best_only` 的 active return；区分“match 贡献”“full-run best guard 贡献”“adaptive 消融贡献”“Cash 贡献”；
- 每个失败 split 至少列出 top-k 邻居、相似度、选择理由、实际后 5 日表现和 jump guard 是否改变结果。

**验收：** 可从 decisions 逐日重建每个 split 的仓位、匹配/未匹配、fallback、风险退出和收益；重建结果与 summary 完全一致。

## 12. W18｜US source-locked full evidence chain

**目标：** 按 W13–W17 固定配置，使用 US market-native source 完成四折研究。

- source 只允许 US v1 admission/source lock 和 US market context；
- 三阈值、primary/ablation、jump guard 都必须在正式 test 前已写入 config；
- 输出单独目录 `model-test/outputs/transformer_state_us/`，不得覆盖 `moe_*_admission_us/`；
- 任何 GPU 不可用时优先 CPU 小模型，禁止无记录地换模型容量或跳过 fold。

**验收：** 四折均 ready；hash/lineage、embedding distribution、coverage、决策重建、每项三阈值输出完整。

## 13. W19｜CN_A source-locked full evidence chain

**目标：** 用 CN_A market-native source 独立完成相同链路。

- 仅用 CN_A 冻结 snapshot、CN_A benchmark/context 和 market-native adaptive control；不得读 US/SPY artifact；
- CN_A price-limit、流动性和 benchmark 跳水阈值在 validation 固定，不能沿用 US 数值；
- 输出目录为 `model-test/outputs/transformer_state_cn_a/`；
- 所有归因表必须独立报告，不以 US 参数/阈值替 CN_A 背书。

**验收：** 与 W18 相同，且 market/source/embedding/memory lineage 全部标记 `CN_A`。

## 14. W20｜研究准入比较

### 14.1 比较对象

每个市场、每个 split 至少输出：

1. `adaptive_router_v1`（冻结 control）；
2. v1 `moe_v2_regime_aware`（历史参考，不能重算后改写）；
3. `full_run_best_only`（US=`sm_bayesian`，CN_A=`sm`；不做状态匹配的冻结 fallback control）；
4. `state_match_balanced + full_run_best_guard`（唯一 v2 primary candidate）；
5. `state_match_loose + full_run_best_guard`、`state_match_strict + full_run_best_guard`（阈值消融）；
6. `state_match_balanced + adaptive_guard`、`state_match_balanced + cash_on_unmatched`（fallback 消融）；
7. no-state / non-Transformer baseline（例如现有静态 regime 或 pooled-factor retrieval），用于确认 Transformer 序列表示确有增益。

### 14.2 冻结 admission 门槛

primary candidate 在单个市场必须同时满足：

1. 恰好 4 个可比较 purged walk-forward test splits；
2. 至少 `3/4` split 的 total return 不低于 adaptive router；
3. 每个 split 最大回撤不得劣于 adaptive router 的 `1.25x`；
4. 每个 split 的同口径 target-position execution turnover 不超过 adaptive 的 `1.25x`；
5. 不得只由少数标的贡献：报告 symbol breadth、中位 symbol relative return 和最差尾部；
6. `matched_decision_coverage` 中位数达到 config 中冻结的最低值，且 guard/fallback 占比透明；
7. jump guard、memory retrieval、encoder/schema、source lock、artifact hash 全部通过复算。

此外必须报告 primary 相对 `full_run_best_only` 的 split-level 增量、matched-only 增量和 fallback-only 贡献。若候选对 adaptive 的优势完全来自 full-run-best fallback，而 state-matched 决策没有可重复增量，则即使数值门槛通过，也只能表述为“fallback control 有效”，不能表述为 Transformer 状态匹配有效或据此推进默认化。

三阈值消融可以揭示 coverage—precision 取舍，但不能因测试后 loose 或 strict 表现较好就替换 primary。若要将另一个阈值作为新的 primary，必须在新的独立 research window 前重新冻结。

**not admitted 时：** 保留所有 reports 和失败归因；不得压低阈值、改用 W11 测试行、改变成本或借跨市场结果重跑到通过。

## 15. W21｜产品 shadow mode（条件窗口）

W21 只有 US 或 CN_A 至少一个市场通过 W20 后才能启动，且仅限通过的市场：

1. v2 仅作为单股 workflow 的非默认 experimental option；
2. UI 只读取已冻结 encoder、memory schema、config、threshold 与 manifest，不在 Streamlit 内训练、更新或写 memory；
3. 正常 unmatched 使用对应市场的 frozen full-run best；整个 v2 artifact/hash/schema/source market 不匹配时才 fail closed 到现有稳定 `adaptive_router_v1`；
4. 页面必须展示市场、训练时间范围、source hashes、threshold policy、matched/fallback model/fallback reason/jump guard reason 和 research-only 警示；
5. HTML 导出与模型评估页只能展示冻结证据，不把历史相似度解释为预测保证；
6. W21 只完成 shadow artifact、监控 contract、回滚与运行时性能验收；真实 shadow 观察放到后续独立计划，观察完成后才可讨论默认化。

W20 未通过时，W21 状态保持 `blocked`；不得实现半成品 UI 以制造“已产品化”印象。

### 15.1 本计划完成后的下一步

本计划的 `research-complete` 与“产品已经完成”是两件事。W20 产生可复算 admission decision 后，研究闭环即完成；是否继续由结果分支决定：

- **没有市场通过 W20：** 以 `not admitted` 收口，保存 source lock、四折结果、fallback-only 对照、失败 split 和 acceptance 记录；线上继续使用既有稳定策略，不启动 W21。Dean's Award 材料可把它作为“诚实的阴性研究与下一步假设验证”补充，但不得替换 Gate 2 / RC 的冻结数字。
- **至少一个市场通过 W20：** 仅对通过市场完成 W21 的非默认 shadow-mode 设计、artifact 打包、运行时 fallback 与回滚验证；另一市场继续保持 research-only。
- **W21 完成之后：** 新开独立 successor plan，顺序固定为 `shadow observation -> product admission review -> optional default promotion`。shadow observation 只记录纸面决策和运行指标，不影响用户默认仓位；至少监控 matched/fallback coverage、相对 adaptive 与 full-run-best 的增量、jump-guard 触发、延迟、artifact 完整性和状态漂移。观察完成后再决定保持实验选项、晋级默认或退役，不能因离线 W20 通过而自动默认化。
- **Dean's Award 叙事更新：** 只有 artifact、acceptance 和复算链完整时，才增加“Post-Gate-2 research extension”章节，展示从静态/硬路由到 MoE、再到时序状态检索的研究演进、消融、失败与限制；原提交版本和原始 v1 阴性结果继续保留。

## 16. 交付物与建议目录

```text
model-test/
  configs/
    transformer_state_us.json
    transformer_state_cn_a.json
    transformer_state_admission_us.json
    transformer_state_admission_cn_a.json
  model_test/
    transformer_state_panel.py
    transformer_state_model.py
    transformer_state_retrieval.py
    transformer_state_execution.py
    transformer_state_admission.py
  run_transformer_state.py
  run_transformer_state_admission.py
  outputs/
    transformer_state_us/
    transformer_state_cn_a/
    transformer_state_admission_us/
    transformer_state_admission_cn_a/
tests/
  test_transformer_state_panel.py
  test_transformer_state_model.py
  test_transformer_state_retrieval.py
  test_transformer_state_execution.py
  test_transformer_state_admission.py
document/acceptance/
  post_gate2_transformer_state_w13_w17_YYYYMMDD.md
  post_gate2_transformer_state_w18_w21_YYYYMMDD.md
```

每个输出目录最少包含 config snapshot、source manifest hash、data snapshot hash、feature/label schema、fold 训练记录、memory bank、threshold 分布、逐日 decisions、summary、report 与完整 artifact manifest。`model-test/outputs/` 被 Git 忽略，交接不能仅靠本地文件存在。

## 17. 测试与验收命令清单

实现后至少提供并运行：

```powershell
# v2 单元与 contract 回归（文件名在 W13 完成后固定）
.\.venv\Scripts\python.exe -m pytest `
  tests\test_transformer_state_panel.py `
  tests\test_transformer_state_model.py `
  tests\test_transformer_state_retrieval.py `
  tests\test_transformer_state_execution.py `
  tests\test_transformer_state_admission.py -q

# 保留既有动态专家组合 contract
.\.venv\Scripts\python.exe -m pytest `
  tests\test_moe_admission.py tests\test_moe_phase_b.py `
  tests\test_moe_phase_c.py tests\test_moe_phase_d.py `
  tests\test_moe_phase_e.py tests\test_moe_phase_f.py -q

# 每次正式 market run 之前
.\.venv\Scripts\python.exe model-test\preflight_research.py `
  --config model-test\configs\full_us_deans_60.json
.\.venv\Scripts\python.exe model-test\preflight_research.py `
  --config model-test\configs\full_cn_a_deans_60.json
```

必须额外测试：未来特征拒绝、标签完整性、self-match 排除、同日/未来检索排除、fold-local scaler/encoder、threshold quantile 固定、三阈值独立结果、未匹配时按市场选择 frozen full-run best、full-run-best hash/映射漂移拒绝、fallback-only 对照、五日持有状态机、jump guard effective-date、资金/仓位重建和 hash drift fail-closed。

## 18. 当前最先执行什么

W13 先把 v2 source contract、5 日标签口径、三阈值计算规则、US/CN_A full-run-best fallback 映射、jump guard 的 validation-only 选择协议和测试清单写成 config/schema；随后 W14 建可重放 panel。**在 W14 的无泄漏测试和 W13 source lock 完成前，不启动 Transformer 训练或任何 full-run。**

v1 的拒绝结论保持有效：本计划是新的、独立的研究假设，不能作为改变 W11/W12 状态或提前接入产品的理由。

## 19. 风险与缓解

| 风险 | 可能表现 | 缓解与停止条件 |
|---|---|---|
| 时序泄漏 | 测试相似状态能检索到未来标签，收益异常好 | manifest 记录 `label_end_date`、memory creation date；self/same-day/future-match 单测失败即停止 |
| embedding collapse | 不同状态 cosine similarity 几乎相同，三阈值没有区分度 | 记录 similarity histogram、方差、effective-neighbor count；低于最低方差则该 fold `unavailable` |
| 标签不稳定 | 多个专家 5 日 utility 接近，top-1 频繁翻转 | 使用 `label_margin` 标记 ambiguous；报告 top-2 accuracy 和 regret，不强行制造确定赢家 |
| 过度 fallback | 大多数时间复制 full-run best，却被误判为 v2 改善 | 披露 matched/fallback coverage 和 `full_run_best_only`；primary 未达到最低 coverage 或 matched-only 无可重复增量时不得宣称 Transformer 有效 |
| 阈值事后选择 | 测试后挑 q50/q75/q90 中最好的 | primary 在 W13 固定为 q75；其余仅消融，换 primary 必须新窗口预注册 |
| 五日锁仓伤害收益 | 状态已切换但仍持有旧专家 | 只允许预先冻结的 jump guard 提前退出；记录 hold window、guard 和反事实结果 |
| 日线跳水假设失真 | 用收盘结果假设当日收盘前能退出 | exit 从下一可执行日生效；报告 daily-bar limitation，不宣称盘中保护 |
| Transformer 过拟合 | 训练 accuracy 高，四折 test 失效 | 小模型、fold-local fit、validation early stop、与非 Transformer retrieval baseline 对照 |
| 市场迁移错误 | CN_A 借用了 US/SPY embedding 或阈值 | source/market/encoder/memory hash 逐层校验；任何跨市场 lineage fail closed |
| 计算/依赖不可复现 | 本机能跑，正式窗口缺少 PyTorch 或资源不足 | W13 先做 CPU smoke 与 runtime preflight；依赖缺失时标记 blocked，不静默换架构 |

## 20. 验证闭环与停止条件

每个窗口按以下顺序验证，任何一步失败都不得进入下一步：

1. **文档/配置验证：** config schema、market、seed、cost、sequence length、threshold policy、fallback、jump guard 均有值且可 hash。
2. **面板验证：** 必需列、时点特征、5 日完整标签、split membership、sequence chronology 和 source lineage 全部通过。
3. **模型验证：** fold-local scaler/encoder、训练/验证权限、embedding 维度、相似度分布、分类/utility baseline 可重放。
4. **检索验证：** memory 只含允许历史行；三阈值实际数值与 train-derived 统计一致；同一输入可生成相同邻居和策略。
5. **执行验证：** 五日 hold、fallback、jump guard effective-date、仓位/收益/换手重建与逐日 artifact 一致。
6. **研究验证：** US/CN_A 各自四折输出、matched/fallback 覆盖完整，W20 admission JSON 与 CSV 可由原始 decisions 重算。
7. **回归验证：** 既有 v1 相关测试和全量 pytest 通过；新增 v2 代码不能改变旧 workflow、默认策略和 v1 acceptance 记录。

停止条件包括：任一市场 source lock 非 ready、任一 fold 缺可比较 test、任一泄漏检查失败、embedding collapse、memory hash drift、coverage 低于冻结值、或 v2 primary 未达到 W20 硬门槛。停止后保留证据和失败归因，不通过改窗口或改成本重启。
