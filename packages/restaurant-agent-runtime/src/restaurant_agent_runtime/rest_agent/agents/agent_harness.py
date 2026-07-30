# %% [CELL 1] Core Imports
"""Agent harness containing shared state schemas and transfer tools.

This module provides the foundational components shared across all agents:
  - ContextSchema: Runtime context with pool, wa_client, recipient, etc.
  - AgentState: Shared state schema for all agents
  - Transfer tools for agent handoffs
  - _transfer_check_delivery_retain: Guard that blocks transfer if delivery is in progress (retain_thread=True)

This module should have NO imports from other agent modules to avoid circular imports.
  Functions/Classes:
    . AgentState
    . ContextSchema
    . get_context_schema
    . _transfer_check_delivery_retain
    . _run_transfer_guards
    . transfer_to_delivery
    . transfer_to_takeaway
    . transfer_to_triage
    . send_restaurant_menu_tool
    . send_takeaway_menu_tool
    . cleanup_before_model
    . respond_on_wa
"""

import re
from typing import Annotated, Any, Literal, Sequence

from langchain.agents.middleware import after_agent, before_model
from langchain.tools import ToolRuntime
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    RemoveMessage,
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
# from restaurant_agent_runtime.services.ordelo_service.ordelo_service import OrdeloService

# from restaurant_agent_runtime.config import project_settings

# ordelo_service = OrdeloService(rest_ref=project_settings.rest_ref)


# %% Define AgentState
class AgentState(TypedDict):
    """Shared state schema for all agents.

    Attributes:
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
        retain_thread: Whether to keep thread active
    """

    rest_ref: str
    active_agent: NotRequired[str]
    messages: Annotated[Sequence[BaseMessage], add_messages]
    wa_name: str
    customer_address: dict
    is_delivery_address_confirmed: bool
    is_outside_delivery_area: bool
    min_order_value: float
    order_id: str
    order_number: str
    is_payment_successful: bool
    reply_to_msg_id: str
    is_delivery_rider_assigned: bool
    rider_live_location_url: str
    is_delivery_picked_up: bool
    retain_thread: bool
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
    project_settings: Any
    client_ordelo: Client
    thread_handler: Any | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.thread_handler is None:
            # Lazy import to avoid importing external config during module import.
            from restaurant_agent_runtime.services.thread_management import ThreadHandler

            self.thread_handler = ThreadHandler(self.pool, agent=self.rest_ref)


def _normalize_min_order_value(raw_min_order_value: Any) -> float:
    if raw_min_order_value in (None, ""):
        return 0.0

    try:
        return float(raw_min_order_value)
    except (TypeError, ValueError):
        # Handle values like "£12.5"
        cleaned_value = re.sub(r"[^\d\.\-]", "", str(raw_min_order_value)).strip()
        if cleaned_value:
            try:
                return float(cleaned_value)
            except ValueError:
                pass

    logger.warning(
        "Invalid min_order_value in state: {}. Falling back to 0.0",
        raw_min_order_value,
    )
    return 0.0


async def _send_menu_tool(
    *,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
    order_type: Literal["delivery", "takeaway"],
) -> Command:
    from restaurant_agent_runtime.rest_agent.agent_wa_senders import send_restaurant_menu

    ctx = runtime.context
    recipient = ctx.recipient
    thread_id, _ = await ctx.thread_handler.get_or_create_thread(recipient)
    min_order_value = _normalize_min_order_value(state.get("min_order_value"))
    rest_ref = state.get("rest_ref") or ctx.rest_ref

    menu_err = await send_restaurant_menu(
        recipient=recipient,
        minimum_order=min_order_value,
        thread_id=str(thread_id),
        rest_ref=rest_ref,
        order_type=order_type,
        wa_client=ctx.wa_client,
        logo_url=ctx.restaurant_logo_url,
    )
    if isinstance(menu_err, ValueError):
        await ctx.wa_client.send_message(
            to=recipient,
            text="Sorry, I couldn't send the menu link right now. Please try again later.",
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        f"Failed to send restaurant menu: {menu_err}",
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
                    "/DoNotRespond: Please select items from the menu to place your order."
                ),
            ],
        },
    )


