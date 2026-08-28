"""
Unit tests for Reality Fixes — InMemoryGraph, ReAct Engine, and Swarm Runner.
"""

import asyncio
import pytest
from sonic.memory.inmemory import InMemoryGraph
from sonic.memory.schemas import AssetNode, AssetType, EngagementNode, FindingNode, FindingSeverity, FindingStatus
from sonic.agents.react_engine import ReActEngine, ToolRegistry, ToolDefinition, ToolCategory, create_default_tool_registry


def test_inmemory_graph_full_lifecycle():
    """Test that InMemoryGraph provides the same API as GraphMemory."""
    async def _run():
        mem = InMemoryGraph()
        await mem.connect()
        assert mem.is_connected is True

        # Create engagement
        eng = EngagementNode(name="Test Engagement", target="target.com", scope="{}")
        eng_id = await mem.create_engagement(eng)
        assert eng_id is not None

        # Create asset
        asset = AssetNode(
            asset_type=AssetType.DOMAIN, value="target.com",
            name="Target", discovered_by="recon-01", engagement_id=eng_id,
        )
        asset_id = await mem.create_asset(asset)
        assert asset_id is not None

        # Find assets
        assets = await mem.find_assets(eng_id)
        assert len(assets) >= 1
        assert assets[0]["value"] == "target.com"

        # Upsert (duplicate check)
        dup_id = await mem.upsert_asset(asset)
        assert dup_id == asset_id  # Same node, not duplicated

        # Create finding
        finding = FindingNode(
            title="XSS in search", description="Reflected XSS",
            vulnerability_class="XSS", severity=FindingSeverity.HIGH,
            status=FindingStatus.NEEDS_VERIFICATION, confidence_score=85,
            poc="<script>alert(1)</script>", impact="Cookie theft",
            found_by="static-01", engagement_id=eng_id,
        )
        fnd_id = await mem.create_finding(finding)
        assert fnd_id is not None

        # Search findings
        findings = await mem.find_findings(eng_id, severity="high")
        assert len(findings) >= 1

        # Stats
        stats = await mem.get_stats()
        assert stats["connected"] is True
        assert stats["total_nodes"] >= 3

    asyncio.run(_run())


def test_react_engine_execution():
    """Test that ReAct engine parses LLM output and calls tools."""
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=3)

        call_count = 0

        async def mock_think(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Thought: I need to scan the target first.\nAction: nmap[-sV target.com]"
            elif call_count == 2:
                return 'Thought: Scan complete. I have enough info.\nFinal Answer: {"ports": [22, 80, 443], "status": "completed"}'
            return "Final Answer: {}"

        result = await engine.execute(
            task="Scan target.com and identify open ports",
            think_fn=mock_think,
        )

        assert result["success"] is True
        assert result["steps"] == 2
        assert len(result["observations"]) == 2
        assert result["observations"][0]["action_type"] == "tool_call"
        assert "nmap" in result["observations"][0]["action_input"]
        assert result["observations"][1]["action_type"] == "final_answer"

    asyncio.run(_run())


def test_react_engine_max_iterations():
    """Test that ReAct engine stops at max iterations."""
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=2)

        async def always_act(prompt: str) -> str:
            return "Thought: Keep scanning.\nAction: nmap[-sV target.com]"

        result = await engine.execute(task="Infinite test", think_fn=always_act)
        assert result["success"] is False
        assert result["steps"] == 2

    asyncio.run(_run())
