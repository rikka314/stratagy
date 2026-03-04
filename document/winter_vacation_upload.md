# 寒假工作记录 - 2026-02-24

## 📋 工作概述

将量化交易策略分析应用从本地部署到火山引擎 ECS 云服务器，并配置 SSH 免密登录和 AI 协作环境。

---

## 🖥️ 服务器部署

### 服务器信息
- **云服务商**：火山引擎 ECS
- **地域**：华北2（北京）
- **实例规格**：c1m1（4GiB RAM），40GiB 极速型 SSD
- **操作系统**：Ubuntu 24.04 LTS
- **公网 IP**：115.191.68.122
- **到期时间**：2027-02-10

### 部署步骤

1. **上传项目文件**  
   通过 SCP 将 `app.py`、`requirements.txt`、`data/*.csv` 上传到服务器 `/opt/stratagy/`

2. **创建 Python 虚拟环境并安装依赖**  
   ```bash
   cd /opt/stratagy
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   安装了 streamlit 1.54.0、akshare、numpy、pandas、plotly、optuna 等依赖

3. **配置 Streamlit**  
   创建 `/opt/stratagy/.streamlit/config.toml`：
   - `address = "0.0.0.0"`（监听所有网络接口）
   - `port = 8501`
   - `headless = true`（无浏览器模式）

4. **配置 systemd 服务**  
   创建 `/etc/systemd/system/stratagy.service`，实现：
   - 开机自动启动
   - 崩溃后自动重启（5秒延迟）
   - 后台持续运行

5. **防火墙配置**  
   UFW 已放通 8501 端口

6. **验证部署**  
   - 服务状态：`active (running)`
   - 端口监听：`0.0.0.0:8501`
   - HTTP 访问：返回 200 OK
   - 访问地址：http://115.191.68.122:8501

---

## 🔑 SSH 免密登录配置

解决每次操作都需要输入服务器密码的问题。

### 配置内容

1. **生成 SSH 密钥对**  
   - 算法：Ed25519
   - 密钥文件：`C:\Users\Steve Huang\.ssh\id_ed25519`
   - 无密码短语（方便脚本和 AI 使用）

2. **上传公钥到服务器**  
   公钥追加到 `/root/.ssh/authorized_keys`

3. **创建 SSH Config 别名**  
   在 `~/.ssh/config` 中添加 `Host stratagy`，以后 `ssh stratagy` 直接免密连接

4. **验证**  
   `ssh stratagy "echo OK"` → 输出 `FREE_LOGIN_OK`，无需密码

---

## 📁 创建的部署文件

| 文件 | 用途 |
|------|------|
| `deploy/deploy.sh` | 服务器一键部署脚本（系统依赖、虚拟环境、systemd、防火墙） |
| `deploy/upload_and_deploy.bat` | Windows 一键上传+部署 |
| `deploy/sync.bat` | 日常同步：上传代码→重启服务（一键） |
| `deploy/fix_config.sh` | 修复 Streamlit 配置文件 |
| `AI_GUIDE.md` | AI 协作工作指南（项目介绍、SSH使用、工作流程） |

---

## 🔄 后续开发工作流

代码修改后的部署流程：

```
本地修改 app.py → 双击 deploy/sync.bat → 自动上传+重启 → 刷新浏览器
```

或 AI 直接执行：
```bash
scp app.py stratagy:/opt/stratagy/
ssh stratagy "systemctl restart stratagy"
```

---

## 📝 备注

- 服务器已安装宝塔面板（端口 8888），是之前的环境，未影响本项目
- `Amphion_repo/` 是工作区中的另一个项目（语音合成），与本项目无关
- SSH 密钥已配置完成，后续 AI 助手可直接通过 `ssh stratagy` 操作服务器

---
---

# 服务器存储优化 - 2026-02-25

## 📋 工作概述

优化云服务器存储空间占用，包括精简 Python 依赖和改造数据存储方式为临时缓存。

---

## ~~🗑️ 精简 venv 依赖（方案三）~~ — 已回滚

### ~~删除 pyarrow~~ ❌ 不可行

- **包名**：pyarrow 23.0.1
- **占用空间**：149 MB
- **用途**：Apache Arrow 列式数据格式，pandas 的可选后端引擎
- **原删除原因**：认为项目仅使用 `pd.read_csv`，不需要 Arrow 格式支持
- **失败原因**：`st.dataframe()` 内部硬依赖 pyarrow（通过 `streamlit/elements/arrow.py` 中的 `import pyarrow as pa`），删除后多股对比页面报 `ModuleNotFoundError: No module named 'pyarrow'`
- **处理**：已重新安装 `pip install pyarrow`，恢复至 pyarrow 23.0.1

> **教训**：pyarrow 虽在 streamlit 的 `requirements.txt` 中标为可选，但 `st.dataframe` 等核心组件实际强依赖它，不可删除。

---

## 📂 数据存储改造为临时缓存（方案五）

### 问题

原方案将股票 CSV 数据持久保存在服务器 `/opt/stratagy/data/` 目录（2.5 MB，10 只股票），占用持久磁盘空间且随用户添加股票不断增长。

### 解决方案

将数据存储从持久目录改为系统临时目录，数据按需从 AkShare 下载。

### 代码修改（app.py）

1. **DATA_DIR 改为临时目录**
   - 新增 `import tempfile`
   - `DATA_DIR = "data"` → `DATA_DIR = os.path.join(tempfile.gettempdir(), "stratagy_cache")`
   - 服务器上实际路径为 `/tmp/stratagy_cache/`

2. **添加默认股票列表**
   - 新增常量 `DEFAULT_STOCKS = ["AAPL", "TSLA", "NVDA", "GOOGL", "META", "ORCL", "ADM", "NTR", "CTVA"]`
   - 无需预下载 CSV 文件，用户打开页面即可选择这些股票

3. **改造 `get_available_stocks()`**
   - 原逻辑：仅扫描 `data/` 目录中的 CSV 文件
   - 新逻辑：返回 `DEFAULT_STOCKS` + 扫描临时缓存中用户额外添加的股票

4. **改造 `load_or_fetch_stock()`**
   - 缓存写入临时目录而非持久目录
   - 首次加载自动创建临时缓存目录

5. **简化主数据加载逻辑**
   - 移除手动构造 `data_path` 和重复的下载/保存逻辑
   - 统一使用 `load_or_fetch_stock()` 函数

### 服务器清理

- 删除旧的 `/opt/stratagy/data/` 目录（10 个 CSV 文件，共 2.5 MB）
- 服务重启后验证正常运行

### 行为变化

| 对比项 | 优化前 | 优化后 |
|--------|--------|--------|
| 数据存储位置 | `/opt/stratagy/data/`（持久） | `/tmp/stratagy_cache/`（临时） |
| 预置数据文件 | 10 个 CSV（随项目部署） | 无（按需下载） |
| 股票列表来源 | 扫描 data/ 目录 | 硬编码默认列表 + 缓存 |
| 服务重启后 | 数据保留 | 缓存可能清空，首次访问重新下载 |
| 磁盘占用增长 | 随添加股票增长 | 不占用持久空间 |

---

## � 修复 Streamlit 弃用警告

将 app.py 中全部 14 处 `use_container_width=True` 替换为 `width="stretch"`，消除 Streamlit 1.54.0 的弃用警告：

```
Please replace `use_container_width` with `width`.
`use_container_width` will be removed after 2025-12-31.
```

涉及组件：`st.plotly_chart`、`st.dataframe`、`st.button`、`st.download_button`

---

## 📊 总体优化效果

| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 项目总大小 | 637 MB | 637 MB（venv 未变） |
| venv | 634 MB | 634 MB（pyarrow 已装回） |
| data/ | 2.5 MB | 0（改为临时缓存） |
| 持久磁盘节省 | — | **2.5 MB + 不再增长** |
| 弃用警告 | 14 处 | 0 |

---
---

# 多股票分析功能增强 - 2026-02-25

## 📋 工作概述

为多股票对比分析页面新增三个分析维度：相对强弱对比、投资组合模拟（含贝叶斯优化）、周期收益率热图。

---

## 💪 功能1：相对强弱对比（Relative Strength Comparison）

### 功能说明

计算每只股票相对于基准的相对强弱指标（RS = 个股归一化价格 ÷ 基准归一化价格），以折线图展示。

- RS 曲线上升 → 跑赢基准（即使股价本身在跌，只要跌得比基准少也算跑赢）
- RS 曲线下降 → 跑输基准
- RS = 1.0 水平线表示与基准持平

### 代码修改

| 修改 | 说明 |
|------|------|
| 新增 `create_relative_strength_chart()` 函数 | 支持两种基准：等权平均 / 指定某只股票 |
| 多股对比 UI 区块 | 在风险-收益分析之前，带基准选择下拉框 |
| HTML 导出 | 在风险收益散点图之前插入 RS 图表 |

### 对决策的影响

动量交易者通过 RS 曲线判断资金分配方向：买入相对强势股票，回避相对弱势股票。

---

## 💼 功能2：投资组合模拟（Portfolio Simulation）

### 功能说明

对每只股票独立运行完整策略流程（`add_indicators` → `compute_signals` → `simulate_strategy`），按自定义权重合成组合净值曲线，并与等权买入持有基准对比。

### 代码修改

| 修改 | 说明 |
|------|------|
| 新增 `run_portfolio_simulation()` 函数 | 逐股跑策略→加权合成组合日收益→累积净值 |
| 新增 `bayesian_optimize_portfolio()` 函数 | 思路C：统一参数优化组合整体的夏普+收益-回撤 |
| 多股对比 UI 区块 | 权重设置（折叠面板）、组合净值图、6列指标卡、各股票独立表现表格、贝叶斯优化按钮+结果展示+优化后重新模拟 |
| HTML 导出 | 组合净值图 + 组合指标摘要卡片 |

### 组合净值图说明

- 绿色实线：组合策略净值
- 红色虚线：等权买入持有基准
- 彩色点线：各股票独立策略净值（半透明）

### 优化方案（思路C）

- 默认用侧边栏统一参数展示组合模拟结果
- 提供"优化组合参数"按钮，采用贝叶斯优化（Optuna），统一一套参数优化组合整体指标
- 优化后展示对比（优化前 vs 优化后的夏普/收益/回撤）+ 最优参数详情 + 重新模拟图表

### 对决策的影响

展示分散投资的效果：组合通常能降低波动和回撤，提升夏普比率。帮助理解资产配置的价值。

---

## 📅 功能3：周期收益率热图（Periodic Returns Heatmap）

### 功能说明

按月/季度/年展示每只股票的收益率热图（行=股票，列=时间周期，颜色=涨跌幅）。

### 代码修改

| 修改 | 说明 |
|------|------|
| 新增 `create_periodic_returns_heatmap()` 函数 | 支持月度(M)/季度(Q)/年度(YE)，红绿色阶，每格标注收益率数值，最多显示24个周期 |
| 多股对比 UI 区块 | 在相关性热图之后，带周期选择下拉框 |
| HTML 导出 | 在组合模拟之前插入热图 |

### 颜色含义

- 深绿：大涨
- 浅绿：小涨
- 白色：零收益
- 浅红：小跌
- 深红：大跌

### 对决策的影响

帮助发现股票的季节性规律或在特定市场环境下的表现差异。例如某些股票可能在特定月份表现特别好，或在市场整体下跌的月份具有抗跌性。

---

## 📊 代码量变化

| 项目 | 变化 |
|------|------|
| app.py 行数 | ~3750 → ~4630（+880 行） |
| 新增函数 | 4 个（`create_relative_strength_chart`、`create_periodic_returns_heatmap`、`run_portfolio_simulation`、`bayesian_optimize_portfolio`） |
| UI 新增区块 | 3 个（相对强弱、周期热图、组合模拟+优化） |
| HTML 导出新增 | 3 个图表 + 1 个指标卡片 |

---
---

# 前端逻辑重构 - 2026-02-25

## 📋 工作概述

重构 Streamlit UI 布局，将模式专属功能从侧边栏移到右侧主区域，统一UI设计原则。

---

## 设计原则

**侧边栏**只放两种模式（单股/多股）通用的控件，**模式专属功能**放在右侧主区域各自的分支中。

---

## 🔧 具体修改

### 1. 侧边栏精简

| 移出的控件 | 原位置 | 新位置 | 原因 |
|-----------|--------|--------|------|
| 训练集比例滑块 | 侧边栏 | 单股右侧主区域 | 仅单股分析使用 |
| Walk-Forward 设置（启用开关、训练/测试窗口） | 侧边栏 | 单股右侧主区域 | 仅单股分析使用 |
| 参数自动推荐（优化方法、次数、搜索按钮、应用按钮） | 侧边栏 | 单股右侧主区域 | 仅单股分析使用 |

### 2. 指标计算延迟到单股分支

`add_indicators()` + `compute_signals()` 原来在公共区域对第一只股票总是执行，但多股模式下完全未使用。现已移入单股分支内部，多股模式省去不必要的计算。

### 3. `simulate_strategy` 仅单股执行

`simulate_strategy()` 的训练集/测试集回测原来不分模式总是运行，现仅在单股分支中执行。

### 4. 单股分析新增 HTML 导出

单股分析末尾新增完整 HTML 报告导出功能，包含蜡烛图、RSI/MACD、因子评分、权益曲线、交易信号共 5 个图表。

---

## 📊 代码量变化

| 项目 | 变化 |
|------|------|
| app.py 行数 | ~4630 → ~4810（+180 行） |
| 侧边栏代码 | 减少 ~60 行 |
| 单股分支代码 | 增加 ~240 行（WF控件、优化控件、HTML导出） |
| 多股分支代码 | 不变 |

---
---

# 策略逻辑优化 + UI 重构 - 2026-02-25

## 📋 工作概述

针对策略表现极差（组合收益 13.41% vs 买入持有 178.27%）的问题，从核心策略逻辑和 UI 交互两方面进行系统性优化。

---

## 🔍 问题诊断

### 根本原因：大部分时间空仓

| 环节 | 原逻辑 | 问题 |
|------|--------|------|
| 入场 | 5个条件全部 AND 或加权投票 | 极难同时满足，错过大量行情 |
| 出场 | 4个条件任一 OR | 稍有波动就被踢出去 |
| 仓位 | ≥95分位才满仓 | 门槛过高，大部分时间空仓或极低仓位 |
| 结果 | 回撤低(-3.98%)但完全踏空 | 组合收益仅 13.41% |

---

## 🔧 策略逻辑改进（4项）

### 1. 入场逻辑改为计数制

| 对比项 | 优化前 | 优化后 |
|--------|--------|--------|
| 入场模式 | AND（全满足）/ 加权投票 | 计数制：5个信号中至少满足 N 个 |
| 默认阈值 | — | 3（5个信号满足3个即可入场） |
| 参数 | `use_voting_entry` / AND 模式 | `entry_min_signals`（1-5可调） |

**5个入场信号**：因子评分达标、趋势向上(EMA)、强度足够(ADX)、RSI正常、MACD向上

### 2. 出场逻辑从 OR 改为计数制

| 对比项 | 优化前 | 优化后 |
|--------|--------|--------|
| 出场模式 | OR（任一触发就平仓） | 计数制：4个信号中至少满足 N 个 |
| 默认阈值 | — | 2（4个信号满足2个才出场） |
| 参数 | — | `exit_min_signals`（1-4可调） |

**4个出场信号**：因子评分过低、趋势反转、RSI越界、MACD跌破信号线

### 3. 降低仓位门槛

| 仓位档 | 优化前分位数 | 优化后分位数 |
|--------|------------|------------|
| 满仓 1.0 | ≥95% | ≥80% |
| 80% 仓位 | ≥85% | ≥65% |
| 60% 仓位 | ≥75% | ≥55% |
| 40% 仓位 | ≥60% | ≥45% |
| 20% 仓位 | ≥50% | ≥35% |

### 4. 新增 `entry_min_signals` 和 `exit_min_signals` 参数

在 `compute_signals()` 函数签名中新增两个参数，所有 10 个调用点（UI主流程、参数优化、组合模拟等）均已更新。

---

## 🖥️ UI 重构（侧边栏）

### 新布局（从上到下）

| 区块 | 内容 | 说明 |
|------|------|------|
| 📅 时间范围 | 日期选择器（默认最近3年） | 从数据加载区移到侧边栏最顶端 |
| 🔍 股票选择 | 多选框、添加/上传 | 保持不变 |
| 📈 入场规则 | 滑块：入场最少信号数（1-5） | **新增**，替代原来的过滤器复选框+AND/投票模式 |
| 📉 出场规则 | 滑块：出场最少信号数（1-4） | **新增**，替代原来的 OR 逻辑 |
| ⚙️ 高级设置 | 折叠区（默认收起） | EMA/MACD/RSI/ADX/ATR参数、因子权重、评分阈值 |

### 移除的控件

| 控件 | 原因 |
|------|------|
| 4个过滤器复选框（趋势/强度/RSI/MACD） | 改为始终启用，通过信号计数控制松紧 |
| 入场逻辑 radio（AND/评分模式） | 统一为计数制 |
| 入场投票阈值滑块 | 不再需要 |
| 各指标参数滑块（直接展示） | 移入高级设置折叠区 |

---

## 📊 代码量变化

| 项目 | 变化 |
|------|------|
| app.py 行数 | ~4810 → ~4700（-110 行） |
| compute_signals 函数 | +25 行（新增计数制入场/出场逻辑） |
| 侧边栏 UI | -230 行（精简参数展示） |
| 新增参数 | `entry_min_signals`(默认3)、`exit_min_signals`(默认2) |

---
---

# 防过拟合 + 预设策略 + 高级策略重构 - 2026-02-27

## 📋 工作概述

解决参数优化过拟合问题，新增预设策略模板系统，将"参数自动优化"重构为"高级策略"模块。

---

## 🛡️ 防过拟合机制（贝叶斯优化 + 随机搜索）

### 问题

优化器仅在训练集上评估，参数极度拟合训练集噪声。训练集表现虚高，测试集表现远差于训练集。25个参数的高维搜索空间加剧了过拟合。

### 解决方案（三管齐下）

#### 1. 子验证集拆分

将训练集内部拆分为子训练集（70%）和子验证集（30%）：

```
原始训练集：[=============================]
拆分后：     [=====子训练集(70%)=====][==子验证集(30%)==]
```

- 在子训练集上生成信号/回测，在子验证集上验证泛化能力
- 数据不足（<50条）时自动跳过拆分，退化为原始行为

#### 2. 改进目标函数

| 对比项 | 优化前 | 优化后 |
|--------|--------|--------|
| 评估数据 | 仅训练集 | 子训练集 + 子验证集 |
| 目标函数 | `sharpe + return - 0.5×|dd|` | `0.4×训练分 + 0.6×验证分 - 0.3×|gap|` |
| 差距惩罚 | 无 | 训练-验证差距越大扣分越多 |
| 正则化 | 无 | L2 惩罚偏离默认值的极端参数 |

#### 3. L2 正则化

对每个参数计算其偏离默认值的程度，施加惩罚：

$$\text{penalty} = \lambda \sum_{i} \left(\frac{p_i - p_i^{\text{default}}}{\Delta p_i}\right)^2$$

- λ = 0.02（轻度正则化，不过分约束搜索空间）
- 覆盖全部 25 个优化参数的默认值和范围

### 代码修改

| 文件 | 函数 | 修改 |
|------|------|------|
| app.py | `bayesian_optimize_params()` | +40行：子验证集拆分、正则化函数、改进目标函数、结果含 val_* 字段 |
| app.py | `random_search_params()` | +30行：同样的子验证集 + 正则化 + gap 惩罚 |

### 结果字段变化

优化结果 dict 新增字段：`val_sharpe`、`val_return`、`val_max_drawdown`

---

## 📋 预设策略模板系统

### 功能说明

在侧边栏新增「策略选择」区块，提供 4 种预设策略模板，选择后自动填充所有参数。

### 预设策略

| 策略 | 入场信号数 | 出场信号数 | 止损 | 止盈 | ADX阈值 | 特点 |
|------|:---------:|:---------:|:----:|:----:|:------:|------|
| 趋势跟随（保守） | 2 | 1 | 1.5× | 3.0× | 15 | 宽松入场、快速止损 |
| 均衡策略（默认） | 3 | 2 | 2.0× | 4.0× | 20 | 攻守兼备 |
| 动量突破（激进） | 4 | 3 | 3.0× | 6.0× | 25 | 严格筛选、放大利润 |
| 自定义参数 | 手动 | 手动 | 手动 | 手动 | 手动 | 在高级设置中调节 |

每个预设策略包含完整的参数集（EMA/MACD/RSI/ADX/ATR/布林带/因子权重/阈值等），选择后通过 `session_state` 同步到所有滑块。

### 代码修改

| 位置 | 修改 |
|------|------|
| 侧边栏（股票选择后、入场规则前） | 新增 `st.selectbox` 策略选择器 + `STRATEGY_PRESETS` 字典 |
| 入场/出场规则 | 滑块默认值根据预设策略动态变化 |
| 高级设置标题 | 根据当前策略显示不同提示 |
| 策略建议标题 | 显示当前预设策略名称 |

### UI 布局变化

```
侧边栏（从上到下）
├── 📅 时间范围
├── 🔍 股票选择
├── 📋 策略选择（新增）← selectbox + 策略说明
├── 📈 入场规则（默认值随策略变化）
├── 📉 出场规则（默认值随策略变化）
└── ⚙️ 高级设置（标题根据策略动态提示）
```

---

## 🔬 「参数自动优化」→「高级策略」重命名

### 变更内容

| 对比项 | 优化前 | 优化后 |
|--------|--------|--------|
| 区块标题 | 🔬 参数自动优化 | 🔬 高级策略 |
| 区块描述 | 无 | 使用智能搜索算法...内置防过拟合机制 |
| radio 标签 | 优化方法 | 搜索方法 |
| 按钮文字 | 🚀 自动搜索参数 | 🚀 运行高级策略搜索 |
| 结果标题 | 参数推荐 | 搜索结果 |
| 结果描述 | 基于训练集的...结果（供参考） | 基于...的结果（含防过拟合验证） |
| 指标展示 | 3列（综合/训练收益/夏普） | 4列（综合/训练收益/训练夏普/验证夏普）+ 验证集收益/回撤/过拟合风险标记 |
| 应用按钮 | 应用推荐参数 | 📥 应用搜索结果到当前策略（primary样式） |
| 空状态提示 | 请先点击"自动搜索参数"按钮 | 点击上方「🚀 运行高级策略搜索」按钮... |

### 过拟合风险标记

搜索结果中新增过拟合风险指示：

| 训练-验证夏普差距 | 标记 |
|:-:|:-:|
| < 0.5 | ✅ 低 |
| 0.5 - 1.0 | ⚠️ 中 |
| > 1.0 | 🔴 高 |

### 应用按钮行为修复

- 点击后自动将策略切换为「自定义参数」
- 通过 `apply_best_params` flag 在页面顶部（widget 渲染前）修改 `session_state`，避免 Streamlit 报错

---

## 🐛 Bug 修复

### 1. 应用参数后 StreamlitAPIException

- **现象**：点击「应用搜索结果」后报错 `st.session_state.strategy_preset_selector cannot be modified after the widget is instantiated`
- **原因**：在按钮点击回调中直接修改 selectbox 的 session_state key，但此时 widget 已渲染
- **修复**：将 `strategy_preset_selector` 的修改移到页面顶部 `apply_best_params` 处理块中（widget 渲染之前）

### 2. 切换股票后旧搜索结果残留

- **现象**：切换股票后「搜索结果」仍显示上一只股票的优化结果
- **修复**：在股票切换检测逻辑中清除 `best_params`（通过 `_last_symbol` 跟踪）

---

## 📊 代码量变化

| 项目 | 变化 |
|------|------|
| app.py 行数 | ~4810 → ~4883（+73 行） |
| `bayesian_optimize_params` | +40 行（防过拟合机制） |
| `random_search_params` | +30 行（防过拟合机制） |
| 侧边栏 UI | +100 行（预设策略） |
| 高级策略 UI | +20 行（验证集指标展示） |
| AI_CONTEXT.md | 同步更新行号和架构描述 |

---
---

# 代码模块化重构 - 2026-03-01

## 📋 工作概述

将 5875 行的单文件 `app.py` 拆分为 **15 个模块文件**（core/ 包 10 个 + ui/ 包 4 个 + app.py 入口），实现关注点分离和模块化架构。原文件备份为 `app_original.py`。

---

## 🎯 重构动机

| 问题 | 影响 |
|------|------|
| 单文件 5875 行 | AI 辅助修改时上下文窗口难以覆盖全文，定位困难 |
| 功能混杂 | 数据处理、指标计算、策略逻辑、UI 渲染全部耦合在一起 |
| 协作不便 | 修改一个小功能需要理解整个文件 |
| 难以测试 | 无法单独导入和测试某个模块 |

---

## 📁 新项目结构

```
app.py                (~120 行)   入口文件：页面配置、路由、参数校验
app_original.py       (5875 行)   重构前的完整单文件备份
core/                              核心逻辑包
├── __init__.py       (~63 行)    统一导出所有公共 API
├── config.py         (~115 行)   常量、预设策略参数
├── data.py           (~100 行)   数据加载、标准化（5个函数）
├── indicators.py     (~226 行)   技术指标计算（10个函数）
├── signals.py        (~182 行)   策略信号生成（1个核心函数）
├── backtest.py       (~180 行)   回测引擎（4个函数）
├── utils.py          (~85 行)    工具函数（4个函数）
├── optimizer.py      (~857 行)   参数优化（4个函数）
├── visualization.py  (~884 行)   图表生成（6个函数）
└── portfolio.py      (~325 行)   投资组合模拟与优化（2个函数）
ui/                                界面模块包
├── __init__.py       (~7 行)     统一导出
├── sidebar.py        (~481 行)   侧边栏控件（render_sidebar → dict）
├── multi_stock.py    (~596 行)   多股票对比分析页
└── single_stock.py   (~1030 行)  单股票策略分析页
```

**总计**：约 4835 行代码（含注释和文档字符串），与原文件功能完全一致。

---

## 🔧 模块拆分设计

### 依赖方向（单向）

```
config ← data ← indicators ← signals ← backtest ← optimizer
                                                  ← portfolio
                                                  ← visualization
