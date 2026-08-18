"""Contract tests for the shared Restaurant Agent composition boundary."""

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from restaurant_agent_runtime import GraphAdapter
from restaurant_agent_runtime.rest_agent import RestaurantPrompts
from tests._stubs.loader import load_module


REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeAgent:
    def __init__(self, name):
        self.name = name
        self.calls = []

    async def ainvoke(self, state):
        self.calls.append(state)
        return {"agent": self.name, "state": state}


@pytest.fixture
def core_runner(monkeypatch):
    captured = {"agents": {}, "graphs": []}

    def agent_module(module_name, build_name, agent_name):
        module = ModuleType(module_name)

        def build_agent(**kwargs):
            captured["agents"][agent_name] = kwargs
            return FakeAgent(agent_name)

        setattr(module, build_name, build_agent)
        return module

    multi_agent = ModuleType("restaurant_agent_runtime.rest_agent.agents.multi_agent")

    def build_multi_agent_graph(**nodes):
        captured["graphs"].append(nodes)
        return SimpleNamespace(nodes=nodes, compile=lambda **_: None)

    multi_agent.build_multi_agent_graph = build_multi_agent_graph
    multi_agent.DINEIN_AGENT = "dinein_agent"

    harness = ModuleType("restaurant_agent_runtime.rest_agent.agents.agent_harness")
    harness.ContextSchema = object

    state_debug = ModuleType("restaurant_agent_runtime.rest_agent.state_debug")
    state_debug.get_state_values = None
    state_debug.shorten_state_messages = None

    graph_config = ModuleType(
        "restaurant_agent_runtime.services.thread_management.graph_config"
    )
    graph_config.get_config_for_recipient = None

    ordelo_service = ModuleType(
        "restaurant_agent_runtime.services.ordelo_service.ordelo_service"
    )
    ordelo_service.OrdeloService = object

    thread_management = ModuleType(
        "restaurant_agent_runtime.services.thread_management"
    )
    thread_management.ThreadHandler = object

    activity = SimpleNamespace(
        AGENT_RUNS="agent_runs",
        tracked=lambda *_args, **_kwargs: lambda fn: fn,
    )
    watomation = ModuleType("restaurant_agent_runtime.watomation")
    watomation.activity = activity

    module = load_module(
        "core_agent_runner_under_test",
        "packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py",
        monkeypatch,
        {
            "restaurant_agent_runtime.rest_agent.agents.agent_harness": harness,
            "restaurant_agent_runtime.rest_agent.agents.delivery": agent_module(
                "restaurant_agent_runtime.rest_agent.agents.delivery",
                "build_delivery_agent",
                "delivery_agent",
            ),
            "restaurant_agent_runtime.rest_agent.agents.dine_in": agent_module(
                "restaurant_agent_runtime.rest_agent.agents.dine_in",
                "build_dinein_agent",
                "dinein_agent",
            ),
            "restaurant_agent_runtime.rest_agent.agents.multi_agent": multi_agent,
            "restaurant_agent_runtime.rest_agent.agents.takeaway": agent_module(
                "restaurant_agent_runtime.rest_agent.agents.takeaway",
                "build_takeaway_agent",
                "takeaway_agent",
            ),
            "restaurant_agent_runtime.rest_agent.agents.triage": agent_module(
                "restaurant_agent_runtime.rest_agent.agents.triage",
                "build_triage_agent",
                "triage_agent",
            ),
            "restaurant_agent_runtime.rest_agent.state_debug": state_debug,
            "restaurant_agent_runtime.services.ordelo_service.ordelo_service": (
                ordelo_service
            ),
            "restaurant_agent_runtime.services.thread_management": thread_management,
            "restaurant_agent_runtime.services.thread_management.graph_config": (
                graph_config
            ),
            "restaurant_agent_runtime.watomation": watomation,
        },
    )
    module._captured = captured
    module.logger = SimpleNamespace(
        critical=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
    )
    return module


