# 0013 Runtime-rendered prompts and service order cutoffs

- Status: Accepted
- Date: 2026-08-03
- Owners: Restaurant platform owner

## Decision

Application packages own complete triage, delivery, and takeaway prompts. They
may use explicit LangChain template variables. The shared runtime renders those
variables immediately before a model call from the exact runtime context:
RestaurantPresentation supplies branding/contact details and RestaurantMaster
supplies address, venue hours, and service-specific new-order cutoffs.

`service_hours_json` remains venue/enquiry availability. New
`delivery_order_cutoff_minutes` and `takeaway_order_cutoff_minutes` subtract
from each active interval only for new service selection, handoff, and menu-link
flows. Existing orders, payments, and status support are not rejected solely
because a cutoff has passed.

## Consequences

No prompt contains copied operational hours, address, or phone fallbacks.
Database migrations add both cutoff fields with a zero default for unaffected
restaurants. Both SFCS and BNAT use the shared behavior in the same release.
