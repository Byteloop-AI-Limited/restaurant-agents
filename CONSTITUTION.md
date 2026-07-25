# SFCS and BNAT UV Workspace Monorepo

- Status: Approved
- Date: 2026-07-25
- SFCS source: `feature/fly-move@ce46201ddf68ce082278ca94b4f5ffdf3ba35b7c`
- BNAT source: `main@db3d4be6b3417338ae12a99a18f1194914482563`

## Summary

Create `/Users/basavaraj/bloop/restaurant-agents` as a new local Git repository containing:

```text
restaurant-agents/
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── packages/
│   └── restaurant-agent-core/
└── apps/
    ├── sfcs/
    └── bnat/
```

SFCS and BNAT remain completely separate Fly applications, images, processes, WhatsApp clients, webhook registrations, and deployments. Only reusable source code is centralized.

Use SFCS's Python and dependency versions as the workspace baseline. Elai is excluded.

## Target Architecture

### Shared core

Create the `restaurant-agent-core` distribution with the import namespace `restaurant_agent_core`. Move reusable implementations into it:

- Pydantic configuration models and AWS secret loading.
- `services`, `watomation`, `utils`, activity tracking, background-task handling, and reusable data models.
- FastAPI application, handler, and router factories.
- Shared Docker/startup/Gunicorn infrastructure.

UV workspaces use one repository and lockfile for interconnected packages, matching this architecture. [UV workspace documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/)

### Restaurant applications

Create workspace members `sfcs-agent` and `bnat-agent`. Each owns:

- Its complete `rest_agent` implementation and prompt files.
- `RestaurantIdentity` and presentation settings.
- Its FastAPI entrypoint.
- Fly manifest, deployment reference, and app-specific tests.
- SFCS uses `rest_ref="SFCS"` and `waba_namespace="sfcs"`.
- BNAT uses `rest_ref="BNAT"` and `waba_namespace="bnat"`.

No app may import the other app package.

### Runtime interfaces

Add these shared interfaces:

- `RestaurantIdentity`: immutable `rest_ref` and `waba_namespace`.
- `RestaurantSettingsBundle`: shared project, database, LLM, payment, maps, and namespaced WABA settings.
- `RestaurantRuntime`: identity, settings bundle, and the restaurant's async and sync WhatsApp clients.
- `GraphAdapter`: protocol exposing `run_rest_graph_with_custom_msg`, `debug_state`, `debug_state_values`, and `debug_state_by_thread`.
- `create_restaurant_app(identity, graph_adapter_factory) -> FastAPI`.

The app factory must:

1. Load the requested namespace without fallback.
2. Fail startup when any namespaced WABA setting is missing.
3. Construct one server-bound WhatsApp client using that namespace's phone ID, verify token, token, and app secret.
4. Enable `validate_updates=True`.
5. Construct the restaurant graph adapter with the same client object.
6. Inject the runtime and adapter into every handler, router, graph context, and WA-sending service.

Remove module-global `_async_wa_client`, `_sync_wa_client`, `waba_business_settings`, and direct shared imports of `rest_agent.agent_runner`.

## Migration

1. Commit BNAT's current WABA cleanup, Fly command reference, and `fly_deploy_env_secrets.sh` before importing it.
2. Record the exact SFCS source as `feature/fly-move@ce46201d` and the resulting BNAT source commit.
3. Initialize the new local repository on `main`, with no remote.
4. Import curated, secret-free SFCS and BNAT snapshots in one provenance commit.
5. Add the root UV workspace and one shared lockfile using SFCS's dependency pins and Python `>=3.13,<3.14`.
6. Extract `config`, `services`, `watomation`, and `utils` into the namespaced shared package. Keep both `rest_agent` trees app-owned.
7. Replace hardcoded restaurant content in shared services with injected presentation settings such as display name, logo URL, contact details, and feature flags.
8. Convert shared routers into factories bound to one `RestaurantRuntime`:
   - Preserve existing public route paths and response schemas.
   - Require every `/{rest_ref}/...` route to match the local runtime identity, not merely any valid database restaurant.
   - Reject cross-restaurant paths with `404` before sending messages, invoking graphs, or scheduling background work.
   - Preserve the current stale-thread `202`, prefix validation, per-thread isolation, and concurrency behavior.
9. Add `sfcs_agent.main:app` and `bnat_agent.main:app`, each assembling its own runtime and graph adapter.
10. Remove the duplicated shared directories from both app members.
11. Fix inherited Ruff findings and reconcile the stale SFCS single-restaurant test so the new repository starts with green checks.

## Docker and Fly

Use one multi-stage root Dockerfile with required `APP_PACKAGE`. It installs only the selected app and `restaurant-agent-core` using a non-editable workspace installation; the final image must not contain the other restaurant package. UV documents workspace-specific Docker layering and `--no-install-workspace` usage. [UV Docker guidance](https://docs.astral.sh/uv/guides/integration/docker/)

Each Fly manifest remains app-owned:

- SFCS: `app="sfcs-agent"`, `APP_MODULE="sfcs_agent.main:app"`.
- BNAT: `app="bnat-agent"`, `APP_MODULE="bnat_agent.main:app"`.

Manual deployments remain independent:

```bash
fly deploy . \
  --config apps/sfcs/fly.toml \
  --dockerfile Dockerfile \
  --build-arg APP_PACKAGE=sfcs-agent \
  --ha=false
```

```bash
fly deploy . \
  --config apps/bnat/fly.toml \
  --dockerfile Dockerfile \
  --build-arg APP_PACKAGE=bnat-agent \
  --ha=false
```

Retain separate `SFCS_APP_URL` and `BNAT_APP_URL` Ordelo configuration values. No Fly or GitHub resources are created during the local implementation.

## Verification and Transition

- Run Ruff and all core, SFCS, and BNAT tests from the workspace.
- Statically verify both minimal Docker image definitions. Do not build images
  unless the repository owner explicitly requests it.
- Construct both FastAPI apps simultaneously with distinct fake clients and prove:
  - Correctly signed updates reach only the matching app.
  - Cross-signed Meta updates are rejected.
  - SFCS webhook calls invoke only the SFCS graph/client.
  - BNAT webhook calls invoke only the BNAT graph/client.
  - Cross-restaurant REST routes return `404` without side effects.
  - `run_rest_graph_with_custom_msg` places the exact app runtime's WA client into its graph context.
- Validate both Fly manifests independently.
- Keep deployment manual: migrate BNAT first, smoke-test WhatsApp, payment, rider, order, and thread webhooks, then migrate SFCS separately.
- Existing repositories remain active until a manual cutoff. Before an app migrates, its old repository remains authoritative; after migration, the monorepo becomes authoritative for that app and any emergency old-repository fix must be forward-ported.

## Fresh-session implementation prompt

Open `/Users/basavaraj/bloop/restaurant-agents/CONSTITUTION.md` before making changes in this repository. Treat it as the governing architecture unless the owner explicitly amends it. Do not deploy, create a remote, or copy secrets. Preserve unrelated user changes and verify implementation changes with focused tests, Ruff, and `git diff --check`.
