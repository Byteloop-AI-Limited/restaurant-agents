"""
Unit tests for the request_rider_location customer tool and its steering branch
    . the tool delegates to rider_location_support.send_rider_location_reply with
      every field sourced from state/ctx, then wraps the result in the standard
      Command/ToolMessage/AIMessage /DoNotRespond shape
    . detailed guard and Ordelo-outcome-mapping behaviour lives in
      test_rider_location_support.py, which exercises send_rider_location_reply
      directly since both the tool and the deterministic pre-model interception
      in on_message_graph_handler.py share that one implementation
    . answer_general_query's rider-location branch steers to the tool instead of
      answering with the restaurant's address (regression test for the fall-through
      the branch directly below it would otherwise trigger)
    . check_delivery_driver_allocation_status redirects to request_rider_location
      once the order is picked up, instead of returning Ordelo's stale
      unassigned/assigned/timedout status (that endpoint has no picked-up state,
      so it would otherwise always answer with outdated "assigned" copy)
  Functions/Classes:
    . _runtime
    . test_request_rider_location_delegates_to_shared_reply_with_state_derived_fields
    . test_request_rider_location_wraps_reply_in_do_not_respond_command
    . test_answer_general_query_steers_rider_location_questions_to_the_tool
    . test_check_delivery_driver_allocation_status_redirects_once_picked_up
    . test_check_delivery_driver_allocation_status_still_works_before_pickup
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.rest_agent.agents import delivery as delivery_module


def _runtime(*, wa_msg_id="wamid.ABC123"):
    wa_client = AsyncMock()
    operational_lookups = object()
    client_ordelo = object()
    context = SimpleNamespace(
        recipient="447000000001",
        rest_ref="SFCS",
        wa_client=wa_client,
        client_ordelo=client_ordelo,
        operational_lookups=operational_lookups,
        wa_msg_id=wa_msg_id,
        restaurant_selection=None,
        reservation_base_url=None,
    )
    return SimpleNamespace(context=context), wa_client, operational_lookups, client_ordelo


async def test_request_rider_location_delegates_to_shared_reply_with_state_derived_fields(
    monkeypatch,
):
    runtime, wa_client, operational_lookups, client_ordelo = _runtime()
    fake_reply = AsyncMock(return_value="some reply text")
    monkeypatch.setattr(delivery_module, "send_rider_location_reply", fake_reply)

    state = {
        "order_number": "SFCS-12345",
        "is_delivery_picked_up": True,
        "reply_to_msg_id": "message-1",
    }

    await delivery_module.request_rider_location(
        state=state, tool_call_id="tc-1", runtime=runtime
    )

    fake_reply.assert_awaited_once_with(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number="SFCS-12345",
        is_delivery_picked_up=True,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=operational_lookups,
        client_ordelo=client_ordelo,
        wa_msg_id="wamid.ABC123",
    )


async def test_request_rider_location_wraps_reply_in_do_not_respond_command(monkeypatch):
    runtime, *_ = _runtime()
    monkeypatch.setattr(
        delivery_module,
        "send_rider_location_reply",
        AsyncMock(return_value="We will share the rider's location soon."),
    )

    result = await delivery_module.request_rider_location(
        state={"order_number": "SFCS-12345", "is_delivery_picked_up": False},
        tool_call_id="tc-1",
        runtime=runtime,
    )

    messages = result.update["messages"]
    assert messages[0].content == "We will share the rider's location soon."
    assert messages[0].tool_call_id == "tc-1"
    assert messages[-1].content == (
        "/DoNotRespond: We will share the rider's location soon."
    )


@pytest.mark.parametrize(
    "question",
    ["where is my food", "where is my rider", "track my order", "rider's location"],
)
async def test_answer_general_query_steers_rider_location_questions_to_the_tool(question):
    runtime, *_ = _runtime()
    runtime.context.restaurant_master = SimpleNamespace(
        house_number=None,
        building_name=None,
        street_name="123 Fake Street",
        city="London",
        postcode="SW1A 1AA",
        service_hours=SimpleNamespace(format_new_order_week=lambda: "9-5"),
    )
    runtime.context.restaurant_contact_phone = "0123456789"
    state = {}

    result = await delivery_module.answer_general_query(
        question=question, state=state, tool_call_id="tc-1", runtime=runtime
    )

    assert result == "Call `request_rider_location` to answer this."
    assert "Fake Street" not in result


class _FakeHttpResponse:
    def __init__(self, json_data):
        self._json = json_data

    def json(self):
        return self._json


class _FakeHttpClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        return self._response


async def test_check_delivery_driver_allocation_status_redirects_once_picked_up():
    runtime, wa_client, *_ = _runtime()

    result = await delivery_module.check_delivery_driver_allocation_status(
        state={"is_delivery_picked_up": True},
        tool_call_id="tc-1",
        runtime=runtime,
    )

    assert result == (
        "The rider has already picked up this order. Call `request_rider_location` instead."
    )
    wa_client.send_message.assert_not_awaited()


async def test_check_delivery_driver_allocation_status_still_works_before_pickup(
    monkeypatch,
):
    runtime, wa_client, *_ = _runtime()
    runtime.context.thread_handler = SimpleNamespace(
        get_or_create_thread=AsyncMock(return_value=("thread-1", False))
    )
    runtime.context.operational_lookups = SimpleNamespace(
        get_app_url=lambda app_ref: "https://ordelo.test"
    )
    monkeypatch.setattr(
        delivery_module.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeHttpClient(
            _FakeHttpResponse({"delivery_summary_status": "unassigned"})
        ),
    )

    state = {
        "is_delivery_picked_up": False,
        "order_id": "order-1",
        "order_number": "SFCS-12345",
        "reply_to_msg_id": "message-1",
    }

    result = await delivery_module.check_delivery_driver_allocation_status(
        state=state, tool_call_id="tc-1", runtime=runtime
    )

    wa_client.send_message.assert_awaited_once()
    assert "still looking for a delivery driver" in result.update["messages"][0].content
