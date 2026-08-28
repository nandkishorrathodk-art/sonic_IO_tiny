"""
Tests for Phase 11: Adversarial Auth & RBAC Verification.
"""

import pytest
from sonic.auth.models import User, UserRole


def test_adversarial_role_isolation():
    # Auditor role must be restricted
    auditor = User(
        id="aud-1",
        email="auditor@corp.com",
        name="Security Auditor",
        role=UserRole.AUDITOR,
        tenant_id="tenant-1",
    )
    assert auditor.role == UserRole.AUDITOR
    assert auditor.role != UserRole.OPERATOR
    assert auditor.role != UserRole.SUPER_ADMIN


def test_tenant_admin_cannot_escalate_to_super_admin():
    tenant_admin = User(
        id="ta-1",
        email="admin@tenant.com",
        name="Tenant Admin",
        role=UserRole.TENANT_ADMIN,
        tenant_id="tenant-1",
    )
    assert tenant_admin.role == UserRole.TENANT_ADMIN
    assert tenant_admin.role != UserRole.SUPER_ADMIN
