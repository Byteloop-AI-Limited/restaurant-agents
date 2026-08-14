# Restaurant Platform Glossary

This glossary defines the ubiquitous language for `restaurant-agents`. Code,
tests, ADRs, prompts, and future agent changes should use these terms
consistently. Terms owned by external systems describe only the contract visible
to this repository.

## A

### Agent

Avoid using this word alone. Use **Restaurant Agent runtime** for the shared
system, **Named Agent** for a LangGraph node, **Restaurant Application** for a
deployed app, and **coding agent** for an automated code contributor.

### AgentBindings

An immutable composition record containing the framework-native callback-data
type and service-selection sender required by shared WhatsApp handlers. It is
application input to the shared web factory, not a plugin registry.

### AgentState

The LangGraph checkpoint state used to continue a conversation and route among
Named Agents. It is runtime workflow state, not authoritative customer, order,
payment, or fulfilment data.

### Aggregate

A consistency boundary whose persisted record is authoritative for a business
concept. `FoodOrder` is the platform's order aggregate. `AgentState`,
`DeliverySummary`, and `TakeawaySummaryData` are not aggregates.

## B

### Bounded Context

A boundary within which terms and authority have one consistent meaning. This
repository contains contexts for application identity, customers and consent,
conversation runtime, Agent orchestration, ordering, service availability, and
integration with external payment and fulfilment systems.

## C

### ContextSchema

The per-run LangGraph context carrying the exact application runtime resources,
including the WhatsApp client, database pool, recipient, Restaurant identity,
presentation, project/payment settings, and Ordelo client. It is execution context, not
persisted domain state.

### Customer

The person interacting with a Restaurant Application. `CustomerMaster` is the
persisted cross-Restaurant customer record. In the current WhatsApp channel,
`cust_id` is the customer's WhatsApp number.

### Customer-Restaurant Relationship

The per-Restaurant relationship represented by `CustRestMap`, keyed by
`(cust_id, rest_ref)`. It owns marketing-consent state and its timestamp; that
state does not belong in `CustomerMaster` or `AgentState`.

## D

### DeliverySummary

An incoming fulfilment contract payload describing a delivery workflow update.
It reports external fulfilment state and is not an order aggregate or source of
truth.

## E

### External Bounded Context

A system whose internal model is outside this repository. The platform
documents only its visible commands, events, payloads, and authority. Current
external contexts include Meta WhatsApp, Ordelo/rider/takeaway fulfilment,
payment services, and address/geocoding providers.

### Enquiry Menu

An app-owned, bounded WhatsApp button menu for non-order triage. It contains
one prompt and one to three `EnquiryOption` values; it passes through
`RestaurantPresentation` so callback and triage-tool paths show the same
restaurant-specific choices.

### Enquiry Option

One visible Enquiry Menu label plus the canonical customer intent placed in its
`/SelectEnquiry` callback. It is customer-facing composition data, not a graph
node, callback registry, or persisted state.

## F

### FoodOrder

The authoritative persisted order aggregate. Delivery and takeaway are
fulfilment variants of one FoodOrder, not separate order aggregates. Order items
belong to the FoodOrder consistency boundary. The absence of an internal
catalog-order writer does not transfer aggregate authority to a payment or
fulfilment integration.

### Fulfilment Projection

The persisted local view of delivery or takeaway progress associated with a
FoodOrder. External Ordelo/rider/takeaway workflows are authoritative; the local
projection follows their events, and `AgentState` may cache it for conversation
flow.

### Fulfilment Type

The FoodOrder variant describing how the customer receives the order. The
standard values are delivery and takeaway/collection. Fulfilment type selects a
workflow without changing FoodOrder identity.

## G

### GraphAdapter

A structural protocol exposing the graph run and debug operations consumed by
the shared web layer. A standard app uses `RestaurantGraphAdapter`; an app owns
another implementation only when graph, state, routing, checkpointing, repair,
or debug semantics are incompatible with the standard contract.

### GraphAdapterFactory

A function type, `RestaurantRuntime -> GraphAdapter`. It is not a factory class
or registry. Each app normally supplies a partially applied
`RestaurantGraphAdapter` constructor with its prompts already bound.

## N

### Named Agent

One node in the standard LangGraph: `triage_agent`, `delivery_agent`, or
`takeaway_agent`. A Named Agent is not a deployment or an independent service.

## O

### OrderItem

A persisted line item belonging to a FoodOrder. It has no independent business
lifecycle outside its order. Its canonical runtime model is independent of any
database-writer implementation.

### Operational Lookup Cache

The per-RestaurantRuntime, process-local TTL cache for stable operational
configuration: application URLs, RestaurantMaster, and the database-backed
Overwatch recipient list. It is not a source of truth and excludes
transactional customer, order, payment, fulfilment, and Thread data.

## P

### Payment Projection

`FoodOrder.payment_status`, the platform's persisted view of the external
payment transaction. Authority flows from the external payment system to this
projection and then, if needed, to an `AgentState` runtime cache.

