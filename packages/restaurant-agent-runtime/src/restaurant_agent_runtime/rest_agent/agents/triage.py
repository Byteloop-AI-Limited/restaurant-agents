# %% [CELL 1] Core Imports
"""Triage agent for onboarding, specialist routing, and conversation termination.
  . Handles service intent classification for a single configured restaurant
  . Routes to specialist agents (delivery, takeaway) on explicit intent
  . Answers general queries (parking, feedback, contact info) directly
  . Owns terminate_conversation — the only agent that can end sessions
  . Manages marketing consent capture before termination
Functions/Classes:
  . context_aware_prompt
  . send_welcome_message
  . ask_user_to_select_service
  . capture_marketing_consent
  . submit_restaurant_feedback
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
    transfer_to_dinein,
    transfer_to_takeaway,
)
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    select_marketing_consent_wa_send,
    select_enquiry_wa_send,
    select_restaurant_wa_send,
    select_service_wa_send,
    send_welcome_msg_wa,
)
from restaurant_agent_runtime.rest_agent.prompt_runtime import render_prompt_middleware
from restaurant_agent_runtime.rest_agent.restaurant_selection import (
    resolve_delivery_button_label,
    resolve_takeaway_button_label,
    selection_pending,
)
from restaurant_agent_runtime.rest_agent.service_selection import retained_handoff_block
from restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel import (
    RestaurantFeedbackRequest,
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

    if ctx.restaurant_selection is not None and selection_pending(
        state, ctx.restaurant_selection
    ):
        await select_restaurant_wa_send(
            recipient=recipient,
            wa_client=ctx.wa_client,
            selection=ctx.restaurant_selection,
        )
        return Command(
            goto=END,
            update={
                "rest_ref": rest_ref,
                "active_agent": "triage_agent",
                "messages": [
                    ToolMessage(
                        "Restaurant selection buttons sent.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("/DoNotRespond: Please select a restaurant."),
                ],
            },
        )

    await select_service_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
        operational_lookups=ctx.operational_lookups,
        delivery_button_label=resolve_delivery_button_label(
            state, ctx.restaurant_selection, ctx.delivery_button_label
        ),
        takeaway_button_label=resolve_takeaway_button_label(
            state, ctx.restaurant_selection, ctx.takeaway_button_label
        ),
        enquiry_button_label=ctx.enquiry_button_label,
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
async def _send_service_selection(
    *,
    state: dict,
    runtime: ToolRuntime[ContextSchema],
    message_before_selection: str | None = None,
) -> None:
    """Send an optional customer response before the standard service menu."""
    ctx = runtime.context
    message = (message_before_selection or "").strip()
    if message:
        await ctx.wa_client.send_message(to=ctx.recipient, text=message)

    await select_service_wa_send(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        rest_ref=(state.get("rest_ref") or ctx.rest_ref).lower(),
        operational_lookups=ctx.operational_lookups,
        delivery_button_label=resolve_delivery_button_label(
            state, ctx.restaurant_selection, ctx.delivery_button_label
        ),
        takeaway_button_label=resolve_takeaway_button_label(
            state, ctx.restaurant_selection, ctx.takeaway_button_label
        ),
        enquiry_button_label=ctx.enquiry_button_label,
    )


@tool
async def ask_user_to_select_service(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
    message_before_selection: str | None = None,
):
    """
    Send interactive WhatsApp buttons asking the customer to select a service.

    When answering a direct enquiry first, put the complete customer-facing
    answer in ``message_before_selection``. The tool sends that text before the
    buttons and ends the turn, so the menu does not interrupt or duplicate the
    response. Omit it only when a bare service menu is appropriate.
    """
    await _send_service_selection(
        state=state,
        runtime=runtime,
        message_before_selection=message_before_selection,
    )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    "Service selection response and buttons sent.",
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    "/DoNotRespond: Customer response and service selection sent."
                ),
            ]
        },
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
        selected_rest_ref=state.get("selected_rest_ref"),
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

# %% Restaurant-selection tools (only bound when the app configures RestaurantSelection)
@tool
async def ask_user_to_select_restaurant(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Send interactive WhatsApp buttons asking which restaurant the customer means.

    Call this before any other triage action whenever this app serves more
    than one restaurant brand and no restaurant has been selected yet.
    """
    ctx = runtime.context
    if ctx.restaurant_selection is None:
        return "This app does not require restaurant selection."

    if (guard := retained_handoff_block(state, tool_call_id)) is not None:
        return guard

    await select_restaurant_wa_send(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        selection=ctx.restaurant_selection,
    )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    "Restaurant selection buttons sent.", tool_call_id=tool_call_id
                ),
                AIMessage("/DoNotRespond: Please select a restaurant."),
            ],
        },
    )


