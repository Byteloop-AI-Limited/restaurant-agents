# Rules to Update Restaurant Agent Prompt Files

This reference defines how to change application-owned prompts without
duplicating or bypassing the shared Restaurant Agent runtime.

See [the multi-agent system overview](./multi_agent_system.md),
[the interactive composition guide](./guides/agent-runtime-composition.html),
and [the governing decision record](./architecture/shared-agent-runtime-decisions.md)
for the surrounding architecture.

## Scope and Ownership

Every application owns three complete prompt files:

```text
apps/<app>/src/<app>_agent/rest_agent/prompts/
  triage_agent_prompt.md
  delivery_multiagent_prompt.md
  takeaway_agent_prompt.md
```

An app that configures the optional standard dine-in node (ADR-0021) owns a
fourth file, `dinein_agent_prompt.md`, in the same directory. Its presence is
what activates the `dinein_agent` node; an app that omits it never constructs
that node or reaches `transfer_to_dinein`.

Current applications:

- SFCS: `apps/sfcs/src/sfcs_agent/rest_agent/prompts/`
- BNAT: `apps/bnat/src/bnat_agent/rest_agent/prompts/`
- ELAS: `apps/elas/src/elas_agent/rest_agent/prompts/` — the first app with a
  fourth (`dinein_agent_prompt.md`) file and the first to configure
  `RestaurantPresentation.restaurant_selection` (ADR-0020), so its triage
  prompt also carries a restaurant-selection gate that SFCS and BNAT do not.

The shared runtime owns agent construction, state, routing, middleware, and
standard tools. It does not own prompt fragments and does not merge a shared
base prompt with an application override. `agent_recipe.py` reads all
configured prompt files (three, or four when dine-in is enabled) into
`RestaurantPrompts` during module import.

## Decide the Change Boundary First

| Desired change | Correct location |
| --- | --- |
| Wording, restaurant policy, tone, or tool-use instruction | App-owned prompt file |
| Standard Enquiry button labels and callback intent | App-owned `RestaurantPresentation.enquiry_menu` |
| Add a native capability to one existing node | App-owned tool plus `extra_tools_by_agent` |
| Replace one complete standard node | App-owned runnable plus `agent_overrides` |
| Add a graph node or change state/routing/handoffs | App-owned `GraphAdapter` |
| Add a WhatsApp callback or API route | Native PyWa handler or FastAPI router in app assembly |

Do not ask a prompt to call a tool that the selected node does not expose. Do
not copy a shared agent module into an application to make a prompt change.
Keep an Enquiry Menu to WhatsApp's ten-row SectionList maximum (ADR-0023).
For a genuinely new callback workflow, use an app-owned native PyWa handler
instead of extending the standard menu into a callback registry.

