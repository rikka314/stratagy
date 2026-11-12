# Web Performance Phase 6 验收记录

> 日期：2026-08-09  
> 范围：启动、依赖与部署链  
> 生产变更边界：本次仅修改并验证仓库中的部署资产；未 reload Nginx、未执行生产部署

## 结论

Phase 6 的代码与部署 contract 已完成。本机重复启动和日常增量同步都以 `requirements.txt` 的 SHA-256 为安装门禁；全量部署记录相同指纹。受支持的 Streamlit 区间已固定为 `>=1.60.0,<1.62.0`。部署后统一输出 Python / Streamlit 版本，并以 `/strategy/_stcore/health` 作为启动成功条件。

Nginx 模板已将 content-hashed 静态资源与 Streamlit 运行时端点拆开：`/strategy/static/` 使用一年 immutable cache，`/strategy/_stcore/` 使用 no-store、关闭代理缓冲并保留 WebSocket upgrade。真实主机已只读确认存在全局 HTML / JS / CSS gzip，因此模板不重复 gzip 指令。

## 实施内容

- `run.bat`
  - 计算 `requirements.txt` SHA-256，保存到 `.venv/.requirements.sha256`。
  - 指纹未变化时跳过 pip；安装成功后才更新指纹。
  - 使用 venv Python 启动 Streamlit，并输出 Python / Streamlit 版本。
  - 提供 `--setup-only` 验收模式，完成依赖检查后不启动服务。
- `deploy/install_requirements_if_needed.sh`
  - 比较远端 requirements 与已安装指纹。
  - 仅在变化时安装，成功后原子替换指纹文件。
- `deploy/check_runtime.sh`
  - 输出服务器 Python / Streamlit 版本。
  - 最多轮询 20 次 base-path health endpoint；失败时返回非零并输出 systemd 状态。
- `deploy/sync.bat`
  - 上传两个新 helper。
  - 先确认依赖，再重启服务，最后执行健康检查。
- `deploy/upload_and_deploy.bat` / `deploy/deploy.sh`
  - 全量上传包含新 helper。
  - bootstrap 完整安装后记录指纹与版本，并把健康检查作为成功门槛。
- `deploy/nginx_strategy.conf`
  - 新增独立 static 与 `_stcore` location；通用 `/strategy/` WebSocket/base-path contract 保持不变。
- `document/interfaces/deploy-runtime.md` / `AI_CONTEXT.md`
  - 同步长期运行时与部署事实。

## 线上只读核验

执行 `nginx -T` 后确认：

- 真实 HTTPS 主 vhost 为 `/www/server/panel/vhost/nginx/www.gfm156.com.conf`。
- 当前 `/strategy` 仍通过保留前缀的 `proxy_pass http://127.0.0.1:8501` 提供。
- Nginx 全局已开启 gzip，并覆盖 HTML / JavaScript / CSS 类型。
- 当前生产服务为 Python 3.12.3 / Streamlit 1.54.0，且尚无依赖指纹；这证明生产仍未执行本阶段部署，不能把其版本记为本阶段已落地结果。
- 当前五条公开路由均返回 HTTP 200；`/strategy/_stcore/health` 返回 200，WebSocket 握手返回 `101 Switching Protocols`。
- 生产 Nginx 尚未合并本次 static / `_stcore` 拆分模板；需要在后续明确部署窗口中合并、`nginx -t`、reload 后重新验证响应头。

## 自动化验证

```text
run.bat --setup-only（首次）：依赖检查 4.7 s，安装成功并写入指纹，Python 3.13.7 / Streamlit 1.60.0
run.bat --setup-only（二次）：1.2 s，明确输出 requirements.txt unchanged; skipping pip install
bash -n deploy/install_requirements_if_needed.sh deploy/check_runtime.sh deploy/deploy.sh：通过
cmd /c deploy\sync.bat --dry-run：通过，依赖安装位于 restart 之前，健康检查位于 restart 之后
cmd /c deploy\upload_and_deploy.bat --dry-run：通过，新 helper 均包含在上传清单
pytest -q tests/test_web_performance_contracts.py tests/test_w8_exports_and_routes.py：26 passed
pytest -q：146 passed in 15.30s
```

## 未执行的外部变更

本阶段没有自动修改生产 vhost、重载 Nginx 或上传当前脏工作树。仓库模板与部署脚本已就绪；生产落地应在明确部署授权下执行，并在完成后检查五条公开路由、静态缓存头、health no-store 与 WebSocket 握手。
