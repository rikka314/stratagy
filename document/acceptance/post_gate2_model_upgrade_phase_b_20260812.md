# Post-Gate-2 Model Upgrade — Phase B Acceptance (2026-08-12)

## Result

Phase B is implemented as a research-only `model-test` materializer:

- `model_test.expert_panel` reads the frozen Phase-A source lock and main-window
  expert artifacts without importing Streamlit or the online workflow.
- The source runner now exports a narrow `daily.csv` containing positions,
  turnover, execution costs and gross/net daily returns for point-in-time audit.
- `expert_day_panel.parquet` is keyed by `date / symbol / market / expert_id`;
  it carries trailing expert, market, optional raw-price and peer-correlation
  features plus source run/model/artifact lineage.
- `future_utility` uses the next 20 complete trading days and the canonical
  already-net `strategy_return`; no second transaction-cost deduction occurs.
- Purged expanding walk-forward splits remove one label horizon and add a
  separate embargo of at least one primary horizon before validation/test.
- Missing/failed experts and the unsupported CN_A adaptive router are explicit
  `expert_status=unavailable` rows with reasons. They are never zero-filled or
  replaced by another strategy.
- Optional news factors use a strict prior-trading-day (`news_*_lag1`) join.

## Outputs

Each ready market output directory contains:

- `expert_day_panel.parquet`
- `expert_panel_walk_forward_splits.csv`
- `expert_panel_manifest.json`
- `expert_panel_quality.json`
- `expert_panel_quality.md`

Run independently for each market:

```bash
python model-test/prepare_expert_panel.py \
  --config model-test/configs/moe_baseline_us.json
python model-test/prepare_expert_panel.py \
  --config model-test/configs/moe_baseline_cn_a.json
```

Strict mode revalidates both Window 3B and full-run source manifests. When the
ignored frozen source outputs are absent, it refuses to fabricate a panel;
`--allow-pending` writes an auditable pending manifest instead.

## Automated verification

| Check | Result |
|---|---|
| Phase-B utility, leakage, purged split and insufficient-history tests | `4 passed` |
| Phase-A tests after daily export change | `4 passed` |
| Synthetic 5-expert source fixture: panel, unavailable router, lineage, labels and parquet round-trip | passed locally |
| News prior-day alignment smoke check | passed locally |
| Streamlit workflow integration | intentionally unchanged |

The repository checkout does not contain `model-test/outputs/` because research
outputs are ignored. Therefore the two production commands above remain source
readiness checks until the frozen Window 3B/full-run directories are restored.
