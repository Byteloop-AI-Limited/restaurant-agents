# ADR-0024: Per-Brand Enquiry Rows and Tool-Response-Only Transfer Guards

- Status: Accepted
- Date: 2026-08-18
- Decision owners: Restaurant platform owner
- Supersedes: [ADR-0023](0023-sectionlist-enquiry-menus.md)

## Context

ADR-0023 shipped ELAS's fourth enquiry row, "Book a table", visible to both
brands behind ELAS's single WhatsApp number — ELAS/"Elai"
(`supports_dine_in=True`) and CHKS/"Wings and Things"
(`supports_dine_in=False`) — and relied on `transfer_to_dinein`'s guard to
decline politely for CHKS.

That decision failed in production. Selecting "Book a table" as a CHKS
customer crashed with:

```
langgraph.errors.InvalidUpdateError: Node toolNode does not exist
```

The failure chain had three links, all confirmed in source:

1. The guard, `dinein_unsupported_block`, returned
   `Command(graph=Command.PARENT, goto="triage_agent", update={"messages":
   [ToolMessage(...), SystemMessage(...)]})`. Exiting to the parent graph
   and re-entering the *same node* that still had a pending tool call
   persisted an out-of-order tail — the customer's checkpointed trace showed
   the `SystemMessage` landing **before** its `ToolMessage`.
2. `_find_malformed_tool_call_tail` (`agent_runner.py`) correctly detected
   that tail on the next message: an `AIMessage` with a pending tool call
   immediately followed by a non-`ToolMessage` reads as a missing tool
   response, even though a `ToolMessage` exists later in the list.
3. The repair path then called `aupdate_state(..., as_node="toolNode")`.
   **No node named `toolNode` has ever existed** in this graph — the real
   nodes are `triage_agent`, `delivery_agent`, `takeaway_agent`,
   `dinein_agent`. The repair itself raised, turning a recoverable malformed
   tail into a hard crash.

`selection_required_block` — fired when no brand has been chosen yet, on
the main delivery/takeaway ordering path, not just dine-in — had the
identical shape and the identical latent defect, just not yet observed in
production.

## Decision

**Hide "Book a table" for Wings and Things instead of relying on a guard to
decline it after the tap.** `EnquiryOption` gains
`only_for_rest_refs: tuple[str, ...] | None = None`; `None` (the default)
means visible to every brand, matching every existing menu unchanged.
`EnquiryMenu.visible_options_for(selected_rest_ref)` filters rows at render
time. `EnquiryMenu.__post_init__` requires at least one always-visible
option, so no configuration can produce an empty SectionList (a zero-row
list fails at the Meta API for the one customer who taps it).

ELAS's "Book a table" now carries `only_for_rest_refs=("ELAS",)`.

**Both render paths must resolve the same brand, or ELAS's two paths
disagree.** The primary path is not the LLM tool: the "More options" button
is minted as `/SelectService` with `human_msg="I have an enquiry"`, so
tapping it lands in `select_service_handler`'s enquiry branch
(`on_callback_handler.py`), not `ask_user_to_select_enquiry`. That branch
now reads `selected_rest_ref` via `graph_adapter.debug_state_values`,
mirroring `route_service_selection`'s existing precedent for a state read at
this same callback boundary, including degrading to unrestricted rows only
if the read fails. `ask_user_to_select_enquiry` (the secondary,
model-invoked path) reads `state["selected_rest_ref"]` directly, since it
already has `InjectedState`. Both pass through `select_enquiry_wa_send`,
which is the single place `EnquiryMenu.visible_options_for` is applied — so
the two paths agree by construction.

**A guard that blocks a transfer answers its own tool call and ends its own
node's turn — never `Command.PARENT` back into the calling node, never a
trailing `SystemMessage`.** This is now the rule for every transfer guard in
the shared runtime, established by two already-proven shapes:

- `dinein_unsupported_block` is deleted. `transfer_to_dinein` returns a
  **plain string** when dine-in is unsupported. LangChain's tool node wraps
  a returned string into a `ToolMessage` and assigns the originating call's
  `tool_call_id` itself — the id is correct by the framework, not by hand.
  `triage.py`'s `send_welcome_message`/`ask_user_to_select_service` and
  `delivery.py`'s `answer_general_query` already return bare strings from
  tools; this is not a new pattern. Because it mutates no state, it also
  cannot evict a retained specialist the way the old `active_agent` write
  could.

  `supports_dine_in`/`dinein_available` survive as this guard's condition.
  Hiding the enquiry row only removes the *button* path — a CHKS customer
  can still type "book a table", and `delivery.py`'s typed-intent branch
  reaches the same guard. Deleting the flag outright would mean that
  customer receives a live Elai reservation link.

