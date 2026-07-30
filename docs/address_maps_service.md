# Feature: Address and Maps Service

The active delivery flow confirms persisted customer addresses, sends customers
to the Restaurant's Ordelo address-update page when an address is missing or
must change, and uses customer coordinates to request minimum-order
eligibility. Shared-location messages may be reverse-geocoded for diagnostics.

## Human-Friendly Code Map

- [AddressResolver and UKAddress](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/maps_service/address_resolver.py)
- [WhatsApp address senders](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_wa_senders.py)
- [Delivery address tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py)
- [Address callback handler](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py)
- [Location-message handler](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py)
- [Minimum-order lookup](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_service.py)

## Active Address Flow

1. Graph startup loads the persisted `CustomerMaster` address into AgentState.
2. `confirm_delivery_address` sends the stored address with Yes/Update buttons.
3. Yes marks `is_delivery_address_confirmed=True` and re-enters the graph.
4. Update marks the address unconfirmed and directs the agent to
   `update_address_of_existing_user`.
5. New-address and update tools call `send_update_address_wa`, which sends a
   URL button to the Restaurant-specific Ordelo address form.
6. The external address-update event refreshes graph address state and forces
   minimum-order recalculation.

The repository does not contain an active postcode-search WhatsApp Flow. Address
persistence and form validation on the URL path belong to the external Ordelo
application.

## Geocoding

`AddressResolver` supports forward UK-postcode and reverse-coordinate lookup
through Google Geocoding. It is constructed with an explicit API key. There is
no module-global resolver or configuration lookup.

The shared-location WhatsApp handler constructs a resolver with
`runtime.settings.maps.maps_api_key` and logs the resolved address. It currently
does not persist that result or update AgentState.

`UKAddress` normalizes UK postcodes and represents structured address fields,
coordinates, and the raw provider response. Provider or network failures return
a partial value rather than raising from the resolver.

## Delivery Eligibility

After an address is confirmed, `calculate_min_order_value` passes customer
coordinates and Restaurant identity to `get_min_order_value`. The service uses
the exact runtime database client to resolve the Restaurant's Ordelo base URL,
then calls the external pricing endpoint. A `None` or `-1` result is handled by
the delivery agent as unavailable or outside the delivery area.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/maps_service/address_resolver.py
symbol: AddressResolver
feature: address-maps
description: >
  Google Geocoding wrapper constructed with an explicit API key.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_message_graph_handler.py
symbol: handle_request_location_response
feature: address-maps
description: >
  Reverse-geocodes a shared WhatsApp location with the exact runtime maps settings.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: capture_delivery_address
feature: address-maps
description: >
  Sends the external Restaurant address form when no customer address is persisted.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py
symbol: update_address_of_existing_user
feature: address-maps
description: >
  Sends the external address-update form unless payment is already complete.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/watomation/on_callback_handler.py
symbol: delivery_address_confirmation
feature: address-maps
description: >
  Applies the customer's address confirmation choice to graph state.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/order_service.py
symbol: get_min_order_value
feature: address-maps
description: >
  Calls the Restaurant's external pricing endpoint through an injected database client.
```

## Edge Cases

- Address capture/update is blocked after successful payment.
- Google API errors produce partial `UKAddress` values for the diagnostic
  location handler.
- A missing Restaurant base URL or pricing failure yields no minimum-order
  value; it does not mutate persisted customer or order data.
- Address confirmation alone does not update `CustomerMaster`; the external
  address form owns persistence.
