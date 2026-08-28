# AUDIT C — SECURITY FINDINGS & VULNERABILITY REGISTER
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Auditor**: Independent Forensic Security Auditor  
**Date**: 2026-08-28  

---

## 1. Vulnerability Findings Summary

| Finding ID | Title | Severity | Impacted Area | Remediation Status |
|---|---|---|---|---|
| `SEC-FINDING-01` | HMAC Secret Length Warning in Test Harness | **LOW** | Test Config Defaults | Addressed (Prod requires $\ge 32$ chars) |
| `SEC-FINDING-02` | Malformed Token Decode Exception Interception | **LOW** | `sonic.auth.google_auth` | **REMEDIATED & VERIFIED** (Returns 401) |
| `SEC-FINDING-03` | Immutable Policy File Runtime Read-Only Barrier| **INFORMATIONAL**| `sonic.safety.scope` | **VERIFIED INVARIANT** |
| `SEC-FINDING-04` | Strict Multi-Tenant Scoping at DB & API Layers | **INFORMATIONAL**| `sonic.api.routes` | **VERIFIED INVARIANT** |

---

## 2. Detailed Vulnerability Analyses

### SEC-FINDING-01: HMAC Secret Key Length in Local Test Environment
- **Severity**: LOW / DEV ONLY
- **Observation**: Default test secrets (e.g. `"testsecret"`) are shorter than the RFC 7518 recommended 32-byte minimum for HS256, emitting PyJWT warnings in tests.
- **Production Guard**: `Settings.jwt_secret` defaults to requiring strong environment keys in production. `infra/docker-compose.staging.yml` enforces 64-byte random hex secrets.

### SEC-FINDING-02: Malformed Token Header Decoding
- **Severity**: LOW / REMEDIATED
- **Observation**: Non-UTF8 byte strings in Authorization Bearer headers previously triggered unhandled `DecodeError` inside PyJWT before hitting the HTTP handler.
- **Remediation**: `google_auth.decode_jwt_token` wrapped all decode exceptions safely, logging structured warnings and returning `None`, ensuring FastAPI returns standard `401 Unauthorized`.
