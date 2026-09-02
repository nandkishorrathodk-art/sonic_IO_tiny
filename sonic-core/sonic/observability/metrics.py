"""
SONIC-REDA — Observability, Telemetry & Prometheus Metrics
============================================================
Collects real-time operational metrics for Prometheus, Grafana, and OpenTelemetry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SwarmMetrics:
    """System-wide operational metrics."""
    active_engagements: int = 0
    active_agents: int = 0
    findings_total: dict[str, int] = field(default_factory=lambda: {
        "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0
    })
    llm_requests_total: int = 0
    llm_tokens_total: int = 0
    llm_cost_usd_total: float = 0.0
    egress_requests_total: int = 0
    safety_violations_blocked: int = 0
    start_time: float = field(default_factory=time.time)

    def record_finding(self, severity: str) -> None:
        sev = severity.lower()
        if sev in self.findings_total:
            self.findings_total[sev] += 1
        else:
            self.findings_total["info"] += 1

    def record_llm_usage(self, tokens: int, cost_usd: float) -> None:
        self.llm_requests_total += 1
        self.llm_tokens_total += tokens
        self.llm_cost_usd_total += cost_usd

    def record_egress(self) -> None:
        self.egress_requests_total += 1

    def record_safety_blocked(self) -> None:
        self.safety_violations_blocked += 1

    def export_prometheus(self) -> str:
        """Export metrics in standard Prometheus exposition text format."""
        uptime = time.time() - self.start_time
        lines = [
            "# HELP sonic_uptime_seconds Total runtime of SONIC-REDA process",
            "# TYPE sonic_uptime_seconds gauge",
            f"sonic_uptime_seconds {uptime:.2f}",
            "",
            "# HELP sonic_active_engagements Number of currently running engagements",
            "# TYPE sonic_active_engagements gauge",
            f"sonic_active_engagements {self.active_engagements}",
            "",
            "# HELP sonic_active_agents Number of active agents in swarm",
            "# TYPE sonic_active_agents gauge",
            f"sonic_active_agents {self.active_agents}",
            "",
            "# HELP sonic_llm_requests_total Total LLM calls processed",
            "# TYPE sonic_llm_requests_total counter",
            f"sonic_llm_requests_total {self.llm_requests_total}",
            "",
            "# HELP sonic_llm_cost_usd_total Cumulative cost in USD",
            "# TYPE sonic_llm_cost_usd_total counter",
            f"sonic_llm_cost_usd_total {self.llm_cost_usd_total:.6f}",
            "",
            "# HELP sonic_egress_requests_total Total network requests sent to targets",
            "# TYPE sonic_egress_requests_total counter",
            f"sonic_egress_requests_total {self.egress_requests_total}",
            "",
            "# HELP sonic_safety_blocked_total Total actions blocked by Immutable Safety Layer",
            "# TYPE sonic_safety_blocked_total counter",
            f"sonic_safety_blocked_total {self.safety_violations_blocked}",
        ]

        for sev, count in self.findings_total.items():
            lines.append(f'sonic_findings_total{{severity="{sev}"}} {count}')

        return "\n".join(lines) + "\n"


# Global singleton
_metrics: SwarmMetrics | None = None


def get_metrics() -> SwarmMetrics:
    global _metrics
    if _metrics is None:
        _metrics = SwarmMetrics()
    return _metrics
