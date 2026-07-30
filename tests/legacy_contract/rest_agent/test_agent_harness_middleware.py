"""
Unit tests for rest_agent.agents.agent_harness middleware and menu tools
    . Verifies cleanup_before_model returns jump_to=end on /DoNotRespond marker
    . Verifies cleanup_before_model returns None on normal AI message
    . Verifies respond_on_wa skips send on blank content
    . Verifies respond_on_wa strips /DoNotRespond marker and replaces the AIMessage
    . Verifies respond_on_wa sends via wa_client when no marker present
    . Verifies send_restaurant_menu_tool builds Command with success ToolMessage
    . Verifies send_takeaway_menu_tool routes order_type="takeaway"
    . Verifies _send_menu_tool falls back to project_settings.rest_ref when state lacks it
    . Verifies _send_menu_tool error path sends apology and returns ToolMessage with error
  Functions/Classes:
    . _Runtime, _Ctx
    . test_cleanup_before_model_*
    . test_respond_on_wa_*
    . test_send_restaurant_menu_tool_*
    . test_send_takeaway_menu_tool_*
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, RemoveMessage

from sfcs_agent.rest_agent.agents.agent_harness import (
    cleanup_before_model,
    respond_on_wa,
    send_restaurant_menu_tool,
    send_takeaway_menu_tool,
)


class _Ctx(SimpleNamespace):
    pass


class _Runtime(SimpleNamespace):
    pass


def test_cleanup_before_model_jumps_to_end_on_marker():
    state = {"messages": [AIMessage("/DoNotRespond: silent")]}
    result = cleanup_before_model.before_model(state, _Runtime())
    assert result == {"jump_to": "end"}


def test_cleanup_before_model_continues_on_normal_message():
    state = {"messages": [AIMessage("normal response")]}
    assert cleanup_before_model.before_model(state, _Runtime()) is None


@pytest.mark.asyncio
async def test_respond_on_wa_skips_blank_content():
    wa = AsyncMock()
    runtime = _Runtime(context=_Ctx(wa_client=wa, recipient="447000"))
    state = {"messages": [AIMessage("   ")]}

    result = await respond_on_wa.aafter_agent(state, runtime)

    assert result is None
    wa.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_respond_on_wa_strips_do_not_respond_marker():
    wa = AsyncMock()
    runtime = _Runtime(context=_Ctx(wa_client=wa, recipient="447000"))
    marked = AIMessage("/DoNotRespond: please pick from menu")
    marked.id = "ai-1"
    state = {"messages": [marked]}

    result = await respond_on_wa.aafter_agent(state, runtime)

    assert result is not None
    msgs = result["messages"]
    assert isinstance(msgs[0], RemoveMessage)
    assert msgs[0].id == "ai-1"
    assert isinstance(msgs[1], AIMessage)
    assert msgs[1].content == " please pick from menu"
    wa.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_respond_on_wa_sends_when_no_marker():
    wa = AsyncMock()
    runtime = _Runtime(context=_Ctx(wa_client=wa, recipient="447000"))
    state = {"messages": [AIMessage("Order received, thanks!")]}

    result = await respond_on_wa.aafter_agent(state, runtime)

    assert result is None
    wa.send_message.assert_awaited_once_with(
        to="447000", text="Order received, thanks!"
    )


def _make_menu_runtime(thread_id="t-1", recipient="447000"):
    """Build a ToolRuntime-shaped stub for the menu tools."""
    thread_handler = AsyncMock()
    thread_handler.get_or_create_thread = AsyncMock(return_value=(thread_id, False))
    wa_client = AsyncMock()
    ctx = _Ctx(
        recipient=recipient,
        thread_handler=thread_handler,
        wa_client=wa_client,
    )
    return _Runtime(context=ctx), wa_client, thread_handler


@pytest.fixture
def _patch_send_restaurant_menu(monkeypatch):
    """Patch the lazily-imported `send_restaurant_menu` symbol and
    `project_settings.rest_ref` fallback inside `_send_menu_tool`."""
    sender = AsyncMock(return_value=None)

    module = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")
    module.send_restaurant_menu = sender
    monkeypatch.setitem(sys.modules, "sfcs_agent.rest_agent.agent_wa_senders", module)

    # _send_menu_tool also does `from restaurant_agent_runtime.config import project_settings` lazily.
    # Stamp the attribute on whatever `config` module is currently in sys.modules
    # (other test fixtures may have replaced it with a stub).
    cfg = sys.modules.get("config")
    if cfg is None:
        cfg = ModuleType("config")
        monkeypatch.setitem(sys.modules, "config", cfg)
    monkeypatch.setattr(
        cfg, "project_settings", SimpleNamespace(rest_ref="DEFAULT_REF"), raising=False
    )
    return sender


@pytest.mark.asyncio
async def test_send_restaurant_menu_tool_success(_patch_send_restaurant_menu):
    sender = _patch_send_restaurant_menu
    runtime, wa_client, thread_handler = _make_menu_runtime()
    state = {"min_order_value": "£12.5", "rest_ref": "ELAS"}

    cmd = await send_restaurant_menu_tool(
        state=state, tool_call_id="tc-1", runtime=runtime
    )

    sender.assert_awaited_once()
    kwargs = sender.await_args.kwargs
    assert kwargs["order_type"] == "delivery"
    assert kwargs["minimum_order"] == 12.5
    assert kwargs["rest_ref"] == "ELAS"
    assert kwargs["thread_id"] == "t-1"

    messages = cmd.update["messages"]
    assert "Restaurant menu sent to customer for delivery order." in messages[0].content
    assert messages[0].tool_call_id == "tc-1"
    assert "/DoNotRespond:" in messages[1].content
    wa_client.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_takeaway_menu_tool_routes_order_type(_patch_send_restaurant_menu):
    sender = _patch_send_restaurant_menu
    runtime, _wa, _th = _make_menu_runtime()
    state = {"min_order_value": 0, "rest_ref": "ELAS"}

    cmd = await send_takeaway_menu_tool(
        state=state, tool_call_id="tc-2", runtime=runtime
    )

    assert sender.await_args.kwargs["order_type"] == "takeaway"
    assert "takeaway order" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_send_menu_tool_falls_back_to_project_rest_ref(
    _patch_send_restaurant_menu,
):
    sender = _patch_send_restaurant_menu
    runtime, _wa, _th = _make_menu_runtime()
    state = {"min_order_value": 5}  # no rest_ref

    await send_restaurant_menu_tool(
        state=state, tool_call_id="tc-3", runtime=runtime
    )

    assert sender.await_args.kwargs["rest_ref"] == "DEFAULT_REF"


@pytest.mark.asyncio
async def test_send_menu_tool_error_path_sends_apology(monkeypatch):
    sender = AsyncMock(return_value=ValueError("menu link unavailable"))
    module = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")
    module.send_restaurant_menu = sender
    monkeypatch.setitem(sys.modules, "sfcs_agent.rest_agent.agent_wa_senders", module)

    cfg = sys.modules.get("config")
    if cfg is None:
        cfg = ModuleType("config")
        monkeypatch.setitem(sys.modules, "config", cfg)
    monkeypatch.setattr(
        cfg, "project_settings", SimpleNamespace(rest_ref="DEFAULT_REF"), raising=False
    )

    runtime, wa_client, _th = _make_menu_runtime()
    state = {"min_order_value": 5, "rest_ref": "ELAS", "reply_to_msg_id": "wamid.1"}

    cmd = await send_restaurant_menu_tool(
        state=state, tool_call_id="tc-err", runtime=runtime
    )

    wa_client.send_message.assert_awaited_once()
    apology = wa_client.send_message.await_args.kwargs
    assert "couldn't send the menu link" in apology["text"]
    assert apology["reply_to_message_id"] == "wamid.1"

    msg = cmd.update["messages"][0]
    assert "Failed to send restaurant menu" in msg.content
    assert msg.tool_call_id == "tc-err"
