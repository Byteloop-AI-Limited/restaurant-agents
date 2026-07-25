---
# Feature: Payment System
The Elai payment system integrates Stripe for customer payments on food orders placed through WhatsApp. It handles the full payment lifecycle: pricing calculation based on customer location, payment intent generation with manual capture mode, webhook processing when Stripe confirms payment, receipt generation for both customer and restaurant views, and final capture or cancellation of authorized payments. The system uses a two-phase payment pattern (authorize then capture) so funds are only captured after delivery confirmation or restaurant acknowledgment.

---

## Human-Friendly Code Map
- [Payment microservice (Stripe integration)](./services/payment_ms/payment.py)
- [FoodOrder Pydantic model](./services/order_management/food_order_pymodel.py)
- [Pricing logic](./services/pricing_ms/pricing_logic.py)
- [Order receipt generation](./services/order_management/food_order_reciept.py)
- [Order event hooks (payment-complete webhook)](./watomation/routers/order_event_hooks.py)
- [Stripe payment hooks (TBD)](./watomation/routers/payment_hooks_tbd.py)

### Detailed Flow Explanation

**1. Pricing Calculation**
1. When a customer places an order, the system calculates the final order value including all fees.
2. `FoodOrder.update_final_order_value_in_db()` fetches the customer's lat/lon from the `customer_master` table.
3. It calls `get_final_order_value()` in `pricing_logic.py`, which posts order details (order number, food value, restaurant coordinates, customer coordinates) to the external pricing microservice at `ms_settings.pricing_url`.
4. The pricing microservice returns delivery options by vehicle type; the system selects the `car` option.
5. The pricing response contains a breakdown with `final_order_value`, `rest_cost`, `service_charge`, `delivery_fee`, `small_order_fee`, and `commission_rate`.
6. These values are persisted to the `food_order` table and updated on the `FoodOrder` instance.

**2. Payment Intent Generation**
1. When the agent determines the order is ready for payment, it creates a `FoodOrder` instance via `FoodOrder.from_order_id()`, which auto-calculates the final order value if not already set.
2. `generate_payment_intent()` in `payment.py` is called with the `FoodOrder` instance.
3. The `FoodOrder.gen_payment_intent_payload()` method builds the Stripe payload: queries `order_item` table for product line items, appends fee items (service charge, delivery fee, small order fee) filtering out zero-value fees, and sets `currency: GBP`, `action: delivery`, `manual_mode_capture: True`.
4. The payload is POSTed to the Stripe integration endpoint at `{stripe_url}/threads/{thread_id}/orders/{order_id}/payment-url` with `ms_settings.stripe_headers` for authentication.
5. On success, a payment URL is returned to the customer via WhatsApp for checkout.
6. On failure, `None` is returned and the error is logged.

**3. Stripe Payment Webhook Processing (Two Paths)**

*Path A: Via `payment_hooks_tbd.py` (Stripe direct webhook)*
1. Stripe sends a `payment-complete` webhook to `POST /payment-hooks/payment-complete` (currently not registered in the app router).
2. `payment_complete_path` extracts the JSON body and delegates to `handle_payment_complete` via `BackgroundTasks`.
3. `handle_payment_complete` extracts `orderID` from `data.object.metadata.orderID` in the Stripe event payload.
4. Updates `food_order.payment_status` to `requires_capture` in Supabase.
5. Invokes `run_elai_graph_with_custom_msg` to tell the agent to verify payment completion.

*Path B: Via `order_event_hooks.py` (Ordelo-mediated webhook)*
1. The Ordelo payment service calls `POST /order-event-hooks/{rest_ref}/payment-complete/{recipient}/{thread_id}` with a `FoodOrder`-shaped body.
2. Validates `rest_ref` against RestaurantMaster, and checks that `recipient` and `thread_id` in the URL match the body.
3. Generates a WhatsApp receipt using `build_wa_order_reciept_for_cust()`.
4. For delivery orders: sends the receipt message to the customer, then runs a background graph update setting `is_payment_successful=True`, `retain_thread=True`, and populating `order_id`, `order_number`, and `reply_to_msg_id`.
5. For takeaway orders: sends receipt with pickup time notice, then runs background graph update with the same state flags. The graph is instructed to thank the user and confirm the pickup time.

**4. Receipt Generation**
1. `build_wa_order_reciept_for_cust()` generates a customer-facing receipt. It fetches order items from the `order_item` table and formats them as `quantity x product_name - price`.
2. Fee lines (service charge, delivery fee, small order fee) are appended if non-zero.
3. The total reflects `final_order_value` (including all fees) or falls back to `total_price`.
4. Notes are appended if present.
5. Returns a tuple of `(header, text)` formatted for WhatsApp markdown (`*bold*` for emphasis, `bullet` for items).
6. `build_wa_order_reciept_for_rest()` generates a restaurant-facing receipt that omits service charge and delivery fee, showing only the food value (`total_price`) and small order fee if applicable.