- `selection_required_block` is reshaped to send the restaurant-selection
  buttons directly and end its turn with `goto=END`, no `Command.PARENT`,
  mirroring `ask_user_to_select_restaurant` and `retained_handoff_block` —
  both already live in production with this exact shape. It becomes `async`
  and takes the tool's `ctx` instead of only a `tool_call_id`.

`agent_runner.py`'s `_repair_malformed_tool_call_tail` no longer passes
`as_node="toolNode"`. `Pregel.aupdate_state`'s own contract is that an
omitted `as_node` resolves to the last node that wrote state — exactly what
this repair wants. A malformed tail from any future cause is now repaired
instead of crashing.

### Two mechanisms for per-brand variation now exist

`RestaurantChoice` already carries four per-brand override fields
(`delivery_promo_caption`, `takeaway_promo_caption`, `delivery_button_label`,
`takeaway_button_label`), each resolved by a `resolve_*(state, selection,
fallback)` function. This ADR adds a second, different mechanism:
`EnquiryOption.only_for_rest_refs` filters *rows within one shared menu*,
rather than swapping in a whole per-brand menu. The owner chose this over a
`RestaurantChoice.enquiry_menu` override to avoid maintaining two full
`EnquiryMenu` literals for what is, today, a single restricted row.

**Use `RestaurantChoice`'s override pattern when an entire value differs per
brand** (a caption, a label, a URL). **Use `EnquiryOption.only_for_rest_refs`
when a shared list needs some rows hidden for some brands.** If a future app
needs the *entire* enquiry menu to differ by brand (different prompt,
different button title, not just a subset of rows), that is a
`RestaurantChoice.enquiry_menu` override, not an extension of
`only_for_rest_refs`.

## Consequences

- CHKS/Wings and Things customers see a 3-row enquiry menu; Elai customers
  see 4 rows. `RestaurantPresentation.enquiry_menu` is still configured with
  all 4 options in one place (`apps/elas/src/elas_agent/identity.py`); only
  rendering filters.
- `select_service_handler`'s enquiry branch adds one `debug_state_values`
  round-trip before every enquiry menu send, wrapped in the same
  `try/except` degradation `route_service_selection` already uses on the
  sibling delivery/takeaway button path.
- `dinein_unsupported_block` no longer exists. `transfer_to_dinein`'s return
  type widens from `Command` to `Command | str`.
- A malformed message tail (from any cause, not just this one) is now
  silently repaired rather than crashing. `logger.warning("Repairing
  malformed tool-call tail before model invoke")` is the only remaining
  signal that a guard produced a bad tail — it should not appear in
  production logs at all if every guard follows this ADR's rule.
- SFCS and BNAT are unaffected: they never set `only_for_rest_refs`, so
  `visible_options_for` is the identity for their menus.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: EnquiryOption
feature: per-brand-enquiry-rows
description: >
  Adds only_for_rest_refs (normalized, empty tuple rejected) and
  is_visible_for; EnquiryMenu adds visible_options_for and requires at
  least one always-visible option.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_wa_senders.py
symbol: select_enquiry_wa_send
feature: per-brand-enquiry-rows
description: >
  Filters rows via menu.visible_options_for(selected_rest_ref) — the single
  choke point both render paths pass through.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py
symbol: select_service_handler
feature: per-brand-enquiry-rows
description: >
  The primary "More options" render path now reads selected_rest_ref via
  graph_adapter.debug_state_values before sending the enquiry SectionList,
  degrading to unrestricted rows on a failed read.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/restaurant_selection.py
symbol: selection_required_block
feature: per-brand-enquiry-rows
description: >
  Reshaped from a Command.PARENT + SystemMessage redirect to a direct send
  plus goto=END, mirroring ask_user_to_select_restaurant. dinein_unsupported_block
  deleted; transfer_to_dinein returns a plain string instead.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py
symbol: _repair_malformed_tool_call_tail
feature: per-brand-enquiry-rows
description: >
  No longer passes as_node="toolNode" (a node that never existed in this
  graph) to aupdate_state; omitting it lets LangGraph infer the writing node.
```
