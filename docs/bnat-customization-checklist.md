# BNAT Restaurant Customization Checklist

> [!WARNING]
> BNAT now composes the shared Restaurant Agent runtime. Do not copy shared
> agents or deploy production changes until every relevant application-owned
> item below has been reviewed.

See [the interactive runtime guide](./guides/agent-runtime-composition.html),
[the multi-agent overview](./multi_agent_system.md), and
[the prompt-update rules](./rules-to-update-prompt-files.md).

## Current Shared-Runtime Composition

- [x] Workspace application is `apps/bnat`.
- [x] Runtime identity is `rest_ref="BNAT"` and `waba_namespace="bnat"` in
  `apps/bnat/src/bnat_agent/identity.py`.
- [x] Entrypoint is `bnat_agent.main:app`.
- [x] `apps/bnat/src/bnat_agent/rest_agent/agent_recipe.py` loads three
  BNAT-owned complete prompts and binds `RestaurantGraphAdapter`.
- [x] Standard graph, tools, state, middleware, runner, and WhatsApp senders come
  from `restaurant-agent-runtime`.
- [x] BNAT does not import the SFCS package.

## Customer-Facing Identity and Prompts

- [ ] Review
  `apps/bnat/src/bnat_agent/rest_agent/prompts/triage_agent_prompt.md`.
- [ ] Review
  `apps/bnat/src/bnat_agent/rest_agent/prompts/delivery_multiagent_prompt.md`.
- [ ] Review
  `apps/bnat/src/bnat_agent/rest_agent/prompts/takeaway_agent_prompt.md`.
- [ ] Remove Southern Fried Chicken, Elai, Salisbury, contact, policy, service,
  and menu wording that does not belong to BNAT.
- [ ] Confirm triage, delivery, and takeaway instructions reference only tools
  exposed by the selected standard node.
- [ ] Confirm `RestaurantPresentation` uses the approved BNAT display name,
  contact details, and logo. The current identity file still requires a BNAT
  logo review.

Prompts remain complete and app-owned even when their current text matches
another app. Do not move them into the shared runtime or import SFCS prompt
files.

## Compatible BNAT Customization

- [ ] For a BNAT-only capability on an existing standard node, implement a
  native app-owned tool and bind it with `extra_tools_by_agent`.
- [ ] For a complete replacement of triage, delivery, or takeaway, keep the
  runnable under BNAT and bind it with `agent_overrides`.
- [ ] Keep custom PyWa callbacks and FastAPI routers app-owned and register them
  through native framework extension points.
- [ ] Do not create an app-local copy of shared agents, tools, state, or runner
  modules.

Only `triage_agent`, `delivery_agent`, and `takeaway_agent` are supported
standard-adapter keys. A node cannot receive extra tools and be replaced at the
same time.

## When BNAT Needs an App-Owned GraphAdapter

Use a complete BNAT-owned adapter only if BNAT must:

- add or remove graph nodes;
- change routing or handoff node names;
- change `AgentState` fields or reducers incompatibly;
- change checkpointing, thread identity, compilation, repair, or debug
  semantics; or
- otherwise fail the standard adapter contract.

The custom adapter must still bind the exact `RestaurantRuntime`, use its exact
async WhatsApp client in graph context, and preserve WABA and route isolation.

## WhatsApp and External Configuration

- [ ] Verify the complete `bnat` WABA namespace in the approved secret-management
  workflow. There is no fallback to another namespace.
- [ ] Verify callback URL, phone ID, verified name, templates, app ID, token,
  app secret, and verify token as one internally consistent Meta app namespace.
- [ ] Verify BNAT menu media, contact information, and customer-facing WhatsApp
  messages.
- [ ] Do not copy, print, or commit credential values.

## Restaurant and Ordelo Data

- [ ] Create or verify the `BNAT` row in `restaurant_master`, including admins,
  service hours, address, coordinates, supported order types, and stale-thread
  policy.
- [ ] Create or verify the `BNAT_APP_URL` Ordelo configuration value.
- [ ] Review SQL examples and migrations before execution; do not apply
  SFCS-specific values unchanged.
- [ ] Verify menu, pricing, payment, maps, rider, reservation, and order-service
  configuration using BNAT data.

## Tests and Acceptance

- [ ] Keep `apps/bnat/tests/test_bnat_agent_recipe.py` green; it proves complete
  prompt loading and exact runtime/WhatsApp-client binding.
- [ ] Run the complete BNAT app test suite.
- [ ] Run the complete shared runtime and repository suite for changes to common
  graph behavior.
- [ ] Run Ruff and `git diff --check`.
- [ ] Confirm cross-restaurant routes return `404` before side effects.
- [ ] Confirm `/healthz`, WhatsApp webhook delivery, BNAT-prefixed thread
  creation, menu links, orders, payment callbacks, and Ordelo event hooks in an
  authorized non-production environment.
- [ ] Treat live WhatsApp probes, deployment, and external configuration writes
  as separately authorized actions.

## Search Before Release

Classify every result from:

```bash
rg -n -i 'sfcs|elai|southern fried|salisbury|sfc[ +_-]?logo' \
  apps/bnat docs/bnat-customization-checklist.md
```

Do not remove an occurrence merely because it matches; historical references
and explicit cleanup checks may be intentional.
