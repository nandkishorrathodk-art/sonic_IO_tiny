"""
SONIC v2 — Perception Models
=============================
Structured representations of multimodal perceptions (Vision + DOM + AX + Network).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class InteractiveControl(BaseModel):
    """An interactive UI element (button, link, input, select)."""
    control_id: str
    tag: str
    role: str = ""
    label: str = ""
    selector: str = ""
    value: str | None = None
    enabled: bool = True
    bounding_box: dict[str, int] = Field(default_factory=dict)


class FormElement(BaseModel):
    """A web or desktop form structure."""
    form_id: str
    action: str = ""
    method: str = "POST"
    fields: list[dict[str, Any]] = Field(default_factory=list)


class NetworkEvent(BaseModel):
    """Captured HTTP network request/response during interaction."""
    method: str
    url: str
    status_code: int = 0
    response_type: str = ""
    payload_summary: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class StructuredWorldState(BaseModel):
    """Unified perception fusing screenshot, DOM, accessibility tree, and telemetry."""
    url: str = ""
    title: str = ""
    page_state: str = "unknown"  # "login", "authenticated_home", "error", "checkout", "admin"
    controls: list[InteractiveControl] = Field(default_factory=list)
    forms: list[FormElement] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    dom_changes: list[str] = Field(default_factory=list)
    network_events: list[NetworkEvent] = Field(default_factory=list)
    screenshot_hash: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def find_control_by_label(self, label: str) -> InteractiveControl | None:
        for c in self.controls:
            if label.lower() in c.label.lower():
                return c
        return None
