---
name: verify-whatsapp-app-change
description: Verify restaurant-agents WhatsApp changes through a controlled Chrome/Computer Use conversation, local FastAPI observation, and runtime-log correlation. Use after SFCS or BNAT changes to prompts, callbacks, WABA/runtime configuration, message routing, service availability, tools, or replies when an auditable live or local verification loop is required.
---

# Verify a WhatsApp App Change

Use this skill after automated tests. Treat a browser reply as user-visible
evidence, not proof that the intended code revision handled the event.

## Establish scope and the verification surface

1. Read the repository instructions and identify the target app (`sfcs` or
   `bnat`), environment, revision, approved test-chat alias, scenario, and
   expected result.
2. Preserve unrelated working-tree changes. Never print credentials, full phone
   numbers, message payloads containing personal data, or secret-bearing URLs.
3. Obtain explicit authorization before actions with business effects. A normal
   greeting or `/reset` is low-risk only in an owner-approved test chat; orders,
   payments, reservations, consent writes, and test feedback submissions that notify real
   administrators need specific approval at the time of the action.
4. Choose the evidence source:

   | Need | Use |
   | --- | --- |
   | Unit/route behavior without external effects | Local FastAPI server and controlled HTTP tests |
   | Customer-visible deployed behavior | WhatsApp Web plus deployed-runtime logs |
   | End-to-end callback into local code | A separately authorized public ingress and callback change |

   A server bound to `127.0.0.1` cannot receive Meta callbacks from WhatsApp.
   Do not expose it through a tunnel or change a WABA callback merely to test it
   unless the owner explicitly authorizes those external changes.

Read [runtime-observation.md](references/runtime-observation.md) before
starting a local server or opening runtime logs.

## Run local FastAPI observation safely

Use a local process to inspect startup, route, and controlled-test logs. Do not
source `.env` files or echo AWS settings. Require the owner-provided bootstrap
variables before importing an app, because settings load during startup.

1. Select an unused port and bind only to `127.0.0.1`.
2. Start exactly one app worker in an interactive terminal session.
3. Check its matching local `/healthz` endpoint and retain only redacted,
   scenario-relevant log lines.
4. Stop the process after the bounded test. Local logs do not establish that a
   deployed app handled a WhatsApp message.

When Codex starts the process, keep the session identifier, poll its output
after each controlled request, and report the server process and port. When the
owner starts it, ask them to provide only the relevant redacted log excerpt.

## Check the deployed runtime before live messaging

1. Establish that the deployed target has the intended revision. If this cannot
   be established, a WhatsApp interaction may be a connectivity test only and
   code verification is `INCONCLUSIVE`.
2. Check health and inspect the narrow log window around the intended probe.
   Use the app-owned Fly manifest to identify the target; do not guess an app
   name or modify cloud configuration.
3. Run focused automated checks first, then Ruff and the full suite for
   cross-cutting runtime changes.

## Run the browser loop with Computer Use

When the task depends on the existing signed-in Chrome WhatsApp Web session,
use Computer Use rather than replacing it with a different browser session.

1. Claim the existing `web.whatsapp.com` tab without reloading it. Locate the
   owner-approved chat and verify the visible header before using the composer.
2. Call `sky.get_app_state` immediately before **every** UI action and again
   after it. Accessibility indices and screenshots are state-specific; never
   reuse a stale index or coordinate.
3. Use the visible text, timestamps, and direction to distinguish the new
   outbound probe from an old message or a fresh app response. Capture a
   screenshot only when accessibility text is insufficient.
4. Send the agreed low-risk probe once. Wait on a bounded schedule (about 10,
   30, and 60 seconds for a quick smoke test); do not send automatic follow-ups.
   Keep the owner updated at least once a minute while waiting.
5. For an interactive menu, reset between independent flows when state could
   affect the result. Stop before any destructive or externally visible branch
   unless that precise branch is authorized.

## Correlate and classify

Correlate a safe marker, send time, or redacted message-id suffix with the
target runtime. Check only stages relevant to the change:

- webhook receipt and signature outcome;
- selected WABA namespace and restaurant runtime;
- deduplication and intended callback/graph route;
- outbound response result; and
- exceptions, retries, cross-app handling, or duplicate replies.

Classify the scenario:

- `PASS` — target revision is established, expected fresh reply appears, and
  matching runtime evidence shows correct handling without duplicate/cross-app
  effects.
- `FAIL` — evidence establishes an incorrect reply, exception, wrong route,
  duplicate, or rejected outbound call.
- `INCONCLUSIVE` — revision/log correlation is unavailable, the observation
  window expires, browser access fails, or external state prevents attribution.

Use this handoff format. Ask before persisting live-chat evidence in the repo.

```text
WhatsApp verification
- App / environment / revision:
- Test-chat alias and authorized scope:
- Scenario and expected result:
- Local server / health / log evidence:
- Probe sent at / delivery state:
- Fresh reply at / latency / redacted summary:
- Runtime-log correlation:
- Automated checks:
- Result: PASS | FAIL | INCONCLUSIVE
- Side effects performed or deliberately avoided:
- Follow-up:
```
