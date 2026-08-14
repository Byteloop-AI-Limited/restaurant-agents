# Feature: Shared Takeaway WhatsApp Agent

The takeaway agent is one standard node in the shared Restaurant Agent runtime.
It handles collection-menu delivery, payment-state checks, customer updates, and
handoffs to delivery or triage. Its implementation and five default tools are
shared; each
restaurant application supplies a complete takeaway prompt and may use the
documented customization seams.

See [the multi-agent system overview](./multi_agent_system.md) and
[the interactive composition guide](./guides/agent-runtime-composition.html)
for the complete ownership model.

---

## Human-Friendly Code Map

- [Standard graph adapter and runner](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py)
- [Takeaway agent and ordered tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/takeaway.py)
- [Shared menu and handoff tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py)
- [Retained-specialist lifecycle projection](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/specialist_lifecycle.py)
- [Shared service-selection policy](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/service_selection.py)
- [Fixed multi-agent graph](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py)
- [WhatsApp sending helpers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_wa_senders.py)
- [Callback handlers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py)
- [Order event router](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py)
- [Takeaway order models](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/takeaway_pymodels.py)
- [FoodOrder model](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_pymodel.py)
- [SFCS takeaway prompt](../apps/sfcs/src/sfcs_agent/rest_agent/prompts/takeaway_agent_prompt.md)
- [BNAT takeaway prompt](../apps/bnat/src/bnat_agent/rest_agent/prompts/takeaway_agent_prompt.md)

## Ownership and Composition

- The shared runtime owns `build_takeaway_agent`, its five ordered default
  tools, shared state/context, middleware, graph routing, checkpointing, repair,
  debug behavior, and common WhatsApp menu helpers.
- Each app owns a complete `takeaway_agent_prompt.md` loaded through
  `rest_agent/agent_recipe.py`.
- `RestaurantGraphAdapter` injects the app runtime's model and takeaway prompt
  into the standard builder.
- The exact app-bound async WhatsApp client reaches the takeaway menu tool
  through `ContextSchema`.

## Detailed Flow Explanation

1. Selecting Collection/Takeaway is handled deterministically by
   `select_service_handler()`. It calls the runtime-owned availability policy;
   a normal recipient who is unavailable receives `Ordering is currently closed.`, while
   an approved or Overwatch recipient proceeds without an LLM availability
   check.
2. An approved callback persists `active_agent="takeaway_agent"` and the
   selection without invoking the model, then sends the collection menu through
   the exact runtime-bound WhatsApp client.
3. Typed explicit collection intent, collection callbacks, and transfer tools
   use the same shared selection policy. A retained delivery or takeaway flow
   preserves its current specialist; an open flow starts the selected service.
   Informational, status, cancellation, and negated messages remain model-owned.
4. `send_takeaway_menu_tool()` uses the same final availability guard for an
   already-active conversation. It sends either the menu, the exact closed message,
   or the concise retry-later fallback; it never asks the customer for the date
   or time.
5. `verify_if_payment_complete()` reads order summary, payment-link, and payment
   state to tell the model whether payment is complete, pending, or not yet
   ready.
6. `payment_complete()` validates the route, recipient, and thread. For
   collection it acknowledges the order, activates `takeaway_agent`, records
   order/payment state, and retains the thread while pickup time is pending.
7. `takeaway_pickup_time_updated()` schedules a runtime-bound two-step sequence:
   notify through `takeaway_agent`, then activate triage and call
   `terminate_conversation`.
8. `takeaway_ready()` sends a direct runtime-bound WhatsApp notification when
   the order is ready for collection.
9. `transfer_to_delivery` and `transfer_to_triage` are model adapters to that
   same selection/lifecycle policy. Retained takeaway work blocks handoff; on
   every model call during that state, the shared dynamic prompt states that
   takeaway flow is in motion and handover is strictly prohibited.

## Ordered Default Tools

1. `verify_if_payment_complete`
2. `update_customer`
3. `send_takeaway_menu_tool`
4. `transfer_to_delivery`
5. `transfer_to_triage`

The ordered list is part of the shared graph contract and is asserted in
`tests/rest_agent/test_graph_contract.py`.

## Takeaway Customization

### Prompt-only behavior

Edit the owning app's complete takeaway prompt. Restaurant wording, collection
policy, and tool-use instructions stay app-owned.

### Additional takeaway tool

Bind a native app-owned tool through:

```python
extra_tools_by_agent={"takeaway_agent": [custom_takeaway_tool]}
```

### Complete takeaway-agent replacement

Bind an app-owned native runnable through:

```python
agent_overrides={"takeaway_agent": CUSTOM_TAKEAWAY_AGENT}
```

The replacement must expose `ainvoke` and preserve the fixed node name, shared
state/context, and handoff behavior.

### Incompatible takeaway graph

An app owns a complete `GraphAdapter` when takeaway needs a new node,
incompatible state/routing, or different checkpointing, compilation, repair, or
debug semantics.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/takeaway.py
symbol: build_takeaway_agent
feature: takeaway-whatsapp-agent
description: >
  Constructs the takeaway LangChain agent from an injected model, complete app-owned prompt, shared schemas, middleware, default tools, and optional extra tools.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/takeaway.py
symbol: verify_if_payment_complete
feature: takeaway-whatsapp-agent
description: >
  Interprets order-summary, payment-link, and payment-success state for the takeaway conversation.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py
symbol: send_takeaway_menu_tool
feature: takeaway-whatsapp-agent
description: >
  Sends a restaurant-specific collection menu through the exact runtime WhatsApp client and ends the turn.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py
symbol: transfer_to_delivery
feature: takeaway-whatsapp-agent
description: >
  Applies transfer guards, sets delivery_agent active, and returns a parent-graph handoff command.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py
symbol: select_service_handler
feature: takeaway-whatsapp-agent
description: >
  Validates service-selection callback data and invokes the app's graph adapter with the selected active agent.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: takeaway-whatsapp-agent
description: >
  Validates collection payment events, updates takeaway graph state, and schedules runtime-bound graph work.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: takeaway_pickup_time_updated
feature: takeaway-whatsapp-agent
description: >
  Schedules pickup-time notification through takeaway followed by conversation termination through triage.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: takeaway_ready
feature: takeaway-whatsapp-agent
description: >
  Sends a direct collection-ready notification with the running app's exact WhatsApp client.
```

## Edge Cases

- Menu-send failure sends fallback text and ends the graph turn.
- Payment checks before an order or payment link return the corresponding
  not-ready state.
- Recipient or thread mismatch in payment events returns `400`.
- Cross-restaurant routes return `404` before graph work or external effects.
- `retain_thread=True` keeps takeaway ownership while pickup time is pending.
  Authoritative customer updates remain in scope; all service-selection paths
  preserve the specialist until a lifecycle event explicitly releases it.
- Pickup-time completion intentionally returns to triage for the standard
  termination tool.
- Invalid callback data is logged and does not advance the graph.
