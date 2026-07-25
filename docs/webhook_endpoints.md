---
# Feature: Webhook Endpoints
The Elai system exposes a set of FastAPI routers that receive external webhook events and internal operational requests. These endpoints bridge WhatsApp interactions, payment providers, delivery services (Ordelo), and thread lifecycle management into the LangGraph agent. Each router group validates its `rest_ref` path parameter against the cached RestaurantMaster, delegates long-running work to FastAPI `BackgroundTasks`, and returns lightweight JSON acknowledgments.

---

## Human-Friendly Code Map
- [Main FastAPI application and handler registration](./watomation/fapp.py)
- [Rider event webhook router](./watomation/routers/rider_event_hooks.py)
- [Order event webhook router](./watomation/routers/order_event_hooks.py)
- [Thread lifecycle hooks router](./watomation/routers/thread_hooks.py)
- [Stripe payment webhook router](./watomation/routers/payment_hooks_tbd.py)
- [Offline mode sub-application](./watomation/routers/offline_mode.py)
- [Agent graph runner](./rest_agent/agent_runner.py)

### Detailed Flow Explanation

**1. Application Bootstrap and Router Registration**
1. `fapp.py` creates the main `FastAPI` app titled `ELAS-ElaiSalisbury`.
2. Three routers are included with URL prefixes: `/rider-event-hooks`, `/order-event-hooks`, `/thread-hooks`. The payment hooks router (`payment_hooks_tbd`) is defined but currently commented out of registration.
3. The offline mode sub-application is mounted at `/offline-mode`.
4. A `WhatsApp` client (`pywa_async`) is initialized and message/callback/flow handlers are registered directly on it.
5. Top-level diagnostic endpoints are defined: `GET /details`, `POST /restaurant-base-url-cache/reset`, `POST /restaurant-master-cache/reset`.

**2. WhatsApp Message Handlers (registered on the WA client, not as routers)**
1. Handlers are evaluated in registration order; the first matching filter wins (`continue_handling=False`).
2. `OUT_OF_HOURS_FILTER` -> `send_closed_message` (rejects messages outside service hours).
3. `ALLOWED_USERS_FILTER` -> `send_redirect_to_offline_mode` (redirects non-allowed users).
4. `WHEN_RESET` -> `reset_thread` (clears thread state on keyword trigger).
5. `filters.location` -> `handle_request_location_response` (processes shared locations).
6. `WHEN_ADHOC_TEST_TAKEAWAY` -> `handle_adhoc_test_takeaway` (takeaway test trigger).
7. `WHEN_ADHOC_TEST` -> `handle_adhoc_test` (delivery test trigger).
8. `WHEN_PAYMENT_COMPLETE` -> `simulate_payment_complete` (simulates payment for testing).
9. Default catch-all -> `handle_wa_msg_in_graph` (routes all other messages into the LangGraph agent).

**3. Callback Button Handlers**
1. `/ConfirmDeliveryAddress` -> `delivery_address_confirmation` (address confirmation buttons).
2. `/AdminCollectionReady` -> `admin_collection_ready` (admin marks takeaway ready for collection).
3. `/RestaurantOrder` -> `restaurant_order_confirmation_handler` (restaurant confirms order).
4. `/SelectService` -> `select_service_handler` (service selection and agent handoff).

**4. Rider Event Hooks (`/rider-event-hooks`)**
1. `POST /{rest_ref}/rider-inflight` - Rider accepts delivery. Parses `DeliverySummary` from body, extracts confirmation code, runs `run_elai_graph_with_custom_msg` as background task to notify customer and set `is_delivery_rider_assigned=True`.
2. `POST /{rest_ref}/on-restaurant-cc/{order_number}/{customer_id}` - Food picked up from restaurant. Sets `is_delivery_picked_up=True` and provides `rider_live_location_url` via background task.
3. `POST /{rest_ref}/on-customer-cc/{order_number}/{customer_id}` - Delivery confirmed to customer. Runs a two-step background sequence: first sends a delivery success message via `send_updates_to_customer`, then after a 5-second delay terminates the conversation via `terminate_conversation`.
4. `POST /{rest_ref}/on-restaurant-enter/{order_number}` - Rider enters restaurant zone. Notifies customer via background task. Reads `customer_id` from request body `delivery_summary`.
5. `POST /{rest_ref}/on-customer-enter/{order_number}` - Rider near customer. Sends confirmation code reminder via background task. Reads `customer_id` and `cust_confirmation_code` from request body.
6. `POST /{rest_ref}/delivery-timedout` - No driver available. Notifies customer that no drivers are available and suggests takeaway as an alternative; payment will be refunded. Does not terminate the conversation. Reads `customer_id` from request body.

