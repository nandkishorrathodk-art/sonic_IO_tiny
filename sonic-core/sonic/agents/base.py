"""
SONIC-REDA — Base Agent Class (Skeleton)
==========================================
Abstract base that all SONIC agents inherit from.

Every agent has:
    - Access to the Model Router (for LLM calls)
    - Access to Graph Memory (for shared knowledge)
    - Access to Evidence Engine (for attaching proofs)
    - Safety checks before every action
    - Structured logging of all actions

Core agents (Phase 1):
    - MetaOrchestrator: High-level planning, task decomposition
    - ReconAgent: Surface mapping, tech detection, asset discovery
    - StaticReasoningAgent: Code analysis, dataflow, pattern matching
    - DynamicExecutionAgent: Live testing inside sandbox
    - HypothesisGenerator: Novel bug class ideation
    - VerifierAgent: Evidence checking, FP filtering
    - ExploitValidator: Safe PoC execution
    - CodeFixAgent: Generate fix + tests + PR
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from sonic.logger import get_logger

logger = get_logger(__name__)

from sonic.llm.router import ModelRouter
from sonic.llm.schemas import LLMRequest, LLMResponse, Message, MessageRole
from sonic.memory.graph import GraphMemory
from sonic.safety.scope import SafetyVerdict, ScopeChecker, RiskLevel


class BaseAgent(ABC):
    """
    Abstract base class for all SONIC-REDA agents.
    
    Every agent must implement:
        - run(): Main execution logic
        - get_system_prompt(): Agent's role/instructions
    """

    def __init__(
        self,
        agent_id: str | None = None,
        name: str = "BaseAgent",
        model_router: ModelRouter | None = None,
        graph_memory: GraphMemory | None = None,
        scope_checker: ScopeChecker | None = None,
    ):
        self.agent_id = agent_id or f"{name.lower()}-{uuid.uuid4().hex[:8]}"
        self.name = name
        self.router = model_router
        self.memory = graph_memory
        self.scope = scope_checker

        self.created_at = datetime.now(timezone.utc)
        self.status = "idle"  # idle, running, completed, failed
        self.action_log: list[dict] = []

        logger.info("agent_created", agent_id=self.agent_id, name=self.name)

    @abstractmethod
    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent's main task.
        
        Args:
            task: Task definition with target, scope, parameters
            
        Returns:
            Results dict with findings, evidence, status
        """
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return this agent's system prompt / role definition."""
        ...

    # ============================================
    # LLM Interaction
    # ============================================

    async def think(
        self,
        user_message: str,
        task_type: str = "reasoning",
        context: list[Message] | None = None,
    ) -> LLMResponse:
        """
        Send a thinking request to the LLM via the Model Router.
        
        Args:
            user_message: The prompt/question for the LLM
            task_type: Routing hint (reasoning, planning, coding, etc.)
            context: Optional previous messages for context
        """
        if not self.router:
            raise RuntimeError(f"Agent {self.agent_id} has no Model Router configured")

        messages = [
            Message(role=MessageRole.SYSTEM, content=self.get_system_prompt()),
        ]
        if context:
            messages.extend(context)
        messages.append(Message(role=MessageRole.USER, content=user_message))

        request = LLMRequest(
            messages=messages,
            task_type=task_type,
            agent_id=self.agent_id,
        )

        response = await self.router.complete(request, task_type=task_type)
        self._log_action("think", {"message": user_message[:100], "task_type": task_type})
        return response

    # ============================================
    # Safety
    # ============================================

    def check_safety(self, action: str, risk_level: RiskLevel = RiskLevel.L0_SAFE) -> SafetyVerdict:
        """Check if an action is allowed by the safety layer."""
        if not self.scope:
            logger.warning("no_scope_checker", agent_id=self.agent_id)
            return SafetyVerdict.BLOCKED  # Fail closed

        verdict = self.scope.check_action(action, risk_level)
        self._log_action("safety_check", {
            "action": action,
            "risk_level": risk_level,
            "verdict": verdict,
        })
        return verdict

    # ============================================
    # Memory
    # ============================================

    async def remember(self, label: str, data: dict[str, Any]) -> Optional[str]:
        """Store something in Graph Memory."""
        if not self.memory:
            return None
        data["created_by"] = self.agent_id
        data["created_at"] = datetime.now(timezone.utc).isoformat()
        return await self.memory.add_node(label, data)

    async def recall(self, query: str) -> list[dict]:
        """Query Graph Memory."""
        if not self.memory:
            return []
        return await self.memory.query(query)

    # ============================================
    # Logging
    # ============================================

    def _log_action(self, action_type: str, details: dict[str, Any]) -> None:
        """Log an agent action for audit trail."""
        entry = {
            "agent_id": self.agent_id,
            "action": action_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        self.action_log.append(entry)
        logger.info("agent_action", **entry)

    def get_status(self) -> dict:
        """Get agent's current status."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "actions_count": len(self.action_log),
        }

    def __repr__(self) -> str:
        return f"<{self.name} id={self.agent_id} status={self.status}>"
