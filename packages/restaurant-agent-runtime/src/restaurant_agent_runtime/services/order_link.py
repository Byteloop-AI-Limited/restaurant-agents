"""Fetch a customer's private order-page link from Ordelo for the payment receipt.

Best effort: any failure returns None and the receipt is sent without the line.
Never log the URL or the token.
  Functions/Classes:
    . TIMEOUT_SECS
    . fetch_order_page_link
"""

import httpx

from restaurant_agent_runtime.config import logger

TIMEOUT_SECS = 2.0
MIN_KEY_LENGTH = 32  # same floor OrdeloAgent enforces for ORDELO_WEB_KEY


async def fetch_order_page_link(
    runtime, order_number: str, recipient: str
) -> str | None:
    """Return the https order-page URL for a paid WhatsApp order, or None."""
    try:
        key = getattr(runtime.settings.ordelo, "web_key", "") or ""
        if len(key) < MIN_KEY_LENGTH:
            return None
        base = runtime.operational_lookups.get_app_url("ORDELO").rstrip("/")
        async with httpx.AsyncClient(
            timeout=TIMEOUT_SECS, follow_redirects=False
        ) as client:
            response = await client.post(
                f"{base}/web/access/whatsapp-link",
                json={"order_number": order_number, "recipient": recipient},
                headers={"X-Ordelo-Web-Key": key},
            )
        if response.status_code != 201:
            logger.warning(
                "order link unavailable order={} status={}",
                order_number,
                response.status_code,
            )
            return None
        url = response.json().get("url")
        return url if isinstance(url, str) and url.startswith("https://") else None
    except Exception as exc:  # noqa: BLE001 - never block the receipt
        logger.warning(
            "order link failed order={} error_type={}",
            order_number,
            type(exc).__name__,
        )
        return None
