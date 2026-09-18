# AI Agent Onboarding & Codebase Orientation Guide

> **Target Audience**: Any AI Agent (Claude, GPT, Cursor, Devin, Windsurf, Aider) working on this repository.  
> **Project**: SONIC (Autonomous Computer-Using Researcher)
> **Repository Root**: `c:\Users\nandk\_society`  
> **Last Updated**: September 2026 (Phase 22 Active)

---

## ⚡ 60-Second Mental Model (Read This First!)

SONIC is a general-purpose computer-using researcher. Its product scope is
ordinary GUI computer-use and isolated sandbox engineering; offensive
cybersecurity workflows are not part of this repository.
SONIC operates its own dedicated local graphical Linux Workstation inside Docker
(`sonic-desktop-workstation`) and a separate headless sandbox execution plane.

### The 4 Golden Invariants (NEVER VIOLATE):
1. **ZERO Host Execution**: Never run task commands on the host operating system
   (Windows). All terminal, file, git, and process execution MUST happen inside
   the headless sandbox via `DockerComputerProvider` or `ComputeProvider`.
2. **Strict Plane Separation**: The Computer plane is GUI/application-only
   (screenshots, windows, mouse, keyboard, and application actions). The
   Sandbox plane is terminal/file/git/process-only. Both planes must remain
   active; legacy `gui_only` and `observe_desktop=False` settings cannot disable
   either plane.
3. **Foundation Scope**: Do not add cybersecurity assessment, scanning,
   exploitation, security-tool execution, or target-attack workflows. Research
   means ordinary computer, software, document, and test work.
4. **Fail-Closed + Real Evidence**: Any policy breach or unrecognized action
   blocks with exit code `126`; completed tasks require real GUI or Sandbox
   evidence, never an LLM claim.

---

## 🗺️ Codebase Map & Where Everything Lives

```
c:\Users\nandk\_society/
├── sonic-core/                         # Python Backend (FastAPI, Python 3.12+)
│   ├── sonic/
│   │   ├── computer/                   # 🖥️ Computer & Sandbox Providers
│   │   │   ├── docker_computer.py      # [PRIMARY] Docker Workstation Provider (XFCE4, noVNC :6080)
│   │   │   ├── docker_sandbox.py       # Duck-typed adapter for legacy Daytona SDK callers
│   │   │   ├── daytona_computer.py     # [LEGACY FALLBACK] Old Daytona Cloud provider
│   │   │   └── models.py               # Data structures (GUIAction, FileEntry, etc.)
│   │   ├── computer_use/               # 🧠 Multimodal Computer-Use Agent
│   │   │   ├── agent.py                # Core observe -> reason -> act -> verify loop
│   │   │   ├── perception_bus.py       # Versioned live state and incremental change events
│   │   │   ├── grounding.py            # Visual grounding for unresolved UI targets
│   │   │   └── models.py               # Traces, observations, metrics
│   │   ├── safety/                     # 🛡️ Sealed Safety Envelope
│   │   │   ├── action_policy.py        # Allowed action types, rate limits, command classifier
│   │   │   └── sealed.py               # SHA-256 sealed immutable policy
│   │   ├── research/                   # 🔬 Neutral epistemic and planning primitives
│   │   └── api/routes/                 # 🌐 FastAPI Endpoints
│   │       ├── workstation.py          # Workstation desktop, VNC streaming, session control
│   └── tests/                          # 🧪 Pytest Test Suites
│       ├── test_docker_computer_provider.py
│       ├── test_docker_workstation_adapter.py
│       ├── test_visual_grounding.py
│       └── test_workstation_interrupt_and_resilience.py
├── sonic-dashboard/                    # 🖥️ Frontend (Next.js 14, React, Tailwind)
│   └── components/computer/
│       └── ComputerSurface.tsx         # Live VNC container (port 6080) & takeover controls
├── scripts/                            # 🚀 Operational Scripts
│   └── launch_agent.py                 # Standalone script to launch autonomous agent
├── docker/
│   └── entrypoint-workstation.sh       # Container entrypoint (Xvfb :99, x11vnc, noVNC, Chrome wrapper)
├── configs/
│   └── models.yaml                     # LLM Model Routing table
├── AGENTS.md                           # Comprehensive historical memory (Phases 1-22)
├── BLUEPRINT.md                        # Master architectural blueprint & glossary
└── SYSTEM_CHANGES_SUMMARY.md           # Detailed changelog & operational guide
```

