# ADR-0017: Ordelo-owned Feedback Admin Notifications

- Status: Accepted
- Date: 2026-08-06
- Decision owners: Restaurant platform owner
- Supersedes: ADR-0014

## Context

ADR-0014 introduced an Ordelo-owned notification path for customer
"complaints." In practice customers use the same enquiry path to report
praise and suggestions, not only problems, and "complaint" reads as
negatively connoted in customer-facing copy. The repository owner decided to
rename the concept to "feedback" end to end: customer copy, agent prompts,
internal code symbols, and the shared HTTP contract with `OrdeloAgent`.

Because the endpoint path and request/response shape are part of the
`restaurant-agents` / `OrdeloAgent` contract, the rename requires a
coordinated, hard-cutover release across both repositories: there is no
endpoint alias, so `OrdeloAgent` and `restaurant-agents` (SFCS and BNAT) must
deploy from the same release window.

## Decision

Rename "complaint" to "feedback" across both repositories:

- Customer-facing enquiry button title: `"Customer complaint"` →
  `"Share feedback"` (14 characters, within WhatsApp's 20-character reply
  button limit); intent copy: `"I want to make a customer complaint"` →
  `"I want to share feedback"`.
- Triage prompts explicitly welcome any sentiment — praise, suggestions, or
  problems — and route all of it through the `submit_restaurant_feedback`
  tool. `description` keeps its existing `min_length=5` validation; no
  sentiment-based relaxation.
- Tool and model rename in `restaurant-agents`:
  `submit_restaurant_complaint` → `submit_restaurant_feedback`,
  `RestaurantComplaintRequest` → `RestaurantFeedbackRequest`,
  `OrdeloService.submit_restaurant_complaint` →
  `OrdeloService.submit_restaurant_feedback`.
- Endpoint and model rename in `OrdeloAgent`:
  `POST /customer-hooks/restaurant-complaints` →
  `POST /customer-hooks/restaurant-feedback` (hard cutover — the old route is
  removed, not aliased), `RestaurantComplaintRequest` →
  `RestaurantFeedbackRequest`, `send_restaurant_complaint_notification` →
  `send_restaurant_feedback_notification`, `_notify_complaint_admins` →
  `_notify_feedback_admins`.
- Generated identifier prefix: `CMP-XXXXXXXXXXXX` → `FDB-XXXXXXXXXXXX`.
- `_ENQUIRY_OPTION_MESSAGES` in `restaurant-agents` holds only the new intent
  string; in-flight legacy buttons carrying the old string degrade through
  the existing triage rule that avoids re-opening the enquiry menu once a
  topic is named, rather than through a compatibility entry.

Because `restaurant-agents/AGENTS.md` requires SFCS and BNAT to ship from the
same revision, the runtime, both apps, their prompts, and their tests are
renamed together in one commit. `OrdeloAgent` ships from a separate repo and
must deploy in the same coordinated window: `OrdeloAgent` first (new route
live), then `restaurant-agents` immediately after, with both sides ready to
roll back if the other fails its health check.

## Consequences

- No endpoint alias exists. A misordered or delayed deploy causes in-flight
  `submit_restaurant_feedback` calls to `404` until both sides are live;
  mitigated by staging the cutover in a non-prod environment first.
- Single-word praise (e.g. "Good") still fails the unchanged `min_length=5`
  validation; the agent is expected to ask for a few more words rather than
  relax validation.
- Customers holding an already-delivered legacy button may see the enquiry
  menu re-open, or reach triage without the suppression system message;
  triage rule 4 already prevents re-opening the menu once a topic is named,
  so this degrades gracefully.
- Persisted conversation threads may retain `submit_restaurant_complaint` in
  completed tool-call history; completed calls are inert, and the exposure
  window for a pending old-name call at deploy time is the sub-second graph
  run itself.
- ADR-0014 is superseded but retained for history per the append-only ADR
  convention.

## References

- `docs/adr/0014-ordelo-owned-complaint-admin-notifications.md`
- `docs/glossary.md`
- `docs/domain/platform-domain-model.md`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/triage.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/ordelo_service/ordelo_service.py`
- `OrdeloAgent/watomation/routers/customer_hooks.py`
- `OrdeloAgent/utils_common/waba_utils/wa_senders.py`
