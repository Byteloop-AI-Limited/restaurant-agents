"""
Unit tests for delivery agent tool branches
    . Loads delivery agent with stubbed config, harness, senders, payment, and order-service dependencies
    . Covers address guardrails, min-order calculation, payment status, general queries, updates, and allocation status
    . Mocks HTTP clients and WhatsApp clients so no network or external sends occur
  Functions/Classes:
    . FakeAsyncClientFactory
    . FakeResponse
    . delivery_module
    . test_address_capture_update_and_confirm_branches
    . test_calculate_min_order_value_inside_and_outside_area
    . test_verify_if_payment_complete_branches
    . test_answer_general_query_and_customer_updates
    . test_send_rider_live_location_link_success_and_failure
    . test_check_delivery_driver_allocation_status_branches
"""

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests._stubs.agent_stubs import (
    build_agent_harness_stub,
    build_langchain_agents_stub,
    build_lg_utils_agent_stub,
    build_runtime,
)
from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class FakeAsyncClientFactory:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.get_calls = []

    def __call__(self, *args, **kwargs):
        factory = self

        class FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, *args, **kwargs):
                factory.get_calls.append({"url": url, "args": args, "kwargs": kwargs})
                if factory.error:
                    raise factory.error
                return factory.response

        return FakeAsyncClient()


@pytest.fixture
def delivery_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.project_settings.project_root = str(Path(__file__).resolve().parents[3])
    config_stub.project_settings.get_ordelo_url = lambda client: "https://ordelo.test"
    harness_stub = build_agent_harness_stub()
    langchain_agents_stub = build_langchain_agents_stub()
    lg_utils_stub = build_lg_utils_agent_stub()

    senders_module = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")
    senders_module.confirm_calls = []
    senders_module.update_calls = []

    async def confirm_delivery_address_wa(recipient, address, header=None):
        senders_module.confirm_calls.append(
            {"recipient": recipient, "address": address, "header": header}
        )

    async def send_update_address_wa(recipient, _async_wa_client):
        senders_module.update_calls.append(
            {"recipient": recipient, "wa_client": _async_wa_client}
        )

    senders_module.confirm_delivery_address_wa = confirm_delivery_address_wa
    senders_module.send_update_address_wa = send_update_address_wa

    payment_module = ModuleType("restaurant_agent_core.services.payment_ms.payment")
    payment_module.cancel_calls = []

    async def cancel_payment(order_id, thread_id):
        payment_module.cancel_calls.append({"order_id": order_id, "thread_id": thread_id})
        return True

    payment_module.cancel_payment = cancel_payment

    order_service_module = ModuleType("restaurant_agent_core.services.order_service")
    order_service_module.next_min_order_value = 15

    async def get_min_order_value(rest_ref, cust_lat, cust_lon):
        return order_service_module.next_min_order_value

    order_service_module.get_min_order_value = get_min_order_value

    module = load_module(
        "test_delivery_agent_module",
        "sfcs_agent.rest_agent/agents/delivery.py",
        monkeypatch,
        {
            "config": config_stub,
            "sfcs_agent.rest_agent.agents.agent_harness": harness_stub,
            "langchain.agents": langchain_agents_stub,
            "restaurant_agent_core.services.lg_utils": lg_utils_stub,
            "sfcs_agent.rest_agent.agent_wa_senders": senders_module,
            "restaurant_agent_core.services.payment_ms.payment": payment_module,
            "restaurant_agent_core.services.order_service": order_service_module,
        },
    )
    module.ButtonUrl = lambda **kwargs: SimpleNamespace(**kwargs)
    module._senders_module = senders_module
    module._payment_module = payment_module
    module._order_service_module = order_service_module
    return module


