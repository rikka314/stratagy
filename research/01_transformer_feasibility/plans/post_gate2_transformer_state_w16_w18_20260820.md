# Post-Gate-2 Transformer State W16–W18 Acceptance

Date: 2026-08-20  
Market: US  
Decision: **W16–W18 engineering accepted; W20 not admitted**

## Scope and outcome

This window completed the US Transformer-state v2 retrieval, five-day
execution, and evidence-sealing chain without changing the existing admission,
full-run returns, default strategy, or Streamlit routes.

The formal run completed successfully:

```powershell
.\.venv\Scripts\python.exe model-test\run_transformer_state.py `
  --config model-test\configs\transformer_state_us.json `
  --stage all
```

W13 through W18 all ended with `status=ready`. W16 and W17 are fully
reconstructable, and W18 independently verified their lineage and complete
evidence matrices.

## Frozen source evidence

- Frozen expert exact-daily artifacts verified: `60 symbols × 7 experts = 420`.
- Adaptive exact-daily artifacts verified: `60`.
- Source execution turnover proof maximum error: `1.665e-16`.
- Admission source outputs overwritten: `false`.
- Frozen full-run returns modified: `false`.
- Phase-A manifest SHA-256:
  `81acdbb2906f32bed36fe903a55043ea584f2315065cbc14ec2a97d68bde0b87`.
- Phase-B manifest SHA-256:
  `9643d21584e5767ccb2564db33e5932ebb2a1b3169ea793c2758c8c93a4a4297`.
- Phase-B panel SHA-256:
  `1ca4e10212690622883b24022e5b641bea4f7972d02a3dac79b0991f6ab78815`.
- Data snapshot aggregate SHA-256:
  `adb08e44cad749c275bdcad972bcb2898ad6014a587a5dbb1318ccb856bedc16`.

## Runtime and code lock

- Optional research runtime: `torch==2.13.0+cpu`.
- Production dependencies remain unchanged; the research dependency is isolated
  in `requirements-research.txt`.
- Frozen code-lock aggregate SHA-256:
  `b07e97aa8bd6433a3fea8fe43cb424751e76b99dbffb9a5d92e211dc45753f23`.

## Manifest chain

| Phase | Manifest | SHA-256 | Status |
|---|---|---|---|
| W13 | `transformer_state_source_manifest.json` | `54069e783ac4efe594d55a659ac387dbe7cd0a397652b70e1b81afcb8252a6fd` | ready |
| W14 | `state_panel_manifest.json` | `bc791ff9a0fec54d049d6514ad6e890ac9f1bd72d146c05830af3e72632802b0` | ready |
| W15 | `transformer_state_model_manifest.json` | `305de52fb65c97d71c30c799447edcd5e639c79352f1cd77ecb640c3131ce17d` | ready |
| W16 | `state_retrieval_manifest.json` | `af96a29849d7b0288735f1393e608f6be6d77c5eda243c1f8d2a9476e5e3fceb` | ready |
| W17 | `state_execution_manifest.json` | `c11ae604713c880e2640ce80f6841d7eb05c3600b09192af49596af5600507ed` | ready |
| W18 | `transformer_state_evidence_manifest.json` | `803d05f5e0299dd21a258a32b00ebbdcd0cff2fe08083d11234f0b2f0395b700` | ready |

All referenced W14/W16/W17 artifacts and all four W15 fold manifests,
encoders, schemas, and metrics were rehashed from disk. Paths are contained
inside the expected output/fold directories.

## W16 retrieval evidence

| Artifact | Shape |
|---|---:|
| `state_memory_bank.parquet` | `6,989 × 15` |
| `state_match_decisions.parquet` | `11,520 × 44` |

- Four folds each contain 960 test queries and three independent threshold
  decisions per query.
- Memory rows are split-train-only with complete finite labels and normalized
  embeddings.
- Every retrieved neighbor is strictly earlier than its query date.
- Query-local expert availability, invalid embedding, schema/dimension drift,
  selected-expert unavailability, full-run-best fallback, and final Cash
  fallback are fail-closed and audited.

## W17 execution evidence

| Artifact | Shape |
|---|---:|
| `state_execution_daily.parquet` | `57,600 × 51` |
| `state_execution_summary.csv` | `5,760 × 29` |
| `state_execution_skipped_decisions.csv` | `34,560 × 7` |

- Executed windows: `11,520`; every window contains exactly holding days 1–5.
- The decision-time target becomes effective on `t+1`; same-symbol windows do
  not overlap.
- The jump guard observes the close and changes risk state only on the next
  executable day.
- Source-net expert returns are consumed without a second cost charge.
- Operational numeric fields are finite; execution turnover reconstructs from
  target-position deltas.
- The persisted summary reconstructs exactly from the daily audit.

## Verification

```text
Targeted Transformer/exact-replay tests: 77 passed, 2 warnings
Full repository tests:                    310 passed, 2 warnings
compileall:                               passed
git diff --check:                         passed (line-ending warnings only)
Independent Python/code/artifact review: APPROVE; 0 CRITICAL/HIGH findings
```

The two test warnings are PyTorch nested-tensor notices caused by
`norm_first=True`; they do not change results.

## Research decision

The preregistered primary is
`state_match_balanced + full_run_best_guard`. Its matched coverage is:

| Fold | Matched coverage |
|---|---:|
| `wf_01` | 0.0% |
| `wf_02` | 0.0% |
| `wf_03` | 0.0% |
| `wf_04` | 0.0% |
| Median | 0.0% |

The frozen minimum is 30%. Therefore this result is an engineering-complete
negative study: W16–W18 are accepted, but W20 is not admitted. The evidence
must not be described as Transformer effectiveness, and the threshold, window,
cost, or test period must not be changed post hoc to manufacture admission.
W19 CN_A remains a separate pending research window and is outside this
acceptance scope.

`model-test/outputs/` is Git-ignored. The local W18 evidence manifest and this
tracked acceptance document together provide the handoff pointer; regenerating
the local artifacts requires the frozen source inputs and optional research
runtime above.
