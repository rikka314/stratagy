# Web Performance Phase 3 Acceptance - 2026-08-08

## Scope

Phase 3 replaces whole-report native rendering with a cached, structured reader that renders one required section at a time. It preserves the archived report files as the only content source, all original markup, the `/strategy/final-report` route, bilingual state, native DOM rendering, and the no-iframe contract.

## Implementation

- `ui.final_report.load_embeddable_report(path, mtime_ns)` now parses and caches a structured reader keyed by report path and source modification time.
- Reader sections retain full original `<section>` markup. It indexes all 10 sections, including `run-instructions` and `submission-packaging`, and marks the eight `section-*` sections as the primary report chapters.
- Default report rendering now emits the intro, archived TOC, and one selected section instead of the entire report body.
- `final_report_active_section` plus `?section=<safe-id>` selects the loaded section. Invalid section IDs safely fall back to the first chapter. TOC and wide-screen rail links load the owning section while preserving the original fragment anchor.
- Search is a submit-only `st.form`. Draft typing does not filter the report; submit returns only matching chapter metadata and snippets. Each result links to the complete selected section. A clear action restores normal section rendering.
- Report search results and active rail styles were added in `ui/theme.py` without changing the shared site palette or global CSS loading strategy.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_final_report_page.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_final_report_page.py tests/test_i18n_language_state.py tests/test_w8_exports_and_routes.py
.\.venv\Scripts\python.exe -m compileall -q ui/final_report.py ui/theme.py tests/test_final_report_page.py
```

## Results

- Report Phase 3 suite: `12 passed`.
- Report, language-state, and route regression suite: `18 passed`.
- Changed Python source and tests compile successfully.
- Tests cover reader structure, original HTML retention, legacy search compatibility, metadata-only structured search, section query fallback, submit-only search behavior, TOC/rail deep links, and cache invalidation by `mtime_ns`.

## Remaining Final-Matrix Work

- Browser-level cold/hot timing and DOM-node measurements remain Phase 7 work; they were not fabricated as part of this code-only acceptance.
- Run full `pytest -q`, browser route checks, and performance measurements before the final release matrix is closed.
