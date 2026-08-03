# ADR-0011: Load Settings at the Application Composition Root

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

Configuration modules previously fetched the shared AWS secret during import
and published process-global settings and database clients. Importing an
otherwise pure model or helper could therefore perform network I/O, select a
WABA namespace indirectly, or bind a service to a client outside the exact
`RestaurantRuntime`.

The constitutional application contract already has an explicit composition
root and requires one isolated runtime and WhatsApp client per application.
SFCS and BNAT must retain their existing `main:app` entrypoints and fail startup
when their selected namespace is incomplete.

## Decision

`load_settings_bundle(identity)` is the only shared configuration-loading
boundary. It fetches the configured AWS secret once, validates the selected
settings, constructs one `RestaurantSettingsBundle`, and loads only the WABA
namespace selected by `RestaurantIdentity`.

Configuration model modules are import-safe class definitions. They do not
fetch AWS data and do not publish process-global settings, pools, or Supabase
clients. Services receive settings and clients through `RestaurantRuntime`,
`ContextSchema`, or explicit function parameters.

Application entrypoints remain `sfcs_agent.main:app` and
`bnat_agent.main:app`. Creating either module-level app is still the explicit,
fail-fast startup composition event; this decision does not introduce a second
FastAPI factory convention.

## Consequences

- Ordinary imports no longer require AWS access or select application state.
- One settings fetch constructs one internally consistent runtime bundle.
- Exact runtime and database-client binding is visible in service signatures
  and testable without replacing configuration module globals.
- Startup still fails before serving traffic when the secret or selected WABA
  namespace is unavailable or incomplete.
- Process-local Restaurant/base-URL and deduplication caches are unchanged;
  their lifecycle remains coupled to the documented one-worker deployment.

## References

- `CONSTITUTION.md`
- `docs/adr/0003-one-isolated-runtime-and-whatsapp-client-per-application.md`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/config/bundle.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py`
- `tests/test_settings_bundle.py`
- `tests/test_aws_secret_name.py`
