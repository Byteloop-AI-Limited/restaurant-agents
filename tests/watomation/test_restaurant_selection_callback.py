import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.rest_agent.agent_wa_senders import CallbackButtonData
from restaurant_agent_runtime.runtime import RestaurantChoice, RestaurantSelection
from restaurant_agent_runtime.watomation import on_callback_handler

ELAI = RestaurantChoice("ELAS", "Elai", "Elai", "I want to order from Elai")
WINGS = RestaurantChoice(
    "CHKS",
    "Wings and Things",
    "Wings and Things",
    "I want to order from Wings and Things",
)
SELECTION = RestaurantSelection(prompt="Which restaurant?", choices=(ELAI, WINGS))


def _callback(*, callback_id: str, data: dict):
    return SimpleNamespace(
        id=callback_id,
        data=json.dumps(data),
        from_user=SimpleNamespace(wa_id="447000000001"),
    )


@pytest.mark.asyncio
async def test_select_restaurant_writes_selected_rest_ref_and_deterministically_sends_service_buttons():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"retain_thread": False}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    select_service_sender = AsyncMock()
    runtime = SimpleNamespace(
        presentation=SimpleNamespace(
            restaurant_selection=SELECTION,
            delivery_button_label="Delivery",
            takeaway_button_label="Takeaway",
            enquiry_button_label="More options",
        ),
        async_wa_client=SimpleNamespace(send_message=AsyncMock()),
        operational_lookups=SimpleNamespace(),
    )
    callback = _callback(
        callback_id="select-restaurant",
        data={
            "action": "/SelectRestaurant",
            "rest_ref": "chks",
            "human_msg": "I want to order from Wings and Things",
        },
    )

    await on_callback_handler.select_restaurant_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=select_service_sender,
    )

    # The next step (service selection) is sent deterministically, not left to
    # the model's tool choice — a system-message instruction was previously
    # unreliable and produced an observed restaurant-selection loop.
    assert graph_adapter.run_rest_graph_with_custom_msg.await_count == 2
    first_kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[0].kwargs
    assert first_kwargs["state_update_dict"] == {
        "selected_rest_ref": "CHKS",
        "active_agent": "triage_agent",
    }
    assert first_kwargs["persist_only"] is True
    assert first_kwargs["msgs"][0].content == "I want to order from Wings and Things"

    select_service_sender.assert_awaited_once()
    send_kwargs = select_service_sender.await_args.kwargs
    assert send_kwargs["rest_ref"] == "chks"
    assert send_kwargs["operational_lookups"] is runtime.operational_lookups
    assert send_kwargs["enquiry_button_label"] == "More options"

    second_kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[1].kwargs
    assert second_kwargs["persist_only"] is True
    assert "Wings and Things" in second_kwargs["msgs"][0].content


@pytest.mark.asyncio
async def test_select_restaurant_rejects_an_unknown_choice():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        presentation=SimpleNamespace(restaurant_selection=SELECTION),
        async_wa_client=SimpleNamespace(send_message=AsyncMock()),
    )
    callback = _callback(
        callback_id="select-restaurant-unknown",
        data={
            "action": "/SelectRestaurant",
            "rest_ref": "wren",
            "human_msg": "I want to order from Wren",
        },
    )

    await on_callback_handler.select_restaurant_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    graph_adapter.debug_state_values.assert_not_awaited()
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_select_restaurant_is_blocked_while_an_order_is_retained():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={"active_agent": "delivery_agent", "retain_thread": True}
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    wa_client = SimpleNamespace(send_message=AsyncMock())
    runtime = SimpleNamespace(
        presentation=SimpleNamespace(restaurant_selection=SELECTION),
        async_wa_client=wa_client,
    )
    callback = _callback(
        callback_id="select-restaurant-retained",
        data={
            "action": "/SelectRestaurant",
            "rest_ref": "chks",
            "human_msg": "I want to order from Wings and Things",
        },
    )

    await on_callback_handler.select_restaurant_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()
    wa_client.send_message.assert_awaited_once()
    assert "current delivery order first" in wa_client.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_select_restaurant_no_op_when_app_has_no_selection_configured():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        presentation=SimpleNamespace(restaurant_selection=None),
        async_wa_client=SimpleNamespace(send_message=AsyncMock()),
    )
    callback = _callback(
        callback_id="select-restaurant-unconfigured",
        data={
            "action": "/SelectRestaurant",
            "rest_ref": "elas",
            "human_msg": "I want to order from Elai",
        },
    )

    await on_callback_handler.select_restaurant_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()
