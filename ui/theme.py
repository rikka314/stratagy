"""
共享前端主题层
==============
为 W6 首页、入口页和路由壳层提供暖米白官网式样式。
"""

from __future__ import annotations

import html
from datetime import date as _date, datetime as _datetime
from functools import wraps
from textwrap import dedent

import streamlit as st


BASE_ROUTE_PATH = "/strategy"
UI_LANGUAGE_STATE_KEY = "ui_language"
UI_THEME_STATE_KEY = "ui_theme"

_TRANSLATION_PAIRS = [
    ("把股票策略入口做成真正的网站首页。", "Turn the stock strategy entry into a real website home."),
    ("这个站点先用市场上下文和清楚的入口动作建立研究方向，再把你送进原有单股或多股分析链路。", "This site starts with market context and clear entry actions, then routes you into the existing single-stock or multi-stock analysis flow."),
    ("目标不是把更多面板堆上来，而是让研究路径一眼就能看懂。", "The goal is not to stack more panels, but to make the research path obvious at a glance."),
    ("单股模式适合围绕一个标的持续展开， 多股模式适合先组织股票池再看横向比较、组合结果和后续策略摘要。", "Single-stock mode is for sustained work around one symbol; multi-stock mode is for building a basket first and then reviewing cross-sectional comparisons, portfolio results, and strategy summaries."),
    ("先看市场上下文，再决定这次研究到底从哪只股票或哪组股票开始。", "Read market context first, then decide which stock or basket this study should start from."),
    ("搜索、上传和推荐入口都保持在同一条页面语法里，不把用户推回后台式操作区。", "Search, upload, and recommendation entry points stay inside the same page grammar instead of pushing users back into a dashboard-style control area."),
    ("主分析页逻辑不变，变化的是入口节奏、视觉层级和网站感。", "The main analysis logic stays intact; what changes is the entry rhythm, visual hierarchy, and product-site feel."),
    ("这个入口页只负责建立研究上下文。左侧完成市场切换、搜索和上传，右侧持续展示当前市场快照与推荐入口。", "This entry page only establishes research context. The left side handles market switching, search, and upload, while the right side keeps the current market snapshot and recommended entry points visible."),
    ("左侧负责把待比较股票整理清楚，右侧持续提供当前市场快照和推荐补充入口。 搜索、上传和推荐最终都会汇到同一个待分析列表。", "The left side organizes the stock pool to compare, while the right side continuously supplies the current market snapshot and recommendation add-ons. Search, upload, and recommendations all merge into the same analysis list."),
    ("左侧固定为模型控制台，右侧固定为结果展示板。W5 已冻结的 request、lineage、artifact、回测和导出链路继续复用，本轮只重构交互壳层与结果组织方式。", "The left side stays as the model console and the right side stays as the result board. The W5-frozen request, lineage, artifact, backtest, and export pipeline are reused; this round only refactors the interaction shell and result organization."),
    ("左侧固定为模型控制台与组合搜索，右侧固定为结果图区、组合 KPI 摘要和个股表现表，对齐第七周第 8 项的“左控台 / 右结果区”结构。", "The left side stays as the model console and portfolio search, while the right side stays as the result board, portfolio KPI summary, and stock-level performance table, matching the Week 7 left-console/right-result structure."),
    ("顶部先给出股票池摘要和明细表，右侧主图在价格对比、相对强弱、风险收益、最新因子评分和相关性之间切换，不再顺序堆叠成长页面。", "The top area shows a stock-pool summary and detail table first, while the main chart on the right switches among price comparison, relative strength, risk-return, latest factor scores, and correlation instead of stacking everything into a long page."),
    ("左侧用文字快速交代当前标的状态，右侧保留高密度 K 线主图和指标小图，训练/测试边界在行情图里保持可见。", "The left side summarizes the current symbol in text, while the right side keeps the high-density candlestick chart and indicator mini-chart visible, with the train/test boundary preserved in the market chart."),
    ("当前站点已经具备单股与多股两条真实路由，入口和主分析页顺序一致。", "The site already has real single-stock and multi-stock routes, and the entry-to-analysis sequence is consistent."),
    ("入口页只负责把研究对象和市场背景整理清楚。进入主分析页后，原有策略工作流、artifact 和下游分析继续保持不变。", "The entry page only organizes the research target and market background. After entering the main analysis page, the existing strategy workflow, artifacts, and downstream analysis remain unchanged."),
    ("入口页只负责把股票池整理清楚。进入主分析页后，现有多股图表、组合模拟和后续分析逻辑继续沿用。", "The entry page only organizes the stock pool. After entering the main analysis page, the existing multi-stock charts, portfolio simulation, and downstream analysis continue to be reused."),
    ("字段缺失会回退为 N/A，不会阻断图表和后续策略工作流。", "Missing fields fall back to N/A and will not block charts or the downstream strategy workflow."),
    ("字段缺失会回退为 N/A，不会阻断页面其余部分。", "Missing fields fall back to N/A and will not block the rest of the page."),
    ("模型还没准备好。", "The model is not ready yet."),
    ("当前没有可展示结果。", "No results are available to display."),
    ("暂无可展示结果。", "No results are available to display."),
    ("暂无数据", "N/A"),
    ("正在加载最新市场数据。", "Loading the latest market data."),
    ("暂时无法获取推荐股票。", "Recommended stocks are temporarily unavailable."),
    ("没有找到匹配股票。", "No matching stock was found."),
    ("研究市场", "Research market"),
    ("输入股票名称或代码", "Enter a stock name or ticker"),
    ("例如：AAPL / Apple / 贵州茅台 / 600519", "For example: AAPL / Apple / Kweichow Moutai / 600519"),
    ("例如：AAPL / NVDA / 贵州茅台 / 600519", "For example: AAPL / NVDA / Kweichow Moutai / 600519"),
    ("匹配结果", "Matches"),
    ("开始单股分析", "Start single-stock analysis"),
    ("开始多股分析", "Start multi-stock analysis"),
    ("加入股票池", "Add to stock pool"),
    ("搜索并确认标的", "Search and confirm a symbol"),
    ("搜索并加入股票", "Search and add stocks"),
    ("上传本地单股 CSV", "Upload a local single-stock CSV"),
    ("上传多个本地 CSV", "Upload multiple local CSVs"),
    ("上传单只股票 CSV", "Upload a single-stock CSV"),
    ("上传多个单股 CSV", "Upload multiple single-stock CSVs"),
    ("当前已选股票", "Selected stocks"),
    ("当前准备分析：", "Ready to analyze: "),
    ("已选择文件：", "Selected file: "),
    ("还没有选择上传文件。", "No upload file has been selected yet."),
    ("支持名称或代码检索。没有索引命中时，也会按代码直接进入分析。", "Search by name or ticker. If the index misses, the app can still analyze directly by ticker."),
    ("支持名称或代码检索。命中索引后加入股票池；没有索引时也支持按代码直接加入。", "Search by name or ticker. Indexed matches can be added to the pool; when the index misses, the raw ticker can still be added directly."),
    ("如果你已经准备好标准化数据文件，可以直接用上传结果进入分析。", "If you already have a standardized dataset, you can enter analysis directly from the uploaded file."),
    ("每个 CSV 会被视为一个独立标的，文件名会自动转换成导入标识。", "Each CSV is treated as an independent symbol, and the filename is converted into an import identifier automatically."),
    ("当前市场的快照和推荐入口", "Current market snapshot and recommended entry points"),
    ("当前市场的快照与推荐补充", "Current market snapshot and recommendation add-ons"),
    ("当前市场的快照与推荐入口", "Current market snapshot and recommended entry points"),
    ("市场快照", "Market snapshot"),
    ("推荐股票", "Recommended stocks"),
    ("当前推荐口径：", "Current recommendation source: "),
    ("刷新市场快照", "Refresh market snapshot"),
    ("现价", "Price"),
    ("涨跌", "Change"),
    ("导入标识：", "Import id: "),
    ("来源：搜索或推荐加入", "Source: added from search or recommendations"),
    ("分析区切换", "Section switch"),
    ("基础信息", "Basics"),
    ("策略", "Strategy"),
    ("切换股票", "Switch stock"),
    ("股票池操作", "Stock pool actions"),
    ("移除股票", "Remove stock"),
    ("添加股票", "Add stock"),
    ("图表切换", "Chart switch"),
    ("查看图表", "View chart"),
    ("详细对比表", "Detailed comparison table"),
    ("相对强弱基准", "Relative-strength benchmark"),
    ("等权平均", "Equal-weight average"),
    ("策略结果视图", "Strategy result view"),
    ("投资组合模拟", "Portfolio simulation"),
    ("周期收益率热图", "Periodic return heatmap"),
    ("热图周期", "Heatmap period"),
    ("月度", "Monthly"),
    ("季度", "Quarterly"),
    ("年度", "Yearly"),
    ("单股基础信息区", "Single-stock basics"),
    ("多股基础信息区", "Multi-stock basics"),
    ("策略区", "Strategy section"),
    ("多股策略区", "Multi-stock strategy"),
    ("单股主分析页", "Single-stock analysis"),
    ("多股主分析页", "Multi-stock analysis"),
    ("模型控制台", "Model console"),
    ("策略结果区", "Strategy result"),
    ("结果模式", "Result mode"),
    ("当前策略", "Current strategy"),
    ("策略比对", "Strategy comparison"),
    ("保存当前策略", "Save current strategy"),
    ("工作台入口", "Workflow entry"),
    ("模型配置", "Model configuration"),
    ("生成与策略库", "Generate and strategy library"),
    ("生成策略", "Generate strategy"),
    ("结果细看", "Detail view"),
    ("买卖点", "Trade signals"),
    ("买卖点比较", "Trade-signal comparison"),
    ("比对细看", "Comparison detail"),
    ("分析", "Analyze"),
    ("加入", "Add"),
    ("移除", "Remove"),
    ("当前技术快照", "Current technical snapshot"),
    ("当前策略摘要", "Current strategy summary"),
    ("结果板暂未生成", "Result board not generated"),
    ("当前工作流链路", "Current workflow chain"),
    ("策略比对模式", "Strategy comparison mode"),
    ("Walk-Forward 回测", "Walk-forward backtest"),
    ("启用 Walk-Forward", "Enable walk-forward"),
    ("训练窗口（交易日）", "Training window (trading days)"),
    ("测试窗口（交易日）", "Test window (trading days)"),
    ("买卖点查看", "Trade-signal view"),
    ("买卖点比较", "Trade-signal comparison"),
    ("导出分析报告", "Export analysis report"),
    ("报告标题", "Report title"),
    ("包含生成日期", "Include generated date"),
    ("生成并下载HTML报告", "Generate and download HTML report"),
    ("生成并下载 HTML 报告", "Generate and download HTML report"),
    ("核心指标", "Key metrics"),
    ("回测净值 / 回撤", "Backtest equity / drawdown"),
    ("月度收益热图", "Monthly return heatmap"),
    ("指标对比表", "Metric comparison table"),
    ("ML 质量展示", "ML quality view"),
    ("Close", "Close"),
    ("Buy", "Buy"),
    ("Sell", "Sell"),
    ("净值曲线", "Equity curve"),
    ("回撤曲线", "Drawdown curve"),
    ("净值（起始=1.0）", "Equity (start=1.0)"),
    ("回撤", "Drawdown"),
    ("日期", "Date"),
    ("价格（对数）", "Price (log)"),
    ("价格", "Price"),
    ("股票", "Stock"),
    ("股票/模型", "Stock/Model"),
    ("股票代码", "Ticker"),
    ("名称", "Name"),
    ("来源", "Source"),
    ("起始价格", "Start price"),
    ("最新价格", "Latest price"),
    ("总收益率", "Total return"),
    ("年化收益率", "Annualized return"),
    ("最高价", "High"),
    ("最低价", "Low"),
    ("数据天数", "Data days"),
    ("权重", "Weight"),
    ("策略收益", "Strategy return"),
    ("夏普比率", "Sharpe ratio"),
    ("最大回撤", "Max drawdown"),
    ("组合总收益", "Portfolio return"),
    ("组合夏普", "Portfolio Sharpe"),
    ("组合最大回撤", "Portfolio max drawdown"),
    ("买入持有收益", "Buy-and-hold return"),
    ("买入持有夏普", "Buy-and-hold Sharpe"),
    ("买入持有回撤", "Buy-and-hold drawdown"),
    ("多股票价格对比（归一化）", "Normalized multi-stock price comparison"),
    ("股票收益率相关性矩阵（按股票配对计算）", "Stock return correlation matrix (pairwise)"),
    ("相对强弱对比（基准: ", "Relative strength comparison (benchmark: "),
    ("等权平均基准", "Equal-weight benchmark"),
    ("风险-收益散点图（年化）", "Risk-return scatter (annualized)"),
    ("月度收益率热图", "Monthly return heatmap"),
    ("季度收益率热图", "Quarterly return heatmap"),
    ("年度收益率热图", "Yearly return heatmap"),
    ("最新因子评分横向对比", "Latest factor score comparison"),
    ("因子评分", "Factor score"),
    ("评分分位数", "Score percentile"),
    ("评分分位数%", "Score percentile %"),
    ("入场阈值", "Entry threshold"),
    ("起点基准 (100)", "Base line (100)"),
    ("股票（期间收益）", "Stocks (period return)"),
    ("基准线 (RS=1.0)", "Reference line (RS=1.0)"),
    ("1周", "1W"),
    ("1月", "1M"),
    ("3月", "3M"),
    ("6月", "6M"),
    ("1年", "1Y"),
    ("全部", "All"),
    ("相对强弱", "Relative strength"),
    ("年化波动率（风险）%", "Annualized volatility (risk) %"),
    ("年化收益率（回报）%", "Annualized return %"),
    ("时间周期", "Time period"),
    ("收益率(%)", "Return (%)"),
    ("相关系数", "Correlation"),
    ("共同交易日", "Shared trading days"),
    ("暂无可展示的 K 线数据。", "No candlestick data is available to display."),
    ("暂无可展示的行情与指标数据。", "No market or indicator data is available to display."),
    ("暂无可展示的指标数据。", "No indicator data is available to display."),
    ("暂无可展示的净值与回撤数据。", "No equity or drawdown data is available to display."),
    ("当前周期下没有可用的 RSI 指标。", "No RSI data is available for the current period."),
    ("当前周期下没有可用的成交量数据。", "No volume data is available for the current period."),
    ("当前周期下没有可用的 MACD 指标。", "No MACD data is available for the current period."),
    ("训练截止", "Train cutoff"),
    ("当前标的", "Current symbol"),
    ("训练 / 测试", "Train / test"),
    ("数据区间", "Data range"),
    ("最新收盘", "Latest close"),
    ("研究状态", "Research status"),
    ("市场上下文", "Market context"),
    ("策略流程", "Strategy flow"),
    ("当前市场的快照和推荐入口", "Current market snapshot and recommended entry points"),
    ("Choose A Route", "Choose A Route"),
    ("Action Card", "Action Card"),
    ("Showcase Board", "Showcase Board"),
    ("Result Surface", "Result Surface"),
    ("Control Panel", "Control Panel"),
    ("Basic Information", "Basic Information"),
    ("Strategy Research Site", "Strategy Research Site"),
    ("Single Stock Route", "Single Stock Route"),
    ("Multi Stock Route", "Multi Stock Route"),
    ("Language", "Language"),
    ("Theme", "Theme"),
    ("亮色", "Light"),
    ("暗色", "Dark"),
    ("\u7f8e\u80a1", "US equities"),
    ("A \u80a1", "A shares"),
    ("\u4ece\u4e00\u4e2a\u6e05\u695a\u7684\u5165\u53e3\u52a8\u4f5c\u5f00\u59cb", "Start from one clear action"),
    ("\u5217\u540d\u9700\u517c\u5bb9 date/open/high/low/close/volume \u6807\u51c6\u3002", "Columns should follow the date/open/high/low/close/volume schema."),
    ("\u53f3\u4fa7\u4fdd\u6301\u4e00\u4e2a\u5927\u7684\u4e0a\u4e0b\u6587\u5c55\u793a\u533a\uff0c\u5e2e\u52a9\u4f60\u4ece\u641c\u7d22\u4e4b\u5916\u8865\u5145\u65b0\u7684\u6bd4\u8f83\u5bf9\u8c61\u3002", "The right side keeps one large context board so you can add new comparison candidates beyond search."),
    ("\u641c\u7d22\u7d22\u5f15\u52a0\u8f7d\u5931\u8d25\uff1a", "Search index failed to load: "),
    ("\u8d8b\u52bf EMA \u5feb\u7ebf\u9700\u8981\u5c0f\u4e8e\u6162\u7ebf\u3002", "The EMA fast line must be smaller than the slow line."),
    ("MACD \u5feb\u7ebf\u5468\u671f\u9700\u8981\u5c0f\u4e8e\u6162\u7ebf\u5468\u671f\u3002", "The MACD fast period must be smaller than the slow period."),
    ("RSI \u4e0b\u9650\u9700\u8981\u5c0f\u4e8e\u4e0a\u9650\u3002", "The RSI lower bound must be smaller than the upper bound."),
    ("\u77ed\u671f\u52a8\u91cf\u7a97\u53e3\u9700\u8981\u5c0f\u4e8e\u4e2d\u671f\u52a8\u91cf\u7a97\u53e3\u3002", "The short momentum window must be smaller than the medium momentum window."),
    ("\u4e2d\u6863\u5206\u4f4d\u6570\u9700\u8981\u5c0f\u4e8e\u9ad8\u6863\u5206\u4f4d\u6570\u3002", "The mid percentile must be smaller than the high percentile."),
    ("\u6240\u9009\u65f6\u95f4\u533a\u95f4\u5185\u6ca1\u6709\u6570\u636e\u3002", "No data is available in the selected date range."),
    ("\u7f3a\u5c11\u5fc5\u9700\u5217\uff1a", "Missing required columns: "),
    ("\u5f53\u524d\u4f7f\u7528\u4e0a\u4f20\u6570\u636e\uff1a", "Currently using uploaded data: "),
    ("\u6ca1\u6709\u52a0\u8f7d\u5230\u6570\u636e\u3002", "No data was loaded."),
    ("\u65e0\u6cd5\u83b7\u53d6", "Failed to load "),
    ("\u7684\u6570\u636e\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u8fde\u63a5\u3002", " data. Check the network connection."),
    ("\u4e0a\u4f20\u6587\u4ef6", "Uploaded file"),
    ("\u8bfb\u53d6\u5931\u8d25\uff1a", "read failed: "),
    ("\u8d8b\u52bf\u8ddf\u968f\uff08\u4fdd\u5b88\uff09", "Trend following (conservative)"),
    ("\u5747\u8861\u7b56\u7565\uff08\u9ed8\u8ba4\uff09", "Balanced strategy (default)"),
    ("\u52a8\u91cf\u7a81\u7834\uff08\u6fc0\u8fdb\uff09", "Momentum breakout (aggressive)"),
    ("\ud83d\udcca \u63a7\u5236\u9762\u677f", "\ud83d\udcca Control panel"),
    ("\u5e02\u573a\u9009\u62e9", "Market"),
    ("\ud83d\udcc5 \u65f6\u95f4\u8303\u56f4", "\ud83d\udcc5 Date range"),
    ("\u9009\u62e9\u65f6\u95f4\u533a\u95f4", "Select a date range"),
    ("\u590d\u6743\u65b9\u5f0f", "Adjustment mode"),
    ("\ud83d\udcc8 \u5165\u573a\u89c4\u5219", "\ud83d\udcc8 Entry rules"),
    ("\ud83d\udcc9 \u51fa\u573a\u89c4\u5219", "\ud83d\udcc9 Exit rules"),
    ("\u5165\u573a\u9700\u6ee1\u8db3\u4ee5\u4e0b\u4fe1\u53f7\u4e2d\u7684\u81f3\u5c11 N \u4e2a\uff1a", "At least N of the following entry signals must be satisfied:"),
    ("\u51fa\u573a\u9700\u6ee1\u8db3\u4ee5\u4e0b\u4fe1\u53f7\u4e2d\u7684\u81f3\u5c11 N \u4e2a\uff1a", "At least N of the following exit signals must be satisfied:"),
    ("\u5165\u573a\u6700\u5c11\u4fe1\u53f7\u6570", "Minimum entry signals"),
    ("\u51fa\u573a\u6700\u5c11\u4fe1\u53f7\u6570", "Minimum exit signals"),
    ("\u8bf7\u8f93\u5165\u7f8e\u80a1\u4ee3\u7801\u540e\u518d\u6dfb\u52a0\u3002", "Enter a US ticker before adding it."),
    ("\u5207\u6362\u540e\u5c06\u4f7f\u7528\u5bf9\u5e94\u5e02\u573a\u7684\u9ed8\u8ba4\u80a1\u7968\u6c60\u548c\u6570\u636e\u4e0b\u8f7d\u8def\u5f84\u3002", "Switching markets uses the matching default stock universe and download path."),
    ("\u9009\u62e9\u56de\u6d4b\u6570\u636e\u7684\u8d77\u6b62\u65e5\u671f", "Choose the start and end dates for the backtest data."),
    ("\u5f71\u54cd\u6570\u636e\u4e0b\u8f7d\u7684\u590d\u6743\u65b9\u5f0f\u3002", "Controls which price-adjustment mode is used when downloading data."),
    ("\u2795 \u6dfb\u52a0\u80a1\u7968 / \u4e0a\u4f20\u6570\u636e", "\u2795 Add stocks / upload data"),
    ("\u4e0a\u4f20 CSV\uff08\u5217\u540d\uff1aopen, close, volumn/volume, high, low\uff09", "Upload CSV (columns: open, close, volume, high, low)"),
    ("\u2699\ufe0f \u9ad8\u7ea7\u8bbe\u7f6e\uff08\u81ea\u5b9a\u4e49\u53c2\u6570 / \u67e5\u770b\u5f53\u524d\u503c\uff09", "\u2699\ufe0f Advanced settings (custom parameters / current values)"),
    ("**EMA \u8d8b\u52bf\u53c2\u6570**", "**EMA trend parameters**"),
    ("EMA \u5feb\u7ebf\u5468\u671f", "EMA fast period"),
    ("EMA \u6162\u7ebf\u5468\u671f", "EMA slow period"),
    ("**MACD \u53c2\u6570**", "**MACD parameters**"),
    ("MACD \u5feb\u7ebf\u5468\u671f", "MACD fast period"),
    ("MACD \u6162\u7ebf\u5468\u671f", "MACD slow period"),
    ("MACD \u4fe1\u53f7\u5468\u671f", "MACD signal period"),
    ("**RSI \u53c2\u6570**", "**RSI parameters**"),
    ("RSI \u5468\u671f", "RSI period"),
    ("RSI \u4e0b\u9650\u9608\u503c", "RSI lower threshold"),
    ("RSI \u4e0a\u9650\u9608\u503c", "RSI upper threshold"),
    ("**ADX \u5f3a\u5ea6\u53c2\u6570**", "**ADX strength parameters**"),
    ("ADX \u5468\u671f", "ADX period"),
    ("ADX \u9608\u503c", "ADX threshold"),
    ("**ATR \u6b62\u635f\u6b62\u76c8**", "**ATR stop-loss / take-profit**"),
    ("ATR \u5468\u671f", "ATR period"),
    ("**\u5e03\u6797\u5e26 / \u9ad8\u7ea7\u6307\u6807\u53c2\u6570**", "**Bollinger / advanced indicator parameters**"),
    ("\u5e03\u6797\u5e26\u5468\u671f", "Bollinger period"),
    ("\u5e03\u6797\u5e26\u6807\u51c6\u5dee\u500d\u6570", "Bollinger std multiplier"),
    ("ATR \u6b62\u635f\u500d\u6570", "ATR stop-loss multiplier"),
    ("ATR \u6b62\u76c8\u500d\u6570", "ATR take-profit multiplier"),
    ("\u77ed\u671f\u52a8\u91cf\u7a97\u53e3", "Short momentum window"),
    ("\u4e2d\u671f\u52a8\u91cf\u7a97\u53e3", "Medium momentum window"),
    ("\u8bc4\u5206\u6807\u51c6\u5316\u7a97\u53e3", "Score normalization window"),
    ("**\u5165\u573a/\u51fa\u573a\u8bc4\u5206\u9608\u503c**", "**Entry / exit score thresholds**"),
    ("\u5165\u573a\u8bc4\u5206\u9608\u503c", "Entry score threshold"),
    ("\u51fa\u573a\u8bc4\u5206\u9608\u503c", "Exit score threshold"),
    ("\ud83d\udcac \u53cd\u9988\u4e0e\u5efa\u8bae", "\ud83d\udcac Feedback"),
    ("\u7c7b\u578b", "Type"),
    ("\u63cf\u8ff0", "Description"),
    ("\ud83d\udce4 \u63d0\u4ea4\u53cd\u9988", "\ud83d\udce4 Submit feedback"),
    ("\u53cd\u9988\u5c06\u901a\u8fc7 [GitHub Issues](https://github.com/rikka314/stratagy/issues) \u8ffd\u8e2a", "Feedback is tracked via [GitHub Issues](https://github.com/rikka314/stratagy/issues)"),
    ("\u4e0a\u4f20\u81ea\u5b9a\u4e49CSV\u6570\u636e\u6587\u4ef6", "Upload a custom CSV dataset"),
    ("\u2713 \u5c06\u4f7f\u7528\u4e0a\u4f20\u7684CSV\u6570\u636e", "\u2713 The uploaded CSV data will be used"),
    ("\u6b63\u5728\u5237\u65b0\u6570\u636e...", "Refreshing data..."),
    ("\u9996\u9875", "Home"),
    ("\u5355\u80a1\u5165\u53e3", "Single-stock entry"),
    ("\u591a\u80a1\u5165\u53e3", "Multi-stock entry"),
    ("\u6a21\u578b\u8bc4\u4f30", "Model evaluation"),
    ("\u4f8b\u5982: TSLA / Apple / \u8d35\u5dde\u8305\u53f0 / 600519", "For example: TSLA / Apple / Kweichow Moutai / 600519"),
    ("\u81ea\u5b9a\u4e49\u53c2\u6570", "Custom parameters"),
    ("\U0001f4ca \u63a7\u5236\u9762\u677f", "\U0001f4ca Control panel"),
    ("\U0001f4c5 \u65f6\u95f4\u8303\u56f4", "\U0001f4c5 Date range"),
    ("\U0001f4c8 \u5165\u573a\u89c4\u5219", "\U0001f4c8 Entry rules"),
    ("\U0001f4c9 \u51fa\u573a\u89c4\u5219", "\U0001f4c9 Exit rules"),
    ("\U0001f4ac \u53cd\u9988\u4e0e\u5efa\u8bae", "\U0001f4ac Feedback"),
    ("\U0001f4e4 \u63d0\u4ea4\u53cd\u9988", "\U0001f4e4 Submit feedback"),
    ("\U0001f41b Bug \u62a5\u544a", "\U0001f41b Bug report"),
    ("\U0001f4a1 \u529f\u80fd\u5efa\u8bae", "\U0001f4a1 Feature request"),
    ("\U0001f4dd \u5176\u4ed6\u53cd\u9988", "\U0001f4dd Other feedback"),
    ("\u8d8b\u52bf\u8fc7\u6ee4\u7684\u77ed\u5468\u671f EMA\u3002", "The short-period EMA used by the trend filter."),
    ("\u8d8b\u52bf\u8fc7\u6ee4\u7684\u957f\u5468\u671f EMA\u3002", "The long-period EMA used by the trend filter."),
    ("MACD \u5feb\u7ebf EMA \u5468\u671f\u3002", "The EMA period of the MACD fast line."),
    ("MACD \u6162\u7ebf EMA \u5468\u671f\u3002", "The EMA period of the MACD slow line."),
    ("MACD \u4fe1\u53f7\u7ebf EMA \u5468\u671f\u3002", "The EMA period of the MACD signal line."),
    ("RSI \u8ba1\u7b97\u5468\u671f\u3002", "The lookback period used to compute RSI."),
    ("RSI \u4f4e\u4e8e\u8be5\u503c\u89c6\u4e3a\u504f\u5f31\u3002", "Values below this threshold are treated as weak RSI."),
    ("RSI \u9ad8\u4e8e\u8be5\u503c\u89c6\u4e3a\u504f\u5f3a\u3002", "Values above this threshold are treated as strong RSI."),
    ("\u8d8b\u52bf\u5f3a\u5ea6\u6307\u6807\u7684\u8ba1\u7b97\u5468\u671f\u3002", "The lookback period used to compute the trend-strength indicator."),
    ("ADX \u9ad8\u4e8e\u8be5\u503c\u624d\u8ba4\u4e3a\u8d8b\u52bf\u6709\u6548\u3002", "A trend is considered valid only when ADX is above this threshold."),
    ("\u6ce2\u52a8\u7387\uff08ATR\uff09\u8ba1\u7b97\u5468\u671f\u3002", "The lookback period used to compute ATR."),
    ("\u5e03\u6797\u5e26\u79fb\u52a8\u5e73\u5747\u7ebf\u7684\u8ba1\u7b97\u5468\u671f\u3002", "The lookback period used for the Bollinger moving average."),
    ("\u5e03\u6797\u5e26\u4e0a\u4e0b\u8f68\u7684\u6807\u51c6\u5dee\u500d\u6570\u3002", "The standard-deviation multiplier used for the Bollinger bands."),
    ("\u6b62\u635f\u8ddd\u79bb=ATR\u00d7\u500d\u6570\u3002", "Stop-loss distance = ATR × multiplier."),
    ("\u6b62\u76c8\u8ddd\u79bb=ATR\u00d7\u500d\u6570\u3002", "Take-profit distance = ATR × multiplier."),
    ("\u77ed\u671f\u6536\u76ca\u7387\u7a97\u53e3\u3002", "The short return window."),
    ("\u4e2d\u671f\u6536\u76ca\u7387\u7a97\u53e3\u3002", "The medium return window."),
    ("\u7528\u4e8e\u8ba1\u7b97\u6eda\u52a8 Z \u5206\u6570\u7684\u7a97\u53e3\u3002", "The window used to compute rolling Z-scores."),
    ("\u6ce2\u52a8\u7387\u8d8a\u9ad8\uff0c\u8bc4\u5206\u60e9\u7f5a\u8d8a\u5927\u3002", "Higher volatility leads to a larger score penalty."),
    ("\u5f53\u524d\u4f7f\u7528\u300c", "Currently using \""),
    ("\u300d\u9884\u8bbe\uff0c\u4ee5\u4e0b\u53c2\u6570\u5df2\u81ea\u52a8\u586b\u5145\u3002\u5207\u6362\u4e3a\u300c\u81ea\u5b9a\u4e49\u53c2\u6570\u300d\u53ef\u624b\u52a8\u4fee\u6539\u3002", "\" preset. The parameters below were filled automatically. Switch to \"Custom parameters\" to edit them manually."),
    ("\u2705 \u611f\u8c22\u53cd\u9988\uff01\u70b9\u51fb\u4e0b\u65b9\u94fe\u63a5\u63d0\u4ea4\u5230 GitHub\uff1a", "\u2705 Thanks for the feedback! Click the link below to submit it to GitHub:"),
    ("\u8bf7\u5148\u586b\u5199\u53cd\u9988\u5185\u5bb9", "Please enter feedback content first."),
    ("\u5df2\u5728\u6570\u636e\u5e93\u4e2d", "is already in the database"),
    ("\u2713 \u5df2\u9009\u62e9", "\u2713 Selected"),
    ("] \u7528\u6237\u53cd\u9988", "] User feedback"),
    ("--- *\u901a\u8fc7\u5e94\u7528\u5185\u53cd\u9988\u63d0\u4ea4*", "--- *Submit via the in-app feedback flow*"),
    ("[\U0001f4cb \u524d\u5f80\u63d0\u4ea4 Issue](", "[\U0001f4cb Open issue form]("),
    ("\u6b63\u5728\u4e0b\u8f7d", "Downloading "),
    ("\u6570\u636e...", " data..."),
    ("\u2713 \u6570\u636e\u5237\u65b0\u5b8c\u6210\uff1a\u6210\u529f", "\u2713 Data refresh finished: success "),
    ("\u4e2a\uff0c\u5931\u8d25", ", failed "),
    ("\u4e2a", ""),
    ("\u6dfb\u52a0\u6210\u529f", "added successfully"),
    ("\u672a\u83b7\u53d6\u5230\u6709\u6548\u6570\u636e", "No valid data was returned"),
    (": \u5df2\u66f4\u65b0\u81f3", ": updated through "),
    ("\u5237\u65b0\u5931\u8d25:", "refresh failed:"),
    ("市场数据", "Market data"),
    ("---\n*通过应用内反馈提交*", "---\n*Submit via the in-app feedback flow*"),
    ("上传数据", "Uploaded data"),
    ("当前价格", "Current price"),
    ("最新涨跌", "Latest change"),
    ("没有找到索引匹配，将按当前输入直接切换。", "No indexed match was found. The app will switch directly using the current input."),
    ("按当前输入切换", "Switch with current input"),
    ("切换", "Switch"),
    ("开盘 / 最高", "Open / High"),
    ("当日开高", "Today's open and high"),
    ("最低 / 成交量", "Low / Volume"),
    ("当日低点与成交量", "Today's low and volume"),
    ("区间收益", "Period return"),
    ("20 日均量", "20-day avg volume"),
    ("不足 20 日时按现有窗口计算", "Uses the available window when fewer than 20 days are present"),
    ("训练集截止", "Train cutoff"),
    ("数据行数", "Row count"),
    ("当前 ·", "Current ·"),
    ("已保存 ·", "Saved ·"),
    (" 到 ", " to "),
    ("Step 1 选择 Family", "Step 1 Select family"),
    ("Step 2 · Baseline 路径", "Step 2 · Baseline path"),
    ("Step 2 · Search 基础模型", "Step 2 · Search base model"),
    ("模型家族", "Model family"),
    ("启用参数搜索", "Enable parameter search"),
    ("启用 ML 过滤", "Enable ML filter"),
    ("请先在上方选择 Baseline 或 Search，再展开具体配置。", "Choose Baseline or Search above before expanding the detailed configuration."),
    ("请先选择 SM 或 FSM，再决定是否追加参数搜索与 ML 过滤。", "Choose SM or FSM first, then decide whether to add parameter search and ML filtering."),
    ("已启用参数搜索：搜索结果只进入 lineage / artifact，不会自动回写侧边栏参数。", "Parameter search is enabled: results only enter lineage / artifact and will not write back into sidebar parameters automatically."),
    ("已启用 ML 过滤：ML 始终消费最近一步成功的上游结果。", "ML filtering is enabled: ML always consumes the latest successful upstream result."),
    ("请先选择 Baseline 或 Search", "Choose Baseline or Search first"),
    ("请先选择 SM 或 FSM", "Choose SM or FSM first"),
    ("请先选择参数搜索方法", "Choose a parameter-search method first"),
    ("请先选择 ML 模型", "Choose an ML model first"),
    ("Baseline -> 等待选择 Naive / Mean / Drift", "Baseline -> Waiting for Naive / Mean / Drift"),
    ("Search -> 等待选择 SM / FSM", "Search -> Waiting for SM / FSM"),
    ("SM基础", "SM base"),
    ("FSM基础", "FSM base"),
    ("参数搜索", "Parameter search"),
    ("ML过滤", "ML filter"),
    ("当前展示的是上次成功生成的 lineage；新草稿尚未提交。", "The current view shows the most recently successful lineage; the new draft has not been committed yet."),
    ("阶段链路：", "Stage chain:"),
    ("数据集时间", "Dataset period"),
    ("训练集", "Training set"),
    ("完整数据", "Full dataset"),
    ("测试集", "Test set"),
    ("未记录", "Not recorded"),
    ("无", "None"),
    ("当前没有足够的信号数据。", "Not enough signal data is available right now."),
    ("当前 artifact", "Current artifact"),
    ("右侧所有结果默认读取 current_artifact", "All results on the right read from current_artifact by default."),
    ("最新建议", "Latest suggestion"),
    ("评分 / 分位", "Score / percentile"),
    ("目标仓位", "Target position"),
    ("来自最新一行 target_position", "Taken from the latest target_position row"),
    ("累计收益", "Cumulative return"),
    ("测试期", "Test period"),
    ("风险调整后表现", "Risk-adjusted performance"),
    ("最新信号偏空，目标仓位", "The latest signal is short-biased, target position"),
    ("当前信号偏多，目标仓位", "The latest signal is long-biased, target position"),
    ("当前维持高仓位，目标仓位", "The current stance keeps a high allocation, target position"),
    ("当前处于观察仓位，目标仓位", "The current stance is observational, target position"),
    ("先在左侧选择 Baseline 或 Search 家族，结果板才会进入可配置状态。", "Choose a Baseline or Search family on the left before the result board becomes configurable."),
    ("当前最佳", "Current best"),
    ("按测试期累计收益优先，夏普作为并列时的次级排序", "Ranks by test-period cumulative return first, with Sharpe used as the tiebreaker."),
    ("测试期结果", "Test-period result"),
    ("越低越稳", "Lower is steadier"),
    ("评分", "Score"),
    ("分位数 %", "Percentile %"),
    ("当前没有可展示标的", "No symbols are available to display"),
    ("参与标的", "Included symbols"),
    ("最佳表现", "Best performer"),
    ("所有曲线都以同一基准起点归一化，适合先看整体强弱排序。", "All curves are normalized to the same starting baseline, making overall relative strength easier to compare first."),
    ("RS 曲线上升代表相对强势，下降代表相对弱势。", "A rising RS line indicates relative strength; a falling line indicates relative weakness."),
    ("风险收益", "Risk / return"),
    ("风险收益散点图", "Risk-return scatter"),
    ("越靠左上通常代表越高收益、越低风险；颜色映射到夏普水平。", "Points nearer the upper-left usually indicate higher return and lower risk; color maps to Sharpe level."),
    ("数据不足以计算风险收益图。", "There is not enough data to compute the risk-return chart."),
    ("相关性", "Correlation"),
    ("接近 1 代表正相关，接近 -1 代表负相关，接近 0 代表相关性弱。", "Values near 1 indicate positive correlation, near -1 negative correlation, and near 0 weak correlation."),
    ("正在生成 HTML 报告...", "Generating HTML report..."),
    ("HTML 报告已生成。", "The HTML report has been generated."),
    ("下载 HTML 报告", "Download HTML report"),
    ("当前市场", "Current market"),
    ("时间范围", "Date range"),
    ("候选搜索失败：", "Candidate search failed: "),
    ("多股组合控制台", "Multi-stock portfolio console"),
    ("**组合参数搜索**", "**Portfolio parameter search**"),
    ("优化试验次数", "Optimization trials"),
    ("开始组合搜索", "Start portfolio search"),
    ("组合结果区", "Portfolio results"),
    ("当前成功加载的有效标的", "Currently loaded valid symbols"),
    ("覆盖区间", "Coverage range"),
    ("试验次数越多越精确，但耗时更长。建议先用 30 次验证路径。", "More trials improve accuracy but take longer. Start with 30 trials to validate the path."),
    ("查看最优参数", "View best parameters"),
    ("出场阈值", "Exit threshold"),
    ("ADX阈值", "ADX threshold"),
    ("止损倍数", "Stop-loss multiplier"),
    ("止盈倍数", "Take-profit multiplier"),
    ("等权基准", "Equal-weight benchmark"),
    ("贝叶斯优化中（", "Bayesian optimization in progress ("),
    ("次试验）...", " trials)..."),
    ("优化后夏普", "Optimized Sharpe"),
    ("优化后收益", "Optimized return"),
    ("当前结果缺少可展示的组合净值图。", "The current result has no portfolio equity chart to display."),
    ("参数", "Parameter"),
    ("最优值", "Best value"),
    ("市场指数", "Market index"),
    ("未生成", "Not generated"),
    ("主窗口 + 稳健性综合评分", "Main-window + robustness composite score"),
    ("仅主窗口总分", "Main-window score only"),
    ("主窗口 +", "Main window +"),
    ("稳健性", "Robustness"),
    ("份 tear sheet", " tear sheets"),
    ("已启用，暂未生成", "Enabled, not generated yet"),
    ("当前没有可展示的 QuantStats 信息。", "No QuantStats information is available to display."),
    ("当前 run 未生成 QuantStats tear sheet。", "The current run did not generate a QuantStats tear sheet."),
    ("当前没有可展示的 MLflow 信息。", "No MLflow information is available to display."),
    ("未记录 MLflow。", "MLflow was not recorded."),
    ("已启用", "Enabled"),
    ("未启用", "Disabled"),
    ("已记录 MLflow", "MLflow recorded"),
    ("未记录 MLflow", "MLflow not recorded"),
    ("浏览已有研究 run", "Browse existing research runs"),
    ("页面只消费 report.json 已汇总的结果和可选的 QuantStats / MLflow 元信息。", "This page only consumes summarized results from report.json plus optional QuantStats / MLflow metadata."),
    ("当前 run 摘要", "Current run summary"),
    ("总览", "Overview"),
    ("异常样本", "Failure samples"),
    ("实验名", "Experiment"),
    ("排名", "Rank"),
    ("模型", "Model"),
    ("族", "Family"),
    ("阶段", "Stage"),
    ("总分", "Total score"),
    ("主窗口分", "Main-window score"),
    ("稳健性分", "Robustness score"),
    ("中位夏普", "Median Sharpe"),
    ("中位超额收益", "Median excess return"),
    ("模型族", "Model family"),
    ("模型数", "Model count"),
    ("平均总分", "Average total score"),
    ("最佳模型", "Best model"),
    ("最佳分数", "Best score"),
    ("方法", "Method"),
    ("稳健性总分", "Robustness total score"),
    ("成功率", "Success rate"),
    ("窗口", "Window"),
    ("状态", "Status"),
    ("说明", "Details"),
    ("· 阶段", "· Stage"),
    ("· 分数", "· Score"),
    ("当前没有可读取的研究 run。", "No readable research runs are available right now."),
    ("选择 run", "Select run"),
    ("tearsheet.html 文件不存在，当前只保留元数据。", "The tearsheet.html file is missing; only metadata is available right now."),
    ("下载 tear sheet", "Download tear sheet"),
    ("扫描目录：", "Scan directory: "),
    ("最新更新时间", "Latest update"),
    ("主榜单固定读取 report.json 中的汇总结果，不在页面内重扫 artifacts。", "The main ranking reads summarized results from report.json and does not rescan artifacts in-page."),
    ("按 baseline / sm / fsm 族查看平均得分与最佳模型。", "Compare average scores and best models across the baseline / sm / fsm families."),
    ("横向比较 random / bayesian / genetic 的平均表现与胜出模型。", "Compare average performance and winning models across random / bayesian / genetic search methods."),
    ("若 run 启用了 rolling robustness，这里显示稳健性汇总；否则只展示空态。", "If the run enabled rolling robustness, its summary appears here; otherwise this section stays empty."),
    ("当前 run 没有 robustness 汇总。", "The current run has no robustness summary."),
    ("这里只展示 report.json 里已汇总的异常样本，不重新追踪底层任务日志。", "This section only shows failure samples already summarized in report.json and does not retrace lower-level task logs."),
    ("当前 run 没有异常样本。", "The current run has no failure samples."),
    ("选中的 run 读取失败。", "The selected run could not be loaded."),
    ("报告文件：", "Report file: "),
    ("Top 1 模型", "Top 1 model"),
    ("模型ID", "Model ID"),
    ("生成时间", "Generated at"),
    ("模型数量", "Model count"),
    ("无法读取报告文件：", "Unable to read report file: "),
    ("Tear Sheet 列表", "Tear sheet list"),
    ("v1 只展示条目摘要并提供文件下载，不在应用内嵌入整页 HTML。", "v1 only shows item summaries and file downloads instead of embedding full HTML pages in-app."),
    ("Run 元信息", "Run metadata"),
    ("页面只显示 mlflow_run.json 元数据，不尝试启动或嵌入 MLflow UI。", "This page only shows metadata from mlflow_run.json and does not launch or embed the MLflow UI."),
    ("先确定一个标的，再进入单股分析。", "Pick a symbol first, then enter single-stock analysis."),
    ("市场切换、搜索确认、开始分析和本地上传都放在同一张主操作卡里。", "Market switching, search confirmation, starting analysis, and local uploads all live in the same primary action card."),
    ("输入股票名称或代码后，这里会出现可直接进入分析的候选项。", "After you enter a stock name or ticker, candidates that can go straight into analysis will appear here."),
    ("请先从搜索结果中选择一只股票。", "Choose a stock from the search results first."),
    ("用上传数据开始分析", "Start analysis with uploaded data"),
    ("右侧只保留一个大的展示区，用来支撑进入分析前的判断，不再把说明拆成多张卡片。", "The right side keeps one large showcase area to support decisions before entering analysis instead of splitting explanations into multiple cards."),
    ("先看大盘快照，再往下进入推荐股票和分析入口。", "Read the market snapshot first, then continue down into recommended stocks and analysis entry points."),
    ("推荐列表放在同一个轻量 sheet 里，点击右侧小按钮即可直接进入分析。", "The recommendation list stays inside one lightweight sheet, and the small buttons on the right jump straight into analysis."),
    ("市场快照暂不可用", "Market snapshot is unavailable"),
    ("市场快照加载失败：", "Market snapshot failed to load: "),
    ("未找到索引匹配，将按该 A 股代码直接尝试分析。", "No indexed match was found. The app will try this A-share ticker directly."),
    ("未找到索引匹配，将按该美股代码直接尝试分析。", "No indexed match was found. The app will try this US ticker directly."),
    ("价格对比", "Price comparison"),
    ("多股票价格对比分析图", "Multi-stock price comparison chart"),
    ("把所有股票起点统一到同一基准，先判断谁在当前观察区间内跑得更快。", "Normalize all stocks to the same starting baseline first, then judge which one is moving faster in the current observation window."),
    ("当前没有足够数据生成价格对比图。", "There is not enough data to generate the price comparison chart."),
    ("相对强弱对比图", "Relative-strength comparison chart"),
    ("默认相对基准使用等权平均，判断每只股票是持续跑赢还是持续跑输股票池。", "The default relative benchmark uses an equal-weight average to show whether each stock is persistently outperforming or lagging the pool."),
    ("数据不足以计算相对强弱（至少需要 2 只有效股票）。", "There is not enough data to compute relative strength; at least two valid stocks are required."),
    ("最新因子评分对比图", "Latest factor-score comparison chart"),
    ("对每只股票独立计算最新一日综合因子评分，直接回答当前更值得关注谁。", "The page computes the latest composite factor score for each stock separately to answer which names deserve attention right now."),
    ("柱子越高，说明当前综合因子评分越强；颜色对应建议仓位。", "Taller bars indicate stronger composite factor scores; color maps to the suggested position."),
    ("当前历史窗口不足，无法稳定计算最新因子评分。", "The historical window is too short to compute the latest factor score reliably."),
    ("股票相关性热图", "Stock-correlation heatmap"),
    ("用共同交易日收益率构造相关性矩阵，帮助判断股票池是否过于同质化。", "The page builds a correlation matrix from shared-day returns to show whether the stock pool is overly homogeneous."),
    ("数据不足以计算相关性热图（需要至少 5 个共同交易日）。", "There is not enough data to compute the correlation heatmap; at least five shared trading days are required."),
    ("当前没有可移除的股票。", "There are no stocks available to remove right now."),
    ("当前股票池仅剩 2 个标的；先在右侧添加新股票，再执行移除。", "Only two symbols remain in the current pool; add another stock on the right before removing one."),
    ("输入名称或代码后，可把新标的直接加入当前股票池。", "Enter a name or ticker to add a new symbol directly into the current stock pool."),
    ("没有加载到有效的股票数据。", "No valid stock data was loaded."),
    ("只读浏览已有模型研究结果。", "Read-only browsing of existing model research results."),
    ("这个页面只读取本地 <code>model-test/outputs</code> 下的现有研究产物，不触发任何研究执行。默认展示最新可读 run，并允许在不同 run 之间切换浏览。", "This page only reads existing research artifacts under local <code>model-test/outputs</code> and never triggers research execution. It shows the latest readable run by default and lets you switch between runs."),
    ("这个页面只读取本地 <code>model-test/outputs</code> 下的现有研究产物，不触发任何研究执行。", "This page only reads existing research artifacts under local <code>model-test/outputs</code> and never triggers research execution."),
    ("默认展示最新可读 run，并允许在不同 run 之间切换浏览。", "It shows the latest readable run by default and lets you switch between runs."),
    ("公开路径", "Public route"),
    ("只读结果浏览页", "Read-only result browser"),
    ("最新可读 run", "Latest readable run"),
    ("可读 run", "readable runs"),
    ("数据来源", "Data source"),
    ("选择一个可读 run 后，这里会展示当前最佳模型和评分规则。", "After you choose a readable run, this panel shows the current best model and scoring rules."),
    ("配置名称", "Config name"),
    ("股票池", "Stock pool"),
    ("搜索股票名称或代码", "Search stock names or tickers"),
    ("该股票已经在当前股票池里。", "This stock is already in the current stock pool."),
    ("没有找到索引匹配，将按当前输入直接加入。", "No indexed match was found. The app will add the current input directly."),
    ("按当前输入加入", "Add current input"),
    ("加载对比股票数据...", "Loading comparison stock data..."),
    ("**组合权重配置**", "**Portfolio weight configuration**"),
    ("组合策略", "Portfolio strategy"),
    ("生成组合策略", "Generate portfolio strategy"),
    ("组合权重之和必须大于 0。", "The sum of portfolio weights must be greater than 0."),
    ("布林带权重", "Bollinger weight"),
    ("成交量权重", "Volume weight"),
    ("价格位置权重", "Price-position weight"),
    ("回撤惩罚权重", "Drawdown penalty weight"),
    ("策略组合", "Strategy portfolio"),
    ("各股票独立策略表现", "Per-stock strategy performance"),
    ("对比股票数量", "Compared stocks"),
    ("平均数据天数", "Average data days"),
    ("按当前日期范围统计", "Calculated within the current date range"),
    ("多股基础信息与右侧图表共用同一筛选结果", "The multi-stock basics and the chart on the right share the same filter result."),
    ("在一个平面里同时看年化收益、波动率和夏普，适合快速识别风险收益结构。", "See annualized return, volatility, and Sharpe in one plane to identify the risk-return structure quickly."),
    ("周期收益率热图已移动到策略区，基础信息区只保留图四对应的多股对比图表。", "The periodic return heatmap moved to the strategy section; the basics section now keeps only the four multi-stock comparison charts."),
    ("组合权重、生成动作和参数搜索收敛到同一侧；策略参数仍统一复用左侧边栏，不再派生第二套配置来源。", "Portfolio weights, generation actions, and parameter search are consolidated on one side; strategy parameters still reuse the left sidebar instead of deriving a second configuration source."),
    ("至少需要 2 个有效标的；如股票池、权重或边栏参数变化，结果区会要求重新生成。", "At least two valid symbols are required. If the stock pool, weights, or sidebar parameters change, the result section will require regeneration."),
    ("检测到股票池、权重或边栏参数变化，请重新生成组合策略。", "The stock pool, weights, or sidebar parameters changed. Regenerate the portfolio strategy."),
    ("模型还没准备好。先在左侧确认权重，再点击“生成组合策略”。", "The model is not ready yet. Confirm the weights on the left, then click \"Generate portfolio strategy\"."),
    ("结果主图在投资组合模拟和周期收益率热图之间切换；投资组合模拟现复用单股结果区的共享净值/回撤组件，组合 KPI 摘要和个股表现表保持固定。", "The main result chart switches between portfolio simulation and the periodic return heatmap. Portfolio simulation reuses the shared equity/drawdown component from the single-stock result area, while the portfolio KPI summary and stock performance table stay fixed."),
    ("图五要求的“组合 KPI 摘要 + 个股表现表”已固定在同一结果区，切换主图不会打散下方信息。", "The \"portfolio KPI summary + stock performance table\" required by chart five stays fixed in the same result section, so switching the main chart does not disrupt the information below."),
    ("多股票对比分析 -", "Multi-stock comparison analysis -"),
    ("正在运行多股组合策略模拟...", "Running the multi-stock portfolio strategy simulation..."),
    ("组合策略已生成，右侧结果区已更新。", "The portfolio strategy has been generated and the result area on the right has been updated."),
    ("当前数据不足以生成组合策略，请检查股票池长度和时间范围。", "The current data is insufficient to generate a portfolio strategy. Check the stock-pool size and date range."),
    ("优化后回撤", "Optimized drawdown"),
    ("当前结果不足以生成策略周期热图。", "The current result is not sufficient to generate the strategy-period heatmap."),
    ("当前主图与单股结果区共用同一套“净值上 / 回撤下”的结果图组件。", "The current main chart reuses the same \"equity above / drawdown below\" component used in the single-stock result area."),
    ("当前没有可展示的个股独立策略表现。", "No per-stock strategy performance is available to display right now."),
    ("请描述你遇到的问题或建议...", "Describe the issue or suggestion..."),
    ("市场", "Market"),
    ("分数", "Score"),
]
_TRANSLATION_PAIRS = sorted(_TRANSLATION_PAIRS, key=lambda item: len(item[0]), reverse=True)


