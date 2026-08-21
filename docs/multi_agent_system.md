# Feature: Shared Multi-Agent Orchestration System

The shared Restaurant Agent runtime coordinates triage, delivery, and takeaway
conversations through one fixed LangGraph topology. The runtime owns the graph,
standard agents, ordered tools, state, middleware, checkpointing, repair, and
debug behavior. Each restaurant application owns its identity, presentation,
three complete prompts, small `agent_recipe.py` composition module, entrypoint,
and any genuinely custom behavior.

For an interactive view of the same architecture, open
[the Agent runtime composition guide](./guides/agent-runtime-composition.html).
The governing design decisions are recorded in
[the shared-runtime decision record](./architecture/shared-agent-runtime-decisions.md).
Platform-wide terms and authority rules are defined in the
[glossary](./glossary.md) and [domain model](./domain/platform-domain-model.md).

---

## Human-Friendly Code Map

- [Runtime interfaces, Enquiry Menu, and GraphAdapter protocol](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py)
- [FastAPI, runtime, and WhatsApp-client assembly](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py)
- [Standard graph adapter and runner](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py)
- [Fixed three-node graph](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py)
- [Shared state, context, handoffs, and middleware](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py)
- [Retained-specialist lifecycle projection](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/specialist_lifecycle.py)
- [Shared typed, callback, and tool service selection](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/service_selection.py)
- [Rider-location guard and Ordelo request shared by the tool](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/rider_location_support.py)
- [Standard triage agent and tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/triage.py)
- [Standard delivery agent and tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py)
- [Standard takeaway agent and tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/takeaway.py)
- [SFCS prompt recipe](../apps/sfcs/src/sfcs_agent/rest_agent/agent_recipe.py)
- [BNAT prompt recipe](../apps/bnat/src/bnat_agent/rest_agent/agent_recipe.py)
- [ELAS prompt recipe (multi-restaurant, dine-in)](../apps/elas/src/elas_agent/rest_agent/agent_recipe.py)
- [Restaurant-selection projection and gates (ADR-0020)](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/restaurant_selection.py)
- [Optional standard dine-in agent (ADR-0021)](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/dine_in.py)

## Composition Vocabulary for Functional Programmers

Most classes in the composition path are immutable records, callable contracts,
or thin framework adapters rather than an inheritance hierarchy.

| Python construct | Functional interpretation | Constructed at | Consumed by |
| --- | --- | --- | --- |
| `RestaurantIdentity` | Validated immutable value | App `identity.py` | App factory, routes, settings loader |
| `RestaurantPresentation` | Immutable configuration value | App `identity.py` | App factory, runtime, customer-facing services and enquiry menus |
| `RestaurantSettingsBundle` | Environment/dependency record | Settings loader | `RestaurantRuntime` and shared services |
| `RestaurantRuntime` | Reader-style environment | `create_restaurant_app()` | Handlers, routers, adapter, graph context |
| `RestaurantPrompts` | Immutable input record | App `agent_recipe.py` | `RestaurantGraphAdapter` |
| `AgentBindings` | Record of functions and framework types | App `main.py` | WhatsApp handler registration |
| `GraphAdapter` | Structural operations contract | Implemented by compatible objects | Shared web and webhook code |
| `GraphAdapterFactory` | Function type `Runtime -> Adapter` | App recipe | `create_restaurant_app()` |
| `RestaurantGraphAdapter` | Closure-like object with named async operations | Graph factory invocation | Shared handlers and routers |
| `create_restaurant_app` | Composition-root function | App entrypoint | Returns one configured FastAPI app |

`frozen=True` prevents rebinding record fields but does not make referenced
clients pure. `functools.partial(RestaurantGraphAdapter, prompts=PROMPTS)` binds
the app-owned prompt argument and leaves a callable waiting for
`RestaurantRuntime`.

Read the construction path in this order:

```text
app identity.py + app agent_recipe.py
    -> app main.py
    -> create_restaurant_app()
    -> RestaurantRuntime
    -> GraphAdapterFactory(runtime)
    -> RestaurantGraphAdapter
    -> build_multi_agent_graph()
```

