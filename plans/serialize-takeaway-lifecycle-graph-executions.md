# Serialize takeaway lifecycle graph executions

## Goal

Prevent the collection payment-pending graph turn from overlapping the
configured-auto pickup-completion sequence for the same active customer
conversation.

The intended customer order is:

1. receipt;
2. `We will confirm the pickup time in a moment.` exactly once;
3. confirmed pickup-time update;
4. conversation termination.

This is a narrow mitigation for the observed payment-complete versus
pickup-time race. It is not a general graph scheduler or webhook-idempotency
project.

## Current failure

`payment_complete()` sends the receipt and queues
`collection_payment_complete`. Configured auto-accept can then call
`takeaway_pickup_time_updated()`, which independently queues
`customer_collection_completion_sequence`.

Both background tasks invoke the graph against the same active checkpoint. If
the pickup task starts after the payment SystemMessage is checkpointed but
before its tool result is persisted, it can see two unresolved authoritative
instructions. That can resend the payment-pending text and leave the pickup
instruction for the terminal turn.

## Decision

Add one private, process-local takeaway lifecycle gate in
`watomation/routers/order_event_hooks.py`.

- Key it by `(validated_rest_ref, recipient)`. The pickup payload does not carry
  `thread_id`; this pair is the existing correlation used to resolve the active
  Restaurant Thread, without adding a database lookup or changing the external
  payload.
- Store locks in a `WeakValueDictionary` so completed customer flows do not
  accumulate permanent lock entries.
- Create locks lazily inside the running event loop.
- Keep the existing `run_background_task` wrapper and task names.
- Reserve the gate in the takeaway `payment_complete()` request before the HTTP
  response is returned. Its background wrapper runs the payment-pending graph
  turn and releases the gate in `finally`.
- Make the pickup-time background wrapper wait for the same gate, then hold it
  across the complete `notify_release_and_optionally_terminate()` sequence:
  notification, persisted release, and terminal graph turn.
- Log only actual contention, so a production canary can confirm that the
  pickup execution waited without adding noise to every order.

This is intentionally compatible with the repository's current single-worker,
`--ha=false` deployment. It does not alter graph topology, checkpoint format,
`AgentState`, `GraphAdapter`, prompts, routes, or webhook schemas.

## Implementation

### 1. Add the private lifecycle gate and wrappers

File:
`packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py`

- Add a private lock lookup keyed by `(rest_ref, recipient)`.
- Add a payment wrapper that receives the already-reserved lock, invokes
  `graph_adapter.run_rest_graph_with_custom_msg()` with the existing
  authoritative payment instruction and retained takeaway state, and always
  releases the lock.
- Add a pickup wrapper that acquires the same lock and invokes the existing
  `notify_release_and_optionally_terminate()` unchanged.
- Do not put a lock around delivery lifecycle paths or ordinary customer,
  callback, stale-thread, or debug graph runs.

### 2. Reserve payment before pickup can be emitted

In the takeaway branch of `payment_complete()`:

- keep the direct receipt send unchanged;
- obtain and acquire the conversation's lifecycle gate before returning;
- schedule the payment wrapper instead of scheduling the graph adapter method
  directly;
- release the reservation immediately if adding the background task fails, so
  an exceptional scheduling path cannot strand the conversation gate;
- preserve the current SystemMessage, `retained_specialist_state()`, reply
  target, background task name, response schema, and error logging.

Reserving before the response matters: Ordelo waits for this HTTP response
before its next configured-auto initialization task can emit the pickup-time
event. Merely acquiring inside the later background task would serialize
execution but would not guarantee that payment takes the gate first.

### 3. Serialize the whole pickup completion sequence

In `takeaway_pickup_time_updated()`:

- keep validation, time formatting, task name, and response unchanged;
- schedule the pickup wrapper instead of calling
  `notify_release_and_optionally_terminate()` directly;
- hold the gate until the pickup update, deterministic state release, and
  terminal turn have all finished.

This ensures the confirmed pickup SystemMessage is appended only after the
payment-pending turn has a matching ToolMessage/AIMessage completion.

### 4. Document only the changed behavior

- `docs/takeaway_whatsapp_agent.md`: state that payment-pending and pickup
  completion are serialized for the same active Restaurant/recipient
  conversation, with the completion sequence held as one unit.
- `docs/multi_agent_system.md`: add the same narrow ordering guarantee to the
  external lifecycle-event flow.
- `docs/to-do.md`: retain the existing durable idempotency/serialization item,
  but clarify that this local mitigation covers only the observed single-process
  takeaway race; multi-instance coordination and genuine webhook replay
  idempotency remain deferred.

No Constitution amendment, glossary change, domain-model change, or new ADR is
needed: authority and ownership stay unchanged, and no public composition or
graph contract is introduced.

## Tests

Use `tests/watomation/test_specialist_lifecycle_updates.py`.

1. Start a payment-pending wrapper that pauses inside the fake graph call, then
   start pickup completion for the same `(rest_ref, recipient)`. Assert that no
   pickup graph call begins until payment finishes.
2. After releasing payment, assert the exact graph-call order is payment
   pending, pickup notification, persisted release, then terminal turn.
3. Make the payment graph raise and assert its `finally` releases the gate so
   pickup completion proceeds instead of deadlocking.
4. Use two recipients and assert one recipient's blocked payment does not block
   the other's lifecycle work; this proves the gate is keyed rather than global.
5. Update the existing route-scheduling assertions to prove both takeaway
   endpoints use the serialized wrappers and preserve their current messages,
   state, and task names.
6. Leave `tests/legacy_contract` untouched.

Do not assert exact free-form model wording or private LangGraph checkpoint
serialization.

## Verification

Run from the repository root:

```bash
uv run pytest tests/watomation/test_specialist_lifecycle_updates.py \
  tests/rest_agent/test_specialist_lifecycle.py
uv run pytest tests
uv run pytest apps/sfcs/tests apps/bnat/tests apps/elas/tests
uv run pytest
uv run ruff check .
git diff --check
```

The automated tests must use fake graph and WhatsApp clients. Do not send live
webhook, payment, order, or WhatsApp events.

An optional post-deployment canary requires separate authorization. For one
configured-auto BNAT takeaway, verify one receipt, one pending-pickup update,
one confirmed-time update, and one termination, with a contention log showing
the pickup sequence waited when the payment graph was still running.

## Explicit non-goals

- No OrdeloAgent or restaurant-frontend changes.
- No direct lifecycle message outside the graph; the Agent remains aware of
  every customer-visible lifecycle update through checkpointed messages.
- No database/advisory lock, event ledger, new table, or webhook payload field.
- No general serialization of `run_rest_graph_with_custom_msg()`.
- No delivery-flow behavior change.
- No suppression of genuine repeated webhook events; durable event idempotency
  remains separate work.
- No deployment or live canary as part of implementation.

## Acceptance criteria

- Same-conversation payment and pickup lifecycle graph work cannot overlap in
  the current deployment model.
- Payment-pending completes before pickup notification starts.
- Pickup notification, release, and termination cannot interleave with the
  payment-pending turn.
- Different recipients remain concurrent.
- Failure releases the gate and preserves the existing terminal cleanup path.
- Existing route contracts, task names, customer copy, graph interfaces, and
  app isolation remain unchanged.