**5. Order Event Hooks (`/order-event-hooks`)**
1. `POST /{rest_ref}/payment-complete/{recipient}/{thread_id}` - Payment succeeded. Validates `recipient` and `thread_id` match between URL and `FoodOrder` body. Generates WhatsApp receipt via `build_wa_order_reciept_for_cust`. For delivery: sends receipt, updates graph with `is_payment_successful=True`, `retain_thread=True`, and order IDs. For takeaway: sends receipt with pickup time notice, updates graph similarly.
2. `POST /{rest_ref}/address-update/{recipient}` - Address changed. Sends acknowledgment, resets `is_delivery_address_confirmed=False` and `min_order_value=None`, re-invokes address confirmation via background task.
3. `POST /{rest_ref}/takeaway-pickup-time-updated` - Restaurant confirms pickup time. Accepts `TakeawayPickupTimePayload`, runs a two-step background sequence: first notifies the customer of the confirmed pickup time via the takeaway agent, then after a 5-second delay terminates the conversation via the triage agent.

**6. Thread Lifecycle Hooks (`/thread-hooks`)**
1. `POST /{rest_ref}/terminate-stale-active-threads` - Accepts `{job_run_id, threads: [{thread_id, recipient}]}` directly from the five-minute PostgreSQL job. The job has already applied the restaurant timeout and latest-checkpoint `retain_thread` policy. The endpoint validates the local restaurant and thread prefixes, acknowledges with HTTP 202, and invokes the graph without an additional preflight database read, with concurrency limited to three.
2. `GET /get-active-thread/{rest_ref}/{recipient}` - Returns active thread ID for a recipient, or `-1` if none.
3. `GET /debug-state-values` - Returns graph state values for a recipient (default: test phone number).
4. `GET /debug-state` - Returns full graph state for a recipient.
5. `GET /debug-thread` - Returns graph state by thread ID.
6. `GET /debug-admin-state` - Returns admin-scoped graph state (same as debug-state currently).
7. `GET /debug-state-by-thread` - Returns graph state by thread ID (query parameter variant).
8. `POST /hil-system-message` - Human-in-the-loop intervention. Accepts `HILMessageRequest` with `thread_id`, `update_message`, optional `recipient`, and optional `state_update_dict`. If recipient is missing, looks up active thread in Supabase. Invokes `send_updates_to_customer` tool via the graph and returns the AI response.

**7. Payment Hooks (`/payment-hooks` - currently not registered)**
1. `POST /payment-complete` - Stripe webhook for payment completion. Extracts `orderID` from Stripe event metadata. Updates `food_order.payment_status` to `requires_capture` in Supabase. Invokes graph to verify payment via `run_elai_graph_with_custom_msg` as background task.

**8. Offline Mode (`/offline-mode` - mounted sub-app)**
1. Separate `FastAPI` app with its own `WhatsApp` client instance.
2. All incoming messages receive automatic offline reply: "Apologies, we are currently offline."
3. `POST /offline-mode/set` - Toggles offline mode by updating WABA callback URL to append or remove `/offline-mode` suffix.
4. `GET /offline-mode/details` - Returns current WhatsApp business configuration for the offline instance.

**9. Top-Level Diagnostic Endpoints**
1. `GET /details` - Returns WhatsApp business phone config, restaurant reference, admin list, service hours, LLM model, and stale thread timeout.
2. `POST /restaurant-base-url-cache/reset` - Clears cached restaurant base URLs. Accepts optional `rest_ref` query param to target a single restaurant.
3. `POST /restaurant-master-cache/reset` - Clears cached RestaurantMaster instances. Accepts optional `rest_ref` query param.

### Code References (Machine-Readable)

file: watomation/fapp.py
symbol: app
feature: Webhook Endpoints
description: >
  Main FastAPI application that includes all routers, mounts offline mode, initializes WhatsApp client, and registers message/callback handlers.

file: watomation/on_callback_handler.py
symbol: select_service_handler
feature: Webhook Endpoints
description: >
  Handles /SelectService callbacks, routes to delivery/takeaway/triage based on active_agent, and sends service selection buttons when rest_ref is present but no agent is selected.

