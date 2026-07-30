# ADR-0010: Remove Live WhatsApp Simulation Commands

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

The standard WhatsApp handler set registers `/test`, `/test-t`, and
`/paid3100` in both production Restaurant Applications. These commands contain
hard-coded diagnostic order data and can write to the database or call an
external HTTP endpoint. They are neither ordinary customer behavior nor safe,
read-only production diagnostics.

`/reset` has a distinct customer-facing purpose: it starts a new conversation
Thread. `/debug` reads graph state and already rejects callers outside the
authorized-user set.

## Decision

Remove `/test`, `/test-t`, and `/paid3100` from the standard shared WhatsApp
handler surface and delete their shared implementations.

Keep `/reset` as a customer-accessible Thread-lifecycle command, using the
database dependency belonging to the exact `RestaurantRuntime`. Keep `/debug`
as a read-only diagnostic command gated by the existing authorized-user rule.

If an application later needs payment or order simulation, it must own that
diagnostic behavior, keep it disabled by default, and provide explicit safety
and authorization controls. Simulation is not a shared production-runtime
capability.

## Consequences

- Standard application assembly no longer exposes hard-coded order reset or
  payment-completion simulations through WhatsApp.
- Removing the commands eliminates their direct module-global database clients
  and external-call paths.
- Thread reset and graph debugging remain available without broadening the
  shared extension contract.
- Future simulations require application-owned composition and focused tests.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py`
- `docs/adr/0003-one-isolated-runtime-and-whatsapp-client-per-application.md`
- `docs/webhook_endpoints.md`

