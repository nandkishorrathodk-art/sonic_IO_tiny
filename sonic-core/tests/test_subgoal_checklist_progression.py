"""
Unit tests for SubGoalChecklist decomposition, progression, failure tracking, and replan advancing.
"""

import pytest
from sonic.computer_use.models import (
    SubGoal,
    SubGoalStatus,
    SubGoalChecklist,
    ActionExecutionStatus,
    ComputerDecisionTrace,
    ComputerActionType,
)
from sonic.computer_use.agent import ComputerUseAgent


def test_subgoal_checklist_model_progression():
    sg1 = SubGoal(description="Navigate to target")
    sg2 = SubGoal(description="Search for item")
    sg3 = SubGoal(description="Verify results")

    checklist = SubGoalChecklist(
        top_level_goal="Find item on target",
        sub_goals=[sg1, sg2, sg3],
        active_index=0,
    )

    assert checklist.active_sub_goal() == sg1
    assert not checklist.is_all_completed()

    # Render prompt
    rendered = checklist.render_prompt_markdown()
    assert "[>] Sub-Goal 1: Navigate to target" in rendered
    assert "[ ] Sub-Goal 2: Search for item" in rendered

    # Advance after step 1 completes
    assert checklist.mark_active_completed(evidence="Page loaded successfully")
    assert sg1.status == SubGoalStatus.COMPLETED
    assert sg1.evidence == "Page loaded successfully"
    assert checklist.active_sub_goal() == sg2
    assert sg2.status == SubGoalStatus.IN_PROGRESS

    # Complete step 2
    assert checklist.mark_active_completed(evidence="Search results visible")
    assert checklist.active_sub_goal() == sg3

    # Complete step 3
    assert checklist.mark_active_completed(evidence="Item verified")
    assert checklist.is_all_completed()


@pytest.mark.asyncio
async def test_agent_goal_decomposition_numbered():
    agent = ComputerUseAgent.__new__(ComputerUseAgent)
    agent.llm_router = None

    prompt = (
        "Complete these steps:\n"
        "1. Open the browser and go to https://example.com\n"
        "2. Click the login button\n"
        "3. Enter test credentials and submit"
    )

    checklist = await agent.decompose_goal(prompt)
    assert len(checklist.sub_goals) == 3
    assert "Open the browser" in checklist.sub_goals[0].description
    assert "Click the login button" in checklist.sub_goals[1].description
    assert "Enter test credentials" in checklist.sub_goals[2].description
    assert checklist.active_index == 0


@pytest.mark.asyncio
async def test_agent_goal_decomposition_web_intent():
    agent = ComputerUseAgent.__new__(ComputerUseAgent)
    agent.llm_router = None

    prompt = "Go to https://opensea.io and search for doodles"
    checklist = await agent.decompose_goal(prompt)
    assert len(checklist.sub_goals) >= 2
    assert any("https://opensea.io" in sg.description for sg in checklist.sub_goals)


def test_agent_replan_advances_failed_subgoal():
    agent = ComputerUseAgent.__new__(ComputerUseAgent)
    agent._replan_count = 0
    agent._consecutive_failures = 3
    agent.history = []
    
    sg1 = SubGoal(description="Attempt broken method")
    sg2 = SubGoal(description="Alternative method")
    agent.checklist = SubGoalChecklist(
        top_level_goal="Test replan",
        sub_goals=[sg1, sg2],
        active_index=0,
    )

    agent._inject_replan("Test replan")

    assert agent._replan_count == 1
    assert agent._consecutive_failures == 0
    assert sg1.status == SubGoalStatus.FAILED
    assert agent.checklist.active_index == 1
    assert agent.checklist.active_sub_goal() == sg2
    assert len(agent.history) == 1
    assert agent.history[0]["action"] == "REPLAN"
