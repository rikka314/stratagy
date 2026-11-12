"""Timeline-first research archive reader.

This module is deliberately read-only.  It consumes the frozen catalog, the
experiment README files and local ``model-test/outputs`` artifacts.  Missing
Git-ignored evidence is represented as pending; no metric is inferred from a
missing file.
"""

from __future__ import annotations

import html
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.theme import render_html, render_status_note, route_href, t


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "research" / "RESEARCH_CATALOG.json"
STATUS_LABELS = {
    "baseline_frozen": ("基线已冻结", "Baseline frozen"),
    "passed_research_gate": ("通过研究准入", "Research gate passed"),
    "framework_complete_pending_real_data_gate": ("框架完成，等待真实数据门", "Framework complete; real-data gate pending"),
    "not_admitted": ("未准入", "Not admitted"),
    "stopped": ("已停止", "Stopped"),
    "completed": ("已完成（研究可选）", "Completed (research optional)"),
    "pending": ("待补证据", "Evidence pending"),
    "unavailable": ("不可用", "Unavailable"),
}

# The archive README files are the canonical English research record.  The
# page also carries a Chinese reading edition so switching the site language
# does not leave a Chinese shell wrapped around an English report.  Numbers,
# identifiers and paths intentionally stay unchanged for traceability.
ZH_RESEARCH_COPY: dict[str, dict[str, str]] = {
    "baseline_sm_fsm_full_market": {
        "title": "SM/FSM 全市场基线",
        "question": "原始 SM/FSM 策略家族在冻结的大规模全市场股票池中是否仍然有用？",
        "decision": "建立了可复现的统一比较和研究候选，但没有证明稳定的全市场超额表现；Naive 继续作为必需对照。",
        "scope": """- US 与 CN_A 是两套独立证据，不能跨市场外推。\n- 每个市场的全量运行使用 60 个标的；主窗口为 1,260 个交易日。\n- 稳健性使用 4 个滚动窗口（756 日、步长 126 日）。\n- Random/Bayesian 各 240 次评估，Genetic 240 次目标评估，随机种子为 42。\n- US 成本为佣金 1 bps + 滑点 2 bps；CN_A 为佣金 3 bps + 滑点 5 bps。\n- 每次比较都保留 `Naive` 买入并持有对照；数据快照由 `data_manifest.json` 描述。""",
        "flow": """1. 冻结市场配置、成本、种子、股票池、数据新鲜度和搜索预算。\n2. 执行预检，拒绝过期数据或不干净的正式运行工作树。\n3. 运行 SM、FSM、RSM、baseline、search、ML 和 adaptive-router 候选。\n4. 保存逐标的、逐窗口产物、模型摘要、滚动稳健性、分段结果和失败记录。\n5. 汇总多目标分数，同时保留绝对收益、超额收益、Sharpe、回撤、覆盖率及 Naive 对照。\n6. 写入市场本地报告和 manifest；排名不转换成收益承诺。""",
        "decisions": """- 候选排名是研究比较，不是投资建议或预期收益估计。\n- 稳健性与击败 Naive 的证据必须和总分一起展示。\n- ML 只作为消融/条件分支，不能假设一定优于父模型。\n- Adaptive routing 是状态感知候选/对照，并未独立证明生产 alpha。""",
        "result": """US 基线冻结为 `full_us_deans_60`，共有 5,460 条运行记录：主窗口成功 1,140 条，滚动记录成功 4,318 条，另有 2 条明确降级。`SM+Bayesian` 以 72.67 的综合分排名第一，但主窗口超额收益中位数为 -7.95%、Sharpe 中位数为 0.03，仅在 40% 的标的上击败 Naive。诚实结论是：基线建立了可复现的比较和默认研究候选，并未证明稳定的全市场超额表现。CN_A 是独立市场来源，必须读取自身 manifest/report，不能替代 US 结果。""",
        "gate": "状态：`baseline_frozen`。这是后续研究的参考基线，不是生产准入门。",
        "problems": """- 超额收益中位数和广泛击败 Naive 的证据不足以支持一般性表现声明。\n- 分段赢家样本较小，只能作为后续研究线索。\n- 后续任何声明都需要新的市场匹配确认层或独立批准的 shadow study。""",
    },
    "transformer_state_feasibility": {
        "title": "Transformer 可行性与状态检索",
        "question": "状态相似性/检索能否提升专家效用，从而值得继续投入 Transformer？",
        "decision": "工程证据通过，但查询效用没有通过；Phase 2 STOP 阻止了 Transformer 训练和产品接入。",
        "scope": """- 已完成的主要证据来自 US；CN_A W19 是独立的待补窗口。\n- 检索只使用更早的记忆行，并采用 purged walk-forward 切分。\n- W16-W18 使用 5 日持有窗口、次日有效性和 source-net 收益。\n- v3 Phase 1 在 Validation 角色上只用训练集缩放/PCA 和确定性随机邻居，并对重复 split signature 去重。\n- 主要价值门槛是查询选择的专家效用/遗憾，而不是视觉相似度或邻居一致性。""",
        "flow": """1. 冻结 exact-daily 专家产物、adaptive 产物、数据快照、代码锁和 manifest。\n2. 构建状态面板和 walk-forward 切分，并执行泄漏检查。\n3. 运行 v2 检索与精确五日回放，重新计算哈希和摘要。\n4. 运行 v3 非深度学习基线：B01 单日 PCA、B02 20 日摘要 PCA、B03 随机邻居。\n5. 比较效用一致性、查询效用、遗憾、覆盖率和 bootstrap 证据。\n6. 在考虑 Transformer 训练前执行预注册的停止/准入决定。""",
        "decisions": """- 工程完整性与研究价值分开判断。\n- 如果邻居内部更一致，却持续选择更差的专家，则这种相似性没有决策价值。\n- 看到结果后不能改阈值、窗口、成本或测试期来制造准入。\n- 价值门槛通过前，生产和 Streamlit 行为保持不变。""",
        "result": """W16-W18 工程验收通过：11,520 个窗口全部审计，exact-daily 产物与 manifest 一致；但四个 fold 的 `state_match_balanced` 匹配覆盖率均为 0%，低于冻结的 30% 最低值，因此 W20 未准入。v3 Phase 1 中 B01/B02 相比随机的效用一致性提升为 +0.017500/+0.020940（单侧 p=0.000999），但查询选择效用反而低于随机 -0.003283/-0.005354，遗憾增加。Phase 2 判定状态相似性不能预测专家效用，在 Transformer 训练前 STOP。""",
        "gate": "状态：`stopped`。这是完整的负向可行性研究，不是 Transformer 已经有效的证据。",
        "problems": """- 当前表示学到了与决策效用不一致的相似性。\n- 后续研究需要预先声明的标签/步长重构或新的效用对齐状态目标，并重新通过查询效用/遗憾门槛。必须开启新研究，不能事后挽救本次结果。""",
    },
    "adaptive_dynamic_experts": {
        "title": "自适应路由与动态专家系统",
        "question": "自适应路由或动态专家组合能否在冻结对照之外达到准入？",
        "decision": "Phase A-F 产物完成，但 W11 非劣性覆盖只有 US 1/4、CN_A 2/4；W12 产品准入被阻断。",
        "scope": """- US 与 CN_A 独立训练和评估。\n- 主 horizon 为 20 个交易日，5/60 日只做消融。\n- source returns 已扣除交易成本（`source_net_no_recharge`），下游不得重复扣费。\n- Phase B 使用 purged walk-forward 切分和至少一个 horizon 的 embargo。\n- Cash 必须存在；缺失专家显示为 unavailable，或通过审计过的 fallback 转入 Cash。\n- Phase C-F 覆盖 soft gating、不确定性/风险约束、在线更新和 selected-action bandit。""",
        "flow": """1. 锁定市场本地 full-run 来源、专家池、manifest、种子、成本和快照。\n2. 生成 Phase A 对照：最佳单专家、专家等权和 adaptive-router。\n3. 建立 point-in-time 专家日面板及未来效用标签（Phase B）。\n4. 训练并回放无状态/状态感知 soft gating（Phase C），再加入不确定性、OOD 和风险限制（Phase D）。\n5. 回放 Hedge/EG 在线更新（Phase E），再运行 selected-action-only LinUCB/Thompson（Phase F）。\n6. 用四个测试切分、回撤、换手和非劣性覆盖执行 W11 准入。\n7. 冻结的 3/4 窗口门槛失败后停止产品/shadow 接入。""",
        "decisions": """- 动态模型只能使用决策时点已经可见的证据。\n- Cash 和明确的 fallback 原因属于模型 contract，不能隐藏为错误处理。\n- bandit 研究中未选择 action 的收益只能用于评估，不能泄漏到学习。\n- 仅有更低风险或更低换手并不足够，收益非劣性也必须有足够覆盖。""",
        "result": """Phase A-F 已作为相关市场的研究产物完成。W11 的非劣性窗口为 US 1/4、CN_A 2/4；两个市场的逐窗口回撤和换手检查通过，但未达到要求的 3/4 覆盖。W12 被阻断：没有启动 shadow mode、Streamlit 接入、默认值修改或产品准入。现有 `adaptive_router_v1` 仍是运行时默认/降级边界。""",
        "gate": "状态：`not_admitted`。这不是工程运行失败，而是明确的产品准入否决。",
        "problems": """- 改善没有在四个冻结测试窗口中广泛出现。\n- 后续尝试必须保持相同成本、切分、target-position 换手重建、source lock 和市场隔离；不能选择有利窗口或事后挑参数单元。""",
    },
    "cn_a_composite_only": {
        "title": "CN_A Composite-only",
        "question": "在一套冻结比较中，市场原生 CN_A Composite 能否击败 SM/FSM？",
        "decision": "Composite 通过 CN_A 研究门，但仍是研究用途且只适用于 CN_A。",
        "scope": """- 市场仅为 CN_A，结论不能外推到 US 或其他市场。\n- 股票池为 `full_cn_a_admission_60` 冻结比较 universe。\n- 因子为 10 个技术因子 + 13 个市场原生因子，均有明确 lineage。\n- Horizon 为 20 个交易日；成本为佣金 3 bps + 滑点 5 bps，使用 source-net returns 且不重复扣费。\n- 在相同市场、fold、horizon 和执行语义下比较 `composite_only`、`sm` 和 `fsm`。\n- 准入要求 Sharpe 优于基线、fold consistency 至少 75%、至少一项风险改善、统一配置和可追溯 manifest。""",
        "flow": """1. 定义显式 market-factor context，禁止 CN_A 隐式读取 SPY/VIX。\n2. 构建并验证 CN_A factor panel、schema、质量报告、lineage 和哈希。\n3. 只用真实 20 日 forward returns 训练 Composite 权重。\n4. 执行 long-only 仓位映射和 fold 级执行比较。\n5. 使用同一 fold、成本、universe 和收益字段比较 Composite 与 SM/FSM。\n6. 应用预声明准入门，并保留失败的 mock-target 尝试作为警示。""",
        "decisions": """- 市场因子必须是市场原生且 point-in-time；US 产物不能静默替代 CN_A 上下文。\n- 初始随机噪声 target 是无效研究输入，已改为真实 forward returns 后才接受性能结论。\n- Composite 先以 `composite_only` 评估并拥有自己的方向，之后才考虑 advisory。\n- 通过研究门不等于完成生产评审。""",
        "result": """修正后的运行得到 Composite Sharpe `0.5972`，高于 SM `0.5277`（+13.2%）和 FSM `0.4984`（+19.8%）。平均最大回撤为 -54.81%，优于 SM 的 -74.07% 和 FSM 的 -64.50%；fold consistency 为 76.7%，达到 >=75% 门槛。权重跨 fold 呈现稳定的均值回归模式：RSI 正向，MACD/BB-position 负向。""",
        "gate": "状态：`passed_research_gate`。结论仅限 CN_A、仅限研究，不是生产或跨市场声明。",
        "problems": """- 只有一个冻结 CN_A universe 和四 fold 比较。\n- Advisory 不在本次门槛内。\n- 未来生产评审仍需独立数据完整性、UI fallback、延迟/回滚和 shadow mode 审查。""",
    },
    "cn_a_composite_advisory": {
        "title": "CN_A Composite + 多专家 Advisory",
        "question": "额外的专家/上下文 advisory 能否在不改变 Composite 方向、不打开未授权仓位的情况下降低风险？",
        "decision": "不可变 contract、advisory 策略、安全边界和测试已完成；没有真实数据通过记录，所需 manifest 和消融产物缺失。",
        "scope": """- 市场仅为 CN_A，不跨市场共享权重。\n- 基础模型为 Phase 4/6 的 `composite_only`。\n- 策略包括 composite_only、trend、reversion、relative strength、macro cap、combined advisory 和 cash controls。\n- long-only 语义：advisory 只能维持或减少 Composite 基础仓位，不能增加；Composite 为零时不能开仓。\n- 最终仓位有上下界和日变化限制；缺失上下文必须显式 fallback，reason code 可审计。\n- 真实数据门要求 Sharpe 下降不超过 10%、至少一项风险改善、换手不超过 30%，且 fallback 质量可接受。""",
        "flow": """1. 冻结 Composite 基线、因子面板、advisory 规则、阈值和门槛。\n2. 用单元测试验证不可变 decision contract 与安全边界。\n3. 合并基线和市场原生因子，检查未来数据泄漏。\n4. 将每个策略作为独立消融，计算净绩效、换手和风险。\n5. 审计 reason code、fallback 比例、advisory multiplier 和平均减仓。\n6. 仅当 ablation_metrics.csv、decision_audit.csv、quality_report.json 与 advisory_manifest.json 一致时才判定真实数据门。""",
        "decisions": """- Composite 负责方向，advisory 只是保守的风险 overlay。\n- 多个 advisory 取最小 multiplier，保留当前最严格的约束。\n- 缺失上下文字段必须显示 fallback，不能静默填成中性值。\n- 框架测试证明 contract 安全，不证明 out-of-sample 收益。""",
        "result": "框架和单元测试已完成：不可变 contract、四类 advisory、fallback 规则和安全边界均有覆盖。当前记录不能声称真实数据策略通过；在本地 advisory manifest 和消融产物出现并完成校验前，状态保持 `framework_complete_pending_real_data_gate`。",
        "gate": "状态：`framework_complete_pending_real_data_gate`。若没有策略满足全部真实数据条件，继续推荐 `composite_only`，并将 advisory 记为负向消融。",
        "problems": """- 仍需有效的真实数据运行，并独立审查 fallback 与换手审计。\n- 未来扩展只能通过新的预注册消融调整阈值或新增专家，不能针对有利测试结果调参后重新命名冻结门。""",
    },
    "ml_enhancement": {
        "title": "ML 增强与参数优化",
        "question": "贝叶斯优化、遗传算法和 LightGBM 过滤能否改善参数搜索？",
        "decision": "ML 增强变体作为研究可选功能接入。",
        "scope": """- 市场：US、CN_A。\n- ML 方法：贝叶斯优化、遗传算法、随机搜索、LightGBM 过滤。\n- 接入方式：策略 pipeline 中的可选 ML filter 分支。\n- 优化目标：Sharpe、收益、回撤和覆盖率的多目标组合。""",
        "flow": """1. 在随机搜索基线旁实现贝叶斯和遗传参数搜索。\n2. 增加可选 LightGBM 预处理过滤器。\n3. 将 ML filter 作为条件分支接入 SM/FSM pipeline。\n4. 与非 ML 基线比较增强变体。\n5. 将 ML 冻结为研究选项，而不是自动生产升级。""",
        "decisions": """- ML 增强保持可选，不假设对所有标的都更好。\n- 每个变体独立评估并保留自己的产物链。\n- 搜索公平性要求不同方法使用相同预算。\n- 过滤器增加计算成本，可能并不改善所有标的。""",
        "result": "ML 增强变体（如 SM+Bayesian、FSM+Genetic）已纳入全市场基线比较。它们排名有竞争力，但没有普遍压过非 ML 变体；ML filter 因此保留为条件分支，而不是生产必选组件。",
        "gate": "状态：`completed`。ML 增强已作为研究可选功能接入。",
        "problems": "未来仍需在统一全市场口径下区分搜索带来的收益与过滤器本身的收益，并继续保留等预算和独立产物链。",
    },
    "news_fusion": {
        "title": "新闻融合与情绪因子",
        "question": "把新闻情绪与技术指标结合，能否提升信号质量？",
        "decision": "新闻融合接入为可选研究分支；覆盖不足时使用显式 fallback，不把缺失覆盖当成提升证据。",
        "scope": """- 市场：US、CN_A。\n- 数据源：新闻情绪信号（外部提供方或模拟输入）。\n- 接入：新闻因子作为可选信号组件。\n- 融合：与技术信号加权组合。""",
        "flow": """1. 定义新闻情绪 schema 和数据 contract。\n2. 实现新闻因子计算模块。\n3. 将新闻因子接入信号生成 pipeline。\n4. 与基线比较新闻增强信号。\n5. 保留新闻为可选功能，并执行质量校验。""",
        "decisions": """- 新闻因子可选；数据缺失不能破坏 pipeline。\n- 覆盖不足的标的可以将新闻权重置零。\n- 情绪分数需要归一化并限制范围。\n- 新闻融合增加复杂度，只有覆盖足够时才有意义。""",
        "result": "新闻因子接入和测试已完成，新闻增强信号作为可选分支可用。该功能仍是 research-only，不是生产运行的必需依赖。",
        "gate": "状态：`completed`。新闻融合已作为研究可选功能接入。",
        "problems": "新闻覆盖不足时不能把 fallback 当成性能证据；未来消融必须报告覆盖率、未来日期泄漏、重复记录和缺失行为。",
    },
    "frontend_evolution": {
        "title": "前端演进（W6-W8）",
        "question": "能否在不改变策略 contract 的前提下，把 Streamlit 界面变成易读、高性能的产品工具？",
        "decision": "暖白视觉系统、路由结构、导出界面和性能方案冻结为前端基线。",
        "scope": """- 视觉：暖白/米色背景、清晰字体和有意图的留白。\n- 组件：统一主题层 `ui/theme.py` 与 CSS 变量。\n- 路由：带持久化状态的多页面导航。\n- 交付：首页、单股分析、多股组合、模型评估和 HTML 导出。""",
        "flow": """1. 定义暖白色板、字体层级和间距节奏。\n2. 实现支持明暗主题的统一主题层。\n3. 用动态新闻、股票星图和市场镜头重建首页。\n4. 统一分析页 hero、控件和结果层级。\n5. 增加自包含样式的 HTML 导出。\n6. 用并行数据片段和工作区缓存做性能优化。""",
        "decisions": """- `FRONTEND_STYLE_STANDARD.md` 是冻结的视觉基线。\n- 不使用通用 AI 渐变或紫色默认风格。\n- 字体和颜色是明确的设计决策，不是占位符。\n- 路由行为和主题 contract 必须有测试。""",
        "result": "W6-W8 前端演进完成：视觉基线、多路由导航、性能优化和导出功能均已冻结，并有文档和测试覆盖。",
        "gate": "状态：`completed`。W6-W8 风格冻结为产品基线。",
        "problems": "视觉和性能完成不等于策略性能或生产准入；主题、路由和导出改动仍需对照冻结 contract 回归。",
    },
    "deployment_optimization": {
        "title": "部署优化与跨设备设置",
        "question": "能否支持 Windows、macOS、Linux 及 `/strategy` 子路径部署，同时保持工作区和缓存边界？",
        "decision": "跨平台设置、Nginx 子路径、工作区持久化、缓存失效和性能监控均已文档化并测试。",
        "scope": """- 部署模式：本地开发、Nginx 子路径和远程服务器。\n- 跨设备：Windows batch、macOS shell、Linux systemd。\n- 远程开发：VS Code Remote-SSH、GitHub Codespaces、云端编辑器。\n- 性能：工作区缓存、市场上下文缓存和 telemetry 监控。""",
        "flow": """1. 实现跨设备设置脚本（`setup.bat`、`start.bat` 及 macOS 等价脚本）。\n2. 增加 `/strategy` 的 Nginx 子路径配置。\n3. 实现工作区持久化和缓存失效。\n4. 增加性能监控（`core/perf.py`、`workspace_cache.py`、`market_cache.py`）。\n5. 文档化部署 contract 和远程开发流程。""",
        "decisions": """- 部署配置冻结在 `deploy/` 和 `.streamlit/config.toml`。\n- 工作区缓存负责跨会话保留分析状态。\n- 市场上下文缓存减少 API 请求。\n- 性能事件跟踪加载和渲染耗时。""",
        "result": "部署优化完成：跨设备设置、Nginx 子路径、工作区持久化和性能监控均已落地，相关 contract 已文档化并测试。",
        "gate": "状态：`completed`。部署 contract 已冻结并可运行。",
        "problems": "部署 contract 是运行边界，不是投资绩效证据；改变子路径、缓存或工作区语义时必须重新做跨平台兼容检查。",
    },
    "us_composite": {
        "title": "US Composite（Phase 0-4）",
        "question": "加入宏观因子的 US Composite 能否击败 SM/FSM？",
        "decision": "US Composite 通过研究门，但所有结论仍只适用于 US 且保持 research-only。",
        "scope": """- 市场仅为 US；结论不能外推到 CN_A。\n- 股票池为冻结 Dean's Award 基线中的 60 个 US 标的。\n- 因子为 10 个技术因子 + 13 个宏观/市场相对因子。\n- Horizon 为 20 个交易日；成本为佣金 1 bps + 滑点 2 bps，使用 source-net returns。\n- Phase 0 建立宏观数据；Phase 1 做因子分层和筛选；Phase 2 做稳健权重；Phase 3 做仓位映射；Phase 4 做 advisory overlay。""",
        "flow": """1. Phase 0：下载 VIX、SPY 和 US 行业映射，执行 fail-closed 校验和 SHA-256。\n2. Phase 1：实现 6 个宏观因子和 4 层、共 23 个因子的 pipeline，并检查因子同质性。\n3. Phase 2：加入 train-only 约束、方向/家族预算、多目标效用、block bootstrap 和稳定性统计。\n4. Phase 3：比较 4 种仓位映射方法，检查 fold consistency 并选择下一阶段方法。\n5. Phase 4：构建 long-only advisory；只能维持或减少 Composite 仓位，不能增加或打开未授权仓位。""",
        "decisions": """- 使用真实 20 日 forward returns 作为训练 target，禁止 synthetic/mock data。\n- 用 VIX regime、相对 SPY 强弱、市场 breadth、beta 和行业动量补足纯技术因子缺失的市场上下文。\n- Composite 拥有自己的学习方向，advisory 只是保守风险 overlay。\n- Advisory multiplier、有界日变化和缺失上下文 fallback 都必须可审计。\n- US 权重与结论只属于 US，CN_A 保持独立研究线。""",
        "result": "US Composite Phase 0-4 完成并通过 US 研究准入，在冻结比较中优于 SM/FSM，fold consistency 达到预注册门槛。Advisory 框架已通过单元测试和消融逻辑验证。所有产物仍是 US-only、research-only，除非另有明确记录，不得视为生产默认或 Streamlit 接入。",
        "gate": "状态：`passed_research_gate`。US Composite 在声明的 universe、horizon 和成本假设下通过冻结研究准入。",
        "problems": """- 只覆盖一个冻结 US universe 和 fold 配置；泛化需要独立确认。\n- Advisory 真实数据门取决于 `composite_advisory_us`（或等价）manifest 和消融产物。\n- 未来生产评审仍需数据完整性、UI fallback、延迟/回滚和 shadow mode 审查。""",
    },
}

