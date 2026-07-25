# %% [CELL 1] Core Imports
"""Multi-agent orchestration for the restaurant agent.

This module implements a multi-agent pattern that coordinates between:
  - Triage Agent: Initial greeting, Q&A, and routing to appropriate agent
  - Delivery Agent: Handles delivery orders
  - Takeaway Agent: Handles takeaway/collection orders

The shared state schemas (ContextSchema, AgentState) and transfer tools
are defined in agent_harness.py to avoid circular imports.
"""

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from bnat_agent.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
)
from bnat_agent.rest_agent.agents.triage import agent as triage_agent


# %% Agent node wrappers
async def call_triage_agent(state: AgentState) -> Command:
    """Node that calls the triage agent."""
    response = await triage_agent.ainvoke(state)
    return response


# %% Router functions
def route_after_agent(
    state: AgentState,
) -> Literal["triage_agent", "delivery_agent", "takeaway_agent", "__end__"]:
    """Route based on active_agent, or END if the agent finished without handoff."""
    messages = state.get("messages", [])

    # Check the last message - if it's an AIMessage without tool calls, we're done
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
            return "__end__"

    # Otherwise route to the active agent, with fallback for invalid values
    active = state.get("active_agent", "triage_agent")
    valid_agents = {"triage_agent", "delivery_agent", "takeaway_agent"}
    if not active or active not in valid_agents:
        return "triage_agent"
    return active


def route_initial(
    state: AgentState,
) -> Literal["triage_agent", "delivery_agent", "takeaway_agent"]:
    """Route to the active agent based on state, default to triage agent."""
    active = state.get("active_agent") or "triage_agent"
    valid_agents = {"triage_agent", "delivery_agent", "takeaway_agent"}
    if active not in valid_agents:
        return "triage_agent"
    return active


# %% Build the multi-agent graph
def build_multi_agent_graph(
    delivery_agent_node,
    takeaway_agent_node,
):
    """Build the multi-agent graph with delivery, takeaway, and triage agents.

    Args:
        delivery_agent_node: Callable node for delivery agent (from delivery.py)
        takeaway_agent_node: Callable node for takeaway agent (from takeaway.py)

    Returns:
        Compiled StateGraph for multi-agent orchestration
    """
    builder = StateGraph(state_schema=AgentState, context_schema=ContextSchema)

    # Add agent nodes
    builder.add_node("triage_agent", call_triage_agent)
    builder.add_node("delivery_agent", delivery_agent_node)
    builder.add_node("takeaway_agent", takeaway_agent_node)

    # Start with conditional routing based on initial active_agent
    builder.add_conditional_edges(
        START,
        route_initial,
        ["triage_agent", "delivery_agent", "takeaway_agent"],
    )

    # After triage agent, check if we should end or route to another agent
    builder.add_conditional_edges(
        "triage_agent",
        route_after_agent,
        ["triage_agent", "delivery_agent", "takeaway_agent", END],
    )

    # After delivery agent, check if we should end or route to another agent
    builder.add_conditional_edges(
        "delivery_agent",
        route_after_agent,
        ["triage_agent", "delivery_agent", "takeaway_agent", END],
    )

    # After takeaway agent, check if we should end or route to another agent
    builder.add_conditional_edges(
        "takeaway_agent",
        route_after_agent,
        ["triage_agent", "delivery_agent", "takeaway_agent", END],
    )

    return builder


# %% Example usage (for testing)
# To use the multi-agent graph:

# from bnat_agent.rest_agent.agents.multi_agent import (
#     build_multi_agent_graph,
# )
# from bnat_agent.rest_agent.agents.agent_harness import (
#     ContextSchema,
#     AgentState,
# )

# from bnat_agent.rest_agent.agents.delivery_multiagent import builder as delivery_agent_builder

# delivery_agent = delivery_agent_builder.compile()
from bnat_agent.rest_agent.agents.delivery import agent as delivery_agent

# %%

from bnat_agent.rest_agent.agents.takeaway import agent as takeaway_agent


# Create agent nodes that invoke the agents
async def call_delivery_agent(state: AgentState) -> Command:
    "Node that calls the delivery agent."
    response = await delivery_agent.ainvoke(state)
    return response


async def call_takeaway_agent(state: AgentState) -> Command:
    "Node that calls the takeaway agent."
    response = await takeaway_agent.ainvoke(state)
    return response


builder = build_multi_agent_graph(
    delivery_agent_node=call_delivery_agent,
    takeaway_agent_node=call_takeaway_agent,
)


# %%

""" Test
# %%

from bnat_agent.rest_agent.agents.agent_harness import get_context_schema
from restaurant_agent_core.services.lg_utils import get_config_for_recipient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

recipient = "447446933210"
config, _ = await get_config_for_recipient(recipient)
checkpointer = AsyncPostgresSaver(pool)

context_schema = await get_context_schema(recipient)
pool = context_schema.pool
# %%
agent = builder.compile(checkpointer=checkpointer)


# %% AGent Loop
initial_msg: str | None = None
while True:
    if initial_msg is not None:
        human_msg = initial_msg
        initial_msg = None
    else:
        human_msg = input("Human Input: ")

    if human_msg.strip().lower() == "exit":
        break

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": human_msg}]},
        config=config,
        context=context_schema,
    )
    print(result["messages"][-1].content)

# %% Check state
from bnat_agent.rest_agent.agent_runner import debug_state_values
from restaurant_agent_core.services.lg_utils import (
    get_config_for_recipient,
    get_state_values,
    shorten_state_messages,
)

state = await graph.aget_state(config=config,)
state.values
# state_values = get_state_values(state.values)
# print(state_values)

# %%
await graph.aupdate_state(
    config=config,
    values={"active_agent": "delivery_agent"},
    # as_node="toolNode",
)

# %%

"""
