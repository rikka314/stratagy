---
name: strategy-interface-alignment
description: "Find interfaces, call chains, inputs, outputs, and ownership boundaries in this repository. Use when the task asks where an interface lives, which function owns a feature, what data flows between modules, what state key drives a page, or which skill should handle the next step."
---

# Strategy Interface Alignment

## Required Reads

1. `AI_CONTEXT.md`
2. `document/MODULE_INTERFACES.md`
3. Exactly one matching domain doc from `document/interfaces/`

## Preferred Search Paths

- Frontend shell and page wiring:
  - `app.py`
  - `ui/sidebar.py`
  - `ui/theme.py`
  - `document/interfaces/frontend-contracts.md`
- Single-stock workflow:
  - `ui/single_stock_workflow.py`
  - `ui/single_stock.py`
  - `document/interfaces/single-stock-workflow.md`
- Core strategy pipeline:
  - `core/data.py`
  - `core/indicators.py`
  - `core/signals.py`
  - `core/backtest.py`
  - `document/interfaces/strategy-pipeline.md`
- Multi-stock and portfolio:
  - `ui/multi_stock.py`
  - `core/portfolio.py`
  - `core/market_context.py`
  - `document/interfaces/multi-stock-portfolio.md`
- Deploy/runtime:
  - `deploy/`
  - `.streamlit/config.toml`
  - `document/interfaces/deploy-runtime.md`

## Output Format

When answering an interface-discovery task, use this order:

1. `入口文件`
2. `关键函数 / 状态键`
3. `输入`
4. `输出`
5. `依赖`
6. `影响范围`
7. `建议转交 skill`

## Do Not Chase

- Do not read `document/archive/` or week-plan files for normal interface discovery.
- Do not load `document/FRONTEND_STYLE_STANDARD.md` unless the question is visual or page-structure specific.
- Do not implement code while still figuring out ownership boundaries unless the user explicitly wants the fix now.

## Completion Checklist

- Name the exact file and function or state key.
- State the immediate upstream and downstream.
- Name the smallest next skill that can finish the task.
- Stop once the interface path is decision-complete; do not keep scanning the whole repo.
