# Feature: Payment Integration

Payment is an external authoritative context under ADR-0006. The shared
runtime receives payment-complete order events and can request cancellation of
an authorized delivery payment; it does not own Stripe state, calculate order
prices, create payment intents, or capture funds.

## Human-Friendly Code Map

- [Runtime-bound payment helper](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/payment_ms/payment.py)
- [Order event router](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py)
- [FoodOrder boundary model](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_pymodel.py)
- [Receipt formatter](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_reciept.py)
- [Delivery cancellation caller](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py)
- [`/paid3100` simulator](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py)

## Payment-Complete Flow

1. The external ordering/payment context persists the authoritative order and
   calls
   `POST /order-event-hooks/{rest_ref}/payment-complete/{recipient}/{thread_id}`
   with a `FoodOrder` body.
2. The route rejects a cross-Restaurant path or URL/body identity mismatch
   before side effects.
3. It generates a receipt using the selected runtime's database client and
   sends it through the same runtime WhatsApp client.
4. It updates graph state with the successful payment, order identifiers, and
   retained-thread state so delivery or takeaway fulfilment can proceed.

The former direct Stripe webhook file was commented out and unregistered; it
has been deleted. Payment completion enters the shared runtime only through the
active order-event contract.

## `/paid3100` Simulation Flow

The standard WhatsApp handler exposes `/paid3100` under ADR-0012. It resolves
the Ordelo base URL and the sender's latest order through the exact runtime
database client. If the order is in `requires_payment`, it posts the established
Stripe-shaped completion payload to Ordelo's `/payment-hooks/payment-complete`
endpoint without following redirects. It does not accept an arbitrary order ID.

## Cancellation Flow

When delivery times out, the delivery agent calls `cancel_payment` with the
current order ID, Thread ID, and `ContextSchema.payment_settings`. The helper:

1. Builds the configured payment-service URI.
2. Posts `{"action": "delivery", "payment_mode": "cancel"}` with the
   injected payment headers.
3. Returns `True` only for a successful empty response; HTTP failures are
   logged and return `False`.

Neither the helper nor its module captures settings or clients globally.
Payment intent generation and capture helpers were deleted because no active
shared-runtime caller used them. A future capture/create capability must start
from an external contract and receive its dependencies explicitly.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py
symbol: simulate_payment_complete
feature: payment-integration
description: >
  Invokes the external payment-complete hook for the sender's latest eligible order.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/payment_ms/payment.py
symbol: get_payment_uri
feature: payment-integration
description: >
  Builds the external payment URI from explicitly supplied runtime payment settings.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/payment_ms/payment.py
symbol: cancel_payment
feature: payment-integration
description: >
  Requests cancellation of an authorized delivery payment with injected settings.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: payment-integration
description: >
  Receives the active external payment-complete FoodOrder event and updates the graph.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py
symbol: ContextSchema
feature: payment-integration
description: >
  Carries the exact runtime payment settings into the delivery agent.
```

## Failure Boundaries

- Cross-Restaurant or mismatched payment-complete requests fail before writes
  or outbound messages.
- Missing order items fail receipt construction rather than fabricating order
  contents.
- Cancellation HTTP errors return `False`; the external payment system remains
  authoritative and may require operational reconciliation.
- `/paid3100` intentionally calls the external payment-complete hook for the
  sender's latest order in `requires_payment`; it is a side-effecting
  operational simulation, not a read-only diagnostic.
