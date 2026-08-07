# Restaurant Agent Runtime Follow-up Work

The shared runtime extraction, SFCS/BNAT cutover, and app-local clone cleanup
are complete. The following work is intentionally deferred.

## Close and release the current refactor

- [ ] Review the complete working-tree diff, then stage and commit the runtime
  rename, extraction, coordinated app cutover, clone deletion, tests, and
  documentation with deliberate commit boundaries.
- [ ] Validate the root Dockerfile and both package selections statically. Do
  not build images unless the repository owner explicitly requests it.
- [ ] Release SFCS and BNAT together from the same repository commit and root
  lockfile. Run both health checks and roll both back if either application
  fails.
- [ ] After separate authorization, run bounded WhatsApp canaries for both
  applications and record the results. Do not make live WhatsApp, Meta,
  payment, order, rider, or database calls as part of the offline test gate.

## Release prerequisites for prompt and availability work

- [ ] Set BNAT's RestaurantMaster schedule to 11:00–23:00 and update SFCS's
  actual RestaurantMaster end times. New delivery and takeaway orders end 15
  minutes before each configured service interval automatically.
- [ ] Add service authentication, persistence/retry, and delivery observability
  for the Ordelo feedback hook (`/customer-hooks/restaurant-feedback`) before
  exposing it outside the trusted internal boundary.

## Non-blocking shared-runtime cleanup

- [ ] `select_service_wa_send`'s Overwatch bypass was dead code: the two live
  `triage.py` call sites passed `restaurant_master=` but never `runtime=`, so
  an Overwatch tester messaging outside service hours saw only the Enquiry
  button. Fixed by moving the recipient-aware decision onto
  `OperationalLookupCache.accepts_new_order`/`.is_open` and making the sender's
  `operational_lookups` argument required, so a missing argument now raises
  instead of silently rendering the wrong menu. `tests/legacy_contract/rest_agent/test_agent_wa_senders.py`
  predates this gating and calls the sender positionally; it is excluded by
  `norecursedirs` and was intentionally left unchanged rather than kept in
  sync with a signature it does not exercise.
- [ ] The service-selection resend at the tail of `select_service_handler`
  (`rest_ref and not active_agent`) previously called the sender with no
  availability information at all, so every recipient saw an unfiltered
  Delivery/Takeaway/Enquiry menu on that specific callback path regardless of
  service hours. Now passes `operational_lookups` like every other gate;
  confirm this tightened behavior against the owner's expectation for that
  callback path in production.
- [ ] Gate checks now read `operational_lookups.get_restaurant_master()`
  freshly per call instead of reusing the `ContextSchema.restaurant_master`
  snapshot taken at the start of one graph invocation. Both come from the same
  5-minute TTL cache entry, so this is a marginal freshness change within a
  single invocation, not a new external read.
- [ ] Consider compiling the graph once only after measuring a concrete benefit
  and designing the asynchronous lifecycle and checkpointer behavior. Do not
  add speculative caches or locks.
- [x] Remove confirmed-unused configuration aliases, process-global settings
  clients, and compatibility shims from production modules.
- [x] Delete the `services/lg_utils.py` catch-all after moving its two live
  responsibilities to focused state-debug and graph-config modules.
- [x] Decide the production diagnostic boundary: remove `/test` and `/test-t`;
  retain `/paid3100`, runtime-bound `/reset`, and authorized read-only `/debug`.
  ADR-0012 supersedes ADR-0010 and records the accepted boundary.
- [x] Remove the two hard-coded order-reset handlers and bind `/paid3100` and
  `/reset` to exact runtime database settings, with focused registration and
  boundary tests.
- [x] Refactor payment helpers that capture settings and clients globally, with
  focused payment contract tests.
- [x] Choose `FoodOrder` and `OrderItem` as the canonical order models without
  an internal catalog-order writer. ADR-0009 records the accepted decision.
- [x] Extract `OrderItem` into its canonical model module, remove the two
  confirmed-unused order writer modules, and retain focused active-flow
  contract tests.
- [x] Remove the in-memory thread fallback after its callers and tests migrated
  to the database-only graph-config module.
- [x] Move AWS secret loading out of module import and into the explicit app
  composition boundary. ADR-0011 records the settings lifecycle.
- [ ] Revisit process-local deduplication only if multi-instance requirements
  change the current one-worker contract. Operational lookup caching is covered
  by ADR-0016; a multi-instance reset requires one request per replica.
- [x] Delete the inconsistent, unused PGVector example/retriever code.

The detailed rationale and source references remain in
`docs/architecture/shared-agent-runtime-decisions.md`.

<!-- Lohith's list -->
/order-event-hooks.py/takeaway_pickup_time_updated
I need to update retian_thread to false after this;
    first_state_update_dict = {
        "active_agent": "takeaway_agent",
        "order_number": summary.order_number,
    }

-- Cache reset is available at POST /internal/cache/reset; see ADR-0016.
-- On hitting goBack, this page errors out at https://restaurant.ordelo.app/checkout-error; This should have a way for starting new session from here.
OR remove go back and instead, have cancel and create new order