ui/sidebar ← core.config（预设策略参数）
ui/multi_stock ← core.visualization, core.portfolio, core.utils
ui/single_stock ← core.indicators, core.signals, core.backtest, core.optimizer, core.utils
app.py ← ui.sidebar, ui.multi_stock, ui.single_stock, core.config, core.data, core.utils
```

### 各模块职责

| 模块 | 职责 | 关键设计决策 |
|------|------|------------|
| `core/config.py` | 全局常量 + 预设参数 | `STRATEGY_PRESETS` 和 `_PRESET_PARAMS_FOR_OPTIMIZATION` 集中管理 |
| `core/data.py` | 数据 I/O | `@st.cache_data` 装饰器保留在此，因为缓存是数据层关注点 |
| `core/indicators.py` | 纯计算 | 无 Streamlit 依赖，可独立测试 |
| `core/signals.py` | 纯计算 | 无 Streamlit 依赖，可独立测试 |
| `core/backtest.py` | 纯计算 | 无 Streamlit 依赖，可独立测试 |
| `core/optimizer.py` | 优化算法 | Optuna 条件导入（`try/except`），`st.error` 用于缺 optuna 时提示 |
| `core/visualization.py` | Plotly 图表生成 | 返回 `go.Figure` 对象，不直接调用 `st.plotly_chart` |
| `core/portfolio.py` | 组合逻辑 | 内部调用 indicators→signals→backtest 完整流程 |
| `ui/sidebar.py` | 侧边栏 UI | 返回 **dict**（约40个键），包含所有策略参数 + UI 状态 |
| `ui/multi_stock.py` | 多股页面 | 从 params dict 提取策略参数，通过 `_strategy_params()` 辅助函数过滤 UI 键 |
| `ui/single_stock.py` | 单股页面 | 内部进一步拆分为 11 个私有函数（图表构建、搜索执行、结果展示等） |

### 参数传递机制

```
render_sidebar() → params: dict（~40个键）
    ↓