## Continuum implementation roadmap

SONIC's foundation is delivered through these saved phases:

0. Scope/correctness and foundation-only cleanup.
1. Reliable Computer/Sandbox primitives and dual-plane execution.
2. Versioned perception cache with deduplication, patches, subscriptions, and
   stale-action invalidation.
3. Empirical latency and outcome measurement.
4. Provider-neutral event adapters for desktop, windows, accessibility/browser,
   filesystem, processes, and sandbox completion.
5. Structured perception before screenshot/OCR fallback.
6. Incremental visual-region processing.
7. Low-risk, already-grounded reflex execution.
8. Fast/deep reasoning selection and failure replanning.
9. Reversible predictive preparation with state-confirmed commit.
10. Independent action verification and reality-grounded replanning.
11. Persistent owned-computer lifecycle and operator takeover.
12. Long-horizon general research, memory, and self-correction.
13. Production gates for correctness, isolation, restart recovery, and honest
   latency.

Current checkpoint: provider-backed desktop/filesystem/process/browser
perception, the empirical benchmark, grounded reflex execution, and a first
Fast/Deep routing slice are implemented. A prepared reversible GUI action uses
the current perception snapshot without an unnecessary LLM round-trip; stale,
ambiguous, or irreversible actions still use deep reasoning. Extend adapters
only through provider APIs; do not invent event sources or use host-side
commands to simulate them.

Latest run: **528 backend tests passed, 27 live-infrastructure tests skipped**;
backend compilation and `git diff --check` passed. The generic foundation
end-to-end contract passes, and the graph speed benchmark now uses a
mutation-invalidated query cache for repeated shortest-path work. Phase 7-12
currently have initial slices:
grounded reflexes, Fast/Deep routing, predictive state, and action-level
reality commit, plus tenant-safe Docker workspace reconnect. Remaining work in
these phases and Phase 13 is still
planned and must not be reported as complete without implementation and tests.

Docker validation note: the local Docker daemon and graphical workstation are
running. The test gate now accepts Docker Compose-prefixed network names such
as `society_sonic-sandbox-net`. The headless `DockerProvider` explicitly
overrides the graphical workstation image entrypoint with `/bin/bash`, so
ComputeProvider workspaces remain alive without VNC configuration. GUI tests
must use `DockerComputerProvider`; the generic headless provider correctly
returns `NO_DISPLAY` and must not manufacture screen data.

The Docker-aligned Phase 13 and Phase 14 contract suites are green. Their
tests now distinguish headless sandbox operations (terminal, files, processes,
git, service commands) from graphical workstation operations (screen capture,
windows, and GUI actions), and no longer assert legacy fake desktop state.

Phase 4 now has a real structured-event adapter in
`sonic/computer_use/perception_adapters.py`. It consumes an injected async
event source and applies only validated perception patches to `PerceptionBus`;
it never polls, screenshots, invents events, or executes host commands.
`DockerContainerEventSource` is the concrete Docker implementation: it reads
`docker events` for one container and emits only truthful lifecycle states
(`CREATED`, `RUNNING`, `PAUSED`, `STOPPED`, `DESTROYED`) into the snapshot's
`runtime_state`. It does not claim filesystem or in-container process events;
those remain provider-backed snapshots.

Phase 5/6 foundation is now present as well. Perception snapshots expose the
real structured sources that contributed state and preserve browser DOM/window/
process/filesystem precedence metadata. `ScreenObservation.changed_regions` and
the bus's `visual_residuals` carry only provider-supplied damage rectangles;
the system never derives fake residuals from arbitrary pixel coordinates.

Phase 7/8 routing is now explicit in the live loop. `FastDeepController`
classifies a prepared action as `FAST` only when its target is current,
high-confidence, and reversible; non-reflex, missing, or ambiguous actions
return `DEEP` without reaching the provider. The mission loop then continues
through normal fresh observation and reasoning, preserving policy and stale
target checks.

