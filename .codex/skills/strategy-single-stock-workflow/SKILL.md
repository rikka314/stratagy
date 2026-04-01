---
name: strategy-single-stock-workflow
description: "Work on the single-stock workflow, artifact lifecycle, stage cache, lineage, and single-stock result board in this repository. Use when a task touches `ui/single_stock_workflow.py`, `current_artifact`, `saved_artifacts`, stage caching, request signatures, or single-stock strategy result wiring."
---

# Strategy Single Stock Workflow

## Required Reads

1. `AI_CONTEXT.md`
2. `document/interfaces/single-stock-workflow.md`
3. `document/interfaces/frontend-contracts.md` when the task also changes page rendering

## Preferred Search Paths

- `ui/single_stock_workflow.py`
- `ui/single_stock.py`
- `document/interfaces/single-stock-workflow.md`
- `document/interfaces/strategy-pipeline.md` when a workflow stage changes core outputs

## Do Not Chase

- Do not read multi-stock or deploy docs unless the task explicitly crosses those domains.
- Do not bypass `run_strategy_pipeline()` by rebuilding a second workflow path inside the page.
- Do not change artifact or workspace semantics without updating the interface doc.

## Completion Checklist

- Confirm `StrategyRequest`, `StageResult`, and `StrategyArtifact` semantics.
- Confirm workspace reset and cache invalidation boundaries.
- Confirm downstream selectors, comparison mode, and export still read the right artifact.
- Update `document/interfaces/single-stock-workflow.md` if lifecycle rules changed.
