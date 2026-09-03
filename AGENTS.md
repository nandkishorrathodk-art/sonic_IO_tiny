# AGENTS.md — SONIC-REDA repository memory

## Project overview
SONIC is an **Autonomous Self-Evolving Penetration Architect (A-SEA)**: an
AI-driven self-developing offensive-security being that operates its own
sandboxed computer environment, autonomously performs authorized security
assessments, discovers and tests new attack hypotheses, analyzes results,
learns from failures and successes, authors its OWN tools (Toolsmith) and
synthesizes NOVEL attack methods (Method Lab), and improves its own testing
strategies, tools, and workflows over time — all within a sealed, tamper-evident
safety envelope, with every "confirmed" / "working" claim backed by real
in-sandbox reproduction (no success-by-decree).

Formerly "SONIC-REDA (autonomous AI red-team system)". The identity was
renamed to A-SEA to match the actual capability surface (researcher +
architect, not just operator). All LLM prompts now use the A-SEA identity.

Architecture: FastAPI backend (`sonic-core/`), Next.js dashboard
(`sonic-dashboard/`), Docker sandbox execution, Neo4j graph memory,
multi-tenant RBAC.

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
- New upgrade tests: `sonic-core/tests/test_ai_and_control_upgrade.py` covers
  LLM retry/backoff, robust tool-argument JSON parsing, ReAct native
  function-calling with parallel tool execution, and ComputerUseAgent
  coordinate-bounds validation.
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

## Honest Autonomy: Adaptive planner + real recon (Phase 7.8)
Closed two remaining PLAN.md audit items.

### Objective-adaptive mission planner (`mission_engine/planner.py`)
Was: a single fixed 3-action plan (pwd / git status / find) for EVERY mission,
never adapting to the objective. Now the orientation baseline is always
prefixed, then intent-specific read-only inspection commands are derived from
the objective text:
- recon-intent → source-file enumeration + TODO/FIXME grep
- web/api-intent → http/url/endpoint grep + route/server file find
- test-intent → test-file + conftest/package.json discovery
- db-intent → query/sql grep + migration/schema find
Active probes remain approval-required (never silently executed). Every action
still compiles to the allowlisted read-only tool schema.

### Real recon, no hallucinated attack surface (`agents/recon.py`)
Was: asked the LLM "what subdomains likely exist? (api., admin., staging.,
dev., mail.)" and presented those guesses as discovered assets — hallucinated
attack surface. Now:
- Real subdomains come from Certificate Transparency logs (crt.sh JSON API),
  returned with `discovered_by: "certificate_transparency"`. Best-effort:
  egress-gated (uses `is_target_allowed`), returns [] if the CT source is
  blocked/unavailable — never invents subdomains.
- LLM-suggested candidates are clearly labeled `discovered_by:
  "llm_hypothesis"` with `confirmed: False` — NOT presented as observed truth.
- LLM subdomains already found via CT are deduped (kept as the real,
  confirmed entry).
- With no router, only real CT assets (if any) are returned — no imagined
  fallback.

### Done-gate (8 + 5 tests)
- `test_mission_planner_adaptive.py` (8): orientation baseline always
  present; recon/web/db intents add intent-specific commands; different
  intents produce different sets; active probe is approval-required (not
  silent); readonly objective adds no probe; empty objective raises.
- `test_recon_honesty.py` (5): real CT subdomains labeled
  certificate_transparency; LLM assets labeled llm_hypothesis/confirmed=False;
  LLM subdomain deduped against real CT; CT blocked → no invented subdomains;
  no router → only real CT assets.

### Test baseline (after Phase 7.8)
- 397 passed, 48 honestly skipped, 0 failures.

## Phase A — Toolsmith loop (AIOSR: being authors its own tools)
Closed the single highest-leverage gap from the AIOSR audit: SONIC was an
"Operator" (orchestrating known nmap/nuclei/ffuf primitives) but not a
"Researcher + Toolsmith" (building its own tools). The being can now author a
NEW small tool (scanner/fuzzer/parser/probe) for an observation gap, persist
it, run it in-sandbox, and register it as a first-class callable tool — but
ONLY after a real successful run. No "tool authored and working" claim by decree.

### `sonic/being/toolsmith.py` — author + confirm + register
- `ToolsmithLoop.author_tool_for_gap(observation, failed_attempts)` asks the LLM
  to propose ONE small Python tool filling a gap NO existing registered tool
  covers. The proposal is explicitly biased away from the existing tool set
  (nmap/nuclei/ffuf/http_client + already-confirmed authored tools) and from the
  reserved names — so the being does not re-author nmap. A `DECLINE` response
  or a duplicate/reserved/invalid name → returns `None` (honest skip: never
  fabricates a tool). A cheap pre-sandbox safety lint rejects host-wiping
  patterns (`rm -rf /`, `mkfs`, `dd of=/dev/`, `shutdown`) before the sandbox.
- The authored source is persisted to `BeingCraft` immediately (durable across
  restart; kind=`tool`, human-readable markdown on disk).
- `confirm_and_register(tool, provider, workspace_id)` writes the source to
  `/home/sonic/workspace/toolsmith/<name>.py` and runs `python <path>` in-sandbox
  via the provider's fail-closed `execute` (exit 126 => sandbox blocked it).
  **Honesty guard:** `reproduced=True` and registration into the
  `SecurityToolRegistry` happen ONLY on exit 0 + non-empty stdout. A blocked
  (exit 126), failed, or empty run leaves `reproduced=False` and the tool is NOT
  registered — the same anti-theatrical discipline as `production_gate`.
- `AuthoredToolAdapter`: wraps a confirmed authored tool as a real `SecurityTool`
  (name/version/build_command/parse_output/execute), bound to the provider that
  confirmed it. It inherits the base `SecurityTool.execute` fail-closed,
  in-sandbox handling (zero host execution, exit 126 => BLOCKED). `parse_output`
  decodes JSON lines (falls back to `{"finding": <line>}`), so the being's own
  tools emit structured findings through the same path as nmap.

### Action surface + safety wiring
- `TOOL_AUTHOR` + `TOOL_RUN` added to `ComputerActionType` + the LLM action
  space/parser/prompt. `execute_action()` dispatches:
  - `TOOL_AUTHOR` → `author_tool_for_gap()` (persists, does NOT register).
  - `TOOL_RUN` → `confirm_and_register()`; on `reproduced=True` the adapter is
    added to `self.security_tools` so the being can call its own tool via the
    existing `SECURITY_TOOL` path. The `available_tools` observation line
    already reflects the live `security_tools` keys, so authored tools surface
    to the LLM automatically once confirmed.
- `ActionPolicy.DEFAULT_ALLOWED_TYPES` extended with `TOOL_AUTHOR`, `TOOL_RUN`.
  Path confinement: `TOOL_AUTHOR` writes under a hardcoded workspace-subdir
  (structural confinement — no payload path to forge); `TOOL_RUN` runs a
  hardcoded `python <workspace-toolsmith-path>` (structural — no user command to
  gate). The sealed `SealedActionPolicy` inherits both (frozen in the seal).

