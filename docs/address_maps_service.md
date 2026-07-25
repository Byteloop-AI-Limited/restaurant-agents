---
# Feature: Address and Maps Service
The address and maps service resolves customer delivery addresses using the Google Geocoding API, captures them through WhatsApp interactive flows, and validates delivery area eligibility. It exists to convert postcodes or coordinates into structured UK addresses, persist them in the customer_master table, and feed coordinates into the pricing service for minimum order value and delivery fee calculations. The flow spans from WhatsApp address capture forms through geocoding resolution to graph state updates that gate the ordering process.

---

## Human-Friendly Code Map
- [AddressResolver and UKAddress model](./services/maps_service/address_resolver.py)
- [WhatsApp address senders (confirm, postcode flow, update)](./rest_agent/agent_wa_senders.py)
- [Callback handler for address confirmation](./watomation/on_callback_handler.py)
- [Postcode search flow handler (archived reference)](./utils_common/archive/on_flow_request_postcode_search.py)
- [Postcode search WhatsApp Flow definition](./utils_common/wa_flows/flow_postcode_search.py)
- [Order service (min order value, coordinate resolution)](./services/order_service.py)

### Detailed Flow Explanation

**Address Resolution via Google Geocoding**

1. `AddressResolver` is initialized with a Google Maps API key from `google_settings` and exposes the Google Geocoding API endpoint.
2. `get_address_from_postcode` formats a UK postcode (uppercase, space-separated), sends a geocoding request with `", UK"` suffix, and parses the response into a `UKAddress` model. Latitude and longitude are extracted from the first result's geometry.
3. `get_address_from_coordinates` performs reverse geocoding using lat/lon with result type filtering for `street_address|premise|subpremise` to get detailed address results.
4. `_parse_geocode_response` maps Google address component types to UKAddress fields: `street_number` to house_number, `route` to street_name, `premise`/`subpremise` to building_name, `postal_town`/`locality` to city, `administrative_area_level_2` to county, and `postal_code` to postcode.
5. The `UKAddress` model validates postcodes via `@field_validator`, stripping spaces, uppercasing, and inserting a space before the last 3 characters.
6. A module-level singleton `address_resolver` is exported for use throughout the application.

**Address Capture via WhatsApp Flow**

1. The delivery agent tool `capture_delivery_address` (or `update_address_of_existing_user`) triggers `send_postcode_search_flow` from `agent_wa_senders.py`, which sends a WhatsApp FlowButton pointing to the `PostcodeSearchElai` flow.
2. The flow is a two-screen interactive form defined in `flow_postcode_search.py`: the START screen accepts a postcode or street name search query, and the ADDRESS screen displays resolved address fields (house number, building, street, city, postcode) for user confirmation.
3. On the START screen submission, `on_ip_pc` calls `address_resolver.get_address_from_postcode` to resolve the input and populates the ADDRESS screen with the result, including lat/lon for downstream use.
4. When the user confirms the ADDRESS form, `on_pc_search_complete` fires. It constructs a `CustomerMaster` record and upserts it into the Supabase `customer_master` table.
5. The handler then updates the LangGraph state via `run_elai_graph_with_custom_msg` with `customer_address`, resets `min_order_value` to None (forcing recalculation), and sets `is_delivery_address_confirmed` to True.

**Address Confirmation via Callback Buttons**

1. The delivery agent tool `confirm_delivery_address` calls `confirm_delivery_address_wa`, which sends a WhatsApp interactive message displaying the stored address with "Yes" and "Update" buttons.
2. The address is formatted from the `customer_address` state dict fields: house_number, building, street_name, city, and postcode.
3. Button callbacks are routed by `fapp.py` to `delivery_address_confirmation` in `on_callback_handler.py` via the `/ConfirmDeliveryAddress` action filter.
4. If the user clicks "Yes", the handler sets `is_delivery_address_confirmed: True` in the graph state and re-enters the graph with the confirmation message.
5. If the user clicks "Update", the handler sets `is_delivery_address_confirmed: False` and injects a SystemMessage instructing the agent to call `update_address_of_existing_user`, which re-triggers the postcode search flow.

**Alternative Address Update Path**

1. `send_update_address_wa` provides a URL-based address update option via a `ButtonUrl` pointing to the Ordelo web app (`restaurant.ordelo.app/address-update`) with the recipient and rest_ref as query parameters.

**Delivery Area Validation**

1. After address confirmation, the delivery agent calls `calculate_min_order_value` which uses `get_min_order_value` from `order_service.py`.
2. `get_min_order_value` calls the Ordelo pricing endpoint with customer lat/lon and restaurant reference to determine the minimum order value for the delivery area.
3. If the endpoint returns None or -1, the customer is outside the delivery area and the agent sets `is_outside_delivery_area` in state, preventing the order flow from proceeding.
4. `_resolve_restaurant_coordinates` resolves restaurant coordinates either from explicit lat/lon parameters or by querying the `restaurant_master` table using `rest_ref`.

