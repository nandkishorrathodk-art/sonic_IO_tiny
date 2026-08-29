# CLAIM VS. FRONTEND EVIDENCE MATRIX

**Date:** 2026-08-28  
**Audit Target:** Comparing user-facing UI claims against verified codebase evidence.

---

| UI Claim / Visible Text | Claimed Reality | Code Evidence (File & Line) | Verified Reality | Forensic Verdict |
|---|---|---|---|---|
| **"PR #19: Release Production Gate & Autonomy Engine (MERGED)"** | Live GitHub Pull Request generated and merged by the autonomous agent. | `sonic-dashboard/app/page.tsx:674, 932-943` | Pure static text in JSX. Zero API calls to GitHub or local git reflog. | **100% FAKE / MOCK** |
| **"Thought for 3s" / "Thought for 20s"** | Live autonomous agent cognitive processing duration. | `sonic-dashboard/app/page.tsx:289, 295`<br>`sonic-core/sonic/api/routes/workstation.py:118, 125` | Static strings in template array (`_init_default_worklog()`). Not calculated from real LLM API latency. | **STATIC TEMPLATE** |
| **"Live OS: Ubuntu 22.04 LTS (Display :1)"** | Active virtual framebuffer / X11 desktop running inside a Linux sandbox. | `sonic-dashboard/app/page.tsx:691, 724` | Plain HTML `<span>` and `<strong>` tags. No VNC stream or X11 canvas. | **100% FAKE / MOCK** |
| **"CPU 14%, RAM 1.3GB / 8GB"** | Live sandbox OS resource telemetry. | `sonic-dashboard/app/page.tsx:703-705` | Hardcoded numbers in JSX. Zero `psutil`, `cgroups`, or Docker stats integration. | **100% FAKE / MOCK** |
| **"Devin typing at scenario_matrix.py"** | Active AI cursor modifying code in real-time. | `sonic-dashboard/app/page.tsx:790-794` | Absolute positioned `<div>` with CSS `animate-ping`. | **100% FAKE / MOCK** |
| **"Chromium — Live Application View Port"** | Embedded web browser running Playwright/sandbox browser. | `sonic-dashboard/app/page.tsx:829-851` | Static card with an SVG icon and text "FastAPI Backend Server live at http://127.0.0.1:8000". | **100% FAKE / MOCK** |
| **"VS Code — Live Editor"** | Realtime interactive IDE editor. | `sonic-dashboard/app/page.tsx:758-788`<br>`sonic-core/sonic/api/routes/workstation.py:241` | Read-only React line mapper reading local file contents via `workstation.py`. No Monaco/editor capabilities. | **READ-ONLY VIEWER** |
| **"sonic@sandbox:~$ (Terminal Execution)"** | Sandboxed shell running inside isolated Docker container. | `sonic-dashboard/app/page.tsx:268, 815`<br>`sonic-core/sonic/api/routes/workstation.py:271` | Executes `subprocess.run(req.command, shell=True)` **directly on the host OS**. | **REAL BUT UNCONTAINED (SECURITY BREACH)** |
| **"Live Git Diff"** | Realtime uncommitted git changes. | `sonic-dashboard/app/page.tsx:219, 901`<br>`sonic-core/sonic/api/routes/workstation.py:221` | Executes `git diff` on local repository and displays diff output. | **REAL + LOCAL** |
| **"Evidence Board — SHA-256 Chain of Custody"** | Live cryptographically verified vulnerability findings. | `sonic-dashboard/app/evidence/page.tsx:69-132` | Hardcoded `useState` array with static `find-jwt-none-01` dummy payload. Zero connection to `EvidenceEngine`. | **100% FAKE / MOCK** |
| **"Autonomous Self-Evolution Engine (v1.0.0 → v1.3.0)"** | Live multi-generation AI skill evolution. | `sonic-dashboard/app/evolution/page.tsx:39-80` | Hardcoded array with static F1 scores and cost numbers. | **100% FAKE / MOCK** |
| **"Self-Security Testing Lab (11/11 Passed)"** | Realtime adversarial penetration test suite. | `sonic-dashboard/app/security-lab/page.tsx:34-46` | Hardcoded list with synthetic durations ("12ms") and "PASS" verdicts. | **100% FAKE / MOCK** |
