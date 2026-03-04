# AI 快速上下文（约2k tokens，替代读源码的43k）

## 项目一句话
Streamlit 模块化量化交易策略分析应用，10因子评分+回测+贝叶斯优化+投资组合模拟，已部署到云服务器。

## 技术栈
Python + Streamlit + AkShare + Plotly + Optuna + NumPy + Pandas

## 文件结构
```
app.py              # 入口文件（~120行，路由+参数校验）
app_original.py     # 重构前的单文件备份（5875行，仅供参考）
core/               # 核心逻辑模块（9个.py + __init__.py）
├── config.py       #   常量、预设参数（~115行）
├── data.py         #   数据加载/标准化（~100行，5个函数）
├── indicators.py   #   技术指标计算（~226行，10个函数）
├── signals.py      #   策略信号生成（~182行，1个核心函数）
├── backtest.py     #   回测引擎（~180行，4个函数）
├── utils.py        #   工具函数（~85行，4个函数）
├── optimizer.py    #   参数优化（~857行，4个函数）
├── visualization.py#   图表生成（~884行，6个函数）
├── portfolio.py    #   投资组合（~325行，2个函数）
└── __init__.py     #   统一导出
ui/                 # UI 界面模块（3个.py + __init__.py）
├── sidebar.py      #   侧边栏控件（~481行）
├── multi_stock.py  #   多股票对比页（~596行）
├── single_stock.py #   单股票分析页（~1030行）
└── __init__.py     #   统一导出
requirements.txt
AI_CONTEXT.md       # 本文件
data/               # 股票CSV数据缓存
deploy/             # 部署脚本（deploy.sh, sync.bat等）
scripts/            # 本地工具脚本（setup.bat, start.bat, check_environment.py等）
document/           # 技术文档 + 更新日志 + 部署指南
```

## 代码地图

### app.py — 入口文件（~120行）
- 页面配置 + `apply_best_params` session_state 同步
- 调用 `render_sidebar()` 获取参数 dict
- 数据加载（上传 or `load_or_fetch_stock`）
- 参数校验（EMA/MACD/RSI/动量/分位数冲突检查）
- 日期筛选
- 路由：多股 → `render_multi_stock_page()` / 单股 → `render_single_stock_page()`

### core/config.py — 常量配置
- `DATA_DIR`: 临时缓存目录（`tempfile.gettempdir()/stratagy_cache`）
- `DEFAULT_SYMBOL`: "AAPL"
- `DEFAULT_STOCKS`: 9只默认美股
- `STRATEGY_PRESETS`: 4种预设策略模板（保守/均衡/激进/自定义）
- `_PRESET_PARAMS_FOR_OPTIMIZATION`: 3组预设参数字典（供优化器热启动）

### core/data.py — 数据处理
| 函数 | 功能 |
|------|------|
| `standardize_columns(df)` | 列名标准化(小写, trade_date→date) |
| `ensure_date_column(df)` | 确保date列为datetime |
| `fetch_data(symbol, adjust)` | AkShare下载美股日线 |
| `load_csv(path)` | 读CSV+标准化（@st.cache_data） |
| `load_uploaded_bytes(data)` | 处理上传的CSV（@st.cache_data） |

### core/indicators.py — 技术指标
| 函数 | 功能 |
|------|------|
| `compute_rsi` | RSI(相对强弱) |
| `rolling_zscore` | 滚动Z-score标准化 |
| `rolling_percentile` | 滚动分位数 |
| `compute_macd` | MACD+信号线+柱状图 |
| `compute_atr` | ATR(真实波幅) |
| `compute_adx` | ADX(趋势强度) |
| `compute_bollinger_bands` | 布林带 |
| `compute_obv` | OBV(能量潮) |
| `rolling_rank` | 滚动排名(0-1) |
| `add_indicators` | **汇总函数**：调用以上所有+EMA |

### core/signals.py — 策略信号
| 函数 | 功能 |
|------|------|
| `compute_signals(df, ...)` | **核心策略**：10因子加权评分→7档仓位→买卖信号 |

**10因子**：短期动量, 长期动量, MACD, RSI, 波动率(负), 布林带位置, OBV趋势, 成交量比率, 价格位置, 回撤(负)
**标准化**：前5个Z-score, 后5个rolling_rank
**仓位档**：≥80%→1.0, ≥65%→0.8, ≥55%→0.6, ≥45%→0.4, ≥35%→0.2, 其他→0
**5个入场信号**：因子评分达标, 趋势(EMA快>慢), 强度(ADX≥阈值), RSI(区间内), MACD(>信号线)
**入场逻辑**：计数制（entry_min_signals，默认3，至少3个信号满足才入场）
**4个出场信号**：评分低, 趋势反转, RSI越界, MACD转弱
**出场逻辑**：计数制（exit_min_signals，默认2，至少2个信号满足才出场）

### core/backtest.py — 回测引擎
| 函数 | 功能 |
|------|------|
| `simulate_strategy(df, ...)` | 逐日模拟交易，ATR止损止盈，输出权益曲线 |
| `max_drawdown(equity)` | 最大回撤 |
| `sharpe_ratio(returns)` | 年化夏普比率(×√252) |
| `walk_forward_backtest(df, ...)` | 滚动窗口回测，训练/测试分离 |

