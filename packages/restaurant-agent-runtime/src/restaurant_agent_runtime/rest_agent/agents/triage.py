# %% [CELL 1] Core Imports
"""Triage agent for onboarding, specialist routing, and conversation termination.
  . Handles service intent classification for a single configured restaurant
  . Routes to specialist agents (delivery, takeaway) on explicit intent
  . Answers general queries (parking, complaints, contact info) directly
  . Owns terminate_conversation — the only agent that can end sessions
  . Manages marketing consent capture before termination
Functions/Classes:
  . context_aware_prompt
  . send_welcome_message
  . ask_user_to_select_service
  . capture_marketing_consent
  . terminate_conversation
"""

from typing import Annotated

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools.base import InjectedToolCallId
from langgraph.graph import END
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
    cleanup_before_model,
    respond_on_wa,
    transfer_to_delivery,
    transfer_to_takeaway,
)
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    select_marketing_consent_wa_send,
    select_enquiry_wa_send,
    select_service_wa_send,
    send_welcome_msg_wa,
)
from restaurant_agent_runtime.rest_agent.prompt_runtime import render_prompt_middleware
from restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel import (
    RestaurantComplaintRequest,
)
from restaurant_agent_runtime.services.ordelo_service.ordelo_service import OrdeloService
from restaurant_agent_runtime.services.ordelo_service.datamodels.cust_rest_map_pymodel import (
    CustRestMap,
)


# %% Tool 1: send_welcome_message
@tool
async def send_welcome_message(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends welcome text and immediately triggers service selection buttons.

    Call this at the start of a new conversation.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    wa_name = state.get("wa_name", "there")
    rest_ref = (state.get("rest_ref") or ctx.rest_ref).lower()

    await send_welcome_msg_wa(
        recipient=recipient,
        user_name=wa_name,
        wa_client=ctx.wa_client,
        restaurant_name=ctx.restaurant_name,
    )

    await select_service_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
        operational_lookups=ctx.operational_lookups,
        delivery_button_label=ctx.delivery_button_label,
        takeaway_button_label=ctx.takeaway_button_label,
    )

    return Command(
        goto=END,
        update={
            "rest_ref": rest_ref,
            "active_agent": "triage_agent",
            "messages": [
                ToolMessage(
                    "Service selection buttons sent (Takeaway/Delivery/Enquiry).",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Please select how I can help you today."),
            ],
        },
    )

    return Command(
        goto=END,
        update={
            "rest_ref": rest_ref,
            "active_agent": "triage_agent",
            "messages": [
                ToolMessage(
                    (
                        f"Welcome message sent to {wa_name}. "
                        "Service selection buttons sent."
                    ),
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    "/DoNotRespond: Welcome sent and service selection requested."
                ),
            ],
        },
    )


# %% Tool 2: ask_user_to_select_service
@tool
async def ask_user_to_select_service(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends interactive WhatsApp buttons asking user to select service type.
    MUST be called after every response to guide user to select Takeaway/Delivery/Something Else.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    rest_ref = (state.get("rest_ref") or ctx.rest_ref).lower()

    await select_service_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
        operational_lookups=ctx.operational_lookups,
        delivery_button_label=ctx.delivery_button_label,
        takeaway_button_label=ctx.takeaway_button_label,
    )


@tool
async def ask_user_to_select_enquiry(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """Show the supported enquiry choices after the customer selects Enquiry."""
    ctx = runtime.context
    await select_enquiry_wa_send(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        rest_ref=(state.get("rest_ref") or ctx.rest_ref).lower(),
        menu=ctx.enquiry_menu,
    )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage("Enquiry options sent.", tool_call_id=tool_call_id),
                AIMessage("/DoNotRespond: Waiting for enquiry selection."),
            ]
        },
    )