def _runtime(model, *, reservation_base_url=None):
    return SimpleNamespace(
        settings=SimpleNamespace(
            llm=SimpleNamespace(llm_client_single_tool_turn=model)
        ),
        presentation=SimpleNamespace(
            restaurant_selection=None, reservation_base_url=reservation_base_url
        ),
    )


def _ai_with_tool_calls(*tool_call_ids):
    return AIMessage(
        content="calling tools",
        id="assistant-call",
        tool_calls=[
            {"id": tool_call_id, "name": "tool", "args": {}, "type": "tool_call"}
            for tool_call_id in tool_call_ids
        ],
    )


@pytest.mark.parametrize("field", ("triage", "delivery", "takeaway"))
def test_restaurant_prompts_reject_empty_values(field):
    values = {"triage": "triage", "delivery": "delivery", "takeaway": "takeaway"}
    values[field] = "  "

    with pytest.raises(ValueError, match=f"{field} prompt must not be empty"):
        RestaurantPrompts(**values)


def test_adapter_builds_standard_agents_once_with_runtime_model(core_runner):
    model = object()
    runtime = _runtime(model)
    prompts = RestaurantPrompts("triage", "delivery", "takeaway")
    custom_tool = object()

    adapter = core_runner.RestaurantGraphAdapter(
        runtime,
        prompts=prompts,
        extra_tools_by_agent={"triage_agent": [custom_tool]},
    )

    assert isinstance(adapter, GraphAdapter)
    assert adapter.runtime is runtime
    assert len(core_runner._captured["graphs"]) == 1
    assert core_runner._captured["agents"] == {
        "triage_agent": {
            "model": model,
            "system_prompt": "triage",
            "extra_tools": [custom_tool],
            "restaurant_selection": None,
            "dinein_enabled": False,
        },
        "delivery_agent": {
            "model": model,
            "system_prompt": "delivery",
            "extra_tools": (),
            "dinein_enabled": False,
        },
        "takeaway_agent": {
            "model": model,
            "system_prompt": "takeaway",
            "extra_tools": (),
            "dinein_enabled": False,
        },
    }


@pytest.mark.asyncio
async def test_adapter_uses_a_complete_native_agent_override(core_runner):
    override = FakeAgent("custom-delivery")
    adapter = core_runner.RestaurantGraphAdapter(
        _runtime(object()),
        prompts=RestaurantPrompts("triage", "delivery", "takeaway"),
        agent_overrides={"delivery_agent": override},
    )

    assert "delivery_agent" not in core_runner._captured["agents"]
    result = await adapter.graph_builder.nodes["delivery_agent_node"]({"order": 1})
    assert result == {"agent": "custom-delivery", "state": {"order": 1}}


@pytest.mark.parametrize(
    "kwargs,match",
    (
        ({"extra_tools_by_agent": {"unknown": []}}, "unknown standard agent"),
        (
            {
                "extra_tools_by_agent": {"triage_agent": []},
                "agent_overrides": {"triage_agent": FakeAgent("triage")},
            },
            "cannot add tools to replaced agents",
        ),
        (
            {"agent_overrides": {"triage_agent": object()}},
            "agent override must define ainvoke",
        ),
    ),
)
def test_adapter_rejects_invalid_customization(core_runner, kwargs, match):
    with pytest.raises(ValueError, match=match):
        core_runner.RestaurantGraphAdapter(
            _runtime(object()),
            prompts=RestaurantPrompts("triage", "delivery", "takeaway"),
            **kwargs,
        )


def test_adapter_rejects_dinein_prompt_without_reservation_base_url(core_runner):
    prompts = RestaurantPrompts("triage", "delivery", "takeaway", dinein="dinein")

    with pytest.raises(ValueError, match="reservation_base_url"):
        core_runner.RestaurantGraphAdapter(
            _runtime(object(), reservation_base_url=None),
            prompts=prompts,
        )


def test_adapter_accepts_dinein_prompt_with_reservation_base_url(core_runner):
    prompts = RestaurantPrompts("triage", "delivery", "takeaway", dinein="dinein")

    adapter = core_runner.RestaurantGraphAdapter(
        _runtime(object(), reservation_base_url="https://example.test"),
        prompts=prompts,
    )

    assert isinstance(adapter, GraphAdapter)


