# Enquiry menu → WhatsApp SectionList, with an app-owned extra option

## Context

ELAS was onboarded with a `dinein_agent` (ADR-0021), but **the customer-facing WhatsApp flow
never offers it.** Dine-in is reachable only if the customer happens to type "book a table" —
triage's LLM then calls `transfer_to_dinein`. Nothing in the button flow surfaces it, because
the enquiry menu is capped at three reply buttons (ADR-0015) and ELAS already spends all three
on Share Feedback / Parking availability / Subscribe for offers.

WhatsApp reply buttons max out at 3. A **SectionList** (interactive list) allows 10 rows. That
is the mechanism that unblocks a 4th option.

**Intended outcome:** the first menu stays 3 static reply buttons — Delivery, Collection, and a
third renamed **"More options"** (today: `"Enquiry"`). Tapping it opens a SectionList. All apps
keep their own option set; ELAS adds **"Book a table"**, which reaches `dinein_agent` through
the *existing guarded* path.

### Decisions taken (owner, this session)

| | Decision |
| --- | --- |
| SFCS parking | Keep SFCS at **2 options**. Its omission is deliberate (ADR-0015) and its prompt answers typed parking questions with "We don't provide parking." |
| List scope | **Always** SectionList, all apps. BNAT/SFCS gain one extra tap on the enquiry menu only. |
| 3rd button label | **"More options"** — reads correctly both alongside Delivery/Collection and alone out of hours, when the other two are hidden. |
| CHKS "Book a table" | **Show it for both brands**; the existing guard declines politely for Wings and Things. No per-brand menu mechanism. |

---

## Design

### The safety property that makes this cheap

The owner's stated mechanism — *"these callbacks use a human msg… as good as human typing"* —
is also the **safe** one, and it is what avoids new machinery.

Every row (including "Book a table") keeps `active_agent="triage_agent"` and carries
`human_msg`. `_run_selected_enquiry` injects it as a `HumanMessage`; triage's LLM calls
`transfer_to_dinein`, which enforces all three guards in order: `selection_pending` →
`dinein_available` → retained-specialist work.

> **Do not** set `active_agent="dinein_agent"` in the callback's `state_update_dict`. It *would*
> route (`route_initial` returns the state string verbatim) but **bypasses all three guards** —
> `dine_in.get_reservation_link` only checks `ctx.reservation_base_url`, which ELAS sets
> app-wide. A Wings and Things customer would receive a real reservation link. This is exactly
> the shape legacy `elai` used, which is why it had to hide the button for `chks` instead.

Because the guarded path is preserved, `RestaurantChoice.supports_dine_in=False` on CHKS is
honoured for free: `dinein_unsupported_block` redirects to triage, which explains and offers
delivery/takeaway. ELAS's triage prompt **already** says exactly this (rule 5). So
`EnquiryOption` needs **no** `active_agent` field.

Verified prerequisite: `_run_selected_enquiry` merges only `{"rest_ref", "active_agent"}`, so a
previously captured `selected_rest_ref` survives — that merge is the one link that is an
assumption rather than a read, and it gets a dedicated test.

### Per-app extra options = tuple splat, not a framework

Export `DEFAULT_ENQUIRY_OPTIONS` (the 3 commons); an app composes
`options=(*DEFAULT_ENQUIRY_OPTIONS, EnquiryOption("Book a table", "I want to book a table"))`.
Plain Python. `CONSTITUTION.md` forbids new contribution abstractions — no merge helper, no
builder, no registry.

---

## Implementation

### 1. `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py`

**`EnquiryOption`** — title cap `20 → 24` (SectionRow limit); add `description: str | None = None`
(strip, empty → `None`, ≤72); add a `human_message` cap.

