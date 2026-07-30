# ADR-0001: Define the Platform Boundary and External Contexts

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

The repository coordinates customer conversations, Restaurant configuration,
orders, and incoming operational events, but it also communicates with systems
whose private workflows live elsewhere. Treating all connected systems as one
model would obscure ownership and encourage cross-repository coupling.

## Decision

`restaurant-agents` owns the independently deployed Restaurant Applications,
their shared Agent runtime, conversation orchestration, local customer and
Restaurant records, and FoodOrder data.

Meta WhatsApp, Ordelo/rider/takeaway fulfilment, payment services, and
maps/geocoding are external bounded contexts. This repository documents only
the commands, events, payloads, and authority visible at their boundaries.
PostgreSQL/Supabase, AWS Secrets Manager, and Fly are infrastructure providers,
not business bounded contexts.

## Consequences

- External payload types are contracts, not local aggregate roots.
- Private external workflows are not duplicated in this repository's domain
  documentation.
- Integration changes require contract tests and boundary documentation.
- Cross-system authority must be explicit before updating local projections.

## References

- `docs/domain/platform-domain-model.md`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/`
