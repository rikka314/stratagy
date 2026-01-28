# 项目日志说明（当前版本 v2.0）

## 🆕 版本 2.0 更新日志（2026-01-28）

### 新增功能：多股票对比分析

#### 1. 多股票管理系统
- ✅ 智能股票搜索与添加功能
  - 侧边栏"多股票对比"专区
  - 输入股票代码自动检测本地数据
  - 自动下载缺失的股票数据到 `data/` 目录
  - 本地数据缓存，避免重复下载

#### 2. 交互式归一化价格对比图表
- ✅ 专业金融风格设计
  - 所有股票起点归一化为 100，直观对比涨跌幅
  - 10种高区分度配色方案
  - 图例显示股票代码和期间收益率
  - 基准线标注起点（虚线）

- ✅ 丰富的交互功能
  - 统一悬停模式：同时显示所有股票数据
  - 快速时间选择器：1周/1月/3月/6月/1年/全部
  - 范围滑块：精确控制显示时间区间
  - 点击图例隐藏/显示特定股票
  - 双击重置视图
  - 高清图表导出（PNG 1200x800px @2x）

#### 3. 股票相关性分析
- ✅ 相关性热图
  - 基于日收益率计算Pearson相关系数
  - 红蓝配色：正相关/负相关/无相关性
  - 数值悬停提示
  - 帮助分散投资风险

#### 4. 详细统计对比
- ✅ 关键指标卡片
  - 对比股票数量
  - 平均数据天数
  - 最佳表现股票及收益率

- ✅ 可展开详细表格
  - 起始价格与最新价格
  - 总收益率
  - 年化波动率
  - 价格区间（最高/最低）
  - 数据完整性

### 技术改进

#### 数据管理
- 新增 `load_or_fetch_stock()` 函数：智能加载/下载股票数据
- 新增 `get_available_stocks()` 函数：扫描本地数据库
- 数据文件命名规范：`{symbol}_daily.csv`

#### 可视化增强
- 新增 `create_multi_stock_comparison_chart()` 函数：创建归一化对比图
- 新增 `create_correlation_heatmap()` 函数：创建相关性热图
- 新增 `normalize_prices()` 函数：价格归一化处理

#### 状态管理
- 使用 `st.session_state` 管理多股票选择状态
- 变量作用域优化，避免重复渲染

### 文档更新
- ✅ 新增 `MULTI_STOCK_FEATURE.md` - 多股票功能完整使用指南
- ✅ 更新 `PROJECT_LOG.md` - 记录v2.0更新内容

---

## 1. 项目概况
这是一个基于 Streamlit 的股票策略实验 WebApp，默认使用 AkShare 下载 AAPL 日线数据，也支持用户上传 CSV。应用提供：
- 📊 **多股票对比分析**（v2.0新增）
- 📈 K 线图、RSI/MACD 指标图
- 🎯 因子评分曲线与分位数
- 💡 策略建议
- 📉 训练/测试集表现
- 🔄 Walk-Forward 回测
- 🔍 自动参数搜索与一键应用推荐参数

## 2. 目录结构
- `app.py`：主应用，包含数据获取、指标计算、策略逻辑、可视化和回测。
- `requirements.txt`：运行依赖。
- `README.md`：快速运行说明。
- `MULTI_STOCK_FEATURE.md`：**[新增]** 多股票对比功能使用指南
- `data/`：数据缓存目录，保存多个股票的日线数据。
- `.venv/`：虚拟环境（本机已创建）。

## 3. 依赖环境
- Python venv：`.venv`
- 主要依赖：`akshare`、`pandas`、`numpy`、`plotly`、`streamlit`
- 运行命令：
  - `source .venv/bin/activate`
  - `streamlit run app.py --server.port 8502`

## 4. 数据来源与输入
1) AkShare 下载：
   - 调用：`ak.stock_us_daily(symbol="AAPL", adjust="qfq")`
   - 保存：`data/{symbol}_daily.csv`
   - 侧边栏可选：标的 `symbol`、复权方式 `adjust`、刷新按钮
   - **[新增]** 多股票搜索与自动下载
2) CSV 上传：
   - 允许列名：`open`, `close`, `high`, `low`，以及 `volumn/volume`
   - 如果没有 `date` 列：自动生成行索引作为日期
3) 日期区间：
   - 如果数据含日期列：侧边栏可调时间区间（默认最近 30 天）
   - 如果不含日期列：提示无法筛选时间区间

