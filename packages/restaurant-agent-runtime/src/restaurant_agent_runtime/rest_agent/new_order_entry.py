"""Shared deterministic effects for starting a new restaurant order."""

from __future__ import annotations

import re
from typing import Any, Literal

from loguru import logger
from pywa_async import WhatsApp

from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)


def normalize_min_order_value(raw_min_order_value: Any) -> float:
    """Coerce a persisted minimum-order value for menu rendering."""
    if raw_min_order_value in (None, ""):
        return 0.0
    try:
        return float(raw_min_order_value)
    except (TypeError, ValueError):
        cleaned_value = re.sub(r"[^\d\.\-]", "", str(raw_min_order_value)).strip()
        if cleaned_value:
            try:
                return float(cleaned_value)
            except ValueError:
                pass
    logger.warning(
        "Invalid min_order_value in state: {}. Falling back to 0.0",
        raw_min_order_value,
    )
    return 0.0


async def send_new_order_closed_message(
    *,
    recipient: str,
    wa_client: WhatsApp,
    reply_to_message_id: str | None = None,
) -> str:
    """Send the authoritative unavailable-service response without an LLM turn."""
    text = "Ordering is currently closed."
    await wa_client.send_message(
        to=recipient,
        text=text,
        reply_to_message_id=reply_to_message_id,
    )
    return text


async def send_new_order_menu(
    *,
    recipient: str,
    state: dict,
    rest_ref: str,
    wa_client: WhatsApp,
    logo_url: str,
    operational_lookups: OperationalLookupCache,
    thread_handler: Any,
    order_type: Literal["delivery", "takeaway"],
    reply_to_message_id: str | None = None,
) -> Literal["sent", "closed", "failed"]:
    """Send a menu through the exact runtime after a final availability check."""
    from restaurant_agent_runtime.rest_agent.agent_wa_senders import send_restaurant_menu

    if not operational_lookups.accepts_new_order(order_type, recipient):
        await send_new_order_closed_message(
            recipient=recipient,
            wa_client=wa_client,
            reply_to_message_id=reply_to_message_id,
        )
        return "closed"

    thread_id, _ = await thread_handler.get_or_create_thread(recipient)
    menu_err = await send_restaurant_menu(
        recipient=recipient,
        minimum_order=normalize_min_order_value(state.get("min_order_value")),
        thread_id=str(thread_id),
        rest_ref=rest_ref,
        order_type=order_type,
        wa_client=wa_client,
        logo_url=logo_url,
        operational_lookups=operational_lookups,
    )
    if isinstance(menu_err, ValueError):
        await wa_client.send_message(
            to=recipient,
            text="Sorry, I couldn't send the menu link right now. Please try again later.",
            reply_to_message_id=reply_to_message_id,
        )
        return "failed"
    return "sent"
