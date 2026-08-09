# Web Performance Phase 5 验收记录

> 日期：2026-08-09  
> 范围：缩小 CSS 与页面增量  
> 视觉基线：`document/FRONTEND_STYLE_STANDARD.md`

## 结论

Phase 5 已完成。`ui/theme.py` 继续维护一份主题源，但运行时按 selector 编译为 `base / home / entry / analysis / report` 五个 bundle；`app.py` 每条真实路由只发送 `base + 当前页面 bundle`。公开路由、状态 payload、视觉 token、策略与报告内容 contract 均未改变。

## 实施内容

- 新增 `inject_base_styles()`、`inject_home_styles()`、`inject_entry_styles()`、`inject_analysis_styles()`、`inject_report_styles()`。
- 保留 `inject_global_styles()` 作为兼容入口，新 route wrapper 不再调用它。
- CSS 编译器保持原规则顺序，递归拆分 `@media` / `@supports`，共享 selector 可进入多个消费 bundle。
- 删除经源码检索确认无消费者的旧 `.hero-shell`、`.hero-copy*`、`.support-*` selector。
- 移动端首页把舞台最小高度调整为 900px，并下移星图，保证标题、星图、控制按钮和市场镜头不重叠。

## Payload 结果

同一 light theme、同一 Python 字符统计口径：

| 项目 | 字符数 |
|---|---:|
| 完整 CSS 源 | 77,524 |
| `base` | 9,418 |
| `home` | 21,148 |
| `entry` | 23,055 |
| `analysis` | 15,284 |
| `report` | 11,269 |
| 首页 `base + home` | 30,566 |
| 入口 `base + entry` | 32,473 |
| 分析 / 模型评估 `base + analysis` | 24,702 |
| 报告 `base + report` | 20,687 |

首页低于计划的 40k 预算。非报告 bundle 不包含 `.native-report-shell`；报告 bundle 不包含 `market-news-hop` 等首页动画。

## 自动化验证

```text
python -m py_compile ui/theme.py app.py
pytest -q tests/test_web_performance_contracts.py tests/test_final_report_page.py tests/test_model_evaluation_page.py tests/test_entry_page_states.py
45 passed in 19.87s

pytest -q
142 passed in 13.74s
```

新增性能 contract 覆盖：

- 首页 payload 预算
- report / home / entry / analysis selector 隔离
- 五条 route 的 bundle 注入映射
- 兼容入口保留

## 浏览器验证

使用真实 Streamlit 1.60 服务与 Playwright CLI 验证：

- 首页桌面 1440×1000：header、标题、星图、控制按钮、三幕市场镜头正常。
- 首页移动端 390×844：实测 `identity.bottom=298.1`、`stock cloud=307.9–483.9`、`controls=483.9–515.9`、`market lens.top=526.1`，区块无重叠。
- 单股入口：浏览器 style block 为约 9.4k base + 23.0k entry；split layout、推荐行与按钮对齐正常。
- 模型评估：约 9.4k base + 15.3k analysis；研究浏览与摘要面板正常。
- 报告：约 9.4k base + 11.2k report；原生 reader 存在，未加载首页动画。

QA 截图位于 `output/playwright/phase5-*.png`，属于本地验收产物，不作为运行时依赖。
