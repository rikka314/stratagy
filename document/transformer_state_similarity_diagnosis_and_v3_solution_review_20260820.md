# Transformer 状态相似度诊断与下一阶段解决方案审核报告

> 日期：2026-08-20
> 研究范围：Post-Gate-2 Transformer-state v2，US W13–W18
> 文档性质：问题诊断、理论修正候选、实验方案与用户审核清单
> 当前状态：仅形成报告，尚未批准或实施任何 v3 修改
> 重要边界：现有 W18 结果保持不可变；本报告不能用于事后重写 W18 结论

---

## 0. 执行摘要

US W13–W18 的工程链已经完整完成，source、模型、memory、决策、五日执行、风险退出、换手、归因、summary 与全部 hash 均可复算。工程验收没有发现 CRITICAL/HIGH 实现缺陷。

但是，当前 v2 的研究假设没有得到有效检验。主要原因不是 W16 或 W17 没有运行，而是 W15–W16 的状态表示和检索协议出现了结构性问题：

1. 当前状态面板共有 22,604 条20日序列，但标签统计中 17,000 条为 ambiguous，仅 5,380 条 ready。
2. 每折原始 Train 有 5,529 或 7,904 条序列，最终进入 memory 的只有 1,286 或 1,901 条，保留率约23%–24%。
3. 正式 Train memory 的专家标签只剩 naive 和 cash，其他六个专家在 memory 中为0。
4. 名义上是16维 embedding，但中心化有效秩只有约1.25–1.27；第一主成分解释约88.7%–89.2%的方差，属于严重表示塌缩或强各向异性。
5. 训练期 strictly-prior Top-1 最大相似度的 q75 达到0.9988–0.9996。
6. 测试期 Top-1 相似度中位数仍有0.9797–0.9879，并非“只有65%相似”，但所有 balanced query 的最大相似度都低于上述极端阈值。
7. 每个测试 query 都成功找到了15个历史邻居，不存在“找不到邻居”的问题；全部 primary fallback 原因都是 similarity_below_threshold。
8. balanced 使用训练最大相似度 q75，名义上只有约25%的同分布样本能通过，却又要求测试 matched coverage 中位数至少30%，协议内部存在覆盖率目标不协调。
9. 当前 encoder 的训练目标是硬 best-expert 分类加 utility margin 回归，它能在主要只有 naive/cash 的训练集上取得90%–95%准确率，但并未直接保证余弦空间具有邻域检索意义。
10. 当前 W18 的正确结论是“旧协议下的工程完整阴性结果”；它不能证明 Transformer 理论无效，也不能证明仅降低阈值即可修复。

本报告的核心建议是：

- 不要直接降低阈值；
- 不要只增加更多高度重叠的逐日窗口；
- 先修标签与表示学习，再修相似度校准；
- 将硬 best-expert 标签改为完整专家 utility 向量；
- 将训练目标改为 utility 回归、排序学习和表示防塌缩；
- memory 按五日频率或其他预注册 stride 降低重复；
- 使用固定 Train memory，由 Validation query 校准 Test 使用的相同检索统计；
- 使用 Top-5 平均或第5近邻，而不是只看 Top-1 最大值；
- 增加 effective rank、主成分占比、邻居 utility 一致性和简单 kNN baseline 等硬停止条件；
- 新协议必须版本化，并在新的未见外层测试窗口上验证。

在用户审核前，不建议直接启动 CN_A W19 的旧协议正式 full run，也不建议在当前 US Test 日期上改阈值后重跑 admission。

---

## 1. 报告目的与审核方式

### 1.1 本报告要回答的问题

本报告集中回答以下问题：

1. 当前“状态相似度”究竟如何计算？
2. q50、q65、q75、q90 与余弦相似度0.50、0.65、0.75、0.90有什么区别？
3. 四个 fold 是否等于四种状态？
4. 每只股票是否拥有独立状态—策略表？
5. Top 15、minimum support=5 与匹配阈值是什么关系？
6. 当前 coverage=0% 是因为没有邻居，还是因为阈值过高？
7. 当前数据量是否不足？
8. 当前 embedding 是否出现表示塌缩？
9. 当前高分类准确率是否能证明 embedding 可用于检索？
10. 应该只改阈值、增加数据、修改标签、修改损失，还是重构整个检索协议？
11. 哪些方案属于必要修复，哪些属于可选研究增强？
12. 如何设计不会再次窥探 Test 的下一阶段实验？

### 1.2 审核状态定义

本报告中的方案分为四类：

| 标记 | 含义 |
|---|---|
| 必须 | 不修正就不应继续正式 admission |
| 推荐 | 高概率改善可解释性或泛化，建议纳入 v3 |
| 可选 | 只有基础方案仍不充分时再增加 |
| 不推荐 | 容易造成事后调参、伪样本扩大或错误归因 |

### 1.3 事实、推断与方案严格分离

全文使用以下语义：

- 已确认事实：由当前 artifact、代码或复算直接证明；
- 高可信推断：由多个已确认事实共同支持，但仍需实验验证；
- 候选方案：尚未实施，需要用户审核；
- 建议门槛：用于讨论的预注册候选，不是已经冻结的正式标准。

---

## 2. 证据范围与不可变边界

### 2.1 当前正式 artifact

| 阶段 | Manifest SHA-256 | 状态 |
|---|---|---|
| W13 source | 54069e783ac4efe594d55a659ac387dbe7cd0a397652b70e1b81afcb8252a6fd | ready |
| W14 panel | bc791ff9a0fec54d049d6514ad6e890ac9f1bd72d146c05830af3e72632802b0 | ready |
| W15 model | 305de52fb65c97d71c30c799447edcd5e639c79352f1cd77ecb640c3131ce17d | ready |
| W16 retrieval | af96a29849d7b0288735f1393e608f6be6d77c5eda243c1f8d2a9476e5e3fceb | ready |
| W17 execution | c11ae604713c880e2640ce80f6841d7eb05c3600b09192af49596af5600507ed | ready |
| W18 evidence | 803d05f5e0299dd21a258a32b00ebbdcd0cff2fe08083d11234f0b2f0395b700 | ready |

正式 code lock：

    b07e97aa8bd6433a3fea8fe43cb424751e76b99dbffb9a5d92e211dc45753f23

### 2.2 已验证工程事实

- 420份冻结专家 exact-daily 已验证；
- 60份 adaptive exact-daily 已验证；
- admission source 没有被覆盖；
- frozen full-run returns 没有被修改；
- 四个 W15 fold 的 checkpoint、schema、metrics 和 manifest hashes 全部通过；
- W16 decisions 为11,520行；
- W17 daily audit 为57,600行；
- 每个执行窗口严格5日；
- execution turnover 可从 target position 精确重建；
- summary 可从 daily audit 完全重建；
- 目标测试77 passed；
- 全仓测试310 passed；
- 独立代码和 artifact 审查为 APPROVE。

### 2.3 不可事后修改的结论

当前 W18 使用旧协议完成。即使本报告提出更合理的新协议，也不能：

- 修改旧 W18 manifest；
- 在相同 Test 日期上降低阈值后宣称正式通过；
- 将 loose 的结果事后替换为 balanced primary；
- 把 full-run-best fallback 收益归因给 Transformer；
- 删除旧阴性结果；
- 用 CN_A 结果重解释 US 旧窗口。

---

## 3. 当前 v2 端到端过程

### 3.1 每个状态是什么

对股票 a 和决策日 t，当前状态输入是同一股票最近20个交易日的28项点时可得特征：

    X(a,t) = [x(a,t-19), ..., x(a,t)]

特征包括：

- 股票收益、趋势、波动率、ATR、流动性、回撤、成交量比例；
- 市场收益、趋势、波动率、回撤和市场 regime；
- 股票相对市场强弱、beta、correlation；
- 专家近期活跃度、净收益、换手和 peer correlation。

序列内部不跨股票；AAPL 的20日序列只由 AAPL 构成。

### 3.2 四个 fold 是什么

四个 fold 是四组按时间推进的 Train / Validation / Test 实验，不是四种市场状态：

    Fold k:
      Train
      -> protection/purge
      -> Validation
      -> protection/embargo
      -> Test

每个 fold 拥有独立 scaler、encoder、checkpoint、memory 和阈值。

### 3.3 当前 encoder

当前 W15 结构为：

    20日 × 28特征
      -> Train-only 标准化
      -> 缺失 mask 拼接，模型输入为20 × 56
      -> 线性投影
      -> 正弦位置编码
      -> 1或2层 Transformer Encoder
      -> 时间维 mean pooling
      -> LayerNorm
      -> 16维 embedding
      -> best-expert 分类头
      -> utility-margin 回归头

训练主目标是 best_expert_5d 硬标签交叉熵，辅助目标是 top1 与 top2 utility margin。

### 3.4 当前 memory

memory 只保留：

- role=train；
- label_status 为 ready/available/complete/valid；
- best_expert_5d 非空；
- utility、return、drawdown、margin 全部有限；
- embedding 有限且范数大于0。

每条 memory 记录：

    date
    symbol
    market
    split_id
    normalized embedding
    best_expert_5d
    future_5d_utility
    future_5d_net_return
    future_5d_drawdown
    label_margin
    lineage hashes

memory 是同市场、同 fold 跨股票共享的。AAPL query 可以检索历史 MSFT、NVDA 或其他股票状态，但不能跨市场或跨 fold。

### 3.5 当前余弦相似度

对 query embedding q 和 memory embedding m：

    q_hat = q / ||q||2
    m_hat = m / ||m||2
    similarity(q,m) = q_hat dot m_hat

理论范围是[-1,1]。

### 3.6 当前阈值计算

