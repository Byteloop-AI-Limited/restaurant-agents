# Feature: Shared Delivery WhatsApp Agent

The delivery agent is one standard node in the shared Restaurant Agent runtime.
It handles address capture and confirmation, minimum-order checks, menu
delivery, payment status, customer updates, rider allocation, live location,
and handoffs. Its implementation and standard tools are shared; each restaurant
application supplies its own complete delivery prompt and may use the documented
customization seams.

See [the multi-agent system overview](./multi_agent_system.md) and
[the interactive composition guide](./guides/agent-runtime-composition.html)
for the complete ownership model.

---

## Human-Friendly Code Map

- [Standard graph adapter and runner](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py)
- [Delivery agent and ordered tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py)
- [Shared state, context, handoffs, and menu tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py)
- [Fixed multi-agent graph](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py)
- [WhatsApp sending helpers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_wa_senders.py)
- [Inbound message handler](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py)
- [Callback handlers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py)
- [Order event router](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py)
- [Rider event router](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/rider_event_hooks.py)
- [Thread router](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/thread_hooks.py)
- [SFCS delivery prompt](../apps/sfcs/src/sfcs_agent/rest_agent/prompts/delivery_multiagent_prompt.md)
- [BNAT delivery prompt](../apps/bnat/src/bnat_agent/rest_agent/prompts/delivery_multiagent_prompt.md)

## Ownership and Composition

- The shared runtime owns `build_delivery_agent`, its thirteen ordered default
  tools, `AgentState`, `ContextSchema`, middleware, graph routing, checkpointing,
  repair, debug behavior, and common WhatsApp helpers.
- Each app owns a complete `delivery_multiagent_prompt.md` and loads it through
  `rest_agent/agent_recipe.py`.
- `RestaurantGraphAdapter` injects the app runtime's selected model and complete
  delivery prompt into `build_delivery_agent`.
- The same `RestaurantRuntime.async_wa_client` is placed in `ContextSchema`, so
  delivery tools send through the exact client bound to the running app.

## Detailed Flow Explanation

1. A WhatsApp message, callback, or internal event reaches a shared handler that
   depends on the app's `GraphAdapter`.
2. `handle_wa_msg_in_graph()` forwards customer text, recipient, and WhatsApp
   display name to `graph_adapter.run_rest_graph_with_custom_msg()`.
3. The adapter compiles the pre-built three-node graph with a PostgreSQL
   checkpointer for the operation, resolves the app-prefixed thread, and creates
   `ContextSchema` from the exact `RestaurantRuntime`.
4. `route_initial()` follows the persisted `active_agent`. Selecting Delivery or
   calling `transfer_to_delivery` sets it to `delivery_agent`.
5. `build_delivery_agent()` creates the native LangChain agent with the
   app-owned complete prompt, shared state/context schemas, common WhatsApp
   middleware, thirteen ordered default tools, and any app-owned extra tools.
6. Address tools capture, update, and confirm customer location. The minimum
   order tool checks delivery eligibility before the delivery menu tool sends a
   restaurant-specific menu link.
7. Payment, order, and rider tools read and update shared graph state and use
   injected runtime resources rather than application imports or module-global
   WhatsApp clients.
8. Order and rider routers validate `rest_ref` against the running app before
   scheduling graph work. Payment completion activates `delivery_agent`, records
   order/payment state, and retains the thread while driver assignment is
   pending.
9. `transfer_to_takeaway` handles a service change.
   `transfer_to_triage` handles out-of-scope intent. Shared transfer guards can
   block a handoff while retained delivery work is active.
10. `cleanup_before_model` and `respond_on_wa` coordinate tool-only turns,
    `/DoNotRespond:` markers, and outbound WhatsApp responses.

## Ordered Default Tools

1. `send_welcome_msg`
2. `answer_general_query`
3. `confirm_delivery_address`
4. `capture_delivery_address`
5. `update_address_of_existing_user`
6. `calculate_min_order_value`
7. `send_restaurant_menu_tool`
8. `verify_if_payment_complete`
9. `send_updates_to_customer`
10. `check_delivery_driver_allocation_status`
11. `send_rider_live_location_link`
12. `transfer_to_takeaway`
13. `transfer_to_triage`

The ordered list is part of the shared graph contract and is asserted in
`tests/rest_agent/test_graph_contract.py`.

## Delivery Customization

### Prompt-only behavior

Edit the owning app's complete delivery prompt. Do not copy or modify the shared
delivery implementation for wording, policies, restaurant identity, or
tool-use instructions.

### Additional delivery tool

Keep the native tool in the app and bind it through:

```python
extra_tools_by_agent={"delivery_agent": [custom_delivery_tool]}
```

Extra tools append after the standard list.

### Complete delivery-agent replacement

Use:

```python
agent_overrides={"delivery_agent": CUSTOM_DELIVERY_AGENT}
```

The runnable must expose `ainvoke` and preserve the fixed node name, shared
state/context, and handoff contract.

### Incompatible delivery graph

An app owns a complete `GraphAdapter` if delivery requires a new node,
incompatible state fields/reducers, changed routing/handoffs, or different
checkpointing, compilation, repair, or debug semantics.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py
symbol: run_rest_graph_with_custom_msg
feature: delivery-whatsapp-agent
description: >
  Runs the shared graph with PostgreSQL checkpointing and a ContextSchema built from the exact application runtime.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: build_delivery_agent
feature: delivery-whatsapp-agent
description: >
  Constructs the delivery LangChain agent from an injected model, complete app-owned prompt, shared schemas, middleware, default tools, and optional extra tools.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: delivery_tools
feature: delivery-whatsapp-agent
description: >
  Defines the ordered standard delivery capabilities and triage/takeaway handoffs.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py
symbol: ContextSchema
feature: delivery-whatsapp-agent
description: >
  Carries the exact runtime WhatsApp client, recipient, database resources, restaurant identity, presentation, and project settings into delivery tools.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: capture_delivery_address
feature: delivery-whatsapp-agent
description: >
  Starts address capture or update behavior through runtime-bound WhatsApp and order-service resources.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: calculate_min_order_value
feature: delivery-whatsapp-agent
description: >
  Resolves delivery eligibility and the minimum order value from the injected restaurant context.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: send_restaurant_menu_tool
feature: delivery-whatsapp-agent
description: >
  Sends the delivery menu only after address capture and confirmation guards pass.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: delivery-whatsapp-agent
description: >
  Validates the target app and payload identity, acknowledges payment, updates delivery graph state, and schedules runtime-bound graph work.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/rider_event_hooks.py
symbol: rider_inflight
feature: delivery-whatsapp-agent
description: >
  Validates the restaurant route and schedules customer notification and delivery-state updates through the injected adapter.
```

## Edge Cases

- Missing or unconfirmed address prevents delivery menu progression.
- A minimum-order lookup that cannot establish eligibility prevents ordering.
- Recipient or thread mismatch in payment events returns `400`.
- A cross-restaurant route returns `404` before graph work or external effects.
- Driver allocation or live-location failure produces fallback customer
  messaging.
- `retain_thread=True` can block handoff while active delivery work must finish.
- A menu-send `ValueError` sends fallback text and ends the turn.
- Malformed persisted tool-call tails are repaired before model invocation; an
  unrecoverable mismatch terminates the session.
