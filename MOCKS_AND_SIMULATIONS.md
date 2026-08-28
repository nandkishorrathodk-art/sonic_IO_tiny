# SONIC-REDA — REGISTER OF MOCKS, HEURISTICS & SIMULATIONS
**Program**: SONIC-REDA 4-Way Independent Forensic Audit  
**Date**: 2026-08-28  

---

## 1. Inventory of Identified Mocks & Heuristics

The following components operate via heuristics or simulated scoring in offline development environments:

| Component | Location | Implementation Reality | Production Upgrade Path |
|---|---|---|---|
| **Offline Action Selection** | `sonic.computer_use.agent:choose_action` | Deterministic 5-step heuristic pipeline | Dynamic tool selection via live Gemini / Claude API |
| **Lab Fixture Scoring** | `sonic.evolution.lab:run_candidate_pipeline` | Calculated true positive ratio (`tp = int(N * 0.9)`) | Real multi-hour benchmark suite against live test targets |
| **Human Benchmark Baseline** | `sonic.mission_engine.benchmark` | Standardized empirical reference array | Controlled multi-developer live comparative study |
| **Offline Graph Memory** | `sonic.api.routes.graph` | In-memory graph dictionary | Live Neo4j 5 cluster connection via Bolt protocol |

---

## 2. Invariant Verification: Zero Mocks in Security Gates
- **Security Invariant**: No security, authentication, tenant isolation, or fail-closed gate relies on mocks or bypasses. All security rejections are computed via strict algorithms (SHA-256, JWT signature checks, and regex policy checks).
