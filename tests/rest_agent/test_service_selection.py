import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from restaurant_agent_runtime.rest_agent.service_selection import (
    classify_service_selection,
    route_service_selection,
    selection_disposition,
)


@pytest.mark.parametrize(
    ("message", "service"),
    [
        ("delivery", "delivery"),
        ("I want delivery", "delivery"),
        ("Could I get delivery please?", "delivery"),
        ("takeaway", "takeaway"),
        ("collection please", "takeaway"),
        ("I would like pickup", "takeaway"),
        ("switch to take away", "takeaway"),
    ],
)
def test_classifies_explicit_service_selection(message, service):
    assert classify_service_selection(message) == service


@pytest.mark.parametrize(
    "message",
    [
        "where is my delivery?",
        "is the food halal?",
        "do you deliver?",
        "I don't want delivery",
        "cancel my takeaway",
        "what is the takeaway status?",
        "I want delivery and takeaway",
    ],
)
def test_does_not_misclassify_questions_cancellations_or_ambiguous_requests(message):
    assert classify_service_selection(message) is None


def test_retained_selection_policy_does_not_recheck_new_order_availability():
    def should_not_run():
        raise AssertionError("retained work must not evaluate new-order availability")

    assert selection_disposition(
        state={"retain_thread": True},
        service="delivery",
        accepts_new_order=should_not_run,
    ) == "retained"


@pytest.mark.asyncio
async def test_retained_typed_selection_preserves_the_current_specialist():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={"active_agent": "delivery_agent", "retain_thread": True}
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        async_wa_client=SimpleNamespace(send_message=AsyncMock()),
        presentation=SimpleNamespace(restaurant_selection=None),
    )

    await route_service_selection(
        recipient="447000000001",
        service="takeaway",
        human_msg="I want takeaway",
        graph_adapter=graph_adapter,
        runtime=runtime,
    )

    kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs
    assert kwargs["msgs"][0].content == "I want takeaway"
    assert "current delivery order first" in kwargs["msgs"][1].content
    assert kwargs["persist_only"] is True
    runtime.async_wa_client.send_message.assert_awaited_once_with(
        to="447000000001", text=kwargs["msgs"][1].content
    )


@pytest.mark.asyncio
async def test_released_typed_delivery_selection_clears_old_order_state():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"retain_thread": False}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        operational_lookups=SimpleNamespace(accepts_new_order=lambda *_: True),
        presentation=SimpleNamespace(restaurant_selection=None),
    )

    await route_service_selection(
        recipient="447000000001",
        service="delivery",
        human_msg="I want delivery",
        graph_adapter=graph_adapter,
        runtime=runtime,
        rest_ref="sfcs",
    )

    update = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs[
        "state_update_dict"
    ]
    assert update["active_agent"] == "delivery_agent"
    assert update["retain_thread"] is False
    assert update["order_id"] is None
    assert update["rest_ref"] == "sfcs"


@pytest.mark.asyncio
async def test_closed_typed_selection_does_not_overwrite_released_state():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"retain_thread": False}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    wa_client = SimpleNamespace(send_message=AsyncMock())
    runtime = SimpleNamespace(
        operational_lookups=SimpleNamespace(accepts_new_order=lambda *_: False),
        async_wa_client=wa_client,
        presentation=SimpleNamespace(restaurant_selection=None),
    )

    await route_service_selection(
        recipient="447000000001",
        service="delivery",
        human_msg="I want delivery",
        graph_adapter=graph_adapter,
        runtime=runtime,
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()
    wa_client.send_message.assert_awaited_once_with(
        to="447000000001", text="Ordering is currently closed.", reply_to_message_id=None
    )
