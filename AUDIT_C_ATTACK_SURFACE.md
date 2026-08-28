# AUDIT C — COMPLETE ATTACK SURFACE ENUMERATION
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Auditor**: Independent Forensic Security Auditor  
**Date**: 2026-08-28  
**Scope**: Black-Box and White-Box Attack Surface Enumeration across 15 Subsystems.

---

## 1. Attack Surface Taxonomy & Entrypoints

```text
+-------------------------------------------------------------------------------+
| EXTERNAL ATTACK VECTORS                                                       |
|  • Web API & Ingress: FastAPI REST endpoints, WebSocket streaming             |
|  • Identity & Access: Google OAuth2 callback, JWT Bearer tokens, RBAC roles   |
|  • Command Line: Typer CLI (`sonic mission`, `sonic computer`, `sonic auth`)  |
+-------------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------------+
| PLATFORM INTERNALS & DATA VECTORS                                             |
|  • State Stores: SQLite / PostgreSQL tables, Redis job queue, Neo4j graph      |
|  • Computer Body: UnifiedComputerProvider, VFS filesystem, PTY streams        |
|  • AI Engines: Prompt inputs, tool outputs, research memory, evolution lab    |
+-------------------------------------------------------------------------------+
                                    │
                                    ▼
+-------------------------------------------------------------------------------+
| COMPUTE SANDBOX & HOST ISOLATION                                              |
|  • Container Plane: Docker engine, Kali/Debian container sandboxes            |
|  • Cloud Sandbox: Daytona SDK execution                                       |
|  • Network Egress: Scope checker, metadata endpoint filter, RFC1918 blocks    |
+-------------------------------------------------------------------------------+
```

---

## 2. Comprehensive Endpoint & Interface Inventory

| Vector Category | Specific Interface / Endpoint | Required Privilege | Threat Model | Security Defense |
|---|---|---|---|---|
| **Auth** | `/auth/google/login`, `/auth/google/callback` | Public | Token forgery, replay, code exchange hijacking | State verification, allowlist domain check |
| **Engagements** | `/engagements/create`, `/engagements/{id}` | `require_auth` | Cross-tenant ID substitution, unauthorized scans | Mandatory `tenant_id` scoping in DB queries |
| **Graph Query** | `/graph/query` | `require_super_admin` | Cypher injection, unauthorized graph dumps | Strict `SUPER_ADMIN` check (403 Forbidden) |
| **Job Queue** | `/jobs/enqueue`, `/jobs/{id}` | `require_operator` | Queue exhaustion, priority tampering | Redis hash auth + worker tenant validation |
| **Terminal WebSocket** | `/ws/terminal/{workspace_id}` | `verify_ws_token` | PTY session hijacking, command injection | JWT verification + workspace tenant ownership |
| **Computer VFS** | `UnifiedComputerProvider.file_write` | `ComputerSession` | Path traversal, host file overwrite | Sandbox chroot/container isolation |
| **Browser Runtime** | `ContainerizedBrowser.execute_script` | `ComputerSession` | Host browser launch, SSRF, XSS | Headless Chromium isolated inside container |
| **Evidence Store** | `EvidenceCustodyManager` | Internal Agent | Evidence modification, false positive coverup | SHA-256 content hashing & custody manifests |
| **Self-Evolution** | `CandidateGenerator.create_candidate` | Internal Engine | Self-loosening safety policies, backdoor | Immutable `EvolutionPolicy` hard blocks |
| **Network Egress** | `ScopeChecker.is_target_in_scope` | Tool Execution | Cloud metadata attack (`169.254.169.254`) | Immutable YAML safety rules + fail-closed |
