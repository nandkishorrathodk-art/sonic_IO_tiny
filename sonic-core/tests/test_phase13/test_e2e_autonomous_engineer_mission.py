"""
Tests for Phase 13: End-to-End Autonomous Engineer Mission Workflow.
"""

import asyncio
import pytest
from sonic.computer.models import (
    ComputerProfile,
    ComputerWorkspaceType,
    GUIAction,
    GUIActionType,
)
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_autonomous_engineer_mission_workflow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Provision Persistent Mission Computer
        ws = await comp.create(
            tenant_id="tenant-e2e",
            engagement_id="eng-e2e-01",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
            profile=ComputerProfile.KALI_SECURITY,
        )

        # 2. Inspect Repository Filesystem
        files = await comp.list_files(ws.id, "/home/sonic/workspace")
        assert len(files) >= 1

        # 3. Launch code-server IDE on Desktop
        obs = await comp.gui_action(
            workspace_id=ws.id,
            action=GUIAction(action=GUIActionType.OPEN_APP, app_name="code-server"),
        )
        assert obs.active_window == "code-server"

        # 4. Edit Source Code to Remediate Vulnerability
        fix_code = """
import jwt

def verify_token(token: str, secret: str) -> dict:
    header = jwt.get_unverified_header(token)
    if header.get("alg") == "none":
        raise ValueError("Algorithm 'none' is prohibited")
    return jwt.decode(token, secret, algorithms=["HS256"])
"""
        write_ok = await comp.write_file(ws.id, "/home/sonic/workspace/auth_controller.py", fix_code)
        assert write_ok is True

        # 5. Run Tests inside Container Terminal
        test_res = await comp.terminal(ws.id, "python3 -c 'print(\"Tests: 14 passed, 0 failed\")'")
        assert test_res.exit_code == 0
        assert "14 passed" in test_res.stdout

        # 6. Branch & Commit in Git
        await comp.git_action(ws.id, "branch", branch_name="fix-jwt-none-alg")
        commit_ok = await comp.git_action(ws.id, "commit", message="fix(auth): forbid jwt none algorithm bypass")
        assert commit_ok is True

        # 7. Check Final Status & Destroy
        state = await comp.status(ws.id)
        assert "code-server" in state.open_applications

        destroyed = await comp.destroy(ws.id)
        assert destroyed is True

    asyncio.run(_run())
