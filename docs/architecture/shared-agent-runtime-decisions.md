# Shared Restaurant Agent Runtime Refactor

- Status: Implemented; deferred work is tracked in `docs/to-do.md`
- Date: 2026-07-29
- Scope: `restaurant-agent-runtime`, SFCS, and BNAT
- Design reference only: `/Users/basavaraj/bloop/elai`
- Compared plan: `.plans/grill-me-to-ask-partitioned-hippo.md`

## Reader map

- Start at the [documentation index](../README.md), then use the
  [platform glossary](../glossary.md),
  [domain model](../domain/platform-domain-model.md), and
  [ADR index](../adr/README.md) for current canonical terminology and decisions.
- Start with the
  [interactive runtime composition guide](../guides/agent-runtime-composition.html)
  to explore common and restaurant-specific assembly.
- Use the [multi-agent system overview](../multi_agent_system.md) for the
  source-backed runtime flow, ownership model, graph, and ordered tool sets.
- Use the [prompt update rules](../rules-to-update-prompt-files.md) when
  changing restaurant behavior or deciding whether a change belongs in a
  prompt, adapter mapping, callback, route, or app-owned adapter.
- See the focused [delivery](../delivery_whatsapp_agent.md) and
  [takeaway](../takeaway_whatsapp_agent.md) references for the two specialist
  nodes.
- Use the [BNAT customization checklist](../bnat-customization-checklist.md) as
  a concrete example of reviewing an app after the shared-runtime extraction.

## Outcome

The production SFCS/BNAT Restaurant Agent implementation now lives in
`restaurant-agent-runtime`; complete prompts remain in each app, and composition
reuses the existing `GraphAdapterFactory` seam.

The implementation introduces no registry, plugin system, generic recipe
model, node specification, state-extension protocol, selection-policy model,
callback/route contribution model, aggregate validation framework, or separate
composer service.

The only new public runtime values are:

1. `RestaurantPrompts`, containing the three required complete prompt strings.
2. `RestaurantGraphAdapter`, the standard runtime-bound adapter accepted by the
   existing `GraphAdapter` protocol.

The standard adapter accepts two small optional mappings because application
variation is already demonstrated by Elai and explicitly required by the owner:

- `extra_tools_by_agent`: existing standard node name to framework-native tools.
- `agent_overrides`: existing standard node name to a framework-native runnable.

Anything that changes graph nodes, handoffs, shared state semantics,
checkpointing, routing, repair, or debug behavior uses an app-owned
`GraphAdapter`. That existing escape hatch is preferable to a general graph
extension API.

## Review against the comparison plan

### Retained

| Comparison-plan idea | Decision | Implementation evidence |
| --- | --- | --- |
| Reuse the existing `graph_adapter_factory` seam | Keep | `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py:63-84` defines `GraphAdapter` and `GraphAdapterFactory`; `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py:195-237` creates the runtime and invokes the factory. |
| Keep the web factory Agent-agnostic | Keep | `create_restaurant_app()` only knows the `GraphAdapter` protocol and stores the result in `app.state` at `web/app_factory.py:232-237`. No prompt or LangGraph type needs to enter `web/`. |
| One runtime adapter replaces two shallow app adapters | Keep | `restaurant_agent_runtime/rest_agent/agent_runner.py:401` defines the only standard adapter; both apps inject it through `rest_agent/agent_recipe.py:18`. |
| Prompts are app-owned and injected | Keep | Each app's `rest_agent/agent_recipe.py:8-18` loads its three files and constructs `RestaurantPrompts`; runtime agent modules do not read prompt files. |
| Move only the production graph | Keep | Runtime `agents/multi_agent.py:57` wires only `triage_agent`, `delivery_agent`, and `takeaway_agent`. |
| Remove dormant duplicated modules | Keep | The app-local `agents/` trees and their dedicated dine-in, router, and journey tests were deleted during clone cleanup. |
| Characterize graph nodes, edges, and tools | Keep, but treat as a narrow public composition contract | `tests/rest_agent/test_graph_contract.py` asserts the runtime graph routes and ordered default tool names. |
| Record shared-runtime findings separately | Keep | Findings are listed below and are not automatically included in the Agent move. |

