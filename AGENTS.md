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

## Persistent memory (Phase 1 — DONE, foundation)
SONIC's mind now survives a backend restart. The memory router
(`sonic/memory/router.py`) selects Neo4j first, then falls back to a
**persistent** SQLite-backed graph (`sonic/memory/sqlite_graph.py`) instead of
the ephemeral `InMemoryGraph`. So if Neo4j is down, memory still persists.
- `SqliteGraph` mirrors the `InMemoryGraph` interface exactly (drop-in), with
  write-through: every node/relationship write commits to SQLite immediately.
  Tables: `memory_nodes(uid,label,tenant_id,props_json,created_at)`,
  `memory_relationships(from_uid,to_uid,type,from_label,to_label,props_json,tenant_id)`.
- `VectorMemory` (`sonic/memory/vector.py`) and `EvolutionMemoryStore`
  (`sonic/evolution/memory.py`) also write through to SQLite (`vector_documents`,
  `evolution_items` tables) via stdlib `sqlite3` (sync API preserved).
- DB path resolves from `SONIC_MEMORY_DB_PATH` env → `DATABASE_URL` (sqlite) →
  `./sonic_data.db`. Tests set `SONIC_MEMORY_DB_PATH` to a temp file.
- `reset_memory_singleton()` / `reset_vector_memory_singleton()` clear the cached
  singletons to simulate a restart (used by `test_phase1_persistent_memory.py`).
- Done-gate test: `sonic-core/tests/test_phase1_persistent_memory.py` — proves
  graph/vector/evolution memory survive restart, tenant isolation holds across
  restart, and no host `subprocess` execution was introduced.
- **Honesty checkpoint:** Phase 1 claims ONLY persistent memory. Reasoning,
  browser-in-loop, security-tool execution, and curiosity/life were originally
  deferred (Phase 3-6). They are now DONE — see "Phases 3-6 (capability
  layer)" below.

## Persistent body + safety (Phase 2 — DONE, foundation)
- `DaytonaComputerProvider` persists its workspace index to
  `sonic_data/workstations.json` (`SONIC_WORKSTATION_STATE_PATH`). `_load_state()`
  runs in `__init__`, so workspace IDs survive a backend restart and
  `_resolve_sandbox` re-attaches via `client.get(id)`. `create()`/`destroy()`
  write-through on every lifecycle change.
- `get_or_create_home(tenant_id)` returns the tenant's long-lived
  `MISSION_COMPUTER` home, reusing a persisted one instead of reprovisioning
  (tenant-scoped).
- Safety regression (verified by `test_phase2_persistent_body_and_safety.py`):
  host execution is hard-forced false outside dev even when
  `SONIC_ALLOW_HOST_EXECUTION=true`; `LocalDevProvider.execute()` returns a
  fail-closed result (exit 126) when disabled — never spawns a host subprocess.
- Test marker `@pytest.mark.no_live_infra` opts a test out of the live-compute
  skip gate (for provider state/safety logic that needs no live sandbox). The
  ~48 genuinely live-gated integration tests remain honestly skipped.
- **Live done-gate (Step 2.4) is environment-gated:** the full
  provision-home → screenshot → terminal → restart → re-attach cycle needs a
  real Daytona cloud desktop (`SONIC_RUN_LIVE_DAYTONA=1`). Not runnable here.

## Phases 3-6 (capability layer — DONE)
The unified observe -> reason (LLM) -> act loop now covers terminal, files, git,
browser, security tools, AND self-directed exploration. No hardcoded fallbacks.

### Phase 3 — Real computer-use reasoning
- `sonic/computer_use/agent.py` rewritten: removed
  `_derive_remediation_from_goal()` and `_heuristic_choose_action()` entirely.
  Action selection is LLM-driven each step: build reasoning context from goal +
  observation + action history -> LLM returns the next action. `observe()` reads
  terminal output via `echo __sonic_obs_ready__` (not a hardcoded string).
  `run_mission()` has goal-aware termination (`GOAL_COMPLETE` sentinel).
- Done-gate: `test_phase3_real_computer_use_reasoning.py` (8 tests).