### Production wiring (`api/main.py` being life loop)
- The being life loop now constructs a `ToolsmithLoop(craft=BeingCraft(being_id),
  llm=router, registry=get_default_registry(provider))` and passes
  `toolsmith=toolsmith` to `ComputerUseAgent`. So the always-on self-directed
  being can author + run its own tools during idle curiosity — every action
  still passes the sealed `SealedActionPolicy` gate.

### Done-gate (`test_phase_a_toolsmith.py`, 10 tests)
- authors a NOVEL tool name not in the registry (unconfirmed pre-run, not
  registered); `DECLINE` / no-novel → `None`; duplicate (nmap) → rejected;
  blocked run (exit 126) → NOT confirmed/registered; empty output → NOT
  registered; successful run → `reproduced=True` + registered + callable by
  name; authored source persists to BeingCraft (re-read off host disk); the
  safety policy ALLOWS `TOOL_AUTHOR`/`TOOL_RUN` (not denied as unknown); a
  destructive-source proposal (`os.system('rm -rf /')`) is rejected by the
  safety lint BEFORE the sandbox; a confirmed tool runs end-to-end via a real
  `ToolRequest` → `execute` and surfaces real parsed findings (not a decree).

### Test baseline (after Phase A)
- 423 passed, 48 honestly skipped, 0 failures.

## Phase B — Method-invention loop (AIOSR: being synthesizes novel techniques)
Closed the ONE gap that kept SONIC an "Operator" rather than a "Researcher":
`CuriosityLoop` proposes new GOALS but uses KNOWN techniques (nmap/nuclei
signatures). Phase B adds the "new new methods" loop from the AIOSR definition
— the being synthesizes a genuinely NOVEL offensive *technique* (a new method:
auth-bypass logic, parser-confusion chain, fuzzer mutation strategy,
header-injection primitive, race-condition probe, info-leak, logic-flow) from an
observation + a prior failure + the known-technique ledger, and confirms it
ONLY on real in-sandbox reproduction.

### `sonic/being/method_lab.py` — synthesize + confirm + persist
- `MethodLab.invent(observation, failure)` asks the LLM to synthesize ONE novel
  technique explicitly biased AWAY from the known-technique ledger (semantic
  search of `VectorMemory` scoped to `kind=technique` records). A `DECLINE`
  response, or a hypothesis that duplicates a known technique, → returns `None`
  (honest skip: never re-invents what it already knows).
- Each technique carries a `family` (auth-bypass/parser-confusion/fuzz-mutation/
  header-injection/race-condition/info-leak/logic-flaw/other), a `hypothesis`
  (the novel idea + why it differs), and a `probe_source` (small Python that
  takes a target as argv[1] and prints JSON findings when the technique works).
- `novelty_vs_ledger` is computed via `NoveltyEngine` so "novel" means genuinely
  outside the working-method ledger (0=identical, 1=fully novel). Empty ledger
  => 1.0.
- `confirm(technique, provider, workspace_id, target)` runs the probe in-sandbox
  (fail-closed exit 126 = blocked). **Honesty guard:** `confirmed=True` + ledger
  persistence happen ONLY on exit 0 + non-empty finding output. A blocked/empty
  run leaves the technique UNCONFIRMED and it is NOT added to the ledger —
  exactly the same anti-theatrical discipline as `production_gate`/`toolsmith`.
- A confirmed technique is parsed into structured `findings` (JSON lines, falls
  back to plain lines) and added to the VectorMemory ledger under doc_id prefix
  `technique-` with `kind=technique, confirmed=True`. So the ledger is a record
  of WORKING methods, and future `invent()` calls see these and steer away —
  novelty compounds across cycles (the being does not re-invent known methods).

### Phase A substrate feeds Phase B
- When a `ToolsmithLoop` is wired, `confirm()` routes the probe through the
  toolsmith's `confirm_and_register`: the probe is written to the sandbox,
  run fail-closed, and on success registered as a callable `SecurityTool`. So a
  confirmed technique's probe becomes a tool the being can re-run against new
  targets through the existing `SECURITY_TOOL` path. Phase A gave Phase B its
  execution substrate (a self-authored tool per self-invented technique).

### Action surface + safety wiring
- `METHOD_INVENT` added to `ComputerActionType` + the LLM action space/parser/
  prompt. `execute_action()` dispatches it to `MethodLab.invent()` then
  `confirm()`; the observation surface includes the technique name/family/finding
  count/novelty-vs-ledger. The `available_tools` line surfaces any probe that
  registered as a tool, so the LLM can re-invoke a confirmed technique.
- `ActionPolicy.DEFAULT_ALLOWED_TYPES` extended with `METHOD_INVENT` (structural
  confinement: the probe runs under a hardcoded workspace-toolsmith path, same
  as TOOL_RUN). The sealed `SealedActionPolicy` inherits it (frozen in the seal).

### Production wiring (`api/main.py` being life loop)
- The being life loop constructs `MethodLab(llm=router, vector_memory=
  get_vector_memory(), toolsmith=toolsmith)` and passes `method_lab=method_lab`
  to `ComputerUseAgent`. So the always-on self-directed being invents + confirms
  novel techniques during idle curiosity — every action still passes the sealed
  `SealedActionPolicy` gate, and every probe runs fail-closed in-sandbox.

### Done-gate (`test_phase_b_method_lab.py`, 9 tests)
- synthesizes a novel technique (novelty=1.0 vs empty ledger, unconfirmed
  pre-run); `DECLINE` → None; duplicate hypothesis → rejected; blocked probe
  (exit 126) → NOT confirmed + NOT in ledger; empty output → NOT confirmed;
  successful reproduction → confirmed + parsed findings + persisted to ledger
  (kind=technique, confirmed=True); a confirmed technique in the ledger steers
  the NEXT invention away (novelty compounds — duplicate synthesis rejected);
  the safety policy ALLOWS METHOD_INVENT; with a ToolsmithLoop wired, a
  confirmed technique's probe is registered as a callable tool.

### Test baseline (after Phase B)
- 432 passed, 48 honestly skipped, 0 failures.

## Prompt-identity + capability-awareness update (post-Phase B)
Renamed the system's LLM-facing identity from "SONIC-REDA, an autonomous AI
red-team system" / "elite bug bounty hunter" / "pentester" to **"SONIC — an
Autonomous Self-Evolving Penetration Architect (A-SEA)"** across every prompt,
so the being self-describes as a self-developing researcher/architect (matching
the real capability surface) rather than just an operator. 14 prompts updated:
- `agents/`: hypothesis, static_reasoning, recon, orchestrator, dynamic_execution,
  verifier, exploit_validator, react_engine.
- `agents/director.py` + `agents/replan.py`: Director + Replan Engine identity.
- `computer_use/agent.py` system prompt: A-SEA identity + now advertises the
  Toolsmith (TOOL_AUTHOR/TOOL_RUN) and Method Lab (METHOD_INVENT) as first-class
  actions, and instructs the LLM to author/invent when no existing tool fits a
  gap (not just re-run a known scanner).