### Projection

A local representation derived from an authoritative source. A projection can
be rebuilt or reconciled and must not silently override its source.

## R

### Recipient

The WhatsApp destination/source identifier used at the messaging boundary. For
customer conversations it currently has the same value as `cust_id`, but the
term describes a channel role rather than customer identity.

### Retained Specialist Flow

The AgentState projection of paid or in-progress delivery/takeaway work. When
`retain_thread=True`, the current specialist owns the conversation and service
handoffs are blocked. A terminal fulfilment event releases the projection to
triage, clears order-scoped runtime fields, and permits future service
selection. This does not change the external order or fulfilment source of
truth.

### Restaurant Application

One independently deployed FastAPI/PyWa application, such as SFCS or BNAT. It
owns identity, presentation, prompts, entrypoint, Fly manifest, and genuinely
custom behavior. Applications do not import each other.

### RestaurantIdentity

An immutable, app-owned routing and secret-namespace record containing
`rest_ref` and `waba_namespace`. It determines which Restaurant and WABA
namespace the running process may serve.

### RestaurantMaster

The authoritative persisted mutable operational Restaurant record. It owns
address, coordinates, administrators, venue service hours, and operational
settings. New-order cutoffs are derived from its service-hour schedule, not
persisted separately.

### RestaurantPresentation

The immutable, app-owned customer-facing branding record: display name, contact
phone, logo URL, service labels, and bounded interactive menu copy. It is
deliberately separate from RestaurantMaster's mutable operational data.

### RestaurantPrompts

An immutable record containing one application's complete triage, delivery, and
takeaway prompts. Prompts are application-owned inputs to the shared runtime.

### RestaurantRuntime

The immutable environment record assembled for exactly one Restaurant
Application. It contains identity, presentation, settings, and the exact async
and sync WhatsApp clients plus its Operational Lookup Cache. The record is
frozen, but referenced clients and services are effectful and mutable.

### RestaurantSettingsBundle

The validated settings and external-client record loaded once at the
application composition root. Configuration model imports are side-effect free;
services receive bundle members through RestaurantRuntime, ContextSchema, or
explicit parameters.

## S

### Service Hours

The RestaurantMaster-owned weekly availability schedule. `WeeklySchedule` is
the parsed runtime value used to determine open/closed behavior and the next
opening time.

### Venue Hours

The RestaurantMaster `service_hours_json` schedule governing whether the
restaurant can receive WhatsApp messages and enquiries.

### Order Cutoff

A RestaurantMaster per-service number of minutes before an active venue-hours
interval ends when new delivery or takeaway orders stop. It does not close the
venue or invalidate existing order/payment/status flows.

### Overwatch Recipient

A recipient listed in Ordelo's `ordelo_config.overwatch_list`, permitted to
exercise the complete restaurant-agent flow outside venue hours and per-service
new-order cutoffs. It is a bounded verification bypass, not a customer
entitlement; an unreadable list fails closed.

### Restaurant Feedback

An ephemeral customer report of any sentiment — praise, a suggestion, or a
problem — containing customer context, optional order reference, and concise
description. Ordelo validates the restaurant and schedules notifications to
its current administrators; it is not persisted by the WhatsApp app.

### Admin Notification Scheduled

The accepted Ordelo outcome meaning notification work was queued in background
tasks. It does not mean every administrator has received the WhatsApp message.

### Source of Truth

The system authorized to establish a fact. For orders this is persisted
FoodOrder data; for payments and fulfilment it begins in the respective
external system; runtime graph state is never the business source of truth.

## T

### TakeawaySummaryData

An incoming fulfilment contract payload describing takeaway preparation or
pickup progress. It is not a separate order aggregate.

### Thread

A persisted conversation-session record scoped by Restaurant and recipient. It
manages active/inactive lifecycle, correlation, and retention, but remains
runtime orchestration state rather than business truth. The customer-accessible
`/reset` is an Overwatch-only operational escape hatch that starts a new Thread
lifecycle. Regular customers cannot use it to abandon an in-progress order.

## W

### WABA Namespace

The application-owned key selecting one complete WhatsApp Business Account
configuration. Startup loads only the requested namespace and never falls back
to another application's values.

### WaLocation

Ordelo's on-demand WhatsApp rider-location client integration. A customer's
`request_rider_location` tool call posts to Ordelo's open
`POST /wa-request-location`, which validates the exact
`delivery_inflight(order_number, dispatch_id, rider_id)` assignment and either
reuses a location observation no more than five minutes old or asks the rider
for their current WhatsApp location. Ordelo posts the result to this app's
`POST /rider-event-hooks/{rest_ref}/wa-location-response` callback, which
resends a WhatsApp pin only after revalidating retained, picked-up,
matching-order state. See
`docs/wa_location_restaurant_agents_integration.md` in OrdeloAgent for the
full contract.

### Webhook Event

An incoming message at an HTTP integration boundary reporting an external fact
or requesting an operation. Payload validation and Restaurant isolation occur
before graph calls or side effects.