ZH_METRIC_LABELS: dict[str, dict[str, str]] = {
    "adaptive_dynamic_experts": {"us_non_inferior_windows": "US 非劣窗口", "cn_a_non_inferior_windows": "CN_A 非劣窗口", "product_integration": "产品接入"},
    "cn_a_composite_only": {"composite_sharpe": "Composite Sharpe", "sm_sharpe": "SM Sharpe", "fsm_sharpe": "FSM Sharpe", "composite_mean_max_drawdown": "Composite 平均最大回撤", "fold_consistency": "Fold 一致性"},
    "cn_a_composite_advisory": {"unit_tests": "单元测试数", "real_data_gate": "真实数据门", "expected_manifest": "预期 manifest"},
    "baseline_sm_fsm_full_market": {"us_top_candidate": "US 首选候选", "us_total_score": "US 综合分", "us_main_window_median_excess_return": "US 主窗口超额收益中位数", "us_main_window_median_sharpe": "US 主窗口 Sharpe 中位数", "us_beat_naive_ratio": "US 击败 Naive 比例", "us_run_records": "US 运行记录数"},
    "transformer_state_feasibility": {"w16_w18_primary_matched_coverage_by_fold": "W16-W18 每 fold 匹配覆盖率", "v3_b01_utility_consistency_delta_vs_random": "B01 相对随机效用一致性差值", "v3_b02_utility_consistency_delta_vs_random": "B02 相对随机效用一致性差值", "v3_b01_query_selected_utility_delta_vs_random": "B01 查询效用相对随机差值", "v3_b02_query_selected_utility_delta_vs_random": "B02 查询效用相对随机差值"},
    "news_fusion": {"status": "状态", "fallback": "降级策略"},
    "frontend_evolution": {"status": "状态"},
    "deployment_optimization": {"status": "状态"},
    "us_composite": {},
}

