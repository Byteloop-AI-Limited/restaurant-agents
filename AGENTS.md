# Repository Instructions

## Governing architecture

Read [`CONSTITUTION.md`](CONSTITUTION.md) completely before planning or changing
this repository. It is the governing architecture for all development here.

If a requested change conflicts with the constitution, stop and resolve the
conflict with the repository owner before editing. Amend the constitution only
when the owner explicitly approves the architectural change.

## Architecture and domain documentation

[`docs/README.md`](docs/README.md) is the documentation entry point. Before
changing domain ownership, data authority, application composition, graph
behavior, integration contracts, or shared-runtime interfaces, read:

- [`docs/glossary.md`](docs/glossary.md) for the repository's ubiquitous
  language.
- [`docs/domain/platform-domain-model.md`](docs/domain/platform-domain-model.md)
  for bounded contexts, aggregates, projections, authority chains, commands,
  events, and external systems.
- [`docs/adr/README.md`](docs/adr/README.md) and the relevant accepted ADRs for
  durable decisions and consequences.
- The relevant feature guide under `docs/` for implemented flow and code
  references.

The major composition constructs are `RestaurantIdentity`,
`RestaurantPresentation`, `RestaurantSettingsBundle`, `RestaurantRuntime`,
`RestaurantPrompts`, `AgentBindings`, `GraphAdapter`, `GraphAdapterFactory`,
`RestaurantGraphAdapter`, and `create_restaurant_app`. The canonical explanation
of how they compose is [`docs/multi_agent_system.md`](docs/multi_agent_system.md).

Update the glossary when a term is introduced, renamed, or changes meaning.
Update the domain model when ownership, authority, commands, events, or context
boundaries change. Add or supersede an ADR for a significant architectural
decision; do not rewrite accepted history. Keep machine-readable `code-ref`
blocks aligned with symbol moves. HTML guides are secondary views and must not
contain rules absent from canonical Markdown.

## Repository shape and boundaries

This is one Python 3.13 UV workspace with one root lockfile:

- `packages/restaurant-agent-runtime` contains reusable configuration, services,
  WhatsApp automation, web factories, runtime interfaces, shared models, and
  the standard Agent runtime.
- `apps/sfcs` contains the SFCS application, identity, complete prompts, Agent
  recipe, any genuinely custom Agent artifacts, Fly manifest, and app-specific
  tests.
- `apps/bnat` contains the Burger Nation application, identity, complete
  prompts, Agent recipe, any genuinely custom Agent artifacts, Fly manifest,
  and app-specific tests.

Keep SFCS and BNAT as independent applications. An app must never import the
other app package. Shared implementations belong in `restaurant-agent-runtime`.
Restaurant identity, presentation, complete prompts, app recipes, entrypoints,
and genuinely custom behavior remain app-owned. Incompatible graph behavior may
remain behind an app-owned `GraphAdapter` under the constitutional criteria.

Preserve the runtime contract described by the constitution:

- Load only the requested WABA namespace and fail startup if it is incomplete.
- Bind one WhatsApp client to the app runtime and pass that same client through
  handlers, routers, services, and graph context.
- Require restaurant-prefixed routes to match the running app's identity and
  return `404` without side effects for cross-restaurant paths.
- Preserve public route paths and response schemas.
- Keep one worker per app. Do not introduce module-global WhatsApp clients or
  direct shared imports of an app's `rest_agent` implementation.

## Shared Agent runtime architecture

The approved Agent centralization and app-extension rules are recorded in
[`docs/architecture/shared-agent-runtime-decisions.md`](docs/architecture/shared-agent-runtime-decisions.md).
They describe the implemented layout and its deliberately small customization
contract. Do not duplicate or move the implementation back into an application.

The standard Agent implementation belongs in
`restaurant-agent-runtime`. Each app retains a small `rest_agent` package for its
complete prompts, one `agent_recipe.py`, and only genuinely custom tools,
callbacks, routes, or complete named-agent replacements. Do not copy a shared
Agent module into an app to customize it; use the documented adapter constructor
seam. Keep behavior app-owned while only one app
needs it; when a second app needs compatible semantics, review it deliberately
for promotion into the shared runtime instead of copying it.

Every application using the shared runtime must own a small composition test.
It must construct the app's graph factory, prove exact runtime and WhatsApp-
client binding, and prove that all three complete app-owned prompts are loaded.
Shared-runtime tests own the standard nodes, edges, tools, routing, repair,
debug, and adapter behavior.

An app's `agent_recipe.py` is a composition module, not an instance of a shared
recipe framework. It loads a `RestaurantPrompts` value and exposes a
`partial(RestaurantGraphAdapter, ...)` compatible with the existing
`GraphAdapterFactory`.

Use framework-native contribution objects whenever possible, including
LangChain tools, FastAPI routers, and PyWa callbacks. Add a narrow shared wrapper
only when the native object lacks graph metadata or startup-validation data
required by the composition contract. Do not create parallel shared abstractions
for behavior the framework already represents.

Use only two optional standard-adapter mappings: `extra_tools_by_agent` for
native tools added to an existing standard node and `agent_overrides` for a
complete native runnable replacing an existing standard node. Unknown node
names raise ordinary `ValueError`. New nodes, incompatible state, routing,
handoffs, checkpointing, repair, or debug behavior require an app-owned
`GraphAdapter`; do not create `AgentNodeSpec` or a node registry.

