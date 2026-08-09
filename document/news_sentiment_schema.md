# News Sentiment Daily Schema

Window 4 owns this schema and the accompanying validation API. It describes the
daily factor CSV consumed by `core.news_factor`; it is deliberately separate
from the frozen cross-window research contract.

## Required columns

| Column | Type | Meaning |
|---|---|---|
| `symbol` | string | `US`: uppercase ticker; `CN_A`: six-digit code. `SZ000001` and `000001.SZ` normalize to `000001`. |
| `date` | ISO date | Information date: the date on which the daily factor became known. It is never used as a same-day trade date. |
| `news_count` | non-negative number | Articles contributing to that symbol-day factor. |
| `sentiment_ewm_3` | number | Three-day exponentially weighted sentiment factor. Expected range is `[-1, 1]`; validation reports, but does not silently clip, outliers. |
| `confidence_mean` | number | Mean source/model confidence. Expected range is `[0, 1]`; validation reports outliers. |

Optional diagnostic fields retained by fusion include `negative_tail_ratio`,
`sentiment_mean`, and `sentiment_sum`. An optional `market` column accepts
`US`, `CN_A`, `CN`, or `A`; persisted values use only `US` and `CN_A`.
One CSV may contain both markets. Loading with an explicit `market` filters to
that canonical market after validation. The loader forces `symbol` to string so
a CSV value such as `000001` keeps its leading zeros; direct numeric input such
as `1` is also normalized to `000001` when the market is `CN_A`.

Minimal example:

```csv
market,symbol,date,news_count,sentiment_ewm_3,confidence_mean
US,AAPL,2026-05-18,4,0.31,0.86
CN_A,000001,2026-05-18,3,-0.12,0.79
```

## Validation and time alignment

`validate_news_factor_frame()` checks missing/invalid dates, blank symbols,
duplicate `(market, symbol, date)` rows, missing numeric values, negative
`news_count`, sentiment/confidence outliers, unknown market values, and
information dates later than the validation `as_of_date`. Unknown market values
are errors. Other quality problems are counted rather than silently clipped.
Duplicate rows are collapsed deterministically to the final CSV row and their
count is retained in metadata. Stable diagnostic keys include:

- `invalid_date_count`, `empty_symbol_count`, `duplicate_news_row_count`
- `missing_sentiment_count`, `missing_confidence_count`, `missing_news_count_count`
- `sentiment_outlier_count`, `confidence_outlier_count`, `negative_news_count_count`
- `future_information_date_count`, `validation_as_of_date`, `markets`

`apply_news_fusion()` maps each information date to the signal calendar with
`news_available_lag_trading_days=1` by default. The first eligible signal row is
one trading day after the first signal day on or after the information date.
It records `news_information_date` and `news_effective_date` per matched row,
and rejects a result if an information date is not strictly earlier than its
trade date. Multi-symbol input uses each symbol's own observed trading calendar;
rolling z-scores, percentiles, and refreshed trade signals are also isolated by
symbol.

With no matched news, or with `news_weight=0`, the upstream `target_position`
is retained. This makes missing coverage visible in metadata while keeping the
technical strategy intact.

## Stable experiment API

`run_news_ablation()` accepts one already-generated upstream signal frame and
runs a fixed `weights × lookbacks` grid against that exact frame. It writes the
UTF-8 `news_ablation_summary.csv` columns frozen for the Dean's Award work:
coverage/missing rates, duplicate and leakage counts, fallback match rate, and
performance metrics. An optional `evaluate_fn` can inject the Window 3/2
backtest metrics without importing or changing their modules.

Stable parameters added for the research handoff are:

- `market`: canonical `US` or `CN_A` (aliases normalize before persistence)
- `weights`, `lookbacks`: the fixed ablation grid
- `news_available_lag_trading_days`: at least `1`; default `1`
- `coverage_threshold`: `[0, 1]`; rows below it are marked `skipped`
- `evaluate_fn(fused_frame)`: optional callback returning the performance keys
  in the frozen cross-window schema

A missing CSV produces one `skipped` row per requested grid point with an
explicit `skip_reason`. A readable CSV with zero matched rows still calculates
fallback metrics, but its rows are marked `skipped: no matched news rows`; it
must not be interpreted as evidence for or against the news factor.
