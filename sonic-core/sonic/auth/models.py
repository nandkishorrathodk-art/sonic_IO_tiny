"""
SONIC-REDA — Enterprise Multi-Tenant Auth Models
===================================================
Pydantic data models for multi-tenant users, enterprise RBAC,
JWT tokens, and security allowlists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    """Enterprise Role-Based Access Control (RBAC) hierarchy."""

    SUPER_ADMIN = "super_admin"    # Global system administrator (all tenants)
    TENANT_ADMIN = "tenant_admin"  # Administrator of a specific tenant organization
    OPERATOR = "operator"          # Security engineer (can launch scans & verify)
    AUDITOR = "auditor"            # Read-only compliance auditor (no mutations)

    # Backward compatibility aliases
    ADMIN = "tenant_admin"
    VIEWER = "auditor"


class User(BaseModel):
    """Authenticated multi-tenant user profile."""

    email: str
    name: str
    tenant_id: str = "default"     # Multi-tenant partition ID
    workspace_id: str | None = None
    picture: str | None = None
    google_id: str = ""
    role: UserRole = UserRole.OPERATOR
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def domain(self) -> str:
        """Extract email domain."""
        return self.email.split("@")[1] if "@" in self.email else ""


class AuthToken(BaseModel):
    """JWT token response returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: User


class TokenPayload(BaseModel):
    """Decoded JWT token payload with tenant ownership."""

    sub: str                       # user email
    name: str
    tenant_id: str = "default"     # multi-tenant partition key
    workspace_id: str | None = None
    picture: str | None = None
    google_id: str = ""
    role: UserRole = UserRole.OPERATOR
    exp: int                       # expiry timestamp
    iat: int                       # issued at timestamp


class AllowlistEntry(BaseModel):
    """An entry in the team access allowlist."""

    value: str  # email or domain
    entry_type: str = "email"  # "email" or "domain"
    tenant_id: str = "default"
    added_by: str = ""
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = ""


class AuthStatus(BaseModel):
    """Current authentication status response."""

    authenticated: bool
    user: User | None = None
    tenant_id: str | None = None
    message: str = ""
