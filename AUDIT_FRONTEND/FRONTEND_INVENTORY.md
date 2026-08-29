# SONIC-REDA — FRONTEND FORENSIC INVENTORY

**Date:** 2026-08-28  
**Audit Target:** `sonic-dashboard/`  
**Classification Baseline:** Complete Repository & Runtime Scan  

---

## 1. Directory Structure Analysis

The dashboard repository `sonic-dashboard/` has an unconventional, completely flattened structure with **zero shared components, zero state stores, zero API service modules, and zero authentication contexts**:

```text
sonic-dashboard/
├── package.json
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── Dockerfile
└── app/
    ├── globals.css
    ├── layout.tsx
    ├── page.tsx                    (Main Devin-Style Workstation Interface - 982 lines, 46KB)
    ├── computer/page.tsx           (Autonomous Computer & Workspace Mock)
    ├── engineer/page.tsx           (Autonomous Engineer Decision Stream Mock)
    ├── evidence/page.tsx           (Evidence Board Mock)
    ├── evolution/page.tsx          (Self-Evolution Engine Mock)
    ├── experiments/page.tsx        (Canary Benchmark Lab - Partial Backend Connected)
    ├── graph/page.tsx              (Agent Graph Memory - Partial Backend Connected)
    ├── mission/page.tsx            (Cognitive Mission Reasoning Mock)
    ├── missions/page.tsx           (Long-Horizon Mission Owner Mock)
    ├── research/page.tsx           (Autonomous Researcher Engine Mock)
    ├── sandbox/page.tsx            (Sandbox Fleet Manager Mock)
    ├── security-lab/page.tsx       (Self-Security Testing Lab Mock)
    ├── settings/page.tsx           (Runtime Settings - Connected)
    └── terminal/page.tsx           (WebSocket PTY Terminal - Broken Auth/Simulated)
```

### Missing Architecture Components
1. **No `components/` Directory**: No modular UI components; each page is a monolithic 200–980 line single-file component with inline HTML and duplicate SVG icons.
2. **No `lib/` or `services/` Directory**: No centralized API client, HTTP interceptors, or error-handling abstractions.
3. **No `stores/` or `providers/`**: No Redux, Zustand, React Context, or state persistence across routes.
4. **No Auth Providers/Tokens**: No JWT storage (localStorage/cookies), no login page, no token injection headers in requests.
5. **No Route Protection**: Zero middleware or client guards for multi-tenancy or access control.

---

## 2. Page & Route Inventory Summary

| Route | Source File | Lines | Bytes | API Calls | WebSockets | Real Backend Connected? | Classification |
|---|---|---|---|---|---|---|---|
| `/` | `app/page.tsx` | 982 | 46,030 | 6 (`/workstation/*`) | 0 | **Partial / Hybrid Mock** | `PARTIAL` / `SIMULATED` |
| `/computer` | `app/computer/page.tsx` | 344 | 18,441 | 0 | 0 | **None (100% Static HTML)** | `MOCK` |
| `/engineer` | `app/engineer/page.tsx` | 353 | 15,278 | 0 | 0 | **None (100% Hardcoded)** | `MOCK` / `SIMULATED` |
| `/evidence` | `app/evidence/page.tsx` | 371 | 17,570 | 0 | 0 | **None (Static Data Array)** | `HARDCODED` |
| `/evolution` | `app/evolution/page.tsx` | 297 | 13,966 | 0 | 0 | **None (Static Data Array)** | `HARDCODED` |
| `/experiments` | `app/experiments/page.tsx` | 220 | 8,890 | 2 (`/live/experiments*`) | 0 | **Yes (FastAPI Live API)** | `REAL + LOCAL` |
| `/graph` | `app/graph/page.tsx` | 152 | 6,914 | 1 (`/live/graph`) | 0 | **Yes (FastAPI Live API)** | `REAL + LOCAL` |
| `/mission` | `app/mission/page.tsx` | 341 | 16,044 | 0 | 0 | **None (Static Data Array)** | `HARDCODED` |
| `/missions` | `app/missions/page.tsx` | 318 | 12,807 | 0 | 0 | **None (Static Data Array)** | `HARDCODED` |
| `/research` | `app/research/page.tsx` | 305 | 15,419 | 0 | 0 | **None (100% Static HTML)** | `MOCK` |
| `/sandbox` | `app/sandbox/page.tsx` | 143 | 6,007 | 0 | 0 | **None (Static Data Array)** | `HARDCODED` |
| `/security-lab` | `app/security-lab/page.tsx` | 245 | 13,782 | 0 | 0 | **None (Static Data Array)** | `HARDCODED` |
| `/settings` | `app/settings/page.tsx` | 202 | 8,984 | 2 (`/live/settings`) | 0 | **Yes (FastAPI Live API)** | `REAL + LOCAL` |
| `/terminal` | `app/terminal/page.tsx` | 187 | 8,174 | 0 | 1 (`/terminal/ws/terminal`) | **Broken (Missing Auth Token, Local Echo)** | `BROKEN` / `SIMULATED` |