对 Train memory 中每个状态 j，只查询更早的 Train 状态：

    s_j = max cosine(z_j, z_i), where date_i < date_j

得到一组 Train strictly-prior Top-1 最大相似度，再取：

| Variant | 当前统计 |
|---|---|
| loose | Train Top-1 max similarity 的 q50 |
| balanced | Train Top-1 max similarity 的 q75 |
| strict | Train Top-1 max similarity 的 q90 |

这里的 q75 是分布的第75百分位，不是相似度等于0.75。

### 3.7 当前 Test 匹配

对每个 Test query：

1. 查询所有 date < query_date 的 memory；
2. 按相似度取 Top 15；
3. 只要候选数至少5，就通过 support gate；
4. 只比较 Top 15 中的最大相似度与阈值；
5. 当前不要求15个邻居全部超过阈值；
6. 当前也不要求第5近邻超过阈值；
7. 如果 Top-1 最大值低于阈值，直接 fallback。

当前判定公式是：

    matched only if max(s_1, ..., s_15) >= threshold

### 3.8 当前专家选择

如果通过阈值，Top 15 邻居按其硬标签 best_expert_5d 分组。

当前权重：

    w_i = max(similarity_i, 0)

对专家 e：

    weighted_mean_utility_e
      = sum(w_i * utility_i for label_i=e)
        / sum(w_i for label_i=e)

    weighted_vote_e
      = sum(w_i for label_i=e)
        / sum(w_i for all neighbors)

选择顺序：

1. weighted_mean_utility 最高；
2. 相同时 weighted_vote 更高；
3. 再相同时 expert ID 稳定排序。

### 3.9 当前五日执行

- 决策在 t 收盘后产生；
- 决策目标从 t+1 生效；
- 同一 symbol 的持有窗口不重叠；
- 最长持有 t+1 至 t+5；
- source-net strategy_return 不重复扣费；
- jump guard 只在收盘观察后影响下一可执行日；
- unmatched primary 使用同市场 frozen full-run best；
- full-run best 不可用时进入 Cash。

---

## 4. 关键术语澄清

### 4.1 q65 不等于相似度0.65

q65 表示“分数分布的第65百分位位置”。如果实际分数分布集中在0.96–0.99，那么 q65 的实际阈值可能是0.98，而不是0.65。

### 4.2 四个 fold 不等于四个状态

四个 fold 是四组时间切分。每个 fold 中有上千条历史状态。

### 4.3 minimum support=5 不等于使用5个邻居

当前最多取15个邻居，5只是最低候选数量。正式运行中每个 query 都找到了15个邻居。

### 4.4 coverage=0% 不等于没有执行

coverage=0% 表示没有任何 primary 决策由状态匹配触发。W17 仍然执行了完整五日窗口，但全部 primary 依赖 fallback。

### 4.5 高分类准确率不等于相似度空间有效

分类头只需要找到能区分主要标签的决策边界。它不必保证 embedding 的余弦距离具有稳定的近邻含义。

---

## 5. 当前数据与模型诊断

### 5.1 面板规模

| 指标 | 数值 |
|---|---:|
| 状态行 | 29,568 |
| 20日序列 | 22,604 |
| ambiguous 标签 | 17,000 |
| ready 标签 | 5,380 |
| unavailable 标签 | 300 |

ready 在上述标签总数中的占比约23.7%。这说明原始状态不少，但可形成明确硬赢家标签的状态很少。

### 5.2 每折 Train 与 memory

| Fold | Train 序列 | Memory 行 | 保留率 | 股票数 | Memory 独立日期数 |
|---|---:|---:|---:|---:|---:|
| wf_01 | 5,529 | 1,286 | 23.26% | 60 | 121 |
| wf_02 | 7,904 | 1,901 | 24.05% | 60 | 161 |
| wf_03 | 7,904 | 1,901 | 24.05% | 60 | 161 |
| wf_04 | 7,904 | 1,901 | 24.05% | 60 | 161 |

已确认：每个 Test query 的 support_count 都是15。因此“memory 太小导致找不到15个邻居”不成立。

### 5.3 Memory 标签退化

| Fold | naive | cash | adaptive | best_search | drift | sm | fsm | ml_filter |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| wf_01 | 817 | 469 | 0 | 0 | 0 | 0 | 0 | 0 |
| wf_02 | 1,119 | 782 | 0 | 0 | 0 | 0 | 0 | 0 |
| wf_03 | 1,119 | 782 | 0 | 0 | 0 | 0 | 0 | 0 |
| wf_04 | 1,119 | 782 | 0 | 0 | 0 | 0 | 0 | 0 |

结论：

- 名义 vocabulary 有8个专家；
- 实际 Train memory 只有2个专家；
- 当前检索无法真正学习8类状态—策略关系；
- 训练准确率主要反映 naive/cash 二分类，而不是完整专家路由能力。

### 5.4 表示几何

有效秩使用中心化 embedding 协方差特征值计算：

    effective_rank = (sum eigenvalues)^2 / sum(eigenvalues^2)

| Fold | 名义维度 | 有效秩 | PC1 方差占比 | PC2 方差占比 |
|---|---:|---:|---:|---:|
| wf_01 | 16 | 1.252 | 89.21% | 4.48% |
| wf_02 | 16 | 1.266 | 88.73% | 4.10% |
| wf_03 | 16 | 1.266 | 88.73% | 4.10% |
| wf_04 | 16 | 1.266 | 88.73% | 4.10% |

高可信结论：当前16维 embedding 的大部分变化集中在一个主方向，存在严重表示塌缩或强各向异性。

### 5.5 Memory 全体 pairwise cosine

| Fold | Mean | Std | q50 | q95 | q99 |
|---|---:|---:|---:|---:|---:|
| wf_01 | 0.7023 | 0.3052 | 0.8313 | 0.9888 | 0.9954 |
| wf_02–04 | 0.5497 | 0.4324 | 0.7304 | 0.9847 | 0.9932 |

并非所有状态彼此都在0.99以上；但最近邻尾部高度集中接近1。

### 5.6 Train strictly-prior Top-1 最大相似度

| Fold | Mean | Std | q50 | q75 | q90 |
|---|---:|---:|---:|---:|---:|
| wf_01 | 0.9942 | 0.0278 | 0.998635 | 0.999598 | 0.999800 |
| wf_02–04 | 0.9927 | 0.0245 | 0.996761 | 0.998793 | 0.999514 |

这正是当前 loose / balanced / strict 阈值。

### 5.7 Test Top-1 相似度

| Fold | Mean | Std | q50 | q95 | Max |
|---|---:|---:|---:|---:|---:|
| wf_01 | 0.9850 | 0.0126 | 0.9879 | 0.9949 | 0.9970 |
| wf_02 | 0.9795 | 0.0195 | 0.9857 | 0.9950 | 0.9975 |
| wf_03 | 0.9763 | 0.0353 | 0.9857 | 0.9968 | 0.9986 |
| wf_04 | 0.9733 | 0.0208 | 0.9797 | 0.9936 | 0.9968 |

测试相似度绝对值很高，但仍低于由 Train 自我近邻形成的极端阈值。

### 5.8 Test Top-15 平均相似度

| Fold | Mean | q50 | q95 |
|---|---:|---:|---:|
| wf_01 | 0.9799 | 0.9834 | 0.9919 |
| wf_02 | 0.9727 | 0.9807 | 0.9928 |
| wf_03 | 0.9664 | 0.9788 | 0.9947 |
| wf_04 | 0.9637 | 0.9710 | 0.9904 |

这些数值可作为未来 Validation Top-k 校准的参考，但不能直接用于修改当前 Test 阈值。

### 5.9 三阈值 Test coverage

| Fold | Loose | Balanced | Strict |
|---|---:|---:|---:|
| wf_01 | 0/960 = 0.00% | 0/960 = 0.00% | 0/960 = 0.00% |
| wf_02 | 7/960 = 0.73% | 0/960 = 0.00% | 0/960 = 0.00% |
| wf_03 | 49/960 = 5.10% | 0/960 = 0.00% | 0/960 = 0.00% |
| wf_04 | 1/960 = 0.10% | 0/960 = 0.00% | 0/960 = 0.00% |

即使事后观察 loose，最高也只有5.10%，仍远低于30%。但 loose 只是消融，不能替换已经冻结的 balanced primary。

### 5.10 训练与验证指标的解释

| Fold | Train Top-1 | Validation Top-1 | Validation Macro-F1 | Validation ready 样本 |
|---|---:|---:|---:|---:|
| wf_01 | 90.28% | 91.33% | 0.610 | 196 |
| wf_02–04 | 95.21% | 90.76% | 0.611 | 249 |

这些准确率不能直接解释为“八类专家预测准确”：

- Train 实际只观察到 naive/cash；
- wf_01 Validation 中 ml_filter recall=0；
- wf_02–04 Validation 中 sm recall=0；
- 高准确率主要由主导的 naive/cash 类贡献；
- validation margin MAE 高于 Train，显示时间外不稳定性。

---

## 6. 已确认结论、推断与尚未证明事项

### 6.1 已确认结论

1. 工程链正确执行且可复算。
2. 每个 query 都有15个邻居。
3. balanced 0% 的直接原因全部是 similarity_below_threshold。
4. q75 不是相似度0.75。
5. 当前 memory 只有 naive/cash 两类硬标签。
6. 当前 embedding 有效秩约1.25。
7. 当前 Train Top-1 阈值接近1。
8. 当前 Test Top-1 仍然很高，但整体低于 Train 自我近邻阈值。
9. q75 名义接受率约25%，与最低30% coverage 目标不协调。
10. 当前 W18 不能进入 W20 admission。

