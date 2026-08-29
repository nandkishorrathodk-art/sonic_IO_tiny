# SONIC-REDA — FRONTEND REALITY RESTORATION & SECURITY REPAIR PLAN

**Date:** 2026-08-28  
**Phase:** Security + Integration Repair  
**Target:** `sonic-dashboard/` (Frontend Refactor) & `sonic-core/sonic/api/routes/workstation.py` (Backend Hardening)

---

## 1. Executive Summary & Objective

The recent forensic frontend audit proved that the workstation redesign introduced critical security vulnerabilities (host shell execution), broke multi-tenant isolation, disconnected genuine Phase 1–19 backend subsystems, and substituted hardcoded mock/demo data across 11 routes.

This repair plan details the step-by-step restoration of Sonic's real architecture without adding unrequested features or regressing the Devin-style AI Workstation layout.

---

## 2. Priority Findings & Scope of Work

### [P0] Immediate Security & Isolation Fixes
1. **Quarantine & Remove Host Command Execution:**
   - **Finding:** `POST /workstation/command` invoked `subprocess.run(shell=True)` directly on the host machine.
   - **Repair:** Completely eliminate host shell execution. Route all execution through `ComputerProvider` / `ComputeProvider` (Daytona / Docker sandbox). If a sandbox is unavailable, **FAIL CLOSED** (`503 Service Unavailable / Sandbox Not Connected`).
2. **Canonical Authentication & JWT Handling:**
   - **Finding:** Frontend omitted JWT auth tokens; all protected `/live/*` endpoints failed or had to be bypassed.
   - **Repair:** Build `sonic-dashboard/lib/api.ts` and `sonic-dashboard/lib/auth.ts`. Ensure all API and WebSocket requests carry valid JWT authentication headers (`Authorization: Bearer ...` and `?token=...`).
3. **Tenant / Workspace / Session Scoping:**
   - **Finding:** Global shared in-memory dictionary `_workstation_state` leaked state across all browser connections.
   - **Repair:** Scope all backend workstation operations by `tenant_id`, `workspace_id`, and `session_id`. Store sessions in scoped dictionaries keyed by `(tenant_id, session_id)`.
4. **Terminal WebSocket Repair:**
   - **Finding:** Terminal lacked JWT auth and simulated output via local echo when disconnected.
   - **Repair:** Pass JWT in `terminal/page.tsx`, remove local echo simulation completely, and render explicit `DISCONNECTED` / `CONNECTING` states.
5. **Purge Fake Fallback Mocks:**
   - **Finding:** Silent `.catch()` blocks in `page.tsx` and static mock pages created illusion of running AI autonomy.
   - **Repair:** Remove fake PR #19, fake CPU/RAM, fake OS display strings, and fake Devin typing animations. Render explicit `OFFLINE` / `UNAVAILABLE` states.

---

### [P1] Real Subsystem Re-Integration
1. **Worklog & Event Stream:** Connect to genuine action events emitted by `MissionDirector` and `SwarmRunner`.
2. **Computer Surface:** Integrate with `UnifiedComputerProvider` to display genuine workspace state, real sandboxed terminal output, real filesystem tree, and real file content.
3. **Research Surface:** Connect to `CognitiveState` and `ResearchManager` (hypotheses, questions, contradictions).
4. **Evidence Surface:** Connect to `EvidenceEngine` (`EvidenceItem`, `CustodyChain`, `IndependentVerifier`).
5. **Evolution Surface:** Connect to `meta/experiment.py` / `EvolutionEngine`.
6. **Mission Surface:** Connect to `MissionDirector` (objectives, real milestones, pause/resume).

---