@pytest.mark.asyncio
async def test_address_capture_update_and_confirm_branches(delivery_module):
    runtime = build_runtime()

    blocked = await delivery_module.capture_delivery_address(
        state={"is_payment_successful": True, "reply_to_msg_id": "msg-1"},
        tool_call_id="tool-1",
        runtime=runtime,
    )
    assert blocked.goto == "__end__"
    assert "can't change" in runtime.context.wa_client.sent_messages[0]["text"]

    already_captured = await delivery_module.capture_delivery_address(
        state={"customer_address": {"postcode": "BR6 6DN"}},
        tool_call_id="tool-2",
        runtime=runtime,
    )
    assert already_captured.goto == "deliveryAgent"

    capture = await delivery_module.capture_delivery_address(
        state={},
        tool_call_id="tool-3",
        runtime=runtime,
    )
    assert capture.goto == "__end__"
    assert delivery_module._senders_module.update_calls[-1]["recipient"] == "447000000001"

    update_confirmed = await delivery_module.update_address_of_existing_user(
        state={"is_delivery_address_confirmed": True},
        tool_call_id="tool-4",
        runtime=runtime,
    )
    assert "already confirmed" in update_confirmed.update["messages"][0].content

    confirm_already = await delivery_module.confirm_delivery_address(
        state={
            "is_delivery_address_confirmed": True,
            "customer_address": {"postcode": "BR6 6DN"},
        },
        tool_call_id="tool-5",
        runtime=runtime,
    )
    assert "already confirmed" in confirm_already.update["messages"][0].content

    address = {"postcode": "BR6 6DN"}
    confirm = await delivery_module.confirm_delivery_address(
        state={"customer_address": address},
        tool_call_id="tool-6",
        runtime=runtime,
    )
    assert "Address confirmation sent" in confirm.update["messages"][0].content
    assert delivery_module._senders_module.confirm_calls[-1] == {
        "recipient": "447000000001",
        "address": address,
        "header": None,
    }


@pytest.mark.asyncio
async def test_calculate_min_order_value_inside_and_outside_area(delivery_module):
    client = FakeSupabaseClient(
        table_data={
            "customer_master": [
                {"lat": 51.0, "lon": -1.0, "postcode": "BR6 6DN", "cust_name": "Bas"}
            ]
        }
    )
    runtime = build_runtime(client_ordelo=client)

    inside = await delivery_module.calculate_min_order_value(
        state={"order_number": "ORD-1"},
        tool_call_id="tool-7",
        runtime=runtime,
    )
    assert inside.update["min_order_value"] == 15
    assert inside.update["is_outside_delivery_area"] is False

    delivery_module._order_service_module.next_min_order_value = -1
    outside = await delivery_module.calculate_min_order_value(
        state={},
        tool_call_id="tool-8",
        runtime=runtime,
    )
    assert outside.update["is_delivery_address_confirmed"] is False
    assert outside.update["is_outside_delivery_area"] is True
    # SFCS-specific: delivery agent handles out-of-area in-flow rather than
    # transferring to triage. See rest_agent/agents/delivery.py:324-338.
    assert outside.update.get("active_agent") == "delivery_agent"
    out_msg = outside.update["messages"][0].content
    assert "transfer_to_triage" not in out_msg
    assert "outside" in out_msg.lower()


@pytest.mark.asyncio
async def test_verify_if_payment_complete_branches(delivery_module):
    runtime = build_runtime(
        client_ordelo=FakeSupabaseClient(
            table_data={"food_order": [{"payment_status": "requires_capture", "order_number": "ELAS-1"}]}
        )
    )

    assert await delivery_module.verify_if_payment_complete({}, "tool-9", runtime) == "Please place the order first."

    paid = await delivery_module.verify_if_payment_complete(
        {"order_id": "ORD-1"},
        "tool-10",
        runtime,
    )
    assert paid.update["is_payment_successful"] is True
    assert paid.update["is_delivery_rider_assigned"] is False

    runtime.context.client_ordelo = FakeSupabaseClient(
        table_data={"food_order": [{"payment_status": "requires_payment", "order_number": "ELAS-1"}]}
    )
    unpaid = await delivery_module.verify_if_payment_complete(
        {"order_id": "ORD-1"},
        "tool-11",
        runtime,
    )
    assert "not complete" in unpaid.update["messages"][0].content


