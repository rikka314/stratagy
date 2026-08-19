# Post-Gate-2 v1 — W00–W02 Acceptance (2026-08-16)

## Result

W00, W01, and W02 are complete for the US research chain. No long-running
full-run was started, no pending artifact was accepted as evidence, and no
Streamlit workflow changed.

| Window | Status | Evidence |
|---|---|---|
| W00 | complete | Read-only full-run preflight, worktree audit, dependency / disk / data-date inventory. |
| W01 | complete | `full_us_deans_60` snapshot files and aggregate hash reverified; smoke-only Window 3B excluded from the authoritative source lock. |
| W02 | complete | Strict Phase-A materializer exited `0` and produced a ready US baseline. |

## W00 inventory

- `full_us_deans_60.json` retains `freeze_data_snapshot=true`, seed `42`, US
  execution costs of 1 bps commission plus 2 bps slippage, and minimum data
  end date `2026-07-31`.
- The formal preflight exited `2` only because the shared worktree was dirty
  and the output directory already existed. It correctly did not claim a new
  formal run was ready. Dependencies and CPU LightGBM 4.7.0 passed; D: had
  approximately 267 GiB free.
- No `full_cn_a_deans_60` output exists. CN_A remains explicitly
  **full-scale experiment incomplete**.

## W01 source lock

The authoritative US source is the existing completed full run:

| Field | Value |
|---|---|
| Run ID | `full_us_deans_60-20260810T102451Z` |
| Source code version | `1b3c1d3` |
| Seed | `42` |
| Source manifest SHA-256 | `31aadc6d97479bf22c048a8b36e6e830382a1c938d32fedea72f50efeef088d9` |
| Data snapshot SHA-256 | `adb08e44cad749c275bdcad972bcb2898ad6014a587a5dbb1318ccb856bedc16` |
| Snapshot files / bytes | `60` / `16,751,317` |

`model_test.moe_baseline` now validates each manifest-listed frozen CSV's
filename, SHA-256 and size, rejects missing or unmanifested CSVs, and
recomputes the source aggregate hash. The former `deans_window3b_us` output is
a six-symbol smoke run without `data.snapshot_sha256`; it is recorded as
`non_authoritative_smoke` only and is neither source-validated nor included in
the Phase-A source fingerprint. No source manifest was hand-edited to claim it
was ready.

## W02 output

Command:

```powershell
.\.venv\Scripts\python.exe model-test\prepare_moe_baseline.py --config model-test\configs\moe_baseline_us.json
```

It completed in strict mode, without `--allow-pending`.

| Artifact | SHA-256 |
|---|---|
| `data_manifest.json` | `49f9bb9922eaa753178df67c9e7656185484df9606a2b07d3c20d93efed185ad` |
| `baseline_results.csv` | `b940ba0266d59d73154a71a8d640c15a740b41e2468ccc82af1aea8fcb501d33` |
| `baseline_daily_returns.csv` | `6afaa38c7162a4cce862485d767ac82e438b625705866c1cc3217875350bdc71` |
| `train_selection_summary.csv` | `bb22f579b631594a606a11870ec0bc5c9004553963c2aae35a98f6b0a6bb3ce0` |

The Phase-A manifest is `ready`, market `US`, and has source fingerprint
`865875dbf3b95e79fe239ed3cd4bee579a60da04a6c06d10e1f1272be4216b22`.
All three frozen controls are ready: `best_single_expert` (`sm_bayesian`),
`equal_weight_experts`, and `adaptive_router_v1`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_moe_phase_a.py -q
# 5 passed

.\.venv\Scripts\python.exe model-test\prepare_moe_baseline.py --config model-test\configs\moe_baseline_us.json
# exit 0
```

## Handoff

W03 may consume only `model-test/outputs/moe_baseline_us/` while its source
fingerprint continues to match. It must not treat the result as cross-market
evidence and must leave CN_A pending until its own full-scale source exists.
