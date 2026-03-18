# 量化交易策略分析应用

一个基于 Streamlit 的模块化量化策略平台，当前以云端服务形态提供使用。

> 最近整理：2026-03-18（移除本地启动遗留文档，文档分层为 current/archive/presentation）

## 当前使用方式（云端）

- 访问地址：`http://115.191.68.122:8501`
- 默认流程：打开网页即可使用，不再要求先在本机安装 Python 或运行本地启动脚本
- 支持功能：单股分析、多股对比、策略回测、参数优化、组合模拟、图表导出

## 功能概览

- 多因子策略打分（10 因子）与分档仓位控制
- 技术指标分析（RSI、MACD、EMA、ATR、ADX、OBV、布林带等）
- 历史回测与 Walk-Forward 验证
- 参数优化（贝叶斯优化 / 遗传算法 / 随机搜索）
- 多股票相关性、风险收益、相对强弱分析

## 项目结构

```text
stratagy/
├── app.py              # 应用入口
├── core/               # 核心策略/回测/优化逻辑
├── ui/                 # 页面与交互
├── deploy/             # 服务器部署脚本
├── document/           # 项目文档（当前文档 + 归档 + 演示稿）
├── data/               # 缓存或样例数据
├── requirements.txt    # 服务器或本地开发依赖
└── AI_CONTEXT.md       # AI 协作上下文
```

## 文档目录说明

- `document/`：当前维护中的工作文档（例如 `SCOPE_FREEZE.md`、`TASK_BREAKDOWN.md`）
- `document/archive/`：历史阶段文档和修复记录（保留追溯，不参与日常维护）
- `document/presentation/`：汇报/演示稿
- `AI_CONTEXT.md`：AI 协作主入口（统一上下文，不再维护独立 AI 指南）

## 代码更新后的部署

在本仓库改完代码后，使用部署命令同步到服务器并重启服务：

```bash
scp -r app.py core/ ui/ stratagy:/opt/stratagy/
ssh stratagy "systemctl restart stratagy"
```

查看服务日志：

```bash
ssh stratagy "journalctl -u stratagy -n 50 --no-pager"
```

## 开发说明

- 本仓库仍是 Python 项目源码仓库，`requirements.txt` 用于部署环境和开发环境依赖管理
- 已移除面向终端用户的本地一键启动/环境检查入口，避免与云端使用方式混淆

## 免责声明

本应用仅供学习和研究使用，不构成任何投资建议。投资有风险，决策需谨慎。