def ensure_ui_preferences() -> None:
    st.session_state.setdefault(UI_LANGUAGE_STATE_KEY, "zh")
    st.session_state.setdefault(UI_THEME_STATE_KEY, "light")


def get_ui_language() -> str:
    ensure_ui_preferences()
    language = str(st.session_state.get(UI_LANGUAGE_STATE_KEY, "zh")).strip().lower()
    return "en" if language == "en" else "zh"


def get_ui_theme() -> str:
    ensure_ui_preferences()
    theme = str(st.session_state.get(UI_THEME_STATE_KEY, "light")).strip().lower()
    return "dark" if theme == "dark" else "light"


def translate_text(value: object) -> object:
    if not isinstance(value, str) or get_ui_language() != "en":
        return value

    translated = value
    for source, target in _TRANSLATION_PAIRS:
        if source in translated:
            translated = translated.replace(source, target)
    return translated


def t(zh: str, en: str) -> str:
    return en if get_ui_language() == "en" else zh


def _get_ui_theme_style_values() -> dict[str, str]:
    if get_ui_theme() == "dark":
        return {
            "root_tokens": """
  --bg-canvas: #151210;
  --bg-canvas-strong: #211b17;
  --bg-glow: rgba(224, 161, 108, 0.16);
  --bg-glow-soft: rgba(84, 64, 44, 0.34);

  --surface-main: rgba(41, 33, 28, 0.9);
  --surface-sheet: rgba(45, 36, 30, 0.96);
  --surface-frost: rgba(53, 42, 35, 0.84);
  --surface-soft: rgba(61, 47, 39, 0.9);
  --surface-line: rgba(242, 231, 217, 0.12);
  --surface-line-strong: rgba(242, 231, 217, 0.2);

  --text-strong: #fff4e7;
  --text-primary: #f2e7d9;
  --text-secondary: #d6bea5;
  --text-muted: #bba286;
  --text-inverse: #18130f;

  --accent-primary: #fff4e7;
  --accent-primary-soft: rgba(255, 244, 231, 0.09);
  --accent-warm: #e0a16c;
  --accent-positive: #7ec28d;
  --accent-warning: #f0b469;
  --accent-danger: #ff8d86;

  --shadow-soft: 0 28px 68px rgba(0, 0, 0, 0.34);
  --shadow-board: 0 36px 92px rgba(0, 0, 0, 0.38);
            """.strip(),
            "app_background": """
  background:
    radial-gradient(circle at 14% 10%, var(--bg-glow), transparent 24%),
    radial-gradient(circle at 86% 9%, var(--bg-glow-soft), transparent 25%),
    radial-gradient(circle at 52% 18%, rgba(77, 58, 42, 0.18), transparent 28%),
    linear-gradient(180deg, var(--bg-canvas-strong) 0%, var(--bg-canvas) 100%);
            """.strip(),
            "sidebar_background": "rgba(31, 25, 21, 0.96)",
            "active_tab_shadow": "0 10px 28px rgba(0, 0, 0, 0.25)",
        }

    return {
        "root_tokens": """
  --bg-canvas: #f7efe2;
  --bg-canvas-strong: #f1e3cf;
  --bg-glow: rgba(222, 184, 133, 0.24);
  --bg-glow-soft: rgba(244, 232, 210, 0.56);

  --surface-main: rgba(255, 250, 243, 0.84);
  --surface-sheet: rgba(255, 249, 241, 0.96);
  --surface-frost: rgba(255, 247, 236, 0.8);
  --surface-soft: rgba(245, 233, 213, 0.88);
  --surface-line: rgba(123, 95, 64, 0.12);
  --surface-line-strong: rgba(123, 95, 64, 0.22);

  --text-strong: #18130f;
  --text-primary: #473626;
  --text-secondary: #765d45;
  --text-muted: #9a8268;
  --text-inverse: #fffdf8;

  --accent-primary: #1f1914;
  --accent-primary-soft: rgba(31, 25, 20, 0.08);
  --accent-warm: #ba7349;
  --accent-positive: #4e7c59;
  --accent-warning: #a46429;
  --accent-danger: #b34a45;

  --shadow-soft: 0 24px 56px rgba(78, 54, 29, 0.08);
  --shadow-board: 0 34px 78px rgba(78, 54, 29, 0.1);
        """.strip(),
        "app_background": """
  background:
    radial-gradient(circle at 14% 10%, var(--bg-glow), transparent 24%),
    radial-gradient(circle at 86% 9%, var(--bg-glow-soft), transparent 25%),
    radial-gradient(circle at 52% 18%, rgba(255, 251, 245, 0.86), transparent 28%),
    linear-gradient(180deg, #fbf6ee 0%, var(--bg-canvas) 100%);
        """.strip(),
        "sidebar_background": "rgba(252, 248, 241, 0.96)",
        "active_tab_shadow": "0 8px 24px rgba(78, 54, 29, 0.12)",
    }