### 6.2 高可信推断

1. 大量连续20日窗口高度重叠，使表面样本量高于有效独立样本量。
2. 多股票共享市场特征，使同日跨股票 embedding 可能由共同市场方向主导。
3. 硬标签和 ambiguous 过滤造成专家标签多样性丢失。
4. 分类目标没有直接训练余弦邻域，因此高分类准确率与低检索质量可同时存在。
5. mean pooling、LayerNorm、L2 normalization 和二类主导监督共同促成强各向异性，但每个组件的因果贡献仍需消融。
6. Test 相似度整体低于 Train 自我近邻，提示时间分布漂移或 Train 表示过拟合。

### 6.3 尚未证明

1. 不能证明 Transformer 理论本身无效。
2. 不能证明只增加数据就能修复。
3. 不能证明只降低阈值就能修复。
4. 不能证明 pooled cross-symbol memory 一定优于同股票或 segment memory。
5. 不能证明 Top-5 平均一定是最终最佳统计。
6. 不能证明16维维度太小；当前问题是有效秩低，不是名义维度必然不足。
7. 不能证明扩大模型层数或参数量会改善。
8. 不能用当前已见 Test 选择 v3 最优方案后再次申报正式准入。

---

## 7. 根因清单与严重性

| ID | 根因 | 证据 | 严重性 | 是否阻断新 admission |
|---|---|---|---|---|
| R01 | Train 自我近邻校准与 Test 查询分布不一致 | Train→prior Train；Test→full Train | 必须修 | 是 |
| R02 | Top-1 最大值对偶然近邻和候选数量敏感 | 当前 gate 只看 max similarity | 必须修 | 是 |
| R03 | q75 与最低30% coverage 不协调 | q75 名义约25%接受 | 必须修 | 是 |
| R04 | 硬 best-expert 标签丢失近似并列信息 | ambiguous=17,000 | 必须修 | 是 |
| R05 | Memory 标签退化为 naive/cash | 四折 memory 其他类均为0 | 必须修 | 是 |
| R06 | Embedding 严重塌缩/各向异性 | effective rank≈1.25，PC1≈89% | 必须修 | 是 |
| R07 | 当前 collapse gate 过弱 | fold 仍被标为 ready | 必须修 | 是 |
| R08 | 每日滑窗高度重叠 | 连续序列共享19/20日 | 推荐修 | 高 |
| R09 | 同日跨股票共享市场特征 | 60只股票共享市场上下文 | 推荐诊断 | 中高 |
| R10 | 分类损失不保证度量空间 | 高准确率但检索失败 | 必须修或增加度量目标 | 是 |
| R11 | Raw cosine 权重差异弱 | 邻居多在0.98–0.99 | 推荐修 | 中 |
| R12 | 只存硬赢家，不能聚合完整策略结构 | memory 每行只有best_expert及其utility | 必须修 | 是 |
| R13 | 邻居数15不等于有效样本15 | 当前无 effective sample size | 推荐修 | 中 |
| R14 | pooled memory 的跨股票迁移假设未验证 | 允许跨股票检索 | 推荐消融 | 中 |
| R15 | Test 已被观察 | 当前 US 外层 Test 已用于诊断 | 必须版本化 | 是 |

---

## 8. 解决问题的总体原则

1. 先修标签和表示，再修阈值。
2. 先建立简单 baseline，再增加 Transformer 复杂度。
3. 只增加独立信息，不增加大量重复行。
4. 让训练目标直接对应检索目标。
5. 让 Validation 和 Test 使用相同查询形式。
6. 让 coverage calibration 与 admission coverage 目标一致。
7. 对 embedding 几何设置硬 gate，不再只看分类 accuracy。
8. 保留完整 utility 信息，不强迫每个状态产生唯一赢家。
9. 让 fallback 与 matched 贡献完全分离。
10. 旧 Test 只能用于探索；新协议必须使用新外层 holdout。

---

## 9. 所有候选解决方案

### 9.1 协议与版本治理

#### S01｜冻结旧 W18，建立 v3 新版本

状态：必须。

做法：

- 保留现有 W13–W18 outputs 和 acceptance；
- 新建独立 config、output_subdir、manifest schema version；
- 不覆盖 transformer_state_us；
- 新规则在看新 Test 前冻结；
- 所有 v3 报告明确引用旧 W18 为 exploratory negative baseline。

优点：

- 防止事后改写；
- 新旧结果可比较；
- 保留研究诚信。

风险：

- 需要新外层 Test；
- 不能立即得到正式 US admission。

#### S02｜暂停旧协议 W19，先决定是否升级 v3

状态：推荐。

可选决策：

- 方案A：继续旧协议 W19，仅为对称诊断，不用于新理论准入；
- 方案B：暂停 W19，先冻结 v3，再对 CN_A 使用新协议；
- 方案C：同时保留 W19-old 和 W19-v3，但明确两者目的不同。

推荐方案B，避免消耗资源重复已知结构性问题。

### 9.2 标签与监督目标

#### S03｜完整专家 utility 向量

状态：必须。

将每条标签从：

    best_expert_5d
    best_expert_future_utility

扩展为：

    utility_naive
    utility_drift
    utility_sm
    utility_fsm
    utility_best_search
    utility_ml_filter
    utility_adaptive_router
    utility_cash

优点：

- 保留所有专家信息；
- ambiguous 状态仍可使用；
- 可直接聚合邻居的专家 utility；
- 可训练 utility regression 和 ranking。

风险：

- 不同专家 utility 尺度与可用性需要显式 mask；
- 极端收益需要 robust loss；
- schema 和 artifact 体积增加。

#### S04｜软标签 / Label Distribution Learning

状态：推荐。

由 utility 向量生成软概率：

    p_e = softmax(U_e / T_u)

优势接近时分布更平，不再制造虚假唯一赢家。

优点：

- 解决近似并列；
- 提高有效监督覆盖；
- 保留不确定性。

风险：

- 温度 T_u 必须在 Validation 前冻结；
- 过高温度会使所有标签过于平均；
- 过低温度会退化为硬标签。

#### S05｜保留 ambiguous，但显式建模“不明确”

状态：必须。

候选做法：

- 使用完整 utility 向量；
- 记录 top1-top2 margin；
- margin 小的状态用于 utility 学习，但不强迫硬分类；
- retrieval 时低 margin 可触发 fallback。

不推荐做法：

- 为了类别平衡随机指定赢家；
- 把 ambiguous 全部写成 Cash；
- 直接复制 top1 并忽略 margin。

#### S06｜类别重采样或 loss reweight

状态：可选，必须在完整 utility 方案之后评估。

用途：

- 防止 naive/cash 主导 batch；
- 按专家、日期、regime 分层。

风险：

- 不能凭空制造不存在的专家赢家；
- 对极少类过度重采样可能过拟合；
- 不应替代标签设计修复。

### 9.3 样本独立性与数据组织

#### S07｜Memory 按五日 stride 采样

状态：推荐。

初始候选：

    t, t+5, t+10, ...

理由：

- 与5日持有频率一致；
- 减少连续20日窗口的19/20重叠；
- 降低近重复状态造成的极端 Top-1。

优点：

- 提高有效独立性；
- 减少 memory 和计算量；
- 更符合执行频率。

风险：

- 行数下降；
- stride 起始 offset 可能影响样本；
- 应使用多个固定 offset 做 Train/Validation 消融，不能按 Test 选。

#### S08｜同日/同股票权重控制

状态：推荐。

做法：

- batch 按日期、symbol、regime 分层；
- 限制单一日期在一个 batch 中的占比；
- 对同日60只股票共享市场特征造成的重复降权；
- 报告同日跨股票 embedding 相似度。

#### S09｜增加更独立的数据，而不是更多重复行

状态：推荐，成本较高。

优先级：

1. 更长且来源一致的历史；
2. 更多牛/熊/震荡/高低波动阶段；
3. 行业、beta、流动性均衡；
4. 扩大股票池；
5. 最后才是更密集时间采样。

禁止：

- 跨市场拼接 encoder/memory；
- 使用未来新数据回填旧 Test；
- 以更多高度重叠序列掩盖低有效秩。

### 9.4 表示学习与模型目标

#### S10｜Utility 向量回归头

状态：必须。

模型输出所有专家预测 utility：

    U_hat = f_theta(X)

建议使用 Huber loss 而非纯 MSE，降低极端收益影响。

#### S11｜专家 pairwise ranking loss

状态：推荐。

如果真实 U_a > U_b，则要求预测 U_hat_a > U_hat_b。

作用：

- 直接优化策略排序；
- 比绝对 utility 误差更贴近选择任务；
- 对 utility 整体尺度漂移更稳健。

#### S12｜Supervised contrastive / metric learning

状态：推荐，但建议在 S03、S10、S11 后加入。

正样本可定义为：

- utility 向量距离小；
- 专家排序接近；
- top1 相同且 margin 足够；
- regime 和风险结构接近。

负样本可定义为：

- utility 排序明显不同；
- 最佳专家不同且 margin 大；
- 风险结构相反。

风险：

- 正负样本定义不当会引入标签噪声；
- 同股票相邻窗口不能自动视为正样本；
- 所有 pair 只能来自 Train。

#### S13｜Variance/Covariance 防塌缩正则

状态：必须。

目标：

- 每个 embedding 维度具有最低方差；
- 降低维度间冗余相关；
- 避免16维退化为一个主方向。

候选形式：

    L_total
      = lambda_u * L_utility
      + lambda_r * L_ranking
      + lambda_c * L_contrastive
      + lambda_v * L_variance
      + lambda_cov * L_covariance

风险：

