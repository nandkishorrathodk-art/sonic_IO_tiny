# COMPUTER UI REALITY AUDIT

**Date:** 2026-08-28  
**Audit Target:** Workstation Desktop, Virtual OS Screens, IDE, PTY Terminal, Browser, and Process Inspector across `app/page.tsx` and `app/computer/page.tsx`.

---

## Forensic Audit of Computer UI Capabilities

### 1. Desktop GUI / Screen
- **Claim:** Live Ubuntu / Kali Linux desktop running on Display :1 / :99 with Xvfb, 60 FPS, 1920x1080 resolution.
- **Reality:** **100% MOCK / FAKE HTML-CSS CONTAINER**.
  - There is **no VNC canvas**, **no noVNC client**, **no Apache Guacamole**, **no WebRTC**, and **no X11 frame stream**.
  - In `app/page.tsx:714-726`, the desktop window is simply a standard React `<div>` with three colored dots (`#FF5F56`, `#FFBD2E`, `#27C93F`) and an SVG icon.
  - In `app/computer/page.tsx:140-176`, the desktop is an empty gray card containing a static `<pre>` tag with Python code.
- **Classification:** `MOCK`

---

### 2. IDE / Code Editor
- **Claim:** Integrated VS Code / code-server editor with live multi-file editing and active AI cursor.
- **Reality:** **HYBRID READ-ONLY VIEWER + FAKE AI BADGE**.
  - In `app/page.tsx:758-788`, the editor is a read-only React list of lines fetched from `GET /workstation/file?path=...`.
  - If the backend is running, it does read real local files from the filesystem via `workstation.py`.
  - However, it is **not VS Code / Monaco Editor / CodeMirror / code-server**; it is raw `<div>` line rendering without syntax parsing, autocompletion, or write capabilities.
  - The AI cursor is a static CSS `animate-ping` badge fixed at bottom-right (`app/page.tsx:790-794`).
- **Classification:** `PARTIAL` (Read-only filesystem viewer, not an interactive IDE).

---

### 3. Terminal Console
- **Claim:** Containerized PTY sandbox shell attached to Daytona / Docker.
- **Reality:**
  - **In `app/page.tsx:798-826`:** An `<input>` form that sends raw commands via `POST /workstation/command` to `sonic-core/sonic/api/routes/workstation.py:271`.
    - **Crucial finding:** This executes commands **directly on the host OS** (`subprocess.run(req.command, shell=True)`), NOT in a sandboxed container!
  - **In `app/computer/page.tsx:181-198`:** 100% static HTML text with hardcoded `uname -a` and `git status`.
  - **In `app/terminal/page.tsx`:** WebSocket client connecting to `/terminal/ws/terminal`, but broken due to missing authentication token and falls back to local echo.
- **Classification:**
  - `app/page.tsx`: `REAL (HOST UNCONTAINED - SECURITY RISK)`
  - `app/computer/page.tsx`: `MOCK`
  - `app/terminal/page.tsx`: `BROKEN`

---

### 4. Running Processes
- **Claim:** Active process list monitoring Xvfb, Chromium, Shell, and code-server.
- **Reality:** **100% HARDCODED HTML / IN-MEMORY DICTIONARY**.
  - In `app/computer/page.tsx:73`, "5 Active: Xvfb, code-server, Chromium, Shell" is hardcoded static text.
  - In `sonic-core/sonic/api/routes/workstation.py:73-78`, the running apps are a static Python dictionary:
    ```python
    "running_apps": [
        {"name": "VS Code", "icon": "code", "status": "active", "file": "scenario_matrix.py"},
        {"name": "Terminal", "icon": "terminal", "status": "running", "cmd": "pytest tests/ -v"},
        {"name": "Chromium", "icon": "globe", "status": "background", "url": "http://127.0.0.1:8000/docs"},
        {"name": "File Manager", "icon": "folder", "status": "idle", "path": "/home/sonic/society"},
    ]
    ```
- **Classification:** `HARDCODED`

---

### 5. Web Browser
- **Claim:** Headless / interactive Chromium web browser inside the sandbox.
- **Reality:** **100% MOCK**.
  - In `app/page.tsx:829-851`, switching to the "Chromium" tab displays a static placeholder card showing "Live Application View Port" and "FastAPI Backend Server live at http://127.0.0.1:8000".
- **Classification:** `MOCK`

---

### 6. Git Diff & Tree
- **Claim:** Realtime Git status, file tree, and uncommitted diffs.
- **Reality:** **REAL BACKEND CONNECTED**.
  - `GET /workstation/tree` executes `os.walk(REPO_DIR)` and returns real repository files.
  - `GET /workstation/git-diff` executes `git diff` via subprocess and returns real git diffs.
- **Classification:** `REAL + LOCAL`
