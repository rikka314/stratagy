---
name: strategy-deploy
description: "Work on deployment, runtime, routing base paths, sync scripts, and Nginx configuration in this repository. Use when a task touches `.streamlit/config.toml`, `deploy/*.bat`, `deploy/*.sh`, `deploy/nginx_strategy.conf`, service names, upload lists, or public `/strategy` routing behavior."
---

# Strategy Deploy

## Required Reads

1. `AI_CONTEXT.md`
2. `document/interfaces/deploy-runtime.md`
3. `.streamlit/config.toml` when changing routing or runtime behavior

## Preferred Search Paths

- `.streamlit/config.toml`
- `deploy/sync.bat`
- `deploy/upload_and_deploy.bat`
- `deploy/deploy.sh`
- `deploy/nginx_strategy.conf`
- `app.py` when route paths or public URLs change

## Do Not Chase

- Do not read frontend style docs for pure deploy tasks.
- Do not change route paths in one place only; base path work is cross-file by default.
- Do not assume local-only behavior is acceptable when the app is deployed under `/strategy`.

## Completion Checklist

- Confirm `app.py`, `.streamlit/config.toml`, and Nginx still agree on the public path.
- Confirm upload scripts include every file needed by the change.
- Confirm service name, remote dir, and restart/log commands still match.
- Update `document/interfaces/deploy-runtime.md` if runtime rules changed.
