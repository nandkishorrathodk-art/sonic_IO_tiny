"""
SONIC-REDA — ReAct Agent Execution Engine
============================================
Real Observe → Think → Act → Observe autonomous loop with tool calling.
This is the CORE ENGINE that makes agents actually work.

Features:
    - Multi-step ReAct loop with configurable max iterations
    - Tool registry with typed tool definitions
    - Sandbox command execution via Virtual Computer
    - Automatic output parsing and graph memory ingestion
    - Safety checks before every tool invocation
    - Structured action/observation logging
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger
from sonic.llm.prompts import react_system_prompt
from sonic.llm.providers.custom import parse_tool_arguments
from sonic.llm.schemas import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall as LLMToolCall,
    ToolDefinition as LLMToolDefinition,
)
from sonic.sandbox.virtual_computer import DaytonaSandbox

logger = get_logger(__name__)


class ToolCategory(StrEnum):
    RECON = "recon"
    SCAN = "scan"
    FUZZ = "fuzz"
    EXPLOIT = "exploit"
    ANALYZE = "analyze"
    UTILITY = "utility"


@dataclass
class ToolDefinition:
    """A tool that an agent can invoke during the ReAct loop."""
    name: str
    description: str
    category: ToolCategory
    parameters: dict[str, str]  # param_name -> description
    handler: Callable[..., Coroutine[Any, Any, str]]  # async function returning string output


@dataclass
class Observation:
    """Result of a tool execution or thought step."""
    step: int
    action_type: str  # "think", "tool_call", "final_answer"
    action_input: str
    result: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_seconds: float = 0.0


class ToolRegistry:
    """Registry of available tools for agent execution."""

    def __init__(self):
        self.tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self.tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": t.name, "description": t.description, "category": t.category, "params": json.dumps(t.parameters)}
            for t in self.tools.values()
        ]

    def format_for_prompt(self) -> str:
        """Format tools for inclusion in LLM system prompt."""
        lines = ["Available Tools:"]
        for t in self.tools.values():
            params_str = ", ".join(f"{k}: {v}" for k, v in t.parameters.items())
            lines.append(f"  - {t.name}({params_str}): {t.description}")
        return "\n".join(lines)

    def to_llm_tool_definitions(self) -> list[LLMToolDefinition]:
        """Convert the registry into provider-agnostic tool schemas for native function-calling.

        Each registered tool becomes a JSON-schema function the LLM can call
        directly (instead of emitting ``Action: name[arg]`` text). The single
        positional argument the handler expects is exposed as a property named
        ``args`` plus each declared parameter, so models can pass either a
        free-form string or a structured object.
        """
        definitions: list[LLMToolDefinition] = []
        for t in self.tools.values():
            properties: dict[str, Any] = {
                "args": {
                    "type": "string",
                    "description": "Primary argument (free-form string) for the tool.",
                }
            }
            for param, desc in t.parameters.items():
                properties[param] = {"type": "string", "description": desc}
            definitions.append(LLMToolDefinition(
                name=t.name,
                description=t.description,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": ["args"],
                },
            ))
        return definitions


class ReActEngine:
    """
    Core ReAct (Reasoning + Acting) execution loop.
    Drives agents through iterative Observe → Think → Act cycles.
    """

    # Regex patterns for parsing LLM ReAct output
    THOUGHT_PATTERN = re.compile(r"Thought:\s*(.*?)(?=Action:|Observation:|Final Answer:|$)", re.DOTALL)
    ACTION_PATTERN = re.compile(r"Action:\s*(\w+)\[(.*?)\]", re.DOTALL)
    FINAL_ANSWER_PATTERN = re.compile(r"Final Answer:\s*(.*)", re.DOTALL)

    def __init__(
        self,
        tool_registry: ToolRegistry,
        sandbox: DaytonaSandbox | None = None,
        max_iterations: int = 10,
    ):
        self.tools = tool_registry
        self.sandbox = sandbox
        self.max_iterations = max_iterations

    def build_react_prompt(self, task_description: str, context: str = "") -> str:
        """Build the ReAct-format prompt for the LLM."""
        return react_system_prompt(
            self.tools.format_for_prompt(),
            self.max_iterations,
            context,
            task_description,
        )

    async def execute(
        self,
        task: str,
        think_fn: Callable[[str], Coroutine[Any, Any, str]],
        context: str = "",
    ) -> dict[str, Any]:
        """
        Run the full ReAct loop.

        Args:
            task: The task description
            think_fn: Async function that sends prompt to LLM and returns text response
            context: Additional context string

        Returns:
            Dict with 'answer', 'observations', 'steps', 'success'
        """
        observations: list[Observation] = []
        scratchpad = ""
        prompt = self.build_react_prompt(task, context)

        for step in range(1, self.max_iterations + 1):
            logger.info("react_step", step=step, max=self.max_iterations)

            # 1. THINK: Send accumulated context to LLM
            full_prompt = prompt + scratchpad
            start = datetime.now(UTC)

            try:
                llm_output = await think_fn(full_prompt)
            except Exception as e:
                logger.error("react_think_failed", step=step, error=str(e))
                observations.append(Observation(step=step, action_type="error", action_input="think", result=str(e)))
                break

            duration = (datetime.now(UTC) - start).total_seconds()

            # 2. PARSE: Extract thought, action, or final answer
            final_match = self.FINAL_ANSWER_PATTERN.search(llm_output)
            if final_match:
                answer = final_match.group(1).strip()
                observations.append(Observation(
                    step=step, action_type="final_answer",
                    action_input="", result=answer, duration_seconds=duration,
                ))
                logger.info("react_final_answer", step=step)
                return {
                    "answer": answer,
                    "observations": [obs.__dict__ for obs in observations],
                    "steps": step,
                    "success": True,
                }

            action_match = self.ACTION_PATTERN.search(llm_output)
            if action_match:
                tool_name = action_match.group(1).strip()
                tool_arg = action_match.group(2).strip()

                # 3. ACT: Execute the tool
                observation_text = await self._execute_tool(tool_name, tool_arg)
                observations.append(Observation(
                    step=step, action_type="tool_call",
                    action_input=f"{tool_name}[{tool_arg}]",
                    result=observation_text[:3000],
                    duration_seconds=duration,
                ))

                # 4. OBSERVE: Add result to scratchpad for next iteration
                thought_match = self.THOUGHT_PATTERN.search(llm_output)
                thought_text = thought_match.group(1).strip() if thought_match else ""

                scratchpad += f"\nThought: {thought_text}\nAction: {tool_name}[{tool_arg}]\nObservation: {observation_text[:2000]}\n"
            else:
                # LLM didn't follow format — add raw output and retry
                scratchpad += f"\n{llm_output}\n\nPlease respond with the correct format: Thought/Action/Final Answer.\n"
                observations.append(Observation(
                    step=step, action_type="malformed",
                    action_input="", result=llm_output[:500], duration_seconds=duration,
                ))

        # Max iterations reached
        logger.warning("react_max_iterations", steps=self.max_iterations)
        return {
            "answer": "Max iterations reached without final answer.",
            "observations": [obs.__dict__ for obs in observations],
            "steps": self.max_iterations,
            "success": False,
        }

    async def execute_continuous(
        self,
        task: str,
        think_fn: Callable[[str], Coroutine[Any, Any, str]],
        *,
        context: str = "",
        max_rounds: int = 3,
        on_round: Callable[[int, dict[str, Any]], str | None] | None = None,
        stop_when: Callable[[int, dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """
        Sustained, multi-round ReAct execution for autonomous pentesting.

        Unlike ``execute`` (which terminates on the first Final Answer), this
        loop treats each round's Final Answer as a *partial result* and feeds it
        back as context for the next round — so the agent keeps probing,
        pivoting, and chaining until:
          * ``stop_when`` returns True (e.g. a kill-chain is confirmed), or
          * ``max_rounds`` is exhausted, or
          * ``on_round`` returns a non-empty new task to continue with.

        Each round runs a full Thought/Action/Observation cycle (bounded by
        ``max_iterations``), so the engine never spins idle — it always either
        acts or stops.

        Returns the accumulated results of every round plus the final answer.
        """
        rounds: list[dict[str, Any]] = []
        running_context = context
        current_task = task
        final_answer = ""

        for round_idx in range(1, max_rounds + 1):
            logger.info("react_continuous_round", round=round_idx, max=max_rounds)
            round_result = await self.execute(current_task, think_fn, running_context)
            round_result["round"] = round_idx
            rounds.append(round_result)

            if round_result.get("success"):
                final_answer = round_result["answer"]

            # Caller-supplied stop condition (e.g. kill-chain confirmed).
            if stop_when is not None and stop_when(round_idx, round_result):
                logger.info("react_continuous_stop_when", round=round_idx)
                break

            # Caller-supplied continuation hook: return a new task to keep going.
            if on_round is not None:
                next_task = on_round(round_idx, round_result)
                if not next_task:
                    break
                current_task = next_task
            else:
                # No hook → feed the partial answer back as context and loop.
                running_context = (
                    f"Previous round produced: {round_result.get('answer', '')}"
                )

        return {
            "rounds": rounds,
            "total_steps": sum(r.get("steps", 0) for r in rounds),
            "rounds_run": len(rounds),
            "answer": final_answer or rounds[-1].get("answer", "") if rounds else "",
            "success": any(r.get("success") for r in rounds),
            "observations": [obs for r in rounds for obs in r.get("observations", [])],
        }

    # =============================================================
    # Native function-calling execution (parallel tool support)
    # =============================================================
    async def execute_with_tools(
        self,
        task: str,
        think_fn: Callable[[LLMRequest], Coroutine[Any, Any, LLMResponse]],
        *,
        system_prompt: str = "",
        context: str = "",
    ) -> dict[str, Any]:
        """Run the ReAct loop using NATIVE function-calling with parallel tool execution.

        Unlike the text-parsed ``execute`` (one ``Action: tool[arg]`` per step),
        this path:
          - Sends real tool schemas to the model (``LLMRequest.tools``).
          - Executes ALL tool_calls returned in a single step concurrently
            (``asyncio.gather``), so the agent can fan out independent probes.
          - Feeds each tool result back as a ``tool`` message keyed by call id,
            so multi-turn tool conversations stay correctly threaded.

        ``think_fn`` returns a provider-agnostic ``LLMResponse``; an empty
        ``tool_calls`` list with non-empty ``content`` is treated as the final
        answer, terminating the loop.

        Returns the same result shape as ``execute`` for drop-in use.
        """
        import asyncio as _asyncio

        observations: list[Observation] = []
        tool_defs = self.tools.to_llm_tool_definitions()
        messages: list[Message] = []
        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
        task_with_context = task
        if context:
            task_with_context = f"{task}\n\nAdditional Context:\n{context}"
        messages.append(Message(role=MessageRole.USER, content=task_with_context))

        for step in range(1, self.max_iterations + 1):
            logger.info("react_tools_step", step=step, max=self.max_iterations)
            start = datetime.now(UTC)

            try:
                request = LLMRequest(
                    messages=messages,
                    tools=tool_defs,
                    task_type="reasoning",
                )
                response = await think_fn(request)
            except Exception as e:
                logger.error("react_tools_think_failed", step=step, error=str(e))
                observations.append(Observation(
                    step=step, action_type="error", action_input="think", result=str(e),
                ))
                break

            duration = (datetime.now(UTC) - start).total_seconds()

            # No tool calls → the model is answering.
            if not response.tool_calls:
                answer = (response.content or "").strip()
                observations.append(Observation(
                    step=step, action_type="final_answer",
                    action_input="", result=answer, duration_seconds=duration,
                ))
                logger.info("react_tools_final_answer", step=step)
                return {
                    "answer": answer,
                    "observations": [obs.__dict__ for obs in observations],
                    "steps": step,
                    "success": bool(answer),
                }

            # Append the assistant turn (with its tool calls) for correct history.
            messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content or "",
            ))
            # NOTE: tool_calls are carried on the request-level response; the
            # message history here only needs content + the tool results below.

            # Execute every requested tool in parallel — independent probes no
            # longer serialize one per step.
            tool_calls = response.tool_calls
            coros = [
                self._execute_tool(tc.name, tc.arguments) for tc in tool_calls
            ]
            results = await _asyncio.gather(*coros, return_exceptions=False)

            for tc, result in zip(tool_calls, results, strict=True):
                arg_repr = tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments)
                observations.append(Observation(
                    step=step, action_type="tool_call",
                    action_input=f"{tc.name}[{arg_repr}]",
                    result=result[:3000], duration_seconds=duration,
                ))
                # Feed the result back as a tool-role message keyed by call id.
                messages.append(Message(
                    role=MessageRole.TOOL,
                    content=result[:2000],
                    tool_call_id=tc.id,
                    name=tc.name,
                ))

            logger.info("react_tools_step_executed",
                        step=step, n_tools=len(tool_calls))

        logger.warning("react_tools_max_iterations", steps=self.max_iterations)
        return {
            "answer": "Max iterations reached without final answer.",
            "observations": [obs.__dict__ for obs in observations],
            "steps": self.max_iterations,
            "success": False,
        }

    async def _execute_tool(self, tool_name: str, argument: str | dict[str, Any]) -> str:
        """Execute a registered tool or sandbox command.

        ``argument`` may be a free-form string (legacy text-parsed ReAct) or a
        dict of structured arguments (native function-calling path). For dict
        arguments, the tool receives the ``args`` field (or the first declared
        parameter) as its positional string, matching the handler signature.
        """
        tool = self.tools.get(tool_name)
        arg_str = self._coerce_tool_argument(argument, tool)

        if tool_name == "bash" or tool_name == "shell":
            # Direct sandbox execution
            if self.sandbox:
                result = await self.sandbox.execute(arg_str, timeout=60)
                return f"Exit Code: {result.exit_code}\nSTDOUT:\n{result.stdout[:2000]}\nSTDERR:\n{result.stderr[:500]}"
            else:
                return "ERROR: No sandbox available for shell execution."

        if tool:
            try:
                return await tool.handler(arg_str)
            except Exception as e:
                return f"ERROR: Tool {tool_name} failed: {str(e)}"

        return f"ERROR: Unknown tool '{tool_name}'. Available: {', '.join(self.tools.tools.keys())}, bash"

    @staticmethod
    def _coerce_tool_argument(
        argument: str | dict[str, Any], tool: ToolDefinition | None,
    ) -> str:
        """Reduce a string-or-dict tool argument to the positional string handlers expect."""
        if isinstance(argument, dict):
            if "args" in argument and isinstance(argument["args"], str):
                return argument["args"]
            if tool and tool.parameters:
                first_param = next(iter(tool.parameters))
                if first_param in argument and isinstance(argument[first_param], str):
                    return argument[first_param]
            # Fall back to a compact representation so the handler still gets text.
            return json.dumps(argument, sort_keys=True)
        return str(argument)


def create_default_tool_registry(sandbox: DaytonaSandbox | None = None) -> ToolRegistry:
    """Create a registry with standard security testing tools."""
    registry = ToolRegistry()

    async def run_nmap(args: str) -> str:
        if sandbox:
            res = await sandbox.execute(f"nmap {args}", timeout=120)
            return res.stdout + res.stderr
        raise RuntimeError("No isolated sandbox is attached; nmap execution is unavailable")

    async def run_nuclei(args: str) -> str:
        if sandbox:
            res = await sandbox.execute(f"nuclei {args}", timeout=180)
            return res.stdout + res.stderr
        raise RuntimeError("No isolated sandbox is attached; nuclei execution is unavailable")

    async def run_ffuf(args: str) -> str:
        if sandbox:
            res = await sandbox.execute(f"ffuf {args}", timeout=120)
            return res.stdout + res.stderr
        raise RuntimeError("No isolated sandbox is attached; ffuf execution is unavailable")

    async def run_curl(args: str) -> str:
        if sandbox:
            res = await sandbox.execute(f"curl -s {args}", timeout=30)
            return res.stdout[:3000]
        raise RuntimeError("No isolated sandbox is attached; HTTP execution is unavailable")

    async def run_httpx(args: str) -> str:
        if sandbox:
            res = await sandbox.execute(f"httpx {args}", timeout=60)
            return res.stdout + res.stderr
        raise RuntimeError("No isolated sandbox is attached; httpx execution is unavailable")

    registry.register(ToolDefinition(
        name="nmap", description="Port scan and service detection",
        category=ToolCategory.RECON,
        parameters={"args": "nmap arguments (e.g., '-sV -p 80,443 target.com')"},
        handler=run_nmap,
    ))
    registry.register(ToolDefinition(
        name="nuclei", description="Run vulnerability templates against target",
        category=ToolCategory.SCAN,
        parameters={"args": "nuclei arguments (e.g., '-u http://target.com -t cves/')"},
        handler=run_nuclei,
    ))
    registry.register(ToolDefinition(
        name="ffuf", description="Web fuzzer for directory and parameter discovery",
        category=ToolCategory.FUZZ,
        parameters={"args": "ffuf arguments (e.g., '-u http://target.com/FUZZ -w wordlist.txt')"},
        handler=run_ffuf,
    ))
    registry.register(ToolDefinition(
        name="curl", description="Send HTTP requests and inspect responses",
        category=ToolCategory.UTILITY,
        parameters={"args": "curl arguments (e.g., '-X POST http://target.com/api')"},
        handler=run_curl,
    ))
    registry.register(ToolDefinition(
        name="httpx", description="HTTP toolkit for tech detection and probing",
        category=ToolCategory.RECON,
        parameters={"args": "httpx arguments (e.g., '-u http://target.com -title -tech-detect')"},
        handler=run_httpx,
    ))

    return registry