ZH_GENERIC_METRIC_LABELS = {
    "status": "状态",
    "fallback": "降级策略",
    "real_data_gate": "真实数据门",
    "expected_manifest": "预期 manifest",
    "unit_tests": "单元测试数",
    "product_integration": "产品接入",
}

# These are additional, already-materialized artifacts that make older
# research lines observable in the browser.  They are labelled supplemental
# and never replace the catalog's canonical evidence contract.
SUPPLEMENTAL_EVIDENCE: dict[str, tuple[str, ...]] = {
    "baseline_sm_fsm_full_market": (
        "model-test/outputs/full_us_deans_60/model_summary.csv",
        "model-test/outputs/full_us_deans_60/robustness_summary.csv",
    ),
    "transformer_state_feasibility": (
        "model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison.csv",
    ),
    "adaptive_dynamic_experts": (
        "model-test/outputs/w11_admission_us/w11_split_summary.csv",
        "model-test/outputs/w11_admission_cn_a/w11_split_summary.csv",
    ),
    "cn_a_composite_only": (
        "model-test/outputs/cn_a_factor_composite_comparison/comparison_metrics.csv",
        "model-test/outputs/cn_a_factor_composite_comparison/comparison_fold_metrics.csv",
    ),
    "cn_a_composite_advisory": (
        "model-test/outputs/composite_advisory_cn_a/quick_ablation_results.csv",
        "model-test/outputs/composite_advisory_phase1/ablation_metrics.csv",
    ),
    "us_composite": (
        "model-test/outputs/composite_stability_phase2/test_metrics.csv",
        "model-test/outputs/phase3_20260822_223619/position_map_ablation.csv",
        "model-test/outputs/composite_stability_phase4/admission_summary.csv",
        "model-test/outputs/composite_stability_phase4/fold_metrics.csv",
    ),
    "ml_enhancement": (
        "model-test/outputs/full_us_deans_60/model_summary.csv",
        "model-test/outputs/phase2_5_advanced_optimization/advanced_optimization_report.md",
    ),
    "news_fusion": (
        "document/acceptance/window_4_news_factor_20260809.md",
    ),
    "frontend_evolution": (
        "document/acceptance/web_performance_phase_7_20260809.md",
    ),
    "deployment_optimization": (
        "document/interfaces/deploy-runtime.md",
    ),
}


