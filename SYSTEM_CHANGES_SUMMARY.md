# SONIC A-SEA — System Architecture & Changes Summary

> **Document**: Master Reference & Future Roadmap Guide  
> **Date**: September 2026  
> **Repository**: `nandkishorrathodk-art/sonic`  
> **Substrate**: Native Docker Cyber Workstation (`sonic-desktop-workstation`)

---

## 1. Executive Summary (Kyu Kiya? — The Motivation)

Is architectural upgrade ka mukhya maksad SONIC A-SEA ko **poori tarah self-contained, independent-thinking aur cloud-dependency-free** banana tha.

### Problems in Earlier Architecture:
1. **Daytona Cloud Limitations**:
   - Daytona Tier 1/2 cloud sandboxes external internet connections ko reset kar dete the (`HTTP 403 Forbidden: Internet is restricted on Tier 1 and Tier 2`).
   - Is wajah se agent real target domains scan nahi kar pata tha, naye tools ya dependencies install nahi kar pata tha, aur security definitions update nahi hoti thi.
   - External cloud token (`DAYTONA_API_KEY`) aur network latency par dependency thi.
2. **Rigid Scanner Chaining vs. Autonomous Thinking**:
   - Traditional automated penetration testing tools hardcoded sequence follow karte hain (`nmap -> nuclei -> ffuf`).
   - User requirement thi ki agent kisi rigid sequence par depend na kare; balki high-level security goal ke mutabiq **First-Principles Reasoning** kare, environment observe kare, hypotheses banaye, aur custom actions/tools chun kar empirical verification kare.
3. **External Cloned Repository (`open-computer-use`) Ambiguity**:
   - Cloned repository `open-computer-use` ek external reference codebase tha. Usko poora merge karne se hamara repo pollute hota. Humne uske algorithms extract karke natively integrate kiye aur clone ko safely ignore kiya.

---

## 2. What Changes Were Made? (Kya Changes Kiye?)

### A. Substrate Layer (Daytona $\to$ Native Docker Workstation)
- **`sonic/computer/docker_computer.py` (`DockerComputerProvider`) [NEW]**:
  - Direct container management of `sonic-desktop-workstation` via `docker exec`.
  - Full XFCE4 desktop running on virtual display `:99` (1280x800x24) with symlink `/tmp/.X11-unix/X0` for universal DISPLAY compatibility.
  - ImageMagick screenshot capture with crosshair rendering (`import` and `convert`).
  - Remote desktop streaming via `x11vnc` on port `5900` + `noVNC` on port `6080` (`http://localhost:6080/vnc.html`).
  - Pre-installed browser: Google Chrome Stable (`google-chrome-stable v152`) with 100% unrestricted outbound internet access.
  - PTY bash terminal execution, application lifecycle management (`APP_LAUNCH`, `APP_CLOSE`, `APP_FOCUS`), and file read/write.
- **`sonic/computer/docker_sandbox.py` (`DockerContainerSandbox`) [NEW]**:
  - Duck-typed drop-in adapter that satisfies legacy Daytona SDK interfaces (`fs`, `process`) so that no existing routes break.
- **`sonic/api/routes/workstation.py` [MODIFIED]**:
  - `get_computer()` and `get_daytona_computer()` now route to `DockerComputerProvider` by default.
  - Session state returns "Linux Cyber Workstation (Docker XFCE4)" with streaming port 6080.
  - Hardened `/workstation/session/interrupt` with `require_operator` RBAC.

### B. Perception & Visual Grounding Layer
- **`sonic/computer_use/grounding.py` [UPGRADED]**:
  - `extract_bbox_midpoint()`: parses `<|box_start|>(x1,y1,x2,y2)<|box_end|>`, normalized `0-1000`, and floats `[0.0, 1.0]` into exact screen pixels `(x, y)` without coordinate guessing.
  - `resolve_ui_target()`: maps natural-language UI queries (e.g., `"Applications menu"`, `"Terminal icon"`, `"Google Chrome"`, `"Window close"`) directly to screen coordinates, with semantic desktop landmarks and multimodal vision grounding callbacks.
  - `draw_action_marker()`: renders distinct visual crosshair reticles on screenshots (cyan for click, pink for right-click, orange for double-click) for real-time audit verification.

