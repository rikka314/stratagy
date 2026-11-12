# 08 · Deployment Optimization and Cross-Device Setup

## Why this line started

To support deployment on multiple platforms (Windows, macOS, Linux) and enable remote development workflows.

## Frozen scope

- Deployment modes: Local development, Nginx subpath, remote server
- Cross-device compatibility: Windows batch scripts, macOS shell scripts, Linux systemd
- Remote development: VS Code Remote-SSH, GitHub Codespaces, cloud editors
- Performance: Workspace caching, market context caching, telemetry monitoring

## Research flow

1. Implement cross-device setup scripts (`setup.bat`, `start.bat`, macOS equivalents)
2. Add Nginx subpath configuration for `/strategy` deployment
3. Implement workspace persistence and cache invalidation
4. Add performance monitoring (`core/perf.py`, `core/workspace_cache.py`, `core/market_cache.py`)
5. Document deployment contracts and remote development workflows

## Key decisions and ideas

- Deployment configuration is frozen in `deploy/` and `.streamlit/config.toml`
- Workspace cache preserves analysis state across sessions
- Market context cache reduces API calls
- Performance events track loading and rendering time

## Result

Deployment optimization completed with cross-device setup, Nginx subpath support, workspace persistence, and performance monitoring. All contracts documented and tested.

## Gate and current status

Status: `completed`. Deployment contracts frozen and operational.

## Source files

- Contracts: `document/interfaces/deploy-runtime.md`, `document/interfaces/workspace.md`
- Code: `deploy/`, `scripts/`, `.streamlit/config.toml`, `core/workspace_cache.py`, `core/market_cache.py`, `core/perf.py`
- Tests: `tests/test_workspace_cache.py`

## Reproduction boundary

Deployment configuration and workspace contracts are frozen. Changes require compatibility verification across all supported platforms.