@dataclass(frozen=True)
class EvidenceItem:
    path: str
    present: bool
    required: bool = False
    supplemental: bool = False

    @property
    def state(self) -> str:
        if self.present:
            return "available"
        return "pending" if self.required else "unavailable"


@dataclass(frozen=True)
class ResearchExperiment:
    record: dict[str, Any]
    readme_path: Path
    readme_text: str
    sections: dict[str, str]
    evidence: tuple[EvidenceItem, ...]

    @property
    def experiment_id(self) -> str:
        return str(self.record.get("id", ""))

    @property
    def title(self) -> str:
        localized = ZH_RESEARCH_COPY.get(self.experiment_id, {}).get("title")
        return localized if get_ui_language_safe() == "zh" and localized else str(self.record.get("title", self.experiment_id))

    @property
    def status(self) -> str:
        return str(self.record.get("status", "pending"))

    @property
    def date_range(self) -> str:
        return str(self.record.get("date_range", ""))

    @property
    def start_date(self) -> date:
        return _parse_start_date(self.date_range)

    @property
    def evidence_available(self) -> int:
        return sum(item.present for item in self.evidence)

    @property
    def evidence_total(self) -> int:
        return len(self.evidence)

    @property
    def canonical_evidence_available(self) -> int:
        return sum(item.present and not item.supplemental for item in self.evidence)

    @property
    def required_evidence_pending(self) -> bool:
        return any(item.required and not item.present for item in self.evidence)