Phase 9 predictive preparation is version-bound. `PreparedAction` stores the
originating perception version, and the controller refuses FAST execution when
that version is stale. `ComputerUseAgent.prepare_reflex_action()` rejects
non-reversible actions, so speculative preparation cannot become an
unverified terminal or file mutation.

Phase 10 reality commit is now fail-closed. Decision traces record
`reality_commit` and `verification_source`; only successful actions with a
relevant post-action perception transition become `VERIFIED`. A failed,
blocked, recovered, or unchanged action cannot be promoted to verified merely
because a later screen update occurred.

Phase 11 lifecycle hardening is complete for the Docker workstation. Persisted
home identity remains tenant-scoped and reconnectable across provider restart,
but `get_or_create_home()` now probes the real container before returning a
reused or newly restored home. Stopped Docker containers are reported as
`STOPPED`; metadata alone never fabricates a live workstation.

---

## 🔍 Recent Architectural Changes & Context

If you are continuing work, here is what was just completed:
1. **Daytona was Replaced with Native Docker**:
   - Daytona Cloud Tier 1/2 had network connection resets (`HTTP 403 Forbidden`).
   - We created `DockerComputerProvider` (`sonic-core/sonic/computer/docker_computer.py`). It talks directly to container `sonic-desktop-workstation` via `docker exec`.
   - Desktop runs XFCE4 on virtual display `:99` (with `/tmp/.X11-unix/X0` symlink).
   - Live stream is served via `noVNC` on `http://localhost:6080/vnc.html`.
   - All backend workstation routes default to `DockerComputerProvider`.
2. **Visual Grounding (`grounding.py`)**:
   - Extracted bounding-box-to-pixel math from reference repo `e2b-dev/open-computer-use`.
   - `extract_bbox_midpoint()` parses `<|box_start|>(x1,y1,x2,y2)<|box_end|>` and normalized floats `[0.0, 1.0]` into exact coordinates.
   - `open-computer-use/` folder is in `.gitignore`. **DO NOT MERGE IT.** It is only a reference library.
3. **Google Chrome Sandbox Fix**:
   - Running Chrome as `root` in Docker requires `--no-sandbox --disable-dev-shm-usage`.
   - Wrapper `/usr/local/bin/chrome` and `/opt/google/chrome/google-chrome` are configured with these flags.
4. **Agent Self-Verification**:
   - `ComputerUseAgent.run_mission()` has post-mission goal verification. When actions succeed, it checks `verify_goal()` and marks `goal_reached = True` (verification score `1.00`).

---

## 🛠️ How to Test & Run (Terminal Cheat Sheet)

### 1. Run Verification Test Suite (17 Tests)
Always run this to make sure core workstation and grounding logic is intact:
```bash
python -m pytest sonic-core/tests/test_docker_computer_provider.py \
                 sonic-core/tests/test_docker_workstation_adapter.py \
                 sonic-core/tests/test_visual_grounding.py \
                 sonic-core/tests/test_workstation_interrupt_and_resilience.py
```

### 2. Launch the Autonomous Agent
Runs a multi-step autonomous mission inside the Docker workstation:
```bash
python scripts/launch_agent.py
```
Output report is generated at: `reports/workstation_assessment_report.md`.

### 3. Check Live Services
- Workstation Desktop VNC: `http://localhost:6080/vnc.html`
- FastAPI Backend: `http://127.0.0.1:12000/health` (docs at `/docs`)
- Next.js Dashboard: `http://localhost:12001`

---

## ⚠️ Common Pitfalls for AI Agents to Avoid

1. **Do NOT run scanner commands on the host**: Never run `nmap`, `curl <target>`, or exploit scripts in PowerShell or the host terminal. Always dispatch them into the container via `provider.terminal(workspace_id, cmd)`.
2. **Do NOT try to git-merge `open-computer-use/`**: It is an external project. Its useful algorithms are already adapted into `sonic/computer_use/grounding.py`.
3. **Do NOT re-introduce Daytona Cloud as default**: Daytona is legacy fallback only. Default provider must remain `DockerComputerProvider`.
4. **Do NOT remove `--no-sandbox` from Chrome**: Chrome running under root inside Docker will crash immediately without it.
5. **Cached settings**: `get_settings()` in FastAPI is cached via `@lru_cache`. Clear cache when modifying env vars in tests.
