# WaLocation client integration — customer rider-location on the delivery agent

## Context

Today a retained delivery customer who asks "where is my rider?" always gets the
same placeholder, no matter how far along the delivery is. `answer_general_query`
(`delivery.py:454-465`) keyword-matches the question and returns
`RIDER_LOCATION_PENDING_MESSAGE` unconditionally, and the prompts explicitly
forbid the legacy `send_rider_live_location_link` tool. That was deliberate: the
paid-retained-flow work shipped the placeholder as a prerequisite, waiting for
Ordelo's WaLocation module to land.

Ordelo's side is now complete — `POST /wa-request-location` is live
(`OrdeloAgent/watomation/routers/wa_location_hooks.py:34`). This change implements
the restaurant-agents half of the contract in
`OrdeloAgent/docs/wa_location_restaurant_agents_integration.md`:

- a new customer-facing delivery tool that asks Ordelo for the rider's location
  once the food is confirmed picked up, and
- a public callback route that receives Ordelo's result and sends the customer a
  real WhatsApp location pin.

Outcome: after pickup, the customer gets an actual pin instead of a placeholder.
Before pickup, behaviour is byte-identical to today.

## Decisions and assumptions

- **Additive, per your call.** `send_rider_live_location_link`,
  `AgentState.rider_live_location_url`, and the map-URL construction at
  `rider_event_hooks.py:204` all stay. §14 of the Ordelo plan wants them removed;
  that is deferred to a follow-up.
  - Two halves of "never use the legacy location path", enforced differently.
    *Fallback after* `request_rider_location` is structural: every return path
    ends in an `AIMessage("/DoNotRespond: …")`, and `cleanup_before_model`
    (`agent_harness.py:402-429`) jumps the graph to `end` on that marker, so
    there is no second tool call. *Initial selection* is not — with
    `send_rider_live_location_link` still registered and still fed by
    `rider_event_hooks.py:204`, the model can reach for it first and send a link
    instead of a pin. Under the additive choice the prompt bullet in step 7 is
    the only thing steering that, so it is load-bearing, not decoration.
- **Callback route lives on the existing rider router**, giving
  `POST /rider-event-hooks/{rest_ref}/wa-location-response` — the exact URL shape
  in the contract's example (integration doc line 59). No new `app_factory` flag.
- **The tool owns every customer-visible location string.** The rider-location
  keyword branch in `answer_general_query` (`:454-465`) stays but stops emitting
  customer copy — it becomes a steering `ToolMessage` pointing at
  `request_rider_location`. It cannot simply be deleted: the branch directly
  below (`:467-471`) matches `"where"` and `"location"`, so "where is my food"
  would start answering with the *restaurant's street address*.
  `RIDER_LOCATION_PENDING_MESSAGE` keeps its curly apostrophes verbatim
  (`test_graph_contract.py:187` asserts the string is present in both prompts).
- **`OrdeloService.request_rider_location()` must not swallow status codes.**
  Every other method catches `httpx.HTTPError` and returns `None`
  (`ordelo_service.py:71-73`), which collapses 403/404/409/422/502 into one
  value. This one returns a typed result carrying `status_code` and the
  `detail.code` string. Explicit `timeout=10.0`, matching
  `submit_restaurant_feedback` (`ordelo_service.py:136`) — without it a hung
  Ordelo hangs the customer's turn.