### C. Cognitive Loop & Autonomy (`agent.py`)
- **`sonic/computer_use/agent.py` [MODIFIED]**:
  - **Natural-Language Element Clicking**: If the LLM generates `ACTION: GUI_CLICK`, `TARGET: "Applications menu"` without raw pixel coordinates, `execute_action()` automatically resolves the query using `resolve_ui_target()` against the screenshot instead of failing.
  - **Right-Click Support (`GUI_RIGHT_CLICK`)**: Full context menu interaction primitive added (`xdotool click 3`), allowlisted in `ActionPolicy`, and handled across `docker_computer.py` and `daytona_computer.py`.
  - **Post-Mission Verification**: Actions complete hone par system state inspect karke `goal_reached = True` aur `verification_score = 1.00` verify karta hai.
  - **Conversational Shell Sanitization**: LLM jab natural-language commands output karta hai (e.g. `"netstat or ss command"`, `"Terminal"`, parenthesized text `(or ss)`), unhe automatically valid shell commands (`which netstat && netstat -tuln || ss -tuln`) me sanitize karta hai.
  - **Fail-Closed Safety Envelope**: Any attempt to access private ranges (e.g. `127.0.0.1` or loopback in browser egress) is intercepted and logged as `BLOCKED` (status 126).

---

## 3. How Repositories are Managed (Repo ka Role & Dark Reality)

| Repository | Path | Role & Dark Reality Comparison |
|---|---|---|
| **`open-computer-use`** | `c:\Users\nandk\_society\open-computer-use` | **Cloned Reference Only (E2B Locked)**: Dark reality is that this repo is a 200-line wrapper completely dependent on E2B paid cloud sandboxes; it cannot run locally on Docker or VPS. We extracted all of its genuine innovations (`extract_bbox_midpoint`, `resolve_ui_target`, `draw_action_marker`, query-based clicking) and integrated them natively into SONIC. Main repo stays clean. |
| **`Target Repositories`** | `/root/workspace/` (inside Docker container) | **Audit & Pen-Testing Target**: Target application codebases ko Docker container ke workspace me mount kiya jata hai. Agent `CodeGraph`, AST aur unit tests chala kar vulnerabilities dhundhta hai aur real patches author karke sandbox me test karta hai. |
| **`SONIC Repository`** | `c:\Users\nandk\_society` | **Main Platform**: FastAPI backend, Next.js dashboard, memory router, sovereign native Docker Cyber Workstation, fail-closed safety envelope, and autonomous reasoning core. |

---

## 4. Verification Test Matrix (33/33 Passed 100%)

All new test suites run via pytest and pass 100%:

```bash
python -m pytest sonic-core/tests/test_visual_grounding.py \
                 sonic-core/tests/test_docker_computer_provider.py \
                 sonic-core/tests/test_docker_workstation_adapter.py \
                 sonic-core/tests/test_workstation_interrupt_and_resilience.py \
                 sonic-core/tests/test_phase_plan6_safety_envelope.py
```

| Test File | Tests | Status | What it Verifies |
|---|---|---|---|
| `test_visual_grounding.py` | 9 | **PASSED** | Bbox extraction, landmarks, dynamic grounding fn, action markers, agent click/right-click dispatch |
| `test_docker_computer_provider.py` | 2 | **PASSED** | Lifecycle, status, terminal exec, screenshot, file read/write, apps |
| `test_docker_workstation_adapter.py` | 3 | **PASSED** | Duck-typed sandbox adapter, VNC preview URL, terminal & screenshot |
| `test_workstation_interrupt_and_resilience.py` | 9 | **PASSED** | Interrupt flag, loop exit, RBAC authentication & rejection, tenant isolation |
| `test_phase_plan6_safety_envelope.py` | 10 | **PASSED** | Fail-closed policy, rate limit, path confinement, egress filter, allowlist |

---

## 5. How to Run and Operate in Future (Aage Kaise Chalana Hai?)

### 1. Start Substrate Containers (Docker)
```powershell
docker start sonic-desktop-workstation sonic-redis sonic-neo4j
```

### 2. Run Backend Control Plane
```powershell
python -m uvicorn sonic.api.main:app --host 127.0.0.1 --port 12000
```
- Health endpoint: `http://127.0.0.1:12000/health`
- Swagger docs: `http://127.0.0.1:12000/docs`

### 3. Run Frontend Dashboard
```powershell
cd sonic-dashboard
npm run dev -- -p 12001
```
- Dashboard UI: `http://localhost:12001`
- Live Cyber Workstation VNC Feed: `http://localhost:6080/vnc.html`

### 4. Launch Autonomous Agent Mission
```powershell
python scripts/launch_agent.py
```
- Ye script agent ko initialize karega, Docker workstation me connect karega, 5-step autonomous cycle chalayega, aur live assessment report generate karega `reports/workstation_assessment_report.md` me.
