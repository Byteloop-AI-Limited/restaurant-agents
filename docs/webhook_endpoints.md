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
- [Reservation events (optional, dine-in apps only)](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/reservation_hooks.py)
- [WhatsApp message handlers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py)
- [WhatsApp callback handlers](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py)

## Application Bootstrap

`create_restaurant_app` loads one settings bundle, constructs one async and one
sync WhatsApp client, builds one `RestaurantRuntime`, and stores the runtime and
graph adapter on `app.state`. It conditionally includes these router groups:

- `/order-event-hooks`
- `/rider-event-hooks`
- `/thread-hooks`
- `/reservation-hooks` — `include_reservation_router=True`, opt-in and off by
  default; only an app that supplies `RestaurantPrompts.dinein` mounts this
  (ADR-0021). ELAS is the first and currently only app that does.

The top-level operational endpoints are `GET /healthz`, `GET /identity`,
`GET /details`, `GET /internal/activity`, and `POST /internal/cache/reset`.
`/details` includes the effective cached `ORDELO_APP_URL`, `BNAT_APP_URL`,
`SFCS_APP_URL`, and `ELAS_APP_URL` values under `ordelo_services`; unavailable
keys are null with sanitized entries in `details_errors.ordelo_services`.
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

1. `/detail`, an Overwatch-only read-only command that sends the same
   sanitized JSON object as `GET /details`.