The `human_message` cap is the load-bearing new validation. `SectionRow.callback_data` is capped
at **200** by Meta and pywa passes it through with **no client-side check** — an over-length
payload fails at the Meta API only for the customer who taps that row. Measured: the
`/SelectEnquiry` JSON envelope is exactly **90** chars with a 4-char `rest_ref`, leaving **110**.
Use a module constant capped at **100** with the arithmetic in a comment. Longest current
`human_message` is 41 chars, so nothing existing breaks.

**`EnquiryMenu`** — cap `1..3 → 1..10`; update the error string (a test matches
`"between one and three"`). Add `button_title: str = "Options"` (≤20) and reuse it as the single
`Section`'s title rather than adding a second knob. No `header`/`footer` fields.

**Constants** — extract `DEFAULT_ENQUIRY_OPTIONS`, then define `DEFAULT_ENQUIRY_MENU` from it.

**`RestaurantPresentation`** — add `enquiry_button_label: str = "More options"` beside the other
two labels; validate ≤20 in the existing `__post_init__`. Do **not** add a per-brand
`RestaurantChoice` override — nothing needs it, and its absence is what makes step 4 principled.

Export `DEFAULT_ENQUIRY_OPTIONS` from `restaurant_agent_runtime/__init__.py`.

### 2. `rest_agent/agent_wa_senders.py`

- Extract `build_enquiry_callback_data(rest_ref, option) -> str` as the single source of truth for
  the `/SelectEnquiry` payload — keeps `action` / `rest_ref` / `active_agent="triage_agent"` /
  `human_msg` **byte-identical** to today, so in-flight button menus keep working.
- Rewrite `select_enquiry_wa_send` (`:155-181`) to emit one `SectionRow` per option → one
  `Section` → one `SectionList`, sent via `send_message(text=menu.prompt, buttons=section_list)`.
  Fix the now-stale docstring ("WhatsApp permits at most three").
- `select_service_wa_send` (`:40-91`): add an `enquiry_button_label` keyword param and replace the
  bare `"Enquiry"` literal at **`:86`**. **Do not touch `human_msg="I have an enquiry"` at `:79`** —
  it is the routing key matched at `on_callback_handler.py:182`; changing it breaks every
  already-delivered service button.

### 3. Thread `enquiry_button_label` through the graph context

`agents/agent_harness.py` `ContextSchema` (add field) → `agent_runner.py` `ContextSchema(...)`
construction → `agents/triage.py` **all three** `select_service_wa_send` call sites (`:106`,
`:168`, `:310`). Missing one yields a menu whose third button disagrees with the others.

### 4. `watomation/on_callback_handler.py`

- `select_restaurant_handler` (`:309`) and `select_service_handler`'s resend (`:218`): pass
  `enquiry_button_label=runtime.presentation.enquiry_button_label`.
- At `:218` pass **only** the enquiry label. That call site already omits
  `delivery_button_label`/`takeaway_button_label` (pre-existing defect, already in `docs/to-do.md`);
  fixing those needs a `selected_rest_ref` state read this path doesn't have. `enquiry_button_label`
  has no per-brand override, so presentation-level *is* its complete answer. **Add an inline comment**
  so nobody "tidies" it by adding the other two.
- `_ENQUIRY_OPTION_MESSAGES` (`:42-49`): **unchanged**. Add a one-line comment recording why
  "I want to book a table" is deliberately absent — that frozenset exists only for stale
  `/SelectService` payloads minted before `/SelectEnquiry`, and a brand-new option never existed
  as one.

### 5. `web/app_factory.py`

Import `CallbackSelectionHandler`. **Keep** the existing `CallbackButtonHandler` for
`/SelectEnquiry` (in-flight menus in live chats) and **add** a `CallbackSelectionHandler` with the
same `bound_enquiry` callback and the same `filters.contains("/SelectEnquiry")`.

Verified safe: pywa computes exactly one handler type per update, so the two never double-fire;
`filters.contains` works on `CallbackSelection` (`_txt_fields == ("data",)`); `wa_dedup` reads only
`update.id`, which `CallbackSelection` has.

### 6. Apps and prompts

