# Claude Code task — Phase 0 only

You are the implementation agent for **Phase 0 only** of the approved web-performance plan. Work in this repository:

`D:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy`

Before editing, read and follow:

1. `D:\Learn\20_Projects\AGENTS.md`
2. `AGENTS.md`
3. `AI_CONTEXT.md`
4. `plan\web_performance_optimization_20260807.md` — especially Phase 0 and its acceptance criteria

## Scope

Implement only Phase 0: reproducible performance telemetry and baseline gates. Do not start Phase 1 or later work.

This is a retry because a prior Claude Code session stopped after a scope acknowledgment without performing any implementation. Do not end after acknowledging scope or describing intended work. Use your tools now, make the required Phase 0 changes, and run verification before producing the final status line.

Use the plan as the functional specification. In particular, implement the Phase 0 deliverables (`core/perf.py`, `scripts/measure_app_performance.py`, `tests/test_web_performance_contracts.py`, and an acceptance artifact where appropriate), integrate trace points without changing application behavior, and run focused verification. Keep production tracing opt-in and protect secrets/user data.

## Guardrails

- This is an already dirty worktree. Preserve and do not revert, overwrite, stage, commit, or "clean up" unrelated user changes.
- Inspect existing interfaces before editing. Make the smallest coherent changes needed for Phase 0.
- Do not implement any later phase, even if it seems tempting.
- Run the focused tests and the measurement script where practical; report commands and concise results.
- Update `AI_CONTEXT.md` only if Phase 0 creates a genuinely durable project-level convention; otherwise leave it unchanged.
- Do not create a git commit in this session.

## Mandatory quota stop rule

If you encounter any Claude API quota, rate-limit, credit, billing, or usage-exhaustion message, **stop immediately**. Do not continue investigation, edits, tests, or later phases. End your response with exactly:

`PHASE_0_BLOCKED: <verbatim or concise quota message>`

Otherwise finish your response with:

`PHASE_0_DONE: <files changed>; <tests/measurements run>; <known limitations>`

Your output is captured as the authoritative transcript for this phase.