### Phase 4 — Unified action surface (browser-in-loop)
- `BROWSER_NAVIGATE / BROWSER_CLICK / BROWSER_TYPE / BROWSER_SCREENSHOT` added
  to `ComputerActionType` and the LLM action space/parser/prompt.
- `ComputerUseAgent` accepts an optional `BrowserAgent`; `observe()` folds the
  live browser page state (url, title, interactive elements) into the
  observation; `execute_action()` dispatches BROWSER_* to the browser.
  `BrowserAgent.current_page_state()` returns the live (url, title) so the
  observation reflects page state AFTER interactions.
- Done-gate: `test_phase4_unified_browser_in_loop.py` (4 tests).

### Phase 5 — Security-tool execution in the unified loop
- `SECURITY_TOOL` added to the action space. `ComputerUseAgent` accepts a
  `security_tools` registry (name -> SecurityTool). `execute_action()` builds a
  `ToolRequest` and calls `tool.execute()`, which runs the tool INSIDE the
  sandbox provider (fail-closed: exit 126 -> status BLOCKED). The structured
  `ToolResult` (findings, status) is stored in `_last_tool_result` and surfaced
  to the next reasoning step, so the LLM acts on REAL scan findings, not a
  "scan ran" claim. Blocked/failed tools trigger recovery; recovery preserves
  the original error cause.
- Done-gate: `test_phase5_security_tool_execution.py` (5 tests).

### Phase 6 — Curiosity / life loop (self-directed, novelty-driven)
- `sonic/computer_use/curiosity.py`: `CuriosityLoop.propose_curious_goal()` asks
  the LLM to propose the most informative goal from the live observation + the
  known-facts list (novelty-biased, not a fixed idle script).
  `measure_novelty()` reuses `NoveltyEngine`; `persist_fact()` records
  genuinely-new facts to `VectorMemory` (Phase 1 Mind) with near-duplicate
  dedup, so curiosity compounds across cycles. Dead-end detection flips the
  proposal prompt into a "pivot to a different area" instruction.
- `ComputerUseAgent.idle_cycle()` / `run_curiosity_loop()`: propose a goal,
  pursue it via the REAL observe->reason->act loop, measure novelty, persist any
  newly-learned fact. The same loop now drives operator goals AND self-directed
  exploration.
- Done-gate: `test_phase6_curiosity_life_loop.py` (5 tests).

### PLAN Phase 6 — Self-host safety envelope / VPS gate (fail-closed ActionPolicy)
- `sonic/safety/action_policy.py`: `ActionPolicy` is a fail-closed gate the loop
  consults BEFORE any action (operator- OR self-directed). It composes existing
  primitives: path confinement (workspace-root) for FILE_*; egress filter
  (`sonic.sandbox.egress`) for SECURITY_TOOL targets + BROWSER_NAVIGATE urls;
  destructive-command gating (`sonic.safety.scope.classify_command_risk`,
  L2->block, L1->needs approval); an action-type allowlist (unknown types
  DENIED by default); and a per-agent rate limit.
- `ComputerUseAgent.execute_action()` evaluates the policy pre-dispatch; a
  denied action is recorded BLOCKED, NEVER reaches the provider, and does NOT
  trigger recovery (recovery must not bypass the gate). Self-host mode
  (`self_host=True`) REFUSES to construct without a safety policy.
- Done-gate: `test_phase_plan6_safety_envelope.py` (10 tests): in-workspace
  actions execute; path-escape/traversal denied; destructive command denied;
  security tool vs metadata IP denied (egress); unknown action type denied;
  the SAME gate blocks curiosity pursuits; self-host requires a policy;
  rate limit caps actions/min.

### Test baseline (after Phases 3-6)
- 332 passed, 48 honestly skipped, 6 pre-existing model-only failures
  (unchanged). The 6 failures assert OLD fake-success behavior in the evolution
  / exploit capability layer; they are out of scope per PLAN and are NOT caused
  by this work.

## AI-Human layer (Phase 7 — Persistent Being + Life + Craft)
The foundation (persistent Mind + Body + safety) is real. The "AI human" layer
makes the being a *stable self* rather than a fresh tool on each boot:

### Persistent Being Identity — `sonic/being/identity.py`
- Before this, `agent_id` was a per-instance UUID (or the literal
  `"computer-use-agent"`) minted fresh every boot — each restart the system
  became a brand-new tool with no continuity. A being that forgets its own
  identity is not alive.