app.py 提取 UI 状态键（compare_stocks, symbol, adjust, selected_range, uploaded_file）
    ↓
render_multi_stock_page(params, ...) 或 render_single_stock_page(params, ...)
    ↓
各页面函数从 params dict 中按需提取策略参数
```

---

## ✅ 验证结果

| 验证项 | 结果 |
|--------|------|
| 15 个文件语法检查 (`py_compile`) | 全部通过 |
| 9 个 core 模块导入测试 | 全部通过 |
| 3 个 UI 模块发现测试 (`importlib.util`) | 全部可发现 |
| Streamlit 启动测试 | 健康检查返回 `ok` |

---

## 📊 代码量变化

| 项目 | 重构前 | 重构后 |
|------|--------|--------|
| app.py | 5875 行 | ~120 行（入口） |
| 核心逻辑 | 混在 app.py 中 | core/ 包，~3017 行（10个文件） |
| UI 代码 | 混在 app.py 中 | ui/ 包，~2114 行（4个文件） |
| 总代码量 | 5875 行 | ~5251 行（含文档字符串） |
| 文件数 | 1 | 15 |
| 可独立测试的模块 | 0 | 5（indicators, signals, backtest, visualization, utils） |

### 新增文件清单

| 文件 | 行数 | 包含的原 app.py 函数 |
|------|------|---------------------|
| `core/config.py` | 115 | 全局常量、`_PRESET_PARAMS_FOR_OPTIMIZATION`、`STRATEGY_PRESETS` |
| `core/data.py` | 100 | `standardize_columns`、`ensure_date_column`、`fetch_data`、`load_csv`、`load_uploaded_bytes` |
| `core/indicators.py` | 226 | `compute_rsi`、`rolling_zscore`、`rolling_percentile`、`compute_macd`、`compute_atr`、`compute_adx`、`compute_bollinger_bands`、`compute_obv`、`rolling_rank`、`add_indicators` |
| `core/signals.py` | 182 | `compute_signals` |
| `core/backtest.py` | 180 | `simulate_strategy`、`max_drawdown`、`sharpe_ratio`、`walk_forward_backtest` |
| `core/utils.py` | 85 | `format_pct`、`load_or_fetch_stock`、`get_available_stocks`、`normalize_prices` |
| `core/optimizer.py` | 857 | `evaluate_presets_for_optimization`、`random_search_params`、`bayesian_optimize_params`、`genetic_algorithm_optimize_params` |
| `core/visualization.py` | 884 | `create_multi_stock_comparison_chart`、`create_correlation_heatmap`、`create_relative_strength_chart`、`create_risk_return_scatter`、`create_periodic_returns_heatmap`、`create_factor_score_comparison` |
| `core/portfolio.py` | 325 | `run_portfolio_simulation`、`bayesian_optimize_portfolio` |
| `core/__init__.py` | 63 | 统一导出 |
| `ui/sidebar.py` | 481 | 侧边栏 UI 代码（`render_sidebar`） |
| `ui/multi_stock.py` | 596 | 多股对比页 UI + HTML 导出 |
| `ui/single_stock.py` | 1030 | 单股分析页 UI + HTML 导出（11个函数） |
| `ui/__init__.py` | 7 | 统一导出 |
| `app_original.py` | 5875 | 原始完整备份 |

---

## 📝 部署影响

重构后部署命令需要变更：

```bash
# 旧命令（单文件）
scp app.py stratagy:/opt/stratagy/
ssh stratagy "systemctl restart stratagy"

