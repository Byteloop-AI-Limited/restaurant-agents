# Runtime observation

## Local FastAPI

Run commands from the repository root after the owner has supplied the four
bootstrap variables required by `AGENTS.md`. Never inspect, copy, source, or
print a `.env` file.

Choose a free loopback port and use the same port for health checks:

```bash
uv run --package <sfcs-agent-or-bnat-agent> uvicorn <module>:app \
  --host 127.0.0.1 --port <port>
curl --fail http://127.0.0.1:<port>/healthz
```

Use `sfcs_agent.main:app` for SFCS and `bnat_agent.main:app` for BNAT. Start
one worker only. Keep stdout/stderr attached to the terminal; inspect a short
window after each request and stop the process once the test ends. Do not send
real webhook, WhatsApp, payment, rider, order, or thread events to this local
server unless separately authorized.

## Deployed runtime

Read the relevant `apps/<app>/fly.toml` before running a read-only health or
log command. With configured access, use the manifest's app name:

```bash
fly logs -a <app-name>
curl --fail https://<app-host>/healthz
```

Use a short time window and redact user data. Log access does not authorize a
deploy, secret change, WABA change, or any Meta action.

## Computer Use loop

Use `com.google.Chrome` and refresh state immediately before each action:

```js
state = await sky.get_app_state({ app: "com.google.Chrome" });
// Act only on an element/index from this state.
await sky.click({ app: "com.google.Chrome", element_index: /* current */ });
state = await sky.get_app_state({ app: "com.google.Chrome" });
```

If the state changes while waiting, refresh it before the next action. Do not
reuse old element indices, and use screenshots only to resolve missing or
ambiguous accessibility information.
