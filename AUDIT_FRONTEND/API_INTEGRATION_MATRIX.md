# API INTEGRATION MATRIX & BACKEND CONTRACT MATCHING

**Date:** 2026-08-28  
**Audit Target:** All network invocations in `sonic-dashboard/` mapped to `sonic-core/` FastAPI handlers.

---

## 1. Network Call Mapping

| Frontend Component / Page | HTTP Method | Target URL in Code | Backend Route Handler | Real Backend Data Store / Action | Authentication / Header Sent | Status / Contract Match |
|---|---|---|---|---|---|---|
| `app/page.tsx:145` | `GET` | `http://127.0.0.1:8000/workstation/state` | `sonic/api/routes/workstation.py:156` `get_workstation_state` | In-memory `_workstation_state` dictionary + `subprocess.run(git)` | **None** (No Auth header) | **Matched** (Returns state with synthetic defaults if unpopulated) |
| `app/page.tsx:154` | `GET` | `http://127.0.0.1:8000/workstation/desktop/status` | `sonic/api/routes/workstation.py:175` `get_desktop_status` | In-memory `_workstation_state["desktop"]` dictionary | **None** | **Matched** (Returns synthetic desktop metadata) |
| `app/page.tsx:163` | `GET` | `http://127.0.0.1:8000/workstation/tree` | `sonic/api/routes/workstation.py:198` `get_workstation_tree` | `os.walk(REPO_DIR)` reading real repository file tree | **None** | **Matched** (Real filesystem read) |
| `app/page.tsx:193` | `GET` | `http://127.0.0.1:8000/workstation/file?path=...` | `sonic/api/routes/workstation.py:241` `get_workstation_file` | `Path(REPO_DIR / path).read_text()` reading actual file content | **None** | **Matched** (Real source code read) |
| `app/page.tsx:219` | `GET` | `http://127.0.0.1:8000/workstation/git-diff` | `sonic/api/routes/workstation.py:221` `get_workstation_git_diff` | `subprocess.run(["git", "diff", ...])` on real local repo | **None** | **Matched** (Real git diff) |
| `app/page.tsx:242` | `POST` | `http://127.0.0.1:8000/workstation/prompt` | `sonic/api/routes/workstation.py:304` `send_workstation_prompt` | Appends user prompt to `_workstation_state["worklog"]`; optionally runs pytest | **None** | **Matched** (Executes test if prompt contains "test" / "pytest") |
| `app/page.tsx:268` | `POST` | `http://127.0.0.1:8000/workstation/command` | `sonic/api/routes/workstation.py:271` `execute_workstation_command` | `subprocess.run(req.command, shell=True)` on local host machine | **None** | **Matched** (Real host shell command execution — **Security Risk: Host Execution Bypass**) |
| `app/graph/page.tsx:31` | `GET` | `${API_BASE}/live/graph` | `sonic/api/routes/live.py:225` `get_live_graph` | `InMemoryGraph` or `Neo4j` nodes/edges | **None** (Fails if backend enforces `require_auth`) | **Mismatched Auth**: Backend requires `require_auth`, frontend sends no Bearer token. |
| `app/experiments/page.tsx:51` | `GET` | `${API_BASE}/live/experiments` | `sonic/api/routes/live.py:264` `get_live_experiments` | `ExperimentManager.list_experiments()`, `BenchmarkLab.fixtures` | **None** (Fails if backend enforces `require_auth`) | **Mismatched Auth**: Backend requires `require_auth`. |
| `app/experiments/page.tsx:72` | `POST` | `${API_BASE}/live/experiments/benchmark` | `sonic/api/routes/live.py:279` `run_benchmark` | `BenchmarkLab.run_benchmark(mock_eval_fn)` | **None** (Fails if backend enforces `require_auth`) | **Mismatched Auth**: Backend requires `require_auth`. |
| `app/settings/page.tsx:23` | `GET` | `${API_BASE}/live/settings` | `sonic/api/routes/live.py:327` `get_runtime_settings` | `_runtime_config` | **None** (Fails if backend enforces `require_auth`) | **Mismatched Auth**: Backend requires `require_auth`. |
| `app/settings/page.tsx:47` | `POST` | `${API_BASE}/live/settings` | `sonic/api/routes/live.py:333` `update_runtime_settings` | Reconfigures `SwarmRunner` & providers | **None** (Fails: requires `require_admin`) | **Mismatched Auth**: Backend requires admin JWT, frontend sends none. |
| `app/terminal/page.tsx:26` | `WS` | `ws://localhost:8000/terminal/ws/terminal` | `sonic/api/routes/terminal.py:111` `terminal_websocket` | `docker exec -i sonic-sandbox /bin/bash` | **None** (`?token=` missing) | **Rejected by Backend**: Backend checks `verify_ws_token(token)` and closes socket with WS_1008. |

---

## 2. Forensic Findings on Backend Contracts

### A. Total Disconnect of Specialized Autonomous Subsystems
The frontend has **zero** API calls to the following production backend routes implemented in `sonic-core`:
1. `sonic-core/sonic/api/routes/agents.py` (`/agents/*`): Completely ignored.
2. `sonic-core/sonic/api/routes/engagements.py` (`/engagements/*`): Completely ignored.
3. `sonic-core/sonic/api/routes/jobs.py` (`/jobs/*`): Completely ignored.
4. `sonic-core/sonic/api/routes/live.py` (`/live/scan`, `/live/stats`, `/live/findings`, `/live/assets`): Completely ignored by the main interface and subpages (`/evidence`, `/sandbox`, `/missions`, etc.).

### B. Hardcoded Port / Protocol Vulnerability
`app/page.tsx` hardcodes `http://127.0.0.1:8000` directly in its fetch calls instead of using `process.env.NEXT_PUBLIC_API_URL`. If the backend runs on any other port or domain (e.g. in Docker or production staging), `app/page.tsx` will fail completely and silently switch to mock arrays.

### C. Host Execution Security Invariant Breach
`app/page.tsx:268` calls `POST /workstation/command`, which calls `subprocess.run(req.command, shell=True, cwd=REPO_DIR)` directly on the host machine. This directly breaches the Sonic safety rule requiring all shell commands to execute strictly inside Daytona/Docker sandboxes (`ContainerTerminalSession`).
