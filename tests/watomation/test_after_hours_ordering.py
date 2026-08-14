from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.watomation.on_message_graph_handler import (
    handle_wa_msg_in_graph,
    is_ordering_request,
    send_closed_message,
)


def test_is_ordering_request_recognizes_delivery_and_collection_intent():
    assert is_ordering_request(SimpleNamespace(text="I want delivery"))
    assert is_ordering_request(SimpleNamespace(text="Can I collect an order?"))
    assert is_ordering_request(SimpleNamespace(text="Please send the menu"))
    assert not is_ordering_request(SimpleNamespace(text="Do you have parking?"))


@pytest.mark.asyncio
async def test_after_hours_ordering_uses_exact_closed_message():
    wa = SimpleNamespace(send_message=AsyncMock())
    msg = SimpleNamespace(sender="447000000001", text="I want collection")
    runtime = SimpleNamespace(operational_lookups=SimpleNamespace())

    await send_closed_message(wa, msg, runtime=runtime)

    wa.send_message.assert_awaited_once_with(
        to="447000000001", text="Ordering is currently closed."
    )


@pytest.mark.asyncio
async def test_after_hours_non_order_keeps_general_closed_reply():
    wa = SimpleNamespace(send_message=AsyncMock())
    msg = SimpleNamespace(sender="447000000001", text="Do you have parking?")
    runtime = SimpleNamespace(
        operational_lookups=SimpleNamespace(
            get_restaurant_master=lambda: SimpleNamespace(
                service_hours=SimpleNamespace(
                    format_today=lambda _at: "We are currently closed."
                )
            )
        )
    )

    await send_closed_message(wa, msg, runtime=runtime)

    wa.send_message.assert_awaited_once_with(
        to="447000000001",
        text="Thank you for your message. We are currently closed.",
    )


@pytest.mark.asyncio
async def test_after_hours_state_lookup_failure_preserves_the_current_graph():
    wa = SimpleNamespace(send_message=AsyncMock())
    msg = SimpleNamespace(
        sender="447000000001",
        text="where is my order?",
        from_user=SimpleNamespace(name="Lohith"),
    )
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(side_effect=RuntimeError("checkpoint unavailable")),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(operational_lookups=SimpleNamespace())

    await send_closed_message(
        wa, msg, runtime=runtime, graph_adapter=graph_adapter
    )

    wa.send_message.assert_not_awaited()
    graph_adapter.run_rest_graph_with_custom_msg.assert_awaited_once_with(
        recipient="447000000001",
        human_msg="where is my order?",
        wa_name="Lohith",
    )


@pytest.mark.asyncio
async def test_refund_question_with_active_assigned_rider_bypasses_model_and_fails_closed():
    msg = SimpleNamespace(
        sender="447000000001",
        text="how long does refund takes?",
        from_user=SimpleNamespace(name="Lohith"),
        indicate_typing=AsyncMock(),
    )
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={
                "active_agent": "delivery_agent",
                "retain_thread": True,
                "is_payment_cancelled": False,
                "is_delivery_rider_assigned": True,
                "is_delivery_picked_up": False,
            }
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        async_wa_client=SimpleNamespace(send_message=AsyncMock())
    )

    await handle_wa_msg_in_graph.__wrapped__(
        SimpleNamespace(), msg, graph_adapter=graph_adapter, runtime=runtime
    )

    runtime.async_wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text="Your delivery order is still in progress and a delivery driver has been assigned.",
    )
    persisted = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs
    assert persisted["persist_only"] is True
    assert "refund has been issued" not in persisted["msgs"][1].content.lower()
