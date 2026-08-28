# AUDIT B — INFRASTRUCTURE SPECIFICATION & CONFIGURATION
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Auditor**: Independent Forensic Infrastructure Auditor  
**Date**: 2026-08-28  

---

## 1. Network Topology & Micro-Segmentation

The production/staging configuration (`infra/docker-compose.staging.yml`) enforces micro-segmentation into two isolated virtual networks:

```text
+-------------------------------------------------------------------------+
| DMZ Network ('sonic-dmz')                                               |
|  • Ingress: Caddy Edge Proxy (Ports 80, 443)                            |
|  • Web API: FastAPI Control Plane (Internal Port 8000)                  |
|  • Dashboard: Next.js Frontend (Internal Port 3000)                     |
+-------------------------------------------------------------------------+
                                    │
                                    ▼ (Controlled Internal Routing)
+-------------------------------------------------------------------------+
| Internal Backend Network ('sonic-internal', internal: true)             |
|  • Relational DB: PostgreSQL 16 (Port 5432) — Isolated                  |
|  • Cache & Queues: Redis 7 (Port 6379) — Isolated                       |
|  • Graph Memory: Neo4j 5 (Bolt 7687, HTTP 7474) — Isolated              |
|  • Async Worker: sonic-worker — Internal execution plane                |
+-------------------------------------------------------------------------+
                                    │
                                    ▼ (Compute Sandbox Network)
+-------------------------------------------------------------------------+
| Sandbox Network ('sonic-sandbox-net')                                   |
|  • Kali Linux Workspace (sonic-sandbox-kali)                            |
|  • Debian Workspace (sonic-sandbox-debian)                              |
+-------------------------------------------------------------------------+
```

---

## 2. Container Hardening & Resource Ceilings

| Service Container | Base Image | CPU Quota | Memory Limit | Security Profile | Network Access |
|---|---|---|---|---|---|
| `sonic-control-plane` | Python 3.12 Slim | 2.0 Cores | 1024 MB | Non-root `sonic` user | `sonic-dmz`, `sonic-internal` |
| `sonic-worker` | Python 3.12 Slim | 4.0 Cores | 2048 MB | Non-root `sonic` user | `sonic-internal` |
| `sonic-sandbox-kali` | Kali Rolling | 2.0 Cores | 2048 MB | `no-new-privileges:true` | `sonic-sandbox-net` (Isolated) |
| `sonic-sandbox-debian`| Debian 12 Slim | 2.0 Cores | 1024 MB | `no-new-privileges:true` | `sonic-sandbox-net` (Isolated) |
| `postgres` | Postgres 16 Alpine | 2.0 Cores | 1024 MB | PostgreSQL Standard | `sonic-internal` only |
| `redis` | Redis 7 Alpine | 1.0 Cores | 256 MB | LRU eviction policy | `sonic-internal` only |
| `neo4j` | Neo4j 5 Community | 2.0 Cores | 1024 MB Heap | APOC Plugins | `sonic-internal` only |

---

## 3. Health Checks & Autonomous Probes

All staging containers declare automated healthchecks:
- **FastAPI Control Plane**: `curl -f http://localhost:8000/health` (Interval: 10s, Timeout: 5s, Retries: 3)
- **PostgreSQL**: `pg_isready -U sonic_admin -d sonic_db` (Interval: 10s, Timeout: 5s, Retries: 5)
- **Redis**: `redis-cli ping` (Interval: 10s, Timeout: 5s, Retries: 5)
- **Neo4j**: `wget --spider http://localhost:7474` (Interval: 10s, Timeout: 5s, Retries: 5)
- **Caddy Edge**: `caddy validate --config /etc/caddy/Caddyfile`
