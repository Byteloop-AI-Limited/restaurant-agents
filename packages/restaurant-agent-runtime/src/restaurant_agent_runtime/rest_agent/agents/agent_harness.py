# %% [CELL 1] Core Imports
"""Agent harness containing shared state schemas and transfer tools.

This module provides the foundational components shared across all agents:
  - ContextSchema: Runtime context with pool, wa_client, recipient, etc.
  - AgentState: Shared state schema for all agents
  - Transfer tools for agent handoffs
  - update_customer: Sends an authoritative specialist update and ends the turn
  - _transfer_check_retained_specialist_work: Guard that blocks handoff while retained work is active

This module should have NO imports from other agent modules to avoid circular imports.
  Functions/Classes:
    . AgentState
    . ContextSchema
    . get_context_schema
    . update_customer
    . _transfer_check_retained_specialist_work
    . _run_transfer_guards
    . transfer_to_delivery
    . transfer_to_takeaway
    . transfer_to_triage
    . send_restaurant_menu_tool
    . send_takeaway_menu_tool
    . cleanup_before_model
    . respond_on_wa
"""

from typing import Annotated, Any, Literal, Sequence

from langchain.agents.middleware import after_agent, before_model
from langchain.tools import ToolRuntime
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools.base import InjectedToolCallId
from langgraph.graph import END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import InjectedState
from langgraph.runtime import Runtime
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict
from pywa_async import WhatsApp
from supabase._sync.client import Client
from typing_extensions import NotRequired, TypedDict
from loguru import logger

from restaurant_agent_runtime.services.ordelo_service.datamodels.restaurant_master_pymodel import (
    RestaurantMaster,
)
from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)
from restaurant_agent_runtime.runtime import EnquiryMenu, RestaurantSelection
from restaurant_agent_runtime.rest_agent.new_order_entry import (
    normalize_min_order_value,
    send_new_order_menu,
)
from restaurant_agent_runtime.rest_agent.service_selection import (
    retained_handoff_block,
    route_tool_service_selection,
)
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    SpecialistFlowView,
    retained_completion_first_message,
)
from restaurant_agent_runtime.rest_agent.restaurant_selection import (
    dinein_available,
    resolve_delivery_promo_caption,
    resolve_menu_logo_url,
    resolve_menu_rest_ref,
    resolve_takeaway_promo_caption,
    selection_pending,
    selection_required_block,
)


# %% Define AgentState
class AgentState(TypedDict):
    """Shared state schema for all agents.

    Attributes:
        rest_ref: Invariant configured app identity. Always seeded on a new
            thread; never the customer's choice among multiple restaurant
            brands. See `selected_rest_ref`.
        selected_rest_ref: The customer's chosen restaurant brand, set only by
            apps that configure `RestaurantPresentation.restaurant_selection`
            (see restaurant_selection.py). Absent or `None` means the choice
            has not been made yet. Never fall back to `rest_ref` here.
        active_agent: Currently active agent name for multi-agent routing
        messages: Conversation history with add_messages reducer
        wa_name: Customer's WhatsApp display name
        customer_address: Customer's delivery address details
        is_delivery_address_confirmed: Whether address is confirmed
        is_outside_delivery_area: Whether customer is outside delivery zone
        min_order_value: Minimum order value for delivery
        order_id: Current order ID
        order_number: Current order number
        is_payment_successful: Whether payment is complete
        reply_to_msg_id: Message ID to reply to
        is_delivery_rider_assigned: Whether a rider is assigned
        rider_live_location_url: URL for rider tracking
        is_delivery_picked_up: Whether food is picked up by rider
        is_payment_cancelled: Whether payment cancellation has been confirmed
        is_delivery_no_rider: Whether delivery ended because no rider was found
        retain_thread: Whether to keep thread active
    """

    rest_ref: str
    selected_rest_ref: NotRequired[str | None]
    active_agent: NotRequired[str]
    messages: Annotated[Sequence[BaseMessage], add_messages]
    wa_name: str
    customer_address: dict | None
    is_delivery_address_confirmed: bool | None
    is_outside_delivery_area: bool | None
    min_order_value: float | None
    order_id: str | None
    order_number: str | None
    is_payment_successful: bool | None
    reply_to_msg_id: str | None
    is_delivery_rider_assigned: bool | None
    rider_live_location_url: str | None
    is_delivery_picked_up: bool | None
    is_payment_cancelled: bool | None
    is_delivery_no_rider: bool | None
    retain_thread: bool
    order_summary: NotRequired[dict | None]
    payment_link: NotRequired[str | None]
    reservation_id: NotRequired[str]
    is_reservation_confirmed: NotRequired[bool]
    ask_for_consent: bool = False