### Simplified or rejected

| Earlier idea | Reduced decision | Why |
| --- | --- | --- |
| Public frozen `AgentRecipe` dataclass | Remove | Each app only needs an `agent_recipe.py` module that loads prompts and exposes a `partial(RestaurantGraphAdapter, ...)` compatible with the existing factory seam. A second configuration object adds no capability. |
| Separate `compose_restaurant_agent()` service | Remove | `RestaurantGraphAdapter.__init__` is the one composition boundary. `create_restaurant_app()` already supplies the runtime. |
| `AgentNodeSpec` and added-node API | Remove | A new node changes the fixed routing contract. Use an app-owned `GraphAdapter` until a second application proves a common new graph shape. |
| Generic exclusions, optional features, capabilities, or registries | Remove | SFCS and BNAT use the same three-node graph. Named tool additions and complete replacements cover the demonstrated compatible variation. |
| Recipe-owned callbacks and FastAPI routers | Remove | PyWa handlers can be registered by app assembly after the standard app is created; FastAPI already provides `app.include_router()`. No parallel abstraction is needed. |
| Shared state-extension and Restaurant-selection policy protocols | Remove | They are not required by SFCS/BNAT. Elai changes state and graph routing and therefore uses an app-owned adapter under this plan. |
| Aggregate `RecipeValidationError` hierarchy | Remove | Constructor-time `ValueError` for missing prompts or unknown mapping keys is sufficient. |
| Public per-agent builder/factory functions | Remove | One internal graph-building function creates the standard agents. Apps never construct individual shared-runtime agents. |
| Compile and cache the graph once in the first pass | Defer | Current code creates the builder once and compiles with an `AsyncPostgresSaver` for each operation at `agent_runner.py:159-165,268-275,297-299,316-318,341-343`. Retaining this avoids adding async lifecycle or cache/locking machinery during extraction. |
| Refactor all `restaurant-agent-runtime` globals before moving agents | Narrow | Remove import-time prompt/model capture in the moved Agent path. Keep unrelated shared-runtime global cleanup as explicit findings unless a characterization test proves it is required by the move. |
| Fix BNAT’s copied SFCS prompt content during extraction | Defer | The prompt files are app-owned and currently byte-identical; BNAT’s SFCS wording in `apps/bnat/src/bnat_agent/rest_agent/prompts/` is logged for post-migration cleanup, not mixed into parity work. |

## Architecture and migration reference map

### Existing composition and isolation seams

| Path and current lines | Symbols | Implementation use |
| --- | --- | --- |
| `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py:8-60` | `RestaurantIdentity`, `RestaurantPresentation`, `RestaurantSettingsBundle`, `RestaurantRuntime` | Keep unchanged; the standard adapter receives this exact runtime. |
| `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/runtime.py:63-84` | `GraphAdapter`, `GraphAdapterFactory` | Keep unchanged; this is the standard/custom-adapter boundary. |
| `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py:22-28` | `AgentBindings` | Keep; standard callback data/sender implementations move to the shared runtime, while an app may still supply custom bindings. |
| `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py:51-192` | `_register_whatsapp_handlers()` | Do not generalize in this refactor. It proves standard handler ordering and consumes `AgentBindings`. |
| `packages/restaurant-agent-runtime/src/restaurant_agent_runtime/web/app_factory.py:195-237` | `create_restaurant_app()` | Do not change its signature. Line 232 is the existing injection point. |
| `apps/sfcs/src/sfcs_agent/main.py:9-15` | `create_app()`, `GRAPH_ADAPTER_FACTORY` wiring | App assembly injects its prompt-bound standard adapter factory. |
| `apps/bnat/src/bnat_agent/main.py:4-16` | `create_app()`, `GRAPH_ADAPTER_FACTORY` wiring | App assembly uses the same runtime boundary with BNAT-owned prompts. |

