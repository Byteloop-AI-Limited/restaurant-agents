# ADR-0022: Disable Webhook Signature Validation

- Status: Accepted
- Date: 2026-08-17
- Decision owners: Restaurant platform owner

## Context

`WabaBusinessSettings.create_async_client` passed `validate_updates=WABA_VALIDATE_UPDATES`
to PyWa, and `WABA_VALIDATE_UPDATES` was `True` by explicit constitutional
requirement (`CONSTITUTION.md`, App Factory Bootstrap, item 4). PyWa uses this
flag to verify Meta's `X-Hub-Signature-256` header against the configured
`app_secret` before dispatching any handler; an invalid signature returns
`200` and drops the update silently.

`docs/incorrect-waba-config-no-response-issue.md` documents a confirmed
2026-07-29 SFCS incident with this exact shape: `app_id`/`app_secret` loaded
from a Meta app different from the one that issued the WABA token, causing
every inbound message to be acknowledged but never processed. That
postmortem's explicit conclusion was to keep `validate_updates=True` and fix
the credentials instead, since the older standalone app's
`validate_updates=False` was identified as the reason the mismatch went
unnoticed for as long as it did.

During the ELAS rollout, local/ngrok testing repeatedly hit friction from
signature validation — compounded by an unconfirmed credential mismatch
found for the `elas_waa_*` namespace (`app_id`/`app_secret` identical to
BNAT's, not yet verified against ELAS's own Meta App Basic Settings). The
owner weighed this against the incident doc's guidance and decided to
disable validation platform-wide rather than gate the fix behind confirming
every namespace's credentials first.

## Decision

`WABA_VALIDATE_UPDATES = False` for every app, permanently. This is a
module-level constant in `config/waba_setting.py`, so the change is
process-wide with no per-namespace override and no app-owned opt-in/out —
consistent with every other WABA-client construction detail in that module.

This explicitly supersedes `CONSTITUTION.md`'s prior item-4 requirement and
`docs/incorrect-waba-config-no-response-issue.md`'s "the monorepo
intentionally keeps validation enabled" framing. That document's credential-
consistency advice (`app_id`/`app_secret`/`token` must belong to the same
Meta app) remains good practice — mismatched credentials still break
`override_waba_callback_url` and media-template creation, which use `app_id`
independently of signature checking — but it no longer determines whether
inbound messages are processed.

## Consequences

- **The webhook endpoint no longer authenticates its caller.** Any party
  that can reach a deployed app's webhook URL can submit a payload PyWa will
  treat as a genuine Meta update; there is no signature check standing
  between an arbitrary HTTP client and the graph, WhatsApp send, or database
  side effects a crafted payload can trigger. This is a real, currently
  accepted exposure across BNAT, SFCS, and ELAS, not a theoretical one.
- The specific SFCS incident's *symptom* (mismatched credentials silently
  dropping messages) cannot recur, because the check that dropped them is
  off. The *underlying* credential mismatch can still exist undetected — it
  just no longer announces itself through dropped messages. Anyone
  debugging a "no response" issue going forward should not expect that
  failure mode to reproduce, and should not assume matching credentials from
  the absence of it.
- `/details`'s `validate_updates` field now reports `false` for every app;
  this is expected, not a misconfiguration to chase.
- Re-enabling validation later requires no code change beyond flipping the
  constant back — but per the incident doc, every namespace's
  `app_id`/`app_secret`/`token` triple should be confirmed against the same
  Meta app first, or the original SFCS failure mode returns immediately.

## Code References (Machine-Readable)

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/config/waba_setting.py
symbol: WABA_VALIDATE_UPDATES
feature: disable-webhook-signature-validation
description: >
  Module-level constant, now False for every app; passed as validate_updates
  to the async WhatsApp client construction.
```

```code-ref
file: packages/restaurant-agent-runtime/src/restaurant_agent_runtime/waba_callback.py
symbol: runtime_waba_details
feature: disable-webhook-signature-validation
description: >
  Surfaces the effective validate_updates value on /details for operational visibility.
```
