# AUTHENTICATION & MULTI-TENANCY UI FORENSICS

**Date:** 2026-08-28  
**Audit Target:** Authentication, JWT handling, session boundaries, and tenant isolation across `sonic-dashboard/`

---

## 1. Authentication Status

### Frontend Assessment: **ZERO AUTHENTICATION IMPLEMENTED**
1. **No Login / Token Ingestion Screen:**
   - There is no `/login`, `/auth`, or SSO screen in `sonic-dashboard/app/`.
   - The entire dashboard renders immediately on root URL `/` without checking for an active session.
2. **No Token Storage:**
   - A search for `localStorage`, `sessionStorage`, `document.cookie`, and `indexedDB` across `sonic-dashboard/` found **zero** authentication tokens stored or managed.
3. **No Authorization Headers:**
   - All `fetch()` calls in `app/page.tsx`, `app/graph/page.tsx`, `app/experiments/page.tsx`, and `app/settings/page.tsx` omit `headers: { "Authorization": "Bearer ..." }`.
4. **Backend Consequence:**
   - In `sonic-core/sonic/api/routes/live.py`, endpoints use `Depends(require_auth)`.
   - When the backend enforces JWT verification, all live requests from `app/graph/page.tsx`, `app/experiments/page.tsx`, and `app/settings/page.tsx` will fail with `401 Unauthorized`.
   - In `app/page.tsx`, the `/workstation/*` routes deliberately omitted the `require_auth` dependency, allowing unauthenticated read and arbitrary command execution on the host machine.

---

## 2. Multi-Tenant UI Isolation

| Component / Layer | Expected Tenant Isolation | Actual Frontend Implementation | Security Status |
|---|---|---|---|
| Workstation State | Scoped by `tenant_id` / `session_id` | Single global in-memory dictionary `_workstation_state` shared across all connections | **CRITICAL LEAK RISK** |
| Code & File Access | Sandboxed per tenant repository | `Path(REPO_DIR / path)` accesses any file within the parent repository directory | **NO ISOLATION** |
| Command Execution | Container-bound sandbox per tenant | `subprocess.run(shell=True)` executed under backend host server process | **CRITICAL ISOLATION BREACH** |
| Graph Memory Explorer | Partitioned by `tenant_id` | Calls `/live/graph` without tenant identifier | Unisolated / Fails Auth |
| Settings / Credentials | Scoped to Tenant Admin | Modifies global `_runtime_config` for entire server | Unisolated |
