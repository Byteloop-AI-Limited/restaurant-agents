"""Runtime-bound helpers for the active payment integration."""

from typing import Any

import httpx

from restaurant_agent_runtime.config import logger


def get_payment_uri(
    order_id: str,
    thread_id: str,
    *,
    payment_settings: Any,
) -> str:
    """Build the configured payment endpoint for an existing FoodOrder."""

    return payment_settings.generate_payment_intent_url(
        order_id=order_id,
        thread_id=thread_id,
    )


async def cancel_payment(
    order_id: str,
    thread_id: str,
    *,
    payment_settings: Any,
) -> bool:
    """Cancel an authorized delivery payment through the configured service."""

    payment_uri = get_payment_uri(
        order_id=order_id,
        thread_id=thread_id,
        payment_settings=payment_settings,
    )
    cancel_payload = {"action": "delivery", "payment_mode": "cancel"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                payment_uri,
                json=cancel_payload,
                headers=payment_settings.headers,
            )
            response.raise_for_status()
            return response.text == ""
        except httpx.HTTPError as exc:
            logger.error(
                "Error during payment cancellation for order {}: {}",
                order_id,
                exc,
            )
            return False
