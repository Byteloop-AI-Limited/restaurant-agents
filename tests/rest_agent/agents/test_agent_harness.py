"""
Unit tests for rest_agent.agents.agent_harness pure helpers
    . Verifies _normalize_min_order_value coerces strings, currency-prefixed values,
      None, empty string, and falls back to 0.0 on garbage
    . Verifies _transfer_check_retained_specialist_work blocks handoff when retain_thread is set
    . Verifies _run_transfer_guards aggregates guard results
    . Verifies transfer_to_delivery/transfer_to_takeaway and the menu tools block a
      normal recipient outside service hours but let an Overwatch recipient through
      as though the venue were open (OperationalLookupCache.accepts_new_order)

SFCS is single-restaurant, so there is no rest_ref guard (unlike elai).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from restaurant_agent_runtime.rest_agent import agent_wa_senders
from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    _normalize_min_order_value,
    _run_transfer_guards,
    _transfer_check_retained_specialist_work,
    send_restaurant_menu_tool,
    transfer_to_delivery,
    transfer_to_takeaway,
    transfer_to_triage,
    update_customer,
)


def test_normalize_min_order_value_handles_numeric_strings():
    assert _normalize_min_order_value("12.5") == 12.5
    assert _normalize_min_order_value(8) == 8.0


def test_normalize_min_order_value_handles_currency_prefix():
    assert _normalize_min_order_value("£12.5") == 12.5
    assert _normalize_min_order_value("$ 9.99") == 9.99


def test_normalize_min_order_value_returns_zero_on_none_or_blank():
    assert _normalize_min_order_value(None) == 0.0
    assert _normalize_min_order_value("") == 0.0


def test_normalize_min_order_value_returns_zero_on_garbage():
    assert _normalize_min_order_value("abc!@#") == 0.0


def test_transfer_check_retained_specialist_work_returns_block_when_retained():
    cmd = _transfer_check_retained_specialist_work(
        {"retain_thread": True}, tool_call_id="tc-1"
    )

    assert cmd is not None
    assert cmd.update["messages"][0].tool_call_id == "tc-1"


def test_transfer_check_retained_specialist_work_allows_false_or_missing_state():
    assert _transfer_check_retained_specialist_work(
        {"retain_thread": False}, tool_call_id="tc-1"
    ) is None
    assert _transfer_check_retained_specialist_work({}, tool_call_id="tc-1") is None


def test_run_transfer_guards_blocks_when_delivery_retained():
    cmd = _run_transfer_guards({"retain_thread": True}, "tc-1")
    assert cmd is not None


def test_run_transfer_guards_returns_none_when_all_clear():
    assert _run_transfer_guards({"retain_thread": False}, "tc-1") is None


async def test_update_customer_sends_once_and_ends_without_state_changes():
    wa_client = AsyncMock()
    runtime = SimpleNamespace(
        context=SimpleNamespace(recipient="447000000001", wa_client=wa_client)
    )
    state = {"reply_to_msg_id": "message-1", "retain_thread": True}

    result = await update_customer(
        message="Your rider has been assigned.",
        state=state,
        tool_call_id="tc-1",
        runtime=runtime,
    )

    wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text="Your rider has been assigned.",
        reply_to_message_id="message-1",
    )
    assert result.goto == "__end__"
    assert state == {"reply_to_msg_id": "message-1", "retain_thread": True}
    assert "/DoNotRespond:" in result.update["messages"][-1].content


def test_transfer_to_triage_is_blocked_while_specialist_work_is_retained():
    runtime = SimpleNamespace(
        state={"retain_thread": True, "messages": []},
        tool_call_id="tc-1",
        context=SimpleNamespace(recipient="447000000001"),
    )

    result = transfer_to_triage(runtime)

    assert "active_agent" not in result.update
    assert "Stay with the current specialist" in result.update["messages"][0].content


class FakeOperationalLookups:
    """Minimal double mirroring OperationalLookupCache.accepts_new_order."""

    def __init__(self, *, delivery_open=True, takeaway_open=True, overwatch_recipients=()):
        self.delivery_open = delivery_open
        self.takeaway_open = takeaway_open
        self.overwatch_recipients = set(overwatch_recipients)

    def accepts_new_order(self, order_type, recipient, at=None):
        if recipient in self.overwatch_recipients:
            return True
        return self.delivery_open if order_type == "delivery" else self.takeaway_open

async def test_transfer_to_delivery_blocks_closed_recipient_but_allows_overwatch():
    ops = FakeOperationalLookups(delivery_open=False, overwatch_recipients={"447000000099"})

    blocked_runtime = SimpleNamespace(
        state={"retain_thread": False, "messages": []},
        tool_call_id="tc-1",
        context=SimpleNamespace(
            recipient="447000000001",
            operational_lookups=ops,
            wa_client=AsyncMock(),
        ),
    )
    blocked = await transfer_to_delivery(blocked_runtime)
    assert "closed" in blocked.update["messages"][0].content
    assert blocked.goto == "__end__"
    blocked_runtime.context.wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text="Ordering is currently closed.",
        reply_to_message_id=None,
    )

    overwatch_runtime = SimpleNamespace(
        state={"retain_thread": False, "messages": []},
        tool_call_id="tc-2",
        context=SimpleNamespace(
            recipient="447000000099",
            operational_lookups=ops,
            wa_client=AsyncMock(),
        ),
    )
    allowed = await transfer_to_delivery(overwatch_runtime)
    assert allowed.goto == "delivery_agent"
    assert allowed.update["active_agent"] == "delivery_agent"


async def test_transfer_to_takeaway_blocks_closed_recipient_but_allows_overwatch(monkeypatch):
    ops = FakeOperationalLookups(takeaway_open=False, overwatch_recipients={"447000000099"})

    blocked_state = {"retain_thread": False, "messages": []}
    blocked_runtime = SimpleNamespace(
        state=blocked_state,
        tool_call_id="tc-1",
        context=SimpleNamespace(
            recipient="447000000001",
            operational_lookups=ops,
            wa_client=AsyncMock(),
            thread_handler=AsyncMock(),
            rest_ref="BNAT",
            restaurant_logo_url="",
        ),
    )
    blocked = await transfer_to_takeaway(blocked_state, blocked_runtime)
    assert "closed" in blocked.update["messages"][0].content
    assert blocked.goto == "__end__"

    overwatch_state = {"retain_thread": False, "messages": [], "active_agent": "triage_agent"}
    overwatch_runtime = SimpleNamespace(
        state=overwatch_state,
        tool_call_id="tc-2",
        context=SimpleNamespace(
            recipient="447000000099",
            operational_lookups=ops,
            wa_client=AsyncMock(),
            thread_handler=AsyncMock(),
            rest_ref="BNAT",
            restaurant_logo_url="",
        ),
    )
    overwatch_runtime.context.thread_handler.get_or_create_thread = AsyncMock(
        return_value=("thread-1", False)
    )
    sender = AsyncMock(return_value=None)
    monkeypatch.setattr(agent_wa_senders, "send_restaurant_menu", sender)
    allowed = await transfer_to_takeaway(overwatch_state, overwatch_runtime)
    assert allowed.goto == "__end__"
    assert allowed.update["active_agent"] == "takeaway_agent"
    sender.assert_awaited_once()


async def test_send_restaurant_menu_tool_blocks_closed_recipient_but_allows_overwatch(
    monkeypatch,
):
    sender = AsyncMock(return_value=None)
    monkeypatch.setattr(agent_wa_senders, "send_restaurant_menu", sender)

    ops = FakeOperationalLookups(delivery_open=False, overwatch_recipients={"447000000099"})
    thread_handler = AsyncMock()
    thread_handler.get_or_create_thread = AsyncMock(return_value=("thread-1", False))
    wa_client = AsyncMock()

    def _runtime(recipient):
        ctx = SimpleNamespace(
            recipient=recipient,
            operational_lookups=ops,
            wa_client=wa_client,
            thread_handler=thread_handler,
            rest_ref="bnat",
            restaurant_logo_url="",
        )
        return SimpleNamespace(context=ctx)

    blocked_cmd = await send_restaurant_menu_tool(
        state={"min_order_value": 10, "rest_ref": "bnat"},
        tool_call_id="tc-1",
        runtime=_runtime("447000000001"),
    )
    assert "closed" in blocked_cmd.update["messages"][0].content
    sender.assert_not_awaited()

    allowed_cmd = await send_restaurant_menu_tool(
        state={"min_order_value": 10, "rest_ref": "bnat"},
        tool_call_id="tc-2",
        runtime=_runtime("447000000099"),
    )
    sender.assert_awaited_once()
    assert isinstance(allowed_cmd.update["messages"][-1], AIMessage)