- 正则过强可能破坏有用结构；
- 系数必须通过 Train/Validation 选择；
- Test 不得参与。

#### S14｜Train-only 自监督预训练

状态：可选，适用于监督标签仍不足。

候选：

- masked feature reconstruction；
- masked time-step reconstruction；
- 同一序列的轻微增强一致性；
- 时间顺序预测。

优点：

- 可使用 Train 中 ambiguous 序列；
- 不依赖硬专家标签；
- 可能提高特征表示稳定性。

风险：

- 自监督目标可能与策略选择无关；
- 增加训练复杂度；
- 仍然只能使用 Train。

#### S15｜改变 pooling

状态：可选。

候选：

- mean pooling；
- last valid token；
- learned attention pooling；
- CLS token。

必须通过独立消融判断。不能因为当前 mean pooling 塌缩就直接断言 CLS 一定更好。

#### S16｜扩大模型

状态：暂不推荐。

原因：

- 当前瓶颈是标签退化和几何目标；
- 更大模型可能更快过拟合 naive/cash；
- 参数量增加不能自动提高有效秩；
- 应先证明小模型在正确目标下仍容量不足。

### 9.5 几何修复与 baseline

#### S17｜PCA/whitening 作为非 Transformer baseline

状态：必须。

流程：

    20日状态特征
      -> Train-only 标准化
      -> 固定序列统计或展平
      -> PCA/whitening
      -> cosine/kNN retrieval

目的：

- 判断 Transformer 是否真的增加信息；
- 判断简单去相关是否已经解决各向异性；
- 为 metric learning 提供下限。

#### S18｜对 Transformer embedding 做 Train-only whitening

状态：推荐消融，不应直接设为 primary。

流程：

    z_centered = z - train_mean
    z_white = W_train * z_centered
    normalize(z_white)

优点：

- 去除主导方向；
- 可能改善 cosine 分辨率；
- 实现成本低。

风险：

- 如果主方向包含真实信息，whitening 可能损伤；
- W 只能在 Train 拟合；
- 应与防塌缩训练分开比较。

#### S19｜非 Transformer 时序 baseline

状态：必须。

至少比较：

- 最后一天特征；
- 20日均值/斜率/波动等手工序列摘要；
- PCA+kNN；
- MLP embedding；
- 静态 regime retrieval。

如果 Transformer 不能在 Validation retrieval regret、邻居 utility 一致性或 coverage 上超过这些 baseline，则停止复杂模型升级。

### 9.6 Memory 结构

#### S20｜固定 Train memory

状态：必须。

Validation 和 Test 都查询完全相同的 Train memory，不向 memory 追加 Validation/Test 行。

优点：

- 候选池大小和来源一致；
- 校准形式与 Test 一致；
- 简化 lineage。

#### S21｜Pooled / segment / same-symbol memory 消融

状态：推荐。

三种候选：

| Memory | 优点 | 风险 |
|---|---|---|
| pooled market | 样本多，可跨股票复用状态 | 共同市场特征可能掩盖股票差异 |
| segment | 在行业/beta/波动分组内迁移 | segment 定义可能过拟合 |
| same-symbol | 避免跨股票错配 | 单股票历史太少 |

只能在 Validation 比较，Test 不能选择 memory 模式。

#### S22｜Memory 去重或密度降权

状态：推荐。

候选：

- 近重复 embedding 聚类后保留 medoid；
- 同日同 segment 限制最大记录数；
- 相似度极高且标签相同的记录降权；
- 保留每个 prototype 的支持数与日期范围。

风险：

- 聚类本身需要 Train-only；
- 去重阈值不能用 Test；
- 不能删除少数 regime。

### 9.7 匹配统计与阈值校准

#### S23｜Validation query → fixed Train memory

状态：必须。

旧：

    Train query -> earlier Train memory

新：

    Validation query -> fixed Train memory
    Test query       -> same fixed Train memory

这是修复校准分布不一致的核心。

#### S24｜Top-5 平均作为 primary match score

状态：推荐 primary 候选。

    S5(q) = mean(s_1, ..., s_5)

意义：

- 要求一个小邻域整体接近；
- 降低单个偶然近邻影响；
- 与 minimum support=5 语义一致。

#### S25｜第5近邻作为 strict density score

状态：推荐消融。

    Sk(q) = s_5

意义：

- 明确要求至少5个邻居达到某个密度；
- 比 Top-1 更严格；
- 对局部邻域稀疏敏感。

#### S26｜Top-15 mean/median

状态：可选消融。

风险：

- 可能被较远邻居拖低；
- 如果 memory 标签噪声高，过大 k 会混合状态；
- 应与 k=5、10、15 在 Validation 比较。

#### S27｜Coverage-aligned threshold

状态：必须。

不能再固定 q75 同时要求最低30% coverage。

候选预注册方案：

- Validation balanced 目标 matched coverage 35%–40%；
- Test admission 最低30%；
- 由完整 Validation 决策流程确定阈值；
- 阈值冻结后 Test 一次执行；
- 如果 Validation 自身达不到目标，fold unavailable，而不是进入 Test 后放宽。

具体35%还是40%需要用户批准，不应在本报告中直接视为冻结值。

#### S28｜Effective sample size

状态：推荐。

    N_eff = (sum w_i)^2 / sum(w_i^2)

作用：

- 区分“15个名义邻居”和“只有1个有效邻居”；
- 作为 support gate 的补充；
- 报告权重集中程度。

### 9.8 邻居权重与专家聚合

#### S29｜Softmax kernel similarity weight

状态：推荐消融。

    w_i = exp((s_i - s_1) / T_s) / sum_j exp((s_j - s_1) / T_s)

作用：

- 放大0.98与0.99之间的相对差异；
- 避免 raw cosine 权重几乎相同。

风险：

- 温度过小会退化为Top-1；
- 温度过大会退化为等权；
- T_s 必须 Validation 冻结。

#### S30｜聚合完整专家 utility

状态：必须。

不再只看每个邻居的硬 best_expert，而是：

    U_hat_e(q) = sum_i w_i * U_i,e

对所有专家同时得到预测 utility。

优点：

- 使用全部历史信息；
- 避免单邻居高 utility 主导硬标签组；
- 支持可用性 mask；
- 支持风险调整与不确定性。

#### S31｜邻居 utility 分歧

状态：推荐。

    variance_e(q)
      = sum_i w_i * (U_i,e - U_hat_e)^2

可形成保守分数：

    score_e = U_hat_e - gamma * std_e

gamma 只能在 Validation 冻结。

#### S32｜Top1–Top2 utility margin gate

状态：推荐。

    margin(q) = score_top1 - score_top2

如果状态相似但专家优势不明确，应 fallback，而不是强行 matched。

#### S33｜邻居专家投票熵

状态：可选。

衡量邻居对专家选择是否一致。高熵表示邻域专家意见分散，可作为 abstention 信号。

### 9.9 OOD 与拒绝机制

#### S34｜Train–Validation embedding drift

状态：必须诊断。

至少报告：

- centroid shift；
- covariance/eigenvalue shift；
- Top-k score 分布差异；
- regime 条件下的漂移；
- symbol/segment 条件下的漂移。

#### S35｜Conformal/rolling calibration

状态：高级可选。

可以将：

    nonconformity = 1 - Top5MeanSimilarity

在 Validation 或滚动 calibration 上形成 p-value/rejection rule。

注意：

- 时间序列不满足简单交换性；
- 应采用时间有序或加权 calibration；
- 不应作为第一轮修复。

### 9.10 数据扩展

#### S36｜扩大时间跨度

状态：推荐但成本高。

优先增加不同市场周期，而不是相邻日期密度。

#### S37｜扩大股票池

状态：可选。

前提：

- source 和 exact-daily 仍可验证；
- 行业/规模/beta/流动性分布受控；
- 不让高相关同日样本主导。

#### S38｜跨市场联合训练

状态：不推荐，当前 contract 禁止。

US/CN_A 的市场结构、成本、价格限制、benchmark 与 expert availability 不同。除非建立独立 domain adaptation 研究并重新冻结 contract，否则不得混合。

---

## 10. 推荐的 v3 完整流程

### 10.1 阶段0：版本和研究边界

1. 冻结旧 W18。
2. 新建 v3 config 和 output directory。
3. 明确旧 Test 只用于 exploratory diagnosis。
4. 为正式评价预留新的外层时间窗口。
5. 在看到新外层 Test 前冻结本节全部规则。

### 10.2 阶段1：构建点时特征与完整 utility

1. 每只股票、每个日期构造28项点时特征。
2. 只使用 t 及以前数据。
3. 构造同股票20日序列。
4. 为每个专家计算 t+1..t+5 完整 source-net utility。
5. 保存完整专家 utility 向量和 availability mask。
6. 保存 top1、top2、margin 和软标签，但不丢弃低 margin 状态。

### 10.3 阶段2：时间切分

1. 每个 fold 定义 Train、Validation、Test。
2. sequence start 和 label end 均不能跨 role。
3. scaler、自监督、监督训练、memory 全部只用 Train。
4. Validation 选择模型、检索与阈值。
5. Test 仅一次性评估。

### 10.4 阶段3：降低样本重叠

1. 以五日 stride 作为 primary 候选。
2. 可设置固定多个 Train offset 做消融。
3. Validation 前冻结使用哪个 offset 或如何聚合 offsets。
4. batch 按日期、symbol、regime 分层。

### 10.5 阶段4：训练 encoder

推荐最小损失：

    L
      = lambda_u * HuberUtilityVectorLoss
      + lambda_r * PairwiseRankingLoss
      + lambda_v * VarianceFloorLoss
      + lambda_cov * CovariancePenalty