@pytest.mark.asyncio
async def test_answer_general_query_and_customer_updates(delivery_module):
    runtime = build_runtime()

    location = await delivery_module.answer_general_query(
        "where are you",
        state={},
        tool_call_id="tool-12",
        runtime=runtime,
    )
    assert "location" in location.lower() or "address" in location.lower()

    assert "phone" in (await delivery_module.answer_general_query("phone", {}, "tool-13", runtime)).lower()
    assert "opening hours" in await delivery_module.answer_general_query("hours", {}, "tool-14", runtime)
    assert "takeaway" in await delivery_module.answer_general_query("collection", {}, "tool-15", runtime)
    assert "dine-in" in await delivery_module.answer_general_query("reservation", {}, "tool-16", runtime)
    assert "can't add" in await delivery_module.answer_general_query(
        "add item",
        {"is_payment_successful": True},
        "tool-17",
        runtime,
    )

    update = await delivery_module.send_updates_to_customer(
        "Food is ready",
        {"reply_to_msg_id": "msg-2"},
        "tool-18",
        runtime,
    )
    assert runtime.context.wa_client.sent_messages[-1] == {
        "to": "447000000001",
        "text": "Food is ready",
        "reply_to_message_id": "msg-2",
    }
    assert "Update sent" in update.update["messages"][0].content

    welcome = await delivery_module.send_welcome_msg({"wa_name": "Bas"}, "tool-19", runtime)
    assert welcome.goto == "deliveryAgent"
    assert "Welcome" in runtime.context.wa_client.sent_messages[-1]["text"]


@pytest.mark.asyncio
async def test_send_rider_live_location_link_success_and_failure(monkeypatch, delivery_module):
    runtime = build_runtime()
    success_factory = FakeAsyncClientFactory(FakeResponse(status_code=200))
    monkeypatch.setattr(delivery_module.httpx, "AsyncClient", success_factory)

    success = await delivery_module.send_rider_live_location_link(
        {"order_id": "ORD-1", "reply_to_msg_id": "msg-1", "rider_live_location_url": "https://track.test"},
        "tool-20",
        runtime,
    )
    assert "Live location link sent" in success.update["messages"][0].content
    assert runtime.context.wa_client.sent_messages[-1]["buttons"].url == "https://track.test"

    failure_factory = FakeAsyncClientFactory(FakeResponse(status_code=500))
    monkeypatch.setattr(delivery_module.httpx, "AsyncClient", failure_factory)
    failure = await delivery_module.send_rider_live_location_link(
        {"reply_to_msg_id": "msg-1", "rider_live_location_url": "https://track.test"},
        "tool-21",
        runtime,
    )
    assert "Cannot obtain live location" in failure.update["messages"][0].content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected_text",
    [
        ("unassigned", "still looking"),
        ("assigned", "assigned"),
        ("timedout", "do not have any delivery drivers"),
    ],
)
async def test_check_delivery_driver_allocation_status_branches(
    monkeypatch,
    delivery_module,
    status,
    expected_text,
):
    runtime = build_runtime()
    factory = FakeAsyncClientFactory(
        FakeResponse(json_data={"delivery_summary_status": status})
    )
    monkeypatch.setattr(delivery_module.httpx, "AsyncClient", factory)

    command = await delivery_module.check_delivery_driver_allocation_status(
        {"order_id": "ORD-1", "order_number": "ELAS-1", "reply_to_msg_id": "msg-1"},
        "tool-22",
        runtime,
    )
    assert expected_text in command.update["messages"][0].content

    missing_order = await delivery_module.check_delivery_driver_allocation_status(
        {},
        "tool-23",
        runtime,
    )
    assert "Order id not found" in missing_order.update["messages"][0].content

    timedout = await delivery_module.check_delivery_driver_allocation_status(
        {"order_id": "ORD-2", "order_number": "ELAS-2", "reply_to_msg_id": "msg-2"},
        "tool-24",
        runtime,
        is_timed_out=True,
    )
    assert delivery_module._payment_module.cancel_calls[-1] == {
        "order_id": "ORD-2",
        "thread_id": "thread-1",
    }
    assert "delivery drivers" in timedout.update["messages"][0].content