**5. Payment Capture**
1. After delivery is confirmed (rider customer confirmation code verified), `capture_payment()` is called.
2. `FoodOrder.gen_capture_payload()` builds the capture request with `action`, `payment_mode: capture`, `rest_payout` (restaurant's share), `total_amount` (final order value), order item summary, and notes.
3. The payload is POSTed to the same Stripe integration URL used for intent creation.
4. A successful capture returns an empty response body (checked via `res.text == ""`).

**6. Payment Cancellation**
1. When a delivery times out (no driver available) or is otherwise cancelled, `cancel_payment()` is called.
2. Posts `action: delivery, payment_mode: cancel` to the Stripe integration endpoint.
3. A successful cancellation returns an empty response body.
4. The customer is notified that their payment will be released.

### Code References (Machine-Readable)

file: services/payment_ms/payment.py
symbol: get_payment_uri
feature: Payment System
description: >
  Constructs the Stripe integration URL for a given order using thread_id and order_id, pointing to the payment-url endpoint.

file: services/payment_ms/payment.py
symbol: generate_payment_intent
feature: Payment System
description: >
  Creates a Stripe payment intent by posting the FoodOrder's intent payload to the Stripe integration endpoint, returning the payment URL or None on failure.

file: services/payment_ms/payment.py
symbol: cancel_payment
feature: Payment System
description: >
  Cancels a Stripe payment intent for a given order by posting a cancel payload to the payment URL, returning True on success.

file: services/payment_ms/payment.py
symbol: capture_payment
feature: Payment System
description: >
  Captures an authorized Stripe payment intent for a given order by posting a capture payload to the payment URL, returning True on success.

file: services/payment_ms/payment.py
symbol: generate_order_summary_for_payment_intent
feature: Payment System
description: >
  Standalone function that builds an order summary with product items and fee items for payment intent creation, querying order_item table from Supabase.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder
feature: Payment System
description: >
  Pydantic model representing a food_order row, providing methods for DB fetch, pricing calculation, payment intent/capture payload generation, and payment URI construction.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.from_order_id
feature: Payment System
description: >
  Class method that fetches a food_order from Supabase by order_id and auto-calculates final_order_value if not already set.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.update_final_order_value_in_db
feature: Payment System
description: >
  Fetches customer location, calls pricing microservice, updates the food_order row with breakdown values, and syncs instance attributes.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.payment_uri
feature: Payment System
description: >
  Property that generates the Stripe payment URL using the order's thread_id and order_id.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.gen_payment_intent_payload
feature: Payment System
description: >
  Generates the Stripe payment intent payload with order items, fee items, GBP currency, and manual_mode_capture flag.

file: services/order_management/food_order_pymodel.py
symbol: FoodOrder.gen_capture_payload
feature: Payment System
description: >
  Generates the payment capture payload including items, action, rest_payout, total_amount, and notes for final settlement.

file: services/pricing_ms/pricing_logic.py
symbol: get_final_order_value
feature: Payment System
description: >
  Calls the external pricing microservice with order and location data, selects the car delivery option, and returns the pricing breakdown dict.

file: services/order_management/food_order_reciept.py
symbol: _fetch_order_items
feature: Payment System
description: >
  Helper that retrieves order_item rows (product_name, quantity, price) from Supabase for a given order_id.

file: services/order_management/food_order_reciept.py
symbol: build_wa_order_reciept_for_cust
feature: Payment System
description: >
  Generates a customer-facing WhatsApp receipt with item lines, fee charges, total, and notes formatted in WhatsApp markdown.

file: services/order_management/food_order_reciept.py
symbol: build_wa_order_reciept_for_rest
feature: Payment System
description: >
  Generates a restaurant-facing WhatsApp receipt showing only food items and total_price, omitting service charge and delivery fee.

file: watomation/routers/order_event_hooks.py
symbol: payment_complete
feature: Payment System
description: >
  Webhook endpoint that processes payment completion, validates path/body consistency, sends WhatsApp receipt, and updates graph state with payment success flags.

file: watomation/routers/payment_hooks_tbd.py
symbol: handle_payment_complete
feature: Payment System
description: >
  Processes Stripe payment webhook by extracting orderID from metadata, updating payment_status to requires_capture, and triggering graph payment verification.

file: watomation/routers/payment_hooks_tbd.py
symbol: payment_complete_path
feature: Payment System
description: >
  FastAPI route that receives Stripe payment-complete webhooks and delegates to handle_payment_complete via BackgroundTasks.

### Edge Cases
- `FoodOrder.from_order_id` returns `None` if the order is not found or if `update_final_order_value_in_db` fails, preventing payment intent generation.
- Customer not found in `customer_master` table -> pricing calculation fails, `update_final_order_value_in_db` returns `False`.
- Pricing microservice returns non-dict response (e.g., error string with min_order_value message) -> update is rejected and logged.
- `generate_payment_intent` HTTP error (4xx/5xx from Stripe integration) -> returns `None`, logged; customer is not sent a payment link.
- `cancel_payment` or `capture_payment` HTTP failure -> returns `False`, logged; may require manual intervention.
- `payment_complete` endpoint receives mismatched `recipient` or `thread_id` between URL and body -> HTTP 400.
- Order items query returns empty list -> `build_wa_order_reciept_for_cust` raises `ValueError`; receipt cannot be generated.
- Fee items with zero or `None` price are filtered out of both payment intent payloads and receipt display.
- `payment_hooks_tbd` router is defined but not registered in the main app; Stripe webhooks are currently handled through the Ordelo-mediated `order_event_hooks` path.
- `capture_payment` has a hardcoded `total_amount: 14.97` in the standalone function (legacy); the `FoodOrder.gen_capture_payload` method uses the actual `final_order_value`.
- Delivery timeout triggers `cancel_payment` flow, releasing authorized funds back to the customer.
