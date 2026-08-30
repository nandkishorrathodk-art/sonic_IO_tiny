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
- Known pre-existing failures (environmental, NOT code bugs):
  - `test_phase13/*` through `test_phase19/*` — require a live Docker daemon
    (`DockerProvider` runs `docker`); not available in CI/this sandbox.
  - `test_phase21_real_graphical_workstation.py::test_daytona_gui_action_dispatch`
    — requires a live Daytona sandbox with a real X11 desktop + VS Code.
  - `test_p0_security_hardening.py::test_secret_key_env_alias_populates_jwt_secret`
    — fails only when a local `.env` sets `JWT_SECRET`/`SECRET_KEY` (the `.env`
    wins over the test's `monkeypatch.setenv`). Remove/rename `.env` to verify;
    this is test-isolation, not a code bug. `.env` is gitignored.
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

## Daytona integration (live-tested, SDK daytona==0.207.0)
Two separate integrations exist; only the first is used by the workstation API:
- `sonic/computer/daytona_computer.py` → `DaytonaComputerProvider` (graphical
  desktop; used by `/workstation/*` routes via `get_daytona_computer()`).
- `sonic/sandbox/providers/daytona_provider.py` → `DaytonaProvider` (generic
  exec sandbox; selected by `factory.py` when `SONIC_COMPUTE_PROVIDER=daytona`
  or `DAYTONA_API_KEY` is set, but NOT wired to any workstation route).

Env vars (read via raw `os.environ`, NOT in config.py):
- `DAYTONA_API_KEY` / `DAYTONA_API_URL` (default https://app.daytona.io/api)
- `DAYTONA_SANDBOX_ID` + `DAYTONA_SANDBOX_TENANT_ID` — env-attach path: if the
  login user's `user.email == DAYTONA_SANDBOX_TENANT_ID`, `create()` reuses the
  existing sandbox instead of provisioning a new one.
- `DAYTONA_IMAGE` / `DAYTONA_RESEARCH_IMAGE` / `DAYTONA_TARGET_IMAGE` — per-type
  image override (default `daytonaio/sandbox:0.9.0`).

SDK API notes (0.207.0):
- `client.list()` is an async generator (`async for sb in client.list()`), NOT
  an awaitable. Older SONIC code may do `await client.list()` — that breaks.
- `client.get(id_or_name)` → `AsyncSandbox` (works).
- `client.start(sandbox)` takes a sandbox OBJECT, not an id.
- `client.delete(sandbox)` for removal (no `client.remove()`).
- `sandbox.process.exec(cmd)` → `ExecuteResponse` with `.exit_code` and
  `.result` (NOT `.stdout`/`.stderr`). SONIC's `terminal()` reads these correctly.
- `sandbox.computer_use.start()` must be called before screenshot/VNC.

Live-tested end-to-end (13/14 routes passed against a real Daytona sandbox):
- ✅ desktop/research-lab/target-sandbox provision (env-attach)
- ✅ desktop status + screenshot
- ✅ /workstation/command (real `uname -a` executed in container)
- ✅ target-sandbox provision (with scope.yaml-format scope_config) + command
- ✅ /llm/chat via NVIDIA NIM (meta/llama-3.2-11b-vision-instruct works)

Known issues and resolutions (current state):
- `status()` now normalizes `SandboxState` enum correctly via
  `_normalize_sandbox_state()`; LIVE sandboxes report `RUNNING` instead of
  `UNREACHABLE`. Resolved.
- `destroy()` falls back to `client.get`/`delete` via `_resolve_sandbox` when
  the workspace is absent from the in-memory map (e.g. after a backend
  restart). Resolved.
- Workstation RBAC tightened: all sensitive mutation routes
  (provision/destroy/command/desktop-action/target-sandbox-command/file-write/
  mission-start/prompt/session-delete/browser-open) now use `require_operator`,
  so read-only `AUDITOR` roles are blocked (403). Resolved.
- `meta/codellama-70b` removed from `configs/models.yaml` (404/EOL on NVIDIA
  NIM); coding routing uses `deepseek-ai/deepseek-r1`. Resolved.
- `/workstation/desktop/screenshot` and `/workstation/desktop/action` now
  return a graceful `200 NO_DISPLAY` observation (instead of `409`) when no
  workstation is provisioned. Resolved.
- `/workstation/command` FAILS CLOSED with `503` (not `409`) when no
  workstation is provisioned — the documented fail-closed contract. Resolved.
- `/workstation/file` path-traversal guard now rejects with `403` (was `400`)
  and is validated BEFORE the provisioning check, so traversal is blocked
  regardless of sandbox state. Resolved.
- Daytona sandboxes auto-stop (15m) / auto-archive (7d) — long test runs must
  set `auto_stop_interval` high or call `client.start()` before each op.
  (Still applies; environmental.)

LLM integration: `configs/models.yaml` has `nvidia` as default provider
(`NVIDIA_API_KEY`, `NVIDIA_BASE_URL`→integrate.api.nvidia.com/v1). Routed via
`sonic/llm/providers/custom.py` `CustomLLMProvider` (OpenAI-compatible).
Endpoint: `POST /llm/chat` (body: message, provider, model, max_tokens).

## End-to-end bug-hunt pipeline (live-tested)
Full flow verified against a dummy vulnerable target (intentionally-vulnerable
Flask app with command-injection RCE) deployed inside a Daytona sandbox:
1. `/auth/login` → operator token (RBAC, role clamped)
2. `/workstation/desktop/provision?session_id=<id>` → attach Daytona sandbox as
   computer-use workstation (env-attach via DAYTONA_SANDBOX_TENANT_ID match)
3. `/workstation/command` (body: command, session_id, timeout) → recon via curl
   inside the sandbox. NOTE: session_id is in the BODY, not query string.
4. `/llm/chat` (provider=nvidia, model=meta/llama-3.2-11b-vision-instruct) →
   LLM sub-agent analyzes recon output, hypothesizes vulnerabilities
5. `/workstation/command` → exploit (confirmed OS command injection RCE:
   `uid=1001(daytona)` + arbitrary file read of `/etc/os-release`)
6. `/workstation/desktop/screenshot?session_id=<id>` → real 1024x768 PNG frame
   from the Daytona desktop (computer_use.start() must succeed first)

Key learnings:
- `session_id` for `/workstation/command` is in the REQUEST BODY
  (`ExecuteCommandRequest.session_id`), NOT the query string. Provision routes
  use `Query("default")` for session_id. Mismatch causes 409 "no workstation".
- Workstation state persists to `sonic_data/workstations.json`. If a sandbox is
  recreated (new ID) but the state file still has the OLD ID, `terminal()`
  fails (exit_code 126) looking up a non-existent sandbox. Delete the state
  file or use a fresh session_id when switching sandboxes.
- Egress guard (P0-6) REFUSES to bind engagement/target-sandbox to private/
  loopback addresses (localhost, 172.x, 10.x, 192.168.x, 169.254.169.254).
  This is correct SSRF/metadata protection. A dummy target inside the sandbox
  is private, so engagement *binding* is refused — but recon/exploit still run
  via `/workstation/command` (which executes inside the already-scoped sandbox
  and doesn't re-check egress on curl destinations).
- LLM analysis quality is variable (llama-3.2-11b sometimes hallucinates
  endpoints not in recon output). Better as a hypothesis generator than
  authoritative finder. Use a larger model (90b) for higher-stakes analysis.
