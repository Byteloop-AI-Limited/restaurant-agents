"""Optional standard dine-in agent: table reservations.

Activated only when an app supplies `RestaurantPrompts.dinein` (see
`agent_runner._build_graph` and `multi_agent.build_multi_agent_graph`). Apps
that do not configure it never construct this module's agent and never see
`dinein_agent` in their graph.
"""

from typing import Annotated

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools.base import InjectedToolCallId
from langgraph.graph import END
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.rest_agent.agent_wa_senders import reservation_link_wa_send
from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
    cleanup_before_model,
    respond_on_wa,
    transfer_to_delivery,
    transfer_to_takeaway,
    transfer_to_triage,
)
from restaurant_agent_runtime.rest_agent.prompt_runtime import render_prompt_middleware
from restaurant_agent_runtime.services.reservation_management.reservation_db_ops import (
    process_reservation_into_db,
)


@tool
async def get_reservation_link(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Create a reservation booking link and send it to the customer.

    Call this when the customer wants to make a dine-in reservation or book a
    table.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    wa_name = state.get("wa_name", "there")

    if not ctx.reservation_base_url:
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Reservation link is not configured for this restaurant.",
                        tool_call_id=tool_call_id,
                    ),
                ]
            },
        )

    thread_id, _ = await ctx.thread_handler.get_or_create_thread(recipient)
    reservation_id = await process_reservation_into_db(
        pool=ctx.pool,
        recipient=recipient,
        thread_id=str(thread_id),
        rest_ref=ctx.rest_ref,
        salt=ctx.project_settings.salt,
    )

    if not reservation_id:
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Failed to create reservation. Please try again or "
                        "contact the restaurant directly.",
                        tool_call_id=tool_call_id,
                    ),
                ]
            },
        )

    reservation_url = f"{ctx.reservation_base_url}/reservations/{reservation_id}"

    await reservation_link_wa_send(
        recipient=recipient,
        reservation_url=reservation_url,
        wa_client=ctx.wa_client,
        wa_name=wa_name,
    )

    await ctx.thread_handler.make_threads_inactive(recipient=recipient)

    return Command(
        goto="end",
        update={
            "reservation_id": reservation_id,
            "is_reservation_confirmed": False,
            "messages": [
                ToolMessage(
                    f"Reservation link sent to customer: {reservation_url}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Reservation link sent"),
            ],
        },
    )


@tool
async def check_reservation_status(
    reservation_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """Check the confirmation status of a reservation by reservation ID.

    Call this when the customer asks about their reservation status and
    provides their reservation ID.
    """
    ctx = runtime.context

    try:
        response = (
            ctx.client_ordelo.table("reservation")
            .select("confirmation_status", "reservation_dt", "reservation_ts")
            .eq("reservation_id", reservation_id)
            .execute()
        )
    except Exception as exc:
        logger.error(f"Error checking reservation status: {exc}")
        return (
            f"Error checking reservation {reservation_id}: {exc}. Tell the "
            "customer there was a problem checking their reservation status "
            "and to try again later."
        )

    if not response.data:
        return (
            f"Reservation not found: {reservation_id}. Tell the customer their "
            "reservation was not found and ask whether they would like to "
            "contact the restaurant or rebook."
        )

    confirmation_status = response.data[0]["confirmation_status"]
    is_confirmed = confirmation_status == "confirmed"
    steer = (
        "Tell the customer their reservation is confirmed and you look "
        "forward to seeing them."
        if is_confirmed
        else "Tell the customer their reservation is pending confirmation and "
        "you will contact them once it's confirmed."
    )
    return Command(
        update={
            "is_reservation_confirmed": is_confirmed,
            "messages": [
                ToolMessage(
                    f"Reservation {reservation_id} status: {confirmation_status}. "
                    + steer,
                    tool_call_id=tool_call_id,
                ),
            ],
        }
    )


dinein_tools = [
    get_reservation_link,
    check_reservation_status,
    transfer_to_delivery,
    transfer_to_takeaway,
    transfer_to_triage,
]


def build_dinein_agent(*, model, system_prompt: str, extra_tools=()):
    return create_agent(
        model=model,
        tools=[*dinein_tools, *extra_tools],
        system_prompt=system_prompt,
        middleware=[
            render_prompt_middleware(system_prompt),
            cleanup_before_model,
            respond_on_wa,
        ],
        state_schema=AgentState,
        context_schema=ContextSchema,
    )
