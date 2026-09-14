"""
SONIC-REDA — Toolsmith Loop (Phase A → AIOSR)
=============================================
The "toolsmith" leg of the AI-Human: the being authors a NEW small tool
(scanner / fuzzer / parser) when it finds an observation gap that NO existing
registered tool covers. The authored tool is persisted via ``BeingCraft``
(survives restart) and registered into the ``SecurityToolRegistry`` — but
ONLY after it actually runs and produces non-empty output in the sandbox.

This is the single highest-leverage step converting SONIC from an "Operator"
(orchestrating known tools) toward an "Independent Offensive Security
Researcher" (building its own tools).

HONESTY INVARIANT (the part that matters most):
    An authored tool is recorded as ``reproduced=True`` and entered into the
    ``SecurityToolRegistry`` ONLY after ``confirm_and_register()`` runs it in
    the sandbox and gets exit 0 with non-empty stdout. A fail-closed (exit 126),
    failed, or empty-output run leaves ``reproduced=False`` and the tool is NOT
    registered — never claim "tool authored and working" by decree. This is the
    same anti-theatrical discipline enforced in ``production_gate``.

SECURITY INVARIANT:
    The authored source is run strictly inside the sandbox provider (never on
    the host). Malicious source (e.g. ``os.system("rm -rf /")``) is contained
    by the sandbox, and the sandbox provider's own fail-closed gate already
    blocks destructive commands before they reach the shell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sonic.llm.prompts import toolsmith_system_prompt
from sonic.logger import get_logger

logger = get_logger(__name__)

# A modest safety lint over the authored source. This is NOT a sandbox (the
# sandbox is the real guard); it is a cheap first filter that rejects source
# obviously not meant as a security tool (e.g. host-wiping). The provider's
# fail-closed gate is the authoritative guard.
_FORBIDDEN_SOURCE_PATTERNS = [
    re.compile(r"\brm\s+-rf\b[^ ]*\s+['\"]?/(['\"]|\s|$)"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=.+of=/dev/"),
]


@dataclass
class AuthoredTool:
    """A tool the being authored itself (source + provenance + run state)."""
    name: str
    source: str            # the Python the being authored
    rationale: str         # why it was needed (the observation gap)
    discovered_by: str = "self_authored"
    reproduced: bool = False
    run_output: str = ""
    run_exit_code: int | None = None
    craft_note_id: str | None = None
    # Provenance timestamps for the audit trail — when the tool was authored
    # and when it was empirically confirmed in-sandbox. Empty until the event
    # occurs so the ledger cannot claim a confirmation that never happened.
    authored_at: str = ""
    confirmed_at: str = ""
    confirmed_workspace_id: str = ""


def _is_valid_tool_name(name: str, existing: set[str] | None = None) -> bool:
    """Tool names must be lowercase identifiers and not collide with live tools."""
    if not name or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return False
    return name not in (existing or set())


def _source_safety_lint(source: str) -> tuple[bool, str]:
    """Cheap pre-sandbox lint. Returns (ok, reason). Not authoritative."""
    if not source or "def " not in source and "import " not in source:
        return False, "source has no def/import — not a runnable tool"
    for pat in _FORBIDDEN_SOURCE_PATTERNS:
        m = pat.search(source)
        if m:
            return False, f"forbidden pattern in source: {m.group(0)!r}"
    return True, "ok"


class ToolsmithLoop:
    """Author + confirm + register self-made security tools.

    Args:
        craft:     the being's durable craft store (host-side persistence).
        llm:       an LLM router (ModelRouter) used to propose tool source.
        registry:  the SecurityToolRegistry the being can later call tools from.
    """

    def __init__(self, craft: Any, llm: Any, registry: Any = None):
        self.craft = craft
        self.llm = llm
        self.registry = registry
        self.authored: list[AuthoredTool] = []

    # ------------------------------------------------------------------
    def _existing_tool_names(self) -> set[str]:
        names: set[str] = set()
        if self.registry is not None and hasattr(self.registry, "names"):
            names.update(self.registry.names())
        names.update(t.name for t in self.authored if t.reproduced)
        return names

    async def _llm_propose_tool(
        self,
        observation: str,
        failed_attempts: list[str],
        existing: set[str],
    ) -> dict[str, str] | None:
        """Ask the LLM to propose a NOVEL small Python tool for the gap.

        Returns ``{"name", "source", "rationale"}`` or ``None`` if the LLM
        declines / proposes a duplicate / proposes a reserved name. The proposal
        is explicitly biased away from ``existing`` so the being does not
        duplicate a capability that is already registered.
        """
        from sonic.llm.schemas import LLMRequest, Message, MessageRole

        existing_str = ", ".join(sorted(existing)) or "(none)"
        system = toolsmith_system_prompt(existing_str)
        user = (
            f"Observation:\n{observation}\n\n"
            f"Failed attempts:\n{(chr(10).join(failed_attempts) or '(none)')}\n"
        )
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system),
                Message(role=MessageRole.USER, content=user),
            ],
            task_type="reasoning",
        )
        try:
            response = await self.llm.complete(request)
        except Exception as e:
            logger.warning("toolsmith_llm_failed", error=str(e))
            return None

        text = getattr(response, "content", "") or ""
        if "DECLINE" in text.strip().splitlines()[0:1]:
            return None
        return self._parse_proposal(text, existing)

    @staticmethod
    def _parse_proposal(text: str, existing: set[str]) -> dict[str, str] | None:
        """Parse the LLM proposal into name/rationale/source. None on any flaw."""
        # NAME
        name = None
        for line in text.splitlines():
            if line.strip().upper().startswith("NAME:"):
                name = line.split(":", 1)[1].strip().lower()
                break
        if not name or not _is_valid_tool_name(name, existing):
            return None
        # RATIONALE
        rationale = ""
        for line in text.splitlines():
            if line.strip().upper().startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
                break
        # SOURCE: everything after the SOURCE: marker.
        src_idx = None
        for i, line in enumerate(text.splitlines()):
            if line.strip().upper().startswith("SOURCE:"):
                src_idx = i
                break
        if src_idx is None:
            return None
        source = "\n".join(text.splitlines()[src_idx + 1:]).strip()
        if not source:
            return None
        # Strip markdown code fences (```python ... ``` and ``` ... ```)
        if "```" in source:
            source = re.sub(r"^`{3,}(?:python|py)?\s*\n?", "", source.strip(), flags=re.IGNORECASE).strip()
            source = re.sub(r"\n?`{3,}\s*$", "", source).strip()
        if not source:
            return None
        ok, reason = _source_safety_lint(source)
        if not ok:
            logger.info("toolsmith_proposal_rejected", name=name, reason=reason)
            return None
        return {"name": name, "rationale": rationale or f"gap-filling tool {name}", "source": source}

    # ------------------------------------------------------------------
    async def author_tool_for_gap(
        self,
        observation: str,
        failed_attempts: list[str] | None = None,
        name: str | None = None,
        source: str | None = None,
        rationale: str | None = None,
    ) -> AuthoredTool | None:
        """Propose + persist a novel tool for the observation gap.

        Supports both direct source provision (when the agent or caller authors
        custom code directly) and LLM-driven proposal for an observation gap.

        Persists the source to BeingCraft immediately (durable across restart)
        but does NOT register into the SecurityToolRegistry until
        ``confirm_and_register`` runs it successfully. Returns ``None`` when no
        novel tool is warranted (honest skip — never fabricates a tool).
        """
        failed_attempts = failed_attempts or []
        existing = self._existing_tool_names()

        if name and source:
            clean_name = str(name).strip().lower()
            if not _is_valid_tool_name(clean_name, existing):
                logger.info("toolsmith_direct_authoring_rejected_name", name=clean_name)
                return None
            clean_source = source
            if "```" in clean_source:
                clean_source = re.sub(r"^`{3,}(?:python|py)?\s*\n?", "", clean_source.strip(), flags=re.IGNORECASE).strip()
                clean_source = re.sub(r"\n?`{3,}\s*$", "", clean_source).strip()
            ok, reason = _source_safety_lint(clean_source)
            if not ok:
                logger.info("toolsmith_direct_authoring_rejected_lint", name=clean_name, reason=reason)
                return None
            spec = {
                "name": clean_name,
                "source": clean_source,
                "rationale": rationale or f"Custom authored tool {clean_name}",
            }
        else:
            spec = await self._llm_propose_tool(observation, failed_attempts, existing)

        if spec is None:
            logger.info("toolsmith_no_novel_tool", existing_count=len(existing))
            return None

        tool = AuthoredTool(
            name=spec["name"], source=spec["source"], rationale=spec["rationale"],
            authored_at=datetime.now(UTC).isoformat(),
        )
        # Persist the authored source as a durable craft note (host-side).
        if self.craft is not None and hasattr(self.craft, "author"):
            note = self.craft.author(
                title=f"Tool: {tool.name}",
                body=f"# rationale\n{tool.rationale}\n\n# source\n```python\n{tool.source}\n```\n",
                kind="tool",
            )
            tool.craft_note_id = getattr(note, "note_id", None)
        self.authored.append(tool)
        logger.info("toolsmith_tool_authored", name=tool.name, confirmed=False)
        return tool

    async def author_tool(
        self,
        observation: str,
        failed_attempts: list[str] | None = None,
        name: str | None = None,
        source: str | None = None,
        rationale: str | None = None,
    ) -> AuthoredTool | None:
        """Alias for author_tool_for_gap to support direct authoring / generation."""
        return await self.author_tool_for_gap(
            observation=observation,
            failed_attempts=failed_attempts,
            name=name,
            source=source,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    async def confirm_and_register(
        self,
        tool: AuthoredTool,
        provider: Any,
        workspace_id: str,
        timeout: int = 60,
        target: str | None = None,
    ) -> AuthoredTool:
        """Run the authored tool in-sandbox. Register ONLY on a successful,
        non-empty run. Never register by decree.

        The authored source is written under the workspace toolsmith dir and
        executed with the provider's fail-closed ``execute`` (exit 126 => the
        sandbox blocked it, e.g. a destructive command — the tool stays
        unconfirmed and is NOT registered).
        """
        if provider is None or not hasattr(provider, "execute"):
            return tool  # nothing to run against — stays unconfirmed
        path = f"/home/sonic/workspace/toolsmith/{tool.name}.py"
        try:
            if hasattr(provider, "write_file"):
                await provider.write_file(workspace_id, path, tool.source)
        except Exception as e:
            logger.warning("toolsmith_write_failed", name=tool.name, error=str(e))
            return tool

        target_arg = target or getattr(tool, "target", None) or "127.0.0.1"
        try:
            res = await provider.execute(workspace_id, f"python {path} {target_arg}", timeout=timeout)
        except Exception as e:
            logger.warning("toolsmith_run_failed", name=tool.name, error=str(e))
            return tool

        tool.run_exit_code = getattr(res, "exit_code", None)
        tool.run_output = getattr(res, "stdout", "") or ""

        # Honest guard: only exit 0 + non-empty output counts as confirmed.
        output_lower = tool.run_output.lower()
        failure_markers = [
            "connection refused",
            "command not found",
            "syntaxerror",
            "traceback",
            "usage:",
            "error:",
        ]
        has_failure = any(marker in output_lower for marker in failure_markers)

        if tool.run_exit_code == 0 and tool.run_output.strip() and not has_failure:
            tool.reproduced = True
            tool.confirmed_at = datetime.now(UTC).isoformat()
            tool.confirmed_workspace_id = workspace_id
            adapter = AuthoredToolAdapter(tool, provider)
            if self.registry is not None and hasattr(self.registry, "register"):
                self.registry.register(tool.name, adapter)
            logger.info(
                "toolsmith_tool_confirmed", name=tool.name,
                exit_code=tool.run_exit_code, registered=True,
            )
        else:
            logger.info(
                "toolsmith_tool_not_confirmed", name=tool.name,
                exit_code=tool.run_exit_code,
                reason="blocked" if tool.run_exit_code == 126 else ("failure-output" if has_failure else "empty-or-failed"),
            )
        return tool


# ---------------------------------------------------------------------------
# Adapter: makes a confirmed authored tool callable like a real SecurityTool
# ---------------------------------------------------------------------------

class AuthoredToolAdapter:
    """A SecurityTool-shaped adapter wrapping a confirmed authored tool.

    Implements the SecurityTool contract (name/version/build_command/parse_output/
    execute) bound to the provider that confirmed it, so the being can call its
    own tools through the same ``SECURITY_TOOL`` action path it uses for
    preinstalled scanners. Zero host execution, exit 126 => BLOCKED.
    """

    def __init__(self, tool: AuthoredTool, provider: Any):
        self._tool = tool
        self.provider = provider

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def version(self) -> str:
        return "self-authored"

    def build_command(self, request: Any) -> str:
        # The authored source is already on disk in the sandbox; just run it.
        # Pass the target as argv[1] so the authored tool can read it.
        target = getattr(request, "target", "") or ""
        safe_target = str(target).replace("'", "")
        return f"python /home/sonic/workspace/toolsmith/{self._tool.name}.py '{safe_target}'"

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Parse each non-empty stdout line as a finding (the authored tool's
        own output format). Tools that emit JSON lines get parsed as JSON."""
        import json as _json
        findings: list[dict[str, Any]] = []
        for line in raw_stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(_json.loads(line))
            except Exception:
                findings.append({"finding": line, "source": self._tool.name})
        return findings

    async def execute(self, request: Any):
        """Execute the authored tool in-sandbox (fail-closed, zero host execution).

        Implements a duck-typed ToolResult matching the SecurityTool interface
        without requiring rigid wrapper classes or base-class inheritance.
        """
        from types import SimpleNamespace

        start_dt = datetime.now(UTC)
        cmd = self.build_command(request)
        timeout = getattr(request, "timeout_seconds", 60)
        workspace_id = getattr(request, "workspace_id", "")
        execution_id = getattr(request, "execution_id", "")
        tenant_id = getattr(request, "tenant_id", "")

        logger.info(
            "authored_tool_execution_started",
            tool=self.name,
            execution_id=execution_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )

        try:
            exec_res = await self.provider.execute(
                workspace_id,
                cmd,
                timeout=timeout,
            )
        except TypeError:
            exec_res = await self.provider.execute(
                workspace_id=workspace_id,
                command=cmd,
                timeout=timeout,
            )

        end_dt = datetime.now(UTC)
        duration = (end_dt - start_dt).total_seconds()

        exit_code = getattr(exec_res, "exit_code", 0)
        stdout = getattr(exec_res, "stdout", "") or ""
        stderr = getattr(exec_res, "stderr", "") or ""
        timed_out = getattr(exec_res, "timed_out", False)

        if timed_out:
            status = "timed_out"
            err = f"Tool execution timed out after {timeout}s"
        elif exit_code == 126:
            status = "blocked"
            err = stderr or "Execution blocked by fail-closed security engine"
        elif exit_code != 0 and not stdout:
            status = "failed"
            err = stderr or f"Tool exited with code {exit_code}"
        else:
            status = "completed"
            err = None

        parsed_data = []
        if stdout:
            try:
                parsed_data = self.parse_output(stdout, stderr)
            except Exception as e:
                logger.error("authored_tool_output_parsing_failed", tool=self.name, error=str(e))
                err = f"Output parsing error: {str(e)}"

        return SimpleNamespace(
            execution_id=execution_id,
            tenant_id=tenant_id,
            engagement_id=getattr(request, "engagement_id", ""),
            workspace_id=workspace_id,
            agent_id=getattr(request, "agent_id", ""),
            tool_name=self.name,
            tool_version=self.version,
            status=status,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            exit_code=exit_code,
            raw_stdout=stdout,
            raw_stderr=stderr,
            parsed_data=parsed_data,
            error_message=err,
            error=err,
            metrics=SimpleNamespace(
                duration_seconds=round(duration, 2),
                exit_code=exit_code,
                bytes_received=len(stdout.encode("utf-8", errors="replace")),
            ),
        )


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

async def author_tool(
    observation: str,
    craft: Any = None,
    llm: Any = None,
    registry: Any = None,
    failed_attempts: list[str] | None = None,
    name: str | None = None,
    source: str | None = None,
    rationale: str | None = None,
) -> AuthoredTool | None:
    """Convenience helper to author a tool using a ToolsmithLoop."""
    loop = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    return await loop.author_tool(
        observation=observation,
        failed_attempts=failed_attempts,
        name=name,
        source=source,
        rationale=rationale,
    )
