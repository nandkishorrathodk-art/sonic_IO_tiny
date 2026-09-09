"""
Tests for the AI + control upgrades:

AI:
  1. LLM provider transient-error retry/backoff (429/5xx) and no-retry for
     auth/model-not-found.
  2. Robust tool-call argument parsing (malformed/noisy JSON).
  3. ReAct engine native function-calling path with PARALLEL tool execution.

Control:
  4. ComputerUseAgent screen-dimension tracking + coordinate bounds validation
     (off-screen / negative coordinates are BLOCKED and never reach the
     provider).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from sonic.agents.react_engine import ReActEngine, create_default_tool_registry
from sonic.computer.models import (
    ComputerState, FileEntry, GitStatusInfo, ScreenObservation,
)
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType
from sonic.llm.providers.custom import (
    CustomLLMProvider,
    _extract_json_object,
    _is_transient_error,
    parse_tool_arguments,
)
from sonic.llm.schemas import LLMRequest, LLMResponse, Message, MessageRole, ToolCall
from sonic.sandbox.provider import ExecResult


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Robust JSON parsing
# ---------------------------------------------------------------------------

def test_parse_tool_arguments_valid_json():
    assert parse_tool_arguments('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_tool_arguments_extracts_from_prose():
    raw = 'I will scan with: {"target": "example.com", "port": 443} now.'
    assert parse_tool_arguments(raw) == {"target": "example.com", "port": 443}


def test_parse_tool_arguments_trailing_comma_fixed():
    assert parse_tool_arguments('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_parse_tool_arguments_single_quotes_fixed():
    assert parse_tool_arguments("{'cmd': 'ls'}") == {"cmd": "ls"}


def test_parse_tool_arguments_none_and_empty():
    assert parse_tool_arguments(None) == {}
    assert parse_tool_arguments("") == {}


def test_parse_tool_arguments_bare_value_wrapped():
    # Non-JSON bare string is wrapped so dict-expecting callers still get text.
    assert parse_tool_arguments("nmap -sV target.com") == {"value": "nmap -sV target.com"}


def test_extract_json_object_returns_none_when_no_object():
    assert _extract_json_object("just words, no braces") is None
    assert _extract_json_object("") is None


# ---------------------------------------------------------------------------
# 2. Transient-error classification
# ---------------------------------------------------------------------------

def test_is_transient_rate_limit():
    assert _is_transient_error(RuntimeError("429 Too Many Requests")) is True
    assert _is_transient_error(RuntimeError("Rate limit exceeded")) is True


def test_is_transient_server_error():
    assert _is_transient_error(RuntimeError("503 Service Unavailable")) is True
    assert _is_transient_error(RuntimeError("502 Bad Gateway")) is True


def test_is_transient_transport_error():
    assert _is_transient_error(ConnectionError("Connection timeout")) is True


def test_non_transient_errors_not_flagged():
    # Auth / bad request / model-not-found must NOT be retried.
    assert _is_transient_error(RuntimeError("401 Unauthorized")) is False
    assert _is_transient_error(RuntimeError("model not found: foo-3")) is False
    assert _is_transient_error(ValueError("invalid api key")) is False


# ---------------------------------------------------------------------------
# 3. LLM provider retry/backoff
# ---------------------------------------------------------------------------

class _ScriptedClient:
    """A fake OpenAI-style SDK client that replays a scripted call sequence.

    ``responses`` is a list of either:
      - an LLMResponse-like object (returned on success), or
      - an Exception instance (raised).
    Each ``chat.completions.create`` call consumes the next item.
    """

    class _Choice:
        def __init__(self, content, tool_calls=None, finish="stop"):
            self.message = type("M", (), {
                "content": content,
                "tool_calls": tool_calls or None,
            })()
            self.finish_reason = finish

    class _Resp:
        def __init__(self, choice, usage=None):
            self.choices = [choice]
            self.usage = type("U", (), {
                "prompt_tokens": (usage or (0, 0, 0))[0],
                "completion_tokens": (usage or (0, 0, 0))[1],
                "total_tokens": (usage or (0, 0, 0))[2],
            })()

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        # Mirror the OpenAI SDK shape: provider._openai_client.chat.completions.create
        self.chat = type("C", (), {"completions": self})()

    async def create(self, **kwargs):
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _make_provider(monkeypatch_sleep, max_retries=3):
    """Build a CustomLLMProvider whose SDK client + sleep are injected for tests."""
    provider = CustomLLMProvider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        default_model="gpt-4o",
        max_retries=max_retries,
        retry_base_delay=0.0,  # no real waiting in tests
        retry_max_delay=0.0,
    )
    return provider


def test_provider_retries_on_rate_limit_then_succeeds(monkeypatch):
    # First call 429s, second succeeds.
    good = _ScriptedClient._Resp(_ScriptedClient._Choice("ok"))
    client = _ScriptedClient([RuntimeError("429 Too Many Requests"), good])
    provider = _make_provider(monkeypatch)
    provider._openai_client = client

    req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
    resp = _run(provider.complete(req))
    assert resp.content == "ok"
    assert client.calls == 2  # one retry


def test_provider_does_not_retry_auth_error(monkeypatch):
    bad = RuntimeError("401 Unauthorized")
    client = _ScriptedClient([bad])
    provider = _make_provider(monkeypatch)
    provider._openai_client = client

    req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
    with pytest.raises(RuntimeError, match="401"):
        _run(provider.complete(req))
    assert client.calls == 1  # no retry


def test_provider_retries_exhausted(monkeypatch):
    err = RuntimeError("503 Service Unavailable")
    client = _ScriptedClient([err, err, err, err])
    provider = _make_provider(monkeypatch, max_retries=3)
    provider._openai_client = client

    req = LLMRequest(messages=[Message(role=MessageRole.USER, content="hi")])
    with pytest.raises(RuntimeError, match="503"):
        _run(provider.complete(req))
    # initial attempt (1) + 3 retries = 4 total calls.
    assert client.calls == 4


# ---------------------------------------------------------------------------
# 4. ReAct native function-calling + parallel tool execution
# ---------------------------------------------------------------------------

class _ToolLLM:
    """Returns a sequence of LLMResponses with tool_calls / final answer."""

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []
        self._i = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        resp = self.responses[self._i]
        self._i += 1
        return resp


def _tc(name: str, arguments: dict, idx: int = 1) -> ToolCall:
    return ToolCall(id=f"call-{idx}-{name}", name=name, arguments=arguments)


def test_react_execute_with_tools_runs_parallel_tool_calls():
    """Multiple tool calls in one step are executed concurrently."""
    registry = create_default_tool_registry()
    # Replace handlers with counters + an ordering barrier to prove parallelism.
    barrier = asyncio.Event()

    seen = {"order": []}

    async def slow_curl(args):
        seen["order"].append(("curl_start", args))
        # Force a context switch so parallel execution overlaps.
        await asyncio.sleep(0)
        seen["order"].append(("curl_end", args))
        return "curl output"

    async def fast_nmap(args):
        seen["order"].append(("nmap_start", args))
        seen["order"].append(("nmap_end", args))
        return "nmap output"

    registry.tools["curl"].handler = slow_curl
    registry.tools["nmap"].handler = fast_nmap

    engine = ReActEngine(registry, max_iterations=5)

    step1 = LLMResponse(
        content="Running two tools in parallel.",
        tool_calls=[_tc("curl", {"args": "http://x"}), _tc("nmap", {"args": "-sV"})],
    )
    step2 = LLMResponse(content="done", tool_calls=[])
    llm = _ToolLLM([step1, step2])

    result = _run(engine.execute_with_tools("recon target", llm.complete))
    assert result["success"] is True
    assert result["steps"] == 2
    # Both tool calls recorded as observations in step 1.
    step1_obs = [o for o in result["observations"] if o["step"] == 1 and o["action_type"] == "tool_call"]
    assert len(step1_obs) == 2
    names = {o["action_input"].split("[")[0] for o in step1_obs}
    assert names == {"curl", "nmap"}
    # Parallel proof: the second tool started before the first ended.
    assert seen["order"].index(("nmap_start", "-sV")) < seen["order"].index(("curl_end", "http://x"))


def test_react_execute_with_tools_tool_schemas_sent():
    """The model request carries real tool definitions, not text parsing hints."""
    registry = create_default_tool_registry()
    engine = ReActEngine(registry, max_iterations=2)
    llm = _ToolLLM([LLMResponse(content="answer", tool_calls=[])])
    _run(engine.execute_with_tools("task", llm.complete))
    assert llm.requests, "think_fn should have been called"
    tools = llm.requests[0].tools
    assert tools and len(tools) == 5
    tool_names = {t.name for t in tools}
    assert {"nmap", "nuclei", "ffuf", "curl", "httpx"} == tool_names


def test_react_execute_with_tools_dict_args_coerced():
    """Dict arguments from function-calling reach handlers as their positional string."""
    registry = create_default_tool_registry()
    received = []

    async def capture(args):
        received.append(args)
        return "ok"

    registry.tools["curl"].handler = capture
    engine = ReActEngine(registry, max_iterations=2)
    step1 = LLMResponse(
        content="",
        tool_calls=[_tc("curl", {"args": "http://example.com"})],
    )

    step2 = LLMResponse(content="final", tool_calls=[])
    llm = _ToolLLM([step1, step2])
    result = _run(engine.execute_with_tools("task", llm.complete))
    assert result["success"] is True
    assert received == ["http://example.com"]


def test_react_execute_with_tools_max_iterations():
    registry = create_default_tool_registry()
    engine = ReActEngine(registry, max_iterations=2)
    # Always requests one tool, never answers.
    llm = _ToolLLM([
        LLMResponse(content="", tool_calls=[_tc("curl", {"args": "x"})]),
        LLMResponse(content="", tool_calls=[_tc("curl", {"args": "y"})]),
    ])
    result = _run(engine.execute_with_tools("task", llm.complete))
    assert result["success"] is False
    assert result["steps"] == 2


# ---------------------------------------------------------------------------
# 5. ComputerUseAgent coordinate bounds validation
# ---------------------------------------------------------------------------

class _StubComputer(ComputerProvider):
    """Minimal computer that records GUI actions and reports a fixed screen size."""

    def __init__(self, width=1920, height=1080):
        self.workspace_id = "ws"
        self.width = width
        self.height = height
        self.gui_calls: list[tuple[str, int, int]] = []

    async def create(self, *a, **k): return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, *a, **k): return True
    async def status(self, workspace_id):
        return ComputerState(workspace_id=workspace_id, tenant_id="t", active_application="x")
    async def screenshot(self, workspace_id):
        return ScreenObservation(width=self.width, height=self.height, visible_text="ui")
    async def gui_action(self, workspace_id, action, actor="operator"):
        self.gui_calls.append((action.action, action.x or 0, action.y or 0))
        return ScreenObservation(width=self.width, height=self.height)
    async def terminal(self, workspace_id, command, timeout=60, actor="operator"):
        return ExecResult(command=command, exit_code=0, stdout="", stderr="")
    async def read_file(self, *a, **k): return ""
    async def write_file(self, *a, **k): return True
    async def list_files(self, *a, **k): return [FileEntry(name="f", path="f")]
    async def git_action(self, *a, **k): return GitStatusInfo(branch="main", is_clean=True)
    async def process_list(self, *a, **k): raise NotImplementedError
    async def application_list(self, *a, **k): raise NotImplementedError
    async def launch_application(self, *a, **k): raise NotImplementedError
    async def close_application(self, *a, **k): raise NotImplementedError
    async def install_application(self, *a, **k): raise NotImplementedError
    async def uninstall_application(self, *a, **k): raise NotImplementedError
    async def service_action(self, *a, **k): raise NotImplementedError
    async def snapshot(self, *a, **k): raise NotImplementedError
    async def restore_snapshot(self, *a, **k): raise NotImplementedError


def test_coordinate_validation_tracks_screen_from_observe():
    comp = _StubComputer(width=1366, height=768)
    agent = ComputerUseAgent(computer_provider=comp)
    assert agent._screen_width == 1920  # default before observe
    _run(agent.observe(comp.workspace_id))
    assert agent._screen_width == 1366
    assert agent._screen_height == 768


def test_off_screen_click_is_blocked_not_executed():
    comp = _StubComputer(width=800, height=600)
    agent = ComputerUseAgent(computer_provider=comp)
    _run(agent.observe(comp.workspace_id))  # learn real screen size
    trace = _run(agent.execute_action(
        comp.workspace_id, ComputerActionType.GUI_CLICK, "900,500",
        {"x": 900, "y": 500}, "click button",
    ))
    assert trace.status == "BLOCKED"
    assert "out of bounds" in trace.actual_observation.lower() or "outside screen" in trace.actual_observation.lower()
    assert comp.gui_calls == []  # provider never touched


def test_negative_coordinates_blocked():
    comp = _StubComputer()
    agent = ComputerUseAgent(computer_provider=comp)
    trace = _run(agent.execute_action(
        comp.workspace_id, ComputerActionType.GUI_CLICK, "-10,20",
        {"x": -10, "y": 20}, "click",
    ))
    assert trace.status == "BLOCKED"
    assert comp.gui_calls == []


def test_in_bounds_click_executed():
    comp = _StubComputer(width=800, height=600)
    agent = ComputerUseAgent(computer_provider=comp)
    _run(agent.observe(comp.workspace_id))
    trace = _run(agent.execute_action(
        comp.workspace_id, ComputerActionType.GUI_CLICK, "100,200",
        {"x": 100, "y": 200}, "click",
    ))
    assert trace.status != "BLOCKED"
    assert len(comp.gui_calls) == 1
    assert comp.gui_calls[0][1] == 100 and comp.gui_calls[0][2] == 200


def test_non_coordinate_action_not_validated():
    """Terminal exec must never be blocked by coordinate validation."""
    comp = _StubComputer()
    agent = ComputerUseAgent(computer_provider=comp)
    trace = _run(agent.execute_action(
        comp.workspace_id, ComputerActionType.TERMINAL_EXEC, "term",
        {"command": "echo hi"}, "run",
    ))
    assert trace.status != "BLOCKED"
    assert "out of bounds" not in trace.actual_observation.lower()


def test_drag_off_screen_target_blocked():
    comp = _StubComputer(width=800, height=600)
    agent = ComputerUseAgent(computer_provider=comp)
    _run(agent.observe(comp.workspace_id))
    # Source in-bounds, drag target off-screen.
    trace = _run(agent.execute_action(
        comp.workspace_id, ComputerActionType.GUI_DRAG, "100,100",
        {"x": 100, "y": 100, "x2": 900, "y2": 100}, "drag",
    ))
    assert trace.status == "BLOCKED"
    assert comp.gui_calls == []


def test_coordinate_at_exact_edge_blocked():
    """x == width is out of bounds (0-indexed)."""
    comp = _StubComputer(width=800, height=600)
    agent = ComputerUseAgent(computer_provider=comp)
    _run(agent.observe(comp.workspace_id))
    trace = _run(agent.execute_action(
        comp.workspace_id, ComputerActionType.GUI_CLICK, "800,599",
        {"x": 800, "y": 599}, "click",
    ))
    assert trace.status == "BLOCKED"
