# Onboarding a new Fly app

Use this guide when a restaurant application already exists in this workspace
but has no Fly app or Machines yet. ELAS is the worked example. This guide
documents manual owner-operated deployment; creating resources, deploying, and
changing live callbacks require the owner's explicit authorization.

You do not need to create a Machine through the Fly portal. Create the Fly app
with the CLI, add its bootstrap secrets, then deploy using the repository's
existing script. The first deployment creates the application Machine and
public networking from the app-owned `fly.toml`. The portal can then be used
to inspect the app, Machines, metrics, and logs.

This is infrastructure onboarding for an implemented application. Adding a
new restaurant package, identity, prompts, or graph behavior is separate
development governed by [CONSTITUTION.md](../CONSTITUTION.md).

## Existing deployment documentation

The app guides document repeat deployments and app-specific prerequisites:

- [SFCS deployment](../apps/sfcs/DEPLOYMENT.md)
- [BNAT deployment](../apps/bnat/DEPLOYMENT.md)
- [ELAS deployment and legacy Elai cutover](../apps/elas/DEPLOYMENT.md)

This guide adds the initial Fly app creation and secret setup steps.

## 1. Select the application and release revision

Run commands from the repository root:

```bash
cd /Users/basavaraj/bloop/restaurant-agents
git status --short
git rev-parse HEAD
```

Choose a reviewed release revision. `fly deploy` uploads the working directory,
so uncommitted changes can be included; resolve the intended release contents
before deploying and preserve unrelated work.

| Application | Script selector | Fly app | Python entrypoint | WABA namespace | Ordelo URL key |
| --- | --- | --- | --- | --- | --- |
| SFCS | `sfcs` | `sfcs-agent` | `sfcs_agent.main:app` | `sfcs` | `SFCS_APP_URL` |
| BNAT | `bnat` | `bnat-agent` | `bnat_agent.main:app` | `bnat` | `BNAT_APP_URL` |
| ELAS | `elas` | `elas-agent` | `elas_agent.main:app` | `elas` | `ELAS_APP_URL` |

Read the selected app's deployment guide and `fly.toml`. ELAS's
[manifest](../apps/elas/fly.toml) configures London (`lhr`), port 8080,
`shared-cpu-1x` with 1 GB RAM, one worker, HTTPS, `/healthz` checks, and
auto-stop disabled. Keep the one-worker runtime contract.

For a shared-runtime release, the constitution requires all app artifacts to
come from the same repository commit and root lockfile, with a coordinated
release window and rollback if any app fails its health check or authorized
canary. Check the deployed SFCS and BNAT revisions when onboarding ELAS;
coordinate their releases if necessary to avoid mixed runtime revisions.

Complete the repository's offline release gate before deployment:

```bash
uv sync --all-packages
uv run ruff check .
uv run pytest
git diff --check
```

These checks do not prove live AWS, Meta, Ordelo, or payment connectivity.
Do not build Docker images as a routine documentation or static-validation
step; an authorized deployment builds the selected artifact.

## 2. Log in and create the Fly app

The Fly CLI must be installed and authenticated to the intended organization.
If it is already authenticated, skip login.

```bash
fly version
fly auth login
fly orgs list
```

Replace `YOUR_ORG_SLUG` with the organization used for the existing agents:

```bash
fly apps create elas-agent --org YOUR_ORG_SLUG
```