## Ownership Model

| Concern | Owner | Extension point |
| --- | --- | --- |
| Identity, presentation, WABA namespace | Application | `identity.py` |
| Enquiry menu labels and callback intent | Application | `RestaurantPresentation.enquiry_menu` |
| Restaurant-selection choices (multi-restaurant apps only) | Application | `RestaurantPresentation.restaurant_selection` (ADR-0020) |
| Complete triage, delivery, and takeaway prompts, plus the optional dine-in prompt | Application | `rest_agent/prompts/*.md` |
| Prompt and adapter composition | Application | `rest_agent/agent_recipe.py` |
| Standard graph, state, routing, middleware, and tools, including the optional dine-in node | Shared runtime | No app-local copy |
| Additional tool on an existing standard node | Application | `extra_tools_by_agent` |
| Complete replacement for one standard node | Application | `agent_overrides` |
| Custom callback or API route | Application | Native PyWa handler or FastAPI router |
| New node, incompatible state, routing, checkpointing, repair, or debug behavior | Application | App-owned `GraphAdapter` |

The runtime never imports an application package, and one application must never
import another. Application values flow into the shared runtime through the
existing `GraphAdapterFactory` callable.

## Detailed Flow Explanation

1. An app entrypoint supplies its `RestaurantIdentity`,
   `RestaurantPresentation`, `GRAPH_ADAPTER_FACTORY`, and `AgentBindings` to
   `create_restaurant_app()`.
2. The web factory calls `load_settings_bundle(identity)`, which fetches
   settings once, loads only the selected WABA namespace, creates one async and
   one sync WhatsApp client, and constructs one `RestaurantRuntime`.
3. The app's `agent_recipe.py` has already loaded three complete prompt files
   into an immutable `RestaurantPrompts` value and bound them to
   `RestaurantGraphAdapter` with `functools.partial`.
4. The web factory calls that bound graph factory with the exact runtime, then
   stores both runtime and adapter on `app.state`.
5. `RestaurantGraphAdapter.__init__` reads the model from
   `runtime.settings.llm`, constructs the standard or overridden triage,
   delivery, and takeaway runnables, and builds the `StateGraph` once.
6. `build_multi_agent_graph()` registers exactly three nodes:
   `triage_agent`, `delivery_agent`, and `takeaway_agent`. `route_initial`
   defaults to triage; `route_after_agent` ends on a final AI message or follows
   `active_agent` to another standard node.
7. For each operation, `run_rest_graph_with_custom_msg()` compiles that builder
   with an `AsyncPostgresSaver`, resolves the restaurant-prefixed thread, repairs
   malformed persisted tool-call tails, and creates `ContextSchema`.
8. `ContextSchema` receives the same async WhatsApp client held by the
   `RestaurantRuntime`, plus the database pool, recipient, restaurant identity,
   presentation (including its Enquiry Menu), project and payment settings, and Ordelo client. Tools
   therefore use the exact application runtime rather than module-global
   settings or clients.
9. Typed explicit service requests, service callbacks, and standard transfer
   tools all use the same selection policy. It first inspects the persisted
   lifecycle projection: a retained flow sends a deterministic completion-first
   reply without changing service; an open flow starts a clean selected service;
   and a closed service sends the deterministic closed response. State-inspection
   failure preserves ownership rather than overwriting a potentially retained
   specialist.
10. Standard transfer tools update `active_agent` with parent-graph
    `Command` objects. `cleanup_before_model` and `respond_on_wa` coordinate
    `/DoNotRespond:` turns and outbound WhatsApp responses.
11. State persists across turns through the PostgreSQL checkpointer. Debug and
    state-inspection methods reuse the same adapter boundary.
12. External payment and fulfilment events update the lifecycle projection.
    Payment completion stores a paid delivery awaiting rider allocation and
    suppresses same-order replays. Terminal events notify through the retained
    specialist, then release to triage and clear order-scoped state. A delivery
    timeout must match the active unassigned delivery before it can notify and
    release; it leaves the Thread active so the customer can later select a new
    service. Completed delivery and confirmed takeaway pickup continue to the
    existing triage termination flow.
