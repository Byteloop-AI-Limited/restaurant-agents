# ADR-0018: Retained Specialist Lifecycle and Service Selection

- Status: Accepted
- Date: 2026-08-13
- Decision owners: Repository owner and maintainers
- Amends: the customer `/reset` treatment described in ADR-0010's historical context

## Context

Delivery and takeaway ownership was represented by independently written
`active_agent` and `retain_thread` values in payment hooks, fulfilment hooks,
callback handlers, transfer tools, and prompt rendering. A no-rider terminal
event could therefore leave `active_agent="delivery_agent"` after clearing
retention. A later typed takeaway request was then left to the delivery model
instead of deterministically starting a new service flow.

## Decision

The shared runtime owns the AgentState projection of specialist lifecycle:

1. `retain_thread=True` means an in-progress specialist owns the conversation;
   customer-requested service handoffs are blocked.
2. External payment and fulfilment events remain authoritative. Terminal events
   notify through the specialist, then deterministically release to triage and
   clear order-scoped state even if notification fails.
3. Delivery timeout keeps the existing Thread active after release. Delivery
   completion and takeaway pickup-time confirmation release before the existing
   triage termination flow.
4. Callback buttons and typed explicit service requests use the same shared
   selection policy. Informational, status, cancellation, and negated messages
   remain model-owned.
5. `/reset` is an Overwatch-only operational escape hatch. Regular customers
   receive a fixed denial and cannot abandon a retained paid flow.

The persisted `retain_thread` boolean remains the compatibility contract for
LangGraph checkpoints and stale-thread processing; no flow-phase migration is
introduced.

Refund confirmation is an exception to model-owned broad support: the delivery
timeout producer supplies a `payment_cancelled` outcome, and the shared runtime
projects it as `is_payment_cancelled`. A refund-timing reply is deterministic
and confirms issuance only for a literal `True`; absent, false, malformed, or
unreadable state fails closed. `is_delivery_no_rider` preserves the separate
no-rider outcome without implying payment cancellation.

## Consequences

- Customer/profile state remains available after release, while order, payment,
  rider, reply, and delivery-calculation state is cleared.
- Selection is deterministic for canonical request phrases and aliases, but
  broad conversational interpretation remains with the active agent.
- Both restaurant applications inherit the behavior without new graph nodes,
  HTTP routes, database changes, or GraphAdapter methods.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/specialist_lifecycle.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/service_selection.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py`