### Code References (Machine-Readable)
file: services/maps_service/address_resolver.py
symbol: AddressResolver
feature: Address and Maps Service
description: >
  Google Geocoding API wrapper that resolves postcodes and coordinates into structured UKAddress objects via forward and reverse geocoding.

file: services/maps_service/address_resolver.py
symbol: UKAddress
feature: Address and Maps Service
description: >
  Pydantic model for structured UK addresses with postcode validation, coordinate fields, and raw API response storage.

file: services/maps_service/address_resolver.py
symbol: AddressResolver.get_address_from_postcode
feature: Address and Maps Service
description: >
  Resolves a UK postcode to a full UKAddress by calling the Google Geocoding API with the formatted postcode and parsing the response.

file: services/maps_service/address_resolver.py
symbol: AddressResolver.get_address_from_coordinates
feature: Address and Maps Service
description: >
  Performs reverse geocoding from lat/lon to a UKAddress, filtering for street_address/premise results.

file: services/maps_service/address_resolver.py
symbol: AddressResolver._parse_geocode_response
feature: Address and Maps Service
description: >
  Extracts structured address fields from Google Geocoding API response components and builds a UKAddress instance.

file: services/maps_service/address_resolver.py
symbol: address_resolver
feature: Address and Maps Service
description: >
  Module-level singleton instance of AddressResolver initialized with the Google Maps API key from config.

file: rest_agent/agent_wa_senders.py
symbol: confirm_delivery_address_wa
feature: Address and Maps Service
description: >
  Sends a WhatsApp interactive message with the customer's stored address and Yes/Update confirmation buttons via callback data.

file: rest_agent/agent_wa_senders.py
symbol: send_postcode_search_flow
feature: Address and Maps Service
description: >
  Sends a WhatsApp FlowButton that launches the PostcodeSearchElai flow for address capture or update with optional initial postcode.

file: rest_agent/agent_wa_senders.py
symbol: send_update_address_wa
feature: Address and Maps Service
description: >
  Sends a WhatsApp URL button linking to the Ordelo web address update form with recipient and restaurant reference parameters.

file: rest_agent/agent_wa_senders.py
symbol: CallbackButtonData
feature: Address and Maps Service
description: >
  Frozen Pydantic model for WhatsApp button callback payloads with an action field and extra-fields support for routing and state data.

file: watomation/on_callback_handler.py
symbol: delivery_address_confirmation
feature: Address and Maps Service
description: >
  Handles address confirmation button callbacks, setting is_delivery_address_confirmed in graph state and optionally triggering the address update flow.

file: utils_common/archive/on_flow_request_postcode_search.py
symbol: on_pc_search_complete
feature: Address and Maps Service
description: >
  Processes completed postcode search flow submissions by upserting the address into customer_master and updating graph state with the confirmed address.

file: utils_common/archive/on_flow_request_postcode_search.py
symbol: on_ip_pc
feature: Address and Maps Service
description: >
  Handles postcode input from the WhatsApp flow START screen, resolves the address via AddressResolver, and populates the ADDRESS screen fields.

file: utils_common/wa_flows/flow_postcode_search.py
symbol: POST_CODE_SEARCH
feature: Address and Maps Service
description: >
  WhatsApp Flow JSON definition with a two-screen postcode search and address confirmation form using PyWa Flow components.

file: services/order_service.py
symbol: get_min_order_value
feature: Address and Maps Service
description: >
  Calls the Ordelo pricing endpoint with customer coordinates and restaurant reference to retrieve the minimum order value for delivery eligibility.

file: services/order_service.py
symbol: _resolve_restaurant_coordinates
feature: Address and Maps Service
description: >
  Resolves restaurant latitude/longitude from explicit parameters or by querying the restaurant_master table with rest_ref.

### Edge Cases
- Google Geocoding API returning non-OK status (e.g. ZERO_RESULTS, OVER_QUERY_LIMIT) results in a partial UKAddress with only coordinates or postcode populated and no structured fields.
- Network failure during geocoding returns a minimal UKAddress with coordinates only; the caller receives a valid object but with mostly None fields.
- Postcode not found during flow interaction (city resolves to None) returns a FlowResponse with an error_message, keeping the user on the search screen.
- Missing house_number, building_name, or street_name from geocoding results are defaulted to empty strings in the flow response to prevent null display issues.
- Address confirmation "Update" path re-enters the postcode search flow, resetting `is_delivery_address_confirmed` to False and requiring full re-confirmation.
- `on_pc_search_complete` casts lat/lon to float from string flow response data; invalid or missing values would raise a ValueError.
- Customer not found in customer_master during address upsert creates a new record; existing records are updated via Supabase upsert semantics.
- `get_min_order_value` returning None (HTTP error or unexpected failure) leaves the agent unable to determine delivery eligibility, requiring fallback handling.
- Restaurant with missing lat/lon in restaurant_master causes `_resolve_restaurant_coordinates` to raise ValueError, blocking minimum order calculation.
- The `send_update_address_wa` URL-based path bypasses the WhatsApp flow and goes through the Ordelo web app, which has its own address update logic independent of graph state.