### Production Agent graph migration map (historical)

The SFCS paths below record the canonical source used for the completed move.
Those app-local implementation paths have now been deleted; their live
counterparts are under
`packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/`.

| Historical source and lines | Completed transformation |
| --- | --- |
| `apps/sfcs/src/sfcs_agent/rest_agent/agents/agent_harness.py:57-128` | Move `AgentState` and `ContextSchema`. Preserve reducers and field meanings. Rewrite the sender import at lines 153-176 to the new shared sender module. |
| `agent_harness.py:240-402` | Move transfer guards and `transfer_to_delivery`, `transfer_to_takeaway`, and `transfer_to_triage` without changing node names or `Command.PARENT` semantics. |
| `agent_harness.py:411-493` | Move `cleanup_before_model` and `respond_on_wa` middleware unchanged. |
| `apps/sfcs/src/sfcs_agent/rest_agent/agents/triage.py:35-45` | Replace app sender import and file-relative prompt load. |
| `triage.py:52-267` | Move dynamic prompt, four native tools, the tool list, middleware, state/context schemas, and model settings. The shared internal builder supplies prompt/model and appends `extra_tools_by_agent["triage_agent"]`. |
| `apps/sfcs/src/sfcs_agent/rest_agent/agents/takeaway.py:20-30,33-97` | Remove config/prompt globals; move `verify_if_payment_complete`, the four-tool default list, middleware, and standard agent configuration. |
| `apps/sfcs/src/sfcs_agent/rest_agent/agents/delivery.py:29-45` | Replace app sender imports and remove direct `llm_settings` import. Keep current service imports for behavior parity unless a focused test requires runtime injection. |
| `delivery.py:50-773` | Move the production delivery tools unchanged. Their database/WA use already flows primarily through `ToolRuntime[ContextSchema]`; examples include `ctx.client_ordelo` and `ctx.project_settings`. |
| `delivery.py:775-819` | Preserve the default tool order, `tool(service)` wrapping, middleware, state/context schema, and model selection; inject complete prompt/model and append native extra tools. |
| `apps/sfcs/src/sfcs_agent/rest_agent/agents/multi_agent.py:27-62` | Move node wrapper and routing functions unchanged. |
| `multi_agent.py:65-114` | Keep the fixed three-node builder. It accepts constructed standard/replacement runnables internally; it does not expose node registration. |
| `multi_agent.py:131-154` | Remove module-level app imports/singletons; runtime adapter composition supplies the three native runnables. |
| `apps/sfcs/src/sfcs_agent/rest_agent/agent_runner.py:57-124` | Move malformed tool-call detection/repair unchanged and add focused runtime tests if missing. |
| `agent_runner.py:143-263` | Move graph invocation; keep exact `RestaurantRuntime` use and exact WA client injection at lines 222-235. |
| `agent_runner.py:268-352` | Move state/debug operations; keep current per-operation checkpointer/compile behavior in this pass. |
| `agent_runner.py:384-412` | Replace app-specific wrapper with one `RestaurantGraphAdapter`. |
| `apps/sfcs/src/sfcs_agent/rest_agent/agent_wa_senders.py:34-316` | Move only symbols reachable from the live graph/standard handler bindings: `CallbackButtonData`, `send_welcome_msg_wa`, `select_service_wa_send`, `select_marketing_consent_wa_send`, `confirm_delivery_address_wa`, `send_restaurant_menu`, and `send_update_address_wa`. |

The live sender consumers are already bounded: app assembly supplies
`CallbackButtonData` and `select_service_wa_send` at
`apps/sfcs/src/sfcs_agent/main.py:3-21`; triage imports the welcome, service, and
marketing senders at `triage.py:35-39`; the harness imports the menu sender at
`agent_harness.py:153-176`; and delivery imports the address senders at
`delivery.py:37-40`. Use these sites as the move checklist rather than exporting
the whole copied sender module.