def get_plotly_theme_tokens() -> dict[str, object]:
    if get_ui_theme() == "dark":
        return {
            "font_family": '"Avenir Next","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
            "font_color": "#f2e7d9",
            "muted_text": "#c5ab90",
            "paper_bg": "rgba(21, 18, 16, 0.96)",
            "paper_bg_transparent": "rgba(21, 18, 16, 0.0)",
            "plot_bg": "rgba(34, 28, 24, 0.94)",
            "grid": "rgba(242, 231, 217, 0.12)",
            "axis_line": "rgba(242, 231, 217, 0.18)",
            "legend_bg": "rgba(47, 39, 33, 0.92)",
            "annotation_bg": "rgba(47, 39, 33, 0.96)",
            "annotation_border": "rgba(242, 231, 217, 0.14)",
            "accent_warm": "#e0a16c",
            "accent_primary": "#fff3e3",
            "accent_positive": "#7ec28d",
            "accent_danger": "#ff8d86",
            "market_up": "#ff8d86",
            "market_down": "#7ec28d",
            "color_sequence": ["#e0a16c", "#7ec28d", "#8fb4ff", "#ff8d86", "#c9a6ff", "#8ed3d1", "#f2c37a"],
        }

    return {
        "font_family": '"Avenir Next","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
        "font_color": "#473626",
        "muted_text": "#765d45",
        "paper_bg": "rgba(255, 252, 247, 0.94)",
        "paper_bg_transparent": "rgba(255, 252, 247, 0.0)",
        "plot_bg": "rgba(255, 252, 247, 0.94)",
        "grid": "rgba(123, 95, 64, 0.10)",
        "axis_line": "rgba(123, 95, 64, 0.14)",
        "legend_bg": "rgba(255, 249, 241, 0.92)",
        "annotation_bg": "rgba(255, 249, 241, 0.92)",
        "annotation_border": "rgba(123, 95, 64, 0.12)",
        "accent_warm": "#ba7349",
        "accent_primary": "#1f1914",
        "accent_positive": "#4e7c59",
        "accent_danger": "#b34a45",
        "market_up": "#b34a45",
        "market_down": "#4e7c59",
        "color_sequence": ["#ba7349", "#4e7c59", "#496a9f", "#b34a45", "#8a67aa", "#58939a", "#d29b52"],
    }


