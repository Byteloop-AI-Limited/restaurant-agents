"""
WhatsApp callback handlers for interactive actions.

This module processes callback payloads (buttons/list selections), updates
conversation state via `run_rest_graph_with_custom_msg`, and routes user/admin
actions across service, delivery, and order-confirmation flows.

Key handlers:
- `delivery_address_confirmation`: confirm/reject delivery address.
- `admin_collection_ready`: notify Ordelo that food is ready for pickup.
- `select_service_handler`: route service selection and agent handoff.
- `delivery_or_takeaway_selection`: persist delivery vs takeaway selection.
- `restaurant_order_confirmation_handler`: process restaurant accept/decline
  callbacks.
"""

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from pywa_async import WhatsApp

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.services.tz_utils import UK_TZ
from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.watomation.dedup import wa_dedup

# %% Define classes
from pywa.types import CallbackButton
from langchain_core.messages import HumanMessage, SystemMessage
from restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel import (
    UpdateCustRestMapRequest,
)
from restaurant_agent_runtime.rest_agent.agent_wa_senders import select_enquiry_wa_send
from restaurant_agent_runtime.services.ordelo_service.ordelo_service import OrdeloService

_ENQUIRY_OPTION_MESSAGES = frozenset(
    {
        "I want to make a customer complaint",
        "I want to know about parking availability",
        "I want to subscribe for offers",
    }
)


async def _run_selected_enquiry(
    *,
    recipient: str,
    rest_ref: str,
    human_msg: str,
    graph_adapter: GraphAdapter,
) -> None:
    """Run a specific enquiry choice through triage without reopening its menu."""
    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=recipient,
        msgs=[
            HumanMessage(human_msg),
            SystemMessage(
                "The customer has already chosen a specific enquiry option (their choice is the message above). "
                "Handle it directly per your rules. The enquiry menu has already been shown, so do NOT call "
                "ask_user_to_select_enquiry again."
            ),
        ],
        state_update_dict={
            "rest_ref": rest_ref,
            "active_agent": "triage_agent",
        },
    )


# %%
@wa_dedup
async def delivery_address_confirmation(
    msg: WhatsApp,
    callback: CallbackButton,
    *,
    callback_data_type: type,
    graph_adapter: GraphAdapter,
):
    # callback data created in agent_wa_senders/ confirm_delivery_address_wa
    callback_data = callback_data_type(**json.loads(callback.data))

    if callback_data.response == "Yes":
        human_msg = callback_data.human_msg
        state_update_dict = {
            "active_agent": "delivery_agent",
            "is_delivery_address_confirmed": True,
        }
        msgs = [
            HumanMessage(human_msg),
            SystemMessage(
                "User confirmed delivery address. Call `calculate_min_order_value` tool now."
            ),
        ]
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=callback_data.recipient,
            msgs=msgs,
            state_update_dict=state_update_dict,
        )
        return
    else:
        human_msg = callback_data.human_msg
        state_update_dict = {
            "active_agent": "delivery_agent",
            "is_delivery_address_confirmed": False,
        }
        msgs = [
            HumanMessage(human_msg),
            SystemMessage(
                "User wants to update delivery address. call `update_address_of_existing_user` tool"
            ),
        ]
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=callback_data.recipient,
            msgs=msgs,
            state_update_dict=state_update_dict,
        )
        return


# %% On adming collection ready
@wa_dedup
async def admin_collection_ready(
    msg: WhatsApp,
    callback: CallbackButton,
    *,
    callback_data_type: type,
    runtime: RestaurantRuntime,
):
    ordelo_app_url = runtime.operational_lookups.get_app_url("ORDELO")
    #  admin_order_reciept - creates the callback data
    callback_data = callback_data_type(**json.loads(callback.data))

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ordelo_app_url}/delivery-hooks/notify-food-ready-for-pickup/{callback_data.rider_id}",
            json={
                "restaurant_name": runtime.presentation.display_name,
                "order_number": callback_data.order_id,
            },
        )
    return


