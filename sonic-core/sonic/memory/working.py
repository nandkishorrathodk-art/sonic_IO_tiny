"""
SONIC v2 — L1 Working Memory
=============================
Real-time, in-session scratchpad and operational context for the active mission.
Tracks active page, current identity/tokens, active hypothesis, and action trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class WorkingMemory:
    """L1 Working Memory for the immediate mission."""
    mission_id: str
    target: str
    active_identity: str = "anonymous"
    active_tokens: dict[str, str] = field(default_factory=dict)
    active_page_url: str = ""
    active_hypothesis_id: str | None = None
    action_history: list[dict[str, Any]] = field(default_factory=list)
    recent_errors: list[str] = field(default_factory=list)
    scratchpad_notes: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def record_action(self, action_type: str, details: dict[str, Any], status: str) -> None:
        self.action_history.append({
            "action_type": action_type,
            "details": details,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    def record_error(self, error: str) -> None:
        self.recent_errors.append(error)
        if len(self.recent_errors) > 20:
            self.recent_errors.pop(0)

    def set_token(self, key: str, value: str) -> None:
        self.active_tokens[key] = value

    def clear(self) -> None:
        self.active_tokens.clear()
        self.action_history.clear()
        self.recent_errors.clear()
        self.scratchpad_notes.clear()
