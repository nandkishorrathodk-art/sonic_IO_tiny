"""
SONIC-REDA Core
===============
Next-Generation Autonomous AI Bug Hunting System — Core Engine.

Modules:
    - auth: Google OAuth2 + JWT authentication
    - llm: Abstract LLM Provider + Model Router
    - agents: Multi-agent system (Orchestrator, Recon, Reasoning, etc.)
    - memory: Agent-to-Agent Graph Memory (Neo4j + Vector)
    - safety: Immutable Safety & Scope Layer
    - evidence: Mandatory Evidence Engine
    - api: FastAPI REST API
"""

__version__ = "0.1.0"
__codename__ = "SONIC-REDA"
