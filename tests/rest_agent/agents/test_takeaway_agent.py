"""
Unit tests for takeaway agent tool logic
    . Loads takeaway agent with stubbed config, harness, and create_agent dependencies
    . Avoids compiling or invoking real LLM-backed agents
    . Covers payment status branch classification and agent construction inputs
  Functions/Classes:
    . takeaway_module
    . test_verify_if_payment_complete_branch_outputs
    . test_takeaway_agent_is_constructed_with_expected_tools_and_prompt
"""

import pytest
from pathlib import Path

from tests._stubs.agent_stubs import (
    build_agent_harness_stub,
    build_langchain_agents_stub,
)
from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


@pytest.fixture
def takeaway_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.project_settings.project_root = str(Path(__file__).resolve().parents[3])
    harness_stub = build_agent_harness_stub()
    langchain_agents_stub = build_langchain_agents_stub()

    module = load_module(
        "test_takeaway_agent_module",
        "restaurant_agent_runtime.rest_agent/agents/takeaway.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_runtime.rest_agent.agents.agent_harness": harness_stub,
            "langchain.agents": langchain_agents_stub,
        },
    )
    module._langchain_agents_stub = langchain_agents_stub
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,expected",
    [
        (
            {"order_summary": {"items": []}, "payment_link": "https://pay", "is_payment_successful": True},
            "Payment complete",
        ),
        (
            {"order_summary": {"items": []}, "payment_link": "https://pay", "is_payment_successful": False},
            "Awaiting Payment",
        ),
        ({"payment_link": "https://pay"}, "User to place food order on WhatsApp"),
        (
            {"order_summary": {"items": []}},
            "payment link not sent, AI to send the payment link using tool `get_payment_link`",
        ),
    ],
)
async def test_verify_if_payment_complete_branch_outputs(takeaway_module, state, expected):
    result = await takeaway_module.verify_if_payment_complete(
        tool_call_id="tool-1",
        state=state,
        runtime=None,
    )

    assert result == expected


def test_takeaway_agent_is_constructed_with_expected_tools_and_prompt(takeaway_module):
    model = object()
    assert takeaway_module._langchain_agents_stub.create_agent_calls == []

    takeaway_module.build_takeaway_agent(
        model=model,
        system_prompt="Takeaway application prompt",
    )
    [call] = takeaway_module._langchain_agents_stub.create_agent_calls

    assert call["model"] is model
    assert takeaway_module.verify_if_payment_complete in call["tools"]
    assert takeaway_module.update_customer in call["tools"]
    assert len(call["tools"]) == 5
    assert "takeaway" in call["system_prompt"].lower()
    assert call["state_schema"] is dict