# %% Select service handler
@wa_dedup
async def select_service_handler(
    wa: WhatsApp,
    callback,
    *,
    callback_data_type: type,
    graph_adapter: GraphAdapter,
    runtime: RestaurantRuntime,
    select_service_sender: Any,
):
    """
    Handles service selection and routes to the appropriate agent.
    """
    recipient = callback.from_user.wa_id
    callback_data_dict: dict = json.loads(callback.data)

    try:
        callback_data = callback_data_type(**callback_data_dict)
    except Exception as e:
        logger.error(
            f"Invalid callback data for /SelectService: {callback_data_dict}, error: {e}"
        )
        return

    rest_ref = callback_data_dict.get("rest_ref") or runtime.identity.rest_ref.lower()
    logger.debug(f"callback_data_dict: {callback_data_dict}")

    active_agent = callback_data_dict.get("active_agent")

    # Treat Enquiry as a triage entry point even when a stale service button
    # still carries the delivery/takeaway agent from the preceding turn.
    if callback_data.human_msg == "I have an enquiry":
        await select_enquiry_wa_send(
            recipient=recipient,
            wa_client=wa,
            rest_ref=rest_ref,
            menu=runtime.presentation.enquiry_menu,
        )
        return

    # Older menus used /SelectService for these buttons. Continue them directly
    # through triage so an already-open chat does not need one extra click.
    if callback_data.human_msg in _ENQUIRY_OPTION_MESSAGES:
        await _run_selected_enquiry(
            recipient=recipient,
            rest_ref=rest_ref,
            human_msg=callback_data.human_msg,
            graph_adapter=graph_adapter,
        )
        return

    order_type = {
        "delivery_agent": "delivery",
        "takeaway_agent": "takeaway",
    }.get(active_agent)
    if order_type is not None:
        master = runtime.operational_lookups.get_restaurant_master()
        if not runtime.operational_lookups.is_overwatch_recipient(
            recipient
        ) and not master.accepts_new_order(
            order_type, datetime.now(UK_TZ)
        ):
            await wa.send_message(
                to=recipient,
                text="Sorry, new orders for that service have closed for today. You can still send us an enquiry.",
            )
            await select_service_sender(
                recipient=recipient,
                wa_client=wa,
                rest_ref=rest_ref,
                runtime=runtime,
            )
            return

    if rest_ref and active_agent:
        human_msg = callback_data.human_msg
        state_update_dict = {
            "rest_ref": rest_ref,
            "active_agent": active_agent,
        }
        msgs = [
            HumanMessage(human_msg),
        ]
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            msgs=msgs,
            state_update_dict=state_update_dict,
        )
        return

    elif rest_ref and not active_agent:
        await select_service_sender(
            recipient=recipient,
            wa_client=wa,
            rest_ref=rest_ref,
        )
        return

    else:
        logger.error(
            f"Incomplete callback data for /SelectService: {callback_data_dict}"
        )
        return


# %% Enquiry selection handler
@wa_dedup
async def select_enquiry_handler(
    wa: WhatsApp,
    callback,
    *,
    callback_data_type: type,
    graph_adapter: GraphAdapter,
    runtime: RestaurantRuntime,
):
    """Route a chosen enquiry option without reopening the enquiry menu."""
    recipient = callback.from_user.wa_id
    callback_data_dict: dict = json.loads(callback.data)
    try:
        callback_data = callback_data_type(**callback_data_dict)
    except Exception as exc:
        logger.error(
            "Invalid callback data for /SelectEnquiry: {}, error: {}",
            callback_data_dict,
            exc,
        )
        return

    rest_ref = callback_data_dict.get("rest_ref") or runtime.identity.rest_ref.lower()
    await _run_selected_enquiry(
        recipient=recipient,
        rest_ref=rest_ref,
        human_msg=callback_data.human_msg,
        graph_adapter=graph_adapter,
    )


# %% Marketing consent handler
@wa_dedup
async def select_consent_handler(
    wa: WhatsApp,
    callback,
    *,
    callback_data_type: type,
    graph_adapter: GraphAdapter,
    runtime: RestaurantRuntime,
):
    """
    Handles marketing consent callback (/SelectConsent).
    Updates ask_for_consent in state and re-invokes the graph.
    """
    recipient = callback.from_user.wa_id
    callback_data_dict: dict = json.loads(callback.data)

    try:
        callback_data = callback_data_type(**callback_data_dict)
    except Exception as e:
        logger.error(
            f"Invalid callback data for /SelectConsent: {callback_data_dict}, error: {e}"
        )
        return

    rest_ref = runtime.identity.rest_ref
    consent_given = str(callback_data_dict.get("response", "")).lower() == "yes"

    if rest_ref:
        ordelo_service = OrdeloService(
            rest_ref=str(rest_ref).upper(),
            database_client=runtime.settings.database_client,
            operational_lookups=runtime.operational_lookups,
        )
        await ordelo_service.update_cust_rest_map(
            UpdateCustRestMapRequest(
                cust_id=recipient,
                rest_ref=str(rest_ref).upper(),
                has_consent=consent_given,
                consent_dtts=datetime.now(timezone.utc),
            )
        )
    else:
        logger.warning(
            "Missing rest_ref while handling /SelectConsent for recipient {}",
            recipient,
        )

    consent_state_text = "gave" if consent_given else "declined"
    system_msg = (
        f"User {consent_state_text} marketing consent. "
        "Now call `terminate_conversation` to end the session politely."
    )
    state_update_dict = {
        "ask_for_consent": False,
        "active_agent": "triage_agent",
        "rest_ref": str(rest_ref).lower() if rest_ref else None,
    }
    msgs = [
        HumanMessage(callback_data.human_msg),
        SystemMessage(system_msg),
    ]

    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=recipient,
        msgs=msgs,
        state_update_dict=state_update_dict,
    )


# %% Restaurant order confirmation
@wa_dedup
async def restaurant_order_confirmation_handler(
    msg: WhatsApp,
    callback: CallbackButton,
    *,
    callback_data_type: type,
):
    callback_data = callback_data_type(**json.loads(callback.data))
    order_number = callback_data.response

    logger.info(f"Restaurant order confirmation: {order_number}")

    if "accept" in callback_data.action:
        logger.info("Restaurant accepted the order")
        # TODO: Implement accept logic
        pass
    elif "decline" in callback_data.action:
        logger.info("Restaurant declined the order")
        # TODO: Implement decline logic
        pass

    return
