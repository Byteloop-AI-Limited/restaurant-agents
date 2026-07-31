"""Runtime-bound external order and takeaway event endpoints."""

# %%

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.order_management.food_order_pymodel import FoodOrder
from restaurant_agent_runtime.services.order_management.food_order_reciept import (
    build_wa_order_reciept_for_cust,
)
from restaurant_agent_runtime.services.order_management.takeaway_pymodels import (
    TakeawayPickupTimePayload,
    TakeawayReadyPayload,
)
from restaurant_agent_runtime.watomation.background_task_runner import run_background_task
from restaurant_agent_runtime.web.dependencies import (
    get_graph_adapter,
    get_restaurant_runtime,
)

# %%

router = APIRouter(tags=["order-event-hooks"])


# %% Validation helper
def validate_rest_ref(rest_ref: str, runtime: RestaurantRuntime) -> str:
    """Validate the route against this service's configured restaurant."""
    rest_ref_upper = rest_ref.upper()
    if not runtime.identity.matches(rest_ref_upper):
        raise HTTPException(status_code=404, detail=f"Restaurant not found: {rest_ref}")
    return rest_ref_upper


def format_time_for_user(pickup_time: str | None) -> str:
    """Return a customer-friendly pickup time string."""
    if not pickup_time:
        return "shortly"

    value = pickup_time.strip()
    if not value:
        return "shortly"

    # Keep already human-formatted values unchanged.
    if "am" in value.lower() or "pm" in value.lower():
        return value

    parse_attempts = [
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M:%S"),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M"),
        lambda v: datetime.strptime(v, "%H:%M:%S"),
        lambda v: datetime.strptime(v, "%H:%M"),
    ]
    for parse_time in parse_attempts:
        try:
            dt = parse_time(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(UK_TZ)
            return dt.strftime("%I:%M %p").lstrip("0").lower()
        except ValueError:
            continue

    # Fall back to the original value if format is unknown.
    return value


# %% Payment Complete
@router.post(
    "/{rest_ref}/payment-complete/{recipient}/{thread_id}",
    summary="Mark payment as complete for an order",
    description="""
    Accepts a persisted FoodOrder payload from the external payment/order
    context, sends the customer receipt, and queues the appropriate delivery or
    takeaway graph state update.
    """,
)
async def payment_complete(
    rest_ref: str,
    recipient: str,
    thread_id: str,
    food_order: FoodOrder,
    background_tasks: BackgroundTasks,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    if food_order.recipient != recipient:
        raise HTTPException(
            status_code=400,
            detail="recipient in path does not match payload.recipient",
        )
    if food_order.thread_id != thread_id:
        raise HTTPException(
            status_code=400,
            detail="thread_id in path does not match payload.thread_id",
        )

    logger.info(f"food_order: {food_order}")
    logger.info(f"recipient: {recipient}")
    logger.info(f"thread_id: {thread_id}")

    customer_receipt_header, customer_receipt_text = build_wa_order_reciept_for_cust(
        food_order=food_order,
        database_client=runtime.settings.database_client,
    )

    formatted_wa_text = f"""
    Thank you for the payment.\n
    Your order id is *{food_order.order_id}*.\n
    {customer_receipt_text}
    """

    order_number = food_order.order_number
    if food_order.action == "delivery":
        # Acknowledge the payment
        formatted_wa_text = f"""
        Thank you for the payment.\n
        Your order id is *{food_order.order_id}*.\n
        {customer_receipt_text}
        """

        msg = await runtime.async_wa_client.send_message(
            to=recipient,
            # header=customer_receipt_header,
            text=formatted_wa_text,
        )
        background_tasks.add_task(
            run_background_task,
            "delivery_payment_complete",
            graph_adapter.run_rest_graph_with_custom_msg,
            recipient=recipient,
            system_msg="User has been already thanked for the payment. Only say that we will notify when a delivery driver is assigned.",
            state_update_dict={
                "active_agent": "delivery_agent",
                "order_id": food_order.order_id,
                "order_number": order_number,
                "reply_to_msg_id": msg.id,
                "is_payment_successful": True,
                "retain_thread": True,  # RETAIN the thread
            },
        )
    else:
        # Acknowlege the order for takeaway, not the payment
        formatted_wa_text = f"""
        Your order id is *{food_order.order_id}*.\n
        {customer_receipt_text}
        """
        msg = await runtime.async_wa_client.send_message(
            to=recipient,
            header=customer_receipt_header,
            text=formatted_wa_text,
        )

        # Collection order received, wait for pickup time confirmation
        system_msg = (
            "Thank user for the order. We will confirm the pickup time in a moment"
        )

        background_tasks.add_task(
            run_background_task,
            "collection_payment_complete",
            graph_adapter.run_rest_graph_with_custom_msg,
            recipient=recipient,
            system_msg=system_msg,
            state_update_dict={
                "active_agent": "takeaway_agent",
                "order_id": food_order.order_id,
                "order_number": order_number,
                "reply_to_msg_id": msg.id,
                "is_payment_successful": True,
                "retain_thread": True,
            },
        )

    return {
        "status": "success",
        "order_id": food_order.order_id,
        "order_number": food_order.order_number,
        "payment_status": food_order.payment_status,
    }


# %%


@router.post(
    "/{rest_ref}/address-update/{recipient}",
    summary="Refresh graph state after an external address update",
    description="""
    Accepts the externally persisted customer address, acknowledges the
    customer, and queues delivery-address reconfirmation.
    """,
)
async def address_update(
    rest_ref: str,
    recipient: str,
    background_tasks: BackgroundTasks,
    request: Request,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)

    # Parse and log the incoming customer_master_row payload
    _cust_master_row = await request.json()

    # Avoid long wait, send immediate acknowledgment
    await runtime.async_wa_client.send_message(
        to=recipient, text="Address update received, processing..."
    )

    # If Already in a delivery order, mention that the delivery address cannot be updated. You can know if already in delivery by checking the state.
    background_tasks.add_task(
        run_background_task,
        "address_update",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=recipient,
        human_msg="Hi there, I have just updated my address.",
        system_msg="User has updated the address. There is a need to confirm the delivery address again. Call `confirm_delivery_address`",
        state_update_dict={
            "active_agent": "delivery_agent",
            "is_delivery_address_confirmed": False,
            "customer_address": _cust_master_row,
            "min_order_value": None,
        },
    )

    return {
        "status": "success",
    }


# %% Takeaway Ready
@router.post(
    "/{rest_ref}/takeaway-ready/{order_id}",
    summary="Notify customer that their takeaway order is ready for collection",
    description="""
    Called when the restaurant marks a takeaway order as ready.
    Sends a direct WhatsApp message to the customer informing them their order is ready for collection.
    """,
)
async def takeaway_ready(
    rest_ref: str,
    order_id: str,
    payload: TakeawayReadyPayload,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)

    await runtime.async_wa_client.send_message(
        to=payload.recipient,
        text=f"Your order *#{payload.order_id}* is ready for collection.\nDo not respond, this is a notification.",
    )

    return {
        "status": "success",
        "order_id": payload.order_id,
        "order_number": payload.order_number,
    }


# %% Takeaway Pickup Time Updated

async def run_customer_collection_completions_sequence(
    customer_id: str,
    first_system_msg: str,
    first_state_update_dict: dict,
    second_system_msg: str,
    second_state_update_dict: dict,
    graph_adapter: GraphAdapter,
):
    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=customer_id,
        system_msg=first_system_msg,
        state_update_dict=first_state_update_dict,
    )

    await asyncio.sleep(5)

    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=customer_id,
        system_msg=second_system_msg,
        state_update_dict=second_state_update_dict,
    )


