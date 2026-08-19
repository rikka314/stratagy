# Post-Gate-2 Model Upgrade — CN_A W08–W10 Acceptance (2026-08-17)

## Result

CN_A W08–W10 complete as a market-specific, source-locked research chain.
The chain remains research-only: no Phase C–F artifact is imported by
Streamlit, no default strategy changed, and W11/W12 were not started.

## W08 full-scale source

- Isolated worktree: `D:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy_w8_cn_a_20260817`
- Campaign: `post-gate2-w08-cn-a-20260817`
- Campaign status: `completed`; 4,740 records = 4,474 success, 240 `SKIPPED`, 26 `degraded`
- Scope: 60 CN_A symbols, 1,260-day main window, 4 rolling windows, 240-search budget
- Frozen snapshot: 60 CSV files, 23,520,695 bytes
- `data_snapshot` SHA-256: `961c865b76b7338a8d4c30b1c786e52abb12c86cf4001b10b236e718eab92058`
- source `data_manifest.json` SHA-256: `f46e4d677bbd051e91b27fd07625fa87f3b98ea9af45b28d67d4ef066e1d1aa`

The first campaign attempt exposed an MLflow 3.15 file-store compatibility
failure. A direct replay with `MLFLOW_ALLOW_FILE_STORE=true` completed without
changing source config, commit, snapshot, task records, costs, or result files;
the recovery is recorded in campaign metadata. The complete output was copied
to the main workspace only after manifest/snapshot equality was checked.

## W09–W10 manifests

Every row below was checked for `status=ready`, `market=CN_A`, declared-file
existence, SHA-256 and (when declared) size. Phase-A was independently
recomputed from the frozen source and matched its stored manifest byte-for-byte
when using its recorded `generated_at`.

| Stage | Output | Manifest SHA-256 | Declared artifacts |
|---|---|---|---:|
| W09 / Phase A | `model-test/outputs/moe_baseline_cn_a/` | `a9bf77abf4d715776941f33adc41d3d6815d6826dcc030f16955709e5bab423c` | source lock + baseline outputs |
| W09 / Phase B | `model-test/outputs/moe_baseline_cn_a/` | `0161132c1498426aee311d453a8bac8d449eeee353be9a6bb9dd6f953e89c9bb` | 3 |
| W10 / Phase C | `model-test/outputs/moe_v1_cn_a/` | `06f7c3a7b9ebbdc8f3abcf0c9add8dfc70f6503e3884151578a20b6587203067` | 5 |
| W10 / Phase D | `model-test/outputs/moe_v2_cn_a/` | `c85d67e86323b4b5850e1527c3f50144d14cc2e5207ae05d76ae893282025d42` | 8 |
| W10 / Phase E | `model-test/outputs/moe_online_cn_a/` | `63b8061b0ad8c69ec730f5807ff35dfb412bbfc2086cf5f8dbbd12f626b311e3` | 5 |
| W10 / Phase F | `model-test/outputs/moe_bandit_cn_a/` | `ecc72154f79414bf4469612843006829ee1e65345218fcfff835f4e0c9d8174c` | 7 |

Notable artifact hashes:

- Phase B `expert_day_panel.parquet`: `34c562c182882b3e7712120d5375c4eafc8bfc26c3b2b0337f07ccfaaf630089`
- Phase C `moe_daily_weights.parquet`: `65a95ed0f84b187e47b1567de470850cbb1998a56ca3696e1ac33afde79dfe2a`
- Phase D `moe_v2_daily_weights.parquet`: `b6be8d022eaf4ab5afe07d6f41ed6e87919f018d234644e3f86fb2a2d11dd578`
- Phase E `moe_online_weights.parquet`: `0bb1a1cc0bb0fed86872a2ca1e4fb5520c87cadf47c37b0b99ea628d812d146f`
- Phase F `moe_bandit_decisions.parquet`: `bb7e5d205c6d33f8ca3bda273317cd2ac634bf7f0a7305f839b5e08e5ca7e6b7`

## Contract checks and conclusions

- All labels and comparisons use already-net `strategy_return` with
  `source_net_no_recharge`; no downstream stage recharged source execution
  costs. Phase-F `incremental_action_switch_cost_bps` is separately disclosed
  and remains `0` pending a measured deployment-cost model.
- Phase B emitted 181,440 rows and 3 purged walk-forward splits with 20-day
  purge, 20-day embargo, and 40-day validation/test partitions. CN_A state
  features are trailing-derived and point-in-time.
- `adaptive_router_v1` is explicitly `known_unavailable` for CN_A in Phase A–F;
  no US SPY artifact was substituted. Cash remains available in later phases.
- Phase C–E comparisons are mixed across the three test splits. Phase D has
  auditable uncertainty/OOD fallbacks and risk controls; Phase E updates only
  after complete feedback. Phase F uses selected-action-only feedback with
  same-date batch updates; the mixed returns and high action-switch rates do
  not establish stable improvement over Hedge/EG. These are evidence rows, not
  a promotion decision.
- W08 `SKIPPED`/`degraded` rows are preserved and reported; regime-family
  skips explain the explicit CN_A adaptive-router unavailability rather than
  being zero-filled.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_moe_phase_c.py tests\test_moe_phase_d.py tests\test_moe_phase_e.py tests\test_moe_phase_f.py -q
# 17 passed in 6.02s
```

W11 remains the next window for US/CN_A admission comparison. Until W11 passes
the frozen thresholds, all CN_A Phase C–F outputs stay research-only and the
Streamlit default path remains unchanged.