如果上述表示仍不合格，再加入 supervised contrastive。

### 10.6 阶段5：表示质量 gate

在建立正式 memory 前验证：

- embedding 全部有限；
- 每维方差；
- effective rank；
- PC1 解释率；
- pairwise cosine；
- Train–Validation drift；
- Top-k neighbor utility consistency；
- 相对随机邻居的改善；
- 相对 PCA+kNN baseline 的改善。

任一硬 gate 失败，fold unavailable，不进入 Test。

### 10.7 阶段6：固定 Train memory

1. memory 只存 Train。
2. 保存完整 utility 向量。
3. 保存 date/symbol/segment。
4. 保存 encoder/schema/source hashes。
5. Validation 和 Test 查询同一 memory。
6. 不 expanding，不写入 Validation/Test。

### 10.8 阶段7：Validation 检索校准

对每个 Validation query：

1. 生成 embedding；
2. 查询固定 Train memory；
3. 排序 Top 15；
4. 计算 Top-5 mean；
5. 计算第5近邻；
6. 计算 N_eff；
7. 聚合完整专家 utility；
8. 计算 uncertainty；
9. 计算 top1-top2 margin；
10. 应用 query-local expert availability；
11. 模拟完整 matched/fallback decision；
12. 统计最终 matched coverage 和 utility regret。

Validation 冻结：

- memory 模式；
- k；
- match statistic；
- similarity threshold；
- softmax temperature；
- N_eff gate；
- uncertainty gamma；
- margin threshold；
- fallback。

### 10.9 阶段8：Test 决策

对每个 Test query：

1. 使用冻结 scaler/encoder；
2. 查询固定 Train memory；
3. 使用冻结 Top-k 和相似度统计；
4. 使用冻结阈值；
5. 使用冻结 utility 聚合；
6. 使用冻结 uncertainty/margin gate；
7. 选中专家可用时 matched；
8. 不满足条件时 full-run-best fallback；
9. full-run-best 不可用时 Cash；
10. 写完整 neighbor、utility、confidence 和 fallback audit。

### 10.10 阶段9：五日执行

1. t 收盘后决策；
2. t+1 生效；
3. 持有至 t+5；
4. 窗口不重叠；
5. source-net 不重复扣费；
6. jump guard 只影响下一可执行日；
7. 记录 position、turnover、return、attribution。

### 10.11 阶段10：Test 揭盲与 admission

Test 决策全部写完后才计算：

- matched/fallback coverage；
- matched-only utility/return；
- fallback-only return；
- active return vs adaptive；
- active return vs full-run-best-only；
- drawdown；
- turnover；
- symbol breadth；
- worst-tail；
- jump guard contribution；
- neighbor consistency；
- utility regret。

任何 Test 结果都不能回调 v3 参数。

## 11. 建议实验路线图

### 11.1 为什么不能把所有方案一次性组合

本报告列出了三十余项候选修改，但不建议一次性全部加入。一次性组合会产生三个问题：

1. 无法知道 coverage 改善来自标签、encoder、memory，还是阈值；
2. 如果结果恶化，无法定位哪项修改造成退化；
3. 组合搜索会形成新的多重试验和 Test 过拟合风险。

因此，实验应当遵循以下顺序：

1. 先建立不依赖 Transformer 的简单 baseline；
2. 再修标签和样本独立性；
3. 再修表示学习目标；
4. 然后比较 memory 与匹配分数；
5. 最后校准拒绝阈值；
6. 全部选择只看 Train/Validation；
7. 冻结后只运行一次新 Test。

### 11.2 实验统一输入与统一输出

每项实验必须共享相同的：

- point-in-time 原始数据；
- Train/Validation 时间边界；
- 专家日收益源；
- 五日 utility 计算方法；
- 交易成本口径；
- 专家可用性口径；
- Cash fallback 口径；
- 随机种子集合；
- 评估脚本；
- artifact hash 与 code lock。

每项实验至少输出：

- 数据和标签统计；
- embedding 维度与有效秩；
- PC1/PC2 方差占比；
- pairwise cosine 分布；
- Train→Train、Validation→Train 分数分布；
- 邻居 utility 一致性；
- coverage 曲线；
- matched utility；
- fallback utility；
- regret；
- 专家选择分布；
- symbol breadth；
- 参数量、训练时间和随机种子稳定性。

### 11.3 D00：冻结诊断基线

目的：在不重训的情况下，把当前 v2 的失败完整固定下来。

操作：

1. 固定现有 W13–W18 manifests；
2. 导出每折 embedding geometry；
3. 导出每个 query 的 Top-15 相似度；
4. 导出邻居日期、symbol、专家和 utility；
5. 导出阈值 coverage 曲线；
6. 导出按日期、symbol、regime 的 coverage；
7. 保留本报告中的精确数值作为对照。

成功标准：诊断脚本能从冻结 artifact 重建本报告数字，且不改写 W18。

### 11.4 B01：单日截面 PCA baseline

目的：检验 Transformer 是否真的优于简单状态表示。

输入：决策日 t 可见的最后一日特征。

处理：

1. 仅在 Train 拟合 scaler；
2. 仅在 Train 拟合 PCA；
3. 保留解释方差达到预定比例的成分；
4. L2 归一化后计算距离或 cosine；
5. 在固定 Train memory 上做 Validation 检索。

需要回答：

- 简单表示的邻居 utility 是否比当前 Transformer 更一致；
- 简单表示是否也出现接近一维的塌缩；
- coverage/utility 是否更稳定；
- Transformer 的复杂度是否带来了可验证增益。

### 11.5 B02：20日摘要特征 baseline

目的：区分“Transformer 失败”与“20日状态本身不可分”。

建议摘要：

- 每个特征的最后值；
- 20日均值、标准差、最小、最大；
- 前后半段均值差；
- 线性趋势；
- 近5日与前15日差异；
- 波动、回撤、量价和 benchmark 相对特征。

处理仍然只在 Train 拟合 scaler/PCA。若 B02 明显优于 Transformer，优先修训练目标，不优先扩大模型。

### 11.6 L01：完整专家 utility 向量

目的：消除 winner-only 标签造成的信息丢失。

对每个状态保留：

- 每个专家未来五日净 utility；
- 每个专家是否 point-in-time 可用；
- 最优与次优 utility；
- utility margin；
- utility dispersion；
- 是否 ambiguous；
- Cash utility。

对比组：

- L01-A：旧 winner class；
- L01-B：完整 utility 回归；
- L01-C：utility 回归加 ranking；
- L01-D：soft label 分布。

关键指标不是分类准确率，而是 Validation 上的专家选择 regret 和 matched utility。

### 11.7 L02：ambiguous 样本处理

至少比较：

- 丢弃 ambiguous；
- ambiguous 作为独立类别；
- 用 utility 温度转换成软标签；
- 按 utility margin 给 loss 加权；
- 低 margin 样本只用于自监督、不用于强监督。

判断标准：不能只看保留样本数，还要看 utility 排序、表示几何和随机种子稳定性。

### 11.8 S01：五日 stride 与密度控制

对比：

- stride=1；
- stride=5；
- stride=1 但同一五日块共享总权重1；
- stride=1 加 memory 密度降权。

假设：如果重叠是阈值过高的主因，stride=5 应显著降低 Train strictly-prior Top-1 的极端集中，同时不会摧毁 Validation utility 一致性。

注意：阈值下降本身不是成功。只有阈值下降且邻居 utility 更可靠，才算改善。

### 11.9 R01：Utility 回归加 pairwise ranking

基础 loss 候选：

Loss = λ1 × utility regression + λ2 × pairwise ranking + λ3 × classification auxiliary

其中 classification 只能是辅助项，不能继续作为唯一目标。

对每个样本：

1. 预测全部专家 utility；
2. 对真实 utility 更高的专家施加排序约束；
3. 对 utility 差异很小的专家降低排序权重；
4. 对不可用专家进行 mask；
5. 记录 predicted–realized utility calibration。

### 11.10 R02：防塌缩正则

在 R01 基础上逐项加入：

- batch variance floor；
- off-diagonal covariance penalty；
- embedding norm 监控；
- 每维标准差监控；
- effective-rank early stopping；
- PC1 占比 early warning。

不要一开始同时加入全部正则。先比较无正则、variance、variance+covariance 三组。

### 11.11 R03：监督式 metric learning

正样本定义候选：

- utility 向量距离小；
- 专家排序相同且 utility margin 足够大；
- 相同 regime 且 utility 向量相近。

负样本定义候选：

- utility 向量差异大；
- 最优专家不同且 margin 大；
- 市场方向/波动状态相反且决策 utility 明显不同。

必须加入 hard-negative 审计，防止模型只学日期、市场 beta 或股票身份。

### 11.12 G01：Train-only whitening

对比：

- 原 embedding + cosine；
- centered embedding + cosine；
- PCA reduced + cosine；
- whitened embedding + cosine；
- whitened embedding + Euclidean/Mahalanobis。

所有变换只可在 Train 拟合。Validation/Test 只能 transform，不能 refit。

如果 whitening 大幅改善邻居 utility 一致性，但 raw embedding 仍塌缩，whitening 可以作为过渡方案，不能替代 encoder 根因修复。

### 11.13 M01：Memory 作用域实验

对比：

- pooled market memory；
- market×segment memory；
- same-symbol memory；
- pooled + same-symbol 双通道；
- pooled memory 但同日/同股票密度降权。

每组都必须报告：

- memory 行数；
- unique date；
- unique symbol；
- 每个 query 有效邻居数；
- 邻居跨 symbol 比例；
- coverage；
- matched utility；
- fallback 率。

