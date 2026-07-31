"""Runtime-bound delivery-order pricing lookup."""

from typing import Any

import httpx

from restaurant_agent_runtime.config import logger


async def get_min_order_value(
    cust_lat: float,
    cust_lon: float,
    rest_ref: str,
    *,
    database_client: Any,
) -> float | None:
    """Retrieve the current minimum order value from the Ordelo boundary."""

    try:
        response = (
            database_client.table("ordelo_config")
            .select("config_value")
            .eq("config_key", "ORDELO_APP_URL")
            .execute()
        )
        if not response.data:
            raise ValueError("ORDELO_APP_URL is not configured")
        target_url = (
            f"{response.data[0]['config_value']}/order-hooks/get-min-order-value"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                target_url,
                params={
                    "customer_latitude": cust_lat,
                    "customer_longitude": cust_lon,
                    "rest_ref": rest_ref,
                },
            )
            response.raise_for_status()
            return response.json().get("min_order_value", -1)
    except httpx.HTTPError as exc:
        logger.error("HTTP error calling Ordelo endpoint: {}", exc)
        return None
    except Exception as exc:
        logger.exception("Unexpected error calling Ordelo endpoint: {}", exc)
        return None
