# ADR-0012: Restore the `/paid3100` Payment Simulation

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers
- Supersedes: ADR-0010

## Context

ADR-0010 removed `/test`, `/test-t`, and `/paid3100` from the standard
WhatsApp surface. The repository owner subsequently confirmed that the
payment-completion simulator is still operationally required. The two
hard-coded order-reset commands are not required.

The former `/paid3100` implementation found the sender's latest order requiring
payment and posted a Stripe-shaped completion payload to the external Ordelo
payment hook, but it captured database configuration globally.

## Decision

Restore `/paid3100` and `simulate_payment_complete` in the shared WhatsApp
handler set for both Restaurant Applications. Keep `/test` and `/test-t`
removed.

The simulator must use the exact `RestaurantRuntime` database client to:

1. Resolve the configured Ordelo base URL.
2. Find the sender's latest `food_order` row.
3. Continue only when that row has `payment_status="requires_payment"`.
4. POST the existing Stripe-shaped payload to
   `/payment-hooks/payment-complete` without following redirects.

If no eligible order exists, send `No order requiring payment found.` and make
no external payment-hook call. Do not restore module-global settings or
hard-coded order identifiers.

## Consequences

- `/paid3100` is intentionally a side-effecting production WhatsApp command;
  invoking it may advance the sender's external payment/order workflow.
- The command operates only on the sender's latest eligible order and does not
  accept an arbitrary order identifier.
- Both applications expose the same shared behavior with their own exact
  runtime dependencies.
- `/test` and `/test-t` remain unavailable.
- Automated coverage must mock the database and HTTP boundary. Live invocation
  remains outside the offline validation gate.

## References

- `docs/adr/0010-remove-live-whatsapp-simulation-commands.md`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py`
- `tests/test_whatsapp_diagnostics.py`
