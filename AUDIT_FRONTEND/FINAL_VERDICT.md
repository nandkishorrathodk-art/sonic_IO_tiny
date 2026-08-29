# SONIC-REDA — FINAL FORENSIC AUDIT VERDICT

**Date:** 2026-08-28  
**Audit Target:** `sonic-dashboard/` & its integration with `sonic-core/`  
**Overall Verdict:** **HYBRID CLIENT WITH CRITICAL MOCK REGRESSIONS (MOCK/DEMO STATE DOMINANT)**

---

## 1. Direct Answers to Core Audit Questions

### 1. Is the current SONIC frontend a REAL runtime client, or has it become a MOCK/DEMO frontend?
**Verdict:** **It has largely become a MOCK / DEMO frontend with thin, selective real endpoints.**
While it has working local filesystem reads (`GET /workstation/tree`, `GET /workstation/file`), real local git diffs (`GET /workstation/git-diff`), and direct host shell execution, **all cognitive, telemetry, OS desktop, evidence, PR, and evolution panels are either static templates or 100% hardcoded HTML mockups.**

---

### 2. Which pages are genuinely backend-connected?
Only **3 pages** have active, genuine backend API integrations:
1. `app/experiments/page.tsx` (`GET /live/experiments`, `POST /live/experiments/benchmark`)
2. `app/graph/page.tsx` (`GET /live/graph`)
3. `app/settings/page.tsx` (`GET /live/settings`, `POST /live/settings`)

And `app/page.tsx` is partially connected to the bespoke `workstation.py` API (reading real repo files and diffs).

---

### 3. Which pages contain mock data?
**11 out of 14 pages** contain heavy or total mock data:
- `app/page.tsx` (Mock PR #19, mock thought timings, mock CPU/RAM, mock OS display, mock Chromium)
- `app/computer/page.tsx` (100% Mock)
- `app/engineer/page.tsx` (100% Mock)
- `app/evidence/page.tsx` (100% Mock)
- `app/evolution/page.tsx` (100% Mock)
- `app/mission/page.tsx` (100% Mock)
- `app/missions/page.tsx` (100% Mock)
- `app/research/page.tsx` (100% Mock)
- `app/sandbox/page.tsx` (100% Mock)
- `app/security-lab/page.tsx` (100% Mock)
- `app/terminal/page.tsx` (Broken WS falling back to local echo simulation)

---

### 4. Which UI panels are fake?
1. **Virtual OS Desktop Window** (`app/page.tsx:712-852` & `app/computer/page.tsx`): Fake HTML/CSS container, no VNC/X11 stream.
2. **AI Cursor & Devin Typing Indicator** (`app/page.tsx:790-794`): Static CSS ping badge.
3. **Chromium Browser Inside Desktop** (`app/page.tsx:829-851`): Static HTML card.
4. **Pull Request #19 Tab** (`app/page.tsx:932-943`): Static HTML text claiming PR #19 is merged.
5. **Waveform Thought Timeline** (`app/page.tsx:950-958`): Hardcoded number array.
6. **Past Sessions History** (`app/page.tsx:403-450`): Static clickable cards.

---

### 5. Which WebSockets are real?
**ZERO active working WebSockets.**
The single WebSocket in `app/terminal/page.tsx` fails authentication because it sends no JWT token, and the component falls back to echoing typed characters locally in JavaScript.

---

### 6. Which computer features are real?
- **Real:** Reading source code files from the workspace directory (`GET /workstation/file`).
- **Real:** Listing files in repository (`GET /workstation/tree`).
- **Real:** Executing shell commands (`POST /workstation/command` — running on host, unsafe).
- **Fake:** Virtual OS display, active Xvfb resolution, CPU/RAM telemetry, active processes list, and Chromium browser viewport.

---

### 7. Which Git / PR information is real?
- **Real:** Git branch name and uncommitted git diffs (`GET /workstation/git-diff`).
- **Fake:** "Pull Request #19: Release Production Gate & Autonomy Engine - MERGED".

---

### 8. Which mission / agent information is real?
- **Real:** Executing pytest if the user prompt explicitly requests it (`POST /workstation/prompt`).
- **Fake:** "Thought for 3s", "Thought for 20s", "Analyzing AST topology", "Thinking: I see the architecture now...", and all cognitive milestone steppers across `/missions` and `/mission`.

---

### 9. Which data silently falls back to fake state?
When the backend is offline:
- `worklog` silently falls back to the 6-item Phase 19 static template.
- `fileTree` silently falls back to 5 hardcoded file paths.
- `fileContent` silently falls back to a hardcoded `TokenValidator` snippet.
- `terminal` silently echoes user commands into the DOM without executing them.

---

## 2. Action Plan Summary (Pending Repair Authorization)

1. **Phase 1 (Security & Containment):**
   - Eliminate host shell execution in `workstation.py`. Re-route all terminal execution through Docker/Daytona sandbox PTY relay.
   - Implement JWT authentication headers across all dashboard API and WebSocket requests.
2. **Phase 2 (True Subsystem Re-Integration):**
   - Connect the main dashboard worklog to real SSE/WebSocket event streams emitted by `SwarmRunner` and `MissionDirector`.
   - Wire `/evidence`, `/evolution`, and `/security-lab` to real backend stores (`sonic_data.db` & `EvidenceEngine`).
3. **Phase 3 (Purge All Fallback Mocks):**
   - Remove hardcoded PR #19, fake CPU/RAM, fake OS display strings, and silent mock fallbacks.
   - Implement explicit "Disconnected / Offline" state indicators.
