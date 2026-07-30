"""
Delivery agent graph setup using create_agent pattern
  . Defines delivery agent prompt and tools
  . Builds a LangGraph agent with WhatsApp response handling
  . Transfers to triage for conversation termination (does not own terminate_conversation)
  Functions/Classes:
    . verify_if_payment_complete
"""

# %%
import uuid
from typing import Annotated

import httpx
from langchain.tools import ToolRuntime
from langchain_core.messages import (
    AIMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.graph import END
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pywa.types import ButtonUrl

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
    send_restaurant_menu_tool as _harness_send_menu_tool,
    transfer_to_takeaway,
    transfer_to_triage,
)
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    confirm_delivery_address_wa,
    send_update_address_wa,
)
from restaurant_agent_runtime.services.payment_ms.payment import cancel_payment
from restaurant_agent_runtime.services.order_service import get_min_order_value


# %%
# %%
async def capture_delivery_address(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    This tool is called ONLY when the user is new and the agent doesnt have user's address.
    It send out a form to fill the user's address.

    Args:
        tool_call_id: The ID of the tool call.
        state: The state of the agent.
        config: The configuration object that may contain additional settings for the operation.

    Returns:
        str: A message indicating the result of the operation.
    """
    if state.get("is_payment_successful", False) is True:
        ctx = runtime.context
        await ctx.wa_client.send_message(
            to=ctx.recipient,
            text="We can't change or capture a new delivery address after payment; please contact us on 01722 656 888.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Address capture blocked because payment is already completed.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: Address capture blocked because payment is already completed."
                    ),
                ]
            },
        )

    if state.get("customer_address", None) is not None:
        return Command(
            goto="deliveryAgent",
            update={
                "messages": [
                    ToolMessage(
                        "Address already captured, call `confirm_delivery_address` tool.",
                        tool_call_id=tool_call_id,
                    ),
                    # AIMessage("/DoNotRespond: Address already captured"),
                ]
            },
        )

    ctx = runtime.context
    await send_update_address_wa(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        rest_ref=ctx.rest_ref,
    )

    return Command(
        goto=END,
        update={
            "min_order_value": None,
            "messages": [
                ToolMessage(
                    "Form to capture address is sent to user", tool_call_id=tool_call_id
                ),
                AIMessage("/DoNotRespond: Please fill the form"),
            ],
        },
    )


# %%
async def update_address_of_existing_user(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    This tool is called when the user intends to update their delivery address.It will capture the user's address.
    It sends out a form to update the user's address.

    Args:
        None

    Returns:
        str: A message indicating the result of the operation.
    """
    if state.get("is_payment_successful", False) is True:
        ctx = runtime.context
        await ctx.wa_client.send_message(
            to=ctx.recipient,
            text="We can't change the delivery address after payment; please contact us on 01722 656 888.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Address update blocked because payment is already completed.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: Address update blocked because payment is already completed."
                    ),
                ]
            },
        )

    if state.get("is_delivery_address_confirmed", None) is True:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Delivery address already confirmed; move to the next step.",
                        tool_call_id=tool_call_id,
                    ),
                ]
            }
        )

    ctx = runtime.context

    await send_update_address_wa(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        rest_ref=ctx.rest_ref,
    )

    return Command(
        goto=END,
        update={
            "min_order_value": None,
            "messages": [
                ToolMessage(
                    "Form to update details is sent to user",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Please fill the form"),
            ],
        },
    )


# %%
async def confirm_delivery_address(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Call this tool when the user has not confirmed their delivery address OR
    if they wish to update their delivery address.

    Args:
        None

    Returns:
        str: A message indicating the result of the operation.
    """
    ctx = runtime.context
    recipient = ctx.recipient

    address: dict | None = state.get("customer_address", None)

    if address is None:
        return "No delivery address found, use tool `capture_customer_address` to capture the address."

    if state.get("is_payment_successful", False) is True:
        ctx = runtime.context
        await ctx.wa_client.send_message(
            to=ctx.recipient,
            text="We can't change the delivery address after payment; please contact us on 01722 656 888.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Address confirmation/update blocked because payment is already completed.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: Address confirmation/update blocked because payment is already completed."
                    ),
                ]
            },
        )


    # Address exists and is already confirmed
    if state.get("is_delivery_address_confirmed", False):
        # already confirmed
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Delivery address already confirmed",
                        tool_call_id=tool_call_id,
                    ),
                ]
            }
        )

    # Address exists, or has been updated, ask for confirmation
    await confirm_delivery_address_wa(recipient, address, wa_client=ctx.wa_client)
    return Command(
        update={
            "messages": [
                    ToolMessage(
                        "Address confirmation sent to user.", tool_call_id=tool_call_id
                    ),
                    AIMessage(
                        f"/DoNotRespond: Please confirm your delivery address ? {address}"
                    ),
                ]
            }
        )


# %%
async def calculate_min_order_value(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Tells the user the minimum order value for delivery.
    Only call this tool when the user has confirmed their delivery address.

    Args:
        None

    Returns:
        str: A message indicating the result of the operation.
    """
    order_number = state.get("order_number", None)
    ctx = runtime.context
    recipient = ctx.recipient

    response = (
        ctx.client_ordelo.table("customer_master")
        .select(
            "house_number",
            "street_name",
            "city",
            "postcode",
            "cust_name",
            "lat",
            "lon",
        )
        .eq("cust_id", recipient)
        .execute()
    )
    customer_master_row = response.data[0]

    lat = customer_master_row.get("lat", None)
    lon = customer_master_row.get("lon", None)

    rest_ref = ctx.rest_ref
    if order_number is not None:
        min_order_value = await get_min_order_value(
            rest_ref=rest_ref, cust_lat=lat, cust_lon=lon
        )
    else:
        _ = uuid.uuid4().hex
        min_order_value = await get_min_order_value(
            rest_ref=rest_ref, cust_lat=lat, cust_lon=lon
        )

    return_msg = f"Minimum order value is £{min_order_value}."
    logger.info(return_msg)

    if min_order_value is None or min_order_value == -1:
        return Command(
            update={
                "active_agent": "delivery_agent",
                "is_delivery_address_confirmed": False,
                "is_outside_delivery_area": True,
                "customer_address": customer_master_row,
                "messages": [
                    ToolMessage(
                        "The provided address is outside our delivery area. Inform the user politely that we cannot deliver to this address, and offer to update the delivery address (call `update_address_of_existing_user`) or switch to takeaway/collection (call `transfer_to_takeaway`). Do NOT transfer to triage.",
                        tool_call_id=tool_call_id,
                    ),
                ],
            }
        )

    return Command(
        update={
            "is_outside_delivery_area": False,
            "min_order_value": min_order_value,
            "customer_address": customer_master_row,
            "messages": [
                ToolMessage(
                    f"Inform the user of the minimum order value £{min_order_value}. Ask them to place the order using our menu web link. Call `send_restaurant_menu_tool` to send the menu.",
                    tool_call_id=tool_call_id,
                ),
            ],
        }
    )


# %%
async def verify_if_payment_complete(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    LLM Tool: Verifies if the payment for the user's order is complete.

    This tool should be called whenever the user claims to have completed the payment or requests an update on their order status.
    It checks the current payment status and, if necessary, informs the user about the minimum order value for delivery based on their location.

    Args:
        None

    Returns:
        str: A message indicating whether the payment is complete, awaiting, or if additional action is needed.
    """
    ctx = runtime.context
    order_id = state.get("order_id", None)

    if order_id is None:
        return "Please place the order first."

    payment_status = (
        ctx.client_ordelo.table("food_order")
        .select("payment_status", "order_number")
        .eq("order_id", order_id)
        .execute()
    )

    is_payment_successful = (
        payment_status.data[0]["payment_status"] == "requires_capture"
    )
    order_number = payment_status.data[0]["order_number"]

    if is_payment_successful:
        return Command(
            update={
                "is_payment_successful": True,
                "is_delivery_rider_assigned": False,
                "messages": [
                    ToolMessage(
                        f"Payment is complete. Your order number is {order_number}. In a moment, we will notify you when a delivery driver is assigned.",
                        tool_call_id=tool_call_id,
                    ),
                ],
            }
        )
    else:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Payment is not complete. Please complete the payment.",
                        tool_call_id=tool_call_id,
                    ),
                ]
            }
        )


# %% General query tool
async def answer_general_query(
    question: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Answers general restaurant queries and optionally sends a WhatsApp location pin.

    Use this tool for restaurant-info questions such as contact details, address/location,
    and delivery-only policy. If the user asks for location/directions, this tool sends a
    WhatsApp location pin.

    Args:
        question: The user's question or intent (free text).

    Returns:
        str: A short message the agent can send back to the user.
    """
    _ = tool_call_id

    q = (question or "").strip().lower()

    # TODO: load restaurant details from restaurant_agent_runtime.config/DB
    phone = "PLACEHOLDER_PHONE"
    address = "PLACEHOLDER_ADDRESS"
    opening_hours = "PLACEHOLDER_HOURS"

    is_payment_successful = state.get("is_payment_successful", False) is True

    if any(
        k in q for k in ["where", "address", "location", "directions", "map", "pin"]
    ):
        # TODO: load coordinates and restaurant name from restaurant_agent_runtime.config
        return f"Here is our location. Address: {address}."

    if any(k in q for k in ["phone", "number", "call", "contact"]):
        return f"Phone number: {phone}."

    if any(
        k in q
        for k in ["hours", "opening", "open", "close", "closing", "time", "times"]
    ):
        return f"Delivery opening hours: {opening_hours}."

    if any(k in q for k in ["takeaway", "collection", "pickup", "pick up"]):
        return "I can transfer you to our takeaway team for collection orders."

    if any(k in q for k in ["dine in", "dine-in", "eat in", "reservation", "table"]):
        return "I can transfer you to our dine-in reservation team."

    if any(k in q for k in ["add", "extra", "change", "edit"]):
        if is_payment_successful:
            return "After payment, we can't add items or change the delivery address."
        return "Before payment, please add items using the menu web link; we can't edit the cart via chat."

    return (
        f"Deliveries only via WhatsApp. Address: {address}. Phone: {phone}. "
        f"Hours: {opening_hours}."
    )


# %% get_rider_live_location_link tool
async def send_rider_live_location_link(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends a live location link to the customer.
    Args:
        None

    Returns:
        str: A message indicating the result of the operation.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    order_id = state.get("order_id")
    reply_to_msg_id = state.get("reply_to_msg_id")
    rider_live_location_url = state.get("rider_live_location_url")

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(rider_live_location_url, timeout=10.0)
        if response.status_code != 200:
            raise ValueError(f"Unexpected status {response.status_code}")
    except Exception:
        await ctx.wa_client.send_message(
            to=recipient,
            text="Cannot obtain live location of the rider. Please try again later.",
            reply_to_message_id=reply_to_msg_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Cannot obtain live location of the rider. Please try again later.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    await ctx.wa_client.send_message(
        to=recipient,
        text="Live location link",
        reply_to_message_id=reply_to_msg_id,
        buttons=ButtonUrl(
            title="Live Location",
            url=rider_live_location_url,
        ),
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    f"Live location link sent to customer: {order_id}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Live location link sent to customer"),
            ],
        }
    )


# %% Check delivery status
async def check_delivery_driver_allocation_status(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
    is_timed_out: bool = False,
):
    """
    Checks if the delivery driver has been allocated to the order.
    Args:
        is_timed_out: Whether the order is timed out or not. Defaults to False
    Returns:
        str: A message indicating the result of the operation.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    order_number = state.get("order_number", None)
    order_id = state.get("order_id", None)
    thread_id, _ = await ctx.thread_handler.get_or_create_thread(recipient)

    if order_id is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Order id not found in state.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("You have not placed any order."),
                ],
            }
        )
    if is_timed_out:
        await ctx.wa_client.send_message(
            to=recipient,
            text="""
Sorry, we do not have any delivery drivers available right now.
We will be cancelling your payment and the amount you paid will be released back to you.
Please try again later.
""",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        logger.info(
            f"Attempting to cancel payment for order_id={order_id}, thread_id={thread_id}"
        )
        result = await cancel_payment(order_id=order_id, thread_id=str(thread_id))
        logger.info(f"Payment cancellation result for order_id={order_id}: {result}")

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Sorry, we do not have any delivery drivers available right now. We have not go through with your payment. Please try again later.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: Sorry, we do not have any delivery drivers available right now. We have not go through with your payment. Please try again later."
                    ),
                ],
            }
        )

    async with httpx.AsyncClient() as client:
        orderlo_url = ctx.project_settings.get_ordelo_url(ctx.client_ordelo)
        logger.info(f"Orderlo URL: {orderlo_url}")
        response = await client.get(
            f"{orderlo_url}/delivery-hooks/check-rider-allocation-status/{order_number}",
        )
    delivery_summary_status = response.json()["delivery_summary_status"]

    if delivery_summary_status == "unassigned":
        await ctx.wa_client.send_message(
            to=recipient,
            text="We are still looking for a delivery driver for your order.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "We are still looking for a delivery driver for your order.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: We are still looking for a delivery driver for your order."
                    ),
                ],
            }
        )
    elif delivery_summary_status == "assigned":
        await ctx.wa_client.send_message(
            to=recipient,
            text="Delivery driver assigned to the order.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Delivery driver assigned to the order.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("/DoNotRespond: Delivery driver assigned to the order."),
                ],
            }
        )
    elif delivery_summary_status == "timedout":
        await ctx.wa_client.send_message(
            to=recipient,
            text="Sorry, we do not have any delivery drivers available right now.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Sorry, we do not have any delivery drivers available right now.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: Sorry, we do not have any delivery drivers available right now."
                    ),
                ],
            }
        )

    pass


# %% Tool to send welcome message
async def send_welcome_msg(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends a personalized welcome message to the user.
    Call this tool at the start of a new conversation to greet the user.

    Args:
        None

    Returns:
        Command: A command with the welcome message sent to the user.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    user_name = state.get("wa_name", "there")

    welcome_text = f"""Hi {user_name}! Welcome!
We are excited to offer a limited-time *20% off* on deliveries!
    """

    await ctx.wa_client.send_message(
        to=recipient,
        text=welcome_text,
    )

    return Command(
        goto="deliveryAgent",
        update={
            "messages": [
                ToolMessage(
                    f"Welcome message sent to {user_name}. Next step: confirm delivery address.",
                    tool_call_id=tool_call_id,
                ),
            ],
        },
    )


# %% Tool to send update to customers
async def send_updates_to_customer(
    update_to_be_sent: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends an update to the customer regarding their order.

    Args:
        update_to_be_sent: The update message to send.

    Returns:
        str: A message indicating the result of the operation.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    reply_to_msg_id = state.get("reply_to_msg_id")

    await ctx.wa_client.send_message(
        to=recipient,
        text=update_to_be_sent,
        reply_to_message_id=reply_to_msg_id,
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    f"Update sent to customer: {update_to_be_sent}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    f"/DoNotRespond: Update sent to customer: {update_to_be_sent}"
                ),
            ],
        }
    )


# %%
async def send_restaurant_menu_tool(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """Send the delivery menu link; guards address capture and confirmation first."""
    if state.get("customer_address") is None:
        return "Address not available. Call `capture_delivery_address` first."
    if state.get("is_delivery_address_confirmed") is not True:
        return "Delivery address not yet confirmed. Call `confirm_delivery_address` first."
    return await _harness_send_menu_tool(state=state, tool_call_id=tool_call_id, runtime=runtime)


# %%
delivery_tools = [
    send_welcome_msg,
    answer_general_query,
    confirm_delivery_address,
    capture_delivery_address,
    update_address_of_existing_user,
    calculate_min_order_value,
    send_restaurant_menu_tool,
    verify_if_payment_complete,
    send_updates_to_customer,
    check_delivery_driver_allocation_status,
    send_rider_live_location_link,
    transfer_to_takeaway,  # Handoff to takeaway agent
    transfer_to_triage,  # Handoff to triage for out-of-scope queries
]

delivery_tools = [tool(service) for service in delivery_tools]

# %% Import shared state schemas, transfer tools, and middleware from agent_harness
from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    ContextSchema,
    cleanup_before_model,
    respond_on_wa,
    transfer_to_triage,
)
from langchain.agents import create_agent


# %%
def build_delivery_agent(*, model, system_prompt: str, extra_tools=()):
    return create_agent(
        model=model,
        tools=[*delivery_tools, *extra_tools],
        system_prompt=system_prompt,
        middleware=[
            cleanup_before_model,
            respond_on_wa,
        ],
        state_schema=AgentState,
        context_schema=ContextSchema,
    )