@router.post(
    "/{rest_ref}/takeaway-pickup-time-updated",
    summary="Notify customer of confirmed takeaway pickup time",
    description="""
    Called by the restaurant confirmation service when a takeaway order's pickup time is confirmed or updated.
    Sends the confirmed pickup time to the customer via the graph.
    """,
)
async def takeaway_pickup_time_updated(
    rest_ref: str,
    payload: TakeawayPickupTimePayload,
    background_tasks: BackgroundTasks,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    summary = payload.takeaway_summary
    recipient = summary.customer_id

    logger.info(
        f"takeaway_pickup_time_updated: order_number={summary.order_number} recipient={recipient} pickup_time={summary.pickup_time}"
    )

    # Notify user on the pickup_time
    pickup_time_str = format_time_for_user(summary.pickup_time)
    first_system_msg = f"inform the user `The order will be ready for collection at *{pickup_time_str}*. Call the restaurant for any queries`"
    first_state_update_dict = {
        "active_agent": "takeaway_agent",
        "order_number": summary.order_number,
    }

    # Terminate the conversation
    second_system_msg = "Call `terminate_conversation` to end the conversation"
    second_state_update_dict = {"active_agent": "triage_agent"}

    background_tasks.add_task(
        run_background_task,
        "customer_collection_completion_sequence",
        run_customer_collection_completions_sequence,
        customer_id=recipient,
        first_system_msg=first_system_msg,
        first_state_update_dict=first_state_update_dict,
        second_system_msg=second_system_msg,
        second_state_update_dict=second_state_update_dict,
        graph_adapter=graph_adapter,
    )

    return {
        "status": "success",
        "order_number": summary.order_number,
        "pickup_time": summary.pickup_time,
    }
