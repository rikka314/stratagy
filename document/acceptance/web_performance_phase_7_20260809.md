# Web 性能 Phase 7 最终验收（2026-08-09）

## 结论

Phase 7 的本地功能矩阵、自动化回归、冷/热浏览器采样和验收记录已完成。

- 全量测试：`156 passed in 16.27s`。
- 冷 `import app`：p50 `736.065 ms`、p75 `736.764 ms`，通过 `<= 1000 ms` 预算。
- 首页恢复为真正的 shell-first：三次独立 Streamlit 进程首访中，壳层 p50 `2235 ms`，完整数据 p50 `5859 ms`；外部接口较慢时平台标题和降级内容仍先显示。
- 报告默认章：`1424` 个 DOM 节点、页面 HTML `115832` 字符，通过 `< 2000` / `< 120k` 预算。
- 本地公开路由、单股、多股、模型评估与报告主流程均可用；未执行生产部署，因此“部署后线上复测”仍是发布动作，不以旧线上版本替代本地结果。

## 环境与口径

- Windows / Python `3.13.7`
- Streamlit `1.60.0`
- 浏览器自动化：Playwright CLI，计时在既有 session 内用 `Date.now()` 包围 `goto/click` 与目标元素 `waitFor()`，不计 `npx` 启动时间。
- “进程冷”：每次重启 Streamlit，使用新浏览器 context 首访。
- “浏览器 context 冷”：同一服务进程中创建新 context；服务端缓存可能已热。
- “热”：同一浏览器 context、同一服务进程重复导航或切换。
- 本地子路由直接打开时，Streamlit 客户端会先探测 `<子路由>/_stcore/health` 与 `host-config` 并产生两条 404，随后回退到 `/strategy/_stcore/*`，WebSocket 与页面功能正常；服务重启期间的 `ERR_CONNECTION_REFUSED` 不计为应用错误。

## 功能矩阵

| 路由/动作 | 验收证据 | 结果 |
|---|---|---|
| 首页 | 浏览器验证 zh/en、美股/A 股、换一只；服务端真实新闻/行情成功，自动化覆盖无 key、短结果、行情失败和无伪造报价；`prefers-reduced-motion: reduce` 下仅第一条新闻和第一幕市场镜头可见 | 通过 |
| 单股入口 | 浏览器以 `AAPL` 搜索并进入分析；推荐、刷新入口可见；上传字段、缺字段和空态由入口状态测试覆盖 | 通过 |
| 单股分析 | AAPL basics/strategy；生成 Naive、保存，生成 Mean，进入比较；验证信号图、Walk-Forward 和 HTML 导出入口 | 通过 |
| 多股入口 | 浏览器从推荐加入 AAPL/NVDA、查看并删除入口、进入双股分析；上传与最少两只校验由入口/页面测试覆盖 | 通过 |
| 多股分析 | basics/strategy、权重、生成组合、30 次组合搜索、模拟/周期收益热图切换、导出入口 | 通过 |
| 模型评估 | 浏览器读取 8 个有效 run，并展示缺 QuantStats / 缺 MLflow 的显式状态；无 run 与缺可选产物分支由 `tests/test_model_evaluation_page.py` 覆盖 | 通过 |
| 报告 | 两个归档版本各保留 10 个 section（8 个课程章节 + `run-instructions` + `submission-packaging`）；浏览器验证中英、提交式搜索、非目录 section 深链接、语言切换保留 section、回到顶部 | 通过 |

## 性能矩阵

原始值均为毫秒；每格保留 3 次样本，括号内为 p50。

| 场景 | 冷 | 热 |
|---|---:|---:|
| `import app` | `736.065 / 724.748 / 737.464`（`736.065`） | N/A |
| 首页壳可见 | 进程冷 `2235 / 2246 / 2167`（`2235`） | `1908 / 2448 / 1924`（`1924`） |
| 首页数据完整 | 进程冷 `3919 / 5931 / 5859`（`5859`） | `1914 / 2453 / 1937`（`1937`） |
| 单股入口壳可见 | context 冷 `2763 / 622 / 4453`（`2763`） | `318 / 3560 / 3480`（`3480`） |
| 报告首章 | context 冷 `7509 / 4339 / 4238`（`4339`） | `4013 / 3982 / 3986`（`3986`） |
| 报告切章 | N/A | `4066 / 4010 / 4036`（`4036`） |
| sidebar 提交参数 | N/A | `676 / 6180 / 1437`（`1437`） |
| 单股结果视图切换 | N/A | `1233 / 1132 / 1111`（`1132`） |
| 多股结果视图切换 | N/A | `4913 / 781 / 1528`（`1528`） |

补充 Python 层 AppTest：首次 `1698.178 ms`，同进程后续 `15.871 ms`。

### 预算解释

- `import app`、报告 DOM 与正文负载通过硬预算。
- 首页已消除“外部 API 完成前整页空白”的功能性问题；进程冷壳层 p50 从修复前与完整数据同时出现的约 `4.2 s` 降到 `2.235 s`。它仍高于 Phase 2 的理想 `1.5 s`，剩余部分主要是本机 Streamlit 客户端/WebSocket 会话成本。
- 报告首章和切章仍受约 `4 s` 的 Streamlit 页面会话成本约束，未达到计划中的 `2.0 s / 1.0 s` 理想值；正文分章带来的 DOM/负载预算已经达成。若必须压到该理想值，需要客户端路由或静态 reader 级别的架构变化，不能由缓存装饰器消除。
- 热交互存在首次图表/会话建立的离群值，表中保留原始样本，没有删除异常点。

## Phase 7 中发现并修复的问题

1. `ui/home.py` 曾把三个首页动态区重新合并到同步线程池中，导致壳层与数据同时出现。现恢复固定 loading/fallback 壳层 + 三个 `st.fragment(parallel=True)`：新闻、推荐股票/K 线、市场镜头。
2. `ui/theme.py` 明确让 parallel fragment 的绝对定位内容以 `home-stage-shell` 为定位上下文；桌面与 390px 移动端均无错位，低动态模式保持稳定。
3. 新增首页 shell-before-fragments 源码合同测试，防止再次把外部请求移回首屏关键路径。
4. `tests/test_full_research_preflight.py` 的 freshness 用例原先会误读仓库级 AAPL cache；现把该用例的数据缓存目录隔离到 `tmp_path`，产品加载逻辑未变。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\measure_app_performance.py --samples 3
.\.venv\Scripts\python.exe -m compileall -q ui\home.py ui\theme.py
```

视觉证据：

- `output/playwright/phase7-home-desktop.png`
- `output/playwright/phase7-home-mobile.png`

## 发布边界

本轮没有获得部署授权，也没有把当前脏工作树上传生产。生产环境仍需在实际发布后重新运行五条公开路由、WebSocket、依赖版本和冷/热计时；该步骤属于发布验收，不影响 Phase 7 本地矩阵已完成的事实。
