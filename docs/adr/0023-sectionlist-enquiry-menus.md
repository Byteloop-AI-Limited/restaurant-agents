# ADR-0023: WhatsApp SectionList Enquiry Menus With an App-Owned Extra Option

- Status: Superseded by [ADR-0024](0024-per-brand-enquiry-rows.md)
- Date: 2026-08-18
- Decision owners: Restaurant platform owner
- Supersedes: [ADR-0015](0015-app-owned-enquiry-menus.md)

## Context

ELAS was onboarded with a `dinein_agent` (ADR-0021), but the customer-facing
WhatsApp flow never offered it: dine-in was reachable only if a customer
happened to type "book a table" and triage's LLM decided to call
`transfer_to_dinein`. Nothing in the button flow surfaced the option, because
ADR-0015 capped the enquiry menu at three reply buttons — WhatsApp's reply
button limit — and ELAS already spent all three on Share Feedback, Parking
availability, and Subscribe for offers.

A WhatsApp SectionList (interactive list) allows up to ten rows instead of
three buttons. That is the mechanism that unblocks a fourth option, for ELAS
and for any future app that needs one.

## Decision

**What carries forward from ADR-0015, unchanged:** enquiry menus remain
app-owned, declared on `RestaurantPresentation.enquiry_menu`; every option
still serializes as a `/SelectEnquiry` callback; the callback handler still
always enters triage before running the graph; this is still not a general
callback registry — a genuinely new callback workflow remains an app-owned
native PyWa handler registered during app assembly.

**What changes:**

1. `EnquiryMenu` accepts **1 to 10** options (was 1 to 3), and gains a
   `button_title` (the SectionList opener, ≤20 chars, reused as the single
   `Section`'s title). `EnquiryOption.title` caps at 24 chars (was 20 —
   `SectionRow`'s limit, not `Button`'s), and gains an optional `description`
   (≤72 chars).
2. `select_enquiry_wa_send` now emits a `SectionList` (one `Section`, one row
   per option) instead of up to three reply `Button`s. The `/SelectEnquiry`
   payload shape is **unchanged** — same `action`, `rest_ref`,
   `active_agent="triage_agent"`, `human_msg` fields — so the callback
   handler needed no change beyond registration.
3. Selecting a SectionList row is a `CallbackSelection` update, not
   `CallbackButton`. The app factory registers a `CallbackSelectionHandler`
   for `/SelectEnquiry` **alongside** the existing `CallbackButtonHandler`,
   not instead of it — an enquiry menu already delivered to a live chat
   before this release must still work when tapped.
4. The third static reply button (Delivery / Takeaway / *this one*) is
   renamed from the literal `"Enquiry"` to a configurable
   `RestaurantPresentation.enquiry_button_label`, default `"More options"`.
   It has no per-brand override on `RestaurantChoice` — nothing needs one.
5. `EnquiryOption.human_message` is capped at 100 characters. `SectionRow`'s
   `callback_data` is capped at 200 by Meta, and pywa does not validate this
   client-side — an over-length payload would fail silently at Meta only for
   the customer who taps that row. The `/SelectEnquiry` JSON envelope
   measures 90 chars with a 4-char `rest_ref`, so the cap leaves headroom.
6. An app may add its own option via a plain tuple splat —
   `options=(*DEFAULT_ENQUIRY_OPTIONS, EnquiryOption(...))` — not a merge
   helper or builder. ELAS adds **"Book a table"**.

### Dine-in reachability does not create a second guarded entry point

"Book a table" keeps `active_agent="triage_agent"`, exactly like every other
enquiry option. Its `human_message` ("I want to book a table") reaches
triage as a plain `HumanMessage`; triage's LLM calls `transfer_to_dinein`,
which is the **only** guarded entry to `dinein_agent` (ADR-0021) — it checks
`selection_pending`, then `dinein_available` (which honours
`RestaurantChoice.supports_dine_in`), then retained-specialist work, in that
order.

This was a deliberate choice, not the default. Setting
`active_agent="dinein_agent"` directly in the callback's `state_update_dict`
would also route — `route_initial` returns the state string verbatim — but
it would **bypass all three guards**: `dine_in.get_reservation_link` only
checks `ctx.reservation_base_url`, which ELAS sets app-wide, and writes
`rest_ref=ctx.rest_ref` (the invariant app identity), never
`selected_rest_ref`. A Wings and Things customer would receive a real
reservation link. Legacy `elai` avoided exactly this by hiding the button
for `chks` instead of guarding the transfer.

**Consequence accepted by the owner:** "Book a table" shows for both ELAS
brands, including Wings and Things (`supports_dine_in=False`).
`transfer_to_dinein`'s existing guard declines politely and offers delivery
or takeaway — this is free, not a new mechanism, and matches what ELAS's
triage prompt already said before this change.

### `_ENQUIRY_OPTION_MESSAGES` is deliberately not extended

`on_callback_handler._ENQUIRY_OPTION_MESSAGES` exists only to continue
`/SelectService` payloads minted before `/SelectEnquiry` existed. "I want to
book a table" never existed as a `/SelectService` payload, so no stale
button in any live chat can carry it — it only ever arrives via
`/SelectEnquiry`, which `select_enquiry_handler` already covers regardless
of update type.

## Consequences

- BNAT and SFCS customers now see the enquiry menu as a list, not reply
  buttons — one extra tap (open list, then pick a row) on a menu that
  previously fit in taps=1. Accepted: one code path, one set of tests, one
  rule in this ADR, rather than a conditional widget chosen by option count.
- The third button's label changes for every customer on all three numbers,
  from "Enquiry" to "More options" (app-overridable).
- Menu configuration remains code-owned; changes still require a
  coordinated release of all three apps from the same shared-runtime
  revision (unchanged from ADR-0015).
- A dine-in enquiry option requires the app to also configure
  `RestaurantPrompts.dinein` (ADR-0021) — otherwise triage has an intent
  with no tool to satisfy it. This is app-owner responsibility, documented
  in `docs/rules-to-update-prompt-files.md`, not something the runtime
  detects or enforces.
- Existing legacy enquiry callback payloads remain accepted by the
  `/SelectService` compatibility branch until no longer observed in active
  conversations (unchanged from ADR-0015).

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: EnquiryMenu
feature: sectionlist-enquiry-menus
description: >
  Widened to 1-10 EnquiryOption values with a button_title; EnquiryOption
  title/human_message/description validated against SectionRow's limits.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_wa_senders.py
symbol: select_enquiry_wa_send
feature: sectionlist-enquiry-menus
description: >
  Sends the app-owned enquiry menu as a WhatsApp SectionList instead of up
  to three reply buttons; the /SelectEnquiry payload shape is unchanged.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py
symbol: _register_whatsapp_handlers
feature: sectionlist-enquiry-menus
description: >
  Registers both a CallbackButtonHandler and a CallbackSelectionHandler for
  /SelectEnquiry so in-flight button menus and new SectionList rows both work.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py
symbol: transfer_to_dinein
feature: sectionlist-enquiry-menus
description: >
  Remains the only guarded entry to dinein_agent; an enquiry option reaches
  it only by keeping active_agent="triage_agent" and letting the LLM call
  this tool, never by setting active_agent="dinein_agent" directly.
```