Keep construction simple: `RestaurantGraphAdapter.__init__` is the only new
composition boundary and is reached through the existing
`GraphAdapterFactory`. Do not add a separate composer or public per-agent
factories. Build standard runnables and the graph builder once; preserve current
per-operation compile/checkpointer behavior during the extraction.

SFCS and BNAT use the shared runtime together and must be released from the same
repository revision. Do not create an intermediate supported state where only
one of these two apps uses the shared implementation. Keep auditable commit and
release rollback points around changes to the shared runtime. Elai is design
evidence, not part of this migration scope.

The implementation followed five auditable checkpoints: characterize both apps;
inject only move-blocking prompt/model dependencies; add the standard runtime
adapter and prompt value; cut SFCS and BNAT over to app prompt/factory modules
together; then remove both duplicated implementations and finalize
documentation. These are development checkpoints, not separately supported
production architectures.

Keep the coordinated extraction behavior-preserving except for changes strictly
required to inject the runtime and enforce the governing invariants. Record
every discovered quirk, dead path, naming issue, temporary compatibility shim,
and deferred simplification in [`docs/to-do.md`](docs/to-do.md). Address those
items in later focused changes after the shared release is stable; do not
silently normalize behavior during an extraction.

Define migration parity through observable routing, handoffs, exposed tools,
state transitions, callbacks/routes, repair/debug behavior, exact runtime
binding, and mocked outbound calls. Do not snapshot private graph internals or
exact LLM output. Keep prompts app-owned and test their required presence and
app-specific behavior in app tests.

The automated gate is the full offline suite plus safe startup/composition
smoke tests for both apps. Live WhatsApp probes require separate authorization
and run only as bounded post-deployment canaries. Build both artifacts from the
same commit and root lockfile, release them in one coordinated window, and roll
both back if either app's health check or authorized canary fails.

The repository owner approved the constitutional amendment and implementation
on 2026-07-29, then reduced it to the concrete contract documented in
`docs/architecture/shared-agent-runtime-decisions.md`. The standard runtime,
coordinated app cutover, and clone cleanup are implemented. Deferred service and
prompt-identity work remains in `docs/to-do.md`.

## Setup and routine commands

Run commands from the repository root.

```bash
uv sync --all-packages
uv run ruff check .
uv run pytest
git diff --check
```

Prefer the smallest relevant test scope while developing, then run the complete
suite before handing off a cross-cutting change:

```bash
uv run pytest apps/sfcs/tests
uv run pytest apps/bnat/tests
uv run pytest tests
```

The root Pytest configuration deliberately excludes `tests/legacy_contract`
from normal collection. Do not treat that directory as part of the default test
suite unless a task explicitly targets legacy contract work.

## Run an application locally

Local startup reads the shared application configuration from AWS Secrets
Manager during module import. Before starting an app, provide these bootstrap
variables in the current shell using values supplied by the repository owner or
the approved local secret-management workflow:

```text
AWS_SETTINGS_KEY_ID
AWS_SETTINGS_ACCESS_KEY
AWS_SETTINGS_REGION
AWS_SETTINGS_SECRET_NAME
```

The runtime currently reads the shared `restaurant-agents-env` AWS secret;
`AWS_SETTINGS_SECRET_NAME` is still required when local AWS settings are
initialized. That secret must contain the shared settings and the complete
namespaced WABA settings for the app being started. Never put credentials or a
`.env` file in this repository and never print secret values in logs, tests, or
handoff notes.

Start SFCS on localhost:

```bash
uv run --package sfcs-agent uvicorn sfcs_agent.main:app \
  --host 127.0.0.1 \
  --port 3101
```
3101 -> http://rest-agent-test.ordelo.app
Start Burger Nation on localhost:

```bash
uv run --package bnat-agent uvicorn bnat_agent.main:app \
  --host 127.0.0.1 \
  --port 3101
```

Using different ports allows both applications to run simultaneously. Verify
the selected process with its local health endpoint:

```bash
curl --fail http://127.0.0.1:8000/healthz  # SFCS
curl --fail http://127.0.0.1:8001/healthz  # Burger Nation
```

Do not send real webhook, WhatsApp, payment, rider, order, or thread events from
a local process unless the repository owner explicitly authorizes the external
side effects and provides a safe test configuration.

## Change discipline

- Inspect existing code and tests before editing; preserve unrelated user
  changes in a dirty worktree.
- Use dependency versions from the root `uv.lock`. Add dependencies to the
  package that owns the requirement and update the single lockfile.
- Put app-specific tests under `apps/<restaurant>/tests` and reusable behavior
  tests under `tests`.
- For shared runtime or routing changes, verify both apps and the isolation
  guarantees in the constitution, not only the app that motivated the change.
- Keep each `fly.toml`, deployment reference, app identity, and entrypoint
  app-owned. The entrypoints are `sfcs_agent.main:app` and
  `bnat_agent.main:app`.
- Do not build Docker images unless the repository owner explicitly requests
  it; validate Docker changes statically by default.
- Never copy `.env` files or credentials into this repository.
- Do not deploy, create or change cloud resources, or create a Git remote unless
  explicitly requested.