# 新命令（多文件）
scp -r app.py core/ ui/ stratagy:/opt/stratagy/
ssh stratagy "systemctl restart stratagy"
```

`deploy/sync.bat` 需要同步更新以上传 core/ 和 ui/ 目录。

---

## 📝 备注

- `app_original.py` 保留在项目根目录，作为重构前的完整参考，勿删除
- `AI_CONTEXT.md` 已同步更新为模块化架构描述
- 功能行为与重构前完全一致，无任何功能变更

---
---

# 个人网站搭建与部署 - 2026-03-02

## 📋 工作概述

搭建个人网站（React SPA），部署到火山引擎 ECS 服务器，域名 gfm156.com，并将量化策略项目集成为子路径 `/strategy/`。

---

## 🎨 技术选型

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19.2.0 | 前端框架 |
| Vite | 7.3.1 | 构建工具 |
| Tailwind CSS | 4.2.1 | 样式框架（暗色科技风） |
| react-type-animation | 3.2.0 | 首屏打字机效果 |
| lucide-react | 0.575.0 | 图标库 |
| react-router-dom | 7.13.1 | 路由管理 |

---

## 🖥️ 网站内容

### 页面组件（8个）

| 组件 | 文件 | 功能 |
|------|------|------|
| Navbar | `src/components/Navbar.jsx` | 固定顶部导航，滚动时毛玻璃效果，移动端汉堡菜单 |
| Hero | `src/components/Hero.jsx` | 首屏：SH头像、打字机动效（6个角色轮播）、社交链接、CTA按钮 |
| About | `src/components/About.jsx` | 个人简介：4个亮点卡片（金融学在读/编程开发/量化交易/持续学习） |
| Projects | `src/components/Projects.jsx` | 项目展示：4个项目卡片，量化策略平台链接到 gfm156.com/strategy/ |
| Skills | `src/components/Skills.jsx` | 技能展示：4类技能进度条，Intersection Observer 触发动画 |
| Blog | `src/components/Blog.jsx` | 博客文章：3篇示例文章卡片，"即将上线"提示 |
| Contact | `src/components/Contact.jsx` | 联系方式：表单 + 联系信息 |
| Footer | `src/components/Footer.jsx` | 页脚：版权信息 + ICP备案号（粤ICP备2026020082号） |

### 设计风格

- **主题**：暗色科技风（dark-bg: `#0a0a0f`）
- **主色调**：靛蓝渐变（primary: `#6366f1`，accent: `#22d3ee`）
- **特效**：毛玻璃卡片（glass-card）、渐变文字、粒子背景、滚动动画
- **响应式**：适配桌面/平板/手机

