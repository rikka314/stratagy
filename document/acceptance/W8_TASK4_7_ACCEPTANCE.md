# W8 任务 4~7 验收记录

> 更新日期：2026-04-01
> 范围：`plan/newplan.md` 第 8 周任务 4~7

## 任务 4：HTML 导出适配新结构

- 状态：已完成
- 落地方式：
  - 新增共享 builder：`ui/export_reports.py`
  - 单股页导出入口继续保留在 `ui/single_stock.py`
  - 多股页导出入口继续保留在 `ui/multi_stock.py`
- 验收点：
  - 导出页改为 W6-W8 统一暖白站点语法，不再使用旧版蓝灰卡片皮肤
  - 单股导出保留：概览、模型摘要表、K 线/指标/评分/净值/信号图
  - 多股导出保留：概览、详细对比表、基础信息图组、组合 KPI、个股表现表
  - 导出页同步当前 `zh/en` 与 `light/dark`

## 任务 5：桌面与移动端响应式检查

- 状态：已完成
- 验收依据：
  - 导出页共享 CSS 内置 `980px` 与 `680px` 两档断点
  - 指标卡、概览区、表格区、图表区在窄屏下统一切到单列
  - 表格保留横向滚动，不挤压字段
  - Plotly 图表统一启用 `responsive: true`
- 自动化覆盖：
  - `tests/test_w8_exports_and_routes.py`

## 任务 6：路由刷新 / 直接访问 / 复制链接验证

- 状态：已完成
- 验收依据：
  - `.streamlit/config.toml` 继续固定 `baseUrlPath = "strategy"`
  - `ui.theme.route_href()` 继续输出：
    - `/strategy`
    - `/strategy/stock-analysis`
    - `/strategy/stocks-analysis`
  - `app.py` 继续显式声明 `stock-analysis` 与 `stocks-analysis` 真实路由
- 自动化覆盖：
  - `tests/test_w8_exports_and_routes.py::test_public_route_contract_remains_on_strategy_base_path`

## 任务 7：单股 / 多股 / 上传 / 推荐股票 / 策略生成 / 策略比对 / 导出完整回归

- 状态：已完成（本轮针对第 8 周 4~7 范围做回归）
- 本轮回归重点：
  - 单股 / 多股导出入口仍使用原页面入口与下载按钮
  - 导出 builder 不改动单股 workflow、artifact、multi-stock workspace 契约
  - 路由基路径与真实 URL 契约未回退
- 自动化覆盖：
  - 单股导出新结构：`tests/test_w8_exports_and_routes.py::test_single_stock_export_html_uses_w8_site_shell`
  - 多股导出新结构：`tests/test_w8_exports_and_routes.py::test_multi_stock_export_html_contains_detail_table_and_strategy_surface`
  - 路由契约：`tests/test_w8_exports_and_routes.py::test_public_route_contract_remains_on_strategy_base_path`
  - 统一回归入口：`pytest -q`（通过新增 `pytest.ini` 固定只收集 `tests/`）

## 当前限制

- 实时市场快照、推荐股票和在线拉数仍依赖 AkShare / 网络环境；本次回归主要锁定导出结构、响应式和路由契约，不覆盖外部数据源稳定性。
