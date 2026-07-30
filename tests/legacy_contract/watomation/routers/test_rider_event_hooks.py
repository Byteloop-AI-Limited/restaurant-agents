"""
Unit tests for rider event webhook router functions
    . Loads rider_event_hooks with stubbed config params and graph runner
    . Tests router functions directly without starting FastAPI server
    . Captures background task scheduling for delivery lifecycle events
  Functions/Classes:
    . FakeBackgroundTasks
    . FakeRequest
    . rider_module
    . delivery_summary_payload
    . test_validate_rest_ref_success_and_failure
    . test_rider_inflight_schedules_assignment_update
    . test_restaurant_and_customer_confirmation_paths_schedule_tasks
    . test_rider_enter_and_delivery_timedout_paths_schedule_tasks
    . test_run_customer_delivery_completion_sequence_calls_graph_twice
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
def rider_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.project_settings.get_ordelo_url = lambda client: "https://ordelo.test"

    params_module = ModuleType("restaurant_agent_runtime.config.params")
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

    runner_module.run_rest_graph_with_custom_msg = run_rest_graph_with_custom_msg

    module = load_module(
        "test_rider_event_hooks_module",
        "restaurant_agent_runtime.watomation/routers/rider_event_hooks.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_runtime.config.params": params_module,
            "sfcs_agent.rest_agent.agent_runner": runner_module,
        },
    )
    module._params_module = params_module
    module._runner_module = runner_module
    return module


@pytest.fixture
def delivery_summary_payload():
    return {
        "delivery_summary": {
            "order_number": "ELAS-ABCD-12",
            "rest_id": "ELAS",
            "rest_name": "Elai",
            "rest_lon": -1.79,
            "rest_lat": 51.07,
            "rest_address": "Mill Stream Approach",
            "town": "Salisbury",
            "customer_id": "447000000001",
            "customer_name": "Bas",
            "customer_lon": -1.80,
            "customer_lat": 51.08,
            "customer_address": "10 High Street",
            "status": "assigned",
            "rest_confirmation_code": 24,
            "cust_confirmation_code": 42,
            "pickup_time": "2026-05-10T12:00:00+00:00",
            "pickup_date": "2026-05-10",
            "dt": "2026-05-10",
            "dtts": "2026-05-10T12:00:00+00:00",
        }
    }


def test_validate_rest_ref_success_and_failure(rider_module):
    assert rider_module.validate_rest_ref("elas") == "ELAS"

    rider_module._params_module.invalid_refs.add("BAD")
    with pytest.raises(HTTPException) as exc:
        rider_module.validate_rest_ref("bad")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rider_inflight_schedules_assignment_update(rider_module, delivery_summary_payload):
    bg = FakeBackgroundTasks()

    result = await rider_module.rider_inflight(
        "elas",
        FakeRequest(delivery_summary_payload),
        bg,
    )

    assert result == {"success": "success"}
    [task] = bg.tasks
    assert task["func"] is rider_module.run_background_task
    assert task["args"][0] == "rider_inflight_customer_update"
    assert task["args"][1] is rider_module.run_rest_graph_with_custom_msg
    assert task["kwargs"]["recipient"] == "447000000001"
    assert "Confirmation Code is 42" in task["kwargs"]["system_msg"]
    assert task["kwargs"]["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_delivery_rider_assigned": True,
    }


@pytest.mark.asyncio
async def test_restaurant_and_customer_confirmation_paths_schedule_tasks(rider_module):
    bg = FakeBackgroundTasks()

    assert await rider_module.rider_restaurant_cc_path("elas", "ELAS-ABCD-12", "447", bg) == {
        "success": "success"
    }
    assert bg.tasks[-1]["kwargs"]["recipient"] == "447"
    assert bg.tasks[-1]["kwargs"]["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_delivery_picked_up": True,
        "rider_live_location_url": "https://ordelo.test/location-hooks/live-location-map/ELAS-ABCD-12",
    }

    assert await rider_module.rider_customer_cc_path("elas", "ELAS-ABCD-12", "447", bg) == {
        "success": "success"
    }
    assert bg.tasks[-1]["func"] is rider_module.run_background_task
    assert bg.tasks[-1]["args"][0] == "customer_delivery_completion_sequence"
    assert bg.tasks[-1]["args"][1] is rider_module.run_customer_delivery_completion_sequence
    assert bg.tasks[-1]["kwargs"]["customer_id"] == "447"
    assert bg.tasks[-1]["kwargs"]["second_state_update_dict"] == {
        "active_agent": "triage_agent"
    }


@pytest.mark.asyncio
async def test_rider_enter_and_delivery_timedout_paths_schedule_tasks(rider_module, delivery_summary_payload):
    bg = FakeBackgroundTasks()

    assert await rider_module.rider_restaurant_enter(
        "elas",
        "ELAS-ABCD-12",
        bg,
        delivery_summary_payload,
    ) == {"success": "success"}
    assert bg.tasks[-1]["kwargs"]["recipient"] == "447000000001"
    assert "restaurant" in bg.tasks[-1]["kwargs"]["system_msg"]

    assert await rider_module.rider_customer_enter(
        "elas",
        "ELAS-ABCD-12",
        bg,
        delivery_summary_payload,
    ) == {"success": "success"}
    assert "Confirmation Code: 42" in bg.tasks[-1]["kwargs"]["system_msg"]

    assert await rider_module.delivery_timedout_path(
        "elas",
        bg,
        {"customer_id": "447000000001"},
    ) == {"success": "success"}
    assert bg.tasks[-1]["kwargs"]["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_payment_successful": False,
        "retain_thread": False,
    }


@pytest.mark.asyncio
async def test_run_customer_delivery_completion_sequence_calls_graph_twice(monkeypatch, rider_module):
    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(rider_module.asyncio, "sleep", no_sleep)

    await rider_module.run_customer_delivery_completion_sequence(
        customer_id="447",
        first_system_msg="first",
        first_state_update_dict={"a": 1},
        second_system_msg="second",
        second_state_update_dict={"b": 2},
    )

    assert rider_module._runner_module.run_calls == [
        {"recipient": "447", "system_msg": "first", "state_update_dict": {"a": 1}},
        {"recipient": "447", "system_msg": "second", "state_update_dict": {"b": 2}},
    ]
