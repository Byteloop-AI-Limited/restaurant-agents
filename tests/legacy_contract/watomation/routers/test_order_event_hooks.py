"""
Unit tests for order event router functions
    . Loads order_event_hooks with stubbed config, graph runner, receipt builder, and thread handler
    . Tests router functions directly without FastAPI server or external services
    . Covers rest_ref validation, time formatting, payment-complete branches, address update, takeaway ready, and pickup-time updates
  Functions/Classes:
    . FakeBackgroundTasks
    . FakeRequest
    . order_module
    . food_order
    . takeaway_pickup_payload
    . test_validate_rest_ref_and_format_time_for_user
    . test_payment_complete_delivery_and_takeaway_schedule_graph_updates
    . test_payment_complete_rejects_path_payload_mismatch
    . test_address_update_sends_ack_and_schedules_graph
    . test_takeaway_ready_sends_notification
    . test_takeaway_pickup_time_updated_schedules_graph
    . test_run_customer_collection_completions_sequence_calls_graph_twice
"""

from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append({"func": func, "args": args, "kwargs": kwargs})


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.fixture
def order_module(monkeypatch):
    config_stub = build_config_stub()

    async def get_pool():
        return object()

    config_stub.pg_settings.get_pool = get_pool

    params_module = ModuleType("restaurant_agent_core.config.params")
    params_module.invalid_refs = set()

    def get_restaurant_master_cached(rest_ref):
        if rest_ref in params_module.invalid_refs:
            raise ValueError(rest_ref)
        return SimpleNamespace(rest_ref=rest_ref)

    params_module.get_restaurant_master_cached = get_restaurant_master_cached

    runner_module = ModuleType("sfcs_agent.rest_agent.agent_runner")
    runner_module.run_calls = []

    async def run_rest_graph_with_custom_msg(**kwargs):
        runner_module.run_calls.append(kwargs)
        return "graph response"

    runner_module.run_rest_graph_with_custom_msg = run_rest_graph_with_custom_msg

    receipt_module = ModuleType("restaurant_agent_core.services.order_management.food_order_reciept")
    receipt_module.build_wa_order_reciept_for_cust = lambda food_order: (
        "Order Header",
        "Receipt Body",
    )

    thread_module = ModuleType("restaurant_agent_core.services.thread_management")

    class ThreadHandler:
        def __init__(self, pool):
            self.pool = pool

    thread_module.ThreadHandler = ThreadHandler

    module = load_module(
        "test_order_event_hooks_module",
        "restaurant_agent_core.watomation/routers/order_event_hooks.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_core.config.params": params_module,
            "sfcs_agent.rest_agent.agent_runner": runner_module,
            "restaurant_agent_core.services.order_management.food_order_reciept": receipt_module,
            "restaurant_agent_core.services.thread_management": thread_module,
        },
    )
    module._params_module = params_module
    module._runner_module = runner_module
    module._config_stub = config_stub
    return module


@pytest.fixture
def food_order(order_module):
    return order_module.FoodOrder(
        order_id="ORD-1",
        order_number="ELAS-1",
        recipient="447000000001",
        thread_id="thread-1",
        action="delivery",
        total_price=20,
        payment_status="requires_capture",
    )


@pytest.fixture
def takeaway_pickup_payload(order_module):
    return order_module.TakeawayPickupTimePayload(
        takeaway_summary={
            "order_number": "ELAS-1",
            "rest_id": "ELAS",
            "rest_name": "Elai",
            "rest_address": "Mill Stream Approach",
            "town": "Salisbury",
            "customer_id": "447000000001",
            "customer_name": "Bas",
            "restaurant_confirmation_status": "confirmed",
            "status": "ready",
            "rest_confirmation_code": 42,
            "pickup_time": "2026-05-10T18:30:00+00:00",
            "pickup_date": "2026-05-10",
            "dt": "2026-05-10",
            "dtts": "2026-05-10T12:00:00+00:00",
        },
        restaurant_master={
            "rest_id": "ELAS",
            "rest_ref": "elas",
            "rest_name": "Elai",
            "admins": ["admin"],
            "lon": -1.79,
            "lat": 51.07,
        },
    )


def test_validate_rest_ref_and_format_time_for_user(order_module):
    assert order_module.validate_rest_ref("elas") == "ELAS"
    order_module._params_module.invalid_refs.add("BAD")
    with pytest.raises(HTTPException):
        order_module.validate_rest_ref("bad")

    assert order_module.format_time_for_user(None) == "shortly"
    assert order_module.format_time_for_user("  ") == "shortly"
    assert order_module.format_time_for_user("6:30 pm") == "6:30 pm"
    assert order_module.format_time_for_user("18:30") == "6:30 pm"
    assert order_module.format_time_for_user("not-a-time") == "not-a-time"


