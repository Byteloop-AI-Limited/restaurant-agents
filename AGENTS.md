# Repository Instructions

## Governing architecture

Read [`CONSTITUTION.md`](CONSTITUTION.md) completely before planning or changing
this repository. It is the governing architecture for all development here.

If a requested change conflicts with the constitution, stop and resolve the
conflict with the repository owner before editing. Amend the constitution only
when the owner explicitly approves the architectural change.

## Repository shape and boundaries

This is one Python 3.13 UV workspace with one root lockfile:

- `packages/restaurant-agent-core` contains reusable configuration, services,
  WhatsApp automation, web factories, runtime interfaces, and shared models.
- `apps/sfcs` contains the SFCS application, identity, prompts, graph adapter,
  Fly manifest, and app-specific tests.
- `apps/bnat` contains the Burger Nation application, identity, prompts, graph
  adapter, Fly manifest, and app-specific tests.

Keep SFCS and BNAT as independent applications. An app must never import the
other app package. Shared implementations belong in `restaurant-agent-core`,
while restaurant identity, presentation, prompts, graph logic, and entrypoints
remain app-owned.

Preserve the runtime contract described by the constitution:

- Load only the requested WABA namespace and fail startup if it is incomplete.
- Bind one WhatsApp client to the app runtime and pass that same client through
  handlers, routers, services, and graph context.
- Require restaurant-prefixed routes to match the running app's identity and
  return `404` without side effects for cross-restaurant paths.
- Preserve public route paths and response schemas.
- Keep one worker per app. Do not introduce module-global WhatsApp clients or
  direct shared imports of an app's `rest_agent` implementation.

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
  --port 8000
```

Start Burger Nation on localhost:

```bash
uv run --package bnat-agent uvicorn bnat_agent.main:app \
  --host 127.0.0.1 \
  --port 3100
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
