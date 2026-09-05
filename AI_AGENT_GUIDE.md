# AI Agent Onboarding & Codebase Orientation Guide

> **Target Audience**: Any AI Agent (Claude, GPT, Cursor, Devin, Windsurf, Aider) working on this repository.  
> **Project**: SONIC A-SEA (Autonomous Self-Evolving Penetration Architect)  
> **Repository Root**: `c:\Users\nandk\_society`  
> **Last Updated**: September 2026 (Phase 22 Active)

---

## ⚡ 60-Second Mental Model (Read This First!)

SONIC is an **autonomous AI offensive-security architect**. Unlike typical AI chatbots or prompt wrappers that just run `nmap` and regurgitate LLM hallucinations, SONIC operates its own **dedicated local graphical Linux Workstation** inside Docker (`sonic-desktop-workstation`), perceives the screen and terminal, reasons using multi-modal models, writes custom tools, and **empirically reproduces every security finding inside the sandbox**.

### The 3 Golden Invariants (NEVER VIOLATE):
1. **ZERO Host Execution**: Never run security scans or assessment shell commands on the host operating system (Windows). All execution MUST happen inside container sandboxes via `DockerComputerProvider` or `ComputeProvider`.
2. **Fail-Closed Safety**: Any policy breach, unrecognized action, or egress violation triggers an immediate exit code `126` (`BLOCKED`).
3. **Empirical Evidence Required (No Success-by-Decree)**: An exploit or bug is NEVER marked as confirmed just because an LLM claims it. It must produce a concrete stdout, HTTP status, or test assertion in the sandbox.

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
│   │   │   ├── grounding.py            # Visual Grounding (BBox to pixel math from open-computer-use)
│   │   │   └── models.py               # Traces, observations, metrics
│   │   ├── safety/                     # 🛡️ Sealed Safety Envelope
│   │   │   ├── action_policy.py        # Allowed action types, rate limits, command classifier
│   │   │   └── sealed.py               # SHA-256 sealed immutable policy
│   │   ├── mission_engine/             # 🎯 Mission Director & Trace Synthesis
│   │   │   └── trace_synthesis.py      # Extracts real knowledge & deliverables from traces
│   │   ├── research/                   # 🔬 Epistemic ledger & CodeGraph
│   │   └── api/routes/                 # 🌐 FastAPI Endpoints
│   │       ├── workstation.py          # Workstation desktop, VNC streaming, session control
│   │       └── engagements.py          # Pentest pipeline
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
