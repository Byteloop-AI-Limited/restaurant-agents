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
  for the Ordelo complaint hook before exposing it outside the trusted internal
  boundary.

## Non-blocking shared-runtime cleanup

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
- [ ] Revisit process-local Restaurant/base-URL and deduplication caches only if
  multi-instance requirements change the current one-worker contract.
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

-- Create these endpoints in this new app
SELECT * FROM ordelo_post('SFCS_APP_URL', '/restaurant-base-url-cache/reset');
SELECT * FROM ordelo_post('SFCS_APP_URL', '/restaurant-master-cache/reset');