- **Idempotency key**: the inbound WhatsApp message id is not currently plumbed
  into the graph (`on_message_graph_handler.py:281` passes only `human_msg` and
  `recipient`; `reply_to_msg_id` holds *outbound* ids from
  `order_event_hooks.py:192`). Plumb it as an optional `ContextSchema` field —
  four non-breaking lines through an existing seam — so the key is
  `rest_ref:order_number:requester_id:wa_msg_id` as the contract prefers. Fall
  back to omitting the key when unavailable (`idempotency_key` is optional on
  Ordelo's model, `wa_location_pymodels.py:32`).
- **Restaurant-admin requests (`location_requested_by="restaurant_admin"`) are
  out of scope.** Customer path only.

## Implementation

### 1. Typed models — new file

`packages/restaurant-agent-runtime/src/restaurant_agent_runtime/services/ordelo_service/datamodels/wa_location_pymodel.py`

Mirror `OrdeloAgent/ordelo_datamodels/wa_location_pymodels.py` for the wire
shapes we send and receive:

- `WaLocationRequest` — `rest_ref`, `order_number`, `location_requested_by`,
  `requester_id`, `callback_url`, `idempotency_key: str | None`.
- `WaLocationRequestOutcome` — `status_code: int`, `status: str | None`,
  `code: str | None`, `request_id: str | None`. Not a wire model; the typed
  result of the HTTP call.
- `WaLocationPoint` — `latitude: float`, `longitude: float`, `source`,
  `observed_at`.
- `WaLocationCallbackPayload` — `request_id`, `order_number`, `customer_id`,
  `rider_id`, `location_requested_by`, `requester_id`, `location: WaLocationPoint`.
  Use `ConfigDict(extra="ignore")` here (not `forbid`) so an Ordelo-side field
  addition doesn't 422 the callback and lose a pin.
- `build_wa_location_callback_url(base_url: str, rest_ref: str) -> str` —
  `f"{base_url.rstrip('/')}/rider-event-hooks/{rest_ref}/wa-location-response"`.
  **The `rstrip` is load-bearing**: the seeded `SFCS_APP_URL` ends in `/`
  (`datamodels/config_updates.sql:19`), a double slash makes FastAPI redirect,
  and Ordelo does not follow redirects — that path ends in
  `502 callback_delivery_failed` with no pin and no retry.

### 2. `OrdeloService.request_rider_location()`

`packages/.../services/ordelo_service/ordelo_service.py`

Follow `submit_restaurant_feedback` (`:127-146`) — `_get_base_url()`, per-call
`httpx.AsyncClient`, loguru brace logging — with two departures: **no
`raise_for_status()`**, and read `response.json().get("detail", {}).get("code")`
on non-2xx. Post to `f"{base_url}/wa-request-location"` (root-level, not under
`/customer-hooks/`). Return `WaLocationRequestOutcome`; on `httpx.HTTPError` or
unparseable body return `status_code=0` so the caller maps it to the generic
safe reply.

### 3. Fixed customer copy

`packages/.../rest_agent/specialist_lifecycle.py`, beside the existing
`RIDER_LOCATION_PENDING_MESSAGE` (`:43-45`, unchanged) — so tests assert
constants rather than literals:

- `RIDER_LOCATION_REQUESTED_MESSAGE` — "I have asked the rider to share their
  current location. I will send it here when they respond."
- `RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE` — delivery no longer active, the
  rider will not be contacted.
- `RIDER_LOCATION_UNAVAILABLE_MESSAGE` — generic safe reply for every
  authorization/validation/transport failure.
- `RIDER_LOCATION_NO_ORDER_MESSAGE` — no active delivery order to locate.

### 4. `request_rider_location` tool

`packages/.../rest_agent/agents/delivery.py`

Bare `async def` (no `@tool` — wrapping happens once at `:778`), signature
matching `check_delivery_driver_allocation_status` (`:565-570`): `state`
(`InjectedState`), `tool_call_id` (`InjectedToolCallId`), `runtime`
(`ToolRuntime[ContextSchema]`), **no LLM-visible arguments**. Every request field
comes from `state` / `ctx`.

Local guards before any HTTP call:

1. `state.get("order_number")` missing → `RIDER_LOCATION_NO_ORDER_MESSAGE`.
2. `state.get("is_delivery_picked_up") is not True` →
   `RIDER_LOCATION_PENDING_MESSAGE`, **zero Ordelo calls**.

Then build the request from `ctx.rest_ref`, `ctx.recipient`,
`ctx.operational_lookups.get_app_url(ctx.rest_ref)` (already permitted by
`_normalize_app_ref`, `operational_lookup_cache.py:207-211`) and call the
service.

Response mapping:

| Result | WhatsApp send | Reply text |
| --- | --- | --- |
| `200 location_available` | **none** — the callback already sent the pin | audit-only `ToolMessage` |
| `202 rider_prompted` / `waiting_for_rider` | one send | `RIDER_LOCATION_REQUESTED_MESSAGE` |
| `409 food_not_picked_up` | one send | `RIDER_LOCATION_PENDING_MESSAGE` |
| `409 delivery_not_inflight` | one send | `RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE` |
| `403` / `404` / `409 delivery_not_active` / `422` / `502` / transport | one send | `RIDER_LOCATION_UNAVAILABLE_MESSAGE`, code logged |

**The 200 asymmetry is the easiest thing to flatten by mistake.** Note that
`respond_on_wa` (`agent_harness.py:432-483`) does *not* send when it sees the
marker — it only strips it. So every non-200 branch must
`await ctx.wa_client.send_message(to=ctx.recipient, text=…, reply_to_message_id=state.get("reply_to_msg_id"))`
itself, exactly like `check_delivery_driver_allocation_status` (`:596-605`),
before returning. The 200 branch sends nothing.

All branches return:

```python
Command(update={"messages": [
    ToolMessage(<audit text>, tool_call_id=tool_call_id),
    AIMessage(f"/DoNotRespond: {text}"),
]})
```

The `AIMessage` must be last — both middlewares only inspect `messages[-1]`.

Also in this file, `answer_general_query`'s rider-location branch (`:454-465`)
keeps its phrase list and its position **above** the generic `"where"`/`"location"`
branch, but its body changes from `return RIDER_LOCATION_PENDING_MESSAGE` to a
steering string — `"Call `request_rider_location` to answer this."` — matching
the existing convention at `:755`. That is a `ToolMessage` the model reads, not
customer copy, and it carries no `/DoNotRespond`, so the model continues and
calls the real tool on the next step. The branch stays unconditional: the tool
already distinguishes pre- and post-pickup itself. Deleting the branch outright
is the trap — the phrases would fall through to `:467-471` and answer a
rider-location question with the restaurant's street address.

Then insert `request_rider_location` into `delivery_tools` (`:762-776`)
immediately after `send_rider_live_location_link`. The list must stay a flat list
of bare names — `test_graph_contract.py:86-92` AST-parses it and rejects anything
but `ast.Name`.

### 5. Inbound message id plumbing

- `agent_harness.py` `ContextSchema` (`:118-146`): add `wa_msg_id: str | None = None`.
- `agent_runner.py` `run_rest_graph_with_custom_msg` (`:243-257`): add
  `wa_msg_id: str | None = None` parameter, pass into the `ContextSchema(...)`
  construction at `:342-358`.
- `on_message_graph_handler.py`: pass `wa_msg_id=msg.id` at **every**
  `run_rest_graph_with_custom_msg` call site that can reach the delivery agent —
  `:281` and the service-selection path at `:273` — so the key is stable
  whichever route the question arrives on.

Optional in the strict sense — the tool degrades to omitting `idempotency_key` —
but it is what makes a replayed webhook reuse one key instead of prompting the
rider twice.

### 6. Callback route

`packages/.../watomation/routers/rider_event_hooks.py` — append
`@router.post("/{rest_ref}/wa-location-response")` taking
`payload: WaLocationCallbackPayload`, `runtime`, `graph_adapter`.

Thin and deterministic, no graph invocation, no assistant message. Order:

1. `validate_rest_ref(rest_ref, runtime)` — 404 on restaurant mismatch (this is
   the only 404 the route emits).
2. Resolve the thread **without creating one**. `debug_state_values(recipient=…)`
   routes through `get_config_for_recipient` → `ThreadHandler.get_or_create_thread`,
   which mints a thread row for an unknown customer — that would violate the
   contract's "mutate no conversation state" for a failed guard. Instead follow
   the precedent at `thread_hooks.py:211-228`:
   `ThreadHandler(await runtime.settings.database.get_pool(), agent=runtime.identity.rest_ref).get_active_thread(payload.customer_id)`.
   No active thread → `409`. Then read state with the explicit config form:
   `graph_adapter.debug_state_values(config={"configurable": {"thread_id": …, "recipient": payload.customer_id}})`.
3. Read failure (wrap in `try/except` like `rider_event_hooks.py:79-86`) → `409`.
4. `SpecialistFlowView.from_state(state)` (`specialist_lifecycle.py:59-69`) and
   require **all** of: `flow.owns_specialist_work`,
   `flow.active_agent == "delivery_agent"`,
   `state.get("order_number") == payload.order_number`,
   `flow.is_delivery_picked_up`. Also require
   `payload.location_requested_by == "customer"` and
   `payload.requester_id == payload.customer_id`. Any failure → log and `409`,
   sending nothing.
5. Label: `whatsapp_current` → "Rider's latest location";
   `restaurant_confirmation` → "Last known at restaurant" (never presented as
   current GPS).
6. `await runtime.async_wa_client.send_location(to=payload.customer_id, latitude=…, longitude=…, name=label)`.
   This is the per-app injected client — never a process global.
   `pywa_async.WhatsApp.send_location` already exists with exactly this
   signature; no client wrapper needed.
7. `204` only after the send returns. Send raises → log and `502`.

### 7. Prompts — both apps

`apps/sfcs/src/sfcs_agent/rest_agent/prompts/delivery_multiagent_prompt.md:8`
and `apps/bnat/.../delivery_multiagent_prompt.md:9`.

Replace the "do not call the legacy live-location tool" clause with the
three-way distinction from §12 of the Ordelo plan:

- `check_delivery_driver_allocation_status` — whether a rider is assigned.
- `request_rider_location` — the sole tool for a rider-location request; it
  handles both the picked-up and not-yet-picked-up cases itself.
- never call `send_rider_live_location_link`.

**Keep the sentence "We will share the rider's location with you once it's
available." verbatim, curly apostrophes intact** — `test_graph_contract.py:187`
asserts it. Reframe it as what the tool replies before pickup rather than as an
instruction for the model to type.

### 8. Docs

`docs/delivery_whatsapp_agent.md`, `docs/webhook_endpoints.md` (new route),
`docs/glossary.md`, `docs/domain/platform-domain-model.md`, and a new ADR under
`docs/adr/` for the cross-repo contract (index it in `docs/adr/README.md`).

## Tests

`pytest` + `pytest-asyncio` in `asyncio_mode = "auto"` — bare `async def`, no
marker. Note `tests/legacy_contract/` is excluded from collection
(`pyproject.toml:35`); don't copy those patterns.

**Contract pin** — `tests/rest_agent/test_graph_contract.py`: add
`"request_rider_location"` to `STANDARD_TOOLS["delivery.py"]` at the position
matching `delivery_tools`.

**Service** — `tests/services/ordelo_service/test_ordelo_service.py`: the
existing `FakeResponse` has no `status_code` and `FakeAsyncClient.post` has no
`**kwargs` (`:48-84`). Widen both, then cover 200 / 202 / each 409 code / 403 /
404 / 422 / 502 / `httpx.HTTPError` → correct `WaLocationRequestOutcome`, and
assert the posted body and the `rstrip`ed callback URL.

**Tool** — new `tests/rest_agent/agents/test_delivery_agent.py`, following the
`SimpleNamespace` + `AsyncMock` style of `test_agent_harness.py:76-98`:

- pre-pickup → exact placeholder, `wa_client.send_message` awaited once,
  **service never called**;
- picked up → request body is state-derived (`order_number`, `requester_id`,
  `rest_ref`) with the app-specific callback URL and the
  `rest_ref:order_number:requester_id:wa_msg_id` key;
- `202` (both statuses) → one acknowledgement, `messages[-1]` carries
  `/DoNotRespond:`;
- `200 location_available` → **no** `send_message` at all;
- each conflict/error code → its fixed constant, and no legacy-tool call;
- `answer_general_query("where is my food")` and `("track my order")` → the
  steering string, **not** the restaurant address and not customer-facing copy.
  This is the regression test for the fall-through trap in step 4.

**Callback route** — new `tests/watomation/routers/test_wa_location_hooks.py`,
using `TestClient` over the real `create_restaurant_app` like
`tests/test_runtime_isolation.py:111-127`, with the `FakeWaClient` from
`tests/_stubs/agent_stubs.py:22-31` (its `sent_locations` list already exists and
has no production caller today):

- valid retained picked-up matching order → one `send_location` with the right
  `to`/lat/lon and 2xx;
- missing thread / unreadable state / `retain_thread=False` /
  `active_agent != "delivery_agent"` / pre-pickup / wrong `order_number` /
  wrong customer → nothing sent, non-2xx, **and no thread row created**;
- `restaurant_confirmation` source → pin labelled "Last known at restaurant";
- `send_location` raising → non-2xx;
- wrong `rest_ref` in path → 404.

## Verification

```bash
uv run pytest tests/ -q
uv run ruff check .
```

End to end, against a deployed pair (both services must be publicly reachable —
Ordelo rejects non-public callback URLs at
`OrdeloAgent/ordelo/wa_location.py:473-503`):

1. Confirm `SFCS_APP_URL` and **`BNAT_APP_URL`** are seeded in the shared
   `ordelo_config` table. Only ELAS/ORDELO/SFCS appear in
   `datamodels/config_updates.sql`; a missing BNAT row raises at
   `operational_lookup_cache.py:83`. Bust the 1 h TTL after any edit with
   `POST /internal/cache/reset?scope=operational_config&app_ref=BNAT`.
2. Ordelo needs the new hook registered in its own
   `config/params.py::WEBHOOK_PATHS` map only if it ever builds this URL itself —
   it does not here, since we supply `callback_url` per request. No change needed.
3. Drive a real delivery to picked-up, ask "where is my rider?", and check the
   `202` path: customer gets the acknowledgement, rider gets WhatsApp's native
   location request, and the pin arrives on the rider's reply.
4. Ask again within five minutes for the cached `200` path: the pin arrives via
   the callback and the tool sends **no** second message.
5. Ask before pickup: the exact placeholder, and no row in Ordelo's WaLocation
   demand table.

**Watch on the `200` path.** It is re-entrant — Ordelo POSTs our callback while
the tool's own request is still open, so the app serves an inbound request during
its own outbound one. A single async uvicorn worker (`WEB_CONCURRENCY=1`,
`gunicorn_conf.py:8`) handles that, and the `max_size=5` pool
(`pg_setting.py:52`) covers the second connection the callback's state read
needs. Confirm in the logs that the callback completes before the tool's
`httpx` call returns, and that neither times out.

## Out of scope

- §14 legacy removal — `send_rider_live_location_link`,
  `AgentState.rider_live_location_url`, and the map URL at
  `rider_event_hooks.py:204` all stay, per your call. Worth a follow-up: the
  field is now written and never read on the new path.
- The restaurant-admin (`location_requested_by="restaurant_admin"`) request path.
- Any change to Ordelo — its side of the contract is already complete.
