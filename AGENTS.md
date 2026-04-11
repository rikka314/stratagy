# Project Instructions

Before doing analysis, planning, code changes, reviews, or answers in this repository, read `AI_CONTEXT.md` at the project root.

Use `AI_CONTEXT.md` as the default source of truth for:
- project architecture and module map
- deployment workflow
- documentation status
- collaboration conventions

If `AI_CONTEXT.md` conflicts with another project document, prefer `AI_CONTEXT.md` unless the user gives newer instructions in the current conversation.

Re-read `AI_CONTEXT.md` whenever:
- the task touches an unfamiliar area of the repository
- `AI_CONTEXT.md` has changed during the session
- you need project-level context that is not already in the active prompt

At the end of each work session, update `AI_CONTEXT.md` when the session changed durable project-level facts, such as architecture, module responsibilities, deployment workflow, documentation status, collaboration conventions, or other long-lived repository context.

When updating `AI_CONTEXT.md`, keep it concise and accurate:
- include stable facts and decisions, not temporary exploration notes
- prefer updating existing sections over appending redundant text
- keep dates current when a status entry is time-sensitive
- skip the update if nothing project-level actually changed

## Workspace Convention

**Do NOT create new worktrees, workspaces, or sandboxes.**

Development and maintenance for this project happen exclusively via SSH remote connection to the server:

- SSH alias: `stratagy`
- Project directory: `/opt/stratagy`

When editing in VS Code or Cursor, use the Remote-SSH extension to connect to `stratagy` and open `/opt/stratagy` directly. Do not clone the repository locally and create a new workspace.
