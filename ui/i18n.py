import streamlit as st

UI_LANGUAGE_STATE_KEY = "ui_language"

LOCALES: dict[str, dict[str, str]] = {
    "analysis.show_details": {
        "zh": "展开详情",
        "en": "Show details",
    },
    "analysis.hide_details": {
        "zh": "收起详情",
        "en": "Hide details",
    },
    "single.strategy.emptyBackdrop": {
        "zh": "交易，从这里开始",
        "en": "Trading starts here",
    },
    "dashboard.combinedLayout": {
        "zh": "组合 KPI + 个股表现表 + 主图",
        "en": "Portfolio KPI + Stock Performance Table + Main Chart"
    },
    "analysis.correlationHeatmap": {
        "zh": "股票相关性热图",
        "en": "Stock Correlation Heatmap"
    },
    "layout.preserveStructure": {
        "zh": "沿用净值上 / 回撤下的组合结构，不把结果拆散成多张独立卡片。",
        "en": "Keep portfolio structure above net value / below drawdown; do not split results into separate cards."
    },
    "strategy.generationFlow": {
        "zh": "Regime -> Adaptive Router V1 -> 动态候选切换 -> 生成策略",
        "en": "Regime → Adaptive Router V1 → Dynamic Candidate Switching → Strategy Generation"
    },
    "rules.exit": {
        "zh": "📉 出场规则",
        "en": "📉 Exit Rules"
    },
    "validation.enterUsStockCode": {
        "zh": "请输入美股代码后再添加。",
        "en": "Please enter a US stock symbol before adding."
    },
    "model.top1": {
        "zh": "Top 1 模型",
        "en": "Top 1 Model"
    },
    "market.latestVolume": {
        "zh": "最新成交量",
        "en": "Latest Volume"
    },
    "search.fallbackToCode": {
        "zh": "支持名称或代码检索。没有索引命中时，也会按代码直接进入分析。",
        "en": "Search by name or symbol. Falls back to direct analysis by symbol if no index match."
    },
    "chart.reusePortfolioChart": {
        "zh": "主图继续沿用结果区里的组合净值图。",
        "en": "Main chart continues to use the portfolio net value chart from results area."
    },
    "strategy.entryThreshold": {
        "zh": "入场阈值",
        "en": "Entry Threshold"
    },
    "analysis.comparisonTargets": {
        "zh": "个对比标的</span>\n  <span class=\"analysis-pill\">",
        "en": "comparison targets"
    },
    "chart.baselineStart": {
        "zh": "起点基准 (100)",
        "en": "Baseline Start (100)"
    },
    "action.refreshStockData": {
        "zh": "🔄 刷新所选股票数据",
        "en": "🔄 Refresh Selected Stock Data"
    },
    "state.saved": {
        "zh": "已保存：",
        "en": "Saved:"
    },
    "data.averageDays": {
        "zh": "平均数据天数",
        "en": "Average Data Days"
    },
    "section.overview": {
        "zh": "总览",
        "en": "Overview"
    },
    "analysis.stocksCompared": {
        "zh": "只股票进行对比",
        "en": "stocks compared"
    },
    "scoring.volatilityPenalty": {
        "zh": "波动率越高，评分惩罚越大。",
        "en": "Higher volatility results in greater score penalty."
    },
    "sentiment.neutralBullish": {
        "zh": "中性偏强",
        "en": "Neutral-Bullish"
    },
    "action.freezeContext": {
        "zh": "按当前页面上下文冻结",
        "en": "Freeze by Current Page Context"
    },
    "action.submitIssue": {
        "zh": "[📋 前往提交 Issue](",
        "en": "[📋 Submit Issue]("
    },
    "indicator.volume20d": {
        "zh": "20 日均量",
        "en": "20-Day Average Volume"
    },
    "market.currentPrice": {
        "zh": "当前价格",
        "en": "Current Price"
    },
    "market.name": {
        "zh": "市场",
        "en": "Market"
    },
    "indicator.obvVolumePriceCycle": {
        "zh": "OBV/成交量/价格位置周期",
        "en": "OBV/Volume/Price Position Cycle"
    },
    "analysis.technicalSnapshot": {
        "zh": "当前技术快照",
        "en": "Current Technical Snapshot"
    },
    "layout.unifiedConfiguration": {
        "zh": "组合权重、生成动作和参数搜索收敛到同一侧；策略参数仍统一复用左侧边栏，不再派生第二套配置来源。",
        "en": "Portfolio weight, generation actions, and parameter search converge to one side; strategy parameters still reuse the left sidebar uniformly, without a second configuration source."
    },
    "analysis.relativeStrengthBaseline": {
        "zh": "相对强弱基准",
        "en": "Relative Strength Baseline"
    },
    "error.emptyTrainingSet": {
        "zh": "训练集为空，无法生成策略阶段结果",
        "en": "Training set is empty; cannot generate strategy phase results."
    },
    "run.latestReadable": {
        "zh": "最新可读 run",
        "en": "Latest Readable Run"
    },
    "action.syncFromResults": {
        "zh": "从当前主结果区同步",
        "en": "Sync from Current Main Results"
    },
    "theme.dark": {
        "zh": "暗色",
        "en": "Dark"
    },
    "warning.noMLMetrics": {
        "zh": "当前所选策略没有 ML 过滤质量指标。",
        "en": "The selected strategy has no ML filtering quality metrics."
    },
    "performance.annualReturnPct": {
        "zh": "年化收益 %",
        "en": "Annual Return %"
    },
    "method.equalWeightedAvg": {
        "zh": "等权平均",
        "en": "Equal-Weighted Average"
    },
    "report.tearSheets": {
        "zh": "份 tear sheet",
        "en": "tear sheet(s)"
    },
    "strategy.portfolioStrategy": {
        "zh": "组合策略",
        "en": "Portfolio Strategy"
    },
    "error.insufficientHistory": {
        "zh": "当前历史窗口不足，无法稳定计算最新因子评分。",
        "en": "Insufficient historical window for stable latest factor score calculation."
    },
    "warning.noMACD": {
        "zh": "当前周期下没有可用的 MACD 指标。",
        "en": "No MACD indicator available for the current period."
    },
    "analysis.dailyFactorRanking": {
        "zh": "对每只股票独立计算最新一日综合因子评分，直接回答当前更值得关注谁。",
        "en": "Calculate latest daily composite factor score for each stock independently, directly indicating which is more noteworthy now."
    },
    "restriction.baselineNoEnhancements": {
        "zh": "Baseline 路径不允许启用 Search / FSM / ML 增强",
        "en": "Baseline path does not allow enabling Search / FSM / ML enhancements."
    },
    "chartMeta.target": {
        "zh": "</div>\n<div class=\"analysis-chart-meta\">\n  <span class=\"analysis-chart-chip\">标的",
        "en": "Target"
    },
    "axis.priceLog": {
        "zh": "价格（对数）",
        "en": "Price (Log)"
    },
    "run.currentSummary": {
        "zh": "<h3 class='surface-title'>当前 run 摘要</h3>",
        "en": "Current Run Summary"
    },
    "position.observationTarget": {
        "zh": "当前处于观察仓位，目标仓位",
        "en": "Currently in observation position, target position"
    },
    "report.tearSheetList": {
        "zh": "Tear Sheet 列表",
        "en": "Tear Sheet List"
    },
    "performance.currentNetDrawdown": {
        "zh": "当前策略净值 / 回撤",
        "en": "Current Strategy Net Value / Drawdown"
    },
    "state.generated": {
        "zh": "已生成",
        "en": "Generated"
    },
    "chart.dualLineConvergence": {
        "zh": "双线贴合",
        "en": "Dual-Line Convergence"
    },
    "optimization.bayesian": {
        "zh": "贝叶斯优化",
        "en": "Bayesian Optimization"
    },
    "model.configuration": {
        "zh": "模型配置",
        "en": "Model Configuration"
    },
    "result.board.notGenerated": {
        "zh": "结果板暂未生成",
        "en": "Result board not yet generated"
    },
    "report.generateDownloadHTML": {
        "zh": "🎁 生成并下载HTML报告",
        "en": "🎁 Generate & Download HTML Report"
    },
    "scoring.weight.volumeRatio": {
        "zh": "成交量比率在评分中的权重。",
        "en": "Weight of volume ratio in scoring."
    },
    "analysis.singleStock.title": {
        "zh": "单股策略分析 -",
        "en": "Single Stock Analysis -"
    },
    "parameterSearch.methodRequired": {
        "zh": "请先选择参数搜索方法",
        "en": "Please select a parameter search method first"
    },
    "data.download.adjustmentMethod": {
        "zh": "影响数据下载的复权方式。",
        "en": "Adjustment method affecting data download."
    },
    "configuration.regime.missing": {
        "zh": "Regime 配置缺失",
        "en": "Regime Configuration Missing"
    },
    "data.rowCount": {
        "zh": "数据行数",
        "en": "Data Row Count"
    },
    "data.priceRows": {
        "zh": "行价格数据",
        "en": "Price Data Rows"
    },
    "baseline.path.invalidKind": {
        "zh": "Baseline 路径缺少合法的 baseline_kind",
        "en": "Baseline path missing valid baseline_kind"
    },
    "comparison.countAndCurrent": {
        "zh": "条；当前参与比较：",
        "en": "items; currently comparing:"
    },
    "trading.sellPoint": {
        "zh": "卖点",
        "en": "Sell Point"
    },
    "chart.lowAndVolume": {
        "zh": "当日低点与成交量",
        "en": "Daily Low & Volume"
    },
    "strategy.exitThreshold": {
        "zh": "出场阈值",
        "en": "Exit Threshold"
    },
    "ui.multiStockEntry.render": {
        "zh": "渲染多股入口页，并在用户发起分析时返回动作。",
        "en": "Render multi-stock entry page and return action on user analysis request."
    },
    "testing.label": {
        "zh": "| 测试：",
        "en": "| Test:"
    },
    "chart.plotlyNote": {
        "zh": "图表由 Plotly 渲染；离线打开时仍保留响应式缩放。",
        "en": "Charts rendered by Plotly; responsive zoom remains available offline."
    },
    "indicator.bollinger.maPeriod": {
        "zh": "布林带移动平均线的计算周期。",
        "en": "Calculation period for Bollinger Bands moving average."
    },
    "indicator.trendStrength.period": {
        "zh": "趋势强度指标的计算周期。",
        "en": "Calculation period for trend strength indicator."
    },
    "strategy.selection": {
        "zh": "📋 策略选择",
        "en": "📋 Strategy Selection"
    },
    "portfolio.removeStock": {
        "zh": "移除股票",
        "en": "Remove Stock"
    },
    "note.recommendationSource": {
        "zh": "<p class='source-note'>当前推荐口径：<strong>",
        "en": "<p class='source-note'>Current recommendation source: <strong>"
    },
    "strategy.generatedCount": {
        "zh": "已生成策略：",
        "en": "Strategies generated:"
    },
    "comparison.insufficientStrategies": {
        "zh": "当前仅有 1 条可比较策略。保存更多快照或额外勾选策略后，可进行多策略比较。",
        "en": "Only 1 strategy available for comparison. Save more snapshots or select additional strategies for multi-strategy comparison."
    },
    "portfolio.insufficientData": {
        "zh": "当前数据不足以生成组合策略，请检查股票池长度和时间范围。",
        "en": "Insufficient data to generate portfolio strategy. Check stock pool size and time range."
    },
    "scoring.label": {
        "zh": "· 分数",
        "en": "· Score"
    },
    "parameterSearch.enabledNote": {
        "zh": "已启用参数搜索：搜索结果只进入 lineage / artifact，不会自动回写侧边栏参数。",
        "en": "Parameter search enabled: results go to lineage/artifact only, not auto-written to sidebar."
    },
    "configuration.name": {
        "zh": "配置名称",
        "en": "Configuration Name"
    },
    "analysis.readyFor": {
        "zh": "当前准备分析：",
        "en": "Ready to analyze:"
    },
    "data.noNavDrawdown": {
        "zh": "暂无可展示的净值与回撤数据。",
        "en": "No NAV or drawdown data available to display."
    },
    "chart.periodReturnHeatmap": {
        "zh": "周期收益率热图",
        "en": "Period Return Heatmap"
    },
    "chart.multiStockPriceComparison": {
        "zh": "多股票价格对比（归一化）",
        "en": "Multi-Stock Price Comparison (Normalized)"
    },
    "status.saved": {
        "zh": "已保存 ·",
        "en": "Saved ·"
    },
    "data.upload.multipleCSV": {
        "zh": "上传多个本地 CSV",
        "en": "Upload Multiple Local CSVs"
    },
    "table.metricComparison": {
        "zh": "指标对比表",
        "en": "Metric Comparison Table"
    },
    "chart.dataWithTradePoints": {
        "zh": "数据，买卖点叠加展示所有已选策略。",
        "en": "Data with buy/sell points overlaid for all selected strategies."
    },
    "chart.relativeStrength": {
        "zh": "相对强弱对比图",
        "en": "Relative Strength Comparison Chart"
    },
    "parameter.presetApplied": {
        "zh": "」预设，以下参数已自动填充。切换为「自定义参数」可手动修改。",
        "en": "」 preset applied. Parameters below auto-filled. Switch to \"Custom Parameters\" to edit manually."
    },
    "layout.combinedKPIAndStockTable": {
        "zh": "图五要求的“组合 KPI 摘要 + 个股表现表”已固定在同一结果区，切换主图不会打散下方信息。",
        "en": "\"Portfolio KPI Summary + Stock Performance Table\" (Fig.5) is fixed in the same result area; switching main charts won't disrupt info below."
    },
    "ui.renderMultiLineHTML": {
        "zh": "渲染多行 HTML，避免 markdown 缩进把标签当成普通文本。",
        "en": "Render multi-line HTML to avoid markdown indentation treating tags as plain text."
    },
    "chart.chip.emaSlow": {
        "zh": "</span>\n  <span class=\"analysis-chart-chip\">EMA 慢线",
        "en": "</span>\n  <span class=\"analysis-chart-chip\">EMA Slow Line"
    },
    "strategy.selectionRequired": {
        "zh": "请先在左侧策略库中勾选至少一条策略。",
        "en": "Please select at least one strategy from the left strategy library."
    },
    "upload.noFileSelected": {
        "zh": "还没有选择上传文件。",
        "en": "No file selected for upload."
    },
    "period.1year": {
        "zh": "1年",
        "en": "1 Year"
    },
    "strategy.noMetrics": {
        "zh": "当前没有可展示的策略指标。",
        "en": "No strategy metrics available to display."
    },
    "comparison.multiStrategyTradePoints": {
        "zh": "多策略买卖点比较",
        "en": "Multi-Strategy Trade Point Comparison"
    },
    "link.enterSingleStockAnalysis": {
        "zh": "\">进入单股分析</a>\n        <a class=\"cta-link secondary\" href=\"",
        "en": "\">Enter Single Stock Analysis</a>\n        <a class=\"cta-link secondary\" href=\""
    },
    "scoring.percentile.mid": {
        "zh": "评分分位数-中档",
        "en": "Score Percentile - Mid"
    },
    "exposure.percentage": {
        "zh": "Exposure 占比",
        "en": "Exposure Ratio"
    },
    "strategy.momentum_breakout_aggressive": {
        "zh": "动量突破（激进）",
        "en": "Momentum Breakout (Aggressive)"
    },
    "data.current_uploaded_data": {
        "zh": "当前使用上传数据：",
        "en": "Current Uploaded Data:"
    },
    "validation.param_search_method_required": {
        "zh": "启用参数搜索时必须选择合法的搜索方法",
        "en": "A valid search method is required for parameter search."
    },
    "market.cn_stock": {
        "zh": "A 股",
        "en": "A-Shares"
    },
    "metric.optimized_sharpe": {
        "zh": "优化后夏普",
        "en": "Optimized Sharpe"
    },
    "warning.no_index_match_fallback": {
        "zh": "未找到索引匹配，将按该美股代码直接尝试分析。",
        "en": "No index match found. Will analyze directly using the US stock symbol."
    },
    "model.selection_prompt": {
        "zh": "请选择 ML 模型",
        "en": "Select ML Model"
    },
    "ui.render_inline_status": {
        "zh": "渲染内联状态提示。",
        "en": "Render inline status hint."
    },
    "price.change": {
        "zh": "&middot; 涨跌",
        "en": "Change"
    },
    "price.latest": {
        "zh": "最新价格",
        "en": "Latest Price"
    },
    "performance.individual_stock_strategy": {
        "zh": "各股票独立策略表现",
        "en": "Individual Stock Strategy Performance"
    },
    "strategy.template_description": {
        "zh": "预设策略模板会自动填充入场/出场规则和高级设置中的所有参数。选择「自定义参数」可手动调节。",
        "en": "Preset templates auto-fill all entry/exit rules and advanced parameters. Select 'Custom Parameters' to adjust manually."
    },
    "chart.price_comparison": {
        "zh": "价格对比分析图",
        "en": "Price Comparison Chart"
    },
    "validation.select_main_strategy_for_heatmap": {
        "zh": "请先选定一个主策略，再查看收益热图。",
        "en": "Please select a main strategy first to view the return heatmap."
    },
    "strategy.regime_legacy_dual_state_routing": {
        "zh": "Regime -> Legacy 双状态路由 -> 生成策略",
        "en": "Regime -> Legacy Dual-State Routing -> Generate Strategy"
    },
    "scoring.normalization_window": {
        "zh": "评分标准化窗口",
        "en": "Score Normalization Window"
    },
    "strategy.current": {
        "zh": "当前策略",
        "en": "Current Strategy"
    },
    "layout.chart_description": {
        "zh": "左侧用文字快速交代当前标的状态，右侧保留高密度 K 线主图和指标小图，训练/测试边界在行情图里保持可见。",
        "en": "Left: quick status summary. Right: high-density main chart with sub-indicators. Train/test boundary visible."
    },
    "strategy.atr_stop_loss_take_profit": {
        "zh": "**ATR 止损止盈**",
        "en": "ATR Stop Loss & Take Profit"
    },
    "artifact.current": {
        "zh": "当前 artifact",
        "en": "Current Artifact"
    },
    "chart.render_artifact_signals": {
        "zh": "渲染主 artifact 的训练/测试集交易信号图。",
        "en": "Render training/test trade signals for the main artifact."
    },
    "chart.build_main_candlestick": {
        "zh": "构建 K 线主图。",
        "en": "Build main candlestick chart."
    },
    "chart.daily_k": {
        "zh": "日 K",
        "en": "Daily"
    },
    "analysis.correlation_matrix_description": {
        "zh": "用共同交易日收益率构造相关性矩阵，帮助判断股票池是否过于同质化。",
        "en": "Correlation matrix from common trading days helps assess if the stock pool is too homogeneous."
    },
    "chart.scatter_plot_legend": {
        "zh": "越靠左上通常代表越高收益、越低风险；颜色映射到夏普水平。",
        "en": "Top-left: higher return, lower risk. Color maps to Sharpe level."
    },
    "section.multi_stock_basic_info": {
        "zh": "多股基础信息区",
        "en": "Multi-Stock Basic Info"
    },
    "ui.render_time_range_control": {
        "zh": "在分析页头部渲染时间范围控件，并同步到 sidebar 状态。",
        "en": "Render time range control in header and sync with sidebar."
    },
    "statistics.quantile_percent": {
        "zh": "分位数 %",
        "en": "Quantile %"
    },
    "status.enabled_not_generated": {
        "zh": "已启用，暂未生成",
        "en": "Enabled, not yet generated"
    },
    "indicator.rsi_weak_threshold": {
        "zh": "RSI 低于该值视为偏弱。",
        "en": "RSI below this is considered weak."
    },
    "action.upload_single_stock_csv": {
        "zh": "上传单只股票 CSV",
        "en": "Upload Single Stock CSV"
    },
    "analysis.benchmark_equal_weight_description": {
        "zh": "默认相对基准使用等权平均，判断每只股票是持续跑赢还是持续跑输股票池。",
        "en": "Uses equal-weighted average as benchmark to identify consistent outperformers/underperformers."
    },
    "section.market_snapshot_and_entry": {
        "zh": "市场指数和推荐股票",
        "en": "Market Indices and Recommended Stocks"
    },
    "indicator.ema_spread": {
        "zh": "EMA 价差",
        "en": "EMA Spread"
    },
    "analysis.secondary_judgment_line": {
        "zh": "直接回答当前更值得关注谁，作为图表以外的第二条判断线。",
        "en": "Direct recommendation on which to watch, as a second judgment line beyond charts."
    },
    "backtest.walk_forward_returns": {
        "zh": "Walk-Forward 策略收益：",
        "en": "Walk-Forward Strategy Returns:"
    },
    "status.using_uploaded_csv": {
        "zh": "✓ 将使用上传的CSV数据",
        "en": "✓ Using uploaded CSV data"
    },
    "weight.volume_ratio": {
        "zh": "成交量比率权重",
        "en": "Volume Ratio Weight"
    },
    "action.generate_strategy": {
        "zh": "-> 生成策略",
        "en": "-> Generate Strategy"
    },
    "indicator.macd_histogram": {
        "zh": "MACD 柱体",
        "en": "MACD Histogram"
    },
    "routing.single_stock_mode_notice": {
        "zh": "当前处于单股路由，仅使用第一只股票进入主分析页。",
        "en": "Single-stock routing mode: only the first stock enters the main analysis."
    },
    "period.quarter": {
        "zh": "季度",
        "en": "Quarter"
    },
    "error.no_stocks_to_analyze": {
        "zh": "当前没有可分析的股票，请返回入口页重新选择。",
        "en": "No stocks to analyze. Please go back and reselect."
    },
    "action.switch": {
        "zh": "切换",
        "en": "Switch"
    },
    "dataset.training": {
        "zh": "训练集",
        "en": "Training Set"
    },
    "validation.portfolio_weight_sum": {
        "zh": "组合权重之和必须大于 0。",
        "en": "Portfolio weight sum must be greater than 0."
    },
    "status.switched_to_stock_only": {
        "zh": "已切到 stock-only",
        "en": "Switched to stock-only"
    },
    "stage.final": {
        "zh": "最终阶段",
        "en": "Final Stage"
    },
    "ui.render_walk_forward_backtest": {
        "zh": "渲染 Walk-Forward 回测区域。",
        "en": "Render Walk-Forward backtest area."
    },
    "filter.validSamples.currentTime": {
        "zh": "按当前时间筛选后的有效样本",
        "en": "Valid samples filtered by current time"
    },
    "settings.enableMLFilter": {
        "zh": "启用 ML 过滤",
        "en": "Enable ML filter"
    },
    "price.highest": {
        "zh": "最高价",
        "en": "Highest price"
    },
    "range.position": {
        "zh": "区间位置",
        "en": "Range position"
    },
    "trading.buySellPoints": {
        "zh": "买卖点",
        "en": "Buy/Sell points"
    },
    "guidance.researchStart": {
        "zh": "先看市场上下文，再决定这次研究到底从哪只股票或哪组股票开始。",
        "en": "Check market context first, then decide which stock or group to start with."
    },
    "score.total": {
        "zh": "总分",
        "en": "Total score"
    },
    "strategy.entryScoreThreshold": {
        "zh": "入场评分阈值",
        "en": "Entry score threshold"
    },
    "data.coverageRange": {
        "zh": "覆盖区间",
        "en": "Coverage range"
    },
    "model.selectSearchBase": {
        "zh": "请选择 Search 基础模型",
        "en": "Select Search base model"
    },
    "ui.designPrinciple": {
        "zh": "目标不是把更多面板堆上来，而是让研究路径一眼就能看懂。",
        "en": "Goal: clarity over clutter—make the research path instantly understandable."
    },
    "action.searchConfirmTarget": {
        "zh": "选择股票",
        "en": "Choose a Stock"
    },
    "chart.monthlyReturnsDescription": {
        "zh": "按主策略测试集日收益率复利聚合到月份；绿色代表正收益，红色代表负收益。",
        "en": "Monthly compounded returns from daily test-set yields; green = positive, red = negative."
    },
    "status.modelNotReady": {
        "zh": "模型还没准备好。",
        "en": "Model not ready."
    },
    "error.unknownSearchMethod": {
        "zh": "未知 search_method:",
        "en": "Unknown search_method:"
    },
    "feedback.inAppSubmission": {
        "zh": "--- *通过应用内反馈提交*",
        "en": "--- *Submit via in-app feedback*"
    },
    "model.trainRatio": {
        "zh": "训练比例",
        "en": "Training ratio"
    },
    "price.latestOHL": {
        "zh": "最新开盘 / 最高 / 最低",
        "en": "Latest Open / High / Low"
    },
    "model.fsmBase": {
        "zh": "FSM基础",
        "en": "FSM base"
    },
    "action.selectRun": {
        "zh": "选择 run",
        "en": "Select run"
    },
    "theme.light": {
        "zh": "亮色",
        "en": "Light"
    },
    "action.downloadTearSheet": {
        "zh": "下载 tear sheet",
        "en": "Download tear sheet"
    },
    "section.title.controlPanel": {
        "zh": "📊 控制面板",
        "en": "📊 Control Panel"
    },
    "chart.multiStockComparison": {
        "zh": "多股票价格对比分析图",
        "en": "Multi-stock price comparison chart"
    },
    "page.readOnlyResults": {
        "zh": "只读结果浏览页",
        "en": "Read-only results viewer"
    },
    "workflow.dynamicSwitch": {
        "zh": "输入新股票后即可直接切换，当前页面的工作流会跟随新标的重新建立。",
        "en": "Enter a new ticker to switch instantly; workflow rebuilds for the new target."
    },
    "mode.proxy": {
        "zh": "代理模式",
        "en": "Proxy mode"
    },
    "data.csvFormat": {
        "zh": "每个 CSV 视为一只股票，列名需兼容 date/open/high/low/close/volume 标准。",
        "en": "Each CSV = one stock; columns must follow date/open/high/low/close/volume."
    },
    "model.family": {
        "zh": "模型族",
        "en": "Model Family"
    },
    "strategy.resultStructure": {
        "zh": "策略结果结构",
        "en": "Strategy result structure"
    },
    "section.browseExistingRuns": {
        "zh": "<h3 class='surface-title'>浏览已有研究 run</h3>",
        "en": "<h3 class='surface-title'>Browse existing research runs</h3>"
    },
    "window.mainPlus": {
        "zh": "主窗口 +",
        "en": "Main window +"
    },
    "algorithm.genetic": {
        "zh": "遗传算法",
        "en": "Genetic algorithm"
    },
    "status.configuringStrategy": {
        "zh": "当前正在配置策略请求；完成必要选择后即可生成。",
        "en": "Configuring strategy request—complete selections to generate."
    },
    "status.strategyReady": {
        "zh": "当前上下文中已有最新生成策略，可继续查看下游分析或再次生成。",
        "en": "Latest strategy ready. Proceed to downstream analysis or regenerate."
    },
    "metrics.maxDrawdownPercent": {
        "zh": "最大回撤 %",
        "en": "Max drawdown %"
    },
    "weight.rangePosition": {
        "zh": "价格在近期高低范围中的位置权重。",
        "en": "Weight of price within recent high-low range."
    },
    "error.insufficientData": {
        "zh": "数据量不足，无法进行策略工作流分析。",
        "en": "Insufficient data for strategy workflow analysis."
    },
    "common.model": {
        "zh": "模型",
        "en": "Model"
    },
    "scope.usMarketNote": {
        "zh": "当前版本只在美股展示，默认使用 SPY 作为市场代理；若代理不可用，会降级为 stock-only 路由。",
        "en": "Current version: US stocks only. SPY as default market proxy; falls back to stock-only if unavailable."
    },
    "chart.periodHeatmapLayout": {
        "zh": "周期热图和主图分开承载，便于桌面和移动端独立阅读。",
        "en": "Period heatmap and main chart separated for desktop/mobile readability."
    },
    "data.datasetTime": {
        "zh": "数据集时间",
        "en": "Dataset time"
    },
    "action.submitFeedback": {
        "zh": "📤 提交反馈",
        "en": "Submit Feedback"
    },
    "status.marketSnapshotUnavailable": {
        "zh": "市场快照暂不可用",
        "en": "Market snapshot unavailable"
    },
    "instruction.selectFamilyFirst": {
        "zh": "请先在上方选择 Baseline 或 Search，再展开具体配置。",
        "en": "First select Baseline or Search above, then configure."
    },
    "chip.currentMarket": {
        "zh": "</span>\n  <span class=\"analysis-chart-chip\">当前市场",
        "en": "</span>\n  <span class=\"analysis-chart-chip\">Current market"
    },
    "action.addStockOrUpload": {
        "zh": "➕ 添加股票 / 上传数据",
        "en": "➕ Add stock / Upload data"
    },
    "instruction.selectFamilyForConfig": {
        "zh": "先在左侧选择 Baseline 或 Search 家族，结果板才会进入可配置状态。",
        "en": "Select Baseline or Search family on the left to enable result board configuration."
    },
    "metrics.avgPositionDays": {
        "zh": "均持仓(日)",
        "en": "Avg holding (days)"
    },
    "language.chinese": {
        "zh": "中文",
        "en": "Chinese"
    },
    "count.failed": {
        "zh": "个，失败",
        "en": "failed"
    },
    "draft.currentPath": {
        "zh": "当前草稿路径：",
        "en": "Current draft path:"
    },
    "strategy.generate": {
        "zh": "生成策略",
        "en": "Generate Strategy"
    },
    "chart.priceComparison.insufficientData": {
        "zh": "当前没有足够数据生成价格对比图。",
        "en": "Insufficient data to generate price comparison chart."
    },
    "indicator.adx.threshold": {
        "zh": "ADX 阈值",
        "en": "ADX Threshold"
    },
    "navigation.singleStock.entry": {
        "zh": "单股入口",
        "en": "Single Stock Entry"
    },
    "ui.analysisPage.description": {
        "zh": "主分析页逻辑不变，变化的是入口节奏、视觉层级和网站感。",
        "en": "Main analysis logic unchanged; changes are in entry flow, visual hierarchy, and site feel."
    },
    "recommendation.current": {
        "zh": "当前推荐口径：",
        "en": "Current recommendation:"
    },
    "strategy.volatilityPenalty.weight": {
        "zh": "波动惩罚权重",
        "en": "Volatility Penalty Weight"
    },
    "chart.latestClose.label": {
        "zh": "</span>\n  <span class=\"analysis-chart-chip\">最新收盘",
        "en": "Latest Close"
    },
    "strategy.atr.takeProfitMultiplier": {
        "zh": "ATR 止盈倍数",
        "en": "ATR Take-Profit Multiplier"
    },
    "common.none": {
        "zh": "无",
        "en": "None"
    },
    "backtest.testSet": {
        "zh": "测试集",
        "en": "Test Set"
    },
    "chart.multiStock.basicInfo": {
        "zh": "多股基础信息图表",
        "en": "Multi-Stock Basic Info Chart"
    },
    "research.run.empty": {
        "zh": "当前没有可读取的研究 run。",
        "en": "No research runs available."
    },
    "action.uploadData": {
        "zh": "上传数据",
        "en": "Upload Data"
    },
    "system.routing.buildPath": {
        "zh": "拼接真实路由路径。",
        "en": "Construct actual routing path."
    },
    "portfolio.weight.configuration": {
        "zh": "**组合权重配置**",
        "en": "Portfolio Weight Configuration"
    },
    "analysis.multiStock": {
        "zh": "多股分析",
        "en": "Multi-Stock Analysis"
    },
    "table.detailedComparison": {
        "zh": "详细对比表",
        "en": "Detailed Comparison Table"
    },
    "indicator.macd.slowEma.period": {
        "zh": "MACD 慢线 EMA 周期。",
        "en": "MACD Slow EMA Period"
    },
    "action.browseResearchRuns": {
        "zh": "浏览已有研究 run",
        "en": "Browse Research Runs"
    },
    "chart.monthlyReturnsHeatmap.insufficientData": {
        "zh": "当前主策略的测试集跨度不足以生成月度收益热图。",
        "en": "Test set span is insufficient to generate monthly returns heatmap."
    },
    "backtest.buySellPoints.read": {
        "zh": "| 买卖点读取：",
        "en": "Buy/Sell Points:"
    },
    "page.multiStockComparison.description": {
        "zh": "多股票对比分析页面\n==================\n选中多只股票时展示的完整对比分析界面。",
        "en": "Multi-Stock Comparison Page\n==================\nFull comparative analysis interface when multiple stocks are selected."
    },
    "indicator.atr.calculationPeriod": {
        "zh": "波动率（ATR）计算周期。",
        "en": "ATR Calculation Period"
    },
    "metric.return.percentage": {
        "zh": "收益率(%)",
        "en": "Return (%)"
    },
    "comparison.stockCount": {
        "zh": "对比股票数量",
        "en": "Number of Stocks Compared"
    },
    "data.missingField.fallback": {
        "zh": "字段缺失会回退为 N/A，不会阻断图表和后续策略工作流。",
        "en": "Missing fields fall back to N/A and do not block charts or subsequent workflows."
    },
    "indicator.macd": {
        "zh": "MACD 指标",
        "en": "MACD Indicator"
    },
    "chart.heatmap.period": {
        "zh": "热图周期",
        "en": "Heatmap Period"
    },
    "strategy.entryExit.scoreThreshold": {
        "zh": "**入场/出场评分阈值**",
        "en": "Entry/Exit Score Threshold"
    },
    "mlflow.info.empty": {
        "zh": "当前没有可展示的 MLflow 信息。",
        "en": "No MLflow information to display."
    },
    "todo.list": {
        "zh": "待完成项：",
        "en": "To-Do:"
    },
    "backtest.walkForward.noResults": {
        "zh": "Walk-Forward 回测未产生结果。",
        "en": "Walk-Forward backtest produced no results."
    },
    "indicator.bollingerBands.advancedParams": {
        "zh": "**布林带 / 高级指标参数**",
        "en": "Bollinger Bands / Advanced Indicator Parameters"
    },
    "chart.monthlyK": {
        "zh": "月 K",
        "en": "Monthly K-Line"
    },
    "optimization.trialCount.tip": {
        "zh": "试验次数越多越精确，但耗时更长。建议先用 30 次验证路径。",
        "en": "More trials increase accuracy but take longer. Start with 30 to verify the path."
    },
    "ui.singleStockEntry.description": {
        "zh": "渲染单股入口页，并在用户发起分析时返回动作。",
        "en": "Render single stock entry page and return action when user initiates analysis."
    },
    "strategy.selection.prompt": {
        "zh": "请选择 Naive / Mean / Drift",
        "en": "Select Naive / Mean / Drift"
    },
    "input.stock.example": {
        "zh": "例如：AAPL / NVDA / 贵州茅台 / 600519",
        "en": "e.g., AAPL / NVDA / Kweichow Moutai / 600519"
    },
    "backtest.buyAndHold.return": {
        "zh": "| 买入并持有收益：",
        "en": "Buy & Hold Return:"
    },
    "data.market.loading": {
        "zh": "正在加载最新市场数据。",
        "en": "Loading latest market data."
    },
    "export.page.description": {
        "zh": "导出页把多股基础信息、横向对比和组合策略结果收进统一的站点式报告，避免再回到旧版大卡片堆叠。",
        "en": "Export page consolidates multi-stock info, comparisons, and portfolio results into a unified site-style report, moving away from stacked cards."
    },
    "indicator.trendFilter.longEma": {
        "zh": "趋势过滤的长周期 EMA。",
        "en": "Long-period EMA for trend filtering."
    },
    "chart.portfolioNetValue.missing": {
        "zh": "当前结果缺少可展示的组合净值图。",
        "en": "Current results lack a displayable portfolio net value chart."
    },
    "indicator.volume.amplification": {
        "zh": "量能放大",
        "en": "Volume Amplification"
    },
    "chart.view": {
        "zh": "查看图表",
        "en": "View Chart"
    },
    "strategyList.displayRules": {
        "zh": "当前策略固定置顶；已保存策略按最近保存倒序展示。比较器按底层 artifact 去重，不重复画线。",
        "en": "Current strategy pinned. Saved strategies sorted by recency. Comparators deduplicated by underlying artifact."
    },
    "component.analysisChartChip.displayName": {
        "zh": "</span>\n  <span class=\"analysis-chart-chip\">显示名",
        "en": "Display Name"
    },
    "state.selected": {
        "zh": "✓ 已选择",
        "en": "✓ Selected"
    },
    "dataSource.description": {
        "zh": "页面只消费 report.json 已汇总的结果和可选的 QuantStats / MLflow 元信息。",
        "en": "Page consumes aggregated report.json results and optional QuantStats/MLflow metadata."
    },
    "status.configCompleteNoResult": {
        "zh": "当前请求已完成配置，尚未生成结果。",
        "en": "Configuration complete. Results pending."
    },
    "metric.scoreAndQuantile": {
        "zh": "评分 / 分位",
        "en": "Score / Quantile"
    },
    "time.annual": {
        "zh": "年度",
        "en": "Annual"
    },
    "metric.buyAndHoldReturn": {
        "zh": "买入持有收益",
        "en": "Buy & Hold Return"
    },
    "stockPool.duplicateWarning": {
        "zh": "该股票已经在当前股票池里。",
        "en": "Stock already in pool."
    },
    "data.warning.fixedWindow": {
        "zh": "数据量较少，已固定训练/测试窗口。",
        "en": "Limited data. Fixed train/test window."
    },
    "common.date": {
        "zh": "日期",
        "en": "Date"
    },
    "common.name": {
        "zh": "名称",
        "en": "Name"
    },
    "time.day": {
        "zh": "天",
        "en": "Day(s)"
    },
    "action.organizeStockPool": {
        "zh": "先把股票池整理清楚",
        "en": "Organize stock pool first"
    },
    "upload.csvFormat": {
        "zh": "上传 CSV（列名：open, close, volumn/volume, high, low）",
        "en": "Upload CSV (columns: open, close, volume, high, low)"
    },
    "action.viewOptimalParams": {
        "zh": "查看最优参数",
        "en": "View Optimal Params"
    },
    "action.loadRunReport": {
        "zh": "读取选中 run 的 report 与可选 MLflow manifest。",
        "en": "Load report and optional MLflow manifest for selected run."
    },
    "validation.mlHorizonDays": {
        "zh": "ml_horizon_days 必须为正整数",
        "en": "ml_horizon_days must be a positive integer."
    },
    "strategy.generationRule": {
        "zh": "按最近一个交易日信号与目标仓位生成",
        "en": "Generated using latest trading day signal and target position."
    },
    "optimization.randomSearch": {
        "zh": "随机搜索",
        "en": "Random Search"
    },
    "report.designConsistency": {
        "zh": "主图、小图指标与训练窗口在离线报告里保持同样的阅读重心。",
        "en": "Main/sub charts and training window maintain visual focus in offline report."
    },
    "metric.lowerIsBetter": {
        "zh": "越低越稳",
        "en": "Lower is more stable"
    },
    "metric.optimizedDrawdown": {
        "zh": "优化后回撤",
        "en": "Optimized Drawdown"
    },
    "layout.mobileFriendlyCharts": {
        "zh": "指标小图跟主图分栏展开，便于在移动端单独阅读。",
        "en": "Sub-charts expand in separate columns for mobile viewing."
    },
    "param.atrStopLossMultiplier": {
        "zh": "ATR 止损倍数",
        "en": "ATR Stop Loss Multiplier"
    },
    "strategy.naiveBuyAndHold": {
        "zh": "Naive（买入持有）",
        "en": "Naive (Buy & Hold)"
    },
    "action.compareStrategies": {
        "zh": "策略比对",
        "en": "Compare Strategies"
    },
    "state.unavailable": {
        "zh": "无法获取",
        "en": "Unavailable"
    },
    "ui.recommendationSheet": {
        "zh": "推荐列表放在同一个轻量 sheet 里，点击右侧小按钮即可直接进入分析。",
        "en": "Recommendations in a lightweight sheet. Click button to analyze."
    },
    "section.strategyWorkflow": {
        "zh": "策略流程",
        "en": "Strategy Workflow"
    },
    "state.mlflowNotRecorded": {
        "zh": "未记录 MLflow。",
        "en": "MLflow not recorded."
    },
    "label.quantile": {
        "zh": "/ 分位",
        "en": "/ Quantile"
    },
    "market.instruments": {
        "zh": "个市场标的",
        "en": " market instruments"
    },
    "error.noValidData": {
        "zh": "未获取到有效数据",
        "en": "No valid data retrieved."
    },
    "section.strategyResults": {
        "zh": "策略结果区",
        "en": "Strategy Results"
    },
    "warning.rebuildStrategy": {
        "zh": "检测到股票池、权重或边栏参数变化，请重新生成组合策略。",
        "en": "Stock pool, weights, or sidebar params changed. Please regenerate strategy."
    },
    "param.macdHistogramWeight": {
        "zh": "MACD 柱在评分中的权重。",
        "en": "MACD histogram weight in scoring."
    },
    "report.offlineHtml": {
        "zh": "离线 HTML",
        "en": "Offline HTML"
    },
    "data.marketData": {
        "zh": "市场数据",
        "en": "Market Data"
    },
    "param.rsiUpperThreshold": {
        "zh": "RSI 上限阈值",
        "en": "RSI Upper Threshold"
    },
    "validation.familyParam": {
        "zh": "family 只支持 baseline、search 或 regime",
        "en": "Family only supports 'baseline', 'search', or 'regime'."
    },
    "action.exportAnalysisReport": {
        "zh": "📤 导出分析报告",
        "en": "📤 Export Analysis Report"
    },
    "chart.correlationMatrix": {
        "zh": "股票收益率相关性矩阵（按股票配对计算）",
        "en": "Stock Return Correlation Matrix (by pair)"
    },
    "label.currentUsing": {
        "zh": "当前使用「",
        "en": "Currently using \""
    },
    "scoring.mainAndRobustness": {
        "zh": "主窗口 + 稳健性综合评分",
        "en": "Main Window + Robustness Score"
    },
    "count.instrumentsSource": {
        "zh": "</strong> 个标的\n  （手动/推荐",
        "en": " instruments (Manual/Recommended"
    },
    "section.currentSelectedStocks": {
        "zh": "当前已选股票",
        "en": "Selected Stocks"
    },
    "ui.stockSearchHint": {
        "zh": "输入股票名称或代码后，这里会出现可直接进入分析的候选项。",
        "en": "Enter name or code to see analysis candidates here."
    },
    "priceComparison.title": {
        "zh": "价格对比",
        "en": "Price Comparison"
    },
    "sidebar.module.description": {
        "zh": "侧边栏 UI 模块\n================\n渲染 Streamlit 侧边栏的所有控件，返回完整的参数字典。",
        "en": "Sidebar UI Module\n================\nRenders all Streamlit sidebar controls and returns a complete parameter dictionary."
    },
    "training.label": {
        "zh": "| 训练：",
        "en": "| Training:"
    },
    "performance.medianExcessReturn": {
        "zh": "中位超额收益",
        "en": "Median Excess Return"
    },
    "strategy.configurationHint": {
        "zh": "先在左侧选择 Baseline、Search 或 Regime 家族，结果板才会进入可配置状态。",
        "en": "Select a Baseline, Search, or Regime family on the left to enable configuration of the results panel."
    },
    "data.noMetricsAvailable": {
        "zh": "暂无可展示的指标数据。",
        "en": "No metric data available for display."
    },
    "sentiment.slightlyCold": {
        "zh": "· 偏冷",
        "en": "· Slightly Cold"
    },
    "multiStock.overview": {
        "zh": "多股概览",
        "en": "Multi-Stock Overview"
    },
    "strategy.creationPrompt": {
        "zh": "请先在左侧工作台生成一条策略。",
        "en": "Please generate a strategy first in the left-side workspace."
    },
    "performance.profitLossRatioVsBenchmark": {
        "zh": "盈亏比 / 基准",
        "en": "Profit/Loss Ratio / Benchmark"
    },
    "run.noRobustnessSummary": {
        "zh": "当前 run 没有 robustness 汇总。",
        "en": "No robustness summary available for the current run."
    },
    "analysis.areaSwitch": {
        "zh": "分析区切换",
        "en": "Analysis Area Switch"
    },
    "strategy.pricePositionWeight": {
        "zh": "价格位置权重",
        "en": "Price Position Weight"
    },
    "strategy.takeProfitMultiplier": {
        "zh": "止盈倍数",
        "en": "Take Profit Multiplier"
    },
    "search.stockExample": {
        "zh": "例如：AAPL / Apple / 600519",
        "en": "e.g., AAPL / Apple / 600519"
    },
    "strategy.workflowSteps": {
        "zh": "Step 2 完成模型配置；Step 3 点击“生成策略”提交当前请求。",
        "en": "Step 2: Complete model configuration; Step 3: Click 'Generate Strategy' to submit the request."
    },
    "run.selectionFailed": {
        "zh": "选中的 run 读取失败。",
        "en": "Failed to load the selected run."
    },
    "export.preserveStockOrder": {
        "zh": "导出保留主分析页当前股票池顺序",
        "en": "Export preserves the current stock pool order from the main analysis page."
    },
    "data.source.currentMarketWindow": {
        "zh": "直接来自当前行情窗口",
        "en": "Directly from the current market window."
    },
    "dateRange.label": {
        "zh": "| 日期范围：",
        "en": "| Date Range:"
    },
    "performance.timeProportion": {
        "zh": "时间占比",
        "en": "Time Proportion"
    },
    "landing.pageDescription": {
        "zh": "这个入口页只负责建立研究上下文。左侧完成市场切换、搜索和上传，右侧持续展示当前市场快照与推荐入口。",
        "en": "This landing page establishes the research context. The left side handles market switching, search, and uploads, while the right side continuously displays the current market snapshot and recommended entry points."
    },
    "data.refreshing": {
        "zh": "正在刷新数据...",
        "en": "Refreshing data..."
    },
    "stock.switch": {
        "zh": "切换股票",
        "en": "Switch Stock"
    },
    "stock.pool": {
        "zh": "股票池",
        "en": "Stock Pool"
    },
    "results.detailedView": {
        "zh": "结果细看",
        "en": "Detailed Results"
    },
    "stock.selectionPrompt": {
        "zh": "选择一只股票进行策略分析，或多只股票进行对比分析",
        "en": "Select a single stock for strategy analysis, or multiple stocks for comparative analysis."
    },
    "strategy.participationCount": {
        "zh": "参与策略数",
        "en": "Number of Participating Strategies"
    },
    "performance.annualizedReturnPercent": {
        "zh": "年化收益率（回报）%",
        "en": "Annualized Return %"
    },
    "strategy.generatePortfolio": {
        "zh": "生成组合策略",
        "en": "Generate Portfolio Strategy"
    },
    "search.indexLoadFailed": {
        "zh": "搜索索引加载失败：",
        "en": "Search index load failed:"
    },
    "performance.medianSharpe": {
        "zh": "中位夏普",
        "en": "Median Sharpe Ratio"
    },
    "indicator.macdValidation": {
        "zh": "MACD 快线周期需要小于慢线周期。",
        "en": "MACD fast period must be less than the slow period."
    },
    "training.cutoff": {
        "zh": "训练截止",
        "en": "Training Cutoff"
    },
    "multiStock.sharedFilter": {
        "zh": "多股基础信息与右侧图表共用同一筛选结果",
        "en": "Multi-stock basic info and right-side charts share the same filter results."
    },
    "strategy.firstStrategyPrompt": {
        "zh": "请选择模型路径并生成第一条策略。",
        "en": "Please select a model path and generate your first strategy."
    },
    "performance.maxDrawdown": {
        "zh": "最大回撤：",
        "en": "Max Drawdown:"
    },
    "search.noMatchingStocks": {
        "zh": "没有找到匹配股票。",
        "en": "No matching stocks found."
    },
    "data.multiStockCleaning": {
        "zh": "为多股票页统一清洗日期和价格列，避免静默缺图。",
        "en": "Unify date and price column cleaning for multi-stock pages to prevent silent missing charts."
    },
    "data.range": {
        "zh": "数据区间",
        "en": "Data Range"
    },
    "data.missingFieldFallback": {
        "zh": "字段缺失会回退为 N/A，不会阻断页面其余部分。",
        "en": "Missing fields fall back to N/A and do not block the rest of the page."
    },
    "research.status": {
        "zh": "研究状态",
        "en": "Research Status"
    },
    "signal.bullishTargetPosition": {
        "zh": "当前信号偏多，目标仓位",
        "en": "Current signal is bullish, target position"
    },
    "performance.optimalValue": {
        "zh": "最优值",
        "en": "Optimal Value"
    },
    "model.comparisonDescription": {
        "zh": "横向比较 random / bayesian / genetic 的平均表现与胜出模型。",
        "en": "Horizontally compare the average performance and winning models of random, Bayesian, and genetic approaches."
    },
    "stock.selectionFromSearchPrompt": {
        "zh": "请先从搜索结果中选择股票。",
        "en": "Please select stocks from the search results first."
    },
    "export.multiStockReport": {
        "zh": "多股导出报告",
        "en": "Multi-Stock Export Report"
    },
    "model.count": {
        "zh": "模型数量",
        "en": "Model Count"
    },
    "market.context": {
        "zh": "市场上下文",
        "en": "Market Context"
    },
    "search.count": {
        "zh": "搜索次数",
        "en": "Search Count"
    },
    "regime.cache_hit": {
        "zh": "Regime 阶段命中缓存。",
        "en": "Regime phase cache hit."
    },
    "strategy.running_multi_stock_simulation": {
        "zh": "正在运行多股组合策略模拟...",
        "en": "Running multi-stock portfolio strategy simulation..."
    },
    "chart.volume": {
        "zh": "成交量",
        "en": "Volume"
    },
    "data.upload_custom_csv": {
        "zh": "上传自定义CSV数据文件",
        "en": "Upload custom CSV data file"
    },
    "market.spy_proxy_available": {
        "zh": "SPY 代理可用",
        "en": "SPY proxy available"
    },
    "chart.candlestick_main": {
        "zh": "K 线主图",
        "en": "Candlestick Chart"
    },
    "common.remove": {
        "zh": "移除",
        "en": "Remove"
    },
    "chart.risk_return_scatter_annualized": {
        "zh": "风险-收益散点图（年化）",
        "en": "Risk-Return Scatter Plot (Annualized)"
    },
    "strategy.select_preset": {
        "zh": "选择预设策略",
        "en": "Select preset strategy"
    },
    "strategy.param_search_disabled": {
        "zh": "当前请求未启用参数搜索",
        "en": "Parameter search is disabled for this request."
    },
    "common.of": {
        "zh": "的",
        "en": "of"
    },
    "strategy.result_view": {
        "zh": "策略结果视图",
        "en": "Strategy Result View"
    },
    "backtest.training_window_days": {
        "zh": "训练窗口（交易日）",
        "en": "Training Window (Trading Days)"
    },
    "export.valid_stocks_count": {
        "zh": "当前导出实际包含的有效股票数",
        "en": "Number of valid stocks in current export"
    },
    "date.june": {
        "zh": "6月",
        "en": "June"
    },
    "strategy.library_status": {
        "zh": "策略库规模：当前 1 条，已保存",
        "en": "Strategy library: 1 current, saved"
    },
    "export.analysis_report": {
        "zh": "导出分析报告",
        "en": "Export Analysis Report"
    },
    "search.await_sm_fsm_selection": {
        "zh": "Search -> 等待选择 SM / FSM",
        "en": "Search → Awaiting SM/FSM selection"
    },
    "common.to": {
        "zh": "到",
        "en": "to"
    },
    "stock_pool.add_by_a_share_code": {
        "zh": "未找到索引匹配，将按该 A 股代码加入股票池。",
        "en": "No index match found. Adding to stock pool by A-share code."
    },
    "factor.latest_score_comparison": {
        "zh": "最新因子评分横向对比",
        "en": "Latest Factor Score Comparison"
    },
    "report.generating_html": {
        "zh": "正在生成HTML报告...",
        "en": "Generating HTML report..."
    },
    "market.latest_trading_day": {
        "zh": "最新交易日",
        "en": "Latest Trading Day"
    },
    "factor.score": {
        "zh": "因子评分",
        "en": "Factor Score"
    },
    "chart.multi_strategy_net_drawdown": {
        "zh": "多策略净值 / 回撤",
        "en": "Multi-Strategy NAV / Drawdown"
    },
    "chart.quarterly_return_heatmap": {
        "zh": "季度收益率热图",
        "en": "Quarterly Return Heatmap"
    },
    "backtest.test_period_result": {
        "zh": "测试期结果",
        "en": "Test Period Results"
    },
    "indicator.slightly_hot": {
        "zh": "· 偏热",
        "en": "· Slightly Hot"
    },
    "factor.weight_short_term_momentum": {
        "zh": "短期动量在评分中的权重。",
        "en": "Weight of short-term momentum in scoring."
    },
    "ui.chart_result_area": {
        "zh": "图表结果区",
        "en": "Chart Result Area"
    },
    "common.not_recorded": {
        "zh": "未记录",
        "en": "Not recorded"
    },
    "chart.shared_net_drawdown_component": {
        "zh": "当前主图与单股结果区共用同一套“净值上 / 回撤下”的结果图组件。",
        "en": "The main chart and single-stock result area share the same 'NAV above / Drawdown below' chart component."
    },
    "metric.excess_percent": {
        "zh": "超额 %",
        "en": "Excess %"
    },
    "view.result_mode": {
        "zh": "结果模式",
        "en": "Result Mode"
    },
    "indicator.relative_strength": {
        "zh": "相对强弱",
        "en": "Relative Strength"
    },
    "market.switch_defaults_notice": {
        "zh": "切换后将使用对应市场的默认股票池和数据下载路径。",
        "en": "After switching, the default stock pool and data download path for that market will be used."
    },
    "data.refresh_complete_success": {
        "zh": "✓ 数据刷新完成：成功",
        "en": "✓ Data refresh completed: Success"
    },
    "optimization.generation": {
        "zh": "进化代数",
        "en": "Generation"
    },
    "common.upload_file": {
        "zh": "上传文件",
        "en": "Upload File"
    },
    "indicator.macd_fast_period": {
        "zh": "MACD 快线周期",
        "en": "MACD Fast Period"
    },
    "indicator.macd_slow_period": {
        "zh": "MACD 慢线周期",
        "en": "MACD Slow Period"
    },
    "factor.weight_rsi": {
        "zh": "RSI 在评分中的权重。",
        "en": "Weight of RSI in scoring."
    },
    "indicator.volume_relative": {
        "zh": "量能相对值",
        "en": "Relative Volume"
    },
    "position.mid_level_threshold": {
        "zh": "评分分位数达到该值进入中档仓位。",
        "en": "Enter medium position when score percentile reaches this value."
    },
    "position.high_level_threshold": {
        "zh": "评分分位数达到该值进入高档仓位。",
        "en": "Enter high position when score percentile reaches this value."
    },
    "indicator.macd_compressed": {
        "zh": "MACD（压缩）",
        "en": "MACD (Compressed)"
    },
    "strategy.results_count": {
        "zh": "条策略结果",
        "en": "strategy results"
    },
    "action.add_with_current_input": {
        "zh": "按当前输入加入",
        "en": "Add with current input"
    },
    "model.fsm_fa_enhanced": {
        "zh": "FSM（FA增强）",
        "en": "FSM (FA Enhanced)"
    },
    "score.robustness_total": {
        "zh": "稳健性总分",
        "en": "Robustness Total Score"
    },
    "regime.latest": {
        "zh": "最新 Regime",
        "en": "Latest Regime"
    },
    "performance.risk_adjusted": {
        "zh": "风险调整后表现",
        "en": "Risk-Adjusted Performance"
    },
    "note.main_leaderboard_source": {
        "zh": "主榜单固定读取 report.json 中的汇总结果，不在页面内重扫 artifacts。",
        "en": "Main leaderboard reads aggregated results from report.json; does not rescan artifacts in-page."
    },
    "home.section_header": {
        "zh": "首页模块\n========",
        "en": "Home Module"
    },
    "message.no_results_to_display": {
        "zh": "<div class='model-eval-rank-empty'>暂无可展示结果。</div>",
        "en": "No results to display."
    },
    "metric.profit_loss_ratio": {
        "zh": "盈亏比",
        "en": "Profit/Loss Ratio"
    },
    "phase.train_test": {
        "zh": "训练 / 测试",
        "en": "Train / Test"
    },
    "section.strategy_overview": {
        "zh": "策略概览",
        "en": "Strategy Overview"
    },
    "placeholder.stock_example": {
        "zh": "例如：AAPL / Apple / 贵州茅台 / 600519",
        "en": "e.g., AAPL / Apple / Kweichow Moutai / 600519"
    },
    "param.adx_strength": {
        "zh": "**ADX 强度参数**",
        "en": "ADX Strength Parameter"
    },
    "error.market_snapshot_failed": {
        "zh": "市场快照加载失败：",
        "en": "Market snapshot failed to load:"
    },
    "period.last_30_trading_days": {
        "zh": "最近 30 个交易日",
        "en": "Last 30 Trading Days"
    },
    "metric.win_rate": {
        "zh": "胜率",
        "en": "Win Rate"
    },
    "characteristic.low_volatility": {
        "zh": "波动偏稳",
        "en": "Low Volatility"
    },
    "param.macd": {
        "zh": "**MACD 参数**",
        "en": "MACD Parameter"
    },
    "note.search_workflow": {
        "zh": "Search 路径的固定顺序是：基础策略 -> 可选参数搜索 -> 可选 ML 过滤。",
        "en": "Search path order: Base Strategy -> Optional Param Search -> Optional ML Filter."
    },
    "note.chart_relocation": {
        "zh": "周期收益率热图已移动到策略区，基础信息区只保留图四对应的多股对比图表。",
        "en": "Period return heatmap moved to Strategy section. Base Info keeps multi-stock comparison chart (Fig.4)."
    },
    "param.rsi_weight": {
        "zh": "RSI 权重",
        "en": "RSI Weight"
    },
    "action.enable_walk_forward": {
        "zh": "启用 Walk-Forward",
        "en": "Enable Walk-Forward"
    },
    "section.current_run_summary": {
        "zh": "当前 run 摘要",
        "en": "Current Run Summary"
    },
    "param.obv_weight": {
        "zh": "OBV权重",
        "en": "OBV Weight"
    },
    "prompt.select_mode": {
        "zh": "请选择 Baseline、Search 或 Regime",
        "en": "Select Baseline, Search, or Regime"
    },
    "message.no_comparison_data": {
        "zh": "当前主策略没有可用于比较的价格与信号数据。",
        "en": "No price/signal data available for comparison in current main strategy."
    },
    "label.selected_file": {
        "zh": "<p class='selection-note'>已选择文件：<strong>",
        "en": "Selected file:"
    },
    "note.entry_page_scope": {
        "zh": "<p class=\"plain-helper\">\n  入口页只负责把研究对象和市场背景整理清楚。进入主分析页后，原有策略工作流、artifact 和下游分析继续保持不变。\n</p>",
        "en": "Entry page clarifies research subject & market context. Original workflow, artifacts, and downstream analysis remain unchanged in main analysis."
    },
    "metric.net_value": {
        "zh": "净值（起始=1.0）",
        "en": "Net Value (Start=1.0)"
    },
    "message.no_stocks_to_remove": {
        "zh": "当前没有可移除的股票。",
        "en": "No stocks to remove."
    },
    "metric.buy_hold_sharpe": {
        "zh": "买入持有夏普",
        "en": "Buy & Hold Sharpe"
    },
    "indicator.rsi": {
        "zh": "RSI 指标",
        "en": "RSI Indicator"
    },
    "action.render_site_nav": {
        "zh": "渲染站点级顶部导航。",
        "en": "Render site-level top navigation."
    },
    "price.latest_close": {
        "zh": "最新收盘",
        "en": "Latest Close"
    },
    "placeholder.search_stock": {
        "zh": "搜索股票名称或代码",
        "en": "Search stock name or code"
    },
    "message.no_results_current": {
        "zh": "当前没有可展示结果。",
        "en": "No results available."
    },
    "price.low": {
        "zh": "最低价",
        "en": "Low"
    },
    "section.feature_suggestion": {
        "zh": "💡 功能建议",
        "en": "💡 Feature Suggestion"
    },
    "metric.success_rate": {
        "zh": "成功率",
        "en": "Success Rate"
    },
    "label.scan_directory": {
        "zh": "扫描目录：",
        "en": "Scan directory:"
    },
    "label.current_symbol": {
        "zh": "当前标的：",
        "en": "Current symbol:"
    },
    "metric.win_rate_percent": {
        "zh": "胜率 %",
        "en": "Win Rate %"
    },
    "label.import_id": {
        "zh": "导入标识：",
        "en": "Import ID:"
    },
    "metric.sharpe_ratio": {
        "zh": "夏普比率",
        "en": "Sharpe Ratio"
    },
    "status.downloading": {
        "zh": "正在下载",
        "en": "Downloading"
    },
    "action.upload_local_csv": {
        "zh": "上传本地单股 CSV",
        "en": "Upload Local Single-Stock CSV"
    },
    "metric.period_return": {
        "zh": "区间收益",
        "en": "Period Return"
    },
    "status.will_analyze": {
        "zh": "✓ 将分析",
        "en": "✓ Will analyze"
    },
    "strategy.buy_and_hold": {
        "zh": "买入并持有",
        "en": "Buy and Hold"
    },
    "action.download_html_report": {
        "zh": "⬇️ 下载HTML报告",
        "en": "⬇️ Download HTML Report"
    },
    "action.research_market": {
        "zh": "研究市场",
        "en": "Research Market"
    },
    "param.macd_signal_ema_period": {
        "zh": "MACD 信号线 EMA 周期。",
        "en": "MACD Signal Line EMA Period"
    },
    "note.buy_sell_chart_layer": {
        "zh": "买卖点图保留为独立图层，方便和主结果图区分阅读。",
        "en": "Buy/Sell chart kept as separate layer for clear distinction from main results."
    },
    "runBrowser.defaultDescription": {
        "zh": "默认展示最新可读 run，并允许在不同 run 之间切换浏览。",
        "en": "Displays the latest readable run by default and allows switching between different runs."
    },
    "recommendation.stocks": {
        "zh": "推荐股票",
        "en": "Recommended Stocks"
    },
    "correlation.legend": {
        "zh": "接近 1 代表正相关，接近 -1 代表负相关，接近 0 代表相关性弱。",
        "en": "Close to 1 indicates positive correlation, close to -1 indicates negative correlation, close to 0 indicates weak correlation."
    },
    "stockPool.insufficientWarning": {
        "zh": "当前有效标的不足 2 个，请返回入口页重新组建股票池。",
        "en": "Insufficient valid securities (less than 2). Please return to the entry page to rebuild the stock pool."
    },
    "feedback.emptyWarning": {
        "zh": "请先填写反馈内容",
        "en": "Please enter feedback content first."
    },
    "analysis.riskReturn": {
        "zh": "风险收益分析",
        "en": "Risk-Return Analysis"
    },
    "theme.sharedLayerDescription": {
        "zh": "共享前端主题层\n==============\n为 W6 首页、入口页和路由壳层提供暖米白官网式样式。",
        "en": "Shared Frontend Theme Layer\n==============\nProvides a warm off-white official website style for the W6 homepage, entry page, and routing shell."
    },
    "common.source": {
        "zh": "来源",
        "en": "Source"
    },
    "market.snapshotTitle": {
        "zh": "当前市场的快照与推荐补充",
        "en": "Current Market Snapshot & Recommendations"
    },
    "relativeStrength.legend": {
        "zh": "RS 曲线上升代表相对强势，下降代表相对弱势。",
        "en": "A rising RS curve indicates relative strength; a falling curve indicates relative weakness."
    },
    "common.descriptionLabel": {
        "zh": "**描述**：",
        "en": "**Description:**"
    },
    "stockList.addAction": {
        "zh": "添加到股票列表",
        "en": "Add to Stock List"
    },
    "dataSource.countSuffix": {
        "zh": "个上传数据源</span>\n</div>",
        "en": " uploaded data sources</span>\n</div>"
    },
    "recommendation.currentPricePrefix": {
        "zh": "</div><div class='recommend-row-meta'>现价",
        "en": "</div><div class='recommend-row-meta'>Current Price"
    },
    "summaryTable.description": {
        "zh": "这张表固定承接图四要求的“摘要数字 + 明细表”，不再把所有信息挤进图里。",
        "en": "This table consistently presents the \"summary metrics + details table\" as required by Chart 4, avoiding clutter within the chart itself."
    },
    "metrics.drawdown": {
        "zh": "回撤",
        "en": "Drawdown"
    },
    "benchmark.equalWeight": {
        "zh": "等权基准",
        "en": "Equal-Weight Benchmark"
    },
    "console.layoutDescription": {
        "zh": "顶部先给出股票池摘要和明细表，右侧主图在价格对比、相对强弱、风险收益、最新因子评分和相关性之间切换，不再顺序堆叠成长页面。",
        "en": "Top section shows stock pool summary and details table. The main chart on the right toggles between price comparison, relative strength, risk-return, latest factor scores, and correlation, replacing a long sequential page."
    },
    "backtest.dateRangePicker": {
        "zh": "选择回测数据的起止日期",
        "en": "Select Backtest Start & End Dates"
    },
    "experiment.name": {
        "zh": "实验名",
        "en": "Experiment Name"
    },
    "strategy.workflowGenerating": {
        "zh": "正在生成策略工作流...",
        "en": "Generating strategy workflow..."
    },
    "backtest.testStart": {
        "zh": "测试起点",
        "en": "Test Start"
    },
    "strategy.noSignalData": {
        "zh": "当前策略缺少可展示的信号数据。",
        "en": "Current strategy lacks displayable signal data."
    },
    "common.score": {
        "zh": "分数",
        "en": "Score"
    },
    "report.exportAreaDescription": {
        "zh": "渲染单股票 HTML 报告导出区域。",
        "en": "Renders the single-stock HTML report export area."
    },
    "analysis.riskReturnSharpeDescription": {
        "zh": "在一个平面里同时看回报、风险和夏普，便于快速识别结构差异。",
        "en": "View return, risk, and Sharpe ratio together on one plane for quick identification of structural differences."
    },
    "feedback.otherTitle": {
        "zh": "📝 其他反馈",
        "en": "📝 Other Feedback"
    },
    "score.percentile": {
        "zh": "评分分位数%",
        "en": "Score Percentile %"
    },
    "stockPool.addAction": {
        "zh": "加入股票池",
        "en": "Add to Stock Pool"
    },
    "strategy.comparisonModeHtml": {
        "zh": "<div class=\"analysis-subsurface\">\n  <h4 class=\"analysis-callout-title\">策略比对模式</h4>\n  <p class=\"analysis-callout-copy\">左侧保留策略库选择器，右侧只切换结果内容。当前最佳候选：",
        "en": "<div class=\"analysis-subsurface\">\n  <h4 class=\"analysis-callout-title\">Strategy Comparison Mode</h4>\n  <p class=\"analysis-callout-copy\">Left panel retains strategy library selector; right panel toggles result content. Current best candidate:"
    },
    "metrics.annualizedReturn": {
        "zh": "年化收益率",
        "en": "Annualized Return"
    },
    "regime.latestLabel": {
        "zh": "最新 Regime：",
        "en": "Latest Regime:"
    },
    "stock.cycle": {
        "zh": "股票周期",
        "en": "Stock Cycle"
    },
    "report.generateDownloadAction": {
        "zh": "生成并下载HTML报告",
        "en": "Generate & Download HTML Report"
    },
    "theme.injectGlobalStyles": {
        "zh": "注入全局共享样式。",
        "en": "Inject global shared styles."
    },
    "date.commonTradingDays": {
        "zh": "共同交易日",
        "en": "Common Trading Days"
    },
    "console.multiStockTitle": {
        "zh": "多股组合控制台",
        "en": "Multi-Stock Portfolio Console"
    },
    "metrics.benchmarkSharpe": {
        "zh": "基准夏普",
        "en": "Benchmark Sharpe"
    },
    "report.exportPageDescription": {
        "zh": "导出页沿用主站点的暖白产品页语法，把单股基础信息、策略摘要和关键图表收进同一份可离线阅读的报告。",
        "en": "The export page follows the main site's warm-white product page style, compiling single-stock basics, strategy summary, and key charts into one offline-readable report."
    },
    "strategy.paramSearchFallback": {
        "zh": "参数搜索失败，已回退到基础策略：",
        "en": "Parameter search failed, fell back to base strategy:"
    },
    "data.loadingComparison": {
        "zh": "加载对比股票数据...",
        "en": "Loading comparison stock data..."
    },
    "dateTime.formatLong": {
        "zh": "%Y年%m月%d日 %H:%M:%S",
        "en": "%Y-%m-%d %H:%M:%S"
    },
    "stockPool.countSuffix": {
        "zh": "个标的",
        "en": " securities"
    },
    "experiment.countSuffix": {
        "zh": "次试验）...",
        "en": " trials)..."
    },
    "path.public": {
        "zh": "公开路径",
        "en": "Public Path"
    },
    "data.loadingFailed": {
        "zh": "没有加载到数据。",
        "en": "No data loaded."
    },
    "strategy.insufficientSignalData": {
        "zh": "当前没有足够的信号数据。",
        "en": "Currently insufficient signal data."
    },
    "common.selectTimeRange": {
        "zh": "选择时间区间",
        "en": "Select Time Range"
    },
    "strategy.comparisonRule": {
        "zh": "当前策略默认参与；已保存策略按需勾选加入多策略比较。",
        "en": "Current strategy participates by default; saved strategies are optionally checked for multi-strategy comparison."
    },
    "strategy.contextStatus": {
        "zh": "当前上下文中存在最新策略和已保存快照。",
        "en": "Latest strategy and saved snapshots exist in the current context."
    },
    "statistics.dateRange.current": {
        "zh": "按当前日期范围统计",
        "en": "Statistics by Current Date Range"
    },
    "validation.selectBaselineOrSearch": {
        "zh": "请先选择 Baseline 或 Search",
        "en": "Please select Baseline or Search first"
    },
    "data.source.latestTargetPosition": {
        "zh": "来自最新一行 target_position",
        "en": "From latest target_position row"
    },
    "quantstats.tearSheet.notGenerated": {
        "zh": "当前 run 未生成 QuantStats tear sheet。",
        "en": "QuantStats tear sheet not generated for this run."
    },
    "mlflow.recorded": {
        "zh": "已记录 MLflow",
        "en": "Logged to MLflow"
    },
    "analysis.startWithUploadedData": {
        "zh": "用上传数据开始分析",
        "en": "Start analysis with uploaded data"
    },
    "index.mismatch.addDirectly": {
        "zh": "没有找到索引匹配，将按当前输入直接加入。",
        "en": "No index match found. Adding input directly."
    },
    "validation.minimumTwoValidInstruments": {
        "zh": "至少需要 2 个有效标的；如股票池、权重或边栏参数变化，结果区会要求重新生成。",
        "en": "At least 2 valid instruments required. Changes to pool, weights, or sidebar parameters will trigger regeneration."
    },
    "summary.coreMetricsTable.description": {
        "zh": "这里固定承接第七周结果区的核心指标摘要，用表格把当前导出的模型收益、回撤、夏普和胜率集中展示。",
        "en": "Displays core metrics summary: model returns, drawdown, Sharpe ratio, and win rate in a table."
    },
    "ml.cache.hit": {
        "zh": "ML 阶段命中缓存。",
        "en": "ML stage cache hit."
    },
    "data.kline.notAvailable": {
        "zh": "暂无可展示的 K 线数据。",
        "en": "No K-line data available."
    },
    "data.stocks.invalid": {
        "zh": "没有加载到有效的股票数据。",
        "en": "No valid stock data loaded."
    },
    "feedback.githubIssues": {
        "zh": "反馈将通过 [GitHub Issues](https://github.com/rikka314/stratagy/issues) 追踪",
        "en": "Feedback tracked via [GitHub Issues](https://github.com/rikka314/stratagy/issues)"
    },
    "scoring.drawdownPenalty": {
        "zh": "回撤越大，评分惩罚越大。",
        "en": "Larger drawdown incurs greater score penalty."
    },
    "results.notAvailable": {
        "zh": "暂无可展示结果。",
        "en": "No results available."
    },
    "strategy.stopLossMultiplier": {
        "zh": "止损倍数",
        "en": "Stop Loss Multiplier"
    },
    "io.read.failed": {
        "zh": "读取失败：",
        "en": "Read failed:"
    },
    "indicators.bearishMomentum": {
        "zh": "空头动能",
        "en": "Bearish Momentum"
    },
    "workflow.currentPipeline": {
        "zh": "当前工作流链路",
        "en": "Current Workflow Pipeline"
    },
    "strategy.primary": {
        "zh": "主策略：",
        "en": "Primary Strategy:"
    },
    "display.current": {
        "zh": "当前展示",
        "en": "Currently Displaying"
    },
    "chart.switch": {
        "zh": "图表切换",
        "en": "Chart Switch"
    },
    "chart.indicatorsMini": {
        "zh": "指标小图",
        "en": "Indicator Mini-Chart"
    },
    "indicators.fastLineBelow": {
        "zh": "快线在下",
        "en": "Fast Line Below"
    },
    "instruments.noneAvailable": {
        "zh": "当前没有可展示标的",
        "en": "No instruments available for display."
    },
    "navigation.workbenchEntry": {
        "zh": "工作台入口",
        "en": "Workbench Entry"
    },
    "page.entry.description": {
        "zh": "入口页只负责把研究对象和市场背景整理清楚。进入主分析页后，原有策略工作流、artifact 和下游分析继续保持不变。",
        "en": "Entry page organizes research subjects and market context. Existing workflows, artifacts, and downstream analysis remain unchanged on the main page."
    },
    "analysis.returnContribution": {
        "zh": "收益贡献",
        "en": "Return Contribution"
    },
    "cache.hit": {
        "zh": "命中缓存。",
        "en": "Cache hit."
    },
    "instrument.type.stock": {
        "zh": "股票",
        "en": "Stocks"
    },
    "research.disableMarketProxy": {
        "zh": "研究禁用市场代理",
        "en": "Disable Market Proxy for Research"
    },
    "model.family.scoreOverview": {
        "zh": "按 baseline / sm / fsm 族查看平均得分与最佳模型。",
        "en": "View average scores and best models by baseline / sm / fsm families."
    },
    "returns.cumulative": {
        "zh": "累计收益",
        "en": "Cumulative Return"
    },
    "strategy.entryRules": {
        "zh": "📈 入场规则",
        "en": "Entry Rules"
    },
    "ml.filter.enabled": {
        "zh": "已启用 ML 过滤：ML 始终消费最近一步成功的上游结果。",
        "en": "ML filter enabled: ML consumes the latest successful upstream result."
    },
    "chart.riskReturn.description": {
        "zh": "在一个平面里同时看年化收益、波动率和夏普，适合快速识别风险收益结构。",
        "en": "View annualized return, volatility, and Sharpe ratio together for quick risk-return assessment."
    },
    "count.unit": {
        "zh": "个）。\n</p>",
        "en": ")."
    },
    "display.cachedResultsNotice": {
        "zh": "当前展示的是上次成功生成的结果；重新生成后才会更新下游分析。",
        "en": "Displaying last successful result. Downstream analysis updates after regeneration."
    },
    "strategy.balanced.default": {
        "zh": "均衡策略（默认）",
        "en": "Balanced Strategy (Default)"
    },
    "page.entry.stockPoolDescription": {
        "zh": "<p class=\"plain-helper\">\n  入口页只负责把股票池整理清楚。进入主分析页后，现有多股图表、组合模拟和后续分析逻辑继续沿用。\n</p>",
        "en": "Entry page organizes the stock pool. Existing multi-stock charts, portfolio simulation, and analysis logic remain on the main page."
    },
    "upload.sources.count": {
        "zh": "个上传源，",
        "en": "upload sources,"
    },
    "rules.exit.conditions.description": {
        "zh": "需要同时满足的出场条件数量。数值越大出场越宽松（不容易被踢出），1=原始逻辑（任一触发就出场），4=全部满足才出场",
        "en": "Number of exit conditions required. Higher value = looser exit (harder to trigger). 1 = original logic (any condition), 4 = all conditions."
    },
    "status.notGenerated": {
        "zh": "未生成",
        "en": "Not Generated"
    },
    "workflow.stage": {
        "zh": "· 阶段",
        "en": "· Stage"
    },
    "analysis.singleInstrument": {
        "zh": "单股分析",
        "en": "Single Instrument Analysis"
    },
    "parameter.search": {
        "zh": "参数搜索：",
        "en": "Parameter Search:"
    },
    "suggestions.current": {
        "zh": "当前建议",
        "en": "Current Suggestions"
    },
    "strategy.count.currentAndSaved": {
        "zh": "当前策略 1 条 + 已保存",
        "en": "1 current strategy + saved"
    },
    "returns.cumulativeRate": {
        "zh": "累计收益率",
        "en": "Cumulative Return Rate"
    },
    "indicators.adx.threshold": {
        "zh": "ADX阈值",
        "en": "ADX Threshold"
    },
    "analysis.fallback.noIndexMatch": {
        "zh": "未找到索引匹配，将按该 A 股代码直接尝试分析。",
        "en": "No index match found. Will attempt direct analysis using this A-share code."
    },
    "page.description.readOnlyOutputs": {
        "zh": "这个页面只读取本地 <code>model-test/outputs</code> 下的现有研究产物，不触发任何研究执行。",
        "en": "This page only reads existing research artifacts from the local <code>model-test/outputs</code> directory and does not trigger any new research execution."
    },
    "site.description.routingStrategy": {
        "zh": "单股研究与多股比较的路由式策略站点。",
        "en": "A routing-based strategy site for single-stock research and multi-stock comparison."
    },
    "strategy.legacyRegime.description": {
        "zh": "Legacy Regime 路径会固定执行双状态路由：股票状态 + 市场代理状态 -> trend / range / risk-off。",
        "en": "The Legacy Regime path enforces a dual-state routing: stock state + market proxy state -> trend / range / risk-off."
    },
    "ui.label.onlyParenthesis": {
        "zh": "只）",
        "en": "Only)"
    },
    "stock.selection.insufficientForMulti": {
        "zh": "当前还没有已选股票。至少准备 2 个标的后再进入多股分析。",
        "en": "No stocks selected yet. Prepare at least 2 tickers before entering multi-stock analysis."
    },
    "paramSearch.insufficientSamples": {
        "zh": "参数搜索至少需要 50 个训练样本；当前训练样本不足，已禁用“生成策略”。",
        "en": "Parameter search requires at least 50 training samples. Insufficient samples, 'Generate Strategy' disabled."
    },
    "model.selection.prompt": {
        "zh": "请先选择 ML 模型",
        "en": "Please select an ML model first."
    },
    "layout.description.consoleAndBoard": {
        "zh": "左侧固定为模型控制台，右侧固定为结果展示板。W5 已冻结的 request、lineage、artifact、回测和导出链路继续复用，本轮只重构交互壳层与结果组织方式。",
        "en": "Left side is fixed as the model console, right side as the results board. Frozen W5 request, lineage, artifact, backtest, and export pipelines are reused. This iteration only refactors the interaction layer and results organization."
    },
    "data.columnName.standard": {
        "zh": "列名需兼容 date/open/high/low/close/volume 标准。",
        "en": "Column names must be compatible with the standard: date/open/high/low/close/volume."
    },
    "export.summary.requirements": {
        "zh": "左侧保持文字型信息载体，先回答当前导出里到底包含什么模型、什么时间窗口和什么主要结论。",
        "en": "The left side maintains a text-based information carrier, first answering what models, time windows, and key conclusions are contained in the current export."
    },
    "action.startComboSearch": {
        "zh": "开始组合搜索",
        "en": "Start Combo Search"
    },
    "status.currentBest": {
        "zh": "当前最佳",
        "en": "Current Best"
    },
    "section.title.comboParamSearch": {
        "zh": "**组合参数搜索**",
        "en": "**Combo Parameter Search**"
    },
    "param.bollingerWeight": {
        "zh": "布林带权重",
        "en": "Bollinger Weight"
    },
    "metric.mlQuality": {
        "zh": "ML 质量",
        "en": "ML Quality"
    },
    "strategy.generation.includes": {
        "zh": "若已生成则附带 KPI 与个股贡献表",
        "en": "If generated, includes KPIs and individual stock contribution table."
    },
    "section.title.netValueAndDrawdown": {
        "zh": "##### 净值与回撤",
        "en": "##### Net Value & Drawdown"
    },
    "layout.mainChartArea.function": {
        "zh": "右侧主图区固定承接价格对比、相对强弱、风险收益、因子评分和相关性，不再堆成长页面。",
        "en": "The right main chart area is fixed for price comparison, relative strength, risk/return, factor scores, and correlation, avoiding a long scrolling page."
    },
    "table.note.percentageFormat": {
        "zh": "表中累计/年化/回撤/胜率/换手/超额等为 ×100 后的百分比数值；夏普与盈亏比为原始比率，未缩放。",
        "en": "Values for Cum Return/Annualized/Drawdown/Win Rate/Turnover/Alpha etc. in the table are percentages (×100). Sharpe and Profit/Loss Ratio are raw ratios, not scaled."
    },
    "field.modelId": {
        "zh": "模型ID",
        "en": "Model ID"
    },
    "paramSearch.noValidResults": {
        "zh": "参数搜索未返回有效结果",
        "en": "Parameter search returned no valid results."
    },
    "page.title.multiStockAnalysis": {
        "zh": "多股主分析页",
        "en": "Multi-Stock Analysis"
    },
    "action.generateArtifact.note": {
        "zh": "点击下方按钮后，系统会按当前请求生成新的 current_artifact。",
        "en": "Clicking the button below will generate a new current_artifact based on the current request."
    },
    "time.range": {
        "zh": "时间范围",
        "en": "Time Range"
    },
    "metric.robustnessScore": {
        "zh": "稳健性分",
        "en": "Robustness Score"
    },
    "param.emaFastPeriod": {
        "zh": "EMA 快线周期",
        "en": "EMA Fast Period"
    },
    "metric.mainWindowScore": {
        "zh": "主窗口分",
        "en": "Main Window Score"
    },
    "strategy.generation.failed": {
        "zh": "策略生成失败。",
        "en": "Strategy generation failed."
    },
    "param.minEntrySignals": {
        "zh": "入场最少信号数",
        "en": "Minimum Entry Signals"
    },
    "action.buildIndicatorMiniChart": {
        "zh": "构建指标小图。",
        "en": "Build indicator mini-charts."
    },
    "page.description.consumesReportOnly": {
        "zh": "<p class='surface-copy'>页面只消费 report.json 已汇总的结果和可选的 QuantStats / MLflow 元信息。</p>",
        "en": "<p class='surface-copy'>This page only consumes results aggregated in report.json and optional QuantStats / MLflow metadata.</p>"
    },
    "field.price": {
        "zh": "价格",
        "en": "Price"
    },
    "run.scan.description": {
        "zh": "扫描可读 run，忽略内部目录、无报告目录和读取失败目录。",
        "en": "Scan for readable runs, ignoring internal directories, directories without reports, and directories that fail to read."
    },
    "stock.pool.addInstruction": {
        "zh": "输入名称或代码后，可把新标的直接加入当前股票池。",
        "en": "After entering a name or code, you can directly add the new ticker to the current stock pool."
    },
    "site.workflow.description": {
        "zh": "这个站点先用市场上下文和清楚的入口动作建立研究方向，再把你送进原有单股或多股分析链路。",
        "en": "This site first establishes a research direction using market context and clear entry actions, then directs you into the existing single or multi-stock analysis pipeline."
    },
    "strategy.postGeneration.viewScores": {
        "zh": "生成策略后可查看评分走势。",
        "en": "After generating a strategy, you can view its score trend."
    },
    "paramSearch.cacheHit": {
        "zh": "参数搜索阶段命中缓存。",
        "en": "Cache hit during parameter search phase."
    },
    "section.title.coreMetrics": {
        "zh": "##### 核心指标",
        "en": "##### Core Metrics"
    },
    "ui.recommendationArea.spec": {
        "zh": "推荐区域保持为单个白色 sheet，内部是轻量行列表和小型加入按钮。",
        "en": "The recommendation area remains a single white sheet, containing a lightweight row list and small add buttons."
    },
    "metric.averageTotalScore": {
        "zh": "平均总分",
        "en": "Average Total Score"
    },
    "recommendation.unavailable": {
        "zh": "暂时无法获取推荐股票。",
        "en": "Stock recommendations are temporarily unavailable."
    },
    "field.rank": {
        "zh": "排名",
        "en": "Rank"
    },
    "ui.label.currentPath": {
        "zh": "当前路径：",
        "en": "Current Path:"
    },
    "metric.longMomentum": {
        "zh": "多头动能",
        "en": "Long Momentum"
    },
    "section.title.marketSnapshot": {
        "zh": "市场快照",
        "en": "Market Snapshot"
    },
    "analysis.selection.currentlyPreparing": {
        "zh": "<p class='selection-note'>当前准备分析：<strong>",
        "en": "<p class='selection-note'>Preparing to analyze: <strong>"
    },
    "mlflow.metadata.displayOnly": {
        "zh": "页面只显示 mlflow_run.json 元数据，不尝试启动或嵌入 MLflow UI。",
        "en": "This page only displays metadata from mlflow_run.json and does not attempt to launch or embed the MLflow UI."
    },
    "baseline.selection_prompt": {
        "zh": "Baseline -> 等待选择 Naive / Mean / Drift",
        "en": "Baseline → Select Naive / Mean / Drift"
    },
    "comparison.detail_view": {
        "zh": "比对细看",
        "en": "Compare Details"
    },
    "bollinger.period": {
        "zh": "布林带周期",
        "en": "Bollinger Band Period"
    },
    "model.sm_basic": {
        "zh": "SM基础",
        "en": "SM Basic"
    },
    "bollinger.weight_in_scoring": {
        "zh": "布林带位置在评分中的权重。",
        "en": "Weight of Bollinger Band position in scoring."
    },
    "error.unknown_baseline_kind": {
        "zh": "未知 baseline_kind:",
        "en": "Unknown baseline_kind:"
    },
    "data.split_chronological": {
        "zh": "按时间顺序切分训练/测试集。",
        "en": "Split train/test sets chronologically."
    },
    "analysis.trade_point_comparison": {
        "zh": "买卖点比较",
        "en": "Trade Point Comparison"
    },
    "console.model": {
        "zh": "模型控制台",
        "en": "Model Console"
    },
    "market.selection": {
        "zh": "市场选择",
        "en": "Market Selection"
    },
    "validation.momentum_window_order": {
        "zh": "短期动量窗口需要小于中期动量窗口。",
        "en": "Short-term momentum window must be smaller than medium-term."
    },
    "menu.feedback": {
        "zh": "💬 反馈与建议",
        "en": "💬 Feedback & Suggestions"
    },
    "results.rolling_robustness_summary": {
        "zh": "若 run 启用了 rolling robustness，这里显示稳健性汇总；否则只展示空态。",
        "en": "Shows robustness summary if rolling robustness is enabled; otherwise empty."
    },
    "error.candidate_search_failed": {
        "zh": "候选搜索失败：",
        "en": "Candidate search failed:"
    },
    "adx.trend_threshold": {
        "zh": "ADX 高于该值才认为趋势有效。",
        "en": "Trend is valid only when ADX is above this value."
    },
    "report.generate_download_html": {
        "zh": "生成并下载 HTML 报告",
        "en": "Generate & Download HTML Report"
    },
    "data.full": {
        "zh": "完整数据",
        "en": "Full Data"
    },
    "portfolio.involved_symbols": {
        "zh": "参与标的",
        "en": "Involved Symbols"
    },
    "note.train_ratio_change_impact": {
        "zh": "修改训练比例后，训练/测试边界、workspace 上下文和右侧结果板会一起刷新。",
        "en": "Changing train ratio refreshes train/test boundary, workspace context, and results panel."
    },
    "error.empty_test_set": {
        "zh": "测试集为空，无法生成策略阶段结果",
        "en": "Test set is empty; cannot generate strategy phase results."
    },
    "report.include_generation_date": {
        "zh": "包含生成日期",
        "en": "Include generation date"
    },
    "sentiment.neutral_weak": {
        "zh": "中性偏弱",
        "en": "Neutral-Weak"
    },
    "data.main_price_curve_reading": {
        "zh": "主价格曲线读取",
        "en": "Main Price Curve Reading"
    },
    "warning.generate_strategy_before_export": {
        "zh": "请先生成策略后再导出 HTML 报告。",
        "en": "Please generate a strategy before exporting HTML report."
    },
    "results.portfolio_section": {
        "zh": "组合结果区",
        "en": "Portfolio Results"
    },
    "factor.exit_threshold": {
        "zh": "因子评分低于该值视为出场信号之一。",
        "en": "Factor score below this is considered an exit signal."
    },
    "visualization.annual_return_heatmap": {
        "zh": "年度收益率热图",
        "en": "Annual Return Heatmap"
    },
    "volatility.relatively_high": {
        "zh": "波动偏高",
        "en": "Volatility Relatively High"
    },
    "indicator.fast_above": {
        "zh": "快线在上",
        "en": "Fast Line Above"
    },
    "metrics.benchmark_annualized_pct": {
        "zh": "基准年化 %",
        "en": "Benchmark Annualized %"
    },
    "metrics.max_drawdown": {
        "zh": "最大回撤",
        "en": "Max Drawdown"
    },
    "visualization.latest_factor_score_comparison": {
        "zh": "最新因子评分对比图",
        "en": "Latest Factor Score Comparison"
    },
    "note.routing_structure": {
        "zh": "当前站点已经具备单股与多股两条真实路由，入口和主分析页顺序一致。",
        "en": "Site now has separate routes for single/multi-stock, with consistent entry and analysis page order."
    },
    "data.trade_point_reading": {
        "zh": "买卖点读取",
        "en": "Trade Point Reading"
    },
    "error.no_data_in_selected_range": {
        "zh": "所选时间区间内没有数据。",
        "en": "No data in selected time range."
    },
    "metrics.buy_hold_drawdown": {
        "zh": "买入持有回撤",
        "en": "Buy & Hold Drawdown"
    },
    "common.phase": {
        "zh": "阶段",
        "en": "Phase"
    },
    "info.no_individual_strategy_performance": {
        "zh": "当前没有可展示的个股独立策略表现。",
        "en": "No individual strategy performance to display."
    },
    "optimization.parameter_search_method": {
        "zh": "参数搜索方法",
        "en": "Parameter Search Method"
    },
    "error.no_matching_stock": {
        "zh": "未找到匹配的股票，请尝试更完整的名称或直接输入代码。",
        "en": "No matching stock found. Try a more complete name or enter the code directly."
    },
    "validation.select_baseline_type": {
        "zh": "请选择 Naive / Mean / Drift 之一。",
        "en": "Please select one of Naive / Mean / Drift."
    },
    "strategy.unified_start_comparison": {
        "zh": "把所有股票起点统一到同一基准，先判断谁在当前观察区间内跑得更快。",
        "en": "Align all stocks to the same starting point to compare performance within the observation period."
    },
    "workflow.select_model_first": {
        "zh": "请先选择 SM 或 FSM，再决定是否追加参数搜索与 ML 过滤。",
        "en": "Select SM or FSM first, then decide on adding parameter search and ML filtering."
    },
    "analysis.identify_homogeneity": {
        "zh": "帮助识别股票池是否过于同质化。",
        "en": "Helps identify if the stock pool is too homogeneous."
    },
    "bollinger.std_dev_multiplier": {
        "zh": "布林带标准差倍数",
        "en": "Bollinger Band Std Dev Multiplier"
    },
    "error.window_exceeds_data_length": {
        "zh": "训练窗口 + 测试窗口超过数据长度，请调小窗口。",
        "en": "Train + test window exceeds data length. Please reduce window sizes."
    },
    "step2.search_base_model": {
        "zh": "Step 2 · Search 基础模型",
        "en": "Step 2 · Search Base Model"
    },
    "search.instructions": {
        "zh": "支持名称或代码检索。命中索引后加入股票池；没有索引时也支持按代码直接加入。",
        "en": "Search by name or ticker. Add to pool on match, or directly by ticker if no match."
    },
    "button.analyze": {
        "zh": "分析",
        "en": "Analyze"
    },
    "nav.strategy_portfolio": {
        "zh": "策略组合",
        "en": "Strategy Portfolio"
    },
    "error.data_fetch_failed": {
        "zh": "的数据，请检查网络连接。",
        "en": "data failed to load. Check network."
    },
    "status.volatility_moderate": {
        "zh": "波动适中",
        "en": "Moderate Volatility"
    },
    "onboarding.market_overview_flow": {
        "zh": "先看大盘快照，再往下进入推荐股票和分析入口。",
        "en": "Start with market snapshot, then proceed to recommended stocks and analysis."
    },
    "validation.rsi_range": {
        "zh": "RSI 下限需要小于上限。",
        "en": "RSI lower bound must be less than upper bound."
    },
    "market.us_stocks": {
        "zh": "美股",
        "en": "US Stocks"
    },
    "info.no_trading_signals": {
        "zh": "当前主策略没有可用的买卖点数据。",
        "en": "No trading signals available for the current strategy."
    },
    "mode.selection.description": {
        "zh": "单股模式适合围绕一个标的持续展开， 多股模式适合先组织股票池再看横向比较、组合结果和后续策略摘要。",
        "en": "Single-stock mode focuses on one asset. Multi-stock mode builds a pool for comparison, portfolio results, and strategy summaries."
    },
    "instruction.select_strategy_first": {
        "zh": "请先选定一个主策略，再查看买卖点。",
        "en": "Select a primary strategy first to view trading signals."
    },
    "backtest.method.rolling_window": {
        "zh": "每次用训练窗口后接测试窗口滚动回测。",
        "en": "Rolling backtest with train window followed by test window."
    },
    "model.not_ready": {
        "zh": "模型还没准备好。先在左侧确认权重，再点击“生成组合策略”。",
        "en": "Model not ready. Confirm weights on the left, then click 'Generate Portfolio Strategy'."
    },
    "section.strategies_for_comparison": {
        "zh": "参与下游比较的策略",
        "en": "Strategies for Downstream Comparison"
    },
    "dataset.trading_signals": {
        "zh": "买卖点查看数据集",
        "en": "Trading Signals Dataset"
    },
    "status.leaning_neutral": {
        "zh": "当前更接近观望状态，执行分支",
        "en": "Leaning neutral, executing branch"
    },
    "chart.weekly_k": {
        "zh": "周 K",
        "en": "Weekly K"
    },
    "weight.short_term_momentum": {
        "zh": "短期动量权重",
        "en": "Short-term Momentum Weight"
    },
    "weight.volume": {
        "zh": "成交量权重",
        "en": "Volume Weight"
    },
    "weight.bollinger_position": {
        "zh": "布林带位置权重",
        "en": "Bollinger Band Position Weight"
    },
    "error.ml_fallback": {
        "zh": "ML 失败，已保留最近一步成功结果：",
        "en": "ML failed, kept last successful result:"
    },
    "info.missing_field_fallback": {
        "zh": "缺失字段会回退为 N/A，不会阻断图表和后续策略工作流。",
        "en": "Missing fields fall back to N/A without blocking charts or strategy workflow."
    },
    "source.search_or_recommendation": {
        "zh": "来源：搜索或推荐加入",
        "en": "Source: Search or Recommendation"
    },
    "action.switch_by_input": {
        "zh": "按当前输入切换",
        "en": "Switch by Current Input"
    },
    "router.adaptive_v1_recommended": {
        "zh": "Adaptive Router V1（推荐）",
        "en": "Adaptive Router V1 (Recommended)"
    },
    "status.volume_stable": {
        "zh": "量能平稳",
        "en": "Volume Stable"
    },
    "signal.bearish_target": {
        "zh": "最新信号偏空，目标仓位",
        "en": "Latest signal bearish, target position"
    },
    "section.parameter_search": {
        "zh": "参数搜索",
        "en": "Parameter Search"
    },
    "button.explanation": {
        "zh": "说明",
        "en": "Info"
    },
    "count.upload": {
        "zh": "个，上传",
        "en": "items, upload"
    },
    "metric.portfolio_max_drawdown": {
        "zh": "组合最大回撤",
        "en": "Portfolio Max Drawdown"
    },
    "status.already_in_database": {
        "zh": "已在数据库中",
        "en": "Already in Database"
    },
    "description.baseline_equal_weight": {
        "zh": "默认相对基准使用等权平均，观察每只股票是持续跑赢还是跑输股票池。",
        "en": "Uses equal-weighted average as baseline to track if stocks consistently outperform or underperform the pool."
    },
    "section.model_evaluation": {
        "zh": "模型评估",
        "en": "Model Evaluation"
    },
    "label.short_term_return_window": {
        "zh": "短期收益率窗口。",
        "en": "Short-term Return Window"
    },
    "label.row_count": {
        "zh": "行数：",
        "en": "Rows:"
    },
    "router.adaptive_v1_fallback": {
        "zh": "Adaptive Router V1 会优先读取最近一次离线 `regime_artifacts/`；缺失时自动降级到 legacy dual-state router。",
        "en": "Adaptive Router V1 prioritizes latest offline `regime_artifacts/`; falls back to legacy dual-state router if missing."
    },
    "metric.turnover_percent": {
        "zh": "换手 %",
        "en": "Turnover %"
    },
    "section.run_metadata": {
        "zh": "<h4 class='analysis-section-title'>Run 元信息</h4>",
        "en": "<h4 class='analysis-section-title'>Run Metadata</h4>"
    },
    "strategy.trend_following_conservative": {
        "zh": "趋势跟随（保守）",
        "en": "Trend Following (Conservative)"
    },
    "section.current_market": {
        "zh": "当前市场",
        "en": "Current Market"
    },
    "chart.label.test_rows": {
        "zh": "行</span>\n  <span class=\"analysis-chart-chip\">测试",
        "en": "rows</span>\n  <span class=\"analysis-chart-chip\">Test"
    },
    "chart.baseline_rs_1": {
        "zh": "基准线 (RS=1.0)",
        "en": "Baseline (RS=1.0)"
    },
    "status.nothing_to_display": {
        "zh": "当前没有可展示的",
        "en": "Nothing to display"
    },
    "footer.in_app_feedback": {
        "zh": "---\n*通过应用内反馈提交*",
        "en": "---\n*Submit via in-app feedback*"
    },
    "action.search_and_add_stocks": {
        "zh": "搜索并加入股票",
        "en": "Search & Add Stocks"
    },
    "ui.context_display_area": {
        "zh": "右侧保持一个大的上下文展示区，帮助你从搜索之外补充新的比较对象。",
        "en": "Right panel maintains a large context area to add comparison targets beyond search."
    },
    "description.trend_filter_ema": {
        "zh": "趋势过滤的短周期 EMA。",
        "en": "Short-period EMA for trend filtering."
    },
    "param.optimization_trials": {
        "zh": "优化试验次数",
        "en": "Optimization Trials"
    },
    "training.insufficient_samples_fallback": {
        "zh": "当前周期下训练窗口可用样本不足，已回退到完整数据区间。",
        "en": "Insufficient samples in current training window. Fallback to full data range."
    },
    "single_stock.entry_page_title": {
        "zh": "单股入口页\n==========",
        "en": "Single Stock Entry"
    },
    "analysis.current_symbol_chip": {
        "zh": "</span>\n  <span class=\"analysis-chart-chip\">当前标的",
        "en": "Current Symbol"
    },
    "common.testing_period": {
        "zh": "测试期",
        "en": "Testing Period"
    },
    "entry_page.description": {
        "zh": "入口页只负责把股票池整理清楚。进入主分析页后，现有多股图表、组合模拟和后续分析逻辑继续沿用。",
        "en": "The entry page organizes the stock pool. Existing multi-stock charts, portfolio simulation, and analysis logic continue on the main analysis page."
    },
    "analysis.model_summary_table": {
        "zh": "模型摘要表",
        "en": "Model Summary"
    },
    "analysis.strategy_summary_section": {
        "zh": "<div class=\"analysis-subsurface\">\n  <h4 class=\"analysis-callout-title\">当前策略摘要</h4>\n  <p class=\"analysis-callout-copy\">当前已提交 artifact：",
        "en": "Current Strategy Summary\nSubmitted artifact:"
    },
    "strategy.selection_prompt": {
        "zh": "请选择 SM 或 FSM",
        "en": "Select SM or FSM"
    },
    "strategy.param_description": {
        "zh": "手动调整所有策略参数，或使用高级策略自动搜索最优值。",
        "en": "Manually adjust all strategy parameters, or use advanced strategy to auto-search for optimal values."
    },
    "upload.multi_csv_title": {
        "zh": "上传多个单股 CSV",
        "en": "Upload Multiple Single-Stock CSVs"
    },
    "homepage.vision": {
        "zh": "把股票策略入口做成真正的网站首页。",
        "en": "Make the stock strategy entry the actual website homepage."
    },
    "stock_pool.operations": {
        "zh": "股票池操作",
        "en": "Stock Pool Operations"
    },
    "strategy.walk_forward": {
        "zh": "Walk-Forward 策略",
        "en": "Walk-Forward Strategy"
    },
    "ui.main_card_design": {
        "zh": "市场切换、搜索确认、开始分析和本地上传都放在同一张主操作卡里。",
        "en": "Market switch, search confirmation, start analysis, and local upload are all placed in the same main operation card."
    },
    "strategy.main_for_details": {
        "zh": "主策略（供收益热图 / 买卖点细看）",
        "en": "Main Strategy (for profit heatmap / trade point details)"
    },
    "context.change_detected": {
        "zh": "检测到股票/数据上下文变化，已清空上一个上下文中的策略结果。",
        "en": "Stock/data context change detected. Cleared strategy results from previous context."
    },
    "params.ema_slow_period": {
        "zh": "EMA 慢线周期",
        "en": "EMA Slow Period"
    },
    "params.short_momentum_window": {
        "zh": "短期动量窗口",
        "en": "Short Momentum Window"
    },
    "validation.ml_min_excess_samples": {
        "zh": "ml_min_excess_samples 必须为正整数",
        "en": "ml_min_excess_samples must be a positive integer."
    },
    "metrics.correlation": {
        "zh": "相关性",
        "en": "Correlation"
    },
    "quantstats.no_data": {
        "zh": "当前没有可展示的 QuantStats 信息。",
        "en": "No QuantStats information available to display."
    },
    "report.file_label": {
        "zh": "报告文件：",
        "en": "Report File:"
    },
    "strategy_library.title": {
        "zh": "##### 策略库 / 多策略选择器",
        "en": "Strategy Library / Multi-Strategy Selector"
    },
    "analysis.row_proportion_chip": {
        "zh": "行</span>\n  <span class=\"analysis-chart-chip\">比例",
        "en": "Row Proportion"
    },
    "upload.import_id_label": {
        "zh": "</div><div class='upload-row-meta'>导入标识：",
        "en": "Import ID:"
    },
    "data.no_volume_current_period": {
        "zh": "当前周期下没有可用的成交量数据。",
        "en": "No volume data available for the current period."
    },
    "scoring.main_window_only": {
        "zh": "仅主窗口总分",
        "en": "Main Window Score Only"
    },
    "comparison.vs_previous_day": {
        "zh": "较前一日",
        "en": "vs Previous Day"
    },
    "actions.generate_and_library": {
        "zh": "生成与策略库",
        "en": "Generate & Strategy Library"
    },
    "research_viewer.description": {
        "zh": "这个页面只读取本地 <code>model-test/outputs</code> 下的现有研究产物，不触发任何研究执行。默认展示最新可读 run，并允许在不同 run 之间切换浏览。",
        "en": "This page only reads existing research artifacts from the local <code>model-test/outputs</code> folder and does not trigger any research execution. It displays the latest readable run by default and allows switching between runs."
    },
    "metrics.core_metrics": {
        "zh": "核心指标",
        "en": "Core Metrics"
    },
    "run.no_anomalous_samples": {
        "zh": "当前 run 没有异常样本。",
        "en": "No anomalous samples in the current run."
    },
    "common.method": {
        "zh": "方法",
        "en": "Method"
    },
    "search.a_share_prompt": {
        "zh": "请先输入 A 股名称或代码，并从候选结果中选择。",
        "en": "Please enter an A-share name or code and select from the candidate results."
    },
    "version.market_scope_note": {
        "zh": "当前版本只在美股展示，默认使用 SPY 作为市场代理；若 adaptive artifact 缺失或损坏，会降级到 legacy dual-state router。",
        "en": "Current version only displays US stocks, using SPY as the default market proxy. Falls back to legacy dual-state router if adaptive artifact is missing or corrupted."
    },
    "visualization.multi_strategy_comparison": {
        "zh": "基于已选 artifact 渲染多策略净值/回撤比较。",
        "en": "Renders multi-strategy NAV/drawdown comparison based on selected artifact."
    },
    "results.intermediate_stage": {
        "zh": "中间阶段结果",
        "en": "Intermediate Stage Results"
    },
    "performance.best": {
        "zh": "最佳表现",
        "en": "Best Performance"
    },
    "portfolio.generation_complete": {
        "zh": "组合策略已生成，右侧结果区已更新。",
        "en": "Portfolio strategy generated. Results area on the right has been updated."
    },
    "params.rsi_lower_threshold": {
        "zh": "RSI 下限阈值",
        "en": "RSI Lower Threshold"
    },
    "multi_stock.minimum_requirement": {
        "zh": "多股分析至少需要 2 个标的。可以组合搜索结果与上传文件。",
        "en": "Multi-stock analysis requires at least 2 symbols. You can combine search results with uploaded files."
    },
    "search.candidates_failed": {
        "zh": "搜索候选项失败：",
        "en": "Failed to fetch search candidates:"
    },
    "export.report_title": {
        "zh": "### 导出分析报告",
        "en": "Export Analysis Report"
    },
    "params.ema_trend_parameters": {
        "zh": "**EMA 趋势参数**",
        "en": "EMA Trend Parameters"
    },
    "single_stock.prerequisite": {
        "zh": "先确定一个标的，再进入单股分析。",
        "en": "First, select a symbol to enter single-stock analysis."
    },
    "metrics.benchmark_drawdown_pct": {
        "zh": "基准回撤 %",
        "en": "Benchmark Drawdown %"
    },
    "optimization.population_size": {
        "zh": "种群大小",
        "en": "Population Size"
    },
    "strategy.min_exit_signals": {
        "zh": "出场最少信号数",
        "en": "Minimum Exit Signals"
    },
    "data.training_set_ratio": {
        "zh": "训练集比例",
        "en": "Training Set Ratio"
    },
    "strategy.entry_condition": {
        "zh": "入场需满足以下信号中的至少 N 个：",
        "en": "Entry requires at least N of the following signals:"
    },
    "baseline.cache_hit": {
        "zh": "Baseline 阶段命中缓存。",
        "en": "Cache hit during Baseline phase."
    },
    "feedback.thank_you": {
        "zh": "✅ 感谢反馈！点击下方链接提交到 GitHub：",
        "en": "✅ Thanks for your feedback! Click the link below to submit to GitHub:"
    },
    "ml.filter": {
        "zh": "ML过滤",
        "en": "ML Filter"
    },
    "draft.incomplete": {
        "zh": "当前草稿尚未补齐，先完成左侧待选项。",
        "en": "Current draft is incomplete. Please fill in the pending options on the left first."
    },
    "route.rendering": {
        "zh": "渲染 `/strategy/model-evaluation`。",
        "en": "Rendering `/strategy/model-evaluation`."
    },
    "export.structure_update": {
        "zh": "导出结构不再沿用旧版蓝灰卡片样式，而是和主分析页保持同一套站点式暖白表面与响应式布局。",
        "en": "The export structure no longer uses the old blue-gray card style. It now adopts the same site-style warm white surface and responsive layout as the main analysis page."
    },
    "navigation.no_index_match": {
        "zh": "没有找到索引匹配，将按当前输入直接切换。",
        "en": "No index match found. Will switch directly based on current input."
    },
    "stock_selection.required": {
        "zh": "请先从搜索结果中选择一只股票。",
        "en": "Please select a stock from the search results first."
    },
    "market.proxy": {
        "zh": "市场代理",
        "en": "Market Proxy"
    },
    "period.monthly": {
        "zh": "月度",
        "en": "Monthly"
    },
    "strategy.generation_flow": {
        "zh": "先选模型路径，再显式点击“生成策略”；页面不再默认预计算全模型结果。",
        "en": "First select a model path, then explicitly click 'Generate Strategy'. The page no longer pre-computes all model results by default."
    },
    "regime.path_pending": {
        "zh": "Regime -> 等待选择 adaptive / legacy 路径",
        "en": "Regime -> Waiting for selection of adaptive / legacy path."
    },
    "scoring.optional": {
        "zh": "评分（可选）",
        "en": "Scoring (Optional)"
    },
    "scoring.weight_midterm_momentum": {
        "zh": "中期动量在评分中的权重。",
        "en": "Weight of mid-term momentum in the scoring."
    },
    "regime.missing_kind": {
        "zh": "Regime 路径缺少合法的 regime_kind",
        "en": "Regime path is missing a valid regime_kind."
    },
    "run.metadata": {
        "zh": "Run 元信息",
        "en": "Run Metadata"
    },
    "month.january": {
        "zh": "1月",
        "en": "January"
    },
    "baseline.type_prompt": {
        "zh": "请选择 Baseline 类型",
        "en": "Please select a Baseline type."
    },
    "comparison.unified_start": {
        "zh": "所有股票起点统一到同一基准，先判断谁在当前观察区间内跑得更快。",
        "en": "All stocks start from the same baseline to determine which performs better within the current observation window."
    },
    "position.near_high": {
        "zh": "靠近区间高位",
        "en": "Near range high"
    },
    "ml.filter_disabled": {
        "zh": "当前请求未启用 ML 过滤",
        "en": "ML filter is not enabled for the current request."
    },
    "metrics.midterm_return_window": {
        "zh": "中期收益率窗口。",
        "en": "Mid-term return window."
    },
    "status.enabled": {
        "zh": "已启用",
        "en": "Enabled"
    },
    "signal.buy_point": {
        "zh": "买点",
        "en": "Buy Point"
    },
    "table.metrics_comparison": {
        "zh": "##### 指标对比表",
        "en": "##### Metrics Comparison Table"
    },
    "layout.site_sync": {
        "zh": "站点结构同步",
        "en": "Site Structure Sync"
    },
    "data.days": {
        "zh": "数据天数",
        "en": "Data Days"
    },
    "page.single_stock_analysis": {
        "zh": "单股主分析页",
        "en": "Single Stock Analysis Page"
    },
    "step.baseline_path": {
        "zh": "Step 2 · Baseline 路径",
        "en": "Step 2 · Baseline Path"
    },
    "requirement.align_chart_four": {
        "zh": "对齐图四要求",
        "en": "Align with Chart 4 requirements"
    },
    "condition.entry_threshold": {
        "zh": "需要同时满足的入场条件数量。数值越大入场越严格，1=最宽松（任一满足即入场），5=最严格（全部满足才入场）",
        "en": "Number of entry conditions required to be met simultaneously. Higher values mean stricter entry: 1=most lenient (any condition), 5=strictest (all conditions)."
    },
    "search.path_required": {
        "zh": "Search 路径必须选择 SM 或 FSM",
        "en": "Search path must select either SM or FSM."
    },
    "ml.quality_display": {
        "zh": "ML 质量展示",
        "en": "ML Quality Display"
    },
    "sorting.cumulative_return_first": {
        "zh": "按测试期累计收益优先，夏普作为并列时的次级排序",
        "en": "Sort by cumulative return during test period first, use Sharpe ratio as secondary tie-breaker."
    },
    "view.strategy_library": {
        "zh": "策略库视图：",
        "en": "Strategy Library View:"
    },
    "rsi.period": {
        "zh": "RSI 周期",
        "en": "RSI Period"
    },
    "data.adjustment": {
        "zh": "复权方式",
        "en": "Adjustment Method"
    },
    "stock_pool.candidates_hint": {
        "zh": "输入名称或代码后，这里会出现可加入股票池的候选项。",
        "en": "Enter a name or code, and candidate stocks for the pool will appear here."
    },
    "backtest.net_value_drawdown": {
        "zh": "回测净值 / 回撤",
        "en": "Backtest Net Value / Drawdown"
    },
    "section.rsi_parameters": {
        "zh": "**RSI 参数**",
        "en": "**RSI Parameters**"
    },
    "optimization.bayesian_running": {
        "zh": "贝叶斯优化中（",
        "en": "Bayesian optimization in progress ("
    },
    "position.high_current_target": {
        "zh": "当前维持高仓位，目标仓位",
        "en": "Currently maintaining high position. Target position:"
    },
    "run.readable_count": {
        "zh": "个可读 run</span>\n      <span class=\"analysis-pill\">",
        "en": " readable run(s)</span>\n      <span class=\"analysis-pill\">"
    },
    "file.tearsheet_missing": {
        "zh": "tearsheet.html 文件不存在，当前只保留元数据。",
        "en": "tearsheet.html file does not exist. Only metadata is retained."
    },
    "scoring.weight_obv_trend": {
        "zh": "OBV 趋势在评分中的权重。",
        "en": "Weight of OBV trend in the scoring."
    },
    "page.multi_stock_comparison": {
        "zh": "多股票对比分析 -",
        "en": "Multi-Stock Comparison Analysis -"
    },
    "chart.monthly_return_heatmap": {
        "zh": "月度收益热图",
        "en": "Monthly Return Heatmap"
    },
    "selection.current_symbol": {
        "zh": "当前标的",
        "en": "Current Symbol"
    },
    "calculation.insufficient_days": {
        "zh": "不足 20 日时按现有窗口计算",
        "en": "If fewer than 20 days, calculate using the available window."
    },
    "factor.weight.phase1.title": {
        "zh": "**Phase 1 新因子权重**",
        "en": "Phase 1: New Factor Weights"
    },
    "metric.riskReturn": {
        "zh": "风险收益",
        "en": "Risk-Return"
    },
    "chart.factorScore.tooltip": {
        "zh": "柱子越高，说明当前综合因子评分越强；颜色对应建议仓位。",
        "en": "Taller bars indicate stronger composite factor scores; color corresponds to suggested position."
    },
    "param.stopLoss.formula": {
        "zh": "止损距离=ATR×倍数。",
        "en": "Stop Loss Distance = ATR × Multiplier"
    },
    "time.month.march": {
        "zh": "3月",
        "en": "Mar"
    },
    "param.entryThreshold.description": {
        "zh": "因子评分高于该值才视为入场信号之一。",
        "en": "Factor score must exceed this value to be considered an entry signal."
    },
    "param.rsi.period.description": {
        "zh": "RSI 计算周期。",
        "en": "RSI calculation period."
    },
    "backtest.rollingWindow.description": {
        "zh": "每次滚动的测试区间长度。",
        "en": "Length of each rolling test window."
    },
    "function.extractStrategyParams.description": {
        "zh": "从完整 params 中提取策略相关参数子集（去除 UI 状态键）。",
        "en": "Extract strategy-related parameter subset from full params (excluding UI state keys)."
    },
    "param.midTermMomentum.window": {
        "zh": "中期动量窗口",
        "en": "Mid-term Momentum Window"
    },
    "component.stockSearch.description": {
        "zh": "渲染搜索与添加股票区域，输入时仅局部刷新。",
        "en": "Renders stock search & add area; partial refresh on input."
    },
    "category.family": {
        "zh": "族",
        "en": "Family"
    },
    "data.marketIndicator.empty": {
        "zh": "暂无可展示的行情与指标数据。",
        "en": "No market or indicator data available."
    },
    "data.fallback.na": {
        "zh": "字段缺失时回退为 N/A",
        "en": "Fallback to N/A if field is missing."
    },
    "position.target": {
        "zh": "目标仓位",
        "en": "Target Position"
    },
    "metric.portfolioSharpe": {
        "zh": "组合夏普",
        "en": "Portfolio Sharpe"
    },
    "strategy.comparison.empty": {
        "zh": "暂无可比策略",
        "en": "No comparable strategies."
    },
    "data.source": {
        "zh": "数据来源",
        "en": "Data Source"
    },
    "data.lastUpdated": {
        "zh": "最新更新时间",
        "en": "Last Updated"
    },
    "metric.driftBaseline": {
        "zh": "Drift（漂移基线）",
        "en": "Drift (Baseline)"
    },
    "strategy.signal.empty": {
        "zh": "所选策略都没有可展示的买卖点数据。",
        "en": "No buy/sell point data available for selected strategies."
    },
    "component.basicInfo.structure": {
        "zh": "基础信息结构",
        "en": "Basic Info Structure"
    },
    "navigation.multiStock.entry": {
        "zh": "多股入口",
        "en": "Multi-Stock Entry"
    },
    "page.strategy.home.description": {
        "zh": "渲染 `/strategy` 首页。",
        "en": "Renders the `/strategy` homepage."
    },
    "metric.robustness": {
        "zh": "稳健性",
        "en": "Robustness"
    },
    "component.singleStock.basicInfo": {
        "zh": "单股基础信息区",
        "en": "Single Stock Basic Info"
    },
    "price.openHigh.today": {
        "zh": "当日开高",
        "en": "Today's Open-High"
    },
    "chart.meta.trainingCutoff": {
        "zh": "</div>\n<div class=\"analysis-chart-meta\">\n  <span class=\"analysis-chart-chip\">训练截止",
        "en": "</div>\n<div class=\"analysis-chart-meta\">\n  <span class=\"analysis-chart-chip\">Training Cutoff"
    },
    "instruction.selectPrimaryStrategy": {
        "zh": "请先指定主策略，再查看多策略买卖点。",
        "en": "Please select a primary strategy first to view multi-strategy signals."
    },
    "section.mlQuality.title": {
        "zh": "##### ML 质量展示",
        "en": "ML Quality Display"
    },
    "section.strategy": {
        "zh": "策略区",
        "en": "Strategy Section"
    },
    "page.multiStockAnalysis.header": {
        "zh": "<h1 class=\"analysis-title\">多股主分析页</h1>\n<div class=\"analysis-subtitle\">",
        "en": "<h1 class=\"analysis-title\">Multi-Stock Analysis</h1>\n<div class=\"analysis-subtitle\">"
    },
    "metric.cumulativeReturn.percent": {
        "zh": "累计收益 %",
        "en": "Cumulative Return %"
    },
    "menu.bugReport": {
        "zh": "🐛 Bug 报告",
        "en": "🐛 Bug Report"
    },
    "param.takeProfit.formula": {
        "zh": "止盈距离=ATR×倍数。",
        "en": "Take Profit Distance = ATR × Multiplier"
    },
    "price.current": {
        "zh": "现价",
        "en": "Current Price"
    },
    "button.advancedSettings": {
        "zh": "⚙️ 高级设置（自定义参数 / 查看当前值）",
        "en": "⚙️ Advanced Settings (Customize / View Params)"
    },
    "workflow.marketSnapshotFirst": {
        "zh": "先看大盘快照，再往下进入推荐股票和补充股票池。",
        "en": "First view market snapshot, then proceed to recommended stocks and supplementary pool."
    },
    "section.parameters": {
        "zh": "参数",
        "en": "Parameters"
    },
    "error.missingRequiredColumns": {
        "zh": "缺少必需列：",
        "en": "Missing required columns:"
    },
    "metric.benchmarkCumulative.percent": {
        "zh": "基准累计 %",
        "en": "Benchmark Cumulative %"
    },
    "component.htmlReportBuilder.description": {
        "zh": "共享 HTML 导出报告 builder\n=========================\n为单股 / 多股页面生成符合 W6-W8 站点风格的离线 HTML 报告。",
        "en": "Shared HTML Report Builder\n=========================\nGenerates offline HTML reports in W6-W8 site style for single/multi-stock pages."
    },
    "label.status": {
        "zh": "状态",
        "en": "Status"
    },
    "strategy.notGenerated": {
        "zh": "未生成策略",
        "en": "Strategy Not Generated"
    },
    "label.marketProxy": {
        "zh": "市场代理：",
        "en": "Market Proxy:"
    },
    "param.bollinger.stdDev.description": {
        "zh": "布林带上下轨的标准差倍数。",
        "en": "Standard deviation multiplier for Bollinger Bands upper/lower bands."
    },
    "data.stock.empty": {
        "zh": "暂无股票数据，请先添加股票",
        "en": "No stock data. Please add stocks first."
    },
    "instruction.selectSmOrFsm": {
        "zh": "请先选择 SM 或 FSM",
        "en": "Please select SM or FSM first."
    },
    "metric.volume.compressed": {
        "zh": "成交量（压缩）",
        "en": "Volume (Compressed)"
    },
    "state.momentum.neutral": {
        "zh": "动能中性",
        "en": "Momentum Neutral"
    },
    "stockPool.addByTicker": {
        "zh": "未找到索引匹配，将按该美股代码加入股票池。",
        "en": "No index match found. Adding to stock pool by US ticker."
    },
    "feedback.title": {
        "zh": "] 用户反馈",
        "en": "User Feedback"
    },
    "indicator.rsi.unavailable": {
        "zh": "当前周期下没有可用的 RSI 指标。",
        "en": "No RSI indicator available for the current period."
    },
    "parameterSearch.enable": {
        "zh": "启用参数搜索",
        "en": "Enable Parameter Search"
    },
    "backtest.optimizedReturn": {
        "zh": "优化后收益",
        "en": "Optimized Return"
    },
    "workflow.stageLink": {
        "zh": "阶段链路：",
        "en": "Stage Link:"
    },
    "score.quantile.high": {
        "zh": "评分分位数-高档",
        "en": "Score Quantile - High"
    },
    "backtest.walkForward": {
        "zh": "Walk-Forward 回测",
        "en": "Walk-Forward Backtest"
    },
    "parameter.zScoreWindow.desc": {
        "zh": "用于计算滚动 Z 分数的窗口。",
        "en": "Window for calculating rolling Z-score."
    },
    "report.composition": {
        "zh": "摘要数字 + 明细表 + 图表组",
        "en": "Summary + Details + Charts"
    },
    "market.index": {
        "zh": "市场指数",
        "en": "Market Index"
    },
    "common.days": {
        "zh": "天数",
        "en": "Days"
    },
    "chart.drawdownCurve": {
        "zh": "回撤曲线",
        "en": "Drawdown Curve"
    },
    "strategy.multiStockResults": {
        "zh": "多股策略结果区",
        "en": "Multi-Stock Strategy Results"
    },
    "score.quantile": {
        "zh": "评分分位数",
        "en": "Score Quantile"
    },
    "common.noData": {
        "zh": "暂无数据",
        "en": "No Data Available"
    },
    "chart.monthlyReturnsHeatmap.title": {
        "zh": "##### 月度收益热图",
        "en": "Monthly Returns Heatmap"
    },
    "chart.alignmentRequirement": {
        "zh": "对齐图五要求",
        "en": "Align with Chart 5 Requirements"
    },
    "factor.latestScoreComparison": {
        "zh": "最新因子评分对比",
        "en": "Latest Factor Score Comparison"
    },
    "common.stockOrModel": {
        "zh": "股票/模型",
        "en": "Stock / Model"
    },
    "report.v1Scope": {
        "zh": "v1 只展示条目摘要并提供文件下载，不在应用内嵌入整页 HTML。",
        "en": "v1: Shows entry summary and file download only. Full HTML not embedded."
    },
    "action.refreshFailed": {
        "zh": "刷新失败:",
        "en": "Refresh Failed:"
    },
    "results.defaultSource": {
        "zh": "右侧所有结果默认读取 current_artifact",
        "en": "All results on the right read from current_artifact by default."
    },
    "parameter.obvCommonWindow.desc": {
        "zh": "OBV 趋势变化率、成交量均量、价格高低点位置的共用计算周期。",
        "en": "Common calculation period for OBV trend rate, average volume, and price high/low points."
    },
    "report.singleStockExport": {
        "zh": "单股导出报告",
        "en": "Single Stock Export Report"
    },
    "parameter.rsiStrongThreshold.desc": {
        "zh": "RSI 高于该值视为偏强。",
        "en": "RSI above this value is considered strong."
    },
    "data.presetSource": {
        "zh": "预设来源",
        "en": "Preset Source"
    },
    "baseline.mean": {
        "zh": "Mean（均值基线）",
        "en": "Mean (Baseline)"
    },
    "chart.correlationHeatmap.insufficientData": {
        "zh": "数据不足以计算相关性热图（需要至少 5 个共同交易日）。",
        "en": "Insufficient data for correlation heatmap (minimum 5 common trading days required)."
    },
    "chart.meta.dataRange": {
        "zh": "</div>\n<div class=\"analysis-chart-meta\">\n  <span class=\"analysis-chart-chip\">数据区间",
        "en": "Data Range"
    },
    "score.regime": {
        "zh": "Regime 评分",
        "en": "Regime Score"
    },
    "parameter.macdSignalPeriod": {
        "zh": "MACD 信号周期",
        "en": "MACD Signal Period"
    },
    "tearSheet.list.title": {
        "zh": "<h4 class='analysis-section-title'>Tear Sheet 列表</h4>",
        "en": "Tear Sheet List"
    },
    "mlflow.notRecorded": {
        "zh": "未记录 MLflow",
        "en": "Not Logged to MLflow"
    },
    "metric.annualizedVolatility": {
        "zh": "年化波动率（风险）%",
        "en": "Annualized Volatility (Risk) %"
    },
    "example.tickerOrName": {
        "zh": "例如: TSLA / Apple / 贵州茅台 / 600519",
        "en": "e.g., TSLA / Apple / Kweichow Moutai / 600519"
    },
    "common.unit.item": {
        "zh": "个",
        "en": ""
    },
    "strategy.comparison.insufficientSnapshots": {
        "zh": "当前只有 1 条策略参与比较。继续保存更多快照后，再观察曲线差异会更有价值。",
        "en": "Only 1 strategy in comparison. Save more snapshots to better observe curve differences."
    },
    "market.snapshotAndRecommendations": {
        "zh": "当前市场的快照与推荐入口",
        "en": "Current Market Snapshot & Recommendations"
    },
    "parameter.custom": {
        "zh": "自定义参数",
        "en": "Custom Parameters"
    },
    "metric.totalReturn": {
        "zh": "总收益率",
        "en": "Total Return"
    },
    "common.type": {
        "zh": "类型",
        "en": "Type"
    },
    "strategy.saveCurrent": {
        "zh": "保存当前策略",
        "en": "Save Current Strategy"
    },
    "mlflow.uiScopeNote": {
        "zh": "<p class='analysis-section-copy'>页面只显示 mlflow_run.json 元数据，不尝试启动或嵌入 MLflow UI。</p>",
        "en": "This page displays mlflow_run.json metadata only. It does not launch or embed the MLflow UI."
    },
    "ui.mainOperationCard.desc": {
        "zh": "市场切换、搜索加入、上传文件和已选股票管理都收进同一张主操作卡，不再拆成多组厚重表单。",
        "en": "Market switch, search & add, file upload, and selected stock management are consolidated into one main operation card, avoiding multiple heavy forms."
    },
    "simulation.portfolio": {
        "zh": "投资组合模拟",
        "en": "Portfolio Simulation"
    },
    "onboarding.clearEntry": {
        "zh": "从一个清楚的入口动作开始",
        "en": "Start with a clear entry action."
    },
    "strategy.multiStockZone": {
        "zh": "多股策略区",
        "en": "Multi-Stock Strategy Zone"
    },
    "strategy.sm10Factor": {
        "zh": "SM（10因子）",
        "en": "SM (10-Factor)"
    },
    "layout.description": {
        "zh": "左侧固定为模型控制台与组合搜索，右侧固定为结果图区、组合 KPI 摘要和个股表现表，对齐第七周第 8 项的“左控台 / 右结果区”结构。",
        "en": "Left side fixed for model console & portfolio search; right side fixed for result charts, portfolio KPI summary, and stock performance table. Aligns with Week 7 Item 8's 'Left Console / Right Results' structure."
    },
    "workflow.executionBranch": {
        "zh": "，执行分支",
        "en": "Execution Branch"
    },
    "comparison.layoutLogic": {
        "zh": "左侧负责把待比较股票整理清楚，右侧持续提供当前市场快照和推荐补充入口。 搜索、上传和推荐最终都会汇到同一个待分析列表。",
        "en": "Left side organizes stocks for comparison; right side provides live market snapshot and recommendation entry. Search, upload, and recommendations feed into a unified analysis list."
    },
    "results.stableZone": {
        "zh": "这部分固定保留组合 KPI、主结果图和各股票表现表，切换主图时不会打散稳定信息区。",
        "en": "This area retains portfolio KPIs, main result chart, and stock performance tables. Switching charts won't disrupt the stable info zone."
    },
    "export.htmlZone": {
        "zh": "在页面底部渲染 HTML 导出区域。",
        "en": "Render HTML export area at page bottom."
    },
    "indicator.macdFastPeriod": {
        "zh": "MACD 快线 EMA 周期。",
        "en": "MACD Fast Line EMA Period."
    },
    "notification.addSuccess": {
        "zh": "添加成功",
        "en": "Added Successfully"
    },
    "status.current": {
        "zh": "当前 ·",
        "en": "Current ·"
    },
    "model.viewOnlyDescription": {
        "zh": "只读浏览已有模型研究结果。",
        "en": "Read-only view of existing model research results."
    },
    "table.rowIndex": {
        "zh": "行索引",
        "en": "Row Index"
    },
    "report.generatingHtml": {
        "zh": "正在生成 HTML 报告...",
        "en": "Generating HTML Report..."
    },
    "validation.quantileOrder": {
        "zh": "中档分位数需要小于高档分位数。",
        "en": "Mid quantile must be less than high quantile."
    },
    "parameter.midTermMomentumWeight": {
        "zh": "中期动量权重",
        "en": "Mid-Term Momentum Weight"
    },
    "metric.strategyReturn": {
        "zh": "策略收益",
        "en": "Strategy Return"
    },
    "chart.lowVolume": {
        "zh": "最低 / 成交量",
        "en": "Low / Volume"
    },
    "page.modelEvaluation": {
        "zh": "模型评估页\n==========\n只读浏览 `model-test/outputs` 里的已有研究产物。",
        "en": "Model Evaluation Page\n==========\nRead-only view of existing research outputs in `model-test/outputs`."
    },
    "strategy.ofTrading": {
        "zh": "的交易策略",
        "en": "Trading Strategy"
    },
    "chart.normalizedCurvesNote": {
        "zh": "所有曲线都以同一基准起点归一化，适合先看整体强弱排序。",
        "en": "All curves normalized to the same baseline start. Suitable for initial strength ranking."
    },
    "selection.source": {
        "zh": "</div><div class='selection-row-meta'>来源：搜索或推荐加入</div></div>",
        "en": "Source: Added via search or recommendation."
    },
    "common.window": {
        "zh": "窗口",
        "en": "Window"
    },
    "anomaly.summaryOnly": {
        "zh": "这里只展示 report.json 里已汇总的异常样本，不重新追踪底层任务日志。",
        "en": "Shows only aggregated anomaly samples from report.json, without re-tracing underlying task logs."
    },
    "report.title": {
        "zh": "报告标题",
        "en": "Report Title"
    },
    "validation.regimePath": {
        "zh": "Regime 路径必须选择合法的 regime_kind",
        "en": "Regime path must select a valid regime_kind."
    },
    "validation.mlModelRequired": {
        "zh": "启用 ML 时必须选择合法的 ML 模型",
        "en": "A valid ML model must be selected when ML is enabled."
    },
    "action.exportModel": {
        "zh": "导出模型",
        "en": "Export Model"
    },
    "export.description": {
        "zh": "由 Strategy Lab 导出，结构与站点主分析页保持同一前端语法。",
        "en": "Exported by Strategy Lab, maintaining the same front-end syntax as the main analysis page."
    },
    "error.insufficientDataForRelativeStrength": {
        "zh": "数据不足以计算相对强弱（至少需要 2 只有效股票）。",
        "en": "Insufficient data to calculate relative strength (at least 2 valid stocks required)."
    },
    "warning.noComparableArtifacts": {
        "zh": "当前没有可比较的 artifact，跳过净值与回撤。",
        "en": "No comparable artifacts available, skipping NAV and drawdown."
    },
    "prompt.selectParamSearchMethod": {
        "zh": "请选择参数搜索方法",
        "en": "Please select a parameter search method."
    },
    "results.portfolio": {
        "zh": "组合结果",
        "en": "Portfolio Results"
    },
    "common.strategy": {
        "zh": "策略",
        "en": "Strategy"
    },
    "action.refreshMarketSnapshot": {
        "zh": "刷新市场快照",
        "en": "Refresh Market Snapshot"
    },
    "parameter.obvTrendWeight": {
        "zh": "OBV 趋势权重",
        "en": "OBV Trend Weight"
    },
    "error.mlTrainingDataEmpty": {
        "zh": "ML 训练样本为空，无法训练过滤器",
        "en": "ML training samples are empty, cannot train filter."
    },
    "parameter.drawdownPenaltyWeight": {
        "zh": "回撤惩罚权重",
        "en": "Drawdown Penalty Weight"
    },
    "section.stockSelection": {
        "zh": "🔍 股票选择",
        "en": "🔍 Stock Selection"
    },
    "results.keepScoreView": {
        "zh": "保留当前结果区中的评分视角，便于补充价格图之外的解释。",
        "en": "Retain the scoring perspective in the results area to facilitate explanations beyond price charts."
    },
    "selection.currentCount": {
        "zh": "<p class=\"selection-note\">\n  当前待分析数量：<strong>",
        "en": "Current items pending analysis: <strong>"
    },
    "ui.searchInputFallback": {
        "zh": "渲染支持 keyup 的搜索输入框；缺少组件时回退到原生输入框。",
        "en": "Render a search input box supporting keyup events; fallback to native input if component missing."
    },
    "action.selectStocks": {
        "zh": "选择股票",
        "en": "Select Stocks"
    },
    "common.weight": {
        "zh": "权重",
        "en": "Weight"
    },
    "placeholder.stockInput": {
        "zh": "输入股票名称或代码",
        "en": "Enter stock name or code"
    },
    "status.loadedValidSecurities": {
        "zh": "当前成功加载的有效标的",
        "en": "Currently loaded valid securities"
    },
    "strategy.courseBaseline": {
        "zh": "课程基线策略",
        "en": "Course Baseline Strategy"
    },
    "parameter.macdWeight": {
        "zh": "MACD 权重",
        "en": "MACD Weight"
    },
    "stock.periodReturn": {
        "zh": "股票（期间收益）",
        "en": "Stock (Period Return)"
    },
    "status.updatedTo": {
        "zh": ": 已更新至",
        "en": "Updated to: "
    },
    "alert.riskFactors": {
        "zh": "1. 📊 因子评分过低\n2. 📉 趋势反转（EMA快<慢）\n3. ⚠️ RSI超出合理区间\n4. 📉 MACD跌破信号线",
        "en": "1. 📊 Factor score too low\n2. 📉 Trend reversal (EMA fast < slow)\n3. ⚠️ RSI out of range\n4. 📉 MACD below signal line"
    },
    "strategy.noSavable": {
        "zh": "当前没有可保存的策略。",
        "en": "No strategies available to save."
    },
    "action.add": {
        "zh": "加入",
        "en": "Add"
    },
    "metric.volatility60d": {
        "zh": "近 60 日波动",
        "en": "60D Volatility"
    },
    "backtest.window": {
        "zh": "测试窗口（交易日）",
        "en": "Test Window (Trading Days)"
    },
    "indicator.volumePullback": {
        "zh": "量能回落",
        "en": "Volume Pullback"
    },
    "chart.monthlyReturnHeatmap": {
        "zh": "月度收益率热图",
        "en": "Monthly Return Heatmap"
    },
    "state.disabled": {
        "zh": "未启用",
        "en": "Disabled"
    },
    "instruction.selectModeFirst": {
        "zh": "请先在上方选择 Baseline、Search 或 Regime，再展开具体配置。",
        "en": "Please select Baseline, Search, or Regime above before configuring."
    },
    "status.draftPending": {
        "zh": "当前结果仍是上次成功提交的 artifact；草稿修改后需要重新点击“生成策略”才会生效。",
        "en": "Current results are from the last successful submission. Draft changes require re-running \"Generate Strategy\"."
    },
    "workflow.submitToArtifact": {
        "zh": "最终提交到 current_artifact",
        "en": "Final submission to current_artifact"
    },
    "ui.unifiedWorkflow": {
        "zh": "搜索、上传和推荐入口都保持在同一条页面语法里，不把用户推回后台式操作区。",
        "en": "Search, upload, and recommendation are unified in one page flow—no back‑office navigation."
    },
    "action.downloadHtmlReport": {
        "zh": "下载 HTML 报告",
        "en": "Download HTML Report"
    },
    "report.ready": {
        "zh": "✅ HTML报告已生成！点击上方按钮下载",
        "en": "✅ HTML report is ready! Click above to download."
    },
    "chart.netValueCurve": {
        "zh": "净值曲线",
        "en": "Net Value Curve"
    },
    "metric.startPrice": {
        "zh": "起始价格",
        "en": "Start Price"
    },
    "strategy.summary": {
        "zh": "当前策略摘要",
        "en": "Strategy Summary"
    },
    "parameter.timePeriod": {
        "zh": "时间周期",
        "en": "Time Period"
    },
    "chart.followsMainStrategy": {
        "zh": "热图和买卖点细看都跟随当前主策略",
        "en": "Heatmaps and trade details follow the active strategy."
    },
    "instruction.selectRunForModel": {
        "zh": "选择一个可读 run 后，这里会展示当前最佳模型和评分规则。",
        "en": "Select a readable run to view the best model and scoring rules."
    },
    "parameter.adxPeriod": {
        "zh": "ADX 周期",
        "en": "ADX Period"
    },
    "indicator.emaFast": {
        "zh": "</span>\n  <span class=\"analysis-chart-chip\">EMA 快线",
        "en": "EMA Fast"
    },
    "field.description": {
        "zh": "描述",
        "en": "Description"
    },
    "meta.generatedTime": {
        "zh": "生成时间",
        "en": "Generated"
    },
    "chart.withQuantileTrend": {
        "zh": "与分位数走势。",
        "en": "with quantile trend."
    },
    "search.matches": {
        "zh": "匹配结果",
        "en": "Matches"
    },
    "data.filteredSamples": {
        "zh": "当前日期筛选后的有效样本",
        "en": "Valid samples after date filter"
    },
    "run.readable": {
        "zh": "可读 run",
        "en": "Readable Run"
    },
    "chart.insufficientDataForHeatmap": {
        "zh": "当前结果不足以生成策略周期热图。",
        "en": "Insufficient data for strategy period heatmap."
    },
    "chart.insufficientDataForRiskReturn": {
        "zh": "数据不足以计算风险收益图。",
        "en": "Insufficient data for risk‑return chart."
    },
    "workflow.step1SelectFamily": {
        "zh": "Step 1 选择 Family",
        "en": "Step 1: Select Family"
    },
    "unit.items": {
        "zh": "条。",
        "en": "items."
    },
    "rule.emaFastBelowSlow": {
        "zh": "趋势 EMA 快线需要小于慢线。",
        "en": "EMA fast line must be below slow line."
    },
    "field.symbol": {
        "zh": "股票代码",
        "en": "Symbol"
    },
    "mode.baselineDescription": {
        "zh": "Baseline 路径只生成单步基线策略，不进入参数搜索或 ML 过滤。",
        "en": "Baseline path generates a single‑step baseline strategy—no parameter search or ML filtering."
    },
    "mode.strategyCompare": {
        "zh": "策略比对模式",
        "en": "Strategy Compare Mode"
    },
    "instruction.uploadReadyData": {
        "zh": "如果你已经准备好标准化数据文件，可以直接用上传结果进入分析。",
        "en": "If you have standardized data files, upload them to start analysis directly."
    },
    "ui.unifiedPreviewArea": {
        "zh": "右侧只保留一个大的展示区，用来支撑进入分析前的判断，不再把说明拆成多张卡片。",
        "en": "Right panel is a single large preview area for pre‑analysis judgment—no split‑up cards."
    },
    "nav.home": {
        "zh": "首页",
        "en": "Home"
    },
    "section.experiment_monitor": {
        "zh": "实验监控",
        "en": "Experiment Monitor"
    },
    "strategy.noSavedYet": {
        "zh": "当前还没有已保存策略。保存当前策略后，这里会形成本次会话的策略库。",
        "en": "No saved strategies yet. Save current strategy to build a session library."
    },
    "action.startSingleStockAnalysis": {
        "zh": "开始单股分析",
        "en": "Start Single‑Stock Analysis"
    },
    "rule.baselineFamilyRequired": {
        "zh": "Baseline 路径必须选择 Naive / Mean / Drift",
        "en": "Baseline path requires Naive, Mean, or Drift family."
    },
    "filter.all": {
        "zh": "全部",
        "en": "All"
    },
    "metric.sharpe": {
        "zh": "夏普：",
        "en": "Sharpe: "
    },
    "status.showingLastLineage": {
        "zh": "当前展示的是上次成功生成的 lineage；新草稿尚未提交。",
        "en": "Showing last successful lineage; new draft not yet submitted."
    },
    "validation.selectModelFamily": {
        "zh": "请选择模型家族",
        "en": "Please select a model family."
    },
    "error.cannotReadReport": {
        "zh": "无法读取报告文件：",
        "en": "Cannot read report file: "
    },
    "price.openHigh": {
        "zh": "开盘 / 最高",
        "en": "Open / High"
    },
    "exit.condition.signalCount": {
        "zh": "出场需满足以下信号中的至少 N 个：",
        "en": "Exit requires at least N of the following signals:"
    },
    "latest.suggestion": {
        "zh": "最新建议",
        "en": "Latest Suggestion"
    },
    "signal.condition.list": {
        "zh": "1. 📊 因子评分达标\n2. 📈 趋势向上（EMA快>慢）\n3. 💪 趋势强度足够（ADX）\n4. 🎯 RSI在合理区间\n5. 📉 MACD在信号线上方",
        "en": "1. 📊 Factor score meets threshold\n2. 📈 Uptrend (Fast EMA > Slow EMA)\n3. 💪 Sufficient trend strength (ADX)\n4. 🎯 RSI within reasonable range\n5. 📉 MACD above signal line"
    },
    "chart.build.scoreQuantile": {
        "zh": "构建评分 + 分位数图。",
        "en": "Build score + quantile chart."
    },
    "strategy.status.inLibrary": {
        "zh": "当前策略已在策略库中。",
        "en": "Current strategy is already in the library."
    },
    "draft.ready.generate": {
        "zh": "当前草稿已经准备好，点击“生成策略”后右侧会提交新的 current_artifact。",
        "en": "Draft is ready. Click 'Generate Strategy' to submit a new current_artifact on the right."
    },
    "timestamp.lastUpdated": {
        "zh": "</span>\n  <span>最新更新时间",
        "en": "Last Updated: "
    },
    "model.ml": {
        "zh": "ML 模型",
        "en": "ML Model"
    },
    "regime.path.restriction.noSearchML": {
        "zh": "Regime 路径不允许携带搜索或 ML 模型配置",
        "en": "Regime path does not allow search or ML model configurations."
    },
    "page.title.multiStockEntry": {
        "zh": "多股入口页\n==========",
        "en": "Multi-Stock Entry"
    },
    "parameter.atr.period": {
        "zh": "ATR 周期",
        "en": "ATR Period"
    },
    "threshold.exitScore": {
        "zh": "出场评分阈值",
        "en": "Exit Score Threshold"
    },
    "task.normalizeReportJson": {
        "zh": "把 report.json 归一成页面消费结构，并兜住旧 run 的缺字段情况。",
        "en": "Normalize report.json into page-consumable structure, handling missing fields from old runs."
    },
    "analysis.flow.summaryFirst": {
        "zh": "先用摘要数字回答股票池规模、样本窗口和结果结构，再进入明细表与图表区。",
        "en": "First present summary numbers for pool size, sample window, and result structure, then proceed to detailed tables and charts."
    },
    "feedback.placeholder": {
        "zh": "请描述你遇到的问题或建议...",
        "en": "Describe your issue or suggestion..."
    },
    "action.startMultiStockAnalysis": {
        "zh": "开始多股分析",
        "en": "Start Multi-Stock Analysis"
    },
    "step.regimePath": {
        "zh": "Step 2 · Regime 路径",
        "en": "Step 2 · Regime Path"
    },
    "stockPool.warning.removeAfterAdd": {
        "zh": "当前股票池仅剩 2 个标的；先在右侧添加新股票，再执行移除。",
        "en": "Only 2 symbols remain in the pool. Add new stocks on the right before removing."
    },
    "fsm.path.description": {
        "zh": "FSM 路径会先在训练集拟合 FA，再进入 FSM 基础策略。",
        "en": "FSM path first fits FA on the training set, then proceeds to the base FSM strategy."
    },
    "portfolio.totalReturn": {
        "zh": "组合总收益",
        "en": "Portfolio Total Return"
    },
    "workflow.generateBeforeWalkForward": {
        "zh": "请先生成当前策略，再执行 Walk-Forward。",
        "en": "Please generate the current strategy first, then run Walk-Forward."
    },
    "performance.topPerformer": {
        "zh": "最佳表现股票",
        "en": "Top Performer"
    },
    "indicator.rsi.status": {
        "zh": "RSI 状态",
        "en": "RSI Status"
    },
    "data.download.fallbackByCode": {
        "zh": "未找到名称索引匹配，将直接按该代码尝试下载。",
        "en": "No name index match found. Will attempt download by code directly."
    },
    "result.mainChart.description": {
        "zh": "结果主图在投资组合模拟和周期收益率热图之间切换；投资组合模拟现复用单股结果区的共享净值/回撤组件，组合 KPI 摘要和个股表现表保持固定。",
        "en": "Main result chart toggles between portfolio simulation and period return heatmap. Portfolio simulation reuses shared equity/drawdown components from single-stock results. Portfolio KPI summary and individual performance table remain fixed."
    },
    "action.viewTradePoints": {
        "zh": "买卖点查看",
        "en": "View Trade Points"
    },
    "report.html.generated": {
        "zh": "HTML 报告已生成。",
        "en": "HTML report generated."
    },
    "kpi.sharpe": {
        "zh": "夏普",
        "en": "Sharpe"
    },
    "testSet.tradingSignals": {
        "zh": "测试集交易信号",
        "en": "Test Set Trading Signals"
    },
    "comparison.stockList.description": {
        "zh": "这里保留待比较股票的轻量行列表。上传文件会在开始分析时一起并入结果。",
        "en": "Lightweight list of stocks for comparison. Uploaded files will be merged into results when analysis starts."
    },
    "import.csv.description": {
        "zh": "每个 CSV 会被视为一个独立标的，文件名会自动转换成导入标识。",
        "en": "Each CSV is treated as an independent symbol. Filename will be auto-converted to import identifier."
    },
    "score": {
        "zh": "评分",
        "en": "Score"
    },
    "ml.filter.quality.noData": {
        "zh": "当前策略路径没有可展示的 ML 过滤质量指标。",
        "en": "No ML filter quality metrics available for the current strategy path."
    },
    "kpi.cumulativeReturn": {
        "zh": "累计收益：",
        "en": "Cumulative Return:"
    },
    "evaluation.kpi.displayOptions": {
        "zh": "评估区 KPI 展示：kind = pct | sharpe | ratio | days",
        "en": "Evaluation KPI display: kind = pct | sharpe | ratio | days"
    },
    "walkForward.closed": {
        "zh": "已关闭 Walk-Forward 回测。",
        "en": "Walk-Forward backtest closed."
    },
    "regime.path.restriction.noBaselineSearchML": {
        "zh": "Regime 路径不允许启用 Baseline / Search / ML 选项",
        "en": "Regime path does not allow enabling Baseline / Search / ML options."
    },
    "report.v1.limitedEmbed": {
        "zh": "<p class='analysis-section-copy'>v1 只展示条目摘要并提供文件下载，不在应用内嵌入整页 HTML。</p>",
        "en": "<p class='analysis-section-copy'>v1 only shows entry summaries and provides file downloads, without embedding full HTML pages in-app.</p>"
    },
    "data.loading": {
        "zh": "数据...",
        "en": "Data..."
    },
    "latest.change": {
        "zh": "最新涨跌",
        "en": "Latest Change"
    },
    "signal.bullish.targetPosition": {
        "zh": "最新信号偏多，目标仓位",
        "en": "Latest signal bullish, target position"
    },
    "range.nearLow": {
        "zh": "靠近区间低位",
        "en": "Near range low"
    },
    "trainingSet.end": {
        "zh": "训练集截止",
        "en": "Training Set End"
    },
    "chart.riskReturnScatter": {
        "zh": "风险收益散点图",
        "en": "Risk-Return Scatter Plot"
    },
    "passRate": {
        "zh": "通过率",
        "en": "Pass Rate"
    },
    "section.factorScoreParameters": {
        "zh": "**因子评分参数**",
        "en": "**Factor Score Parameters**"
    },
    "duration.1week": {
        "zh": "1周",
        "en": "1 Week"
    },
    "file.selected": {
        "zh": "已选择文件：",
        "en": "Selected file:"
    },
    "range.mid": {
        "zh": "处于区间中段",
        "en": "Mid-range"
    },
    "metrics.correlationCoefficient": {
        "zh": "相关系数",
        "en": "Correlation Coefficient"
    },
    "panel.basicInfo": {
        "zh": "基础信息",
        "en": "Basic Info"
    },
    "model.bestModel": {
        "zh": "最佳模型",
        "en": "Best Model"
    },
    "data.abnormalSamples": {
        "zh": "异常样本",
        "en": "Anomalous Samples"
    },
    "algorithm.adaptivePathDescription": {
        "zh": "Adaptive 路径会先预测离散 state，再按 state 在 baseline / SM / FSM 候选中动态切换。",
        "en": "The Adaptive path first predicts discrete states, then dynamically switches between baseline/SM/FSM candidates based on the state."
    },
    "action.addStock": {
        "zh": "添加股票",
        "en": "Add Stock"
    },
    "metrics.bestScore": {
        "zh": "最佳分数",
        "en": "Best Score"
    },
    "modelEvaluation.section.searchMethodSummary": {
        "zh": "搜索方法汇总",
        "en": "Search Method Summary"
    },
    "home.hero.title": {
        "zh": "让股票策略入口成为真正的产品首页。",
        "en": "Turn the stock strategy entry into a real product homepage."
    },
    "home.hero.copy": {
        "zh": "从市场背景与清晰入口开始，再进入现有的单股或多股分析流程。重点不是增加面板，而是让研究路径一目了然。",
        "en": "Start with market context and clear entry actions, then hand off to the existing single-stock or multi-stock analysis flow. The goal is not more panels, but a research path that is readable at a glance."
    },
    "entry.multi.title": {
        "zh": "先建立股票池，再进入多股分析。",
        "en": "Assemble the stock pool first, then enter multi-stock analysis."
    },
    "single.strategy.entryCopy": {
        "zh": "先确定课程基线、搜索或 Regime 路径，再填写其余配置；页面不再默认预计算所有模型结果。",
        "en": "Decide whether you are on the course baseline path, search path, or regime path before filling in the remaining configuration below. The page no longer precomputes every model result by default."
    },
    "home.hero.note.1": {
        "zh": "先阅读市场背景，再确定研究从单只股票还是股票池开始。",
        "en": "Read market context first, then decide which stock or stock group this research should start from."
    },
    "home.hero.note.2": {
        "zh": "搜索、上传和推荐保持在同一页面逻辑中，不再把用户推回后台式控制区。",
        "en": "Search, upload, and recommendation stay in one page grammar instead of pushing the user back into an admin-style control area."
    },
    "home.hero.note.3": {
        "zh": "核心分析逻辑保持不变，调整的是入口节奏、视觉层级和站点体验。",
        "en": "The core analysis logic stays the same. What changes is the entry rhythm, visual hierarchy, and site feel."
    },
    "modelEvaluation.section.robustnessSummary": {
        "zh": "稳健性汇总",
        "en": "Robustness Summary"
    },
    "home.market.copy": {
        "zh": "指数快照与推荐入口固定在右侧，让研究先完成背景判断，再进入具体操作。",
        "en": "Index snapshots and recommendation entry stay fixed on the right so research starts from context judgment before moving into specific actions."
    },
    "home.market.us": {
        "zh": "纳斯达克 / 标普 500 / 道琼斯",
        "en": "Nasdaq / S&P 500 / Dow"
    },
    "home.market.cn": {
        "zh": "上证 / 深证 / 创业板",
        "en": "SSE / SZSE / ChiNext"
    },
    "modelEvaluation.section.familySummary": {
        "zh": "模型族汇总",
        "en": "Family Summary"
    },
    "home.workflow.copy": {
        "zh": "入口页只负责设定上下文，参数、工作流与 artifact 在分析页继续完成。",
        "en": "The entry page only sets context. Parameters, workflow, and artifacts continue on the analysis page."
    },
    "home.progress.copy": {
        "zh": "站点已具备真实的单股与多股路由，入口页与主分析顺序保持一致。",
        "en": "The site now has real single-stock and multi-stock routes, with entry pages aligned to the main analysis sequence."
    },
    "home.board.title": {
        "zh": "市场背景 → 入口操作 → 分析",
        "en": "Market Context ? Entry Actions ? Analysis"
    },
    "home.board.copy": {
        "zh": "左侧承载叙事与主要操作，右侧用一个展示板说明工具使用方式。单股与多股共用同一路由壳层，让页面更像产品而不是面板堆叠。",
        "en": "The left side carries narrative and the main CTA. The right side uses one large board to explain how the tool is used. Single-stock and multi-stock share the same route shell so the page reads like a product, not a pile of panels."
    },
    "home.board.footnote": {
        "zh": "推荐入口已合并到主流程，不再扩展成独立的悬浮面板。",
        "en": "Recommendation entry is already merged into the main flow rather than growing into a separate floating panel."
    },
    "home.support.multi.copy": {
        "zh": "适合先整理股票池，再进入横向比较、组合模拟和策略汇总。",
        "en": "Best for organizing a stock pool first, then moving into lateral comparison, portfolio simulation, and strategy-level summaries."
    },
    "home.support.unified.copy": {
        "zh": "首页和入口页先建立研究上下文，分析页延续现有工作流，不引入第二套逻辑。",
        "en": "Home and entry pages establish research context first, while analysis pages continue the existing workflow without introducing a second logic system."
    },
    "metric.mlPrecision": {
        "zh": "ML 精确率：",
        "en": "ML Precision: "
    },
    "metric.precision": {
        "zh": "Precision",
        "en": "Precision"
    },
    "metric.recall": {
        "zh": "Recall",
        "en": "Recall"
    },
    "metric.f1": {
        "zh": "F1",
        "en": "F1"
    },
    "metric.prAuc": {
        "zh": "PR-AUC",
        "en": "PR-AUC"
    },
    "walkForward.summary": {
        "zh": "Walk-Forward 收益：{strategy_return} | 买入持有收益：{buy_hold_return}",
        "en": "Walk-Forward return: {strategy_return} | Buy-and-hold return: {buy_hold_return}"
    },
    "surface.resultBoard": {
        "zh": "结果板",
        "en": "Result Board"
    },
    "signal.sellLabel": {
        "zh": "卖出",
        "en": "Sell"
    },
    "single.strategy.workspaceCopy": {
        "zh": "左侧保留模型控制台，右侧保留结果板。继续使用 W5 冻结的 request、lineage、artifact、回测与导出链路；本轮只重构交互壳层和结果组织。",
        "en": "The left side stays as the model console and the right side stays as the result board. The W5-frozen request, lineage, artifact, backtest, and export chain remains in use; this round only restructures the interaction shell and result organization."
    },
    "single.strategy.workspaceKicker": {
        "zh": "策略工作台",
        "en": "Strategy Workspace"
    },
    "single.strategy.controlKicker": {
        "zh": "模型路径",
        "en": "Model Path"
    },
    "single.strategy.controlCopy": {
        "zh": "训练窗口、模型路径、生成动作与策略库集中在一个控制区；股票或训练比例变化时，workspace 会根据上下文重建。",
        "en": "The training window, model path, generate action, and strategy library are all grouped in one control surface. When the stock or train ratio changes, the workspace is rebuilt from context."
    },
    "single.strategy.libraryCopy": {
        "zh": "生成操作只提交新的 <code>current_artifact</code>；保存后才进入会话策略库，供结果板比较多条策略。",
        "en": "Generate only submits a new <code>current_artifact</code>. It enters the in-session strategy library only after saving, so the result board can compare multiple strategies."
    },
    "single.strategy.resultPlaceholderCopy": {
        "zh": "左侧模型路径完成后，此区域承接当前策略摘要、净值与回撤、月度收益、交易点、Walk-Forward 和比较视图。",
        "en": "Once the model path is completed on the left, this area takes over the current strategy summary, equity/drawdown, monthly returns, trade points, Walk-Forward, and comparison views."
    },
    "single.strategy.workflowCopy": {
        "zh": "保留 W5 分阶段 artifact 语义，明确当前结果来自 baseline、search、regime 还是最终 ML 过滤提交。",
        "en": "W5 staged artifact semantics are kept so it stays clear whether the current result comes from baseline, search, regime, or the final ML-filtered submission."
    },
    "single.strategy.currentArtifactCopy": {
        "zh": "当前已提交策略结果：{label}。{action}",
        "en": "Current submitted strategy result: {label}. {action}"
    },
    "entry.marketSnapshotFailed": {
        "zh": "市场快照加载失败：{error}",
        "en": "Failed to load the market snapshot: {error}"
    },
    "entry.single.title": {
        "zh": "先锁定一个标的，再进入单股分析。",
        "en": "Lock in one target before entering single-stock analysis."
    },
    "entry.single.copy": {
        "zh": "此入口页只负责建立研究上下文。左侧用于切换市场、搜索与上传，右侧持续显示市场快照和推荐入口。",
        "en": "This entry page only sets up the research context. Use the left side for market switching, search, and uploads, while the right side keeps the current market snapshot and recommendation entry visible."
    },
    "entry.single.helper": {
        "zh": "入口页只组织研究标的与市场背景；进入主分析页后，现有策略工作流、已保存 artifact 与后续分析保持不变。",
        "en": "The entry page only organizes the research target and market context. After you enter the main analysis page, the existing strategy workflow, saved artifacts, and downstream analysis stay intact."
    },
    "entry.multi.copy": {
        "zh": "左侧用于整理待比较股票，右侧保留市场快照和推荐入口；搜索、上传与推荐均汇入同一个分析列表。",
        "en": "Use the left side to organize the stocks to compare, while the right side keeps the market snapshot and recommendation add-ons visible. Search, uploads, and recommendations all flow into the same analysis list."
    },
    "entry.multi.helper": {
        "zh": "入口页只负责整理股票池；进入主分析页后，现有多股图表、组合模拟和后续分析逻辑保持不变。",
        "en": "The entry page only organizes the stock pool. After you enter the main analysis page, the current multi-stock charts, portfolio simulation, and follow-up analysis logic continue unchanged."
    },
    "single.strategy.configCopy": {
        "zh": "按 W5 冻结语义继续配置 baseline、简化状态机、完整状态机、search 与 regime 路径，不在此处改变底层参数 contract。",
        "en": "Continue configuring the baseline, simplified state machine, full state machine, search, and regime paths under the frozen W5 semantics. Do not change the underlying parameter contract here."
    },
    "message.currentUploadedData": {
        "zh": "当前使用上传数据：{name}",
        "en": "Using uploaded data: {name}"
    },
    "message.dataFetchFailed": {
        "zh": "无法获取 {symbol} 的数据，请检查网络连接。",
        "en": "Unable to fetch data for {symbol}. Please check the network connection."
    },
    "message.uploadReadFailed": {
        "zh": "读取上传文件 {name} 失败：{error}",
        "en": "Failed to read uploaded file {name}: {error}"
    },
    "modelEvaluation.quantstatsCount": {
        "zh": "{count} 份 tear sheet",
        "en": "{count} tear sheets"
    },
    "modelEvaluation.title": {
        "zh": "以只读方式浏览已有模型研究结果。",
        "en": "Browse existing model research results in read-only mode."
    },
    "modelEvaluation.copy": {
        "zh": "此页面只读取本地 <code>model-test/outputs</code> 中的已有研究产物，不触发研究执行；默认展示最新可读 run，并支持切换。",
        "en": "This page only reads existing research artifacts under local <code>model-test/outputs</code> and does not trigger any research execution. It shows the latest readable run by default and lets you switch between runs."
    },
    "modelEvaluation.section.failures": {
        "zh": "失败与降级样本",
        "en": "Failures / Degraded Samples"
    },
    "modelEvaluation.dataSourceMeta": {
        "zh": "report.json / mlflow_run.json",
        "en": "report.json / mlflow_run.json"
    },
    "modelEvaluation.reportFile": {
        "zh": "报告文件：{path}",
        "en": "Report file: {path}"
    },
    "modelEvaluation.lastUpdated": {
        "zh": "最近更新：{time}",
        "en": "Last updated {time}"
    },
    "modelEvaluation.tab.observability": {
        "zh": "QuantStats / MLflow",
        "en": "QuantStats / MLflow"
    },
    "modelEvaluation.quantstatsPooledRun": {
        "zh": "汇总运行数 {count}",
        "en": "Pooled run {count}"
    },
    "model.idLabel": {
        "zh": "模型 ID {value}",
        "en": "Model ID {value}"
    },
    "score.label": {
        "zh": "分数 {value}",
        "en": "Score {value}"
    },
    "mlflow.runId": {
        "zh": "运行 ID",
        "en": "Run ID"
    },
    "mlflow.artifactUri": {
        "zh": "产物 URI",
        "en": "Artifact URI"
    },
    "modelEvaluation.runMeta": {
        "zh": "运行：{run_id}",
        "en": "Run: {run_id}"
    },
    "params.adjustable": {
        "zh": "可调参数",
        "en": "Adjustable Parameters"
    },
    "params.adjust.description": {
        "zh": "调整策略核心参数。修改后点击「生成策略」重新运行。",
        "en": "Adjust core strategy parameters. Click 'Generate Strategy' to re-run after changes."
    },
    "params.indicator_settings": {
        "zh": "指标设置",
        "en": "Indicator Settings"
    },
    "params.factor_weights": {
        "zh": "因子权重",
        "en": "Factor Weights"
    },
    "params.entry_exit": {
        "zh": "入场/出场阈值",
        "en": "Entry / Exit Thresholds"
    },
    "params.risk_control": {
        "zh": "风险控制",
        "en": "Risk Control"
    },
    "export.stock_profile": {
        "zh": "股票概览",
        "en": "Stock Profile"
    },
    "export.model_analysis": {
        "zh": "模型对比分析",
        "en": "Model Comparison Analysis"
    },
    "export.model_strengths": {
        "zh": "优势",
        "en": "Strengths"
    },
    "export.model_weaknesses": {
        "zh": "劣势",
        "en": "Weaknesses"
    },
    "export.model_verdict": {
        "zh": "综合评价",
        "en": "Overall Verdict"
    },
    "export.why_underperform": {
        "zh": "为什么该模型表现欠佳",
        "en": "Why this model underperforms"
    },
    "export.stock_info": {
        "zh": "基本信息",
        "en": "Basic Information"
    },
    "export.data_coverage": {
        "zh": "数据覆盖",
        "en": "Data Coverage"
    },
    "export.price_range": {
        "zh": "价格区间",
        "en": "Price Range"
    },
    "export.model_interpretation": {
        "zh": "模型差异解读",
        "en": "Model Difference Interpretation"
    },
    "export.best_model": {
        "zh": "最佳模型",
        "en": "Best Model"
    },
    "export.ranking_explanation": {
        "zh": "排名解读",
        "en": "Ranking Explanation"
    },
    "params.multi_stock_adjust": {
        "zh": "策略参数调整",
        "en": "Strategy Parameter Adjustment"
    },
    "params.multi_stock_adjust.description": {
        "zh": "调整组合策略的信号权重和阈值参数。修改后点击「生成组合策略」重新运行。",
        "en": "Adjust signal weights and threshold parameters for portfolio strategy. Click 'Generate Portfolio' to re-run."
    },
    "award.home.kicker": {"zh": "证据优先的量化研究", "en": "Evidence-first quantitative research"},
    "award.home.title": {"zh": "把价格数据变成经得起追问的双市场策略研究。", "en": "Turn price data into a cross-market strategy study that can withstand scrutiny."},
    "award.home.copy": {"zh": "从清晰的研究对象开始，在统一口径下比较美国与中国 A 股市场，并将每项结论回溯到可复现的实验输出。", "en": "Start with a clear research target, compare US and China A-share markets under one protocol, and trace every conclusion back to reproducible evidence."},
    "award.home.action.kicker": {"zh": "选择研究入口", "en": "Choose a research entry"},
    "award.home.action.title": {"zh": "先定义问题，再运行分析。", "en": "Define the question, then run the analysis."},
    "award.home.action.copy": {"zh": "单股用于解释一个标的；多股用于检验策略在股票池和市场之间是否仍成立。", "en": "Use one stock to explain a target; use a stock universe to test whether a strategy holds across instruments and markets."},
    "award.home.cta.single": {"zh": "分析一只股票", "en": "Analyze one stock"},
    "award.home.cta.multi": {"zh": "比较股票池", "en": "Compare a stock universe"},
    "award.home.note.problem": {"zh": "先明确研究的是一个标的、一个股票池，还是一个跨市场问题。", "en": "First decide whether the question concerns one target, a stock pool, or a cross-market comparison."},
    "award.home.note.method": {"zh": "市场、数据和策略路径在进入分析前被显式设定。", "en": "Market, data source, and strategy path are made explicit before analysis begins."},
    "award.home.note.evidence": {"zh": "结果页面保留指标、样本与研究产物，方便复核而不是只展示排名。", "en": "Result surfaces retain metrics, samples, and research artifacts for review—not just a ranking."},
    "award.home.board.kicker": {"zh": "研究视角", "en": "Research lens"},
    "award.home.market.title": {"zh": "两个市场，同一研究问题", "en": "Two markets, one research question"},
    "award.home.market.copy": {"zh": "US 与 CN_A 从各自市场上下文开始，但结论必须明确说明样本与限制。", "en": "US and CN_A begin with their own market context, while conclusions must state their sample and limitations."},
    "award.home.market.us": {"zh": "美股研究入口", "en": "US market entry"},
    "award.home.market.cn": {"zh": "中国 A 股研究入口", "en": "China A-share entry"},
    "award.home.market.rule1": {"zh": "先看市场快照", "en": "Read the market snapshot first"},
    "award.home.market.rule2": {"zh": "再锁定研究标的", "en": "Then lock the research target"},
    "award.home.protocol.title": {"zh": "固定研究口径", "en": "A fixed research protocol"},
    "award.home.protocol.copy": {"zh": "数据、策略、评估与限制按同一条链路组织。", "en": "Data, strategy, evaluation, and limitations follow one visible chain."},
    "award.home.output.title": {"zh": "可追溯的结论", "en": "Traceable conclusions"},
    "award.home.output.copy": {"zh": "网页、报告与实验输出共同承载证据。", "en": "The page, report, and experiment outputs carry the evidence together."},
    "award.home.flow.kicker": {"zh": "研究路径", "en": "Research path"},
    "award.home.flow.title": {"zh": "让证据先于推荐出现。", "en": "Put evidence before recommendation."},
    "award.home.flow.copy": {"zh": "每一步都从市场与样本出发，再走向可解释的策略比较和结果浏览。", "en": "Each step begins with market and sample context, then moves to interpretable strategy comparison and result review."},
    "award.home.flow.market": {"zh": "选择市场", "en": "Choose market"},
    "award.home.flow.target": {"zh": "定义标的", "en": "Define target"},
    "award.home.flow.experiment": {"zh": "运行实验", "en": "Run experiment"},
    "award.home.flow.evidence": {"zh": "检查证据", "en": "Inspect evidence"},
    "award.home.flow.footnote": {"zh": "策略建议只有在能回溯到样本、指标与失败记录时才有意义。", "en": "A strategy recommendation only matters when it can be traced to samples, metrics, and failure records."},
    "award.home.support.single.title": {"zh": "单股研究", "en": "Single-stock research"},
    "award.home.support.single.copy": {"zh": "为一个具体标的建立市场、数据与策略上下文，再进入完整工作流。", "en": "Build market, data, and strategy context for one specific target before entering the full workflow."},
    "award.home.support.single.cta": {"zh": "浏览研究证据", "en": "Browse research evidence"},
    "award.home.support.multi.title": {"zh": "股票池与组合", "en": "Stock pools and portfolios"},
    "award.home.support.multi.copy": {"zh": "把搜索、推荐与上传来源合并为一个可管理的比较股票池。", "en": "Combine search, recommendations, and uploads into one manageable comparison universe."},
    "award.home.support.unified.title": {"zh": "统一的结论边界", "en": "One boundary for conclusions"},
    "award.home.support.unified.copy": {"zh": "入口页负责定义问题；分析页和只读研究页负责展示结果、证据与局限。", "en": "Entry pages define the question; analysis and read-only research pages present results, evidence, and limits."},
    "award.entry.step.market": {"zh": "市场", "en": "Market"},
    "award.entry.single.kicker": {"zh": "单股研究入口", "en": "Single-stock research entry"},
    "award.entry.single.title": {"zh": "单股策略分析", "en": "Single-Stock Strategy Analysis"},
    "award.entry.single.copy": {"zh": "按市场、标的与数据的顺序组织研究上下文；右侧始终保留市场快照和推荐来源作为判断依据。", "en": "Organize research context in market, target, and data order; keep the market snapshot and recommendation source visible on the right."},
    "award.entry.multi.kicker": {"zh": "多股研究入口", "en": "Multi-stock research entry"},
    "award.entry.multi.title": {"zh": "多股策略分析", "en": "Multi-Stock Strategy Analysis"},
    "award.entry.multi.copy": {"zh": "搜索、推荐和上传数据汇入同一个股票池；进入分析后再做比较、组合模拟和结果解释。", "en": "Search, recommendations, and uploads enter one stock universe; comparison, portfolio simulation, and interpretation follow in analysis."},
    "award.entry.actionCard": {"zh": "研究设置", "en": "Research setup"},
    "award.entry.showcaseBoard": {"zh": "市场证据板", "en": "Market evidence board"},
    "award.entry.step.target": {"zh": "标的", "en": "Target"},
    "award.entry.step.data": {"zh": "数据", "en": "Data"},
    "award.entry.step.analyze": {"zh": "开始分析", "en": "Analyze"},
    "award.entry.marketEmpty": {"zh": "暂无可展示的市场快照。", "en": "No market snapshot is available right now."},
    "award.entry.recommendationSource": {"zh": "推荐来源", "en": "Recommendation source"},
    "award.entry.quote": {"zh": "现价 {price} · 涨跌 {change}", "en": "Price {price} · Change {change}"},
    "award.entry.heatQuote": {"zh": "热度 {heat} · 涨跌 {change}", "en": "Heat {heat} · Change {change}"},
    "recommendation.source.hotSearchToday": {"zh": "百度股市通今日热搜", "en": "Baidu Finance hot searches today"},
    "recommendation.source.aRealtimeMovers": {"zh": "A 股实时涨幅榜（热搜不可用）", "en": "A-share real-time movers (hot search unavailable)"},
    "recommendation.source.usRealtimeMovers": {"zh": "知名美股实时涨幅榜（热搜不可用）", "en": "Real-time movers among well-known US stocks (hot search unavailable)"},
    "recommendation.source.unavailable": {"zh": "暂时无法获取推荐股票", "en": "Recommended stocks are temporarily unavailable"},
    "entry.csvRequirements.trigger": {"zh": "查看标准化 CSV 数据要求", "en": "View standardized CSV requirements"},
    "entry.csvRequirements.title": {"zh": "上传文件需要满足什么格式？", "en": "What format should the uploaded file use?"},
    "entry.csvRequirements.body": {
        "zh": "- 必需列：`date`、`open`、`high`、`low`、`close`、`volume`。\n- `date` 必须是可解析的交易日期；系统会按日期升序排列，同日重复记录保留最后一条。\n- 开盘、最高、最低和收盘价必须为正数且不能缺失；成交量必须非负，标准单位为“股”。\n- 支持常见别名，例如 `trade_date`、`datetime`、`日期`、`开盘`、`最高`、`最低`、`收盘`、`vol`、`成交量`。\n- 如果 A 股来源以“手”记录成交量，请先乘以 100 转换为“股”。",
        "en": "- Required columns: `date`, `open`, `high`, `low`, `close`, and `volume`.\n- `date` must be a parseable trading date. Rows are sorted ascending, and the last duplicate for a date is kept.\n- Open, high, low, and close must be positive and non-missing. Volume must be non-negative and expressed in shares.\n- Common aliases are accepted, including `trade_date`, `datetime`, `日期`, `开盘`, `最高`, `最低`, `收盘`, `vol`, and `成交量`.\n- If an A-share source reports volume in lots, multiply it by 100 before uploading."
    },
    "entry.csvRequirements.source": {
        "zh": "一般可从券商客户端、行情终端或数据平台导出日线历史行情 CSV；上传更适合自有、清洗后或离线数据。",
        "en": "Daily historical CSV files can usually be exported from a broker, market terminal, or data provider. Uploads are best suited to proprietary, cleaned, or offline data."
    },
    "award.entry.importId": {"zh": "导入标识：{symbol}", "en": "Import ID: {symbol}"},
    "award.entry.selectionSource": {"zh": "来源：搜索或推荐", "en": "Source: search or recommendation"},
    "award.entry.poolCount": {"zh": "当前待分析数量：{total} 个标的（手动或推荐 {selected} 个，上传 {uploaded} 个）。", "en": "Ready to analyze: {total} instruments ({selected} selected or recommended, {uploaded} uploaded)."},
    "award.common.noData": {"zh": "暂无数据", "en": "N/A"},
}

