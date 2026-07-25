# Rules to Update Prompt Files

This reference defines how to update multi-agent prompt files consistently for the WhatsApp assistant.

## Scope
- Default scope: multi-agent prompts only
  - `rest_agent/agents/prompts/triage_agent_prompt.md`
  - `rest_agent/agents/prompts/delivery_multiagent_prompt.md`
  - `rest_agent/agents/prompts/takeaway_agent_prompt.md`
- Legacy single-agent prompts are out of scope unless explicitly requested.

## Core Behavioral Rules

### 1) Service Selection Is Mandatory (Prompt-Level)
- Triage must verify the customer's service intent (delivery, takeaway, or inquiry) before proceeding.
- If service intent is not clearly known from state/system messages/conversation, triage must call:
  - `ask_user_to_select_service`
- Do not guess service intent.

### 2) Immediate Transfer for Explicit Specialized Intent
- If user explicitly asks for delivery -> `transfer_to_delivery`
- If user explicitly asks for takeaway/collection -> `transfer_to_takeaway`
- If user explicitly asks for dine-in/table booking/reservation -> triage handles it as unsupported; specialist agents call `transfer_to_triage`
- Use tool-first behavior; avoid extra pre-transfer clarification if intent is explicit.

### 3) General Queries Stay in Triage
- For complaints, parking, contact info, unsatisfactory service, events, and similar non-specialized intents:
  - Answer directly in triage
  - Do not transfer unless the user explicitly requests a specialized service

### 4) Inquiry Button Handling
- The third top-level service option is `Inquiry`.
- Selecting `Inquiry` activates triage with `HumanMessage("Inquiry")`.
- Triage asks one concise direct question to understand the inquiry.

### 5) Single Restaurant Language
- The system operates for a single restaurant (SFC - Southern Fried Chicken Salisbury).
- Refer to the restaurant by name when appropriate; no branch disambiguation is needed.

## Prompt Writing Rules (GPT-4.1-mini)
- Use deterministic instruction order:
  1. Non-negotiable rules
  2. Decision ladder
  3. Tool usage map
  4. Output style
  5. Examples
  6. Negative examples
- Reduce ambiguity and conflicting instructions.
- Prefer short, imperative sentences.

## Output Style Rules (WhatsApp)
- Keep responses concise and operational.
- Prefer one short line for simple replies.
- If multiple points are required, use bullet points.
- Avoid long paragraphs.

## Consistency Checklist Before Finalizing Prompt Changes
- [ ] Triage gate behavior is explicit and hard to misread.
- [ ] Transfer rules are immediate for explicit service intent.
- [ ] General-query handling remains in triage.
- [ ] Number and text equivalents are both supported for fallback menus.
- [ ] Style guidance is concise and WhatsApp-appropriate.
- [ ] Tool names exactly match implemented tools.
- [ ] No legacy prompt files were edited unless explicitly requested.

## Change Log Template (Optional)
- Date:
- Prompt files updated:
- Behavior changes:
- Risks noted:
- Follow-up needed:
