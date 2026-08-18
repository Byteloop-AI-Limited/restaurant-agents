# ADR-0020: App-Owned Restaurant Selection for Multi-Brand Apps

- Status: Accepted
- Date: 2026-08-17
- Decision owners: Restaurant platform owner and maintainers

## Context

ELAS serves two restaurant brands — Elai (`ELAS`) and Wings and Things
(`CHKS`) — behind one WhatsApp number, replacing the `select_rest_ref_handler`
flow from the pre-monorepo `elai` monolith (design evidence only, not part of
this migration; see ADR-0002). SFCS and BNAT serve exactly one restaurant and
must remain unaffected: `RestaurantIdentity.rest_ref` is simultaneously the
WABA namespace key, the thread-id prefix, the webhook `404` guard, the
`restaurant_master` key, and the Ordelo customer/consent key, and none of
that changes for a multi-brand app. Only the menu link, CTA logo, and
customer-facing wording vary per brand; every operational authority
(hours, address, delivery-area, customer master, consent, thread namespace)
stays canonical to the app's own `rest_ref`, matching how Ordelo's
`_REST_REF_ALIAS_MAP` resolves `CHKS -> ELAS` for all DB-backed lookups.

`elai`'s own implementation of this flow used `state["rest_ref"]` for both
the invariant app identity *and* the customer's brand choice. Because
`rest_ref` is unconditionally seeded on every new thread, that conflation
meant a stale `/SelectService` button — or any code path assuming
`rest_ref` implies "restaurant chosen" — could silently believe a selection
had already been made, or silently overwrite it.

## Decision

Restaurant selection is app-owned configuration, not a shared framework,
exactly mirroring the `EnquiryMenu` precedent (ADR-0015):
`RestaurantPresentation.restaurant_selection: RestaurantSelection | None`
holds an immutable `RestaurantSelection` (a prompt plus two or three
`RestaurantChoice` values, WhatsApp's button cap). Its default of `None`
leaves every selection-aware code path inert for every existing app.

The customer's choice lives in a new state key, `selected_rest_ref`, with
exactly one writer: the `/SelectRestaurant` callback handler and the
`capture_restaurant_selected` triage tool. `rest_ref` is never read as a
fallback for it. Three call sites gate on
`restaurant_selection.py:selection_pending()` before allowing an order to
start: the `transfer_to_delivery`/`transfer_to_takeaway`/`transfer_to_dinein`
tools (via `route_tool_service_selection`), the `/SelectService` callback and
every typed "I want delivery" message (via `route_service_selection`), and
the new `ask_user_to_select_restaurant` tool checks the same retained-work
guard used elsewhere so a switch is blocked mid-order. Two tools —
`ask_user_to_select_restaurant` and `capture_restaurant_selected` — are
appended to `triage_tools` only when `restaurant_selection` is configured,
following the same conditional-append pattern as `extra_tools_by_agent`;
the unconditional `triage_tools` list itself, and therefore BNAT's and
SFCS's exact tool set, is untouched.

Only the menu resolution surface (`resolve_menu_rest_ref`,
`resolve_menu_logo_url`) reads the selected choice; `restaurant_master`,
`OperationalLookupCache`, customer master, consent, and the thread-id prefix
all continue to use the app's own `rest_ref` exclusively — this is a
deliberate scope decision, not an oversight, and it means CHKS never needs
its own `restaurant_master` row.

## Consequences

- SFCS and BNAT are byte-identical in behavior, tool lists, and graph shape;
  `restaurant_selection=None` is the only new field they carry, and it is
  never read.
- ELAS onboarding needs no new shared abstraction beyond one config value and
  one new state key — see `apps/elas/src/elas_agent/identity.py`.
- A future third or fourth restaurant behind one app reuses the same
  `RestaurantChoice` mechanism without a shared-runtime change.
- Cutover consequence: in-flight `elai` threads carry no `selected_rest_ref`
  and will be asked to choose once after `ELAS_APP_URL` is repointed at this
  deployment — this matches `elai`'s own `/reset` semantics and is accepted.
- This is not a general selection-policy or routing framework: a genuinely
  different multi-entity concern (for example, per-branch delivery zones)
  requires its own deliberate design, not an extension of
  `RestaurantChoice`.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: RestaurantSelection
feature: app-owned-restaurant-selection
description: >
  Immutable app-owned configuration of two or three selectable restaurant
  brands behind one WhatsApp number.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/restaurant_selection.py
symbol: selection_pending
feature: app-owned-restaurant-selection
description: >
  Single predicate consulted by every gate that must block an order until a
  restaurant is chosen.
```

```code-ref
file: apps/elas/src/elas_agent/identity.py
symbol: RESTAURANT_SELECTION
feature: app-owned-restaurant-selection
description: >
  ELAS-owned configuration of the Elai and Wings and Things choices.
```
