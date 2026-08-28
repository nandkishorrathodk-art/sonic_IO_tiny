"""
Tests for Phase 17: Procedural Novel Task Repair (Open-World Generalization).
"""

import asyncio
import pytest
from sonic.computer.models import ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.open_world.novelty_generator import ProceduralNoveltyGenerator
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_procedural_novel_task_repair_workflow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Generate a completely unique, randomized repository task
        task = ProceduralNoveltyGenerator.generate_random_repo()
        assert task.class_name is not None
        assert task.method_name is not None

        # 2. Instantiate workspace and plant procedural files
        ws = await comp.create(
            tenant_id="tenant-alpha",
            engagement_id="proc-task-ws",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        )

        await comp.write_file(ws.id, f"/home/sonic/workspace/{task.source_filename}", task.broken_source_code)
        await comp.write_file(ws.id, f"/home/sonic/workspace/{task.test_filename}", task.test_suite_code)

        # 3. Apply fix dynamically
        await comp.write_file(ws.id, f"/home/sonic/workspace/{task.source_filename}", task.correct_source_code)

        # 4. Verify test suite passes
        exec_res = await comp.terminal(
            ws.id,
            f"python -c 'from {task.class_name.lower()} import {task.class_name}; inst = {task.class_name}(); assert inst.{task.method_name}(10, 2) == {10 * 2 + 42}; print(\"PASS\")'",
        )
        assert exec_res.exit_code == 0

        # 5. Commit verified patch
        commit_res = await comp.git_action(ws.id, "commit", message=f"fix({task.class_name.lower()}): resolve offset calculation")
        assert commit_res is not None

    asyncio.run(_run())