The shared runtime package already declares the required LangChain, LangGraph,
checkpointer, and PyWa dependencies at
`packages/restaurant-agent-runtime/pyproject.toml:6-33`. The move should not add a
second dependency declaration or lockfile.

### Files that remain app-owned

| App path | Action |
| --- | --- |
| `apps/<app>/src/<app>_agent/identity.py` | Keep identity and presentation unchanged. |
| `apps/<app>/src/<app>_agent/main.py` | Keep entrypoint and app assembly; switch only imports/bindings. |
| `apps/<app>/src/<app>_agent/rest_agent/agent_recipe.py` | Add one small module that reads all three complete prompts and exports `GRAPH_ADAPTER_FACTORY = partial(RestaurantGraphAdapter, prompts=PROMPTS, ...)`. This module is not an instance of a shared recipe type. |
| `apps/<app>/src/<app>_agent/rest_agent/prompts/triage_agent_prompt.md` | Move current app prompt here unchanged. |
| `.../prompts/delivery_multiagent_prompt.md` | Move current app prompt here unchanged. |
| `.../prompts/takeaway_agent_prompt.md` | Move current app prompt here unchanged. |
| `apps/<app>/src/<app>_agent/rest_agent/tools/`, `callbacks/`, `routers/`, `agents/` | Create only when the app has a genuine custom artifact. Never create empty placeholder directories. |

### Dormant duplicates to delete, not move

These files are outside the production three-node builder and are directly
referenced only by dedicated tests or notebook/example code:

- `apps/*/src/*_agent/rest_agent/agents/dine_in.py`
- `apps/*/src/*_agent/rest_agent/agents/get_journey_instructions.py`
- `apps/*/src/*_agent/rest_agent/agents/router_agent.py`
- `apps/*/src/*_agent/rest_agent/agents/router_agent_prompt.md`
- `apps/*/src/*_agent/rest_agent/agents/prompts/dinein_agent_prompt.md`
- `apps/*/src/*_agent/rest_agent/agents/prompts/delivery_agent_prompt_TBD.md`
- Unreachable sender helpers `delivery_or_takeaway`,
  `send_postcode_search_flow`, and `reservation_link_wa_send` at
  `agent_wa_senders.py:40-61,224-247,316-335`.

Delete their active-suite tests with the code:

- `tests/rest_agent/agents/test_dine_in_agent.py`
- `tests/rest_agent/agents/test_journey_instructions.py`
- `tests/rest_agent/agents/test_router_agent.py`

Do not edit `tests/legacy_contract` unless the task is explicitly expanded to
legacy-contract work; root Pytest excludes it at `pyproject.toml:26-33`.

## Implemented layout

```text
packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/
  __init__.py              # exports RestaurantPrompts, RestaurantGraphAdapter
  prompts.py               # three-string frozen value object only
  agent_runner.py          # generic standard GraphAdapter
  agent_wa_senders.py      # live standard senders only
  agents/
    __init__.py
    agent_harness.py
    triage.py
    delivery.py
    takeaway.py
    multi_agent.py         # fixed three-node graph and one internal build path

apps/<app>/src/<app>_agent/rest_agent/
  __init__.py
  agent_recipe.py          # prompt loading + existing GraphAdapterFactory partial
  prompts/
    triage_agent_prompt.md
    delivery_multiagent_prompt.md
    takeaway_agent_prompt.md
  tools/                   # only if genuinely custom
  callbacks/               # only if genuinely custom
  routers/                 # only if genuinely custom
  agents/                  # complete named replacements only
```

## Minimal public contract

The public shape is deliberately small:

```python
@dataclass(frozen=True, slots=True)
class RestaurantPrompts:
    triage: str
    delivery: str
    takeaway: str


class RestaurantGraphAdapter:
    def __init__(
        self,
        runtime: RestaurantRuntime,
        *,
        prompts: RestaurantPrompts,
        extra_tools_by_agent: Mapping[str, Sequence[BaseTool | Callable]] | None = None,
        agent_overrides: Mapping[str, Runnable] | None = None,
    ) -> None: ...
```

Rules:

