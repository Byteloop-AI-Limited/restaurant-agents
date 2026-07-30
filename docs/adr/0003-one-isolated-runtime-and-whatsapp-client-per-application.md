# ADR-0003: Construct One Isolated Runtime and WhatsApp Client per Application

- Status: Accepted
- Date: 2026-07-29
- Decision owners: Repository owner and maintainers

## Context

Module-global clients and fallback WABA configuration can route messages or
side effects through the wrong Restaurant identity. Handlers, routers, services,
and Agent tools must agree on one application context.

## Decision

`create_restaurant_app()` loads exactly the requested WABA namespace, constructs
one async and one sync WhatsApp client, and creates one `RestaurantRuntime`.
The exact runtime and async client flow through handlers, routers, graph
adapters, `ContextSchema`, services, and tools.

Restaurant-prefixed routes must match `RestaurantIdentity.rest_ref` and return
`404` before graph calls, background work, or external side effects when they do
not match.

## Consequences

- No module-global WhatsApp clients are permitted.
- Startup fails on incomplete namespaced WABA configuration.
- Runtime-isolation and cross-Restaurant rejection require tests across both
  applications.
- One worker per app remains part of the runtime contract.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py`
- `tests/test_runtime_isolation.py`
