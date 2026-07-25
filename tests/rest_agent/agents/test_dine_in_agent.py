"""
Unit tests for dine-in agent tools and nodes
    . Loads dine_in agent with stubbed config, reservation DB ops, harness, and agent factory
    . Covers reservation-link success/failure, reservation status branches, and node routing
    . Uses fake WhatsApp, thread-handler, and Supabase clients to avoid external services
  Functions/Classes:
    . dinein_module
    . FakeReservationClient
    . ErrorReservationClient
    . test_get_reservation_link_success_sends_link_and_deactivates_thread
    . test_get_reservation_link_failure_returns_error_message
    . test_check_reservation_status_confirmed_pending_not_found_and_error
    . test_setup_agent_and_respond_nodes
"""

from pathlib import Path
from types import ModuleType

import pytest
from langchain_core.messages import AIMessage

from tests._stubs.agent_stubs import (
    FakeWaClient,
    build_agent_harness_stub,
    build_lg_utils_agent_stub,
    build_runtime,
)
from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


class FakeReservationClient(FakeSupabaseClient):
    def __init__(self, rows):
        super().__init__(table_data={"reservation": rows})


class ErrorReservationClient:
    def table(self, table_name):
        raise RuntimeError("db down")


@pytest.fixture
def dinein_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.project_settings.project_root = str(Path(__file__).resolve().parents[3])
    harness_stub = build_agent_harness_stub()
    lg_utils_stub = build_lg_utils_agent_stub()

    reservation_module = ModuleType("restaurant_agent_core.services.reservation_management.reservation_db_ops")
    reservation_module.next_reservation_id = "RES-1"

    async def process_reservation_into_db(pool, recipient, thread_id, *, rest_ref):
        reservation_module.received_rest_ref = rest_ref
        return reservation_module.next_reservation_id

    reservation_module.process_reservation_into_db = process_reservation_into_db

    senders_module = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")
    senders_module.sent_reservation_links = []

    async def reservation_link_wa_send(recipient, reservation_url, wa, wa_name="There"):
        senders_module.sent_reservation_links.append(
            {
                "recipient": recipient,
                "reservation_url": reservation_url,
                "wa": wa,
                "wa_name": wa_name,
            }
        )

    senders_module.reservation_link_wa_send = reservation_link_wa_send

    module = load_module(
        "test_dine_in_agent_module",
        "sfcs_agent.rest_agent/agents/dine_in.py",
        monkeypatch,
        {
            "config": config_stub,
            "sfcs_agent.rest_agent.agents.agent_harness": harness_stub,
            "restaurant_agent_core.services.lg_utils": lg_utils_stub,
            "restaurant_agent_core.services.reservation_management.reservation_db_ops": reservation_module,
            "sfcs_agent.rest_agent.agent_wa_senders": senders_module,
        },
    )
    module._reservation_module = reservation_module
    module._senders_module = senders_module
    return module


@pytest.mark.asyncio
async def test_get_reservation_link_success_sends_link_and_deactivates_thread(dinein_module):
    runtime = build_runtime()

    command = await dinein_module.get_reservation_link.coroutine(
        state={"wa_name": "Bas"},
        tool_call_id="tool-1",
        runtime=runtime,
    )

    assert command.update["reservation_id"] == "RES-1"
    assert command.update["is_reservation_confirmed"] is False
    assert dinein_module._reservation_module.received_rest_ref == "SFCS"
    assert dinein_module._senders_module.sent_reservation_links == [
        {
            "recipient": "447000000001",
            "reservation_url": "https://reservation.example.com/reservations/RES-1",
            "wa": runtime.context.wa_client,
            "wa_name": "Bas",
        }
    ]
    assert runtime.context.thread_handler.inactive_recipients == ["447000000001"]


@pytest.mark.asyncio
async def test_get_reservation_link_failure_returns_error_message(dinein_module):
    dinein_module._reservation_module.next_reservation_id = None
    runtime = build_runtime()

    command = await dinein_module.get_reservation_link.coroutine(
        state={},
        tool_call_id="tool-2",
        runtime=runtime,
    )

    assert "Failed to create reservation" in command.update["messages"][0].content
    assert dinein_module._senders_module.sent_reservation_links == []
    assert runtime.context.thread_handler.inactive_recipients == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows,expected_confirmed,expected_text",
    [
        ([{"confirmation_status": "confirmed"}], True, "Great news"),
        ([{"confirmation_status": "pending"}], False, "pending confirmation"),
        ([], None, "Reservation not found"),
    ],
)
async def test_check_reservation_status_confirmed_pending_not_found_and_error(
    dinein_module,
    rows,
    expected_confirmed,
    expected_text,
):
    wa = FakeWaClient()
    runtime = build_runtime(
        wa_client=wa,
        client_ordelo=FakeReservationClient(rows),
    )

    command = await dinein_module.check_reservation_status.coroutine(
        reservation_id="RES-1",
        state={},
        tool_call_id="tool-3",
        runtime=runtime,
    )

    assert expected_text in wa.sent_messages[0]["text"]
    if expected_confirmed is None:
        assert "is_reservation_confirmed" not in command.update
    else:
        assert command.update["is_reservation_confirmed"] is expected_confirmed

    error_wa = FakeWaClient()
    error_runtime = build_runtime(wa_client=error_wa, client_ordelo=ErrorReservationClient())
    error_command = await dinein_module.check_reservation_status.coroutine(
        reservation_id="RES-2",
        state={},
        tool_call_id="tool-4",
        runtime=error_runtime,
    )
    assert "error checking" in error_wa.sent_messages[0]["text"]
    assert "Error checking reservation" in error_command.update["messages"][0].content


@pytest.mark.asyncio
async def test_setup_agent_and_respond_nodes(dinein_module):
    setup_command = await dinein_module.setup_node({}, runtime=None)
    assert setup_command.goto == "dineinAgent"

    do_not_respond = dinein_module.agent_node(
        {"messages": [AIMessage("/DoNotRespond: hidden", id="ai-1")]}
    )
    assert do_not_respond.goto == "__end__"
    assert do_not_respond.update["messages"][1].content == "hidden"

    dinein_module.dinein_agent.invoke_result = AIMessage("hello user")
    response_route = dinein_module.agent_node({"messages": [AIMessage("input")]})
    assert response_route.goto == "respondNode"
    assert response_route.update["messages"] == [AIMessage("hello user")]

    dinein_module.dinein_agent.invoke_result = AIMessage(
        "tool",
        tool_calls=[{"name": "get_reservation_link", "args": {}, "id": "call-1"}],
    )
    tool_route = dinein_module.agent_node({"messages": [AIMessage("input")]})
    assert tool_route.goto == "toolNode"

    runtime = build_runtime()
    respond_command = await dinein_module.respond_node(
        {"messages": [AIMessage("send this")]},
        runtime=runtime,
    )
    assert respond_command.goto == "__end__"
    assert runtime.context.wa_client.sent_messages == [
        {"to": "447000000001", "text": "send this"}
    ]