- **`apps/elas/.../identity.py`** — `options=(*DEFAULT_ENQUIRY_OPTIONS, EnquiryOption("Book a table",
  "I want to book a table"))`, plus a `button_title`. No `description` on the booking row: an
  "Elai only" subtitle would render for Elai customers too.
- **`apps/bnat/.../identity.py`** — switch to `options=DEFAULT_ENQUIRY_OPTIONS` (byte-identical to
  today). **`apps/sfcs/.../identity.py`** — unchanged 2 options.
- **Triage prompts only** (verified: the six delivery/takeaway/dinein prompts have no enquiry wording):
  - All three: replace the `"Enquiry"` literal with `"More options"` (bnat `:20`, sfcs `:18`, elas `:30`).
  - ELAS `:30` — add booking a table to the named topic list.
  - ELAS `:29` (rule 5) — append that a table-booking request calls `transfer_to_dinein` **in the
    same turn, with no preamble, even when it arrives as a chosen menu option.** This is the cheap
    mitigation for the one real risk below.

### 7. Documentation

| File | Change |
| --- | --- |
| `docs/adr/0023-sectionlist-enquiry-menus.md` | **New, supersedes ADR-0015.** The 1–3 cap is in 0015's *Decision* text, and `docs/adr/README.md` has no "amended" status — supersede, don't rewrite. Restate carry-forwards (app-owned menus, `/SelectEnquiry`, always-enter-triage, "not a general callback registry"); add the 10-row cap, SectionList widget, `CallbackSelection` handler, retained button handler, and — referencing ADR-0021 — that **`transfer_to_dinein` remains the only guarded entry to `dinein_agent`.** |
| `docs/adr/0015-*.md` | Header status → Superseded by ADR-0023. Body untouched. |
| `docs/adr/README.md` | 0015 → Superseded; add the 0023 row. |
| `docs/webhook_endpoints.md` | Extend the "Callback Button Title Length" section to SectionRow: title ≤24, description ≤72, callback_data ≤**200** (vs Button's 256), `button_title` ≤20, ≤10 rows total. State that pywa does **not** enforce callback_data length, which is why `EnquiryOption` caps `human_message`. Also: enquiry now registers both a button and a selection handler. |
| `docs/rules-to-update-prompt-files.md` | `:55` "three-button maximum" → ten-row maximum. `:60` cap statement → split 20 vs 24. Add the ADR-0023 invariant that a dine-in enquiry option requires the app to configure `prompts.dinein`, or triage has an intent with no tool. |
| `docs/glossary.md` | Enquiry Menu / Enquiry Option: 1–10, SectionList, `button_title`, `description`. Fix the "every button title … capped at 20" line, which now excludes `EnquiryOption.title` (24). |
| `docs/multi_agent_system.md` | Enquiry-menu descriptions; `ask_user_to_select_enquiry` sends a list; realign the `EnquiryMenu` `code-ref` block. |
| `docs/to-do.md` | (a) deterministic dine-in fallback with the observation criterion that would trigger it; (b) the `select_service_handler:218` delivery/takeaway label gap. |

`CONSTITUTION.md` needs **no** amendment — app-owned presentation config plus a widget/handler
swap inside the shared runtime; no new node, state key, or composition boundary.

---

## Tests

**`tests/watomation/test_enquiry_callbacks.py`** — `test_enquiry_menu_rejects_more_than_whatsapp_allows`
becomes 11 options with an updated `match=`; add an accepts-ten test.
`test_enquiry_sender_uses_the_app_owned_menu` **changes shape**: `kwargs["buttons"]` is now a single
`SectionList`, not an iterable of `Button`s — assert the type, `button_title`, row titles, and
`'"action":"/SelectEnquiry"'` in each row's `callback_data`. Add: a `CallbackSelection`-shaped update
through `select_enquiry_handler`; a description round-trip; `human_message` over-budget rejection;
title ≤24. **Keep** `test_specific_enquiry_callback_runs_triage_directly` — the button path must
still work.

**Highest-value new test — CHKS taps "Book a table".** Seed `selected_rest_ref="CHKS"` **before** the
enquiry callback, run `transfer_to_dinein` against ELAS's real `RESTAURANT_SELECTION` and
`reservation_base_url`, assert `dinein_unsupported_block` fires. Seeding beforehand is what proves
`selected_rest_ref` survives `_run_selected_enquiry`'s merge. Place near
`tests/rest_agent/test_restaurant_selection.py`.

**Handler registration** — assert both handler types are registered for `/SelectEnquiry`, and prove
it by calling the handler's check against a `CallbackSelection`-shaped update; asserting the object
exists is not enough.

**`tests/rest_agent/test_agent_wa_senders.py`** — `"Enquiry"` → `"More options"` at `:65,:90,:112,:125`;
add an app-owned-label test.

**Presentation doubles needing the new field:** `tests/rest_agent/test_core_adapter.py`,
`tests/rest_agent/agents/test_triage_agent.py`, `tests/watomation/test_restaurant_selection_callback.py`,
`tests/rest_agent/test_agent_wa_senders.py`.

**App tests:** ELAS identity → 4 titles incl. "Book a table" with exact `human_message`;
BNAT/SFCS → add an `enquiry_button_label` assertion, option lists unchanged.

---

## Verification

```bash
uv run ruff check .
uv run pytest tests
uv run pytest apps/sfcs/tests apps/bnat/tests apps/elas/tests
uv run pytest            # full suite
git diff --check
```

Plus the offline composition smoke (`tests/test_runtime_isolation.py` pattern): construct all three
apps with fake clients; assert no `ValueError` from the new caps and both `/SelectEnquiry` handler
types registered.

Shared-runtime change ⇒ per `CONSTITUTION.md` all three apps build from **one commit and one root
lockfile**, release in **one window**, and **all three roll back** if any check fails.

Owner-authorized WhatsApp canary (ELAS, Overwatch recipient): new thread → pick a restaurant →
first menu shows Delivery / Takeaway / **More options** → tap it → SectionList with 4 rows → tap
**Book a table** → for Elai a reservation link arrives; for Wings and Things triage politely
declines and offers delivery/takeaway.

---

## Risks

| # | Risk | Mitigation |
| --- | --- | --- |
| R1 | **"Book a table" is the first enquiry option needing a handoff to another node** — the other three are satisfied by tools already on triage. If the LLM prose-answers instead of transferring, the customer is stuck. This repo has a documented production case of a system-message instruction not being followed (`select_restaurant_handler`'s docstring). | Degraded, not looping: the existing anti-loop `SystemMessage` prevents re-showing the menu. Hardened at prompt level (§6). `docs/to-do.md` records the escalation to a deterministic transfer with its observation criterion. |
| R2 | Third button label changes on every customer's first message on all three numbers. | Owner-chosen ("More options"); per-app override exists. |
| R3 | BNAT/SFCS gain a tap on a menu that fit in buttons. | Owner-accepted; conditional rendering is the escape hatch if drop-off appears. |
| R4 | Already-delivered button menus stop working. | Existing `CallbackButtonHandler` retained; payload byte-identical. |
| R5 | Over-length `callback_data` fails silently at Meta for one row. | `EnquiryOption.__post_init__` cap fails at import. |
| R6 | CHKS customers see "Book a table" and are refused. | Deliberate, owner-chosen. Guard + prompt produce a polite redirect. |

## Commit sequence

1. Core: `EnquiryMenu`/`EnquiryOption` widening + `enquiry_button_label` + SectionList sender +
   handler registration, with tests. BNAT/SFCS green.
2. Apps: ELAS "Book a table", BNAT `DEFAULT_ENQUIRY_OPTIONS`, prompt edits, app tests.
3. Docs: ADR-0023, supersede 0015, and the doc table above.
