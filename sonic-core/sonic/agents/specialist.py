"""
SONIC v2 — Subordinated Specialist Pool
========================================
Specialists are bounded investigators managed by the Central Research Brain.
They do NOT run open-ended mission loops. They execute discrete experiments,
measure behavioral differentials, produce structured evidence, and publish
outcomes to the Event Bus.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.brain.experiment import Experiment, ExperimentResult
from sonic.kernel.action_broker import ActionBroker, BrokerResult
from sonic.kernel.event_bus import EventBus, EventTopic
from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SpecialistResult:
    """Outcome produced by a specialist after testing an experiment."""
    experiment_id: str
    hypothesis_id: str
    specialist_type: str
    status: str  # "completed", "failed", "dead_end", "blocked"
    baseline_observation: str = ""
    probe_observation: str = ""
    behavioral_difference_detected: bool = False
    difference_description: str = ""
    evidence_payload: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


class BaseSpecialist(ABC):
    """Abstract base for all subordinated domain specialists."""

    def __init__(
        self,
        specialist_type: str,
        action_broker: ActionBroker,
        event_bus: EventBus | None = None,
        provider: Any = None,
    ):
        self.specialist_type = specialist_type
        self.broker = action_broker
        self.event_bus = event_bus
        self.provider = provider

    @abstractmethod
    def run_experiment(self, experiment: Experiment) -> SpecialistResult:
        """Executes a targeted empirical probe and measures the behavioral differential."""
        pass

    def publish_result(self, result: SpecialistResult) -> None:
        if self.event_bus:
            self.event_bus.publish(
                topic=EventTopic.EXPERIMENT_RESULT,
                sender=self.specialist_type,
                payload={
                    "experiment_id": result.experiment_id,
                    "hypothesis_id": result.hypothesis_id,
                    "specialist_type": result.specialist_type,
                    "status": result.status,
                    "behavioral_difference_detected": result.behavioral_difference_detected,
                    "difference_description": result.difference_description,
                    "evidence_payload": result.evidence_payload,
                },
            )


class ReconSpecialist(BaseSpecialist):
    """Investigates target exposure, endpoints, and technology stack."""

    def __init__(self, action_broker: ActionBroker, event_bus: EventBus | None = None, provider: Any = None):
        super().__init__("recon", action_broker, event_bus, provider)

    def run_experiment(self, experiment: Experiment) -> SpecialistResult:
        target = experiment.target_asset
        # Run inspection command via ActionBroker
        cmd = f"curl -sI {target}"
        res: BrokerResult = self.broker.execute(
            action_type="TERMINAL_COMMAND",
            parameters={"command": cmd},
            provider=self.provider,
        )

        diff = bool(res.stdout and "HTTP/" in res.stdout)
        evidence = {"headers": res.stdout} if diff else {}

        result = SpecialistResult(
            experiment_id=experiment.experiment_id,
            hypothesis_id=experiment.hypothesis_id,
            specialist_type="recon",
            status="completed" if res.is_success else "failed",
            baseline_observation="",
            probe_observation=res.stdout,
            behavioral_difference_detected=diff,
            difference_description="Discovered service response headers" if diff else "No service response",
            evidence_payload=evidence,
            duration_ms=res.duration_ms,
        )
        self.publish_result(result)
        return result


class WebSpecialist(BaseSpecialist):
    """Investigates web application interfaces, input reflections, and DOM changes."""

    def __init__(self, action_broker: ActionBroker, event_bus: EventBus | None = None, provider: Any = None):
        super().__init__("web", action_broker, event_bus, provider)

    def run_experiment(self, experiment: Experiment) -> SpecialistResult:
        target = experiment.target_asset
        params = experiment.parameters

        baseline = params.get("baseline", "HTTP 200 OK - Normal rendering")
        # In a real mission, this dispatches browser/HTTP actions through broker
        probe = params.get("simulated_probe", baseline)
        diff_detected = probe != baseline

        evidence = {"probe_response": probe} if diff_detected else {}

        result = SpecialistResult(
            experiment_id=experiment.experiment_id,
            hypothesis_id=experiment.hypothesis_id,
            specialist_type="web",
            status="completed",
            baseline_observation=baseline,
            probe_observation=probe,
            behavioral_difference_detected=diff_detected,
            difference_description="Page returned altered rendering or payload reflection" if diff_detected else "No difference",
            evidence_payload=evidence,
        )
        self.publish_result(result)
        return result


class APISpecialist(BaseSpecialist):
    """Investigates REST/GraphQL API boundaries, serialization, and status codes."""

    def __init__(self, action_broker: ActionBroker, event_bus: EventBus | None = None, provider: Any = None):
        super().__init__("api", action_broker, event_bus, provider)

    def run_experiment(self, experiment: Experiment) -> SpecialistResult:
        params = experiment.parameters
        baseline = params.get("baseline", "HTTP 401 Unauthorized")
        probe = params.get("simulated_probe", baseline)
        diff_detected = probe != baseline

        result = SpecialistResult(
            experiment_id=experiment.experiment_id,
            hypothesis_id=experiment.hypothesis_id,
            specialist_type="api",
            status="completed",
            baseline_observation=baseline,
            probe_observation=probe,
            behavioral_difference_detected=diff_detected,
            difference_description="API endpoint accepted altered query / payload" if diff_detected else "Identical response",
            evidence_payload={"api_response": probe} if diff_detected else {},
        )
        self.publish_result(result)
        return result


class AuthSpecialist(BaseSpecialist):
    """Investigates session identity boundaries, token tampering, and IDOR."""

    def __init__(self, action_broker: ActionBroker, event_bus: EventBus | None = None, provider: Any = None):
        super().__init__("auth", action_broker, event_bus, provider)

    def run_experiment(self, experiment: Experiment) -> SpecialistResult:
        params = experiment.parameters
        baseline = params.get("baseline", "HTTP 403 Forbidden")
        probe = params.get("simulated_probe", baseline)
        diff_detected = probe != baseline

        result = SpecialistResult(
            experiment_id=experiment.experiment_id,
            hypothesis_id=experiment.hypothesis_id,
            specialist_type="auth",
            status="completed",
            baseline_observation=baseline,
            probe_observation=probe,
            behavioral_difference_detected=diff_detected,
            difference_description="Swapped identity crossed authorization boundary" if diff_detected else "Access strictly denied",
            evidence_payload={"leaked_data": probe} if diff_detected else {},
        )
        self.publish_result(result)
        return result


class LogicSpecialist(BaseSpecialist):
    """Investigates multi-step workflows, race conditions, and state machine transitions."""

    def __init__(self, action_broker: ActionBroker, event_bus: EventBus | None = None, provider: Any = None):
        super().__init__("logic", action_broker, event_bus, provider)

    def run_experiment(self, experiment: Experiment) -> SpecialistResult:
        params = experiment.parameters
        baseline = params.get("baseline", "Order state: cancelled")
        probe = params.get("simulated_probe", baseline)
        diff_detected = probe != baseline

        result = SpecialistResult(
            experiment_id=experiment.experiment_id,
            hypothesis_id=experiment.hypothesis_id,
            specialist_type="logic",
            status="completed",
            baseline_observation=baseline,
            probe_observation=probe,
            behavioral_difference_detected=diff_detected,
            difference_description="Unexpected state transition observed" if diff_detected else "State transition rejected",
            evidence_payload={"transition_record": probe} if diff_detected else {},
        )
        self.publish_result(result)
        return result


class SpecialistPool:
    """Registry and dispatcher for subordinated specialists."""

    def __init__(
        self,
        action_broker: ActionBroker,
        event_bus: EventBus | None = None,
        provider: Any = None,
    ):
        self.broker = action_broker
        self.event_bus = event_bus
        self.provider = provider
        self._specialists: dict[str, BaseSpecialist] = {
            "recon": ReconSpecialist(action_broker, event_bus, provider),
            "web": WebSpecialist(action_broker, event_bus, provider),
            "api": APISpecialist(action_broker, event_bus, provider),
            "auth": AuthSpecialist(action_broker, event_bus, provider),
            "logic": LogicSpecialist(action_broker, event_bus, provider),
        }

    def get_specialist(self, specialist_type: str) -> BaseSpecialist | None:
        return self._specialists.get(specialist_type.lower())

    def execute_experiment(self, experiment: Experiment) -> SpecialistResult:
        specialist = self.get_specialist(experiment.specialist_type)
        if not specialist:
            # Fallback to web specialist
            specialist = self._specialists["web"]
        return specialist.run_experiment(experiment)
