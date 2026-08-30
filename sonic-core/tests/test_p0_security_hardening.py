"""
P0 Security Hardening Regression Tests.

Verifies the fixes for the critical findings in the security audit:
  P0-1: /auth/login and /auth/dev-token are dev-only and cannot escalate to admin.
  P0-2: Production refuses to boot with an insecure JWT secret.
  P0-3: docker-compose.prod.yml contains no plaintext secrets.
  P0-4: run_engagement is tenant-scoped; cross-tenant runs are refused.
  P0-5: Host shell execution is forbidden outside development.
  P0-6: Egress filter rejects private/loopback/metadata engagement targets.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole
from sonic.config import Settings, get_settings


@pytest.fixture
def client():
    from sonic.api.main import app

    return TestClient(app)


def _dev_login(client: TestClient, role: str, tenant_id: str = "default") -> dict:
    return client.post(
        "/auth/login",
        json={"email": f"u@{tenant_id}.com", "name": "U", "role": role, "tenant_id": tenant_id},
    )


# ==========================================================
# P0-1: dev-only auth endpoints + no admin escalation
# ==========================================================

def test_dev_login_works_in_development(client):
    """In dev, /auth/login issues a token for a non-admin role."""
    res = _dev_login(client, role="operator")
    assert res.status_code == 200
    data = res.json()
    assert data["access_token"]
    assert data["user"]["role"] == "operator"


def test_dev_login_clamps_super_admin_role(client):
    """CRITICAL: requesting super_admin via /auth/login must NOT escalate."""
    res = _dev_login(client, role="super_admin")
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] != "super_admin"
    assert data["user"]["role"] == "operator"


def test_dev_login_clamps_tenant_admin_role(client):
    """Requesting tenant_admin via /auth/login must NOT escalate."""
    res = _dev_login(client, role="tenant_admin")
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "operator"


def test_dev_token_works_in_development(client):
    res = client.post("/auth/dev-token")
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_dev_token_is_operator_only(client):
    res = client.post("/auth/dev-token")
    assert res.json()["token"]["user"]["role"] == "operator"


def test_auth_endpoints_disabled_in_production(monkeypatch):
    """In production, /auth/login and /auth/dev-token must be disabled."""
    from sonic.api.routes import auth as auth_routes

    prod_settings = Settings(app_env="production", jwt_secret="x" * 48)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: prod_settings)

    res_login = _dev_login(client=pytest.importorskip("fastapi.testclient").TestClient(
        __import__("sonic.api.main", fromlist=["app"]).app
    ), role="operator")
    assert res_login.status_code == 404

    res_dev = pytest.importorskip("fastapi.testclient").TestClient(
        __import__("sonic.api.main", fromlist=["app"]).app
    ).post("/auth/dev-token")
    assert res_dev.status_code == 404


# ==========================================================
# P0-2: JWT secret validation
# ==========================================================

def test_jwt_secret_rejects_default_in_production():
    s = Settings(app_env="production", jwt_secret="CHANGE-ME")
    ok, _ = s.validate_jwt_secret()
    assert ok is False


def test_jwt_secret_rejects_empty_in_production():
    s = Settings(app_env="production", jwt_secret="")
    ok, _ = s.validate_jwt_secret()
    assert ok is False


def test_jwt_secret_rejects_short_in_production():
    s = Settings(app_env="production", jwt_secret="shortkey")
    ok, _ = s.validate_jwt_secret()
    assert ok is False


def test_jwt_secret_accepts_strong_in_production():
    s = Settings(app_env="production", jwt_secret="a" * 48)
    ok, _ = s.validate_jwt_secret()
    assert ok is True


def test_jwt_secret_allows_default_in_development():
    s = Settings(app_env="development", jwt_secret="CHANGE-ME")
    ok, _ = s.validate_jwt_secret()
    assert ok is True


def test_secret_key_env_alias_populates_jwt_secret(monkeypatch):
    """SECRET_KEY env var (used by docker-compose.prod.yml) must populate jwt_secret.

    Fully env-isolated: clears all jwt_secret aliases (JWT_SECRET/SECRET_KEY) and
    disables .env loading so a polluted os.environ or the repo .env file cannot
    leak a stale value across the suite (AliasChoices resolves the first alias
    found per source, so a stray JWT_SECRET env var would otherwise win over the
    SECRET_KEY alias this test exercises).
    """
    for alias in ("JWT_SECRET", "SECRET_KEY", "jwt_secret"):
        monkeypatch.delenv(alias, raising=False)
    monkeypatch.setenv("SECRET_KEY", "from-secret-key-env-var-" + "x" * 30)
    monkeypatch.setenv("APP_ENV", "production")
    s = Settings(_env_file=None)
    assert s.jwt_secret == "from-secret-key-env-var-" + "x" * 30
    ok, _ = s.validate_jwt_secret()
    assert ok is True


# ==========================================================
# P0-3: no plaintext secrets in prod compose
# ==========================================================

def test_prod_compose_has_no_plaintext_secrets():
    repo_root = Path(__file__).resolve().parents[2]
    compose = (repo_root / "docker-compose.prod.yml").read_text()
    # The previously-committed secrets must be gone.
    assert "sonic_secret_password_2026" not in compose
    assert "prod_super_secret_jwt_key_sonic_2026" not in compose
    # Secrets must be injected via env interpolation.
    assert "${NEO4J_PASSWORD" in compose
    assert "${SECRET_KEY" in compose


# ==========================================================
# P0-4: tenant-scoped engagement run
# ==========================================================

def _make_headers(role: UserRole, tenant_id: str) -> dict:
    user = User(email=f"{role.value}@{tenant_id}.com", name="T", tenant_id=tenant_id, role=role)
    token = create_jwt_token(user)
    return {"Authorization": f"Bearer {token.access_token}"}


def test_run_engagement_refuses_cross_tenant(client):
    """Tenant Beta must not run Tenant Alpha's engagement."""
    headers_alpha = _make_headers(UserRole.OPERATOR, "tenant-alpha")
    headers_beta = _make_headers(UserRole.OPERATOR, "tenant-beta")

    # Alpha creates an engagement against a public, in-egress target.
    res_create = client.post(
        "/engagements/",
        json={"name": "Alpha Eng", "target": "example.com"},
        headers=headers_alpha,
    )
    assert res_create.status_code == 200
    eng_id = res_create.json()["engagement_id"]

    # Beta attempts to run Alpha's engagement -> must be refused.
    res_run = client.post(
        f"/engagements/{eng_id}/run",
        json={"phases": ["recon"]},
        headers=headers_beta,
    )
    assert res_run.status_code == 404