Every button title configured through `RestaurantPresentation` or
`RestaurantChoice` (including a discount suffix like `"(20% off)"`) is
capped at 20 characters; `EnquiryOption.title` (a SectionList row, not a
button) is capped at 24. Both are validated at construction time — see
[Callback Button and List-Row Title Length](webhook_endpoints.md#callback-button-and-list-row-title-length).

An enquiry option that requires a handoff to a different standard node (for
example ELAS's "Book a table", which reaches `dinein_agent`) must keep
`active_agent="triage_agent"` like every other option — never set the
target node's name directly — and the app must configure the matching
`RestaurantPrompts` field (`dinein` for a dine-in option) so triage actually
has a tool that can satisfy the intent. See ADR-0023.

## Cross-App Change Rules

- A restaurant-specific policy or identity change updates only the owning app.
- A standard behavioral change intended for SFCS and BNAT must review both
  apps' complete prompts and the shared graph/tool contract together.
- Do not import or reuse another app's prompt file.
- Keep prompts app-owned even when two applications currently contain identical
  text.
- Restart the application after a prompt edit; the recipe loads prompt text at
  import time.

## Core Behavioral Rules

### 1. Service selection is mandatory

- Triage must establish delivery, takeaway/collection, or inquiry intent before
  proceeding.
- If intent is not clear from state, system messages, or conversation, call
  `ask_user_to_select_service`.
- Do not guess service intent.
- When a customer has asked a completed direct question, answer or acknowledge
  that question first by passing the complete customer-facing text as
  `message_before_selection`. The tool sends that text before its service
  buttons and ends the turn.
- Do not show the service menu while collecting missing feedback details,
  waiting for an enquiry/consent choice, or transferring to a specialist.

### 2. Explicit specialized intent transfers immediately

- Delivery intent -> `transfer_to_delivery`
- Takeaway or collection intent -> `transfer_to_takeaway`
- Unsupported dine-in, booking, or reservation intent stays in triage; a
  specialist returns it with `transfer_to_triage`.
- Prefer the transfer tool without unnecessary pre-transfer prose.

### 3. General queries stay in triage

Feedback, parking, contact details, events, and similar non-ordering questions
remain in triage unless the customer explicitly requests a specialized service.

### 4. Enquiry selection stays in triage

The third static service button (`RestaurantPresentation.enquiry_button_label`,
default "More options") activates `triage_agent` and opens the app's
`EnquiryMenu` SectionList (ADR-0023). Triage should ask one concise question
when the enquiry is not yet clear. An option whose fulfilment requires a
different node (a dine-in booking option, for example) still activates
`triage_agent` — the LLM transfers from there via the normal guarded tool,
never by targeting the other node directly.

### 5. Restaurant identity must match the owning app

- Use the restaurant name, contact details, service policy, and locality that
  belong to the selected application.
- Do not leave SFCS/Salisbury wording in BNAT prompts or BNAT wording in SFCS
  prompts.
- Do not change `rest_ref`, WABA namespace, or presentation values in prompt
  text; those belong in the app's identity and settings composition.
- For an app that configures `restaurant_selection` (currently ELAS only), use
  the `{selected_restaurant_name}` template variable rather than a literal
  brand name anywhere the prompt states which restaurant is active — the
  shared runtime resolves it to "not yet selected" before a choice is
  captured, so a literal brand name in that spot renders as a false
  statement. See ADR-0020 and `prompt_runtime.py`.

## Prompt Writing Rules

Use a deterministic instruction order:

1. Non-negotiable rules
2. Decision ladder
3. Tool-usage map
4. Output style
5. Examples
6. Negative examples

Prefer short imperative instructions, remove conflicts, and keep tool names
identical to the implementation.

## WhatsApp Output Style

- Keep simple replies to one short line where practical.
- Use bullets only when multiple points are needed.
- Avoid long paragraphs and internal implementation language.
- Do not emit extra text after a tool-only handoff instruction. When a tool
  sends both a reply and interactive buttons, place the complete reply in the
  documented tool argument instead of producing a separate model response.

## Validation Checklist

- [ ] The edited file belongs to the intended app.
- [ ] All three prompts for that app remain non-empty.
- [ ] Restaurant identity and policies match the owning app.
- [ ] Triage service-selection behavior remains explicit.
- [ ] Specialized transfers use exact implemented tool names.
- [ ] General queries remain in triage.
- [ ] Every referenced tool exists on that standard node or is supplied through
      `extra_tools_by_agent`.
- [ ] No shared runtime module or other app prompt was copied.
- [ ] The app's composition test still proves prompt loading and exact runtime
      binding.
- [ ] If behavior is intended to be common, both apps and shared contract tests
      were reviewed.

## Relevant Validation

For a prompt-only change, run the complete app package test suite for each app
whose prompt changed, then the repository documentation/static checks required
by the task. Cross-app standard behavior changes require both app suites and the
shared runtime suite.

## Change Log Template

- Date:
- Application:
- Prompt files updated:
- Behavior changes:
- Tool-contract impact:
- Cross-app review:
- Risks:
- Follow-up:
