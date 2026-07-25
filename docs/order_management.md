---
# Feature: Order Management
The order management subsystem handles the full lifecycle of food orders placed through WhatsApp, from creation through payment and receipt generation. It exists because the system evolved from a legacy psycopg-based path (OrderHandler) to a Supabase-backed path (FoodOrder), and both remain in use. The subsystem covers order ID generation, order item persistence, pricing calculation with fees, Stripe payment intent creation, and WhatsApp receipt formatting for both customers and restaurants.

---

## Human-Friendly Code Map
- [Legacy order DB operations and OrderHandler](./services/order_management/order_db_ops.py)
- [Supabase-backed FoodOrder model](./services/order_management/food_order_pymodel.py)
- [WhatsApp receipt generation](./services/order_management/food_order_reciept.py)
- [Delivery data models](./services/order_management/delivery_pymodels.py)
- [Takeaway data models](./services/order_management/takeaway_pymodels.py)
- [Order service helpers (min order, pricing)](./services/order_service.py)

### Detailed Flow Explanation

**Order Creation Path 1: Legacy psycopg (OrderHandler)**

1. `process_order_into_db` receives a psycopg connection pool, recipient, thread_id, and a pywa `Order` object from the WhatsApp catalog.
2. `OrderHandler.get_seq_num` calls the `get_next_daily_seq` PostgreSQL function to obtain a daily sequence number.
3. A `FoodOrderModel` is constructed with the recipient, total amount, thread_id, and seq_id. The `@model_validator` auto-generates an `order_id` by hashing the last 4 digits of the recipient phone number with a salt and the current date, producing a 4-character uppercase code suffixed with the sequence number (e.g. `ABCD-12`).
4. `OrderHandler.create_food_order` inserts the order row into the `FoodOrder` table via raw SQL.
5. `OrderHandler.insert_order_items` converts the pywa `Order` products into `OrderItem` models (enriching each with product name from the SKU map) and batch-inserts them into the `OrderItem` table.
6. `create_order_summary_from_db` re-fetches the order with items via a JOIN query and builds a summary dict suitable for Stripe payment intent creation.
7. `get_stripe_payment_link` posts the order summary to the Stripe microservice endpoint to obtain a payment URL.

**Order Creation Path 2: Supabase (FoodOrder)**

1. `FoodOrder.from_order_id` fetches a single row from the Supabase `food_order` table by order_id and hydrates a `FoodOrder` Pydantic model.
2. On instantiation, if `final_order_value` is None, `update_final_order_value_in_db` is called automatically to compute pricing.
3. `update_final_order_value_in_db` fetches customer coordinates from `customer_master`, calls the pricing microservice via `get_final_order_value`, and updates the `food_order` row with final_order_value, rest_cost, service_charge, delivery_fee, small_order_fee, and commission_rate.
4. `gen_payment_intent_payload` assembles the Stripe payment intent payload by fetching order items from the `order_item` table and appending non-zero fee line items (service charge, delivery fee, small order fee).
5. `gen_capture_payload` produces a capture-mode payload for post-authorization payment capture, including the restaurant payout amount and order notes.
6. The `payment_uri` property constructs the Stripe payment URL using the thread_id and order_id.

**Receipt Generation**

1. `build_wa_order_reciept_for_cust` generates a customer-facing WhatsApp receipt with item lines, service charge, delivery fee, small order fee, and total using `final_order_value`.
2. `build_wa_order_reciept_for_rest` generates a restaurant-facing receipt that omits service charge and delivery fee, showing only food total via `total_price` and small order fee if applicable.
3. Both functions return a `(header, text)` tuple formatted with WhatsApp markdown (`*bold*`, bullet `*` characters).

**Delivery and Takeaway Models**

1. `DeliveryDetail` captures full delivery routing data: restaurant and customer coordinates, rider assignment, dispatch ID, and generates a Google Maps navigation URL via its `google_maps_url` property.
2. `DeliverySummary` tracks delivery status with confirmation codes, pickup time, and timestamps for both restaurant and customer sides.
3. `DeliveryDispatch` models the rider assignment record with payout and distance.
4. `TakeawaySummaryData` tracks takeaway order status including restaurant confirmation, prep time, and pickup scheduling.
5. `TakeawayPickupTimePayload` bundles a `TakeawaySummaryData` with `RestaurantMasterData` for the pickup time webhook.

**Order Service Helpers**

1. `get_min_order_value` calls the Ordelo pricing endpoint with customer coordinates and restaurant reference to retrieve the minimum order value for delivery eligibility.
2. `_resolve_restaurant_coordinates` resolves restaurant lat/lon either from explicit parameters or by looking up the `restaurant_master` table using `rest_ref`.
3. `get_min_order_value_for_location` combines coordinate resolution with the pricing call to return a human-readable minimum order message.

### Code References (Machine-Readable)
file: services/order_management/order_db_ops.py
symbol: FoodOrderModel
feature: Order Management
description: >
  Legacy Pydantic model for food orders with auto-generated order IDs via salted hash of recipient phone and date, used with psycopg OrderHandler.

file: services/order_management/order_db_ops.py
symbol: OrderItem
feature: Order Management
description: >
  Pydantic model for individual order line items with order_id, product_name, quantity, and price.

file: services/order_management/order_db_ops.py
symbol: OrderHandler
feature: Order Management
description: >
  Legacy psycopg-based handler providing direct SQL operations for order creation, item insertion, sequence numbering, and payment status updates.

