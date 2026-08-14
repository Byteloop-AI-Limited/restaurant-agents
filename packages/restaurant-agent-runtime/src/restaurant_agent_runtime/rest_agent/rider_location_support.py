"""Rider-location reply logic shared by the request_rider_location tool.

Routing a customer's rider-location question to this tool is the model's
call, made from the delivery prompt and the `answer_general_query` steering
branch -- there is deliberately no regex-based pre-model interception here.
An earlier version of this module tried that and it backfired: it duplicated
intent recognition the model already does, and it did not address the actual
production failure, which was `update_customer` reusing a stale system
instruction rather than a rider-location misclassification. That failure is
now prevented structurally in `update_customer` itself (see
`agent_harness._last_turn_started_by_system_message`), which also protects
every other kind of customer question, not just location ones.

`send_rider_location_reply` stays a standalone function so the guard and
Ordelo-response mapping can be unit tested without the LangGraph
Command/ToolMessage wrapping the tool itself adds.
"""

from __future__ import annotations

from typing import Any

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE,
    RIDER_LOCATION_NO_ORDER_MESSAGE,
    RIDER_LOCATION_PENDING_MESSAGE,
    RIDER_LOCATION_REQUESTED_MESSAGE,
    RIDER_LOCATION_UNAVAILABLE_MESSAGE,
)
from restaurant_agent_runtime.services.ordelo_service import OrdeloService
from restaurant_agent_runtime.services.ordelo_service.datamodels.wa_location_pymodel import (
    WaLocationRequest,
    build_wa_location_callback_url,
)


async def send_rider_location_reply(
    *,
    rest_ref: str,
    recipient: str,
    order_number: str | None,
    is_delivery_picked_up: bool | None,
    reply_to_msg_id: str | None,
    wa_client: Any,
    operational_lookups: Any,
    client_ordelo: Any,
    wa_msg_id: str | None,
) -> str:
    """Send the one allowed rider-location reply; return its text for the audit trail.

    Pre-pickup and no-active-order both fail closed with a fixed reply and
    make no Ordelo call. Once picked up, Ordelo's response is mapped to fixed
    copy; on `200 location_available` the callback has already sent the pin,
    so nothing is sent here.
    """

    async def _send(text: str) -> str:
        await wa_client.send_message(
            to=recipient, text=text, reply_to_message_id=reply_to_msg_id
        )
        return text

    if not order_number:
        return await _send(RIDER_LOCATION_NO_ORDER_MESSAGE)

    if is_delivery_picked_up is not True:
        return await _send(RIDER_LOCATION_PENDING_MESSAGE)

    base_url = operational_lookups.get_app_url(rest_ref)
    callback_url = build_wa_location_callback_url(base_url, rest_ref)
    idempotency_key = (
        f"{rest_ref}:{order_number}:{recipient}:{wa_msg_id}" if wa_msg_id else None
    )

    outcome = await OrdeloService(
        rest_ref=rest_ref,
        database_client=client_ordelo,
        operational_lookups=operational_lookups,
    ).request_rider_location(
        WaLocationRequest(
            rest_ref=rest_ref,
            order_number=order_number,
            location_requested_by="customer",
            requester_id=recipient,
            callback_url=callback_url,
            idempotency_key=idempotency_key,
        )
    )

    if outcome.status_code == 200:
        return "Rider location was already fresh; callback sent the pin."

    if outcome.status_code == 202:
        return await _send(RIDER_LOCATION_REQUESTED_MESSAGE)

    if outcome.status_code == 409 and outcome.code == "food_not_picked_up":
        return await _send(RIDER_LOCATION_PENDING_MESSAGE)

    if outcome.status_code == 409 and outcome.code == "delivery_not_inflight":
        return await _send(RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE)

    logger.error(
        "request_rider_location failed for order {}: status={} code={}",
        order_number,
        outcome.status_code,
        outcome.code,
    )
    return await _send(RIDER_LOCATION_UNAVAILABLE_MESSAGE)
