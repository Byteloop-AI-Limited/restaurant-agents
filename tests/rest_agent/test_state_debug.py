"""Tests for pure Restaurant Agent state-debug formatting."""

from langchain_core.messages import AIMessage, HumanMessage

from restaurant_agent_runtime.rest_agent.state_debug import (
    get_state_values,
    shorten_state_messages,
)


def test_get_state_values_excludes_messages():
    assert get_state_values(
        {"messages": [HumanMessage("hello")], "order_id": "ORD-1"}
    ) == {"order_id": "ORD-1"}


def test_shorten_state_messages_reverses_and_limits_fields():
    messages = [
        HumanMessage("hello", id="human-1"),
        AIMessage("welcome", id="assistant-1", additional_kwargs={"source": "test"}),
    ]

    assert shorten_state_messages(messages) == [
        {
            "AIMessage": {
                "content": "welcome",
                "additional_kwargs": {"source": "test"},
            }
        },
        {"HumanMessage": {"content": "hello", "additional_kwargs": {}}},
    ]