file: services/order_management/order_db_ops.py
symbol: process_order_into_db
feature: Order Management
description: >
  Orchestrates legacy order creation by generating a sequence number, building a FoodOrderModel, and inserting both the order and its items via OrderHandler.

file: services/order_management/order_db_ops.py
symbol: get_stripe_payment_link
feature: Order Management
description: >
  Fetches order summary from the database and posts it to the Stripe microservice to obtain a payment URL.

file: services/order_management/order_db_ops.py
symbol: create_order_items_from_order
feature: Order Management
description: >
  Transforms a pywa Order object into a list of OrderItem models, mapping SKU codes to product names via the SKU map.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder
feature: Order Management
description: >
  Supabase-backed Pydantic model for food orders with pricing breakdown fields, auto-pricing on instantiation, and Stripe payment intent/capture payload generation.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.from_order_id
feature: Order Management
description: >
  Class method that fetches a food order from the Supabase food_order table and ensures final_order_value is computed before returning.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.update_final_order_value_in_db
feature: Order Management
description: >
  Calculates final order value including fees by calling the pricing microservice with customer coordinates, then updates the database and instance fields.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.gen_payment_intent_payload
feature: Order Management
description: >
  Assembles a Stripe payment intent payload with order items and non-zero fee line items for payment creation.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.gen_capture_payload
feature: Order Management
description: >
  Generates a capture-mode payment payload including restaurant payout, total amount, and order notes.

file: services/order_management/food_order_reciept.py
symbol: build_wa_order_reciept_for_cust
feature: Order Management
description: >
  Generates a customer-facing WhatsApp receipt with items, fees, and final total formatted with WhatsApp markdown.

file: services/order_management/food_order_reciept.py
symbol: build_wa_order_reciept_for_rest
feature: Order Management
description: >
  Generates a restaurant-facing WhatsApp receipt showing only food items and total_price, omitting service and delivery charges.

file: services/order_management/food_order_reciept.py
symbol: _fetch_order_items
feature: Order Management
description: >
  Helper that retrieves order_item rows from Supabase for a given order_id, returning product_name, quantity, and price.

file: services/order_management/delivery_pymodels.py
symbol: DeliveryDetail
feature: Order Management
description: >
  Pydantic model for delivery routing data with restaurant/customer coordinates, rider assignment, and a google_maps_url property for navigation.

file: services/order_management/delivery_pymodels.py
symbol: DeliverySummary
feature: Order Management
description: >
  Pydantic model tracking delivery status with confirmation codes, pickup time, and timestamps for both parties.

file: services/order_management/delivery_pymodels.py
symbol: DeliveryDispatch
feature: Order Management
description: >
  Pydantic model for rider dispatch assignments with payout and distance fields.

file: services/order_management/takeaway_pymodels.py
symbol: TakeawaySummaryData
feature: Order Management
description: >
  Pydantic model for takeaway order tracking with restaurant confirmation status, prep time, pickup scheduling, and confirmation codes.

file: services/order_management/takeaway_pymodels.py
symbol: TakeawayPickupTimePayload
feature: Order Management
description: >
  Webhook payload model bundling TakeawaySummaryData with RestaurantMasterData for pickup time notifications.

file: services/order_management/takeaway_pymodels.py
symbol: RestaurantMasterData
feature: Order Management
description: >
  Pydantic model for restaurant master data including coordinates, address fields, and admin list used in webhook payloads.

file: services/order_service.py
symbol: get_min_order_value
feature: Order Management
description: >
  Async function that calls the Ordelo pricing endpoint with customer coordinates and restaurant reference to retrieve the minimum order value.

file: services/order_service.py
symbol: _resolve_restaurant_coordinates
feature: Order Management
description: >
  Resolves restaurant latitude/longitude from explicit parameters or by querying the restaurant_master table with rest_ref.

file: services/order_service.py
symbol: get_min_order_value_for_location
feature: Order Management
description: >
  Combines restaurant coordinate resolution with the pricing service call to return a human-readable minimum order value message.

### Edge Cases
- Order ID collision is mitigated by the salted hash using recipient phone, date, and daily sequence number, but two orders from the same phone on the same day rely on the sequence to differentiate.
- `FoodOrder.from_order_id` returns None if the order is not found or if `update_final_order_value_in_db` fails, so callers must handle None gracefully.
- Pricing service returning a non-dict response causes `update_final_order_value_in_db` to fail and return False, leaving `final_order_value` as None.
- Customer not found in `customer_master` during pricing lookup prevents final order value calculation; the order remains without computed fees.
- `_fetch_order_items` returns an empty list on database failure, causing `build_wa_order_reciept_for_cust` and `build_wa_order_reciept_for_rest` to raise ValueError.
- Receipt generation falls back to `total_price` when `final_order_value` is None, which may understate the customer-facing total.
- `get_stripe_payment_link` returns None on HTTP errors from the Stripe microservice, requiring the caller to handle missing payment URLs.
- Legacy `OrderHandler.insert_order_items` uses `executemany` without explicit transaction rollback, so a partial insert failure may leave orphaned order rows.
- `get_min_order_value` returns None on any HTTP or unexpected error, so the agent must handle missing minimum order values.
- Restaurant receipt omits service charge and delivery fee by design, showing only `total_price` to reflect the restaurant's food value payout.