13. `update_customer` (shared by `delivery_agent` and `takeaway_agent`) refuses
    to fire unless the current turn was opened by a fresh runtime
    `SystemMessage`: a customer's own message can never trigger it, and it can
    never fire on an earlier turn's already-consumed system instruction. This
    is a structural guard on the tool itself, not prompt wording, so it applies
    identically to both agents regardless of app-owned prompt phrasing.

## Standard Nodes and Ordered Tools

The lists below are the unconditional baseline every app gets. Two
conditional appends exist, each activated only by app config and each
appended *after* this baseline, never inserted into it:

- `ask_user_to_select_restaurant` and `capture_restaurant_selected` are
  appended to `triage_agent`'s tools only when the app configures
  `RestaurantPresentation.restaurant_selection` (ADR-0020).
- `transfer_to_dinein` is appended to `triage_agent`, `delivery_agent`, and
  `takeaway_agent`'s tools, and the `dinein_agent` node itself only exists,
  when the app supplies `RestaurantPrompts.dinein` (ADR-0021).

An app that configures neither (SFCS, BNAT) gets exactly the lists below,
byte-for-byte.

### `triage_agent`

1. `send_welcome_message`
2. `ask_user_to_select_service`
3. `ask_user_to_select_enquiry`
4. `capture_marketing_consent`
5. `submit_restaurant_feedback`
6. `terminate_conversation`
7. `transfer_to_delivery`
8. `transfer_to_takeaway`

### `delivery_agent`

1. `send_welcome_msg`
2. `answer_general_query`
3. `confirm_delivery_address`
4. `capture_delivery_address`
5. `update_address_of_existing_user`
6. `calculate_min_order_value`
7. `send_restaurant_menu_tool`
8. `verify_if_payment_complete`
9. `update_customer`
10. `check_delivery_driver_allocation_status`
11. `send_rider_live_location_link`
12. `request_rider_location`
13. `transfer_to_takeaway`
14. `transfer_to_triage`

### `takeaway_agent`

1. `verify_if_payment_complete`
2. `update_customer`
3. `send_takeaway_menu_tool`
4. `transfer_to_delivery`
5. `transfer_to_triage`

### `dinein_agent` (optional standard node, ADR-0021)

Only constructed when `RestaurantPrompts.dinein` is supplied.

1. `get_reservation_link`
2. `check_reservation_status`
3. `transfer_to_delivery`
4. `transfer_to_takeaway`
5. `transfer_to_triage`

Shared-runtime contract tests own these node names, routes, and ordered tool
lists — `tests/rest_agent/test_graph_contract.py` characterizes both the
unconditional baseline and the two configured variants by constructing the
real graph and adapter, not by parsing source text, since a runtime config
branch is no longer visible to static AST parsing. App tests own prompt
presence and exact runtime/client composition.

For a standalone triage enquiry with no chosen service,
`ask_user_to_select_service(message_before_selection=...)` sends the complete
customer-facing answer before its interactive buttons and ends the turn. After
Ordelo accepts feedback, `submit_restaurant_feedback` likewise sends its
model-written acknowledgement before the same menu. This preserves mandatory
service selection without interrupting an answer or acknowledgement.

Owner-approved Overwatch recipients bypass venue-hours and new-order-cutoff
guards across service selection, transfers, and menu sends, so an end-to-end
test can run at any time. This bypass is restricted to the shared allow-list
and is implemented once, as `OperationalLookupCache.accepts_new_order` and
`.is_open` (see [Operational Lookup Cache](caching_system.md)); every gate
calls one of these two methods rather than re-checking
`is_overwatch_recipient` inline.

New-order availability is determined before the model is involved. An approved
collection callback or transfer sends its menu directly; an approved delivery
flow starts address capture/confirmation; and a closed normal recipient gets a
single `Ordering is currently closed.` message. The model never asks a customer
for the current date or time to decide whether a new order is available.

## Customization Contract

