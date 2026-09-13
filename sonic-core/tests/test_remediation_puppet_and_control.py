"""
Targeted tests for puppet remediation and control fixes:
- Visual verification pre-action screenshot capture before marker drawing
- Application binary name resolution (no word-splitting bugs on 'Burp Suite' or 'VS Code')
- choose_action LLM routing (no blind fallback to pytest for general goals)
- Burp Suite unblocking in DaytonaComputerProvider
- SubAgent feature forwarding and context inheritance in BossAgent
- [0, 0] VLM target rejection (preventing blind top-left clicks)
- SubMissionResult semantic success evaluation
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

pytestmark = pytest.mark.no_live_infra

from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.boss import BossAgent
from sonic.computer_use.grounding import extract_bbox_midpoint
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerDecisionTrace,
    ComputerWorldObservation,
)
from sonic.computer_use.models_boss import SubMission, SubMissionResult
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.models import GUIAction, ScreenObservation


def test_extract_bbox_midpoint_rejects_zero_zero():
    """Verify [0, 0] indicating not visible returns None rather than clicking (0, 0)."""
    assert extract_bbox_midpoint([0.0, 0.0], width=1280, height=800) is None
    assert extract_bbox_midpoint("<|box_start|>(0, 0, 0, 0)<|box_end|>", width=1280, height=800) is None
    # Valid non-zero points still resolve
    valid = extract_bbox_midpoint([500, 400], width=1280, height=800)
    assert valid is not None
    assert valid == (500, 400)


def test_app_name_resolution_generic():
    """Verify application names with spaces dynamically resolve to safe binary identifiers without hardcoded app lists."""
    assert ComputerUseAgent._resolve_app_binary("Burp Suite") == "burpsuite"
    assert ComputerUseAgent._resolve_app_binary("burp") == "burp"
    assert ComputerUseAgent._resolve_app_binary("VS Code") == "vscode"
    assert ComputerUseAgent._resolve_app_binary("Wireshark") == "wireshark"
    assert ComputerUseAgent._resolve_app_binary("My Custom Tool") == "mycustomtool"


@pytest.mark.asyncio
async def test_choose_action_routes_general_goals_to_llm():
    """Goals containing 'run' or 'bash' must NOT blindly return pytest."""
    computer = AsyncMock()
    llm = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.content = (
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: bash\n"
        "PAYLOAD: {\"command\": \"cat /etc/passwd\"}\n"
        "EXPECTED: users listed"
    )
    mock_resp.reasoning_content = ""
    llm.complete = AsyncMock(return_value=mock_resp)

    agent = ComputerUseAgent(computer_provider=computer, llm_router=llm)
    obs = ComputerWorldObservation(active_application="Terminal")

    action_type, target, payload, expected = await agent.choose_action(
        "run bash script to audit accounts", obs, 1
    )

    assert llm.complete.called
    assert payload.get("command") == "cat /etc/passwd"


@pytest.mark.asyncio
async def test_choose_action_explicit_operator_override():
    """Explicit 'terminal: ls -la' syntax respects operator override."""
    computer = AsyncMock()
    llm = AsyncMock()
    agent = ComputerUseAgent(computer_provider=computer, llm_router=llm)
    obs = ComputerWorldObservation()

    action_type, target, payload, expected = await agent.choose_action(
        "terminal: ls -la", obs, 1
    )

    assert action_type == ComputerActionType.TERMINAL_EXEC
    assert payload.get("command") == "ls -la"
    assert not llm.complete.called


@pytest.mark.asyncio
async def test_visual_verification_records_clean_pre_screenshot():
    """pre_screen_b64 must be recorded before drawing action marker crosshairs."""
    computer = AsyncMock()
    clean_screenshot = "data:image/png;base64,CLEAN_SCREEN_DATA"

    obs_after = ScreenObservation(
        screenshot_base64=clean_screenshot,
        active_window="Browser",
    )
    computer.gui_action = AsyncMock(return_value=obs_after)

    agent = ComputerUseAgent(computer_provider=computer)
    agent._last_screenshot_b64 = clean_screenshot

    trace = await agent.execute_action(
        workspace_id="ws-1",
        action_type=ComputerActionType.GUI_CLICK,
        target_resource="640,400",
        payload={"x": 640, "y": 400},
        predicted_outcome="click button",
    )

    assert "[VISUAL VERIFICATION]: Screen state unchanged after click" in trace.actual_observation


@pytest.mark.asyncio
async def test_daytona_burpsuite_unblocked():
    """Burp Suite installation is no longer artificially blocked."""
    computer = DaytonaComputerProvider()
    computer.terminal = AsyncMock(return_value=MagicMock(exit_code=0, stdout="Installed", stderr=""))

    success, msg = await computer.install_application("ws-1", "burpsuite")
    assert success is True
    assert "Burp Suite installation is disabled" not in msg


@pytest.mark.asyncio
async def test_boss_subagent_feature_forwarding_and_context():
    """BossAgent forwards browser, toolsmith, and accumulated discoveries."""
    computer = AsyncMock()
    llm = AsyncMock()
    mock_browser = MagicMock()
    mock_toolsmith = MagicMock()

    boss = BossAgent(
        computer_provider=computer,
        llm_router=llm,
        browser=mock_browser,
        toolsmith=mock_toolsmith,
    )
    boss._accumulated_context.append("Found port 8080 open on 10.0.0.5")

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_instance = MagicMock()
        mock_trace = ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="scan",
            predicted_outcome="done",
            actual_observation="found /api/v1",
            status=ActionExecutionStatus.COMPLETED,
        )
        mock_instance.run_mission = AsyncMock(return_value=[mock_trace])
        MockAgentClass.return_value = mock_instance

        sub = SubMission(id="sub-1", goal="inspect endpoint", max_steps=2)
        result = await boss._dispatch_sub_agent("ws-1", sub)

        _, kwargs = MockAgentClass.call_args
        assert kwargs["browser"] == mock_browser
        assert kwargs["toolsmith"] == mock_toolsmith

        run_kwargs = mock_instance.run_mission.call_args[1]
        assert "Found port 8080 open on 10.0.0.5" in run_kwargs["goal"]


@pytest.mark.asyncio
async def test_grounding_clean_failure_without_landmarks():
    """Verify that when allow_landmarks=False, grounding fails cleanly (None) instead of clicking fake mock coordinates."""
    from sonic.computer_use.grounding import resolve_ui_target, resolve_ui_target_async

    # When allow_landmarks is False, mock landmark strings MUST return None
    res_submit = resolve_ui_target("submit button", allow_landmarks=False)
    assert res_submit is None

    res_wallet = await resolve_ui_target_async("connect wallet", allow_landmarks=False)
    assert res_wallet is None

    res_cart = await resolve_ui_target_async("cart", allow_landmarks=False)
    assert res_cart is None

    # Numeric coordinates must still resolve
    res_num = await resolve_ui_target_async("300, 200", allow_landmarks=False)
    assert res_num == (300, 200)


def test_grounding_never_uses_landmarks_when_pixels_exist():
    """Live pixels require VLM/direct coordinates even for legacy callers."""
    from sonic.computer_use.grounding import resolve_ui_target

    assert resolve_ui_target(
        "connect wallet",
        screenshot_b64="not-a-real-image",
        allow_landmarks=True,
    ) is None


def test_boss_parallel_worker_budget_is_explicit_and_bounded():
    """Boss exposes a configured concurrency budget rather than a fixed wave size."""
    boss = BossAgent(
        computer_provider=MagicMock(),
        llm_router=MagicMock(),
        max_parallel_workers=2,
    )
    assert boss.max_parallel_workers == 2


def test_replan_trigger_negation_awareness():
    """Verify that negated vulnerability claims do NOT trigger NEW_HIGH_CONFIDENCE_FINDING."""
    from sonic.agents.replan import ReplanTrigger
    from sonic.computer_use.boss import BossAgent
    from sonic.computer_use.models_boss import SubMissionResult

    boss = BossAgent(computer_provider=MagicMock(), llm_router=MagicMock())

    # Negated SQLi and bypass
    neg_res = SubMissionResult(
        sub_mission_id="sub-neg",
        goal="Test login for SQLi",
        success=True,
        findings_summary="Target is not vulnerable to SQLi and failed to bypass authentication.",
        key_discoveries=["No SQLi detected"],
    )
    trigger = boss._detect_sub_mission_trigger(neg_res)
    assert trigger is None


def test_replan_trigger_broad_offensive_coverage():
    """Verify that SSRF, IDOR, buffer overflow, and CTF flags trigger NEW_HIGH_CONFIDENCE_FINDING."""
    from sonic.agents.replan import ReplanTrigger
    from sonic.computer_use.boss import BossAgent
    from sonic.computer_use.models_boss import SubMissionResult

    boss = BossAgent(computer_provider=MagicMock(), llm_router=MagicMock())

    # 1. SSRF
    ssrf_res = SubMissionResult(
        sub_mission_id="sub-ssrf",
        goal="Check webhook",
        success=True,
        findings_summary="Confirmed SSRF to internal metadata service 169.254.169.254.",
    )
    assert boss._detect_sub_mission_trigger(ssrf_res) == ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING

    # 2. IDOR / Authorization
    idor_res = SubMissionResult(
        sub_mission_id="sub-idor",
        goal="Audit user profile API",
        success=True,
        findings_summary="Discovered critical IDOR allowing unauthorized access to admin records.",
    )
    assert boss._detect_sub_mission_trigger(idor_res) == ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING

    # 3. Binary Memory Corruption
    pwn_res = SubMissionResult(
        sub_mission_id="sub-pwn",
        goal="Analyze binary parser",
        success=True,
        findings_summary="Confirmed buffer overflow and constructed ROP chain.",
    )
    assert boss._detect_sub_mission_trigger(pwn_res) == ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING

    # 4. CTF Flag
    flag_res = SubMissionResult(
        sub_mission_id="sub-flag",
        goal="Extract flag",
        success=True,
        findings_summary="Flag extracted successfully: flag{autonomous_penetration_architect_2026}",
    )
    assert boss._detect_sub_mission_trigger(flag_res) == ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING

    # 5. Attack surface (open port)
    port_res = SubMissionResult(
        sub_mission_id="sub-port",
        goal="Recon target",
        success=True,
        findings_summary="Discovered open port 3306 on target.",
    )
    assert boss._detect_sub_mission_trigger(port_res) == ReplanTrigger.NEW_ATTACK_SURFACE


def test_boss_target_agnostic_fallback_decomposition():
    """Fallback stays adaptive instead of forcing a domain-specific pipeline."""
    from sonic.computer_use.boss import BossAgent

    boss = BossAgent(computer_provider=MagicMock(), llm_router=MagicMock())

    phase_bin = boss._fallback_decomposition("Analyze /tmp/firmware.bin and reverse engineer the key")
    assert phase_bin.phase_number == 1
    assert len(phase_bin.sub_missions) == 1
    assert phase_bin.sub_missions[0].id == "adaptive-investigator"
    assert "predefined tool sequence" in phase_bin.sub_missions[0].goal
    assert len(boss.thinking_log) >= 1

    phase_net = boss._fallback_decomposition("Scan network subnet 10.0.0.0/24 for active hosts")
    assert len(phase_net.sub_missions) == 1
    assert phase_net.sub_missions[0].depends_on == []
    assert phase_net.name == "Adaptive Investigation (Fallback)"


def test_command_parser_no_arbitrary_tuln_flag_injection():
    """Verify alternative command parsing does not inject hardcoded -tuln flags."""
    from sonic.computer_use.agent import ComputerUseAgent

    agent = ComputerUseAgent(computer_provider=MagicMock(), llm_router=None)
    action_type, target, payload, expected = agent._parse_llm_action(
        "ACTION: TERMINAL_EXEC\nTARGET: compiler\nCOMMAND: gcc or clang\nEXPECTED: compiler check",
        default_file="main.py",
    )
    assert "-tuln" not in payload.get("command", "")
    assert payload["command"] == "which gcc && gcc || clang"
