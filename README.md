# SONIC-REDA
### Next-Generation Autonomous AI Bug Hunting System

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red.svg)]()

> **Codename:** SONIC A-SEA (Autonomous Self-Evolving Penetration Architect)  
> **Status:** Phase 22 — Native Docker Cyber Workstation & Autonomous Reasoning  
> 
> 🤖 **If you are an AI Coding Agent working on this repository, please read [AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md) and [BLUEPRINT.md](BLUEPRINT.md) first!**

---

## What is SONIC-REDA?

The most powerful, self-evolving, multi-agent AI red-team system that combines:

- 🖥️ **Devin-style** full virtual computer control
- 🔴 **RedAmon-level** autonomous kill-chain power
- 🧠 **True multi-agent swarm intelligence** with Agent-to-Agent Graph Memory
- 🎯 **Autonomous pentest loop** — Observe → Think → Act → Re-probe, keeps
  going until the kill-chain is proven (no more one-shot-and-stop)
- 📋 **Mandatory Evidence Engine** — zero hallucination tolerance, every
  finding ships with the real request + response that proved it
- 🔄 **Controlled self-development** with measurable improvement
- 🛡️ **Production-grade safety** + rollback (default-deny egress, scope, rate-limit)

## Architecture

```
┌──────────────────────────────────────────────┐
│       Immutable Safety & Scope Layer         │
├──────────────────────────────────────────────┤
│       Meta / Self-Development Layer          │
├──────────────────────────────────────────────┤
│       Sonic Agentic Graph (Core Brain)       │
│  Orchestrator ↔ Recon ↔ Reasoning ↔ Dynamic │
│  Hypothesis ↔ Verifier ↔ Exploit ↔ CodeFix  │
├──────────────────────────────────────────────┤
│       Virtual Computer Layer (Sandbox)       │
└──────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Node.js 20+ (for dashboard)
- A Google Cloud project with OAuth2 credentials

### Setup

```bash
# 1. Clone and enter the project
git clone https://github.com/nandkishorrathodk-art/sonic.git
cd sonic

# 2. Copy environment template
cp .env.example .env
# Edit .env with your API keys and Google OAuth credentials

# 3. Start infrastructure (Neo4j + Redis)
#    Neo4j is OPTIONAL in dev — the backend falls back to an in-memory
#    graph store if localhost:7687 is unreachable.
docker-compose up -d

# 4. Install Python dependencies
pip install -e sonic-core[dev]
pip install -e sonic-cli[dev]

# 5. Start the backend
#    uvicorn is not on PATH; invoke it as a module:
APP_ENV=development python -m uvicorn sonic.api.main:app --port 12000 --reload

# 6. Start Native Docker Cyber Workstation
docker start sonic-desktop-workstation
# Stream live XFCE4 desktop at: http://localhost:6080/vnc.html

# 7. Launch Autonomous Agent Mission
python scripts/launch_agent.py
```

## Project Structure

```
sonic/
├── sonic-core/          # 🧠 Core Python backend (FastAPI)
│   └── sonic/
│       ├── auth/        # Google OAuth2 + JWT
│       ├── llm/         # Abstract LLM Provider + Model Router
│       ├── agents/      # Multi-agent system
│       ├── memory/      # Neo4j Graph Memory
│       ├── safety/      # Immutable Safety Layer
│       ├── evidence/    # Evidence Engine
│       └── api/         # REST API
├── sonic-cli/           # ⌨️ CLI (Typer + Rich)
├── sonic-dashboard/     # 🖥️ Next.js Dashboard
└── configs/             # 📋 Shared YAML configs
```

## Core Principles

1. **Evidence > Claims** — No finding without proof
2. **Speed without chaos** — Sonic fast, never reckless
3. **Shared intelligence** — Graph Memory for all agents
4. **Self-improvement** — Only through measured experiments
5. **Immutable safety** — Core rules cannot be modified by agents
6. **Human authority** — Final say on high-risk actions

## License

Proprietary — All rights reserved.
