---
name: strategy-core-pipeline
description: "Work on the core strategy pipeline in this repository: data loading, indicators, signals, FA/ML filters, backtest, baselines, evaluation, and optimization. Use when a task changes strategy logic, signal columns, evaluation outputs, or core pipeline interfaces from `core/data.py` through `core/backtest.py`."
---

# Strategy Core Pipeline

## Required Reads

1. `AI_CONTEXT.md`
2. `document/interfaces/strategy-pipeline.md`
3. `document/DATA_SCHEMA.md`
4. `document/MODEL_INTERFACES.md` when touching `ModelResult`, baselines, or evaluation

## Preferred Search Paths

- `core/data.py`
- `core/utils.py`
- `core/indicators.py`
- `core/signals.py`
- `core/fa_filter.py`
- `core/ml_filter.py`
- `core/backtest.py`
- `core/baselines.py`
- `core/evaluation.py`
- `core/optimizer.py`

## Do Not Chase

- Do not read frontend style docs for pure pipeline work.
- Do not change `ui/` files unless the task explicitly crosses the UI boundary.
- Do not invent new output keys in core results without updating the matching interface doc.

## Completion Checklist

- Confirm the input schema and required columns.
- Confirm which output columns or result keys changed.
- Identify downstream consumers in workflow or UI before renaming anything.
- Update `document/interfaces/strategy-pipeline.md` if the contract changed.
