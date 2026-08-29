# FORENSIC AUDIT FINDINGS & SEVERITY CLASSIFICATION

**Date:** 2026-08-28  
**Audit Target:** `sonic-dashboard/` & `sonic-core/sonic/api/`

---

## Priority Ranked Findings

### [P0 - CRITICAL] Unauthenticated Arbitrary Host Shell Execution via Workstation API
- **Location:** `sonic-dashboard/app/page.tsx:268` & `sonic-core/sonic/api/routes/workstation.py:271`
- **Finding:** The workstation command endpoint executes `subprocess.run(req.command, shell=True, cwd=REPO_DIR)` directly on the host operating system without requiring JWT authentication, session validation, or Docker/Daytona sandbox containment.
- **Risk:** Anyone who can access the web dashboard port can execute arbitrary system commands on the host machine.

---

### [P0 - CRITICAL] Complete Absence of Frontend Authentication & Tenant Isolation
- **Location:** `sonic-dashboard/app/*`
- **Finding:** There is no login flow, token ingestion, or Authorization header in any frontend request. All `live.py` endpoints requiring `require_auth` or `require_admin` fail, while the workstation state is shared globally across all users in a single in-memory dictionary.
- **Risk:** Zero tenant data privacy, unauthorized configuration mutation, and failure of protected API routes.

---

### [P1 - HIGH] Pervasive Hardcoded Mock/Demo State Masking Disconnected Features
- **Location:** `app/page.tsx`, `app/computer/page.tsx`, `app/engineer/page.tsx`, `app/evidence/page.tsx`, `app/evolution/page.tsx`, `app/missions/page.tsx`, `app/research/page.tsx`, `app/sandbox/page.tsx`, `app/security-lab/page.tsx`
- **Finding:** 9 out of 14 routes are 100% hardcoded HTML mockups with zero backend API integration. The main landing page (`app/page.tsx`) contains fallback mock data for PRs, thinking time, CPU/RAM, and OS display that automatically renders if the backend fails, creating a false impression of active AI autonomy.
- **Risk:** Completely misleading UI; users and stakeholders cannot distinguish between working AI systems and static HTML demos.

---

### [P1 - HIGH] Broken WebSocket Terminal Relay with Fake Local Echo
- **Location:** `sonic-dashboard/app/terminal/page.tsx:26, 50-54`
- **Finding:** The terminal WebSocket attempts to connect to `ws://localhost:8000/terminal/ws/terminal` without passing a JWT token. When rejected by the backend, it falls back to echoing user commands locally, giving a false impression of an active terminal.
- **Risk:** Non-functional terminal pretending to accept commands.

---

### [P2 - MEDIUM] Architecture Regression & Subsystem Disconnection
- **Location:** `sonic-dashboard/app/page.tsx`
- **Finding:** The workstation redesign severed connections to the core multi-agent orchestrator (`SwarmRunner`, `MissionDirector`, `EvidenceEngine`, `EvolutionEngine`) and replaced them with a standalone in-memory `workstation.py` router.
- **Risk:** AI capabilities developed across Phases 1–19 are not wired to the main dashboard interface.

---

### [P3 - LOW] Hardcoded IP and Port in Frontend Code
- **Location:** `sonic-dashboard/app/page.tsx:145, 154, 163, 193, 219, 242, 268`
- **Finding:** `http://127.0.0.1:8000` is hardcoded in `page.tsx` rather than using `process.env.NEXT_PUBLIC_API_URL`.
- **Risk:** Frontend fails when deployed in Docker, remote servers, or non-standard ports.
