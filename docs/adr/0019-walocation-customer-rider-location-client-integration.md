# ADR-0019: WaLocation Customer Rider-Location Client Integration

- Status: Accepted
- Date: 2026-08-14
- Decision owners: Repository owner and maintainers
- Depends on: ADR-0018's retained specialist lifecycle projection

## Context

A retained delivery customer asking "where is my rider?" always received the
same fixed placeholder, regardless of delivery phase, because Ordelo's
on-demand WhatsApp location module (WaLocation) had not yet landed. The
placeholder was a deliberate prerequisite: it kept behavior safe and
deterministic while `is_delivery_picked_up` state and paid-retained-flow
ownership were established (ADR-0018).

Ordelo's side of WaLocation is now live: an open, unsigned
`POST /wa-request-location` that validates the exact
`delivery_inflight(order_number, dispatch_id, rider_id)` assignment and either
reuses a location observation no more than five minutes old or asks the rider
for their current WhatsApp location, then posts the result to a caller-supplied
callback URL. The cross-repo contract is
`docs/wa_location_restaurant_agents_integration.md` in OrdeloAgent.

Production testing surfaced a failure in the model-driven routing: "where is
my order? share rider lcoation" was answered by re-invoking `update_customer`
with an earlier, unrelated payment-confirmation message still present in
conversation history, instead of the correct pre-pickup placeholder. A first
revision of this ADR responded by adding a regex-based deterministic
interception ahead of the model, mirroring the existing
`is_refund_timing_query` pattern. That traded away the model's actual
strength — recognising the wide range of ways a customer phrases "where's my
food" — to fix a problem that was not, on inspection, a rider-location
misclassification at all: the model correctly attempted to answer, but misused
`update_customer` by replaying stale context. The fix belongs at that point of
misuse, not in front of every customer message.

## Decision

1. Rider-location routing stays model-driven. The delivery prompt and the
   `answer_general_query` steering branch point rider-location phrasing at
   `request_rider_location`; there is no regex-based pre-model interception.
   The `answer_general_query` branch cannot simply be deleted: those phrases
   would otherwise fall through to the generic "where"/"location" branch and
   answer with the restaurant's street address.
2. `update_customer` refuses to fire unless the current turn was opened by a
   fresh runtime `SystemMessage`
   (`agent_harness._last_turn_started_by_system_message`), walking backward
   past any intermediate tool exchanges to find the message that actually
   started the turn. A customer's own message can never trigger it, and it can
   never fire on an earlier turn's already-consumed system instruction — which
   is exactly the failure that was observed. This is a structural guard, not a
   phrase list: it protects every kind of customer question that could trigger
   this misuse, not only rider-location ones, and it leaves the model fully in
   charge of recognising intent.
3. `rider_location_support.send_rider_location_reply` is the implementation
   behind `request_rider_location`, kept as a standalone function purely so
   the guard and Ordelo-response mapping are unit-testable without the
   LangGraph `Command`/`ToolMessage` wrapping the tool itself adds. It enforces
   `order_number` present and `is_delivery_picked_up is True` locally before
   ever calling Ordelo — zero Ordelo calls pre-pickup, matching the retained
   placeholder behavior exactly.
4. `OrdeloService.request_rider_location()` does not collapse non-2xx
   responses to `None` the way every other `OrdeloService` method does. It
   returns a typed `WaLocationRequestOutcome` carrying the HTTP status and
   Ordelo's `detail.code`, because the guard must distinguish
   `409 food_not_picked_up` from `409 delivery_not_inflight` from a plain
   transport failure, each with different customer copy.
5. A new open callback route, `POST /rider-event-hooks/{rest_ref}/wa-location-response`,
   receives Ordelo's asynchronous result. It is deliberately thin: no graph
   invocation, no assistant message. Before any WhatsApp side effect it
   resolves the customer's active Thread through the non-creating
   `ThreadHandler.get_active_thread` (not the recipient-based
   `debug_state_values`, which mints a Thread row via `get_or_create_thread`
   for an unknown customer) and revalidates retained, `delivery_agent`-owned,
   matching-`order_number`, picked-up state before sending a pin with this
   app's injected WhatsApp client.
6. `send_rider_live_location_link` (a link, not a pin) stays registered in
   `delivery_tools` rather than being removed in this change. The prompt is the
   only thing steering the model away from it on initial tool selection; the
   `/DoNotRespond:` suppression convention already prevents a *second* tool
   call after `request_rider_location` returns, but does not prevent the model
   choosing the legacy tool first. Removing the legacy tool, its state field,
   and the map-URL construction at rider event pickup is deferred to a
   follow-up.
7. `check_delivery_driver_allocation_status` refuses once
   `is_delivery_picked_up` is `True` and redirects to `request_rider_location`,
   instead of calling Ordelo's `/delivery-hooks/check-rider-allocation-status`
   endpoint. Production testing showed "where is my food now?" — genuinely
   ambiguous between an arrival-time question and a location question, and
   valid under the prompt's own arrival-time guidance — being answered with
   stale "a driver has been assigned" copy after the order had already been
   picked up, because that endpoint only reports
   `unassigned`/`assigned`/`timedout` and has no concept of pickup at all. The
   fix is the same shape as the `update_customer` guard: gate the tool that is
   wrong post-pickup, rather than trying to fully disambiguate every phrasing
   that could reach it. Removing the tool outright was considered and rejected
   — it still answers a real, distinct question ("has a driver been assigned
   yet?") pre-pickup that a placeholder does not cover.

## Consequences

- After pickup, a rider-location question gets a real WhatsApp location pin
  instead of a placeholder; before pickup, behavior is unchanged.
- The model retains full responsibility for recognising a rider-location
  question in any phrasing; no parallel regex intent-classifier exists to
  drift out of sync with the prompt.
- `update_customer` misuse is prevented structurally for every customer
  question, not just the one phrasing that exposed it in testing.
- `check_delivery_driver_allocation_status` can no longer answer a post-pickup
  question with stale allocation status; it hands off to
  `request_rider_location` instead, regardless of which phrasing routed the
  model to it.
- Two tools can still answer a rider-location-shaped request depending on
  model choice, until the deferred legacy-removal follow-up lands.
- The callback route's guard-failure paths mutate no conversation state and
  create no Thread row, so a callback for an unknown, released, or mismatched
  customer is inert rather than side-effecting.
- `ContextSchema` gained an optional `wa_msg_id` field, threaded from the
  primary inbound-message handler, so the Ordelo idempotency key can include
  the actual WhatsApp message id rather than being omitted.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py`
  (`_last_turn_started_by_system_message`, `update_customer`)
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/rider_location_support.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/ordelo_service/ordelo_service.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/ordelo_service/datamodels/wa_location_pymodel.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/rider_event_hooks.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/specialist_lifecycle.py`
- `docs/wa_location_restaurant_agents_integration.md` (OrdeloAgent)
