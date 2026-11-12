# Dean's Award Research Contract

> Frozen at Gate 0: 2026-08-03  
> Owners: Window 0 maintains this contract. Windows 2–4 implement only the
> sections explicitly assigned to them. Any incompatible change requires a
> Window 0 contract revision before merge.

## 1. Canonical market identifiers

| Canonical value | Accepted input aliases | Scope | Status |
|---|---|---|---|
| `US` | `US` | United States equities | Supported |
| `CN_A` | `CN_A`, `CN`, `A` | Mainland China A shares | Supported by data/UI; offline runner support is Gate 1 work |

Inputs are trimmed and compared case-insensitively. Persisted configs, manifests,
CSV output, and recommendation payloads must use only `US` or `CN_A`. An unknown
market is a validation error; it must not silently default to `US`.

## 2. Execution-cost contract

Window 2 will introduce a backward-compatible `MarketExecutionConfig` for
`core.backtest.simulate_strategy`. The default call with no execution config must
remain numerically identical to the pre-Gate-0 backtest.

```python
MarketExecutionConfig(
    market: Literal["US", "CN_A"],
    commission_bps: float,
    slippage_bps: float,
)
```

`commission_bps` and `slippage_bps` apply once for each unit of position change;
they are non-negative. For day *t*, the deducted cost return is:

```text
turnover_t = abs(position_t - position_(t-1))
cost_return_t = turnover_t * (commission_bps + slippage_bps) / 10_000
net_strategy_return_t = gross_strategy_return_t - cost_return_t
```

The position before the first observed day is `0`. Costs are therefore charged
only for opening, closing, or resizing a position—not while a position is held
unchanged. The frozen standard research defaults are:

| Market | Commission | Slippage | Total |
|---|---:|---:|---:|
| `US` | 1 bps | 2 bps | 3 bps |
| `CN_A` | 3 bps | 5 bps | 8 bps |

This is a transparent proportional-cost approximation, not a complete exchange
rule simulator. Taxes, lot-size constraints, price limits, short-sale rules, and
market-impact modelling remain limitations unless explicitly added and versioned
in a later contract revision.

All runs must retain a zero-cost regression mode (`commission_bps=0`,
`slippage_bps=0`) for compatibility testing. The run manifest records the
effective configuration, including zero-cost mode.

### Required backtest result fields

The implementation preserves existing result columns and adds these fields when
an execution config is supplied:

| Field | Meaning |
|---|---|
| `turnover` | Absolute daily position change |
| `transaction_cost` | Daily cost return deducted from gross return |
| `gross_strategy_return` | Return before transaction costs |
| `strategy_return` | Net daily strategy return (existing consumer-facing field) |

Aggregates exposed in model/run summaries are `total_turnover`,
`total_transaction_cost`, `gross_total_return`, and `net_total_return`.

## 3. Research-output contract

Every official US or CN_A run writes the existing `report.json` plus the
following UTF-8 artifacts. Numeric values use JSON numbers / CSV numeric fields;
unavailable values are blank in CSV and `null` in JSON. Dates use ISO-8601
`YYYY-MM-DD`.

### `market_strategy_matrix.csv`

One row per `(market, strategy_id, evaluation_window)` with these columns:

```text
market,strategy_id,strategy_label,evaluation_window,symbol_count,
successful_symbol_count,failed_symbol_count,skipped_symbol_count,
coverage_rate,total_return,annualized_return,sharpe,max_drawdown,
total_turnover,total_transaction_cost,net_total_return,
naive_win_rate,median_excess_return,rolling_rank_median,
rolling_direction_consistency,degraded_run_rate
```

### `market_strategy_recommendations.json`

```json
{
  "schema_version": "1.0",
  "generated_at": "ISO-8601 timestamp",
  "markets": {
    "US": {
      "recommendation": "strategy_id or null",
      "confidence": "high|medium|low|insufficient_evidence",
      "evidence": {},
      "limitations": ["..."]
    }
  }
}
```

Both `US` and `CN_A` keys are required. A market with inadequate evidence uses
`recommendation: null` and `confidence: "insufficient_evidence"`; it is never
silently omitted or assigned a forced winner.

### `news_ablation_summary.csv`

One row per `(market, base_strategy_id, news_weight, lookback_days)` with:

