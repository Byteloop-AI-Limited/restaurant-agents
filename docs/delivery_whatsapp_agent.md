---
# Feature: Delivery WhatsApp Agent
The Elai delivery WhatsApp agent orchestrates menu browsing, ordering, and delivery updates through a LangGraph workflow backed by PostgreSQL checkpoints. It exists to keep conversation state synchronized with Supabase/Ordelo data and WhatsApp interactions, allowing automated but tool-driven responses. In multi-agent mode, delivery supports explicit handoff to takeaway when customer intent changes and routes unsupported dine-in/reservation requests back to triage, while preserving thread context and transfer safety guards.

---

## Human-Friendly Code Map
- [Agent runner entrypoint](./rest_agent/agent_runner.py)
- [Delivery agent graph and tools](./rest_agent/agents/delivery.py)
- [WhatsApp sending helpers](./rest_agent/agent_wa_senders.py)
- [LLM prompt for delivery agent (multi-agent)](./rest_agent/agents/prompts/delivery_multiagent_prompt.md)
- [Incoming WhatsApp message handler](./watomation/on_message_graph_handler.py)
- [Callback button handler](./watomation/on_callback_handler.py)
- [WhatsApp Flow (address form) handler](./watomation/on_flow_request_postcode_search.py)
- [Catalog order handler](./watomation/on_order_handler.py)
- [Order/payment webhook router](./watomation/routers/order_event_hooks.py)
- [Rider event webhooks](./watomation/routers/rider_event_hooks.py)
- [Payment webhook (Stripe) handler](./watomation/routers/payment_hooks_tbd.py)
- [Thread timeout hooks](./watomation/routers/thread_hooks.py)

### Detailed Flow Explanation
1. Entry points (message, button callback, flow completion, order/payment/rider webhooks, and stale-thread cleanup) call `run_elai_graph_with_custom_msg` with human/system/tool instructions plus optional state updates to nudge the graph.
2. `run_elai_graph_with_custom_msg` compiles the delivery graph with a Postgres checkpointer, builds `ContextSchema` (WhatsApp client, pools, recipient), fetches or reuses thread config, and seeds welcome guidance when a new thread arrives with a known `wa_name`.
3. Incoming prompts are normalized into LangChain messages (`SystemMessage`, `AIMessage`, `HumanMessage`), merged with optional `state_update_dict` applied to `toolNode` for immediate state mutation before graph execution.
4. The compiled `builder` graph (`setupNode` → `deliveryAgent` → optional `toolNode`) runs via `graph.ainvoke`, preserving conversation history and returning the new AI message; outbound WhatsApp sends are executed inside agent/tool nodes when needed.
5. `setup_node` hydrates customer address/min-order context from Supabase, seeds journey instructions as `SystemMessage`, or requests address capture for new users before handing off to the main agent node.
6. `agent_node` feeds state into the LLM agent (built from `delivery_multiagent_prompt.md` and registered tools). Tool calls route to `ToolNode`, while plain replies are pushed to WhatsApp and the turn ends.
7. Tool implementations in `delivery.py` delegate side effects to `agent_wa_senders.py` (welcome/menu/address flows, live location buttons) and Ordelo/payment services, updating state flags for address confirmation, min order value, order IDs, payment status, rider allocation, and termination.
8. External events keep the conversation aligned: order handlers attach order_id/order_number, payment hooks flip `is_payment_successful`, rider hooks broadcast driver allocation/pickup/arrival, and thread hooks terminate inactive sessions via `terminate_conversation`.
9. Explicit takeaway intent triggers `transfer_to_takeaway`, and unsupported dine-in/reservation intent triggers `transfer_to_triage`. The prompt requires tool-call-only transfer responses (no extra text) for these handoffs.
10. Shared transfer guards in `agent_harness.py` are applied before handoff: transfer is blocked while `retain_thread=True` (active retained flow).

### Code References (Machine-Readable)
file: rest_agent/agent_runner.py
symbol: run_elai_graph_with_custom_msg
feature: Delivery WhatsApp Agent
description: >
  Executes the delivery LangGraph with optional custom messages and state updates, wiring context (DB pool, WhatsApp client) and returning the latest AI reply content.

file: rest_agent/agents/delivery.py
symbol: AgentState
feature: Delivery WhatsApp Agent
description: >
  Defines the structured state tracked across the delivery conversation, covering messages, address, payment, rider, and order-type flags.

file: rest_agent/agents/delivery.py
symbol: ContextSchema
feature: Delivery WhatsApp Agent
description: >
  Carries runtime resources (Postgres pool, WhatsApp client, recipient, Ordelo client) into graph nodes and tools.

file: rest_agent/agents/delivery.py
symbol: setup_node
feature: Delivery WhatsApp Agent
description: >
  Prepares the graph turn by fetching customer address data, emitting journey guidance, or prompting address capture before entering the main agent.

file: rest_agent/agents/delivery.py
symbol: agent_node
feature: Delivery WhatsApp Agent
description: >
  Runs the LLM agent, forwards tool calls to ToolNode, or sends direct WhatsApp replies while cleaning /DoNotRespond scaffolding.

file: rest_agent/agents/delivery.py
symbol: delivery_agent
feature: Delivery WhatsApp Agent
description: >
  LLM agent built from the delivery prompt and registered tools with parallel calls disabled for sequential flow control.

file: rest_agent/agents/delivery.py
symbol: delivery_tools
feature: Delivery WhatsApp Agent
description: >
  Multi-agent delivery toolset that includes transfer_to_takeaway for collection service-switch handoff and transfer_to_triage for unsupported dine-in/reservation requests.

