"""
Order services for WhatsApp automation
  . Provides reusable helpers for order pricing lookups
  . Retrieves minimum order value from database or pricing service fallback
  . Resolves restaurant coordinates via explicit values or rest_ref lookup
  . Generates minimum order value messages based on coordinates
  . Calls Ordelo endpoint for minimum order value using coordinates
  . Creates food orders with order items in database with rollback support
  . Captures payments for orders using Stripe payment microservice
  . Integrates with Supabase for order persistence and httpx for async HTTP
Functions/Classes:
  . _call_pricing_service - Calls pricing microservice
  . _resolve_restaurant_coordinates - Resolves restaurant coordinates
  . get_min_order_value - Calls Ordelo endpoint with coordinates for minimum order value
  . get_min_order_value_for_location - Builds delivery message for customer location
  . create_order_with_items - Creates order and order items with transaction rollback
  . capture_payment_for_order - Captures payment for order with restaurant confirmation
"""

# %%
from __future__ import annotations

from typing import Optional, Tuple

import httpx

from restaurant_agent_core.config import client_ordelo, logger


def _resolve_restaurant_coordinates(
    rest_lat: Optional[float], rest_lon: Optional[float], rest_ref: Optional[str]
) -> Tuple[float, float]:
    """Return restaurant coordinates using explicit values or rest_ref lookup."""
    if rest_lat is not None or rest_lon is not None:
        if rest_lat is None or rest_lon is None:
            raise ValueError("Both rest_lat and rest_lon are required when provided")
        return rest_lat, rest_lon

    if rest_ref:
        response = (
            client_ordelo.table("restaurant_master")
            .select("lat, lon")
            .eq("rest_ref", rest_ref.upper())
            .execute()
        )
        records = response.data if response else []
        if not records:
            raise ValueError(f"Restaurant with ref '{rest_ref}' not found")

        record = records[0]
        lat = record.get("lat")
        lon = record.get("lon")
        if lat is None or lon is None:
            raise ValueError(
                f"Restaurant '{rest_ref}' does not have lat/lon coordinates configured"
            )

        return float(lat), float(lon)

    raise ValueError("Either rest_lat/rest_lon or rest_ref is required")


# %%


async def get_min_order_value(
    cust_lat: float,
    cust_lon: float,
    rest_ref: str,
) -> Optional[float]:
    """
    Retrieve minimum order value by calling the Ordelo endpoint with coordinates.

    Args:
        cust_lat: Customer latitude
        cust_lon: Customer longitude
        restaurant_ref: Restaurant reference code

    Returns:
        Minimum order value as float, or None if request fails
    """
    try:
        # Fetch Ordelo app URL from restaurant_agent_core.config
        ordelo_app_url = (
            client_ordelo.table("ordelo_config")
            .select("config_value")
            .eq("config_key", "ORDELO_APP_URL")
            .execute()
            .data[0]["config_value"]
        )

        # Build the target URL
        target_url = f"{ordelo_app_url}/order-hooks/get-min-order-value"

        # Make async GET request with query parameters
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

            result = response.json()
            min_order_value = result.get("min_order_value", -1)

            return min_order_value

    except httpx.HTTPError as http_err:
        logger.error(f"HTTP error calling Ordelo endpoint: {http_err}")
        return None
    except Exception as err:
        logger.exception(f"Unexpected error calling Ordelo endpoint: {err}")
        return None


def get_min_order_value_for_location(
    cust_lat: float,
    cust_lon: float,
    *,
    rest_lat: Optional[float] = None,
    rest_lon: Optional[float] = None,
    rest_ref: Optional[str] = None,
) -> str:
    """Return human-readable minimum order value message for lat/lon pair."""
    restaurant_lat, restaurant_lon = _resolve_restaurant_coordinates(
        rest_lat, rest_lon, rest_ref
    )

    payload = {
        "total_food_value": 0,
        "restaurant_latitude": restaurant_lat,
        "restaurant_longitude": restaurant_lon,
        "customer_latitude": cust_lat,
        "customer_longitude": cust_lon,
    }

    # ToDo - When there is a requirement, use orddelo url to hit the right endpoint
    response_json = get_min_order_value(payload)
    if not response_json:
        return ""

    message_parts: list[str] = []
    for option in response_json.get("delivery_options", []):
        if option.get("vehicle_type") == "car":
            message_parts.append(option.get("message", ""))

    return "".join(message_parts)


# %%


# async def create_order_with_items(
#     recipient: str, thread_id: str, order_items: List[OrderItem], rest_ref: str
# ) -> Dict[str, Any]:
#     """
#     Creates a new food order with order items in the database.

#     Args:
#         recipient: Customer phone number
#         thread_id: WhatsApp thread ID
#         order_items: List of OrderItem objects
#         rest_ref: Restaurant reference code

#     Returns:
#         Dict with success status, order_id, order_number, or error details
#     """
#     order_dt: str = datetime.now().strftime("%Y-%m-%d")

#     # Calculate total price from order items
#     total_price = sum(item.price * item.quantity for item in order_items)

