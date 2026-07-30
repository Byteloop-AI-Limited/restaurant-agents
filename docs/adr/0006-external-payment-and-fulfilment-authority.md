# ADR-0006: Treat External Payment and Fulfilment State as Authoritative

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

Payment and fulfilment state crosses multiple boundaries and is represented in
external services, FoodOrder fields, webhook payloads, and AgentState. The
platform needs an explicit precedence rule for reconciliation and conversation
updates.

## Decision

Payment authority is:

```text
External payment system > FoodOrder.payment_status > AgentState runtime cache
```

Fulfilment authority is:

```text
External Ordelo/rider/takeaway workflow > FoodOrder fulfilment projection
> AgentState runtime cache
```

Webhook payloads report external facts. The platform validates them, updates
the appropriate persisted projection, and then nudges conversation state.

## Consequences

- Agent tools do not originate successful payment or fulfilment facts.
- Local projections must be reconcilable with external providers.
- Duplicate or out-of-order events require idempotent boundary handling where
  the contract permits it.
- Runtime state may lag but may not override persisted or external authority.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/rider_event_hooks.py`
- `docs/payment_system.md`
- `docs/webhook_endpoints.md`
