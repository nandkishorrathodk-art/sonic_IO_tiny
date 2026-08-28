# SONIC-REDA — UNVERIFIED CAPABILITIES REGISTER
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Date**: 2026-08-28  

---

## 1. Unverified Cloud / External Endpoints

The following capabilities are fully implemented in source code but remain **unverified in live remote cloud environments** due to absence of external cloud API credentials in the local evaluation environment:

| Capability | Module Path | Status | Reason Unverified |
|---|---|---|---|
| **Daytona Cloud Remote VM Fleet** | `sonic.sandbox.providers.daytona_provider` | `IMPLEMENTED + UNVERIFIED` | Missing `DAYTONA_API_KEY` (Fail-closed exit code 126 verified) |
| **Remote Neo4j Cloud Graph Cluster** | `sonic.api.routes.graph` | `IMPLEMENTED + UNVERIFIED` | Missing remote Bolt URI & cluster credentials |
| **Google Cloud OAuth Live Callback** | `sonic.auth.google_auth` | `IMPLEMENTED + UNVERIFIED` | Requires live public domain redirect URI |
| **Live Multi-LLM API Dynamic Routing**| `sonic.llm.router` | `IMPLEMENTED + UNVERIFIED` | Requires active OpenAI / Claude API keys |