### 身份信息

- 中文名：黄宇嘉
- 英文名：Steve Huang
- 学校：香港中文大学（深圳）
- 专业：AI 相关

---

## 📁 项目结构

```
personal-website/                  （位于 C:\Users\Steve Huang\iCloudDrive\Learn\20_Projects\）
├── src/
│   ├── components/               8个页面组件
│   │   ├── Navbar.jsx
│   │   ├── Hero.jsx
│   │   ├── About.jsx
│   │   ├── Projects.jsx
│   │   ├── Skills.jsx
│   │   ├── Blog.jsx
│   │   ├── Contact.jsx
│   │   └── Footer.jsx
│   ├── App.jsx                   主组件（组装所有页面）
│   ├── main.jsx                  入口文件
│   └── index.css                 全局样式 + Tailwind @theme 配置
├── public/
│   └── favicon.svg               SVG 图标
├── nginx/
│   └── www.gfm156.com.conf       Nginx 生产配置（HTTPS + 代理）
├── deploy.bat                    Windows 一键部署脚本
├── deploy.sh                     Linux 一键部署脚本
├── vite.config.js                Vite 构建配置
└── package.json                  依赖管理
```

---

## 🚀 部署配置

### Nginx 配置（/www/server/panel/vhost/nginx/www.gfm156.com.conf）