2. `/reset-cache`, an Overwatch-only project reset that fresh-reads the BNAT,
   SFCS, and ELAS application URLs and requests `scope=all` cache reset from
   each one. It reports per-app results; see [Operational Lookup Cache](caching_system.md#overwatch-project-reset).
3. `/reset`, an Overwatch-only operational escape hatch that marks the
   sender's persistent Threads inactive using the runtime database pool.
   Regular customers receive a fixed denial.
4. Out-of-hours guard.
5. Shared-location handling with runtime maps settings.
6. `/paid3100`, which posts a payment-complete simulation for the sender's
   latest eligible order using exact runtime dependencies.
7. `/debug`, which is read-only, ignores callers outside the runtime Overwatch
   allowlist, and appends the four effective cached application URLs to graph-state output.
8. Default graph handler.

`/detail`, `/reset-cache`, `/reset`, and `/debug` are exact, case-insensitive
commands; text such as `/reset-cache-now` does not invoke an operational command.

ADR-0012 restores `/paid3100`; `/test` and `/test-t` remain removed.

Callback registration covers delivery-address confirmation, collection-ready,
Restaurant-order confirmation, service selection, enquiry selection, and
marketing consent. `/SelectRestaurant` is registered only when the app
configures `RestaurantPresentation.restaurant_selection` (ADR-0020); it is
absent for SFCS and BNAT. `/SelectEnquiry` registers **both** a
`CallbackButtonHandler` and a `CallbackSelectionHandler` (ADR-0023): the
enquiry menu renders as a WhatsApp SectionList, whose row taps arrive as a
`CallbackSelection` update, not `CallbackButton` — the button handler is
kept only so menus already delivered to a live chat before a release still
work.

## Callback Button and List-Row Title Length

Every WhatsApp interactive **button** title Meta accepts is capped at **20
characters**; a **SectionList row** title is capped at **24**, its optional
description at **72**, and its `callback_data` at **200** (looser than a
button's 256). A longer value is rejected by the WhatsApp API at send time —
or, for `callback_data`, pywa does not validate the length client-side at
all, so an over-length payload fails silently at Meta only for the customer
who taps that specific row. This applies to every app-owned title/label
surface in the shared runtime:

- `RestaurantPresentation.delivery_button_label` /
  `.takeaway_button_label` / `.enquiry_button_label` — the three
  service-selection buttons ("How can I help you today?").
- `RestaurantChoice.delivery_button_label` / `.takeaway_button_label` — a
  per-brand override of the first two for a multi-restaurant app (ADR-0020);
  `None` (the default) falls back to `RestaurantPresentation`'s value.
  `enquiry_button_label` has no per-brand override.
- `RestaurantChoice.title` — the restaurant-selection buttons (Elai / Wings
  and Things).
- `EnquiryMenu.button_title` — the SectionList opener button and its single
  `Section`'s title (both ≤20).
- `EnquiryOption.title` / `.description` — one SectionList row (≤24 / ≤72).
- `EnquiryOption.human_message` — capped at **100** characters, well inside
  the 200-char `callback_data` budget (the `/SelectEnquiry` JSON envelope
  measures 90 chars with a 4-char `rest_ref`). This is the cap that actually
  protects `callback_data`, since pywa does not.

All of the above are validated in `__post_init__` at config-construction
time (`RestaurantPresentation`, `RestaurantChoice`, `EnquiryOption`,
`EnquiryMenu` in `runtime.py`), so a too-long value fails app startup with a
`ValueError` rather than failing silently or erroring only when a customer
happens to trigger that specific button or row. When embedding a discount in
a button label (for example `"Delivery (20% off)"`), count the full
rendered string, including the percentage and parentheses —
`"Collection (15% off)"` is exactly 20 characters, the maximum that still
fits a button.

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
- `POST /{rest_ref}/wa-location-response`

These routes translate external fulfilment reports into customer messages and
graph-state projections. Delivery timeout also invokes the runtime-bound
payment-cancellation flow, then releases the retained delivery projection to
triage and clears order-scoped runtime state. It intentionally leaves the
Thread active so a subsequent new-service request can be handled normally.

`wa-location-response` is Ordelo's open, unsigned callback for the WaLocation
client integration (`docs/wa_location_restaurant_agents_integration.md` in
OrdeloAgent). It is invoked out-of-band from a customer's `request_rider_location`
tool call, not from a background task queued by another route. It looks up the
customer's active Thread without creating one, revalidates retained/picked-up/
matching-order state, and sends a WhatsApp location pin through this app's
injected client only after every check passes — returning `409` on any guard
failure and `502` if the WhatsApp send itself fails, so Ordelo can tell a
rejected request apart from an accepted one it failed to deliver.

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

## Reservation Routes (Optional, Dine-in Apps Only)

Mounted only when `include_reservation_router=True` (ADR-0021):

- `POST /{rest_ref}/reservation-form-submitted` sends the initial reservation
  acknowledgement once the external reservation service records a booking.
- `GET /{rest_ref}/reservation-confirmed/{reservation_id}` and
  `GET /{rest_ref}/reservation-declined/{reservation_id}` send the
  corresponding customer notification. Both validate the reservation ID's
  `rest_ref` prefix against the URL's `rest_ref` before sending.

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
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/rider_event_hooks.py
symbol: wa_location_response
feature: webhook-endpoints
description: >
  Open Ordelo-to-service WaLocation callback; revalidates retained/picked-up/matching-order state before sending a WhatsApp location pin.
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

## Manual Retained-Flow Verification

Run this only against the test application/WABA with an Overwatch test recipient.
Do not point a production WhatsApp webhook at a local server or invoke
`/paid3100` against a production order.

1. Start a delivery or takeaway order and complete its test payment. Confirm
   `/debug` reports the relevant specialist as `active_agent` and
   `retain_thread: True`.
2. While it is retained, send an explicit request for the other service both as
   text (for example, `I want takeaway`) and with the service button. Confirm
   the conversation remains with the current specialist and no other-service
   menu is sent.
3. For delivery, invoke the test rider timeout endpoint:

   ```text
   POST /rider-event-hooks/{rest_ref}/delivery-timedout
   {"customer_id":"<test-recipient>"}
   ```

   Wait for the queued customer update, then use `/debug`. The expected
   projection is `active_agent: triage_agent`, `retain_thread: False`, payment
   false, and cleared order/rider/reply fields; the Thread remains active.
4. Send the same explicit service request again. Confirm the selected new-order
   flow starts (the takeaway menu is sent directly; delivery begins its address
   flow), proving the old specialist owner was cleared.
5. Send `/reset` as the normal test customer and confirm it returns the fixed
   denial. Repeat only with an Overwatch recipient and confirm a new Thread
   lifecycle is started.

For the policy and exact state boundary, see
[ADR-0018](adr/0018-retained-specialist-lifecycle-and-service-selection.md).
