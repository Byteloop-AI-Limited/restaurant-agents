---
name: verify-whatsapp-app-change
description: Run a bounded end-to-end WhatsApp verification for restaurant-agents code changes and record auditable evidence. Use after changes to an app's webhook handling, WABA/runtime configuration, message routing, deduplication, graph behavior, prompts, or outbound replies when validation requires sending a real probe through WhatsApp Web and waiting for the target app's response.
---

# Verify a WhatsApp App Change

Verify that the intended `restaurant-agents` runtime receives a deliberate
WhatsApp message and produces the expected response. Treat this as a live smoke
test after automated checks, not as a replacement for tests, Ruff, or log
inspection.

## Establish the test boundary

1. Read the repository instructions and governing architecture before acting.
2. Identify the target app (`sfcs` or `bnat`), environment, scenario, and code
   revision under test.
3. Confirm that the target runtime actually contains the revision. Do not deploy
   or change callbacks, WABA configuration, secrets, or cloud resources unless
   the user explicitly requests it.
4. Use only an owner-approved test chat. Never select a customer or rider chat
   merely because it is convenient.
5. Agree on the exact probe text and expected response. Prefer a non-sensitive,
   unique probe that exercises the changed path. Add a short correlation marker
   only when it will not change the scenario's semantics.
6. Avoid probes that create orders, payments, reservations, subscriptions, or
   other business side effects unless those effects are explicitly authorized.

Record the app, environment, revision, test chat alias, scenario, expected
behavior, and local time zone before sending.

## Run preflight checks

Run the smallest relevant automated checks first. Confirm the target service is
healthy and inspect its recent logs for an existing fault. Preserve unrelated
working-tree changes and never print credentials, tokens, phone numbers, or
secret-bearing URLs.

If the deployed revision cannot be established, continue only when the user
wants a connectivity check and label the final result `INCONCLUSIVE` for code
validation.

## Send the probe through WhatsApp Web

Use the user-requested browser surface. When Chrome is requested or an existing
signed-in Chrome WhatsApp Web tab is part of the task, use the available Chrome
control skill and its safety rules.

1. Claim the existing `https://web.whatsapp.com/` tab without reloading it.
2. Locate the exact approved chat and verify the chat header before editing the
   composer. Fail closed if the name is ambiguous.
3. Fill the composer with the exact agreed probe. Do not include secrets or
   unrelated personal data.
4. Ask for action-time confirmation immediately before pressing Enter or
   clicking Send. Sending a message represents the user to a third party, so an
   earlier blanket instruction does not replace this confirmation.
5. After confirmation, send once. Record the send time and the strongest visible
   state: `sent`, `delivered`, or `read`.

Do not infer application success from delivery alone. Delivery shows that
WhatsApp accepted and delivered the message; it does not prove that the changed
application processed it.

## Wait for a fresh reply

Capture the chat state immediately after sending, then check for a new inbound
message after a short interval. Compare message direction, timestamp, and content
against the sent probe; do not mistake an older message or the outbound probe for
a reply.

Use a bounded wait window agreed with the user. For a quick smoke test, check at
roughly 10, 30, and 60 seconds. Keep the user updated at least once per minute if
the window is longer. Avoid rapid polling and do not send automatic follow-ups.

If a reply arrives, record its time, content or redacted summary, and latency. If
no reply arrives by the deadline, preserve the delivered state and continue to
log correlation instead of immediately declaring failure.

## Correlate application evidence

Inspect only the target app's logs for the send/reply window. Correlate the probe
using a safe marker, timestamp, or redacted message identifier. Check the stages
relevant to the change:

- inbound webhook received and signature validation outcome;
- correct WABA namespace and restaurant runtime selected;
- deduplication decision;
- intended handler or graph path invoked;
- outbound reply attempted and accepted or rejected;
- exception, timeout, or retry evidence;
- absence of cross-app handling or duplicate replies.

Sanitize evidence. Record identifiers as short redacted suffixes or hashes when
needed; never store access tokens, app secrets, full phone numbers, message
payloads containing personal data, or secret-bearing URLs.

## Classify the result

- `PASS`: the tested revision/runtime is established, the probe is delivered, a
  fresh expected reply arrives, and logs show the target app handled the matching
  event without cross-app or duplicate side effects.
- `FAIL`: evidence establishes a defect, such as non-delivery caused by the
  tested system, rejected webhook processing, wrong app routing, an exception,
  duplicate handling, or a reply that contradicts the expected behavior.
- `INCONCLUSIVE`: the probe is delivered but no reply arrives without enough log
  evidence, the running revision is uncertain, the observation window expires,
  authentication/browser access is unavailable, or external WhatsApp/Meta state
  prevents attribution to the code change.

State exactly which automated checks, live actions, and log stages were or were
not verified. Never upgrade `INCONCLUSIVE` to `PASS` based only on a delivered or
read receipt.

## Evidence record

Use this compact structure in the handoff, issue, or PR note. Ask before writing
live-chat evidence to a repository file, and redact personal data by default.

```text
WhatsApp verification
- App / environment:
- Revision under test:
- Scenario:
- Test chat alias:
- Probe text or safe correlation marker:
- Sent at / delivery state:
- Reply at / latency:
- Reply summary:
- Application log correlation:
- Cross-app and duplicate check:
- Automated checks completed:
- Result: PASS | FAIL | INCONCLUSIVE
- Unverified boundaries / follow-up:
```
