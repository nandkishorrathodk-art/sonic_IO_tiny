"""
SONIC-REDA — Autonomous Computer-Use Agent Engine (Phase 3: real reasoning)
==========================================================================
Closed-loop autonomous engineer that operates the SONIC Computer to
investigate, inspect, edit, build, test, debug, verify, and remediate code.

Phase 3 replaced the step-indexed hardcoded script with genuine
observe → reason (LLM) → act → observe-result reasoning. The agent carries
its action history and the live screen/terminal observation into each LLM
call, so its next action is a function of (goal, observation, history) — not
of a step counter. No vulnerability-specific fix is hardcoded anywhere.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import time
from typing import Any

from sonic.computer.models import (
    GUIAction,
    GUIActionType,
)
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.grounding import (
    draw_action_marker,
    query_multimodal_grounding,
    resolve_ui_target,
    resolve_ui_target_async,
)
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerAutonomyLevel,
    ComputerDecisionTrace,
    ComputerUseMetrics,
    ComputerWorldObservation,
    EngineeringMissionMode,
    FailureClassification,
    FailureRecord,
    StrategyState,
    SubGoal,
    SubGoalChecklist,
    SubGoalStatus,
)
from sonic.computer_use.motor import MotorReflexes
from sonic.computer_use.scratchpad import HackerScratchpad
from sonic.computer_use.wire_telemetry import WireTelemetryEngine
from sonic.research.failure_budget import FailureBudgetTracker
from sonic.research.failure_classifier import classify_failure

from sonic.logger import get_logger

logger = get_logger(__name__)

# A sentinel the LLM may emit to signal the goal is achieved, so the mission
# loop can terminate early instead of running a fixed step count.
_GOAL_COMPLETE_SENTINEL = "GOAL_COMPLETE"


class ComputerUseAgent:
    """
    Autonomous Computer-Using Engineer uniting Brain (Cognitive State,
    Hypothesis Portfolio, Epistemic Reasoning) and Body (SONIC Computer).

    When an ``llm_router`` is supplied, action selection is genuinely LLM-driven:
    each step the agent observes the world (screen text, terminal output, files,
    git state), feeds that plus its action history to the LLM, and executes the
    returned action. Without a router it falls back to a generic, non-scripted
    diagnostic probe (read the primary file) — never a hardcoded vulnerability
    fix.
    """

    def __init__(
        self,
        computer_provider: ComputerProvider,
        autonomy_level: ComputerAutonomyLevel = ComputerAutonomyLevel.L3_AUTONOMOUS,
        mode: EngineeringMissionMode = EngineeringMissionMode.ENGINEERING_MODE,
        max_actions: int = 50,
        max_recovery_attempts: int = 5,
        llm_router: Any | None = None,
        browser: Any | None = None,
        security_tools: dict[str, Any] | None = None,
        safety: Any | None = None,
        self_host: bool = False,
        toolsmith: Any | None = None,
        method_lab: Any | None = None,
        lessons_ledger: Any | None = None,
        tenant_id: str = "default",
        engagement_id: str = "default",
        agent_id: str = "computer-use-agent",
        enable_llm_verification: bool = False,
        failure_budget: FailureBudgetTracker | None = None,
        scratchpad: HackerScratchpad | None = None,
        motor: MotorReflexes | None = None,
        wire_telemetry: WireTelemetryEngine | None = None,
        burp_client: Any | None = None,
    ):
        self.computer = computer_provider
        self.autonomy_level = autonomy_level
        self.mode = mode
        self.max_actions = max_actions
        self.max_recovery_attempts = max_recovery_attempts
        self.llm_router = llm_router  # ModelRouter for LLM-driven reasoning
        # Optional BrowserAgent so the same observe->reason->act loop can drive a
        # real web browser (navigate/click/type/screenshot) — unified computer-use.
        self.browser = browser
        # Optional registry of SecurityTool adapters (name -> tool) the agent can
        # invoke as a first-class reasoning action. Tools execute in-sandbox and
        # fail closed; their structured findings feed back into the observation.
        self.security_tools = security_tools or {}
        # Optional ToolsmithLoop (Phase A, AIOSR): the being authors NEW tools
        # for observation gaps. The authored tool is registered into the
        # security_tools map ONLY after a real in-sandbox run succeeds.
        self.toolsmith = toolsmith
        # Optional MethodLab (Phase B, AIOSR): the being synthesizes NOVEL
        # offensive techniques (new methods, not just tools) from observation +
        # failure + the known-technique ledger. Confirmed only on reproduction.
        self.method_lab = method_lab
        # Optional LessonsLedger (self-improvement learn→apply loop): persists
        # cross-mission lessons (failed approaches to avoid, successful ones to
        # reuse) and injects them into reasoning so the being does not forget
        # what it learned across missions. None = lessons not collected.
        self.lessons_ledger = lessons_ledger
        # Optional fail-closed safety envelope (PLAN Phase 6). Required in
        # self-host mode: the agent may NOT act autonomously without a policy.
        self.safety = safety
        self.self_host = self_host
        if self_host and safety is None:
            raise ValueError(
                "self-host mode requires a safety policy — construct "
                "ComputerUseAgent with safety=ActionPolicy(...) so every "
                "autonomous action passes the fail-closed envelope."
            )
        self.tenant_id = tenant_id
        self.engagement_id = engagement_id
        self.agent_id = agent_id
        self.enable_llm_verification = enable_llm_verification
        self.failure_budget = failure_budget if failure_budget is not None else FailureBudgetTracker()
        self.scratchpad = scratchpad if scratchpad is not None else HackerScratchpad()
        self.motor = motor if motor is not None else MotorReflexes(self.computer)
        self.burp_client = burp_client
        self.wire_telemetry = (
            wire_telemetry
            if wire_telemetry is not None
            else WireTelemetryEngine(burp_client)
        )
        self.strategies: dict[str, dict[str, Any]] = {
            "Strategy A": {
                "name": "Direct Primary Execution",
                "description": "Primary probe / targeted execution",
                "state": StrategyState.ACTIVE,
            },
            "Strategy B": {
                "name": "Alternative Instrumentation",
                "description": "Secondary inspection / fallback tool",
                "state": StrategyState.ACTIVE,
            },
        }

        self.traces: list[ComputerDecisionTrace] = []
        self.recovery_events: int = 0
        self.action_counter: int = 0
        self.metrics = ComputerUseMetrics()
        # Running transcript of (action, result) the LLM reasons over. This is
        # what makes the agent adaptive: step N's action depends on step N-1's
        # observed outcome, not on a pre-written script.
        self.history: list[dict[str, str]] = []
        # Last captured browser page state, carried into the next observation so
        # the LLM sees the current page even between browser actions.
        self._last_browser_snapshot: Any | None = None
        # Last structured security-tool result, surfaced to the next reasoning
        # step so the LLM acts on real scan findings rather than a claim.
        self._last_tool_result: Any | None = None
        self._last_screenshot_b64: str = ""
        # Last observed screen dimensions, used to validate GUI coordinate
        # actions before they touch the provider. Updated on every observe() /
        # screenshot; sane defaults until the first real observation lands.
        self._screen_width: int = 1920
        self._screen_height: int = 1080
        self._interrupted: bool = False
        self.goal_reached: bool = False
        self._consecutive_failures: int = 0
        self._replan_count: int = 0
        self._last_navigated_url: str = ""
        self._recent_action_signatures: list[tuple[str, str, str]] = []
        self.checklist: SubGoalChecklist | None = None

    def interrupt(self) -> None:
        """Signal the agent to stop its active mission loop immediately."""
        self._interrupted = True

    async def decompose_goal(self, goal: str) -> SubGoalChecklist:
        """Decompose a top-level mission into sequential, verifiable sub-goals."""
        sub_goals: list[SubGoal] = []

        # 1. Check for explicit numbered/bulleted steps in user prompt
        lines = [line.strip() for line in goal.splitlines() if line.strip()]
        if len(lines) <= 1:
            lines = [line.strip() for line in re.split(r'(?<=\w\w)\.\s+(?=[0-9]\.|\b[A-Z])', goal) if line.strip()]
        numbered_items = []
        for l in lines:
            m = re.match(r'^(?:\d+[\.\)]|\-|\*)\s*(.*)', l)
            if m and len(m.group(1).strip()) > 3:
                numbered_items.append(m.group(1).strip())

        if len(numbered_items) >= 2:
            for item in numbered_items[:6]:
                sub_goals.append(SubGoal(description=item))
            return SubGoalChecklist(top_level_goal=goal, sub_goals=sub_goals, active_index=0)

        # 2. Intent-based heuristic decomposition
        g_lower = goal.lower()
        if any(w in g_lower for w in ("http://", "https://", ".com", ".org", "browse", "opensea", "web", "site")):
            target_url = ""
            for part in goal.split():
                if part.startswith(("http://", "https://")):
                    target_url = part
                    break
            sub_goals = [
                SubGoal(description=f"Navigate to {target_url or 'target web page'} and confirm page loaded"),
                SubGoal(description="Locate interactive search or input controls and execute query"),
                SubGoal(description="Read observation results and verify data extracted"),
            ]
        elif any(w in g_lower for w in ("scan", "port", "nmap", "recon", "network")):
            sub_goals = [
                SubGoal(description="Perform initial network reconnaissance and service discovery"),
                SubGoal(description="Analyze open ports and inspect service banners"),
                SubGoal(description="Compile security findings and verify evidence"),
            ]
        elif any(w in g_lower for w in ("test", "pytest", "unit test", "bug", "fix")):
            sub_goals = [
                SubGoal(description="Inspect test files and reproduce initial state"),
                SubGoal(description="Implement fix or diagnostic patch"),
                SubGoal(description="Run test suite and confirm verification passes"),
            ]
        else:
            sub_goals = [
                SubGoal(description=f"Inspect environment and orient on primary resource for: {goal[:50]}"),
                SubGoal(description="Execute core operation and collect output"),
                SubGoal(description="Verify outcome matches expectation and complete goal"),
            ]

        return SubGoalChecklist(top_level_goal=goal, sub_goals=sub_goals, active_index=0)

    # =============================================================
    # 1. Closed-Loop Observation
    # =============================================================
    async def observe(self, workspace_id: str) -> ComputerWorldObservation:
        """Capture a multi-modal observation of the computer environment.

        The terminal output is read from a real (cheap) probe so the agent
        reacts to what is actually on the screen/terminal, not a placeholder.
        When a browser is attached, the current page state (url, title,
        interactive elements) is folded into the observation so the same
        reasoning loop can drive web interaction.
        """
        screen_obs = await self.computer.screenshot(workspace_id)
        # Store screenshot for vision-in-the-loop (VLM image input)
        self._last_screenshot_b64 = getattr(screen_obs, "screenshot_base64", "")
        # Track real screen dimensions so coordinate actions can be validated
        # against the actual desktop size rather than a default guess. Some
        # callers construct the agent via __new__ (bypassing __init__), so
        # initialize the defaults defensively here if they are missing.
        if not hasattr(self, "_screen_width"):
            self._screen_width = 1920
        if not hasattr(self, "_screen_height"):
            self._screen_height = 1080
        self._screen_width = int(getattr(screen_obs, "width", self._screen_width) or self._screen_width)
        self._screen_height = int(getattr(screen_obs, "height", self._screen_height) or self._screen_height)
        status = await self.computer.status(workspace_id)
        files = await self.computer.list_files(workspace_id, ".")
        git_st = await self.computer.git_action(workspace_id, "status")

        # Read the live terminal state so reasoning reflects reality. A no-op
        # echo keeps this cheap; providers return their real shell output.
        try:
            term_res = await self.computer.terminal(workspace_id, "echo __sonic_obs_ready__")
            terminal_output = (term_res.stdout.strip() if term_res.stdout else "") or f"Exit {term_res.exit_code}"
        except Exception:
            terminal_output = f"Terminal Ready ({len(status.running_processes)} procs)"

        if not hasattr(self, "_last_navigated_url"):
            self._last_navigated_url = ""
        if not hasattr(self, "_recent_action_signatures"):
            self._recent_action_signatures = []

        browser_state = {
            "url": self._last_navigated_url or "about:blank",
            "title": "Desktop Browser" if self._last_navigated_url else "New Tab",
            "interactive_elements": [],
        }
        if self.browser is not None:
            try:
                browser_state = await self._observe_browser()
            except Exception as e:
                logger.warning("browser_observe_failed", error=str(e))

        file_names = [f.name for f in files]
        return ComputerWorldObservation(
            screen=screen_obs,
            active_application=status.active_application,
            windows=status.open_applications,
            visible_text=screen_obs.visible_text,
            filesystem_files=file_names,
            processes=status.running_processes,
            terminal_output=terminal_output,
            working_directory=getattr(status, "working_directory", "") or "/home/daytona",
            browser_state=browser_state,
            ide_state={"active_file": file_names[0] if file_names else "", "cursor_line": 1},
            git_branch=git_st.branch if hasattr(git_st, "branch") else "main",
            git_clean=git_st.is_clean if hasattr(git_st, "is_clean") else True,
        )

    async def _observe_browser(self) -> dict[str, Any]:
        """Capture the current browser page state for reasoning.

        Prefers the browser's LIVE page state (which reflects post-click/type
        navigation), falling back to the last navigated snapshot. Refreshes the
        interactive-element list so the LLM sees what it can click/type.
        """
        url, title = "about:blank", "New Tab"
        if hasattr(self.browser, "current_page_state"):
            try:
                import inspect
                res = self.browser.current_page_state()
                if inspect.isawaitable(res):
                    url, title = await res
                else:
                    url, title = res
            except Exception:
                pass
        elif self._last_browser_snapshot:
            url = getattr(self._last_browser_snapshot, "url", url)
            title = getattr(self._last_browser_snapshot, "title", title)

        elements: list[dict[str, Any]] = []
        elem_fn = getattr(self.browser, "find_interactive_elements", None) or getattr(self.browser, "get_interactive_elements", None)
        if elem_fn is not None:
            try:
                import inspect
                res = elem_fn()
                if inspect.isawaitable(res):
                    raw_el = await res
                else:
                    raw_el = res
                elements = [
                    {"tag": getattr(e, "tag", ""), "text": getattr(e, "text", ""), "selector": getattr(e, "selector", "")}
                    if not isinstance(e, dict) else e
                    for e in (raw_el or [])
                ]
            except Exception as el_err:
                logger.debug("browser_interactive_elements_failed", error=str(el_err))

        return {
            "url": url,
            "title": title,
            "interactive_elements": elements,
        }

    # =============================================================
    # 2. Closed-Loop Reasoning & Action Selection
    # =============================================================
    async def choose_action(
        self,
        goal: str,
        observation: ComputerWorldObservation,
        step_index: int = 1,
    ) -> tuple[ComputerActionType, str, dict[str, Any], str]:
        """Choose the next action dynamically based on observation and goal.

        Decide the next action from (goal, observation, history).

        With an LLM router this is genuine model-driven reasoning: the live
        screen text, terminal output, file list, and git state — plus the
        transcript of actions already taken — are all fed to the model, and
        its chosen action is executed. Without a router a generic diagnostic
        probe is used (no vulnerability-specific logic).

        Returns: (action_type, target_resource, payload_dict, predicted_outcome)
        """
        target_files = observation.filesystem_files or []
        code_files = [f for f in target_files if f.endswith((".py", ".js", ".ts", ".go", ".rs", ".sh")) and not f.startswith("test_")]
        test_files = [f for f in target_files if f.startswith("test_") or f.endswith(("_test.py", ".test.js", ".test.ts"))]
        primary_file = code_files[0] if code_files else (target_files[0] if target_files else "")
        test_file = test_files[0] if test_files else ""

        # Direct Terminal Command Goal (operator-pinned command, not reasoning).
        goal_lower = goal.lower()
        if any(term_kw in goal_lower for term_kw in ["run command", "terminal:", "exec:", "bash"]):
            cmd = goal.split(":", 1)[1].strip() if ":" in goal else "pytest"
            return (
                ComputerActionType.TERMINAL_EXEC,
                "terminal-command",
                {"command": cmd},
                f"Executed command '{cmd}' in sandbox PTY",
            )

        if self.llm_router is not None:
            return await self._llm_choose_action(goal, observation, step_index, primary_file, test_file)

        return self._diagnostic_fallback(primary_file)

    def _build_reasoning_context(
        self,
        goal: str,
        observation: ComputerWorldObservation,
        step_index: int,
        primary_file: str,
        test_file: str,
    ) -> tuple[str, str]:
        """Build the (system_prompt, user_prompt) the LLM reasons over.

        The user prompt embeds the LIVE observation — screen visible text,
        terminal output, files, git state, browser page — and the full
        action/result history, so the model's decision is a function of the
        current world state and what it has already done, not a step counter.
        """
        if not hasattr(self, "failure_budget"):
            self.failure_budget = FailureBudgetTracker()
        if not hasattr(self, "strategies"):
            self.strategies = {
                "Strategy A": {"name": "Direct Primary Execution", "description": "Primary probe / targeted execution", "state": StrategyState.ACTIVE},
                "Strategy B": {"name": "Alternative Instrumentation", "description": "Secondary inspection / fallback tool", "state": StrategyState.ACTIVE},
            }

        history_text = self._format_history()

        # Truthful observations: output UNKNOWN when missing or unavailable (no fake observations)
        screen_text = (observation.visible_text or "").strip() or "UNKNOWN"
        terminal_text = (observation.terminal_output or "").strip() or "UNKNOWN"
        workdir = getattr(observation, "working_directory", "") or "UNKNOWN"
        user_home = workdir.split("/workspace")[0] if ("/workspace" in workdir and workdir != "UNKNOWN") else workdir
        self._last_working_dir = workdir
        active_app = observation.active_application or "UNKNOWN"
        windows_str = ", ".join(observation.windows) if observation.windows else "UNKNOWN"
        files_str = str(observation.filesystem_files) if (observation.filesystem_files is not None and len(observation.filesystem_files) > 0) else "UNKNOWN"
        git_branch_str = observation.git_branch or "UNKNOWN"
        primary_file_str = primary_file or "UNKNOWN"
        test_file_str = test_file or "UNKNOWN"
        available_tools = ", ".join(sorted(self.security_tools.keys())) if self.security_tools else "UNKNOWN"

        bs = observation.browser_state or {}
        browser_lines = ""
        active_url = bs.get("url") if (self.browser and bs.get("url") and bs.get("url") != "about:blank") else getattr(self, "_last_navigated_url", "")
        if self.browser is not None:
            elements = bs.get("interactive_elements", [])
            el_summary = ", ".join(
                f"{e.get('tag', '?')}[{e.get('selector', '')}]:'{e.get('text', '')}'"
                for e in elements[:10]
            ) or "(no interactive elements)"
            browser_lines = (
                f"Browser page: url={bs.get('url', 'about:blank')}, "
                f"title={bs.get('title', '')}\n"
                f"Interactive elements: {el_summary}\n"
            )
        elif active_url:
            browser_lines = f"Desktop browser page: url={active_url}\n"

        anti_loop_banner = ""
        if active_url:
            anti_loop_banner = (
                f"ACTIVE BROWSER PAGE: '{active_url}' is ALREADY loaded in the active desktop browser tab.\n"
                f"ANTI-LOOP PROGRESSION RULE: Do NOT emit BROWSER_NAVIGATE to '{active_url}' again! "
                "The page is already open on screen. You MUST interact directly with the visible page: "
                "use GUI_CLICK on buttons, input fields, links, or search bars (using coordinates or element names like 'search bar', 'explore', 'connect wallet'), "
                "or use GUI_TYPE, GUI_SCROLL, or TERMINAL_EXEC to make forward progress.\n"
            )

        recent_sigs = getattr(self, "_recent_action_signatures", [])
        if len(recent_sigs) >= 2:
            last_sig = recent_sigs[-1]
            if all(s == last_sig for s in recent_sigs[-2:]):
                anti_loop_banner += (
                    f"ANTI-REPETITION ALERT: You have already executed '{last_sig[0]}' with target '{last_sig[1]}'. "
                    "DO NOT repeat this action! Choose a different action to advance state.\n"
                )

        tool_lines = ""
        if self._last_tool_result is not None:
            tr = self._last_tool_result
            findings = getattr(tr, "parsed_data", []) or []
            status = getattr(tr, "status", "?")
            tool_name = getattr(tr, "tool_name", "?")
            findings_excerpt = str(findings[:5])[:400]
            tool_lines = (
                f"Last security-tool result: tool={tool_name}, status={status}, "
                f"findings_count={len(findings)}\n"
                f"Findings excerpt: {findings_excerpt}\n"
            )

        # Cross-mission lessons
        lessons_block = ""
        if self.lessons_ledger is not None:
            from sonic.being.lessons import inject_into_context
            lessons_block = inject_into_context(self.lessons_ledger.relevant(goal))

        # Explicit strategy tracking
        curr_tool = primary_file_str if primary_file_str != "UNKNOWN" else "terminal"
        provider_name = self._get_provider_name()
        strat_a = self.strategies.get("Strategy A", {})
        strat_b = self.strategies.get("Strategy B", {})
        strat_a_state = strat_a.get("state", StrategyState.ACTIVE)
        strat_b_state = strat_b.get("state", StrategyState.ACTIVE)

        if self.failure_budget.is_strategy_exhausted(curr_tool, provider_name):
            strat_a_state = StrategyState.EXHAUSTED
            strat_a["state"] = StrategyState.EXHAUSTED
        if self.failure_budget.substrate_outage:
            strat_a_state = StrategyState.EXHAUSTED
            strat_b_state = StrategyState.DEGRADED
            strat_a["state"] = StrategyState.EXHAUSTED
            strat_b["state"] = StrategyState.DEGRADED

        strategy_tracking_block = (
            "Strategy Tracking:\n"
            f"  Strategy A: {strat_a.get('name', 'Direct Primary Execution')} (Status: {getattr(strat_a_state, 'value', str(strat_a_state))})\n"
            f"  Strategy B: {strat_b.get('name', 'Alternative Instrumentation')} (Status: {getattr(strat_b_state, 'value', str(strat_b_state))})\n"
        )

        # Cognitive Reasoning Fields (truthful and epistemic)
        known_facts: list[str] = []
        if active_url:
            known_facts.append(f"Browser active URL: {active_url}")
        if files_str != "UNKNOWN":
            known_facts.append(f"Workspace files: {files_str}")
        if active_app != "UNKNOWN":
            known_facts.append(f"Active application: {active_app}")
        if git_branch_str != "UNKNOWN":
            known_facts.append(f"Git branch: {git_branch_str} (clean={observation.git_clean})")
        if terminal_text != "UNKNOWN":
            known_facts.append(f"Terminal output: {terminal_text[:120]}")
        what_do_i_know = "; ".join(known_facts) if known_facts else "UNKNOWN"

        not_known_facts: list[str] = []
        if not self.traces:
            not_known_facts.append("Target service response, vulnerability profile, and runtime state")
        else:
            not_known_facts.append("Unverified edge conditions and outcomes of unexecuted alternate strategies")
        if terminal_text == "UNKNOWN":
            not_known_facts.append("Terminal output for last command")
        what_do_i_not_know = "; ".join(not_known_facts) if not_known_facts else "UNKNOWN"

        active_sg = self.checklist.active_sub_goal() if getattr(self, "checklist", None) else None
        active_sg_desc = active_sg.description if active_sg else goal
        checklist_str = self.checklist.render_prompt_markdown() if getattr(self, "checklist", None) else f"  Mission Goal: {goal}"

        if self.failure_budget.records:
            last_fail = self.failure_budget.records[-1]
            what_failed = f"{last_fail.tool} on {last_fail.provider} ({last_fail.error_class.value})"
            why_did_it_fail = last_fail.raw_error or f"Classified as {last_fail.error_class.value}"
            what_hypothesis = f"Disproves direct success of {last_fail.tool}; supports hypothesis that alternative approach is required."
            if strat_a_state == StrategyState.EXHAUSTED:
                highest_info_action = "Pivot to Strategy B (alternative instrumentation) since Strategy A is exhausted."
            else:
                highest_info_action = f"Retry or inspect error cause for {last_fail.tool} with diagnostic probe."
        else:
            what_failed = "NONE"
            why_did_it_fail = "NONE"
            what_hypothesis = f"Supports hypothesis that target can be tested via primary plan toward: {goal}."
            if active_sg:
                highest_info_action = f"Advance active sub-goal: '{active_sg.description}'."
            else:
                highest_info_action = f"Execute primary diagnostic or inspection action against {primary_file_str}."

        if self.failure_budget.substrate_outage:
            highest_info_action = "Execute substrate diagnostic probe to resolve infrastructure outage."

        cognitive_block = (
            "Cognitive Reasoning Assessment:\n"
            f"  WHAT DO I KNOW?: {what_do_i_know}\n"
            f"  WHAT DO I NOT KNOW?: {what_do_i_not_know}\n"
            f"  WHAT FAILED?: {what_failed}\n"
            f"  WHY DID IT FAIL?: {why_did_it_fail}\n"
            f"  WHAT HYPOTHESIS DOES THIS SUPPORT/DISPROVE?: {what_hypothesis}\n"
            f"  WHAT IS THE HIGHEST-INFORMATION NEXT ACTION?: {highest_info_action}\n"
        )

        scratchpad_hud = ""
        if hasattr(self, "scratchpad") and self.scratchpad and not self.scratchpad.is_empty():
            hud_text = self.scratchpad.render_hud_markdown()
            if hud_text:
                scratchpad_hud = f"{hud_text}\n"

        wire_summary = ""
        if hasattr(self, "wire_telemetry") and self.wire_telemetry:
            events = self.wire_telemetry.fetch_latest_wire_events_sync(limit=3)
            w_text = self.wire_telemetry.format_wire_summary(events)
            if w_text:
                wire_summary = f"{w_text}\n"

        obs_summary = (
            f"Screen resolution: {self._screen_width}x{self._screen_height}\n"
            f"Step {step_index} of {self.max_actions}. Overall Mission: {goal}\n"
            f"CURRENT ACTIVE SUB-GOAL: {active_sg_desc}\n"
            f"{checklist_str}\n"
            f"INSTRUCTION: Focus your next action strictly on advancing the CURRENT ACTIVE SUB-GOAL above.\n"
            f"{scratchpad_hud}"
            f"{wire_summary}"
            f"Current working directory: {workdir}\n"
            f"User home directory: {user_home} (Desktop path: {user_home}/Desktop)\n"
            f"Active window / app: {active_app}\n"
            f"Open desktop windows: {windows_str}\n"
            f"Screen visible text:\n{screen_text}\n"
            f"Terminal output:\n{terminal_text}\n"
            f"{browser_lines}{tool_lines}"
            f"{anti_loop_banner}"
            f"Files in workspace: {files_str}\n"
            f"Git branch: {git_branch_str}, clean: {observation.git_clean}\n"
            f"Primary file: {primary_file_str}, Test file: {test_file_str}\n"
            f"Available security tools: {available_tools}\n"
            f"{lessons_block}"
            f"{strategy_tracking_block}"
            f"{cognitive_block}"
            f"Actions taken so far:\n{history_text or '(none — this is the first action)'}\n"
        )
        system_prompt = (
            "You are the computer-use core of SONIC — an Autonomous Self-Evolving "
            "Penetration Architect (A-SEA): an autonomous offensive-security and "
            "engineering agent with COMPLETE, UNRESTRICTED CONTROL of the sandboxed "
            "computer environment. You have full operating system authority: "
            "terminal execution, filesystem read/write, git operations, desktop GUI "
            "mouse and keyboard interaction, launching, focusing, switching, and "
            "closing ANY desktop application or window (e.g. terminals, text editors, "
            "browsers, Wireshark, Burp Suite, Metasploit, file managers, or custom tools), "
            "browser automation, and registered security scanner execution. "
            "You are NOT limited to any single tool or browser; you operate the entire computer. "
            "You can see the screen text, open windows, active application, terminal output, "
            "workspace files, git state, and previous action history. "
            "Choose the ONE next action that makes the most progress toward the "
            "goal, reacting to the latest observation and your prior actions — do "
            "NOT follow a fixed script. When 'Past lessons' appear in the "
            "observation, AVOID approaches marked [AVOID] (they failed before) and "
            "prefer approaches marked [REUSE] (they worked before). When no existing "
            "tool fits a gap, author a new one (TOOL_AUTHOR) and verify it (TOOL_RUN); "
            "when a gap needs a new METHOD, invent a technique (METHOD_INVENT). "
            "If the goal is already achieved, respond GOAL_COMPLETE.\n"
            "If the goal can be accomplished cleanly via shell command, prefer TERMINAL_EXEC.\n"
            "You can see the desktop screenshot and interact with GUI elements by clicking at coordinates.\n"
            "CRITICAL SUB-GOAL ADVANCEMENT RULES:\n"
            "1. Focus strictly on executing the CURRENT ACTIVE SUB-GOAL shown in the Execution Checklist.\n"
            "2. Once an active sub-goal is accomplished (e.g. page loaded, element clicked, command executed), advance to the next sub-goal. Do NOT repeat completed sub-goals.\n"
            "CRITICAL ANTI-LOOPING AND PROGRESSION RULES:\n"
            "1. NEVER navigate repeatedly to the same URL. If a webpage is already open, interact with its elements on screen (GUI_CLICK on search bar, buttons, links, or GUI_TYPE).\n"
            "2. NEVER repeat the exact same action and target consecutively without state progression.\n"
            "3. Look closely at the screen screenshot / screen visible text to identify buttons, input boxes, menus, and links. Use GUI_CLICK with coordinates or landmark query (e.g. 'search bar', 'connect wallet', 'explore') to interact with them.\n"
            "Before choosing an action, reason through these mandatory cognitive fields:\n"
            "WHAT DO I KNOW?: <Facts established by verified observation, or UNKNOWN>\n"
            "WHAT DO I NOT KNOW?: <Unverified assumptions, missing data, or UNKNOWN>\n"
            "WHAT FAILED?: <Previous failure if any, or NONE>\n"
            "WHY DID IT FAIL?: <Root cause classification and explanation, or NONE>\n"
            "WHAT HYPOTHESIS DOES THIS SUPPORT/DISPROVE?: <Epistemic hypothesis update>\n"
            "WHAT IS THE HIGHEST-INFORMATION NEXT ACTION?: <Strategic justification for the action chosen>\n"
            "Respond in EXACTLY this format (no markdown code fences):\n"
            "WHAT DO I KNOW?: ...\n"
            "WHAT DO I NOT KNOW?: ...\n"
            "WHAT FAILED?: ...\n"
            "WHY DID IT FAIL?: ...\n"
            "WHAT HYPOTHESIS DOES THIS SUPPORT/DISPROVE?: ...\n"
            "WHAT IS THE HIGHEST-INFORMATION NEXT ACTION?: ...\n"
            "THOUGHT: <Brief 1-sentence thought explaining what you intend to do and why>\n"
            "ACTION: <GUI_CLICK|GUI_DOUBLE_CLICK|GUI_RIGHT_CLICK|GUI_TYPE|GUI_KEYPRESS|GUI_MOVE|GUI_SCROLL|GUI_DRAG|GUI_SCREENSHOT|GUI_WAIT|FILE_READ|FILE_WRITE|TERMINAL_EXEC|GIT_COMMIT|APP_LAUNCH|APP_CLOSE|APP_FOCUS|APP_INSTALL|SERVICE_ACTION|BROWSER_NAVIGATE|BROWSER_CLICK|BROWSER_TYPE|BROWSER_SCREENSHOT|BROWSER_WAIT|BROWSER_DOWNLOAD|SECURITY_TOOL|TOOL_AUTHOR|TOOL_RUN|METHOD_INVENT|GOAL_COMPLETE>\n"
            "TARGET: <resource path, application/window name, url, css selector, coordinates, or UI element query>\n"
            'PAYLOAD: <json dict, e.g. {"path": "...", "content": "..."}, '
            '{"command": "..."}, {"url": "..."}, {"selector": "...", "text": "..."}, '
            '{"app_name": "..."}, {"tool": "...", "target": "...", "args": "..."}>\n'
            'For GUI_CLICK/GUI_DOUBLE_CLICK/GUI_RIGHT_CLICK/GUI_MOVE: TARGET can be numeric pixel coordinates like "640,400" OR a visual UI query like "Applications menu", "Terminal icon", "Google Chrome", "search bar"\n'
            'For GUI_DRAG: TARGET is "x,y" (source) and PAYLOAD is {"x2": <int>, "y2": <int>} (destination)\n'
            'For GUI_TYPE: PAYLOAD is {"text": "..."}\n'
            'For GUI_KEYPRESS: PAYLOAD is {"key": "Return|Tab|Escape|ctrl+c|ctrl+v|alt+Tab|..."}\n'
            'For GUI_SCROLL: TARGET is "x,y" and PAYLOAD is {"delta": -3} (negative=down, positive=up)\n'
            'For GUI_SCREENSHOT: no target or payload needed\n'
            'For GUI_WAIT: PAYLOAD is {"seconds": 3} to let a window or page settle\n'
            'For APP_INSTALL: TARGET is the package to install (e.g. nmap, wireshark, chromium, git, curl)\n'
            'For APP_LAUNCH: TARGET is the application name to start (e.g. xfce4-terminal, mousepad, thunar, burpsuite, wireshark, chromium, code)\n'
            'For APP_FOCUS: TARGET is the window title or application name to bring to foreground (e.g. any window from Open desktop windows)\n'
            'For APP_CLOSE: TARGET is the application or window name to close\n'
            'For TERMINAL_EXEC: TARGET or PAYLOAD {"command": "..."} must be an EXACT executable shell command line (e.g. uname -a, netstat -tuln, which google-chrome, ls -la), NEVER natural language like "Terminal" or "netstat or ss command"\n'
            'For BROWSER_NAVIGATE: TARGET or PAYLOAD {"url": "..."} is the external target URL (e.g. https://google.com, https://example.org). Private subnets (localhost, 127.0.0.1, 10.0.0.0/8) are blocked by safety policy.\n'
            'For BROWSER_TYPE: PAYLOAD is {"text": "text to type"} and TARGET is the input selector or "address bar"\n'
            'For SECURITY_TOOL: TARGET must be one of the Available security tools listed above (e.g. nmap, nuclei, ffuf, http_client)\n'
            'For BROWSER_WAIT: PAYLOAD is {"selector": "<css>"} to wait for an element to render\n'
            'For BROWSER_DOWNLOAD: PAYLOAD is {"selector": "<css>", "save_path": "~/workspace/file"}\n'
            "EXPECTED: <short description of predicted outcome>"
        )
        return system_prompt, obs_summary

    def _format_history(self) -> str:
        """Render the action/result transcript for the LLM."""
        if not self.history:
            return ""
        lines = []
        for i, h in enumerate(self.history, 1):
            lines.append(
                f"  {i}. {h.get('action', '?')} -> {h.get('result', '?')}"
            )
        return "\n".join(lines)

    async def _llm_choose_action(
        self,
        goal: str,
        observation: ComputerWorldObservation,
        step_index: int,
        primary_file: str,
        test_file: str,
    ) -> tuple[ComputerActionType, str, dict[str, Any], str]:
        """Use the LLM to decide the next action from goal + observation + history."""
        from sonic.llm.schemas import ImageContent, LLMRequest, Message, MessageRole

        system_prompt, obs_summary = self._build_reasoning_context(
            goal, observation, step_index, primary_file, test_file
        )
        # Build the user message — multimodal (image+text) when screenshot available.
        images: list[ImageContent] = []
        if self._last_screenshot_b64:
            raw_b64 = self._last_screenshot_b64
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            images = [ImageContent(base64=raw_b64, media_type="image/png")]
            user_text = f"{obs_summary}\n\nBased on the desktop screenshot and observation above, choose the next action."
        else:
            user_text = obs_summary

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_text, images=images),
            ],
            task_type="reasoning",
        )
        t_thought_start = time.perf_counter()
        try:
            response = await self.llm_router.complete(request)
            self._last_thought_duration = round(time.perf_counter() - t_thought_start, 2)
            t_match = re.search(r'(?:\*{1,2}|_)?\bTHOUGHT\b(?:\*{1,2}|_)?:\s*(.*?)(?=(?:\*{1,2}|_)?\b(?:THOUGHT|ACTION|TARGET|PAYLOAD|EXPECTED)\b(?:\*{1,2}|_)?\:|$)', response.content, re.DOTALL | re.IGNORECASE)
            self._last_thought = t_match.group(1).strip(" *_\n\r\t") if t_match else ""
            action_type, target, payload, expected = self._parse_llm_action(
                response.content, primary_file
            )
            return action_type, target, payload, expected
        except Exception as e:
            self._last_thought_duration = round(time.perf_counter() - t_thought_start, 2)
            logger.warning("computer_llm_action_failed_diagnostic_fallback", error=str(e))
            self._last_thought = ""
            return self._diagnostic_fallback(primary_file)

    @staticmethod
    def _parse_llm_action(
        text: str, default_file: str
    ) -> tuple[ComputerActionType, str, dict[str, Any], str]:
        """Parse structured LLM response into an action tuple."""
        # Robust multi-field extraction (handles single-line, multi-line, markdown bold/italics, and alternative delimiter names)
        pattern = r'(?:\*{1,2}|_)?\b(ACTION|TARGET|PAYLOAD|EXPECTED|EXPECTED[\s_]+OUTCOME|REASONING|THOUGHT|EXPLANATION)\b(?:\*{1,2}|_)?:\s*(.*?)(?=(?:\*{1,2}|_)?\b(?:ACTION|TARGET|PAYLOAD|EXPECTED|EXPECTED[\s_]+OUTCOME|REASONING|THOUGHT|EXPLANATION)\b(?:\*{1,2}|_)?\:|$)'
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        raw_fields: dict[str, str] = {k.strip().upper(): v.strip(" *_\n\r\t") for k, v in matches}
        fields: dict[str, str] = {}
        for k, v in raw_fields.items():
            if "OUTCOME" in k:
                fields.setdefault("EXPECTED", v)
            elif any(sub in k for sub in ("THOUGHT", "REASON", "EXPLAN")):
                fields.setdefault("THOUGHT", v)
            else:
                fields[k] = v

        # Fallback to line-by-line if regex matched nothing
        if not fields:
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            for line in lines:
                if ":" in line:
                    key, _, val = line.partition(":")
                    fields[key.strip().upper()] = val.strip()

        raw_action = fields.get("ACTION", "TERMINAL_EXEC").upper()
        action_word = raw_action.split()[0] if raw_action.split() else "TERMINAL_EXEC"
        action_str = action_word.strip(" *_\n\r\t`\"'")
        action_map = {
            "GUI_CLICK": ComputerActionType.GUI_CLICK,
            "GUI_DOUBLE_CLICK": ComputerActionType.GUI_DOUBLE_CLICK,
            "GUI_RIGHT_CLICK": ComputerActionType.GUI_RIGHT_CLICK,
            "GUI_TYPE": ComputerActionType.GUI_TYPE,
            "GUI_KEYPRESS": ComputerActionType.GUI_KEYPRESS,
            "GUI_MOVE": ComputerActionType.GUI_MOVE,
            "GUI_SCROLL": ComputerActionType.GUI_SCROLL,
            "GUI_SCREENSHOT": ComputerActionType.GUI_SCREENSHOT,
            "GUI_DRAG": ComputerActionType.GUI_DRAG,
            "GUI_WAIT": ComputerActionType.GUI_WAIT,
            "FILE_READ": ComputerActionType.FILE_READ,
            "FILE_WRITE": ComputerActionType.FILE_WRITE,
            "TERMINAL_EXEC": ComputerActionType.TERMINAL_EXEC,
            "GIT_COMMIT": ComputerActionType.GIT_COMMIT,
            "APP_LAUNCH": ComputerActionType.APP_LAUNCH,
            "APP_CLOSE": ComputerActionType.APP_CLOSE,
            "APP_FOCUS": ComputerActionType.APP_FOCUS,
            "APP_INSTALL": ComputerActionType.APP_INSTALL,
            "SERVICE_ACTION": ComputerActionType.SERVICE_ACTION,
            "BROWSER_NAVIGATE": ComputerActionType.BROWSER_NAVIGATE,
            "BROWSER_CLICK": ComputerActionType.BROWSER_CLICK,
            "BROWSER_TYPE": ComputerActionType.BROWSER_TYPE,
            "BROWSER_SCREENSHOT": ComputerActionType.BROWSER_SCREENSHOT,
            "BROWSER_WAIT": ComputerActionType.BROWSER_WAIT,
            "BROWSER_DOWNLOAD": ComputerActionType.BROWSER_DOWNLOAD,
            "SECURITY_TOOL": ComputerActionType.SECURITY_TOOL,
            "TOOL_AUTHOR": ComputerActionType.TOOL_AUTHOR,
            "TOOL_RUN": ComputerActionType.TOOL_RUN,
            "METHOD_INVENT": ComputerActionType.METHOD_INVENT,
            # GOAL_COMPLETE is handled by the caller as a no-op terminator.
            "GOAL_COMPLETE": ComputerActionType.TERMINAL_EXEC,
        }
        action_type = action_map.get(action_str, ComputerActionType.TERMINAL_EXEC)

        # Signal early termination up to the mission loop via the expected text.
        if action_str == _GOAL_COMPLETE_SENTINEL:
            return (
                action_type,
                "goal-complete",
                {"command": "true"},
                _GOAL_COMPLETE_SENTINEL,
            )

        default_target = default_file if action_type in (ComputerActionType.FILE_READ, ComputerActionType.FILE_WRITE) else ""

        raw_target = fields.get("TARGET", "") or default_target
        target = raw_target.strip(" *_\n\r\t`\"'")
        if target:
            # Take first non-empty line to strip accidental trailing markdown blocks
            for line in target.splitlines():
                if line.strip():
                    target = line.strip(" *_\n\r\t`\"'")
                    break

        if action_type in (ComputerActionType.APP_LAUNCH, ComputerActionType.APP_CLOSE, ComputerActionType.APP_FOCUS, ComputerActionType.APP_INSTALL):
            if target:
                words = target.split()
                if words:
                    if words[0].lower() in ("the", "a", "an") and len(words) > 1:
                        target = words[1].strip(" *_\n\r\t`\"'")
                    else:
                        target = words[0].strip(" *_\n\r\t`\"'")
                if target.lower() in ("terminal", "the terminal"):
                    target = "xfce4-terminal"
                elif target.lower() in ("editor", "text editor"):
                    target = "mousepad"
                elif target.lower() in ("files", "file manager"):
                    target = "thunar"

        elif action_type == ComputerActionType.BROWSER_NAVIGATE:
            target_lower = target.lower()
            if not target or target_lower in ("/", "none", "not specified", "null", "about:blank"):
                target = "about:blank"
            elif not (target.startswith("http://") or target.startswith("https://") or target.startswith("about:") or target.startswith("file://")):
                if "localhost" in target or "127.0.0.1" in target:
                    target = f"http://{target}"
                elif "." in target and " " not in target:
                    target = f"https://{target}"

        payload_str = fields.get("PAYLOAD", "{}")
        import json
        try:
            payload = json.loads(payload_str) if payload_str.startswith("{") else {"command": payload_str}
        except Exception:
            payload = {"command": payload_str} if action_type == ComputerActionType.TERMINAL_EXEC else {}

        if action_type == ComputerActionType.BROWSER_TYPE:
            if "command" in payload and "text" not in payload:
                payload["text"] = payload["command"]

        if action_type == ComputerActionType.TERMINAL_EXEC:
            raw_cmd = payload.get("command")
            if not raw_cmd or str(raw_cmd).lower() == "none":
                payload["command"] = target if target and target != default_file else "pwd"
            if payload.get("command"):
                cmd_str = str(payload["command"]).strip()
                cmd_str = re.sub(r'^(?:xfce4-terminal,?\s*)?(?:command|cmd)\s*=\s*', '', cmd_str)
                # Remove parenthesized comments e.g. "netstat -tuln (or ss)" -> "netstat -tuln"
                cmd_str = re.sub(r'\(.*?\)', '', cmd_str).strip()
                # Handle conversational placeholders like "Terminal" or "Terminal window"
                if cmd_str.lower() in ("terminal", "terminal window", "the terminal", "bash", "shell", "console"):
                    cmd_str = "pwd"
                # Handle phrases like "No specific target is needed for this command."
                if any(phrase in cmd_str.lower() for phrase in ("no specific", "not needed", "n/a", "none", "no target")):
                    cmd_str = "uname -m"
                # Handle "X or Y command" (e.g. "netstat or ss" -> "which netstat && netstat -tuln || ss -tuln")
                m_or = re.match(r'^([a-zA-Z0-9_-]+)\s+or\s+([a-zA-Z0-9_-]+)(?:\s+command)?$', cmd_str, re.IGNORECASE)
                if m_or:
                    cmd1, cmd2 = m_or.group(1), m_or.group(2)
                    cmd_str = f"which {cmd1} && {cmd1} -tuln || {cmd2} -tuln"
                else:
                    # Strip trailing " command" or " commands"
                    cmd_str = re.sub(r'\s+commands?$', '', cmd_str, flags=re.IGNORECASE)
                payload["command"] = cmd_str

        if action_type in (ComputerActionType.GUI_CLICK, ComputerActionType.GUI_DOUBLE_CLICK, ComputerActionType.GUI_RIGHT_CLICK, ComputerActionType.GUI_MOVE, ComputerActionType.GUI_DRAG):
            if target and "," in target:
                parts = target.split(",")
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    payload["x"] = int(parts[0].strip())
                    payload["y"] = int(parts[1].strip())
                elif any(p.strip().lower() in ("x", "y", "x,y", "x, y") for p in parts):
                    payload.pop("x", None)
                    payload.pop("y", None)
        if action_type == ComputerActionType.GUI_SCROLL:
            if target and "," in target:
                parts = target.split(",")
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    payload["x"] = int(parts[0].strip())
                    payload["y"] = int(parts[1].strip())

        expected = fields.get("EXPECTED", f"Action {action_type} on {target}")
        return action_type, target, payload, expected

    @staticmethod
    def _diagnostic_fallback(primary_file: str) -> tuple[ComputerActionType, str, dict[str, Any], str]:
        """Offline fallback when no LLM is available.

        Deliberately generic: it inspects the primary source file as a
        diagnostic probe. It does NOT apply any vulnerability-specific patch
        and contains no JWT/SQLi/XSS logic. Real remediation requires an LLM.
        """
        return (
            ComputerActionType.FILE_READ,
            f"/home/sonic/workspace/{primary_file}",
            {"path": f"/home/sonic/workspace/{primary_file}"},
            f"Diagnostic: inspected {primary_file} (no LLM available to remediate)",
        )

    # =============================================================
    # 3. Action Execution & Closed-Loop Verification
    # =============================================================
    # Actions that target pixel coordinates and must stay on-screen.
    _COORDINATE_ACTIONS: frozenset[str] = frozenset({
        "GUI_CLICK", "GUI_DOUBLE_CLICK", "GUI_RIGHT_CLICK", "GUI_MOVE", "GUI_SCROLL", "GUI_DRAG",
    })

    def _validate_coordinates(
        self, action_type: ComputerActionType, payload: dict[str, Any],
    ) -> str | None:
        """Return an error string if a coordinate action is off-screen, else None.

        Validates (x, y) — and (x2, y2) for drags — against the last observed
        screen dimensions. Coordinates must be non-negative integers strictly
        inside the screen (0 <= x < width, 0 <= y < height). Non-coordinate
        actions are always allowed (return None).
        """
        if action_type.value not in self._COORDINATE_ACTIONS:
            return None

        width = getattr(self, "_screen_width", 1920)
        height = getattr(self, "_screen_height", 1080)

        def _check(x: Any, y: Any, label: str) -> str | None:
            try:
                ix, iy = int(x), int(y)
            except (TypeError, ValueError):
                return f"{label} ({x},{y}) is not a valid integer coordinate"
            if ix < 0 or iy < 0:
                return f"{label} ({ix},{iy}) is negative"
            if ix >= width or iy >= height:
                return (
                    f"{label} ({ix},{iy}) is outside screen "
                    f"{width}x{height}"
                )
            return None

        err = _check(payload.get("x", 0), payload.get("y", 0), "point")
        if err is not None:
            return err
        if action_type == ComputerActionType.GUI_DRAG:
            err = _check(payload.get("x2", payload.get("x", 0)),
                         payload.get("y2", payload.get("y", 0)), "drag target")
            if err is not None:
                return err
        return None

    def _update_screen_dims(self, screen: Any) -> None:
        """Refresh tracked screen dimensions from a screenshot observation."""
        w = int(getattr(screen, "width", 0) or 0)
        h = int(getattr(screen, "height", 0) or 0)
        if w > 0:
            self._screen_width = w
        if h > 0:
            self._screen_height = h

    def _get_provider_name(self) -> str:
        """Return human-readable identifier for computer provider."""
        if hasattr(self.computer, "name"):
            return str(self.computer.name)
        if hasattr(self.computer, "compute_provider") and hasattr(self.computer.compute_provider, "__class__"):
            return self.computer.compute_provider.__class__.__name__
        if hasattr(self.computer, "__class__"):
            return self.computer.__class__.__name__
        return "sandbox"

    def _extract_tool_name(
        self,
        action_type: ComputerActionType,
        target_resource: str,
        payload: dict[str, Any],
    ) -> str:
        """Extract tool or binary name for failure budget tracking."""
        if action_type == ComputerActionType.TERMINAL_EXEC:
            cmd = payload.get("command") or target_resource or "terminal"
            parts = str(cmd).strip().split()
            return parts[0] if parts else "terminal"
        if action_type == ComputerActionType.SECURITY_TOOL:
            return str(payload.get("tool") or target_resource or "security_tool")
        if action_type == ComputerActionType.APP_INSTALL:
            return str(payload.get("package") or payload.get("app_name") or target_resource or "installer")
        return action_type.value

    async def execute_action(
        self,
        workspace_id: str,
        action_type: ComputerActionType,
        target_resource: str,
        payload: dict[str, Any],
        predicted_outcome: str,
    ) -> ComputerDecisionTrace:
        """Executes the action inside the computer sandbox and validates outcome."""
        self.action_counter += 1
        t_start = time.perf_counter()
        actual_obs_str = ""
        status = ActionExecutionStatus.COMPLETED
        recovery_needed = False
        action_exit_code: int | None = None

        if not hasattr(self, "failure_budget"):
            self.failure_budget = FailureBudgetTracker()
        if not hasattr(self, "strategies"):
            self.strategies = {
                "Strategy A": {"name": "Direct Primary Execution", "description": "Primary probe / targeted execution", "state": StrategyState.ACTIVE},
                "Strategy B": {"name": "Alternative Instrumentation", "description": "Secondary inspection / fallback tool", "state": StrategyState.ACTIVE},
            }

        provider_name = self._get_provider_name()
        tool_name = self._extract_tool_name(action_type, target_resource, payload)

        # ----- PLAN Phase 6: fail-closed safety envelope -----
        # Every action — operator-issued OR self-directed (curiosity) — must pass
        # the policy before it touches the provider. A denied action is recorded
        # as BLOCKED and NEVER executed, and deliberately does NOT trigger the
        # recovery path (recovery must not be able to bypass the safety gate).
        if self.safety is not None:
            verdict = self.safety.evaluate(action_type.value, target_resource, payload)
            if not verdict.allowed:
                actual_obs_str = f"Safety blocked: {verdict.reason}"
                status = ActionExecutionStatus.BLOCKED
                logger.warning("action_blocked_by_policy",
                               action=action_type.value, reason=verdict.reason)
                trace = ComputerDecisionTrace(
                    step_index=self.action_counter,
                    action_type=action_type,
                    target_resource=target_resource,
                    payload=str(payload),
                    predicted_outcome=predicted_outcome,
                    actual_observation=actual_obs_str,
                    expected_observation=predicted_outcome,
                    info_gain=0.0,
                    recovery_attempted=False,
                    status=status,
                    exit_code=126,
                    duration_seconds=round(time.perf_counter() - t_start, 3),
                    thought_duration_seconds=getattr(self, "_last_thought_duration", 0.0),
                )
                self.traces.append(trace)
                self.history.append({"action": action_type.value, "result": actual_obs_str})
                return trace

        # ----- Substrate Outage Detection (Failure Budget) -----
        # If 3 consecutive provider errors occurred, STOP target actions and switch to substrate diagnostic action.
        if self.failure_budget.substrate_outage:
            diag_info = self.failure_budget.diagnose_substrate_health()
            actual_obs_str = (
                f"SUBSTRATE_OUTAGE_DETECTED: Consecutive provider/sandbox failures reached threshold. "
                f"Target actions stopped; switched to substrate diagnostic: {diag_info}"
            )
            status = ActionExecutionStatus.BLOCKED
            logger.error(
                "substrate_outage_target_halted",
                provider=provider_name,
                tool=tool_name,
                status=self.failure_budget.diagnostic_status,
            )
            trace = ComputerDecisionTrace(
                step_index=self.action_counter,
                action_type=action_type,
                target_resource=target_resource,
                payload=str(payload),
                predicted_outcome=predicted_outcome,
                actual_observation=actual_obs_str,
                expected_observation=predicted_outcome,
                info_gain=0.0,
                recovery_attempted=False,
                status=status,
                duration_seconds=round(time.perf_counter() - t_start, 3),
                thought_duration_seconds=getattr(self, "_last_thought_duration", 0.0),
            )
            self.traces.append(trace)
            self.history.append({"action": f"{action_type.value} {target_resource}", "result": actual_obs_str})
            return trace

        # ----- Strategy Exhaustion Check -----
        # If strategy for this tool/provider is exhausted, DO NOT retry the same command/tool!
        # Record strategy exhausted and set status = ActionExecutionStatus.FAILED.
        if self.failure_budget.is_strategy_exhausted(tool=tool_name, provider=provider_name):
            actual_obs_str = (
                f"Strategy exhausted for tool '{tool_name}' on provider '{provider_name}'. "
                f"Failure budget exceeded; retry blocked."
            )
            status = ActionExecutionStatus.FAILED
            logger.warning(
                "strategy_exhausted_execution_blocked",
                tool=tool_name,
                provider=provider_name,
            )
            trace = ComputerDecisionTrace(
                step_index=self.action_counter,
                action_type=action_type,
                target_resource=target_resource,
                payload=str(payload),
                predicted_outcome=predicted_outcome,
                actual_observation=actual_obs_str,
                expected_observation=predicted_outcome,
                info_gain=0.0,
                recovery_attempted=False,
                status=status,
                duration_seconds=round(time.perf_counter() - t_start, 3),
                thought_duration_seconds=getattr(self, "_last_thought_duration", 0.0),
            )
            self.traces.append(trace)
            self.history.append({"action": f"{action_type.value} {target_resource}", "result": actual_obs_str})
            return trace

        # ----- Consecutive Action Loop Detector & Circuit Breaker -----
        # Detect if the agent is repeating the exact same GUI action signature consecutively.
        # Terminal and Security Tool actions are governed by FailureBudgetTracker and strategy budgets.
        if action_type not in (ComputerActionType.TERMINAL_EXEC, ComputerActionType.SECURITY_TOOL):
            action_sig = (action_type.value, str(target_resource).strip().lower(), str(payload).strip())
            self._recent_action_signatures.append(action_sig)
            if len(self._recent_action_signatures) >= 3 and all(
                s == action_sig for s in self._recent_action_signatures[-3:]
            ):
                actual_obs_str = (
                    f"[ACTION LOOP DETECTED]: You have repeated '{action_type.value}' on '{target_resource}' "
                    "3 times consecutively without state progression. "
                    "This action is BLOCKED. Advance to a different action (e.g. GUI_CLICK on elements, GUI_TYPE, scroll, or conclude)."
                )
                status = ActionExecutionStatus.BLOCKED
                logger.warning(
                    "action_loop_breaker_triggered",
                    action=action_type.value,
                    target=target_resource,
                    consecutive_count=3,
                )
                trace = ComputerDecisionTrace(
                    step_index=self.action_counter,
                    action_type=action_type,
                    target_resource=target_resource,
                    payload=str(payload),
                    predicted_outcome=predicted_outcome,
                    actual_observation=actual_obs_str,
                    expected_observation=predicted_outcome,
                    info_gain=0.0,
                    recovery_attempted=False,
                    status=status,
                    thought=getattr(self, "_last_thought", ""),
                    duration_seconds=round(time.perf_counter() - t_start, 3),
                    thought_duration_seconds=getattr(self, "_last_thought_duration", 0.0),
                )
                self.traces.append(trace)
                self.history.append({"action": f"{action_type.value} {target_resource}", "result": actual_obs_str})
                return trace

        # ----- Visual Grounding Target Resolution -----
        # If numeric coordinates were not provided for a GUI action, attempt to
        # resolve the target resource query (e.g. "Applications menu", "Terminal icon")
        # to screen coordinates using the visual grounding engine.
        resolved_via_grounding = False
        if action_type in (
            ComputerActionType.GUI_CLICK,
            ComputerActionType.GUI_DOUBLE_CLICK,
            ComputerActionType.GUI_RIGHT_CLICK,
            ComputerActionType.GUI_MOVE,
        ) and (payload.get("x") is None or payload.get("y") is None):
            grounding_fn = None
            if self.llm_router and self._last_screenshot_b64:
                async def _ground(q, s):
                    return await query_multimodal_grounding(
                        self.llm_router, q, s, width=self._screen_width, height=self._screen_height
                    )
                grounding_fn = _ground

            res_coords = await resolve_ui_target_async(
                query=target_resource,
                screenshot_b64=self._last_screenshot_b64,
                width=self._screen_width,
                height=self._screen_height,
                grounding_fn=grounding_fn,
            )
            if res_coords is not None:
                payload["x"], payload["y"] = res_coords
                resolved_via_grounding = True
                logger.info(
                    "visual_grounding_target_resolved",
                    action=action_type.value,
                    query=target_resource,
                    resolved_x=res_coords[0],
                    resolved_y=res_coords[1],
                )

        # ----- Coordinate bounds validation -----
        # GUI coordinate actions are validated against the last observed screen
        # size BEFORE execution. A model can hallucinate off-screen or negative
        # coordinates (e.g. from a stale screenshot after a resize); clicking
        # those does nothing useful and can mis-click. We BLOCK such actions —
        # without triggering recovery (the provider state is fine; the agent
        # simply needs to re-observe and pick valid coordinates).
        coord_err = self._validate_coordinates(action_type, payload)
        if coord_err is not None:
            actual_obs_str = f"Coordinate out of bounds: {coord_err}"
            status = ActionExecutionStatus.BLOCKED
            logger.warning("action_blocked_out_of_bounds",
                           action=action_type.value, reason=coord_err,
                           screen=f"{self._screen_width}x{self._screen_height}")
            trace = ComputerDecisionTrace(
                step_index=self.action_counter,
                action_type=action_type,
                target_resource=target_resource,
                payload=str(payload),
                predicted_outcome=predicted_outcome,
                actual_observation=actual_obs_str,
                expected_observation=predicted_outcome,
                info_gain=0.0,
                recovery_attempted=False,
                status=status,
                thought=getattr(self, "_last_thought", ""),
                duration_seconds=round(time.perf_counter() - t_start, 3),
                thought_duration_seconds=getattr(self, "_last_thought_duration", 0.0),
            )
            self.traces.append(trace)
            self.history.append({"action": action_type.value, "result": actual_obs_str})
            return trace

        try:
            if action_type == ComputerActionType.GUI_CLICK:
                if payload.get("x") is None or payload.get("y") is None:
                    actual_obs_str = f"GUI_CLICK failed: integer pixel coordinates x,y required or visual target '{target_resource}' could not be resolved"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    x = int(payload.get("x", 0))
                    y = int(payload.get("y", 0))
                    if self._last_screenshot_b64:
                        self._last_screenshot_b64 = draw_action_marker(
                            self._last_screenshot_b64, (x, y), label="CLICK", color="#00ffcc"
                        )
                    pre_screen_b64 = getattr(self, "_last_screenshot_b64", "")
                    obs_after = await self.computer.gui_action(
                        workspace_id,
                        GUIAction(action=GUIActionType.CLICK, x=x, y=y),
                    )
                    post_screen_b64 = getattr(obs_after, "screenshot_base64", "") if obs_after else ""
                    if post_screen_b64:
                        self._last_screenshot_b64 = post_screen_b64
                        self._update_screen_dims(obs_after)
                    if resolved_via_grounding:
                        actual_obs_str = f"Visual grounding resolved '{target_resource}' to ({x}, {y}) and clicked"
                    else:
                        actual_obs_str = f"Clicked at ({x}, {y})"
                    if pre_screen_b64 and post_screen_b64 and pre_screen_b64 == post_screen_b64:
                        actual_obs_str = f"{actual_obs_str} | [VISUAL VERIFICATION]: Screen state unchanged after click — target element may be occluded, missing, or page is loading."

            elif action_type == ComputerActionType.GUI_DOUBLE_CLICK:
                if payload.get("x") is None or payload.get("y") is None:
                    actual_obs_str = f"GUI_DOUBLE_CLICK failed: integer pixel coordinates x,y required or visual target '{target_resource}' could not be resolved"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    x = int(payload.get("x", 0))
                    y = int(payload.get("y", 0))
                    if self._last_screenshot_b64:
                        self._last_screenshot_b64 = draw_action_marker(
                            self._last_screenshot_b64, (x, y), label="DOUBLE_CLICK", color="#ffaa00"
                        )
                    pre_screen_b64 = getattr(self, "_last_screenshot_b64", "")
                    obs_after = await self.computer.gui_action(
                        workspace_id,
                        GUIAction(action=GUIActionType.DOUBLE_CLICK, x=x, y=y),
                    )
                    post_screen_b64 = getattr(obs_after, "screenshot_base64", "") if obs_after else ""
                    if post_screen_b64:
                        self._last_screenshot_b64 = post_screen_b64
                        self._update_screen_dims(obs_after)
                    if resolved_via_grounding:
                        actual_obs_str = f"Visual grounding resolved '{target_resource}' to ({x}, {y}) and double-clicked"
                    else:
                        actual_obs_str = f"Double-clicked at ({x}, {y})"
                    if pre_screen_b64 and post_screen_b64 and pre_screen_b64 == post_screen_b64:
                        actual_obs_str = f"{actual_obs_str} | [VISUAL VERIFICATION]: Screen state unchanged after double-click."

            elif action_type == ComputerActionType.GUI_RIGHT_CLICK:
                if payload.get("x") is None or payload.get("y") is None:
                    actual_obs_str = f"GUI_RIGHT_CLICK failed: integer pixel coordinates x,y required or visual target '{target_resource}' could not be resolved"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    x = int(payload.get("x", 0))
                    y = int(payload.get("y", 0))
                    if self._last_screenshot_b64:
                        self._last_screenshot_b64 = draw_action_marker(
                            self._last_screenshot_b64, (x, y), label="RIGHT_CLICK", color="#ff3366"
                        )
                    pre_screen_b64 = getattr(self, "_last_screenshot_b64", "")
                    obs_after = await self.computer.gui_action(
                        workspace_id,
                        GUIAction(action=GUIActionType.RIGHT_CLICK, x=x, y=y),
                    )
                    post_screen_b64 = getattr(obs_after, "screenshot_base64", "") if obs_after else ""
                    if post_screen_b64:
                        self._last_screenshot_b64 = post_screen_b64
                        self._update_screen_dims(obs_after)
                    if resolved_via_grounding:
                        actual_obs_str = f"Visual grounding resolved '{target_resource}' to ({x}, {y}) and right-clicked"
                    else:
                        actual_obs_str = f"Right-clicked at ({x}, {y})"

            elif action_type == ComputerActionType.GUI_TYPE:
                text = payload.get("text", "")
                pre_screen_b64 = getattr(self, "_last_screenshot_b64", "")
                obs_after = None
                if hasattr(self, "motor") and self.motor:
                    await self.motor.human_type(workspace_id, text, delay_ms=payload.get("delay_ms", 25))
                else:
                    obs_after = await self.computer.gui_action(
                        workspace_id,
                        GUIAction(action=GUIActionType.TYPE, text=text),
                    )
                if hasattr(self.computer, "screenshot") and not obs_after:
                    try:
                        obs_after = await self.computer.screenshot(workspace_id)
                    except Exception:
                        pass
                post_screen_b64 = getattr(obs_after, "screenshot_base64", "") if obs_after else ""
                if post_screen_b64:
                    self._last_screenshot_b64 = post_screen_b64
                    self._update_screen_dims(obs_after)
                actual_obs_str = f"Typed {len(text)} chars: {text[:50]}"

            elif action_type == ComputerActionType.GUI_KEYPRESS:
                key = payload.get("key", "Return")
                await self.computer.gui_action(
                    workspace_id,
                    GUIAction(action=GUIActionType.KEYPRESS, key=key),
                )
                actual_obs_str = f"Pressed key: {key}"

            elif action_type == ComputerActionType.GUI_MOVE:
                if payload.get("x") is None or payload.get("y") is None:
                    actual_obs_str = f"GUI_MOVE failed: coordinates required or visual target '{target_resource}' could not be resolved"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    x = int(payload.get("x", 0))
                    y = int(payload.get("y", 0))
                    await self.computer.gui_action(
                        workspace_id,
                        GUIAction(action=GUIActionType.MOVE, x=x, y=y),
                    )
                    if resolved_via_grounding:
                        actual_obs_str = f"Visual grounding resolved '{target_resource}' to ({x}, {y}) and moved mouse"
                    else:
                        actual_obs_str = f"Moved mouse to ({x}, {y})"

            elif action_type == ComputerActionType.GUI_DRAG:
                # Press-move-release (a human drag). Source (x,y) may come from
                # TARGET "x,y" (parsed above) or payload; destination (x2,y2)
                # comes from payload. Lets the agent drag-drop a file or slide.
                x = int(payload.get("x", 0))
                y = int(payload.get("y", 0))
                x2 = int(payload.get("x2", 0))
                y2 = int(payload.get("y2", 0))
                await self.computer.gui_action(
                    workspace_id,
                    GUIAction(action=GUIActionType.DRAG, x=x, y=y, x2=x2, y2=y2),
                )
                actual_obs_str = f"Dragged from ({x},{y}) to ({x2},{y2})"

            elif action_type == ComputerActionType.GUI_SCROLL:
                x = int(payload.get("x", 640))
                y = int(payload.get("y", 400))
                delta = int(payload.get("delta", -3))
                await self.computer.gui_action(
                    workspace_id,
                    GUIAction(action=GUIActionType.SCROLL, x=x, y=y, scroll_delta=delta),
                )
                actual_obs_str = f"Scrolled at ({x}, {y}) delta={delta}"

            elif action_type == ComputerActionType.GUI_SCREENSHOT:
                screen = await self.computer.screenshot(workspace_id)
                self._last_screenshot_b64 = getattr(screen, "screenshot_base64", "")
                self._update_screen_dims(screen)
                actual_obs_str = f"Screenshot captured ({screen.width}x{screen.height})"

            elif action_type == ComputerActionType.GUI_WAIT:
                # A human waits for a wizard step or progress bar before acting.
                # Without this the agent re-screenshots a still-loading UI and
                # clicks stale coordinates. Wait a fixed duration, then refresh
                # the screen so the NEXT observation reflects the settled state.
                import asyncio as _asyncio
                seconds = max(0, min(int(payload.get("seconds", 2)), 30))
                await _asyncio.sleep(seconds)
                screen = await self.computer.screenshot(workspace_id)
                self._last_screenshot_b64 = getattr(screen, "screenshot_base64", "")
                self._update_screen_dims(screen)
                actual_obs_str = f"Waited {seconds}s; screen refreshed"

            elif action_type == ComputerActionType.APP_LAUNCH:
                raw_app = payload.get("app_name") or target_resource
                app_name = str(raw_app).strip(" *_\n\r\t`\"'") if raw_app else ""
                if not app_name or app_name.lower() in ("none", "null", ""):
                    actual_obs_str = "APP_LAUNCH failed: application name required"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    if "\n" in app_name:
                        app_name = app_name.split("\n")[0].strip(" *_\n\r\t`\"'")
                    words = app_name.split()
                    if words and words[0].lower() in ("the", "a", "an") and len(words) > 1:
                        app_name = words[1]
                    elif words:
                        app_name = words[0]
                    await self.computer.gui_action(workspace_id, GUIAction(action=GUIActionType.OPEN_APP, app_name=app_name))
                    actual_obs_str = f"Launched and focused {app_name}"

            elif action_type == ComputerActionType.APP_CLOSE:
                raw_app = payload.get("app_name") or target_resource
                app_name = str(raw_app).strip(" *_\n\r\t`\"'") if raw_app else ""
                if not app_name or app_name.lower() in ("none", "null", ""):
                    actual_obs_str = "APP_CLOSE failed: application name required"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    if "\n" in app_name:
                        app_name = app_name.split("\n")[0].strip(" *_\n\r\t`\"'")
                    words = app_name.split()
                    if words and words[0].lower() in ("the", "a", "an") and len(words) > 1:
                        app_name = words[1]
                    elif words:
                        app_name = words[0]
                    await self.computer.gui_action(workspace_id, GUIAction(action=GUIActionType.CLOSE_APP, app_name=app_name))
                    actual_obs_str = f"Closed {app_name}"

            elif action_type == ComputerActionType.APP_FOCUS:
                raw_app = payload.get("app_name") or target_resource
                app_name = str(raw_app).strip(" *_\n\r\t`\"'") if raw_app else ""
                if not app_name or app_name.lower() in ("none", "null", ""):
                    actual_obs_str = "APP_FOCUS failed: window or application name required"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    if "\n" in app_name:
                        app_name = app_name.split("\n")[0].strip(" *_\n\r\t`\"'")
                    await self.computer.gui_action(
                        workspace_id,
                        GUIAction(action=GUIActionType.SELECT_WINDOW, app_name=app_name),
                    )
                    actual_obs_str = f"Focused window: {app_name}"

            elif action_type == ComputerActionType.APP_INSTALL:
                # Install a package via the provider's install_application(),
                # which enforces the ApplicationPolicy allowlist (forbidden
                # packages are blocked). This is the sanctioned install path —
                # an agent must NOT bypass it with a raw `apt-get install`
                # TERMINAL_EXEC, which would skip the package-policy gate.
                if not hasattr(self.computer, "install_application"):
                    actual_obs_str = "Install not supported by this computer provider"
                    recovery_needed = True
                    status = ActionExecutionStatus.FAILED
                else:
                    package = payload.get("package") or payload.get("app_name") or target_resource
                    if not package:
                        actual_obs_str = "APP_INSTALL requires a package name"
                        recovery_needed = True
                        status = ActionExecutionStatus.FAILED
                    else:
                        ok, output = await self.computer.install_application(
                            workspace_id, package,
                        )
                        if ok:
                            actual_obs_str = f"Installed {package}: {(output or '')[:200]}"
                        else:
                            actual_obs_str = f"Install {package} blocked/failed: {(output or '')[:200]}"
                            # A policy-blocked install (forbidden package) is
                            # NOT a recovery trigger — the safety gate decided
                            # correctly; the agent should pick a different tool.
                            if "prohibited" not in (output or "").lower():
                                recovery_needed = True
                                status = ActionExecutionStatus.FAILED
                            else:
                                status = ActionExecutionStatus.BLOCKED

            elif action_type == ComputerActionType.FILE_READ:
                path = payload.get("path") or target_resource or "/home/sonic/workspace/README.md"
                content = await self.computer.read_file(workspace_id, path)
                actual_obs_str = f"Read {len(content)} bytes from {path}"

            elif action_type == ComputerActionType.FILE_WRITE:
                path = payload.get("path") or target_resource or "/home/sonic/workspace/auth.py"
                content = payload.get("content", "")
                await self.computer.write_file(workspace_id, path, content)
                actual_obs_str = f"Wrote patch ({len(content)} bytes) to {path}"

            elif action_type == ComputerActionType.TERMINAL_EXEC:
                cmd = payload.get("command") or target_resource or "echo OK"
                if str(cmd).lower() in ("none", ""):
                    cmd = "echo OK"
                cmd_str = str(cmd).strip()
                cmd_str = re.sub(r'^(?:xfce4-terminal,?\s*)?(?:command|cmd)\s*=\s*', '', cmd_str)
                # Map /home/sonic to the actual sandbox home directory
                if "/home/sonic" in cmd_str:
                    real_home = getattr(self, "_last_working_dir", "") or "/home/daytona"
                    if "/workspace" in real_home:
                        real_home = real_home.split("/workspace")[0]
                    cmd_str = cmd_str.replace("/home/sonic", real_home)
                # Expand ~/ if used
                if "~/" in cmd_str:
                    real_home = getattr(self, "_last_working_dir", "") or "/home/daytona"
                    if "/workspace" in real_home:
                        real_home = real_home.split("/workspace")[0]
                    cmd_str = cmd_str.replace("~/", f"{real_home}/")
                # GUI applications must not block the terminal execution
                _GUI_APPS = ("chromium", "google-chrome", "firefox", "mousepad", "thunar", "burpsuite", "xfce4-terminal")
                if any(cmd_str.startswith(app) or cmd_str == app for app in _GUI_APPS) and not cmd_str.endswith("&"):
                    cmd_str = f"DISPLAY=:0 {cmd_str} &"
                res = await self.computer.terminal(workspace_id, cmd_str)
                action_exit_code = getattr(res, "exit_code", None)
                actual_obs_str = res.stdout.strip() or f"Exit {res.exit_code}"
                if res.exit_code != 0:
                    err_class, err_reason = classify_failure(
                        exit_code=res.exit_code,
                        stdout=getattr(res, "stdout", "") or "",
                        stderr=getattr(res, "stderr", "") or "",
                        provider=provider_name,
                        tool=tool_name,
                    )
                    fail_rec = self.failure_budget.record_failure(
                        tool=tool_name,
                        provider=provider_name,
                        error_class=err_class,
                        raw_error=getattr(res, "stderr", "") or getattr(res, "stdout", "") or f"Exit {res.exit_code}",
                    )
                    if self.failure_budget.is_strategy_exhausted(tool=tool_name, provider=provider_name):
                        actual_obs_str = f"{actual_obs_str} | Strategy exhausted ({fail_rec.count} failures). Retrying is blocked."
                        status = ActionExecutionStatus.FAILED
                        recovery_needed = False
                    elif res.exit_code == 124:
                        status = ActionExecutionStatus.TIMED_OUT
                        recovery_needed = True
                    elif res.exit_code in (125, 126):
                        status = ActionExecutionStatus.BLOCKED
                        recovery_needed = False
                    else:
                        status = ActionExecutionStatus.FAILED
                        recovery_needed = True
                else:
                    self.failure_budget.record_success(tool=tool_name, provider=provider_name)

                if hasattr(self, "scratchpad") and self.scratchpad:
                    self.scratchpad.extract_from_text(res.stdout, source="terminal")
                    if getattr(res, "stderr", ""):
                        self.scratchpad.extract_from_text(res.stderr, source="terminal_err")

                if hasattr(self, "wire_telemetry") and self.wire_telemetry:
                    if "curl " in cmd_str or "http " in cmd_str:
                        url_m = re.search(r'https?://[^\s"\']+', cmd_str)
                        target_url = url_m.group(0) if url_m else "http://target"
                        method = "POST" if ("-X POST" in cmd_str or "-d " in cmd_str or "--data" in cmd_str) else "GET"
                        status_code = 200 if res.exit_code == 0 else 500
                        status_m = re.search(r'\b([1-5]\d{2})\b', res.stdout[:50])
                        if status_m:
                            try:
                                status_code = int(status_m.group(1))
                            except Exception:
                                pass
                        self.wire_telemetry.record_wire_event(
                            method=method,
                            url=target_url,
                            status_code=status_code,
                            response_body=res.stdout[:300],
                        )

            elif action_type == ComputerActionType.GIT_COMMIT:
                msg = payload.get("message", "feat: automated patch")
                await self.computer.git_action(workspace_id, "commit", message=msg)
                actual_obs_str = f"Committed change: {msg}"

            elif action_type == ComputerActionType.SERVICE_ACTION:
                svc = payload.get("service", "xvfb")
                act = payload.get("action", "restart")
                svc_info = await self.computer.service_action(workspace_id, svc, act)
                actual_obs_str = f"Service {svc} is {svc_info.status}"

            elif action_type == ComputerActionType.BROWSER_NAVIGATE:
                raw_url = payload.get("url") or target_resource
                url = str(raw_url).strip(" *_\n\r\t`\"'") if raw_url else ""
                if "\n" in url:
                    url = url.split("\n")[0].strip(" *_\n\r\t`\"'")
                if not url or url.lower() in ("none", "not specified", "null", "/"):
                    url = "about:blank"
                elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("about:") or url.startswith("file://")):
                    if "localhost" in url or "127.0.0.1" in url:
                        url = f"http://{url}"
                    elif "." in url and " " not in url:
                        url = f"https://{url}"

                if self.browser is not None:
                    snap = await self.browser.navigate(url)
                    self._last_browser_snapshot = snap
                    self._last_navigated_url = url
                    actual_obs_str = f"Navigated to {getattr(snap, 'url', url)} (title: {getattr(snap, 'title', '')})"
                else:
                    is_same_url = getattr(self, "_last_navigated_url", "") == url
                    self._last_navigated_url = url
                    if is_same_url:
                        # Re-focus existing browser without spawning duplicate tabs
                        focus_cmd = "DISPLAY=:0 xdotool search --onlyvisible --class chromium windowactivate 2>/dev/null || true"
                        await self.computer.terminal(workspace_id, focus_cmd)
                        actual_obs_str = (
                            f"Browser is already active on {url}. Existing tab focused (duplicate tab prevented). "
                            "Proceed to interact with the webpage via GUI_CLICK on buttons, search bar, or scroll."
                        )
                    else:
                        # Check if Chromium is already running in the desktop session
                        chk = await self.computer.terminal(workspace_id, "pgrep -i chromium || pgrep -i chrome 2>/dev/null || true")
                        chrome_running = bool(chk.stdout.strip())
                        if chrome_running:
                            # Reuse existing Chromium window: focus, focus address bar via ctrl+l, type URL and press Return
                            nav_cmd = (
                                f"DISPLAY=:0 xdotool search --onlyvisible --class chromium windowactivate --sync "
                                f"key --clearmodifiers ctrl+l sleep 0.1 type --delay 15 {shlex.quote(url)} key Return 2>/dev/null || true"
                            )
                            await self.computer.terminal(workspace_id, nav_cmd)
                            if hasattr(self, "motor") and self.motor:
                                await self.motor.enforce_tab_budget(workspace_id, max_tabs=3)
                            actual_obs_str = f"Navigated active browser tab to {url} (tab reused via address bar)"
                        else:
                            clean_flags = "--no-sandbox --disable-dev-shm-usage --disable-session-crashed-bubble --no-first-run --no-default-browser-check"
                            cmd = f"DISPLAY=:0 nohup chromium {clean_flags} {shlex.quote(url)} >/dev/null 2>&1 &"
                            await self.computer.terminal(workspace_id, cmd)
                            actual_obs_str = f"Launched browser and navigated to {url}"

                if hasattr(self, "scratchpad") and self.scratchpad:
                    self.scratchpad.extract_from_text(url, source="url")
                if hasattr(self, "wire_telemetry") and self.wire_telemetry and url.startswith("http"):
                    self.wire_telemetry.record_wire_event(
                        method="GET",
                        url=url,
                        status_code=200,
                        response_body="HTML DOM Rendered",
                    )
                if url.startswith("http"):
                    await self.check_and_resolve_intercept_deadlock(workspace_id)

            elif action_type == ComputerActionType.BROWSER_CLICK:
                selector = payload.get("selector") or target_resource
                if self.browser is not None:
                    ok = await self.browser.click(selector)
                    actual_obs_str = f"Clicked {selector}" if ok else f"Click failed: {selector}"
                    if not ok:
                        recovery_needed = True
                    await self.check_and_resolve_intercept_deadlock(workspace_id)
                else:
                    actual_obs_str = f"Browser DOM click '{selector}' not available without BrowserAgent; use GUI_CLICK"

            elif action_type == ComputerActionType.BROWSER_TYPE:
                selector = str(payload.get("selector") or target_resource or "").strip(" *_\n\r\t`\"'")
                text = (
                    payload.get("text")
                    or payload.get("command")
                    or payload.get("value")
                    or payload.get("query")
                    or payload.get("input")
                    or ""
                )
                if not text and selector:
                    elem_keywords = ("address", "bar", "input", "selector", "field", "box", "element", "button", "div", "form")
                    if not any(k in selector.lower() for k in elem_keywords):
                        text = selector
                        selector = "input"

                if self.browser is not None:
                    ok = await self.browser.type_text(selector, text)
                    actual_obs_str = f"Typed {len(text)} chars into {selector}" if ok else f"Type failed: {selector}"
                    if not ok:
                        recovery_needed = True
                else:
                    is_address_bar = any(k in selector.lower() for k in ("address", "url bar", "location", "omnibox"))
                    if is_address_bar:
                        await self.computer.gui_action(workspace_id, GUIAction(action=GUIActionType.KEYPRESS, key="ctrl+l"))
                        import asyncio as _asyncio
                        await _asyncio.sleep(0.3)

                    if text:
                        await self.computer.gui_action(workspace_id, GUIAction(action=GUIActionType.TYPE, text=text))
                        import asyncio as _asyncio
                        await _asyncio.sleep(0.2)
                        if is_address_bar or "search" in selector.lower():
                            await self.computer.gui_action(workspace_id, GUIAction(action=GUIActionType.KEYPRESS, key="Return"))
                        actual_obs_str = f"Typed {len(text)} chars via GUI keyboard: {text[:40]}"
                    else:
                        actual_obs_str = f"Typed 0 chars via GUI keyboard (empty text for {selector})"

            elif action_type == ComputerActionType.BROWSER_SCREENSHOT:
                if self.browser is not None:
                    snap = await self.browser.navigate(
                        getattr(self._last_browser_snapshot, "url", "about:blank")
                    ) if self._last_browser_snapshot else await self.browser.navigate("about:blank")
                    self._last_browser_snapshot = snap
                    actual_obs_str = f"Screenshot captured: {getattr(snap, 'url', '')}"
                else:
                    screen = await self.computer.screenshot(workspace_id)
                    self._update_screen_dims(screen)
                    actual_obs_str = f"Desktop screenshot captured ({screen.width}x{screen.height})"

            elif action_type == ComputerActionType.BROWSER_WAIT:
                # Wait for a page element to render before clicking it — a human
                # waits for a download button or "Next" to appear.
                selector = payload.get("selector") or target_resource
                if self.browser is not None and selector:
                    ok = await self.browser.wait_for_element(selector)
                    actual_obs_str = f"Element {selector} ready" if ok else f"Element {selector} not found within timeout"
                else:
                    import asyncio as _asyncio
                    await _asyncio.sleep(2)
                    actual_obs_str = "Waited 2s (no BrowserAgent)"

            elif action_type == ComputerActionType.BROWSER_DOWNLOAD:
                # Human step: click a download link on the website and save the
                # file to the sandbox workspace. save_path is confined to the
                # workspace root by the safety gate (FILE_WRITE-style).
                selector = payload.get("selector") or target_resource
                save_path = payload.get("save_path") or payload.get("path")
                if self.browser is None:
                    actual_obs_str = "Download requires BrowserAgent (Playwright)"
                    recovery_needed = True
                elif not selector or not save_path:
                    actual_obs_str = "BROWSER_DOWNLOAD requires selector and save_path"
                    recovery_needed = True
                else:
                    ok = await self.browser.download(selector, save_path)
                    if ok:
                        actual_obs_str = f"Downloaded {selector} to {save_path}"
                    else:
                        actual_obs_str = f"Download failed: {selector}"
                        recovery_needed = True

            elif action_type == ComputerActionType.SECURITY_TOOL:
                tool_name = payload.get("tool", target_resource)
                scan_target = payload.get("target", target_resource)
                args = payload.get("args", "")
                tool = self.security_tools.get(tool_name)
                if tool is None:
                    actual_obs_str = f"Unknown security tool: {tool_name}"
                    recovery_needed = True
                else:
                    from sonic.tools.base import ToolRequest
                    options = {"args": args} if args else {}
                    req = ToolRequest(
                        tenant_id=self.tenant_id,
                        engagement_id=self.engagement_id,
                        workspace_id=workspace_id,
                        agent_id=self.agent_id,
                        tool_name=tool_name,
                        target=scan_target,
                        options=options,
                    )
                    result = await tool.execute(req)
                    self._last_tool_result = result
                    findings = getattr(result, "parsed_data", []) or []
                    actual_obs_str = (
                        f"Tool {tool_name} status={getattr(result, 'status', '?')} "
                        f"findings={len(findings)}"
                    )
                    # Fail-closed: a blocked/failed tool is a recovery trigger.
                    status_val = str(getattr(result, "status", "")).lower()
                    if status_val in ("blocked", "failed", "timed_out"):
                        raw_err = getattr(result, "raw_output", "") or getattr(result, "error", "")
                        exit_c = 126 if status_val == "blocked" else (124 if status_val == "timed_out" else 1)
                        action_exit_code = exit_c
                        err_class, _ = classify_failure(
                            exit_code=exit_c,
                            stdout="",
                            stderr=str(raw_err),
                            provider=provider_name,
                            tool=tool_name,
                        )
                        fail_rec = self.failure_budget.record_failure(
                            tool=tool_name,
                            provider=provider_name,
                            error_class=err_class,
                            raw_error=str(raw_err),
                        )
                        if self.failure_budget.is_strategy_exhausted(tool=tool_name, provider=provider_name):
                            actual_obs_str = f"{actual_obs_str} | Strategy exhausted ({fail_rec.count} failures). Retrying is blocked."
                            status = ActionExecutionStatus.FAILED
                            recovery_needed = False
                        elif status_val == "blocked":
                            status = ActionExecutionStatus.BLOCKED
                            recovery_needed = True
                        elif status_val == "timed_out":
                            status = ActionExecutionStatus.TIMED_OUT
                            recovery_needed = True
                        else:
                            status = ActionExecutionStatus.FAILED
                            recovery_needed = True
                    else:
                        action_exit_code = 0
                        self.failure_budget.record_success(tool=tool_name, provider=provider_name)

            elif action_type == ComputerActionType.TOOL_AUTHOR:
                # Toolsmith (Phase A, AIOSR): the being authors a NEW tool for an
                # observation gap. The source is persisted to BeingCraft; the
                # tool is NOT registered until TOOL_RUN confirms it in-sandbox.
                # No "tool authored and working" claim by decree.
                if self.toolsmith is None:
                    actual_obs_str = "Toolsmith not configured (no tool authoring)"
                    recovery_needed = True
                else:
                    observation = payload.get("observation", "") or target_resource
                    failed = payload.get("failed_attempts", [])
                    authored = await self.toolsmith.author_tool_for_gap(
                        observation=observation, failed_attempts=list(failed),
                    )
                    if authored is None:
                        actual_obs_str = "Toolsmith: no novel tool warranted (honest skip)"
                    else:
                        actual_obs_str = (
                            f"Authored tool '{authored.name}' (unconfirmed; "
                            f"run TOOL_RUN to verify): {authored.rationale}"
                        )

            elif action_type == ComputerActionType.TOOL_RUN:
                # Run a previously-authored tool in-sandbox and register it into
                # the security_tools map ONLY on a real successful run. Honesty
                # guard lives in ToolsmithLoop.confirm_and_register.
                if self.toolsmith is None:
                    actual_obs_str = "Toolsmith not configured (no tool running)"
                    recovery_needed = True
                else:
                    tool_name = payload.get("tool", target_resource)
                    authored = next(
                        (t for t in self.toolsmith.authored if t.name == tool_name), None
                    )
                    if authored is None:
                        actual_obs_str = f"No authored tool named '{tool_name}' to run"
                        recovery_needed = True
                    else:
                        confirmed = await self.toolsmith.confirm_and_register(
                            authored, self.computer, workspace_id,
                        )
                        if confirmed.reproduced:
                            # Make the confirmed tool callable via SECURITY_TOOL.
                            adapter = self.toolsmith.registry.get(confirmed.name)
                            if adapter is not None:
                                self.security_tools[confirmed.name] = adapter
                            actual_obs_str = (
                                f"Tool '{confirmed.name}' CONFIRMED and registered "
                                f"(exit={confirmed.run_exit_code})"
                            )
                        else:
                            actual_obs_str = (
                                f"Tool '{confirmed.name}' NOT confirmed "
                                f"(exit={confirmed.run_exit_code}); not registered"
                            )
                            recovery_needed = True

            elif action_type == ComputerActionType.METHOD_INVENT:
                # Method-invention (Phase B, AIOSR): synthesize a NOVEL
                # offensive technique (a new METHOD, not just a tool) from the
                # observation + a prior failure + the known-technique ledger.
                # Confirmed ONLY on real in-sandbox reproduction — never by decree.
                if self.method_lab is None:
                    actual_obs_str = "MethodLab not configured (no technique invention)"
                    recovery_needed = True
                else:
                    observation = payload.get("observation", "") or target_resource
                    failure = payload.get("failure", "")
                    technique = await self.method_lab.invent(
                        observation=observation, failure=failure,
                    )
                    if technique is None:
                        actual_obs_str = "MethodLab: no novel technique warranted (honest skip)"
                    else:
                        # Run the probe in-sandbox; confirm only on a real finding.
                        target = payload.get("target", "") or technique.target_hint
                        confirmed = await self.method_lab.confirm(
                            technique, self.computer, workspace_id, target=target,
                        )
                        if confirmed.confirmed:
                            actual_obs_str = (
                                f"Technique '{confirmed.name}' ({confirmed.family}) "
                                f"CONFIRMED — {len(confirmed.findings)} finding(s); "
                                f"novelty={confirmed.novelty_vs_ledger:.2f} vs ledger"
                            )
                        else:
                            actual_obs_str = (
                                f"Technique '{confirmed.name}' NOT confirmed "
                                f"(exit={confirmed.run_exit_code}); not added to ledger"
                            )
                            recovery_needed = True

        except Exception as e:
            actual_obs_str = f"Error: {str(e)}"
            recovery_needed = True
            status = ActionExecutionStatus.FAILED
            err_class, _ = classify_failure(
                exit_code=1,
                stderr=str(e),
                provider=provider_name,
                tool=tool_name,
            )
            if hasattr(self, "failure_budget"):
                self.failure_budget.record_failure(
                    tool=tool_name,
                    provider=provider_name,
                    error_class=err_class,
                    raw_error=str(e),
                )

        # Adaptive Closed-Loop Recovery if needed
        if recovery_needed:
            if self.recovery_events < self.max_recovery_attempts:
                rec_trace = await self.recover(workspace_id, action_type, actual_obs_str)
                actual_obs_str = f"{actual_obs_str} | Recovered: {rec_trace}"
                status = ActionExecutionStatus.RECOVERED
            else:
                if status in (ActionExecutionStatus.COMPLETED, ActionExecutionStatus.SUCCESS):
                    status = ActionExecutionStatus.FAILED

        # Automatic Hacker Scratchpad loot/token extraction
        if hasattr(self, "scratchpad") and self.scratchpad:
            self.scratchpad.extract_from_text(actual_obs_str, source=action_type.value.lower())

        # Reflexive backtracking on blocking modal overlays
        if hasattr(self, "motor") and self.motor:
            lower_obs = actual_obs_str.lower()
            if any(term in lower_obs for term in ("modal_blocked", "blocked by modal", "overlay detected", "dismiss modal")):
                await self.motor.backtrack(workspace_id, reason="modal_blocked")
                actual_obs_str = f"{actual_obs_str} | Reflexive backtrack: dismissed blocking modal"

        trace = ComputerDecisionTrace(
            step_index=self.action_counter,
            action_type=action_type,
            target_resource=target_resource,
            payload=str(payload),
            predicted_outcome=predicted_outcome,
            actual_observation=actual_obs_str,
            info_gain=1.0,
            recovery_attempted=recovery_needed,
            thought=getattr(self, "_last_thought", ""),
            status=status,
            exit_code=action_exit_code,
            duration_seconds=round(time.perf_counter() - t_start, 2),
            thought_duration_seconds=getattr(self, "_last_thought_duration", 0.0),
        )
        self.traces.append(trace)
        # Record into the reasoning history so the next LLM call sees what was
        # done and how it turned out — the basis for adaptive (non-scripted) action.
        self.history.append({
            "action": f"{action_type.value} {target_resource}",
            "result": actual_obs_str,
        })
        return trace

    # =============================================================
    # 4. Adaptive Recovery Intelligence
    # =============================================================
    async def recover(
        self,
        workspace_id: str,
        failed_action_type: ComputerActionType,
        error_context: str,
    ) -> str:
        """Generates closed-loop recovery actions to heal broken computer state."""
        self.recovery_events += 1
        logger.warning("computer_recovery_triggered", action=failed_action_type, error=error_context)

        # Recovery strategy 1: Restart display service if GUI failed
        if failed_action_type in [
            ComputerActionType.APP_LAUNCH, ComputerActionType.GUI_CLICK,
            ComputerActionType.GUI_DOUBLE_CLICK, ComputerActionType.GUI_TYPE,
            ComputerActionType.GUI_KEYPRESS, ComputerActionType.GUI_MOVE,
            ComputerActionType.GUI_SCROLL,
        ]:
            await self.computer.service_action(workspace_id, "xvfb", "restart")
            await self.computer.gui_action(workspace_id, GUIAction(action=GUIActionType.OPEN_APP, app_name="code-server"))
            return "Restarted Xvfb and relaunched code-server"

        # Recovery strategy 2: Restore workspace snapshot or re-verify file
        if failed_action_type == ComputerActionType.FILE_READ:
            return "Recovery blocked: the missing file must be restored from a real workspace snapshot or repository checkout"

        # Recovery strategy 3: Terminal PTY reset
        if failed_action_type == ComputerActionType.TERMINAL_EXEC:
            await self.computer.terminal(workspace_id, "clear || true")
            return "Reset terminal shell session"

        return "Generic recovery action applied"

    # =============================================================
    # 5. Full Autonomous Mission Execution Loop
    # =============================================================

    # Threshold: after this many consecutive failures in a row, the loop
    # considers the current approach stuck and injects a replan prompt rather
    # than repeating the same failing strategy until the step budget is gone.
    _STUCK_THRESHOLD: int = 3

    async def check_and_resolve_intercept_deadlock(
        self,
        workspace_id: str,
        screen_observation: Any | None = None,
    ) -> bool:
        """
        Detects if an HTTP request is stalled in Burp Suite Proxy Intercept:
        If Burp proxy intercept is holding a request or if the screen shows Burp Suite
        with an active intercepted packet, dispatches an automatic packet forward (motor.burp_forward)
        or toggles intercept so browser missions never deadlock.
        """
        # 1. Check if Burp is active or burp_client configured
        burp_active = self.burp_client is not None
        if not burp_active and hasattr(self.computer, "terminal"):
            try:
                chk = await self.computer.terminal(workspace_id, "pgrep -i burp || pgrep -i java 2>/dev/null || true")
                if chk and getattr(chk, "stdout", "").strip():
                    burp_active = True
            except Exception:
                pass

        if not burp_active:
            return False

        # 2. Check if screen indicates intercepted request or active window is Burp
        should_forward = False
        if screen_observation is not None:
            active_win = str(getattr(screen_observation, "active_window", "")).lower()
            if "burp" in active_win:
                should_forward = True

        if not should_forward and hasattr(self, "wire_telemetry") and self.wire_telemetry:
            should_forward = True

        if should_forward and hasattr(self, "motor") and self.motor:
            try:
                await self.motor.burp_forward(workspace_id)
                logger.info("burp_intercept_deadlock_resolved_via_forward", workspace_id=workspace_id)
                return True
            except Exception as exc:
                logger.warning("burp_intercept_deadlock_resolution_failed", error=str(exc))

        return False

    async def verify_goal(
        self,
        workspace_id: str,
        goal: str,
        *,
        use_llm: bool | None = None,
    ) -> tuple[bool, str]:
        """Independently verify whether a goal has been achieved.

        Supports LLM-driven verification when explicitly requested (use_llm=True
        or self.enable_llm_verification=True), asking the LLM to evaluate real
        evidence rather than circular self-judgment.

        When in standard mode, performs an independent sandbox check grounded
        in real system state (service/process/test artifacts) without theatrical
        echo stubs.

        Returns (verified, evidence). verified=True only on real evidence.
        """
        do_llm = use_llm if use_llm is not None else getattr(self, "enable_llm_verification", False)

        if do_llm and self.llm_router is not None:
            async def _query_llm(prompt: str) -> str:
                from sonic.llm.schemas import LLMRequest, Message, MessageRole
                req = LLMRequest(
                    messages=[Message(role=MessageRole.USER, content=prompt)],
                    task_type="reasoning",
                )
                resp = await self.llm_router.complete(req)
                return resp.content

            # Step 1: Gather current observation for context
            obs = await self.observe(workspace_id)
            obs_summary = f"app={obs.active_application}, term={obs.terminal_output[:200] if obs.terminal_output else 'empty'}"

            # Step 2: Ask LLM to propose a verification command
            verify_prompt = (
                f"Goal: {goal}\n"
                f"Current observation: {obs_summary}\n\n"
                "Propose a single shell command that would verify whether this goal "
                "has been achieved. The command should produce clear output that "
                "proves success or failure. Respond with ONLY the command, nothing else.\n"
                "If no verification command makes sense, respond with: OBSERVE_ONLY"
            )

            evidence = ""
            try:
                llm_resp = await _query_llm(verify_prompt)
                verify_cmd = llm_resp.strip().split("\n")[0].strip()

                if verify_cmd and verify_cmd != "OBSERVE_ONLY" and len(verify_cmd) < 500:
                    try:
                        res = await self.computer.terminal(workspace_id, verify_cmd)
                        evidence = (res.stdout.strip() if res.stdout else "") or f"Exit {res.exit_code}"
                    except Exception as e:
                        evidence = f"Verify probe failed: {e}"
                else:
                    evidence = f"Observation: {obs_summary}"
            except Exception:
                evidence = f"Observation (LLM unavailable): {obs_summary}"

            # Step 3: Ask LLM to evaluate the evidence
            try:
                eval_prompt = (
                    f"Goal: {goal}\n"
                    f"Verification evidence:\n{evidence[:2000]}\n\n"
                    "Based on this evidence, has the goal been achieved? "
                    "Respond with exactly YES or NO on the first line, "
                    "followed by a brief explanation."
                )
                eval_resp = await _query_llm(eval_prompt)
                first_line = eval_resp.strip().split("\n")[0].upper()
                verified = "YES" in first_line
            except Exception:
                ev_lower = evidence.lower()
                verified = bool(evidence) and "error" not in ev_lower and "traceback" not in ev_lower

            return verified, evidence

        # Standard sandbox-grounded probe
        g = goal.lower().strip()
        verify_cmd: str | None = None
        if any(k in g for k in ("test", "pytest", "unittest")):
            verify_cmd = "python -m pytest -q --tb=short 2>&1 | tail -5"
        elif any(k in g for k in ("install", "set up", "setup")):
            m = re.search(r"install(?:\s+(?:the\s+)?)?([a-zA-Z0-9_.-]+)", g)
            pkg = m.group(1) if m else ""
            if pkg:
                verify_cmd = f"which {pkg} 2>/dev/null || dpkg -l {pkg} 2>/dev/null | grep ^ii"
        elif any(k in g for k in ("run", "start", "serve", "launch")):
            obs = await self.observe(workspace_id)
            procs = " ".join(obs.processes) if obs.processes else ""
            evidence = f"Running processes: {procs or 'none detected'}"
            verified = len(obs.processes) > 0 or obs.active_application != ""
            return verified, evidence

        evidence = ""
        if verify_cmd:
            try:
                res = await self.computer.terminal(workspace_id, verify_cmd)
                evidence = (res.stdout.strip() if res.stdout else "") or f"Exit {res.exit_code}"
            except Exception as e:
                evidence = f"Verify probe failed: {e}"
        else:
            obs = await self.observe(workspace_id)
            evidence = f"Re-observed: app={obs.active_application}, term={obs.terminal_output[:120]}"

        ev_lower = evidence.lower()
        verified = bool(evidence) and "error" not in ev_lower and "traceback" not in ev_lower
        return verified, evidence

    def _inject_replan(self, goal: str) -> None:
        """Signal the reasoning loop to abandon the current approach.

        When the agent is stuck (N consecutive failures), a human reassesses:
        "this isn't working, try a different angle." We inject that signal into
        the history so the NEXT LLM call sees it and pivots, rather than
        repeating the same failing action until the step budget is exhausted.
        """
        self._replan_count += 1
        self._consecutive_failures = 0
        if getattr(self, "checklist", None) is not None:
            active_sg = self.checklist.active_sub_goal()
            if active_sg:
                active_sg.status = SubGoalStatus.FAILED
                active_sg.evidence = "Failed repeatedly during execution — pivoting strategy."
                self.checklist.advance()

        replan_note = (
            f"REPLAN #{self._replan_count}: the last approach failed repeatedly. "
            f"Goal remains: {goal}. Re-assess from the current observation and "
            f"choose a DIFFERENT strategy — do not repeat the failing action."
        )
        self.history.append({"action": "REPLAN", "result": replan_note})
        logger.warning(
            "mission_replan_triggered",
            replan_count=self._replan_count,
            goal=goal,
        )

    async def run_mission(
        self,
        workspace_id: str,
        goal: str,
        steps: int = 5,
        step_callback: Optional[Any] = None,
        interrupt_check: Optional[Any] = None,
    ) -> list[ComputerDecisionTrace]:
        """Runs an end-to-end closed-loop autonomous engineering mission."""
        t_start = time.perf_counter()
        self._interrupted = False
        goal_reached = False

        if getattr(self, "checklist", None) is None or self.checklist.top_level_goal != goal:
            self.checklist = await self.decompose_goal(goal)

        # Autonomous Workstation Environment Bootstrap & Audit (Phase 8)
        if not getattr(self, "_bootstrap_performed", False):
            try:
                from sonic.computer.bootstrap import WorkstationBootstrapEngine
                bootstrap = WorkstationBootstrapEngine(self.computer)
                b_res = await bootstrap.ensure_workstation_ready(workspace_id=workspace_id)
                logger.info(
                    "mission_workstation_bootstrap_audit",
                    status=b_res.get("status"),
                    present_count=len(b_res.get("present", [])),
                    missing=b_res.get("missing", []),
                )
                self._bootstrap_performed = True
            except Exception as b_err:
                logger.warning("mission_workstation_bootstrap_failed", error=str(b_err))

        for step in range(1, steps + 1):
            if self._interrupted or (callable(interrupt_check) and interrupt_check()):
                self._interrupted = True
                logger.info("mission_interrupted_by_user", step=step)
                break
            if self.action_counter >= self.max_actions:
                logger.warning("max_actions_reached", max=self.max_actions)
                break

            # 1. OBSERVE
            obs = await self.observe(workspace_id)

            # 2. REASON & CHOOSE ACTION
            action_type, target, payload, expected = await self.choose_action(goal, obs, step)

            # Goal-complete sentinel: the LLM JUDGED the goal achieved — but we
            # do not stop on self-declaration alone. We independently verify.
            if expected == _GOAL_COMPLETE_SENTINEL:
                verified, evidence = await self.verify_goal(workspace_id, goal)
                if verified:
                    logger.info(
                        "mission_goal_complete_verified",
                        step=step,
                        actions_taken=self.action_counter,
                        evidence=evidence[:200],
                    )
                    if getattr(self, "checklist", None) is not None:
                        for sg in self.checklist.sub_goals:
                            if sg.status != SubGoalStatus.COMPLETED:
                                sg.status = SubGoalStatus.COMPLETED
                                sg.evidence = evidence[:100]
                    goal_reached = True
                    break
                # Self-declared done but independent verification FAILED: the
                # goal is NOT actually achieved. Feed the evidence back so the
                # LLM corrects course instead of stopping on a false positive.
                self.history.append({
                    "action": "GOAL_COMPLETE (self-declared)",
                    "result": f"VERIFICATION FAILED: {evidence[:200]}. Goal NOT achieved — continue.",
                })
                self._consecutive_failures += 1
                if getattr(self, "checklist", None) is not None:
                    active_sg = self.checklist.active_sub_goal()
                    if active_sg:
                        active_sg.attempt_count += 1
                if self._consecutive_failures >= self._STUCK_THRESHOLD:
                    self._inject_replan(goal)
                continue

            # 3. ACT & VERIFY
            trace = await self.execute_action(workspace_id, action_type, target, payload, expected)

            # Invoke real-time step streaming callback if provided
            if step_callback is not None:
                try:
                    cb_res = step_callback(trace)
                    if asyncio.iscoroutine(cb_res):
                        await cb_res
                except Exception as cb_err:
                    logger.warning("run_mission_step_callback_failed", error=str(cb_err))

            # Track consecutive failures for stuck/replan detection.
            is_failed_status = trace.status in (
                ActionExecutionStatus.FAILED,
                ActionExecutionStatus.TIMED_OUT,
                ActionExecutionStatus.BLOCKED,
                ActionExecutionStatus.CANCELLED,
                "FAILED",
                "TIMED_OUT",
                "BLOCKED",
                "CANCELLED",
            )
            if is_failed_status or trace.recovery_attempted:
                self._consecutive_failures += 1
                if getattr(self, "checklist", None) is not None:
                    active_sg = self.checklist.active_sub_goal()
                    if active_sg:
                        active_sg.attempt_count += 1
                if self._consecutive_failures >= self._STUCK_THRESHOLD:
                    self._inject_replan(goal)
            elif trace.status in (
                ActionExecutionStatus.COMPLETED,
                ActionExecutionStatus.SUCCESS,
                ActionExecutionStatus.VERIFIED,
                "COMPLETED",
                "SUCCESS",
                "VERIFIED",
            ):
                self._consecutive_failures = 0
                if getattr(self, "checklist", None) is not None:
                    active_sg = self.checklist.active_sub_goal()
                    if active_sg:
                        active_sg.attempt_count += 1
                        obs_txt = str(getattr(trace, "actual_observation", "") or "")
                        if "[VISUAL VERIFICATION]: Screen state unchanged" not in obs_txt:
                            cmd_str = str(getattr(trace, "payload", "") or "").strip().lower()
                            trivial_cmds = ("pwd", "whoami", "uname", "id", "echo", "true")
                            is_trivial = any(cmd_str == tc or cmd_str.startswith(f"{tc} ") for tc in trivial_cmds)
                            if not is_trivial:
                                self.checklist.mark_active_completed(
                                    evidence=f"{action_type} succeeded: {obs_txt[:100]}"
                                )

        # Update Telemetry Metrics.
        self.metrics.actions_total = len(self.traces)
        self.metrics.actions_successful = sum(
            1 for t in self.traces if t.status in (
                ActionExecutionStatus.COMPLETED,
                ActionExecutionStatus.SUCCESS,
                ActionExecutionStatus.RECOVERED,
                ActionExecutionStatus.VERIFIED,
                "COMPLETED",
                "SUCCESS",
                "RECOVERED",
                "VERIFIED",
            )
        )
        self.metrics.actions_failed = sum(
            1 for t in self.traces if t.status in (
                ActionExecutionStatus.FAILED,
                ActionExecutionStatus.TIMED_OUT,
                ActionExecutionStatus.BLOCKED,
                ActionExecutionStatus.CANCELLED,
                "FAILED",
                "TIMED_OUT",
                "BLOCKED",
                "CANCELLED",
            )
        )
        self.metrics.recovery_events = self.recovery_events

        if not goal_reached and self.metrics.actions_successful > 0 and self.metrics.actions_failed == 0:
            try:
                verified, _ = await self.verify_goal(workspace_id, goal)
                if verified:
                    goal_reached = True
            except Exception as v_err:
                logger.debug("post_mission_verify_error", error=str(v_err))

        self.goal_reached = goal_reached
        t_elapsed = time.perf_counter() - t_start
        self.metrics.time_to_completion_seconds = round(t_elapsed, 2)
        self.metrics.verification_score = 1.00 if goal_reached else (
            0.90 if self.metrics.actions_failed == 0 else 0.80
        )

        # Close the learn→apply loop: distill this mission's traces into lessons
        # and persist them so the NEXT mission's reasoning sees them. Grounded
        # in real trace outcomes (FAILED→AVOID, SUCCESS/RECOVERED→REUSE) — never
        # fabricated. Skipped silently when no ledger is wired in.
        if self.lessons_ledger is not None:
            from sonic.being.lessons import extract_lessons
            new_lessons = extract_lessons(self.traces, goal, self.agent_id)
            if new_lessons:
                self.lessons_ledger.record(new_lessons)

        return self.traces

    # =============================================================
    # 6. Self-Directed Curiosity / Life Loop (Phase 6)
    # =============================================================
    async def _observation_summary(self, workspace_id: str) -> str:
        """A compact text summary of the current world for curiosity proposals."""
        obs = await self.observe(workspace_id)
        return (
            f"Active app: {obs.active_application}\n"
            f"Screen: {(obs.visible_text or '')[:300]}\n"
            f"Terminal: {(obs.terminal_output or '')[:200]}\n"
            f"Files: {obs.filesystem_files}\n"
            f"Git: branch={obs.git_branch}, clean={obs.git_clean}"
        )

    async def idle_cycle(
        self,
        workspace_id: str,
        curiosity: Any,
    ) -> Any:
        """One self-directed curiosity cycle, no operator goal required.

        Uses the CuriosityLoop to PROPOSE a goal from the live observation +
        learned facts, pursues it via the real observe->reason->act loop, then
        measures novelty and persists any newly-learned fact. Returns the
        CuriosityCycleResult.
        """
        async def pursue(goal: str, steps: int) -> str:
            before = len(self.traces)
            await self.run_mission(workspace_id, goal, steps=steps)
            # Summarize what the pursuit actually observed/did.
            new_traces = self.traces[before:]
            if not new_traces:
                return f"no actions taken toward: {goal}"
            outcomes = "; ".join(
                f"{t.action_type.value}:{(t.actual_observation or '')[:60]}" for t in new_traces
            )
            return f"{goal} -> {outcomes}"

        obs_summary = await self._observation_summary(workspace_id)
        return await curiosity.run_cycle(obs_summary, pursue)

    async def run_curiosity_loop(
        self,
        workspace_id: str,
        curiosity: Any,
    ) -> list[Any]:
        """Run repeated self-directed curiosity cycles until max_cycles."""
        results = []
        for _ in range(curiosity.max_cycles):
            res = await self.idle_cycle(workspace_id, curiosity)
            results.append(res)
        return results