#### HTTP → HTTPS 重定向

```nginx
server {
    listen 80;
    listen 32;
    server_name 115.191.68.122 www.gfm156.com gfm156.com;
    location / {
        return 301 https://$host$request_uri;
    }
}
```

#### HTTPS 主配置

- 监听 443 端口，启用 SSL
- SPA 路由：`try_files $uri $uri/ /index.html`
- 策略项目代理：`location ^~ /strategy/` → `proxy_pass http://127.0.0.1:8501/`
- 静态资源缓存：图片 30 天，JS/CSS 12 小时
- 安全头：HSTS、X-Frame-Options、X-Content-Type-Options

#### 关键设计：`^~` 修饰符

```nginx
location ^~ /strategy/ {
    proxy_pass http://127.0.0.1:8501/;
    ...
}
```

使用 `^~` 前缀修饰符而非普通前缀匹配，阻止正则 location（`~ .*\.(js|css)$`）拦截 `/strategy/` 下的静态资源请求。如果不加 `^~`，Streamlit 的 JS/CSS 文件会被 Nginx 当作本地文件处理，导致 404。

### 网站文件位置

- 服务器路径：`/www/wwwroot/www.gfm156.com/`
- 文件所有者：`www:www`（与 Nginx worker 进程一致）

### 部署流程