def apply_plotly_theme(
    fig,
    *,
    height: int | None = None,
    margin: dict[str, int] | None = None,
    transparent_paper: bool = False,
    hovermode: str | None = None,
):
    if fig is None:
        return None

    tokens = get_plotly_theme_tokens()
    legend_update = dict(
        bgcolor=tokens["legend_bg"],
        bordercolor=tokens["axis_line"],
        borderwidth=1,
        font=dict(color=tokens["font_color"]),
        title=dict(font=dict(color=tokens["font_color"])),
    )
    fig.update_layout(
        template="none",
        height=height or getattr(fig.layout, "height", None),
        margin=margin or getattr(fig.layout, "margin", None),
        paper_bgcolor=tokens["paper_bg_transparent"] if transparent_paper else tokens["paper_bg"],
        plot_bgcolor=tokens["plot_bg"],
        font=dict(family=tokens["font_family"], color=tokens["font_color"]),
        colorway=list(tokens["color_sequence"]),
        legend=legend_update,
    )
    if hovermode is not None:
        fig.update_layout(hovermode=hovermode)

    fig.update_xaxes(
        gridcolor=tokens["grid"],
        linecolor=tokens["axis_line"],
        zerolinecolor=tokens["axis_line"],
        tickfont=dict(color=tokens["font_color"]),
        title_font=dict(color=tokens["font_color"]),
    )
    fig.update_yaxes(
        gridcolor=tokens["grid"],
        linecolor=tokens["axis_line"],
        zerolinecolor=tokens["axis_line"],
        tickfont=dict(color=tokens["font_color"]),
        title_font=dict(color=tokens["font_color"]),
    )

    if getattr(fig.layout, "title", None) is not None:
        fig.layout.title.text = translate_text(fig.layout.title.text)
        fig.layout.title.font = {
            **(fig.layout.title.font.to_plotly_json() if fig.layout.title.font else {}),
            "color": tokens["font_color"],
            "family": tokens["font_family"],
        }

    if getattr(fig.layout, "legend", None) is not None and getattr(fig.layout.legend, "title", None) is not None:
        fig.layout.legend.title.text = translate_text(fig.layout.legend.title.text)

    for axis_name in [key for key in fig.layout if str(key).startswith(("xaxis", "yaxis"))]:
        axis = fig.layout[axis_name]
        if getattr(axis, "title", None) is not None and getattr(axis.title, "text", None):
            axis.title.text = translate_text(axis.title.text)
        if getattr(axis, "rangeselector", None) is not None and getattr(axis.rangeselector, "buttons", None):
            for button in axis.rangeselector.buttons:
                if getattr(button, "label", None):
                    button.label = translate_text(button.label)

    for annotation in list(getattr(fig.layout, "annotations", []) or []):
        annotation.text = translate_text(annotation.text)
        if annotation.font is None:
            annotation.font = {}
        annotation.font.color = tokens["font_color"]
        annotation.font.family = tokens["font_family"]
        if getattr(annotation, "bgcolor", None):
            annotation.bgcolor = tokens["annotation_bg"]
        if getattr(annotation, "bordercolor", None):
            annotation.bordercolor = tokens["annotation_border"]

    for trace in list(getattr(fig, "data", []) or []):
        if getattr(trace, "name", None):
            trace.name = translate_text(trace.name)
        if getattr(trace, "hovertemplate", None):
            trace.hovertemplate = translate_text(trace.hovertemplate)
        trace_text = getattr(trace, "text", None)
        if isinstance(trace_text, str):
            trace.text = translate_text(trace_text)
        if getattr(trace, "textfont", None) is not None and hasattr(trace.textfont, "color"):
            trace.textfont.color = tokens["font_color"]
        if getattr(trace, "colorbar", None) is not None and getattr(trace.colorbar, "title", None) is not None:
            trace.colorbar.title.text = translate_text(trace.colorbar.title.text)
            trace.colorbar.title.font = {
                **(trace.colorbar.title.font.to_plotly_json() if trace.colorbar.title.font else {}),
                "color": tokens["font_color"],
            }
    return fig