same-symbol memory 可能语义更纯，但历史少，不能预设其一定更好。

### 11.14 C01：Primary match score

至少比较：

- Top-1；
- Top-3 mean；
- Top-5 mean；
- 第5近邻；
- Top-15 mean；
- utility-weighted neighborhood confidence。

推荐优先研究 Top-5 mean，因为它兼顾局部中心和单点噪声；第5近邻可作为密度辅助条件，而不是唯一条件。

### 11.15 C02：邻居权重

至少比较：

- max(cosine,0)；
- rank weight；
- softmax(cosine/temperature)；
- distance kernel；
- uniform weight。

温度只能在 Validation 选择。必须报告有效样本数 ESS，避免名义上15个邻居、实际上一个邻居占据绝大权重。

### 11.16 C03：专家聚合

对比：

- 当前 winner-only weighted mean；
- 完整 utility 向量加权平均；
- utility 中位数；
- trimmed mean；
- Bayesian shrinkage 到市场/segment 先验；
- predicted utility 与 retrieved utility 集成。

推荐的最小改进是完整 utility 向量加权平均。它能够让每个邻居对所有专家提供信息，而不是只给历史 winner 投票。

### 11.17 C04：拒绝条件组合

候选拒绝信号：

- match score；
- 第5邻居分数；
- ESS；
- 邻居 utility dispersion；
- Top1–Top2 专家 utility margin；
- 专家选择熵；
- embedding OOD score；
- point-in-time 专家可用性。

建议先用简单可解释的二到三个条件，不建议一开始训练复杂的二级 gate。

### 11.18 E01：最终冻结实验

只有满足以下条件后才能进入：

1. 所有组件选择仅使用 Train/Validation；
2. 数据、标签、模型、memory、阈值均有 hash；
3. 预先写好 admission 条件；
4. 新 Test 从未用于选择方案；
5. 旧 W18 保持不变；
6. Test 只揭盲一次。

## 12. 下一阶段候选 Gate

本节全部是提案，尚未批准，也不是现有 W20 的正式门槛。审核者可以逐项接受、修改或拒绝。

### 12.1 G-DATA：数据与时间边界

候选要求：

- 所有输入均有 source hash；
- feature 在 t 收盘时可见；
- label 只用于训练目标和事后评估；
- Train/Validation/Test 时间严格有序；
- scaler、PCA、whitening、阈值全部只在 Train/Validation 拟合；
- Test 不参与任何参数、门槛或方案选择；
- 每个窗口的 t+1…t+5 完整存在；
- 专家可用性为 symbol/date point-in-time 信息。

### 12.2 G-LABEL：标签与 utility

候选要求：

- 每个可用专家都有完整五日 utility；
- utility、return、turnover 全部 finite；
- Cash 有显式 utility；
- ambiguous 比例和原因被审计；
- 每个专家的有效样本量被报告；
- 训练不再只依赖 argmax winner class；
- 专家 utility 排序在回放中可精确重建。

### 12.3 G-GEOMETRY：表示空间

建议候选，不是硬编码结论：

- 16维 embedding effective rank 至少达到4；
- PC1 解释方差不高于70%；
- 每维方差没有大面积接近0；
- 不同随机种子的 geometry 指标方向一致；
- Validation 相对 Train 的 drift 被报告；
- 相似度高低与 utility 相似度具有单调关系。

70%与4维只是初始研究门槛。应先基于 baseline 和多随机种子结果确认，不能把它们直接写成永久 admission 条款。

### 12.4 G-NEIGHBOR：邻居语义有效性

候选要求：

- 真实邻居的 utility 向量距离优于随机邻居；
- 真实邻居的专家 regret 优于随机或日期邻近 baseline；
- bootstrap 置信区间不跨越“无改善”；
- 结果不能只由同一天或单一 symbol 驱动；
- 每个 query 的 neighbor lineage 完整可追溯；
- effective sample size 达到预设下限。

这项 gate 比“cosine 很高”更重要。高 cosine 只有在对应决策行为相近时才有意义。

### 12.5 G-CALIBRATION：Validation 阈值校准

候选要求：

- 使用 Validation query → fixed Train memory；
- 预先选择 primary score；
- coverage 目标与最终 admission 下限兼容；
- 阈值在不同时间段、symbol 和随机种子下不剧烈漂移；
- matched utility 高于 fallback 或基线；
- coverage–quality 曲线被完整保存，而不是只保存一个点。

候选目标：balanced Validation coverage 35%–40%，为 Test 最低30%留出漂移缓冲。这个数值仍需实验确认。

### 12.6 G-RETRIEVAL：检索决策

候选要求：

- Top-k、weight、temperature、memory scope 全部冻结；
- matched query 同时满足 score、support、ESS 和不确定性条件；
- unmatched 的 fallback 路径唯一且可复算；
- full-run-best 不可用时明确降级 Cash；
- 专家选择基于完整 utility 聚合；
- tie-break 固定且确定性。

### 12.7 G-EXECUTION：执行真实性

候选要求：

- t 决策、t+1 生效；
- 每个窗口严格五日；
- 窗口不重叠；
- turnover 可由持仓差分重建；
- strategy_return、position、turnover 和 guard 全 finite；
- source-net 不重复扣费；
- jump guard 只有次日有效语义；
- summary 可从 daily 精确重建。

### 12.8 G-ADMISSION：Test 准入

候选准入应至少同时覆盖：

- balanced coverage 不低于预先冻结下限；
- 四折均通过，而非只看 pooled average；
- matched-only utility 有实质改善；
- 相对 adaptive 和 full-run-best-only 的主动收益被报告；
- drawdown、turnover 与 worst-tail 不恶化到预设容忍度之外；
- symbol breadth 达到下限；
- 结果不是由少数日期、少数 symbol 或单一专家驱动；
- 所有 source/code/artifact hashes 一致；
- 任何失败都 fail closed，不允许手工解释成通过。

## 13. 可供审核的四种解决方案套餐

### 13.1 套餐A：只改阈值与匹配分数

内容：

- Train-prior calibration 改为 Validation→Train；
- primary score 从 Top-1 改为 Top-5 mean；
- coverage-aligned threshold；
- 保留现有 encoder、winner label 和 memory。

优点：

- 改动最少；
- 实验快；
- 能直接验证阈值协议错位的影响。

缺点：

- 不修复16维表示接近一维；
- 不修复 memory 只有 naive/cash；
- 不修复17,000个 ambiguous 被丢弃；
- coverage 增加可能只是放宽拒绝条件。

结论：适合作为诊断对照，不建议作为正式 v3。

### 13.2 套餐B：推荐的最小可信 v3

内容：

- 完整专家 utility 向量；
- soft label 或 utility-margin 权重；
- stride=5 或等价的五日块降权；
- utility regression + ranking；
- variance/covariance 防塌缩；
- 固定 Train memory；
- Validation→Train 校准；
- Top-5 mean primary score；
- 完整 utility 加权聚合；
- PCA/摘要特征 baseline；
- 新 Test 一次揭盲。

优点：

- 同时处理标签退化、样本重叠、表示塌缩和阈值错位；
- 每项都可单独消融；
- 仍可保持现有 W16/W17 execution 结构的大部分接口。

缺点：

- 需要重做 W14/W15/W16 协议；
- 需要新的 artifact schema；
- 训练和验证成本中等。

结论：本报告首选方案。

### 13.3 套餐C：高级 metric/OOD v3

在套餐B上增加：

- supervised contrastive；
- Train-only 自监督预训练；
- hard-negative mining；
- pooled/segment/same-symbol 双通道；
- uncertainty ensemble；
- conformal 或 rolling calibration；
- learned rejection gate。

优点：潜在上限更高，能够更明确地塑造决策相似空间。

缺点：

- 复杂度和过拟合风险更高；
- 需要更大的独立数据量；
- attribution 和 fail-closed 审计更困难；
- 不适合在基础 baseline 尚未成立时直接启动。

结论：作为套餐B通过后的第二阶段研究，不建议第一步就采用。

### 13.4 套餐D：先扩数据再建模

内容：

- 延长历史时间；
- 扩大股票池；
- 增加更多独立 regime；
- 保持 point-in-time 和固定 Test；
- 再运行套餐B或C。

优点：直接改善有效状态覆盖，降低模型只记住局部时期的风险。

缺点：

- 数据质量和 survivorship bias 风险增加；
- 需要重建所有 source lock；
- 更多行不等于更多独立状态；
- 如果标签和表示目标不修，扩数据可能只扩大错误。

结论：应作为并行数据工程方向，但不能替代套餐B的基本修复。

## 14. 推荐优先级与实施顺序

### 14.1 P0：治理与冻结

在任何新实验前完成：

1. 保留当前 v2/W18 不变；
2. 新建 v3 配置、输出目录和 manifest 版本；
3. 定义新的 Train/Validation/Test；
4. 写明 Test 一次揭盲原则；
5. 冻结实验指标和候选 gate；
6. 明确 W19 是运行旧协议还是等待 v3。

不完成 P0，不应启动正式模型比较。

### 14.2 P1：诊断与 baseline

优先运行：

- D00 当前表示诊断；
- B01 单日 PCA；
- B02 20日摘要 PCA；
- 随机邻居；
- 日期邻近邻居；
- same-symbol 最近历史；
- 不使用状态匹配的 full-run-best-only；
- adaptive baseline。

目标：先确定“状态检索”是否在 Validation 上提供真实增量。

### 14.3 P2：标签与样本

优先修改：

- 完整 utility 向量；
- ambiguous 的软标签/低权重；
- 五日 stride 或块权重；
- 专家可用性 mask；
- label distribution 和有效样本量审计。