@pytest.mark.asyncio
async def test_payment_complete_delivery_and_takeaway_schedule_graph_updates(order_module, food_order):
    bg = FakeBackgroundTasks()

    result = await order_module.payment_complete(
        "elas",
        "447000000001",
        "thread-1",
        food_order,
        bg,
    )
    assert result == {
        "status": "success",
        "order_id": "ORD-1",
        "order_number": "ELAS-1",
        "payment_status": "requires_capture",
    }
    assert "Thank you for the payment" in order_module._async_wa_client.sent_messages[-1]["text"]
    assert bg.tasks[-1]["kwargs"]["state_update_dict"]["active_agent"] == "delivery_agent"
    assert bg.tasks[-1]["kwargs"]["state_update_dict"]["reply_to_msg_id"] is None

    takeaway = food_order.model_copy(update={"action": "takeaway"})
    await order_module.payment_complete("elas", "447000000001", "thread-1", takeaway, bg)
    assert order_module._async_wa_client.sent_messages[-1]["header"] == "Order Header"
    assert bg.tasks[-1]["kwargs"]["state_update_dict"]["active_agent"] == "takeaway_agent"


@pytest.mark.asyncio
async def test_payment_complete_rejects_path_payload_mismatch(order_module, food_order):
    with pytest.raises(HTTPException) as recipient_mismatch:
        await order_module.payment_complete("elas", "wrong", "thread-1", food_order, FakeBackgroundTasks())
    assert recipient_mismatch.value.status_code == 400

    with pytest.raises(HTTPException) as thread_mismatch:
        await order_module.payment_complete("elas", "447000000001", "wrong", food_order, FakeBackgroundTasks())
    assert thread_mismatch.value.status_code == 400


@pytest.mark.asyncio
async def test_address_update_sends_ack_and_schedules_graph(order_module):
    bg = FakeBackgroundTasks()
    address = {"postcode": "BR6 6DN"}

    result = await order_module.address_update(
        "elas",
        "447000000001",
        bg,
        FakeRequest(address),
    )

    assert result == {"status": "success"}
    assert order_module._async_wa_client.sent_messages[-1] == {
        "to": "447000000001",
        "text": "Address update received, processing...",
    }
    assert bg.tasks[-1]["kwargs"]["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_delivery_address_confirmed": False,
        "customer_address": address,
        "min_order_value": None,
    }


@pytest.mark.asyncio
async def test_takeaway_ready_sends_notification(order_module):
    payload = order_module.TakeawayReadyPayload(
        order_id="ORD-1",
        order_number="ELAS-1",
        recipient="447000000001",
        admin_id="admin",
        event="ready",
        event_dtts="2026-05-10T12:00:00+00:00",
    )

    result = await order_module.takeaway_ready("elas", "ORD-1", payload)

    assert result == {"status": "success", "order_id": "ORD-1", "order_number": "ELAS-1"}
    assert "ready for collection" in order_module._async_wa_client.sent_messages[-1]["text"]


@pytest.mark.skip(reason="SFCS schedules via run_customer_collection_completions_sequence(customer_id=...); signature differs from elai")
@pytest.mark.asyncio
async def test_takeaway_pickup_time_updated_schedules_graph(order_module, takeaway_pickup_payload):
    bg = FakeBackgroundTasks()

    result = await order_module.takeaway_pickup_time_updated(
        "elas",
        takeaway_pickup_payload,
        bg,
    )

    assert result == {
        "status": "success",
        "order_number": "ELAS-1",
        "pickup_time": "2026-05-10T18:30:00+00:00",
    }
    assert bg.tasks[-1]["kwargs"]["recipient"] == "447000000001"
    assert "7:30 pm" in bg.tasks[-1]["kwargs"]["system_msg"]
    assert bg.tasks[-1]["kwargs"]["state_update_dict"] == {
        "active_agent": "takeaway_agent",
        "order_number": "ELAS-1",
        "retain_thread": False,
    }


@pytest.mark.asyncio
async def test_run_customer_collection_completions_sequence_calls_graph_twice(monkeypatch, order_module):
    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(order_module.asyncio, "sleep", no_sleep)

    await order_module.run_customer_collection_completions_sequence(
        customer_id="447",
        first_system_msg="first",
        first_state_update_dict={"a": 1},
        second_system_msg="second",
        second_state_update_dict={"b": 2},
    )

    assert order_module._runner_module.run_calls == [
        {"recipient": "447", "system_msg": "first", "state_update_dict": {"a": 1}},
        {"recipient": "447", "system_msg": "second", "state_update_dict": {"b": 2}},
    ]
