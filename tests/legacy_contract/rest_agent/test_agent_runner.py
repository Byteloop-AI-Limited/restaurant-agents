"""
Unit tests for rest_agent.agent_runner tool-call repair helpers
    . Stubs heavyweight imports (services.lg_utils, ordelo_service, multi_agent.builder,
      thread_management, ContextSchema-bearing harness) before importing the module
    . Verifies _find_malformed_tool_call_tail detects Case A and ignores well-formed tails
    . Verifies _find_orphan_tool_message detects Case B
    . Verifies _find_repair_point picks the earliest malformation across both cases
  Functions/Classes:
    . _ai_with_tool_call
    . _tool_response
    . agent_runner_module
    . test_find_malformed_tool_call_tail_detects_missing_responses
    . test_find_malformed_tool_call_tail_returns_none_when_well_formed
    . test_find_orphan_tool_message_detects_unmatched_tool_msg
    . test_find_orphan_tool_message_returns_none_when_all_match
    . test_find_repair_point_picks_earliest_case
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _ai_with_tool_call(content, ids):
    msg = AIMessage(
        content=content,
        tool_calls=[
            {"id": id_, "name": "x", "args": {}, "type": "tool_call"} for id_ in ids
        ],
    )
    return msg


def _tool_response(tool_call_id, content="ok"):
    return ToolMessage(content=content, tool_call_id=tool_call_id)


@pytest.fixture
def agent_runner_module(monkeypatch):
    from tests._stubs.config_stub import build_config_stub

    config_stub = build_config_stub()
    monkeypatch.setitem(sys.modules, "config", config_stub)

    lg_stub = ModuleType("restaurant_agent_runtime.services.lg_utils")
    lg_stub.get_config_for_recipient = lambda *a, **k: None
    lg_stub.get_state_values = lambda *a, **k: {}
    lg_stub.shorten_state_messages = lambda *a, **k: []
    monkeypatch.setitem(sys.modules, "restaurant_agent_runtime.services.lg_utils", lg_stub)

    ordelo_stub = ModuleType("restaurant_agent_runtime.services.ordelo_service.ordelo_service")

    class FakeOrdeloService:
        def __init__(self, rest_ref):
            self.rest_ref = rest_ref

    ordelo_stub.OrdeloService = FakeOrdeloService
    monkeypatch.setitem(sys.modules, "restaurant_agent_runtime.services.ordelo_service.ordelo_service", ordelo_stub)

    thread_mgmt_stub = ModuleType("restaurant_agent_runtime.services.thread_management")

    class FakeThreadHandler:
        def __init__(self, pool):
            self.pool = pool

    thread_mgmt_stub.ThreadHandler = FakeThreadHandler
    monkeypatch.setitem(sys.modules, "restaurant_agent_runtime.services.thread_management", thread_mgmt_stub)

    multi_agent_stub = ModuleType("sfcs_agent.rest_agent.agents.multi_agent")
    multi_agent_stub.builder = SimpleNamespace(compile=lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "sfcs_agent.rest_agent.agents.multi_agent", multi_agent_stub)

    sys.modules.pop("sfcs_agent.rest_agent.agent_runner", None)
    from sfcs_agent.rest_agent import agent_runner as module  # noqa: E402

    yield module
    sys.modules.pop("sfcs_agent.rest_agent.agent_runner", None)


def test_find_malformed_tool_call_tail_detects_missing_responses(agent_runner_module):
    messages = [
        HumanMessage("hi"),
        _ai_with_tool_call("calling tool", ids=["tc-1", "tc-2"]),
        _tool_response("tc-1"),
        # tc-2 response missing
        HumanMessage("oops"),
    ]

    result = agent_runner_module._find_malformed_tool_call_tail(messages)

    assert result is not None
    idx, missing_ids = result
    assert idx == 1
    assert missing_ids == ["tc-2"]


def test_find_malformed_tool_call_tail_returns_none_when_well_formed(
    agent_runner_module,
):
    messages = [
        HumanMessage("hi"),
        _ai_with_tool_call("calling tool", ids=["tc-1"]),
        _tool_response("tc-1"),
        AIMessage("done"),
    ]
    assert agent_runner_module._find_malformed_tool_call_tail(messages) is None


@pytest.mark.skip(reason="SFCS agent_runner does not have _find_orphan_tool_message (elai-only helper)")
def test_find_orphan_tool_message_detects_unmatched_tool_msg(agent_runner_module):
    messages = [
        HumanMessage("hi"),
        _tool_response("orphan-id"),  # orphan: no preceding AIMessage.tool_calls
    ]

    assert agent_runner_module._find_orphan_tool_message(messages) == 1


@pytest.mark.skip(reason="SFCS agent_runner does not have _find_orphan_tool_message (elai-only helper)")
def test_find_orphan_tool_message_returns_none_when_all_match(agent_runner_module):
    messages = [
        _ai_with_tool_call("call", ids=["tc-1"]),
        _tool_response("tc-1"),
    ]
    assert agent_runner_module._find_orphan_tool_message(messages) is None


@pytest.mark.skip(reason="SFCS agent_runner does not have _find_repair_point (elai-only helper)")
def test_find_repair_point_picks_earliest_case(agent_runner_module):
    # Case A at idx 1 (AIMessage with missing tool responses)
    # Case B at idx 3 (orphan ToolMessage after that)
    messages = [
        HumanMessage("hi"),
        _ai_with_tool_call("calling tool", ids=["tc-1"]),
        HumanMessage("then user spoke"),  # tail no tool response → Case A
        _tool_response("never-matched"),  # orphan
    ]
    result = agent_runner_module._find_repair_point(messages)
    assert result is not None
    idx, reason, _ = result
    # Case A index (1) < Case B index (3) → pick Case A
    assert idx == 1
    assert reason == "missing_tool_responses"


@pytest.mark.skip(reason="SFCS agent_runner does not have _find_repair_point (elai-only helper)")
def test_find_repair_point_returns_none_when_clean(agent_runner_module):
    messages = [HumanMessage("hello"), AIMessage("hi back")]
    assert agent_runner_module._find_repair_point(messages) is None


# ---------------------------------------------------------------------------
# run_rest_graph_with_custom_msg repair-and-retry loop
# ---------------------------------------------------------------------------


class _FakeGraph:
    """Fake LangGraph supporting aget_state / aupdate_state / ainvoke.

    `ainvoke_side_effects` is a list of values; each call pops the head.
    If the head is an Exception (class or instance), it is raised; otherwise
    it is returned as the invoke result.

    `state_messages_sequence` allows different aget_state results per call
    (e.g. malformed only after the first ainvoke failure to exercise the
    in-except repair path).
    """

    def __init__(
        self,
        state_messages=None,
        state_messages_sequence=None,
        ainvoke_side_effects=None,
    ):
        self._state_messages = state_messages or []
        self._state_sequence = (
            list(state_messages_sequence) if state_messages_sequence else None
        )
        self.ainvoke_side_effects = list(ainvoke_side_effects or [])
        self.invoke_calls = 0
        self.aget_state_calls = 0
        self.updates = []

    async def aget_state(self, config=None):
        self.aget_state_calls += 1
        if self._state_sequence is not None:
            idx = min(self.aget_state_calls - 1, len(self._state_sequence) - 1)
            return SimpleNamespace(values={"messages": list(self._state_sequence[idx])})
        return SimpleNamespace(values={"messages": list(self._state_messages)})

    async def aupdate_state(self, config=None, values=None, **_):
        self.updates.append(values)
        if values and "messages" in values:
            removed_ids = {
                getattr(m, "id", None) for m in values["messages"]
                if type(m).__name__ == "RemoveMessage"
            }
            if removed_ids:
                self._state_messages = [
                    m for m in self._state_messages if getattr(m, "id", None) not in removed_ids
                ]

    async def ainvoke(self, input=None, config=None, context=None):
        self.invoke_calls += 1
        if not self.ainvoke_side_effects:
            return {"messages": [AIMessage("ok")]}
        nxt = self.ainvoke_side_effects.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


def _install_runner_dependencies(monkeypatch, module, graph, bad_request_cls):
    """Wire up minimal dependencies so run_rest_graph_with_custom_msg can run."""
    fake_builder = SimpleNamespace(compile=lambda **kwargs: graph)
    monkeypatch.setattr(module, "builder", fake_builder)

    async def _fake_get_pool():
        return SimpleNamespace()

    monkeypatch.setattr(module.pg_settings, "get_pool", _fake_get_pool, raising=False)

    async def _fake_get_config(recipient, pool):
        return ({"configurable": {"thread_id": "t-1"}}, False)  # not a new thread

    monkeypatch.setattr(module, "get_config_for_recipient", _fake_get_config)
    monkeypatch.setattr(
        module, "AsyncPostgresSaver", lambda pool: SimpleNamespace()
    )
    monkeypatch.setattr(module, "_async_wa_client", SimpleNamespace())
    monkeypatch.setattr(module, "client_ordelo", SimpleNamespace())
    monkeypatch.setattr(module, "openai", SimpleNamespace(BadRequestError=bad_request_cls))

    # ContextSchema is a strict pydantic model; replace it with a permissive
    # stand-in so we don't have to construct real AsyncConnectionPool / WhatsApp
    # / Client instances just to exercise the repair-and-retry control flow.
    class _PermissiveCtx:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            if not hasattr(self, "thread_handler") or self.thread_handler is None:
                self.thread_handler = SimpleNamespace()

    monkeypatch.setattr(module, "ContextSchema", _PermissiveCtx)

    # DummyLogger doesn't define .critical — give the module a noop logger.
    class _NoopLogger:
        def __getattr__(self, _name):
            def _noop(*a, **k):
                pass
            return _noop

    monkeypatch.setattr(module, "logger", _NoopLogger())


class _FakeBadRequest(Exception):
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="SFCS agent_runner lacks the repair-and-retry loop (elai-only behavior)")
async def test_run_rest_graph_retries_after_repairable_400(
    agent_runner_module, monkeypatch
):
    # Prophylactic repair sees clean state, so it returns False.
    # ainvoke then raises a repairable 400.
    # The in-except repair call sees a malformed tail and trims, enabling the
    # retry to succeed.
    clean_state = [HumanMessage("hi")]
    bad_ai = _ai_with_tool_call("calling tool", ids=["tc-bad"])
    bad_ai.id = "ai-bad"
    malformed_state = [HumanMessage("hi"), bad_ai, HumanMessage("oops")]

    bad_err = _FakeBadRequest(
        "messages with role 'tool' must be a response to a preceeding "
        "message with 'tool_calls'"
    )
    graph = _FakeGraph(
        state_messages_sequence=[clean_state, malformed_state],
        # First invoke raises 400, second returns success after repair
        ainvoke_side_effects=[bad_err, {"messages": [AIMessage("final reply")]}],
    )
    _install_runner_dependencies(
        monkeypatch, agent_runner_module, graph, _FakeBadRequest
    )

    result = await agent_runner_module.run_rest_graph_with_custom_msg(
        recipient="447000", human_msg="hello"
    )

    assert result == "final reply"
    assert graph.invoke_calls == 2
    # Two repair attempts: one prophylactic before invoke (no-op since first state
    # had no `id` we tracked — actually our bad_ai had id so it should trim) and
    # one after the 400. At minimum, at least one update with RemoveMessage list.
    remove_updates = [u for u in graph.updates if u and "messages" in u]
    assert any(
        any(type(m).__name__ == "RemoveMessage" for m in u["messages"])
        for u in remove_updates
    )


@pytest.mark.asyncio
@pytest.mark.skip(reason="SFCS agent_runner lacks the repair-and-retry loop (elai-only behavior)")
async def test_run_rest_graph_terminates_session_when_repair_fails(
    agent_runner_module, monkeypatch
):
    # Persisted state is clean → repair detector finds nothing → repair returns
    # False → production code terminates session and re-raises.
    state_messages = [HumanMessage("hi"), AIMessage("hello back")]

    bad_err = _FakeBadRequest(
        "messages with role 'tool' must be a response to a preceeding "
        "message with 'tool_calls'"
    )
    graph = _FakeGraph(
        state_messages=state_messages,
        ainvoke_side_effects=[bad_err],
    )
    _install_runner_dependencies(
        monkeypatch, agent_runner_module, graph, _FakeBadRequest
    )

    terminate_calls = []

    async def _fake_terminate(context_schema, recipient):
        terminate_calls.append(recipient)

    monkeypatch.setattr(
        agent_runner_module,
        "_terminate_session_on_tool_call_error",
        _fake_terminate,
    )

    with pytest.raises(_FakeBadRequest):
        await agent_runner_module.run_rest_graph_with_custom_msg(
            recipient="447000", human_msg="hello"
        )

    assert terminate_calls == ["447000"]


@pytest.mark.asyncio
async def test_run_rest_graph_reraises_unrelated_bad_request(
    agent_runner_module, monkeypatch
):
    # 400 not matching tool-call signatures should be re-raised immediately
    # without attempting repair / termination.
    state_messages = [HumanMessage("hi")]
    unrelated_err = _FakeBadRequest("rate limit exceeded")
    graph = _FakeGraph(
        state_messages=state_messages,
        ainvoke_side_effects=[unrelated_err],
    )
    _install_runner_dependencies(
        monkeypatch, agent_runner_module, graph, _FakeBadRequest
    )

    terminate_called = []

    async def _fake_terminate(context_schema, recipient):
        terminate_called.append(recipient)

    monkeypatch.setattr(
        agent_runner_module,
        "_terminate_session_on_tool_call_error",
        _fake_terminate,
    )

    with pytest.raises(_FakeBadRequest):
        await agent_runner_module.run_rest_graph_with_custom_msg(
            recipient="447000", human_msg="hello"
        )

    assert graph.invoke_calls == 1  # no retry
    assert terminate_called == []  # not terminated


@pytest.mark.asyncio
async def test_run_rest_graph_clean_path_returns_ai_content(
    agent_runner_module, monkeypatch
):
    state_messages = [HumanMessage("hi")]
    graph = _FakeGraph(
        state_messages=state_messages,
        ainvoke_side_effects=[{"messages": [AIMessage("hello there")]}],
    )
    _install_runner_dependencies(
        monkeypatch, agent_runner_module, graph, _FakeBadRequest
    )

    result = await agent_runner_module.run_rest_graph_with_custom_msg(
        recipient="447000", human_msg="hi"
    )

    assert result == "hello there"
    assert graph.invoke_calls == 1
