# 🤖 AI 协作工作指南

> 本文档面向参与本项目的 AI 助手（如 GitHub Copilot、Cursor、Claude 等），  
> 帮助你快速理解项目、获取权限、参与开发工作。

---

## 📋 项目概览

**项目名称**：量化交易策略分析应用（策略实验室）  
**技术栈**：Python + Streamlit + AkShare + Plotly + Optuna  
**当前状态**：已部署到云服务器，可在线访问

### 核心功能
| 功能 | 说明 |
|------|------|
| 股票数据管理 | 从 AkShare 下载美股日线数据，本地缓存 CSV |
| 技术指标计算 | RSI、MACD、EMA、ATR、ADX、布林带、OBV 等 |
| 多因子量化策略 | 10个因子加权评分 + 4个可选入场过滤器 + 7档动态仓位 |
| 策略回测 | 模拟交易、止损止盈、Walk-Forward 滚动回测 |
| 参数优化 | 贝叶斯优化（Optuna）/ 随机搜索 自动寻优 |
| 多股对比 | 归一化价格对比、相关性热图、HTML 报告导出 |
| Web 界面 | Streamlit 构建，所有参数可通过侧边栏实时调整 |

### 项目结构
```
stratagy/
├── app.py                # 主程序（约3300行，单文件架构）
├── requirements.txt      # Python 依赖
├── data/                 # 股票 CSV 数据（10只美股）
├── deploy/               # 部署相关脚本
│   ├── deploy.sh         # 服务器一键部署脚本
│   ├── sync.bat          # 本地→服务器 一键同步
│   ├── upload_and_deploy.bat
│   └── fix_config.sh
├── document/             # 技术文档
├── docs/                 # 项目文档
└── AI_GUIDE.md           # 本文件
```

### app.py 代码结构
| 模块 | 行范围（约） | 功能 |
|------|-------------|------|
| 数据处理 | 1-170 | 列名标准化、CSV加载、AkShare下载 |
| 技术指标 | 170-570 | RSI、MACD、ATR、ADX、布林带、OBV 等计算 |
| 策略信号 | 570-910 | 10因子评分 + 过滤器 + 仓位管理 |
| 回测引擎 | 910-1090 | 模拟交易（ATR止损止盈、动态仓位） |
| 评估指标 | 1090-1160 | 最大回撤、夏普比率 |
| Walk-Forward | 1160-1250 | 滚动窗口回测 |
| 参数优化 | 1250-1590 | 随机搜索 + 贝叶斯优化 |
| UI 界面 | 1590-3305 | Streamlit 侧边栏、图表、多股对比、HTML导出 |

---

## 🖥️ 服务器信息

| 项目 | 值 |
|------|-----|
| 云服务商 | 火山引擎 ECS |
| 地域 | 华北2（北京） |
| 系统 | Ubuntu 24.04 LTS |
| 公网 IP | `115.191.68.122` |
| 应用端口 | `8501`（Streamlit） |
| 访问地址 | http://115.191.68.122:8501 |
| 项目路径 | `/opt/stratagy/` |
| 虚拟环境 | `/opt/stratagy/venv/` |
| 服务名称 | `stratagy.service`（systemd） |

---

## 🔑 SSH 免密登录（AI 如何连接服务器）

### 已配置的方式

本机已配置 SSH 密钥免密登录，SSH Config 中注册了别名 `stratagy`。

**SSH Config 位置**：`C:\Users\Steve Huang\.ssh\config`  

```
Host stratagy
    HostName 115.191.68.122
    User root
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking no
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

### 使用方法

```bash
# 登录服务器（无需密码）
ssh stratagy

# 远程执行命令
ssh stratagy "systemctl status stratagy"

# 上传文件
scp app.py stratagy:/opt/stratagy/

# 上传整个目录
scp -r data/ stratagy:/opt/stratagy/data/
```

### 如果你是新加入的 AI

如果你在另一台机器上工作，需要：
1. 生成自己的密钥：`ssh-keygen -t ed25519 -C "ai-agent-name"`
2. 将公钥内容告知项目负责人，由负责人添加到服务器 `~/.ssh/authorized_keys`
3. 在你的 `~/.ssh/config` 中添加上面的 Host 配置

---

## 🔄 日常开发工作流

### 修改代码后部署（推荐流程）

```bash
# 方式1：一键同步（双击即可）
deploy/sync.bat

# 方式2：手动操作
scp app.py stratagy:/opt/stratagy/
ssh stratagy "systemctl restart stratagy"
```

### AI 参与工作的典型操作

```bash
# 1. 编辑本地 app.py（在 VS Code 中直接修改）

# 2. 同步到服务器
scp app.py stratagy:/opt/stratagy/

# 3. 重启服务
ssh stratagy "systemctl restart stratagy"

# 4. 验证是否正常运行
ssh stratagy "systemctl is-active stratagy"

# 5. 查看错误日志（如果出问题）
ssh stratagy "journalctl -u stratagy -n 50 --no-pager"
```

---

## 🛠️ 服务器管理命令速查

| 操作 | 命令 |
|------|------|
| 查看服务状态 | `ssh stratagy "systemctl status stratagy --no-pager"` |
| 重启服务 | `ssh stratagy "systemctl restart stratagy"` |
| 停止服务 | `ssh stratagy "systemctl stop stratagy"` |
| 查看日志 | `ssh stratagy "journalctl -u stratagy -f"` |
| 查看最近日志 | `ssh stratagy "journalctl -u stratagy -n 50 --no-pager"` |
| 检查端口 | `ssh stratagy "ss -tlnp \| grep 8501"` |
| 检查磁盘 | `ssh stratagy "df -h"` |
| 检查内存 | `ssh stratagy "free -h"` |
| 更新依赖 | `ssh stratagy "source /opt/stratagy/venv/bin/activate && pip install -r /opt/stratagy/requirements.txt"` |

---

## ⚠️ 注意事项

### 操作规范
1. **修改前先读代码**：app.py 有 3300+ 行，修改前确保理解上下文
2. **小步提交**：每次只改一个功能点，同步后验证再改下一个
3. **检查日志**：每次重启后用 `journalctl` 确认没有报错
4. **不要删除 data/ 目录**：里面是已缓存的股票数据

### 已知限制
- 服务器内存 4GiB，贝叶斯优化时注意资源占用
- AkShare 需要网络访问，服务器在北京，访问美股数据可能偶尔超时
- 单文件架构（app.py），后续可能需要拆分模块

### 安全提醒
- SSH 密钥文件 (`id_ed25519`) 不要上传到 Git 仓库
- 公网 IP 和端口信息不要公开分享
- 如果密钥泄露，立即在服务器删除对应公钥并重新生成

---

## 📞 联系方式

项目负责人：Steve Huang  
课程：AIE1902  
学期：2026 Spring

---

*最后更新：2026年2月24日*
