# Feature: Order Management

The shared runtime consumes persisted food orders; it does not create catalog
orders. `FoodOrder` is the canonical order aggregate and `OrderItem` is its
canonical line-item value, as decided by ADR-0005 and ADR-0009. The external
ordering/payment path persists the aggregate before calling the runtime's order
event endpoint.

## Human-Friendly Code Map

- [FoodOrder aggregate](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_pymodel.py)
- [OrderItem value](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/order_item_pymodel.py)
- [WhatsApp receipt formatting](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_reciept.py)
- [Delivery records](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/delivery_pymodels.py)
- [Takeaway records](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/takeaway_pymodels.py)
- [Minimum-order lookup](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_service.py)
- [Payment-complete order event](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py)

## Active Flow

1. An external ordering/payment context persists a `food_order` record and its
   `order_item` rows.
2. The payment-complete integration posts the persisted aggregate to
   `POST /order-event-hooks/{rest_ref}/payment-complete/{recipient}/{thread_id}`.
3. The route validates the restaurant prefix and confirms that the recipient
   and thread in the URL match the `FoodOrder` body before any side effect.
4. Receipt formatting fetches line items with the exact database client from
   the selected `RestaurantRuntime`.
5. The customer receives a delivery or takeaway receipt, and the graph is
   updated with the payment result, order identifiers, and retained-thread
   state.

There is no shared catalog-order command, order-reference generator, direct
order insert, automatic pricing mutation, or payment-payload method on
`FoodOrder`. A future internal writer requires a separate design with explicit
aggregate invariants and an injected persistence dependency.

## Aggregate and Receipt Contracts

`FoodOrder` is a pure Pydantic boundary model. It validates the persisted order
identity, customer/thread correlation, fulfilment action, food total, optional
fee breakdown, and payment status. Constructing it performs no database or
network I/O.

`OrderItem` represents a persisted line item. Restaurant receipt callers may
provide validated `OrderItem` values directly; otherwise receipt formatting
loads the rows through an explicit database client.

- Customer receipts show food items, applicable service/delivery/small-order
  charges, notes, and `final_order_value` (falling back to `total_price`).
- Restaurant receipts omit customer service and delivery charges and show the
  food total. They include the small-order fee when present.
- Missing line items are a contract error and raise `ValueError`; the runtime
  does not invent an empty receipt.

## Delivery, Takeaway, and Minimum Order

`DeliveryDetail`, `DeliverySummary`, and `DeliveryDispatch` model fulfilment
data reported through the delivery flow. `TakeawaySummaryData` and
`TakeawayPickupTimePayload` model preparation and pickup events. These are
integration records; the external fulfilment context remains authoritative.

`get_min_order_value` calls the configured Ordelo endpoint with customer
coordinates and the restaurant reference. Its database client is explicit and
is used only to resolve the restaurant-specific base URL. HTTP or response
errors return `None` for the agent to handle.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_pymodel.py
symbol: FoodOrder
feature: order-management
description: >
  Pure canonical FoodOrder aggregate used at persistence and integration boundaries.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/order_item_pymodel.py
symbol: OrderItem
feature: order-management
description: >
  Canonical persisted line-item value independent of any order writer.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_reciept.py
symbol: build_wa_order_reciept_for_cust
feature: order-management
description: >
  Builds the customer WhatsApp receipt using the exact injected database client.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_management/food_order_reciept.py
symbol: build_wa_order_reciept_for_rest
feature: order-management
description: >
  Builds a restaurant receipt from provided OrderItems or an injected database client.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: order-management
description: >
  Validates and processes the external payment-complete FoodOrder event.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_service.py
symbol: get_min_order_value
feature: order-management
description: >
  Calls the restaurant Ordelo pricing endpoint using an injected database client.
```

## Edge Cases

- Cross-restaurant paths return `404` before database, graph, or WhatsApp work.
- URL/body recipient or thread mismatches are rejected before sending a receipt.
- Missing order items prevent receipt generation.
- A missing `final_order_value` makes the customer receipt display
  `total_price`; upstream persistence owns fee calculation.
- Minimum-order lookup failure returns `None`; it does not mutate the order.
