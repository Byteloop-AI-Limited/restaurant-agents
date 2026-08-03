# Feature: Webhook Endpoints

Each Restaurant Application exposes the same shared FastAPI surface backed by
its exact `RestaurantRuntime` and app-owned graph adapter. Restaurant-prefixed
routes validate the path against the running `RestaurantIdentity` and return
`404` before database, graph, or WhatsApp side effects on a mismatch.

## Human-Friendly Code Map

- [Application factory and WhatsApp registration](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py)
- [Order events](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py)
- [Rider events](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/rider_event_hooks.py)
- [Thread lifecycle and operations](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/thread_hooks.py)
- [WhatsApp message handlers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py)
- [WhatsApp callback handlers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py)

## Application Bootstrap

`create_restaurant_app` loads one settings bundle, constructs one async and one
sync WhatsApp client, builds one `RestaurantRuntime`, and stores the runtime and
graph adapter on `app.state`. It conditionally includes these router groups:

- `/order-event-hooks`
- `/rider-event-hooks`
- `/thread-hooks`

The top-level operational endpoints are `GET /healthz`, `GET /identity`,
`GET /details`, `GET /internal/activity`, and `POST /internal/cache/reset`.
The reset endpoint clears only the current process's runtime-owned operational
lookup cache; its documented unauthenticated internal convention and scopes are
defined in [Operational Lookup Cache](caching_system.md). The inactive
offline-mode module is not mounted, and there is no direct shared Stripe router.

## Operational Cache Reset

`POST /internal/cache/reset` accepts `scope=all` (default),
`operational_config`, `restaurant_master`, or `overwatch`. Use `app_ref` only
with `scope=operational_config` to clear one URL entry. For full request and
response examples, see [Operational Lookup Cache](caching_system.md#calls).

## WhatsApp Handler Surface

Message handlers are registered on the runtime's exact async WhatsApp client in
this order:

1. Out-of-hours guard.
2. `/reset`, which marks the customer's persistent Threads inactive using the
   runtime database pool.
3. Shared-location handling with runtime maps settings.
4. `/paid3100`, which posts a payment-complete simulation for the sender's
   latest eligible order using exact runtime dependencies.
5. `/debug`, which is read-only and ignores callers outside the runtime Overwatch allowlist.
6. Default graph handler.

ADR-0012 restores `/paid3100`; `/test` and `/test-t` remain removed.

Callback registration covers delivery-address confirmation, collection-ready,
Restaurant-order confirmation, service selection, and marketing consent.

## Order Event Routes

- `POST /{rest_ref}/payment-complete/{recipient}/{thread_id}` validates a
  `FoodOrder`, sends the customer receipt, and queues a delivery or takeaway
  graph update.
- `POST /{rest_ref}/address-update/{recipient}` acknowledges externally
  persisted customer data and queues address reconfirmation.
- `POST /{rest_ref}/takeaway-ready/{order_id}` sends a direct collection-ready
  notification.
- `POST /{rest_ref}/takeaway-pickup-time-updated` queues pickup-time
  notification followed by conversation termination.

Payment completion enters the runtime through this order-event contract. The
external payment system remains authoritative.

## Rider Event Routes

- `POST /{rest_ref}/rider-inflight`
- `POST /{rest_ref}/on-restaurant-cc/{order_number}/{customer_id}`
- `POST /{rest_ref}/on-customer-cc/{order_number}/{customer_id}`
- `POST /{rest_ref}/on-restaurant-enter/{order_number}`
- `POST /{rest_ref}/on-customer-enter/{order_number}`
- `POST /{rest_ref}/delivery-timedout`

These routes translate external fulfilment reports into customer messages and
graph-state projections. Delivery timeout also invokes the runtime-bound
payment-cancellation flow.

## Thread Routes

- `POST /{rest_ref}/terminate-stale-active-threads` accepts a batch already
  selected by the scheduled database job, validates Thread prefixes, returns
  `202`, and processes at most three graph runs concurrently.
- `GET /get-active-thread/{rest_ref}/{recipient}` reads the persistent active
  Thread for the selected Restaurant.
- `GET /debug-state-values`, `/debug-state`, `/debug-thread`,
  `/debug-admin-state`, and `/debug-state-by-thread` expose graph inspection
  operations.
- `POST /hil-system-message` performs an operator-requested graph intervention
  and resolves a missing recipient through the exact runtime database client.

## Activity Endpoint

`GET /internal/activity` reports one busy/idle signal for external machine
lifecycle automation:

```json
{
  "active_requests": 0,
  "active_jobs": 0,
  "active_agent_runs": 0,
  "idle_seconds": 320.4,
  "draining": false,
  "safe_to_stop": true,
  "idle_threshold_seconds": 60.0
}
```

A single webhook may increment both request and job counters; consumers must
require every counter to be zero rather than sum them. Health and activity
polling do not reset idle time. `safe_to_stop` also requires the configured
idle threshold, and the external scheduler should require two consecutive safe
responses before stopping a Machine.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py
symbol: create_restaurant_app
feature: webhook-endpoints
description: >
  Constructs one runtime-bound FastAPI application and registers its routers and WhatsApp handlers.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: webhook-endpoints
description: >
  Validates and processes the external FoodOrder payment-complete event.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/thread_hooks.py
symbol: terminate_stale_active_threads
feature: webhook-endpoints
description: >
  Queues database-selected stale Threads for bounded graph termination.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py
symbol: simulate_payment_complete
feature: webhook-endpoints
description: >
  Implements the runtime-bound side-effecting `/paid3100` payment simulation.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py
symbol: reset_thread
feature: webhook-endpoints
description: >
  Resets customer Thread lifecycle through the exact runtime database pool.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py
symbol: handle_debug_state
feature: webhook-endpoints
description: >
  Provides the authorized read-only WhatsApp debug command.
```

## Failure Boundaries

- Cross-Restaurant route prefixes return `404` before side effects.
- Payment-complete URL/body recipient or Thread mismatches return `400`.
- A stale-thread candidate with the wrong Restaurant prefix rejects the batch.
- Background-task acknowledgement means work was queued, not completed; use
  activity reporting and application logs for completion evidence.
- `/paid3100` is side-effecting and may advance the sender's external
  payment/order workflow; the offline test gate never invokes it live.
