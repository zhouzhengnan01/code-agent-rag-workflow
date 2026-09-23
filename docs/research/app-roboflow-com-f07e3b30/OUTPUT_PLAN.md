# Roboflow-inspired authentication and navigation output plan

## Targets

| Source | Source page key | Destination | Existing route policy |
| --- | --- | --- | --- |
| `https://app.roboflow.com/login` | `login-7e93fba0` | `/login` and `/register` | Explicitly requested replacement of the existing authentication UI; existing FastAPI auth endpoints preserved |
| `https://app.roboflow.com/zhouzhengnans-workspace/agent` | `agent-af2d120e` | `/workbench.html` | Preserve the existing application and update only its shared navigation shell |

## Project adaptation

This repository is a FastAPI application with a static HTML/CSS/JavaScript frontend, not the Next.js scaffold assumed by the generic cloning workflow. The durable output therefore lives under `web/`, while research stays namespaced below this directory. No existing application route is removed.

## Planned output

- Authentication UI: `web/login.html`, `web/register.html`, `web/auth.css`, `web/auth.js`, `web/auth-promo.css`, `web/auth-promo.js`
- Local source assets: `web/sites/app-roboflow-com-f07e3b30/login-7e93fba0/`
- Existing workbench shell: `web/workbench.html`, `web/roboflow-theme.css`, `web/workbench.js`
- Backend authentication and GitHub OAuth: `backend/app/auth.py`, route/middleware integration in `backend/app/main.py`
- Persistent auth tables: `backend/app/db.py`
- Configuration: `.env.example`
- Tests: `tests/test_auth.py`

## Shared foundation

- Inter/system sans-serif stack
- Roboflow dark navigation tokens: `#0c0f1a`, `rgba(255,255,255,.08)`
- Purple action tokens: `#6d28d9`, `#7c3aed`, `#f5f3ff`
- Local inline SVG marks only; no remote runtime assets