### core/optimizer.py — 参数优化（4个函数）
| 函数 | 功能 |
|------|------|
| `evaluate_presets_for_optimization(...)` | 预评估3个预设策略，选最佳起点 |
| `random_search_params(...)` | 随机搜索(含防过拟合：子验证集+正则化+gap惩罚) |
| `bayesian_optimize_params(...)` | Optuna贝叶斯优化(含热启动+防过拟合) |
| `genetic_algorithm_optimize_params(...)` | 遗传算法(热启动+多核并行+精英保留) |

三种方法均内置：训练集内部70/30拆分、目标函数=0.4×训练分+0.6×验证分-0.3×|gap|-L2正则化、progress_callback进度回调

### core/utils.py — 工具函数
| 函数 | 功能 |
|------|------|
| `format_pct(value)` | 格式化百分比 |
| `load_or_fetch_stock(symbol, adjust)` | 缓存优先加载股票 |
| `get_available_stocks()` | 默认列表+缓存扫描 |
| `normalize_prices(df_dict)` | 归一化到起点=100 |

### core/visualization.py — 可视化图表
| 函数 | 功能 |
|------|------|
| `create_multi_stock_comparison_chart` | 多股归一化价格对比 |
| `create_correlation_heatmap` | 收益率相关性热图 |
| `create_relative_strength_chart` | 相对强弱对比图 |
| `create_risk_return_scatter` | 风险收益散点图 |
| `create_periodic_returns_heatmap` | 周期收益率热图 |
| `create_factor_score_comparison` | 因子评分柱状对比 |

### core/portfolio.py — 投资组合
| 函数 | 功能 |
|------|------|
| `run_portfolio_simulation(...)` | 投资组合回测模拟 |
| `bayesian_optimize_portfolio(...)` | 组合参数贝叶斯优化 |

### ui/sidebar.py — 侧边栏
| 函数 | 功能 |
|------|------|
| `render_sidebar()` → dict | 渲染全部侧边栏控件，返回~40个参数的字典 |

包含：日期选择、股票选择/添加/上传、策略预设切换、入/出场规则、高级设置折叠区（EMA/MACD/RSI/ADX/ATR/BB参数、因子权重、评分阈值）

### ui/multi_stock.py — 多股票对比页
| 函数 | 功能 |
|------|------|
| `render_multi_stock_page(params, ...)` | 归一化图、统计表、相对强弱、风险收益散点、因子对比、相关性热图、周期热图、组合模拟+贝叶斯优化、HTML导出 |

### ui/single_stock.py — 单股票分析页
| 函数 | 功能 |
|------|------|
| `render_single_stock_page(params, df_raw, symbol)` | 指标计算、训练/测试切分、K线图、RSI/MACD图、因子评分图、策略建议、高级策略搜索（贝叶斯/GA/随机）、测试集表现、Walk-Forward、交易信号、HTML导出 |

内部辅助函数：`_build_candlestick_chart`, `_build_rsi_macd_chart`, `_build_factor_score_chart`, `_render_strategy_suggestion`, `_render_advanced_search`, `_execute_search`, `_render_search_results`, `_render_test_performance`, `_render_walk_forward`, `_render_trade_signals`, `_render_single_stock_export`

## 部署信息
- 服务器：`115.191.68.122:8501`，Ubuntu 24.04，systemd服务
- SSH别名：`stratagy`（已配免密登录）
- 部署：需上传 app.py + core/ + ui/ 三部分
  ```bash
  scp -r app.py core/ ui/ stratagy:/opt/stratagy/
  ssh stratagy "systemctl restart stratagy"
  ```
- 日志：`ssh stratagy "journalctl -u stratagy -n 50 --no-pager"`

## 跨平台开发环境

本项目支持在 **Windows** 和 **macOS** 两台机器上开发，通过 Git 同步代码。

### 已验证的能力

| 能力 | Windows | macOS |
|------|---------|-------|
| SSH 免密连接服务器 (`stratagy`) | ✅ | ✅ |
| Git 推送 GitHub (HTTPS) | ✅ | ✅ |
| 本地 Streamlit 运行 | ✅ | ✅ (`.venv/bin/streamlit run app.py`) |
| scp 部署到服务器 | ✅ (`sync.bat`) | ✅ (手动 scp 或 `deploy/deploy.sh`) |

### SSH 配置

两台机器均已配置 `~/.ssh/config`，别名 `stratagy` 指向 `root@115.191.68.122:22`。

- **Windows**: 密钥位于 `C:\Users\<用户>\.ssh\`
- **macOS**: 密钥位于 `/Users/rikka/.ssh/id_ed25519`（ed25519）

### 注意事项
- Windows 部署脚本为 `.bat`（`deploy/sync.bat`），macOS 下请用 `scp`/`ssh` 命令或 shell 脚本
- 两台机器代码通过 **Git (GitHub)** 保持同步，切换机器前先 `git pull`
- Python 虚拟环境 `.venv/` 不跨平台，每台机器需各自创建

## 修改须知
1. **模块化架构**：代码分布在 app.py + core/ + ui/ 中，修改前先定位目标模块
2. 核心逻辑改 core/ 下对应文件，UI改 ui/ 下对应文件，入口/路由改 app.py
3. 模块间依赖方向：config ← data ← indicators ← signals ← backtest ← optimizer
4. `render_sidebar()` 返回 dict，所有参数通过 dict 传递给页面函数
5. 服务器内存4GiB，注意优化时资源
6. 侧边栏只放通用控件，模式专属功能放右侧主区域
7. `app_original.py` 是重构前的完整单文件备份，勿删除
