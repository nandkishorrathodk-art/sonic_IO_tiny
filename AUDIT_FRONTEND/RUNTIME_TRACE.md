# RUNTIME NETWORK & DATA TRACE

**Date:** 2026-08-28  
**Audit Target:** End-to-end data tracing from UI panels down to backend workers.

---

## Complete UI Panel Data Flow Trace

```text
====================================================================================================
1. LEFT PANEL: SESSIONS LIST (`app/page.tsx:385-451`)
====================================================================================================
UI RENDER:
  - Active Session: "graph-game-devin" (Working · Branch 1 · PR 1)
  - Past Session 1: "sonic-core-auth-guard" (Completed · PR 1)
  - Past Session 2: "token-replay-fix" (Completed · PR 1)
  - Past Session 3: "router-table-optimization" (Completed)
DATA TRACE:
  - Active session name: `liveState?.mission_name || "graph-game-devin"` (from `GET /workstation/state` or default).
  - Past sessions: 100% hardcoded in JSX (`app/page.tsx:403-450`).
  - Clicking past sessions calls `fetchFile(...)` to open local repo files.
VERDICT: MOCK / HARDCODED

====================================================================================================
2. LEFT PANEL: WORKLOG FEED (`app/page.tsx:505-574`)
====================================================================================================
UI RENDER:
  - "Thought for 3s"
  - "Thought for 20s"
  - "$ git status --short"
  - "Read scenario_matrix.py:1-60"
  - "Thinking: I see the architecture now..."
  - "$ python -m pytest tests/test_phase19/ -v" (4 passed in 1.48s)
DATA TRACE:
  - If backend live: `GET /workstation/state` -> `_workstation_state["worklog"]` -> Initialized from `_init_default_worklog()`.
  - If backend offline: `worklog` array in `app/page.tsx:285-317`.
  - If prompt submitted with "pytest": `POST /workstation/prompt` -> executes real `pytest` on host -> appends stdout to worklog.
VERDICT: HYBRID TEMPLATE / REAL EXECUTION ON PROMPT

====================================================================================================
3. TOP APP BAR & SUB-HEADER (`app/page.tsx:480-491, 686-706`)
====================================================================================================
UI RENDER:
  - Title: "graph-game-devin"
  - Branch: "main" (Green pulse)
  - "Live OS: Ubuntu 22.04 LTS (Display :1)"
  - "READY / ACTIVE"
  - "CPU 14%"
  - "RAM 1.3GB / 8GB"
DATA TRACE:
  - Title/Branch: `liveState?.git_branch` (from `subprocess.run(git branch)` via `workstation.py`).
  - OS Name / Display / CPU / RAM: Hardcoded raw text in JSX (`app/page.tsx:691, 703-704`).
VERDICT: HARDCODED STRINGS

====================================================================================================
4. RIGHT PANEL: DESKTOP TAB (`app/page.tsx:712-852`)
====================================================================================================
UI RENDER:
  - VS Code tab: Code viewer with line numbers + "Devin typing at scenario_matrix.py" badge.
  - Terminal tab: Interactive shell with prompt `sonic@sandbox:~$`.
  - Chromium tab: Placeholder card with "http://127.0.0.1:8000/docs".
DATA TRACE:
  - VS Code code content: `GET /workstation/file?path=...` -> `Path(REPO_DIR / path).read_text()` -> real filesystem read.
  - Terminal commands: `POST /workstation/command` -> `subprocess.run(req.command, shell=True)` -> real host execution.
  - Chromium: 100% static HTML card.
  - Window frame / OS: 100% static HTML/CSS.
VERDICT: PARTIAL (Real file reading + Real host shell execution wrapped in fake OS desktop markup)

====================================================================================================
5. RIGHT PANEL: CHANGES / GIT DIFF TAB (`app/page.tsx:901-930`)
====================================================================================================
UI RENDER:
  - Diff view with green (+) and red (-) lines or "Working tree clean".
DATA TRACE:
  - `GET /workstation/git-diff` -> `subprocess.run(["git", "diff", ...])` on `REPO_DIR` -> real git diff.
VERDICT: REAL + LOCAL

====================================================================================================
6. RIGHT PANEL: PR #19 TAB (`app/page.tsx:932-943`)
====================================================================================================
UI RENDER:
  - "Pull Request #19: Release Production Gate & Autonomy Engine - MERGED"
DATA TRACE:
  - 100% static text in JSX. Zero API calls.
VERDICT: HARDCODED MOCK
```