def get_ui_language_safe() -> str:
    """Read the app language without making archive helpers hard to test."""
    try:
        from ui.i18n import get_ui_language

        return get_ui_language()
    except Exception:
        return "en"


def _localized_copy(experiment: ResearchExperiment, key: str, fallback: str = "") -> str:
    if get_ui_language_safe() == "zh":
        return ZH_RESEARCH_COPY.get(experiment.experiment_id, {}).get(key, fallback)
    return fallback


def _localized_record_text(experiment: ResearchExperiment, key: str, fallback: str = "") -> str:
    return _localized_copy(experiment, key, str(experiment.record.get(key, fallback) or fallback))


def _localized_section(experiment: ResearchExperiment, key: str, *names: str) -> str:
    return _localized_copy(experiment, key, _section(experiment, *names))


def load_research_experiments(
    repo_root: Path = REPO_ROOT,
    catalog_path: Path | None = None,
) -> tuple[list[ResearchExperiment], list[str]]:
    """Load and sort the catalog without mutating any source or output."""
    path = catalog_path or (repo_root / "research" / "RESEARCH_CATALOG.json")
    issues: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"Unable to read research catalog: {exc}"]
    raw_experiments = payload.get("experiments") if isinstance(payload, dict) else None
    if not isinstance(raw_experiments, list):
        return [], ["Research catalog has no experiments list"]

    experiments: list[ResearchExperiment] = []
    for raw in raw_experiments:
        if not isinstance(raw, dict):
            issues.append("Ignored non-object experiment record")
            continue
        archive_path = repo_root / str(raw.get("archive_path", ""))
        readme_path = archive_path / "README.md"
        try:
            readme_text = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
        except OSError:
            readme_text = ""
            issues.append(f"Unable to read {readme_path.relative_to(repo_root)}")
        if not readme_text:
            issues.append(f"Missing experiment README: {raw.get('archive_path', '')}/README.md")

        evidence: list[EvidenceItem] = []
        for entry in raw.get("evidence", []) if isinstance(raw.get("evidence"), list) else []:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                issues.append(f"{raw.get('id', 'unknown')}: malformed evidence entry")
                continue
            evidence_path = str(entry["path"])
            evidence.append(
                EvidenceItem(
                    evidence_path,
                    (repo_root / evidence_path).is_file(),
                    required=bool(entry.get("required", False)),
                )
            )
        for evidence_path in SUPPLEMENTAL_EVIDENCE.get(str(raw.get("id")), ()):
            if evidence_path not in {item.path for item in evidence}:
                evidence.append(
                    EvidenceItem(
                        evidence_path,
                        (repo_root / evidence_path).is_file(),
                        supplemental=True,
                    )
                )

        experiments.append(
            ResearchExperiment(
                record=raw,
                readme_path=readme_path,
                readme_text=readme_text,
                sections=_extract_sections(readme_text),
                evidence=tuple(evidence),
            )
        )
    # The numbered catalog/research README order is the frozen chronology.
    # Do not sort by the human-entered date_range: dates are intentionally not
    # rendered and can be approximate or wrong for this archive.
    return experiments, issues


def search_research_experiments(
    experiments: Iterable[ResearchExperiment],
    query: str,
) -> list[ResearchExperiment]:
    """Search title, question, decisions, sections, sources and evidence paths."""
    needle = " ".join(str(query or "").lower().split())
    if not needle:
        return list(experiments)
    matches: list[ResearchExperiment] = []
    for experiment in experiments:
        record = experiment.record
        haystack_parts = [
            experiment.experiment_id,
            experiment.title,
            str(record.get("question", "")),
            str(record.get("decision", "")),
            str(record.get("gate", "")),
            experiment.readme_text,
            " ".join(str(item) for item in record.get("sources", []) or []),
            " ".join(item.path for item in experiment.evidence),
            " ".join(ZH_RESEARCH_COPY.get(experiment.experiment_id, {}).values()),
            " ".join(ZH_METRIC_LABELS.get(experiment.experiment_id, {}).values()),
            " ".join(f"{key} {value}" for key, value in (record.get("key_results") or {}).items())
            if isinstance(record.get("key_results"), dict)
            else "",
        ]
        haystack = " ".join(haystack_parts).lower()
        tokens = needle.split()
        if all(token in haystack for token in tokens):
            matches.append(experiment)
    return matches