## 5. 特征与指标计算
在 `add_indicators()` 中计算：
- RSI：`compute_rsi(close, period)`
- MACD：`compute_macd(close, fast, slow, signal)`，输出 `macd`, `signal`, `histogram`
- EMA：`ema_fast`, `ema_slow`（趋势过滤）
- ATR：`compute_atr()`（波动率）
- ADX：`compute_adx()`（趋势强度）

## 6. 因子评分体系
在 `compute_signals()` 中构建因子评分：
- 短期动量：`ret_short = close.pct_change(momentum_short)`
- 中期动量：`ret_long = close.pct_change(momentum_long)`
- 波动率：`volatility = atr / close`
- 以上因子与 MACD/RSI 均做滚动 Z 分数：`rolling_zscore`
- 因子评分：  
  `factor_score = w1*mom_short_z + w2*mom_long_z + w3*macd_z + w4*rsi_z - w5*vol_z`
- 评分分位数：`factor_percentile`（滚动分位）

## 7. 策略逻辑（更灵敏版）
核心思想：评分 + 过滤条件 + 分档仓位。

1) 过滤条件：
- 趋势过滤：`ema_fast > ema_slow`
- 强度过滤：`adx >= adx_threshold`
- RSI 区间：`rsi_lower < rsi < rsi_upper`
- MACD 条件：`macd > signal`（不再要求“金叉”）
- 入场评分阈值：`factor_score >= entry_threshold`

2) 分档仓位：
- 评分分位数 >= 高档阈值：仓位 1.0
- 评分分位数 >= 中档阈值：仓位 0.5
- 否则：仓位 0

3) 退出条件（任意触发）：
- `factor_score <= exit_threshold`
- `ema_fast < ema_slow`
- RSI 超上/下限
- `macd < signal`

4) 止损/止盈（ATR）：
- 止损：`entry_price - stop_loss_mult * entry_atr`
- 止盈：`entry_price + take_profit_mult * entry_atr`

5) 仓位执行：
`simulate_strategy()` 支持 `target_position`（0/0.5/1），按目标仓位计算收益。

## 8. 回测与指标
1) Train/Test 切分：
- 按时间顺序切分，比例由 `train_ratio` 控制
2) 输出指标：
- 策略累计收益
- Buy & Hold 收益
- 最大回撤
- 夏普比率（年化）

## 9. Walk-Forward 回测
在 `walk_forward_backtest()` 中实现：
- 训练窗口与测试窗口可调（交易日）
- 滚动测试段逐段串联权益曲线
- 输出每段收益、夏普、最大回撤，并显示合并后的 WF 权益曲线
注意：当前版本对每段测试使用相同的策略参数（未做每段再优化）。

## 10. 自动参数搜索与推荐
在 `random_search_params()` 中实现随机搜索：
- 搜索范围：
  - `entry_threshold`
  - `exit_threshold`
  - `adx_threshold`
  - `stop_loss_mult`
  - `take_profit_mult`
- 评分函数：`score = sharpe + total_return`（基于训练集）
- 结果会显示评分、收益、夏普，并可一键应用推荐参数
- 应用按钮只会更新：`adx_threshold`、`entry_threshold`、`exit_threshold`、`stop_loss_mult`、`take_profit_mult`

## 11. 可视化组件
1) 训练集 K 线：
   - 红涨绿跌，K 线悬浮显示 OHLC
   - 可横向缩放/拖动，带范围选择器
   - 如有成交量，显示子图
2) RSI + MACD：
   - RSI 上下阈值线
   - MACD/Signal/Histogram
3) 因子评分：
   - 评分曲线 + 分位数曲线
   - 评分分位的参考线（20/50/80 分位）
4) 测试集表现：
   - 策略 vs Buy&Hold 权益曲线
5) Walk-Forward：
   - WF 权益曲线 + 分段结果表
6) 测试集交易信号：
   - 买卖点散点标注

## 12. 已知限制与注意事项
- 未计入交易成本与滑点。
- 目标仓位分档仅支持 0/0.5/1（可扩展）。
- 分档仓位在改变时使用同一笔入场价格与 ATR（不做加仓重新计入场价）。
- 参数搜索只优化部分参数，并基于训练集，有过拟合风险。
- Walk-Forward 目前不做滚动再训练，仅滚动测试。
- 当数据较少时，WF 窗口会固定并提示。

## 13. 后续可扩展方向
- 引入交易成本/滑点模型
- 分档仓位改为连续仓位
- Walk-Forward 内部自动再优化（每段训练后更新参数）
- 添加更多因子（波段、均值回归、成交量因子等）