- Allowed mapping keys are only `triage_agent`, `delivery_agent`, and
  `takeaway_agent`; unknown keys raise ordinary `ValueError` during app
  construction.
- `RestaurantPrompts` rejects empty strings with ordinary `ValueError`.
- Extra tools are appended to the existing tool order. They remain native
  LangChain tools/callables; there is no `ToolSpec`.
- A replacement is a native runnable with `ainvoke` and must preserve the
  standard node name, `AgentState`, `ContextSchema`, and handoff behavior.
- The adapter constructs standard agent runnables and the `StateGraph` builder
  once in `__init__`. It retains current compile-with-checkpointer behavior per
  operation. No graph cache or lifecycle lock is introduced in this pass.
- Apps import only `RestaurantPrompts` and `RestaurantGraphAdapter` from this
  subpackage. Internal agent modules are not extension APIs.

Example app recipe:

```python
from functools import partial
from pathlib import Path

from restaurant_agent_runtime.rest_agent import (
    RestaurantGraphAdapter,
    RestaurantPrompts,
)

_PROMPT_DIR = Path(__file__).parent / "prompts"
PROMPTS = RestaurantPrompts(
    triage=(_PROMPT_DIR / "triage_agent_prompt.md").read_text(),
    delivery=(_PROMPT_DIR / "delivery_multiagent_prompt.md").read_text(),
    takeaway=(_PROMPT_DIR / "takeaway_agent_prompt.md").read_text(),
)
GRAPH_ADAPTER_FACTORY = partial(RestaurantGraphAdapter, prompts=PROMPTS)
```

`main.py` passes `GRAPH_ADAPTER_FACTORY` directly to the existing
`create_restaurant_app(..., graph_adapter_factory=...)` argument. No web factory
change is needed.

## Application-level customization

### Compatible customization using the standard adapter

- Add native tools to an existing node through `extra_tools_by_agent`.
- Replace an entire standard node runnable through `agent_overrides`.
- Keep the complete custom implementation under the owning app's `rest_agent`
  package and import it only from `agent_recipe.py`.
- Continue using `AgentBindings` for a custom callback data type or replacement
  service-selection sender (`web/app_factory.py:22-28,111-149`).

### Custom callbacks and routes without a recipe framework

After calling `create_restaurant_app()`, an app may register genuine custom
PyWa handlers on `app.state.restaurant_runtime.async_wa_client` and include
native FastAPI routers with `app.include_router()`. Standard runtime and adapter
objects are already stored on `app.state` at `web/app_factory.py:232-234`.

If custom handler ordering makes post-registration incorrect, the app owns its
application factory. Do not add a generic handler registry to the shared runtime.

### When an app owns `GraphAdapter`

Use an app-owned adapter when any of these changes are required:

- Add or remove graph nodes.
- Change routing or handoff node names.
- Change `AgentState` fields/reducers incompatibly.
- Change checkpointing, thread identity, repair, debug, or compilation behavior.
- Mutate private shared-runtime graph internals.

The custom adapter must still implement `runtime.py:63-81`, bind the exact
`RestaurantRuntime`, use its exact WhatsApp client in graph context, and preserve
route/WABA isolation.

### How Elai maps to the reduced seams

Elai remains design evidence, not migration scope:

| Elai behavior | Reference | Reduced treatment |
| --- | --- | --- |
| Restaurant selection tools | `/Users/basavaraj/bloop/elai/rest_agent/agents/triage.py:168-183,286-322` | App-owned triage tools or a complete triage replacement. |
| Selection buttons | `/Users/basavaraj/bloop/elai/rest_agent/agent_wa_senders.py:140-166` | App-owned native sender. |
| `/SelectRestRef` callback | `/Users/basavaraj/bloop/elai/watomation/on_callback_handler.py:274-315` and `watomation/fapp.py:188-189` | App-owned PyWa handler registered during app assembly. |
| Dine-in node | `/Users/basavaraj/bloop/elai/rest_agent/agents/multi_agent.py:65-117,142-173` | App-owned `GraphAdapter` because this changes the fixed standard graph. |
| Selected Restaurant state | Elai transfer guard at `agent_harness.py:240-270` | Remains app-owned with the custom adapter; it never changes application identity or WABA namespace. |