def test_malformed_tool_call_detection_finds_missing_response(core_runner):
    messages = [
        HumanMessage("hello"),
        _ai_with_tool_calls("call-1", "call-2"),
        ToolMessage("done", tool_call_id="call-1"),
        HumanMessage("interrupted"),
    ]

    assert core_runner._find_malformed_tool_call_tail(messages) == (
        1,
        "missing_tool_responses",
        ["call-2"],
    )


def test_malformed_tool_call_detection_accepts_complete_tool_turns(core_runner):
    messages = [
        HumanMessage("hello"),
        _ai_with_tool_calls("call-1", "call-2"),
        ToolMessage("done", tool_call_id="call-1"),
        ToolMessage("done", tool_call_id="call-2"),
        AIMessage("finished"),
    ]

    assert core_runner._find_malformed_tool_call_tail(messages) is None


def test_malformed_tool_call_detection_finds_orphan_response(core_runner):
    messages = [
        HumanMessage("hello"),
        ToolMessage("orphan", tool_call_id="call-1"),
        AIMessage("finished"),
    ]

    assert core_runner._find_malformed_tool_call_tail(messages) == (
        1,
        "orphan_tool_response",
        ["call-1"],
    )


def test_malformed_tool_call_detection_rewinds_unexpected_response(core_runner):
    messages = [
        HumanMessage("hello"),
        _ai_with_tool_calls("call-1"),
        ToolMessage("wrong", tool_call_id="call-2"),
    ]

    assert core_runner._find_malformed_tool_call_tail(messages) == (
        1,
        "unexpected_tool_response",
        ["call-2", "call-1"],
    )


def test_malformed_tool_call_detection_finds_extra_response(core_runner):
    messages = [
        _ai_with_tool_calls("call-1"),
        ToolMessage("done", tool_call_id="call-1"),
        ToolMessage("duplicate", tool_call_id="call-1"),
    ]

    assert core_runner._find_malformed_tool_call_tail(messages) == (
        2,
        "orphan_tool_response",
        ["call-1"],
    )


@pytest.mark.asyncio
async def test_malformed_tool_call_repair_removes_the_persisted_tail(core_runner):
    valid = HumanMessage("valid", id="valid-prefix")
    orphan = ToolMessage("orphan", tool_call_id="call-1", id="orphan-tool")
    later = AIMessage("later", id="later-message")
    updates = []

    class Graph:
        async def aget_state(self, config):
            return SimpleNamespace(values={"messages": [valid, orphan, later]})

        async def aupdate_state(self, **kwargs):
            updates.append(kwargs)

    repaired = await core_runner._repair_malformed_tool_call_tail(
        Graph(), {"configurable": {"thread_id": "thread-1"}}
    )

    assert repaired is True
    assert updates[0]["as_node"] == "toolNode"
    assert [message.id for message in updates[0]["values"]["messages"]] == [
        "orphan-tool",
        "later-message",
    ]


@pytest.mark.asyncio
async def test_malformed_tool_call_repair_refuses_idless_tail(core_runner):
    orphan = ToolMessage("orphan", tool_call_id="call-1")
    updates = []

    class Graph:
        async def aget_state(self, config):
            return SimpleNamespace(values={"messages": [orphan]})

        async def aupdate_state(self, **kwargs):
            updates.append(kwargs)

    repaired = await core_runner._repair_malformed_tool_call_tail(
        Graph(), {"configurable": {"thread_id": "thread-1"}}
    )

    assert repaired is False
    assert updates == []


@pytest.mark.parametrize(
    "message",
    (
        "An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'.",
        "Invalid parameter: messages with role 'tool' must be a response to a preceeding message with 'tool_calls'.",
        "Invalid parameter: messages with role 'tool' must be a response to a preceding message with 'tool_calls'.",
    ),
)
def test_tool_protocol_error_recognizes_openai_variants(core_runner, message):
    error = SimpleNamespace(body={"message": message})

    assert core_runner._is_tool_protocol_error(error) is True


