"""Handles the dine-in reservation workflow and agent logic.
  . Dine-in flow: welcome → send reservation link → confirmation
  . Provides tool for generating and sending reservation booking links
  . Integrates with Langchain, LangGraph, and WhatsApp APIs for table booking
  . Transfers to triage for conversation termination (does not own terminate_conversation)
Classes:
  . AgentState
  . ContextSchema
Functions:
  . get_reservation_link
  . check_reservation_status
  . setup_node
  . agent_node
  . respond_node
"""

# %%
from typing import Annotated, Literal
from langchain_core.messages import (
    AIMessage,
    RemoveMessage,
    ToolMessage,
)

from langgraph.graph import END, START, StateGraph
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.prebuilt import InjectedState, ToolNode
from langchain.tools import ToolRuntime
from langgraph.runtime import Runtime
from langgraph.types import Command

from pathlib import Path

from restaurant_agent_core.config import logger
from restaurant_agent_core.services.lg_utils import (
    create_agent_w_sys_prompt_n_tools,
    llm_settings,
)
from restaurant_agent_core.services.reservation_management.reservation_db_ops import (
    process_reservation_into_db,
)

# %% Import shared state schemas and transfer tools from agent_harness
from sfcs_agent.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
    transfer_to_delivery,
    transfer_to_takeaway,
    transfer_to_triage,
)
from sfcs_agent.rest_agent.agent_wa_senders import reservation_link_wa_send