This handles the demonstrated custom behavior without adding a standard
selection policy, state-extension system, or node registry before a second
compatible consumer exists.

## Five-checkpoint implementation record

SFCS and BNAT were cut over together. The sections below record the review
checkpoints and are not separately supported production architectures.

### Checkpoint 1: Characterize the live graph

1. Add a focused graph contract test under `tests/rest_agent/` asserting the
   three node names, conditional destinations, and the ordered default tool
   names shown at `multi_agent.py:79-114`, `triage.py:251-258`,
   `takeaway.py:78-83`, and `delivery.py:775-789`.
2. Preserve current tests for `AgentState`, transfer guards, middleware,
   takeaway payment branches, runner repair behavior, and WhatsApp senders.
3. Record that the three production SFCS/BNAT prompt files compare byte-for-byte,
   but assert only app ownership/presence—not shared content.
4. Do not snapshot serialized private LangGraph objects or exact generated LLM
   text.

### Checkpoint 2: Remove only move-blocking import-time coupling

1. Stop live agent modules from reading prompts at import
   (`triage.py:44-45`, `takeaway.py:29-30`, `delivery.py:794-795`).
2. Stop live agent modules from choosing the model through module-global
   `llm_settings` (`triage.py:40,260-267`, `takeaway.py:20,86-97`,
   `delivery.py:41-43,808-819`). Pass the selected model internally from
   `runtime.settings.llm` during standard adapter construction.
3. Preserve runtime context construction exactly at
   `agent_runner.py:159-235`, including the exact async WhatsApp client.
4. Do not refactor unrelated handler, order, payment, AWS, or cache globals in
   this commit; record them in the shared-runtime review below.

### Checkpoint 3: Move the live implementation into the runtime

1. Create `restaurant_agent_runtime/rest_agent/` using the reduced target layout.
2. Move the live symbols listed in the reference map, rewriting only package
   imports and composition inputs.
3. Add `RestaurantPrompts` and generic `RestaurantGraphAdapter`.
4. Add only the two mapping arguments. Validate non-empty prompts and known
   standard node keys with ordinary `ValueError`.
5. Build standard runnables/builder once; preserve per-operation compile and
   checkpointer creation.
6. Do not change `runtime.py`, the `GraphAdapterFactory` type, or
   `web/app_factory.py` unless a failing characterization test proves the
   existing seam insufficient.

### Checkpoint 4: Cut both apps over and remove clones

1. Add SFCS and BNAT `rest_agent/agent_recipe.py` modules and move their three
   live prompts to app-owned `rest_agent/prompts/` directories unchanged.
2. Update both `main.py` files to pass their `GRAPH_ADAPTER_FACTORY` and shared
   standard `AgentBindings` implementations.
3. Delete both app copies of live standard Python modules and both shallow
   adapter classes.
4. Delete the dormant duplicates and their active-suite tests listed above.
   Remove the now-unused `transfer_to_dinein` test stub at
   `tests/_stubs/agent_stubs.py:95-108` at the same time.
5. Add one small composition test per app proving its factory binds the exact
   app runtime/client and loads that app's prompt files.

### Checkpoint 5: Repoint tests and close the migration

1. Change `tests/_stubs/loader.py:19-33` from the SFCS `rest_agent` source/module
   mapping to `restaurant_agent_runtime.rest_agent`.
2. Repoint live Agent tests such as
   `tests/rest_agent/agents/test_agent_harness.py:11-20` and
   `test_takeaway_agent.py:76-82` to shared-runtime symbols.
3. Update `tests/test_activity.py:171-204` to scan the single runtime runner rather
   than two app runners.
4. Preserve and run runtime isolation tests at
   `tests/test_runtime_isolation.py:94-147,190-242,303-323`.