def test_run_engagement_refuses_cross_tenant_even_for_super_admin(client):
    """SUPER_ADMIN is also bound to their tenant for engagement execution."""
    headers_alpha = _make_headers(UserRole.OPERATOR, "tenant-alpha")
    headers_super = _make_headers(UserRole.SUPER_ADMIN, "tenant-other")

    res_create = client.post(
        "/engagements/",
        json={"name": "Alpha Eng", "target": "example.com"},
        headers=headers_alpha,
    )
    eng_id = res_create.json()["engagement_id"]

    res_run = client.post(
        f"/engagements/{eng_id}/run",
        json={"phases": ["recon"]},
        headers=headers_super,
    )
    assert res_run.status_code == 404


# ==========================================================
# P0-5: host shell execution forbidden outside development
# ==========================================================

def test_factory_refuses_host_execution_in_production(monkeypatch):
    from sonic.sandbox import factory
    from sonic.config import get_settings

    monkeypatch.setenv("SONIC_ALLOW_HOST_EXECUTION", "true")
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    monkeypatch.setattr(factory, "_active_provider", None)

    provider = factory.get_compute_provider(force_provider="local")
    # The provider must have been created fail-closed.
    assert provider.allow_host_execution is False
    get_settings.cache_clear()


def test_factory_allows_host_execution_in_dev(monkeypatch):
    from sonic.sandbox import factory
    from sonic.config import get_settings

    monkeypatch.setenv("SONIC_ALLOW_HOST_EXECUTION", "true")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    monkeypatch.setattr(factory, "_active_provider", None)

    provider = factory.get_compute_provider(force_provider="local")
    assert provider.allow_host_execution is True
    get_settings.cache_clear()


# ==========================================================
# P0-6: egress filter rejects private/metadata targets
# ==========================================================

def test_engagement_target_rejects_metadata_address(client):
    headers = _make_headers(UserRole.OPERATOR, "tenant-egress")
    res = client.post(
        "/engagements/",
        json={"name": "SSRF", "target": "169.254.169.254"},
        headers=headers,
    )
    assert res.status_code == 400


def test_engagement_target_rejects_loopback(client):
    headers = _make_headers(UserRole.OPERATOR, "tenant-egress")
    res = client.post(
        "/engagements/",
        json={"name": "Loopback", "target": "127.0.0.1"},
        headers=headers,
    )
    assert res.status_code == 400


def test_engagement_target_rejects_private_range(client):
    headers = _make_headers(UserRole.OPERATOR, "tenant-egress")
    res = client.post(
        "/engagements/",
        json={"name": "Internal", "target": "10.0.0.5"},
        headers=headers,
    )
    assert res.status_code == 400


def test_engagement_target_accepts_public(client):
    headers = _make_headers(UserRole.OPERATOR, "tenant-egress")
    res = client.post(
        "/engagements/",
        json={"name": "Public", "target": "example.com"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "created"
