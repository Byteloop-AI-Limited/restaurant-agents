---
# Feature: Takeaway WhatsApp Agent
The takeaway WhatsApp agent handles collection/pickup orders through a LangGraph agent backed by PostgreSQL checkpoints. It exists to guide customers through the takeaway ordering flow: menu browsing, order placement via WhatsApp catalog, payment (online or pay-at-restaurant), pickup time confirmation, and conversation termination. The agent can hand off to delivery when customers switch intent and routes unsupported dine-in/reservation requests back to triage.

---

## Human-Friendly Code Map
- [Takeaway agent definition and tools](./rest_agent/agents/takeaway.py)
- [Takeaway agent system prompt](./rest_agent/agents/prompts/takeaway_agent_prompt.md)
- [Shared state schemas and transfer tools](./rest_agent/agents/agent_harness.py)
- [WhatsApp sending helpers](./rest_agent/agent_wa_senders.py)
- [Order/payment webhook router](./watomation/routers/order_event_hooks.py)
- [Takeaway Pydantic models](./services/order_management/takeaway_pymodels.py)
- [FoodOrder model](./services/order_management/food_order_pymodel.py)
- [Callback handler (service selection)](./watomation/on_callback_handler.py)
- [Graph runner (entry point)](./rest_agent/agent_runner.py)

### Detailed Flow Explanation
1. The customer selects "Takeaway" via WhatsApp interactive buttons handled by `select_service_handler` in `on_callback_handler.py`, which sets `active_agent` to `"takeaway_agent"` in graph state and re-enters the graph via `run_elai_graph_with_custom_msg`.
2. The multi-agent router directs execution to the takeaway agent node. The agent is a LangChain agent created with `create_agent`, configured with `takeaway_agent_prompt_str`, four tools (`send_takeaway_menu_tool`, `verify_if_payment_complete`, `transfer_to_delivery`, `transfer_to_triage`), and middleware hooks (`cleanup_before_model`, `respond_on_wa`).
3. When the customer wants to order, the agent calls `send_takeaway_menu_tool`, which retrieves the thread ID, constructs `RestMenuQueryParams` with `order_type="takeaway"`, and delegates to `send_restaurant_menu_non_carousel` in `agent_wa_senders.py` to send the menu link via WhatsApp. Menu media branding now resolves logo image by restaurant (`{rest_ref.lower()}_logo.jpg`). The turn ends with a `/DoNotRespond:` marker.
4. The customer browses the menu and places an order through the WhatsApp catalog. The order is processed externally: order items are stored in the database and a payment link is generated. A system message with order details is injected into the graph.
5. The customer can choose to pay online (Stripe) or pay at the restaurant upon pickup. If paying online, the payment service webhook calls `payment_complete` in `order_event_hooks.py` with a `FoodOrder` payload.
6. The `payment_complete` endpoint differentiates between delivery and takeaway orders via `food_order.action`. For takeaway orders, it sends a receipt with "We will confirm the pickup time in a moment", updates graph state with `order_id`, `order_number`, `is_payment_successful=True`, and `retain_thread=True`, then nudges the graph via a background task.
7. If the customer claims payment is complete or asks for an update, the agent calls `verify_if_payment_complete`, which checks three state fields: `order_summary`, `payment_link`, and `is_payment_successful`. It returns the appropriate status string ("Payment complete", "Awaiting Payment", "User to place food order on WhatsApp", or instructions to send the payment link).
8. After payment is confirmed (or pay-at-restaurant is acknowledged), the agent thanks the customer and indicates that pickup time will be confirmed shortly. The thread is retained via `retain_thread=True` to await the pickup time webhook.
9. When the restaurant confirms the order and sets a pickup time, the external service calls `takeaway_pickup_time_updated` in `order_event_hooks.py` with a `TakeawayPickupTimePayload` containing `TakeawaySummaryData` (order number, customer ID, pickup time, restaurant details). The endpoint runs a two-step background sequence: first it notifies the customer of the confirmed pickup time via the takeaway agent, then after a 5-second delay it calls `terminate_conversation` via the triage agent to end the session.
10. The `terminate_conversation` tool (defined in `agent_harness.py`) sends a goodbye message to the customer via WhatsApp, marks the thread as inactive, and ends the graph with `Command(goto=END)`.
11. If at any point the customer requests delivery instead of takeaway, the agent calls `transfer_to_delivery` (from `agent_harness.py`), which sets `active_agent` to `"delivery_agent"` and returns a handoff command.
12. If the customer requests table booking/dine-in, the agent calls `transfer_to_triage` so triage can explain that dine-in reservations are not available in this WhatsApp flow.

### Code References (Machine-Readable)
file: rest_agent/agents/agent_harness.py
symbol: send_takeaway_menu_tool
feature: Takeaway WhatsApp Agent
description: >
  Sends the restaurant takeaway menu to the customer via WhatsApp by constructing RestMenuQueryParams with order_type="takeaway" and delegating to send_restaurant_menu.

file: rest_agent/agents/takeaway.py
symbol: verify_if_payment_complete
feature: Takeaway WhatsApp Agent
description: >
  Checks order_summary, payment_link, and is_payment_successful state fields to determine and return the current payment status.

