---
# Feature: Multi-Agent Orchestration System
The multi-agent orchestration system coordinates conversations across specialized agents (Triage, Delivery, Takeaway) using a LangGraph StateGraph with conditional routing. It exists to classify customer intent and seamlessly hand off conversations between agents while preserving shared state. The triage agent greets customers, answers inquiries/general questions, routes to the appropriate ordering agent, and handles unsupported dine-in/reservation requests directly; transfer tools update `active_agent` in shared state and the router graph directs execution to the correct agent node on each turn.

---

## Human-Friendly Code Map
- [Multi-agent graph builder](./rest_agent/agents/multi_agent.py)
- [Shared state schemas and transfer tools](./rest_agent/agents/agent_harness.py)
- [Triage agent definition](./rest_agent/agents/triage.py)
- [Triage agent system prompt](./rest_agent/agents/prompts/triage_agent_prompt.md)
- [Graph runner (entry point)](./rest_agent/agent_runner.py)
- [Callback handler (service selection)](./watomation/on_callback_handler.py)
- [WhatsApp sending helpers](./rest_agent/agent_wa_senders.py)

### Detailed Flow Explanation
1. A WhatsApp message arrives and is routed to `run_elai_graph_with_custom_msg` in `agent_runner.py`, which compiles the multi-agent graph from `multi_agent.builder` with a PostgreSQL checkpointer and builds a `ContextSchema` carrying runtime resources (DB pool, WhatsApp client, recipient, Ordelo client).
2. On the first turn of a new thread, the runner seeds `wa_name` and a system message instructing the agent to call `send_welcome_msg`. The graph enters via `START` and `route_initial` reads `active_agent` from state, defaulting to `"triage_agent"` when no agent has been selected.
3. The triage agent node (`call_triage_agent`) invokes the triage LangChain agent, which is configured with tools for welcome, service selection, marketing consent, termination, and delivery/takeaway transfers. Middleware hooks (`cleanup_before_model`, `respond_on_wa`) handle skipping redundant LLM calls when `/DoNotRespond:` markers are present and sending WhatsApp replies.
4. The triage agent greets the customer via `send_welcome_message`, then sends service selection buttons (Collection / Delivery / Inquiry) and ends the turn with a `/DoNotRespond:` marker.
5. When the customer taps a service button, `select_service_handler` in `on_callback_handler.py` parses callback data and updates shared state via `run_elai_graph_with_custom_msg` with `state_update_dict` containing the new `active_agent` value (`"delivery_agent"`, `"takeaway_agent"`, or `"triage_agent"` for Inquiry). If `active_agent` is missing but `rest_ref` is present, the handler sends service selection buttons.
6. If the customer's intent is clear from text (e.g., delivery or takeaway), the triage agent calls the matching transfer tool directly. Dine-in/table/reservation requests stay in triage and are answered as unsupported for this WhatsApp flow. Transfer tools in `agent_harness.py` run the delivery retain guard, which blocks transfer away from delivery while `retain_thread=True`.
7. After any agent node completes, `route_after_agent` inspects the last message: if it is an `AIMessage` without tool calls, the graph ends (`__end__`); otherwise it reads `active_agent` from state and routes to the corresponding agent node, enabling seamless multi-turn handoffs.
8. The delivery and takeaway agent nodes (`call_delivery_agent`, `call_takeaway_agent`) are wrappers that invoke their compiled agents.
9. State persists across turns via `AsyncPostgresSaver`. The `AgentState` TypedDict includes `active_agent` for routing, `messages` with an `add_messages` reducer for conversation history, and all order/delivery/payment flags shared across agents. `ContextSchema` (Pydantic BaseModel) carries the PostgreSQL pool, WhatsApp client, recipient, Ordelo client, and a lazily-initialized `ThreadHandler`.

### Code References

#### Graph Construction & Routing — Builds the state machine and decides which agent runs next
- `build_multi_agent_graph` in [`rest_agent/agents/multi_agent.py`](./rest_agent/agents/multi_agent.py) — Constructs the StateGraph with triage, delivery, and takeaway agent nodes plus conditional routing edges based on `active_agent` state.
- `route_initial` in [`rest_agent/agents/multi_agent.py`](./rest_agent/agents/multi_agent.py) — Routes the initial graph entry to the active agent, defaulting to `triage_agent` when no agent has been selected yet.
- `route_after_agent` in [`rest_agent/agents/multi_agent.py`](./rest_agent/agents/multi_agent.py) — Ends the graph when the last message is an AIMessage without tool calls, or routes to the next active agent for continued processing.