file: watomation/fapp.py
symbol: get_details
feature: Webhook Endpoints
description: >
  Returns WhatsApp business configuration including phone ID, display number, callback URL, restaurant reference, admin list, service hours, and LLM model.

file: watomation/fapp.py
symbol: reset_restaurant_base_url_cache_endpoint
feature: Webhook Endpoints
description: >
  Clears the in-memory restaurant base URL cache, optionally scoped to a single rest_ref.

file: watomation/fapp.py
symbol: reset_restaurant_master_cache_endpoint
feature: Webhook Endpoints
description: >
  Clears the in-memory RestaurantMaster cache, optionally scoped to a single rest_ref.

file: watomation/routers/rider_event_hooks.py
symbol: validate_rest_ref
feature: Webhook Endpoints
description: >
  Validates a rest_ref path parameter against the cached RestaurantMaster, returning the normalized uppercase value or raising HTTP 404.

file: watomation/routers/rider_event_hooks.py
symbol: rider_inflight
feature: Webhook Endpoints
description: >
  Handles rider assignment webhook, parsing DeliverySummary from the body and notifying the customer of the confirmation code via background graph invocation.

file: watomation/routers/rider_event_hooks.py
symbol: rider_restaurant_cc_path
feature: Webhook Endpoints
description: >
  Handles food pickup confirmation, setting is_delivery_picked_up and providing rider_live_location_url to the customer via background task.

file: watomation/routers/rider_event_hooks.py
symbol: rider_customer_cc_path
feature: Webhook Endpoints
description: >
  Handles delivery completion by running a two-step background sequence: first sends a delivery success message, then terminates the conversation after a 5-second delay.

file: watomation/routers/rider_event_hooks.py
symbol: rider_restaurant_enter
feature: Webhook Endpoints
description: >
  Notifies the customer when the rider enters the restaurant zone via background task.

file: watomation/routers/rider_event_hooks.py
symbol: rider_customer_enter
feature: Webhook Endpoints
description: >
  Notifies the customer when the rider is nearby and reminds them of the 2-digit confirmation code via background task.

file: watomation/routers/rider_event_hooks.py
symbol: delivery_timedout_path
feature: Webhook Endpoints
description: >
  Handles delivery timeout by notifying the customer that no drivers are available, suggesting takeaway as an alternative, and noting that payment will be refunded.

file: watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: Webhook Endpoints
description: >
  Processes payment completion webhook, validates path/body consistency, sends WhatsApp receipt, and updates graph state with payment and order details.

file: watomation/routers/order_event_hooks.py
symbol: address_update
feature: Webhook Endpoints
description: >
  Handles address update notification, resets delivery address confirmation and min order value, and triggers address re-confirmation via graph.

file: watomation/routers/order_event_hooks.py
symbol: takeaway_pickup_time_updated
feature: Webhook Endpoints
description: >
  Processes confirmed takeaway pickup time from the restaurant and runs a two-step background sequence: first notifies the customer of the pickup time, then terminates the conversation after a 5-second delay.

file: watomation/routers/thread_hooks.py
symbol: terminate_stale_active_threads
feature: Webhook Endpoints
description: >
  Accepts the reduced database-selected thread_id/recipient batch and queues termination through the agent graph without an additional stale-state query.

file: watomation/routers/thread_hooks.py
symbol: get_active_thread
feature: Webhook Endpoints
description: >
  Returns the active thread ID for a given recipient, or -1 if no active thread exists.

file: watomation/routers/thread_hooks.py
symbol: HILMessageRequest
feature: Webhook Endpoints
description: >
  Pydantic model for human-in-the-loop requests containing thread_id, update_message, optional recipient, and optional state_update_dict.

file: watomation/routers/thread_hooks.py
symbol: hil_system_message
feature: Webhook Endpoints
description: >
  Human-in-the-loop endpoint that sends a system message through the agent graph for manual intervention, looking up recipient from thread if not provided.

file: watomation/routers/payment_hooks_tbd.py
symbol: handle_payment_complete
feature: Webhook Endpoints
description: >
  Processes Stripe payment webhook, extracts orderID from event metadata, updates food_order payment_status to requires_capture, and triggers graph payment verification.

file: watomation/routers/payment_hooks_tbd.py
symbol: payment_complete_path
feature: Webhook Endpoints
description: >
  FastAPI route that receives Stripe payment-complete webhooks and delegates processing to handle_payment_complete via BackgroundTasks.

file: watomation/routers/offline_mode.py
symbol: handle_offline_message
feature: Webhook Endpoints
description: >
  WhatsApp message handler that auto-replies with an offline notification message when the system is in offline mode.

