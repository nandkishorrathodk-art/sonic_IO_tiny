"""
SONIC-REDA — PostgreSQL Relational Data Models (Data Plane)
=============================================================
Defines relational schemas for Tenants, Users, Engagements,
Findings, and Immutable Audit Trails using SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class TenantModel(Base):
    """Multi-tenant organization account."""
    __tablename__ = "tenants"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False, unique=True)
    slug = Column(String(64), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    users = relationship("UserModel", back_populates="tenant", cascade="all, delete-orphan")
    engagements = relationship("EngagementModel", back_populates="tenant", cascade="all, delete-orphan")


class UserModel(Base):
    """User accounts belonging to a specific tenant."""
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(128), nullable=False)
    role = Column(String(32), default="operator", nullable=False)
    google_id = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_login = Column(DateTime(timezone=True), default=utc_now)

    tenant = relationship("TenantModel", back_populates="users")
    audit_logs = relationship("AuditLogModel", back_populates="user")


class EngagementModel(Base):
    """Security testing engagements partitioned by tenant."""
    __tablename__ = "engagements"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    target_summary = Column(String(255), nullable=False)
    status = Column(String(32), default="created", nullable=False, index=True)
    scope_config = Column(JSON, default=dict)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant = relationship("TenantModel", back_populates="engagements")
    findings = relationship("FindingModel", back_populates="engagement", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_engagement_tenant_status", "tenant_id", "status"),
    )


class FindingModel(Base):
    """Verified security findings and metadata."""
    __tablename__ = "findings"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    engagement_id = Column(String(64), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    vulnerability_class = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), default="medium", nullable=False, index=True)
    status = Column(String(32), default="draft", nullable=False)
    confidence_score = Column(Integer, default=0, nullable=False)
    poc = Column(Text, default="")
    impact = Column(Text, default="")
    remediation = Column(Text, default="")
    found_by = Column(String(64), default="")
    verified_by = Column(String(64), default="")
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    engagement = relationship("EngagementModel", back_populates="findings")

    __table_args__ = (
        Index("ix_finding_tenant_severity", "tenant_id", "severity"),
    )


class AuditLogModel(Base):
    """Immutable audit trail of security operations."""
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(45), default="")
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = relationship("UserModel", back_populates="audit_logs")
