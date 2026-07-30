# ADR-0005: Make FoodOrder the Authoritative Order Aggregate

- Status: Accepted
- Date: 2026-07-30
- Decision owners: Repository owner and maintainers

## Context

Order details appear in persisted FoodOrder records, incoming fulfilment
payloads, Threads, and LangGraph AgentState. Without an authority rule, runtime
conversation data can be mistaken for the order ledger. Delivery and takeaway
also risk becoming competing order models.

## Decision

Persisted `FoodOrder` data is authoritative for the order. `OrderItem` belongs
to the FoodOrder consistency boundary. Delivery and takeaway are fulfilment
variants of the same aggregate, not separate aggregates.

Thread and AgentState are runtime orchestration state. They may correlate to an
order and cache values needed for conversation flow, but they do not establish
order truth. `DeliverySummary` and `TakeawaySummaryData` are incoming workflow
contracts, not aggregates.

## Consequences

- Business decisions re-read or reconcile against persisted FoodOrder state
  when authority matters.
- Graph checkpoints cannot silently overwrite order records.
- Future order-model consolidation must preserve one aggregate identity across
  both fulfilment variants.
- Stringly typed legacy fields remain a documented cleanup item rather than an
  invented enum contract.

## References

- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_pymodel.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/delivery_pymodels.py`
- `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/takeaway_pymodels.py`
- `docs/to-do.md`
