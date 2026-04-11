# 第9周计划 · 课程最终交付与项目收口 (W9 Final Delivery Plan)

**适用阶段：** 第 9 周 (W9)
**核心目标：** 停止开发新功能，将已有功能映射到课程 `Project Guidelines (4).md` 的得分点，完成最终 ZIP 打包、HTML 报告撰写与答辩（Defence）准备。

## 1. 最终提交物打包清单 (The ZIP File)

根据课程 Guidelines 4.1 节要求，最终需提交命名格式为 `Final_gpXX.zip`（XX为组号）的压缩包。压缩包解压后必须包含：

- [ ] **运行代码与环境 (`Related codes & files`)**
  - 清理后的项目完整代码（删除 `__pycache__`、`.git`、本地临时庞大数据等无关文件）。
  - 环境依赖清单 `requirements.txt` 或 `environment.yml`，确保助教/教授在纯净环境中能跑起来。
  - 数据文件或说明（若无自带全量本地数据，需在说明中提示 AkShare 实时拉取的网络要求）。
- [ ] **离线 HTML 报告 (`A HTML file`)**
  - 一个点击即可阅读的 HTML 文件。所有生成的最终报告及分析文档均统一存放在 `strategy/reports/` 文件夹中。可以复用 `ui/export_reports.py` 生成的完整报告，或单独编写一个包含应用运行截图、分析结论的静态页面。
- [ ] **运行说明文档 (`README.md`)**
  - 明确写出启动 WebApp 的确切命令（例如 `streamlit run app.py`）。

> **Smoke Test (冒烟测试) 强要求**：打包完 ZIP 后，必须发给组内另一台未运行过该项目的电脑，解压并完全按 README 运行一次。若无法启动，WebApp 将面临 0 分风险。

## 2. [x] 最终报告 (HTML) 核心模块与得分点映射

根据 Guidelines 2.1 节的 8 个 Basic Requirements，HTML 报告必须包含以下明确对应的章节标题。已建立 `strategy/reports/` 文件夹（见 `strategy/reports/Final_Report.html`），后续所有相关报告均生成至此目录。

1. **Problem Definition & Final Answer (对应 Requirement 1)**
   - *问题定义*：利用金融历史数据（美股/A股）预测资产价格走势，构建并评估量化投资策略。
   - *最终结论*：一句话总结 Proposed Model 是否跑赢了市场基线（买入持有）及课程简单基线。
2. **Proposed Models Specification (对应 Requirement 2)**
   - 清晰定义使用的复杂模型（如基于 `core/ml_filter.py` 的机器学习过滤模型，或 `core/adaptive_regime.py` 的自适应状态路由机制）。
3. **Model Analysis: Strengths, Weaknesses & Constraints (对应 Requirement 3)**
   - 列举模型的优缺点与约束。例如：机器学习模型拟合能力强（Strength），但在极端市场下易过拟合（Weakness），强依赖数据平稳性（Constraint）。
4. **Baseline Comparison (对应 Requirement 4)**
   - **核心得分点**：必须说明已实现 Lecture Notes 中的简单模型（Naive, Mean, Drift 等，对应 `core/baselines.py`），并用图表展示 Proposed Model 与这些基线的性能对比。
5. **Parameter Learning & WebApp Adjustability (对应 Requirement 5)**
   - 简述参数学习方式（如通过 Walk-Forward 滚动训练、贝叶斯优化寻找最优超参数）。
   - **截图得分点**：附上 WebApp 截图，证明参数（如训练窗口长度、特征数、阈值等）可在页面 UI 上由用户手动调节。
6. **Model Checking (对应 Requirement 6)**
   - 描述如何使用课件方法检验模型。例如：OOS (Out-of-Sample) 样本外测试、平稳性检验、残差分析（对应 `core/evaluation.py`）。
7. **Interpretation of Differences (对应 Requirement 7)**
   - 解释 Proposed Model 胜出/落后于 Baseline 的原因。例如通过特定技术指标（MACD, RSI，对应 `core/indicators.py`）捕捉到了基线模型无法察觉的非线性趋势。
8. **References (对应 Requirement 8)**
   - 规范列出所有参考文献（包含 Lecture Notes、使用的开源库如 AkShare、Streamlit，以及参考的论文/教材）。

## 3. WebApp 前端应用最终核稳

在封板前，对照确保 `app.py` 运行后的应用满足以下要求：

- [ ] **参数可调性可见**：UI 界面必须有供调节的组件（如侧边栏下拉框选模型、滑块调整周期），直接满足 Requirement 5。
- [ ] **图表对比直观**：单股分析页（`/strategy/stock-analysis`）必须能同时画出 Proposed Model 和 Baseline 的净值回撤曲线，满足 Requirement 4 与 7。
- [ ] **鲁棒性处理**：测试断网或输入偏门股票代码无数据时，页面必须有优雅的异常提示（如显示“暂无数据”），禁止红屏报错栈直接暴露给用户。
- [ ] **HTML 一键导出可用**：检查应用内的 HTML 导出功能排版是否正常，是否包含所有必需的评估指标文字。

## 4. 答辩 (Defence) 准备指南与日程建议

根据 Guidelines 第 3 节，每位成员需应对独立提问，重点准备以下防线：

- **防线 1：全链路认知**。每人必须清楚数据获取、特征工程、模型训练、回测评估的完整 Pipeline，防止被判分工不均或不了解项目。
- **防线 2：模型原理抽查**。能用自己的话解释 Naive Baseline 的含义，以及己方 ML 模型防过拟合的机制。
- **防线 3：代码架构定位**。遇到关于实现的提问，能迅速定位："数据预处理在 `core/data.py`，模型在 `core/signals.py`，评估在 `core/evaluation.py`"。

**建议 W9 倒计时 3 天日程：**
- **Day 1：代码冻结与修 Bug**。全员停止开发新功能（Feature Freeze）。测试 WebApp 稳定性，补充各类异常报错捕获。
- **Day 2：跑数据与写报告**。在 WebApp 中截图、生成图表实验数据，撰写最终的 HTML Report 并严格对齐上述的 8 个得分点。
- **Day 3：打包、冒烟测试与 Mock 答辩**。完成 ZIP 打包，在空白环境电脑上走一遍完整启动流程；组内开展一轮互相提问的模拟答辩。