### [P2] Frontend Modular Architecture Refactor
1. **Refactor Monolithic `app/page.tsx` (982 lines):**
   - Create modular directory structure:
     - `components/workstation/` (Header, Sidebar, Navigation)
     - `components/computer/` (Real Computer View & Desktop Surface)
     - `components/code/` (Code Viewer / Workspace Editor)
     - `components/worklog/` (Realtime Event Feed)
     - `components/research/` (Hypothesis & Knowledge Tree)
     - `components/evidence/` (Verified Findings & Custody Chain)
     - `components/evolution/` (Canary Benchmarks & Generations)
     - `components/mission/` (Mission Owner Controls & Milestone Tracker)
     - `components/common/` (StatusBadge, EmptyState, OfflineBanner)
     - `lib/api.ts` (Unified API Client with environment URL and auth)
     - `lib/auth.ts` (JWT Token Storage & User Context)
     - `lib/ws.ts` (Authenticated WebSocket Relay Client)
     - `types/workstation.ts` (Strict TypeScript interfaces)

---

## 3. Affected Files

### Backend (`sonic-core/`):
- `sonic/api/routes/workstation.py`: Hardened with tenant scoping, JWT auth dependencies, and `ComputerProvider` integration; host shell execution eliminated.
- `sonic/api/routes/terminal.py`: Validated for authenticated container PTY handshake.
- `tests/test_phase20_workstation_security_and_repair.py`: New regression test suite proving zero host execution, tenant scoping, and auth enforcement.

### Frontend (`sonic-dashboard/`):
- `lib/api.ts`: **[NEW]** Shared API client with `NEXT_PUBLIC_API_URL` and auth interceptor.
- `lib/auth.ts`: **[NEW]** Auth token manager and user session state.
- `lib/ws.ts`: **[NEW]** Authenticated WebSocket manager.
- `types/workstation.ts`: **[NEW]** Canonical TypeScript schemas.
- `components/common/OfflineBanner.tsx`: **[NEW]** Explicit connection status indicator.
- `components/workstation/WorkstationHeader.tsx`: **[NEW]** Header with real branch and connection status.
- `components/workstation/WorkstationSidebar.tsx`: **[NEW]** Real session management.
- `components/worklog/WorklogFeed.tsx`: **[NEW]** Real event feed without hardcoded templates.
- `components/computer/ComputerSurface.tsx`: **[NEW]** Real computer observation & PTY terminal.
- `components/code/CodeViewer.tsx`: **[NEW]** Real filesystem workspace reader/editor.
- `components/research/ResearchView.tsx`: **[NEW]** Real CognitiveState viewer.
- `components/evidence/EvidenceView.tsx`: **[NEW]** Real EvidenceEngine viewer.
- `components/evolution/EvolutionView.tsx`: **[NEW]** Real Evolution & Benchmark viewer.
- `components/mission/MissionView.tsx`: **[NEW]** Real MissionDirector viewer.
- `app/page.tsx`: **[MODIFY]** Refactored clean root layout assembling modular components.
- `app/terminal/page.tsx`: **[MODIFY]** Fixed WebSocket authentication & removed local echo.
- `app/computer/page.tsx`: **[MODIFY]** Replaced static mock with real ComputerProvider client.
- `app/evidence/page.tsx`: **[MODIFY]** Connected to `/live/evidence`.
- `app/evolution/page.tsx`: **[MODIFY]** Connected to `/live/experiments`.
- `app/research/page.tsx`: **[MODIFY]** Connected to `/live/graph` / cognitive state.
- `app/missions/page.tsx`: **[MODIFY]** Connected to `/engagements` / mission state.
- `app/security-lab/page.tsx`: **[MODIFY]** Connected to `/experiments/benchmark`.

---

## 4. Security & Isolation Impact
- **Zero Host Execution Invariant:** Verified. Host machine shell execution completely deleted.
- **Fail-Closed Sandbox:** Verified. If sandbox container is stopped or unavailable, endpoints return standard 503 errors without falling back to host execution.
- **Tenant Data Confidentiality:** Verified. All session memory partitioned by `tenant_id`.

---

## 5. Verification Method
1. **Pytest Regression Suite:** Execute automated tests in `tests/test_phase20_workstation_security_and_repair.py`.
2. **Next.js Production Build:** Execute `npm run build` inside `sonic-dashboard/` to guarantee zero type errors and zero broken imports.
3. **End-to-End Contract Verification:** Validate complete data flow from UI to backend with zero mock data.
