# MOCK & FAKE DATA FORENSIC INVENTORY

**Date:** 2026-08-28  
**Audit Target:** All hardcoded fixtures, simulated states, and fake telemetry across `sonic-dashboard/`

---

## 1. Concrete Inventory of Hardcoded / Mock Entities

### Item 1: Fake Pull Request #19 Tab & Details
- **File & Lines:** `app/page.tsx:673-675`, `app/page.tsx:932-943`
- **Exact Code:**
  ```tsx
  {/* Line 673 */}
  <button onClick={() => { setActiveTab("pr66"); setRightView("pr66"); }}>
    <GitPullRequest className="w-3.5 h-3.5 text-[#D2A8FF]" />
    <span>PR #19</span>
  </button>

  {/* Line 932 */}
  {/* VIEW D: PR #19 */}
  {rightView === "pr66" && (
    <div className="flex-1 rounded-lg border border-[#21262D] bg-[#161B22] flex flex-col overflow-hidden p-4 font-mono text-xs space-y-3">
      <div className="flex items-center justify-between border-b border-[#30363D] pb-2">
        <span className="font-semibold text-white">Pull Request #19: Release Production Gate & Autonomy Engine</span>
        <span className="px-2 py-0.5 rounded bg-[#238636] text-white font-bold text-[10px]">MERGED</span>
      </div>
      <p className="text-[#8B949E] text-xs font-sans">
        Autonomous Pull Request incorporating all 225 unit tests across Phases 1–19, 4-tier reality taxonomy, and continuous self-development.
      </p>
    </div>
  )}
  ```
- **Why Suspicious:** 100% static HTML. Zero GitHub API, zero local git PR lookup, zero commit hash.
- **Production Impact:** Misleads users into believing an automated PR was generated and merged.

---

### Item 2: Fake "Thought for 3s" and "Thought for 20s" Worklog
- **File & Lines:** `app/page.tsx:285-317`
- **Exact Code:**
  ```tsx
  const worklog = liveState?.worklog && liveState.worklog.length > 0 ? liveState.worklog : [
    {
      type: "thought",
      duration: "3s",
      title: "Thought for 3s",
      content: "Repository attached. Initialized environment on branch main.",
    },
    {
      type: "thought",
      duration: "20s",
      title: "Thought for 20s",
      content: "Analyzing AST topology and 225 unit tests across Phases 1-19.",
    },
    {
      type: "command",
      command: "git status --short",
      output: "Working tree clean. All files committed.",
    },
    {
      type: "read",
      file: "sonic-core/sonic/production_gate/scenario_matrix.py",
      lines: "1-60",
    },
    {
      type: "thinking",
      content: "I see the architecture now—SONIC Workstation manages real-time computer use, sandboxed code execution, and autonomous multi-generation reproduction gates. All 8 failure scenarios verified under fail-closed security invariants.",
    },
    {
      type: "command",
      command: "python -m pytest tests/test_phase19/ -v",
      output: "4 passed in 1.48s",
    },
  ];
  ```
- **Why Suspicious:** If the backend is offline or returns empty worklog, the UI automatically renders this static paragraph simulating active cognitive deliberation and test suite execution.
- **Production Impact:** Masks backend failure by pretending the AI agent just finished analyzing the AST topology.

---

### Item 3: Fake OS Telemetry ("Ubuntu 22.04 LTS (Display :1)", CPU 14%, RAM 1.3GB)
- **File & Lines:** `app/page.tsx:690-706`, `app/page.tsx:724-725`
- **Exact Code:**
  ```tsx
  {/* Line 691 */}
  Live OS: <strong className="text-white">Ubuntu 22.04 LTS (Display :1)</strong>

  {/* Line 703-705 */}
  <span>CPU 14%</span>
  <span>RAM 1.3GB / 8GB</span>

  {/* Line 724 */}
  SONIC Desktop Workspace — Ubuntu 22.04 (1920x1080)
  ```
- **Why Suspicious:** Hardcoded directly into the JSX body. Not even bound to a variable or state!
- **Production Impact:** Gives a false appearance of live Linux telemetry and active X11 display.

---