#     # Get next sequence number
#     try:
#         seq_number = client_ordelo.rpc(
#             "get_next_daily_seq", {"input_date": order_dt}
#         ).execute()
#     except Exception as e:
#         error_message = str(e)
#         logger.error(f"Error getting sequence number: {error_message}")
#         return {
#             "success": False,
#             "error": "Failed to get sequence number",
#             "details": error_message,
#         }

#     # Create order reference for given recipient and date
#     order_reference = create_order_reference(recipient, order_dt)
#     order_id = f"{order_reference}-{seq_number.data}"
#     order_number = f"{rest_ref.upper()}-{order_reference}-{seq_number.data}"

#     insert_payload = {
#         "order_id": order_id,
#         "order_number": order_number,
#         "seq_id": seq_number.data,
#         "recipient": recipient,
#         "thread_id": thread_id,
#         "action": "delivery",
#         "total_price": total_price,
#         "payment_status": "requires_payment",
#     }

#     # Insert into FoodOrder
#     try:
#         food_order_response = (
#             client_ordelo.table("food_order").insert(insert_payload).execute()
#         )
#         if not food_order_response.data:
#             logger.error(f"Warning: Inserting food order {order_id} returned no data.")
#             return {
#                 "success": False,
#                 "error": "No data returned from food_order insert",
#             }
#     except Exception as e:
#         error_message = str(e)
#         logger.error(f"Error inserting food order {order_id}: {error_message}")
#         return {
#             "success": False,
#             "error": "Failed to insert food order",
#             "details": error_message,
#         }

#     # Insert order_items - only proceed if food_order insert was successful
#     try:
#         # Update order_id for all items
#         items_to_insert = [
#             item.model_copy(update={"order_id": order_id}) for item in order_items
#         ]
#         order_items_response = (
#             client_ordelo.table("order_item")
#             .insert([x.model_dump() for x in items_to_insert])
#             .execute()
#         )
#         if not order_items_response.data:
#             logger.error(
#                 f"Warning: Inserting order items for order {order_id} returned no data."
#             )
#             # Attempt to delete the potentially orphaned food_order
#             try:
#                 client_ordelo.table("food_order").delete().eq(
#                     "order_id", order_id
#                 ).execute()
#                 logger.error(
#                     f"Rollback attempted: Deleted food_order {order_id} due to order_item insert issue (no data)."
#                 )
#             except Exception as del_e:
#                 logger.error(
#                     f"Error during rollback: Failed to delete food_order {order_id}: {del_e}"
#                 )
#             return {
#                 "success": False,
#                 "error": "No data returned from order_item insert operation",
#                 "details": "Insert seemed successful but no data was returned. Rollback attempted.",
#             }
#     except Exception as e:
#         error_message = str(e)
#         logger.error(
#             f"Error inserting order items for order {order_id}: {error_message}"
#         )
#         # Attempt to delete the potentially orphaned food_order
#         try:
#             client_ordelo.table("food_order").delete().eq(
#                 "order_id", order_id
#             ).execute()
#             logger.error(
#                 f"Rollback attempted: Deleted food_order {order_id} due to order_item insert failure."
#             )
#         except Exception as del_e:
#             logger.error(
#                 f"Error during rollback: Failed to delete food_order {order_id}: {del_e}"
#             )
#         return {
#             "success": False,
#             "error": "Failed to insert order items",
#             "details": error_message + ". Rollback attempted.",
#         }

#     # If both inserts succeeded and returned data
#     return {"success": True, "order_id": order_id, "order_number": order_number}


# async def capture_payment_for_order(
#     order_id: str, thread_id: str, capture_payload: dict, restaurant_cc: int
# ) -> Optional[str]:
#     """
#     Captures a payment for the specified order using the payment microservice.

#     Args:
#         order_id: The ID of the order for which payment should be captured
#         restaurant_cc: Restaurant confirmation code

#     Returns:
#         Payment URL string if successful, otherwise None
#     """
#     # food_order = FoodOrder.from_order_id(order_id=order_id)
#     # if not food_order:
#     #     logger.error(f"FoodOrder not found for order_id: {order_id}")
#     #     return None

#     payment_uri = get_payment_uri(order_id=order_id, thread_id=thread_id)

#     # Call stripe
#     async with httpx.AsyncClient() as _client:
#         logger.info(
#             f"Capturing payment for order {order_id} with payment URI: {payment_uri}"
#         )
#         try:
#             logger.info(f"Capture payload: {capture_payload}")
#             capture_payload["restaurant_confirmation_code"] = str(restaurant_cc)
#             logger.info(f"Capture payload: {capture_payload}")
#             res = await _client.post(
#                 payment_uri,
#                 json=capture_payload,
#                 headers=ms_settings.stripe_headers,
#             )
#             res.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
#             return res.text
#         except httpx.HTTPError as e:
#             logger.error(f"Error during payment capture for order {order_id}: {e}")
#             if "res" in locals():
#                 logger.error(res.text)
#             return None


# %%
""" Test



# %%
"""
