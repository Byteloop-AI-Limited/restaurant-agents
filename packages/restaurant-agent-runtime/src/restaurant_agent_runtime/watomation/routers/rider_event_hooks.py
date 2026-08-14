"""
Rider event webhook handlers for the delivery system. These events are called from ordelo.
    . Processes rider event webhooks for food delivery tracking
    . Manages delivery lifecycle from dispatch to completion
    . Updates customers on delivery progress through WhatsApp
    . Sends location tracking links to customers
    . Notifies restaurant staff about rider status
    . Provides delivery confirmation functionality
    . Handles timeout scenarios for deliveries
    . Validates rest_ref path parameter against restaurant_master
    . Uses FastAPI BackgroundTasks for async notifications and graph updates
    . Uses get_payload dependency for extracting request body where needed
  Functions/Classes:
    . validate_rest_ref - Validates rest_ref and returns 404 if invalid
    . get_payload - Extracts JSON payload from incoming request
    . rider_inflight - Handles initial rider assignment and customer notification (uses BackgroundTasks)
    . rider_restaurant_cc_path - Processes food pickup confirmation from restaurant (uses BackgroundTasks)
    . rider_customer_cc_path - Handles delivery completion confirmation to customer (uses BackgroundTasks)
    . rider_restaurant_enter - Sends notification when rider nears restaurant
    . rider_customer_enter - Sends notification when rider nears customer (now uses Depends(get_payload))
    . delivery_timedout_path - Manages delivery timeout scenarios (uses BackgroundTasks)
"""

# %%

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.order_management.delivery_pymodels import DeliverySummary
from restaurant_agent_runtime.services.ordelo_service.datamodels.wa_location_pymodel import (
    WaLocationCallbackPayload,
)
from restaurant_agent_runtime.services.thread_management import ThreadHandler
from restaurant_agent_runtime.web.dependencies import (
    get_graph_adapter,
    get_restaurant_runtime,
)
from restaurant_agent_runtime.watomation.background_task_runner import run_background_task
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    NO_RIDER_OUTCOME_PENDING_MESSAGE,
    NO_RIDER_REFUND_ISSUED_MESSAGE,
    SpecialistFlowView,
    notify_release_and_optionally_terminate,
)
from restaurant_agent_runtime.config import logger

# %% Define Router

router = APIRouter(tags=["rider-event-hooks"])


# %% Define Dependencies and routes
def validate_rest_ref(rest_ref: str, runtime: RestaurantRuntime) -> str:
    """Validate the route against this service's configured restaurant."""
    rest_ref_upper = rest_ref.upper()
    if not runtime.identity.matches(rest_ref_upper):
        raise HTTPException(status_code=404, detail=f"Restaurant not found: {rest_ref}")
    return rest_ref_upper


async def get_payload(request: Request):
    return await request.json()


async def _release_timedout_delivery_if_current(
    *, delivery_summary: dict, graph_adapter: GraphAdapter
) -> None:
    """Release only the matching unassigned delivery after a no-rider event.

    Timeout delivery webhooks can be delayed or replayed. The persisted
    conversation is the boundary that prevents an old event from notifying or
    releasing a newer assigned, picked-up, completed, or replacement order.
    """
    customer_id = delivery_summary.get("customer_id")
    order_number = delivery_summary.get("order_number")
    if not customer_id or not order_number:
        logger.warning(
            "Ignoring delivery timeout without customer_id/order_number: {}",
            delivery_summary,
        )
        return

    try:
        state = await graph_adapter.debug_state_values(recipient=customer_id)
    except Exception:
        logger.exception(
            "Ignoring delivery timeout because state could not be read for {}",
            customer_id,
        )
        return

    flow = SpecialistFlowView.from_state(state)
    if not (
        flow.owns_specialist_work
        and flow.active_agent == "delivery_agent"
        and state.get("order_number") == order_number
        and not flow.is_delivery_rider_assigned
        and not flow.is_delivery_picked_up
    ):
        logger.warning(
            "Ignoring stale delivery timeout for order {} and customer {}",
            order_number,
            customer_id,
        )
        return

    payment_cancelled = delivery_summary.get("payment_cancelled") is True
    if "payment_cancelled" not in delivery_summary:
        logger.warning(
            "Delivery timeout for order {} did not include payment_cancelled; "
            "failing closed for refund confirmation.",
            order_number,
        )

    await notify_release_and_optionally_terminate(
        recipient=customer_id,
        specialist="delivery_agent",
        message=(
            NO_RIDER_REFUND_ISSUED_MESSAGE
            if payment_cancelled
            else NO_RIDER_OUTCOME_PENDING_MESSAGE
        ),
        graph_adapter=graph_adapter,
        terminate=False,
        release_state_overrides={
            "is_payment_cancelled": payment_cancelled,
            "is_delivery_no_rider": True,
        },
    )


