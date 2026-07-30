"""
Unit tests for pure LangGraph utility helpers
    . Loads lg_utils with stubbed config and OpenAI clients to avoid external side effects
    . Covers state extraction, recent-message slicing, JSON checks, config extraction, and deletion helpers
    . Verifies chain invocation and message-shortening behavior with real LangChain message classes
  Functions/Classes:
    . lg_utils_module
    . test_extract_state_fields_from_tool_msgs
    . test_extract_state_fields_returns_state_when_last_message_has_error
    . test_get_recent_messages_includes_previous_message_when_boundary_is_tool
    . test_get_state_values_excludes_messages
    . test_config_extractors_and_is_json
    . test_shorten_state_messages_reverses_and_limits_fields
    . test_delete_messages_only_when_more_than_three
    . test_call_agent_chain_wraps_response
    . test_formatted_response_model_defaults
"""

from types import ModuleType, SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


@pytest.fixture
def lg_utils_module(monkeypatch):
    config_stub = build_config_stub()

    openai_module = ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, *args, **kwargs):
            self.embeddings = SimpleNamespace(
                create=lambda **kw: SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.1, 0.2])]
                )
            )

    openai_module.OpenAI = FakeOpenAI

    langchain_openai = ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __call__(self, value):
            return value

        def bind_tools(self, *args, **kwargs):
            return lambda value: value

        def with_structured_output(self, *args, **kwargs):
            return lambda value: value

        def __ror__(self, other):
            return self

    langchain_openai.ChatOpenAI = FakeChatOpenAI

    thread_handlers_module = ModuleType("restaurant_agent_runtime.services.thread_handlers")
    thread_handlers_module.ThreadHandlerLocal = object

    thread_management_module = ModuleType("restaurant_agent_runtime.services.thread_management")
    thread_management_module.ThreadHandler = object

    return load_module(
        "test_lg_utils_module",
        "restaurant_agent_runtime.services/lg_utils.py",
        monkeypatch,
        {
            "config": config_stub,
            "openai": openai_module,
            "langchain_openai": langchain_openai,
            "restaurant_agent_runtime.services.thread_handlers": thread_handlers_module,
            "restaurant_agent_runtime.services.thread_management": thread_management_module,
        },
    )


def test_extract_state_fields_from_tool_msgs(lg_utils_module):
    state = {
        "messages": [
            HumanMessage("hello"),
            ToolMessage('{"state_fields": {"order_id": "ORD-1"}}', tool_call_id="1"),
            ToolMessage("not-json", tool_call_id="2"),
            AIMessage("done"),
        ]
    }

    assert lg_utils_module.extract_state_fields_from_tool_msgs(state) == {"order_id": "ORD-1"}
    assert lg_utils_module.extract_state_fields_from_tool_msgs({"messages": ["not-message"]}) == {}


def test_extract_state_fields_returns_state_when_last_message_has_error(lg_utils_module):
    state = {"messages": [AIMessage("Error: failed")], "order_id": "ORD-1"}

    assert lg_utils_module.extract_state_fields_from_tool_msgs(state) == state


def test_get_recent_messages_includes_previous_message_when_boundary_is_tool(lg_utils_module):
    messages = [
        HumanMessage("one"),
        ToolMessage("tool", tool_call_id="1"),
        AIMessage("two"),
        HumanMessage("three"),
    ]

    assert lg_utils_module.get_recent_messages(messages, num_msgs=2) == messages[-2:]
    assert lg_utils_module.get_recent_messages(messages, num_msgs=3) == messages
    assert lg_utils_module.get_recent_messages(messages, num_msgs=10) == messages


def test_get_state_values_excludes_messages(lg_utils_module):
    assert lg_utils_module.get_state_values({"messages": [], "order_id": "ORD-1"}) == {
        "order_id": "ORD-1"
    }


def test_config_extractors_and_is_json(lg_utils_module):
    config = {"configurable": {"thread_id": "thread-1", "recipient": "447"}}

    assert lg_utils_module.get_thread_from_config(config) == "thread-1"
    assert lg_utils_module.get_recipient_from_config(config) == "447"
    assert lg_utils_module.is_json("{}") is True
    assert lg_utils_module.is_json("not-json") is False


def test_shorten_state_messages_reverses_and_limits_fields(lg_utils_module):
    messages = [HumanMessage("hello"), AIMessage("world")]

    shortened = lg_utils_module.shorten_state_messages(messages)

    assert list(shortened[0]) == ["AIMessage"]
    assert shortened[0]["AIMessage"] == {"content": "world", "additional_kwargs": {}}
    assert list(shortened[1]) == ["HumanMessage"]


def test_delete_messages_only_when_more_than_three(lg_utils_module):
    short_state = {"messages": [HumanMessage("1"), HumanMessage("2"), HumanMessage("3")]}
    long_state = {
        "messages": [
            HumanMessage("1", id="1"),
            HumanMessage("2", id="2"),
            HumanMessage("3", id="3"),
            HumanMessage("4", id="4"),
        ]
    }

    assert lg_utils_module.delete_messages(short_state) is None
    deleted = lg_utils_module.delete_messages(long_state)
    assert len(deleted["messages"]) == 1
    assert deleted["messages"][0].id == "1"


def test_call_agent_chain_wraps_response(lg_utils_module):
    chain = SimpleNamespace(invoke=lambda state: AIMessage("response"))

    result = lg_utils_module.call_agent_chain({"messages": [HumanMessage("hi")]}, chain, {})

    assert result["messages"] == [AIMessage("response")]


def test_formatted_response_model_defaults(lg_utils_module):
    response = lg_utils_module.FormattedResponse(general_ai_response="hello")

    assert response.general_ai_response == "hello"
    assert response.options is None
