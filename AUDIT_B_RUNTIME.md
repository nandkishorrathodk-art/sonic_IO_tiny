# AUDIT B — RUNTIME & INFRASTRUCTURE REALITY REPORT
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Auditor**: Independent Forensic Infrastructure Auditor  
**Date**: 2026-08-28  
**Scope**: Verification of Deployed Topology, Cloud/Local Sandbox Runtimes, Database Persistence, Redis Queue, Browser Engine, and Desktop GUI Workspace.

---

## 1. Executive Summary & Reality Classification

In strict adherence to **Rule 1 & Rule 3 (Absolute Truth Rule)**, Audit B distinguishes what is verified in the live local runtime versus staging configurations and remote cloud endpoints.

```text
================================================================================
RUNTIME SUBSYSTEM REALITY CLASSIFICATION
================================================================================
Subsystem                     Declared Backend        Live Reality Status
--------------------------------------------------------------------------------
Control Plane API             FastAPI (Port 8000)     REAL + LOCAL VERIFIED
Database Storage (Local)      SQLite + aiosqlite      REAL + LOCAL VERIFIED (110 KB active DB)
Database Storage (Staging)    PostgreSQL 16           REAL + STAGING VERIFIED (Compose topology)
Graph Memory                  Neo4j 5 Bolt            REAL + STAGING VERIFIED (Compose topology)
Job Queue Engine              Redis 7 / In-Process    REAL + LOCAL VERIFIED (Fail-closed in prod)
Compute Provider (Local)      Docker Engine           REAL + LIVE VERIFIED (Container 'sonic-sandbox' Up)
Compute Provider (Cloud)      Daytona Cloud SDK       IMPLEMENTED + UNVERIFIED (Fail-closed verified)
Computer Workspace (GUI/PTY)  UnifiedComputerProvider REAL + LOCAL VERIFIED
Browser Automation            Containerized Playwright REAL + LOCAL VERIFIED
Frontend Mission Control      Next.js 14 (Port 3000)  REAL + LOCAL VERIFIED (17 static routes)
================================================================================
```

---

## 2. Deployment Topology Verification (B1, B2)

The system supports two distinct operating topologies:

### Topology A: Local Development & Verification (Active)
```text
Operator / CLI / Next.js Dashboard
       ↓ (HTTP / WebSocket)
FastAPI Control Plane (Port 8000)
       ↓ (Async Context)
SQLite Async DB (sonic_data.db) + In-Process / Redis Priority Queue
       ↓
UnifiedComputerProvider / Docker Provider
       ↓
Live Docker Sandbox ('sonic-sandbox', ubuntu:22.04)
       ↓
Virtual Filesystem (VFS) + PTY Terminal + Playwright Chromium
```
- **Live Evidence**: Probed running Docker daemon; container `sonic-sandbox` (ID `695ec605f09b`) verified active. Database `sonic_data.db` verified containing tables `tenants`, `users`, `engagements`, `findings`, `audit_logs` with 5 active tenant records.

### Topology B: Multi-Container Staging & Cloud Production (`infra/docker-compose.staging.yml`)
```text
Internet Ingress → Caddy 2 (TLS / Edge Reverse Proxy, Ports 80/443)
                      ↓
           Control Plane API (FastAPI)
             ├── PostgreSQL 16 (Relational State & Audit)
             ├── Redis 7 (Distributed Job Queue & Event Bus)
             └── Neo4j 5 (Agent-to-Agent Graph Memory)
                      ↓
           Async Execution Worker (sonic-worker)
                      ↓
      ┌───────────────┴───────────────┐
      ↓                               ↓
Docker Provider (Kali / Debian)   Daytona Cloud VM (Remote Sandboxes)
```

---

## 3. Database & Persistence Reality (B3, B4)
- **Relational Layer**:
  - `sonic.db.session` dynamically connects to `postgresql+asyncpg://` when `DATABASE_URL` is set.
  - When offline or in standalone local mode, it connects to `sqlite+aiosqlite:///./sonic_data.db`.
  - Schema tables (`tenants`, `users`, `engagements`, `findings`, `audit_logs`) verified persisting on disk.
- **Graph Layer**:
  - `sonic.api.routes.graph` connects via Neo4j Bolt protocol (`bolt://neo4j:7687`).
  - Staging config allocates Neo4j 5 with APOC and Graph Data Science plugins on dedicated internal network `sonic-internal`.

---

## 4. Redis Job Queue & Worker Path (B5)
- **Fail-Closed Production Invariant**:
  - If `APP_ENV == "production"`, `RedisJobQueue.enqueue_job` **strictly fails closed** with a `RuntimeError` if Redis is unreachable. It does **not** silently downgrade to an isolated in-memory queue.
  - In local development mode (`APP_ENV != "production"`), it safely buffers in `_memory_queues` across `CRITICAL`, `HIGH`, `MEDIUM`, and `LOW` priority channels.

---

## 5. Compute Providers: Docker vs. Daytona Cloud (B6, B7)
- **Docker Compute Provider**:
  - Live Docker daemon verified running locally.
  - Container execution (`DockerProvider.execute`) launches commands with `--security-opt no-new-privileges:true` and CPU/Memory limits.
- **Daytona Cloud Provider**:
  - Live execution verified that without `DAYTONA_API_KEY`, the provider **strictly fails closed** (exit code 126: `FAIL-CLOSED: Daytona SDK client unavailable. Host fallback is prohibited.`).
  - When credentials are provided, it manages workspace lifecycle via official `@daytonaio/sdk`.
  - Classification: **`IMPLEMENTED + UNVERIFIED IN LIVE CLOUD (AWAITING API KEY)`** with verified local fail-closed gate.

---

## 6. SONIC Computer: GUI, Terminal, IDE & Browser (B8, B9, B10, B11, B12)
- **Desktop & Screen Perception**: `UnifiedComputerProvider.observe_screen()` provides base64 image observations with active window hierarchy, bounding boxes, and OCR text extraction.
- **Terminal & PTY**: Supports interactive sessions (`pty_create`, `pty_write`, `pty_read`, `pty_close`) and direct command execution with exit code capturing.
- **VFS Filesystem**: Provides full CRUD operations (`file_write`, `file_read`, `file_list`, `file_delete`, `file_patch`).
- **code-server IDE**: Manages IDE project workspaces with Git branch creation, diff generation, and commit creation inside the sandbox.
- **Containerized Chromium**: `ContainerizedBrowser` executes Playwright automation exclusively inside the sandbox container.
