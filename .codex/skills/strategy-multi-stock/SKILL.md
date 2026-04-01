---
name: strategy-multi-stock
description: "Work on the multi-stock analysis page, portfolio simulation, market context, and multi-stock result surfaces in this repository. Use when a task touches `ui/multi_stock.py`, `core/portfolio.py`, `core/market_context.py`, portfolio result dictionaries, or multi-stock export behavior."
---

# Strategy Multi Stock

## Required Reads

1. `AI_CONTEXT.md`
2. `document/interfaces/multi-stock-portfolio.md`
3. `document/interfaces/frontend-contracts.md` when the task changes page layout or shared chart wiring

## Preferred Search Paths

- `ui/multi_stock.py`
- `core/portfolio.py`
- `core/market_context.py`
- `core/visualization.py`
- `document/interfaces/multi-stock-portfolio.md`

## Do Not Chase

- Do not reuse single-stock artifact/state rules for multi-stock work.
- Do not read deploy docs unless the task changes public routes or deployment behavior.
- Do not change `portfolio_result` or optimization result keys without updating the interface doc and export path.

## Completion Checklist

- Confirm route state and workspace signature behavior.
- Confirm the `portfolio_result` dictionary still satisfies the result board and export path.
- Confirm market snapshot and recommended-stock sources still match the page contract.
- Update `document/interfaces/multi-stock-portfolio.md` if returned keys or workspace rules changed.
