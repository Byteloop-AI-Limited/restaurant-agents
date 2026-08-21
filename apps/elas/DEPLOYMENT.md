# ELAS manual deployment

From the workspace root:

```bash
scripts/deploy-agent.sh --app elas
```

Extra arguments after `--app elas` are passed through to `fly deploy`. The
script runs `fly deploy . --config apps/elas/fly.toml --build-arg
APP_PACKAGE=elas-agent --ha=false`. The config builds the root `Dockerfile`
via `dockerfile = "../../Dockerfile"` (paths in `fly.toml` resolve relative
to the config file, not the workspace root).

The app must use the `elas_*` WABA secret namespace and `ELAS_APP_URL` Ordelo
configuration. Unlike SFCS and BNAT, ELAS serves two restaurant brands (Elai
and Wings and Things) behind one WhatsApp number — see
`src/elas_agent/identity.py`'s `restaurant_selection`. Both brands resolve to
the canonical `ELAS` `restaurant_master` row and Ordelo config on the Ordelo
side (`CHKS` aliases to `ELAS`); only the menu link and CTA logo vary per
brand.

To follow the deployed app's runtime logs:

```bash
fly --config apps/elas/fly.toml logs
```

## External prerequisites (owner-authorized, outside this repository)

The code in this app cannot function until an owner completes these steps.
None of them are actions this repository performs.

1. AWS secret `restaurant-agents-env`: add the complete `elas_waa_*` WABA
   namespace (`account_id`, `business_account_id`, `token`, `phone_id`,
   `callback_url`, `verify_token`, `app_id`, `app_secret`,
   `private_key_password`). Startup fails closed if any field is missing —
   there is no fallback namespace.
2. `ordelo_config`: `ELAS_APP_URL` must point at this deployment. **This is
   the cutover switch** — it currently points at the legacy `elai`
   deployment.
3. `elas_waa_callback_url` must redirect Meta's webhooks off the legacy
   `elai` deployment onto this app.
4. `restaurant_master` must have an `ELAS` row (hours, address, cutoffs). No
   `CHKS` row is needed — CHKS never drives operational data; see the
   selection-scope decision in ADR-0020.
5. The menu web app must serve `/restaurant/chks`. **Resolved 2026-08-17:**
   `elai`'s live menu-sending path (`agent_harness.py:_send_menu_tool` →
   `state["rest_ref"]`, set to `"chks"` by its `/SelectRestRef` callback)
   confirms `chks` is the correct slug for both the menu-link URL and the
   logo image filename (`chks_logo.jpg`, confirmed reachable). A `wits`
   filename exists in the same image repo but is referenced only by a
   commented-out, never-invoked carousel template experiment — not live
   code. Still confirm the menu web app itself actually serves
   `/restaurant/chks` before cutover; this only resolves which slug ELAS's
   own code should send, not the menu app's routing.

**Cutover consequence to state plainly:** in-flight `elai` threads carry no
`selected_rest_ref`. After cutover, each such thread is asked to choose once,
matching `elai`'s own reset semantics — this is expected, not a bug.
