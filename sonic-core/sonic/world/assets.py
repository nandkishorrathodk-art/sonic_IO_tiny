"""
SONIC v2 — Asset Inventory & Attack Surface
===========================================
First-class representations of target assets, services, and technologies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AssetNode(BaseModel):
    """A discovered target asset or network service."""
    asset_id: str = Field(default_factory=lambda: f"asset-{uuid.uuid4().hex[:8]}")
    identifier: str  # e.g., "example.com", "192.168.1.10", "https://api.example.com"
    asset_type: str = "web"  # "web", "api", "host", "cloud_bucket", "service"
    ip: str | None = None
    port: int | None = None
    technology_stack: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    criticality: float = 1.0  # 1.0 (low) to 5.0 (critical crown jewel)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetInventory:
    """Manages discovered targets and services."""

    def __init__(self):
        self._assets: dict[str, AssetNode] = {}

    def register_asset(
        self,
        identifier: str,
        asset_type: str = "web",
        ip: str | None = None,
        port: int | None = None,
        technologies: list[str] | None = None,
        criticality: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> AssetNode:
        for existing in self._assets.values():
            if existing.identifier == identifier and existing.port == port:
                if technologies:
                    existing.technology_stack = sorted(list(set(existing.technology_stack + technologies)))
                return existing

        node = AssetNode(
            identifier=identifier,
            asset_type=asset_type,
            ip=ip,
            port=port,
            technology_stack=technologies or [],
            criticality=criticality,
            metadata=metadata or {},
        )
        self._assets[node.asset_id] = node
        return node

    def add_endpoint(self, asset_id: str, endpoint: str) -> None:
        if asset_id in self._assets:
            if endpoint not in self._assets[asset_id].endpoints:
                self._assets[asset_id].endpoints.append(endpoint)

    def get_by_identifier(self, identifier: str) -> AssetNode | None:
        for a in self._assets.values():
            if a.identifier == identifier:
                return a
        return None

    def get_all(self) -> list[AssetNode]:
        return list(self._assets.values())
