"""
Unit tests for send_rider_location_reply, the state-gated guard and
Ordelo-response mapping behind the request_rider_location tool
    . kept as a standalone function so this logic is testable without the
      LangGraph Command/ToolMessage wrapping the tool itself adds; the model
      decides when to call the tool, this only decides what to do once called
  Functions/Classes:
    . _operational_lookups
    . test_no_active_order_sends_fixed_reply_without_calling_ordelo
    . test_pre_pickup_sends_placeholder_without_calling_ordelo
    . test_posts_state_derived_request_once_picked_up
    . test_202_sends_acknowledgement
    . test_200_sends_no_message
    . test_maps_conflict_and_error_codes
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.rest_agent import rider_location_support
from restaurant_agent_runtime.rest_agent.rider_location_support import (
    send_rider_location_reply,
)
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE,
    RIDER_LOCATION_NO_ORDER_MESSAGE,
    RIDER_LOCATION_PENDING_MESSAGE,
    RIDER_LOCATION_REQUESTED_MESSAGE,
    RIDER_LOCATION_UNAVAILABLE_MESSAGE,
)
from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)
from restaurant_agent_runtime.services.ordelo_service.datamodels.wa_location_pymodel import (
    WaLocationRequestOutcome,
)


def _operational_lookups(base_url="https://sfcs-agent.example.com/"):
    class ConfigClient:
        def table(self, _name):
            return self

        def select(self, _fields):
            return self

        def eq(self, _field, _value):
            return self

        def limit(self, _count):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"config_value": base_url}])

    return OperationalLookupCache(rest_ref="SFCS", database_client=ConfigClient())


async def test_no_active_order_sends_fixed_reply_without_calling_ordelo(monkeypatch):
    wa_client = AsyncMock()
    called = AsyncMock()
    monkeypatch.setattr(
        rider_location_support.OrdeloService, "request_rider_location", called
    )

    text = await send_rider_location_reply(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number=None,
        is_delivery_picked_up=None,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=_operational_lookups(),
        client_ordelo=None,
        wa_msg_id="wamid.ABC123",
    )

    assert text == RIDER_LOCATION_NO_ORDER_MESSAGE
    wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text=RIDER_LOCATION_NO_ORDER_MESSAGE,
        reply_to_message_id="message-1",
    )
    called.assert_not_awaited()


async def test_pre_pickup_sends_placeholder_without_calling_ordelo(monkeypatch):
    wa_client = AsyncMock()
    called = AsyncMock()
    monkeypatch.setattr(
        rider_location_support.OrdeloService, "request_rider_location", called
    )

    text = await send_rider_location_reply(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number="SFCS-12345",
        is_delivery_picked_up=False,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=_operational_lookups(),
        client_ordelo=None,
        wa_msg_id="wamid.ABC123",
    )

    assert text == RIDER_LOCATION_PENDING_MESSAGE
    wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text=RIDER_LOCATION_PENDING_MESSAGE,
        reply_to_message_id="message-1",
    )
    called.assert_not_awaited()


async def test_posts_state_derived_request_once_picked_up(monkeypatch):
    wa_client = AsyncMock()
    lookups = _operational_lookups(base_url="https://sfcs-agent.example.com/")
    captured = {}

    async def fake_request_rider_location(self, request):
        captured["service_rest_ref"] = self.rest_ref
        captured["request"] = request
        return WaLocationRequestOutcome(status_code=202, status="rider_prompted")

    monkeypatch.setattr(
        rider_location_support.OrdeloService,
        "request_rider_location",
        fake_request_rider_location,
    )

    await send_rider_location_reply(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number="SFCS-12345",
        is_delivery_picked_up=True,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=lookups,
        client_ordelo=None,
        wa_msg_id="wamid.ABC123",
    )

    request = captured["request"]
    assert captured["service_rest_ref"] == "SFCS"
    assert request.order_number == "SFCS-12345"
    assert request.location_requested_by == "customer"
    assert request.requester_id == "447000000001"
    assert request.callback_url == (
        "https://sfcs-agent.example.com/rider-event-hooks/SFCS/wa-location-response"
    )
    assert request.idempotency_key == "SFCS:SFCS-12345:447000000001:wamid.ABC123"


async def test_202_sends_acknowledgement(monkeypatch):
    wa_client = AsyncMock()

    async def fake_request_rider_location(self, request):
        return WaLocationRequestOutcome(status_code=202, status="waiting_for_rider")

    monkeypatch.setattr(
        rider_location_support.OrdeloService,
        "request_rider_location",
        fake_request_rider_location,
    )

    text = await send_rider_location_reply(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number="SFCS-12345",
        is_delivery_picked_up=True,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=_operational_lookups(),
        client_ordelo=None,
        wa_msg_id="wamid.ABC123",
    )

    assert text == RIDER_LOCATION_REQUESTED_MESSAGE
    wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text=RIDER_LOCATION_REQUESTED_MESSAGE,
        reply_to_message_id="message-1",
    )


async def test_200_sends_no_message(monkeypatch):
    wa_client = AsyncMock()

    async def fake_request_rider_location(self, request):
        return WaLocationRequestOutcome(status_code=200, status="location_available")

    monkeypatch.setattr(
        rider_location_support.OrdeloService,
        "request_rider_location",
        fake_request_rider_location,
    )

    await send_rider_location_reply(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number="SFCS-12345",
        is_delivery_picked_up=True,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=_operational_lookups(),
        client_ordelo=None,
        wa_msg_id="wamid.ABC123",
    )

    wa_client.send_message.assert_not_awaited()


@pytest.mark.parametrize(
    ("status_code", "code", "expected_text"),
    [
        (409, "food_not_picked_up", RIDER_LOCATION_PENDING_MESSAGE),
        (409, "delivery_not_inflight", RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE),
        (409, "delivery_not_active", RIDER_LOCATION_UNAVAILABLE_MESSAGE),
        (403, "requester_not_authorized", RIDER_LOCATION_UNAVAILABLE_MESSAGE),
        (404, "active_dispatch_not_found", RIDER_LOCATION_UNAVAILABLE_MESSAGE),
        (422, "invalid_payload", RIDER_LOCATION_UNAVAILABLE_MESSAGE),
        (502, "callback_delivery_failed", RIDER_LOCATION_UNAVAILABLE_MESSAGE),
        (0, None, RIDER_LOCATION_UNAVAILABLE_MESSAGE),
    ],
)
async def test_maps_conflict_and_error_codes(monkeypatch, status_code, code, expected_text):
    wa_client = AsyncMock()

    async def fake_request_rider_location(self, request):
        return WaLocationRequestOutcome(status_code=status_code, code=code)

    monkeypatch.setattr(
        rider_location_support.OrdeloService,
        "request_rider_location",
        fake_request_rider_location,
    )

    text = await send_rider_location_reply(
        rest_ref="SFCS",
        recipient="447000000001",
        order_number="SFCS-12345",
        is_delivery_picked_up=True,
        reply_to_msg_id="message-1",
        wa_client=wa_client,
        operational_lookups=_operational_lookups(),
        client_ordelo=None,
        wa_msg_id="wamid.ABC123",
    )

    assert text == expected_text
    wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text=expected_text,
        reply_to_message_id="message-1",
    )
