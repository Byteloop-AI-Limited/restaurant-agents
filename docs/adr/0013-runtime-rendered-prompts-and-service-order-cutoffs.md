# 0013 Runtime-rendered prompts and service order cutoffs

- Status: Accepted
- Date: 2026-08-03
- Owners: Restaurant platform owner

## Decision

Application packages own complete triage, delivery, and takeaway prompts. They
may use explicit LangChain template variables. The shared runtime renders those
variables immediately before a model call from the exact runtime context:
RestaurantPresentation supplies branding/contact details and RestaurantMaster
supplies address and venue hours.

`service_hours_json` remains the sole persisted availability configuration.
New delivery and takeaway orders close exactly 15 minutes before the end of
each active service interval. That shared calculation applies only to new
service selection, handoff, and menu-link flows. Existing orders, payments, and
status support are not rejected solely because a cutoff has passed.

## Consequences

No prompt contains copied operational hours, address, or phone fallbacks.
There is no RestaurantMaster cutoff column or migration. Both SFCS and BNAT use
the shared 15-minute behavior in the same release.