async def send_restaurant_menu_tool(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
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
) -> Command:
    """Send the takeaway menu link."""
    return await _send_menu_tool(
        state=state,
        tool_call_id=tool_call_id,
        runtime=runtime,
        order_type="takeaway",
    )


def _run_transfer_guards(state: dict, tool_call_id: str) -> Command | None:
    """Run all pre-transfer guards in order; return the first blocking Command or None."""
    for check in (
        _transfer_check_delivery_retain(state, tool_call_id),
    ):
        if check is not None:
            return check
    return None


def transfer_to_delivery(
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Transfer the conversation to the delivery agent.

    Use this tool when the customer wants to order food for delivery.
    """
    if (guard := _run_transfer_guards(runtime.state, runtime.tool_call_id)) is not None:
        return guard

    transfer_message = ToolMessage(
        content="Transferred to delivery agent. Customer wants food delivery.",
        tool_call_id=runtime.tool_call_id,
    )

    logger.info(
        f"Transferring to delivery agent for recipient: {runtime.context.recipient}"
    )
    update_messages = [transfer_message]

    # Get the last AI message to include in the handoff
    last_ai_message = next(
        (
            msg
            for msg in reversed(runtime.state["messages"])
            if isinstance(msg, AIMessage)
        ),
        None,
    )
    if last_ai_message:
        update_messages.insert(0, last_ai_message)

    return Command(
        # Jump to the parent orchestration graph where delivery_agent is defined.
        graph=Command.PARENT,
        goto="delivery_agent",
        update={
            "active_agent": "delivery_agent",
            "messages": update_messages,
        },
    )


# %%
def _transfer_check_delivery_retain(state: dict, tool_call_id: str) -> Command | None:
    """Block transfer away from delivery if a delivery is in progress (retain_thread=True).

    Returns a Command that stays in the current agent with an explanatory ToolMessage,
    or None if the transfer is allowed.
    """
    if state.get("retain_thread") is True:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Cannot transfer: a delivery is currently in progress. Stay with the delivery agent to complete the order.",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    return None


def transfer_to_takeaway(
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Transfer the conversation to the takeaway agent.

    Use this tool when the customer wants to order food for collection/takeaway.
    """
    if (guard := _run_transfer_guards(state, runtime.tool_call_id)) is not None:
        return guard

    _current_active_agent = state.get("active_agent", "triage_agent")
    _current_rest_ref = state.get("rest_ref")

    transfer_message = ToolMessage(
        content=f"Transferred to takeaway agent. Customer wants takeaway/collection. Current agent: {_current_active_agent}, Restaurant: {_current_rest_ref}",
        tool_call_id=runtime.tool_call_id,
    )

    logger.info(
        f"Transferring to takeaway agent for recipient: {runtime.context.recipient}"
    )

    update_messages = [transfer_message]

    # Get the last AI message to include in the handoff
    last_ai_message = next(
        (
            msg
            for msg in reversed(runtime.state["messages"])
            if isinstance(msg, AIMessage)
        ),
        None,
    )
    if last_ai_message:
        update_messages.insert(0, last_ai_message)

    return Command(
        # Jump to the parent orchestration graph where takeaway_agent is defined.
        graph=Command.PARENT,
        goto="takeaway_agent",
        update={
            "active_agent": "takeaway_agent",
            "messages": update_messages,
        },
    )


# %%
def transfer_to_triage(
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Transfer the conversation back to the triage agent.

    Use this tool when the customer's request is outside this agent's scope:
    complaints, general queries (parking, events, catering, contact info),
    restaurant switch, ending/restarting the conversation, or when a system
    message instructs to terminate the conversation.
    """
    if (
        guard := _transfer_check_delivery_retain(runtime.state, runtime.tool_call_id)
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