# %% When rider is assigned for the delivery
@router.post("/{rest_ref}/rider-inflight")
async def rider_inflight(
    rest_ref: str,
    request: Request,
    background_tasks: BackgroundTasks,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    """
    When the rider has accepted the delivery order, Receives a JSON request body. Parses it as a DeliverySummary. Called by delivery-hooks-> post_rider_event_inflight ->
    toDo - need to add callback to notifications.
        - notify customer of the 2 digit customer confirmation code
        - issue a print request as well
        - For customers, may be include options to download the reciept as PDF ?
    Uses BackgroundTasks for async notifications and graph updates.
    """
    data = await request.json()

    deliver_summary_dict = data["delivery_summary"]
    delivery_summary = DeliverySummary(**deliver_summary_dict)

    customer_confirmation_code = delivery_summary.cust_confirmation_code

    # Run customer graph as background task
    background_tasks.add_task(
        run_background_task,
        "rider_inflight_customer_update",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=delivery_summary.customer_id,
        system_msg=(
            "Call `update_customer` with "
            f"message='Delivery driver has been assigned. Confirmation Code is {customer_confirmation_code}'. "
            "The confirmation code is crucial and must be included."
        ),
        state_update_dict={
            "active_agent": "delivery_agent",
            "is_delivery_rider_assigned": True,
        },
    )

    return {"success": "success"}


# %% Once the rider has collected the food from the restaurant


@router.post("/{rest_ref}/on-restaurant-cc/{order_number}/{customer_id}")
async def rider_restaurant_cc_path(
    rest_ref: str,
    order_number: str,
    customer_id: str,
    background_tasks: BackgroundTasks,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    """
    Handles the update of the rider event status in the graph.
        Should send live-location link to both customer and restaurant
    Uses BackgroundTasks for async notifications and graph updates.
    """
    ordelo_app_url = runtime.operational_lookups.get_app_url("ORDELO")
    background_tasks.add_task(
        run_background_task,
        "rider_restaurant_cc",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=customer_id,
        system_msg=(
            "Call `update_customer` with "
            "message='Delivery driver has picked up the food from the restaurant.'"
        ),
        state_update_dict={
            "active_agent": "delivery_agent",
            "is_delivery_picked_up": True,
            "rider_live_location_url": f"{ordelo_app_url}/location-hooks/live-location-map/{order_number}",
        },
    )
    return {"success": "success"}


# %% On customer confirmation code from rider

@router.post("/{rest_ref}/on-customer-cc/{order_number}/{customer_id}")
async def rider_customer_cc_path(
    rest_ref: str,
    order_number: str,
    customer_id: str,
    background_tasks: BackgroundTasks,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    """
    Handles the update of the rider event status in the graph. Final step in order delivery system.
    Initiated within the rider agent tool, verify_customer_confirmation_code.
        Should send order completion notification to both customer and restaurant
        Captures the payment
    Uses BackgroundTasks for async notifications and graph updates.
    """

    background_tasks.add_task(
        run_background_task,
        "customer_delivery_completion_sequence",
        notify_release_and_optionally_terminate,
        recipient=customer_id,
        specialist="delivery_agent",
        message="Your order has been delivered successfully. Thank you for choosing our restaurant!",
        graph_adapter=graph_adapter,
        terminate=True,
    )
    return {"success": "success"}


# %% Once the rider has entered the customer location


@router.post("/{rest_ref}/on-restaurant-enter/{order_number}")
async def rider_restaurant_enter(
    rest_ref: str,
    order_number: str,
    background_tasks: BackgroundTasks,
    delivery_summary: dict = Depends(get_payload),
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    """
    Handles notification when rider enters restaurant zone.
    Uses BackgroundTasks for async notifications.
    Accepts delivery_summary from request body using get_payload dependency.
    """
    rest_ref = validate_rest_ref(rest_ref, runtime)
    customer_id = delivery_summary.get("delivery_summary", {}).get("customer_id")
    background_tasks.add_task(
        run_background_task,
        "rider_restaurant_enter",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=customer_id,
        system_msg=(
            "Call `update_customer` with "
            "message='Your rider has arrived at the restaurant to pick up your order.'"
        ),
        state_update_dict={
            "active_agent": "delivery_agent",
        },
    )
    return {"success": "success"}


@router.post("/{rest_ref}/on-customer-enter/{order_number}")
async def rider_customer_enter(
    rest_ref: str,
    order_number: str,
    background_tasks: BackgroundTasks,
    delivery_summary: dict = Depends(get_payload),
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    """
    Handles the update of the rider event status in the graph. Created in location_hooks triggered by insert on rider_location_event (job_process_owntracks).
        Should send order completion notification to both customer and restaurant
    Uses BackgroundTasks for async notifications and graph updates.
    Accepts delivery_summary from request body using get_payload dependency.
    """
    cust_confirmation_code = delivery_summary.get("delivery_summary", {}).get(
        "cust_confirmation_code"
    )
    customer_id = delivery_summary.get("delivery_summary", {}).get("customer_id")
    # Send notifications to customer as background task
    background_tasks.add_task(
        run_background_task,
        "rider_customer_enter",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=customer_id,
        system_msg=(
            "Call `update_customer` with "
            f"message='Your rider is near you. Please share the 2 digit confirmation code with the rider: {cust_confirmation_code}'."
        ),
        state_update_dict={
            "active_agent": "delivery_agent",
        },
    )
    return {"success": "success"}


# %%
@router.post("/{rest_ref}/delivery-timedout")
async def delivery_timedout_path(
    rest_ref: str,
    background_tasks: BackgroundTasks,
    delivery_summary: dict = Depends(get_payload),
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    """
    Handles timedout deliveries
    Uses BackgroundTasks for async notifications and graph updates.
    """
    background_tasks.add_task(
        run_background_task,
        "delivery_timedout",
        _release_timedout_delivery_if_current,
        delivery_summary=delivery_summary,
        graph_adapter=graph_adapter,
    )
    return {"success": "success"}


# %% Open Ordelo-to-service rider-location callback


@router.post("/{rest_ref}/wa-location-response")
async def wa_location_response(
    rest_ref: str,
    payload: WaLocationCallbackPayload,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
) -> Response:
    """Receive Ordelo's rider-location result and send the customer a pin.

    Thin and deterministic: no graph invocation, no assistant message. Every
    guard failure sends nothing and mutates no conversation state. Thread
    lookup deliberately uses the non-creating ``get_active_thread`` rather
    than ``debug_state_values(recipient=...)`` (which mints a thread row via
    ``get_or_create_thread`` for an unknown customer) so a callback for a
    customer with no thread cannot create one.
    """
    rest_ref = validate_rest_ref(rest_ref, runtime)

    pool = await runtime.settings.database.get_pool()
    thread_handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    thread_row = await thread_handler.get_active_thread(payload.customer_id)
    if not thread_row or not thread_row.get("thread_id"):
        logger.warning(
            "Ignoring wa-location callback for unknown/inactive thread: customer={}",
            payload.customer_id,
        )
        return Response(status_code=409)

    config = {
        "configurable": {
            "thread_id": str(thread_row["thread_id"]),
            "recipient": payload.customer_id,
        }
    }

    try:
        state = await graph_adapter.debug_state_values(config=config)
    except Exception:
        logger.exception(
            "Ignoring wa-location callback because state could not be read for {}",
            payload.customer_id,
        )
        return Response(status_code=409)

    flow = SpecialistFlowView.from_state(state)
    if not (
        flow.owns_specialist_work
        and flow.active_agent == "delivery_agent"
        and state.get("order_number") == payload.order_number
        and flow.is_delivery_picked_up
        and payload.location_requested_by == "customer"
        and payload.requester_id == payload.customer_id
    ):
        logger.warning(
            "Ignoring stale/mismatched wa-location callback for order {} and customer {}",
            payload.order_number,
            payload.customer_id,
        )
        return Response(status_code=409)

    label = (
        "Rider's latest location"
        if payload.location.source == "whatsapp_current"
        else "Last known at restaurant"
    )

    try:
        await runtime.async_wa_client.send_location(
            to=payload.customer_id,
            latitude=payload.location.latitude,
            longitude=payload.location.longitude,
            name=label,
        )
    except Exception:
        logger.exception("Failed to send rider location pin to {}", payload.customer_id)
        return Response(status_code=502)

    return Response(status_code=204)