```text
market,base_strategy_id,news_weight,lookback_days,symbol_count,
matched_row_count,coverage_rate,missing_rate,future_leakage_violation_count,
duplicate_news_row_count,fallback_position_match_rate,total_return,
max_drawdown,sharpe,total_turnover,total_transaction_cost,
net_total_return,rolling_direction_consistency,status,skip_reason
```

`fallback_position_match_rate` measures no-news rows whose final position equals
the upstream strategy position; a valid no-news fallback has a rate of `1.0`.

### `data_manifest.json`

```json
{
  "schema_version": "1.0",
  "market": "US|CN_A",
  "run_id": "string",
  "code_version": "git SHA or dirty marker",
  "random_seed": 0,
  "generated_at": "ISO-8601 timestamp",
  "data": {"source": "...", "adjustment": "...", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "universe": {"symbols": [], "selection_rationale": "..."},
  "evaluation": {"train_end": "YYYY-MM-DD", "test_start": "YYYY-MM-DD", "rolling_windows": []},
  "execution": {"commission_bps": 0.0, "slippage_bps": 0.0},
  "search": {"budget": 0},
  "news": {"available_lag_trading_days": 1, "coverage_threshold": 0.0}
}
```

`market_strategy_report.md` cites the run ID, its manifest, the matrix rows used
for each conclusion, and all limitations/skip reasons.

### Window 3B campaign control files

The local full-run manager writes under
`model-test/outputs/_campaigns/<campaign_id>/`:

- `campaign.json`: campaign identity, clean Git commit, config SHA-256 values,
  run sequence, statuses, manager/runner PIDs, timestamps, and terminal error.
- `progress.json`: active config, phase, planned/completed record counts, status
  counts, in-flight/pending batches, and last completed record key.
- `pause.request.json`: cooperative pause request. Its presence stops new batch
  submission; it never kills a worker.
- `campaign.log`: combined detached-manager and runner output.

The runner exit code `75` means a requested pause completed safely. Resuming
requires the original Git commit and unchanged config hashes and relies on the
existing checkpoint key `(symbol, window_id, model_id)`.

## 4. Window ownership, dependencies, and acceptance

| Window | May modify | Must not modify | Gate-0 dependency | Minimum acceptance command |
|---|---|---|---|---|
| 0 | `plan/`, `AI_CONTEXT.md`, `README.md`, `document/interfaces/`, `requirements-dev.txt`, `pytest.ini`, `.gitignore`, release checklist | Window 1–5 owned code | This contract | `.\\.venv\\Scripts\\python.exe -m pytest` |
| 1 | `ui/theme.py`, `ui/home.py`, `ui/single_stock_entry.py`, `ui/multi_stock_entry.py`, `app.py`, `ui/i18n.py`, matching frontend tests | `core/`, `model-test/`, `ui/model_evaluation.py`, shared contracts | Market labels and output names in this contract | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_w8_exports_and_routes.py tests/test_model_evaluation_page.py` |
| 2 | `core/backtest.py`, optional `core/market_rules.py`, matching backtest tests | `ui/`, `model-test/`, shared contracts | Section 2 | `.\\.venv\\Scripts\\python.exe -m pytest tests -k "backtest or market_rules"` |
| 3 | `model-test/model_test/{config,models,universe,runner,execution,summarize,reporting}.py`, `model-test/configs/*deans*.json`, runner tests | `core/backtest.py`, `core/news_factor.py`, `ui/`, shared contracts | Sections 1–3; Window 2/4 implementation before formal run | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_model_test_runner.py` |
| 4 | `core/news_factor.py`, `tests/test_news_factor.py`, standalone news validation/experiment helpers, news schema docs | `model-test/model_test/`, `core/backtest.py`, `ui/`, shared contracts | Sections 1 and 3 | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_news_factor.py` |
| 5 | `ui/model_evaluation.py`, `core/visualization.py`, `ui/export_reports.py`, evaluation/export tests | `ui/theme.py`, `ui/i18n.py`, runner and core-strategy files | Section 3 payloads frozen by Window 3 | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_model_evaluation_page.py` |

The pre-existing uncommitted fix in `core/news_factor.py` is exclusively owned by
Window 4: it restores upstream `target_position` values only for rows without
news. Window 0 must preserve it and must not amend it during Gate 0.