5. Confirm no shared-runtime import starts with `sfcs_agent` or `bnat_agent`, neither app
   imports the other, and app `rest_agent` directories contain only recipe,
   prompts, and genuine custom code.
6. Add discovered non-behavioral cleanup to the ledger; do not fix prompt drift
   or unrelated shared-runtime findings in this commit.

## `restaurant-agent-runtime` review

These are concrete follow-ups, not reasons to grow the Agent composition API.
Only a finding proven to block the move entered checkpoints 2-4.

| Finding | Current references | Disposition |
| --- | --- | --- |
| `lg_utils.py` mixes LLM construction, legacy builders, thread lookup, graph display, and REPL helpers | `services/lg_utils.py:33-47,56-118,129-228,442-471,518-602` | The live Agent move stops importing its module-global model. Split/delete the remaining catch-all later after usage-specific tests exist. |
| Shared WhatsApp diagnostic handlers still bypass runtime database clients | `watomation/on_message_graph_handler.py:33-34,127-171,198-308` | Separate runtime-injection follow-up; do not mix `/test`, `/test-t`, `/reset`, or payment-simulation behavior changes into Agent centralization. |
| Payment helpers capture settings/client globals | `services/payment_ms/payment.py:18-36,40-137` | Separate service refactor with payment contract tests. |
| Order code has competing legacy/new models and global settings | `services/order_management/order_db_ops.py:1-35`; `order_db_ops_new.py:1-36`; receipt imports `OrderItem` at `food_order_reciept.py:15-17` | Decide canonical model in a dedicated change; behavior differs and is too risky for this move. |
| In-memory thread fallback remains in production utility imports | `services/thread_handlers.py:20-116`; used by `lg_utils.py:35,442-471` | Delete only after callers/tests are migrated away in a separate cleanup. |
| AWS secret is loaded at import | `utils/aws_setting.py:101-108`; settings modules import `agent_env` | Separate configuration-lifecycle refactor; current tests intentionally stub this behavior. |
| Restaurant/base URL and dedup caches are process-local | `config/params.py:30-32,48-132`; `watomation/dedup.py:23-39` | Document one-worker constraint; revisit only with multi-instance requirements. |
| PGVector example/retriever code is inconsistent with the commented store property | `config/pg_setting.py:19,180-183,216-232` | Delete or repair in a dedicated dead-code cleanup. |

## Post-migration cleanup ledger

Deferred release and cleanup work is maintained in
[`docs/to-do.md`](../to-do.md). The runtime-review findings above provide the
supporting code references for those follow-ups.

## Verification and release gate

Run from repository root:

```bash
uv run pytest tests/rest_agent tests/test_activity.py tests/test_runtime_isolation.py
uv run pytest apps/sfcs/tests apps/bnat/tests
uv run pytest
uv run ruff check .
git diff --check
```

Required evidence:

- The current three-node/edge/tool contract is unchanged.
- Both app composition tests bind their exact `RestaurantRuntime` and async
  WhatsApp client.
- `tests/test_runtime_isolation.py` continues to prove separate identities,
  clients, WABA namespaces, and cross-Restaurant `404` before side effects.
- Root Pytest stays green; `tests/legacy_contract` remains excluded unless
  separately requested.
- No live Meta, database, payment, rider, order, or webhook side effects occur
  during automated validation.
- Both deployable artifacts are built later from the same commit and root
  lockfile. Live WhatsApp canaries remain separately authorized.

## Success criteria

- One production standard Agent implementation exists in the shared runtime.
- SFCS and BNAT own complete prompts and a tiny `agent_recipe.py`, not copied
  standard agent code.
- The standard web/runtime contracts are reused unchanged.
- Custom tools and whole named-agent replacements can remain app-owned without
  a registry or framework wrapper.
- New graph shapes use the existing app-owned `GraphAdapter` escape hatch.
- Dormant duplicated code is removed rather than promoted into the runtime.
- The plan leaves a concrete, code-referenced path for later shared-runtime cleanup.

Implementation was explicitly authorized by the repository owner on 2026-07-29.