目标：让训练看到比 naive/cash winner 更完整的决策结构。

### 14.4 P3：表示学习

按复杂度递增：

1. utility regression；
2. utility regression + ranking；
3. + variance regularization；
4. + covariance regularization；
5. + supervised contrastive；
6. 可选自监督预训练。

每一步都与上一步做同数据、同随机种子、同评估的消融。

### 14.5 P4：检索与校准

在表示通过 geometry 和 neighbor utility gate 后，再选择：

- memory scope；
- Top-k；
- primary score；
- weight kernel；
- ESS 下限；
- uncertainty/margin gate；
- Validation coverage target。

若表示未通过，不允许通过不断放宽阈值“修复” coverage。

### 14.6 P5：冻结并运行新 Test

只有 P0–P4 的决策全部基于 Train/Validation 完成，才可以：

1. 生成冻结 manifest；
2. 运行新 Test retrieval；
3. 运行五日执行；
4. 生成 admission evidence；
5. 记录通过或不通过；
6. 不根据 Test 结果回调参数。

## 15. W19 中国市场的处理选项

### 15.1 选项W19-A：立即按旧 v2 协议运行

能够回答：

- 同一旧协议在 CN 是否也出现 coverage=0；
- US 问题是否跨市场复现。

不能回答：

- 新流程是否有效；
- 更合理的阈值是否能够准入；
- utility 表示是否改善决策。

风险：投入计算和审计成本，但大概率只复现已知的协议缺陷。

### 15.2 选项W19-B：把 CN 作为旧协议只读诊断

做法：

- 不提交 admission；
- 只导出 label、geometry、Train/Test similarity 和 coverage；
- 不根据 CN 结果修改 US v2；
- 将 CN 结果作为跨市场根因证据。

价值：比完整执行便宜，能检验塌缩和阈值错位是否普遍存在。

### 15.3 选项W19-C：等待 v3 冻结后再运行 CN

做法：

- 先在预先指定的开发市场/时间范围完成 v3 Train/Validation；
- 冻结协议；
- CN 作为独立外部验证或后续市场；
- 严禁看过 CN Test 后再调 v3。

价值：最能保护 CN 的独立验证价值。

### 15.4 本报告建议

推荐 W19-C；如审核者需要快速判断 US 根因是否跨市场，选择 W19-B。暂不推荐 W19-A。

## 16. “需要新理论还是跑实验”的明确回答

### 16.1 不需要发明新的相似度理论

当前问题可由成熟方法覆盖：

- 多任务 utility 回归；
- pairwise/listwise ranking；
- label distribution learning；
- metric learning；
- variance/covariance 防塌缩；
- PCA/whitening；
- kernel-weighted nearest neighbors；
- validation calibration；
- uncertainty/OOD rejection；
- 可选 conformal calibration。

问题不在于缺少一个全新的数学名词，而在于当前监督目标、样本独立性、表示几何、阈值总体和 Test governance 没有形成一致闭环。

### 16.2 必须跑实验，但实验要回答明确假设

应验证的核心假设：

- H1：winner-only 标签是 memory 只剩 naive/cash 的主要原因；
- H2：20日窗口 stride=1 造成 Train 最近邻阈值异常接近1；
- H3：当前 CE+margin 目标造成 embedding 决策语义不足；
- H4：variance/covariance 能提高有效秩；
- H5：Validation→Train 校准能使 coverage 与目标一致；
- H6：Top-5 mean 比 Top-1 更稳定；
- H7：完整 utility 聚合比 winner 投票降低 regret；
- H8：pooled memory 优于或劣于 segment/same-symbol memory；
- H9：更复杂 Transformer 是否优于简单 PCA/摘要 baseline；
- H10：增加独立历史能否带来可重复增益。

每个实验只应改变一类因素，并预先写明支持/否定假设的标准。

### 16.3 不能接受的实验方式

- 在同一个 US Test 上反复改 q50/q65/q75；
- 看 Test coverage 后反推阈值；
- 只报告 coverage，不报告 matched utility；
- 只报告分类准确率，不报告 geometry 和 regret；
- 同时改变标签、模型、memory、阈值却不做消融；
- 只选择最好随机种子；
- 把增加重复窗口当成增加独立数据；
- 用 Test 拟合 PCA、whitening 或温度；
- 覆盖旧 W18 后声称旧结果被修复。

## 17. 预计实现影响范围

本节只是范围估计，不代表这些文件已修改。

### 17.1 配置

可能需要新增或修改：

- v3 标签模式；
- utility horizon；
- sequence stride；
- regression/ranking/contrastive loss 权重；
- collapse regularization；
- memory scope；
- primary match score；
- kernel temperature；
- ESS/margin/dispersion gate；
- Validation coverage target；
- 新 Test 时间边界；
- artifact schema version。

### 17.2 W14 类面板层

可能需要产物：

- full_expert_utility_panel；
- expert_availability_mask；
- utility_margin；
- ambiguity_reason；
- sample_block_id；
- state_weight；
- label_schema manifest。

### 17.3 W15 类模型层

可能需要产物：

- encoder checkpoint；
- utility head checkpoint；
- embedding geometry report；
- per-seed metrics；
- baseline comparison；
- loss component history；
- collapse gate evidence。

### 17.4 W16 类检索层

可能需要产物：

- fixed Train memory；
- Validation calibration queries；
- coverage–quality curve；
- selected primary score；
- selected kernel/temperature；
- ESS、dispersion、margin；
- full utility neighbor aggregate；
- detailed fallback audit。

### 17.5 W17 类执行层

现有执行合同可较大程度复用，但需确认：

- decision 中的新 selected utility 字段；
- matched confidence/uncertainty lineage；
- Cash 降级 attribution；
- summary 中 matched/fallback 分组；
- regret 和 calibration 统计；
- 所有 daily 数值重建规则。

### 17.6 W18 类 evidence 层

需增加：

- geometry gate；
- neighbor utility gate；
- Validation calibration freeze proof；
- baseline comparison；
- per-seed stability；
- complete utility schema hash；
- v3 Test one-shot declaration；
- coverage、quality、risk 的联合 admission。

### 17.7 测试

至少应覆盖：

- utility 无未来泄漏；
- ambiguous/availability mask；
- stride 和 block weight；
- loss finite；
- collapse gate 失败；
- whitening Train-only；
- fixed memory；
- Validation calibration；
- Top-k/ESS；
- full utility aggregation；
- fallback 与 Cash；
- artifact path/hash containment；
- Test 不参与调参；
- execution summary 精确重建；
- admission 缺证据 fail closed。

## 18. 风险登记表

| 风险ID | 风险 | 发生可能性 | 影响 | 缓解方式 |
|---|---|---:|---:|---|
| K01 | 阈值放宽带来虚假 coverage | 高 | 高 | 同时要求 matched utility、regret 和 baseline 改善 |
| K02 | 继续在 US Test 调参 | 高 | 极高 | 新版本、新 Test、一次揭盲 |
| K03 | utility 标签仍被未来信息污染 | 中 | 极高 | point-in-time 审计和 source hash |
| K04 | ambiguous 处理造成偏差 | 高 | 高 | 软标签、margin weighting 和保留率消融 |
| K05 | embedding 仍塌缩 | 高 | 高 | geometry gate、variance/cov、简单 baseline |
| K06 | stride=5 样本太少 | 中 | 中 | block weighting、扩大独立历史 |
| K07 | pooled memory 被市场共因子主导 | 高 | 高 | segment/same-symbol 消融和同日降权 |
| K08 | same-symbol memory 支持不足 | 高 | 中 | pooled + same-symbol 双通道与 support gate |
| K09 | softmax 权重过度集中 | 中 | 中 | ESS gate 和温度 Validation 校准 |
| K10 | 多 loss 权重产生搜索过拟合 | 中 | 高 | 小型预注册网格、消融、多个种子 |
| K11 | 更大模型掩盖数据问题 | 高 | 高 | baseline 先行，模型扩容最后 |
| K12 | 增加股票引入 survivorship bias | 中 | 高 | 历史成分股/退市标的和数据版本审计 |
| K13 | 跨市场混训语义不一致 | 中 | 高 | market-specific baseline、分层 normalization |
| K14 | Validation coverage 稳定但 Test 漂移 | 中 | 高 | 时间稳定性、drift/OOD gate、coverage buffer |
| K15 | 复杂 gate 难以审计 | 中 | 中 | 先使用少量可解释条件 |
| K16 | W19 提前运行损失独立验证价值 | 高 | 高 | 优先选择 W19-C |
| K17 | 多重实验只汇报最好结果 | 中 | 高 | 预注册实验ID并保留全部 artifacts |
| K18 | 新 schema 与 W17 不兼容 | 中 | 中 | schema version、contract tests、迁移 adapter |
| K19 | 结果由少数 symbol/日期驱动 | 高 | 高 | breadth、leave-one-symbol/date-block analysis |
| K20 | 交易成本或 turnover 被重复计算 | 低 | 高 | exact replay 与 summary reconstruction |

## 19. 审核者逐项决策清单

请在下一阶段开工前对本节作出选择。每项可标记为批准、修改后批准、拒绝或待实验。

### 19.1 版本与边界

- [ ] D01：保留 v2/W18 不变，所有修复进入 v3。
- [ ] D02：为 v3 指定新的 Train/Validation/Test 时间边界。
- [ ] D03：新 Test 只揭盲一次。
- [ ] D04：禁止根据现有 US Test coverage 调整 v3。
- [ ] D05：所有实验保留独立 artifact、config、code lock 和 manifest。

### 19.2 W19