@tool
async def capture_restaurant_selected(
    rest_ref: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Capture a restaurant selection typed as plain text (e.g. "elai", "wings").

    Call this only when the customer's message unambiguously names one of the
    configured restaurant choices, passing that choice's exact rest_ref.
    """
    ctx = runtime.context
    selection = ctx.restaurant_selection
    if selection is None:
        return "This app does not require restaurant selection."

    choice = selection.choice_for(rest_ref)
    if choice is None:
        return (
            f"Unknown restaurant choice: {rest_ref!r}. "
            "Call `ask_user_to_select_restaurant` instead."
        )

    if (guard := retained_handoff_block(state, tool_call_id)) is not None:
        return guard

    # `state` predates this turn's write, so it cannot carry `choice` yet —
    # resolve directly from the just-captured choice instead of via state.
    await select_service_wa_send(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        rest_ref=(state.get("rest_ref") or ctx.rest_ref).lower(),
        operational_lookups=ctx.operational_lookups,
        delivery_button_label=choice.delivery_button_label or ctx.delivery_button_label,
        takeaway_button_label=choice.takeaway_button_label or ctx.takeaway_button_label,
        enquiry_button_label=ctx.enquiry_button_label,
    )
    return Command(
        goto=END,
        update={
            "selected_rest_ref": choice.rest_ref,
            "messages": [
                ToolMessage(
                    f"Restaurant captured from plain text ({choice.rest_ref}). "
                    "Service selection buttons sent.",
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    "/DoNotRespond: Please select how I can help you today."
                ),
            ],
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
async def submit_restaurant_feedback(
    description: str,
    order_reference: str | None,
    acknowledgement_message: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """Schedule feedback through Ordelo, then acknowledge it before the service menu.

    ``acknowledgement_message`` must be a short, customer-facing acknowledgement
    appropriate to the feedback sentiment. It is sent only after Ordelo accepts
    the feedback, so it must not promise a response time or delivery to a person.
    """
    ctx = runtime.context
    result = await OrdeloService(
        rest_ref=ctx.rest_ref,
        database_client=ctx.client_ordelo,
        operational_lookups=ctx.operational_lookups,
    ).submit_restaurant_feedback(
        RestaurantFeedbackRequest(
            rest_ref=ctx.rest_ref,
            cust_id=ctx.recipient,
            cust_name=state.get("wa_name"),
            order_reference=order_reference,
            description=description,
        )
    )
    if result is None:
        if ctx.restaurant_contact_phone:
            failure_message = (
                "Sorry, I couldn't pass your feedback to the restaurant team right "
                f"now. Please call us on {ctx.restaurant_contact_phone}."
            )
        else:
            failure_message = (
                "Sorry, I couldn't pass your feedback to the restaurant team right "
                "now. Please try again later or call the restaurant."
            )
        await _send_service_selection(
            state=state,
            runtime=runtime,
            message_before_selection=failure_message,
        )
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Feedback could not be scheduled; failure response and service selection sent.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(
                        "/DoNotRespond: Feedback failure response and service selection sent."
                    ),
                ]
            }
        )

    acknowledgement = acknowledgement_message.strip()
    if not acknowledgement:
        acknowledgement = "Thank you for your feedback. I've passed it to the restaurant team."
    await _send_service_selection(
        state=state,
        runtime=runtime,
        message_before_selection=acknowledgement,
    )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    "Feedback submitted to Ordelo; acknowledgement and service selection sent.",
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    "/DoNotRespond: Feedback acknowledgement and service selection sent."
                ),
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
    submit_restaurant_feedback,
    terminate_conversation,
    transfer_to_delivery,
    transfer_to_takeaway,
]

def build_triage_agent(
    *,
    model,
    system_prompt: str,
    extra_tools=(),
    restaurant_selection=None,
    dinein_enabled: bool = False,
):
    selection_tools = (
        (ask_user_to_select_restaurant, capture_restaurant_selected)
        if restaurant_selection is not None
        else ()
    )
    dinein_tools = (transfer_to_dinein,) if dinein_enabled else ()
    return create_agent(
        model=model,
        tools=[*triage_tools, *selection_tools, *dinein_tools, *extra_tools],
        system_prompt=system_prompt,
        middleware=[
            render_prompt_middleware(system_prompt),
            cleanup_before_model,
            respond_on_wa,
        ],
        state_schema=AgentState,
        context_schema=ContextSchema,
    )