def _parse_start_date(value: str) -> date:
    match = re.search(r"(20\d{2})(?:-(\d{2}))?(?:-(\d{2}))?", value or "")
    if not match:
        return date.max
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    return date(year, month, day)


def _extract_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if not markdown:
        return sections
    matches = list(re.finditer(r"^#{1,6}\s+(.+?)\s*$", markdown, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        heading = re.sub(r"[`*_]", "", match.group(1)).strip().lower()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        content = markdown[match.end() : end].strip()
        sections[heading] = content
    return sections


def _section(experiment: ResearchExperiment, *names: str) -> str:
    for name in names:
        normalized = name.lower()
        for key, value in experiment.sections.items():
            if key == normalized or normalized in key:
                return value
    return ""


def _status_label(status: str) -> str:
    zh, en = STATUS_LABELS.get(status, (status, status))
    return t(zh, en)


def _experiment_status_label(experiment: ResearchExperiment) -> str:
    if experiment.status == "passed_research_gate" and experiment.required_evidence_pending:
        return t("历史记录通过；当前必需证据待补", "Historical pass; required evidence pending")
    if experiment.status == "passed_research_gate" and experiment.canonical_evidence_available == 0:
        return t("历史记录通过；当前无 canonical 机器证据", "Historical pass; no canonical machine evidence currently available")
    return _status_label(experiment.status)


def _metric_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, list):
        return ", ".join(_metric_value(item) for item in value)
    return str(value)


def _metric_items(experiment: ResearchExperiment) -> list[tuple[str, str, str]]:
    record = experiment.record
    result = record.get("key_results") if isinstance(record.get("key_results"), dict) else {}
    items: list[tuple[str, str, str]] = [
        (t("研究状态", "Status"), _experiment_status_label(experiment), t("研究档案状态", "Research archive status")),
        (t("市场", "Markets"), ", ".join(str(item) for item in record.get("markets", []) or []) or "—", t("结论独立于市场", "Market-local conclusions")),
        (t("证据", "Evidence"), f"{experiment.evidence_available}/{experiment.evidence_total}", t(f"其中 canonical {experiment.canonical_evidence_available} 条", f"{experiment.canonical_evidence_available} canonical")),
    ]
    for key, value in list(result.items())[:3]:
        label = key.replace("_", " ")
        if get_ui_language_safe() == "zh":
            label = ZH_METRIC_LABELS.get(experiment.experiment_id, {}).get(key, ZH_GENERIC_METRIC_LABELS.get(key, label))
        items.append((label, _metric_value(value), t("目录记录", "Catalog record")))
    return items


def _render_kv_grid(items: list[tuple[str, str, str]]) -> None:
    cards = "".join(
        f"<div class='analysis-kv-item'><span class='analysis-kv-label'>{html.escape(label)}</span>"
        f"<span class='analysis-kv-value'>{html.escape(value)}</span>"
        f"<span class='analysis-kv-meta'>{html.escape(meta)}</span></div>"
        for label, value, meta in items
    )
    render_html(f"<div class='analysis-kv-grid research-kv-grid'>{cards}</div>", localize=False)


def _render_timeline(experiments: list[ResearchExperiment], selected_id: str) -> None:
    rows: list[str] = []
    for index, experiment in enumerate(experiments, start=1):
        active = " active" if experiment.experiment_id == selected_id else ""
        href = _research_experiment_href(experiment.experiment_id)
        rows.append(
            f"<a class='research-timeline-node{active}' href='{html.escape(href, quote=True)}'>"
            f"<span class='research-timeline-index'>{index:02d}</span>"
            f"<strong>{html.escape(experiment.title)}</strong>"
            f"<small>{html.escape(_experiment_status_label(experiment))}</small></a>"
        )
    render_html(f"<nav class='research-timeline' aria-label='{html.escape(t('研究目录', 'Research contents'))}'>{''.join(rows)}</nav>", localize=False)


def _render_experiment_toc(experiments: list[ResearchExperiment], selected_id: str) -> None:
    # Reuse the exact hierarchy and class contract of the Help/report rail.
    # Keeping one directory implementation avoids the old research-only rail
    # drifting in width, active states, and responsive behavior.
    groups = []
    for index, experiment in enumerate(experiments):
        active = " is-active" if experiment.experiment_id == selected_id else ""
        href = _research_experiment_href(experiment.experiment_id)
        groups.append(
            f"<div class='report-scroll-rail-group' data-report-group='{index}'>"
            f"<a class='report-scroll-rail-chapter{active}' href='{html.escape(href, quote=True)}' "
            f"data-report-section='research-{html.escape(experiment.experiment_id)}' title='{html.escape(experiment.title, quote=True)}'>"
            f"{html.escape(experiment.title)}</a></div>"
        )
    render_html(
        f"<aside class='report-scroll-rail' aria-label='{html.escape(t('本页目录', 'On this page'), quote=True)}'>"
        f"<span class='report-scroll-rail-label'>{html.escape(t('本页目录', 'On this page'))}</span>"
        f"<nav>{''.join(groups)}</nav></aside>",
        localize=False,
    )


def _research_experiment_href(experiment_id: str) -> str:
    """Navigate like the Help/report rail: rerun with the selected chapter."""
    return f"{route_href('model-evaluation', query={'experiment': experiment_id})}#research-{experiment_id}"


def _query_experiment_id() -> str:
    try:
        value = st.query_params.get("experiment", "")
        if isinstance(value, (list, tuple)):
            value = value[-1] if value else ""
        return str(value or "")
    except (AttributeError, KeyError, TypeError):
        return ""


def _render_section(title: str, body: str, *, fallback: str, section_key: str) -> None:
    # Streamlit element keys must be unique across the complete archive.  The
    # same six section titles are rendered for every experiment, so include
    # the experiment id in the key seed rather than relying on the title only.
    slug = hashlib.sha1(f"{section_key}:{title}".encode("utf-8")).hexdigest()[:10]
    with st.container(key=f"research-detail-{section_key}-{slug}"):
        st.markdown(f"<div class='surface-kicker'>{html.escape(title)}</div>", unsafe_allow_html=True)
        if body:
            st.markdown(body)
        else:
            st.markdown(f"<p class='research-empty'>{html.escape(fallback)}</p>", unsafe_allow_html=True)


def _markdown_body(body: str) -> str:
    """Keep markdown semantics in Streamlit while escaping only HTML wrappers."""
    return body


def _render_evidence_ledger(experiment: ResearchExperiment, repo_root: Path) -> None:
    rows = []
    for item in experiment.evidence:
        state = t("可用", "Available") if item.present else (t("待补", "Pending") if item.required else t("不可用", "Unavailable"))
        kind = t("补充证据", "Supplemental") if item.supplemental else (t("必需", "Required") if item.required else t("可选", "Optional"))
        tone = "available" if item.present else "pending"
        rows.append(
            f"<tr><td><code>{html.escape(item.path)}</code></td><td><span class='research-evidence-badge {tone}'>{html.escape(state)}</span></td>"
            f"<td>{html.escape(kind)}</td></tr>"
        )
    sources = experiment.record.get("sources", []) if isinstance(experiment.record.get("sources"), list) else []
    source_rows = []
    for source in sources:
        source_path = repo_root / str(source)
        source_rows.append(
            f"<li><span class='research-source-state {'available' if source_path.exists() else 'pending'}'>"
            f"{'✓' if source_path.exists() else '…'}</span><code>{html.escape(str(source))}</code></li>"
        )
    render_html(
        f"<section class='research-detail-section research-ledger'><div class='surface-kicker'>{html.escape(t('证据账本', 'Evidence ledger'))}</div>"
        f"<p>{html.escape(t('每个指标都必须回到可定位的源文件；缺失 Git-ignored 输出只显示待补，不会被填成 0。', 'Every metric must trace to a locatable source. Missing Git-ignored outputs stay pending and are never filled with zeros.'))}</p>"
        f"<table><thead><tr><th>{html.escape(t('路径', 'Path'))}</th><th>{html.escape(t('状态', 'State'))}</th><th>{html.escape(t('类型', 'Type'))}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"<details><summary>{html.escape(t('计划、代码和验收源文件', 'Plans, code and acceptance sources'))}</summary><ul>{''.join(source_rows) or '<li>—</li>'}</ul></details></section>",
        localize=False,
    )


def _read_csv(repo_root: Path, relative_path: str) -> pd.DataFrame:
    path = repo_root / relative_path
    try:
        return pd.read_csv(path) if path.is_file() else pd.DataFrame()
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()


def _chart_frame(experiment: ResearchExperiment, repo_root: Path) -> tuple[str, pd.DataFrame]:
    """Return the best real CSV already present for a timeline experiment."""
    candidates = {
        "baseline_sm_fsm_full_market": "model-test/outputs/full_us_deans_60/model_summary.csv",
        "transformer_state_feasibility": "model-test/outputs/transformer_state_v3_us/baseline_artifacts/baseline_comparison.csv",
        "adaptive_dynamic_experts": "model-test/outputs/w11_admission_us/w11_split_summary.csv",
        "cn_a_composite_only": "model-test/outputs/cn_a_factor_composite_comparison/comparison_metrics.csv",
        "cn_a_composite_advisory": "model-test/outputs/composite_advisory_phase1/ablation_metrics.csv",
        "us_composite": "model-test/outputs/composite_stability_phase4/admission_summary.csv",
        "ml_enhancement": "model-test/outputs/full_us_deans_60/model_summary.csv",
    }
    path = candidates.get(experiment.experiment_id, "")
    return path, _read_csv(repo_root, path) if path else pd.DataFrame()


def _render_chart(experiment: ResearchExperiment, repo_root: Path) -> None:
    path, frame = _chart_frame(experiment, repo_root)
    if frame.empty:
        render_status_note(t("没有找到可绘图的已落地 CSV；这不是零结果。", "No materialized CSV is available for a chart; this is not a zero result."), tone="warning")
        return

    figure = go.Figure()
    title = t("可复核数据图表", "Reproducible evidence chart")
    if experiment.experiment_id in {"cn_a_composite_only"} and {"model_name", "sharpe_mean"}.issubset(frame.columns):
        figure.add_bar(x=frame["model_name"], y=frame["sharpe_mean"], name=t("Sharpe", "Sharpe"))
        figure.update_yaxes(title_text=t("Sharpe", "Sharpe"))
        title = t("CN_A Composite 与 SM/FSM 的统一 Sharpe 对比", "Unified CN_A Sharpe comparison: Composite vs SM/FSM")
    elif experiment.experiment_id == "transformer_state_feasibility" and {"method", "mean_query_selected_utility"}.issubset(frame.columns):
        grouped = frame.groupby("method", as_index=False)[["mean_query_selected_utility", "mean_regret"]].mean()
        figure.add_bar(x=grouped["method"], y=grouped["mean_query_selected_utility"], name=t("查询效用", "Query utility"))
        figure.add_bar(x=grouped["method"], y=grouped["mean_regret"], name=t("遗憾", "Regret"))
        figure.update_yaxes(title_text=t("效用 / 遗憾", "Utility / regret"))
        title = t("查询效用与遗憾：为什么 Transformer 在门前停止", "Query utility and regret: why Transformer stopped")
    elif experiment.experiment_id == "adaptive_dynamic_experts" and {"split_id", "candidate_total_return", "adaptive_total_return"}.issubset(frame.columns):
        figure.add_bar(x=frame["split_id"], y=frame["candidate_total_return"], name=t("候选策略", "Candidate"))
        figure.add_bar(x=frame["split_id"], y=frame["adaptive_total_return"], name=t("Adaptive 对照", "Adaptive control"))
        figure.update_yaxes(tickformat=".1%", title_text=t("净收益", "Net return"))
        title = t("W11 US 四个窗口：候选策略与 adaptive control", "W11 US: candidate vs adaptive control across four windows")
    elif experiment.experiment_id == "cn_a_composite_advisory" and {"policy", "sharpe", "max_drawdown"}.issubset(frame.columns):
        grouped = frame.groupby("policy", as_index=False)[["sharpe", "max_drawdown"]].mean()
        figure.add_bar(x=grouped["policy"], y=grouped["sharpe"], name=t("Sharpe", "Sharpe"))
        figure.add_bar(x=grouped["policy"], y=grouped["max_drawdown"], name=t("最大回撤", "Max drawdown"))
        figure.update_yaxes(title_text=t("指标", "Metric"))
        title = t("Advisory 消融：收益与风险必须同时看", "Advisory ablation: read return and risk together")
    elif experiment.experiment_id == "us_composite" and {"strategy_variant", "pass_rate"}.issubset(frame.columns):
        figure.add_bar(x=frame["strategy_variant"], y=frame["pass_rate"], name=t("Fold 通过率", "Fold pass rate"))
        figure.update_yaxes(tickformat=".0%", title_text=t("Fold 通过率", "Fold pass rate"))
        title = t("US Composite 跨 fold 准入率", "US Composite cross-fold admission rate")
    elif {"display_name", "total_score"}.issubset(frame.columns):
        sample = frame.sort_values("rank").head(10) if "rank" in frame.columns else frame.head(10)
        figure.add_bar(x=sample["display_name"], y=sample["total_score"], name=t("综合分", "Total score"))
        figure.update_yaxes(title_text=t("分数", "Score"))
        title = t("基线模型综合分（前十）", "Baseline composite score (top ten)")
    else:
        render_status_note(t("该实验的已落地数据暂不满足图表字段要求。", "The materialized data does not contain the fields needed for a chart."), tone="warning")
        return

    figure.update_layout(
        title=None,
        height=360,
        margin=dict(l=10, r=10, t=20, b=110),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.08, x=0),
    )
    st.markdown(f"#### {html.escape(title)}")
    is_supplemental = any(item.path == path and item.supplemental for item in experiment.evidence)
    source_label = t("补充诊断来源（不等于 canonical gate 证据）", "Supplemental diagnostic source (not canonical gate evidence)") if is_supplemental else t("真实来源", "Real source")
    st.caption(f"{source_label}: {path}")
    if is_supplemental:
        render_status_note(
            t("这张图使用已有补充产物帮助理解研究过程；它不会替代目录中声明的必需 manifest / ablation gate。", "This chart uses an existing supplemental artifact to explain the process; it does not replace the required manifest/ablation gate declared by the catalog."),
            tone="warning",
        )
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "responsive": True}, key=f"research-chart-{experiment.experiment_id}")