file: rest_agent/agents/takeaway.py
symbol: agent
feature: Takeaway WhatsApp Agent
description: >
  LangChain agent configured with takeaway tools, system prompt, middleware hooks, and shared AgentState/ContextSchema schemas.

file: rest_agent/agents/agent_harness.py
symbol: AgentState
feature: Takeaway WhatsApp Agent
description: >
  Shared TypedDict state schema containing messages, order/payment flags, and active_agent for multi-agent routing.

file: rest_agent/agents/agent_harness.py
symbol: ContextSchema
feature: Takeaway WhatsApp Agent
description: >
  Pydantic BaseModel carrying runtime resources (PostgreSQL pool, WhatsApp client, recipient, Ordelo client, ThreadHandler) into graph nodes and tools.

file: rest_agent/agents/agent_harness.py
symbol: transfer_to_delivery
feature: Takeaway WhatsApp Agent
description: >
  Transfer tool that sets active_agent to delivery_agent and returns a parent-graph handoff command for takeaway to delivery routing.

file: rest_agent/agents/agent_harness.py
symbol: terminate_conversation
feature: Takeaway WhatsApp Agent
description: >
  Marks threads inactive, sends goodbye via WhatsApp, and ends the graph with termination metadata.

file: rest_agent/agents/agent_harness.py
symbol: cleanup_before_model
feature: Takeaway WhatsApp Agent
description: >
  Pre-model middleware that detects /DoNotRespond: markers and skips the LLM call by jumping to end.

file: rest_agent/agents/agent_harness.py
symbol: respond_on_wa
feature: Takeaway WhatsApp Agent
description: >
  Post-agent middleware that sends AI responses via WhatsApp and cleans up /DoNotRespond: markers from message history.

file: rest_agent/agent_wa_senders.py
symbol: send_restaurant_menu
feature: Takeaway WhatsApp Agent
description: >
  Constructs RestMenuQueryParams and calls send_restaurant_menu_non_carousel to deliver the menu via WhatsApp, returning ValueError on failure.

file: services/wa_templates/rest_menu_wa_template.py
symbol: send_restaurant_menu_non_carousel
feature: Takeaway WhatsApp Agent
description: >
  Sends menu media and now resolves the WhatsApp image URL dynamically from rest_ref-specific logo assets.

file: watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: Takeaway WhatsApp Agent
description: >
  Webhook endpoint that processes payment completion for takeaway orders, sends receipt, updates graph state with order and payment details, and nudges the graph.

file: watomation/routers/order_event_hooks.py
symbol: takeaway_pickup_time_updated
feature: Takeaway WhatsApp Agent
description: >
  Webhook endpoint that receives confirmed pickup time from the restaurant and runs a two-step background sequence: first notifies the customer of the pickup time via the takeaway agent, then terminates the conversation via the triage agent after a 5-second delay.

file: services/order_management/takeaway_pymodels.py
symbol: TakeawaySummaryData
feature: Takeaway WhatsApp Agent
description: >
  Pydantic model containing takeaway order tracking fields including order_number, customer_id, pickup_time, restaurant details, and confirmation status.

file: services/order_management/takeaway_pymodels.py
symbol: TakeawayPickupTimePayload
feature: Takeaway WhatsApp Agent
description: >
  Pydantic model wrapping TakeawaySummaryData and RestaurantMasterData as the webhook payload for pickup time updates.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder
feature: Takeaway WhatsApp Agent
description: >
  Pydantic model representing the food_order table, used in payment_complete webhook to carry order details, pricing, and payment status.

file: watomation/on_callback_handler.py
symbol: select_service_handler
feature: Takeaway WhatsApp Agent
description: >
  Handles WhatsApp callback buttons for service selection, setting active_agent to takeaway_agent when takeaway is selected.

### Edge Cases
- Menu send failure -> `send_takeaway_menu_tool` catches `ValueError` from `send_restaurant_menu` and sends a fallback text message to the customer.
- Customer requests delivery mid-takeaway -> agent calls `transfer_to_delivery` which sets `active_agent` to `"delivery_agent"` and hands off to the delivery graph.
- Customer requests dine-in/table booking mid-takeaway -> agent calls `transfer_to_triage`; triage explains that dine-in reservations are not available in this WhatsApp flow and offers delivery or collection.
- Payment not yet complete when customer asks for update -> `verify_if_payment_complete` returns "Awaiting Payment" and the agent prompts the customer to complete payment.
- No order placed yet when payment check is called -> `verify_if_payment_complete` returns "User to place food order on WhatsApp" to redirect the flow.
- Pickup time webhook arrives before payment -> the system message instructs `terminate_conversation` regardless; the thread ends and the customer is given the pickup time.
- Pay-at-restaurant selected -> the agent acknowledges the choice; no `is_payment_successful` state flip occurs via webhook; the flow continues to pickup time confirmation.
- Stale thread without `retain_thread` -> thread hooks terminate the session; with `retain_thread=True` (set after payment), the thread persists until pickup time is confirmed.
- Transfer requested while `retain_thread=True` -> shared transfer guard can block handoff and keep the current flow until retained delivery/takeaway state is resolved.
- Recipient mismatch in payment webhook -> `payment_complete` returns HTTP 400 if `food_order.recipient` does not match the path parameter.
- No scheduled or prebooked pickups -> the agent prompt explicitly states all pickups are based on the confirmed time provided after order placement; no pre-booking is supported.
