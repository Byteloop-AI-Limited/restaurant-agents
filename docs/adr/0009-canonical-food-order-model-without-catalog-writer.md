# ADR-0009: Canonicalize Ordering Without an Internal Catalog Writer

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

The shared runtime contains two inactive order-writing modules:
`order_db_ops.py` and `order_db_ops_new.py`. They model different schemas,
calculate totals differently, capture database clients and settings globally,
and have no production callers. The only live dependency on either module is
the newer `OrderItem` value imported by receipt formatting.

SFCS and BNAT do not need to create WhatsApp catalog orders inside this runtime
in the foreseeable application scope. Active payment and order-event flows use
the persisted `FoodOrder` aggregate and its line items.

## Decision

`FoodOrder` remains the canonical order aggregate and `OrderItem` remains its
canonical line-item value. `OrderItem` will live in a model module independent
of any database writer.

Delete both inactive order-writing modules and their writer-specific tests.
Keep focused model, receipt, and integration-boundary contract tests for
behavior used by the active applications.

Do not introduce a replacement order repository, database writer, or direct
WhatsApp catalog-order handler without a concrete application consumer. If
direct catalog-order creation becomes required, design it as a separate command
flow with an injected database dependency and explicit aggregate invariants.

This decision does not transfer order authority to the external payment or
fulfilment contexts. Persisted `FoodOrder` data remains authoritative under
ADR-0005.

## Consequences

- Competing legacy/new writer schemas and pricing semantics are removed rather
  than merged speculatively.
- Receipt formatting imports `OrderItem` from the canonical model module.
- Dormant order-reference generation, insert, rollback, and legacy payment-link
  behavior are deleted because no live application invokes them.
- A future catalog-order creation flow requires a deliberate design decision
  and contract tests; it must not restore module-global settings or clients.

## References

- `docs/adr/0005-food-order-is-the-authoritative-order-aggregate.md`
- `docs/domain/platform-domain-model.md`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_pymodel.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_reciept.py`