file: rest_agent/agents/prompts/delivery_multiagent_prompt.md
symbol: (prompt document)
feature: Delivery WhatsApp Agent
description: >
  Multi-agent prompt guidance that requires immediate tool-call transfer for explicit takeaway intent and triage transfer for unsupported dine-in/reservation intent.

file: rest_agent/agents/delivery.py
symbol: send_welcome_msg
feature: Delivery WhatsApp Agent
description: >
  Sends personalized greeting plus delivery/takeaway buttons and marks the turn complete with non-response marker.

file: rest_agent/agents/delivery.py
symbol: capture_delivery_address
feature: Delivery WhatsApp Agent
description: >
  Triggers address update flow for new users and halts the graph after emitting tool and AI messages.

file: rest_agent/agents/delivery.py
symbol: confirm_delivery_address
feature: Delivery WhatsApp Agent
description: >
  Sends address confirmation buttons or acknowledges existing confirmation, guiding next steps via ToolMessage updates.

file: rest_agent/agents/delivery.py
symbol: calculate_min_order_value
feature: Delivery WhatsApp Agent
description: >
  Looks up location-aware minimum order value, marks outside-area cases, and instructs menu sending when eligible.

file: rest_agent/agents/delivery.py
symbol: send_restaurant_menu_tool
feature: Delivery WhatsApp Agent
description: >
  Dispatches the WhatsApp restaurant menu (delivery or takeaway) and pauses for user selection.

file: rest_agent/agents/delivery.py
symbol: verify_if_payment_complete
feature: Delivery WhatsApp Agent
description: >
  Checks payment status in Ordelo, updates state, and informs customer about driver assignment or pickup timing.

file: rest_agent/agents/delivery.py
symbol: check_delivery_driver_allocation_status
feature: Delivery WhatsApp Agent
description: >
  Polls driver assignment via Ordelo and notifies the customer, including timeout handling.

file: rest_agent/agents/delivery.py
symbol: send_rider_live_location_link
feature: Delivery WhatsApp Agent
description: >
  Validates and shares live rider location via WhatsApp buttons, updating state with tool feedback.

file: rest_agent/agents/delivery.py
symbol: send_updates_to_customer
feature: Delivery WhatsApp Agent
description: >
  Sends arbitrary status updates to the customer and mirrors them into conversation state.

file: rest_agent/agents/delivery.py
symbol: terminate_conversation
feature: Delivery WhatsApp Agent
description: >
  Marks threads inactive, sends goodbye messaging, and ends the graph turn with termination metadata.

file: rest_agent/agent_wa_senders.py
symbol: delivery_or_takeaway
feature: Delivery WhatsApp Agent
description: >
  Presents delivery/takeaway buttons used in welcomes and order-type selection callbacks.

file: rest_agent/agent_wa_senders.py
symbol: confirm_delivery_address_wa
feature: Delivery WhatsApp Agent
description: >
  Sends interactive address confirmation buttons that drive subsequent callback handling.

file: watomation/on_message_graph_handler.py
symbol: handle_wa_msg_in_graph
feature: Delivery WhatsApp Agent
description: >
  Primary inbound WhatsApp text handler that forwards user messages and wa_name into the delivery graph runner.

file: watomation/on_callback_handler.py
symbol: delivery_or_takeaway_selection
feature: Delivery WhatsApp Agent
description: >
  Processes delivery/takeaway button callbacks, sets is_delivery state, and re-enters the graph.

file: watomation/on_flow_request_postcode_search.py
symbol: on_pc_search_complete
feature: Delivery WhatsApp Agent
description: >
  Handles completed address form submissions, persists address, updates graph state, and resumes the flow via system prompt.

file: watomation/on_order_handler.py
symbol: handle_order
feature: Delivery WhatsApp Agent
description: >
  Ingests WhatsApp catalog orders, validates against min order value, stores order details, and triggers graph updates.

file: watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: Delivery WhatsApp Agent
description: >
  Webhook endpoint marking payments complete, sending receipts, and updating graph state for driver allocation messaging.

file: watomation/routers/rider_event_hooks.py
symbol: rider_inflight
feature: Delivery WhatsApp Agent
description: >
  Rider assignment webhook that updates graph state to mark driver allocation and prompts customer notification.

file: watomation/routers/payment_hooks_tbd.py
symbol: handle_payment_complete
feature: Delivery WhatsApp Agent
description: >
  Stripe webhook processor that flips payment status in Ordelo and asks the agent to verify payment completion.

file: watomation/routers/thread_hooks.py
symbol: terminate_stale_active_threads
feature: Delivery WhatsApp Agent
description: >
  Scheduled cleanup that closes inactive threads via the agent runner unless threads are explicitly retained.

### Edge Cases
- No stored address → `setup_node` routes to address capture; confirmation tool blocks progression until state flips true.
- Min order lookup returns None or -1 → state marks `is_outside_delivery_area` and resets order type to prevent ordering.
- Order total below min value → `handle_order` injects system warning and stops payment flow.
- Payment not completed or webhook mismatch → agent keeps `is_payment_successful` false and prompts completion.
- Explicit takeaway or dine-in intent while in delivery → multi-agent delivery prompt/tooling transfers immediately to the appropriate agent.
- Rider allocation timeout/unavailability → `check_delivery_driver_allocation_status` or timed-out hooks notify cancellation and may trigger payment reversal.
- Stale conversation threads without `retain_thread` → thread hooks end the session via `terminate_conversation`.
- Transfer requested while `retain_thread=True` → shared transfer guard blocks handoff until retained flow state is resolved.
- Live location fetch failure → `send_rider_live_location_link` sends fallback text instead of button.