file: watomation/routers/offline_mode.py
symbol: set_offline_mode
feature: Webhook Endpoints
description: >
  Toggles offline mode by updating the WABA callback URL to append or remove the /offline-mode path suffix.

### Activity Reporting — `GET /internal/activity`

Every webhook above returns eagerly and does the real work (LangGraph runs, WhatsApp sends) in a
Starlette background task lasting 2–5 minutes, so "HTTP 200 returned" does not mean "work finished".
`/internal/activity` (`watomation/fapp.py`, backed by `watomation/activity.py`) exposes the in-flight
counts so an **external** scheduler can decide when it is safe to stop the machine. Unauthenticated,
counters only, excluded from OpenAPI.

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

**Read it as one busy/idle signal, not as three workloads.** A single webhook deliberately appears as
*both* `active_requests: 1` and `active_jobs: 1` for the same unit of work — that redundancy is the
safety property, not double counting. Test "every counter is zero"; never sum or reconcile them.

- `active_requests` — in-flight ASGI calls, counted by `ActivityMiddleware`. Because Starlette runs
  `BackgroundTasks` inside `Response.__call__`, a request stays counted until its background tasks
  finish too. This only holds for the pure ASGI middleware class; `BaseHTTPMiddleware` would report
  the request complete while the job ran.
- `active_jobs` — units passing through `run_background_task`.
- `active_agent_runs` — units passing through `run_rest_graph_with_custom_msg`, the single choke point
  for every agent run, including WhatsApp messages handled inline by pywa.
- `idle_seconds` — since the last unit of work completed. `/healthz` and `/internal/activity` are
  excluded from tracking, so health checks and scheduler polling never reset it.
- `safe_to_stop` — all counters zero **and** `idle_seconds >= idle_threshold_seconds`
  (`ACTIVITY_IDLE_THRESHOLD_SECONDS`, default 60). A convenience; the scheduler may apply its own
  threshold to `idle_seconds` instead.
- `draining` — always `false`. The app never refuses work; a request arriving mid-stop is handled,
  which is the point of `auto_start_machines = true`.

Scheduler contract: confirm the machine is `started`, require **two consecutive** `safe_to_stop: true`
responses, then stop via the Machines API with SIGTERM and a 300s timeout. `ops/fly_stop_scheduler.py`
implements this. Never infer job state from log quiescence — a 4-minute graph run emits nothing
between its start and end lines. Anything polling a *tracked* path more often than the threshold makes
the machine permanently unstoppable with no error anywhere.

**Log levels.** Agent runs log start/finish at `INFO`; requests and jobs log at `DEBUG`, so the
default `LOG_LEVEL=info` stays quiet — measured at ~2.7 µs and 0 log bytes per request, versus
~29.5 µs and ~1.7 KB of serialized JSON if requests were at `INFO`. Jobs still log at `INFO` through
`run_background_task`, with a `task_id` and duration, so nothing diagnostic is lost. Set
`LOG_LEVEL=debug` to see every counter transition while investigating.

### Edge Cases
- Invalid `rest_ref` in path parameter -> `validate_rest_ref` raises HTTP 404; all rider, order, and thread hooks validate before processing.
- `/SelectService` callback without `active_agent` -> callback handler sends service selection buttons if `rest_ref` is present, or logs an error if data is incomplete.
- `recipient` or `thread_id` mismatch between URL path and `FoodOrder` body in `payment_complete` -> HTTP 400 rejection.
- Stale thread has latest-checkpoint `retain_thread=True` -> the PostgreSQL job excludes it before calling this service.
- A thread changes after database selection -> the background worker intentionally uses the scheduled `thread_id` and `recipient` without a preflight recheck.
- HIL system message with missing or `"None"` recipient -> falls back to Supabase thread lookup; raises 404 if thread not found or inactive.
- Payment hooks router (`payment_hooks_tbd`) is defined but not included in the app; Stripe webhooks currently route through the order event hooks `payment_complete` endpoint instead.
- Delivery timeout -> notifies customer that no drivers are available, suggests takeaway, and informs of automatic payment refund. Does not terminate the conversation.
- Offline mode already active when `set_offline_mode(enable=True)` called -> returns early with "Already in offline mode" message.
- `delivery_summary` missing `customer_id` in rider enter endpoints -> potential `None` passed to `run_elai_graph_with_custom_msg`, which would fail silently in background task.
