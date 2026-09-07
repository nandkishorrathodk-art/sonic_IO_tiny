"""
Tests for SONIC's Cross-Session Memory & Lessons Ledger:
  1. Distilling traces into real lessons (AVOID for failed, REUSE for success).
  2. Honesty: zero fabrication from empty traces.
  3. Deduplication and ranking by relevance.
  4. Durable persistence across restarts (host-FS JSON).
  5. Tenant and agent isolation.
  6. Injection into ComputerUseAgent reasoning context.
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from sonic.being.lessons import (
    LessonKind,
    LessonsLedger,
    extract_lessons,
    inject_into_context,
)
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType, ComputerDecisionTrace


@pytest.fixture
def temp_ledger_dir(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setenv("SONIC_DATA_DIR", temp_dir)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_extract_lessons_honesty():
    """Empty traces produce NO fabricated lessons."""
    assert extract_lessons([], goal="Test goal") == []


def test_extract_lessons_from_traces():
    """Real traces distill into AVOID for failures and REUSE for successes."""
    traces = [
        ComputerDecisionTrace(
            step_index=1,
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="nmap -sV target",
            predicted_outcome="Discover ports",
            actual_observation="nmap: command not found",
            status="FAILED",
        ),
        ComputerDecisionTrace(
            step_index=2,
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl -s http://target:8080",
            predicted_outcome="Read HTTP headers",
            actual_observation="HTTP/1.1 200 OK",
            status="SUCCESS",
        ),
    ]

    lessons = extract_lessons(traces, goal="Inspect target web service")
    assert len(lessons) == 2

    avoid = [lsn for lsn in lessons if lsn.kind == LessonKind.AVOID]
    reuse = [lsn for lsn in lessons if lsn.kind == LessonKind.REUSE]

    assert len(avoid) == 1
    assert "nmap" in avoid[0].approach
    assert "not found" in avoid[0].evidence

    assert len(reuse) == 1
    assert "curl" in reuse[0].approach
    assert "200 OK" in reuse[0].evidence


def test_lessons_ledger_persistence_and_isolation(temp_ledger_dir):
    """Lessons survive ledger restart and respect tenant/agent isolation."""
    ledger1 = LessonsLedger(tenant_id="tenant-a", agent_id="agent-1")
    traces = [
        ComputerDecisionTrace(
            step_index=1,
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="pytest",
            predicted_outcome="Pass tests",
            actual_observation="3 passed",
            status="SUCCESS",
        )
    ]
    lessons = extract_lessons(traces, goal="Run test suite")
    ledger1.record(lessons)

    # Re-instantiate same tenant+agent -> loads from disk
    ledger1_reloaded = LessonsLedger(tenant_id="tenant-a", agent_id="agent-1")
    all_lessons = ledger1_reloaded.all()
    assert len(all_lessons) == 1
    assert all_lessons[0].kind == LessonKind.REUSE

    # Different tenant -> isolated (empty)
    ledger_b = LessonsLedger(tenant_id="tenant-b", agent_id="agent-1")
    assert len(ledger_b.all()) == 0

    # Different agent -> isolated (empty)
    ledger_other_agent = LessonsLedger(tenant_id="tenant-a", agent_id="agent-2")
    assert len(ledger_other_agent.all()) == 0


def test_lessons_deduplication(temp_ledger_dir):
    """Recording the same lesson twice deduplicates."""
    ledger = LessonsLedger(tenant_id="test", agent_id="agent-test")
    traces = [
        ComputerDecisionTrace(
            step_index=1,
            action_type=ComputerActionType.FILE_READ,
            target_resource="/etc/shadow",
            predicted_outcome="Read file",
            actual_observation="Permission denied",
            status="FAILED",
        )
    ]
    lessons1 = extract_lessons(traces, goal="Steal shadow")
    lessons2 = extract_lessons(traces, goal="Steal shadow again")

    ledger.record(lessons1)
    ledger.record(lessons2)

    assert len(ledger.all()) == 1


def test_inject_into_context_and_relevance(temp_ledger_dir):
    """Context block formats properly and prioritizes relevant lessons."""
    ledger = LessonsLedger(tenant_id="test", agent_id="agent-test")
    traces = [
        ComputerDecisionTrace(
            step_index=1,
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="sqlmap -u target",
            predicted_outcome="Inject SQL",
            actual_observation="WAF blocked connection",
            status="FAILED",
        ),
        ComputerDecisionTrace(
            step_index=2,
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="nuclei -t cves/",
            predicted_outcome="Scan templates",
            actual_observation="Scan completed cleanly",
            status="SUCCESS",
        ),
    ]
    ledger.record(extract_lessons(traces, goal="Run security scan with sqlmap"))

    # Matching goal retrieves sqlmap lesson
    relevant = ledger.relevant("Test SQL injection with sqlmap")
    assert len(relevant) >= 1
    assert any("sqlmap" in lsn.approach for lsn in relevant)

    # Injected text has AVOID block
    rendered = inject_into_context(relevant)
    assert "[AVOID]" in rendered
    assert "WAF blocked" in rendered


@pytest.mark.asyncio
async def test_agent_reasoning_context_includes_lessons(temp_ledger_dir):
    """ComputerUseAgent._build_reasoning_context injects lessons into prompt."""
    ledger = LessonsLedger(tenant_id="tenant-cu", agent_id="agent-cu")
    traces = [
        ComputerDecisionTrace(
            step_index=1,
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="nikto -h web",
            predicted_outcome="Scan server",
            actual_observation="timed out",
            status="FAILED",
        )
    ]
    ledger.record(extract_lessons(traces, goal="Scan web with nikto"))

    class DummyComputer:
        pass

    agent = ComputerUseAgent(
        computer_provider=DummyComputer(),
        lessons_ledger=ledger,
        tenant_id="tenant-cu",
        agent_id="agent-cu",
    )

    from sonic.computer_use.models import ComputerWorldObservation
    obs = ComputerWorldObservation(
        visible_text="Terminal prompt ready",
        terminal_output="",
        windows=[],
        active_application="Terminal",
    )

    system_prompt, user_prompt = agent._build_reasoning_context(
        "Scan web server with nikto", obs, step_index=1,
        primary_file="server.py", test_file="test_server.py",
    )
    assert "Past lessons — approaches that FAILED (avoid repeating):" in user_prompt
    assert "[AVOID]" in user_prompt
    assert "nikto" in user_prompt
