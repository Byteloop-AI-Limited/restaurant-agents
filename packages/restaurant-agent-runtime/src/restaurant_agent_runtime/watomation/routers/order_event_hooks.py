"""Runtime-bound external order and takeaway event endpoints."""

# %%

import asyncio
from datetime import datetime, timezone
from weakref import WeakValueDictionary
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pywa.types import ButtonUrl
from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.order_link import fetch_order_page_link
from restaurant_agent_runtime.services.order_management.food_order_pymodel import FoodOrder
from restaurant_agent_runtime.services.order_management.food_order_reciept import (
    build_wa_order_reciept_for_cust,
)
from restaurant_agent_runtime.services.order_management.takeaway_pymodels import (
    TakeawayPickupTimePayload,
    TakeawayReadyPayload,
)
from restaurant_agent_runtime.watomation.background_task_runner import run_background_task
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    DELIVERY_PAYMENT_PENDING_RIDER_MESSAGE,
    SpecialistFlowView,
    notify_release_and_optionally_terminate,
    retained_specialist_state,
)
from restaurant_agent_runtime.web.dependencies import (
    get_graph_adapter,
    get_restaurant_runtime,
)

# %%

router = APIRouter(tags=["order-event-hooks"])


# The pickup-time webhook carries a recipient but not a Thread ID. In the
# current one-worker application deployment, this process-local key identifies
# the active Restaurant conversation without widening the external contract.
_TAKEAWAY_LIFECYCLE_LOCKS: WeakValueDictionary[tuple[str, str], asyncio.Lock] = (
    WeakValueDictionary()
)


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


def _is_duplicate_delivery_payment_event(state: dict, food_order: FoodOrder) -> bool:
    """Return whether this delivery payment event already owns the checkpoint."""
    flow = SpecialistFlowView.from_state(state)
    return (
        flow.owns_specialist_work
        and flow.active_agent == "delivery_agent"
        and flow.is_payment_successful
        and state.get("order_id") == food_order.order_id
    )


def _takeaway_payment_pending_pickup_system_message() -> str:
    """Return the authoritative collection payment update for the graph."""
    return (
        "AUTHORITATIVE TAKEAWAY PAYMENT EVENT: payment is confirmed and pickup time "
        "is pending. Do not call a menu tool, start a new order, or hand off. Call "
        "`update_customer` with message='We will confirm the pickup time in a moment.'. "
        "Then end this turn."
    )


def _takeaway_lifecycle_lock(rest_ref: str, recipient: str) -> asyncio.Lock:
    """Return the per-conversation lock for authoritative takeaway updates."""
    key = (rest_ref, recipient)
    lock = _TAKEAWAY_LIFECYCLE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _TAKEAWAY_LIFECYCLE_LOCKS[key] = lock
    return lock


async def _run_reserved_takeaway_payment_update(
    *,
    lock: asyncio.Lock,
    recipient: str,
    system_msg: str,
    state_update_dict: dict,
    graph_adapter: GraphAdapter,
) -> None:
    """Run the payment-pending turn, then release its pre-reserved gate."""
    try:
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            system_msg=system_msg,
            state_update_dict=state_update_dict,
        )
    finally:
        lock.release()


async def _run_serialized_takeaway_pickup_completion(
    *,
    rest_ref: str,
    recipient: str,
    specialist: str,
    message: str,
    graph_adapter: GraphAdapter,
    terminate: bool,
) -> None:
    """Run the complete pickup sequence after any payment-pending turn."""
    lock = _takeaway_lifecycle_lock(rest_ref, recipient)
    if lock.locked():
        logger.info(
            "Waiting for earlier takeaway lifecycle work for recipient {}", recipient
        )
    async with lock:
        await notify_release_and_optionally_terminate(
            recipient=recipient,
            specialist=specialist,
            message=message,
            graph_adapter=graph_adapter,
            terminate=terminate,
        )


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

    if food_order.action == "delivery":
        try:
            current_state = await graph_adapter.debug_state_values(recipient=recipient)
        except Exception:
            # The first event must still reach the customer if a transient
            # checkpoint read fails. This is deliberately best-effort replay
            # protection, not a new durable event ledger.
            logger.exception(
                "Could not inspect payment replay state for recipient {}", recipient
            )
        else:
            if _is_duplicate_delivery_payment_event(current_state, food_order):
                logger.info(
                    "Ignoring replayed delivery payment event for order {}",
                    food_order.order_id,
                )
                return {
                    "status": "success",
                    "order_id": food_order.order_id,
                    "order_number": food_order.order_number,
                    "payment_status": food_order.payment_status,
                }

    logger.info(f"food_order: {food_order}")
    logger.info(f"recipient: {recipient}")
    logger.info(f"thread_id: {thread_id}")

    customer_receipt_header, customer_receipt_text = build_wa_order_reciept_for_cust(
        food_order=food_order,
        database_client=runtime.settings.database_client,
    )

    # Best effort, 2 s cap: the receipt always goes out, with or without the link.
    order_link = await fetch_order_page_link(
        runtime, food_order.order_number, recipient
    )
    # A tappable "Order Tracking" button on the receipt itself; no button when there is no link.
    track_buttons = (
        {"buttons": ButtonUrl(title="Order Tracking", url=order_link)}
        if order_link
        else {}
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
            **track_buttons,
        )
        background_tasks.add_task(
            run_background_task,
            "delivery_payment_complete",
            graph_adapter.run_rest_graph_with_custom_msg,
            recipient=recipient,
            system_msg=(
                "AUTHORITATIVE DELIVERY PAYMENT EVENT: the customer has placed an "
                f"order ({food_order.order_id}/{order_number}); payment is confirmed "
                "and delivery-driver allocation is pending. Do not ask the customer "
                "to place another order, select menu items, or make payment again. "
                "Call `update_customer` with "
                f"message={DELIVERY_PAYMENT_PENDING_RIDER_MESSAGE!r}. Then end this turn."
            ),
            state_update_dict=retained_specialist_state(
                "delivery",
                order_id=food_order.order_id,
                order_number=order_number,
                reply_to_msg_id=msg.id,
            ),
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
            **track_buttons,
        )

        # Collection order received, wait for pickup time confirmation
        system_msg = _takeaway_payment_pending_pickup_system_message()
        state_update_dict = retained_specialist_state(
            "takeaway",
            order_id=food_order.order_id,
            order_number=order_number,
            reply_to_msg_id=msg.id,
        )
        lock = _takeaway_lifecycle_lock(rest_ref, recipient)
        if lock.locked():
            logger.info(
                "Waiting to reserve takeaway lifecycle work for recipient {}", recipient
            )
        await lock.acquire()

        try:
            background_tasks.add_task(
                run_background_task,
                "collection_payment_complete",
                _run_reserved_takeaway_payment_update,
                lock=lock,
                recipient=recipient,
                system_msg=system_msg,
                state_update_dict=state_update_dict,
                graph_adapter=graph_adapter,
            )
        except Exception:
            lock.release()
            raise

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

    pickup_time_str = format_time_for_user(summary.pickup_time)
    background_tasks.add_task(
        run_background_task,
        "customer_collection_completion_sequence",
        _run_serialized_takeaway_pickup_completion,
        rest_ref=rest_ref,
        recipient=recipient,
        specialist="takeaway_agent",
        message=(
            f"The order will be ready for collection at *{pickup_time_str}*. "
            "Call the restaurant for any queries."
        ),
        graph_adapter=graph_adapter,
        terminate=True,
    )

    return {
        "status": "success",
        "order_number": summary.order_number,
        "pickup_time": summary.pickup_time,
    }