### Change only wording or policy

Edit the owning app's complete prompt file. Prompts are not assembled from
shared fragments. The shared runtime renders only explicit template variables
for current RestaurantMaster and RestaurantPresentation facts at model-call
time. Because `agent_recipe.py` reads them during module import, the application
process must restart to load wording changes.

### Add a tool to an existing node

Keep the native LangChain tool in the app package and bind it in
`agent_recipe.py`:

```python
GRAPH_ADAPTER_FACTORY = partial(
    RestaurantGraphAdapter,
    prompts=PROMPTS,
    extra_tools_by_agent={"triage_agent": [check_loyalty]},
)
```

Only the three standard node names are valid. Extra tools are appended after the
standard ordered tools.

### Replace one complete standard agent

Supply a native runnable through `agent_overrides`:

```python
GRAPH_ADAPTER_FACTORY = partial(
    RestaurantGraphAdapter,
    prompts=PROMPTS,
    agent_overrides={"delivery_agent": CUSTOM_DELIVERY_AGENT},
)
```

The replacement must define `ainvoke` and preserve the standard node name,
`AgentState`, `ContextSchema`, and handoff behavior. A node cannot receive extra
tools and be replaced at the same time.

### Change graph or state semantics

An app owns a complete `GraphAdapter` when it adds or removes nodes, changes
routing or handoff names, changes shared state incompatibly, or changes
checkpointing, compilation, repair, or debug behavior. Do not mutate private
shared-runtime graph internals or introduce a node registry.

### Add callbacks or routes

Use framework-native extension points during app assembly: register PyWa
handlers on `app.state.restaurant_runtime.async_wa_client` and include FastAPI
routers with `app.include_router()`. If handler ordering makes post-registration
incorrect, the application owns its application factory.

## New Restaurant Composition Checklist

1. Create `apps/<slug>` as an independent workspace application.
2. Add app-owned `RestaurantIdentity` and `RestaurantPresentation` values.
3. Provide a complete, strict WABA namespace; no other namespace is a fallback.
4. Add all three complete prompt files under the app's `rest_agent/prompts/`.
5. Add `agent_recipe.py` that exposes a `GraphAdapterFactory`-compatible callable.
6. Pass identity, presentation, graph factory, and bindings to
   `create_restaurant_app()`.
7. Add an app composition test that proves exact runtime and async
   WhatsApp-client binding plus all three app-owned prompts.
8. Use extra tools or a named-agent override for compatible variation; use an
   app-owned adapter only for an incompatible graph contract.
9. Only if the app serves more than one restaurant brand behind one WhatsApp
   number: configure `RestaurantPresentation.restaurant_selection` and add
   the app's own `rest_ref` as one of its choices, or `create_restaurant_app`
   refuses to start (ADR-0020). ELAS is the reference implementation.
10. Only if the app takes table bookings: add a fourth
    `dinein_agent_prompt.md`, pass it as `RestaurantPrompts.dinein`, and set
    `include_reservation_router=True` (ADR-0021). ELAS is the reference
    implementation.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: RestaurantIdentity
feature: shared-multi-agent-orchestration
description: >
  Immutable app-owned routing identity containing rest_ref and WABA namespace.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: RestaurantPresentation
feature: shared-multi-agent-orchestration
description: >
  Immutable app-owned customer-facing branding supplied to the shared runtime.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: EnquiryMenu
feature: shared-multi-agent-orchestration
description: >
 App-owned bounded WhatsApp SectionList enquiry prompt and callback options (ADR-0023) carried through RestaurantPresentation.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: RestaurantSettingsBundle
feature: shared-multi-agent-orchestration
description: >
  Groups the selected settings and external clients required by one application runtime.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: RestaurantRuntime
feature: shared-multi-agent-orchestration
description: >
  Carries one application's identity, presentation, settings, and exact WhatsApp clients.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/prompts.py
symbol: RestaurantPrompts
feature: shared-multi-agent-orchestration
description: >
  Immutable record of complete app-owned triage, delivery, and takeaway prompts.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py
