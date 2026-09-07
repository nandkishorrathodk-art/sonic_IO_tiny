"""
SONIC A-SEA — System 1 Motor Reflexes, Human Cadence & Hotkeys
===============================================================
Provides human-like motor reflexes, human typing cadence, hotkey navigation,
reflexive backtracking (modal dismissal / history back), and browser tab
budget hygiene for the SONIC Computer.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from sonic.computer.models import GUIAction, GUIActionType
from sonic.logger import get_logger

logger = get_logger(__name__)


class MotorReflexes:
    """System 1 Motor Reflexes and human physical cadence engine."""

    def __init__(self, computer: Any):
        self.computer = computer

    async def _exec_cmd(self, cmd: str, workspace_id: str = "") -> tuple[int, str, str]:
        """Execute a shell command via _docker_exec or terminal."""
        if hasattr(self.computer, "_docker_exec"):
            try:
                res = await self.computer._docker_exec(cmd)
                if isinstance(res, tuple) and len(res) >= 3:
                    return res
                elif isinstance(res, tuple) and len(res) == 2:
                    return res[0], res[1], ""
            except Exception:
                pass
        if hasattr(self.computer, "terminal"):
            try:
                res = await self.computer.terminal(workspace_id, cmd)
                if hasattr(res, "exit_code"):
                    return res.exit_code, getattr(res, "stdout", ""), getattr(res, "stderr", "")
            except Exception:
                pass
        return 1, "", "No execution method available"

    async def _send_hotkey(self, workspace_id: str, key: str) -> None:
        """Send a keyboard shortcut or keypress to the workstation."""
        safe_key = shlex.quote(key)
        cmd = f"DISPLAY=:99 xdotool key --clearmodifiers {safe_key}"
        if hasattr(self.computer, "_docker_exec"):
            try:
                res = await self.computer._docker_exec(cmd)
                if isinstance(res, tuple):
                    return
            except Exception:
                pass
        if hasattr(self.computer, "terminal"):
            try:
                await self.computer.terminal(workspace_id, cmd)
                return
            except Exception:
                pass
        if hasattr(self.computer, "gui_action"):
            await self.computer.gui_action(
                workspace_id, GUIAction(action=GUIActionType.KEYPRESS, key=key)
            )
            return

    async def human_type(self, workspace_id: str, text: str, delay_ms: int = 25) -> str:
        """
        Executes xdotool type --delay {delay_ms} --clearmodifiers {safe_text} via
        computer._docker_exec (or computer.gui_action). If delay_ms > 0, types with
        natural human cadence (preventing React debounce drops and anti-bot flags).
        """
        safe_text = shlex.quote(text)
        delay_arg = f"--delay {delay_ms} " if delay_ms > 0 else ""
        cmd = f"DISPLAY=:99 xdotool type {delay_arg}--clearmodifiers {safe_text}"

        if hasattr(self.computer, "_docker_exec"):
            try:
                res = await self.computer._docker_exec(cmd)
                if isinstance(res, tuple) and len(res) >= 2:
                    out = res[1]
                    return out.strip() if out and str(out).strip() else f"typed: {text}"
            except Exception:
                pass

        if hasattr(self.computer, "gui_action"):
            await self.computer.gui_action(
                workspace_id, GUIAction(action=GUIActionType.TYPE, text=text)
            )
            return f"typed: {text}"
        elif hasattr(self.computer, "terminal"):
            try:
                res = await self.computer.terminal(workspace_id, cmd)
                out = getattr(res, "stdout", "")
                return out.strip() if out and out.strip() else f"typed: {text}"
            except Exception:
                pass
        return f"typed: {text}"

    async def hotkey_navigate(self, workspace_id: str, url: str, delay_ms: int = 25) -> str:
        """
        Focuses address bar with Ctrl + L (hotkey), types URL with human cadence,
        then presses Return.
        """
        await self._send_hotkey(workspace_id, "ctrl+l")
        await asyncio.sleep(0.05)
        await self.human_type(workspace_id, url, delay_ms=delay_ms)
        await asyncio.sleep(0.05)
        await self._send_hotkey(workspace_id, "Return")
        return f"navigated: {url}"

    async def hotkey_close_tab(self, workspace_id: str) -> str:
        """Presses Ctrl + W to close the active browser tab."""
        await self._send_hotkey(workspace_id, "ctrl+w")
        return "closed_tab"

    async def hotkey_new_tab(self, workspace_id: str, url: str = "") -> str:
        """Presses Ctrl + T, and if url provided, hotkey_navigates to it."""
        await self._send_hotkey(workspace_id, "ctrl+t")
        if url:
            await asyncio.sleep(0.05)
            return await self.hotkey_navigate(workspace_id, url)
        return "new_tab"

    async def backtrack(self, workspace_id: str, reason: str = "modal_blocked") -> str:
        """
        Human reflexive backtracking: presses Escape (to dismiss modal/dialog).
        If reason is "wrong_page", sends Alt + Left (browser back).
        """
        if reason == "wrong_page":
            await self._send_hotkey(workspace_id, "alt+Left")
        else:
            await self._send_hotkey(workspace_id, "Escape")
        return f"backtracked: {reason}"

    async def backtrack_reflex(self, workspace_id: str, reason: str = "modal_blocked") -> str:
        """Alias for backtrack."""
        return await self.backtrack(workspace_id, reason)

    async def hotkey_switch_app(self, workspace_id: str) -> str:
        """Switch active window via Alt + Tab."""
        await self._send_hotkey(workspace_id, "alt+Tab")
        return "switched_app"

    async def enforce_tab_budget(self, workspace_id: str, max_tabs: int = 3) -> int:
        """
        Checks open browser windows/tabs. If count > max_tabs, closes excess tabs via Ctrl + W.
        Returns the number of excess tabs closed.
        """
        count = 0
        if hasattr(self.computer, "get_open_tab_count"):
            res = self.computer.get_open_tab_count(workspace_id)
            count = await res if asyncio.iscoroutine(res) else res
        elif hasattr(self.computer, "open_tabs"):
            val = getattr(self.computer, "open_tabs")
            count = len(val) if isinstance(val, (list, tuple, set)) else int(val)
        elif hasattr(self.computer, "tab_count"):
            val = getattr(self.computer, "tab_count")
            count = val() if callable(val) else int(val)
        else:
            code, out, _ = await self._exec_cmd(
                "DISPLAY=:99 wmctrl -l 2>/dev/null || wmctrl -l 2>/dev/null", workspace_id
            )
            if code == 0 and out.strip():
                for line in out.splitlines():
                    line_lower = line.lower()
                    if any(b in line_lower for b in ("chrome", "chromium", "google chrome")):
                        count += 1
            if count == 0 and hasattr(self.computer, "status"):
                try:
                    st = await self.computer.status(workspace_id)
                    if hasattr(st, "open_applications"):
                        for app in st.open_applications:
                            line_lower = str(app).lower()
                            if any(b in line_lower for b in ("chrome", "chromium", "google chrome")):
                                count += 1
                except Exception:
                    pass

        excess = max(0, count - max_tabs)
        for _ in range(excess):
            await self.hotkey_close_tab(workspace_id)
            await asyncio.sleep(0.02)
        return excess

