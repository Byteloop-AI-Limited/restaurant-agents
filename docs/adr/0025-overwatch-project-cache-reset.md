# ADR-0025: Overwatch Project Cache Reset and URL Diagnostics

- Status: Accepted
- Date: 2026-08-22
- Decision owners: Restaurant platform owner and maintainers

## Context

`OperationalLookupCache` keeps application URLs for up to one hour. Operators
need to inspect the effective Ordelo and Restaurant Application URLs from a
WhatsApp conversation, then recover promptly after a corrected
`ordelo_config` value without invoking internal HTTP routes by hand.

The existing reset route clears one process only. A Restaurant Application
cannot safely assume that a public URL reaches every deployed replica, and
ELAS's restaurant choices are not independent applications.

## Decision

The shared runtime exposes the cached `ORDELO_APP_URL`, `BNAT_APP_URL`,
`SFCS_APP_URL`, and `ELAS_APP_URL` through `GET /details`, WhatsApp `/detail`,
and WhatsApp `/debug`. `/detail` and `/debug` are Overwatch-only; diagnostics
remain sanitized and never reveal raw credentials or exception text.

Overwatch-only `/reset-cache` force-refreshes the configured BNAT, SFCS, and
ELAS URLs from `ordelo_config`, then sends one best-effort `POST` with
`scope=all` to each application's existing `/internal/cache/reset` route. It
continues after individual missing URLs or HTTP failures and reports one
sanitized result per application. It accepts no WhatsApp arguments.

The target set is the fixed deployed application set, not customer-facing
restaurant choices. The internal reset route retains its existing local scope,
authentication convention, and `app_ref` contract.

## Consequences

- Corrected URLs are used immediately for reset fan-out, rather than waiting
  for the caller's cached URL to expire.
- Each target receives one public-route request. Multi-instance deployments
  still need per-instance reset coverage or their normal TTL expiry.
- The shared Operational Lookup Cache may resolve the fixed project app URLs;
  its public internal reset route still permits targeted `app_ref` only for
  Ordelo, Restaurant Menu, and the running application's own reference.
- New Restaurant Applications require an explicit update to the fixed project
  target and diagnostics lists, this ADR's successor if the policy changes,
  and focused tests.

## References

- [ADR-0016](0016-runtime-owned-operational-lookup-cache.md)
- [Operational Lookup Cache](../caching_system.md)
- [Webhook Endpoints](../webhook_endpoints.md)
