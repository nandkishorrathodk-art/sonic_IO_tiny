# FRONTEND ARCHITECTURE REGRESSIONS

**Date:** 2026-08-28  
**Audit Target:** Architecture regressions introduced during the recent workstation redesign.

---

## 1. Executive Regression Summary

During the recent redesign to build a Devin-like split-pane interface in `app/page.tsx`, the frontend underwent **severe architectural regressions**:

1. **Subsystem Disconnection:**
   - The original multi-page architecture (`/graph`, `/evidence`, `/evolution`, `/security-lab`, `/missions`, `/sandbox`) was completely bypassed.
   - The main landing page `/` was overwritten with a monolithic 982-line file (`app/page.tsx`) that severed connections to the core AI agents (`MissionDirector`, `EvidenceEngine`, `EvolutionEngine`, `ResearchManager`).

2. **Replaced Real Backend Integration with Synthetic Workstation Route:**
   - Instead of integrating with the genuine multi-tenant FastAPI engines (`/agents`, `/engagements`, `/jobs`, `/live/*`), a bespoke temporary router (`sonic-core/sonic/api/routes/workstation.py`) was created.
   - This router uses a static global in-memory state dictionary (`_workstation_state`) seeded with hardcoded strings ("Thought for 3s", "Thought for 20s", "Ubuntu 22.04").

3. **Breakage of Fail-Closed Sandboxing:**
   - The terminal execution in `app/page.tsx` was wired to `POST /workstation/command`, which invokes `subprocess.run(req.command, shell=True)` directly on the host machine.
   - This broke the strict Daytona/Docker isolation invariant enforced by `terminal.py`.

4. **Masking of Disconnected State with Hardcoded Fallbacks:**
   - Every fetch call on the new UI was wrapped in `.catch(() => {})` with massive hardcoded mock fallbacks, making it impossible for a developer or user to know whether the UI is connected to a live backend or rendering fake static data.

---

## 2. Regression Inventory by Component

| Component / Subsystem | Previous / Expected Architecture | Current Redesign State | Regression Impact |
|---|---|---|---|
| **Landing Interface (`/`)** | Realtime mission controller attached to backend orchestrator | Single-file 982-line Devin clone with hardcoded fallback mock state | High: Users see fake agent thoughts and fake PR #19 |
| **Terminal Execution** | Container-bound WebSocket relay strictly inside Daytona sandbox | Unauthenticated host shell execution via `workstation.py` | Critical: Security vulnerability + isolation bypass |
| **Evidence & Findings** | Cryptographic SHA-256 chain from `EvidenceEngine` | Isolated mock page (`/evidence`) disconnected from main UI | High: Evidence engine not visible in workstation |
| **Autonomous Evolution** | Multi-gate promotion & canary benchmarks via `meta/experiment.py` | Disconnected mock page (`/evolution`) | High: Evolution telemetry not linked to main loop |
| **Agent Reasoning Stream** | SSE / WebSocket streaming of auditable action events | `setInterval` polling every 4s with hardcoded text templates | High: No real reasoning stream |
| **Multi-Tenancy** | JWT-authenticated, tenant-scoped database sessions | Unauthenticated single-tenant in-memory dictionary | Critical: Multi-tenancy broken on frontend |
