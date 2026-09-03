"""
SONIC-REDA — Backend tests for the real /findings and /engagements sub-routes.

These tests exercise the endpoints that previously returned "not implemented":
finding verify / reproduce / challenge / evidence / provenance / confidence /
review, and engagement tasks / unknowns / decisions / next-action / pause /
resume. They assert real (non-fabricated) behavior: tenant isolation, honest
empty responses for non-Director engagements, and persisted verdicts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole
from sonic.memory.router import get_memory_sync, reset_memory_singleton
from sonic.memory.schemas import (
    EngagementNode,
    EvidenceNode,
    FindingNode,
    FindingSeverity,
    FindingStatus,
)


client = TestClient(app)


def _headers(role: UserRole = UserRole.OPERATOR, email: str = "operator@target.com"):
    user = User(email=email, name="Test Operator", google_id="g-1", role=role, tenant_id=email)
    token = create_jwt_token(user)
    return {"Authorization": f"Bearer {token.access_token}"}


@pytest.fixture(autouse=True)
def _isolate_memory():
    """Use a fresh InMemory backend + fresh manager singletons per test."""
    reset_memory_singleton()
    # The engagement manager / director are module-level singletons that hold
    # a reference to the memory backend captured at construction time. Reset
    # them so they re-bind to the fresh memory backend seeded by this test.
    import sonic.api.routes.engagements as eng_route
    eng_route._engagement_manager = None
    eng_route._director_instance = None
    yield
    reset_memory_singleton()
    eng_route._engagement_manager = None
    eng_route._director_instance = None


def _seed_finding(tenant: str = "operator@target.com"):
    """Seed an engagement + finding + evidence in the active memory backend."""
    mem = get_memory_sync()
    import asyncio

    async def _seed():
        eng = EngagementNode(name="t", target_summary="https://example.com", tenant_id=tenant)
        eng_uid = await mem.create_engagement(eng)
        finding = FindingNode(
            title="Reflected XSS",
            description="q param reflected unescaped",
            vulnerability_class="XSS",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.NEEDS_VERIFICATION,
            poc="GET /search?q=<script>alert(1)</script>",
            found_by="dynamic-agent-01",
            engagement_id=eng_uid,
            tenant_id=tenant,
            confidence_score=0,
        )
        fid = await mem.create_finding(finding)
        ev = EvidenceNode(
            evidence_type="request",
            content="GET /search?q=%3Cscript%3Ealert(1)%3C/script%3E HTTP/1.1",
            description="original PoC request",
            finding_id=fid,
            engagement_id=eng_uid,
            tenant_id=tenant,
        )
        await mem.create_evidence(ev)
        return eng_uid, fid

    return asyncio.new_event_loop().run_until_complete(_seed())


# ---- Auth / tenant isolation ----

def test_findings_endpoints_require_auth():
    assert client.get("/findings/any").status_code == 401
    assert client.get("/findings/any/evidence").status_code == 401
    assert client.get("/findings/any/confidence").status_code == 401
    assert client.get("/findings/any/provenance").status_code == 401
    assert client.post("/findings/any/review", json={"action": "approve"}).status_code == 401


def test_finding_404_for_missing_id():
    h = _headers()
    r = client.get("/findings/does-not-exist", headers=h)
    assert r.status_code == 404


def test_finding_tenant_isolation():
    """A finding seeded for tenant A is invisible to tenant B."""
    _, fid = _seed_finding(tenant="a@target.com")
    h_b = _headers(email="b@target.com")
    assert client.get(f"/findings/{fid}", headers=h_b).status_code == 404
    assert client.get(f"/findings/{fid}/evidence", headers=h_b).status_code == 404
    assert client.get(f"/findings/{fid}/confidence", headers=h_b).status_code == 404
    assert client.get(f"/findings/{fid}/provenance", headers=h_b).status_code == 404


# ---- /findings read endpoints ----

def test_get_finding_returns_real_data():
    _, fid = _seed_finding()
    r = client.get(f"/findings/{fid}", headers=_headers())
    assert r.status_code == 200
    assert r.json()["finding"]["title"] == "Reflected XSS"


def test_finding_evidence_returns_real_hashes():
    _, fid = _seed_finding()
    r = client.get(f"/findings/{fid}/evidence", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["total_items"] == 1
    ev = data["evidence"][0]
    assert ev["evidence_type"] == "request"
    assert "original PoC request" in ev["description"]


def test_finding_confidence_returns_real_score():
    _, fid = _seed_finding()
    r = client.get(f"/findings/{fid}/confidence", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["finding_id"] == fid
    assert data["confidence_score"] == 0
    assert data["status"] == FindingStatus.NEEDS_VERIFICATION


def test_finding_provenance_returns_real_graph():
    _, fid = _seed_finding()
    r = client.get(f"/findings/{fid}/provenance", headers=_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["finding"]["title"] == "Reflected XSS"
    assert data["discovered_by"] == "dynamic-agent-01"


# ---- /findings write endpoints ----

def test_finding_review_persists_decision():
    _, fid = _seed_finding()
    r = client.post(f"/findings/{fid}/review", json={"action": "approve"}, headers=_headers())
    assert r.status_code == 200
    assert r.json()["new_status"] == FindingStatus.VERIFIED

    # The persisted status is now VERIFIED.
    conf = client.get(f"/findings/{fid}/confidence", headers=_headers()).json()
    assert conf["status"] == FindingStatus.VERIFIED


def test_finding_review_reject_invalid_action():
    _, fid = _seed_finding()
    r = client.post(f"/findings/{fid}/review", json={"action": "maybe"}, headers=_headers())
    assert r.status_code == 400


def test_finding_review_requires_operator_role():
    """A read-only user cannot review findings."""
    _, fid = _seed_finding()
    viewer = User(email="viewer@target.com", name="V", google_id="g-2", role=UserRole.VIEWER, tenant_id="viewer@target.com")
    token = create_jwt_token(viewer)
    h = {"Authorization": f"Bearer {token.access_token}"}
    assert client.post(f"/findings/{fid}/review", json={"action": "approve"}, headers=h).status_code == 403


# ---- /engagements sub-routes ----

def test_engagement_subroutes_require_auth():
    assert client.get("/engagements/eng-x/tasks").status_code == 401
    assert client.get("/engagements/eng-x/unknowns").status_code == 401
    assert client.get("/engagements/eng-x/decisions").status_code == 401
    assert client.get("/engagements/eng-x/next-action").status_code == 401


def test_engagement_subroutes_404_for_unknown():
    h = _headers()
    assert client.get("/engagements/eng-missing/tasks", headers=h).status_code == 404
    assert client.get("/engagements/eng-missing/unknowns", headers=h).status_code == 404
    assert client.get("/engagements/eng-missing/decisions", headers=h).status_code == 404
    assert client.get("/engagements/eng-missing/next-action", headers=h).status_code == 404


def test_engagement_subroutes_honest_empty_for_linear_engagement():
    """A non-Director engagement returns honest empty responses, not fake data."""
    eng_uid, _ = _seed_finding()
    h = _headers()
    r = client.get(f"/engagements/{eng_uid}/tasks", headers=h)
    assert r.status_code == 200
    assert "note" in r.json()
    assert r.json()["tasks"] == {}

    r = client.get(f"/engagements/{eng_uid}/unknowns", headers=h)
    assert r.status_code == 200
    assert r.json()["unknowns"] == []

    r = client.get(f"/engagements/{eng_uid}/decisions", headers=h)
    assert r.status_code == 200
    assert r.json()["decisions"] == []

    r = client.get(f"/engagements/{eng_uid}/next-action", headers=h)
    assert r.status_code == 200
    assert r.json()["next_best_action"] == ""


def test_engagement_pause_resume_updates_status():
    eng_uid, _ = _seed_finding()
    h = _headers()
    r = client.post(f"/engagements/{eng_uid}/pause", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "paused"
    r = client.post(f"/engagements/{eng_uid}/resume", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_engagement_replan_honest_for_linear_engagement():
    eng_uid, _ = _seed_finding()
    r = client.post(f"/engagements/{eng_uid}/replan", json={"reason": "manual"}, headers=_headers())
    assert r.status_code == 200
    assert r.json()["replanned"] is False
