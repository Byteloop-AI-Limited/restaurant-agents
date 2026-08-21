# %% [CELL 1] Core Imports
"""Multi-agent orchestration for the restaurant agent.

This module implements a multi-agent pattern that coordinates between:
  - Triage Agent: Initial greeting, Q&A, and routing to appropriate agent
  - Delivery Agent: Handles delivery orders
  - Takeaway Agent: Handles takeaway/collection orders

The shared state schemas (ContextSchema, AgentState) and transfer tools
are defined in agent_harness.py to avoid circular imports.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
)

STANDARD_AGENTS = ("triage_agent", "delivery_agent", "takeaway_agent")
DINEIN_AGENT = "dinein_agent"


# %% Router functions
def route_after_agent(
    state: AgentState,
    *,
    valid_agents: frozenset[str] = frozenset(STANDARD_AGENTS),
) -> str:
    """Route based on active_agent, or END if the agent finished without handoff."""
    messages = state.get("messages", [])

    # Check the last message - if it's an AIMessage without tool calls, we're done
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
            return "__end__"

    # Otherwise route to the active agent, with fallback for invalid values
    active = state.get("active_agent", "triage_agent")
    if not active or active not in valid_agents:
        return "triage_agent"
    return active


def route_initial(
    state: AgentState,
    *,
    valid_agents: frozenset[str] = frozenset(STANDARD_AGENTS),
) -> str:
    """Route to the active agent based on state, default to triage agent."""
    active = state.get("active_agent") or "triage_agent"
    if active not in valid_agents:
        return "triage_agent"
    return active


# %% Build the multi-agent graph
def build_multi_agent_graph(
    triage_agent_node,
    delivery_agent_node,
    takeaway_agent_node,
    dinein_agent_node=None,
):
    """Build the multi-agent graph with delivery, takeaway, and triage agents.

    Args:
        triage_agent_node: Callable node for triage agent (from triage.py)
        delivery_agent_node: Callable node for delivery agent (from delivery.py)
        takeaway_agent_node: Callable node for takeaway agent (from takeaway.py)
        dinein_agent_node: Optional callable node for the dine-in agent (from
            dine_in.py). Only apps that configure a dine-in prompt supply
            this; every other app gets today's unchanged three-node graph.

    Returns:
        Uncompiled StateGraph builder for multi-agent orchestration
    """
    node_names = STANDARD_AGENTS
    if dinein_agent_node is not None:
        node_names = (*STANDARD_AGENTS, DINEIN_AGENT)
    valid_agents = frozenset(node_names)

    def _route_after_agent(state: AgentState) -> str:
        return route_after_agent(state, valid_agents=valid_agents)

    def _route_initial(state: AgentState) -> str:
        return route_initial(state, valid_agents=valid_agents)

    builder = StateGraph(state_schema=AgentState, context_schema=ContextSchema)

    # Add agent nodes
    builder.add_node("triage_agent", triage_agent_node)
    builder.add_node("delivery_agent", delivery_agent_node)
    builder.add_node("takeaway_agent", takeaway_agent_node)
    if dinein_agent_node is not None:
        builder.add_node(DINEIN_AGENT, dinein_agent_node)

    # Start with conditional routing based on initial active_agent
    builder.add_conditional_edges(START, _route_initial, list(node_names))

    # After each agent, check if we should end or route to another agent
    destinations = [*node_names, END]
    for node_name in node_names:
        builder.add_conditional_edges(node_name, _route_after_agent, destinations)

    return builder