### Item 4: Fake "Devin Typing" AI Cursor Overlay
- **File & Lines:** `app/page.tsx:790-794`
- **Exact Code:**
  ```tsx
  <div className="absolute bottom-4 right-4 bg-[#388BFD] text-white px-2 py-0.5 rounded text-[10px] font-mono font-bold shadow-lg flex items-center gap-1.5">
    <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
    <span>Devin typing at {activeFile.split("/").pop()}</span>
  </div>
  ```
- **Why Suspicious:** A static floating badge positioned at `bottom: 1rem; right: 1rem` with a CSS pulse animation. It does not reflect any live agent action.
- **Production Impact:** Deceives users into thinking an autonomous AI is actively editing the code file.

---

### Item 5: Fake Chromium Web Browser in Desktop View
- **File & Lines:** `app/page.tsx:829-851`
- **Exact Code:**
  ```tsx
  {activeDesktopApp === "browser" && (
    <div className="flex-1 flex flex-col bg-[#12151A] overflow-hidden">
      <div className="h-7 border-b border-[#21262D] bg-[#161B22] px-3 flex items-center justify-between text-[11px] font-mono text-[#8B949E]">
        <div className="flex items-center gap-2 flex-1">
          <Globe className="w-3.5 h-3.5 text-[#58A6FF]" />
          <span className="px-2 py-0.5 rounded bg-[#0D1117] text-white flex-1 truncate">
            http://127.0.0.1:8000/docs
          </span>
        </div>
        <span className="text-[#3FB950] text-[10px] ml-2">HTTP 200 OK</span>
      </div>
      <div className="flex-1 p-6 flex flex-col items-center justify-center text-center space-y-2 bg-[#0A0C10]">
        <div className="w-10 h-10 rounded-full bg-[#238636]/20 border border-[#238636] flex items-center justify-center text-[#3FB950]">
          <CheckCircle2 className="w-5 h-5" />
        </div>
        <h4 className="text-sm font-semibold text-white">Live Application View Port</h4>
        <p className="text-xs text-[#8B949E] max-w-sm">
          FastAPI Backend Server &amp; Security OpenAPI live at <code className="text-[#58A6FF]">http://127.0.0.1:8000</code>.
        </p>
      </div>
    </div>
  )}
  ```
- **Why Suspicious:** Renders a static mock box with a green checkmark instead of an actual embedded browser or Playwright/VNC view.
- **Production Impact:** Claims to provide a live Chromium browser viewport inside the virtual OS desktop when none exists.

---

### Item 6: Fake Past Sessions List in Sidebar
- **File & Lines:** `app/page.tsx:403-450`
- **Exact Code:**
  - `sonic-core-auth-guard` (PR 1, Completed)
  - `token-replay-fix` (PR 1, Completed)
  - `router-table-optimization` (Completed)
- **Why Suspicious:** Hardcoded clickable cards that just switch the file viewer to specific local repository files (`scenario_matrix.py`, `continuous_loop.py`, `pyproject.toml`).
- **Production Impact:** Fake session history.

---

### Item 7: Fake Autonomous Engineer Traces (`app/engineer/page.tsx`)
- **File & Lines:** `app/engineer/page.tsx:33-79`
- **Exact Code:** `INITIAL_TRACES` containing 5 static steps with pre-calculated `time_ms` (12ms, 8ms, 15ms, 420ms, 35ms) and fake unit test outputs (`14 passed, 0 failed`). `handleRunMission` uses `setTimeout(..., 1500)`.

---

### Item 8: Fake Evidence Board (`app/evidence/page.tsx`)
- **File & Lines:** `app/evidence/page.tsx:69-132`
- **Exact Code:** Static array with finding `find-jwt-none-01`, fake SHA256 hashes (`e3b0c442...`, `5e884898...`), and fake Daytona sandbox replay notes.

---

### Item 9: Fake Multi-Generation Evolution (`app/evolution/page.tsx`)
- **File & Lines:** `app/evolution/page.tsx:39-80`
- **Exact Code:** Static array of 4 versions (v1.0.0 through v1.3.0) with synthetic F1 improvements (0.667 → 0.974) and hardcoded cost savings ($0.080 → $0.045).

---

### Item 10: Fake Security Lab Tests (`app/security-lab/page.tsx`)
- **File & Lines:** `app/security-lab/page.tsx:34-46`
- **Exact Code:** 11 hardcoded test items (`SEC-AUTH-01` to `SEC-CHAOS-01`) all marked `PASS` with synthetic execution times (`12ms`, `18ms`, etc.).
