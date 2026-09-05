"""
Launch SONIC A-SEA Autonomous Agent on Cyber Workstation
========================================================
Executes an autonomous, goal-oriented mission inside the interactive
Docker cyber workstation (sonic-desktop-workstation).
Demonstrates independent thinking, observation, reasoning, and empirical action.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from sonic.computer.docker_computer import DockerComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.llm.router import ModelRouter
from sonic.safety.action_policy import ActionPolicy
from sonic.tools.registry import get_default_registry


async def main():
    print("=" * 60)
    print("  SONIC A-SEA: Autonomous Penetration Architect")
    print("  Launching Autonomous Agent on Docker Workstation")
    print("=" * 60)

    # 1. Initialize workstation computer provider (Native Docker)
    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    workspace_id = "sonic-desktop-workstation"

    # Verify connection to workstation
    status = await provider.status(workspace_id)
    print(f"[+] Workstation Target: {workspace_id}")
    st_val = status.status.value if hasattr(status.status, "value") else str(status.status)
    print(f"[+] Operational State: {st_val}")
    print(f"[+] Active Window: {status.active_window}")
    print(f"[+] Active Application: {status.active_application}")
    print(f"[+] Running Processes: {len(status.running_processes)}")

    vnc_url = await provider.get_vnc_url(workspace_id)
    print(f"[+] Live Desktop Stream: {vnc_url}")

    # 2. Build model router and safety policy
    router = ModelRouter.from_config("configs/models.yaml")
    safety = ActionPolicy(
        workspace_root="/root",
        max_actions_per_minute=60,
        require_approval_for_intrusive=False,
    )
    security_tools = get_default_registry(provider).as_dict()

    # 3. Create ComputerUseAgent
    agent = ComputerUseAgent(
        computer_provider=provider,
        llm_router=router,
        safety=safety,
        security_tools=security_tools,
        self_host=True,
    )

    # 4. Define High-Level Autonomous Goal (CLI argument or default)
    default_goal = (
        "Inspect the cyber workstation environment: check architecture, "
        "inspect active services on ports 6080 and 5900, verify Google Chrome browser is installed and runnable, "
        "and summarize the workstation state."
    )
    goal = sys.argv[1] if len(sys.argv) > 1 else default_goal
    print(f"\n[!] Mission Goal:\n    {goal}\n")
    print("[*] Starting autonomous observe -> reason -> act cycle (5 steps)...\n")

    def on_step(trace):
        print(f"\n>>> [STEP EXECUTED]")
        print(f"    Action: {trace.action_type.value if hasattr(trace.action_type, 'value') else trace.action_type}")
        print(f"    Target: {trace.target_resource}")
        print(f"    Status: {trace.status}")
        preview = trace.actual_observation[:250].replace("\n", " ") if trace.actual_observation else "(empty)"
        print(f"    Result: {preview}")

    traces = await agent.run_mission(
        workspace_id=workspace_id,
        goal=goal,
        steps=5,
        step_callback=on_step,
    )

    print("\n" + "=" * 60)
    print(f"  Mission Complete! Total Steps Executed: {len(traces)}")
    print(f"  Goal Verified: {agent.goal_reached}")
    print(f"  Verification Score: {agent.metrics.verification_score:.2f}")
    print("=" * 60)

    for i, trace in enumerate(traces, 1):
        print(f"\n--- Step {i} ---")
        print(f"Action: {trace.action_type.value if hasattr(trace.action_type, 'value') else trace.action_type}")
        print(f"Target: {trace.target_resource}")
        print(f"Status: {trace.status}")
        obs_preview = trace.actual_observation[:200] + "..." if len(trace.actual_observation) > 200 else trace.actual_observation
        print(f"Observation:\n{obs_preview.strip()}")

    # Synthesize Mission Knowledge and Deliverables
    from sonic.mission_engine.trace_synthesis import synthesize_knowledge, synthesize_deliverables
    knowledge = synthesize_knowledge(goal, traces)
    deliverables = synthesize_deliverables("mission-workstation-001", goal, traces)

    print("\n" + "=" * 60)
    print(f"  Trace-Derived Mission Knowledge (Confidence: {knowledge.confidence * 100:.1f}%)")
    print("=" * 60)
    print("What We Know:")
    for item in knowledge.what_we_know:
        print(f"  - {item}")
    print(f"Deliverables Synthesized: {len(deliverables)}")

    # Write Markdown Report
    os.makedirs("reports", exist_ok=True)
    report_path = Path("reports/workstation_assessment_report.md")
    report_lines = [
        "# SONIC A-SEA — Cyber Workstation Assessment Report",
        "",
        f"**Workstation**: `{workspace_id}`  ",
        f"**Goal**: {goal}  ",
        f"**Goal Verified**: `{agent.goal_reached}`  ",
        f"**Verification Score**: `{agent.metrics.verification_score:.2f}`  ",
        f"**Confidence**: `{knowledge.confidence * 100:.1f}%`  ",
        f"**Actions Executed**: `{len(traces)}` (`{agent.metrics.actions_successful}` successful, `{agent.metrics.actions_failed}` failed)  ",
        "",
        "## Execution Trace Matrix",
        "",
        "| Step | Action Type | Target | Status | Actual Observation |",
        "|---|---|---|---|---|",
    ]
    for i, t in enumerate(traces, 1):
        act = t.action_type.value if hasattr(t.action_type, "value") else str(t.action_type)
        obs = t.actual_observation.replace("\n", " ").replace("|", "\\|")[:120]
        report_lines.append(f"| {i} | `{act}` | `{t.target_resource}` | **{t.status}** | {obs} |")

    report_lines.extend([
        "",
        "## Trace-Derived Knowledge",
        "",
    ])
    for item in knowledge.what_we_know:
        clean_item = item.replace("\n", " ")
        report_lines.append(f"- {clean_item}")

    report_lines.extend([
        "",
        "## Deliverables",
        "",
    ])
    if deliverables:
        for d in deliverables:
            report_lines.append(f"- **{d.title}** (`{d.deliverable_type.value}`): `{d.summary}`")
    else:
        report_lines.append("- *(No persistent file/commit deliverables produced; environment inspection completed.)*")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n[+] Assessment report successfully generated at: {report_path.resolve()}")
    print("[+] Autonomous Mission Execution Complete.")


if __name__ == "__main__":
    asyncio.run(main())
