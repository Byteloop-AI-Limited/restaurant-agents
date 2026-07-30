"""
Takeaway agent graph setup and notebook test harness
  . Defines takeaway agent prompt and tools
  . Builds a LangGraph agent with WhatsApp response handling
  . Transfers to triage for conversation termination (does not own terminate_conversation)
  . Provides a notebook-friendly loop for interactive testing
  Functions/Classes:
    . verify_if_payment_complete
"""

# %% [CELL 1] Core Imports
# Standard library imports
from typing import Annotated
from langgraph.prebuilt import InjectedState
from langchain.tools import ToolRuntime

# Project-specific imports
from restaurant_agent_runtime.config import logger

# Third-party: LangChain/LangGraph core
from langchain.agents import create_agent

from langchain_core.tools.base import InjectedToolCallId

# %% Import shared state schemas, transfer tools, and middleware from agent_harness
from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
    cleanup_before_model,
    respond_on_wa,
    send_takeaway_menu_tool,
    transfer_to_delivery,
    transfer_to_triage,
)


# %%


async def verify_if_payment_complete(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime[ContextSchema],
):
    """
    When ever user says he has completed the payment OR asks for an update on the order, use this tool
    Args:
        state: The current state of the agent, which may contain relevant data for the order.
    """
    is_order_summary_avialable = bool(state.get("order_summary"))
    is_payment_link_sent = bool(state.get("payment_link"))
    is_payment_successful = bool(state.get("is_payment_successful"))

    if is_order_summary_avialable and is_payment_link_sent and is_payment_successful:
        logger.info("Condition 1 met: Payment complete")
        return "Payment complete"

    elif is_order_summary_avialable and is_payment_link_sent:
        logger.info("Condition 2 met: Awaiting Payment")
        return "Awaiting Payment"

    elif not is_order_summary_avialable:
        logger.info("Condition 3 met: User to place food order on WhatsApp")
        return "User to place food order on WhatsApp"

    elif not is_payment_link_sent:
        return "payment link not sent, AI to send the payment link using tool `get_payment_link`"


takeaway_tools = [
    verify_if_payment_complete,
    send_takeaway_menu_tool,
    transfer_to_delivery,  # Handoff to delivery agent
    transfer_to_triage,  # Handoff to triage for out-of-scope queries and termination
]

# %%
def build_takeaway_agent(*, model, system_prompt: str, extra_tools=()):
    return create_agent(
        model=model,
        tools=[*takeaway_tools, *extra_tools],
        system_prompt=system_prompt,
        middleware=[
            cleanup_before_model,
            respond_on_wa,
        ],
        state_schema=AgentState,
        context_schema=ContextSchema,
    )
