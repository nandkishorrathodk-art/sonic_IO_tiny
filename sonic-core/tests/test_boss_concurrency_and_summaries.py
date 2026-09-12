"""Tests verifying concurrent subagent dispatch, structured discovery extraction,
and phase intelligence propagation in BossAgent.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sonic.computer_use.boss import BossAgent
from sonic.computer_use.models_boss import Phase, SubMission, SubMissionResult
from sonic.agents.task_graph import TaskStatus


class MockComputerProvider:
    async def terminal(self, cmd: str, timeout: int = 15) -> str:
        return "mock terminal output"

    async def screenshot(self) -> bytes:
        return b"mock png bytes"

    async def status(self) -> dict:
        return {"status": "RUNNING", "windows": ["Terminal"]}


class MockLLMRouter:
    async def complete(self, request):
        resp = MagicMock()
        content = request.messages[-1].content
        if "Summarize the worker agent's findings" in str(request.messages[0].content):
            resp.content = "Port 5432 is open on target. Server returned HTTP 200 with PostgreSQL banner."
        elif "You are a Boss Agent analyzing reports" in str(request.messages[0].content):
            resp.content = "Phase 1 confirmed PostgreSQL is active on port 5432 with HTTP admin endpoint reachable."
        elif "You are a Boss Agent creating a final report" in str(request.messages[0].content):
            resp.content = "Target PostgreSQL service and web interface successfully enumerated."
        elif "Determine if the user's objective has been fully satisfied" in str(request.messages[0].content):
            resp.content = '{"complete": true, "reason": "All services identified"}'
        elif "planning the next phase of work" in content:
            resp.content = '{"thinking": "Finished", "phase_name": "Done", "sub_missions": []}'
        else:
            resp.content = '{"thinking": "Initial recon", "phase_name": "Recon", "sub_missions": []}'
        return resp


@pytest.mark.asyncio
async def test_extract_key_discoveries_structured():
    """Verify regex entity extraction captures ports, flags, and HTTP codes while filtering noise."""
    boss = BossAgent(MockComputerProvider(), MockLLMRouter())

    # Create mock traces with various realistic observations
    trace_noise = MagicMock(
        target_resource="nmap",
        payload='{"command": "nmap -p 22,5432 target"}',
        status="COMPLETED",
        actual_observation="Starting Nmap 7.80 ( https://nmap.org ) at 2026-09-12 12:00 UTC\nNmap scan report for target (10.0.0.1)\nHost is up (0.01s latency).\n22/tcp open  ssh\n5432/tcp open  postgresql\nNmap done: 1 IP address (1 host up) scanned in 0.50 seconds",
    )
    trace_diag = MagicMock(
        target_resource="ifconfig.me",
        payload='{"command": "curl ifconfig.me"}',
        status="COMPLETED",
        actual_observation="49.15.83.4",
    )
    trace_flag = MagicMock(
        target_resource="curl",
        payload='{"command": "curl -sI https://target.com/flag"}',
        status="COMPLETED",
        actual_observation="HTTP/2 200 OK\nserver: nginx\nflag: CTF{s3cur1ty_flag_pwned_1337}\ncontent-length: 42",
    )

    discoveries = boss._extract_key_discoveries([trace_noise, trace_diag, trace_flag])

    # Diagnostic IP must be skipped
    assert "49.15.83.4" not in discoveries
    # Tool noise banners must be skipped
    assert not any("Starting Nmap" in d for d in discoveries)
    assert not any("Nmap done" in d for d in discoveries)

    # Real open ports and flags must be extracted
    assert any("22/tcp open" in d for d in discoveries)
    assert any("5432/tcp open" in d for d in discoveries)
    assert any("HTTP/2 200" in d for d in discoveries)
    assert any("CTF{s3cur1ty_flag_pwned_1337}" in d for d in discoveries)


@pytest.mark.asyncio
async def test_concurrent_dependency_waves():
    """Verify that independent sub-missions execute concurrently in parallel waves."""
    boss = BossAgent(MockComputerProvider(), MockLLMRouter(), max_phases=1)

    execution_log = []

    # Mock _dispatch_sub_agent to simulate asynchronous work and record execution timing
    async def fake_dispatch(workspace_id, sub_m, phase_callback=None, sub_agent_num=1):
        execution_log.append({
            "sub_id": sub_m.id,
            "agent_num": sub_agent_num,
            "start": time.perf_counter(),
        })
        # Simulate 50ms of network / tool execution
        await asyncio.sleep(0.05)
        return SubMissionResult(
            sub_mission_id=sub_m.id,
            goal=sub_m.goal,
            success=True,
            findings_summary=f"Worker {sub_agent_num} completed {sub_m.id}",
            key_discoveries=[f"Discovery from {sub_m.id}"],
            actions_taken=2,
            duration_seconds=0.05,
        )

    boss._dispatch_sub_agent = fake_dispatch

    # Setup a phase with 3 independent tasks and 1 dependent task
    sub1 = SubMission(id="sub-1", goal="Port scan", priority=3)
    sub2 = SubMission(id="sub-2", goal="Web scan", priority=3)
    sub3 = SubMission(id="sub-3", goal="DNS recon", priority=3)
    sub4 = SubMission(id="sub-4", goal="Exploit finding", priority=1, depends_on=["sub-1", "sub-2"])

    phase = Phase(
        phase_number=1,
        name="Concurrent Recon Wave",
        thinking="Run parallel recon first, then attack",
        sub_missions=[sub1, sub2, sub3, sub4],
    )
    boss.phases.append(phase)

    # Mock LLM calls in completion / aggregation
    boss._aggregate_findings = AsyncMock(return_value="Phase 1 intelligence unified")
    boss._check_objective_complete = AsyncMock(return_value=(True, "Objective met"))

    await boss.run(workspace_id="test-ws", objective="Audit target system")

    # Verify all 4 tasks were executed
    assert len(execution_log) == 4

    # Verify unique agent numbers were allocated (1, 2, 3, 4)
    agent_nums = [entry["agent_num"] for entry in execution_log]
    assert agent_nums == [1, 2, 3, 4]

    # Verify sub1, sub2, sub3 started virtually at the same time (Wave 1: concurrent execution)
    wave1_starts = [entry["start"] for entry in execution_log if entry["sub_id"] in ("sub-1", "sub-2", "sub-3")]
    assert max(wave1_starts) - min(wave1_starts) < 0.03  # Started within 30ms of each other

    # Verify sub4 started AFTER sub1 and sub2 finished (Wave 2: dependent execution)
    sub4_entry = next(entry for entry in execution_log if entry["sub_id"] == "sub-4")
    assert sub4_entry["start"] > min(wave1_starts) + 0.04


@pytest.mark.asyncio
async def test_phase_summary_and_all_findings_collection():
    """Verify phase.summary is populated and reflected in _collect_all_findings()."""
    boss = BossAgent(MockComputerProvider(), MockLLMRouter())

    phase1 = Phase(
        phase_number=1,
        name="Service Discovery",
        summary="Unified Intelligence: Open port 5432 postgresql verified with default credentials allowed.",
    )
    boss.phases.append(phase1)

    all_findings = boss._collect_all_findings()
    assert "[Phase 1 (Service Discovery) Unified Intelligence]:" in all_findings
    assert "Open port 5432 postgresql verified" in all_findings