def _wrap_streamlit_text_method(func_name: str) -> None:
    original = getattr(st, func_name)

    @wraps(original)
    def wrapper(*args, **kwargs):
        if func_name == "tabs" and args and isinstance(args[0], (list, tuple)):
            localized_labels = [
                translate_text(label) if isinstance(label, str) else label
                for label in args[0]
            ]
            args = (localized_labels, *args[1:])
        else:
            args = tuple(translate_text(arg) if isinstance(arg, str) else arg for arg in args)
        for key in ("help", "placeholder"):
            if isinstance(kwargs.get(key), str):
                kwargs[key] = translate_text(kwargs[key])
        if func_name in {"selectbox", "radio", "segmented_control", "multiselect"}:
            if callable(kwargs.get("format_func")):
                base_format = kwargs["format_func"]

                @wraps(base_format)
                def localized_format(value):
                    result = base_format(value)
                    return translate_text(result) if isinstance(result, str) else result

                kwargs["format_func"] = localized_format
            else:
                kwargs["format_func"] = lambda value: translate_text(value) if isinstance(value, str) else value
        return original(*args, **kwargs)

    setattr(st, func_name, wrapper)


def _wrap_streamlit_write() -> None:
    original = st.write

    @wraps(original)
    def wrapper(*args, **kwargs):
        localized_args = tuple(translate_text(arg) if isinstance(arg, str) else arg for arg in args)
        return original(*localized_args, **kwargs)

    st.write = wrapper