[`fly apps create`](https://docs.fly.io/flyctl/cmd/fly_apps_create) creates
the app without generating or replacing a `fly.toml`. Use the manifest already
in `apps/elas`; there is no need to run a configuration-generating `fly launch`.
If the name is unavailable, choose an available name and align the app-owned
manifest and all subsequent commands and URLs with it.

## 3. Prepare the AWS application configuration

The app loads shared configuration from AWS Secrets Manager during application
construction. The current settings-bundle loader explicitly requests
`restaurant-agents-env`. `AWS_SETTINGS_SECRET_NAME` is still required to
construct the bootstrap settings; set it to `restaurant-agents-env`.

Before starting ELAS, verify that this AWS secret contains the shared settings
and every required ELAS WABA field:

```text
elas_waa_account_id
elas_waa_business_account_id
elas_waa_token
elas_waa_phone_id
elas_waa_callback_url
elas_waa_verify_token
elas_waa_app_id
elas_waa_app_secret
elas_waa_private_key_password
```

The app loads only the `elas` namespace and fails startup if it is incomplete.
Use ELAS's own account, phone, token, and app settings; another restaurant's
namespace cannot substitute for it. Additional feature-specific configuration,
such as the private key used by WhatsApp Flows, must also be available when
that feature is used.

See the [settings-bundle loader](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/config/bundle.py),
[AWS bootstrap loader](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/utils/aws_setting.py),
and [namespaced WABA settings](../packages/restaurant-agent-runtime/src/restaurant_agent_runtime/config/waba_setting.py).

For ELAS, also confirm the canonical `ELAS` restaurant-master row and the menu
frontend's `/restaurant/chks` route. Elai and Wings and Things share the
canonical ELAS operational configuration; a separate CHKS restaurant-master
row is not required. See the [ELAS guide](../apps/elas/DEPLOYMENT.md).

## 4. Add Fly bootstrap secrets

Fly secrets are app-specific. ELAS does not inherit SFCS or BNAT's secrets.
Provide these four values through the approved local secret-management
workflow:

| Fly secret | Value |
| --- | --- |
| `AWS_SETTINGS_KEY_ID` | Approved AWS access key ID |
| `AWS_SETTINGS_ACCESS_KEY` | Corresponding AWS secret access key |
| `AWS_SETTINGS_REGION` | Region containing the shared AWS secret |
| `AWS_SETTINGS_SECRET_NAME` | `restaurant-agents-env` |

The AWS credentials must be able to read the shared secret, including any
required KMS decryption permissions. Keep credentials and `.env` files outside
this repository and do not print values in logs or handoff notes.

If the approved workflow supplies an external file containing only those four
`NAME=VALUE` lines, import it through standard input. Replace the example path
with the actual external file:

```bash
fly secrets import --app elas-agent --stage < /absolute/path/to/bootstrap.env
fly secrets list --app elas-agent
```

The list command shows names and metadata, not plaintext values. `--stage`
stores the secrets for the next deployment without starting a release. See
[Fly secrets documentation](https://docs.fly.io/apps/secrets).

The WABA, database, LLM, and other shared application settings stay in the AWS
secret; the four Fly secrets bootstrap access to it.

## 5. Deploy the selected application

```bash
scripts/deploy-agent.sh --app elas
```

The [deployment script](../scripts/deploy-agent.sh) runs:

```bash
fly deploy . \
  --config apps/elas/fly.toml \
  --build-arg APP_PACKAGE=elas-agent \
  --ha=false
```

The manifest points to the root Dockerfile using `../../Dockerfile`, resolved
relative to the manifest. The build selects ELAS and the shared runtime using
the root lockfile. `--ha=false` disables automatic spare Machines on the
initial deployment. Verify the resulting Machine count after deployment.

With this manifest's `[http_service]`, Fly automatically allocates public
IPv6 and shared IPv4 on the first deployment. Manual IP allocation and a
dedicated IPv4 are not needed for this setup. See
[Fly deploy](https://docs.fly.io/flyctl/cmd/fly_deploy) and
[public networking](https://docs.fly.io/networking/services).

## 6. Verify before moving production traffic

```bash
fly status --app elas-agent
fly checks list --app elas-agent
fly ips list --app elas-agent
curl --fail https://elas-agent.fly.dev/healthz
fly logs --app elas-agent
```

Confirm the Machine is running, health checks pass, and logs contain no startup
configuration errors. `fly logs` follows the log stream; use Ctrl-C to exit.
A successful health check proves the app responds, but does not validate an
end-to-end WhatsApp conversation or an order/payment flow. Live probes require
separate authorization and a bounded test configuration.

## 7. Cut ELAS over from legacy Elai

Record the previous Ordelo URL and effective Meta callback before changing
either. After the new deployment is healthy, coordinate these changes:

1. Set Ordelo's `ELAS_APP_URL` to `https://elas-agent.fly.dev`.
2. Set `elas_waa_callback_url` in the shared AWS secret to
   `https://elas-agent.fly.dev/` and restart/redeploy ELAS so it reloads the
   setting. The running app does not automatically reload an AWS secret edit.
3. Update Meta's effective webhook callback to `https://elas-agent.fly.dev/`
   using the matching ELAS verify token and account. Editing the AWS field
   alone does not update Meta's webhook registration.
4. Verify the effective callback and run only the separately authorized
   post-deployment canary.

If using a custom domain instead, configure its DNS and Fly certificate first,
verify HTTPS, and use that domain consistently for both URLs.

The [callback notebook](../notebooks/update_callback_url.py) contains a live
WABA callback update cell. Inspect its selected app and target URL before
executing it; it may target the local test tunnel. Also inspect any phone-level
callback override, which takes precedence over a WABA-level override.

As documented in the ELAS deployment guide, legacy Elai threads do not carry
`selected_rest_ref`; after cutover they will be asked to choose a restaurant
once. This is an accepted cutover consequence.

## Troubleshooting and rollback

| Symptom | Check |
| --- | --- |
| Fly app does not exist | Complete app creation in the intended organization; match the manifest's app name. |
| Startup fails while loading configuration | Check the four Fly secret names, AWS region, secret availability, IAM permissions, and complete ELAS namespace. |
| Health check fails | Inspect Fly logs, the entrypoint, and port 8080; allow the configured startup grace period. |
| Healthy app receives no WhatsApp updates | Inspect Meta's effective callback and override precedence; verify it targets the new ELAS app. |
| Ordelo still calls legacy Elai | Verify the effective `ELAS_APP_URL` configuration on the Ordelo side. |

If a cutover fails, restore the recorded Ordelo URL and Meta callback, restore
the corresponding AWS callback setting, and reload any affected runtime. Keep
the legacy deployment available until the cutover is verified. For a
coordinated shared-runtime release, follow the constitutional requirement to
roll all apps back to the previous known-good shared commit if any app fails.

Do not destroy the legacy app, change live order/payment state, or send customer
messages as an implicit rollback step.
