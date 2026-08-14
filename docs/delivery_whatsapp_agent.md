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
- [Retained-specialist lifecycle projection](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/specialist_lifecycle.py)
- [Shared service-selection policy](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/service_selection.py)
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
4. `route_initial()` follows the persisted `active_agent`. Delivery selection
   and `transfer_to_delivery` first use the runtime-owned availability policy.
   A closed normal recipient receives `Ordering is currently closed.` without a model
   turn; an approved recipient enters `delivery_agent` with availability already
   final.
5. `build_delivery_agent()` creates the native LangChain agent with the
   app-owned complete prompt, shared state/context schemas, common WhatsApp
   middleware, thirteen ordered default tools, and any app-owned extra tools.
6. Address tools capture, update, and confirm customer location. The minimum
   order tool and delivery menu tool retain the final deterministic availability
   guard before sending a restaurant-specific menu link; the model never asks
   the customer for a date or time to decide availability.
7. Payment, order, and rider tools read and update shared graph state and use
   injected runtime resources rather than application imports or module-global
   WhatsApp clients.
8. Order and rider routers validate `rest_ref` against the running app before
   scheduling graph work. Payment completion activates `delivery_agent`, records
   a paid, received, rider-pending delivery projection, and retains the thread
   while driver assignment is pending. A replay for that retained order is
   suppressed before a second receipt or customer update is sent.
9. Typed explicit service requests, service callbacks, and delivery transfer
   tools use the same shared selection policy. While retained delivery work is
   active, a new service or paid-order change receives the deterministic
   completion-first reply rather than a restaurant-contact fallback. Once a
   terminal event releases the flow, the same request starts the selected
   new-order path. Informational support, including status and hours, remains
   available.
10. `transfer_to_triage` handles genuinely out-of-scope intent only when the
    lifecycle permits it. On every model call during retained delivery work, the
    shared dynamic prompt injects a system message that delivery flow is in
    motion and handover is strictly prohibited.
11. `cleanup_before_model` and `respond_on_wa` coordinate tool-only turns,
   `/DoNotRespond:` markers, and outbound WhatsApp responses.
12. A no-rider webhook releases delivery only when its order matches the active
   retained unassigned delivery. Delayed, replayed, assigned, picked-up, or
   mismatched timeout events are logged and ignored.
   The upstream timeout webhook includes `payment_cancelled` only after the
   payment-cancellation call succeeds. The runtime stores that result as
   `is_payment_cancelled`, plus `is_delivery_no_rider`; refund-timing questions
   are answered deterministically and can confirm a refund only when the former
   flag is literally `True`.
13. A customer rider-location request (`request_rider_location`) is routed by
   the model, the same as any other tool choice: the delivery prompt and the
   `answer_general_query` steering branch point rider-location phrasing at it,
   and the tool itself decides the reply. It calls Ordelo's
   `POST /wa-request-location` only once `order_number` is set and
   `is_delivery_picked_up` is `True`; before pickup it replies with a fixed
   placeholder and makes no Ordelo call. Ordelo asynchronously posts the result
   to `POST /rider-event-hooks/{rest_ref}/wa-location-response`, which
   revalidates the retained, picked-up, matching-order state before sending a
   WhatsApp location pin with this app's injected client. See
   `docs/wa_location_restaurant_agents_integration.md` in OrdeloAgent for the
   full cross-repo contract. The legacy `send_rider_live_location_link` tool
   (a link, not a pin) stays registered but is no longer prompted for.
14. `update_customer` refuses to fire unless the current turn was opened by a
   fresh runtime `SystemMessage` (`_last_turn_started_by_system_message`): a
   customer's own message must never trigger it, and it must never reuse an
   earlier turn's already-consumed system instruction. This exists because
   production testing found the model reusing a stale `update_customer`
   instruction — still visible in conversation history — to answer an
   unrelated rider-location question with a fabricated-looking but actually
   copy-pasted status update. The guard is structural rather than
   phrase-matched, so it protects every kind of customer question that could
   trigger this misuse, not only rider-location ones, and it leaves the model
   fully in charge of recognising intent and choosing the right tool.
15. `check_delivery_driver_allocation_status` refuses once
   `is_delivery_picked_up` is `True` and redirects the model to
   `request_rider_location` instead of calling Ordelo. Its
   `/delivery-hooks/check-rider-allocation-status/{order_number}` endpoint only
   ever reports `unassigned`/`assigned`/`timedout` — it has no picked-up state
   — so after pickup it would otherwise always answer with stale "a driver has
   been assigned" copy no matter how the model got there, since an
   arrival-time-shaped question ("where is my food now?") and an explicit
   location request both route to it pre-pickup. The guard fixes the
   staleness at its source rather than trying to fully disambiguate every
   phrasing.

## Ordered Default Tools

1. `send_welcome_msg`
2. `answer_general_query`
3. `confirm_delivery_address`
4. `capture_delivery_address`
5. `update_address_of_existing_user`
6. `calculate_min_order_value`
7. `send_restaurant_menu_tool`
8. `verify_if_payment_complete`
9. `update_customer`
10. `check_delivery_driver_allocation_status`
11. `send_rider_live_location_link`
12. `request_rider_location`
13. `transfer_to_takeaway`
14. `transfer_to_triage`

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
- `retain_thread=True` keeps delivery ownership with the specialist. Callback
  and typed service-selection requests preserve that ownership until a terminal
  lifecycle event releases it. Authoritative customer updates remain in scope.
- A menu-send `ValueError` sends fallback text and ends the turn.
- Malformed persisted tool-call tails are repaired before model invocation; an
  unrecoverable mismatch terminates the session.
