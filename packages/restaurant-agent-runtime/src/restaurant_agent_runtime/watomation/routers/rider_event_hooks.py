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

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.order_management.delivery_pymodels import DeliverySummary
from restaurant_agent_runtime.web.dependencies import (
    get_graph_adapter,
    get_restaurant_runtime,
)
from restaurant_agent_runtime.watomation.background_task_runner import run_background_task

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
        system_msg=f"`update_customer`: call`send_update_to_customer` with message `Delivery driver has been assigned. Confirmation Code is {customer_confirmation_code}`. Confirmation code is crucial and hence, the agent has to mention this code to customer.",
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
    ordelo_app_url = runtime.settings.project.get_ordelo_url(
        runtime.settings.database_client
    )
    background_tasks.add_task(
        run_background_task,
        "rider_restaurant_cc",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=customer_id,
        system_msg="Call tool `update_customer`: Delivery driver has picked up the food from the restaurant.",
        state_update_dict={
            "active_agent": "delivery_agent",
            "is_delivery_picked_up": True,
            "rider_live_location_url": f"{ordelo_app_url}/location-hooks/live-location-map/{order_number}",
        },
    )
    return {"success": "success"}


# %% On customer confirmation code from rider

async def run_customer_delivery_completion_sequence(
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

    # Notify completion to customer
    first_state_update_dict = {"retain_thread": False}
    first_system_msg = "First, call `send_updates_to_customer` with message_to_be_sent_to_user='Your order has been delivered successfully. Thanks you for choosing our restaurant!'"

    # Terminate conversation after sending message
    second_state_update_dict={"active_agent": "triage_agent"}
    second_system_msg = "call `terminate_conversation` tool to terminate the conversation."

    # Send notifications to customer as background task
    background_tasks.add_task(
        run_background_task,
        "customer_delivery_completion_sequence",
        run_customer_delivery_completion_sequence,
        customer_id=customer_id,
        first_system_msg=first_system_msg,
        first_state_update_dict=first_state_update_dict,
        second_system_msg=second_system_msg,
        second_state_update_dict=second_state_update_dict,
        graph_adapter=graph_adapter,
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
        system_msg="`update_customer`: Rider has arrived at the restaurant to pick up your order.",
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
        system_msg=f"`update_customer`: Rider is near you, please share the 2 digit confirmation code with the rider. Confirmation Code: {cust_confirmation_code}",
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
    customer_id = delivery_summary["customer_id"]
    system_msg = "call tool `update_customer` with message='Sorry we do not have any delivery drivers available right due to high demand. \nNo worries, your payment will be released back to your account right away. If you'd still like to order, you canopt in for takeaway!'. If customer continues the conversation, start from the beginning, asking customer to select the service using `ask_user_to_select_service` tool."

    background_tasks.add_task(
        run_background_task,
        "delivery_timedout",
        graph_adapter.run_rest_graph_with_custom_msg,
        recipient=customer_id,
        system_msg=system_msg,
        state_update_dict={
            "active_agent": "delivery_agent",
            "is_payment_successful": False,
            "retain_thread": False,
        },
    )
    return {"success": "success"}
