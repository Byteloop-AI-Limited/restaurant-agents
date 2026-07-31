"""
Order receipt generation and formatting utilities
  . Fetches order items from database for receipt generation
  . Formats order item lines with modifications for display
  . Builds WhatsApp receipts for customers and restaurants
  . Calculates order totals including fees and charges
  Functions/Classes:
    . _fetch_order_items
    . _format_order_item_lines
    . build_wa_order_reciept_for_cust
    . build_wa_order_reciept_for_rest
"""

# %%
from restaurant_agent_runtime.services.order_management.food_order_pymodel import FoodOrder
from restaurant_agent_runtime.services.order_management.order_item_pymodel import OrderItem
from typing import List, Tuple


def _fetch_order_items(order_id: str, *, database_client) -> List[dict]:
    """Helper to retrieve order_items rows for the given order_id.

    Args:
        order_id: Unique identifier of the order.

    Returns:
        A list of order_items rows as dictionaries. Falls back to an empty list
        if the query fails or no items are found.
    """
    try:
        response = (
            database_client.table("order_item")
            .select("product_name, quantity, price, modifications")
            .eq("order_id", order_id)
            .execute()
        )
        return response.data or []
    except Exception as e:  # pragma: no cover – database/network failure
        print(f"⚠️  Failed to fetch order_items for {order_id}: {e}")
        return []


def _format_order_item_lines(items_data: List[dict]) -> List[str]:
    item_lines: List[str] = []
    for item in items_data:
        qty = item.get("quantity", 1)
        name = item.get("product_name", "Item")
        unit_price = item.get("price", 0)
        line_total = unit_price * qty
        item_lines.append(f"*• {qty} × {name}  –  £{line_total:.2f}*")

        modifications = item.get("modifications") or []
        if isinstance(modifications, str):
            modification_values = [modifications]
        else:
            try:
                modification_values = list(modifications)
            except TypeError:
                modification_values = [modifications]

        for modification in modification_values:
            modification_text = str(modification).strip()
            if modification_text:
                item_lines.append(f"   ↳ _{modification_text}_")

    return item_lines


# %%
# --------------------------------------------------------------------------------------
# Customer-facing receipt
# --------------------------------------------------------------------------------------


def build_wa_order_reciept_for_cust(
    *, food_order: FoodOrder, database_client
) -> Tuple[str, str]:
    """Create WhatsApp order-receipt text with basic markdown.

    The function fetches persisted line items for the provided aggregate and
    converts them into a WhatsApp-friendly receipt message.

    WhatsApp supports a subset of Markdown: ``*bold*``, ``_italic_`` and `````monospace````.
    We use ``*`` for bold highlights and a simple middle-dot (•) as a bullet.

    Args:
        food_order: The validated persisted order aggregate.
        database_client: The exact RestaurantRuntime database client.

    Returns:
        A tuple ``(header, text)`` suitable for the ``header`` and ``text``
        parameters in ``WhatsApp.send_message``.
    """

    order = food_order
    order_items = _fetch_order_items(
        order.order_id,
        database_client=database_client,
    )
    if not order_items:
        raise ValueError(f"No order_items found for {order.order_id}")

    # 2️⃣ Build header
    header = f"Order #{order.order_number}"  # eg: Order #ELB-QPRX-28

    # 3️⃣ Build items list
    item_lines = _format_order_item_lines(order_items)

    items_block = "\n".join(item_lines)

    # 4️⃣ Build charges & totals
    charges_lines: List[str] = []
    if order.service_charge:
        charges_lines.append(f"Service charge: £{order.service_charge:.2f}")
    if order.delivery_fee:
        charges_lines.append(f"Delivery fee: £{order.delivery_fee:.2f}")
    if order.small_order_fee:
        charges_lines.append(f"Small order fee: £{order.small_order_fee:.2f}")

    charges_block = "\n".join(charges_lines)

    total_line = f"*Total:* £{order.final_order_value or order.total_price:.2f}"

    # 5️⃣ Assemble message text
    text_parts = [
        "*Items:*",  # title
        items_block,
    ]
    if charges_block:
        text_parts.extend(["", charges_block])
    text_parts.extend(["", total_line])

    if order.notes:
        text_parts.extend(["", "*Notes:*", f"_{order.notes}_"])

    text = "\n".join(text_parts).strip()

    return header, text


# --------------------------------------------------------------------------------------
# Restaurant-facing receipt (no service or delivery charge, total = total_price)
# --------------------------------------------------------------------------------------


def build_wa_order_reciept_for_rest(
    *,
    food_order: FoodOrder,
    database_client=None,
    order_items: List[OrderItem] = None,
) -> Tuple[str, str]:
    """Build WhatsApp receipt text for the restaurant.

    Differences vs. *build_wa_order_reciept_for_cust*:
        • Omits *Service charge* and *Delivery fee* lines.
        • ``Total`` reflects the *total_price* (food value) rather than the final
          customer-facing value.

    Args:
        food_order: The validated persisted order aggregate.
        database_client: Required only when ``order_items`` is omitted.
        order_items: Optional validated line items supplied by the caller.
    """
    order = food_order

    # Use provided order_items if available, otherwise fetch from DB
    if order_items is None:
        if database_client is None:
            raise ValueError("database_client is required when order_items are omitted")
        items_data = _fetch_order_items(
            order.order_id,
            database_client=database_client,
        )
        if not items_data:
            raise ValueError(f"No order_items found for {order.order_id}")
    else:
        # Convert OrderItem Pydantic models to dict format for processing
        items_data = [
            {
                "quantity": item.quantity,
                "product_name": item.product_name,
                "price": item.price,
                "modifications": item.modifications,
            }
            for item in order_items
        ]

    header = f"Order #{order.order_number} (Kitchen)"

    # Items
    item_lines = _format_order_item_lines(items_data)

    items_block = "\n".join(item_lines)

    # Charges – only include small_order_fee if present and non-zero
    charges_lines: List[str] = []
    if order.small_order_fee:
        charges_lines.append(f"Small order fee: £{order.small_order_fee:.2f}")

    charges_block = "\n".join(charges_lines)

    total_line = f"*Total:* £{order.total_price:.2f}"

    text_parts = ["*Items:*", items_block]
    if charges_block:
        text_parts.extend(["", charges_block])
    text_parts.extend(["", total_line])
    if order.notes:
        text_parts.extend(["", "*Notes:*", f"_{order.notes}_"])

    return header, "\n".join(text_parts).strip()
