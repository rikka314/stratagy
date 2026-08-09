# Dean's Award Window 4 Acceptance

> Completed: 2026-08-09  
> Scope: news sentiment schema, validation, leakage-safe alignment, fallback,
> and standalone ablation API. No `model-test/model_test/*`, `core/backtest.py`,
> or `ui/*` files were changed by this window.

## Completion matrix

| Item | Result |
|---|---|
| 4.1 schema and normalization | `document/news_sentiment_schema.md`; canonical `US/CN_A`; A-share leading zeros preserved |
| 4.2 data-quality checks | Coverage/missing, duplicates, invalid/future dates, missing numeric values, negative counts, and outliers are auditable |
| 4.3 fallback cases | No matched news and zero weight preserve upstream positions; missing files become explicit skipped ablation rows |
| 4.4 leakage prevention | Configurable lag is at least one trading day; information/effective dates are recorded and validated |
| 4.5 ablation | `run_news_ablation()` writes the frozen `news_ablation_summary.csv` grid and accepts a Window 2/3 evaluator callback |
| 4.6 handoff | Stable parameters, diagnostics, output fields, and skipped semantics are documented without modifying the runner |

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_news_factor.py -q
```

Result: `16 passed`.

Full repository regression: `142 passed`.

The tests cover US/CN_A normalization, mixed-market input, leading-zero
preservation, duplicate/outlier/future-date diagnostics, custom trading-day
lag, missing/zero/extreme coverage fallback, per-symbol calendar isolation,
missing files, and the frozen ablation output columns.

## Local ablation diagnostic

The local diagnostic output is:

```text
output/deans_window4_local_20260809/news_ablation_summary.csv
```

It uses the same AAPL technical signal frame for all `4 weights × 2 lookbacks`.
The local AAPL price cache ends on 2026-02-03, while the available FinGPT sample
contains news only from 2026-05-18 through 2026-05-20. Therefore all eight rows
correctly report zero coverage, `fallback_position_match_rate=1.0`, and
`status=skipped` with `skip_reason=no matched news rows`. This file validates
fallback and output behavior only; it is not research evidence. Window 3 must
rerun the same API with overlapping price/news dates for the formal comparison.
