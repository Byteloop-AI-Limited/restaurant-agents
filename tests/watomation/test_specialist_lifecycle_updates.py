"""Contract tests for specialist-owned lifecycle customer updates."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import BackgroundTasks

from restaurant_agent_runtime.watomation.routers import order_event_hooks
from restaurant_agent_runtime.watomation.routers import rider_event_hooks


def _runtime(rest_ref: str = "SFCS"):
    return SimpleNamespace(identity=SimpleNamespace(matches=lambda value: value == rest_ref))


def test_payment_followups_use_the_specialist_update_tool():
    state = order_event_hooks.retained_specialist_state(
        "delivery", order_id="id", order_number="number", reply_to_msg_id="wamid"
    )
    assert state == {
        "active_agent": "delivery_agent",
        "order_id": "id",
        "order_number": "number",
        "reply_to_msg_id": "wamid",
        "is_payment_successful": True,
        "retain_thread": True,
        "is_delivery_rider_assigned": False,
        "is_delivery_picked_up": False,
        "rider_live_location_url": None,
        "is_payment_cancelled": False,
        "is_delivery_no_rider": False,
    }


def test_payment_replay_guard_only_suppresses_the_matching_retained_order():
    order = SimpleNamespace(order_id="order-1")
    assert order_event_hooks._is_duplicate_delivery_payment_event(
        {
            "active_agent": "delivery_agent",
            "retain_thread": True,
            "is_payment_successful": True,
            "order_id": "order-1",
        },
        order,
    )
    assert not order_event_hooks._is_duplicate_delivery_payment_event(
        {
            "active_agent": "delivery_agent",
            "retain_thread": True,
            "is_payment_successful": True,
            "order_id": "order-2",
        },
        order,
    )


async def test_delivery_timeout_uses_shared_terminal_release_sequence():
    background_tasks = BackgroundTasks()

    result = await rider_event_hooks.delivery_timedout_path(
        rest_ref="SFCS",
        background_tasks=background_tasks,
        delivery_summary={"customer_id": "447000000001", "order_number": "SFCS-1"},
        runtime=_runtime(),
        graph_adapter=SimpleNamespace(run_rest_graph_with_custom_msg=object()),
    )

    assert result == {"success": "success"}
    [task] = background_tasks.tasks
    assert task.args[1] is rider_event_hooks._release_timedout_delivery_if_current
    assert task.kwargs["delivery_summary"]["order_number"] == "SFCS-1"


async def test_delivery_timeout_releases_only_the_matching_unassigned_delivery():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={
                "active_agent": "delivery_agent",
                "retain_thread": True,
                "order_number": "SFCS-1",
                "is_delivery_rider_assigned": False,
                "is_delivery_picked_up": False,
            }
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )

    await rider_event_hooks._release_timedout_delivery_if_current(
        delivery_summary={
            "customer_id": "447000000001",
            "order_number": "SFCS-1",
            "payment_cancelled": True,
        },
        graph_adapter=graph_adapter,
    )

    assert graph_adapter.run_rest_graph_with_custom_msg.await_count == 2
    notification = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[0].kwargs
    assert "refund has been issued" in notification["system_msg"]
    release = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[1].kwargs
    assert release["state_update_dict"]["is_payment_cancelled"] is True


async def test_delivery_timeout_without_confirmed_cancellation_never_claims_refund():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={
                "active_agent": "delivery_agent",
                "retain_thread": True,
                "order_number": "SFCS-1",
                "is_delivery_rider_assigned": False,
                "is_delivery_picked_up": False,
            }
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )

    await rider_event_hooks._release_timedout_delivery_if_current(
        delivery_summary={
            "customer_id": "447000000001",
            "order_number": "SFCS-1",
            "payment_cancelled": False,
        },
        graph_adapter=graph_adapter,
    )

    calls = graph_adapter.run_rest_graph_with_custom_msg.await_args_list
    assert "refund has been issued" not in calls[0].kwargs["system_msg"]
    assert calls[1].kwargs["state_update_dict"]["is_payment_cancelled"] is False
    assert calls[1].kwargs["state_update_dict"]["is_delivery_no_rider"] is True


async def test_delivery_timeout_ignores_assigned_or_mismatched_delivery():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={
                "active_agent": "delivery_agent",
                "retain_thread": True,
                "order_number": "SFCS-2",
                "is_delivery_rider_assigned": True,
                "is_delivery_picked_up": False,
            }
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )

    await rider_event_hooks._release_timedout_delivery_if_current(
        delivery_summary={"customer_id": "447000000001", "order_number": "SFCS-1"},
        graph_adapter=graph_adapter,
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


async def test_takeaway_pickup_time_uses_shared_terminal_release_sequence():
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
    assert task.kwargs["specialist"] == "takeaway_agent"
    assert task.kwargs["terminate"] is True
    assert "ready for collection" in task.kwargs["message"]
