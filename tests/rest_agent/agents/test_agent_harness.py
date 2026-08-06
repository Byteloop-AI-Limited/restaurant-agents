"""
Unit tests for rest_agent.agents.agent_harness pure helpers
    . Verifies _normalize_min_order_value coerces strings, currency-prefixed values,
      None, empty string, and falls back to 0.0 on garbage
    . Verifies _transfer_check_delivery_retain blocks transfer when retain_thread is set
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
    _transfer_check_delivery_retain,
    send_restaurant_menu_tool,
    transfer_to_delivery,
    transfer_to_takeaway,
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


def test_transfer_check_delivery_retain_returns_block_when_retained():
    cmd = _transfer_check_delivery_retain({"retain_thread": True}, tool_call_id="tc-1")

    assert cmd is not None
    assert cmd.update["messages"][0].tool_call_id == "tc-1"


def test_transfer_check_delivery_retain_returns_none_when_not_retained():
    assert (
        _transfer_check_delivery_retain({"retain_thread": False}, tool_call_id="tc-1")
        is None
    )


def test_run_transfer_guards_blocks_when_delivery_retained():
    cmd = _run_transfer_guards({"retain_thread": True}, "tc-1")
    assert cmd is not None


def test_run_transfer_guards_returns_none_when_all_clear():
    assert _run_transfer_guards({"retain_thread": False}, "tc-1") is None


class FakeOperationalLookups:
    """Minimal double mirroring OperationalLookupCache.accepts_new_order."""

    def __init__(self, *, delivery_open=True, takeaway_open=True, overwatch_recipients=()):
        self.delivery_open = delivery_open
        self.takeaway_open = takeaway_open
        self.overwatch_recipients = set(overwatch_recipients)

    def accepts_new_order(self, order_type, recipient):
        if recipient in self.overwatch_recipients:
            return True
        return self.delivery_open if order_type == "delivery" else self.takeaway_open


def test_transfer_to_delivery_blocks_closed_recipient_but_allows_overwatch():
    ops = FakeOperationalLookups(delivery_open=False, overwatch_recipients={"447000000099"})

    blocked_runtime = SimpleNamespace(
        state={"retain_thread": False, "messages": []},
        tool_call_id="tc-1",
        context=SimpleNamespace(recipient="447000000001", operational_lookups=ops),
    )
    blocked = transfer_to_delivery(blocked_runtime)
    assert "closed" in blocked.update["messages"][0].content
    assert blocked.goto == ()

    overwatch_runtime = SimpleNamespace(
        state={"retain_thread": False, "messages": []},
        tool_call_id="tc-2",
        context=SimpleNamespace(recipient="447000000099", operational_lookups=ops),
    )
    allowed = transfer_to_delivery(overwatch_runtime)
    assert allowed.goto == "delivery_agent"
    assert allowed.update["active_agent"] == "delivery_agent"


def test_transfer_to_takeaway_blocks_closed_recipient_but_allows_overwatch():
    ops = FakeOperationalLookups(takeaway_open=False, overwatch_recipients={"447000000099"})

    blocked_state = {"retain_thread": False, "messages": []}
    blocked_runtime = SimpleNamespace(
        state=blocked_state,
        tool_call_id="tc-1",
        context=SimpleNamespace(recipient="447000000001", operational_lookups=ops),
    )
    blocked = transfer_to_takeaway(blocked_state, blocked_runtime)
    assert "closed" in blocked.update["messages"][0].content
    assert blocked.goto == ()

    overwatch_state = {"retain_thread": False, "messages": [], "active_agent": "triage_agent"}
    overwatch_runtime = SimpleNamespace(
        state=overwatch_state,
        tool_call_id="tc-2",
        context=SimpleNamespace(recipient="447000000099", operational_lookups=ops),
    )
    allowed = transfer_to_takeaway(overwatch_state, overwatch_runtime)
    assert allowed.goto == "takeaway_agent"
    assert allowed.update["active_agent"] == "takeaway_agent"


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
    assert "cutoff" in blocked_cmd.update["messages"][0].content
    sender.assert_not_awaited()

    allowed_cmd = await send_restaurant_menu_tool(
        state={"min_order_value": 10, "rest_ref": "bnat"},
        tool_call_id="tc-2",
        runtime=_runtime("447000000099"),
    )
    sender.assert_awaited_once()
    assert isinstance(allowed_cmd.update["messages"][-1], AIMessage)
