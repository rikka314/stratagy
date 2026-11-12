# JavaScript Frontend Runtime

项目默认入口已迁移为 JavaScript SPA 与 Python API 的单进程部署形态。Python 的策略计算模块继续位于 `core/`，FastAPI 负责参数校验、任务编排和结果序列化；React/Vite 负责页面、状态与图表交互。

## 环境要求

- Python 3.10+
- Node.js 20.19+ 或 22.12+
- npm

Windows 运行 `run.bat`，macOS/Linux 运行 `./run.sh`。浏览器入口为 `http://localhost:8501/strategy/`，API 健康检查为 `http://localhost:8501/strategy/api/health`。

只安装依赖并构建前端：

```bat
run.bat --setup-only
```

临时回到旧 Streamlit 页面：

```bat
run.bat --legacy-streamlit
```

前端构建产物位于 `frontend/dist/`。它属于生成文件且不会提交到 Git，但部署脚本会上传它，因此每次部署前要先完成一次 setup/build。

## 开发边界

- UI 路由和组件：`frontend/src/`
- 前端构建配置：`frontend/vite.config.js`
- HTTP API 与 SPA 挂载：`api/`
- 策略计算：`core/`
- 旧页面回滚入口：`app.py`、`ui/`、`.streamlit/config.toml`

修改公开路径时要保持 `/strategy` 在 Vite base、FastAPI route、前端 API client 和 Nginx 中一致。完整部署约定见 `document/interfaces/deploy-runtime.md`。

## 临时工作区与本地实验控制

浏览器保存轻量草稿、数据集 ID、任务 ID 和组合结果 ID；数据与完成结果保存在 Python 服务端，默认有效期 24 小时。刷新恢复完成结果，不自动重新计算。浏览器存储禁用或配额不足会显示未保存提示；过期数据需要重新加载。

`/strategy/experiment-monitor` 默认只显示控制未启用状态。需要本地实验控制时，在启动 Python 服务之前显式设置 `STRATAGY_RESEARCH_CONTROL=1`；不要在公开生产服务上开启。迁移验收没有启动或暂停任何研究实验。