- `Being` (stable `being_id`, `name`, `tenant_id`, `born_at`) + `BeingMind`
  (cross-session mood: `curiosity_drive`/`focus`/`satiety`, learned-facts
  ledger, idle/goal tallies) are persisted to SQLite (write-through, mirrors
  the Phase-1 VectorMemory pattern: stdlib `sqlite3` + read cache +
  `reset_being_singleton()`). They share `sonic_data.db` (env
  `SONIC_BEING_DB_PATH`/`SONIC_MEMORY_DB_PATH`).
- `BeingMind` is distinct from `agents/cognitive_state.py:CognitiveState`
  (per-engagement, Redis-TTL'd 24h). The being's affect survives restart;
  `record_idle_cycle()` evolves mood deterministically from the outcome (novel
  fact -> curiosity+satiety rise; dead-end -> satiety/boredom + focus rise).
- `get_or_create_being(tenant_id)` is the identity equivalent of
  `get_or_create_home(tenant_id)` for the Body: on restart the identity is
  RE-RESOLVED from SQLite (same `being_id`, same `born_at`), not reminted.
  Tenant isolation holds: one being per tenant, cross-tenant reads return nothing.

### Always-on Life Loop — `sonic/being/life_loop.py`
- `BeingLifeLoop` is the always-on tick that runs when no operator goal is
  active, letting the being pursue self-directed curiosity between (and
  independent of) API requests. Before this, `CuriosityLoop` existed but was
  dead unless manually poked — a being that only acts when poked is a tool.
- Each tick proposes a curious goal (LLM, novelty-biased) and pursues it via
  the agent's REAL observe->reason->act loop. **Every autonomous action still
  passes the Phase-6 `ActionPolicy` safety envelope** — the being cannot escape
  it when "left to its own devices". Constructing a life loop without a safety
  policy is refused (mirrors `ComputerUseAgent(self_host=True)`).
- Spawned as a long-lived `asyncio.Task` in `api/main.py:lifespan()` (env-gated
  `SONIC_ENABLE_BEING_LIFE_LOOP=1`; cancelled cleanly on shutdown; a failed
  tick is logged and the loop continues, so one bad cycle can't kill the being).

### Durable Craft — `sonic/being/craft.py`
- `BeingCraft` persists being-authored artifacts (notes/observations/scripts)
  on the HOST filesystem under `sonic_data/craft/<being_id>/`, so the being
  builds a personal toolkit that survives restart — distinct from disposable
  in-sandbox research outputs (which were durable only via git commits).
- Files are markdown and human-readable on disk; an `index.json` lists metadata.
  Being-scoped isolation holds between beings.

### Done-gate (test_phase7_ai_human_being.py, 11 tests)
- identity stable across restart (same being_id + born_at, not reminted);
  first-contact provisions / second-contact re-attaches;
  BeingMind persists + mood evolves (novel rewards, dead-end -> boredom);
  tenant isolation; life loop refuses construction without a safety policy;
  the life loop tick routes the being's self-directed action THROUGH the safety
  gate (destructive idle pursuit BLOCKED, never executed, still recorded);
  loop starts/stops cleanly + survives a failed tick; craft persists across
  restart + being-scoped + human-readable on disk.

### Test baseline (after Phase 7)
- 353 passed, 48 honestly skipped, 0 failures (PR#3's simulated-provider fixes
  resolved the 6 previously pre-existing model-only failures; Phase 1-7 green).

## Security Tool Adapter Registry (Phase 7.5 — wire real adapters to all callers)
Closed the audit-flagged gap: the real SecurityTool adapters (nmap/nuclei/ffuf/
http_client) existed but were unreachable from production callers — only the
queue worker wired them up privately, and the mission director + AI-Human being
life loop constructed `ComputerUseAgent` with an EMPTY `security_tools=` map,
so the agent could advertise a `SECURITY_TOOL` action to the LLM but never
actually dispatch a scan.

### `sonic/tools/registry.py` — one shared registry
- `build_security_tools(provider)` constructs the 4 REAL adapters bound to a
  ComputeProvider (every tool runs in-sandbox via `SecurityTool.execute` →
  `provider.execute`; fail-closed on exit 126 — zero host execution, no stubs).
- `SecurityToolRegistry`: name→tool lookup with `register()` plugin extension
  point; `get_default_registry(provider)` is the production entry point.
- Provider-scoped by design (NOT a process-global) — adapters bind to a specific
  provider/tenant sandbox, so a global would leak a sandbox across tenants.

### Wiring (one source of truth)
- `queue/worker.py`: builds `_tools` via `build_security_tools()` (replaces the
  private hardcoded dict).
- `api/main.py` being life loop: passes `security_tools=get_default_registry(
  provider).as_dict()` so the AI-Human being can run real scans during
  self-directed curiosity.
- `mission_engine/director.py`: passes registry tools to the engineering-phase
  `ComputerUseAgent` (bound to the underlying `ComputeProvider`).

### Done-gate (test_security_tool_registry.py, 6 tests)
- build returns the 4 real adapters bound to the provider; registry lookup +
  extension + provider-scoping (no global leak); worker uses the registry; the
  agent dispatches a REAL NmapAdapter end-to-end via registry tools (canned nmap
  stdout parsed by the real adapter, port 22 surfaced as a finding); a
  fail-closed (exit 126) tool outcome triggers recovery through the registry path.

### Test baseline (after Phase 7.5)
- 359 passed, 48 honestly skipped, 0 failures.

## Sealed Safety Policy (Phase 7.6 — tamper-evident guards)
Closed the PLAN.md audit item: "Safety immutability: guards are real but NOT
protected from a self-evolving agent modifying them (no read-only/signed layer)."
The existing guards were plain mutable Python objects — an in-process
self-evolving being could widen its own envelope at runtime
(``policy.security_tool_targets.add(...)``, ``egress.BLOCKED_NETWORKS.clear()``,
or reassigning ``agent.safety``) and then act.

### `sonic/safety/sealed.py` — tamper-evident policy
- `SealedActionPolicy(ActionPolicy)`: at `seal()` time freezes a snapshot of every
  verdict-controlling field (allowed_types, security_tool_targets [frozenset],
  rate cap, approval flag, workspace root, and a *copy* of the egress
  blocked-networks list) and records a SHA-256 seal hash.
- After sealing, mutation of any safety-relevant field raises `AttributeError`
  (effectively immutable); the rate window may still mutate.
- On every `evaluate()` the seal hash is recomputed + compared; any mismatch
  (config altered) makes the verdict fail-closed DENY + logs
  `safety_policy_tampered` — the being may NOT act under an unprovable policy.
- `_check_egress` uses the FROZEN blocked-networks snapshot (via the new
  `egress.is_target_allowed(blocked_networks=...)` param), so a runtime mutation
  of the module-level `BLOCKED_NETWORKS` list cannot widen what this policy
  permits. Backward compatible: `is_target_allowed` defaults to the live list.
- `seal_default()` builds + seals the standard production policy.
- Additive + opt-in: plain `ActionPolicy` still works unchanged (existing tests
  hold); the being life loop constructs a `SealedActionPolicy`.

### Wiring
- `api/main.py` being life loop: `safety = seal_default(...)` (was a plain
  `ActionPolicy`) — the AI-Human being always acts under a proven-intact envelope.

### Done-gate (test_safety_sealed_policy.py, 11 tests)
- seal freezes config + records a 64-char sha256 hash; sealed fields are
  immutable (AttributeError on mutation of allowed_types/rate/approval/workspace);
  a tampered policy (object.__dict__ bypass) fails-closed DENY + logs tamper;
  egress uses the frozen snapshot (clearing `egress.BLOCKED_NETWORKS` does NOT
  widen the sealed policy — `10.0.0.5` stays blocked — and the seal stays intact);
  contrast: a plain unsealed `ActionPolicy` IS widened by the same mutation
  (proving the gap the sealed layer closes); the agent under a sealed policy
  allows a public target and blocks (status=BLOCKED) a private one.

### Test baseline (after Phase 7.6)
- 370 passed, 48 honestly skipped, 0 failures.

## Real Autonomy: Trace-Derived Mission Artifacts (Phase 7.7)
Closed the PLAN.md audit item: the mission director hardcoded its milestones
(all force-set to COMPLETED), deliverables ("JWT none algorithm bypass" + a
fake commit hash `7b8e1f0a2c`), knowledge summary ("what_we_know" JWT strings),
and confidence (=1.00) — NONE of it derived from what the agent actually did.
That was scripted theater: the director reported success and fabricated
evidence regardless of the traces.

### `sonic/mission_engine/trace_synthesis.py` — derive real artifacts from traces
- `synthesize_deliverables(mission_id, goal, traces)` — one deliverable per
  concrete successful engineering action the agent ACTUALLY took
  (FILE_WRITE→ENGINEERING_PATCH, GIT_COMMIT→GIT_COMMIT, SECURITY_TOOL→
  EVIDENCE_PACKAGE). Content = the real observation text, not a hardcoded vuln
  name. No successful artifact action → empty list (honest: no fabrication).
- `synthesize_knowledge(goal, traces)` — what_we_know/decisions/evidence come
  from the real traces; confidence = success ratio (NOT 1.00 by decree).
- `milestone_status_from_traces(traces, plan)` — a milestone is COMPLETED only
  where the traces contain a relevant successful action; otherwise stays
  PENDING. Never force-completed by decree.

### Director wiring (`director.py`)
- `coordinate()`: milestones now derived via `milestone_status_from_traces`;
  confidence = successful/total; outcome is SUCCESS only if the agent actually
  did something that succeeded (else PARTIAL_SUCCESS/FAILED).
- `finalize(traces=...)`: returns trace-derived deliverables (was the hardcoded
  JWT pair). No traces → empty list.
- `get_knowledge_summary()`: reflects the stashed real traces (was hardcoded
  JWT strings).
- RESEARCH-phase hypotheses seeded from the objective's constraints, not a
  hardcoded "JWT none algorithm" hypothesis.

### Browser action surface wiring (also closes the "orphaned browser" item)
- `director.coordinate()` + `api/main.py` being loop now construct a
  `BrowserAgent(headless=True)`, launch it, and pass `browser=` to the agent.
  The browser was orphaned before (BrowserAgent existed + the agent's
  observe→reason→act loop had full browser support, but no caller ever passed
  `browser=`, so `agent.browser` was always None and the browser branch never
  ran). Now navigate/click/type/screenshot dispatch as first-class actions.
- Removed dead code: `_derive_remediation_from_goal()` (67 lines of hardcoded
  JWT/SQLi/XSS/traversal patches, never called) — the LLM-driven
  `_llm_choose_action` + generic `_diagnostic_fallback` are the real paths.

### `MissionKnowledgeSummary.confidence` field added
- New `confidence: float = 0.0` field so the trace-derived success ratio is
  surfaced in the knowledge snapshot (was on `MissionState` only).

### Done-gate (12 + 2 tests)
- `test_mission_trace_synthesis.py` (12): deliverables one-per-artifact +
  content-is-real-observation + failed-produces-none + empty-is-empty +
  dedupe; knowledge derived-from-traces + confidence=success-ratio (not 1.00)
  + empty-is-honest + all-success=1.0; milestones completed-only-where-proven
  + all-pending-when-no-success; director.finalize trace-derived (not JWT) +
  honest-on-no-traces; knowledge summary reflects stashed traces.
- `test_browser_wiring.py` (2): browser-attached dispatches navigate to the
  browser (SUCCESS trace); browser=None does not crash (graceful skip).

### Test baseline (after Phase 7.7)
- 384 passed, 48 honestly skipped, 0 failures.

## Current test baseline
- 384 passed, 48 honestly skipped (Docker-daemon / Daytona-live gated via
  `sonic-core/tests/conftest.py`), 0 failures.
- The previously-pre-existing 6 model-only/fail-closed contract failures were
  resolved by PR#3's simulated-provider + execution-evidence fixes (they asserted
  the OLD fake-success behavior; now correctly supplied).
- `test_phase20_workstation_security_and_repair.py` is now GREEN: the
  `/workstation/command` route returns 503 fail-closed (not 409) when no sandbox
  is provisioned, and `/workstation/file` validates path confinement (403) BEFORE
  the workspace-state check.

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