#### Agent Node Wrappers — Invoke each specialized agent within the graph
- `call_triage_agent` in [`rest_agent/agents/multi_agent.py`](./rest_agent/agents/multi_agent.py) — Invokes the triage agent and returns its Command response for graph routing.
- `call_delivery_agent` in [`rest_agent/agents/multi_agent.py`](./rest_agent/agents/multi_agent.py) — Invokes the compiled delivery sub-graph and returns its response.
- `call_takeaway_agent` in [`rest_agent/agents/multi_agent.py`](./rest_agent/agents/multi_agent.py) — Invokes the takeaway agent sub-graph and returns its response.

#### Shared State & Runtime Resources — Define the data all agents read and write
- `AgentState` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Shared TypedDict containing `active_agent` for routing, `messages` with `add_messages` reducer, and all order/delivery/payment flags.
- `ContextSchema` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Pydantic BaseModel carrying runtime resources (PostgreSQL pool, WhatsApp client, recipient, Ordelo client, ThreadHandler) shared across all graph nodes and tools.

#### Agent Handoff Tools — Transfer control between agents mid-conversation
- `transfer_to_delivery` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Sets `active_agent` to `delivery_agent` and returns a parent-graph handoff command with a ToolMessage.
- `transfer_to_takeaway` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Sets `active_agent` to `takeaway_agent` and returns a parent-graph handoff command with a ToolMessage.
- `terminate_conversation` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Marks threads inactive, sends a goodbye message via WhatsApp, and ends the graph.

#### Middleware — Controls when the LLM runs and how responses reach WhatsApp
- `cleanup_before_model` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Pre-model hook that detects `/DoNotRespond:` markers in the last message and skips the LLM call by jumping to end.
- `respond_on_wa` in [`rest_agent/agents/agent_harness.py`](./rest_agent/agents/agent_harness.py) — Post-agent hook that sends AI responses via WhatsApp and cleans up `/DoNotRespond:` markers from message history.

#### Triage Agent — Greets the customer and routes them to the right ordering agent
- `agent` in [`rest_agent/agents/triage.py`](./rest_agent/agents/triage.py) — LangChain agent configured with triage tools (welcome, service selection, marketing consent, termination, and delivery/takeaway transfer) and middleware hooks for WhatsApp response handling.
- `send_welcome_message` in [`rest_agent/agents/triage.py`](./rest_agent/agents/triage.py) — Sends a personalized welcome message to the customer at conversation start via WhatsApp.
- `ask_user_to_select_service` in [`rest_agent/agents/triage.py`](./rest_agent/agents/triage.py) — Sends interactive WhatsApp buttons (Collection / Delivery / Inquiry) and ends the turn with a DoNotRespond marker.

#### Graph Execution — Compiles and runs the multi-agent graph for each incoming message
- `run_elai_graph_with_custom_msg` in [`rest_agent/agent_runner.py`](./rest_agent/agent_runner.py) — Compiles the graph with a PostgreSQL checkpointer, injects messages and state updates, and executes the graph returning the AI response.

#### WhatsApp Callback Handling — Processes button taps and sends interactive messages
- `select_service_handler` in [`watomation/on_callback_handler.py`](./watomation/on_callback_handler.py) — Handles `/SelectService` callback buttons for service selection, parsing `rest_ref` and `active_agent` from callback data and routing back into the graph. If `active_agent` is missing but `rest_ref` is present, it sends service selection buttons.
- `select_service_wa_send` in [`rest_agent/agent_wa_senders.py`](./rest_agent/agent_wa_senders.py) — Sends WhatsApp buttons for Collection / Delivery / Inquiry with `rest_ref` and `active_agent` encoded in `/SelectService` callback data.

### Edge Cases
- No `active_agent` in state -> `route_initial` defaults to `"triage_agent"`, ensuring new conversations always start with triage.
- Agent returns AIMessage without tool calls -> `route_after_agent` routes to `__end__`, preventing infinite loops when the agent has finished responding.
- Transfer tool called but target agent sub-graph fails -> the error propagates through `run_elai_graph_with_custom_msg`; OpenAI BadRequestError from tool-call mismatch triggers `_repair_last_ai_tool_call_message` or session termination.
- Inquiry button selected -> `select_service_handler` invokes triage with `HumanMessage("Inquiry")`, and triage asks one concise direct question to understand the inquiry.
- Stale thread with no recent activity -> the PostgreSQL job excludes latest-checkpoint `retain_thread=True` rows and sends eligible thread IDs and recipients directly to thread hooks, whose bounded background worker invokes `terminate_conversation` without a preflight database recheck.
- Transfer requested while `retain_thread=True` (delivery in progress) -> `_transfer_check_delivery_retain` blocks handoff and keeps the user in the current delivery flow.
- Circular handoffs (e.g., triage -> delivery -> triage) -> prevented by `route_after_agent` ending the graph when no tool calls are pending; state-based routing ensures only one agent is active per turn.
- Incomplete callback data (missing `active_agent` after service selection) -> `select_service_handler` logs an error and returns without advancing the graph.
