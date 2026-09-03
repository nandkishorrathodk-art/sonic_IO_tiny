"""
Tests for the gap-fill backend endpoints added in Round 2:

  - /experiments/{id}/approve | /reject | /promote
  - /experiments/weaknesses/summary | /history/timeline
  - /engagements/{id}/hypotheses | /leads | /anomalies
  - /security/audit | /attack-surface | /tests | /findings | /release-gate | /reproduce/{id}
  - /workstation/services | /snapshot | /snapshots

These were previously CLI-side "no backend endpoint" gaps; they now have real
implementations so the CLI renders authentic data instead of fabricated panels.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from sonic.api.main import app

    return TestClient(app)


def _login(client: TestClient, role: str = "operator", tenant_id: str = "default") -> str:
    res = client.post(
        "/auth/login",
        json={"email": f"u@{tenant_id}.com", "name": "U", "role": role, "tenant_id": tenant_id},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==========================================================
# /experiments lifecycle: approve / reject / promote / weaknesses / history
# ==========================================================

def test_approve_reject_promote_lifecycle(client):
    """An experiment flows PROPOSED -> approve -> CANARY -> promote -> PROMOTED."""
    token = _login(client)
    h = _auth(token)

    # Propose an experiment
    res = client.post(
        "/experiments/propose",
        json={
            "title": "Tweak recon prompt",
            "description": "Mutation",
            "experiment_type": "prompt_mutation",
            "target_component": "prompts/recon.txt",
            "diff_or_payload": "add line",
        },
        headers=h,
    )
    assert res.status_code == 200, res.text
    exp_id = res.json()["proposal"]["id"]
    assert exp_id.startswith("exp-")

    # Approve -> canary_testing
    res = client.post(f"/experiments/{exp_id}/approve", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["new_state"] == "canary_testing"

    # Cannot approve twice from canary
    res = client.post(f"/experiments/{exp_id}/approve", headers=h)
    assert res.status_code == 409

    # Promote -> promoted
    res = client.post(f"/experiments/{exp_id}/promote", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "promoted"

    # History now records the promotion
    res = client.get("/experiments/history/timeline", headers=h)
    assert res.status_code == 200
    hist = res.json()
    assert hist["total_generations"] >= 1
    assert any(v["experiment_id"] == exp_id for v in hist["version_history"])


def test_reject_archives_experiment(client):
    token = _login(client)
    h = _auth(token)
    res = client.post(
        "/experiments/propose",
        json={
            "title": "Bad idea",
            "description": "x",
            "experiment_type": "prompt_mutation",
            "target_component": "prompts/recon.txt",
            "diff_or_payload": "x",
        },
        headers=h,
    )
    exp_id = res.json()["proposal"]["id"]
    res = client.post(f"/experiments/{exp_id}/reject", params={"reason": "no good"}, headers=h)
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    # Weaknesses summary surfaces the rejected experiment
    res = client.get("/experiments/weaknesses/summary", headers=h)
    assert res.status_code == 200
    assert any(w["experiment_id"] == exp_id for w in res.json()["weaknesses"])


def test_safety_violation_proposal_auto_rejected(client):
    """Proposing a change to the immutable safety layer is auto-rejected (HTTP 400)."""
    token = _login(client)
    h = _auth(token)
    res = client.post(
        "/experiments/propose",
        json={
            "title": "Disable safety",
            "description": "x",
            "experiment_type": "prompt_mutation",
            "target_component": "safety/scope.py",
            "diff_or_payload": "disable_safety=true",
        },
        headers=h,
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Rejected" in detail or "immutable" in detail.lower()
    # The rejected experiment is still stored and surfaces in weaknesses
    res = client.get("/experiments/weaknesses/summary", headers=h)
    matches = [w for w in res.json()["weaknesses"] if w["category"] == "SAFETY_VIOLATION"]
    assert matches, "Safety-violation proposal should appear in weaknesses"


def test_approve_nonexistent_returns_404(client):
    token = _login(client)
    res = client.post("/experiments/exp-doesnotexist/approve", headers=_auth(token))
    assert res.status_code == 404


def test_promote_from_wrong_state_rejected(client):
    token = _login(client)
    h = _auth(token)
    res = client.post(
        "/experiments/propose",
        json={
            "title": "Still proposed",
            "description": "x",
            "experiment_type": "prompt_mutation",
            "target_component": "prompts/recon.txt",
            "diff_or_payload": "x",
        },
        headers=h,
    )
    exp_id = res.json()["proposal"]["id"]
    # Cannot promote directly from PROPOSED
    res = client.post(f"/experiments/{exp_id}/promote", headers=h)
    assert res.status_code == 409


# ==========================================================
# /security audit lab
# ==========================================================

def test_security_tests_catalog(client):
    token = _login(client)
    res = client.get("/security/tests", headers=_auth(token))
    assert res.status_code == 200
    tests = res.json()["tests"]
    assert len(tests) == 11
    ids = {t["test_id"] for t in tests}
    assert "SEC-AUTH-01" in ids and "SEC-EVOL-01" in ids


def test_security_audit_runs_and_records(client):
    token = _login(client)
    h = _auth(token)
    res = client.post("/security/audit", headers=h)
    assert res.status_code == 200
    data = res.json()
    assert data["tests_executed"] == 11
    assert data["passed"] + data["failed"] + data["skipped"] == 11
    # Findings recorded
    res = client.get("/security/findings", headers=h)
    assert res.status_code == 200
    assert res.json()["total_recorded"] >= 11


def test_security_release_gate(client):
    token = _login(client)
    h = _auth(token)
    res = client.get("/security/release-gate", headers=h)
    assert res.status_code == 200
    # Either no audit run yet, or a gate verdict from a prior test-run audit.
    assert res.json()["status"] in (
        "NO_AUDIT_RUN",
        "RELEASE_CANDIDATE_CERTIFIED",
        "FAIL_CRITICAL",
        "FAIL_NON_CRITICAL",
    )
    # After audit we definitely have a verdict.
    client.post("/security/audit", headers=h)
    res = client.get("/security/release-gate", headers=h)
    assert res.status_code == 200
    assert res.json()["status"] in (
        "RELEASE_CANDIDATE_CERTIFIED",
        "FAIL_CRITICAL",
        "FAIL_NON_CRITICAL",
    )


def test_security_reproduce_single_test(client):
    token = _login(client)
    res = client.post("/security/reproduce/SEC-EVOL-01", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()
    assert data["test_id"] == "SEC-EVOL-01"
    assert data["verdict"] in ("PASS", "FAIL", "SKIP")
    assert data["pytest_path"].startswith("tests/")


def test_security_reproduce_unknown_id_404(client):
    token = _login(client)
    res = client.post("/security/reproduce/SEC-NOPE-99", headers=_auth(token))
    assert res.status_code == 404


def test_security_attack_surface(client):
    token = _login(client)
    res = client.get("/security/attack-surface", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    names = {s["name"] for s in data["attack_surface"]}
    assert "Public Health" in names


def test_security_endpoints_require_auth(client):
    """No token -> 401 (or 403) — not anonymous access."""
    res = client.get("/security/tests")
    assert res.status_code in (401, 403)


# ==========================================================
# /engagements hypotheses / leads / anomalies
# ==========================================================

def test_engagement_hypotheses_linear_pipeline_note(client):
    """A linear-pipeline engagement has no cognitive state -> honest note."""
    token = _login(client)
    h = _auth(token)
    res = client.post(
        "/engagements/",
        json={"name": "lin-test", "target": "example.com"},
        headers=h,
    )
    assert res.status_code == 200, res.text
    eng_id = res.json().get("engagement_id")
    res = client.get(f"/engagements/{eng_id}/hypotheses", headers=h)
    assert res.status_code == 200
    data = res.json()
    assert "note" in data or data["hypotheses"] == []


def test_engagement_leads_linear_pipeline_note(client):
    token = _login(client)
    h = _auth(token)
    res = client.post(
        "/engagements/",
        json={"name": "lin-leads", "target": "example.com"},
        headers=h,
    )
    eng_id = res.json()["engagement_id"]
    res = client.get(f"/engagements/{eng_id}/leads", headers=h)
    assert res.status_code == 200
    assert "leads" in res.json()


def test_engagement_anomalies_linear_pipeline_note(client):
    token = _login(client)
    h = _auth(token)
    res = client.post(
        "/engagements/",
        json={"name": "lin-anom", "target": "example.com"},
        headers=h,
    )
    eng_id = res.json()["engagement_id"]
    res = client.get(f"/engagements/{eng_id}/anomalies", headers=h)
    assert res.status_code == 200
    data = res.json()
    assert "anomalies" in data and "contradictions" in data


def test_engagement_hypotheses_unknown_engagement_404(client):
    token = _login(client)
    res = client.get("/engagements/eng-doesnotexist/hypotheses", headers=_auth(token))
    assert res.status_code == 404


# ==========================================================
# /workstation services / snapshots
# ==========================================================

def test_workstation_services_no_workspace(client):
    token = _login(client)
    res = client.get("/workstation/services", headers=_auth(token))
    assert res.status_code == 200
    assert "services" in res.json()


def test_workstation_snapshot_create_and_list(client):
    token = _login(client)
    h = _auth(token)
    res = client.post("/workstation/snapshot", params={"name": "test-snap"}, headers=h)
    assert res.status_code == 200
    assert res.json()["snapshot"]["name"] == "test-snap"
    res = client.get("/workstation/snapshots", headers=h)
    assert res.status_code == 200
    snaps = res.json()["snapshots"]
    assert any(s["name"] == "test-snap" for s in snaps)


def test_workstation_snapshot_requires_operator(client):
    """A read-only auditor cannot create a snapshot."""
    token = _login(client, role="auditor")
    res = client.post("/workstation/snapshot", params={"name": "x"}, headers=_auth(token))
    assert res.status_code == 403