```
本地 npm run build → scp dist/* 到服务器 → nginx -s reload
```

或双击 `deploy.bat` 一键完成。

---

## 🔐 SSL/HTTPS 配置

### 证书信息

| 项目 | 详情 |
|------|------|
| 证书颁发方 | Let's Encrypt |
| 工具 | certbot 2.9.0 |
| 覆盖域名 | gfm156.com + www.gfm156.com |
| 证书路径 | `/etc/letsencrypt/live/gfm156.com/fullchain.pem` |
| 私钥路径 | `/etc/letsencrypt/live/gfm156.com/privkey.pem` |
| 到期时间 | 2026-06-01 |
| 自动续期 | systemd timer（certbot.timer），每 12 小时检查 |

### SSL 安全配置

- 协议：TLSv1.2 + TLSv1.3
- 密码套件：ECDHE-ECDSA/RSA-AES128/256-GCM-SHA256/384
- Session Cache：shared:SSL:10m
- HSTS：max-age=63072000（2年）

### 申请方式

```bash
certbot certonly --webroot -w /www/wwwroot/www.gfm156.com \
  -d gfm156.com -d www.gfm156.com \
  --non-interactive --agree-tos --register-unsafely-without-email
```

---

## 🐛 问题排查与解决

### 1. 端口 80 被火山引擎拦截