- `computer_use/curiosity.py`: A-SEA identity + prefers goals that expose a
  Toolsmith/Method-Lab gap (so self-directed curiosity feeds method invention).
- `being/toolsmith.py` + `being/method_lab.py`: A-SEA identity; the toolsmith
  blocklist is now the DYNAMIC existing-tool set (was a hardcoded
  "nmap/nuclei/ffuf/http_client" literal — generalized so authored tools are
  auto-excluded from re-authoring).
- `continuous_dev/continuous_loop.py`: A-SEA identity + honesty clause (never
  claim success without a passing test command).
- `api/routes/workstation.py` workstation chat prompt: A-SEA identity + now
  describes the Toolsmith + Method Lab + sealed safety envelope + honesty rule
  (never claim confirmed without reproduction); generalized the Cloudflare-specific
  example to "a CDN".

No test asserted the old prompt text, so the rename was safe; full suite stayed
green (432 passed).

### Test baseline (after prompt update)
- 432 passed, 48 honestly skipped, 0 failures.

## Phase C — Dead-code removal (4,042 LOC deleted)
A static reachability audit from all production entry points (api/main + all
routers, queue worker, mission_engine, computer_use, being/*, swarm, cli)
proved that **6 packages form a closed, mutually-referencing island** that NO
production code path ever imports. They were vestigial scaffolding from the
old scripted-"success" evolution layer (Phases 8-19) that the real
observe→reason→act + Toolsmith + MethodLab loops replaced.

Deleted packages (production code):
- `sonic/autonomy/` (560 LOC) — blind_repair, hidden_root_cause, empirical_evolution, cryptographic_holdout, anti_scripting_verifier
- `sonic/continuous_dev/` (556 LOC) — ContinuousAutonomousDevLoop, autonomous_tool_selector, open_system_improver (was NOT wired to any route despite the Phase 7.9 AGENTS.md claim — that claim was aspirational/inaccurate)
- `sonic/open_world/` (399 LOC) — self_development_orchestrator, limitation_discovery, novelty_generator
- `sonic/production_gate/` (533 LOC) — scenario_matrix, temporal_holdout_generator, independent_evaluator
- `sonic/security_lab/` (709 LOC) — attack_surface, SecurityAcceptanceRunner
- `sonic/evolution/` (1,285 LOC) — the shared dependency hub (FailureMiner, CandidateGenerator, EvolutionLab, PromotionEngine, EvolutionMemoryStore, etc.); imported ONLY by the 5 packages above

Deleted test suites (31 files): test_phase8/, test_phase10/, test_phase11/,
test_phase16/, test_phase17/, test_phase18/, test_phase19/,
test_continuous_dev_curiosity_driven.py — all tested the deleted code.

`test_phase1_persistent_memory.py` updated: removed the
`test_evolution_memory_survives_restart` test (tested the deleted
EvolutionMemoryStore) and the `evo_memory` clause from
`test_no_host_execution_introduced` (now checks only sqlite_graph + vector).
The 3 core memory-survival tests (graph, vector, tenant isolation) remain —
they test the REAL persistent memory layer.

Packages KEPT (verified live):
- `sonic/meta/` (668 LOC) — used by `/experiments` route (CanaryPipeline, ExperimentManager, benchmark).
- `sonic/research/` (995 LOC) — used by `agents/director.py` (live swarm path: epistemic, information_gain, decision_trace, world_model).
- `sonic/agents/director.py` — the Phase-5 event-driven Director, reachable via `swarm.py` → `/live` route.
- `sonic/mission_engine/` — planner/executor used by `/workstation` mission loop.

### Test baseline (after Phase C)
- 386 passed, 37 honestly skipped, 0 failures. (46 deleted tests were for
  the removed code; 11 of those were Docker-gated skips.)

## Current test baseline
- 386 passed, 37 honestly skipped (Docker-daemon / Daytona-live gated via
  `sonic-core/tests/conftest.py`), 0 failures.
- The previously-pre-existing 6 model-only/fail-closed contract failures were
  resolved by PR#3's simulated-provider + execution-evidence fixes (they asserted
  the OLD fake-success behavior; now correctly supplied).
- `test_phase20_workstation_security_and_repair.py` is now GREEN: the
  `/workstation/command` route returns 503 fail-closed (not 409) when no sandbox
  is provisioned, and `/workstation/file` validates path confinement (403) BEFORE
  the workspace-state check.

## Audit fixes (honesty + wiring + test-isolation)
- `test_workstation_desktop_browser_and_news.py` was BROKEN at collection
  (missing `_clean_rss_titles`, no news/khabar intent). Fixed in
  `api/routes/workstation.py`: added the helper + news/info intent detection in
  `_detect_requested_app` / `_is_action_prompt`. (6 tests now collected + pass.)
- `CodeFixAgent` / `ExploitValidator` existed but were never wired into
  production dispatch (`swarm.py` `agent_map`/`agent_configs` omitted them;
  `queue/worker.py` `_run_agent_step` did not import them). Wired both so the
  AGENT_STEP dispatch path can actually instantiate them.
- Removed FAKE values from `production_gate/` + benchmark suites:
  - `scenario_matrix.py`: `initial_failure_verified` was hardcoded `True`
    (the broken version was never run). Now each scenario runs the BROKEN code
    first via `_verify_initial_failure()` and sets the flag from the real
    non-zero exit. `performance_delta_pct` (was 100/75/85 by decree) is now `0.0`
    (unmeasured — no before/after benchmark was run). Fake commit-hash fallbacks
    (`c01a9b`..`c08a9b`) replaced by `_commit_hash_from()` (empty when the
    provider returns a `bool`, which is what `git_action("commit")` does today).
  - `temporal_holdout_generator.py`: `v1_f1=0.667`, `v2_f1=1.000`, `tp=1/fp=0/
    fn=0` were all hardcoded. Now computed by a REAL token classifier
    (`_classify_v1`/`_classify_v2`/`_f1`) decoding JWT headers + signature length
    against real fixtures; v1 misses a short-signature token v2 catches, so
    the gain emerges from real behavior (still satisfies the test's
    success/gain>0.30 invariants).
  - `autonomy/blind_repair.py`: fake commit hash `7b8e1f0a2c` -> empty.
  - `computer_use/benchmark.py` + `mission_engine/benchmark.py`:
    `sonic_success_rate=1.00`/`autonomy_score=1.00`/`human_success_rate=0.92/0.88`
    (by decree) now DERIVED from per-trial success-flag lists.
  - `computer_use/models.py` + `computer/benchmark.py`: default scores 1.00 ->
    0.0 (honest "unmeasured" before `run_mission()`/the benchmark fills them in).
- `test_phase8/test_synthetic_self_evolution_mission.py` failed in the FULL
  suite (passed in isolation) because `EvolutionMemoryStore()` used the shared
  default SQLite DB polluted by earlier tests. Fixed to `persist=False`
  (in-memory isolation). This was a pre-existing suite-order bug, not caused
  by the honesty/wiring work.

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

## Phase 7.9 — security-scan dispatch + curiosity-driven continuous_dev

### Mission executor: real security scans (audit gap closed)
- `MissionToolExecutor` previously returned "Tool adapter is not implemented"
  for nmap/nuclei/ffuf. Fixed: `target_security_scan` is now a registered
  `APPROVAL_REQUIRED` tool, and the executor accepts an optional
  `SecurityToolRegistry`. When wired -> dispatches a REAL in-sandbox scan via
  `SecurityTool.execute` and surfaces parsed findings in `evidence`. When NOT
  wired -> BLOCKS with "security tool registry is not configured" (never the
  generic "not implemented").
- Provider bridge: security adapters need a `ComputeProvider` (`.execute(ws,
  command, timeout)`), but the executor has a `ComputerProvider` (Daytona,
  `.terminal`). The thin `sonic/tools/computer_as_compute_provider.py`
  adapter bridges them so scanners run against the same target sandbox the
  executor already uses — no second provisioning hierarchy.
- Production wiring: `api/routes/workstation.py` mission loop builds the real
  registry via `get_default_registry(ComputerAsComputeProvider(comp))`.
- Safety: approval is enforced (AWAITING_APPROVAL without operator approval);
  forbidden-pattern scan targets are BLOCKED by the scope checker; all scans
  run fail-closed in-sandbox.

### continuous_dev: curiosity-driven lifecycle (audit gap closed)
- `run_curiosity_driven_lifecycle()`: each generation's patch is derived from
  a novelty-steered goal (CuriosityLoop) + LLM-authored patch for that goal —
  NOT the hardcoded v1->v2->v3 StreamBuffer/QueryCache demo. Honest failure
  (`GenerationStatus.ROLLED_BACK`) when the LLM can't author a patch. The
  scripted demo is retained as a labeled fallback when no curiosity/router is
  wired.
- `_derive_patch_from_goal(goal, rationale, gen_idx)` invokes the LLM to author
  a patch for the goal; records a rolled-back generation (not a fabricated
  success) on failure.

### Test discipline (done-gate)
- Done-gate tests must NOT import `DaytonaComputerProvider` at module top-level
  — the conftest autouse fixture skips any module importing Daytona symbols
  unless `SONIC_RUN_LIVE_DAYTONA=1`. Use a `_StubComputer` with a `.terminal`
  method instead.
- `PlannedAction` requires a `risk` field (ToolRisk) — construction without it
  raises a pydantic ValidationError.
- Suite as of Phase 7.9: 407 passed, 48 skipped, 0 failures.

## Phase 8 — Real Visual Computer Use (A-SEA sees and controls its desktop)

Closed the fundamental autonomy gap: SONIC had a full graphical desktop (Daytona
XFCE, 1280x800) and mouse/keyboard SDK capabilities, but the workstation endpoint
ran a regex-based bash dispatcher instead of the agentic loop, and `GUI_CLICK`/
`GUI_TYPE` were unhandled enums.

### Core Enhancements:
1. **GUI Action Surface in `ComputerUseAgent`**:
   - `ComputerActionType` enum expanded: `GUI_CLICK`, `GUI_DOUBLE_CLICK`, `GUI_TYPE`,
     `GUI_KEYPRESS`, `GUI_MOVE`, `GUI_SCROLL`, `GUI_SCREENSHOT`.
   - `execute_action()` dispatches GUI actions to `computer.gui_action()` (mouse click/move,
     keyboard type/press, scroll via xdotool, explicit screenshot re-observe).
   - `_parse_llm_action()` parses visual coordinate format (`TARGET: 640,400` -> `x=640, y=400`).
   - System prompt advertises GUI action schema + coordinate guidance.
2. **Vision-in-the-Loop**:
   - `observe()` stores `_last_screenshot_b64` from Daytona screen captures.
   - `_llm_choose_action()` formats multimodal user content (`image_url` block + text)
     when screenshot pixels are available, enabling visual spatial reasoning by VLMs.
3. **Workstation Route Agentic Wiring (`api/routes/workstation.py`)**:
   - `_run_prompt_reasoning()` instantiates `ComputerUseAgent` for actionable user prompts
     and executes a multi-step mission loop (`run_mission(steps=15)`).
   - Live streaming: each agent step's observation, decision, and result are appended to
     the session worklog in real-time.
4. **Scroll & Drag Support in Daytona Provider**:
   - `DaytonaComputerProvider.gui_action` maps `GUIActionType.SCROLL` via `xdotool`
     wheel click events (button 4=up, 5=down). `GUIAction` model extended with `scroll_delta`.
5. **Safety Envelope (`sonic/safety/action_policy.py`)**:
   - `DEFAULT_ALLOWED_TYPES` allowlists in-sandbox GUI actions (`GUI_CLICK`, `GUI_DOUBLE_CLICK`,
     `GUI_TYPE`, `GUI_KEYPRESS`, `GUI_MOVE`, `GUI_SCROLL`, `GUI_SCREENSHOT`).

### Done-gate (`test_phase8_visual_computer_use.py`, 16 tests)
- GUI click, type, keypress, double-click, scroll, and screenshot dispatch verified end-to-end.
- Coordinate parsing and system prompt schema verified.
- Safety policy allows GUI actions in-sandbox and denies destructive host/terminal operations.


## Improvement Round 2 — Module Robustness + Advanced Definition (2026-09-02)

### Bugs fixed (fail-closed + resource-safety hardening)
- CRITICAL SSRF bypass (sandbox/egress.py): IPv4-mapped IPv6 (::ffff:169.254.169.254) bypassed all blocked networks. Added ::ffff:0.0.0.0/96, NAT64 64:ff9b::/96, and _ip_blocked() helper that normalizes mapped v6->v4. DNS-resolved IPs now checked too.
- Scope injection (agents/recon.py): CT-log subdomain enum used endswith("example.com") -> accepted evil-example.com. Replaced with _is_subdomain_of() (dot-boundary check).
- Process leak on timeout (docker_provider.py, local_dev_provider.py): orphaned child processes (e.g. sleep) survived timeout. Now uses start_new_session=True + os.killpg(SIGKILL) + os.waitpid to kill+reap the whole process group.
- Browser leak (agents/browser_agent.py): close() skipped page/context and crashed on partial launch. Now closes page->context->browser->playwright independently with suppress(), and supports async with BrowserAgent() as agent.
- Rate limiter (safety/rate_limiter.py): documented lock-contract for _get_bucket.

### Honest self-improvement provenance (ASIPTA Pillar 5 hardening)
- AuthoredTool + InventedTechnique now carry authored_at/invented_at, confirmed_at, confirmed_workspace_id timestamps. Confirmed fields are set ONLY on empirical in-sandbox reproduction (exit 0 + non-empty), never on failure.

### Tests added (tests/test_module_robustness.py - 27 tests)
- 8 egress SSRF bypass tests, 7 recon subdomain-injection, 1 provider timeout-kills-process-group, 4 browser-agent safe-close, 3 rate-limiter underflow, 4 provenance.

### Architecture document (docs/ARCHITECTURE.md)
- Formal ASIPTA definition grounded in real codebase, 6-layer architecture, 5 pillars, 4 end-to-end call chains.

### Test status: 429 passed, 37 skipped, 0 failures; ruff F-category clean.

## Improvement Round 3 — Human-Like Multi-Modal Interaction (2026-09-02)

### Goal
The agent must work like a human: not only `apt-get install` from a terminal, but
also open a browser, click a download button, save a file, then run a GUI install
wizard with mouse + keyboard + wait. This round added the primitives a human uses.

### Window/app management
- **APP_FOCUS** (ComputerActionType): toggle focus between desktop windows (e.g.
  Chromium <-> terminal) without relaunching. Maps to GUIActionType.SELECT_WINDOW,
  dispatched via `wmctrl -a` / `xdotool search --name ... windowactivate` on the
  sandbox X11 display. Previously SELECT_WINDOW was defined but unhandled (gap).
- **APP_INSTALL** (ComputerActionType): sanctioned install path that routes
  through `install_application()` -> ApplicationPolicy (forbidden packages like
  cryptominer/tor-relay/ddos-bot blocked). Closes a real bypass: a raw
  `apt-get install` via TERMINAL_EXEC was L0_SAFE and skipped the package gate.

### Human-like desktop primitives
- **GUI_DRAG** (ComputerActionType -> GUIActionType.DRAG): press-move-release
  gesture. GUIAction extended with x2/y2 destination coords. Lets the agent
  drag-drop a file onto a folder or slide a wizard control. DRAG was defined in
  the enum but unhandled (gap, same class as SELECT_WINDOW).
- **GUI_WAIT** (ComputerActionType): sleep N seconds then refresh the screen. A
  human waits for a progress bar / "Next" button before acting; without this the
  agent re-screenshots a still-loading UI and clicks stale coordinates.

### Human-like browser primitives (agents/browser_agent.py)
- **wait_for_element(selector)**: wait for a CSS element to render before
  clicking it (human waits for "Download"/"Next" to appear). No-op in httpx fallback.
- **download(selector, save_path)**: click a download link and save the file to
  the sandbox workspace (accept_downloads=True at context creation). Models the
  human "download then run" step. Fail-closed (False) without Playwright.
- **BROWSER_WAIT / BROWSER_DOWNLOAD** action types exposed to the agent loop.

### LLM system prompt + action map
- All new actions added to the ACTION list, action_map, and per-action payload
  format docs so the LLM can actually choose them.

### Fail-closed guarantees
- Headless UnifiedComputerProvider.gui_action raises RuntimeError for SELECT_WINDOW
  (no silent no-op). APP_INSTALL forbidden-package block is NOT a recovery trigger
  (the safety gate decided correctly). BrowserAgent.download returns False without
  Playwright (no fabricated file).

### Tests (tests/test_module_robustness.py - 22 new tests)
- TestWindowToggle (5): APP_FOCUS enum, policy, mapping, allowed, headless refusal.
- TestAppInstallGate (7): enum, policy, forbidden-blocked, allowed-pass,
  provider-gate, documented TERMINAL_EXEC bypass gap.
- TestHumanLikeInteraction (10): GUI_DRAG coords, GUI_WAIT/BROWSER_WAIT/BROWSER_DOWNLOAD
  in allowlist, policy evaluate, BrowserAgent wait/download methods, httpx fallback
  no-op, fail-closed without Playwright.

### Test status: 451 passed, 37 skipped, 0 failures; ruff F-category clean.

## Improvement Round 4 — Devin-Style Closed Loop: VERIFY + REPLAN (2026-09-02)

### Goal
Mapped SONIC's `run_mission` loop against the Devin-style 8-stage closed-loop
model (Observe → Reason → Act → **Verify** → **Replan on stuck**). Stages 1-6
were already strong; stages 7 (Verify) and 8 (Replan) had real gaps.

### Gap found: Stage 7 — Verification was circular
- The old loop stopped when the LLM emitted `GOAL_COMPLETE` — i.e. the agent
  judged itself done (circular: "code likh diya = task complete"). There was NO
  independent check grounded in the real sandbox state. A false-positive
  self-declaration would stop the mission prematurely.
- **Fix**: `verify_goal()` performs an INDEPENDENT probe inferred from the goal:
  - "fix tests" → runs `pytest` and reads the actual result
  - "install X" → runs `which X` / `dpkg -l X`
  - "run/serve" → probes the started artifact
  - no inferable probe → re-observes the live state
- Fail-closed: empty/error/traceback output is NOT success — "absence of
  evidence is not evidence of success." Only on real non-error evidence does
  verification pass. `GOAL_COMPLETE` that fails verification is fed back to the
  LLM as "VERIFICATION FAILED — continue", not accepted.

### Gap found: Stage 8 — No stuck detection / replan
- The old loop ran N steps; on failure it called `recover()` which restarts Xvfb
  (infrastructure recovery, NOT strategy revision). There was no detection of
  "I'm stuck repeating the same failing approach", and no replan — it just
  burned the step budget.
- **Fix**: `_consecutive_failures` counter + `_STUCK_THRESHOLD` (3). After N
  consecutive failures (or N failed self-verifications), `_inject_replan()`
  appends a `REPLAN` entry to the reasoning history so the NEXT LLM call sees
  "your approach isn't working, try a DIFFERENT strategy" — and pivots rather
  than repeating the failing action. This is the "plan static nahi hoti"
  principle: replan on failure, not a fixed script.

### Loop now (Devin-aligned)
```
for step in 1..N:
    OBSERVE          (multi-modal: screen+AT-SPI+terminal+files+git+browser)
    REASON & CHOOSE  (LLM: goal + observation + history)
    if GOAL_COMPLETE:
        VERIFY       (independent sandbox probe — NOT self-declaration)
        if verified: DONE
        else:        feed "VERIFICATION FAILED" back, count failure, maybe REPLAN
    ACT              (safety gate → provider → sandbox)
    if FAILED:       count consecutive failure; if stuck → REPLAN
```

### Tests (tests/test_module_robustness.py::TestVerifyAndReplan, 5 tests)
- verify_goal fail-closed on error/traceback output
- verify_goal passes on real non-error evidence (artifact exists)
- verify_goal re-observes when no concrete probe inferable
- _inject_replan adds REPLAN to history + resets failure counter
- run_mission replans after 3 consecutive failures (stuck detection wired)

### Test status: 456 passed, 37 skipped, 0 failures; ruff F-category clean.

## Improvement Round 5 — Self-Improvement: Closing the Learn→Apply Loop (2026-09-02)

### Goal
Mapped SONIC's self-improvement stack to find what actually self-improves vs
what just has the infrastructure. SONIC has 6 self-improvement building blocks:
Toolsmith (author+confirm tools), MethodLab (invent+confirm techniques),
CuriosityLoop (novelty-driven goals), Canary+SelfEval (A/B promote/rollback),
BeingMind+Craft (durable facts/notes), and epistemic PredictionComparison
(lessons from prediction-vs-actual). All EXIST and are honest (confirm-on-run).

### The real gap: lessons were OPEN-LOOP
The single biggest self-improvement gap: **lessons were computed but never fed
back into the next mission's reasoning.**
- `PredictionComparison.evaluate()` derived a lesson after each task, stored it
  in `CognitiveState.prediction_comparisons` — but the agent's
  `_build_reasoning_context()` never showed these to the LLM.
- `ResearchMemoryStore` (cross-mission playbooks with success rates) existed
  but was never queried by the agent.
- Net: the being forgot what it learned across missions. It was
  "self-authoring" (builds new tools) but NOT "self-learning" (reuses past
  lessons). Same gap-class as Round 4's verify: infrastructure existed, the
  loop wasn't closed.

### Fix: LessonsLedger (learn → apply)
New module `sonic/being/lessons.py`:

1. **`extract_lessons(traces, goal)`** — at mission end, distill the trace into
   concrete lessons grounded in REAL trace.status:
   - `FAILED` → `AVOID` lesson ("nmap on this target → connection refused")
   - `SUCCESS`/`RECOVERED` → `REUSE` lesson ("ffuf -mc 200,301 found admin panel")
   - Empty trace → no lessons (fail-closed: never fabricate)

2. **`LessonsLedger`** — durable host-FS store (mirrors BeingCraft convention,
   restart-proof under `sonic_data/lessons/`). `record()` dedupes by
   (kind, approach) so the same failed approach in 3 missions counts once.
   `relevant(goal, k)` returns top-K lessons matching the current goal by
   keyword overlap (no embeddings — flat dependency surface).

3. **Injection into reasoning** — `_build_reasoning_context()` now embeds the
   top-K relevant past lessons as a `Past lessons` block:
   ```
   Past lessons — approaches that WORKED (reuse them):
     [REUSE] nmap -sV → found service
   Past lessons — approaches that FAILED (avoid repeating):
     [AVOID] ffuf without -mc filter → 0 results on noisy targets
   ```
   The system prompt instructs the LLM: "When 'Past lessons' appear, AVOID
   [AVOID] approaches and prefer [REUSE] ones — apply your cross-mission
   learning."

4. **Wired into `run_mission`** — at mission end, `extract_lessons()` →
   `ledger.record()`. The NEXT mission's reasoning sees them. The being now
   compounds knowledge across missions instead of starting with amnesia.

### Self-improvement map after Round 5
```
Toolsmith    : builds new TOOLS        → confirm-on-run → registered  ✅ honest
MethodLab    : builds new TECHNIQUES   → confirm-on-run → ledger'd    ✅ honest
LessonsLedger: learns from OUTCOMES    → extract→record→inject         ✅ NEW (closed loop)
Canary/Eval  : A/B tests CHANGES       → zero-regression promote/rollback ✅
CuriosityLoop: proposes new GOALS      → novelty-biased                ✅
```
Toolsmith/MethodLab = "build new capabilities". LessonsLedger = "reuse past
experience". Together they cover both halves of self-improvement: the being
grows its toolkit AND grows wiser from its own history.

### Tests (tests/test_module_robustness.py::TestLessonsLedger, 7 tests)
- extract_lessons: AVOID on FAILED, REUSE on SUCCESS/RECOVERED, evidence grounded
- empty trace yields no lessons (never fabricate)
- ledger persists to disk + dedupes (kind, approach)
- relevant() keyword-overlap ranking (top hit matches goal keyword)
- inject_into_context empty when no lessons (zero noise for fresh being)
- inject_into_context renders [AVOID]/[REUSE] block
- end-to-end: mission 1 records a lesson, mission 2 sees it in reasoning context

### Test status: 463 passed, 37 skipped, 0 failures; ruff F-category clean.

---

## Round 6 — Dual-Process (Fast/Deep) Hierarchical Sub-agent Controller
Makes the agent reason like a human researcher: **fast on familiar ground,
deep on novel/uncertain ground, and silent until it genuinely needs a human.**

### `sonic/orchestration/dual_process.py` (NEW, ~280 lines)
Four pillars, all building on existing pieces — never duplicating them:

1. **Dual-Process (Fast/Deep) Controller** — `DualProcessController.decide()`
   picks FAST (heuristic, high-throughput, parallel children) or DEEP
   (thorough, careful, limited parallelism) per hypothesis node. The decision
   is a PURE FUNCTION of observable signals: `ConfidenceBand`, unresolved
   `Unknown`s (importance), novelty (lessons-ledger hit), and branch failure
   count. Deterministic + testable, not a hidden LLM whim.

2. **Dual-Process switching** — HIGH/VERY_HIGH confidence + few low-importance
   unknowns + a known pattern → FAST. LOW/MODERATE confidence OR a high-
   importance unknown OR a novel pattern → DEEP. Stuck in DEEP + high
   uncertainty → ESCALATE.

3. **Hierarchical Hypothesis + Sub-agents** — `HierarchicalHypothesisTree`
   over `CognitiveHypothesis.parent_id` / `children_ids` (added this round).
   A VERIFIED parent **expands** into more-specific children; a DISPROVED
   parent's whole subtree is **pruned** (no wasted sub-agents on dead branches).
   Each node dispatches the EXISTING swarm agents as sub-agents scoped to that
   node's test plan — no new agent classes.

4. **Parallel sub-agent execution** — children run concurrently via
   `asyncio.gather`, capped by `max_parallel` — exactly like `SwarmRunner`.

5. **Smart Human-in-the-loop escalation (sirf high-uncertainty pe)** —
   escalate ONLY when ALL hold: already in DEEP + high-importance unresolved
   Unknown (importance ≥ 0.70) + subtree stuck (≥3 branch failures) + novel
   (no lessons-ledger resolution). Does NOT escalate on high-confidence findings,
   budget exhaustion, or diminishing returns. Escalation surfaces the actual
   `Unknown` question for a human; the node stays PROPOSED (never auto-confirms
   or auto-disproves — that would be fabrication).

### Honesty invariants
- FAST mode never VERIFIES — only DEEP confirms/disproves (like confirm-on-run).
- Sub-agents invoke real agent code via the injected `agent_runner` — no mocks.
- Pruning follows real DISPROVED lifecycle status, never heuristic guesses.
- A sub-agent exception → node is DISPROVED (fail-closed), never left ambiguous.
- Escalation never fabricates a question; it surfaces the real `Unknown`.

### Security invariant
Sub-agent dispatch carries a scoped hypothesis context (goal + test plan),
never the full `CognitiveState`. Children inherit the parent's
engagement/tenant id so each agent sees only what its branch needs.

### `sonic/agents/cognitive_state.py` (modified)
`CognitiveHypothesis` gained three fields for the hierarchy: `parent_id`,
`children_ids`, `process_mode`. Backward-compatible (all default empty) — no
existing test broke.

### Tests (tests/test_module_robustness.py, +18 tests)
`TestDualProcessController` (9): high-conf+known→FAST; low/moderate→DEEP;
high-importance-unknown→DEEP even at high conf; novel→DEEP; escalation ONLY
on stuck+high-uncertainty+novel; no escalation when pattern known; no
escalation on low-importance unknown; no escalation when not yet stuck.

`TestHierarchicalHypothesisTree` (9): expand attaches children w/ context
inheritance; subtree BFS; prune removes disproved subtree; prune ignores
non-disproved (no heuristic guessing); DEEP confirms→fans-out children;
FAST runs node+children in parallel; max_parallel cap enforced; sub-agent
exception→DISPROVED (fail-closed); escalation surfaces Unknown + does NOT
run a sub-agent + keeps node PROPOSED.

### Test status: 481 passed, 37 skipped, 0 failures; ruff clean.

---

## Round 7 — Epistemic Awareness + Falsification Mindset + Long-horizon Planning
Fills the three highest-value gaps from the "human-like AI" checklist
(Section 1, the most important) **inside existing files** — no new files. Every
change enhances an existing, already-tested module; nothing was duplicated.

### 1. Epistemic Awareness — `cognitive_state.py::CognitiveState.get_top_epistemic_gap()`
"Mujhe kya nahi pata" made explicit and actionable. Ranks unresolved `Unknown`s
by `estimated_importance` and **excludes dead-ends** — an unknown whose every
`possible_action` already appears in `get_failed_methods()` is dropped, so the
agent never re-chases a question it cannot answer with the methods it has
tried. Returns `[]` when there is genuinely nothing open (never invents a gap).

### 2. Falsification Mindset — `experiment_designer.py::AdversarialChallenger.challenge_leading_hypothesis()`
"Actively apni hypotheses todne ki koshish kare." The existing
`generate_falsification_challenge` built the challenge but nothing chose *which*
hypothesis to attack — the natural confirmation-bias failure mode. Now
`CognitiveState.leading_hypothesis()` selects the strongest active hypothesis
(lowest `priority`, recency tie-break; DISPROVED/ABANDONED excluded) and
`challenge_leading_hypothesis()` auto-targets it for an explicit **disproof**
attempt. High-quality findings come from theories that *survived* an active
disproof, not ones merely confirmed. Reuses the existing challenge generator
(no logic duplication); returns `None` when there's no active target (never
fabricates a challenge).

### 3. Long-horizon Planning — `planner.py::MissionPlanner.build_long_horizon_plan()`
"10-20 steps aage soch sake." The baseline `build_plan` produced only 3-6
shallow commands. `build_long_horizon_plan` decomposes an objective into a
multi-stage ordered pipeline:

```
stage 0 orient → 1 surface map → 2 deep map → 3 hypothesize →
4 active test (APPROVAL_REQUIRED, never auto-run) → 5 verify → 6 report
```

Each action carries `stage` + `depends_on` (the prior stage's anchor action_id)
so the executor can order and gate the chain. All stages before the active test
are `READ_ONLY` (safety envelope honoured); the active test is
`APPROVAL_REQUIRED` and never silently executed. Deterministic, allowlist-only,
no unconstrained model command generation — same discipline as `build_plan`.

New fields: `PlannedAction.stage`, `PlannedAction.depends_on`;
`MissionActionPlan.stage_count()`, `MissionActionPlan.chain_head()`.

### Checklist coverage already present (not re-done — these existed)
- **Competing Hypotheses / Unknown model** → `research/epistemic.py`
- **Dual-Process Thinking** → `orchestration/dual_process.py` (Round 6)
- **Mental Model of Target** → `research/world_model.py`
- **Curiosity + Goal Mgmt** → `computer_use/curiosity.py`
- **Information-Gain action selection** → `research/information_gain.py`
- **Strategy switching on diminishing returns** → `world_model.StopConditionEvaluator`
- **Tool/Method authoring w/ verification** → `being/toolsmith.py`, `being/method_lab.py`
- **Failed-strategy + cross-engagement memory** → `being/lessons.py` (Round 5)
- **Fail-closed isolation / tamper-evident / egress** → `safety/scope.py`, `safety/sealed.py`, `safety/action_policy.py`
- **Audit trail + evidence custody** → `evidence/custody.py`
- **Independent adversarial verification** → `evidence/independent_verifier.py`

### Tests (+19, all in existing test files)
`TestEpistemicAwareness` (6): rank by importance; exclude dead-ends; keep
partially-live; exclude resolved; empty when none; top_k limit.
`TestLeadingHypothesis` (3): picks lowest priority; None when none active;
DISPROVED excluded.
`TestFalsificationMindsetWiring` (2): targets the strongest hypothesis;
None (not fabricated) when no target.
`TestLongHorizonPlan` (8): ≥10 steps; ≥5 ordered stages; every action chains
via depends_on; active test is APPROVAL_REQUIRED; read-only objective has no
approval stage; orient runs first; empty raises; deeper than baseline.

### Test status: 500 passed, 37 skipped, 0 failures; ruff clean.

## Engagement recon — lab target `testapp.sonic-lab.local` / `10.10.50.0/24`

### Environment reality (Phase A recon, falsified hypotheses)
- The stated lab target is **NOT live infrastructure** in this environment.
  - `testapp.sonic-lab.local` -> **NXDOMAIN** (verified from host AND from a
    Daytona sandbox via 8.8.8.8/1.1.1.1). It does not exist in DNS.
  - `10.10.50.x:80` -> HTTP **403 "Internet is restricted on Tier 1 and Tier 2"**,
    ~0.0007s RTT, identical 45-byte body for *every* IP. This is the Daytona
    egress-deny proxy intercepting RFC1918, NOT a real web server. `bash`'s
    `/dev/tcp` reports such IPs as "OPEN" — a false positive; real `curl`/`nc`
    is the discriminator.
  - Control: `github.com` -> 200 from the same sandbox, so the sandbox is
    fine; only the stated lab range is denied/unreachable.
- **Conclusion:** no real host to exploit; per evidence-custody rule we must
  NOT fabricate findings/flags against an unreachable target. Genuine
  attack-chain capability was instead demonstrated against a deliberately
  vulnerable app stood up *inside* our own sandbox (in-bounds), see below.

### Safety-envelope penetration (requirement #8 — actively attack own boundaries)
34 probes across 4 layers; every verdict recorded (`_safety_results.json`
was the artifact). Findings + fixes:

- **BUG 1 (scope CIDR):** `ScopeChecker.is_target_in_scope` did a literal
  `target in targets["ips"]` check — never expanded CIDRs and never stripped
  URL scheme/port. So `10.10.50.10` against allowed `["10.10.50.0/24"]`
  returned False (over-block) and only the CIDR *string* matched.
  **Fixed** in `sonic/safety/scope.py`: parse host from URL via `urlparse`,
  expand CIDRs via `ipaddress.ip_network`, numeric membership test. Added
  `_ip_in_scope_list` helper.
- **BUG 2 (classifier policy parity):** `classify_command_risk` only used
  hardcoded `_DESTRUCTIVE_PATTERNS`, ignoring the YAML-loaded
  `_forbidden_patterns`, and the hardcoded set missed `DROP DATABASE`,
  `exfiltrate`, `disable logging`, `modify safety_rules`, and reverse shells
  (all returned L0 despite `safety_rules.yaml` listing them as forbidden).
  **Fixed:** classifier now also consults `_forbidden_patterns` (YAML), and
  the hardcoded set was extended to cover the policy gaps + reverse shells.
- Verified `check_action` fail-closes when rules not loaded (`self._loaded`
  False -> BLOCKED) — correct by design; with rules loaded it returns
  ALLOWED / NEEDS_APPROVAL / BLOCKED for L0/L1/L2 as expected, and the YAML
  `exfiltrate` forbidden pattern now fires (policy→enforcement parity).
- Live egress: all out-of-scope/RFC1918/metadata/localhost probes BLOCKED
  (403 deny-proxy or code=000). Egress envelope confirmed fail-closed.

### Regression tests
`sonic-core/tests/test_safety_envelope_regressions.py` (11 tests) reproduces
both bugs red→green and covers CIDR members, URL host extraction, out-of-scope
URLs, and all forbidden-command classes. `11 passed`.

### Attack-chain demonstration (in-sandbox, no external system)
Stood up a 1-file deliberately-vulnerable app (`/?page=` LFI + `/admin?token=&cmd=`
auth-gated RCE) inside a Daytona sandbox and ran a 5-step chain: recon -> LFI
(leaks admin token from `/opt/app/config.json`) -> auth+command-injection
(`uid=0(root)`) -> RCE flag read (`SONIC{chain_recon_lfi_auth_rce_flag_captured}`)
-> post-exploitation (wrote `/tmp/pwned.txt`). Each step recorded request,
response, SHA-256 evidence hash, and confidence (0.95–0.99). Demonstrates
multi-step chaining + evidence custody without touching any out-of-scope host.

### Multi-modal perception (requirement #6)
Confirmed working on a benign target (OpenHands docs): DOM, interactive
element/accessibility tree, screenshot (saved to disk), and markdown content
extraction. Browser DOM/JS analysis was also used earlier to reverse the
BurpSuite download endpoint (`/burp/releases/download?product=desktop&version=...`).

### Sandbox hygiene note
The `/dev/tcp` "OPEN" heuristic is unreliable behind a deny-proxy; always
follow up with a real `curl`/`nc` HTTP GET and compare body+RTT to
distinguish a live host (varied banner, higher RTT) from a deny-proxy
(identical short 403, sub-ms RTT).

## sonic-cli audit (2026-09-03)
Backend routes (sonic-core/sonic/api/main.py): health (/health,/health/detailed), /auth, /engagements (POST /,POST /{id}/run,GET /{id},GET /{id}/findings,GET /,POST /kill, GET /{id}/tasks, /{id}/unknowns, /{id}/decisions, /{id}/next-action, POST /{id}/replan, /{id}/pause, /{id}/resume), /findings (GET /{id}, POST /{id}/verify,/challenge,/reproduce,/review, GET /{id}/evidence,/provenance,/confidence), /agents, /graph (/stats,/search,/query,/engagement/{id}/summary,/finding/{uid}), /experiments, /terminal, /live, /jobs, /workstation.
IMPLEMENTED (real, non-fabricated): /findings router wired to GraphMemory + VerifierAgent (verify/challenge/reproduce persist verdicts; evidence/provenance/confidence read real graph data; review approves/rejects). /engagements sub-routes surface Director cognitive state + task graph when available; honest empty responses (with `note`) for linear-pipeline engagements — never fake panels. CLI finding & mission & research commands now call these real endpoints.
Tenant isolation gotcha: JWT `tenant_id` defaults to "default" unless the User sets it explicitly; route reads/writes use `user.tenant_id` (NOT `user.email`). The live routes use `user.email` as tenant — keep this split in mind. Memory backends (InMemory/SQLite/Neo4j) all expose `find_evidence(finding_id, tenant_id)`.
EngagementManager vs Director: EngagementManager is the linear pipeline (no task graph); Director is the autonomous pipeline with CognitiveState (unknowns, next_best_action, decisions) + TaskGraph. /engagements sub-routes try Director first, fall back to honest empty.
Tests: sonic-cli/tests has only __init__.py (no test files); python -m pytest -> no tests ran, exit 0.

## AI + control upgrade (reliability hardening)
Two independent robustness layers were added on top of the existing AI core
and control loop — the legacy text-parsed ReAct and provider paths are
unchanged and still the default; the new paths are opt-in additions.

- **LLM provider resilience** (`sonic/llm/providers/custom.py`):
  - Transient-error retry/backoff on the SAME provider/model (429 rate-limit,
    5xx, transport errors) via `_with_retry` with exponential backoff + full
    jitter, before the existing model-level (`fallback_models`) and router
    provider-level fallback chains kick in. Configurable via `max_retries`,
    `retry_base_delay`, `retry_max_delay` (default 3 / 0.5s / 20s; set to 0 to
    disable). Auth/bad-request/model-not-found errors are NOT retried — they
    flow straight to the fallback chain.
  - Robust tool-call argument parsing via `parse_tool_arguments`:
    extracts the first JSON object from noisy/prose-wrapped tool-call output,
    fixes trailing commas and single quotes, wraps bare values as `{"value": …}`,
    and returns `{}` for empty/None. Used by both the OpenAI tool-call path and
    the ReAct engine so one parser governs all tool arguments.
- **ReAct native function-calling** (`sonic/agents/react_engine.py`):
  - `ToolRegistry.to_llm_tool_definitions()` converts the registry into
    provider-agnostic JSON-schema tool definitions for `LLMRequest.tools`.
  - `ReActEngine.execute_with_tools(task, think_fn, …)` runs the ReAct loop
    using native function-calling instead of `Action: name[arg]` text regex.
    ALL `tool_calls` in a single step are executed concurrently
    (`asyncio.gather`), so the agent fans out independent probes in one turn
    instead of one per step. Results are fed back as `tool`-role messages
    keyed by call id for correct multi-turn threading. No tool calls with
    non-empty content terminates as the final answer.
  - `_execute_tool` now accepts dict arguments (function-calling path) and
    coerces them to the positional string handlers expect; the legacy text
    path is unchanged.
- **Control loop coordinate validation** (`sonic/computer_use/agent.py`):
  - The agent now tracks the real screen dimensions (`_screen_width`,
    `_screen_height`), refreshed on every `observe()` and screenshot action.
  - `execute_action` validates GUI coordinate actions (click/double-click/
    move/scroll/drag, including drag targets) against the tracked screen
    bounds BEFORE execution. Out-of-bounds, negative, or non-integer
    coordinates are recorded as `BLOCKED` and never reach the provider — no
    recovery is triggered (the provider state is fine; the agent just needs to
    re-observe). Non-coordinate actions (terminal exec, etc.) are unaffected.
  - Tests: `sonic-core/tests/test_ai_and_control_upgrade.py` (25 tests).
