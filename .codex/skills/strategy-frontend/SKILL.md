---
name: strategy-frontend
description: "Apply the W6-W8 shared frontend system for strategy routes, UI pages, charts, and export surfaces in this repository."
---

# Strategy Frontend

Use this skill when the task touches frontend-facing work in this repository, especially:

- `app.py`
- `ui/`
- `core/visualization.py`
- exported HTML structure
- frontend documentation or shared theme files

## Required Reads

Read these before planning or editing:

1. `AI_CONTEXT.md`
2. `document/FRONTEND_STYLE_STANDARD.md`

If `document/UI_DESIGN_GUIDE.md` conflicts with the new standard, prefer `document/FRONTEND_STYLE_STANDARD.md` for W6-W8 work.

## Required Interface Reads

Read `document/interfaces/frontend-contracts.md` for frontend-facing contracts before tracing code.

Add one adjacent interface doc only when the task crosses that boundary:

- `document/interfaces/single-stock-workflow.md` for artifact, lineage, stage cache, or single-stock result-board wiring
- `document/interfaces/multi-stock-portfolio.md` for multi-stock result surfaces, market context, or portfolio result wiring
- `document/interfaces/strategy-pipeline.md` for core signal/backtest outputs that surface directly in UI

## Source Of Truth

The approved visual direction is whatever is currently frozen in `document/FRONTEND_STYLE_STANDARD.md`.

That means:

- warm-white / rice-white background
- no full-page grid texture
- light site header instead of boxed navigation
- brand-left plus pill-style route controls on the right
- left narrative + right showcase split layout
- one main action card plus one main showcase board
- white floating sheets and lightweight row lists
- low border density, strong spacing rhythm, restrained shadow
- no underline-driven link states
- large shared HTML must use the shared `render_html()` path, with `st.html()` preferred
- showcase modules must be stably arranged, not stacked by absolute-position overlap
- row-list text blocks and action buttons must stay vertically aligned

Do not reintroduce the earlier blue-gray paper-card dashboard language unless the user explicitly asks for it.

## Working Rules

- Reuse semantic tokens before adding page-local CSS values.
- Reuse `ui/theme.py` before adding page-local wrappers or CSS.
- Reuse or create shared wrappers/components before duplicating layout patterns.
- Route large static HTML through `render_html()` instead of page-local markdown hacks.
- Keep charts theme-synced with the page surface and text colors.
- Keep all new labels, buttons, titles, and export headings ready for `zh/en`.
- Keep all new surfaces ready for light/dark token switching.
- Keep `core/` strategy and workflow contracts stable unless the task explicitly requires backend changes.
- Prefer structural cleanup over decorative polish.

## Page Rules

### Home

- Use a product-site hero with strong left-side narrative.
- Keep route choices obvious with two primary actions.
- Use one large right-side showcase board with a stable internal cluster plus main sheet.
- Do not build the showcase out of overlapping float cards.

### Entry Pages

- Use a clear left action card and right showcase board on desktop.
- Search, upload, and recommended stocks are the three allowed entry paths.
- Market switching must update the right-side context as a single system.
- Recommended stocks must be rendered as lightweight row lists inside one white sheet.
- Row-list text and right-side action buttons must be vertically centered.

### Analysis Pages

- Use top context, then section navigation, then paper-surface content.
- Avoid endless vertical stacks when tabs, section nav, or segmented controls fit better.
- Keep text summary blocks and charts complementary; neither should fully replace the other.

## Chart Rules

- No Plotly default theme leakage.
- Respect the fixed structures frozen in the style standard:
  - single-stock K-line: main chart + indicator mini-chart + range control
  - single-stock strategy: equity + drawdown + monthly heatmap
  - multi-stock info: summary metrics + detail table
  - multi-stock strategy: portfolio KPI + stock contribution table
- Use red/green market colors only for price-direction semantics, not for whole-page theming.

## State Rules

Every new UI block must define:

- loading state
- empty state
- error/fallback state
- missing-field fallback (`暂无数据` / `N/A`)

Do not let a missing upstream field break an entire page section.

## Do Not Chase

- Do not read deploy/runtime docs unless the task changes public routes, base path, or server behavior.
- Do not dive into core algorithm internals when `document/interfaces/frontend-contracts.md` already answers the page contract.
- Do not load archived feature notes or week plans for normal frontend implementation.
- If the contract is unclear after reading frontend-facing docs, hand interface discovery to `strategy-interface-alignment` instead of re-scanning the whole repository.

## Avoid

- Streamlit default blue buttons as the final visual
- full-page grid backgrounds or cold blue-gray paper-card language
- boxed heavy nav bars or underline-based active states
- scattered hardcoded colors, radii, spacing, or shadows
- introducing a second visual language for one page
- strong animations, bounce effects, or decorative motion that competes with data
- burying key actions at the end of long pages
- turning recommended stocks back into stacked cards or oversized buttons
- overlapping showcase cards
- large HTML blocks rendered through `st.markdown(..., unsafe_allow_html=True)` as the primary path
- row-list buttons drifting out of vertical alignment with their text

## Completion Checklist

Before finishing frontend work, confirm:

- the change follows `document/FRONTEND_STYLE_STANDARD.md`
- desktop and mobile layouts still work
- header still reads as a light website nav instead of a dashboard shell
- showcase modules are stable and non-overlapping
- large shared HTML is rendering as real HTML, not literal tag text
- row-list text and buttons stay vertically aligned
- copy is ready for bilingual wiring
- light/dark token hooks are preserved
- charts, cards, tables, and buttons still look like one system