def install_streamlit_localizers() -> None:
    if getattr(st, "_strategy_i18n_patched", False):
        return

    for method_name in [
        "markdown",
        "caption",
        "button",
        "checkbox",
        "toggle",
        "text_input",
        "text_area",
        "date_input",
        "multiselect",
        "selectbox",
        "radio",
        "segmented_control",
        "file_uploader",
        "slider",
        "number_input",
        "subheader",
        "header",
        "title",
        "info",
        "warning",
        "error",
        "success",
        "spinner",
        "popover",
        "expander",
        "metric",
        "tabs",
        "form_submit_button",
        "download_button",
    ]:
        if hasattr(st, method_name):
            _wrap_streamlit_text_method(method_name)
    _wrap_streamlit_write()
    st._strategy_i18n_patched = True


def route_href(url_path: str = "") -> str:
    """拼接真实路由路径。"""
    normalized = str(url_path or "").strip().strip("/")
    if not normalized:
        return BASE_ROUTE_PATH
    return f"{BASE_ROUTE_PATH}/{normalized}"


def render_html(markup: str, *, localize: bool = True) -> None:
    """渲染多行 HTML，避免 markdown 缩进把标签当成普通文本。"""
    body = dedent(markup).strip()
    if localize:
        body = str(translate_text(body))
    if hasattr(st, "html"):
        st.html(body)
        return
    st.markdown(body, unsafe_allow_html=True)


def _coerce_date_value(value: object) -> _date | None:
    if value is None:
        return None
    if isinstance(value, _datetime):
        return value.date()
    if isinstance(value, _date):
        return value
    try:
        timestamp = _datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return timestamp.date()


def _normalize_date_range(value: object) -> tuple[_date, ...]:
    if isinstance(value, (list, tuple)):
        normalized = tuple(
            normalized_item
            for normalized_item in (_coerce_date_value(item) for item in value)
            if normalized_item is not None
        )
        return normalized[:2]

    single_value = _coerce_date_value(value)
    return (single_value,) if single_value is not None else ()


def render_analysis_date_range_control(
    *,
    current_range: object,
    key_prefix: str,
    label: str = "时间范围",
    in_hero: bool = False,
) -> None:
    """在分析页头部渲染时间范围控件，并同步到 sidebar 状态。"""
    normalized_current = _normalize_date_range(
        st.session_state.get("sidebar_selected_range", current_range)
    )
    if not normalized_current:
        today = _date.today()
        normalized_current = (today.replace(year=max(2015, today.year - 3)), today)

    widget_key = f"{key_prefix}_header_selected_range"
    if _normalize_date_range(st.session_state.get(widget_key)) != normalized_current:
        st.session_state[widget_key] = normalized_current

    host_key = f"{key_prefix}-header-range"
    with st.container(key=host_key):
        if in_hero:
            st.caption(label)
            selected = st.date_input(
                label,
                value=normalized_current,
                min_value=_date(2015, 1, 1),
                max_value=_date.today(),
                key=widget_key,
                label_visibility="collapsed",
            )
        else:
            control_col, _spacer_col = st.columns([0.78, 1.22], gap="large")
            with control_col:
                st.caption(label)
                selected = st.date_input(
                    label,
                    value=normalized_current,
                    min_value=_date(2015, 1, 1),
                    max_value=_date.today(),
                    key=widget_key,
                    label_visibility="collapsed",
                )

    selected_normalized = _normalize_date_range(selected)
    if selected_normalized and selected_normalized != normalized_current:
        st.session_state["sidebar_selected_range"] = selected_normalized
        st.rerun()


