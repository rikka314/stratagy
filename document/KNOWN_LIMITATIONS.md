# 已知限制清单

> 更新日期：2026-04-01  
> 适用范围：当前 `/strategy` 云端部署版本

## 1. 外部数据源依赖

- 实时指数、推荐股票、部分市场快照依赖 AkShare 与网络环境。
- 当上游接口波动、限流或字段缺失时，页面会优先降级为 `暂无数据` / `N/A`，而不是保证所有字段始终完整。

## 2. 服务器不长期存放全量股票数据

- 当前部署遵循“按需拉取最新数据”的路线，服务器不作为长期股票 CSV 仓库。
- 因此首次打开某些标的时，加载速度与可用性受网络和数据源状态影响。

## 3. 上传数据入口仍以 CSV 为主

- 当前上传入口读取的是 CSV 字节流。
- 上传文件需要能被标准化为 `date/open/high/low/close/volume` 这一组核心字段；否则页面无法进入完整分析链路。

## 4. 模型评估页依赖离线研究输出物

- `/strategy/model-evaluation` 展示内容依赖 `model-test/outputs/` 下已生成并已同步到服务器的 `report.json` / `mlflow_run.json` / QuantStats HTML。
- 本地未生成或未上传的研究结果不会出现在线上评估页中。

## 5. 子路径部署依赖 Nginx 与 Streamlit contract

- 当前公网可访问性依赖以下三处保持一致：
  - `app.py`
  - `.streamlit/config.toml`
  - `deploy/nginx_strategy.conf`
- 若后续变更 `/strategy` 基路径，只改其中一处会导致刷新、直达链接或反向代理行为异常。