- [ ] D06：选择 W19-A，按旧协议完整运行。
- [ ] D07：选择 W19-B，只做 CN 旧协议诊断。
- [ ] D08：选择 W19-C，等待 v3 冻结后保留 CN 独立性。

以上 D06–D08 应只选择一个。报告推荐 D08；若需要跨市场快速诊断则选择 D07。

### 19.3 标签

- [ ] D09：保存完整专家 utility 向量。
- [ ] D10：保留 winner class 仅作辅助任务。
- [ ] D11：使用 soft label。
- [ ] D12：按 utility margin 给样本加权。
- [ ] D13：ambiguous 样本不再全部删除。
- [ ] D14：point-in-time availability 作为显式 mask。

### 19.4 样本与数据

- [ ] D15：sequence/memory 主实验使用 stride=5。
- [ ] D16：保留 stride=1，但按五日块归一总权重。
- [ ] D17：加入同日/同股票密度降权。
- [ ] D18：扩大独立历史。
- [ ] D19：扩大股票池。
- [ ] D20：暂不跨市场联合训练。

D15 与 D16 可作为对比实验，不应未经实验同时认定为最终方案。

### 19.5 模型目标

- [ ] D21：utility vector regression 为主任务。
- [ ] D22：加入 pairwise ranking。
- [ ] D23：加入 variance regularization。
- [ ] D24：加入 covariance regularization。
- [ ] D25：supervised contrastive 仅作为后续消融。
- [ ] D26：自监督预训练仅在数据量足够时研究。
- [ ] D27：当前阶段不扩大 Transformer。

### 19.6 Baseline 与几何

- [ ] D28：必须运行单日 PCA baseline。
- [ ] D29：必须运行20日摘要 baseline。
- [ ] D30：必须运行非 Transformer 时序 baseline。
- [ ] D31：研究 Train-only whitening。
- [ ] D32：候选 geometry gate 使用 effective rank≥4/16。
- [ ] D33：候选 geometry gate 使用 PC1≤70%。
- [ ] D34：geometry 门槛先实验校准，再冻结。

### 19.7 Memory

- [ ] D35：使用 fixed Train memory。
- [ ] D36：比较 pooled、segment、same-symbol。
- [ ] D37：研究 pooled + same-symbol 双通道。
- [ ] D38：memory 做去重或密度降权。

### 19.8 匹配和阈值

- [ ] D39：阈值只用 Validation query → fixed Train memory 校准。
- [ ] D40：Top-5 mean 作为 primary score 首选。
- [ ] D41：第5近邻作为密度辅助 gate。
- [ ] D42：保留 Top-1 仅作对照。
- [ ] D43：Validation balanced coverage 目标初设35%–40%。
- [ ] D44：Test balanced coverage admission 下限暂保留30%。
- [ ] D45：阈值选择同时优化 coverage 与 matched utility。

### 19.9 权重、聚合与拒绝

- [ ] D46：比较 raw positive cosine、uniform、rank、softmax kernel。
- [ ] D47：温度只在 Validation 校准。
- [ ] D48：加入 ESS 下限。
- [ ] D49：按完整 utility 向量聚合专家。
- [ ] D50：加入邻居 utility dispersion。
- [ ] D51：加入 Top1–Top2 utility margin gate。
- [ ] D52：加入专家投票熵。
- [ ] D53：高级 conformal/OOD 延后到基础流程通过后。

### 19.10 Admission

- [ ] D54：四折必须分别通过 coverage，不只看总平均。
- [ ] D55：matched-only utility 必须优于预定 baseline。
- [ ] D56：报告 fallback-only 和 overall，不隐藏 fallback。
- [ ] D57：报告 symbol/date breadth 和 worst-tail。
- [ ] D58：报告 drawdown、turnover、regret 和 guard contribution。
- [ ] D59：所有 artifact/source/code hash 漂移 fail closed。
- [ ] D60：任何 Gate 失败都不能用人工说明改成 ready。

## 20. 建议的审核结论模板

审核者可直接复制以下模板填写：

### 20.1 版本决定

- v2/W18 是否永久冻结：
- v3 是否立项：
- 新 Test 时间范围：
- W19 选择：A / B / C

### 20.2 批准的最小方案

- 标签：
- 样本 stride/weight：
- 模型目标：
- collapse regularization：
- baseline：
- memory：
- primary score：
- neighbor weight：
- utility 聚合：
- rejection gate：

### 20.3 候选门槛

- effective rank：
- PC1 share：
- Validation coverage target：
- Test coverage minimum：
- ESS minimum：
- matched utility improvement：
- breadth minimum：
- drawdown/turnover tolerance：

### 20.4 延后研究

- supervised contrastive：
- self-supervised pretraining：
- same-symbol dual memory：
- conformal calibration：
- 扩大模型：
- 扩大历史/股票池：
- 跨市场联合训练：

### 20.5 明确拒绝

- 不采用的方案：
- 拒绝原因：
- 是否保留为诊断实验：

## 21. 最终建议

### 21.1 对当前结果的最终判断

W20 不准入不是因为“每支股票找不到15个历史状态”，也不是因为“相似度只有65%”。事实是：

- 每个 Test query 都有15个邻居；
- Test Top-1 中位数约0.98；
- 但 Train strictly-prior 阈值约0.997–0.9996；
- balanced 四折 coverage 因此全部为0%；
- memory 监督标签几乎只剩 naive/cash；
- 16维表示的 PC1 约占89%，有效秩约1.25；
- 现有 q75 门槛和30% coverage admission 在统计含义上也不协调。

因此，当前失败是多因素叠加：标签信息损失、窗口高度重叠、表示空间塌缩、阈值总体错位，以及 admission 目标不一致。

### 21.2 不推荐的修法

不建议只把 q75 改成 q65 或把阈值直接设为某个 cosine 数字。这样可能增加 coverage，但无法证明选出的专家更正确，也无法修复表示几何和标签退化。

### 21.3 推荐的最小行动

本报告建议批准套餐B，并按以下顺序执行：

1. 冻结 v2/W18；
2. 保留 CN/W19 的独立价值；
3. 建立新 v3 Train/Validation/Test；
4. 先跑 PCA/摘要 baseline；
5. 把标签改为完整 utility 向量；
6. 降低五日窗口重复权重；
7. 用 utility regression + ranking 训练；
8. 加 variance/covariance 防塌缩；
9. geometry 和 neighbor utility 通过后才做检索；
10. 用 Validation→fixed Train memory 校准 Top-5 mean；
11. 按完整 utility 和可解释的不确定性条件选择专家；
12. 冻结后只运行一次新 Test。

### 21.4 停止条件

如果简单 PCA/摘要 baseline 与改进模型都无法在 Validation 上证明：

- 邻居 utility 比随机/日期邻近更一致；
- matched utility 高于 fallback 或基线；
- coverage–quality 曲线存在可接受区间；

则应停止继续扩大 Transformer，并重新评估“状态相似检索选择专家”这一产品假设本身。Cash、adaptive 或 full-run-best-only 可能是更可靠的最终方案。

## 22. 本地证据索引

本报告结论主要来自：

- 冻结 W13–W18 manifests 与 evidence；
- state sequence/label/split artifacts；
- 四折 encoder 和训练指标；
- memory bank、similarity distribution、state decisions；
- execution daily/summary；
- 当前 v2 acceptance 文档；
- post-gate2 transformer state execution 计划；
- 现有配置中的 top_k、minimum_support、quantile 和 coverage gate；
- 对冻结 embedding、memory 和 Test query 的附加只读诊断。

### 22.1 可直接复核的主要文件

| 类别 | 路径 |
|---|---|
| W13 source manifest | ../model-test/outputs/transformer_state_us/transformer_state_source_manifest.json |
| W14 panel manifest | ../model-test/outputs/transformer_state_us/state_panel_manifest.json |
| W15 model manifest | ../model-test/outputs/transformer_state_us/transformer_state_model_manifest.json |
| W16 retrieval manifest | ../model-test/outputs/transformer_state_us/state_retrieval_manifest.json |
| W17 execution manifest | ../model-test/outputs/transformer_state_us/state_execution_manifest.json |
| W18 evidence manifest | ../model-test/outputs/transformer_state_us/transformer_state_evidence_manifest.json |
| sequence panel | ../model-test/outputs/transformer_state_us/state_sequence_panel.parquet |
| label panel | ../model-test/outputs/transformer_state_us/state_label_panel.parquet |
| walk-forward splits | ../model-test/outputs/transformer_state_us/transformer_state_walk_forward_splits.csv |
| memory bank | ../model-test/outputs/transformer_state_us/state_memory_bank.parquet |
| similarity distribution | ../model-test/outputs/transformer_state_us/state_similarity_distribution.csv |
| retrieval decisions | ../model-test/outputs/transformer_state_us/state_match_decisions.parquet |
| retrieval report | ../model-test/outputs/transformer_state_us/state_retrieval_report.md |
| execution daily | ../model-test/outputs/transformer_state_us/state_execution_daily.parquet |
| execution summary | ../model-test/outputs/transformer_state_us/state_execution_summary.csv |
| execution report | ../model-test/outputs/transformer_state_us/state_execution_report.md |
| W16–W18 acceptance | acceptance/post_gate2_transformer_state_w16_w18_20260820.md |
| v2 execution plan | ../plan/post_gate2_model_upgrade_v2_transformer_state_execution.md |

上述 output artifacts 当前存在于本地工作区且受 frozen manifest 约束；如果单独复制本报告，链接可能因没有同步 artifacts 而失效。

这些证据只支持对当前 v2 的诊断。第9–21节中的 v3 方法、阈值和 Gate 均是待审核提案，不能被表述为已经实现或已经验证。