def set_ui_language(language: str) -> None:
    normalized = _normalize_ui_language(language)
    st.session_state[UI_LANGUAGE_STATE_KEY] = normalized
    try:
        if _normalize_ui_language(st.query_params.get("lang"), default="") != normalized:
            st.query_params["lang"] = normalized
    except (AttributeError, KeyError, TypeError):
        pass

def get_ui_language() -> str:
    query_language = ""
    try:
        query_value = st.query_params.get("lang")
        if isinstance(query_value, (list, tuple)):
            query_value = query_value[-1] if query_value else ""
        query_language = _normalize_ui_language(query_value, default="")
    except (AttributeError, KeyError, TypeError):
        pass

    if query_language:
        st.session_state[UI_LANGUAGE_STATE_KEY] = query_language
        return query_language

    session_language = _normalize_ui_language(
        st.session_state.get(UI_LANGUAGE_STATE_KEY),
        default="en",
    )
    st.session_state[UI_LANGUAGE_STATE_KEY] = session_language
    return session_language

def _normalize_ui_language(language: object, *, default: str = "en") -> str:
    normalized = str(language or "").strip().lower().replace("_", "-")
    if normalized.startswith("zh"):
        return "zh"
    if normalized.startswith("en"):
        return "en"
    return default

def tr(key: str, **kwargs) -> str:
    lang = get_ui_language()
    
    locale_dict = LOCALES.get(key, {})
    text = locale_dict.get(lang, key)
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
            
    return text

def localize_entity_name(symbol: str, raw_label: str, kind: str = "") -> str:
    lang = get_ui_language()
    if lang == 'en':
        if symbol:
            return symbol
        else:
            return raw_label
            
    return raw_label if raw_label else symbol
