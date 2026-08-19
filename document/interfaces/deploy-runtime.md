# Deploy And Runtime Interfaces

> 最近更新：2026-08-11
> 适用范围：`.streamlit/config.toml`、`deploy/*.bat`、`deploy/*.sh`、`deploy/nginx_strategy.conf`。

## 当前运行时事实

- Streamlit 地址：`0.0.0.0:8501`
- `server.baseUrlPath = "strategy"`
- 公开路径：
  - `/strategy`
  - `/strategy/stock-analysis`
  - `/strategy/stocks-analysis`
  - `/strategy/model-evaluation`
  - `/strategy/final-report`
- 本地控制路径：`/strategy/experiment-monitor`，仅在
  `STRATAGY_RESEARCH_CONTROL=1` 时注册，不属于生产默认公开路由。
- 支持的 Web 运行时：`streamlit>=1.60.0,<1.62.0`
- 服务器别名：`stratagy`
- 服务器目录：`/opt/stratagy`
- systemd 服务名：`stratagy`

## 核心文件与职责

| 文件 | 角色 |
|---|---|
| `.streamlit/config.toml` | Streamlit 地址、端口、`baseUrlPath`、上传大小 |
| `deploy/sync.bat` | Windows 侧增量同步与服务重启 |
| `deploy/upload_and_deploy.bat` | Windows 侧全量上传并远端执行 `deploy.sh` |
| `deploy/deploy.sh` | 服务器 bootstrap：依赖、venv、systemd、UFW、默认配置 |
| `deploy/install_requirements_if_needed.sh` | 比较远端依赖指纹，仅在 `requirements.txt` 变化时安装 |
| `deploy/check_runtime.sh` | 输出 Python / Streamlit 版本并检查 base-path health endpoint |
| `deploy/nginx_strategy.conf` | `/strategy` 子路径反向代理模板 |
| `deploy/fix_config.sh` | 远端修配置辅助脚本 |

## `.streamlit/config.toml`

当前关键项：

```toml
[server]
address = "0.0.0.0"
port = 8501
headless = true
baseUrlPath = "strategy"
maxUploadSize = 50
```

如果改公开路由或子路径，必须同步检查：

- `app.py`
- `.streamlit/config.toml`
- `deploy/nginx_strategy.conf`
- 上传脚本中的文件清单

## 增量同步：`deploy/sync.bat`

职责：

- 检查 `ssh` / `scp`
- 创建远端目录
- 上传：
  - `app.py`
  - `requirements.txt`
  - `core/*.py`
  - `ui/*.py`
  - `.streamlit/config.toml`
- `deploy/deploy.sh`
- `deploy/fix_config.sh`
- `deploy/install_requirements_if_needed.sh`
- `deploy/check_runtime.sh`
- `deploy/nginx_strategy.conf`
- `core/catalogs/*.csv`
- `data/*.csv`（存在时）
- `model-test/outputs/`（存在时；供 `/strategy/model-evaluation` 读取 `report.json` / `mlflow_run.json` / QuantStats HTML）
- 上传后执行 `install_requirements_if_needed.sh`：远端 `venv/.requirements.sha256` 与新 `requirements.txt` 的 SHA-256 一致时跳过 pip，否则先安装并在成功后原子更新指纹
- 依赖确认完成后重启 `stratagy` 服务，并由 `check_runtime.sh` 输出 Python / Streamlit 版本、轮询 `/strategy/_stcore/health`

支持：

- `--dry-run`

## 全量上传：`deploy/upload_and_deploy.bat`

职责：

- 以 `root@115.191.68.122` 为目标执行完整上传
- 上传与 `sync.bat` 基本同一批文件
- 若本地存在 `model-test/outputs/`，一并上传到 `/opt/stratagy/model-test/outputs/`
- 远端执行：

```bash
bash /opt/stratagy/deploy/deploy.sh
```

支持：

- `--dry-run`

## 远端 bootstrap：`deploy/deploy.sh`

