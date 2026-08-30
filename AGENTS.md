# AGENTS.md — SONIC-REDA repository memory

## Project overview
SONIC-REDA is an autonomous AI bug-hunting / red-team system: FastAPI backend
(`sonic-core/`), Next.js dashboard (`sonic-dashboard/`), Docker sandbox
execution, Neo4j graph memory, multi-tenant RBAC.

## Layout
- `sonic-core/` — Python backend (uv workspace, Python 3.12+). `pip install -e sonic-core[dev]`.
- `sonic-dashboard/` — Next.js 14 dashboard. `npm install` then `npm run dev`.
- `docker-compose.prod.yml` — prod compose (secrets via env interpolation).
- `sonic-cli/` — CLI wrapper package.

## Running locally (dev)
- Backend: `APP_ENV=development python -m uvicorn sonic.api.main:app --port 12000`
  (uvicorn is not on PATH; use `python -m uvicorn`).
- Dashboard: `NEXT_PUBLIC_API_URL=<backend-url> npx next dev -p 12001`
- Neo4j is optional in dev — the backend falls back to "Running without Graph
  Memory" if localhost:7687 is unreachable.

## Testing
- `python -m pytest sonic-core/tests/`
- Security regression suite: `sonic-core/tests/test_p0_security_hardening.py`
- Known pre-existing failures (NOT caused by recent security work):
  - `test_phase2_compute_and_db.py` — needs `sqlalchemy` (not in pyproject dev deps).
  - `test_phase7/*` — `test_reproduction_engine_simulation`, `test_synthetic_trust_mission_lifecycle`.
  - `test_phase20_workstation_security_and_repair.py::test_workstation_command_executes_in_sandbox`
    — expects a provisioned Daytona workspace; returns 409 without one.
- `get_settings()` is `@lru_cache`d — in tests that monkeypatch env vars, call
  `get_settings.cache_clear()` before and after.

## Security hardening applied (commit ab99ae2)
P0 fixes (all covered by `test_p0_security_hardening.py`):
1. `/auth/login` + `/auth/dev-token` are dev-only (404 in non-dev); roles clamped
   to OPERATOR — no SUPER_ADMIN/TENANT_ADMIN escalation.
2. Production refuses to boot with insecure/default/short JWT secret. `jwt_secret`
   reads `SECRET_KEY` / `JWT_SECRET` env aliases.
3. `docker-compose.prod.yml` secrets injected via `${VAR:?...}`.
4. `run_engagement()` is tenant-scoped; SUPER_ADMIN tenant bypass removed.
5. `SONIC_ALLOW_HOST_EXECUTION=true` forcibly false outside development.
6. Egress filter (`is_target_allowed`) wired into engagement creation + target
   sandbox provisioning — rejects private/loopback/metadata targets.

## Conventions
- Config via pydantic-settings (`sonic/config.py`). Settings are env-driven.
- CORS origins configured via `CORS_ORIGINS` env (comma-separated). main.py had a
  duplicate hardcoded CORS middleware — now deduped to use `cors_origins_list`.
- Egress policy: `sonic/sandbox/egress.py` (`is_target_allowed`). Default deny
  for private/loopback/metadata ranges.