- **现象**：网站部署后无法通过 HTTP 访问
- **原因**：域名未在火山引擎完成「接入备案」，云厂商在网络层拦截 HTTP 请求
- **解决**：在火山引擎控制台完成域名接入备案

### 2. 静态资源文件权限不足

- **现象**：CSS/JS 文件返回 403 Forbidden
- **原因**：`scp` 上传的 `assets/` 目录权限为 700（仅 root 可读），Nginx 以 www 用户运行
- **解决**：`chown -R www:www /www/wwwroot/www.gfm156.com/ && chmod 755 assets/`

### 3. /strategy/ 页面空白

- **现象**：访问 `https://gfm156.com/strategy/` 显示空白页，但 Streamlit 在 8501 端口正常运行
- **原因**：Nginx 正则 `location ~ .*\.(js|css)$`（静态资源缓存规则）优先级高于普通前缀 `location /strategy/static/`，Streamlit 的 JS/CSS 文件被 Nginx 当作本地静态文件匹配，返回 404
- **验证**：`curl -sI https://gfm156.com/strategy/static/js/index.Drusyo5m.js` 返回 404
- **解决**：将 `location /strategy/` 改为 `location ^~ /strategy/`，`^~` 修饰符使前缀匹配优先于正则匹配，所有 `/strategy/` 下的请求统一代理到 Streamlit

### 4. 浏览器显示"不安全"

- **现象**：网站可访问但地址栏显示"不安全"
- **原因**：仅配置了 HTTP（80端口），未配置 HTTPS（443端口），与 ICP 备案无关
- **解决**：安装 certbot，申请 Let's Encrypt SSL 证书，配置 HTTPS + HTTP→HTTPS 重定向

---

## 📊 最终验证结果

| 验证项 | 结果 |
|--------|------|
| https://www.gfm156.com | ✅ 200 OK，显示个人网站 |
| https://gfm156.com/strategy/ | ✅ 200 OK，显示量化策略平台 |
| http://www.gfm156.com | ✅ 301 重定向到 HTTPS |
| SSL 证书 | ✅ 有效，浏览器显示🔒 |
| HSTS 头 | ✅ max-age=63072000 |
| 证书自动续期 | ✅ dry-run 测试通过 |

---

## 📝 备注

- ICP 备案号：粤ICP备2026020082号，已展示在网站 Footer 并链接到 beian.miit.gov.cn
- 个人网站项目独立于量化策略项目，位于 `C:\Users\Steve Huang\iCloudDrive\Learn\20_Projects\personal-website\`
- SSH 免密登录沿用此前配置的 Ed25519 密钥，`ssh root@115.191.68.122` 直接连接
