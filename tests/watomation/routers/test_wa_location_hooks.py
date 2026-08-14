"""
Unit tests for the wa_location_response callback route
    . Calls the handler function directly (matching test_specialist_lifecycle_updates.py)
      rather than driving the full app through TestClient, since the handler touches
      the database via ThreadHandler
    . Valid retained picked-up matching order sends one pin and returns 204
    . Every guard failure sends nothing, mutates no state, and never creates a thread
    . restaurant_confirmation source is labelled "last known at restaurant"
    . A WhatsApp send failure returns 502
    . A rest_ref path mismatch is rejected before any lookup, via validate_rest_ref
  Functions/Classes:
    . FakeThreadHandler
    . _runtime
    . _payload
    . test_valid_callback_sends_one_pin_and_returns_204
    . test_restaurant_confirmation_source_is_labelled_last_known_at_restaurant
    . test_unknown_thread_sends_nothing_and_returns_409
    . test_unreadable_state_sends_nothing_and_returns_409
    . test_guard_failures_send_nothing_and_return_409
    . test_send_failure_returns_502
    . test_wrong_rest_ref_is_rejected_before_any_lookup
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from restaurant_agent_runtime.services.ordelo_service.datamodels.wa_location_pymodel import (
    WaLocationCallbackPayload,
)
from restaurant_agent_runtime.watomation.routers import rider_event_hooks


class FakeThreadHandler:
    """Records construction args; ``get_active_thread`` never creates a row."""

    instances = []

    def __init__(self, pool, agent):
        self.pool = pool
        self.agent = agent
        type(self).instances.append(self)

    async def get_active_thread(self, recipient):
        return type(self).thread_row_for(recipient)

    @classmethod
    def thread_row_for(cls, recipient):
        return cls.rows.get(recipient)


def _install_fake_thread_handler(monkeypatch, *, rows):
    FakeThreadHandler.rows = rows
    FakeThreadHandler.instances = []
    monkeypatch.setattr(rider_event_hooks, "ThreadHandler", FakeThreadHandler)
    return FakeThreadHandler


def _runtime(*, rest_ref="SFCS", send_location=None):
    async_wa_client = SimpleNamespace(send_location=send_location or AsyncMock())
    return SimpleNamespace(
        identity=SimpleNamespace(matches=lambda value: value == rest_ref, rest_ref=rest_ref),
        settings=SimpleNamespace(
            database=SimpleNamespace(get_pool=AsyncMock(return_value=object()))
        ),
        async_wa_client=async_wa_client,
    )


def _payload(**overrides):
    fields = dict(
        request_id="3db6435f-abd1-461c-b71d-d1e47d92def0",
        order_number="SFCS-12345",
        customer_id="447000000001",
        rider_id="447000000111",
        location_requested_by="customer",
        requester_id="447000000001",
        location={
            "latitude": 51.5007,
            "longitude": -0.1246,
            "source": "whatsapp_current",
            "observed_at": "2026-08-07T20:30:00+00:00",
        },
    )
    fields.update(overrides)
    return WaLocationCallbackPayload(**fields)


def _retained_picked_up_state(**overrides):
    state = {
        "active_agent": "delivery_agent",
        "retain_thread": True,
        "order_number": "SFCS-12345",
        "is_delivery_picked_up": True,
    }
    state.update(overrides)
    return state


async def test_valid_callback_sends_one_pin_and_returns_204(monkeypatch):
    _install_fake_thread_handler(
        monkeypatch, rows={"447000000001": {"thread_id": "thread-1"}}
    )
    runtime = _runtime()
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value=_retained_picked_up_state())
    )

    response = await rider_event_hooks.wa_location_response(
        rest_ref="SFCS",
        payload=_payload(),
        runtime=runtime,
        graph_adapter=graph_adapter,
    )

    assert response.status_code == 204
    runtime.async_wa_client.send_location.assert_awaited_once_with(
        to="447000000001",
        latitude=51.5007,
        longitude=-0.1246,
        name="Rider's latest location",
    )
    [config_call] = graph_adapter.debug_state_values.await_args_list
    assert config_call.kwargs["config"] == {
        "configurable": {"thread_id": "thread-1", "recipient": "447000000001"}
    }


async def test_restaurant_confirmation_source_is_labelled_last_known_at_restaurant(
    monkeypatch,
):
    _install_fake_thread_handler(
        monkeypatch, rows={"447000000001": {"thread_id": "thread-1"}}
    )
    runtime = _runtime()
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value=_retained_picked_up_state())
    )

    response = await rider_event_hooks.wa_location_response(
        rest_ref="SFCS",
        payload=_payload(
            location={
                "latitude": 51.5,
                "longitude": -0.12,
                "source": "restaurant_confirmation",
                "observed_at": "2026-08-07T20:00:00+00:00",
            }
        ),
        runtime=runtime,
        graph_adapter=graph_adapter,
    )

    assert response.status_code == 204
    assert (
        runtime.async_wa_client.send_location.await_args.kwargs["name"]
        == "Last known at restaurant"
    )


async def test_unknown_thread_sends_nothing_and_returns_409(monkeypatch):
    _install_fake_thread_handler(monkeypatch, rows={})
    runtime = _runtime()
    graph_adapter = SimpleNamespace(debug_state_values=AsyncMock())

    response = await rider_event_hooks.wa_location_response(
        rest_ref="SFCS",
        payload=_payload(),
        runtime=runtime,
        graph_adapter=graph_adapter,
    )

    assert response.status_code == 409
    runtime.async_wa_client.send_location.assert_not_awaited()
    graph_adapter.debug_state_values.assert_not_awaited()


async def test_unreadable_state_sends_nothing_and_returns_409(monkeypatch):
    _install_fake_thread_handler(
        monkeypatch, rows={"447000000001": {"thread_id": "thread-1"}}
    )
    runtime = _runtime()
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(side_effect=RuntimeError("boom"))
    )

    response = await rider_event_hooks.wa_location_response(
        rest_ref="SFCS",
        payload=_payload(),
        runtime=runtime,
        graph_adapter=graph_adapter,
    )

    assert response.status_code == 409
    runtime.async_wa_client.send_location.assert_not_awaited()


@pytest.mark.parametrize(
    ("state_overrides", "payload_overrides"),
    [
        ({"retain_thread": False}, {}),
        ({"active_agent": "takeaway_agent"}, {}),
        ({"order_number": "SFCS-99999"}, {}),
        ({"is_delivery_picked_up": False}, {}),
        ({}, {"location_requested_by": "restaurant_admin"}),
        ({}, {"requester_id": "447000000999"}),
    ],
    ids=[
        "not_retained",
        "wrong_active_agent",
        "wrong_order_number",
        "not_picked_up",
        "not_customer_requested",
        "requester_mismatch",
    ],
)
async def test_guard_failures_send_nothing_and_return_409(
    monkeypatch, state_overrides, payload_overrides
):
    _install_fake_thread_handler(
        monkeypatch, rows={"447000000001": {"thread_id": "thread-1"}}
    )
    runtime = _runtime()
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value=_retained_picked_up_state(**state_overrides)
        )
    )

    response = await rider_event_hooks.wa_location_response(
        rest_ref="SFCS",
        payload=_payload(**payload_overrides),
        runtime=runtime,
        graph_adapter=graph_adapter,
    )

    assert response.status_code == 409
    runtime.async_wa_client.send_location.assert_not_awaited()


async def test_send_failure_returns_502(monkeypatch):
    _install_fake_thread_handler(
        monkeypatch, rows={"447000000001": {"thread_id": "thread-1"}}
    )
    runtime = _runtime(send_location=AsyncMock(side_effect=RuntimeError("wa down")))
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value=_retained_picked_up_state())
    )

    response = await rider_event_hooks.wa_location_response(
        rest_ref="SFCS",
        payload=_payload(),
        runtime=runtime,
        graph_adapter=graph_adapter,
    )

    assert response.status_code == 502


async def test_wrong_rest_ref_is_rejected_before_any_lookup(monkeypatch):
    thread_handler_cls = _install_fake_thread_handler(monkeypatch, rows={})
    runtime = _runtime(rest_ref="SFCS")
    graph_adapter = SimpleNamespace(debug_state_values=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await rider_event_hooks.wa_location_response(
            rest_ref="BNAT",
            payload=_payload(),
            runtime=runtime,
            graph_adapter=graph_adapter,
        )

    assert exc_info.value.status_code == 404
    assert thread_handler_cls.instances == []
    graph_adapter.debug_state_values.assert_not_awaited()
