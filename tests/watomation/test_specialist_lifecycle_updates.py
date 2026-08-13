"""Contract tests for specialist-owned lifecycle customer updates."""

from types import SimpleNamespace
from pathlib import Path

from fastapi import BackgroundTasks

from restaurant_agent_runtime.watomation.routers import order_event_hooks
from restaurant_agent_runtime.watomation.routers import rider_event_hooks


def _runtime(rest_ref: str = "SFCS"):
    return SimpleNamespace(identity=SimpleNamespace(matches=lambda value: value == rest_ref))


def test_payment_followups_use_the_specialist_update_tool():
    source = order_event_hooks.__file__
    assert source is not None
    content = Path(source).read_text()

    assert content.count("Call `update_customer` with ") >= 3
    assert "User has been already thanked for the payment" not in content


async def test_delivery_timeout_uses_delivery_update_and_ends_the_turn_later():
    background_tasks = BackgroundTasks()

    result = await rider_event_hooks.delivery_timedout_path(
        rest_ref="SFCS",
        background_tasks=background_tasks,
        delivery_summary={"customer_id": "447000000001"},
        runtime=_runtime(),
        graph_adapter=SimpleNamespace(run_rest_graph_with_custom_msg=object()),
    )

    assert result == {"success": "success"}
    [task] = background_tasks.tasks
    assert task.kwargs["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_payment_successful": False,
        "retain_thread": False,
    }
    assert "Call `update_customer`" in task.kwargs["system_msg"]
    assert "ask_user_to_select_service" not in task.kwargs["system_msg"]
    assert "Then end this turn." in task.kwargs["system_msg"]


async def test_takeaway_pickup_time_releases_retention_before_triage_termination():
    background_tasks = BackgroundTasks()
    summary = SimpleNamespace(
        customer_id="447000000001",
        order_number="SFCS-123",
        pickup_time="2026-08-13T18:30:00+00:00",
    )

    result = await order_event_hooks.takeaway_pickup_time_updated(
        rest_ref="SFCS",
        payload=SimpleNamespace(takeaway_summary=summary),
        background_tasks=background_tasks,
        runtime=_runtime(),
        graph_adapter=SimpleNamespace(),
    )

    assert result["status"] == "success"
    [task] = background_tasks.tasks
    assert task.kwargs["first_state_update_dict"] == {
        "active_agent": "takeaway_agent",
        "order_number": "SFCS-123",
        "retain_thread": False,
    }
    assert "Call `update_customer`" in task.kwargs["first_system_msg"]
    assert task.kwargs["second_state_update_dict"] == {"active_agent": "triage_agent"}