def test_tool_protocol_error_rejects_unrelated_bad_request(core_runner):
    error = SimpleNamespace(body={"message": "Invalid model parameter."})

    assert core_runner._is_tool_protocol_error(error) is False


@pytest.mark.asyncio
async def test_tool_protocol_error_repairs_and_retries_once(core_runner, monkeypatch):
    class FakeBadRequestError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.body = {"message": message}

    error = FakeBadRequestError(
        "Invalid parameter: messages with role 'tool' must be a response "
        "to a preceeding message with 'tool_calls'."
    )
    graph = SimpleNamespace(
        ainvoke=AsyncMock(
            side_effect=[error, {"messages": [AIMessage("recovered")]}]
        )
    )
    core_runner.ContextSchema = lambda **kwargs: SimpleNamespace(
        **kwargs, thread_handler=AsyncMock()
    )
    core_runner.AsyncPostgresSaver = lambda _pool: object()
    core_runner._repair_malformed_tool_call_tail = AsyncMock(
        side_effect=[False, True]
    )
    monkeypatch.setattr(core_runner.openai, "BadRequestError", FakeBadRequestError)
    runtime = SimpleNamespace(
        async_wa_client=object(),
        identity=SimpleNamespace(rest_ref="SFCS"),
        presentation=SimpleNamespace(
            display_name="SFCS",
            logo_url=None,
            contact_phone=None,
            delivery_button_label="Delivery",
            takeaway_button_label="Collection",
            enquiry_button_label="More options",
            delivery_promo_caption="20% off delivery",
            takeaway_promo_caption="Get started with your collection order",
            enquiry_menu=object(),
            restaurant_selection=None,
            reservation_base_url=None,
        ),
        settings=SimpleNamespace(
            project=object(),
            payment=object(),
            database_client=object(),
        ),
        operational_lookups=SimpleNamespace(
            get_restaurant_master=lambda: object()
        ),
    )
    graph_builder = SimpleNamespace(compile=lambda **_: graph)

    result = await core_runner.run_rest_graph_with_custom_msg(
        recipient="447000000001",
        pool=object(),
        config={"configurable": {"thread_id": "thread-1"}},
        human_msg="hello",
        runtime=runtime,
        graph_builder=graph_builder,
    )

    assert result == "recovered"
    assert graph.ainvoke.await_count == 2
    assert core_runner._repair_malformed_tool_call_tail.await_count == 2


@pytest.mark.asyncio
async def test_persist_only_updates_state_without_invoking_the_model(core_runner):
    updates = []
    graph = SimpleNamespace(
        aupdate_state=AsyncMock(side_effect=lambda config, values: updates.append((config, values)))
    )
    core_runner.AsyncPostgresSaver = lambda _pool: object()
    core_runner.get_config_for_recipient = AsyncMock(
        return_value=({"configurable": {"thread_id": "thread-1"}}, False)
    )
    core_runner._repair_malformed_tool_call_tail = AsyncMock(return_value=False)
    graph_builder = SimpleNamespace(compile=lambda **_: graph)
    runtime = SimpleNamespace(
        settings=SimpleNamespace(database=SimpleNamespace(get_pool=AsyncMock(return_value=object()))),
        identity=SimpleNamespace(rest_ref="SFCS"),
    )

    result = await core_runner.run_rest_graph_with_custom_msg(
        recipient="447000000001",
        msgs=[HumanMessage("I want takeaway")],
        state_update_dict={"active_agent": "takeaway_agent"},
        persist_only=True,
        runtime=runtime,
        graph_builder=graph_builder,
    )

    assert result is None
    assert updates == [
        (
            {"configurable": {"thread_id": "thread-1"}},
            {
                "active_agent": "takeaway_agent",
                "messages": [HumanMessage("I want takeaway")],
            },
        )
    ]


def test_core_agent_runtime_never_imports_an_application_package():
    package_root = (
        REPO_ROOT
        / "packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent"
    )
    source = "\n".join(path.read_text() for path in package_root.rglob("*.py"))

    assert "sfcs_agent" not in source
    assert "bnat_agent" not in source