def inject_global_styles() -> None:
    """注入全局共享样式。"""
    ensure_ui_preferences()
    install_streamlit_localizers()
    theme_styles = _get_ui_theme_style_values()
    style_markup = """
<style>
:root {
__ROOT_TOKENS__
}

html,
body,
[class*="css"] {
  font-family: "Avenir Next", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

body {
  color: var(--text-primary);
}

.stApp {
__APP_BACKGROUND__
  color: var(--text-primary);
}

a,
a:hover,
a:visited,
a:active {
  text-decoration: none !important;
}

[data-testid="stHeader"] {
  display: none;
}

#MainMenu,
footer {
  visibility: hidden;
}

[data-testid="stSidebar"] {
  background: __SIDEBAR_BACKGROUND__;
  border-right: 1px solid var(--surface-line);
}

.block-container {
  max-width: 1480px;
  padding-top: 0.7rem;
  padding-bottom: 4rem;
}

[data-baseweb="tab-list"] {
  background: var(--surface-frost);
  border: 1px solid var(--surface-line);
  border-radius: 999px;
  padding: 0.2rem;
  gap: 0.12rem;
}

[data-baseweb="tab"] {
  color: var(--text-secondary);
  border-radius: 999px;
  min-height: 38px;
}

[data-baseweb="tab"][aria-selected="true"] {
  background: var(--surface-sheet);
  color: var(--text-strong);
  box-shadow: __ACTIVE_TAB_SHADOW__;
}

.site-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.3rem;
  margin: 0 auto 2rem;
  padding: 0.35rem 0 0.8rem;
}

div[class*="st-key-route-header-shell-"] {
  margin: 0 auto 2rem;
  padding: 0.35rem 0 0.8rem;
}

div[class*="st-key-route-header-shell-"] > div[data-testid="stHorizontalBlock"] {
  align-items: center;
  gap: clamp(0.9rem, 2vw, 1.45rem);
}

div[class*="st-key-route-header-brand-"],
div[class*="st-key-route-header-preferences-"],
div[class*="st-key-route-header-nav-"] {
  min-width: 0;
}

div[class*="st-key-route-header-brand-"] .site-brand-wrap {
  min-height: 3rem;
}

div[class*="st-key-route-header-preferences-"] {
  display: flex;
  align-items: center;
  max-width: 392px;
  margin: 0 0 0 auto;
}

div[class*="st-key-route-header-preferences-"] > div[data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-route-header-preferences-"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
  display: flex;
  align-items: center;
}

div[class*="st-key-route-header-preferences-"] [data-testid="stSegmentedControl"] {
  width: 100%;
  margin: 0;
}

div[class*="st-key-route-header-nav-"] {
  display: flex;
  justify-content: flex-end;
}

div[class*="st-key-route-header-nav-"] .site-nav {
  margin-left: auto;
}

.site-brand-wrap {
  display: flex;
  align-items: center;
}

.site-brand-mark {
  display: none;
}

.site-brand-copy {
  display: flex;
  align-items: center;
}

.site-brand {
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: 1.68rem;
  font-style: italic;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.site-brand:hover,
.site-brand:visited,
.site-brand:active {
  color: var(--text-strong);
}

.site-brand-subtitle {
  display: none;
}

.site-nav {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.18rem;
  padding: 0.3rem;
  border: 1px solid var(--surface-line);
  border-radius: 999px;
  background: rgba(255, 249, 241, 0.78);
  box-shadow: var(--shadow-soft);
}

.site-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0.58rem 0.98rem;
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 0.95rem;
  font-weight: 600;
  transition: color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.site-link:hover,
.site-link.active {
  color: var(--text-strong);
  background: rgba(255, 253, 248, 0.98);
  box-shadow: 0 8px 18px rgba(78, 54, 29, 0.08);
}

.page-kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--accent-warm);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.page-kicker::before {
  content: "";
  width: 1.7rem;
  height: 1px;
  background: rgba(186, 115, 73, 0.38);
}

.hero-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(430px, 0.95fr);
  align-items: start;
  gap: clamp(2rem, 4vw, 3.8rem);
  margin-bottom: 3rem;
  padding-top: clamp(0.8rem, 2vw, 2rem);
}

.hero-copy-column {
  padding-top: clamp(0.2rem, 1vw, 1rem);
}

.hero-title,
.entry-title {
  margin: 1rem 0 0.85rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  line-height: 0.96;
  letter-spacing: -0.05em;
}

.hero-title {
  font-size: clamp(3.2rem, 5.8vw, 5.5rem);
}

.entry-title {
  font-size: clamp(2.3rem, 4.6vw, 3.4rem);
}

.hero-copy,
.entry-copy {
  max-width: 560px;
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.05rem;
  line-height: 1.78;
}

.entry-intro {
  max-width: 780px;
  margin: 0 0 1.6rem;
}

.action-card {
  max-width: 470px;
  margin-top: 1.55rem;
  padding: 1.45rem 1.5rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

.action-card-kicker,
.surface-kicker {
  color: var(--text-muted);
  font-size: 0.79rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.action-card-title {
  margin: 0.45rem 0 0.35rem;
  color: var(--text-strong);
  font-size: 1.12rem;
  font-weight: 700;
}

.action-card-copy,
.surface-copy,
.section-copy {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.68;
}

.cta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.cta-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0.72rem 1.16rem;
  border: 1px solid transparent;
  border-radius: 999px;
  background: var(--accent-primary);
  color: var(--text-inverse);
  font-weight: 700;
  transition: transform 0.15s ease, opacity 0.15s ease, background 0.15s ease;
}

.cta-link:hover {
  transform: translateY(-1px);
  opacity: 0.97;
}

.cta-link:hover,
.cta-link:visited,
.cta-link:active {
  color: var(--text-inverse);
}

.cta-link.secondary {
  border-color: var(--surface-line-strong);
  background: rgba(255, 252, 247, 0.78);
  color: var(--text-strong);
}

.cta-link.secondary:hover,
.cta-link.secondary:visited,
.cta-link.secondary:active {
  color: var(--text-strong);
}

.cta-link.pill-secondary {
  min-height: 36px;
  padding: 0.42rem 0.9rem;
  border-color: rgba(123, 95, 64, 0.16);
  background: rgba(255, 252, 247, 0.9);
  color: var(--text-strong);
  font-size: 0.84rem;
  font-weight: 700;
  box-shadow: none;
}

.cta-link.pill-secondary:hover,
.cta-link.pill-secondary:visited,
.cta-link.pill-secondary:active {
  color: var(--text-strong);
}

.hero-note-list {
  display: grid;
  gap: 0.75rem;
  margin-top: 1.2rem;
}

.hero-note-item {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.65;
}

.hero-note-item strong {
  min-width: 2rem;
  color: var(--text-strong);
  font-size: 0.84rem;
}

.showcase-board {
  position: relative;
  min-height: 650px;
  padding: 1.5rem;
  border: 1px solid var(--surface-line);
  border-radius: 34px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
  overflow: hidden;
}

.showcase-board::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 12%, rgba(255, 255, 255, 0.78), transparent 22%),
    radial-gradient(circle at 86% 16%, rgba(251, 239, 222, 0.6), transparent 20%),
    radial-gradient(circle at 58% 72%, rgba(232, 204, 170, 0.24), transparent 24%);
  pointer-events: none;
}

.home-showcase {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: auto;
  margin-top: clamp(1.1rem, 2vw, 1.55rem);
}

.home-showcase-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(220px, 0.88fr);
  gap: 1rem;
}

.home-showcase-stack {
  display: grid;
  gap: 1rem;
}

.board-chip {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.38rem 0.76rem;
  border-radius: 999px;
  background: rgba(255, 251, 245, 0.84);
  color: var(--text-secondary);
  font-size: 0.81rem;
  font-weight: 700;
}

.board-chip::before {
  content: "";
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: var(--accent-warm);
}

.board-main-sheet,
.floating-sheet {
  position: absolute;
  border: 1px solid var(--surface-line);
  border-radius: 24px;
  background: rgba(255, 249, 241, 0.92);
  box-shadow: var(--shadow-soft);
}

.board-main-sheet {
  left: 2rem;
  right: 2rem;
  bottom: 1.9rem;
  padding: 1.28rem 1.34rem;
}

.floating-sheet {
  padding: 1rem 1.05rem;
}

.home-showcase .floating-sheet,
.home-showcase .board-main-sheet {
  position: relative;
  left: auto;
  right: auto;
  top: auto;
  bottom: auto;
  width: auto !important;
}

.home-showcase .sheet-market {
  min-height: 216px;
  padding: 1.1rem 1.15rem;
}

.home-showcase .sheet-workflow,
.home-showcase .sheet-progress {
  min-height: 132px;
}

.floating-sheet-title {
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.floating-sheet-copy {
  margin-top: 0.35rem;
  color: var(--text-secondary);
  font-size: 0.91rem;
  line-height: 1.6;
}

.board-main-sheet h3 {
  margin: 0.45rem 0 0.35rem;
  color: var(--text-strong);
  font-size: 1.3rem;
  font-weight: 700;
}

.board-main-sheet p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.94rem;
  line-height: 1.7;
}

.board-flow-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.9rem;
}

.board-flow-row span {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0.38rem 0.8rem;
  border-radius: 999px;
  background: var(--accent-primary-soft);
  color: var(--text-primary);
  font-size: 0.84rem;
  font-weight: 600;
}

.board-flow-row.compact {
  margin-top: 0.75rem;
}

.board-flow-row.compact span {
  min-height: 30px;
  padding: 0.32rem 0.72rem;
  font-size: 0.8rem;
}

.board-micro-list {
  display: grid;
  gap: 0.45rem;
  margin-top: 0.7rem;
}

.board-micro-item {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.board-micro-item strong {
  color: var(--text-strong);
  font-weight: 700;
}

.home-showcase .board-main-sheet {
  z-index: 1;
  margin-top: 0.2rem;
}

.board-footnote {
  margin-top: 0.75rem !important;
  color: var(--text-muted) !important;
  font-size: 0.88rem !important;
  line-height: 1.55 !important;
}

.support-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.6rem;
}

.support-block {
  padding-top: 1rem;
  border-top: 1px solid var(--surface-line);
}

.support-block h3 {
  margin: 0 0 0.35rem;
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.support-block p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.94rem;
  line-height: 1.7;
}

.support-cta-row {
  display: flex;
  flex-wrap: wrap;
  margin-top: 0.95rem;
}

.support-cta-row .cta-link {
  width: auto;
}

div[class*="st-key-single-action-card"],
div[class*="st-key-multi-action-card"] {
  padding: 1.4rem 1.45rem 1.3rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-showcase-board"],
div[class*="st-key-multi-showcase-board"] {
  min-height: 720px;
  padding: 1.35rem 1.4rem 1.25rem;
  border: 1px solid var(--surface-line);
  border-radius: 32px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
}

div[class*="st-key-single-recommend-sheet"],
div[class*="st-key-multi-recommend-sheet"] {
  margin-top: 1rem;
  padding: 1.12rem 1.15rem 0.8rem;
  border: 1px solid var(--surface-line);
  border-radius: 24px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-basic-section"],
div[class*="st-key-single-stock-strategy-section"],
div[class*="st-key-multi-stock-basic-section"],
div[class*="st-key-multi-stock-strategy-section"] {
  padding: 1.45rem 1.5rem 1.35rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-analysis-hero"],
div[class*="st-key-multi-stock-analysis-hero"] {
  padding: 1.55rem 1.6rem 1.35rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(248, 237, 220, 0.92));
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-analysis-hero"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-stock-analysis-hero"] [data-testid="stHorizontalBlock"] {
  align-items: stretch;
}

div[class*="st-key-single-stock-header-range"],
div[class*="st-key-multi-stock-header-range"] {
  margin-top: 1rem;
  padding: 0.95rem 1rem 0.22rem;
  border: 1px solid rgba(123, 95, 64, 0.1);
  border-radius: 24px;
  background: rgba(255, 249, 241, 0.74);
}

div[class*="st-key-single-stock-header-range"] [data-testid="stDateInputField"],
div[class*="st-key-multi-stock-header-range"] [data-testid="stDateInputField"] {
  min-height: 54px;
  border-radius: 22px !important;
  background: rgba(255, 251, 245, 0.94) !important;
  box-shadow: none;
}

div[class*="st-key-single-stock-chart-frame"],
div[class*="st-key-multi-stock-chart-frame"] {
  padding: 1.05rem 1.1rem 0.82rem;
  border-radius: 26px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 252, 247, 0.94);
}

div[class*="st-key-multi-stock-basic-panel"],
div[class*="st-key-multi-stock-strategy-panel"] {
  padding: 1.12rem 1.15rem 1rem;
  border-radius: 26px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 252, 247, 0.94);
}

.surface-title {
  margin: 0.35rem 0 0.25rem;
  color: var(--text-strong);
  font-size: 1.24rem;
  font-weight: 700;
}

.entry-section-title {
  margin: 0;
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.entry-section-copy {
  margin: 0.22rem 0 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.62;
}

.section-divider {
  height: 1px;
  margin: 1.15rem 0;
  background: var(--surface-line);
}

.plain-helper {
  margin: 0.55rem 0 0;
  color: var(--text-muted);
  font-size: 0.89rem;
  line-height: 1.6;
}

.selection-note,
.source-note {
  margin: 0.65rem 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.55;
}

.selection-note strong,
.source-note strong {
  color: var(--text-strong);
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
  margin-top: 1rem;
}

.snapshot-item {
  padding: 0.95rem 1rem;
  border-radius: 20px;
  background: rgba(255, 248, 239, 0.58);
  border: 1px solid rgba(123, 95, 64, 0.08);
  backdrop-filter: blur(8px);
}

.snapshot-label {
  display: block;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.snapshot-value {
  display: block;
  margin-top: 0.38rem;
  color: var(--text-strong);
  font-size: 1.16rem;
  font-weight: 700;
}

.snapshot-delta {
  display: block;
  margin-top: 0.22rem;
  color: var(--text-muted);
  font-size: 0.88rem;
  font-weight: 600;
}

.snapshot-delta.up {
  color: var(--accent-danger);
}

.snapshot-delta.down {
  color: var(--accent-positive);
}

div[class*="st-key-single-recommend-scroll"],
div[class*="st-key-multi-recommend-scroll"] {
  max-height: 390px;
  overflow-y: auto;
  padding-right: 0.1rem;
}

div[class*="st-key-single-recommend-scroll"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-recommend-scroll"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-selected-symbols"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-stock-remove-list"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-stock-add-list"] [data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-single-recommend-scroll"] [data-testid="column"],
div[class*="st-key-multi-recommend-scroll"] [data-testid="column"],
div[class*="st-key-multi-selected-symbols"] [data-testid="column"],
div[class*="st-key-multi-stock-remove-list"] [data-testid="column"],
div[class*="st-key-multi-stock-add-list"] [data-testid="column"] {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

div[class*="st-key-single-recommend-scroll"]::-webkit-scrollbar,
div[class*="st-key-multi-recommend-scroll"]::-webkit-scrollbar {
  width: 7px;
}

div[class*="st-key-single-recommend-scroll"]::-webkit-scrollbar-thumb,
div[class*="st-key-multi-recommend-scroll"]::-webkit-scrollbar-thumb {
  background: rgba(149, 122, 91, 0.42);
  border-radius: 999px;
}

.recommend-row,
.selection-row,
.upload-row {
  padding: 0.82rem 0;
  border-bottom: 1px solid rgba(123, 95, 64, 0.1);
}

.recommend-row-title,
.selection-row-title,
.upload-row-title {
  color: var(--text-strong);
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1.35;
}

.recommend-row-meta,
.selection-row-meta,
.upload-row-meta {
  margin-top: 0.18rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.55;
}

div[class*="st-key-single-recommend-scroll"] .stButton,
div[class*="st-key-multi-recommend-scroll"] .stButton,
div[class*="st-key-multi-selected-symbols"] .stButton,
div[class*="st-key-multi-stock-remove-list"] .stButton,
div[class*="st-key-multi-stock-add-list"] .stButton {
  display: flex;
  justify-content: flex-end;
}

div[class*="st-key-single-recommend-scroll"] .stButton > button,
div[class*="st-key-multi-recommend-scroll"] .stButton > button,
div[class*="st-key-multi-selected-symbols"] .stButton > button {
  min-width: 84px;
  min-height: 34px;
  padding: 0.32rem 0.8rem;
  font-size: 0.82rem;
  font-weight: 700;
}

div[class*="st-key-multi-stock-remove-list"] .stButton > button,
div[class*="st-key-multi-stock-add-list"] .stButton > button {
  min-width: 72px;
  min-height: 38px;
  padding: 0.3rem 0.72rem;
  border-radius: 16px !important;
  font-size: 0.82rem;
  box-shadow: none;
}

div[class*="st-key-multi-stock-remove-list"] .stButton > button {
  border-color: rgba(179, 74, 69, 0.22) !important;
  background: rgba(255, 245, 243, 0.92) !important;
  color: var(--accent-danger) !important;
}

div[class*="st-key-multi-stock-remove-list"] .stButton > button:hover {
  border-color: rgba(179, 74, 69, 0.34) !important;
  background: rgba(255, 250, 247, 0.98) !important;
}

div[class*="st-key-multi-stock-add-list"] .stButton > button {
  border-color: rgba(78, 124, 89, 0.18) !important;
  background: rgba(244, 250, 245, 0.92) !important;
  color: var(--accent-positive) !important;
}

div[class*="st-key-multi-stock-add-list"] .stButton > button:hover {
  border-color: rgba(78, 124, 89, 0.3) !important;
  background: rgba(250, 253, 250, 0.98) !important;
}

.analysis-page-shell {
  display: grid;
  gap: 1.6rem;
  margin: 1.1rem 0 0.35rem;
}

.analysis-hero {
  padding: 1.55rem 1.6rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(248, 237, 220, 0.92));
  box-shadow: var(--shadow-soft);
}

.analysis-hero-topline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.7rem;
  margin-bottom: 0.9rem;
}

.analysis-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0.34rem 0.8rem;
  border: 1px solid rgba(123, 95, 64, 0.14);
  border-radius: 999px;
  background: rgba(255, 252, 247, 0.84);
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.analysis-pill.accent {
  background: rgba(186, 115, 73, 0.12);
  color: var(--accent-warm);
  border-color: rgba(186, 115, 73, 0.2);
}

.analysis-pill.positive {
  color: var(--accent-positive);
}

.analysis-pill.negative {
  color: var(--accent-danger);
}

.analysis-hero-main {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
  gap: 1.2rem;
  align-items: start;
}

.analysis-title {
  margin: 0;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: clamp(2rem, 3.6vw, 3.1rem);
  line-height: 0.98;
  letter-spacing: -0.04em;
}

.analysis-subtitle {
  margin-top: 0.55rem;
  color: var(--text-secondary);
  font-size: 0.98rem;
  line-height: 1.7;
}

.analysis-quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
}

.analysis-quick-item {
  min-width: 0;
  padding: 0.95rem 1rem;
  border-radius: 22px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 249, 241, 0.88);
}

.analysis-quick-label {
  display: block;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.analysis-quick-value {
  display: block;
  min-width: 0;
  margin-top: 0.4rem;
  color: var(--text-strong);
  font-size: 1.12rem;
  font-weight: 700;
  line-height: 1.38;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.analysis-quick-meta {
  display: block;
  margin-top: 0.24rem;
  color: var(--text-secondary);
  font-size: 0.86rem;
  line-height: 1.45;
}

.analysis-market-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.7rem;
  margin-top: 1rem;
}

.analysis-market-card {
  padding: 0.92rem 0.98rem;
  border-radius: 22px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 250, 243, 0.72);
}

.analysis-market-label {
  display: block;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.analysis-market-value {
  display: block;
  margin-top: 0.38rem;
  color: var(--text-strong);
  font-size: 1.08rem;
  font-weight: 700;
}

.analysis-market-delta {
  display: block;
  margin-top: 0.18rem;
  color: var(--text-muted);
  font-size: 0.86rem;
  font-weight: 600;
}

.analysis-market-delta.up {
  color: var(--accent-danger);
}

.analysis-market-delta.down {
  color: var(--accent-positive);
}

.analysis-nav-shell {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
}

.analysis-nav-links {
  display: inline-flex;
  align-items: center;
  width: 100%;
  gap: 0.32rem;
  padding: 0.34rem;
  border: 1px solid var(--surface-line);
  border-radius: 24px;
  background: rgba(255, 249, 241, 0.9);
  box-shadow: var(--shadow-soft);
}

.analysis-nav-links-wide {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.analysis-nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 46px;
  padding: 0.6rem 1.05rem;
  border-radius: 18px;
  color: var(--text-secondary);
  font-size: 0.92rem;
  font-weight: 700;
}

.analysis-nav-link:hover,
.analysis-nav-link:visited,
.analysis-nav-link:active {
  color: var(--text-strong);
}

.analysis-nav-link.is-active {
  background: rgba(255, 252, 247, 0.98);
  color: var(--text-strong);
  box-shadow: 0 8px 18px rgba(78, 54, 29, 0.08);
}

div[class*="st-key-single-stock-switch-popover"] .stPopover,
div[class*="st-key-multi-stock-edit-popover"] .stPopover {
  width: 100%;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button,
div[class*="st-key-multi-stock-remove-popover"] .stPopover > button,
div[class*="st-key-multi-stock-add-popover"] .stPopover > button {
  width: 100%;
  min-height: 48px;
  padding: 0.6rem 1.05rem;
  border: 1px solid var(--surface-line) !important;
  border-radius: 24px !important;
  background: rgba(255, 249, 241, 0.9) !important;
  color: var(--text-strong) !important;
  font-size: 0.92rem;
  font-weight: 700;
  box-shadow: var(--shadow-soft);
  justify-content: center;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button:hover,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button:hover,
div[class*="st-key-multi-stock-remove-popover"] .stPopover > button:hover,
div[class*="st-key-multi-stock-add-popover"] .stPopover > button:hover {
  border-color: rgba(123, 95, 64, 0.24) !important;
  background: rgba(255, 252, 247, 0.98) !important;
}

div[class*="st-key-multi-stock-remove-popover"] .stPopover > button {
  border-color: rgba(179, 74, 69, 0.18) !important;
  background: rgba(255, 246, 244, 0.92) !important;
}

div[class*="st-key-multi-stock-remove-popover"] .stPopover > button:hover {
  border-color: rgba(179, 74, 69, 0.28) !important;
  background: rgba(255, 250, 247, 0.98) !important;
}

div[class*="st-key-multi-stock-add-popover"] .stPopover > button {
  border-color: rgba(78, 124, 89, 0.16) !important;
  background: rgba(246, 251, 247, 0.92) !important;
}

div[class*="st-key-multi-stock-add-popover"] .stPopover > button:hover {
  border-color: rgba(78, 124, 89, 0.26) !important;
  background: rgba(250, 253, 250, 0.98) !important;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button p,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button p {
  margin: 0;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button svg,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button svg {
  color: var(--text-secondary);
}

.analysis-section-block {
  padding: 1.45rem 1.5rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

.analysis-section-header {
  margin-bottom: 1.05rem;
}

.analysis-section-title {
  margin: 0.3rem 0 0;
  color: var(--text-strong);
  font-size: 1.4rem;
  font-weight: 700;
}

.analysis-section-copy {
  margin: 0.4rem 0 0;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.7;
}

.analysis-kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.analysis-kv-item {
  padding: 0.92rem 0.96rem;
  border-radius: 20px;
  background: rgba(248, 238, 224, 0.64);
  border: 1px solid rgba(123, 95, 64, 0.08);
}

.analysis-kv-label {
  display: block;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.analysis-kv-value {
  display: block;
  margin-top: 0.34rem;
  color: var(--text-strong);
  font-size: 1.08rem;
  font-weight: 700;
}

.analysis-kv-meta {
  display: block;
  margin-top: 0.16rem;
  color: var(--text-secondary);
  font-size: 0.84rem;
  line-height: 1.45;
}

.analysis-chart-frame {
  padding: 1.1rem 1.15rem 0.8rem;
  border-radius: 26px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 252, 247, 0.94);
}

.analysis-chart-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  flex-wrap: wrap;
  margin-bottom: 0.7rem;
}

.analysis-chart-title {
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.analysis-chart-copy {
  color: var(--text-secondary);
  font-size: 0.88rem;
  line-height: 1.55;
}

.analysis-chart-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.42rem;
  margin-top: 0.75rem;
}

.analysis-chart-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0.3rem 0.68rem;
  border-radius: 999px;
  background: rgba(31, 25, 20, 0.06);
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 700;
}

div[class*="st-key-single-stock-strategy-control-panel"],
div[class*="st-key-single-stock-strategy-result-board"] {
  padding: 1.25rem 1.2rem 1.15rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-strategy-result-board"] {
  background: rgba(255, 252, 247, 0.96);
}

div[class*="st-key-model-evaluation-control-card"],
div[class*="st-key-model-evaluation-detail-section"] {
  padding: 1.35rem 1.4rem 1.22rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-model-evaluation-tabs-shell"] {
  margin-top: 0.18rem;
}

div[class*="st-key-model-evaluation-tabs-shell"] [data-baseweb="tab-list"],
div[class*="st-key-model-evaluation-tabs-shell"] [role="tablist"] {
  padding: 0.28rem 0.4rem;
  gap: 0.32rem;
  margin-bottom: 0.4rem;
}

div[class*="st-key-model-evaluation-tabs-shell"] [data-baseweb="tab"],
div[class*="st-key-model-evaluation-tabs-shell"] button[role="tab"] {
  min-height: 44px;
  padding: 0.2rem 1rem 0.9rem;
  font-weight: 600;
  line-height: 1.35;
}

div[class*="st-key-model-evaluation-tabs-shell"] [data-baseweb="tab-panel"] {
  padding-top: 0.28rem;
}

div[class*="st-key-model-evaluation-summary-board"] {
  min-height: 520px;
  padding: 1.35rem 1.4rem 1.25rem;
  border: 1px solid var(--surface-line);
  border-radius: 32px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
}

.model-eval-rank-list {
  display: grid;
  gap: 0.72rem;
  margin-top: 1rem;
}

.model-eval-rank-item {
  display: flex;
  gap: 0.78rem;
  align-items: flex-start;
  padding: 0.86rem 0.92rem;
  border-radius: 22px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 249, 241, 0.86);
}

.model-eval-rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 30px;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  background: rgba(31, 25, 20, 0.08);
  color: var(--text-strong);
  font-size: 0.8rem;
  font-weight: 700;
}

.model-eval-rank-copy {
  display: grid;
  gap: 0.18rem;
}

.model-eval-rank-title {
  color: var(--text-strong);
  font-size: 0.98rem;
  font-weight: 700;
}

.model-eval-rank-meta,
.model-eval-rank-empty {
  color: var(--text-secondary);
  font-size: 0.88rem;
  line-height: 1.58;
}

div[class*="st-key-single-stock-strategy-control-panel"] .stDivider,
div[class*="st-key-single-stock-strategy-result-board"] .stDivider {
  margin: 0.8rem 0 1rem;
}

div[class*="st-key-single-stock-strategy-control-panel"] [data-testid="stSegmentedControl"],
div[class*="st-key-single-stock-strategy-result-board"] [data-testid="stSegmentedControl"] {
  margin: 0.1rem 0 0.65rem;
}

.analysis-subsurface {
  padding: 1rem 1.05rem;
  border-radius: 24px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(248, 238, 224, 0.46);
}

.analysis-subsurface + .analysis-subsurface {
  margin-top: 0.95rem;
}

.analysis-callout-title {
  margin: 0;
  color: var(--text-strong);
  font-size: 1.02rem;
  font-weight: 700;
}

.analysis-callout-copy {
  margin: 0.34rem 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.62;
}

.status-note {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  margin-top: 0.5rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  line-height: 1.58;
}

.status-note::before {
  content: "";
  width: 0.42rem;
  height: 0.42rem;
  margin-top: 0.45rem;
  border-radius: 999px;
  background: rgba(154, 130, 104, 0.72);
  flex: 0 0 auto;
}

.status-note.warning {
  color: var(--accent-warning);
}

.status-note.warning::before {
  background: rgba(164, 100, 41, 0.66);
}

.status-note.error {
  color: var(--accent-danger);
}

.status-note.error::before {
  background: rgba(179, 74, 69, 0.72);
}

.status-note.positive {
  color: var(--accent-positive);
}

.status-note.positive::before {
  background: rgba(78, 124, 89, 0.72);
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
  min-height: 42px;
  padding: 0.64rem 0.96rem;
  border: 1px solid var(--surface-line-strong);
  border-radius: 999px;
  background: rgba(255, 251, 245, 0.84);
  color: var(--text-strong);
  font-weight: 700;
  box-shadow: none;
  transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
  transform: translateY(-1px);
  background: rgba(255, 252, 247, 0.98);
  border-color: rgba(123, 95, 64, 0.28);
}

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
  background: var(--accent-primary);
  color: var(--text-inverse);
  border-color: transparent;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
div[data-baseweb="select"] > div,
[data-testid="stDateInputField"],
[data-testid="stFileUploaderDropzone"] {
  border-radius: 18px !important;
  border-color: rgba(123, 95, 64, 0.16) !important;
  background: rgba(255, 251, 245, 0.76) !important;
  color: var(--text-primary) !important;
}

[data-testid="stFileUploaderDropzone"] {
  border-style: dashed !important;
}

[data-testid="stSegmentedControl"] {
  padding: 0.24rem;
  border: 1px solid var(--surface-line);
  border-radius: 999px;
  background: rgba(255, 250, 242, 0.68);
}

[data-testid="stSegmentedControl"] button {
  min-height: 38px;
  border-radius: 999px !important;
  color: var(--text-secondary) !important;
}

[data-testid="stSegmentedControl"] button[aria-selected="true"],
[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
  background: var(--accent-primary) !important;
  color: var(--text-inverse) !important;
}

[data-testid="stRadio"] > div {
  gap: 0.55rem;
}

[data-testid="stRadio"] label {
  padding: 0.82rem 0.9rem;
  border: 1px solid var(--surface-line);
  border-radius: 18px;
  background: rgba(255, 251, 245, 0.68);
}

[data-testid="stRadio"] label:hover {
  border-color: rgba(123, 95, 64, 0.24);
}

[data-testid="stCaptionContainer"],
.stCaption,
.stMarkdown small,
.stMarkdown a {
  color: var(--text-muted);
}

@media (max-width: 1100px) {
  .hero-shell {
    grid-template-columns: 1fr;
    gap: 2rem;
  }

  .home-showcase {
    margin-top: 0;
  }

  div[class*="st-key-single-showcase-board"],
  div[class*="st-key-multi-showcase-board"],
  div[class*="st-key-model-evaluation-summary-board"] {
    min-height: 620px;
  }
}

@media (max-width: 880px) {
  .site-header,
  div[class*="st-key-route-header-shell-"] > div[data-testid="stHorizontalBlock"] {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  div[class*="st-key-route-header-shell-"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  div[class*="st-key-route-header-preferences-"] {
    max-width: none;
    margin: 0;
  }

  div[class*="st-key-route-header-nav-"] {
    justify-content: flex-start;
  }

  div[class*="st-key-route-header-nav-"] .site-nav {
    margin-left: 0;
  }

  .support-columns,
  .snapshot-grid {
    grid-template-columns: 1fr;
  }

  .home-showcase-grid {
    grid-template-columns: 1fr;
  }

  .showcase-board,
  div[class*="st-key-single-showcase-board"],
  div[class*="st-key-multi-showcase-board"],
  div[class*="st-key-model-evaluation-summary-board"] {
    min-height: auto;
  }

  .analysis-hero-main,
  .analysis-quick-grid,
  .analysis-market-strip,
  .analysis-kv-grid {
    grid-template-columns: 1fr;
  }

  .board-main-sheet,
  .floating-sheet {
    position: static;
    width: auto !important;
    margin-top: 0.85rem;
  }
}

@media (max-width: 640px) {
  .hero-title {
    font-size: 2.95rem;
  }

  .entry-title {
    font-size: 2.18rem;
  }

  .site-nav {
    width: 100%;
    justify-content: space-between;
  }

  div[class*="st-key-route-header-preferences-"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  .cta-row {
    width: 100%;
  }

  .cta-link {
    width: 100%;
  }
}
</style>
        """
    style_markup = style_markup.replace("__ROOT_TOKENS__", theme_styles["root_tokens"])
    style_markup = style_markup.replace("__APP_BACKGROUND__", theme_styles["app_background"])
    style_markup = style_markup.replace("__SIDEBAR_BACKGROUND__", theme_styles["sidebar_background"])
    style_markup = style_markup.replace("__ACTIVE_TAB_SHADOW__", theme_styles["active_tab_shadow"])
    render_html(style_markup, localize=False)