主要步骤：

1. 安装系统依赖
2. 创建 `/opt/stratagy`
3. 创建 venv 并完整安装 `requirements.txt`，记录 `venv/.requirements.sha256` 和 Python / Streamlit 版本
4. 写 `.streamlit/config.toml`
5. 创建并重启 `stratagy.service`，轮询 `http://127.0.0.1:8501/strategy/_stcore/health`；超出检查预算则部署失败并输出服务状态
6. 打开 UFW 22 / 8501

这份脚本承担“首次部署或完整修复”的职责，不是日常小改动的首选路径。

## Nginx 子路径 contract：`deploy/nginx_strategy.conf`

当前模板固定四段：

- `location = /strategy`
  - 302 到 `/strategy/`，并通过 `$is_args$args` 保留 `lang`、`ws` 等查询参数
- `location ^~ /strategy/static/`
  - 保留 `/strategy` 前缀反代静态资源
  - 开启代理缓冲，隐藏上游 Cache-Control 后返回单一 `Cache-Control: public, max-age=31536000, immutable`
- `location ^~ /strategy/_stcore/`
  - 承载 health、host-config 与 WebSocket
  - 隐藏上游 Cache-Control 后明确返回单一 `Cache-Control: no-store`、关闭代理缓冲、保留 Upgrade 头与长连接 timeout
- `location ^~ /strategy/`
  - 反代到 `http://127.0.0.1:8501`
  - 保留前缀
  - 带 websocket upgrade 头

2026-08-09 已通过 `nginx -T` 只读核验真实主机：全局 `http` 配置已对 HTML / JS / CSS 启用 gzip，因此 vhost 模板不重复声明 gzip。合并模板后仍须执行 `nginx -t`，再 reload 并核对静态缓存头与 `_stcore` no-store。

这是线上子路径运行成立的关键。如果改成别的路径，不仅要改 nginx，还要同步 `baseUrlPath` 和 `app.py` 路由认知。

## 本地一键启动：`run.bat` / `run.sh`

- Windows 使用 `run.bat`，macOS / Linux 使用根目录 `run.sh`；两者都直接调用虚拟环境内的 Python，不依赖手工 activate。
- `run.bat` 使用 PowerShell `Get-FileHash`，`run.sh` 使用 Python 标准库计算 `requirements.txt` 的 SHA-256。
- 指纹保存在忽略版本控制的 `.venv/.requirements.sha256`。
- venv 不存在时先创建；指纹缺失或变化时才执行 `python -m pip install -r requirements.txt`。
- 安装成功后才更新指纹；普通二次启动直接跳过 pip。
- 每次启动输出 Python / Streamlit 版本，并通过该 venv 的 Python 启动 Streamlit。
- 启动 Streamlit 前设置 `STRATAGY_RESEARCH_CONTROL=1`，开放本机实验监控与安全暂停页；远端 systemd 未设置该变量，因此生产默认不注册控制页。
- `run.bat --setup-only` / `./run.sh --setup-only` 执行相同依赖检查与版本输出后退出，用于无服务启动的验收。
- `run.sh` 默认优先选择 `python3`，也可通过 `PYTHON_BIN=/path/to/python` 显式指定解释器。

## 常用运维命令

```bash
ssh stratagy "systemctl restart stratagy"
ssh stratagy "systemctl is-active stratagy"
ssh stratagy "journalctl -u stratagy -n 50 --no-pager"
ssh stratagy "/opt/stratagy/deploy/check_runtime.sh /opt/stratagy"
```

## 修改规则

- 改公开路径：
  同步 `app.py`、`.streamlit/config.toml`、`deploy/nginx_strategy.conf`
- 改上传清单：
  同步 `deploy/sync.bat` 与 `deploy/upload_and_deploy.bat`
- 改服务名或目录：
  同步两份 bat、`deploy.sh`、文档与运维命令

如果任务只是页面或策略逻辑修改，不需要读本文档。
