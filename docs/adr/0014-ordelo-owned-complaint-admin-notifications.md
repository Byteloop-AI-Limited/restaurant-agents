# 0014 Ordelo-owned complaint admin notifications

- Status: Superseded by ADR-0017
- Date: 2026-08-03
- Owners: Restaurant platform owner

ADR-0017 supersedes this decision, renaming "complaint" to "feedback"
throughout the customer-facing and internal surface and widening the intended
scope to any sentiment (praise, suggestions, or problems), not only problems.
The underlying Ordelo-owned notification mechanism described below is
otherwise unchanged.

## Decision

Restaurant WhatsApp agents submit validated customer complaints to the Ordelo
customer-hooks API. Ordelo resolves the current `RestaurantMaster.admins` list
and schedules each WhatsApp notification through `BackgroundTasks`, returning
an accepted response without waiting for delivery. The restaurant agent never
messages administrators directly.

Version one does not persist complaints, retry failed notifications, or require
service-to-service authentication. These limitations are explicit operational
risks to address before exposing the route beyond the trusted internal network.

## Consequences

The customer acknowledgement means only that the restaurant team was notified
through the accepted scheduling path; it is not a delivery confirmation.