def _render_experiment_detail(experiment: ResearchExperiment, repo_root: Path) -> None:
    record = experiment.record
    anchor = html.escape(experiment.experiment_id)
    question = _localized_record_text(experiment, "question")
    render_html(
        f"<article id='research-{anchor}' class='research-experiment'>"
        f"<div class='research-experiment-heading'><div>"
        f"<h2>{html.escape(experiment.title)}</h2><p>{html.escape(question)}</p></div>"
        f"<span class='research-status-pill {html.escape(experiment.status)}'>{html.escape(_experiment_status_label(experiment))}</span></div></article>",
        localize=False,
    )
    _render_kv_grid(_metric_items(experiment))
    if experiment.required_evidence_pending or (
        experiment.status == "passed_research_gate" and experiment.canonical_evidence_available == 0
    ):
        render_status_note(
            t(
                "目录记录保留了历史结论，但至少一份必需机器证据当前缺失；请勿把该条目当作当前可复核的准入证明。",
                "The catalog preserves the historical conclusion, but at least one required machine-readable artifact is missing; do not treat this entry as currently verifiable admission evidence.",
            ),
            tone="warning",
        )

    # The README sections are the human-readable research report.  Keeping
    # them sourced from disk makes the page update with the archive and avoids
    # copying stale narrative into UI code.
    section_key = experiment.experiment_id
    _render_section(t("研究计划与范围", "Plan and frozen scope"), _markdown_body(_localized_section(experiment, "scope", "frozen scope", "scope", "hypothesis")), fallback=t("此记录没有单独的范围段落。", "No separate scope section is recorded."), section_key=section_key)
    _render_section(t("研究流程", "Research flow"), _markdown_body(_localized_section(experiment, "flow", "research flow", "workflow")), fallback=t("此记录没有流程段落。", "No research-flow section is recorded."), section_key=section_key)
    _render_section(t("重要决策与关键想法", "Decisions and key ideas"), _markdown_body(_localized_section(experiment, "decisions", "key decisions and ideas", "decisions")), fallback=t("此记录没有决策段落。", "No decision section is recorded."), section_key=section_key)
    _render_section(t("结果与图表", "Results and charts"), _markdown_body(_localized_section(experiment, "result", "result and current status", "result")), fallback=t("没有叙述性结果；请以证据账本为准。", "No narrative result is recorded; use the evidence ledger."), section_key=section_key)
    _render_chart(experiment, repo_root)

    result = record.get("key_results") if isinstance(record.get("key_results"), dict) else {}
    if result:
        rows = [{t("指标", "Metric"): key.replace("_", " "), t("值", "Value"): _metric_value(value)} for key, value in result.items()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    gate_text = _localized_section(experiment, "gate", "gate and current status", "gate and stop conditions", "gate")
    if not gate_text:
        gate_text = str(record.get("gate", ""))
    _render_section(t("Gate：在哪里停下或放行", "Gate: where it stopped or passed"), _markdown_body(gate_text), fallback=t("目录没有记录 gate 说明。", "No gate explanation is recorded."), section_key=section_key)
    limitations = record.get("limitations") if isinstance(record.get("limitations"), list) else []
    limitations_body = "\n".join(f"- {item}" for item in limitations)
    problems = _localized_section(experiment, "problems", "problems and future work", "problems and future remedies", "problems")
    _render_section(t("问题、卡点与未来解决方法", "Problems, blockers and future remedies"), _markdown_body(problems or limitations_body), fallback=t("没有记录局限；这不代表不存在局限。", "No limitations are recorded; this does not imply there are none."), section_key=section_key)
    _render_evidence_ledger(experiment, repo_root)


def render_research_archive_page(*, repo_root: Path = REPO_ROOT) -> bool:
    """Render the new archive browser and return whether it was rendered."""
    # Compatibility: legacy tests use a tiny fake Streamlit object.  Real
    # Streamlit always has text_input; this lets the old report helpers remain
    # testable without coupling them to the archive browser.
    if not hasattr(st, "text_input"):
        return False

    experiments, issues = load_research_experiments(repo_root)
    if not experiments:
        render_status_note(t("研究目录暂时不可用。", "The research catalog is unavailable."), tone="error")
        for issue in issues:
            st.caption(issue)
        return True

    render_html(
        f"<div class='research-archive-title-wrap'><h1 class='research-archive-title'>{html.escape(t('从基线到 Composite：完整研究报告', 'From baseline to Composite: the complete research report'))}</h1></div>",
        localize=False,
    )

    query = st.text_input(
        t("搜索研究：实验名、结论、gate、文件路径或指标", "Search research: title, conclusion, gate, path or metric"),
        key="research-archive-search",
        placeholder=t("例如：Composite、Transformer、drawdown、pending", "e.g. Composite, Transformer, drawdown, pending"),
    )
    filtered = search_research_experiments(experiments, query)
    if query and not filtered:
        render_status_note(t("没有匹配的实验；尝试搜索 Composite、advisory、gate 或文件名。", "No experiment matched. Try Composite, advisory, gate or a file name."), tone="warning")
        return True
    if not filtered:
        filtered = experiments

    query_experiment = _query_experiment_id()
    selected_id = query_experiment if query_experiment in {item.experiment_id for item in filtered} else filtered[0].experiment_id
    _render_timeline(filtered, selected_id)
    _render_experiment_toc(filtered, selected_id)
    # Render every matching experiment as a continuous report.  The flowchart
    # and Help-style rail are the navigation controls; Streamlit expanders
    # would hide research details behind a second set of visual boxes and
    # make the archive look like a dashboard instead of a readable report.
    for experiment in filtered:
        _render_experiment_detail(experiment, repo_root)

    if issues:
        with st.expander(t("归档校验提示", "Archive validation notes")):
            for issue in issues:
                st.caption(issue)
    return True