# %% Define RuntimeContext
class ContextSchema(BaseModel):
    """Runtime context shared across all agents.

    Attributes:
        pool: PostgreSQL connection pool for database operations
        wa_client: WhatsApp client for sending messages
        recipient: Customer's WhatsApp number
        client_ordelo: Supabase client for order/customer data
        thread_handler: Handler for thread management (auto-created if None)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pool: AsyncConnectionPool
    wa_client: WhatsApp
    recipient: str
    rest_ref: str
    restaurant_name: str
    restaurant_logo_url: str
    restaurant_contact_phone: str | None = None
    delivery_button_label: str = "Delivery"
    takeaway_button_label: str = "Takeaway"
    enquiry_button_label: str = "More options"
    delivery_promo_caption: str
    takeaway_promo_caption: str
    enquiry_menu: EnquiryMenu
    restaurant_master: RestaurantMaster
    project_settings: Any
    payment_settings: Any
    client_ordelo: Client
    operational_lookups: OperationalLookupCache
    thread_handler: Any | None = None
    wa_msg_id: str | None = None
    restaurant_selection: RestaurantSelection | None = None
    reservation_base_url: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.thread_handler is None:
            # Lazy import to avoid importing external config during module import.
            from restaurant_agent_runtime.services.thread_management import ThreadHandler

            self.thread_handler = ThreadHandler(self.pool, agent=self.rest_ref)


def _normalize_min_order_value(raw_min_order_value: Any) -> float:
    """Compatibility export for callers of the former harness helper."""
    return normalize_min_order_value(raw_min_order_value)


async def _send_menu_tool(
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
    order_type: Literal["delivery", "takeaway"],
) -> Command | str:
    retained_flow = SpecialistFlowView.from_state(state)
    if retained_flow.owns_specialist_work:
        if _last_turn_started_by_system_message(state.get("messages", ())):
            return (
                "Menu send blocked because authoritative retained-order lifecycle work "
                "is active. Do not send a menu, start a new order, or hand off. Follow "
                "the current system instruction and call `update_customer` with its "
                "supplied message."
            )

        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Menu send blocked because retained specialist work is active.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage(retained_completion_first_message(state)),
                ]
            },
        )

    ctx = runtime.context
    result = await send_new_order_menu(
        recipient=ctx.recipient,
        state=state,
        rest_ref=resolve_menu_rest_ref(state, ctx.restaurant_selection, ctx.rest_ref),
        wa_client=ctx.wa_client,
        logo_url=resolve_menu_logo_url(
            state, ctx.restaurant_selection, ctx.restaurant_logo_url
        ),
        operational_lookups=ctx.operational_lookups,
        thread_handler=ctx.thread_handler,
        order_type=order_type,
        delivery_promo_caption=resolve_delivery_promo_caption(
            state, ctx.restaurant_selection, ctx.delivery_promo_caption
        ),
        takeaway_promo_caption=resolve_takeaway_promo_caption(
            state, ctx.restaurant_selection, ctx.takeaway_promo_caption
        ),
        reply_to_message_id=state.get("reply_to_msg_id"),
    )
    if result == "closed":
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "New order menu blocked because the service is currently closed.",
                        tool_call_id=tool_call_id,
                    )
                ]
            },
        )
    if result == "failed":
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Failed to send restaurant menu.",
                        tool_call_id=tool_call_id,
                    ),
                ],
            },
        )

    order_label = "takeaway" if order_type == "takeaway" else "delivery"
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    f"Restaurant menu sent to customer for {order_label} order.",
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    f"/DoNotRespond: The {order_label} menu was successfully sent to "
                    "the customer. Wait for them to place the order. Do not send another "
                    "menu unless they explicitly request one and no retained order is active."
                ),
            ],
        },
    )


async def send_restaurant_menu_tool(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command | str:
    """Send the delivery menu link after minimum order is available."""
    return await _send_menu_tool(
        state=state,
        tool_call_id=tool_call_id,
        runtime=runtime,
        order_type="delivery",
    )


async def send_takeaway_menu_tool(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command | str:
    """Send the takeaway menu link."""
    return await _send_menu_tool(
        state=state,
        tool_call_id=tool_call_id,
        runtime=runtime,
        order_type="takeaway",
    )


def _last_turn_started_by_system_message(messages: Sequence[BaseMessage]) -> bool:
    """Whether the current turn was opened by a runtime SystemMessage.

    A tool-calling turn can chain several AIMessage/ToolMessage pairs before
    reaching `update_customer`; walk backward past those to find the human or
    system message that actually started the turn. Every legitimate
    `update_customer` call site queues a `system_msg` and nothing else for
    that turn, so a customer HumanMessage as the most recent turn-starter
    means no system instruction authorized this call.
    """
    for msg in reversed(messages):
        if isinstance(msg, SystemMessage):
            return True
        if isinstance(msg, HumanMessage):
            return False
    return False


async def update_customer(
    message: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Send an authoritative order update from the active specialist.

    Use this only for a delivery or takeaway update supplied by an authoritative
    system event or system instruction. It deliberately does not change thread
    retention, agent ownership, payment, or fulfilment state.

    Refuses to fire unless this turn was opened by a runtime SystemMessage: a
    customer's own message must never trigger it, and it must never reuse an
    earlier turn's already-consumed system instruction.
    """
    if not _last_turn_started_by_system_message(state.get("messages", [])):
        return (
            "update_customer is for runtime-authoritative updates only, supplied "
            "by a system message in this exact turn. This turn was started by "
            "the customer's own message, not a system instruction, so no update "
            "was sent. Use the tool that matches what the customer actually "
            "asked, or answer from current state."
        )

    text = message.strip()
    if not text:
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Customer update was not sent because the message was empty.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("/DoNotRespond: Customer update was not sent."),
                ]
            },
        )

    ctx = runtime.context
    await ctx.wa_client.send_message(
        to=ctx.recipient,
        text=text,
        reply_to_message_id=state.get("reply_to_msg_id"),
    )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    f"Authoritative update sent to customer: {text}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Authoritative customer update sent."),
            ]
        },
    )


