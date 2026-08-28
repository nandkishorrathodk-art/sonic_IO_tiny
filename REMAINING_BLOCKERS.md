# SONIC-REDA — REMAINING PRODUCTION BLOCKERS & CHECKLIST
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Date**: 2026-08-28  

---

## 1. Production Release Blocker Checklist

To graduate SONIC-REDA from **`RELEASE CANDIDATE (RC-1)`** to **`PRODUCTION READY (GA)`**, the following operational milestones must be completed:

- [ ] **1. Cloud API Keys Provisioning**: Set `DAYTONA_API_KEY`, `DAYTONA_API_URL`, `NEO4J_PASSWORD`, `GEMINI_API_KEY` in production environment.
- [ ] **2. Cloud Staging Deployment Run**: Deploy `infra/docker-compose.staging.yml` on a dedicated Linux VPS or AWS/GCP instance with Caddy TLS.
- [ ] **3. End-to-End Live Pentest Mission on Staging**: Run `sonic engage create --target http://staging.target.com` against a designated staging target.
- [ ] **4. Production Secret Key Hardening**: Generate a 64-character random hex string for `JWT_SECRET`.
- [ ] **5. Alembic Database Migration**: Execute database migrations against PostgreSQL 16 instance.
