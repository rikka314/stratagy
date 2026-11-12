# Deploy And Runtime Interfaces

> 最近更新：2026-09-15
> 适用范围：`run.bat`、`run.sh`、`scripts/setup.bat`、`scripts/start.bat`、`deploy/*`、`.streamlit/config.toml`。

## 当前运行时契约

- 默认 Web 运行时：React/Vite JavaScript 前端 + FastAPI Python 后端。
- Python 入口：`uvicorn api.main:app`。
- 本地监听：`0.0.0.0:8501`；生产 systemd 只监听 `127.0.0.1:8501`，由 Nginx 对外提供服务。
- SPA 基础路径：`/strategy`，构建输出为 `frontend/dist/`，由 FastAPI 挂载并支持 deep-link fallback。
- API 前缀：`/strategy/api`；健康检查：`GET /strategy/api/health`。
- 旧 Streamlit 入口仍为 `app.py`，只通过本地 `--legacy-streamlit` 显式启用；`.streamlit/config.toml` 只服务这个回滚入口。
- 服务器别名：`stratagy`；目录：`/opt/stratagy`；systemd 服务：`stratagy`。

## 本地启动

Windows 使用 `run.bat`，macOS/Linux 使用 `./run.sh`。默认流程：

1. 验证 Python 3.10+，创建 `.venv`。
2. 比较 `.venv/.requirements.sha256`，仅在 `requirements.txt` 变化时安装 Python 依赖。
3. 验证 Vite 8 支持的 Node.js（20.19+ 或 22.12+）与 npm。
4. 比较 `.venv/.frontend-requirements.sha256`；仅在 `package.json` 或 lockfile 变化时运行 `npm install`，随后执行 `npm run build`。
5. 启动 `python -m uvicorn api.main:app --host 0.0.0.0 --port 8501`。

支持 `--setup-only`（安装并构建但不启动）和 `--legacy-streamlit`（跳过 Node 构建并运行旧 `app.py`），两者可以组合。`scripts/setup.bat` 和 `scripts/start.bat` 转发到根脚本，避免维护第二套依赖逻辑。

## Python 依赖与前端产物

- `requirements.txt` 同时包含 FastAPI/Uvicorn 和旧 Streamlit 依赖。保留 Streamlit 是为了可回滚。
- `frontend/node_modules/` 与 `frontend/dist/` 不进入 Git。
- 部署前运行 `run.bat --setup-only` 或 `./run.sh --setup-only`，生成待上传的 `frontend/dist/index.html`。
- 服务端无需 Node.js；服务器运行预先构建的静态文件。

## 增量同步与全量部署

2026-09-15 已完成生产迁移，服务与主站 Nginx 已使用下述 FastAPI 契约。发布前程序、systemd 和 Nginx 配置备份位于服务器 `/opt/stratagy-backups/20260915-release/`。

当前两个上传脚本的研究输出筛选仅覆盖含 `report.json` 的目录，会遗漏部分研究图表证据，且不上传 `document/`。发布时必须补传本地存在的 catalog / supplemental evidence；本次以压缩包同步全部 `model-test/outputs/`、`document/` 和相关研究运行文件，压缩包经 SHA-256 校验后解压。跨 Windows/Linux 上传的 shell 脚本应确认使用 LF 换行后再执行。

`deploy/sync.bat` 上传 `api/*.py`、`core/*.py`、`frontend/dist/`、`research/`、`model-test/model_test/`、`model-test/configs/`、`data/macro/`、requirements、部署配置和可用的数据/报告资源。`app.py` 与 `ui/*.py` 也继续上传，供旧入口回滚。上传后按 requirements 指纹安装依赖，再通过 `fix_config.sh` 写入并启动 Uvicorn systemd 服务，最后检查 `/strategy/api/health`。

`deploy/upload_and_deploy.bat` 上传相同运行集合，并执行 `deploy/deploy.sh` 完成首次 bootstrap。两个脚本都支持 `--dry-run`，且要求本地已经存在 API 入口和前端构建产物。

## systemd

`deploy/deploy.sh` 与 `deploy/fix_config.sh` 写入相同入口：

```ini
WorkingDirectory=/opt/stratagy
ExecStart=/opt/stratagy/venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8501
```

服务仍命名为 `stratagy`。首次 bootstrap 安装 Python 系统依赖、创建 venv、安装 requirements、记录依赖指纹、写入 systemd 并运行健康检查。生产端口只绑定 loopback；公网访问经过 Nginx。

## Nginx `/strategy` 契约

`deploy/nginx_strategy.conf` 分离请求：

- `= /strategy`：302 到 `/strategy/`，保留 query string。
- `= /strategy/api/health`：反代健康检查并返回 `Cache-Control: no-store`。
- `^~ /strategy/api/`：反代 API，关闭响应缓冲并允许较长计算请求。
- `^~ /strategy/assets/`：缓存 Vite content-hashed assets 一年并标记 immutable。
- `^~ /strategy/`：反代 SPA HTML 与 deep links，由 FastAPI fallback 到 `index.html`。

合并模板后执行 `nginx -t`，再 reload。至少验证：

```bash
curl -fsS http://127.0.0.1:8501/strategy/api/health
curl -I https://www.gfm156.com/strategy/
curl -I https://www.gfm156.com/strategy/stock-analysis
```

## 常用运维命令

```bash
ssh stratagy "systemctl restart stratagy"
ssh stratagy "systemctl is-active stratagy"
ssh stratagy "journalctl -u stratagy -n 50 --no-pager"
ssh stratagy "/opt/stratagy/deploy/check_runtime.sh /opt/stratagy"
```

## 修改规则

- 改 API 前缀、SPA base path 或健康检查时，同步检查 `api/main.py`、`frontend/vite.config.js`、前端 API client、Nginx、health helper 与本文档。
- 改上传清单时，同步 `deploy/sync.bat` 与 `deploy/upload_and_deploy.bat`。
- 改服务名、端口或目录时，同步两份 bat、部署 shell、Nginx 与运维命令。
- `.streamlit/config.toml` 的 `baseUrlPath = "strategy"` 必须继续与旧回滚入口一致。
