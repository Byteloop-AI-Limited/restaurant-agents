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

## Non-blocking application cleanup

- [ ] Correct BNAT-owned prompt identity and wording after the
  behavior-preserving release. The copied SFCS wording remains in BNAT's triage
  and delivery prompts under
  `apps/bnat/src/bnat_agent/rest_agent/prompts/`.

## Non-blocking shared-runtime cleanup

- [ ] Consider compiling the graph once only after measuring a concrete benefit
  and designing the asynchronous lifecycle and checkpointer behavior. Do not
  add speculative caches or locks.
- [ ] Find and remove confirmed-unused import aliases or compatibility shims.
- [ ] Split or reduce `services/lg_utils.py`, which currently mixes LLM
  construction, legacy builders, thread lookup, graph display, and REPL helpers.
- [ ] Inject runtime database clients into shared diagnostic WhatsApp handlers
  before changing `/test`, `/test-t`, `/reset`, or payment-simulation behavior.
- [ ] Refactor payment helpers that capture settings and clients globally, with
  focused payment contract tests.
- [ ] Choose a canonical order model before consolidating the competing legacy
  and newer order-management implementations.
- [ ] Remove the in-memory thread fallback only after its callers and tests have
  migrated.
- [ ] Move AWS secret loading out of module import only as a separate
  configuration-lifecycle change.
- [ ] Revisit process-local Restaurant/base-URL and deduplication caches only if
  multi-instance requirements change the current one-worker contract.
- [ ] Delete or repair the inconsistent PGVector example/retriever code in a
  dedicated dead-code cleanup.

The detailed rationale and source references remain in
`docs/architecture/shared-agent-runtime-decisions.md`.
