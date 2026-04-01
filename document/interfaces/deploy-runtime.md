# Deploy And Runtime Interfaces

> 最近更新：2026-03-31
> 适用范围：`.streamlit/config.toml`、`deploy/*.bat`、`deploy/*.sh`、`deploy/nginx_strategy.conf`。

## 当前运行时事实

- Streamlit 地址：`0.0.0.0:8501`
- `server.baseUrlPath = "strategy"`
- 公开路径：
  - `/strategy`
  - `/strategy/stock-analysis`
  - `/strategy/stocks-analysis`
  - `/strategy/model-evaluation`
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
- `deploy/nginx_strategy.conf`
- `core/catalogs/*.csv`
- `data/*.csv`（存在时）
- `model-test/outputs/`（存在时；供 `/strategy/model-evaluation` 读取 `report.json` / `mlflow_run.json` / QuantStats HTML）
- 重启 `stratagy` 服务

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
3. 创建 venv 并安装 `requirements.txt`
4. 写 `.streamlit/config.toml`
5. 创建并重启 `stratagy.service`
6. 打开 UFW 22 / 8501

这份脚本承担“首次部署或完整修复”的职责，不是日常小改动的首选路径。

## Nginx 子路径 contract：`deploy/nginx_strategy.conf`

当前模板固定两段：

- `location = /strategy`
  - 302 到 `/strategy/`
- `location ^~ /strategy/`
  - 反代到 `http://127.0.0.1:8501`
  - 保留前缀
  - 带 websocket upgrade 头

这是线上子路径运行成立的关键。如果改成别的路径，不仅要改 nginx，还要同步 `baseUrlPath` 和 `app.py` 路由认知。

## 常用运维命令

```bash
ssh stratagy "systemctl restart stratagy"
ssh stratagy "systemctl is-active stratagy"
ssh stratagy "journalctl -u stratagy -n 50 --no-pager"
```

## 修改规则

- 改公开路径：
  同步 `app.py`、`.streamlit/config.toml`、`deploy/nginx_strategy.conf`
- 改上传清单：
  同步 `deploy/sync.bat` 与 `deploy/upload_and_deploy.bat`
- 改服务名或目录：
  同步两份 bat、`deploy.sh`、文档与运维命令

如果任务只是页面或策略逻辑修改，不需要读本文档。
