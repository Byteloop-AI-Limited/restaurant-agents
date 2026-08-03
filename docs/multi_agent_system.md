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

- [Runtime interfaces and GraphAdapter protocol](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py)
- [FastAPI, runtime, and WhatsApp-client assembly](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py)
- [Standard graph adapter and runner](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agent_runner.py)
- [Fixed three-node graph](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/multi_agent.py)
- [Shared state, context, handoffs, and middleware](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/agent_harness.py)
- [Standard triage agent and tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/triage.py)
- [Standard delivery agent and tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/delivery.py)
- [Standard takeaway agent and tools](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents/takeaway.py)
- [SFCS prompt recipe](../apps/sfcs/src/sfcs_agent/rest_agent/agent_recipe.py)
- [BNAT prompt recipe](../apps/bnat/src/bnat_agent/rest_agent/agent_recipe.py)

## Composition Vocabulary for Functional Programmers

Most classes in the composition path are immutable records, callable contracts,
or thin framework adapters rather than an inheritance hierarchy.

| Python construct | Functional interpretation | Constructed at | Consumed by |
| --- | --- | --- | --- |
| `RestaurantIdentity` | Validated immutable value | App `identity.py` | App factory, routes, settings loader |
| `RestaurantPresentation` | Immutable configuration value | App `identity.py` | App factory, runtime, customer-facing services |
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
| Complete triage, delivery, and takeaway prompts | Application | `rest_agent/prompts/*.md` |
| Prompt and adapter composition | Application | `rest_agent/agent_recipe.py` |
| Standard graph, state, routing, middleware, and tools | Shared runtime | No app-local copy |
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
   presentation, project and payment settings, and Ordelo client. Tools
   therefore use the exact application runtime rather than module-global
   settings or clients.
9. Standard transfer tools update `active_agent` with parent-graph
   `Command` objects. `cleanup_before_model` and `respond_on_wa` coordinate
   `/DoNotRespond:` turns and outbound WhatsApp responses.
10. State persists across turns through the PostgreSQL checkpointer. Debug and
    state-inspection methods reuse the same adapter boundary.

## Standard Nodes and Ordered Tools

### `triage_agent`

1. `send_welcome_message`
2. `ask_user_to_select_service`
3. `capture_marketing_consent`
4. `terminate_conversation`
5. `transfer_to_delivery`
6. `transfer_to_takeaway`

### `delivery_agent`

1. `send_welcome_msg`
2. `answer_general_query`
3. `confirm_delivery_address`
4. `capture_delivery_address`
5. `update_address_of_existing_user`
6. `calculate_min_order_value`
7. `send_restaurant_menu_tool`
8. `verify_if_payment_complete`
9. `send_updates_to_customer`
10. `check_delivery_driver_allocation_status`
11. `send_rider_live_location_link`
12. `transfer_to_takeaway`
13. `transfer_to_triage`

### `takeaway_agent`

1. `verify_if_payment_complete`
2. `send_takeaway_menu_tool`
3. `transfer_to_delivery`
4. `transfer_to_triage`

Shared-runtime contract tests own these node names, routes, and ordered tool
lists. App tests own prompt presence and exact runtime/client composition.

## Customization Contract

### Change only wording or policy

Edit the owning app's complete prompt file. Prompts are not assembled from
shared fragments. Because `agent_recipe.py` reads them during module import, the
application process must restart to load changes.

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
- Transfer guards can block a handoff while retained delivery work is active.
- A malformed persisted assistant/tool tail is trimmed and retried once; an
  unrecoverable mismatch terminates the session.
- Cross-restaurant routes return `404` before graph calls or external side
  effects.
