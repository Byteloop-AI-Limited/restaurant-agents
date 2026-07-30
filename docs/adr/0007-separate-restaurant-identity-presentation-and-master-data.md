# ADR-0007: Separate Restaurant Identity, Presentation, and Master Data

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

The word Restaurant refers to deployment routing, customer-facing branding, and
mutable operational data. Combining those concerns would allow database changes
to alter security boundaries or force static branding into operational tables.

## Decision

- `RestaurantIdentity` is immutable and app-owned. It contains `rest_ref` and
  WABA namespace for routing and configuration isolation.
- `RestaurantPresentation` is immutable and app-owned. It contains display
  name, contact number, and logo URL.
- `RestaurantMaster` is the persisted source of truth for mutable operational
  data, including address, coordinates, administrators, service hours, and
  operational settings.

These concepts may share `rest_ref` but are not interchangeable.

## Consequences

- Runtime route validation uses RestaurantIdentity, not a database lookup for
  arbitrary valid Restaurants.
- Branding changes remain app changes unless the architecture is deliberately
  amended.
- Operational updates do not change the deployed application's identity.
- The glossary must qualify “Restaurant” when the distinction matters.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/ordelo_service/datamodels/restaurant_master_pymodel.py`
- `apps/sfcs/src/sfcs_agent/identity.py`
- `apps/bnat/src/bnat_agent/identity.py`
