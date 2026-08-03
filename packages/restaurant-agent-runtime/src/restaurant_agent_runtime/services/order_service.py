"""Runtime-bound delivery-order pricing lookup."""

import httpx

from restaurant_agent_runtime.config import logger


async def get_min_order_value(
    cust_lat: float,
    cust_lon: float,
    rest_ref: str,
    *,
    operational_lookups,
) -> float | None:
    """Retrieve the current minimum order value from the Ordelo boundary."""

    try:
        target_url = (
            f"{operational_lookups.get_app_url('ORDELO')}"
            "/order-hooks/get-min-order-value"
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