# %%
@tool
async def get_reservation_link(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """
    Creates a reservation booking link and sends it to the user via WhatsApp.
    Call this tool when the user wants to make a dine-in reservation or book a table.

    Args:
        None

    Returns:
        Command: Updates state with reservation_id and sends confirmation message.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    pool = ctx.pool
    wa_name = state.get("wa_name", "There")

    # Get thread_id from restaurant_agent_core.config (you may need to extract this from runtime.config)
    # For now, using recipient as thread_id fallback
    thread_id = recipient  # You might want to get this from restaurant_agent_core.config properly

    # Create reservation in database
    reservation_id = await process_reservation_into_db(
        pool=pool,
        recipient=recipient,
        thread_id=thread_id,
        rest_ref=ctx.rest_ref,
    )

    if not reservation_id:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        "Failed to create reservation. Please try again or contact the restaurant directly.",
                        tool_call_id=tool_call_id,
                    ),
                ]
            }
        )

    # Construct reservation link
    # TODO: make reservation base URL configurable
    reservation_url = f"https://reservation.example.com/reservations/{reservation_id}"

    # Send message to user
    await reservation_link_wa_send(
        recipient=recipient,
        reservation_url=reservation_url,
        wa=ctx.wa_client,
        wa_name=wa_name,
    )

    # Deactivate thread since sending reservation link is the final step
    await ctx.thread_handler.make_threads_inactive(recipient=recipient)

    return Command(
        update={
            "reservation_id": reservation_id,
            "is_reservation_confirmed": False,
            "messages": [
                ToolMessage(
                    f"Reservation link sent to user: {reservation_url}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Reservation link sent"),
            ],
        }
    )


# %%
@tool
async def check_reservation_status(
    reservation_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
) -> Command:
    """
    Checks the confirmation status of a reservation by reservation ID.
    Call this tool when the user asks about their reservation status and provides their reservation ID.

    Args:
        reservation_id: The reservation ID provided by the user (e.g., "RES-XXXX-23")

    Returns:
        Command: Updates state and sends the reservation status to the user.
    """
    ctx = runtime.context
    recipient = ctx.recipient

    try:
        response = (
            ctx.client_ordelo.table("reservation")
            .select("confirmation_status", "reservation_dt", "reservation_ts")
            .eq("reservation_id", reservation_id)
            .execute()
        )

        if len(response.data) == 0:
            status_message = "Reservation not found. Kindly contact the restaurant or would you like to rebook?"
            await ctx.wa_client.send_message(
                to=recipient,
                text=status_message,
            )
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Reservation not found: {reservation_id}",
                            tool_call_id=tool_call_id,
                        ),
                        AIMessage(
                            "/DoNotRespond: Reservation not found, error message sent to user"
                        ),
                    ],
                }
            )

        reservation_row = response.data[0]
        confirmation_status = reservation_row["confirmation_status"]

        if confirmation_status == "confirmed":
            status_message = (
                f"Great news! Your reservation {reservation_id} has been confirmed. "
                "We look forward to seeing you!"
            )
        else:
            status_message = (
                f"Your reservation {reservation_id} is currently pending confirmation. "
                "We will contact you once it's confirmed."
            )

        await ctx.wa_client.send_message(
            to=recipient,
            text=status_message,
        )

        return Command(
            update={
                "is_reservation_confirmed": confirmation_status == "confirmed",
                "messages": [
                    ToolMessage(
                        f"Reservation status checked: {confirmation_status}",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("/DoNotRespond: Reservation status sent to user"),
                ],
            }
        )
    except Exception as e:
        logger.error(f"Error checking reservation status: {e}")
        error_message = "Sorry, there was an error checking your reservation status. Please try again later."
        await ctx.wa_client.send_message(
            to=recipient,
            text=error_message,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error checking reservation: {str(e)}",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("/DoNotRespond: Error checking reservation status"),
                ],
            }
        )


# %%
dinein_tools = [
    get_reservation_link,
    check_reservation_status,
    transfer_to_delivery,  # Handoff to delivery agent
    transfer_to_takeaway,  # Handoff to takeaway agent
    transfer_to_triage,  # Handoff to triage for out-of-scope queries and termination
]

# %% Build prompt
with (Path(__file__).parent / "prompts" / "dinein_agent_prompt.md").open() as file:
    dinein_agent_prompt = file.read()

# %% create dinein_agent
dinein_agent = create_agent_w_sys_prompt_n_tools(
    llm=llm_settings.llm_client,
    system_prompt=dinein_agent_prompt,
    tools=dinein_tools,
    parallel_tool_calls=False,
)


# %% setup_node
async def setup_node(
    state: AgentState, runtime: Runtime[ContextSchema]
) -> Command[Literal["dineinAgent", END]]:
    """
    Initializes the dine-in agent. Simple setup - just proceed to agent.
    """
    return Command(goto="dineinAgent")


# %% agent_node
def agent_node(
    state: AgentState,
) -> Command[Literal["toolNode", "respondNode", END]]:
    """
    Main agent node that processes user input and determines next action.
    """
    last_msg = state["messages"][-1]

    # Check for DoNotRespond pattern
    if (
        isinstance(last_msg, AIMessage)
        and isinstance(last_msg.content, str)
        and last_msg.content.startswith("/DoNotRespond:")
    ):
        clean_ai_msg = last_msg.content.replace("/DoNotRespond:", "", 1).lstrip()
        return Command(
            goto=END,
            update={
                "messages": [
                    RemoveMessage(id=last_msg.id),
                    AIMessage(clean_ai_msg),
                ],
            },
        )

    # Invoke agent
    ai_msg = dinein_agent.invoke(state)
    goto = "toolNode" if ai_msg.tool_calls else "respondNode"
    return Command(update={"messages": [ai_msg]}, goto=goto)


# %% respond_node
async def respond_node(
    state: AgentState, runtime: Runtime[ContextSchema]
) -> Command[Literal[END]]:
    """
    Sends the AI's response to the user via WhatsApp.
    """
    ctx = runtime.context
    recipient = ctx.recipient

    last_ai_msg = state["messages"][-1]

    if isinstance(last_ai_msg, AIMessage) and isinstance(last_ai_msg.content, str):
        await ctx.wa_client.send_message(
            to=recipient,
            text=last_ai_msg.content,
        )

    return Command(goto=END, update={"messages": [last_ai_msg]})


# %% Construct the graph
builder = StateGraph(state_schema=AgentState, context_schema=ContextSchema)
builder.add_node("setupNode", setup_node)
builder.add_node("dineinAgent", agent_node)
builder.add_node("respondNode", respond_node)
builder.add_node("toolNode", ToolNode(dinein_tools))
builder.add_edge(START, "setupNode")
builder.add_edge("toolNode", "dineinAgent")


# # Test
# # %%
# from restaurant_agent_core.services.lg_utils import display_graph
# # %%
# display_graph(builder)

# # %%
# from langgraph.checkpoint.memory import MemorySaver
# from langchain_core.messages import HumanMessage
# from restaurant_agent_core.services.lg_utils import agent_loop_test

# async def run_test():
#     await agent_loop_test(builder, thread_id=21)

# await run_test()


# # %%