def render_route_nav(current: str) -> None:
    """渲染站点级顶部导航。"""
    ensure_ui_preferences()
    nav_items = [
        ("home", t("首页", "Home"), route_href("")),
        ("single", t("单股分析", "Single Stock"), route_href("stock-analysis")),
        ("multi", t("多股分析", "Multi Stock"), route_href("stocks-analysis")),
    ]
    links_html = "".join(
        f"<a class='site-link {'active' if key == current else ''}' href='{href}'>{label}</a>"
        for key, label, href in nav_items
    )
    current_language = get_ui_language()
    current_theme = get_ui_theme()

    with st.container(key=f"route-header-shell-{current}"):
        brand_col, preference_col, nav_col = st.columns([0.78, 0.86, 1.04], gap="large", vertical_alignment="center")

        with brand_col:
            with st.container(key=f"route-header-brand-{current}"):
                render_html(
                    f"""
<div class="site-brand-wrap">
  <span class="site-brand-mark"></span>
  <div class="site-brand-copy">
    <a class="site-brand" href="{route_href('')}">Strategy Lab</a>
    <div class="site-brand-subtitle">{t("\u5355\u80a1\u7814\u7a76\u4e0e\u591a\u80a1\u6bd4\u8f83\u7684\u8def\u7531\u5f0f\u7b56\u7565\u7ad9\u70b9\u3002", "A route-based strategy site for single-stock research and multi-stock comparison.")}</div>
  </div>
</div>
                    """
                )

        with preference_col:
            with st.container(key=f"route-header-preferences-{current}"):
                preference_col1, preference_col2 = st.columns(2, gap="small", vertical_alignment="center")

                with preference_col1:
                    selected_language = st.segmented_control(
                        "Language",
                        options=["zh", "en"],
                        format_func=lambda value: "\u4e2d\u6587" if value == "zh" else "EN",
                        default=current_language,
                        key=f"route_nav_language_{current}",
                        label_visibility="collapsed",
                        width="stretch",
                    ) or current_language

                with preference_col2:
                    selected_theme = st.segmented_control(
                        "Theme",
                        options=["light", "dark"],
                        format_func=lambda value: t("\u4eae\u8272", "Light") if value == "light" else t("\u6697\u8272", "Dark"),
                        default=current_theme,
                        key=f"route_nav_theme_{current}",
                        label_visibility="collapsed",
                        width="stretch",
                    ) or current_theme

        with nav_col:
            with st.container(key=f"route-header-nav-{current}"):
                render_html(f"<nav class='site-nav'>{links_html}</nav>")

    if selected_language != current_language:
        st.session_state[UI_LANGUAGE_STATE_KEY] = selected_language
        st.rerun()
    if selected_theme != current_theme:
        st.session_state[UI_THEME_STATE_KEY] = selected_theme
        st.rerun()


def render_status_note(message: str, tone: str = "info") -> None:
    """渲染内联状态提示。"""
    tone_class = tone if tone in {"info", "positive", "warning", "error"} else "info"
    st.markdown(
        f"<div class='status-note {tone_class}'>{html.escape(str(translate_text(message)))}</div>",
        unsafe_allow_html=True,
    )
