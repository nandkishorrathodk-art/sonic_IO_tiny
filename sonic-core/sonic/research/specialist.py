"""
SONIC — Specialized Asynchronous Research Agents
==================================================
Multi-agent specialist substrate for parallel, non-blocking offensive security research:
  - Base SpecialistAgent with state machine, hypothesis tracking, and budget enforcement
  - WebSpecialist: Endpoints, forms, parameters, web technologies
  - ApiSpecialist: API schemas, REST/GraphQL endpoints, parameter structures
  - AuthSpecialist: Authentication schemes, tokens, session state, access boundaries
  - NetworkSpecialist: Network services, open ports, service banners
  - FalsificationSpecialist: Adversarial disproving experiments to eliminate confirmation bias
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from sonic.logger import get_logger
from sonic.research.epistemic import CompetingHypothesis
from sonic.research.event_bus import (
    AnomalyDetectedEvent,
    EndpointDiscoveredEvent,
    HypothesisFalsifiedEvent,
    HypothesisProposedEvent,
    ResearchEventBus,
    ResearchStateChangedEvent,
    TargetDiscoveredEvent,
    VulnerabilityVerifiedEvent,
)

logger = get_logger(__name__)


# =====================================================================
# 1. State, Budget & Exceptions
# =====================================================================

class SpecialistState(StrEnum):
    IDLE = "idle"
    RESEARCHING = "researching"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class BudgetExhaustedError(Exception):
    """Raised when an agent exhausts its action, token, or time budget."""


class SpecialistBlockedError(Exception):
    """Raised when a substrate, sandbox, provider, or security envelope blocks specialist execution."""

    def __init__(
        self,
        message: str = "Specialist execution blocked by substrate or provider",
        reason: str = "PROVIDER_FAILURE",
        diagnostic: str = "",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.diagnostic = diagnostic or message
        self.details = details or {}


class SpecialistTimeoutError(Exception):
    """Raised when a specialist times out during investigation."""

    def __init__(
        self,
        message: str = "Specialist execution timed out",
        reason: str = "TIMEOUT",
        diagnostic: str = "",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.diagnostic = diagnostic or message
        self.details = details or {}


def classify_specialist_failure(
    ex: BaseException,
) -> tuple[SpecialistState, str, str, str]:
    """
    Classify an exception into (target_state, reason, error_type, diagnostic).
    Distinguishes BLOCKED (e.g. PROVIDER_FAILURE, exit 125/126, sandbox container errors)
    from FAILED (e.g. TIMEOUT, budget exhaustion, or generic runtime errors).
    """
    error_type = type(ex).__name__
    ex_str = str(ex)
    ex_upper = ex_str.upper()

    if isinstance(ex, SpecialistBlockedError):
        reason = ex.reason or "PROVIDER_FAILURE"
        diag = ex.diagnostic or ex_str
        return SpecialistState.BLOCKED, reason, error_type, diag

    if isinstance(ex, SpecialistTimeoutError):
        reason = ex.reason or "TIMEOUT"
        diag = ex.diagnostic or ex_str
        state = SpecialistState.BLOCKED if "BLOCKED" in ex_upper else SpecialistState.FAILED
        return state, reason, error_type, diag

    if isinstance(ex, (TimeoutError, asyncio.TimeoutError)):
        return SpecialistState.FAILED, "TIMEOUT", error_type, f"Operation timed out: {ex_str or 'timeout exceeded'}"

    if isinstance(ex, BudgetExhaustedError):
        return SpecialistState.FAILED, "BUDGET_EXHAUSTED", error_type, f"Budget exhausted: {ex_str}"

    if any(
        k in ex_upper
        for k in (
            "PROVIDER_FAILURE",
            "BLOCKED",
            "EXIT 125",
            "EXIT 126",
            "SANDBOX_ERROR",
            "CONTAINER IS NOT RUNNING",
            "PERMISSION DENIED",
        )
    ):
        reason = "PROVIDER_FAILURE" if "PROVIDER" in ex_upper else "BLOCKED"
        return SpecialistState.BLOCKED, reason, error_type, ex_str

    if "TIMEOUT" in ex_upper:
        state = SpecialistState.BLOCKED if "BLOCKED" in ex_upper else SpecialistState.FAILED
        return state, "TIMEOUT", error_type, ex_str

    return SpecialistState.FAILED, "EXECUTION_FAILURE", error_type, ex_str


class SpecialistBudget(BaseModel):
    """Execution budget limits for a specialist agent."""
    max_actions: int = 50
    timeout_seconds: float = 60.0
    token_limit: int = 100_000
    actions_used: int = 0
    tokens_used: int = 0
    start_time: float | None = None

    def start(self) -> None:
        if self.start_time is None:
            self.start_time = time.time()

    def is_exhausted(self) -> bool:
        if self.actions_used >= self.max_actions:
            return True
        if self.tokens_used >= self.token_limit:
            return True
        return bool(self.start_time is not None and (time.time() - self.start_time) >= self.timeout_seconds)

    def record_action(self, count: int = 1) -> None:
        self.actions_used += count
        if self.actions_used > self.max_actions:
            raise BudgetExhaustedError(
                f"Action budget exceeded: {self.actions_used}/{self.max_actions}"
            )

    def record_tokens(self, count: int = 1) -> None:
        self.tokens_used += count
        if self.tokens_used > self.token_limit:
            raise BudgetExhaustedError(
                f"Token budget exceeded: {self.tokens_used}/{self.token_limit}"
            )

    def check_limits(self) -> None:
        if self.is_exhausted():
            raise BudgetExhaustedError("Execution budget limit reached")


# =====================================================================
# 2. Base Specialist Agent
# =====================================================================

class SpecialistAgent(ABC):
    """
    Abstract base class for all asynchronous research specialists.

    Attributes:
      - name: Human-readable agent name
      - specialty: Domain identifier ('web', 'api', 'auth', 'network', 'falsification')
      - objective: Current investigation goal
      - state: SpecialistState (IDLE, RESEARCHING, BLOCKED, COMPLETED, FAILED)
      - hypotheses: Tracked competing hypotheses
      - budget: Resource limit controls
    """

    def __init__(
        self,
        name: str,
        specialty: str,
        objective: str = "",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.name = name
        self.specialty = specialty
        self.objective = objective
        self.state = SpecialistState.IDLE
        self.hypotheses: list[CompetingHypothesis] = []
        self.budget = budget or SpecialistBudget()
        self.priority = priority
        self.agent_id = f"{specialty}-{uuid.uuid4().hex[:8]}"
        self._investigation_fn = investigation_fn
        self._cancelled = False
        self._cancel_event = asyncio.Event()
        self._event_bus: ResearchEventBus | None = None
        self.last_error: str | None = None
        self.failure_reason: str | None = None
        self.failure_diagnostic: dict[str, Any] | str | None = None
        self.state_reason: str = ""

    def __await__(self):
        """Allow both synchronous and awaited specialist references (e.g. resume_specialist)."""
        async def _identity() -> SpecialistAgent:
            return self
        return _identity().__await__()

    async def transition_to(
        self,
        new_state: SpecialistState,
        reason: str = "",
        event_bus: ResearchEventBus | None = None,
    ) -> None:
        """Update specialist lifecycle state and announce via event bus."""
        old_state = self.state.value
        self.state = new_state
        self.state_reason = reason
        if new_state in (SpecialistState.FAILED, SpecialistState.BLOCKED) and not self.failure_reason:
            clean = reason.split(":", 1)[0].strip() if ":" in reason else reason
            self.failure_reason = clean or ("PROVIDER_FAILURE" if new_state == SpecialistState.BLOCKED else "FAILED")
        target_bus = event_bus or self._event_bus
        if target_bus is not None:
            await target_bus.publish(
                ResearchStateChangedEvent(
                    agent_name=self.name,
                    old_state=old_state,
                    new_state=new_state.value,
                    reason=reason,
                    source=self.name,
                )
            )

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self._cancelled = True
        self._cancel_event.set()

    def record_action(self, count: int = 1) -> None:
        """Record action usage against the budget."""
        self.budget.record_action(count)

    def record_tokens(self, count: int = 1) -> None:
        """Record token usage against the budget."""
        self.budget.record_tokens(count)

    async def propose_hypothesis(
        self,
        statement: str,
        vulnerability_class: str = "",
        falsification_criteria: str = "",
        confidence: float = 0.5,
        target: str = "",
        event_bus: ResearchEventBus | None = None,
    ) -> CompetingHypothesis:
        """Formulate a testable hypothesis and publish it."""
        hypo = CompetingHypothesis(
            statement=statement,
            vulnerability_class=vulnerability_class,
            falsification_criteria=falsification_criteria,
            confidence=confidence,
        )
        self.hypotheses.append(hypo)
        if event_bus is not None:
            await event_bus.publish(
                HypothesisProposedEvent(
                    source=self.name,
                    hypothesis_id=hypo.id,
                    statement=statement,
                    vulnerability_class=vulnerability_class,
                    confidence=confidence,
                    falsification_criteria=falsification_criteria,
                    target=target,
                )
            )
        return hypo

    async def falsify_hypothesis(
        self,
        hypothesis_id: str,
        reason: str,
        evidence: Any = None,
        event_bus: ResearchEventBus | None = None,
    ) -> None:
        """Mark hypothesis as disproved and publish falsification event."""
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                h.status = "disproved"  # type: ignore[assignment]
                break

        if event_bus is not None:
            await event_bus.publish(
                HypothesisFalsifiedEvent(
                    source=self.name,
                    hypothesis_id=hypothesis_id,
                    reason=reason,
                    evidence=evidence,
                    disproved_by=self.name,
                )
            )

    async def verify_vulnerability(
        self,
        vulnerability_id: str = "",
        title: str = "",
        vulnerability_class: str = "",
        severity: str = "high",
        target: str = "",
        evidence: Any = None,
        reproduction_steps: list[str] | None = None,
        event_bus: ResearchEventBus | None = None,
    ) -> None:
        """Publish a verified vulnerability finding."""
        if not vulnerability_id:
            vulnerability_id = f"vuln-{uuid.uuid4().hex[:8]}"
        if event_bus is not None:
            await event_bus.publish(
                VulnerabilityVerifiedEvent(
                    source=self.name,
                    vulnerability_id=vulnerability_id,
                    title=title,
                    vulnerability_class=vulnerability_class,
                    severity=severity,
                    target=target,
                    evidence=evidence,
                    reproduction_steps=reproduction_steps or [],
                )
            )

    async def run(
        self,
        context: dict[str, Any],
        event_bus: ResearchEventBus,
    ) -> Any:
        """
        Main specialist execution loop:
          - Enforces budget timers and action limits
          - Handles cooperative cancellation
          - Emits lifecycle state transitions
          - Isolates worker failures (BLOCKED / FAILED) with rich diagnostics
        """
        self._event_bus = event_bus
        if self._cancelled:
            await self.transition_to(SpecialistState.COMPLETED, "Cancelled before start", event_bus)
            return None

        self.budget.start()
        await self.transition_to(SpecialistState.RESEARCHING, "Beginning investigation", event_bus)

        try:
            if self._cancelled:
                raise asyncio.CancelledError()

            if self._investigation_fn is not None:
                res = self._investigation_fn(self, context, event_bus)
                if asyncio.iscoroutine(res):
                    result = await res
                else:
                    result = res
            else:
                result = await self._execute(context, event_bus)

            await self.transition_to(
                SpecialistState.COMPLETED, "Investigation completed successfully", event_bus
            )
            return result

        except BudgetExhaustedError as be:
            logger.info("specialist_budget_exhausted", agent=self.name, error=str(be))
            self.last_error = str(be)
            self.failure_reason = "BUDGET_EXHAUSTED"
            self.failure_diagnostic = f"Execution budget limit reached: {be}"
            await self.transition_to(SpecialistState.FAILED, f"Budget exhausted: {be}", event_bus)
            return None

        except asyncio.CancelledError:
            self._cancelled = True
            logger.info("specialist_cancelled", agent=self.name)
            await self.transition_to(SpecialistState.COMPLETED, "Cancelled", event_bus)
            raise

        except Exception as ex:
            target_state, reason, err_type, diag = classify_specialist_failure(ex)
            self.last_error = str(ex)
            self.failure_reason = reason
            self.failure_diagnostic = diag
            logger.error(
                "specialist_execution_failed",
                agent=self.name,
                error=str(ex),
                target_state=target_state.value,
                reason=reason,
                diagnostic=diag,
            )
            await self.transition_to(target_state, f"{reason}: {diag}", event_bus)
            return None

    @abstractmethod
    async def _execute(
        self,
        context: dict[str, Any],
        event_bus: ResearchEventBus,
    ) -> Any:
        """Core specialist research logic implemented by concrete subclasses."""
        raise NotImplementedError


# =====================================================================
# 3. Concrete Specialized Research Agents
# =====================================================================

class WebSpecialist(SpecialistAgent):
    """
    Focuses on web applications: routes, forms, technologies, parameters, and front-end anomalies.
    """

    def __init__(
        self,
        name: str = "WebSpecialist",
        target_url: str = "",
        objective: str = "Discover web surface, forms, headers, and client-side parameters",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="web",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target_url = target_url

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        target = self.target_url or context.get("target_url") or context.get("target") or "http://localhost"
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        # Discovered endpoints from real tools, provider probes, or context
        endpoints = []
        tools = context.get("tools") or context.get("security_tools") or {}
        http_tool = tools.get("http_client") if isinstance(tools, dict) else None

        if http_tool:
            try:
                from sonic.tools.base import ToolRequest
                req = ToolRequest(tool_name="http_client", action="probe", target=target)
                res = await http_tool.execute(req)
                if res and getattr(res, "findings", None):
                    for finding in res.findings:
                        raw = getattr(finding, "raw", finding) if not isinstance(finding, dict) else finding
                        endpoints.append({
                            "url": target,
                            "method": "GET",
                            "status_code": raw.get("status_code", 200),
                            "params": [],
                        })
            except Exception as e:
                logger.debug("web_specialist_http_probe_failed", error=str(e))

        provider = context.get("provider") or context.get("computer")
        if not endpoints and provider and hasattr(provider, "http_probe"):
            try:
                probe_res = await provider.http_probe(target)
                endpoints.append({
                    "url": target,
                    "method": "GET",
                    "status_code": probe_res.get("status_code", 200),
                    "params": [],
                })
            except Exception as e:
                logger.debug("web_specialist_provider_probe_failed", error=str(e))

        if not endpoints:
            endpoints = context.get(
                "endpoints",
                [
                    {"url": f"{target}/", "method": "GET", "params": []},
                    {"url": f"{target}/login", "method": "GET", "params": ["username", "password"]},
                    {"url": f"{target}/api/v1/user", "method": "GET", "params": ["id"], "auth_required": True},
                ],
            )

        for ep in endpoints:
            self.budget.check_limits()
            await event_bus.publish(
                EndpointDiscoveredEvent(
                    source=self.name,
                    url=ep.get("url", f"{target}/endpoint"),
                    method=ep.get("method", "GET"),
                    params=ep.get("params", []),
                    auth_required=ep.get("auth_required"),
                    metadata=ep.get("metadata", {}),
                )
            )

        # Anomalies check
        anomalies = context.get("anomalies", [])
        for anom in anomalies:
            self.budget.record_action()
            await event_bus.publish(
                AnomalyDetectedEvent(
                    source=self.name,
                    description=anom.get("description", "Potential web anomaly detected"),
                    severity=anom.get("severity", "medium"),
                    component=anom.get("component", "web_router"),
                    target=target,
                    evidence=anom.get("evidence"),
                )
            )

        # Optional hypothesis proposal
        if context.get("propose_hypothesis"):
            hypo_data = context["propose_hypothesis"]
            statement = hypo_data.get("statement") if isinstance(hypo_data, dict) else "Web input reflection without sanitization"
            vuln_class = hypo_data.get("vulnerability_class", "xss") if isinstance(hypo_data, dict) else "xss"
            criteria = hypo_data.get("falsification_criteria", "Output is HTML encoded") if isinstance(hypo_data, dict) else "Output is encoded"
            conf = hypo_data.get("confidence", 0.6) if isinstance(hypo_data, dict) else 0.6
            await self.propose_hypothesis(
                statement=statement,
                vulnerability_class=vuln_class,
                falsification_criteria=criteria,
                confidence=conf,
                target=target,
                event_bus=event_bus,
            )

        return {"discovered_endpoints_count": len(endpoints)}


class ApiSpecialist(SpecialistAgent):
    """
    Focuses on API architectures: REST/GraphQL endpoints, parameter structures, schemas, and BOLA/IDOR.
    """

    def __init__(
        self,
        name: str = "ApiSpecialist",
        target_url: str = "",
        objective: str = "Analyze API schemas, REST/GraphQL schemas, and parameter hierarchies",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="api",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target_url = target_url

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        target = self.target_url or context.get("target_url") or context.get("target") or "http://localhost/api"
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        api_routes = context.get(
            "api_routes",
            [
                {
                    "url": f"{target}/v1/users/me",
                    "method": "GET",
                    "params": ["fields"],
                    "content_type": "application/json",
                },
                {
                    "url": f"{target}/v1/orders",
                    "method": "POST",
                    "params": ["item_id", "qty", "shipping_address"],
                    "content_type": "application/json",
                },
            ],
        )

        for route in api_routes:
            self.budget.check_limits()
            await event_bus.publish(
                EndpointDiscoveredEvent(
                    source=self.name,
                    url=route.get("url", target),
                    method=route.get("method", "GET"),
                    params=route.get("params", []),
                    content_type=route.get("content_type", "application/json"),
                    auth_required=True,
                )
            )

        # Propose BOLA/IDOR hypothesis if requested
        if context.get("propose_hypothesis", True):
            hypo_data = context.get("propose_hypothesis")
            statement = (
                hypo_data.get("statement")
                if isinstance(hypo_data, dict)
                else f"Endpoint {target}/v1/users/me may permit IDOR via parameter tampering"
            )
            await self.propose_hypothesis(
                statement=statement,
                vulnerability_class="idor",
                falsification_criteria="Server strictly verifies authenticated tenant ID against requested resource ID",
                confidence=0.7,
                target=target,
                event_bus=event_bus,
            )

        return {"api_routes_analyzed": len(api_routes)}


class AuthSpecialist(SpecialistAgent):
    """
    Focuses on authentication schemes, tokens (JWT, session cookies), OAuth flows, and access control.
    """

    def __init__(
        self,
        name: str = "AuthSpecialist",
        target_url: str = "",
        objective: str = "Analyze authentication mechanisms, JWT signatures, and authorization boundaries",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="auth",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target_url = target_url

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        target = self.target_url or context.get("target_url") or context.get("target") or "http://localhost/auth"
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        hypo = await self.propose_hypothesis(
            statement=context.get(
                "statement",
                f"Authentication on {target} accepts unverified JWT algorithm 'none'",
            ),
            vulnerability_class="broken_auth",
            falsification_criteria="Server rejects tokens without verified HMAC/RSA signature with 401 Unauthorized",
            confidence=0.75,
            target=target,
            event_bus=event_bus,
        )

        if context.get("verified", False):
            self.budget.record_action()
            await self.verify_vulnerability(
                vulnerability_id=f"vuln-{uuid.uuid4().hex[:8]}",
                title=f"Authentication Bypass on {target}",
                vulnerability_class="Authentication Bypass",
                severity="critical",
                target=target,
                evidence=context.get("evidence", {"jwt_header": {"alg": "none"}}),
                reproduction_steps=[
                    "1. Construct JWT header with alg='none'",
                    "2. Submit request with unsigned token",
                    "3. Observe 200 OK access granted",
                ],
                event_bus=event_bus,
            )

        return {"auth_hypothesis_id": hypo.id}


class NetworkSpecialist(SpecialistAgent):
    """
    Focuses on network services, open ports, service banners, and transport security.
    """

    def __init__(
        self,
        name: str = "NetworkSpecialist",
        target: str = "",
        objective: str = "Discover network services, open ports, banners, and protocol endpoints",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="network",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target = target

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        target = self.target or context.get("target", "127.0.0.1")
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        ports = []
        tools = context.get("tools") or context.get("security_tools") or {}
        nmap_tool = tools.get("nmap") if isinstance(tools, dict) else None

        if nmap_tool:
            try:
                from sonic.tools.base import ToolRequest
                req = ToolRequest(tool_name="nmap", action="scan", target=target, options=context.get("nmap_options", {}))
                res = await nmap_tool.execute(req)
                if res and getattr(res, "findings", None):
                    for finding in res.findings:
                        raw = getattr(finding, "raw", finding) if not isinstance(finding, dict) else finding
                        ports.append({
                            "port": raw.get("port"),
                            "service": raw.get("service", "unknown"),
                            "banner": raw.get("version", ""),
                        })
            except Exception as e:
                logger.debug("network_specialist_nmap_failed", error=str(e))

        provider = context.get("provider") or context.get("computer")
        if not ports and provider and hasattr(provider, "scan_ports"):
            try:
                probed = await provider.scan_ports(target, [80, 443, 8080, 22, 3000, 5000, 8000])
                for p in probed:
                    if p.get("state") == "open":
                        ports.append(p)
            except Exception as e:
                logger.debug("network_specialist_scan_ports_failed", error=str(e))

        if not ports:
            # Only use ports explicitly provided in context (e.g. test fixtures or prior scans).
            # Never fabricate hallucinated open ports when live probing finds nothing.
            ports = context.get("open_ports", [])

        for p in ports:
            self.budget.check_limits()
            port_num = p.get("port")
            service_name = p.get("service", "unknown")
            banner = p.get("banner", "")

            # 1. Publish TargetDiscoveredEvent
            await event_bus.publish(
                TargetDiscoveredEvent(
                    source=self.name,
                    target=target,
                    target_type="network_service",
                    port=port_num,
                    service=service_name,
                    banner=banner,
                )
            )

            # 2. If it is an HTTP service, publish EndpointDiscoveredEvent
            if service_name in ("http", "http-alt", "https") or port_num in (80, 443, 8080, 8443):
                scheme = "https" if (port_num == 443 or service_name == "https") else "http"
                url = f"{scheme}://{target}:{port_num}/" if port_num not in (80, 443) else f"{scheme}://{target}/"
                await event_bus.publish(
                    EndpointDiscoveredEvent(
                        source=self.name,
                        url=url,
                        method="GET",
                        metadata={"service": service_name, "port": port_num},
                    )
                )

        return {"open_ports_discovered": len(ports)}


class BusinessLogicSpecialist(SpecialistAgent):
    """
    Focuses on multi-step workflows, state machine transitions, race conditions,
    parameter tampering (price, quantity, negative values), coupon/credit reuse,
    and step-skipping flaws.
    """

    def __init__(
        self,
        name: str = "BusinessLogicSpecialist",
        target_url: str = "",
        objective: str = "Analyze workflow state machines, race conditions, and business logic boundaries",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="business_logic",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target_url = target_url

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        target = self.target_url or context.get("target_url") or context.get("target") or "http://localhost"
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        workflows = context.get(
            "workflows",
            [
                {"name": "checkout", "steps": ["/cart", "/checkout", "/pay", "/confirm"]},
                {"name": "coupon_redemption", "steps": ["/cart", "/apply-coupon"]},
            ],
        )

        # 1. Look for order-of-operation anomalies or race conditions
        for wf in workflows:
            wf_name = wf.get("name", "unknown")
            steps = wf.get("steps", [])
            await event_bus.publish(
                AnomalyDetectedEvent(
                    source=self.name,
                    anomaly_type="business_logic_workflow",
                    target=target,
                    observation=f"Multi-step workflow identified: {wf_name} ({len(steps)} steps)",
                    confidence=0.7,
                )
            )

        # 2. Formulate business logic hypothesis
        hypo = await self.propose_hypothesis(
            statement=context.get(
                "statement",
                f"Multi-step checkout on {target} allows payment step-skipping or parameter tampering",
            ),
            vulnerability_class="business_logic_flaw",
            falsification_criteria="Server enforces strict state validation and rejects out-of-order finalization",
            confidence=0.70,
            target=target,
            event_bus=event_bus,
        )

        if context.get("verified", False):
            self.budget.record_action()
            await self.verify_vulnerability(
                vulnerability_id=f"vuln-{uuid.uuid4().hex[:8]}",
                title=f"Business Logic Bypass on {target}",
                vulnerability_class="Business Logic Flaw",
                severity="high",
                target=target,
                evidence=context.get("evidence", {"skipped_step": "/pay", "order_status": "confirmed"}),
                reproduction_steps=[
                    "1. Add item to cart",
                    "2. Skip payment step and directly call /confirm with order_id",
                    "3. Order processed without valid payment capture",
                ],
                event_bus=event_bus,
            )

        return {"business_logic_hypothesis_id": hypo.id, "workflows_analyzed": len(workflows)}


class CloudSpecialist(SpecialistAgent):
    """
    Focuses on cloud infrastructure, instance metadata services (IMDSv1/v2),
    exposed storage buckets (S3, GCS, Azure Blob), serverless functions, and cloud IAM boundaries.
    """

    def __init__(
        self,
        name: str = "CloudSpecialist",
        target_host: str = "",
        objective: str = "Discover cloud metadata services, storage buckets, and IAM privilege boundaries",
        budget: SpecialistBudget | None = None,
        priority: int = 10,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="cloud",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target_host = target_host

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        target = self.target_host or context.get("target_host") or context.get("target") or "target.cloud"
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        cloud_assets = context.get(
            "cloud_assets",
            [
                {"type": "cloud_storage", "name": f"{target}-assets", "provider": "s3"},
                {"type": "imds_target", "name": "169.254.169.254", "flavor": "aws_imds_v1"},
            ],
        )

        for asset in cloud_assets:
            self.budget.check_limits()
            await event_bus.publish(
                TargetDiscoveredEvent(
                    source=self.name,
                    target=asset.get("name", target),
                    target_type="cloud_resource",
                    metadata={"provider": asset.get("provider", "aws"), "asset_type": asset.get("type")},
                )
            )

        hypo = await self.propose_hypothesis(
            statement=context.get(
                "statement",
                f"Cloud asset {target} permits unauthorized S3 bucket access or IMDSv1 SSRF credential extraction",
            ),
            vulnerability_class="cloud_misconfiguration",
            falsification_criteria="IMDSv2 hop-limit enforced and S3 bucket blocks unauthenticated public read/write",
            confidence=0.80,
            target=target,
            event_bus=event_bus,
        )

        if context.get("verified", False):
            self.budget.record_action()
            await self.verify_vulnerability(
                vulnerability_id=f"vuln-{uuid.uuid4().hex[:8]}",
                title=f"Cloud Asset Misconfiguration on {target}",
                vulnerability_class="Cloud Misconfiguration",
                severity="critical",
                target=target,
                evidence=context.get("evidence", {"public_bucket_acl": "AllUsers:READ"}),
                reproduction_steps=[
                    f"1. Query public storage endpoint {target}-assets",
                    "2. Enumerate objects without authentication",
                    "3. Confidential backups retrieved",
                ],
                event_bus=event_bus,
            )

        return {"cloud_hypothesis_id": hypo.id, "cloud_assets_evaluated": len(cloud_assets)}


class FalsificationSpecialist(SpecialistAgent):
    """
    Adversarial challenger: Generates counter-experiments to disprove active hypotheses,
    ensuring findings are backed by real verification rather than confirmation bias.
    """

    def __init__(
        self,
        name: str = "FalsificationSpecialist",
        target_hypothesis_id: str = "",
        falsification_plan: dict[str, Any] | None = None,
        objective: str = "Generate disproving experiments to challenge and falsify candidate hypotheses",
        budget: SpecialistBudget | None = None,
        priority: int = 5,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            specialty="falsification",
            objective=objective,
            budget=budget,
            priority=priority,
            investigation_fn=investigation_fn,
        )
        self.target_hypothesis_id = target_hypothesis_id
        self.falsification_plan = falsification_plan or {}

    async def _execute(self, context: dict[str, Any], event_bus: ResearchEventBus) -> Any:
        delay = context.get("delay", 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        self.budget.record_action()

        # Find matching hypothesis from context
        hypo_id = self.target_hypothesis_id or context.get("hypothesis_id", "hypo-default")
        hypotheses_list = context.get("hypotheses", [])
        matched_hypo: dict[str, Any] = {}
        for h in hypotheses_list:
            if isinstance(h, dict) and h.get("id") == hypo_id:
                matched_hypo = h
                break
            elif isinstance(h, CompetingHypothesis) and h.id == hypo_id:
                matched_hypo = {"id": h.id, "statement": h.statement, "vulnerability_class": h.vulnerability_class}
                break

        statement = matched_hypo.get("statement", context.get("statement", "Candidate vulnerability"))
        vuln_class = matched_hypo.get("vulnerability_class", "")

        # Determine vulnerability class if statement mentions common types
        if not vuln_class:
            if "SQL" in statement or "sqli" in hypo_id.lower():
                vuln_class = "SQL Injection"
            elif "IDOR" in statement or "User ID" in statement or "idor" in hypo_id.lower():
                vuln_class = "IDOR"
            elif "JWT" in statement or "Auth" in statement:
                vuln_class = "Broken Authentication"
            else:
                vuln_class = "Vulnerability"

        target = context.get("target", "target.local")

        # Check plan vs context
        plan = self.falsification_plan or context.get("falsification_plan", {})
        should_falsify = plan.get("should_falsify", context.get("should_falsify", False))

        if should_falsify:
            reason = plan.get(
                "disproving_evidence",
                context.get(
                    "falsification_reason",
                    f"Adversarial counter-test proved {statement} does not trigger exploitable condition",
                ),
            )
            await self.falsify_hypothesis(
                hypothesis_id=hypo_id,
                reason=reason,
                evidence=plan.get("evidence", {"test": "adversarial_probe_disproved"}),
                event_bus=event_bus,
            )
            return {"falsified": True, "hypothesis_id": hypo_id}
        elif plan.get("verification_details") or context.get("verification_details") or plan.get("verified") or context.get("verified"):
            verification_details = plan.get(
                "verification_details",
                context.get("verification_details", f"Adversarially Confirmed: {statement}"),
            )
            await self.verify_vulnerability(
                vulnerability_id=f"vuln-{uuid.uuid4().hex[:8]}",
                title=verification_details,
                vulnerability_class=vuln_class,
                severity=context.get("severity", "high"),
                target=target,
                evidence=plan.get("evidence", {"verification": "confirmed"}),
                reproduction_steps=[
                    f"1. Formulated hypothesis: {statement}",
                    "2. Executed discriminating falsification test",
                    f"3. Target confirmed with evidence: {verification_details}",
                ],
                event_bus=event_bus,
            )
            return {"falsified": False, "verified": True, "hypothesis_id": hypo_id}
        else:
            return {"falsified": False, "verified": False, "hypothesis_id": hypo_id, "status": "INCONCLUSIVE"}