symbol: AgentBindings
feature: shared-multi-agent-orchestration
description: >
  Supplies the native callback-data type and service-selection sender used during handler registration.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py
symbol: GraphAdapterFactory
feature: shared-multi-agent-orchestration
description: >
  Defines the application-owned callable boundary that receives one RestaurantRuntime and returns a GraphAdapter.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py
symbol: create_restaurant_app
feature: shared-multi-agent-orchestration
description: >
  Builds one isolated FastAPI application, runtime, WhatsApp-client pair, graph adapter, handler set, and router set.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py
symbol: RestaurantGraphAdapter
feature: shared-multi-agent-orchestration
description: >
  Binds app-owned prompts and optional standard-node customizations to the exact RestaurantRuntime.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py
symbol: run_rest_graph_with_custom_msg
feature: shared-multi-agent-orchestration
description: >
  Compiles and runs the graph with PostgreSQL checkpointing and an execution context carrying the exact application runtime.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py
symbol: build_multi_agent_graph
feature: shared-multi-agent-orchestration
description: >
  Constructs the fixed triage, delivery, and takeaway StateGraph and its conditional routing edges.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py
symbol: ContextSchema
feature: shared-multi-agent-orchestration
description: >
  Carries the exact runtime WhatsApp client, database resources, recipient, identity, and presentation into agents and tools.
```

```code-ref
file: apps/sfcs/src/sfcs_agent/rest_agent/agent_recipe.py
symbol: GRAPH_ADAPTER_FACTORY
feature: shared-multi-agent-orchestration
description: >
  Loads SFCS-owned complete prompts and binds them to the standard RestaurantGraphAdapter.
```

```code-ref
file: apps/bnat/src/bnat_agent/rest_agent/agent_recipe.py
symbol: GRAPH_ADAPTER_FACTORY
feature: shared-multi-agent-orchestration
description: >
  Loads BNAT-owned complete prompts and binds them to the standard RestaurantGraphAdapter.
```

## Edge Cases

- Empty prompt values fail application construction with `ValueError`.
- Unknown keys in `extra_tools_by_agent` or `agent_overrides` fail construction.
- A node present in both customization mappings fails construction.
- An agent override without callable `ainvoke` fails construction.
- Missing namespaced WABA values fail startup; there is no cross-app fallback.
- Invalid or missing `active_agent` values route to `triage_agent`.
- A final `AIMessage` without tool calls routes to `END`.
- `restaurant_selection` configured but missing the app's own `rest_ref` among
  its choices fails application construction with `ValueError`.
- `selected_rest_ref` is never inferred from `rest_ref`: a fresh thread always
  seeds `rest_ref` but never `selected_rest_ref`, so a configured selection
  gate always fires on a new conversation. Releasing a specialist flow
  (below) never clears `selected_rest_ref`.
- A `RestaurantChoice` with `supports_dine_in=False` makes `transfer_to_dinein`
  redirect back to triage with an explanation, even while `dinein_agent` is
  configured for the app as a whole.
- `retain_thread=True` adds a current-call system message declaring the active
  delivery or takeaway flow in motion and strictly prohibiting handoff. The
  shared transfer guard remains the deterministic enforcement layer. When
  retention is explicitly cleared, a current-call system message permits—but
  never initiates—a transfer.
- Releasing a specialist flow resets the persisted owner to triage and clears
  order, payment, rider, reply, and delivery-calculation fields while preserving
  Restaurant and customer-profile context. A no-rider timeout does not
  terminate the Thread after that release. Its authoritative payment outcome is
  retained as `is_payment_cancelled`; with `is_delivery_no_rider`, it provides
  a fail-closed, deterministic answer to refund questions. Only a literal
  `is_payment_cancelled=True` permits the customer-facing confirmation that a
  refund has been issued.
- A malformed persisted assistant/tool tail, including an orphan or mismatched
  tool response, is trimmed from the first invalid message while retaining the
  valid checkpoint prefix, then retried once; an unrecoverable mismatch
  terminates the session.
- Cross-restaurant routes return `404` before graph calls or external side
  effects.
