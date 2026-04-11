# 项目规范

## 每次对话开始时

**必须先读取 `AI_CONTEXT.md`**，获取项目结构、模块说明和修改须知，再开始工作。

这个文件是整个项目的快速上下文（约2k tokens），能让你避免重复读源码。

## 工作区约定

**不要创建新的工作区（worktree / workspace / sandbox）。**

本项目的开发和运维均通过 SSH 远程连接到服务器进行：

- SSH 别名：`stratagy`
- 项目目录：`/opt/stratagy`

如需在编辑器（VS Code / Cursor）中工作，请使用 Remote-SSH 扩展直接连接 `stratagy`，打开 `/opt/stratagy` 目录，**不要在本地克隆后新建工作区**。
