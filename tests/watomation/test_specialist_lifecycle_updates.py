"""Contract tests for specialist-owned lifecycle customer updates."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import BackgroundTasks
import pytest

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


def test_takeaway_payment_instruction_allows_only_the_authoritative_update():
    instruction = order_event_hooks._takeaway_payment_pending_pickup_system_message()

    assert "We will confirm the pickup time in a moment." in instruction
    assert "Do not call a menu tool" in instruction
    assert "start a new order" in instruction
    assert "hand off" in instruction


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


async def test_takeaway_payment_reserves_the_lifecycle_gate_before_queueing(
    monkeypatch,
):
    monkeypatch.setattr(
        order_event_hooks,
        "build_wa_order_reciept_for_cust",
        lambda **_: ("Order Header", "Receipt Body"),
    )
    wa_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(id="wamid.receipt"))
    )
    runtime = SimpleNamespace(
        identity=SimpleNamespace(matches=lambda value: value == "SFCS"),
        settings=SimpleNamespace(database_client=object()),
        async_wa_client=wa_client,
    )
    order = SimpleNamespace(
        recipient="447000000010",
        thread_id="SFCS-thread-10",
        action="takeaway",
        order_id="ORD-10",
        order_number="SFCS-10",
        payment_status="requires_capture",
    )
    background_tasks = BackgroundTasks()

    result = await order_event_hooks.payment_complete(
        rest_ref="SFCS",
        recipient=order.recipient,
        thread_id=order.thread_id,
        food_order=order,
        background_tasks=background_tasks,
        runtime=runtime,
        graph_adapter=SimpleNamespace(),
    )

    assert result["status"] == "success"
    [task] = background_tasks.tasks
    assert task.args == (
        "collection_payment_complete",
        order_event_hooks._run_reserved_takeaway_payment_update,
    )
    assert task.kwargs["lock"].locked()
    assert task.kwargs["recipient"] == order.recipient
    assert task.kwargs["state_update_dict"] == order_event_hooks.retained_specialist_state(
        "takeaway",
        order_id=order.order_id,
        order_number=order.order_number,
        reply_to_msg_id="wamid.receipt",
    )

    task.kwargs["lock"].release()


async def test_takeaway_lifecycle_runs_payment_before_pickup_completion():
    rest_ref = "SFCS"
    recipient = "447000000011"
    lock = order_event_hooks._takeaway_lifecycle_lock(rest_ref, recipient)
    await lock.acquire()
    payment_started = asyncio.Event()
    release_payment = asyncio.Event()
    calls: list[str] = []

    class GraphAdapter:
        async def run_rest_graph_with_custom_msg(self, **kwargs):
            system_msg = kwargs.get("system_msg", "")
            if "TAKEAWAY PAYMENT EVENT" in system_msg:
                calls.append("payment-start")
                payment_started.set()
                await release_payment.wait()
                calls.append("payment-finished")
            elif kwargs.get("persist_only"):
                calls.append("release")
            elif "SPECIALIST LIFECYCLE EVENT" in system_msg:
                calls.append("pickup-notification")
            elif "TERMINAL EVENT" in system_msg:
                calls.append("terminate")
            else:
                raise AssertionError(f"unexpected graph call: {kwargs}")

    graph_adapter = GraphAdapter()
    payment_task = asyncio.create_task(
        order_event_hooks._run_reserved_takeaway_payment_update(
            lock=lock,
            recipient=recipient,
            system_msg=order_event_hooks._takeaway_payment_pending_pickup_system_message(),
            state_update_dict={},
            graph_adapter=graph_adapter,
        )
    )
    await payment_started.wait()
    pickup_task = asyncio.create_task(
        order_event_hooks._run_serialized_takeaway_pickup_completion(
            rest_ref=rest_ref,
            recipient=recipient,
            specialist="takeaway_agent",
            message="Ready shortly.",
            graph_adapter=graph_adapter,
            terminate=True,
        )
    )

    await asyncio.sleep(0)
    assert calls == ["payment-start"]

    release_payment.set()
    await asyncio.gather(payment_task, pickup_task)

    assert calls == [
        "payment-start",
        "payment-finished",
        "pickup-notification",
        "release",
        "terminate",
    ]


async def test_takeaway_payment_failure_releases_the_lifecycle_gate():
    rest_ref = "SFCS"
    recipient = "447000000012"
    lock = order_event_hooks._takeaway_lifecycle_lock(rest_ref, recipient)
    await lock.acquire()
    graph_adapter = SimpleNamespace(
        run_rest_graph_with_custom_msg=AsyncMock(side_effect=RuntimeError("failed"))
    )

    with pytest.raises(RuntimeError, match="failed"):
        await order_event_hooks._run_reserved_takeaway_payment_update(
            lock=lock,
            recipient=recipient,
            system_msg=order_event_hooks._takeaway_payment_pending_pickup_system_message(),
            state_update_dict={},
            graph_adapter=graph_adapter,
        )

    assert not lock.locked()


async def test_takeaway_lifecycle_lock_does_not_block_another_recipient():
    rest_ref = "SFCS"
    first_recipient = "447000000013"
    second_recipient = "447000000014"
    first_lock = order_event_hooks._takeaway_lifecycle_lock(rest_ref, first_recipient)
    await first_lock.acquire()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_finished = asyncio.Event()

    class GraphAdapter:
        async def run_rest_graph_with_custom_msg(self, **kwargs):
            recipient = kwargs["recipient"]
            if recipient == first_recipient:
                first_started.set()
                await release_first.wait()
            else:
                second_finished.set()

    graph_adapter = GraphAdapter()
    first_task = asyncio.create_task(
        order_event_hooks._run_reserved_takeaway_payment_update(
            lock=first_lock,
            recipient=first_recipient,
            system_msg=order_event_hooks._takeaway_payment_pending_pickup_system_message(),
            state_update_dict={},
            graph_adapter=graph_adapter,
        )
    )
    await first_started.wait()

    await order_event_hooks._run_serialized_takeaway_pickup_completion(
        rest_ref=rest_ref,
        recipient=second_recipient,
        specialist="takeaway_agent",
        message="Ready shortly.",
        graph_adapter=graph_adapter,
        terminate=False,
    )

    assert second_finished.is_set()
    release_first.set()
    await first_task


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
    assert task.args == (
        "customer_collection_completion_sequence",
        order_event_hooks._run_serialized_takeaway_pickup_completion,
    )
    assert task.kwargs["rest_ref"] == "SFCS"
    assert task.kwargs["specialist"] == "takeaway_agent"
    assert task.kwargs["terminate"] is True
    assert "ready for collection" in task.kwargs["message"]