def _run_transfer_guards(state: dict, tool_call_id: str) -> Command | None:
    """Compatibility adapter for the legacy guard helper.

    New handoff paths call the lifecycle view directly; retaining this tiny
    adapter avoids breaking existing integrations that imported the helper.
    """
    return _transfer_check_retained_specialist_work(state, tool_call_id)


async def transfer_to_delivery(
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Transfer the conversation to the delivery agent.

    Use this tool when the customer wants to order food for delivery.
    """
    return await route_tool_service_selection(
        service="delivery",
        state=runtime.state,
        tool_call_id=runtime.tool_call_id,
        runtime=runtime,
    )


# %%
def _transfer_check_retained_specialist_work(
    state: dict, tool_call_id: str
) -> Command | None:
    """Block a specialist handoff while explicitly retained work is active.

    Missing or null values retain the legacy pre-order behavior and are treated
    as not retained. A literal ``True`` keeps the current specialist responsible
    for safe customer support until a lifecycle event explicitly clears it.
    """
    return retained_handoff_block(state, tool_call_id)


async def transfer_to_takeaway(
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Transfer the conversation to the takeaway agent.

    Use this tool when the customer wants to order food for collection/takeaway.
    """
    return await route_tool_service_selection(
        service="takeaway",
        state=state,
        tool_call_id=runtime.tool_call_id,
        runtime=runtime,
    )


# %%
def transfer_to_triage(
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Transfer the conversation back to the triage agent.

    Use this tool when the customer's request is outside this agent's scope:
    feedback, general queries (parking, events, catering, contact info),
    restaurant switch, ending/restarting the conversation, or when a system
    message instructs to terminate the conversation.
    """
    if (
        guard := _transfer_check_retained_specialist_work(
            runtime.state, runtime.tool_call_id
        )
    ) is not None:
        return guard

    # Get the last AI message to include in the handoff
    last_ai_message = next(
        (
            msg
            for msg in reversed(runtime.state["messages"])
            if isinstance(msg, AIMessage)
        ),
        None,
    )

    transfer_message = ToolMessage(
        content="Transferred back to triage agent. Customer query is outside this specialist's scope.",
        tool_call_id=runtime.tool_call_id,
    )

    update_messages = [transfer_message]
    if last_ai_message:
        update_messages.insert(0, last_ai_message)

    logger.info(
        f"Transferring to triage agent for recipient: {runtime.context.recipient}"
    )

    return Command(
        graph=Command.PARENT,
        goto="triage_agent",
        update={
            "active_agent": "triage_agent",
            "messages": update_messages,
        },
    )


# %%
async def transfer_to_dinein(
    runtime: ToolRuntime[ContextSchema],
) -> Command | str:
    """Transfer the conversation to the dine-in agent.

    Use this tool when the customer wants to book a table or make a dine-in
    reservation. Only available when this app configures a dine-in prompt.
    """
    state = runtime.state
    tool_call_id = runtime.tool_call_id
    ctx = runtime.context

    if selection_pending(state, ctx.restaurant_selection):
        return await selection_required_block(ctx, tool_call_id)

    if not dinein_available(state, ctx.restaurant_selection, ctx.reservation_base_url):
        # A plain string return lets LangChain's tool node wrap it into a
        # ToolMessage carrying the originating call's tool_call_id itself,
        # ending this turn without a Command.PARENT redirect — see
        # selection_required_block's docstring for why that shape corrupts
        # the checkpointed message tail. This is the typed-intent backstop:
        # the enquiry menu no longer shows "Book a table" for a brand with
        # supports_dine_in=False (see ADR-0024), so this only fires when the
        # customer types the request instead of tapping it.
        return (
            "This restaurant does not offer dine-in reservations. Tell the "
            "customer politely and offer delivery or takeaway instead."
        )

    if (
        guard := _transfer_check_retained_specialist_work(state, tool_call_id)
    ) is not None:
        return guard

    last_ai_message = next(
        (
            msg
            for msg in reversed(state["messages"])
            if isinstance(msg, AIMessage)
        ),
        None,
    )

    transfer_message = ToolMessage(
        content="Transferred to dine-in agent for table reservation.",
        tool_call_id=tool_call_id,
    )

    update_messages = [transfer_message]
    if last_ai_message:
        update_messages.insert(0, last_ai_message)

    logger.info(f"Transferring to dine-in agent for recipient: {ctx.recipient}")

    return Command(
        graph=Command.PARENT,
        goto="dinein_agent",
        update={
            "active_agent": "dinein_agent",
            "messages": update_messages,
        },
    )


# %% Middleware functions
@before_model(can_jump_to=["end"])
def cleanup_before_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Pre-model hook to check for special markers and skip model call if needed.

    Purpose:
        - Detect "/DoNotRespond:" marker in last AI message
        - Skip model call and jump to "end" if marker is present
        - Log state keys for debugging

    Args:
        state: Current agent state with messages
        runtime: Runtime context (not used here, but available)

    Returns:
        dict | None: {"jump_to": "end"} to skip model, None to continue normally

    Pattern:
        This prevents unnecessary LLM calls when tools have already set the response.
        The "/DoNotRespond:" marker is added by tools that handle their own messaging.
    """

    # Check last message for special marker
    last_ai_msg = state["messages"][-1]
    if "/DoNotRespond:" in last_ai_msg.content:
        # Skip model call and go directly to end
        return {"jump_to": "end"}

    return None  # Continue normally


@after_agent()
async def respond_on_wa(
    state: AgentState, runtime: Runtime[ContextSchema]
) -> dict | None:
    """Post-agent hook to send WhatsApp responses and clean up markers.

    Purpose:
        - Send AI responses via WhatsApp (if not marked with "/DoNotRespond:")
        - Clean up "/DoNotRespond:" markers from messages
        - Replace marked messages with clean versions

    Args:
        state: Current agent state with messages
        runtime: Runtime context with wa_client and recipient

    Returns:
        dict | None: State update to remove/replace messages, or None

    Pattern:
        This hook handles external communication (WhatsApp) as a side effect.
        It keeps the agent logic clean by separating message delivery from generation.

    Note:
        Currently commented out in middleware list (line 277) for web implementation.
    """
    recipient = runtime.context.recipient
    last_ai_msg = state["messages"][-1]

    content = last_ai_msg.content if isinstance(last_ai_msg.content, str) else ""
    if not content.strip():
        return None

    # Check for "/DoNotRespond:" marker
    if "/DoNotRespond:" in last_ai_msg.content:
        # Clean the marker and replace the message
        clean_ai_msg = last_ai_msg.content.replace("/DoNotRespond:", "")
        msg_id_to_delete: str | None = last_ai_msg.id

        return {
            "messages": [
                RemoveMessage(msg_id_to_delete),  # Remove marked message
                AIMessage(content=clean_ai_msg),  # Add clean version
            ],
        }

    # Send response via WhatsApp if no marker present
    await runtime.context.wa_client.send_message(
        to=recipient,
        text=last_ai_msg.content,
    )

    return None  # No state update needed
