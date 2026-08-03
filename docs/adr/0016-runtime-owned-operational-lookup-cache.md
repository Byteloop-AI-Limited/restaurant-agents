# ADR-0016: Keep Operational Lookup Caches Runtime-Owned

- Status: Accepted
- Date: 2026-08-03
- Decision owners: Restaurant platform owner and maintainers

## Context

Handlers and Agent tools repeatedly read Ordelo application URLs,
`RestaurantMaster`, and the Overwatch allowlist. The prior cache was a
module-global dictionary, the Overwatch list was hard-coded, and documented
reset paths did not exist. Those choices could cross app boundaries within a
worker and made urgent operational changes difficult to apply.

## Decision

`create_restaurant_app` constructs one `OperationalLookupCache` from the exact
runtime database client and stores it on `RestaurantRuntime`. The cache owns
only application URLs (60 minutes), `RestaurantMaster` (5 minutes), and
`ordelo_config.overwatch_list` (5 minutes). It uses a monotonic TTL and
per-key cold-load locking; failures, missing values, negative results, and
stale data are never cached.

Overwatch is sourced exclusively from the database and fails closed. The shared
factory exposes unauthenticated `POST /internal/cache/reset` for the current
process with explicit scopes. It returns counts only. Transactional domain
records remain uncached.

## Consequences

- SFCS and BNAT receive isolated cache instances with their own database client.
- URL, operational-master, and operator-list changes take effect by TTL or
  targeted reset; all replicas must be reset independently if deployed.
- The public deployment perimeter, rather than application authentication,
  must protect the internal reset convention.
- New cache candidates require a separate authority, freshness, and failure
  decision; this ADR does not authorize caching transactional data.