# %% Tool 3: capture_marketing_consent
@tool
async def capture_marketing_consent(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
    explicit_subscription: bool = False,
):
    """
    Sends marketing consent buttons (Yes/No) to the user.
    Call this before terminating the conversation to ask if the user wants marketing updates.
    Do not call if ask_for_consent is false in state.
    """
    # Early exit if the question already asked
    if not state.get("ask_for_consent", False) and not explicit_subscription:
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Marketing consent prompt is not needed. Proceed with termination.",
                        tool_call_id=tool_call_id,
                    ),
                ],
            },
        )

    ctx = runtime.context
    recipient = ctx.recipient
    rest_ref = (state.get("rest_ref") or ctx.rest_ref).lower()

    if explicit_subscription:
        try:
            consent = CustRestMap.from_cust_id_and_rest_ref(
                recipient,
                rest_ref,
                database_client=ctx.client_ordelo,
            )
        except ValueError:
            consent = None
        if consent is not None and consent.has_consent:
            return Command(
                goto=END,
                update={
                    "messages": [
                        ToolMessage(
                            "Customer is already subscribed to offers.",
                            tool_call_id=tool_call_id,
                        ),
                        AIMessage("You're already subscribed to offers."),
                    ]
                },
            )

    await select_marketing_consent_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
    )

    return Command(
        goto=END,
        update={
            "ask_for_consent": False,
            "messages": [
                ToolMessage(
                    "Marketing consent buttons sent (Yes/No).",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Waiting for marketing consent response."),
            ],
        },
    )


@tool
async def submit_restaurant_complaint(
    description: str,
    order_reference: str | None,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """Schedule a restaurant-admin complaint notification through Ordelo."""
    ctx = runtime.context
    result = await OrdeloService(
        rest_ref=ctx.rest_ref,
        database_client=ctx.client_ordelo,
        operational_lookups=ctx.operational_lookups,
    ).submit_restaurant_complaint(
        RestaurantComplaintRequest(
            rest_ref=ctx.rest_ref,
            cust_id=ctx.recipient,
            cust_name=state.get("wa_name"),
            order_reference=order_reference,
            description=description,
        )
    )
    if result is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Complaint could not be scheduled. Ask the customer to call the restaurant.",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    "Complaint submitted to Ordelo for restaurant-admin notification.",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("I've passed your complaint to the restaurant team."),
            ]
        },
    )

# %% Terminate conversation tool (owned exclusively by triage)
@tool
async def terminate_conversation(
    reason_for_terminating_conversation: str,
    message_to_be_sent_to_user: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Terminates the conversation and marks the thread as inactive.
    Call this tool when instructed by system messages to end the session.

    Scenarios when this tool should be called:
    1. Delivery cycle is complete (food delivered successfully)
    2. Customer is outside delivery area
    3. On timeouts (e.g., no delivery driver available after extended wait)

    Args:
        reason_for_terminating_conversation: Internal reason for ending the conversation (for logging).
        message_to_be_sent_to_user: A polite message to send to the user explaining the conversation is ending.

    Returns:
        Command: State update with ToolMessage and AIMessage indicating conversation ended.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    ask_for_consent = state.get("ask_for_consent", False)

    if ask_for_consent:
        return "User has pending marketing consent. Call `capture_marketing_consent` before terminating."

    await ctx.wa_client.send_message(
        to=recipient,
        text=f"{message_to_be_sent_to_user}\n\nThank you and good bye! 👋",
    )

    await ctx.thread_handler.make_threads_inactive(recipient=recipient)

    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    f"Conversation terminated. Reason: {reason_for_terminating_conversation}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Conversation ended"),
            ],
            "ask_for_consent": False,
        },
    )


# %% Build triage agent
triage_tools = [
    send_welcome_message,
    ask_user_to_select_service,
    ask_user_to_select_enquiry,
    capture_marketing_consent,
    submit_restaurant_complaint,
    terminate_conversation,
    transfer_to_delivery,
    transfer_to_takeaway,
]

def build_triage_agent(*, model, system_prompt: str, extra_tools=()):
    return create_agent(
        model=model,
        tools=[*triage_tools, *extra_tools],
        system_prompt=system_prompt,
        middleware=[
            render_prompt_middleware(system_prompt),
            cleanup_before_model,
            respond_on_wa,
        ],
        state_schema=AgentState,
        context_schema=ContextSchema,
    )
