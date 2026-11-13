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
  add speculative caches.
- [ ] Design durable per-thread lifecycle-event idempotency and serialization
  before treating concurrent webhook retries or multi-replica execution as
  supported. Takeaway payment-pending and pickup-completion graph turns are
  serialized in the current one-worker process by `(rest_ref, recipient)`, but
  that narrow gate does not make receipt delivery, event replay, or
  cross-process checkpoint ordering generally idempotent.
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

## Discovered during ELAS onboarding (2026-08-17)

- [x] `prompt_runtime.py`'s `render` resolved `selected_restaurant_name` to
  `context.restaurant_name` whenever no choice had been captured yet. For a
  single-restaurant app that is the app's own name (correct), but for ELAS
  before the customer picks a brand it rendered as `restaurant_name` =
  `PRESENTATION.display_name` = "Elai" — a real brand name — directly
  contradicting the same prompt's "restaurant not yet known" rule. Fixed by
  resolving to the literal `"not yet selected"` whenever
  `context.restaurant_selection is not None` and no choice has been captured;
  single-restaurant apps are unaffected. See
  `tests/rest_agent/test_prompt_runtime.py`.
- [ ] `rest_agent/agents/triage.py`'s `send_welcome_message` has a second,
  unreachable `return Command(...)` block (the "Welcome message sent to
  {wa_name}..." variant) immediately after the first, live `return
  Command(...)` ("Service selection buttons sent..."). This predates the
  ELAS restaurant-selection branch added above it and is dead code on
  SFCS/BNAT/ELAS alike. Low risk, but delete it in a follow-up pass rather
  than as a drive-by edit during unrelated work.
- [x] elai's carousel menu template used the slug `wits` for the "Wings and
  Things" brand; its live non-carousel path (the one actually invoked) used
  `chks`. Resolved 2026-08-17 by tracing `_send_menu_tool` → `state["rest_ref"]`
  → set to `"chks"` by `/SelectRestRef` — `wits` only appeared in a
  commented-out, never-invoked carousel experiment. ELAS's `RestaurantChoice`
  for CHKS now uses the confirmed-correct `chks_logo.jpg`; this was also the
  root cause of a real production `MediaUploadError` (403) — the original
  `identity.py` logo URLs were a fabricated S3 path that never existed, not
  even the wits/chks slug. Still open: confirming the menu *web app itself*
  serves `/restaurant/chks` (see `apps/elas/DEPLOYMENT.md`).
- [ ] The AST-based graph-contract test
  (`tests/rest_agent/test_graph_contract.py`) that pinned `multi_agent.py` by
  parsing source text for exactly 3 `add_node`/4 `add_conditional_edges`
  calls could not survive `build_multi_agent_graph` gaining an optional
  config-gated 4th node (ADR-0021): a loop-based node/edge builder is
  correct and necessary to avoid duplicating the function per node count,
  but it makes any additional `add_node` call in source — even one only
  reached conditionally at runtime — permanently unparseable by an
  unconditional AST walk. Replaced that one test with a stronger
  characterization that builds the real `StateGraph` twice (with and
  without `dinein_agent_node`) and inspects `builder.nodes.keys()` plus
  `route_initial`/`route_after_agent` directly. If another shared graph
  file grows a similar structural AST-pinned test, expect the same failure
  mode the next time a config-gated node is added.
- [x] BNAT's service-selection buttons said "Delivery (15% off)" /
  "Takeaway (10% off)" (`apps/bnat/src/bnat_agent/identity.py`), but its
  menu-image caption had never been given its own `delivery_promo_caption` /
  `takeaway_promo_caption` (added 2026-08-17), so it fell through to
  `DEFAULT_DELIVERY_PROMO_CAPTION` = "...20% off..." — a live mismatch
  between the button (15%) and the caption sent moments later (20%).
  Resolved 2026-08-17: set BNAT's captions to match its existing buttons
  (15% delivery / 10% takeaway), confirmed by the owner.
- [x] `on_callback_handler.select_service_handler`'s deterministic resend
  branch (`if rest_ref and not active_agent: await select_service_sender(...)`)
  formerly omitted `delivery_button_label`/`takeaway_button_label`, so it
  rendered `select_service_wa_send`'s bare defaults instead of the app's
  configured labels. Resolved 2026-08-26: the resend now passes the app-owned
  presentation labels and preserves a matching per-brand override when the
  callback `rest_ref` identifies a configured `RestaurantChoice`, consistent
  with the other service-button call sites.
- [x] "Book a table" (ELAS enquiry menu, ADR-0023) was the first enquiry
  option whose fulfilment required a handoff to a different graph node. The
  risk noted here anticipated a *degraded* failure (triage prose-answering
  instead of transferring); what actually happened in production
  (2026-08-18) was a hard crash — `InvalidUpdateError: Node toolNode does
  not exist` — the first time a CHKS/Wings and Things customer
  (`supports_dine_in=False`) tapped it. Root cause was not the prompt:
  `dinein_unsupported_block` (and, identically, `selection_required_block`)
  redirected via `Command(graph=Command.PARENT, goto="triage_agent",
  update={"messages": [ToolMessage(...), SystemMessage(...)]})`, re-entering
  the same node that made the pending tool call; the persisted tail came
  back with the `SystemMessage` ordered before its `ToolMessage`, which
  `agent_runner.py`'s tail-repair logic misread as a missing tool response
  and then crashed trying to fix it via a hardcoded, nonexistent
  `as_node="toolNode"`. Resolved by ADR-0024: the enquiry row is now hidden
  for Wings and Things entirely (`EnquiryOption.only_for_rest_refs`) rather
  than shown-and-declined, and the guard shape is fixed everywhere it
  appears — a blocked transfer answers its own tool call and ends its own
  node's turn, never `Command.PARENT` back into the calling node. Also fixed
  the hardcoded `as_node="toolNode"` in `agent_runner.py`.

The detailed rationale and source references remain in
`docs/architecture/shared-agent-runtime-decisions.md`.

## Remove leftover restaurant-admin code (owner: Lohith; added 15 Oct 2026)

This runtime does not talk to restaurant admins. OrdeloAgent owns every
restaurant-facing message and button (WhatsApp from Ordelo's own number, and now
Telegram; see OrdeloAgent `plans/telegram-rest-admin-scaffold-plan.md`, phases 7-8).
The code below is left over from before that split. Remove it once the checks
below pass. Nothing here is urgent and nothing has been removed yet.

Candidates to remove:

- [ ] `watomation/on_callback_handler.py` `admin_collection_ready`, its
  `bound_collection_ready` wrapper and the `/AdminCollectionReady`
  `CallbackButtonHandler` in `web/app_factory.py` (import at line ~63, wrapper
  ~136, registration ~216), and the test
  `tests/legacy_contract/watomation/test_on_callback_handler.py::test_admin_collection_ready_posts_to_ordelo`.
  The button is created by OrdeloAgent `wa_senders.admin_order_reciept` and
  sent from Ordelo's WhatsApp number, so taps land on OrdeloAgent's own
  `on_callback_wa_handler.admin_collection_ready`, not here.
- [ ] `watomation/on_admin_message.py`, the whole module
  (`handle_wa_msg_in_admin_graph`, `handle_admin_order`,
  `handle_admin_referred_product`, `reset_thread_admin`). None of them is
  registered in `web/app_factory.py`; only
  `tests/legacy_contract/watomation/test_on_admin_message.py` imports them.
- [ ] `watomation/on_callback_handler.py` `restaurant_order_confirmation_handler`
  (an accept/decline stub that does nothing), its `/RestaurantOrder`
  registration in `web/app_factory.py` (~220) and the test
  `test_restaurant_order_confirmation_handler_accept_decline`.
- [ ] `services/wa_templates/restaurant_confirmation_template.py`
  (`send_restaurant_order_confirmation`, `send_restaurant_pickup_time_confirmation`).
  They are never called; OrdeloAgent sends the confirmation and pickup prompts.
- [ ] `watomation/routers/thread_hooks.py` `debug_admin_state_path`
  (`GET /debug-admin-state`, which defaults to a real phone number). It is a
  generic graph debug endpoint: remove it, or rename it and drop the default.

Keep: `RestaurantMaster.admins` and the takeaway payload fields
(`restaurant_admin`, `admins`, `admin_id`), which parse payloads OrdeloAgent
sends; `waba_callback._restaurant_master_details` (read-only diagnostics);
`OrdeloService` feedback scheduling (it asks Ordelo to notify the admins).

Checks before removing (so nothing is affected):

- [ ] Confirm that no restaurant app's WABA phone number or callback URL is
  Ordelo's number (`/waba-callback` diagnostics, `waa_callback_url`), so no
  `/AdminCollectionReady` or `/RestaurantOrder-*` tap can arrive here.
- [ ] Search production logs for `/AdminCollectionReady` and
  `Restaurant order confirmation:` in SFCS/BNAT over the last 30 days; expect zero.
- [ ] After removal, OrdeloAgent `/delivery-hooks/notify-food-ready-for-pickup`
  has no caller. Decide there whether to keep it (manual/ops use) or remove it.
- [ ] Update `docs/glossary.md`, the domain model `code-ref` blocks and the
  feature guides that mention these handlers in the same change.

<!-- Lohith's list -->
/order-event-hooks.py/takeaway_pickup_time_updated
I need to update retian_thread to false after this;
    first_state_update_dict = {
        "active_agent": "takeaway_agent",
        "order_number": summary.order_number,
    }

-- When rider not found, the update is not sent to the customer - why? JUmps straight to 'marketingConsent'
-- Cache reset is available at POST /internal/cache/reset; see ADR-0016.
-- On hitting goBack, this page errors out at https://restaurant.ordelo.app/checkout-error; This should have a way for starting new session from here.
OR remove go back and instead, have cancel and create new order
