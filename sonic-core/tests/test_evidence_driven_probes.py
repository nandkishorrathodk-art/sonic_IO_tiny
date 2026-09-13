"""
Evidence-driven, concrete probe planning — anti-puppet done-gate tests.

This closes the "puppet gate" gap: the planner previously emitted
``echo APPROVAL_REQUIRED`` as its active-test action — a no-op string that gave
the operator nothing real to approve and taught the executor nothing. Now the
planner derives CONCRETE, typed ``target_security_scan`` probes from the
objective and the in-scope target, and the follow-up batch adapts to the actual
evidence of the completed discovery batch.

Assertions here prove:

  1. ``build_plan`` for an active-test objective NEVER contains the dummy
     ``echo APPROVAL_REQUIRED``; it contains real approval-required probes.
  2. Every probe is a ``target_security_scan`` planned action with a concrete
     tool (nmap/http_client/nuclei/ffuf), a concrete target derived from the
     mission target, a concrete option set, and a human-readable ``command``
     preview the operator can review.
  3. Probes only exist for active-test intents; read-only inspection objectives
     emit no approval-required action.
  4. The probe inputs dispatch correctly through the real ``MissionToolExecutor``
     security-tool path (with a fake scanner registry), which remains
     approval-gated.
  5. Follow-up actions adapt to evidence: a discovery batch that surfaced
     secrets or web routes yields different read-only follow-ups than one that
     did not.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sonic.mission_engine.executor import MissionToolExecutor
from sonic.mission_engine.planner import MissionPlanner, PlannedAction
from sonic.mission_engine.tool_registry import ToolRisk
from sonic.sandbox.provider import ExecResult
from sonic.tools.base import SecurityTool, ToolRequest, ToolResult, ToolStatus


def _plan(objective, target="https://api.internal.target:8443/v1"):
    return MissionPlanner().build_plan("m-evidence", objective, target, "ws-1")


def _probes(plan):
    return [a for a in plan.actions if a.tool == "target_security_scan"]


# =====================================================================
# 1. The dummy echo gate is gone
# =====================================================================

def test_no_dummy_echo_approval_gate():
    """An active-test objective must NOT carry the scripted `echo APPROVAL_REQUIRED`
    no-op — it must carry concrete probe proposals."""
    plan = _plan("scan and audit the target for open ports")
    texts = [str(a.model_dump()) for a in plan.actions]
    assert not any("echo APPROVAL_REQUIRED" in t for t in texts), \
        "the puppet `echo APPROVAL_REQUIRED` stub must be gone"
    probes = _probes(plan)
    assert probes, "an active-test objective MUST produce concrete probes"


# =====================================================================
# 2. Probes are concrete, typed, and derived from the target
# =====================================================================

def test_probes_are_concrete_and_scoped_to_target():
    plan = _plan("scan and audit the target for open ports")
    probes = _probes(plan)
    assert probes
    for probe in probes:
        assert probe.risk == ToolRisk.APPROVAL_REQUIRED
        assert probe.requires_approval is True
        tool = probe.input["tool"]
        assert tool in {"nmap", "http_client", "nuclei", "ffuf"}
        target = probe.input["target"]
        # The probe must be scoped to the mission target, never a random host.
        assert "api.internal.target" in target or target == "api.internal.target", \
            f"probe target {target!r} must stay within the in-scope target"
        # A human-readable command preview exists for the operator.
        assert "command" in probe.input and probe.input["command"].strip()
        # Options exist and keep the scan bounded/non-destructive.
        assert probe.input.get("options")


def test_nmap_probe_uses_bounded_options():
    plan = _plan("scan the target")
    nmap = next(p for p in _probes(plan) if p.input["tool"] == "nmap")
    opts = nmap.input["options"]
    assert opts.get("ports") == "top-100"
    assert opts.get("timing") == "T4"
    assert "--open" in opts.get("extra_args", "")


def test_web_intent_gets_http_probe():
    plan = _plan("audit the http api endpoints")
    http = next(p for p in _probes(plan) if p.input["tool"] == "http_client")
    assert http.input["target"].startswith("https://api.internal.target:8443")  # port preserved


def test_readonly_objective_produces_no_probes():
    plan = _plan("inspect the source code structure")
    assert not _probes(plan)
    assert not any(a.requires_approval for a in plan.actions)


# =====================================================================
# 3. Probes dispatch through the executor's security-tool path AND stay
#    approval-gated
# =====================================================================

class _FakeScanner(SecurityTool):
    """A real SecurityTool double that records the dispatched request."""
    def __init__(self, provider: Any, name: str = "nmap", stdout: str = "scan ok"):
        super().__init__(provider)
        self._name = name
        self._stdout = stdout
        self.last_request: ToolRequest | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return "test-1.0"

    def build_command(self, request: ToolRequest) -> str:
        return f"{self._name} {request.target}"

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        return [{"finding": "open", "raw": raw_stdout}]

    async def execute(self, request: ToolRequest) -> ToolResult:
        self.last_request = request
        return ToolResult(
            execution_id=request.execution_id,
            tenant_id=request.tenant_id,
            engagement_id=request.engagement_id,
            workspace_id=request.workspace_id,
            agent_id=request.agent_id,
            tool_name=self._name,
            tool_version=self.version,
            status=ToolStatus.COMPLETED,
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=datetime.now(timezone.utc).isoformat(),
            exit_code=0,
            raw_stdout=self._stdout,
            raw_stderr="",
            parsed_data=self.parse_output(self._stdout, ""),
        )


class _StubComputer:
    async def terminal(self, workspace_id, command, timeout=120, actor="operator"):
        return ExecResult(command=command, exit_code=0, stdout="", stderr="")


def test_probe_executes_only_with_approval():
    scanner = _FakeScanner(_StubComputer(), name="nmap")
    executor = MissionToolExecutor(_StubComputer(), security_tools={"nmap": scanner}, scoped_target="api.internal.target")

    probe = next(p for p in _probes(_plan("scan the target")) if p.input["tool"] == "nmap")

    # Without approval → AWAITING_APPROVAL, scanner never invoked.
    res = asyncio.run(executor.execute(probe, target_workspace_id="ws-1", approved=False))
    assert res.status == "AWAITING_APPROVAL"
    assert scanner.last_request is None

    # With approval → dispatched through the scanner with the probe's real options.
    res = asyncio.run(executor.execute(probe, target_workspace_id="ws-1", approved=True))
    assert res.status == "SUCCESS"
    assert scanner.last_request is not None
    assert scanner.last_request.target == "api.internal.target"
    assert scanner.last_request.options.get("ports") == "top-100"


def test_executor_blocks_out_of_scope_probe_even_when_approved():
    """Scope hardening: a probe aimed outside the engaged scope is BLOCKED
    even after operator approval — a defence in depth over the planner-only
    construction guarantee."""
    scanner = _FakeScanner(_StubComputer(), name="nmap")
    executor = MissionToolExecutor(_StubComputer(), security_tools={"nmap": scanner}, scoped_target="api.internal.target")

    probe = PlannedAction(
        tool="target_security_scan",
        input={"tool": "nmap", "target": "10.0.0.99", "options": {}},
        risk=ToolRisk.APPROVAL_REQUIRED,
        requires_approval=True,
    )
    res = asyncio.run(executor.execute(probe, target_workspace_id="ws-1", approved=True))
    assert res.status == "BLOCKED"
    assert "outside the engagement scope" in res.output
    assert scanner.last_request is None

    # Suffix-safe: a sibling that merely *ends with* the scope is out-of-scope.
    executor_suffix = MissionToolExecutor(_StubComputer(), security_tools={"nmap": scanner}, scoped_target="internal.target")
    probe_bad = PlannedAction(
        tool="target_security_scan",
        input={"tool": "nmap", "target": "https://internal.target.evil.net:8443", "options": {}},
        risk=ToolRisk.APPROVAL_REQUIRED,
        requires_approval=True,
    )
    res_bad = asyncio.run(executor_suffix.execute(probe_bad, target_workspace_id="ws-1", approved=True))
    assert res_bad.status == "BLOCKED"


# =====================================================================
# 4. Follow-up adapts to evidence (not a fixed copy-paste batch)
# =====================================================================

def test_follow_up_adapts_to_secret_evidence():
    planner = MissionPlanner()
    plan = planner.build_plan("m-lh2", "scan and audit the target", "api.internal.target", "ws-1")
    completed = {a.action_id for a in plan.actions}

    # Evidence that surfaced a hardcoded credential.
    secret_evidence = ["grep tokens ...: aws_secret_access_key = 'AKIA...' found in config.py"]

    follow_up = planner.build_follow_up_actions(
        plan, completed, evidence_brief=secret_evidence
    )
    cmds = " ".join(a.input["command"] for a in follow_up)
    assert "secret" in cmds or "api[_-]?key" in cmds or "password" in cmds, \
        "evidence of a secret must trigger a secret-hunt follow-up"
    assert all(a.risk == ToolRisk.READ_ONLY for a in follow_up)


def test_follow_up_adapts_to_web_route_evidence():
    planner = MissionPlanner()
    plan = planner.build_plan("m-lh3", "audit the web api", "api.internal.target", "ws-1")
    completed = {a.action_id for a in plan.actions}

    follow_up = planner.build_follow_up_actions(
        plan, completed, evidence_brief=["found endpoint route /api/v1/auth in router definitions"]
    )
    cmds = " ".join(a.input["command"] for a in follow_up)
    assert "router" in cmds or "app.get" in cmds or "endpoint" in cmds


def test_follow_up_without_evidence_stays_baseline():
    planner = MissionPlanner()
    plan = planner.build_plan("m-lh4", "scan the target", "api.internal.target", "ws-1")
    completed = {a.action_id for a in plan.actions}

    bare = planner.build_follow_up_actions(plan, completed, evidence_brief=None)
    secret = planner.build_follow_up_actions(
        plan, completed, evidence_brief=["found hardcoded token sk-abc123xyz in creds.py"]
    )
    assert "".join(a.input["command"] for a in bare) != "".join(a.input["command"] for a in secret)


import pytest


@pytest.mark.asyncio
async def test_approve_workstation_mission_probe_endpoint(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sonic.api.routes.workstation import router, _get_or_create_session
    from sonic.auth.models import User, UserRole
    from sonic.auth.middleware import require_operator

    session = _get_or_create_session("op@corp.com", "test-session")
    session["target_sandbox"] = {"workspace_id": "ws-target", "sandbox_id": "ws-target", "target": "10.0.0.1", "scope_verified": True}
    session["mission"] = {
        "mission_id": "m-123",
        "status": "AWAITING_APPROVAL",
        "proposed_actions": [
            {
                "action_id": "act-probe-1",
                "tool": "target_security_scan",
                "input": {"tool": "nmap", "target": "10.0.0.1", "options": {"ports": "top-100", "timing": "T4", "extra_args": "-sV"}},
                "risk": "APPROVAL_REQUIRED",
                "requires_approval": True,
                "stage": 3,
                "depends_on": "",
            }
        ],
        "events": [],
    }

    app = FastAPI()
    app.include_router(router)

    class _MockComputer:
        async def terminal(self, *args, **kwargs):
            return ExecResult(command="cmd", exit_code=0, stdout="PORT 80/tcp OPEN", stderr="")

        async def execute(self, *args, **kwargs):
            return ExecResult(command="cmd", exit_code=0, stdout="80/tcp open http Apache\n", stderr="")

    monkeypatch.setattr("sonic.api.routes.workstation.get_daytona_computer", lambda: _MockComputer())
    app.dependency_overrides[require_operator] = lambda: User(email="op@corp.com", name="Operator", role=UserRole.OPERATOR, tenant_id="tenant-1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test approving the probe
        resp = await client.post(
            "/workstation/mission/approve-probe?session_id=test-session",
            json={"action_id": "act-probe-1", "approved": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["mission_status"] == "COMPLETED"
        assert session["mission"]["proposed_actions"] == []


@pytest.mark.asyncio
async def test_dismiss_workstation_mission_probe_endpoint(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sonic.api.routes.workstation import router, _get_or_create_session
    from sonic.auth.models import User, UserRole
    from sonic.auth.middleware import require_operator

    session = _get_or_create_session("op@corp.com", "test-session-dismiss")
    session["target_sandbox"] = {"workspace_id": "ws-target", "sandbox_id": "ws-target", "target": "10.0.0.1", "scope_verified": True}
    session["mission"] = {
        "mission_id": "m-456",
        "status": "AWAITING_APPROVAL",
        "proposed_actions": [
            {
                "action_id": "act-probe-dismiss",
                "tool": "target_security_scan",
                "input": {"tool": "ffuf", "target": "10.0.0.1", "options": {}},
                "risk": "APPROVAL_REQUIRED",
                "requires_approval": True,
                "stage": 3,
                "depends_on": "",
            }
        ],
        "events": [],
    }

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_operator] = lambda: User(email="op@corp.com", name="Operator", role=UserRole.OPERATOR, tenant_id="tenant-1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/workstation/mission/approve-probe?session_id=test-session-dismiss",
            json={"action_id": "act-probe-dismiss", "approved": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dismissed"
        assert data["mission_status"] == "DISMISSED"
        assert session["mission"]["proposed_actions"] == []